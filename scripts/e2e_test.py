#!/usr/bin/env python3
"""End-to-end test of a running ScanMyLib stack, acting like the phone app.

Creates a document, uploads page photos out of order over two "sessions",
waits for the OCR sandbox to process them, then checks the organized library
on disk (document.md, per-page files, illustrations, INDEX.md).

Standard library only, so it runs with the system python3:

    scripts/e2e_test.py IMAGE [IMAGE...] [--api http://127.0.0.1:8765]
                        [--token-file /data/user/scanmylib/state/token]
                        [--library /home/user/Documents/ScanMyLib] [--timeout 900]
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import random
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path


class Api:
    """Minimal client for the ScanMyLib HTTP API (docs/API.md)."""

    def __init__(self, base: str, token: str) -> None:
        self.base = base.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}", "X-ScanMyLib": "1"}

    def request(self, method: str, path: str, body: bytes | None = None,
                content_type: str | None = None) -> tuple[int, bytes]:
        headers = dict(self.headers)
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(self.base + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as err:
            return err.code, err.read()

    def json(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        body = json.dumps(payload).encode() if payload is not None else None
        status, data = self.request(method, path, body, "application/json" if body else None)
        return status, (json.loads(data) if data else {})

    def upload(self, doc_id: str, image: Path, fields: dict[str, str]) -> tuple[int, dict]:
        boundary = uuid.uuid4().hex
        parts = []
        for name, value in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        mime = mimetypes.guess_type(image.name)[0] or "image/jpeg"
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{image.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n".encode() + image.read_bytes() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        status, data = self.request("POST", f"/api/documents/{doc_id}/pages", b"".join(parts),
                                    f"multipart/form-data; boundary={boundary}")
        return status, (json.loads(data) if data else {})


def check(condition: bool, message: str, failures: list[str]) -> None:
    print(("  ok    " if condition else "  FAIL  ") + message)
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--api", default="http://127.0.0.1:8765")
    parser.add_argument("--token-file", type=Path, default=Path("/data/user/scanmylib/state/token"))
    parser.add_argument("--library", type=Path, default=Path.home() / "Documents" / "ScanMyLib")
    parser.add_argument("--title", default=f"Test E2E {datetime.now():%Y-%m-%d %H:%M:%S}")
    parser.add_argument("--timeout", type=int, default=900, help="seconds to wait for OCR")
    args = parser.parse_args()

    api = Api(args.api, args.token_file.read_text().strip())
    failures: list[str] = []

    print(f"== API {args.api}")
    status, health = api.json("GET", "/api/health")
    check(status == 200 and health.get("name") == "ScanMyLib", f"health: {status} {health}", failures)
    status, _ = Api(args.api, "wrong-token").json("GET", "/api/status")
    check(status == 401, f"wrong token rejected ({status})", failures)

    doc_id = str(uuid.uuid4())
    status, doc = api.json("PUT", f"/api/documents/{doc_id}", {"title": args.title, "kind": "book"})
    check(status == 201, f"document created: {doc.get('slug')}", failures)
    status, _ = api.json("PUT", f"/api/documents/{doc_id}", {"title": args.title, "kind": "book"})
    check(status == 200, "document upsert is idempotent", failures)

    # Upload out of order, split into two capture sessions.
    images = list(args.images)
    random.Random(42).shuffle(images)
    half = (len(images) + 1) // 2
    page_ids = []
    print(f"== Uploading {len(images)} pages (shuffled, 2 sessions)")
    for session_images in (images[:half], images[half:]):
        session_id = str(uuid.uuid4())
        for seq, image in enumerate(session_images):
            page_id = str(uuid.uuid4())
            fields = {"page_id": page_id, "session_id": session_id, "seq": str(seq),
                      "captured_at": datetime.now(timezone.utc).isoformat()}
            status, page = api.upload(doc_id, image, fields)
            check(status == 201, f"upload {image.name} -> {status}", failures)
            status_again, _ = api.upload(doc_id, image, fields)
            check(status_again == 200, f"re-upload of the same page_id is idempotent ({status_again})", failures)
            page_ids.append(page_id)

    print(f"== Waiting for OCR (timeout {args.timeout}s)")
    started = time.monotonic()
    while True:
        status, doc = api.json("GET", f"/api/documents/{doc_id}")
        stats = doc.get("stats", {})
        pending = stats.get("queued", 0) + stats.get("processing", 0)
        print(f"  {time.monotonic() - started:6.0f}s  {stats}")
        if pending == 0 or time.monotonic() - started > args.timeout:
            break
        time.sleep(10)
    check(stats.get("done") == len(images), f"all pages OCR'd ({stats.get('done')}/{len(images)})", failures)

    print("== Pages in reading order")
    for page in doc.get("pages", []):
        ocr = page.get("ocr") or {}
        print(f"  {page['key']}  label={page.get('page_label')!s:6} source={page.get('number_source')!s:9} "
              f"status={page['status']:10} images={ocr.get('images')} chars={ocr.get('chars')} "
              f"t={ocr.get('duration_s')}s {page.get('error') or ''}")
    print(f"  coverage: {doc.get('coverage')}")

    print("== Library on disk")
    folder = args.library / doc["slug"]
    document_md = folder / "document.md"
    check(document_md.is_file(), f"{document_md} exists", failures)
    if document_md.is_file():
        text = document_md.read_text(encoding="utf-8")
        check(text.startswith("---\n"), "document.md has YAML front matter", failures)
        refs = re.findall(r'(?:src="|\]\()(images/[^")]+)', text)
        missing = [ref for ref in refs if not (folder / ref).is_file()]
        check(not missing, f"{len(refs)} illustration links resolve (missing: {missing[:3]})", failures)
    check((folder / "document.json").is_file(), "document.json exists", failures)
    check(len(list((folder / "scans").glob("*"))) == len(images), "original scans kept", failures)
    check(len(list((folder / "pages").glob("*.md"))) == len(images), "one markdown per page", failures)
    index = args.library / "INDEX.md"
    check(index.is_file() and args.title in index.read_text(encoding="utf-8"), "INDEX.md lists the document", failures)

    print(f"\n{'PASSED' if not failures else f'FAILED ({len(failures)})'} — document folder: {folder}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
