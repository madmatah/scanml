"""Reading order end to end: automatic placement, PUT/DELETE /api/documents/{id}/order, document.md."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from scanmylib.devtools.fake_ocr import FakeOcrServer
from scanmylib.ordering import int_to_roman
from support import AUTH, TOKEN, create_document, new_id, page_image, upload, wait_until_processed

NO_NUMBER = 0  # page_image(0): the fake OCR finds no page number
ROMAN = 2  # page_image(n, ROMAN): the fake OCR finds n in roman numerals (front matter)
UNNUMBERED_HEADING = "## Unnumbered pages"


def scan(
    client: TestClient, document_id: str, number: int, session: str, seq: int, minute: int = 0, variant: int = 0
) -> dict[str, Any]:
    response = upload(
        client,
        document_id,
        page_image(number, variant),
        session_id=session,
        seq=seq,
        captured_at=f"2026-10-12T20:{minute:02d}:{seq:02d}+02:00",
    )
    assert response.status_code == 201, response.text
    page: dict[str, Any] = response.json()
    return page


def ids(pages: list[dict[str, Any]]) -> list[str]:
    return [page["id"] for page in pages]


def reading(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [page for page in document["pages"] if page["in_document"]]


def put_order(client: TestClient, document_id: str, page_ids: list[str]) -> httpx2.Response:
    return client.put(f"/api/documents/{document_id}/order", json={"page_ids": page_ids}, headers=AUTH)


def markers(client: TestClient, document_id: str) -> list[str]:
    """Page and gap markers of document.md, and its unnumbered heading, in order."""
    markdown = client.get(f"/api/documents/{document_id}/markdown", headers=AUTH).text
    return [line for line in markdown.splitlines() if line.startswith("<!-- ") or line == UNNUMBERED_HEADING]


def page_markers(pages: list[dict[str, Any]]) -> list[str]:
    return [
        f"<!-- page {page['page_label']} · scan {page['key']} -->"
        if page["page_label"]
        else f"<!-- scan {page['key']} -->"
        for page in pages
    ]


def test_front_matter_scanned_before_page_one_opens_the_document(client: TestClient) -> None:
    document_id = create_document(client, kind="book")
    session = new_id()
    front = [scan(client, document_id, NO_NUMBER, session, seq) for seq in range(20)]
    body = [scan(client, document_id, n, session, 19 + n) for n in range(1, 6)]
    document = wait_until_processed(client, document_id)

    assert ids(reading(document)) == ids(front + body)
    assert [p["placement"] for p in reading(document)] == ["session"] * 20 + ["number"] * 5
    assert [p["page_label"] for p in reading(document)] == [None] * 20 + ["1", "2", "3", "4", "5"]
    assert all(p["position"] is None for p in document["pages"])
    assert document["coverage"]["label"] == "1–5" and document["coverage"]["unnumbered"] == 20
    assert document["cover_thumb_url"] == f"/api/pages/{front[0]['id']}/thumb"
    assert markers(client, document_id) == page_markers(reading(document))  # no unnumbered heading


def test_roman_front_matter_then_the_main_text_in_one_session(client: TestClient) -> None:
    # The user's book, 25 pages in one session: cover and unnumbered pages, front matter in roman
    # numerals, then the main text. The OCR found XV, XXV and 3, and no number it could read on the
    # other pages ("1X", garbage instead of the 2...): the two pages before page 3 are pages 1 and 2.
    document_id = create_document(client, kind="book")
    session = new_id()
    found = {15: (15, ROMAN), 22: (25, ROMAN), 25: (3, 0)}
    pages = []
    for seq in range(1, 26):
        number, variant = found.get(seq, (NO_NUMBER, 0))
        pages.append(scan(client, document_id, number, session, seq, variant=variant))
    document = wait_until_processed(client, document_id)

    assert ids(reading(document)) == ids(pages)
    labels = [int_to_roman(seq) for seq in range(1, 22)] + ["xxv", "1", "2", "3"]
    assert [p["page_label"] for p in reading(document)] == labels
    assert [p["number_source"] for p in reading(document)][21:] == ["detected", "inferred", "inferred", "detected"]
    assert placements(document) == ["number"] * 25
    assert document["coverage"]["label"] == "1–3" and document["coverage"]["unnumbered"] == 0
    assert markers(client, document_id) == page_markers(reading(document))

    # A number typed by hand wins (the user had typed these); cleared, the same number is inferred.
    typed = client.patch(f"/api/pages/{pages[22]['id']}", json={"manual_number": 1}, headers=AUTH).json()
    assert (typed["page_label"], typed["number_source"]) == ("1", "manual")
    cleared = client.patch(f"/api/pages/{pages[22]['id']}", json={"manual_number": None}, headers=AUTH).json()
    assert (cleared["page_label"], cleared["number_source"]) == ("1", "inferred")


def test_pages_moved_before_page_one_then_more_pages_scanned(client: TestClient, library_dir: Path) -> None:
    document_id = create_document(client, kind="book")
    book, loose = new_id(), new_id()
    body = [scan(client, document_id, n, book, n - 1) for n in range(1, 6)]
    front = [scan(client, document_id, NO_NUMBER, loose, seq, minute=10) for seq in range(20)]
    document = wait_until_processed(client, document_id)
    # Scanned in a session of their own, the unnumbered pages cannot be placed: they come last.
    assert ids(reading(document)) == ids(body + front)
    assert [p["placement"] for p in reading(document)] == ["number"] * 5 + ["unplaced"] * 20
    pages = reading(document)
    assert markers(client, document_id) == [*page_markers(pages[:5]), UNNUMBERED_HEADING, *page_markers(pages[5:])]

    response = put_order(client, document_id, ids(front + body))
    assert response.status_code == 200, response.text
    document = response.json()
    assert ids(reading(document)) == ids(front + body)
    assert [p["position"] for p in reading(document)] == [float(v) for v in range(-19, 1)] + [None] * 5
    assert [p["placement"] for p in reading(document)] == ["manual"] * 20 + ["number"] * 5
    assert [p["page_label"] for p in reading(document)] == [None] * 20 + ["1", "2", "3", "4", "5"]
    assert document["coverage"]["label"] == "1–5" and document["stats"]["duplicates"] == 0
    assert document["cover_thumb_url"] == f"/api/pages/{front[0]['id']}/thumb"
    assert markers(client, document_id) == page_markers(reading(document))
    metadata = json.loads((library_dir / "sample-cafe-guide" / "document.json").read_text())
    assert [(p["id"], p["position"], p["placement"]) for p in metadata["pages"]] == [
        (p["id"], p["position"], p["placement"]) for p in document["pages"]
    ]

    # Page 6, scanned later, slots in after page 5.
    p6 = scan(client, document_id, 6, new_id(), 0, minute=20)
    document = wait_until_processed(client, document_id)
    assert ids(reading(document)) == [*ids(front + body), p6["id"]]
    assert reading(document)[-1]["placement"] == "number"
    assert markers(client, document_id) == page_markers(reading(document))

    # Back to the automatic order.
    response = client.delete(f"/api/documents/{document_id}/order", headers=AUTH)
    assert response.status_code == 200, response.text
    document = response.json()
    assert ids(reading(document)) == [*ids(body), p6["id"], *ids(front)]
    assert all(p["position"] is None for p in document["pages"])
    assert [p["placement"] for p in reading(document)] == ["number"] * 6 + ["unplaced"] * 20
    pages = reading(document)
    assert markers(client, document_id) == [*page_markers(pages[:6]), UNNUMBERED_HEADING, *page_markers(pages[6:])]
    assert client.get(f"/api/documents/{document_id}", headers=AUTH).json() == document
    # Nothing left to clear.
    assert client.delete(f"/api/documents/{document_id}/order", headers=AUTH).json() == document


def test_moving_one_page_sets_one_position(client: TestClient) -> None:
    document_id = create_document(client)
    session = new_id()
    pages = [scan(client, document_id, n, session, n) for n in range(1, 7)]
    wait_until_processed(client, document_id)
    p1, p2, p3, p4, p5, p6 = pages
    wanted = ids([p1, p5, p2, p3, p4, p6])

    document = put_order(client, document_id, wanted).json()
    assert ids(reading(document)) == wanted
    assert {p["id"]: p["position"] for p in document["pages"] if p["position"] is not None} == {p5["id"]: 1.5}
    assert [p["placement"] for p in reading(document)] == ["number", "manual", "number", "number", "number", "number"]
    assert markers(client, document_id) == page_markers(reading(document))
    assert [p["page_label"] for p in reading(document)] == ["1", "5", "2", "3", "4", "6"]

    # The same order again changes nothing.
    assert put_order(client, document_id, wanted).json() == document
    # Putting page 5 back clears its position.
    document = put_order(client, document_id, ids(pages)).json()
    assert ids(reading(document)) == ids(pages)
    assert all(p["position"] is None for p in document["pages"])


def placements(document: dict[str, Any]) -> list[str]:
    return [page["placement"] for page in reading(document)]


def positions(document: dict[str, Any]) -> dict[str, float]:
    return {page["id"]: page["position"] for page in document["pages"] if page["position"] is not None}


def test_moving_loose_pages_into_a_book_leaves_the_other_pages_in_place(client: TestClient) -> None:
    # 20 unnumbered pages (title, preface...), pages 1–10 and a plate after page 5 scanned in one
    # session; 3 more pages scanned on their own later: they are unplaced, at the end.
    document_id = create_document(client, kind="book")
    book, loose = new_id(), new_id()
    front = [scan(client, document_id, NO_NUMBER, book, seq) for seq in range(20)]
    first = [scan(client, document_id, n, book, 19 + n) for n in range(1, 6)]
    plate = scan(client, document_id, NO_NUMBER, book, 25)
    rest = [scan(client, document_id, n, book, 20 + n) for n in range(6, 11)]
    extra = [scan(client, document_id, NO_NUMBER, loose, seq, minute=30) for seq in range(3)]
    document = wait_until_processed(client, document_id)
    in_book = [*front, *first, plate, *rest]
    book_placements = ["session"] * 20 + ["number"] * 5 + ["session"] + ["number"] * 5
    assert ids(reading(document)) == ids(in_book + extra)
    assert placements(document) == [*book_placements, "unplaced", "unplaced", "unplaced"]

    # Moved before page 1 (after the front pages): only they get a position, between the last front page and page 1.
    wanted = ids([*front, *extra, *first, plate, *rest])
    document = put_order(client, document_id, wanted).json()
    assert ids(reading(document)) == wanted
    assert placements(document) == book_placements[:20] + ["manual"] * 3 + book_placements[20:]
    between = {page["id"]: 0.9999 + 0.0001 * k / 4 for k, page in enumerate(extra, 1)}  # 1 − 0.0001 < … < 1
    assert positions(document) == pytest.approx(between)
    assert markers(client, document_id) == page_markers(reading(document))  # every page has a place: no heading
    assert put_order(client, document_id, wanted).json() == document  # the same order again changes nothing

    # Moved to the front instead.
    document = put_order(client, document_id, ids(extra + in_book)).json()
    assert ids(reading(document)) == ids(extra + in_book)
    assert placements(document) == ["manual"] * 3 + book_placements
    assert positions(document) == {page["id"]: float(k) for k, page in zip(range(-22, -19), extra, strict=True)}

    # Back to the automatic order.
    document = client.delete(f"/api/documents/{document_id}/order", headers=AUTH).json()
    assert ids(reading(document)) == ids(in_book + extra)
    assert positions(document) == {}


def test_moving_an_unnumbered_page_sets_one_position(client: TestClient) -> None:
    document_id = create_document(client, kind="book")
    session = new_id()
    title = scan(client, document_id, NO_NUMBER, session, 0)
    p1, p2, p3 = (scan(client, document_id, n, session, n) for n in (1, 2, 3))
    plate = scan(client, document_id, NO_NUMBER, session, 4)
    p4, p5 = (scan(client, document_id, n, session, n + 1) for n in (4, 5))
    document = wait_until_processed(client, document_id)
    assert placements(document) == ["session", "number", "number", "number", "session", "number", "number"]

    wanted = ids([title, p1, p2, p3, p4, plate, p5])  # the plate after page 4
    document = put_order(client, document_id, wanted).json()
    assert ids(reading(document)) == wanted
    assert positions(document) == {plate["id"]: 4.5}
    assert placements(document) == ["session", "number", "number", "number", "number", "manual", "number"]
    assert markers(client, document_id) == page_markers(reading(document))


def test_duplicates_are_unaffected_by_positions(client: TestClient) -> None:
    document_id = create_document(client)
    first, later = new_id(), new_id()
    p1, p2, p3 = (scan(client, document_id, n, first, n) for n in (1, 2, 3))
    wait_until_processed(client, document_id)
    assert put_order(client, document_id, ids([p3, p1, p2])).status_code == 200

    rescan = scan(client, document_id, 3, later, 0, minute=30)  # page 3 photographed again
    document = wait_until_processed(client, document_id)
    old = next(p for p in document["pages"] if p["id"] == p3["id"])
    assert (old["duplicate_of"], old["in_document"], old["position"], old["placement"]) == (
        rescan["id"],
        False,
        0.0,
        None,
    )
    assert ids(reading(document)) == ids([p1, p2, rescan])
    assert [p["placement"] for p in reading(document)] == ["number"] * 3
    assert document["stats"]["duplicates"] == 1


def test_stale_or_invalid_orders_are_refused(client: TestClient, fake_ocr: FakeOcrServer) -> None:
    document_id = create_document(client)
    session = new_id()
    p1, p2, p3, excluded = (scan(client, document_id, n, session, n) for n in (1, 2, 3, 4))
    wait_until_processed(client, document_id)
    assert client.patch(f"/api/pages/{excluded['id']}", json={"excluded": True}, headers=AUTH).status_code == 200
    other = create_document(client, "Other")
    foreign = scan(client, other, 1, new_id(), 0)
    wait_until_processed(client, other)

    for page_ids in (
        ids([p1, p2]),  # a page is missing
        ids([p1, p2, p3, excluded]),  # a page that is not in the reading order
        ids([p1, p2, p3, foreign]),  # a page of another document
        ids([p1, p2, p3, p3]),  # the same page twice
        [*ids([p1, p2]), new_id()],  # an unknown page
        [],
    ):
        response = put_order(client, document_id, page_ids)
        assert response.status_code == 409, page_ids
        assert response.json() == {"detail": "page set changed"}

    fake_ocr.unavailable = True  # the next page stays queued: not in the reading order yet
    late = scan(client, document_id, 5, session, 5)
    assert put_order(client, document_id, ids([p3, p1, p2, late])).status_code == 409
    assert put_order(client, document_id, ids([p3, p1, p2])).status_code == 200

    for body in (
        {},
        {"page_ids": None},
        {"page_ids": p1["id"]},
        {"page_ids": [1]},
        {"page_ids": ["p1"]},
        {"page_ids": [p1["id"].upper()]},
        {"page_ids": [new_id()] * 10_001},
    ):
        response = client.put(f"/api/documents/{document_id}/order", json=body, headers=AUTH)
        assert response.status_code == 422, body
    for method in ("PUT", "DELETE"):
        response = client.request(method, f"/api/documents/{new_id()}/order", json={"page_ids": []}, headers=AUTH)
        assert response.status_code == 404
        assert response.json() == {"detail": "document not found"}
    document = client.get(f"/api/documents/{document_id}", headers=AUTH).json()
    assert ids(reading(document)) == ids([p3, p1, p2])  # the refused requests changed nothing


def test_reordering_a_document_without_page_numbers(client: TestClient) -> None:
    document_id = create_document(client, "Letter")
    a, b, c = (scan(client, document_id, NO_NUMBER, new_id(), 0, minute=m) for m in (1, 2, 3))
    document = wait_until_processed(client, document_id)
    assert ids(reading(document)) == ids([a, b, c])  # capture order
    assert [p["placement"] for p in reading(document)] == ["unplaced"] * 3

    document = put_order(client, document_id, ids([c, a, b])).json()
    assert ids(reading(document)) == ids([c, a, b])
    # Only the page that moved gets a position; a and b stay after it, in capture order.
    assert [p["position"] for p in reading(document)] == [1.0, None, None]
    assert [p["placement"] for p in reading(document)] == ["manual", "unplaced", "unplaced"]
    assert markers(client, document_id) == page_markers(reading(document))  # no heading: no page has a number


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_order_routes_need_the_csrf_header_with_a_cookie(client: TestClient, method: str) -> None:
    document_id = create_document(client)
    assert client.post("/api/session", json={"token": TOKEN}).status_code == 204
    path = f"/api/documents/{document_id}/order"
    refused = client.request(method, path, json={"page_ids": []})
    assert refused.status_code == 403
    assert client.request(method, path, json={"page_ids": []}, headers={"X-ScanMyLib": "1"}).status_code == 200
