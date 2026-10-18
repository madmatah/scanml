"""Run test pages through the OCR sandbox and score the results.

For each selected image of ``<testdata>/variants.json`` it calls
``POST /v1/parse`` on the sandbox socket, saves what came back under
``<testdata>/results/<run>/`` (Markdown, figure crops, raw JSON) and scores it:

* ``cer`` / ``wer``: character / word error rates of the reading text (table
  cells included, page furniture excluded) against the reference
  transcription (``groundtruth/<page>.txt``), after normalizing quotes,
  apostrophes and hyphens;
* ``page_ok``: the printed page number is among the detected ``page_numbers``;
* ``angle``: rotation applied by the orientation classifier.

It also samples the GPU memory (nvidia-smi, whole device) while it runs.
Engine-agnostic: the same command compares OCR engines or settings.

With DATA_DIR the stack's data directory (see .env):

    python3 -I ocr/bench/run_bench.py --run baseline --testdata "$DATA_DIR/testdata" --socket "$DATA_DIR/run/ocr.sock"
    python3 -I ocr/bench/run_bench.py --run unwarp --unwarp 1 --variant curved --variant combined \
        --testdata "$DATA_DIR/testdata" --socket "$DATA_DIR/run/ocr.sock"
    python3 -I ocr/bench/run_bench.py --run baseline --rescore \
        --testdata "$DATA_DIR/testdata"  # after a ground-truth change
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import statistics
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scanmylib_ocr.client import request_json

# -- text comparison -------------------------------------------------------------


def markdown_to_text(markdown: str) -> str:
    """Reading text of an OCR page, table cells included, without images or markup."""
    text = re.sub(r"<[^>]+>", " ", markdown)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = text.replace("**", "").replace("$", "")
    return html.unescape(text)


def normalize(text: str) -> str:
    """Remove differences of convention between transcriptions (not reading errors)."""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s*[\^_]\{\s*([^}]*?)\s*\}", r"\1", text)  # LaTeX super/subscripts: 0 ^{m},385
    text = re.sub(r"\.{2,}|…", " ", text)  # dot leaders of tables
    text = re.sub(r"[’‘′`´]", "'", text)
    text = re.sub(r"[«»“”„″]", '"', text)
    text = re.sub(r"(?<=\w)\s*-\s*(?=\w)", "", text)  # line-break hyphens differ by design
    text = re.sub(r"\s+([,.;:!?)\]\"])", r"\1", text)
    text = re.sub(r"([(\[\"])\s+", r"\1", text)
    return " ".join(text.split())


def _levenshtein(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b)))
        previous = current
    return previous[-1]


def error_rates(hypothesis: str, reference: str) -> tuple[float, float]:
    """(CER, WER). Words are aligned first; characters are compared within substituted words."""
    hyp, ref = hypothesis.split(), reference.split()
    rows, cols = len(ref) + 1, len(hyp) + 1
    cost = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        cost[i][0] = i
    for j in range(cols):
        cost[0][j] = j
    for i in range(1, rows):
        row, above = cost[i], cost[i - 1]
        word = ref[i - 1]
        for j in range(1, cols):
            row[j] = min(above[j] + 1, row[j - 1] + 1, above[j - 1] + (word != hyp[j - 1]))
    word_errors = cost[-1][-1]

    char_errors, i, j = 0, rows - 1, cols - 1
    while i > 0 or j > 0:
        if i > 0 and j > 0 and cost[i][j] == cost[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            if ref[i - 1] != hyp[j - 1]:
                char_errors += _levenshtein(ref[i - 1], hyp[j - 1])
            i, j = i - 1, j - 1
        elif i > 0 and cost[i][j] == cost[i - 1][j] + 1:
            char_errors += len(ref[i - 1]) + 1
            i -= 1
        else:
            char_errors += len(hyp[j - 1]) + 1
            j -= 1
    return char_errors / max(1, len(reference)), word_errors / max(1, len(ref))


# -- GPU memory -------------------------------------------------------------------


class GpuSampler(threading.Thread):
    """Peak memory used on the whole GPU (MiB) while the benchmark runs."""

    def __init__(self, interval_s: float = 0.5) -> None:
        super().__init__(daemon=True)
        self.interval_s = interval_s
        self.peak_mb = 0
        self._done = threading.Event()

    @staticmethod
    def used_mb() -> int:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True,
        ).stdout  # fmt: skip
        return int(output.split()[0])

    def run(self) -> None:
        while not self._done.is_set():
            try:
                self.peak_mb = max(self.peak_mb, self.used_mb())
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
            self._done.wait(self.interval_s)

    def stop(self) -> int:
        self._done.set()
        self.join()
        return self.peak_mb


# -- run ----------------------------------------------------------------------------


def save_result(directory: Path, response: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "page.md").write_text(response.get("markdown", ""), encoding="utf-8")
    images = response.get("images", [])
    if images:
        (directory / "imgs").mkdir(exist_ok=True)
    for image in images:
        name = Path(image["name"]).name
        (directory / "imgs" / name).write_bytes(base64.b64decode(image["data_b64"]))
    stripped = {**response, "images": [{k: v for k, v in i.items() if k != "data_b64"} for i in images]}
    (directory / "response.json").write_text(json.dumps(stripped, indent=1, ensure_ascii=False), encoding="utf-8")


def score(
    entry: dict[str, Any], response: dict[str, Any], testdata: Path, pages: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    page = pages.get(entry["page"], {})
    metrics: dict[str, Any] = {
        "file": entry["file"],
        "variant": entry["variant"],
        "blocks": len(response.get("blocks", [])),
        "images": len(response.get("images", [])),
        "tables": sum(1 for b in response.get("blocks", []) if b["label"] == "table"),
        "page_numbers": response.get("page_numbers", []),
        "page_ok": page.get("printed_page") in response.get("page_numbers", []),
        "angle": response.get("preprocess", {}).get("angle"),
        "unwarped": response.get("preprocess", {}).get("unwarped"),
        "infer_s": response.get("timings", {}).get("infer_s"),
    }
    truth = testdata / "groundtruth" / f"{entry['page']}.txt"
    if truth.exists():
        reference = normalize(truth.read_text(encoding="utf-8"))
        hypothesis = normalize(markdown_to_text(response.get("markdown", "")))
        metrics["cer"], metrics["wer"] = (round(rate, 4) for rate in error_rates(hypothesis, reference))
    return metrics


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in results if r.get("status") == 200]
    by_variant: dict[str, list[dict[str, Any]]] = {}
    for result in ok:
        by_variant.setdefault(result["variant"], []).append(result)

    def mean(values: list[float]) -> float | None:
        return round(statistics.fmean(values), 4) if values else None

    return {
        "pages": len(results),
        "succeeded": len(ok),
        "page_number_found": sum(1 for r in ok if r["page_ok"]),
        "median_infer_s": round(statistics.median([r["infer_s"] for r in ok]), 2) if ok else None,
        "by_variant": {
            variant: {
                "n": len(items),
                "cer": mean([r["cer"] for r in items if "cer" in r]),
                "wer": mean([r["wer"] for r in items if "wer" in r]),
                "page_ok": sum(1 for r in items if r["page_ok"]),
                "angles": sorted({r["angle"] for r in items}),
            }
            for variant, items in sorted(by_variant.items())
        },
    }


def write_summary(run_dir: Path, summary: dict[str, Any]) -> None:
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2, ensure_ascii=False))


def rescore(run_dir: Path, entries: list[dict[str, Any]], testdata: Path, pages: dict[str, dict[str, Any]]) -> None:
    """Recompute the scores of a past run from its saved responses (timings are kept)."""
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    by_file = {entry["file"]: entry for entry in entries}
    results = []
    for result in summary["results"]:
        if result.get("status") == 200 and result["file"] in by_file:
            saved = run_dir / Path(result["file"]).stem / "response.json"
            response = json.loads(saved.read_text(encoding="utf-8"))
            result = {**result, **score(by_file[result["file"]], response, testdata, pages)}
        results.append(result)
    summary.update(summarize(results), results=results)
    write_summary(run_dir, summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True, help="name of this run (results/<run>/)")
    parser.add_argument("--testdata", type=Path, required=True, help="the test pages (DATA_DIR/testdata)")
    parser.add_argument("--socket", help="the sandbox's socket (DATA_DIR/run/ocr.sock); not needed with --rescore")
    parser.add_argument("--variant", action="append", help="only these variants (scan, curved, ...)")
    parser.add_argument("--page", action="append", help="only these pages (page ids of sources.json)")
    parser.add_argument("--orientation", default="1")
    parser.add_argument("--unwarp", default="0")
    parser.add_argument("--rescore", action="store_true", help="score the saved responses of --run again")
    args = parser.parse_args()
    if not args.socket and not args.rescore:
        parser.error("--socket is required, except with --rescore")

    entries = json.loads((args.testdata / "variants.json").read_text())
    entries = [e for e in entries if (not args.variant or e["variant"] in args.variant)]
    entries = [e for e in entries if (not args.page or e["page"] in args.page)]
    pages = {p["page"]: p for p in json.loads((args.testdata / "pages.json").read_text(encoding="utf-8"))}
    run_dir = args.testdata / "results" / args.run
    if args.rescore:
        rescore(run_dir, entries, args.testdata, pages)
        return
    run_dir.mkdir(parents=True, exist_ok=True)

    sampler = GpuSampler()
    sampler.start()
    results = []
    started = time.monotonic()
    for entry in entries:
        image = (args.testdata / entry["file"]).read_bytes()
        query = f"orientation={args.orientation}&unwarp={args.unwarp}&request_id=bench-{Path(entry['file']).stem}"
        sent = time.monotonic()
        status, response = request_json(
            args.socket, "POST", f"/v1/parse?{query}", body=image, headers={"Content-Type": "image/jpeg"}
        )
        wall_s = round(time.monotonic() - sent, 2)
        result = {"file": entry["file"], "variant": entry["variant"], "status": status, "wall_s": wall_s}
        if status == 200:
            save_result(run_dir / Path(entry["file"]).stem, response)
            result.update(score(entry, response, args.testdata, pages))
            result["timings"] = response.get("timings")
        else:
            result["error"] = response
        results.append(result)
        print(json.dumps({k: v for k, v in result.items() if k not in ("timings",)}, ensure_ascii=False), flush=True)
    total_s = time.monotonic() - started
    peak_mb = sampler.stop()

    summary = {
        "run": args.run,
        "options": {"orientation": args.orientation, "unwarp": args.unwarp},
        "total_s": round(total_s, 1),
        "pages_per_min": round(len(entries) / total_s * 60, 1) if entries else None,
        "gpu_peak_used_mb": peak_mb,
        **summarize(results),
        "results": results,
    }
    write_summary(run_dir, summary)


if __name__ == "__main__":
    main()
