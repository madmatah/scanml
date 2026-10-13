"""Authentication, CSRF guard, security headers, body limits, public routes."""

from __future__ import annotations

import dataclasses
import errno
import os

import pytest
from fastapi.testclient import TestClient
from starlette.formparsers import MultiPartParser
from support import AUTH, TOKEN, create_document, jpeg, new_id, upload

from scanmylib import __version__
from scanmylib.app import create_app
from scanmylib.auth import load_or_create_token
from scanmylib.images import MAX_UPLOAD_BYTES

PROTECTED = [
    ("GET", "/api/status"),
    ("GET", "/api/pairing"),
    ("GET", "/api/pairing/qr.svg"),
    ("GET", "/api/pairing/apk-qr.svg"),
    ("GET", "/api/documents"),
    ("PUT", f"/api/documents/{new_id()}"),
    ("PUT", f"/api/documents/{new_id()}/order"),
    ("DELETE", f"/api/documents/{new_id()}/order"),
    ("GET", f"/api/documents/{new_id()}/markdown"),
    ("GET", f"/api/documents/{new_id()}/files/document.md"),
    ("POST", f"/api/documents/{new_id()}/pages"),
    ("GET", f"/api/pages/{new_id()}"),
    ("PATCH", f"/api/pages/{new_id()}"),
    ("POST", f"/api/pages/{new_id()}/reprocess"),
    ("DELETE", f"/api/pages/{new_id()}"),
    ("GET", f"/api/pages/{new_id()}/thumb"),
]


def test_health_is_public(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"name": "ScanMyLib", "version": __version__, "api": 1}


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_protected_routes_require_a_credential(client, method, path):
    for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}, {"Cookie": "scanmylib_session=forged"}):
        response = client.request(method, path, headers=headers, json={"title": "x"} if method != "GET" else None)
        assert response.status_code == 401, (headers, response.text)
        assert response.json() == {"detail": "unauthorized"}


def test_bearer_token_grants_access(client):
    assert client.get("/api/documents", headers=AUTH).json() == {"documents": []}


def test_web_session_cookie_and_csrf_header(client):
    assert client.post("/api/session", json={"token": "wrong"}).status_code == 401
    response = client.post("/api/session", json={"token": TOKEN})
    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    for attribute in ("scanmylib_session=", "HttpOnly", "Max-Age=31536000", "Path=/", "SameSite=strict"):
        assert attribute in cookie
    assert "Secure" not in cookie  # plain HTTP on the LAN
    session_id = client.cookies["scanmylib_session"]

    assert client.get("/api/documents").status_code == 200
    document_id = new_id()
    refused = client.put(f"/api/documents/{document_id}", json={"title": "No header"})
    assert refused.status_code == 403
    assert refused.json() == {"detail": "missing X-ScanMyLib header"}
    assert client.put(f"/api/documents/{document_id}", json={"title": "With header"}, headers={"X-ScanMyLib": "1"}).status_code == 201

    assert client.delete("/api/session").status_code == 204
    assert "scanmylib_session" not in client.cookies
    assert client.get("/api/documents").status_code == 401
    # The server forgot the session: replaying the old cookie does not work.
    assert client.get("/api/documents", headers={"Cookie": f"scanmylib_session={session_id}"}).status_code == 401


def test_phone_requests_with_bearer_need_no_csrf_header(client):
    assert client.put(f"/api/documents/{new_id()}", json={"title": "From the phone"}, headers=AUTH).status_code == 201


def test_sessions_end_when_the_token_is_regenerated(settings, fake_ocr):
    with TestClient(create_app(settings)) as first:
        assert first.post("/api/session", json={"token": TOKEN}).status_code == 204
        cookie = first.cookies["scanmylib_session"]
    with TestClient(create_app(dataclasses.replace(settings, token="another-token-1234567890"))) as second:
        assert second.get("/api/documents", headers={"Cookie": f"scanmylib_session={cookie}"}).status_code == 401


def test_token_is_generated_once_and_kept(settings, fake_ocr):
    generated = dataclasses.replace(settings, token=None)
    with TestClient(create_app(generated)) as client:
        token = generated.token_path.read_text().strip()
        assert len(token) >= 43
        assert client.get("/api/documents", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert oct(generated.token_path.stat().st_mode & 0o777) == "0o600"
    with TestClient(create_app(generated)):
        assert generated.token_path.read_text().strip() == token


@pytest.mark.parametrize("content", ["", "\n", "  \n"])
def test_an_empty_token_file_gets_a_new_token(settings, fake_ocr, content):
    # E.g. left by a crash or a full disk during the first start: it used to
    # become the token, and an empty login opened a session for anyone.
    generated = dataclasses.replace(settings, token=None)
    generated.state_dir.mkdir(parents=True)
    generated.token_path.write_text(content)
    with TestClient(create_app(generated)) as client:
        assert client.post("/api/session", json={"token": ""}).status_code == 401
        assert client.post("/api/session", json={"token": content}).status_code == 401
        token = generated.token_path.read_text().strip()
        assert len(token) >= 43
        assert client.get("/api/documents", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert oct(generated.token_path.stat().st_mode & 0o777) == "0o600"


def test_a_failed_token_write_leaves_no_token_file(tmp_path, monkeypatch):
    path = tmp_path / "state" / "token"
    fdopen = os.fdopen

    class FullDisk:
        def __init__(self, fd, *args, **kwargs):
            self._stream = fdopen(fd, *args, **kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            self._stream.close()

        def write(self, data):
            raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "fdopen", FullDisk)
    with pytest.raises(OSError):
        load_or_create_token(path)
    monkeypatch.undo()
    assert list(path.parent.iterdir()) == []  # no empty token file, no temporary file
    token = load_or_create_token(path)  # the next start creates a real token
    assert len(token) >= 43 and path.read_text().strip() == token


def test_security_headers(client):
    for path in ("/", "/api/health", "/api/documents"):
        headers = client.get(path, headers=AUTH).headers
        assert headers["content-security-policy"].startswith("default-src 'self'")
        assert "frame-ancestors 'none'" in headers["content-security-policy"]
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert headers["referrer-policy"] == "no-referrer"
    assert client.get("/api/documents", headers=AUTH).headers["cache-control"] == "no-store"


def test_api_documentation_is_not_exposed(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_upload_bodies_are_not_read_before_authentication(client, monkeypatch):
    parsed = []
    parse = MultiPartParser.parse

    async def recording_parse(self):
        parsed.append(self)
        return await parse(self)

    monkeypatch.setattr(MultiPartParser, "parse", recording_parse)
    document_id = create_document(client)
    for headers, status in (({}, 401), ({"Authorization": "Bearer wrong"}, 401)):
        assert upload(client, document_id, jpeg(), headers=headers).status_code == status
    assert client.post("/api/session", json={"token": TOKEN}).status_code == 204
    assert upload(client, document_id, jpeg(), headers={}).status_code == 403  # cookie without CSRF header
    assert parsed == []  # refused before the 40 MiB body was read and spooled
    assert upload(client, document_id, jpeg(), headers={"X-ScanMyLib": "1"}).status_code == 201
    assert len(parsed) == 1


def test_unencodable_json_input_gets_a_validation_error(client):
    # The 422 response used to echo the invalid input, which failed to encode (500).
    json_type = {"Content-Type": "application/json"}
    login = client.post("/api/session", content=b'{"token": "\\ud800"}', headers=json_type)
    assert login.status_code == 422
    assert login.json()["detail"][0]["loc"] == ["body", "token"]
    assert "input" not in login.json()["detail"][0]
    document_id = create_document(client)
    for path, body in (
        (f"/api/documents/{document_id}", b'{"title": "x\\udfff"}'),
        (f"/api/documents/{document_id}", b'{"title": NaN}'),
        (f"/api/pages/{new_id()}", b'{"manual_number": Infinity}'),
        (f"/api/pages/{new_id()}", b'{"rotation": 1e999}'),
    ):
        assert client.patch(path, content=body, headers={**AUTH, **json_type}).status_code == 422, body
    assert client.post("/api/session", content='{"token": "é"}'.encode(), headers=json_type).status_code == 401


def test_request_bodies_are_limited(client):
    assert client.post("/api/session", content=b"{" + b" " * (2 * 1024 * 1024) + b"}",
                       headers={"Content-Type": "application/json"}).status_code == 413
    document_id = create_document(client)
    response = upload(client, document_id, b"\xff\xd8" + b"\x00" * (MAX_UPLOAD_BYTES + 2 * 1024 * 1024))
    assert response.status_code == 413
    assert response.headers["content-security-policy"]


def test_web_ui_placeholder_then_files(client, settings):
    placeholder = client.get("/")
    assert placeholder.status_code == 200 and "the web UI is not installed" in placeholder.text
    static = settings.web_dir / "static"
    static.mkdir(parents=True)
    (settings.web_dir / "index.html").write_text("<!doctype html><title>ScanMyLib UI</title>")
    (static / "app.js").write_text("console.log('ok')")
    assert "ScanMyLib UI" in client.get("/").text
    script = client.get("/static/app.js")
    assert script.status_code == 200 and script.headers["content-type"].startswith("text/javascript")
    assert client.get("/static/../index.html").status_code == 404
    assert client.get("/static/%2e%2e/index.html").status_code == 404


def test_apk_download_and_pairing(client, settings):
    assert client.get("/download/scanmylib.apk").status_code == 404
    pairing = client.get("/api/pairing", headers=AUTH).json()
    assert pairing == {
        "url": "http://192.168.1.10:8765",
        "token": TOKEN,
        "pair_uri": f"scanmylib://pair?url=http%3A%2F%2F192.168.1.10%3A8765&token={TOKEN}",
        "apk_available": False,
        "apk_url": "http://192.168.1.10:8765/download/scanmylib.apk",
    }
    settings.apk_path.parent.mkdir(parents=True)
    settings.apk_path.write_bytes(b"PK\x03\x04 fake apk")
    apk = client.get("/download/scanmylib.apk")
    assert apk.status_code == 200 and apk.content == b"PK\x03\x04 fake apk"
    assert apk.headers["content-type"] == "application/vnd.android.package-archive"
    assert client.get("/api/pairing", headers=AUTH).json()["apk_available"] is True
    for path in ("/api/pairing/qr.svg", "/api/pairing/apk-qr.svg"):
        qr = client.get(path, headers=AUTH)
        assert qr.headers["content-type"] == "image/svg+xml"
        assert b"<svg" in qr.content and b"<script" not in qr.content
