"""Measure the engine lifecycle of the OCR sandbox: cold start, speed, VRAM, unload.

Steps: make sure the engine is unloaded, read the GPU memory baseline, load the
engine (``POST /v1/load``) and time it until ``/health`` says ready, OCR the
clean test pages one after another (like the api's loop), then unload and
check that the GPU memory is back to the baseline. With ``--idle-unload S``
it instead waits for the automatic unload after one more page.

VRAM figures come from nvidia-smi on the host: whole-device usage, and the
per-process usage of the sandbox processes.

With DATA_DIR the stack's data directory (see .env):

    python3 -I ocr/bench/measure.py --label gpu030 --testdata "$DATA_DIR/testdata" --socket "$DATA_DIR/run/ocr.sock"
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_bench import GpuSampler, request_json  # noqa: E402


def compute_processes() -> list[dict]:
    output = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    processes = []
    for line in output.strip().splitlines():
        pid, name, used = (field.strip() for field in line.split(","))
        processes.append({"pid": int(pid), "name": name, "used_mb": int(used)})
    return processes


def health(socket_path: str) -> dict:
    status, body = request_json(socket_path, "GET", "/health", timeout=10)
    if status != 200:
        raise RuntimeError(f"/health answered {status}")
    return body


def wait_for_state(socket_path: str, wanted: str, timeout_s: float) -> float:
    started = time.monotonic()
    while time.monotonic() - started < timeout_s:
        engine = health(socket_path)["engine"]
        if engine["state"] == wanted:
            return time.monotonic() - started
        if engine["state"] == "error":
            raise RuntimeError(f"engine error: {engine['last_error']}")
        time.sleep(0.25)
    raise TimeoutError(f"engine not {wanted} after {timeout_s:.0f} s")


def parse(socket_path: str, path: Path) -> dict:
    status, body = request_json(
        socket_path, "POST", f"/v1/parse?request_id=measure-{path.stem}",
        body=path.read_bytes(), headers={"Content-Type": "image/jpeg"},
    )  # fmt: skip
    if status != 200:
        raise RuntimeError(f"{path.name}: HTTP {status}: {body}")
    return body


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", required=True, help="name of the measurement (results/measure-<label>.json)")
    parser.add_argument("--testdata", type=Path, required=True, help="the test pages (DATA_DIR/testdata)")
    parser.add_argument("--socket", required=True, help="the sandbox's socket (DATA_DIR/run/ocr.sock)")
    parser.add_argument("--idle-unload", type=float, help="wait for the automatic unload (OCR_IDLE_UNLOAD_S)")
    args = parser.parse_args()
    pages = sorted((args.testdata / "pages").glob("*.jpg"))

    request_json(args.socket, "POST", "/v1/unload")
    time.sleep(2)
    baseline_mb = GpuSampler.used_mb()

    sent = time.monotonic()
    status, _ = request_json(args.socket, "POST", "/v1/load")
    wait_for_state(args.socket, "ready", 900)
    cold_start_s = round(time.monotonic() - sent, 1)
    loaded_mb = GpuSampler.used_mb()
    processes = compute_processes()

    sampler = GpuSampler(interval_s=0.25)
    sampler.start()
    first = parse(args.socket, pages[0])
    started = time.monotonic()
    timings = [parse(args.socket, page)["timings"]["infer_s"] for page in pages]
    batch_s = time.monotonic() - started
    peak_mb = sampler.stop()

    result = {
        "label": args.label,
        "settings": {
            k: v for k, v in health(args.socket)["engine"].items() if k in ("name", "backend", "idle_unload_s")
        },
        "gpu_baseline_mb": baseline_mb,
        "load_request_status": status,
        "cold_start_s": cold_start_s,
        "first_page_s": first["timings"]["infer_s"],
        "warm_page_s_median": round(statistics.median(timings), 2),
        "warm_page_s_max": round(max(timings), 2),
        "pages": len(pages),
        "batch_s": round(batch_s, 1),
        "pages_per_min": round(len(pages) / batch_s * 60, 1),
        "vram_loaded_mb": loaded_mb - baseline_mb,
        "vram_peak_mb": peak_mb - baseline_mb,
        "gpu_processes_loaded": processes,
    }

    if args.idle_unload:
        parse(args.socket, pages[0])
        result["idle_unload_after_s"] = round(wait_for_state(args.socket, "idle", args.idle_unload + 120), 1)
    else:
        unload_started = time.monotonic()
        request_json(args.socket, "POST", "/v1/unload")
        result["unload_s"] = round(time.monotonic() - unload_started, 1)
    time.sleep(2)
    result["vram_after_unload_mb"] = GpuSampler.used_mb() - baseline_mb
    result["gpu_processes_after_unload"] = compute_processes()

    output = args.testdata / "results" / f"measure-{args.label}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
