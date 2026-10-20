"""Reading order end to end: automatic placement, PUT/DELETE /api/documents/{id}/order, document.md."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from scanmylib.ordering import int_to_roman
from support import (
    AUTH,
    NO_NUMBER,
    TOKEN,
    Answer,
    PageNumberVariant,
    capture_answer,
    create_document,
    list_labels,
    new_id,
    page_image,
    running_api,
    select_reading_order,
    upload,
    wait_until_processed,
)

UNNUMBERED_HEADING = "## Unnumbered pages"


def scan(
    client: TestClient,
    document_id: str,
    number: int,
    session: str,
    seq: int,
    minute: int = 0,
    variant: PageNumberVariant = PageNumberVariant.ARABIC,
) -> dict[str, Any]:
    response = upload(
        client,
        document_id,
        page_image(number, variant),
        session_id=session,
        seq=seq,
        captured_at=f"2026-10-12T20:{minute:02d}:{seq:02d}+02:00",
    )
    response.raise_for_status()
    page: dict[str, Any] = response.json()
    return page


def list_ids(pages: list[dict[str, Any]]) -> list[str]:
    return [page["id"] for page in pages]


def list_placements(document: dict[str, Any]) -> list[str]:
    return [page["placement"] for page in select_reading_order(document)]


def list_positions(document: dict[str, Any]) -> list[float | None]:
    return [page["position"] for page in select_reading_order(document)]


def map_positions(document: dict[str, Any]) -> dict[str, float]:
    return {page["id"]: page["position"] for page in document["pages"] if page["position"] is not None}


def put_order(client: TestClient, document_id: str, page_ids: list[str]) -> httpx2.Response:
    return client.put(f"/api/documents/{document_id}/order", json={"page_ids": page_ids}, headers=AUTH)


def read_markers(client: TestClient, document_id: str) -> list[str]:
    markdown = client.get(f"/api/documents/{document_id}/markdown", headers=AUTH).text
    return [line for line in markdown.splitlines() if line.startswith("<!-- ") or line == UNNUMBERED_HEADING]


def build_markers(pages: list[dict[str, Any]]) -> list[str]:
    return [
        f"<!-- page {page['page_label']} · scan {page['key']} -->"
        if page["page_label"]
        else f"<!-- scan {page['key']} -->"
        for page in pages
    ]


@dataclass(frozen=True)
class PrintedNumber:
    number: int
    variant: PageNumberVariant


@dataclass(frozen=True)
class FrontMatterBook:
    front: list[dict[str, Any]]
    body: list[dict[str, Any]]
    document: dict[str, Any]
    markers: list[str]


@dataclass(frozen=True)
class RomanBook:
    pages: list[dict[str, Any]]
    document: dict[str, Any]
    markers: list[str]
    typed_page: dict[str, Any]
    cleared_page: dict[str, Any]


@dataclass(frozen=True)
class FrontMatterMovedByHand:
    body: list[dict[str, Any]]
    front: list[dict[str, Any]]
    document_once_read: dict[str, Any]
    markers_once_read: list[str]
    move_status: int
    moved_document: dict[str, Any]
    moved_markers: list[str]
    moved_metadata_pages: list[dict[str, Any]]
    page_six: dict[str, Any]
    document_with_page_six: dict[str, Any]
    markers_with_page_six: list[str]
    restore_status: int
    restored_document: dict[str, Any]
    restored_markers: list[str]
    document_read_after_restore: dict[str, Any]
    document_restored_again: dict[str, Any]


@dataclass(frozen=True)
class PageMovedByHand:
    pages: list[dict[str, Any]]
    order_put: list[str]
    moved_document: dict[str, Any]
    moved_markers: list[str]
    document_moved_again: dict[str, Any]
    document_put_back: dict[str, Any]


@dataclass(frozen=True)
class LoosePagesMovedByHand:
    in_book: list[dict[str, Any]]
    loose: list[dict[str, Any]]
    document_once_read: dict[str, Any]
    order_between: list[str]
    document_moved_between: dict[str, Any]
    markers_moved_between: list[str]
    document_moved_between_again: dict[str, Any]
    document_moved_first: dict[str, Any]
    restored_document: dict[str, Any]


@dataclass(frozen=True)
class PlateMovedByHand:
    plate: dict[str, Any]
    document_once_read: dict[str, Any]
    order_put: list[str]
    moved_document: dict[str, Any]
    moved_markers: list[str]


@dataclass(frozen=True)
class RescannedPage:
    earlier_scan: dict[str, Any]
    rescan: dict[str, Any]
    numbered_pages: list[dict[str, Any]]
    document: dict[str, Any]


@dataclass(frozen=True)
class RefusedOrders:
    changed_page_sets: dict[str, Answer]
    status_with_a_queued_page: int
    status_without_the_queued_page: int
    malformed_statuses: dict[str, int]
    unknown_document: dict[str, Answer]
    accepted_order: list[str]
    order_after_refusals: list[str]


@dataclass(frozen=True)
class LetterMovedByHand:
    pages: list[dict[str, Any]]
    document_once_read: dict[str, Any]
    order_put: list[str]
    moved_document: dict[str, Any]
    moved_markers: list[str]


@dataclass(frozen=True)
class OrderChangedFromTheWebUi:
    status_without_header: int
    status_with_header: int


@pytest.fixture(scope="module")
def roman_book(tmp_path_factory: pytest.TempPathFactory) -> RomanBook:
    printed_numbers_by_seq = {
        15: PrintedNumber(15, PageNumberVariant.ROMAN),
        22: PrintedNumber(25, PageNumberVariant.ROMAN),
        25: PrintedNumber(3, PageNumberVariant.ARABIC),
    }
    no_printed_number = PrintedNumber(NO_NUMBER, PageNumberVariant.ARABIC)
    with running_api(tmp_path_factory.mktemp("api")) as api:
        document_id = create_document(api.client, kind="book")
        session = new_id()
        printed_numbers = [printed_numbers_by_seq.get(seq, no_printed_number) for seq in range(1, 26)]
        pages = [
            scan(api.client, document_id, printed_number.number, session, seq, variant=printed_number.variant)
            for seq, printed_number in enumerate(printed_numbers, 1)
        ]
        document = wait_until_processed(api.client, document_id)
        markers = read_markers(api.client, document_id)
        inferred_page_one = f"/api/pages/{pages[22]['id']}"
        typed_page = api.client.patch(inferred_page_one, json={"manual_number": 1}, headers=AUTH).json()
        cleared_page = api.client.patch(inferred_page_one, json={"manual_number": None}, headers=AUTH).json()
        return RomanBook(pages, document, markers, typed_page, cleared_page)


@pytest.fixture(scope="module")
def front_matter_moved_by_hand(tmp_path_factory: pytest.TempPathFactory) -> FrontMatterMovedByHand:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        document_id = create_document(client, kind="book")
        book, loose = new_id(), new_id()
        body = [scan(client, document_id, number, book, number - 1) for number in range(1, 6)]
        front = [scan(client, document_id, NO_NUMBER, loose, seq, minute=10) for seq in range(20)]
        document_once_read = wait_until_processed(client, document_id)
        markers_once_read = read_markers(client, document_id)
        moved = put_order(client, document_id, list_ids(front + body))
        moved_markers = read_markers(client, document_id)
        metadata = json.loads((api.settings.library_dir / "sample-cafe-guide" / "document.json").read_text())
        page_six = scan(client, document_id, 6, new_id(), 0, minute=20)
        document_with_page_six = wait_until_processed(client, document_id)
        markers_with_page_six = read_markers(client, document_id)
        restored = client.delete(f"/api/documents/{document_id}/order", headers=AUTH)
        restored_markers = read_markers(client, document_id)
        return FrontMatterMovedByHand(
            body=body,
            front=front,
            document_once_read=document_once_read,
            markers_once_read=markers_once_read,
            move_status=moved.status_code,
            moved_document=moved.json(),
            moved_markers=moved_markers,
            moved_metadata_pages=metadata["pages"],
            page_six=page_six,
            document_with_page_six=document_with_page_six,
            markers_with_page_six=markers_with_page_six,
            restore_status=restored.status_code,
            restored_document=restored.json(),
            restored_markers=restored_markers,
            document_read_after_restore=client.get(f"/api/documents/{document_id}", headers=AUTH).json(),
            document_restored_again=client.delete(f"/api/documents/{document_id}/order", headers=AUTH).json(),
        )


@pytest.fixture(scope="module")
def page_moved_by_hand(tmp_path_factory: pytest.TempPathFactory) -> PageMovedByHand:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        document_id = create_document(api.client)
        session = new_id()
        pages = [scan(api.client, document_id, number, session, number) for number in range(1, 7)]
        wait_until_processed(api.client, document_id)
        page_one, page_two, page_three, page_four, page_five, page_six = pages
        order_put = list_ids([page_one, page_five, page_two, page_three, page_four, page_six])
        moved_document = put_order(api.client, document_id, order_put).json()
        moved_markers = read_markers(api.client, document_id)
        document_moved_again = put_order(api.client, document_id, order_put).json()
        document_put_back = put_order(api.client, document_id, list_ids(pages)).json()
        return PageMovedByHand(pages, order_put, moved_document, moved_markers, document_moved_again, document_put_back)


@pytest.fixture(scope="module")
def loose_pages_moved_by_hand(tmp_path_factory: pytest.TempPathFactory) -> LoosePagesMovedByHand:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        document_id = create_document(client, kind="book")
        book, loose_session = new_id(), new_id()
        front = [scan(client, document_id, NO_NUMBER, book, seq) for seq in range(20)]
        first = [scan(client, document_id, number, book, 19 + number) for number in range(1, 6)]
        plate = scan(client, document_id, NO_NUMBER, book, 25)
        rest = [scan(client, document_id, number, book, 20 + number) for number in range(6, 11)]
        loose = [scan(client, document_id, NO_NUMBER, loose_session, seq, minute=30) for seq in range(3)]
        document_once_read = wait_until_processed(client, document_id)
        in_book = [*front, *first, plate, *rest]
        order_between = list_ids([*front, *loose, *first, plate, *rest])
        document_moved_between = put_order(client, document_id, order_between).json()
        markers_moved_between = read_markers(client, document_id)
        document_moved_between_again = put_order(client, document_id, order_between).json()
        document_moved_first = put_order(client, document_id, list_ids(loose + in_book)).json()
        restored_document = client.delete(f"/api/documents/{document_id}/order", headers=AUTH).json()
        return LoosePagesMovedByHand(
            in_book=in_book,
            loose=loose,
            document_once_read=document_once_read,
            order_between=order_between,
            document_moved_between=document_moved_between,
            markers_moved_between=markers_moved_between,
            document_moved_between_again=document_moved_between_again,
            document_moved_first=document_moved_first,
            restored_document=restored_document,
        )


@pytest.fixture(scope="module")
def plate_moved_by_hand(tmp_path_factory: pytest.TempPathFactory) -> PlateMovedByHand:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        document_id = create_document(client, kind="book")
        session = new_id()
        title = scan(client, document_id, NO_NUMBER, session, 0)
        page_one, page_two, page_three = (scan(client, document_id, number, session, number) for number in (1, 2, 3))
        plate = scan(client, document_id, NO_NUMBER, session, 4)
        page_four, page_five = (scan(client, document_id, number, session, number + 1) for number in (4, 5))
        document_once_read = wait_until_processed(client, document_id)
        order_put = list_ids([title, page_one, page_two, page_three, page_four, plate, page_five])
        moved_document = put_order(client, document_id, order_put).json()
        return PlateMovedByHand(plate, document_once_read, order_put, moved_document, read_markers(client, document_id))


@pytest.fixture(scope="module")
def refused_orders(tmp_path_factory: pytest.TempPathFactory) -> RefusedOrders:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        document_id = create_document(client)
        session = new_id()
        page_one, page_two, page_three, excluded = (
            scan(client, document_id, number, session, number) for number in (1, 2, 3, 4)
        )
        wait_until_processed(client, document_id)
        client.patch(f"/api/pages/{excluded['id']}", json={"excluded": True}, headers=AUTH).raise_for_status()
        other = create_document(client, "Other")
        foreign = scan(client, other, 1, new_id(), 0)
        wait_until_processed(client, other)
        changed_page_sets = {
            "a-page-missing": list_ids([page_one, page_two]),
            "a-page-out-of-the-reading-order": list_ids([page_one, page_two, page_three, excluded]),
            "a-page-of-another-document": list_ids([page_one, page_two, page_three, foreign]),
            "the-same-page-twice": list_ids([page_one, page_two, page_three, page_three]),
            "an-unknown-page": [*list_ids([page_one, page_two]), new_id()],
            "no-page": [],
        }
        changed_page_set_answers = {
            name: capture_answer(put_order(client, document_id, page_ids))
            for name, page_ids in changed_page_sets.items()
        }
        api.fake_ocr.unavailable = True  # the next page stays queued: not in the reading order yet
        queued = scan(client, document_id, 5, session, 5)
        accepted_order = list_ids([page_three, page_one, page_two])
        status_with_a_queued_page = put_order(client, document_id, [*accepted_order, queued["id"]]).status_code
        status_without_the_queued_page = put_order(client, document_id, accepted_order).status_code
        malformed_bodies: dict[str, object] = {
            "no-page-ids": {},
            "no-list": {"page_ids": None},
            "a-page-id-instead-of-a-list": {"page_ids": page_one["id"]},
            "a-number-for-a-page-id": {"page_ids": [1]},
            "a-page-id-that-is-not-a-uuid": {"page_ids": ["p1"]},
            "an-uppercase-page-id": {"page_ids": [page_one["id"].upper()]},
            "over-10000-page-ids": {"page_ids": [new_id()] * 10_001},
        }
        malformed_statuses = {
            name: client.put(f"/api/documents/{document_id}/order", json=body, headers=AUTH).status_code
            for name, body in malformed_bodies.items()
        }
        unknown_document = {
            method: capture_answer(
                client.request(method, f"/api/documents/{new_id()}/order", json={"page_ids": []}, headers=AUTH)
            )
            for method in ("PUT", "DELETE")
        }
        document = client.get(f"/api/documents/{document_id}", headers=AUTH).json()
        return RefusedOrders(
            changed_page_sets=changed_page_set_answers,
            status_with_a_queued_page=status_with_a_queued_page,
            status_without_the_queued_page=status_without_the_queued_page,
            malformed_statuses=malformed_statuses,
            unknown_document=unknown_document,
            accepted_order=accepted_order,
            order_after_refusals=list_ids(select_reading_order(document)),
        )


@pytest.fixture(scope="module")
def letter_moved_by_hand(tmp_path_factory: pytest.TempPathFactory) -> LetterMovedByHand:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        document_id = create_document(api.client, "Letter")
        pages = [scan(api.client, document_id, NO_NUMBER, new_id(), 0, minute=minute) for minute in (1, 2, 3)]
        document_once_read = wait_until_processed(api.client, document_id)
        first, second, last = pages
        order_put = list_ids([last, first, second])
        moved_document = put_order(api.client, document_id, order_put).json()
        return LetterMovedByHand(
            pages, document_once_read, order_put, moved_document, read_markers(api.client, document_id)
        )


class TestABookWithUnnumberedFrontMatter:
    class TestWhenItIsScannedWithPageOneInOneSession:
        @pytest.fixture(scope="class")
        @classmethod
        def front_matter_book(cls, tmp_path_factory: pytest.TempPathFactory) -> FrontMatterBook:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                document_id = create_document(api.client, kind="book")
                session = new_id()
                front = [scan(api.client, document_id, NO_NUMBER, session, seq) for seq in range(20)]
                body = [scan(api.client, document_id, number, session, 19 + number) for number in range(1, 6)]
                document = wait_until_processed(api.client, document_id)
                return FrontMatterBook(front, body, document, read_markers(api.client, document_id))

        def test_should_open_the_reading_order_with_the_front_matter(self, front_matter_book: FrontMatterBook) -> None:
            assert list_ids(select_reading_order(front_matter_book.document)) == list_ids(
                front_matter_book.front + front_matter_book.body
            )

        def test_should_place_the_front_matter_by_its_session_and_the_other_pages_by_their_numbers(
            self, front_matter_book: FrontMatterBook
        ) -> None:
            assert list_placements(front_matter_book.document) == ["session"] * 20 + ["number"] * 5

        def test_should_label_only_the_numbered_pages(self, front_matter_book: FrontMatterBook) -> None:
            assert list_labels(front_matter_book.document) == [None] * 20 + ["1", "2", "3", "4", "5"]

        def test_should_give_no_page_a_position_of_its_own(self, front_matter_book: FrontMatterBook) -> None:
            assert [page["position"] for page in front_matter_book.document["pages"]] == [None] * 25

        def test_should_cover_pages_one_to_five_and_count_the_unnumbered_pages(
            self, front_matter_book: FrontMatterBook
        ) -> None:
            coverage = front_matter_book.document["coverage"]
            assert (coverage["label"], coverage["unnumbered"]) == ("1–5", 20)

        def test_should_take_the_first_front_page_as_the_cover(self, front_matter_book: FrontMatterBook) -> None:
            first_front_page = front_matter_book.front[0]
            assert front_matter_book.document["cover_thumb_url"] == f"/api/pages/{first_front_page['id']}/thumb"

        def test_should_mark_each_page_in_its_markdown_without_an_unnumbered_heading(
            self, front_matter_book: FrontMatterBook
        ) -> None:
            assert front_matter_book.markers == build_markers(select_reading_order(front_matter_book.document))


class TestABookWithRomanFrontMatterAndItsMainTextInOneSession:
    class TestWhenTheOcrFindsOnlySomeOfItsNumbers:
        def test_should_read_the_pages_in_the_order_of_their_scans(self, roman_book: RomanBook) -> None:
            assert list_ids(select_reading_order(roman_book.document)) == list_ids(roman_book.pages)

        def test_should_infer_the_numbers_it_misses_from_those_it_finds(self, roman_book: RomanBook) -> None:
            assert list_labels(roman_book.document) == [int_to_roman(seq) for seq in range(1, 22)] + [
                "xxv",
                "1",
                "2",
                "3",
            ]

        def test_should_mark_the_numbers_of_the_two_pages_before_page_three_as_inferred(
            self, roman_book: RomanBook
        ) -> None:
            number_sources = [page["number_source"] for page in select_reading_order(roman_book.document)]
            assert number_sources[21:] == ["detected", "inferred", "inferred", "detected"]

        def test_should_place_every_page_by_its_number(self, roman_book: RomanBook) -> None:
            assert list_placements(roman_book.document) == ["number"] * 25

        def test_should_cover_pages_one_to_three_with_no_unnumbered_page(self, roman_book: RomanBook) -> None:
            coverage = roman_book.document["coverage"]
            assert (coverage["label"], coverage["unnumbered"]) == ("1–3", 0)

        def test_should_mark_each_page_in_its_markdown(self, roman_book: RomanBook) -> None:
            assert roman_book.markers == build_markers(select_reading_order(roman_book.document))

        class TestWhenANumberIsTypedOnAPageWhoseNumberIsInferred:
            def test_should_label_the_page_with_the_typed_number_since_a_number_typed_by_hand_wins(
                self, roman_book: RomanBook
            ) -> None:
                typed_page = roman_book.typed_page
                assert (typed_page["page_label"], typed_page["number_source"]) == ("1", "manual")

            class TestWhenTheTypedNumberIsCleared:
                def test_should_infer_the_same_number_again(self, roman_book: RomanBook) -> None:
                    cleared_page = roman_book.cleared_page
                    assert (cleared_page["page_label"], cleared_page["number_source"]) == ("1", "inferred")


class TestABookWhoseUnnumberedPagesAreScannedInASessionOfTheirOwn:
    class TestWhenItsPagesAreRead:
        def test_should_put_the_unnumbered_pages_last(self, front_matter_moved_by_hand: FrontMatterMovedByHand) -> None:
            book = front_matter_moved_by_hand
            assert list_ids(select_reading_order(book.document_once_read)) == list_ids(book.body + book.front)

        def test_should_leave_the_unnumbered_pages_unplaced_since_nothing_places_them(
            self, front_matter_moved_by_hand: FrontMatterMovedByHand
        ) -> None:
            assert list_placements(front_matter_moved_by_hand.document_once_read) == ["number"] * 5 + ["unplaced"] * 20

        def test_should_mark_the_unnumbered_pages_under_their_heading(
            self, front_matter_moved_by_hand: FrontMatterMovedByHand
        ) -> None:
            pages = select_reading_order(front_matter_moved_by_hand.document_once_read)
            assert front_matter_moved_by_hand.markers_once_read == [
                *build_markers(pages[:5]),
                UNNUMBERED_HEADING,
                *build_markers(pages[5:]),
            ]

        class TestWhenTheyAreMovedBeforePageOne:
            def test_should_accept_the_order(self, front_matter_moved_by_hand: FrontMatterMovedByHand) -> None:
                assert front_matter_moved_by_hand.move_status == 200

            def test_should_read_them_first(self, front_matter_moved_by_hand: FrontMatterMovedByHand) -> None:
                book = front_matter_moved_by_hand
                assert list_ids(select_reading_order(book.moved_document)) == list_ids(book.front + book.body)

            def test_should_give_each_moved_page_a_position_before_page_one(
                self, front_matter_moved_by_hand: FrontMatterMovedByHand
            ) -> None:
                assert (
                    list_positions(front_matter_moved_by_hand.moved_document)
                    == [float(position) for position in range(-19, 1)] + [None] * 5
                )

            def test_should_place_the_moved_pages_by_hand(
                self, front_matter_moved_by_hand: FrontMatterMovedByHand
            ) -> None:
                assert list_placements(front_matter_moved_by_hand.moved_document) == ["manual"] * 20 + ["number"] * 5

            def test_should_label_only_the_numbered_pages(
                self, front_matter_moved_by_hand: FrontMatterMovedByHand
            ) -> None:
                assert list_labels(front_matter_moved_by_hand.moved_document) == [None] * 20 + ["1", "2", "3", "4", "5"]

            def test_should_cover_pages_one_to_five_without_duplicates(
                self, front_matter_moved_by_hand: FrontMatterMovedByHand
            ) -> None:
                document = front_matter_moved_by_hand.moved_document
                assert (document["coverage"]["label"], document["stats"]["duplicates"]) == ("1–5", 0)

            def test_should_take_the_first_moved_page_as_the_cover(
                self, front_matter_moved_by_hand: FrontMatterMovedByHand
            ) -> None:
                first_front_page = front_matter_moved_by_hand.front[0]
                cover_thumb_url = front_matter_moved_by_hand.moved_document["cover_thumb_url"]
                assert cover_thumb_url == f"/api/pages/{first_front_page['id']}/thumb"

            def test_should_mark_each_page_in_its_markdown_without_an_unnumbered_heading(
                self, front_matter_moved_by_hand: FrontMatterMovedByHand
            ) -> None:
                book = front_matter_moved_by_hand
                assert book.moved_markers == build_markers(select_reading_order(book.moved_document))

            def test_should_write_the_positions_and_the_placements_to_the_metadata_of_the_document(
                self, front_matter_moved_by_hand: FrontMatterMovedByHand
            ) -> None:
                book = front_matter_moved_by_hand
                assert [(page["id"], page["position"], page["placement"]) for page in book.moved_metadata_pages] == [
                    (page["id"], page["position"], page["placement"]) for page in book.moved_document["pages"]
                ]

            class TestWhenPageSixIsScannedLater:
                def test_should_slot_it_in_after_page_five(
                    self, front_matter_moved_by_hand: FrontMatterMovedByHand
                ) -> None:
                    book = front_matter_moved_by_hand
                    assert list_ids(select_reading_order(book.document_with_page_six)) == [
                        *list_ids(book.front + book.body),
                        book.page_six["id"],
                    ]

                def test_should_place_it_by_its_number(
                    self, front_matter_moved_by_hand: FrontMatterMovedByHand
                ) -> None:
                    assert list_placements(front_matter_moved_by_hand.document_with_page_six)[-1] == "number"

                def test_should_mark_each_page_in_its_markdown(
                    self, front_matter_moved_by_hand: FrontMatterMovedByHand
                ) -> None:
                    book = front_matter_moved_by_hand
                    assert book.markers_with_page_six == build_markers(
                        select_reading_order(book.document_with_page_six)
                    )

                class TestWhenTheAutomaticOrderIsRestored:
                    def test_should_accept_it(self, front_matter_moved_by_hand: FrontMatterMovedByHand) -> None:
                        assert front_matter_moved_by_hand.restore_status == 200

                    def test_should_put_the_unnumbered_pages_last_again(
                        self, front_matter_moved_by_hand: FrontMatterMovedByHand
                    ) -> None:
                        book = front_matter_moved_by_hand
                        assert list_ids(select_reading_order(book.restored_document)) == [
                            *list_ids(book.body),
                            book.page_six["id"],
                            *list_ids(book.front),
                        ]

                    def test_should_clear_every_position(
                        self, front_matter_moved_by_hand: FrontMatterMovedByHand
                    ) -> None:
                        restored_pages = front_matter_moved_by_hand.restored_document["pages"]
                        assert [page["position"] for page in restored_pages] == [None] * 26

                    def test_should_leave_the_unnumbered_pages_unplaced(
                        self, front_matter_moved_by_hand: FrontMatterMovedByHand
                    ) -> None:
                        assert (
                            list_placements(front_matter_moved_by_hand.restored_document)
                            == ["number"] * 6 + ["unplaced"] * 20
                        )

                    def test_should_mark_the_unnumbered_pages_under_their_heading_again(
                        self, front_matter_moved_by_hand: FrontMatterMovedByHand
                    ) -> None:
                        pages = select_reading_order(front_matter_moved_by_hand.restored_document)
                        assert front_matter_moved_by_hand.restored_markers == [
                            *build_markers(pages[:6]),
                            UNNUMBERED_HEADING,
                            *build_markers(pages[6:]),
                        ]

                    def test_should_answer_the_document_as_it_reads_afterwards(
                        self, front_matter_moved_by_hand: FrontMatterMovedByHand
                    ) -> None:
                        book = front_matter_moved_by_hand
                        assert book.document_read_after_restore == book.restored_document

                    def test_should_change_nothing_when_restored_again_since_nothing_is_left_to_clear(
                        self, front_matter_moved_by_hand: FrontMatterMovedByHand
                    ) -> None:
                        book = front_matter_moved_by_hand
                        assert book.document_restored_again == book.restored_document


class TestADocumentOfNumberedPages:
    class TestWhenPageFiveIsMovedAfterPageOne:
        def test_should_read_the_pages_in_the_order_put(self, page_moved_by_hand: PageMovedByHand) -> None:
            moved = page_moved_by_hand
            assert list_ids(select_reading_order(moved.moved_document)) == moved.order_put

        def test_should_give_a_position_to_the_moved_page_only(self, page_moved_by_hand: PageMovedByHand) -> None:
            page_five = page_moved_by_hand.pages[4]
            assert map_positions(page_moved_by_hand.moved_document) == {page_five["id"]: 1.5}

        def test_should_place_the_moved_page_by_hand_and_the_others_by_their_numbers(
            self, page_moved_by_hand: PageMovedByHand
        ) -> None:
            assert list_placements(page_moved_by_hand.moved_document) == [
                "number",
                "manual",
                "number",
                "number",
                "number",
                "number",
            ]

        def test_should_keep_the_labels_of_the_pages(self, page_moved_by_hand: PageMovedByHand) -> None:
            assert list_labels(page_moved_by_hand.moved_document) == ["1", "5", "2", "3", "4", "6"]

        def test_should_mark_each_page_in_its_markdown(self, page_moved_by_hand: PageMovedByHand) -> None:
            moved = page_moved_by_hand
            assert moved.moved_markers == build_markers(select_reading_order(moved.moved_document))

        def test_should_change_nothing_when_the_same_order_is_put_again(
            self, page_moved_by_hand: PageMovedByHand
        ) -> None:
            assert page_moved_by_hand.document_moved_again == page_moved_by_hand.moved_document

        class TestWhenItIsPutBackInItsPlace:
            def test_should_read_the_pages_in_the_order_of_their_numbers(
                self, page_moved_by_hand: PageMovedByHand
            ) -> None:
                moved = page_moved_by_hand
                assert list_ids(select_reading_order(moved.document_put_back)) == list_ids(moved.pages)

            def test_should_clear_its_position(self, page_moved_by_hand: PageMovedByHand) -> None:
                pages_put_back = page_moved_by_hand.document_put_back["pages"]
                assert [page["position"] for page in pages_put_back] == [None] * 6


class TestABookWithLoosePagesScannedOnTheirOwnLater:
    BOOK_PLACEMENTS = ("session",) * 20 + ("number",) * 5 + ("session",) + ("number",) * 5

    class TestWhenItsPagesAreRead:
        def test_should_put_the_loose_pages_last(self, loose_pages_moved_by_hand: LoosePagesMovedByHand) -> None:
            book = loose_pages_moved_by_hand
            assert list_ids(select_reading_order(book.document_once_read)) == list_ids(book.in_book + book.loose)

        def test_should_leave_the_loose_pages_unplaced(self, loose_pages_moved_by_hand: LoosePagesMovedByHand) -> None:
            assert list_placements(loose_pages_moved_by_hand.document_once_read) == [
                *TestABookWithLoosePagesScannedOnTheirOwnLater.BOOK_PLACEMENTS,
                *["unplaced"] * 3,
            ]

        class TestWhenTheLoosePagesAreMovedBetweenTheFrontMatterAndPageOne:
            def test_should_read_the_pages_in_the_order_put(
                self, loose_pages_moved_by_hand: LoosePagesMovedByHand
            ) -> None:
                book = loose_pages_moved_by_hand
                assert list_ids(select_reading_order(book.document_moved_between)) == book.order_between

            def test_should_place_the_loose_pages_by_hand_and_leave_the_others_in_place(
                self, loose_pages_moved_by_hand: LoosePagesMovedByHand
            ) -> None:
                assert list_placements(loose_pages_moved_by_hand.document_moved_between) == [
                    *TestABookWithLoosePagesScannedOnTheirOwnLater.BOOK_PLACEMENTS[:20],
                    *["manual"] * 3,
                    *TestABookWithLoosePagesScannedOnTheirOwnLater.BOOK_PLACEMENTS[20:],
                ]

            def test_should_position_the_loose_pages_only_between_the_last_front_page_and_page_one(
                self, loose_pages_moved_by_hand: LoosePagesMovedByHand
            ) -> None:
                book = loose_pages_moved_by_hand
                page_one_position, gap_below_page_one = 1.0, 0.0001
                spacing = gap_below_page_one / (len(book.loose) + 1)
                between = {
                    page["id"]: page_one_position - gap_below_page_one + spacing * rank
                    for rank, page in enumerate(book.loose, 1)
                }
                assert map_positions(book.document_moved_between) == pytest.approx(between)

            def test_should_mark_each_page_in_its_markdown_without_an_unnumbered_heading_since_every_page_has_a_place(
                self, loose_pages_moved_by_hand: LoosePagesMovedByHand
            ) -> None:
                book = loose_pages_moved_by_hand
                assert book.markers_moved_between == build_markers(select_reading_order(book.document_moved_between))

            def test_should_change_nothing_when_the_same_order_is_put_again(
                self, loose_pages_moved_by_hand: LoosePagesMovedByHand
            ) -> None:
                book = loose_pages_moved_by_hand
                assert book.document_moved_between_again == book.document_moved_between

            class TestWhenTheyAreMovedToTheFrontInstead:
                def test_should_read_them_first(self, loose_pages_moved_by_hand: LoosePagesMovedByHand) -> None:
                    book = loose_pages_moved_by_hand
                    assert list_ids(select_reading_order(book.document_moved_first)) == list_ids(
                        book.loose + book.in_book
                    )

                def test_should_place_them_by_hand_and_leave_the_others_in_place(
                    self, loose_pages_moved_by_hand: LoosePagesMovedByHand
                ) -> None:
                    assert list_placements(loose_pages_moved_by_hand.document_moved_first) == [
                        *["manual"] * 3,
                        *TestABookWithLoosePagesScannedOnTheirOwnLater.BOOK_PLACEMENTS,
                    ]

                def test_should_position_them_before_the_first_front_page(
                    self, loose_pages_moved_by_hand: LoosePagesMovedByHand
                ) -> None:
                    book = loose_pages_moved_by_hand
                    assert map_positions(book.document_moved_first) == {
                        page["id"]: float(position) for position, page in zip(range(-22, -19), book.loose, strict=True)
                    }

                class TestWhenTheAutomaticOrderIsRestored:
                    def test_should_put_the_loose_pages_last_again(
                        self, loose_pages_moved_by_hand: LoosePagesMovedByHand
                    ) -> None:
                        book = loose_pages_moved_by_hand
                        assert list_ids(select_reading_order(book.restored_document)) == list_ids(
                            book.in_book + book.loose
                        )

                    def test_should_clear_every_position(
                        self, loose_pages_moved_by_hand: LoosePagesMovedByHand
                    ) -> None:
                        restored_pages = loose_pages_moved_by_hand.restored_document["pages"]
                        assert [page["position"] for page in restored_pages] == [None] * 34


class TestABookWithAnUnnumberedPlate:
    class TestWhenItsPagesAreRead:
        def test_should_place_its_unnumbered_pages_by_their_session(
            self, plate_moved_by_hand: PlateMovedByHand
        ) -> None:
            assert list_placements(plate_moved_by_hand.document_once_read) == [
                "session",
                "number",
                "number",
                "number",
                "session",
                "number",
                "number",
            ]

        class TestWhenThePlateIsMovedAfterPageFour:
            def test_should_read_the_pages_in_the_order_put(self, plate_moved_by_hand: PlateMovedByHand) -> None:
                book = plate_moved_by_hand
                assert list_ids(select_reading_order(book.moved_document)) == book.order_put

            def test_should_give_a_position_to_the_plate_only(self, plate_moved_by_hand: PlateMovedByHand) -> None:
                book = plate_moved_by_hand
                assert map_positions(book.moved_document) == {book.plate["id"]: 4.5}

            def test_should_place_the_plate_by_hand(self, plate_moved_by_hand: PlateMovedByHand) -> None:
                assert list_placements(plate_moved_by_hand.moved_document) == [
                    "session",
                    "number",
                    "number",
                    "number",
                    "number",
                    "manual",
                    "number",
                ]

            def test_should_mark_each_page_in_its_markdown(self, plate_moved_by_hand: PlateMovedByHand) -> None:
                book = plate_moved_by_hand
                assert book.moved_markers == build_markers(select_reading_order(book.moved_document))


class TestADocumentWhosePageMovedByHandIsRescanned:
    class TestWhenTheRescanIsRead:
        @pytest.fixture(scope="class")
        @classmethod
        def rescanned_page(cls, tmp_path_factory: pytest.TempPathFactory) -> RescannedPage:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                client = api.client
                document_id = create_document(client)
                first_session, later_session = new_id(), new_id()
                page_one, page_two, page_three = (
                    scan(client, document_id, number, first_session, number) for number in (1, 2, 3)
                )
                wait_until_processed(client, document_id)
                put_order(client, document_id, list_ids([page_three, page_one, page_two])).raise_for_status()
                rescan = scan(client, document_id, 3, later_session, 0, minute=30)
                document = wait_until_processed(client, document_id)
                pages_by_id = {page["id"]: page for page in document["pages"]}
                return RescannedPage(pages_by_id[page_three["id"]], rescan, [page_one, page_two], document)

        def test_should_make_the_earlier_scan_a_duplicate_of_the_rescan(self, rescanned_page: RescannedPage) -> None:
            assert rescanned_page.earlier_scan["duplicate_of"] == rescanned_page.rescan["id"]

        def test_should_take_the_earlier_scan_out_of_the_reading_order(self, rescanned_page: RescannedPage) -> None:
            assert rescanned_page.earlier_scan["in_document"] is False

        def test_should_keep_the_position_of_the_earlier_scan(self, rescanned_page: RescannedPage) -> None:
            assert rescanned_page.earlier_scan["position"] == 0.0

        def test_should_give_the_earlier_scan_no_placement(self, rescanned_page: RescannedPage) -> None:
            assert rescanned_page.earlier_scan["placement"] is None

        def test_should_read_the_rescan_in_the_place_of_its_number_since_the_position_was_the_earlier_scan_s(
            self, rescanned_page: RescannedPage
        ) -> None:
            assert list_ids(select_reading_order(rescanned_page.document)) == [
                *list_ids(rescanned_page.numbered_pages),
                rescanned_page.rescan["id"],
            ]

        def test_should_place_every_page_by_its_number(self, rescanned_page: RescannedPage) -> None:
            assert list_placements(rescanned_page.document) == ["number"] * 3

        def test_should_count_one_duplicate(self, rescanned_page: RescannedPage) -> None:
            assert rescanned_page.document["stats"]["duplicates"] == 1


class TestAReadingOrderPutByHand:
    class TestWhenItDoesNotHoldTheExactPagesOfTheReadingOrder:
        def test_should_refuse_it_as_a_conflict(self, refused_orders: RefusedOrders) -> None:
            page_sets = refused_orders.changed_page_sets
            accepted_page_sets = [name for name, answer in page_sets.items() if answer.status != 409]
            assert len(page_sets) == 6
            assert accepted_page_sets == []

        def test_should_say_that_the_page_set_changed(self, refused_orders: RefusedOrders) -> None:
            page_sets = refused_orders.changed_page_sets
            unexplained_page_sets = [
                name for name, answer in page_sets.items() if answer.body != {"detail": "page set changed"}
            ]
            assert len(page_sets) == 6
            assert unexplained_page_sets == []

    class TestWhenAPageIsStillQueued:
        def test_should_refuse_an_order_that_holds_it_since_it_is_not_in_the_reading_order_yet(
            self, refused_orders: RefusedOrders
        ) -> None:
            assert refused_orders.status_with_a_queued_page == 409

        def test_should_accept_an_order_of_the_pages_already_read(self, refused_orders: RefusedOrders) -> None:
            assert refused_orders.status_without_the_queued_page == 200

    class TestWhenItsBodyIsMalformed:
        def test_should_refuse_it_as_invalid(self, refused_orders: RefusedOrders) -> None:
            statuses = refused_orders.malformed_statuses
            accepted_bodies = [name for name, status in statuses.items() if status != 422]
            assert len(statuses) == 7
            assert accepted_bodies == []

    class TestWhenTheDocumentIsUnknown:
        def test_should_answer_not_found_to_a_put_or_a_delete(self, refused_orders: RefusedOrders) -> None:
            answers = refused_orders.unknown_document
            found_methods = [method for method, answer in answers.items() if answer.status != 404]
            assert len(answers) == 2
            assert found_methods == []

        def test_should_say_that_the_document_is_not_found(self, refused_orders: RefusedOrders) -> None:
            answers = refused_orders.unknown_document
            unexplained_methods = [
                method for method, answer in answers.items() if answer.body != {"detail": "document not found"}
            ]
            assert len(answers) == 2
            assert unexplained_methods == []

    class TestWhenRequestsAreRefused:
        def test_should_keep_the_order_accepted_before(self, refused_orders: RefusedOrders) -> None:
            assert refused_orders.order_after_refusals == refused_orders.accepted_order


class TestALetterWithoutPageNumbers:
    class TestWhenItsPagesAreRead:
        def test_should_read_them_in_the_order_of_their_capture(self, letter_moved_by_hand: LetterMovedByHand) -> None:
            letter = letter_moved_by_hand
            assert list_ids(select_reading_order(letter.document_once_read)) == list_ids(letter.pages)

        def test_should_leave_them_unplaced(self, letter_moved_by_hand: LetterMovedByHand) -> None:
            assert list_placements(letter_moved_by_hand.document_once_read) == ["unplaced"] * 3

        class TestWhenItsLastPageIsMovedFirst:
            def test_should_read_the_pages_in_the_order_put(self, letter_moved_by_hand: LetterMovedByHand) -> None:
                letter = letter_moved_by_hand
                assert list_ids(select_reading_order(letter.moved_document)) == letter.order_put

            def test_should_give_a_position_to_the_moved_page_only_and_keep_the_others_in_the_order_of_their_capture(
                self, letter_moved_by_hand: LetterMovedByHand
            ) -> None:
                assert list_positions(letter_moved_by_hand.moved_document) == [1.0, None, None]

            def test_should_place_the_moved_page_by_hand_and_leave_the_others_unplaced(
                self, letter_moved_by_hand: LetterMovedByHand
            ) -> None:
                assert list_placements(letter_moved_by_hand.moved_document) == ["manual", "unplaced", "unplaced"]

            def test_should_mark_each_page_in_its_markdown_without_an_unnumbered_heading_since_no_page_has_a_number(
                self, letter_moved_by_hand: LetterMovedByHand
            ) -> None:
                letter = letter_moved_by_hand
                assert letter.moved_markers == build_markers(select_reading_order(letter.moved_document))


class TestAReadingOrderChangedFromTheWebUi:
    class TestWhenItsRequestCarriesTheSessionCookie:
        @pytest.fixture(scope="class", params=["PUT", "DELETE"], ids=["put", "delete"])
        @classmethod
        def order_change(
            cls, request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
        ) -> OrderChangedFromTheWebUi:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                document_id = create_document(api.client)
                api.client.post("/api/session", json={"token": TOKEN}).raise_for_status()
                path = f"/api/documents/{document_id}/order"
                return OrderChangedFromTheWebUi(
                    status_without_header=api.client.request(request.param, path, json={"page_ids": []}).status_code,
                    status_with_header=api.client.request(
                        request.param, path, json={"page_ids": []}, headers={"X-ScanMyLib": "1"}
                    ).status_code,
                )

        def test_should_refuse_it_without_the_csrf_header(self, order_change: OrderChangedFromTheWebUi) -> None:
            assert order_change.status_without_header == 403

        def test_should_accept_it_with_the_csrf_header(self, order_change: OrderChangedFromTheWebUi) -> None:
            assert order_change.status_with_header == 200
