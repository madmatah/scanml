#!/usr/bin/env python3
"""End-to-end test of a running ScanMyLib stack, acting like the phone app.

Creates a document, uploads page photos out of order over two "sessions",
waits for the OCR sandbox to process them, then checks the organized library
on disk (document.md, per-page files, illustrations, INDEX.md).

Standard library only, so it runs with the system python3:

    scripts/e2e_test.py IMAGE [IMAGE...] [--api URL] [--token-file FILE] [--library DIR]
                        [--timeout 900] [--production]

It targets the stack of the checkout it runs from, read from its .env (strict
format, scripts/lib/stack.py): the api on 127.0.0.1:API_PORT, the token in
DATA_DIR/state/token and the library LIBRARY_DIR. In a worktree, that is the
development stack (scripts/dev-env.sh). Options override the .env.

It refuses to write into production (its project, its ports, its data or its
library, from the .env of production's checkout and from its containers, or the
library the api reports) unless --production is given: the test document would
land in the user's library. An --api URL without an explicit port is refused
too.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
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


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
sys.dont_write_bytecode = True  # no __pycache__ left in the checkout
import stack  # noqa: E402  (scripts/lib/stack.py: the strict .env format)
import version  # noqa: E402  (scripts/lib/version.py: the version of a build)


def read_env(path: Path) -> dict[str, str]:
    """The KEY=VALUE pairs of a .env in the strict format (empty when there is no file)."""
    return stack.read_env(path) if path.is_file() else {}


def production_containers() -> list[dict]:
    """`docker inspect` of production's containers (empty without Docker: production is then
    described by the .env of ~/Dev/scanmylib and the defaults)."""
    try:
        ids = subprocess.run(["docker", "ps", "--all", "--quiet", "--filter",
                              f"label=com.docker.compose.project={stack.PRODUCTION_PROJECT}"],
                             capture_output=True, text=True, check=True).stdout.split()
        if not ids:
            return []
        return json.loads(subprocess.run(["docker", "inspect", *ids], capture_output=True, text=True,
                                         check=True).stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"  note  cannot list production's containers ({exc}): production's defaults only", file=sys.stderr)
        return []


def port_of(url: str) -> int:
    """The explicit port of an http(s) URL (ValueError when there is none or it is invalid)."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"{url}: expected http://HOST:PORT")
    if parts.port is None:  # .port raises ValueError on an invalid port
        raise ValueError(f"{url}: no explicit port")
    return parts.port


class Production:
    """What production owns: the .env of its checkout, its containers, the defaults (stack.py)."""

    def __init__(self) -> None:
        containers = production_containers()
        self.identity = stack.production_identity(stack.production_checkout(containers), containers)
        libraries = {description: path for description, path in self.identity.paths.items()
                     if "LIBRARY_DIR" in description or description.startswith("mount /library ")}
        self.libraries = stack.Production(paths=libraries)

    def owns_library(self, library: Path | str) -> bool:
        return bool(self.libraries.relations(os.path.realpath(library)))

    def reasons(self, env: dict[str, str], api: str, token_file: Path, library: Path) -> list[str]:
        """Why these targets are production's (an empty list when they are not)."""
        reasons = []
        if env.get("COMPOSE_PROJECT_NAME") in self.identity.projects:
            reasons.append(f"{ROOT / '.env'} is production's (COMPOSE_PROJECT_NAME={env['COMPOSE_PROJECT_NAME']})")
        try:
            if port_of(api) in self.identity.ports:
                reasons.append(f"{api} is production's port")
        except ValueError as exc:
            reasons.append(f"cannot tell the port of --api: {exc}")
        reasons += [f"{token_file} {relation}" for relation in self.identity.relations(os.path.realpath(token_file))]
        if self.owns_library(library):
            reasons.append(f"{library} is production's library")
        return reasons


def check(condition: bool, message: str, failures: list[str]) -> None:
    print(("  ok    " if condition else "  FAIL  ") + message)
    if not condition:
        failures.append(message)


def main() -> int:
    try:
        env = read_env(ROOT / ".env")
    except stack.EnvError as exc:
        sys.exit(f"error: {exc}")
    data_dir = env.get("DATA_DIR")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--api", default=f"http://127.0.0.1:{env.get('API_PORT') or 8765}" if env else None,
                        help="default: http://127.0.0.1:API_PORT")
    parser.add_argument("--token-file", type=Path, default=Path(data_dir, "state", "token") if data_dir else None,
                        help="default: DATA_DIR/state/token")
    parser.add_argument("--library", type=Path, default=Path(env["LIBRARY_DIR"]) if env.get("LIBRARY_DIR") else None,
                        help="default: LIBRARY_DIR")
    parser.add_argument("--title", default=f"Test E2E {datetime.now():%Y-%m-%d %H:%M:%S}")
    parser.add_argument("--timeout", type=int, default=900, help="seconds to wait for OCR")
    parser.add_argument("--production", action="store_true",
                        help="allow a test document in production's library (refused otherwise)")
    args = parser.parse_args()
    missing = [option for option, value in (("--api", args.api), ("--token-file", args.token_file),
                                            ("--library", args.library)) if value is None]
    if missing:
        parser.error(f"no active environment in {ROOT / '.env'} (scripts/dev-env.sh in a worktree): "
                     f"pass {', '.join(missing)}")
    try:
        production = Production()
    except stack.EnvError as exc:
        sys.exit(f"error: cannot tell what production owns ({exc}): nothing was sent")
    reasons = production.reasons(env, args.api, args.token_file, args.library)
    if reasons and not args.production:
        sys.exit("error: refusing to write a test document into production:\n  - " + "\n  - ".join(reasons)
                 + "\nRun it from a worktree's development stack (scripts/dev-env.sh), or pass --production.")

    api = Api(args.api, args.token_file.read_text().strip())
    failures: list[str] = []

    print(f"== Environment {env.get('COMPOSE_PROJECT_NAME') or '(options only)'} ({ROOT / '.env'})")
    print(f"  api {args.api}, token {args.token_file}, library {args.library}")
    if reasons:
        print("  PRODUCTION (--production): the test document goes into the user's library")
    print(f"== API {args.api}")
    status, health = api.json("GET", "/api/health")
    check(status == 200 and health.get("name") == "ScanMyLib", f"health: {status} {health}", failures)
    # The api of a development stack reports the version of its build (scripts/lib/version.py): another
    # one means a stack built from another commit or worktree.
    running = health.get("version")
    try:
        release = version.read_release(ROOT)
        expected = version.format_release(release)
        if isinstance(running, str) and "-dev" in running:
            expected = version.dev_version(ROOT, release)
    except (OSError, ValueError):
        expected = None
    if expected and running != expected:
        print(f"  note  the api runs version {running}, this checkout is {expected}")
    status, _ = Api(args.api, "wrong-token").json("GET", "/api/status")
    check(status == 401, f"wrong token rejected ({status})", failures)
    # Where this api really writes: the library it reports, whatever the options said.
    status, api_status = api.json("GET", "/api/status")
    reported = api_status.get("library_dir") if status == 200 else None
    if reported and production.owns_library(reported) and not args.production:
        sys.exit(f"error: the api at {args.api} writes into production's library ({reported}): nothing was sent."
                 "\nPass --production to test production anyway.")
    if reported and Path(os.path.realpath(reported)) != Path(os.path.realpath(args.library)):
        print(f"  note  the api reports the library {reported}, the checks read {args.library}")

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
