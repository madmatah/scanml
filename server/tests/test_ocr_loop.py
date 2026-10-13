"""OCR loop behavior (docs/API.md "Behavior notes") against the fake sandbox."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from support import AUTH, create_document, page_image, upload, wait_for, wait_until_processed

from scanmylib.app import create_app
from scanmylib.devtools.fake_ocr import FakeOcrServer
from scanmylib.library import MAX_OCR_RETRIES
from scanmylib.ocr_client import OcrClient, OcrUnavailable


def page_status(client, page_id: str) -> dict:
    return client.get(f"/api/pages/{page_id}", headers=AUTH).json()


def test_uploads_wait_while_the_sandbox_is_down_then_get_processed(settings):
    with TestClient(create_app(settings)) as client:
        status = client.get("/api/status", headers=AUTH).json()
        assert status["ocr"] == {
            "reachable": False, "state": "unreachable", "backend": None,
            "last_error": f"socket {settings.ocr_socket} absent", "gpu": None,
        }
        document_id = create_document(client)
        page = upload(client, document_id, page_image(8)).json()
        wait_for(lambda: page_status(client, page["id"])["status"] == "queued")

        sandbox = FakeOcrServer(settings.ocr_socket)  # the sandbox (re)starts
        sandbox.start()
        try:
            document = wait_until_processed(client, document_id)
            assert document["pages"][0]["status"] == "done"
            assert document["pages"][0]["number"] == 8
        finally:
            sandbox.stop()


def test_engine_unavailable_is_retried_without_counting_failures(client, fake_ocr):
    fake_ocr.fail_next(503, MAX_OCR_RETRIES + 3)
    document_id = create_document(client)
    page = upload(client, document_id, page_image(5)).json()
    wait_until_processed(client, document_id, timeout=30)
    assert page_status(client, page["id"])["status"] == "done"
    assert len(fake_ocr.requests) == MAX_OCR_RETRIES + 4


def test_processing_errors_are_retried_then_reported(client, fake_ocr):
    fake_ocr.fail_next(500, MAX_OCR_RETRIES + 1)
    document_id = create_document(client)
    page = upload(client, document_id, page_image(5)).json()
    document = wait_until_processed(client, document_id)
    failed = document["pages"][0]
    assert failed["status"] == "error"
    assert failed["error"].startswith("OCR failed: HTTP 500 (processing_failed: simulated failure)")
    assert len(fake_ocr.requests) == MAX_OCR_RETRIES + 1
    assert document["stats"]["error"] == 1 and not failed["in_document"]

    client.post(f"/api/pages/{page['id']}/reprocess", headers=AUTH)
    wait_until_processed(client, document_id)
    recovered = page_status(client, page["id"])
    assert (recovered["status"], recovered["error"]) == ("done", None)


def test_a_transient_failure_is_retried(client, fake_ocr):
    fake_ocr.fail_next(500, 2)
    document_id = create_document(client)
    upload(client, document_id, page_image(6))
    assert wait_until_processed(client, document_id)["pages"][0]["status"] == "done"
    assert len(fake_ocr.requests) == 3


def test_pages_are_processed_in_upload_order(client, fake_ocr):
    document_id = create_document(client)
    for number in (30, 10, 20):
        upload(client, document_id, page_image(number))
    wait_until_processed(client, document_id)
    assert [request["height"] - 1000 for request in fake_ocr.requests] == [30, 10, 20]


def test_interrupted_processing_is_requeued_on_restart(settings, fake_ocr):
    fake_ocr.delay = 3.0
    with TestClient(create_app(settings)) as client:
        document_id = create_document(client)
        page = upload(client, document_id, page_image(9)).json()
        wait_for(lambda: page_status(client, page["id"])["status"] == "processing")
    # The api stopped in the middle of the page; on restart it is queued again.
    fake_ocr.delay = 0.0
    with TestClient(create_app(settings)) as client:
        document = wait_until_processed(client, document_id)
        assert document["pages"][0]["status"] == "done"


def test_new_work_prewarms_the_engine(client, fake_ocr):
    document_id = create_document(client)
    assert fake_ocr.load_requests == 0
    upload(client, document_id, page_image(1))
    wait_for(lambda: fake_ocr.load_requests == 1)
    wait_until_processed(client, document_id)


def test_status_reports_the_sandbox_engine(client):
    status = client.get("/api/status", headers=AUTH).json()
    assert status["ocr"] == {"reachable": True, "state": "idle", "backend": "fake", "last_error": None, "gpu": None}
    assert status["version"] == "0.1.0"


def test_status_relays_only_typed_and_bounded_sandbox_fields(client, fake_ocr):
    # The phone app decodes "state" and "last_error" as strings: other types must not get through.
    fake_ocr.status_body = json.dumps({
        "engine": {"state": 1, "backend": {"a": 1}, "last_error": "x\ud800\n" + "y" * 5000},
        "gpu": {"name": ["x"], "memory_used_mb": "lots", "memory_total_mb": 24576, "extra": "z"},
    }).encode()
    response = client.get("/api/status", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["ocr"] == {
        "reachable": True, "state": None, "backend": None,
        "last_error": ("x? " + "y" * 5000)[:1000],
        "gpu": {"name": None, "memory_used_mb": None, "memory_total_mb": 24576},
    }


@pytest.mark.parametrize(
    "body",
    [b"[" * 50_000, b'{"engine": {"state": "error", "last_error": "' + b"A" * (1024 * 1024) + b'"}}'],
    ids=["deeply-nested", "oversized"],
)
def test_unusable_health_answers_mean_unreachable(client, fake_ocr, body):
    fake_ocr.status_body = body
    response = client.get("/api/status", headers=AUTH)
    assert response.status_code == 200
    ocr = response.json()["ocr"]
    assert (ocr["reachable"], ocr["state"]) == (False, "unreachable")
    assert len(ocr["last_error"]) <= 300


def test_oversized_load_answer_is_refused_without_buffering(fake_ocr):
    fake_ocr.status_body = b"x" * (1024 * 1024)

    async def load() -> None:
        sandbox = OcrClient(fake_ocr.socket_path, 10)
        try:
            await sandbox.load()
        finally:
            await sandbox.aclose()

    with pytest.raises(OcrUnavailable, match="larger than"):
        asyncio.run(load())
