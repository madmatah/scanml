"""Page numbering and ordering (docs/ARCHITECTURE.md), on hand-built pages."""

from __future__ import annotations

import dataclasses
import itertools
import random
from collections.abc import Sequence
from typing import NamedTuple

import pytest

from scanmylib import ordering
from scanmylib.ordering import (
    SESSION_STEP,
    Coverage,
    CoverageJson,
    Layout,
    PageInput,
    PageNumber,
    compute_layout,
    int_to_roman,
    order_positions,
    parse_detected_numbers,
    positions_for_order,
    roman_to_int,
)

#: The numbers of pages 1–3, 7–8 and the spread 10–11.
COVERAGE_WITH_GAPS = Coverage(ranges=((1, 3), (7, 8), (10, 11)), unnumbered=0)


def page(
    page_id: str,
    *,
    session: str | None = "s1",
    seq: int | None = None,
    ts: float = 0.0,
    status: str = "done",
    excluded: bool = False,
    manual: int | None = None,
    hint: int | None = None,
    detected: tuple[str, ...] = (),
    position: float | None = None,
) -> PageInput:
    return PageInput(
        id=page_id,
        session_id=session,
        seq=seq,
        captured_ts=ts,
        status=status,
        excluded=excluded,
        manual_number=manual,
        hint_number=hint,
        detected_numbers=detected,
        position=position,
    )


def labels(layout: Layout, ids: Sequence[str] | None = None) -> list[str | None]:
    ids = layout.reading_order if ids is None else ids
    return [n.label if (n := layout.placements[i].number) else None for i in ids]


def label_of(page_number: PageNumber | None) -> str | None:
    return page_number.label if page_number is not None else None


class Reading(NamedTuple):
    page_number: PageNumber | None
    expected_page_number: PageNumber


class RomanReading(NamedTuple):
    page_number: PageNumber | None
    label: str | None
    expected_value: int
    expected_label: str


def placed_by(layout: Layout, ids: Sequence[str] | None = None) -> list[str | None]:
    ids = layout.reading_order if ids is None else ids
    return [layout.placements[i].placed_by for i in ids]


def sort_values(layout: Layout, ids: Sequence[str] | None = None) -> list[float | None]:
    ids = layout.reading_order if ids is None else ids
    return [layout.placements[i].sort_value for i in ids]


def numbers_and_sources(layout: Layout, ids: Sequence[str]) -> list[tuple[PageNumber | None, str | None]]:
    return [(layout.placements[i].number, layout.placements[i].source) for i in ids]


def book_with_roman_front_matter(typed: dict[int, int] | None = None) -> list[PageInput]:
    """25 pages of a book scanned in one session (seq 1–25), with the numbers `typed` by seq.

    Cover and unnumbered pages, front matter in roman numerals, then the main
    text; the OCR read "1X" (no number), XV, XXV, garbage instead of the 2, and 3.
    """
    detected = {11: ("1X",), 15: ("XV",), 22: ("XXV",), 24: ("$ x_{0} $",), 25: ("3",)}
    typed = typed or {}
    return [
        page(f"s{seq}", seq=seq, ts=seq, detected=detected.get(seq, ()), manual=typed.get(seq)) for seq in range(1, 26)
    ]


def session_labels(detected: Sequence[str]) -> list[str | None]:
    """Labels of the pages of one session, in seq order, from the number found on each ("": none)."""
    pages = [page(f"s{seq}", seq=seq, ts=seq, detected=(text,) if text else ()) for seq, text in enumerate(detected)]
    return labels(compute_layout(pages), [p.id for p in pages])


def book_scanned_in_order(rng: random.Random, *, skipping: bool) -> tuple[list[PageInput], list[str]]:
    """One session over a run of a book (roman front matter, then the main text from page 1), in order.

    The OCR misses the number of some pages (nothing found, or garbage);
    `skipping`: some pages of the run are left out. Returns the pages, in seq
    order, and their real labels.
    """
    book = [int_to_roman(v) for v in range(1, rng.randint(0, 30) + 1)]
    book += [str(v) for v in range(1, rng.randint(1, 40) + 1)]
    start = rng.randrange(len(book))
    run = book[start : rng.randint(start + 1, len(book))]
    real = [label for label in run if not skipping or rng.random() < 0.7] or run[:1]
    found = rng.random()  # share of the numbers the OCR reads
    pages = []
    for seq, label in enumerate(real, start=1):
        detected: tuple[str, ...]
        if rng.random() < found:
            detected = (rng.choice([label, label.upper()]),)
        else:
            detected = rng.choice([(), ("1X",), ("$ x_{0} $",)])
        pages.append(page(f"s{seq}", seq=seq, ts=seq, detected=detected))
    return pages, real


def expected_labels(pages: Sequence[PageInput], real: Sequence[str]) -> list[str | None]:
    found = [k for k, p in enumerate(pages) if parse_detected_numbers(p.detected_numbers)]
    expected: list[str | None] = []
    for k, label in enumerate(real):
        before, after = [j for j in found if j <= k], [j for j in found if j > k]
        if before and (after or real[before[-1]].isdigit() == label.isdigit()):
            expected.append(label)
        elif before:
            last_found = roman_to_int(real[before[-1]])
            if last_found is None:
                raise ValueError(
                    "the front matter does not come first: the last number found before the page is not roman"
                )
            expected.append(int_to_roman(last_found + k - before[-1]))
        elif after and real[after[0]].isdigit() == label.isdigit():
            expected.append(label)
        else:
            expected.append(None)
    return expected


def own_number(p: PageInput) -> tuple[PageNumber | None, str | None]:
    """The number a page has by itself, and its source: manual, else found by the OCR, else the hint."""
    if p.manual_number is not None:
        return PageNumber(p.manual_number), "manual"
    if (detected := parse_detected_numbers(p.detected_numbers)) is not None:
        return detected, "detected"
    if p.hint_number is not None:
        return PageNumber(p.hint_number), "hint"
    return None, None


def random_session(rng: random.Random) -> list[PageInput]:
    """Up to 12 pages of one session, their numbers in any order.

    Found by the OCR (arabic, roman, spread) or not, typed, hinted; gaps in
    seq, excluded pages, pages waiting for the OCR.
    """
    pages, seq = [], 0
    for index in range(rng.randint(1, 12)):
        seq += rng.choice([1, 1, 1, 2, 3])
        kind = rng.choice(["arabic", "roman", "spread", "none", "none", "none"])
        number = rng.randint(1, 30)
        detected = {
            "arabic": (str(number),),
            "roman": (int_to_roman(number),),
            "spread": (str(number), str(number + 1)),
        }.get(kind, ())
        pages.append(
            page(
                f"x{index}",
                seq=seq,
                ts=index,
                detected=detected,
                manual=rng.choice([None] * 9 + [rng.randint(1, 30)]),
                hint=rng.choice([None] * 9 + [rng.randint(1, 30)]),
                excluded=rng.random() < 0.1,
                status=rng.choice(["done"] * 9 + ["queued"]),
            )
        )
    return pages


class InferenceFindings(NamedTuple):
    page_ids: list[str]
    checked_page_ids: list[str]
    own_number_changed: list[str]
    not_counted_back_from_the_main_text: list[str]
    not_marked_inferred: list[str]
    out_of_range: list[str]
    on_a_numbered_page: list[str]
    counted_from_elsewhere: list[str]


def check_inference(pages: Sequence[PageInput], layout: Layout) -> InferenceFindings:
    own = {p.id: own_number(p) for p in pages}
    anchors = [
        (p.seq, anchor) for p in pages if (anchor := own[p.id][0]) is not None and p.seq is not None and not p.excluded
    ]
    findings = InferenceFindings([p.id for p in pages], [], [], [], [], [], [], [])
    for p in pages:
        seq = p.seq
        if seq is None:
            continue
        findings.checked_page_ids.append(p.id)
        number, source = layout.placements[p.id].number, layout.placements[p.id].source
        if own[p.id][0] is not None:
            if (number, source) != own[p.id]:
                findings.own_number_changed.append(p.id)
            continue
        before = [(s, n) for s, n in anchors if s < seq]
        after = [(s, n) for s, n in anchors if s > seq]
        previous = before[-1][1] if before else None
        following = after[0][1] if after else None
        if previous is not None and following is not None and previous.front_matter and not following.front_matter:
            value = following.value - (after[0][0] - seq)
            main_text_before = next((n.last for _, n in reversed(before) if not n.front_matter), 0)
            if value > main_text_before and number != PageNumber(value):
                findings.not_counted_back_from_the_main_text.append(p.id)
        if number is None:
            continue
        if source != "inferred":
            findings.not_marked_inferred.append(p.id)
        if number.value < 1 or (number.front_matter and number.value > 399):
            findings.out_of_range.append(p.id)
        lower = [n for _, n in before if n.front_matter == number.front_matter]
        upper = [n for _, n in after if n.front_matter == number.front_matter]
        if (lower and lower[-1].last >= number.value) or (upper and number.value >= upper[0].value):
            findings.on_a_numbered_page.append(p.id)
        forward = previous is not None and number == PageNumber(
            previous.last + seq - before[-1][0], front_matter=previous.front_matter
        )
        backward = following is not None and number == PageNumber(
            following.value - (after[0][0] - seq), front_matter=following.front_matter
        )
        backward_allowed = following is not None and (
            previous is None or (previous.front_matter and not following.front_matter)
        )
        if not forward and not (backward and backward_allowed):
            findings.counted_from_elsewhere.append(p.id)
    return findings


class SessionReading(NamedTuple):
    labels: list[str | None]
    expected_labels: list[str | None]


class ComparedLayouts(NamedTuple):
    typed_layout: Layout
    inferred_layout: Layout


class BookScannedInOrder(NamedTuple):
    scan_order: tuple[str, ...]
    reading_order: tuple[str, ...]
    labels: list[str | None]
    expected_labels: list[str | None]
    coverage: Coverage


class BookScannedSkippingPages(NamedTuple):
    scan_order: tuple[str, ...]
    reading_order: tuple[str, ...]
    naturals: list[int]
    labels_of_the_numbers_found: list[str | None]
    real_labels_of_the_numbers_found: list[str]


# -- positions for an order chosen by the user ----------------------------------------------


def reorder(pages: list[PageInput], wanted: list[str]) -> tuple[list[float | None], list[PageInput]]:
    """Positions that order_positions gives for `wanted`, and the pages with those positions."""
    layout = compute_layout(pages)
    by_id = {p.id: p for p in pages}
    numbers = [layout.placements[i].number for i in wanted]
    positions = order_positions(
        [n.natural if n is not None else None for n in numbers], [by_id[i].position is not None for i in wanted]
    )
    new = dict(zip(wanted, positions, strict=True))
    return positions, [dataclasses.replace(p, position=new[p.id]) if p.id in new else p for p in pages]


def numbered_pages(*numbers: int) -> list[PageInput]:
    return [page(f"p{n}", seq=n, ts=n, detected=(str(n),)) for n in numbers]


def test_moving_one_page_sets_exactly_one_position() -> None:
    pages = numbered_pages(*range(1, 11))
    wanted = ["p1", "p2", "p7", "p3", "p4", "p5", "p6", "p8", "p9", "p10"]
    positions, moved = reorder(pages, wanted)
    assert positions == [None, None, 2.5, None, None, None, None, None, None, None]
    assert compute_layout(moved).reading_order == tuple(wanted)
    # Asking for the same order again changes nothing.
    assert reorder(moved, wanted)[0] == positions


def test_pages_moved_before_page_one_and_a_page_scanned_later() -> None:
    body = numbered_pages(1, 2, 3, 4, 5)
    front = [page(f"f{i}", session="loose", seq=i, ts=100 + i) for i in range(20)]
    assert compute_layout(body + front).reading_order[5:] == tuple(p.id for p in front)  # unplaced, at the end
    wanted = [p.id for p in front + body]
    positions, moved = reorder(body + front, wanted)
    assert positions == [float(v) for v in range(-19, 1)] + [None] * 5
    # Page 6, scanned later, slots in after page 5.
    layout = compute_layout([*moved, page("p6", session="later", ts=200, detected=("6",))])
    assert layout.reading_order == (*wanted, "p6")


def test_pages_between_two_kept_pages_share_the_gap() -> None:
    pages = [*numbered_pages(1, 2), page("x", session="x", ts=10), page("y", session="y", ts=11)]
    positions, moved = reorder(pages, ["p1", "x", "y", "p2"])
    assert positions == pytest.approx([None, 1 + 1 / 3, 1 + 2 / 3, None])
    assert compute_layout(moved).reading_order == ("p1", "x", "y", "p2")


def test_pages_after_the_last_kept_page_follow_it_one_by_one() -> None:
    pages = [*numbered_pages(4, 5), page("x", session="x", ts=10), page("y", session="y", ts=11)]
    positions, _ = reorder(pages, ["p4", "p5", "y", "x"])
    assert positions == [None, None, 6.0, 7.0]


def test_documents_without_numbers_get_positions_one_to_n() -> None:
    pages = [page(c, session=c, ts=i) for i, c in enumerate("abc")]
    positions, moved = reorder(pages, ["c", "a", "b"])
    assert positions == [1.0, 2.0, 3.0]
    layout = compute_layout(moved)
    assert layout.reading_order == ("c", "a", "b")
    assert placed_by(layout) == ["manual"] * 3


def test_pages_without_position_are_kept_first() -> None:
    # [1, 3, 2, 4]: keeping 1, 2, 4 or 1, 3, 4 both need one position; the
    # page that has one already is the one that keeps it.
    swapped = ["p1", "p3", "p2", "p4"]
    pages = numbered_pages(1, 2, 3, 4)
    with_2 = [dataclasses.replace(p, position=3.5) if p.id == "p2" else p for p in pages]
    with_3 = [dataclasses.replace(p, position=1.5) if p.id == "p3" else p for p in pages]
    assert reorder(with_2, swapped)[0] == [None, None, 3.5, None]
    assert reorder(with_3, swapped)[0] == [None, 1.5, None, None]
    # Back to the order of the numbers: no position at all.
    assert reorder(with_2, ["p1", "p2", "p3", "p4"])[0] == [None] * 4


def _best_kept_score(naturals: list[int | None], positioned: list[bool]) -> tuple[int, int]:
    """(length, pages without position) of the best increasing subsequence, by brute force."""
    best = (0, 0)
    for size in range(len(naturals), 0, -1):
        for indices in itertools.combinations(range(len(naturals)), size):
            values = [natural for i in indices if (natural := naturals[i]) is not None]
            if len(values) == size and all(a < b for a, b in itertools.pairwise(values)):
                best = max(best, (size, sum(not positioned[i] for i in indices)))
    return best


@pytest.mark.parametrize("seed", range(200))
def test_any_order_is_reproduced_with_the_fewest_positions(seed: int) -> None:
    rng = random.Random(seed)
    pages = []
    for index in range(rng.randint(1, 9)):
        kind = rng.choice(["arabic", "arabic", "roman", "spread", "loose", "plate"])
        number = rng.randint(1, 30)
        detected = {
            "arabic": (str(number),),
            "roman": (int_to_roman(number),),
            "spread": (str(number), str(number + 1)),
        }.get(kind, ())
        position = rng.choice([None, None, rng.uniform(-5, 35)])
        session = f"s{index}" if kind == "loose" else rng.choice(["a", "b"])
        pages.append(page(f"x{index}", session=session, seq=index, ts=index, detected=detected, position=position))
    layout = compute_layout(pages)
    wanted = list(layout.reading_order)
    rng.shuffle(wanted)
    positions, moved = reorder(pages, wanted)

    assert compute_layout(moved).reading_order == tuple(wanted)
    by_id = {p.id: p for p in pages}
    naturals = [n.natural if (n := layout.placements[i].number) else None for i in wanted]
    positioned = [by_id[i].position is not None for i in wanted]
    kept = [i for i, position in enumerate(positions) if position is None]
    assert (len(kept), sum(not positioned[i] for i in kept)) == _best_kept_score(naturals, positioned)
    assert [layout.placements[i].number for i in wanted] == [compute_layout(moved).placements[i].number for i in wanted]


# -- only the pages that moved get a position ------------------------------------------------------


def with_positions(pages: list[PageInput], positions: dict[str, float | None]) -> list[PageInput]:
    return [dataclasses.replace(p, position=positions[p.id]) if p.id in positions else p for p in pages]


def put_order(pages: list[PageInput], wanted: list[str]) -> tuple[dict[str, float | None], list[PageInput]]:
    """positions_for_order for `wanted`, and the pages with these positions: their reading order is `wanted`."""
    positions = positions_for_order(pages, wanted)
    moved = with_positions(pages, positions)
    assert compute_layout(moved).reading_order == tuple(wanted)
    return positions, moved


def given(positions: dict[str, float | None]) -> dict[str, float]:
    return {page_id: position for page_id, position in positions.items() if position is not None}


def moved_to(order: list[str], page_id: str, before: str) -> list[str]:
    wanted = [i for i in order if i != page_id]
    wanted.insert(wanted.index(before), page_id)
    return wanted


def users_book() -> list[PageInput]:
    """20 unnumbered front pages, pages 1–10 and a plate after page 5 in one session; 3 pages scanned on their own."""
    front = [page(f"f{i}", session="book", seq=i, ts=i) for i in range(20)]
    first = [page(f"p{n}", session="book", seq=19 + n, ts=19 + n, detected=(str(n),)) for n in range(1, 6)]
    plate = page("plate", session="book", seq=25, ts=25)
    rest = [page(f"p{n}", session="book", seq=20 + n, ts=20 + n, detected=(str(n),)) for n in range(6, 11)]
    loose = [page(f"u{i}", session="loose", seq=i, ts=100 + i) for i in range(3)]
    return [*front, *first, plate, *rest, *loose]


BOOK_PLACEMENTS = ["session"] * 20 + ["number"] * 5 + ["session"] + ["number"] * 5


def test_moving_loose_pages_into_a_book_leaves_the_other_pages_in_place() -> None:
    pages = users_book()
    layout = compute_layout(pages)
    order = list(layout.reading_order)
    book, loose = order[:-3], order[-3:]
    assert loose == ["u0", "u1", "u2"]
    assert placed_by(layout) == [*BOOK_PLACEMENTS, "unplaced", "unplaced", "unplaced"]

    # To the front: the front pages and the plate stay placed by their session, without position.
    positions, moved = put_order(pages, loose + book)
    assert given(positions) == {"u0": -22.0, "u1": -21.0, "u2": -20.0}
    assert placed_by(compute_layout(moved)) == ["manual"] * 3 + BOOK_PLACEMENTS

    # Before page 1, i.e. after the last front page: between its place and page 1.
    wanted = [*book[:20], *loose, *book[20:]]
    positions, moved = put_order(pages, wanted)
    last_front = 1 - SESSION_STEP
    assert given(positions) == pytest.approx({f"u{k}": last_front + SESSION_STEP * (k + 1) / 4 for k in range(3)})
    layout = compute_layout(moved)
    assert placed_by(layout) == BOOK_PLACEMENTS[:20] + ["manual"] * 3 + BOOK_PLACEMENTS[20:]
    assert layout.placements["f19"].sort_value == pytest.approx(last_front)


def test_moving_one_session_page_sets_exactly_one_position() -> None:
    pages = users_book()
    order = list(compute_layout(pages).reading_order)
    positions, moved = put_order(pages, moved_to(order, "plate", before="p9"))
    assert given(positions) == {"plate": 8.5}
    layout = compute_layout(moved)
    assert placed_by(layout, ["f0", "f19", "plate", "u0"]) == ["session", "session", "manual", "unplaced"]
    # Put back after page 5, it keeps a position: only the numbered pages get theirs cleared.
    positions, moved = put_order(moved, order)
    assert given(positions) == {"plate": 5.5}


def test_a_moved_session_page_holds_the_pages_scanned_next_to_it() -> None:
    # f4 and f6 would follow f5, the page next to them in their session:
    # they get a position at their own place; the other front pages stay placed by their session.
    pages = users_book()
    before = compute_layout(pages)
    order = list(before.reading_order)
    wanted = moved_to(order, "f5", before="p4")
    positions, moved = put_order(pages, wanted)
    assert given(positions) == pytest.approx({"f4": 1 - 16 * SESSION_STEP, "f6": 1 - 14 * SESSION_STEP, "f5": 3.5})
    layout = compute_layout(moved)
    front = wanted[:19]
    places = [layout.placements[i].sort_value for i in front]
    assert places == pytest.approx([before.placements[i].sort_value for i in front])
    assert placed_by(layout, front).count("session") == 17


def test_a_page_placed_after_a_moved_page_keeps_its_place_with_a_position() -> None:
    # The plate follows page 5 in its session: it stays between pages 4 and 6 only with a position.
    pages = users_book()
    order = list(compute_layout(pages).reading_order)
    positions, _ = put_order(pages, moved_to(order, "p5", before="p9"))
    assert given(positions) == {"plate": 5.0, "p5": 8.5}


def test_unplaced_pages_left_in_their_order_stay_unplaced() -> None:
    pages = [page(c, session=c, ts=i) for i, c in enumerate("abc")]
    positions, moved = put_order(pages, ["c", "a", "b"])
    assert given(positions) == {"c": 1.0}
    assert placed_by(compute_layout(moved)) == ["manual", "unplaced", "unplaced"]


def test_the_page_scanned_before_a_moved_unnumbered_page_keeps_its_place() -> None:
    # One session without numbers: once d has a position, a, b and c would be placed next to it.
    # Holding c (scanned just before d) at the end is enough: a and b are placed before c.
    pages = [page(c, session="letter", seq=i, ts=i) for i, c in enumerate("abcd")]
    positions, moved = put_order(pages, ["d", "a", "b", "c"])
    assert given(positions) == {"d": 1.0, "c": 4.0}
    assert placed_by(compute_layout(moved)) == ["manual", "session", "session", "manual"]


def test_pages_moved_between_two_pages_at_the_same_place_move_one_of_them() -> None:
    # a0 and b0, scanned just before a page 1 in two sessions (a1 is a duplicate of b1), share
    # the place 1 − SESSION_STEP: x cannot go between them unless b0 gets a position too.
    pages = [
        page("a0", session="a", seq=0, ts=0),
        page("a1", session="a", seq=1, ts=1, detected=("1",)),
        page("b0", session="b", seq=0, ts=10),
        page("b1", session="b", seq=1, ts=11, detected=("1",)),
        page("x", session="x", seq=0, ts=20),
    ]
    layout = compute_layout(pages)
    assert layout.reading_order == ("a0", "b0", "b1", "x")
    assert layout.placements["a0"].sort_value == layout.placements["b0"].sort_value
    positions, moved = put_order(pages, ["a0", "x", "b0", "b1"])
    assert set(given(positions)) == {"x", "b0"}
    assert placed_by(compute_layout(moved)) == ["session", "manual", "manual", "number"]


def test_sending_the_current_order_again_changes_nothing() -> None:
    # Even positions that are not needed (set by an older version) stay.
    pages = with_positions(users_book(), {f"f{i}": float(i - 22) for i in range(20)})
    order = list(compute_layout(pages).reading_order)
    assert positions_for_order(pages, order) == {p.id: p.position for p in pages}


@pytest.mark.parametrize("wanted", [["p1", "p2"], ["p1", "p2", "p3", "p3"], ["p1", "p2", "p3", "p4"], []])
def test_positions_for_order_needs_exactly_the_pages_of_the_reading_order(wanted: list[str]) -> None:
    with pytest.raises(ValueError, match="not the pages of the reading order"):
        positions_for_order(numbered_pages(1, 2, 3), wanted)


def test_without_budget_the_order_is_still_the_wanted_one(monkeypatch: pytest.MonkeyPatch) -> None:
    # On a huge document the search stops early: more pages keep a position, the order is the same.
    monkeypatch.setattr(ordering, "REORDER_BUDGET", 0)
    pages = users_book()
    order = list(compute_layout(pages).reading_order)
    positions, _ = put_order(pages, moved_to(order, "f5", before="p4"))
    assert {"f4", "f5", "f6"} < set(given(positions))


def loose_groups(pages: list[PageInput], wanted: list[str]) -> tuple[set[str], set[str]]:
    """Pages without number nor position in every / in some largest group that can stay in place.

    Their places: the ones they get when none of them has a position and the
    other pages of `wanted` have their order_positions position. A group can
    stay in place if these places, with those of the numbered pages kept by
    order_positions, increase along `wanted`, unplaced pages only at its end.
    """
    layout = compute_layout(pages)
    by_id = {p.id: p for p in pages}
    numbers = [layout.placements[i].number for i in wanted]
    base = order_positions([n.natural if n else None for n in numbers], [by_id[i].position is not None for i in wanted])
    kept = {i for i, position in zip(wanted, base, strict=True) if position is None}
    loose = [i for i, n in zip(wanted, numbers, strict=True) if n is None and by_id[i].position is None]
    reference = compute_layout(with_positions(pages, {**dict(zip(wanted, base, strict=True)), **dict.fromkeys(loose)}))
    placements = reference.placements

    def stays(group: set[str]) -> bool:
        staying = [i for i in wanted if i in kept or i in group]
        if any(placements[a].rank >= placements[b].rank for a, b in itertools.pairwise(staying)):
            return False
        unplaced = [k for k, i in enumerate(wanted) if i in group and placements[i].sort_value is None]
        return not unplaced or all(i in group for i in wanted[unplaced[0] :])

    for size in range(len(loose), -1, -1):
        largest = [set(group) for group in itertools.combinations(loose, size) if stays(set(group))]
        if largest:
            return set.intersection(*largest), set.union(*largest)
    raise AssertionError("the empty group always stays")


def random_pages(rng: random.Random) -> list[PageInput]:
    """Up to 10 pages: numbered or not, in two book sessions or scanned apart; some positions, excluded, queued."""
    pages = []
    for index in range(rng.randint(1, 10)):
        kind = rng.choice(["arabic", "arabic", "roman", "spread", "unnumbered", "unnumbered", "loose", "loose"])
        number = rng.randint(1, 30)
        detected = {
            "arabic": (str(number),),
            "roman": (int_to_roman(number),),
            "spread": (str(number), str(number + 1)),
        }.get(kind, ())
        session = rng.choice([f"own{index}", "loose"]) if kind == "loose" else rng.choice(["a", "b"])
        pages.append(
            page(
                f"x{index}",
                session=session,
                seq=rng.choice([index, index, None]),
                ts=index,
                detected=detected,
                position=rng.choice([None, None, None, rng.uniform(-5, 35)]),
                excluded=rng.random() < 0.1,
                status=rng.choice(["done"] * 9 + ["queued"]),
            )
        )
    return pages


def block_moved(rng: random.Random, order: list[str]) -> list[str]:
    """`order` with a run of its pages moved elsewhere, as the page organizer does."""
    size = rng.randint(1, max(1, len(order) // 3))
    start = rng.randrange(len(order) - size + 1)
    block, rest = order[start : start + size], order[:start] + order[start + size :]
    at = rng.randint(0, len(rest))
    return rest[:at] + block + rest[at:]


@pytest.mark.parametrize("seed", range(300))
def test_any_order_positions_only_the_pages_that_moved(seed: int) -> None:
    rng = random.Random(seed)
    pages = random_pages(rng)
    for _ in range(2):  # a second order, from the positions given for the first one
        layout = compute_layout(pages)
        current = list(layout.reading_order)
        if not current:
            return
        wanted = block_moved(rng, current) if rng.random() < 0.5 else rng.sample(current, len(current))
        positions, moved = put_order(pages, wanted)  # the reading order is the wanted one
        numbers = [compute_layout(moved).placements[i].number for i in wanted]
        assert numbers == [layout.placements[i].number for i in wanted]
        by_id = {p.id: p for p in pages}
        if wanted != current:
            # Numbered pages: a longest increasing subsequence keeps its place, preferably pages without position.
            naturals = [n.natural if (n := layout.placements[i].number) else None for i in wanted]
            had = [by_id[i].position is not None for i in wanted]
            kept = [k for k, i in enumerate(wanted) if naturals[k] is not None and positions[i] is None]
            assert (len(kept), sum(not had[k] for k in kept)) == _best_kept_score(naturals, had)
            # Pages without number: one that had a position keeps one, one that moved gets one,
            # one that stays in place gets one only if the order needs it.
            unnumbered = [(i, has) for i, natural, has in zip(wanted, naturals, had, strict=True) if natural is None]
            assert all(positions[i] is not None for i, has in unnumbered if has)
            in_every, in_some = loose_groups(pages, wanted)
            assert all(positions[i] is not None for i, has in unnumbered if not has and i not in in_some)
            for i in in_every:
                if positions[i] is not None:
                    assert compute_layout(with_positions(moved, {i: None})).reading_order != tuple(wanted), i
        # The same order again changes nothing.
        assert positions_for_order(moved, wanted) == positions
        pages = moved


def random_book(rng: random.Random) -> list[PageInput]:
    """Books scanned in 1–3 sessions, then 1–4 loose sessions.

    Unnumbered front pages, roman front matter in the first session, numbered
    pages and plates; in some sessions, the OCR misses some numbers.
    """
    pages, ts, number = [], 0.0, 1
    for book in range(rng.randint(1, 3)):
        kinds = ["front"] * rng.randint(0, 6) + ["roman"] * (rng.randint(0, 6) if book == 0 else 0)
        for _ in range(rng.randint(1, 8)):
            kinds += ["number", "plate"] if rng.random() < 0.25 else ["number"]
        missed, roman = rng.choice([0, 0, 0.3]), 1
        for seq, kind in enumerate(kinds):
            detected: tuple[str, ...] = ()
            if kind == "roman":
                detected, roman = (int_to_roman(roman),), roman + 1
            elif kind == "number":
                detected, number = (str(number),), number + 1
            if rng.random() < missed:
                detected = ()
            pages.append(page(f"b{book}-{seq}", session=f"book{book}", seq=seq, ts=ts, detected=detected))
            ts += 1
        number += rng.randint(0, 5)
    for loose in range(rng.randint(1, 4)):
        for seq in range(rng.randint(1, 4)):
            pages.append(page(f"u{loose}-{seq}", session=f"loose{loose}", seq=seq, ts=1000 + ts))
            ts += 1
    return pages


@pytest.mark.parametrize("seed", range(200))
def test_moving_loose_sessions_into_a_book_positions_only_their_pages(seed: int) -> None:
    rng = random.Random(seed)
    pages = random_book(rng)
    by_id = {p.id: p for p in pages}
    layout = compute_layout(pages)
    order = list(layout.reading_order)
    sessions = sorted({session for p in pages if (session := p.session_id) is not None and session.startswith("loose")})
    moving = set(rng.sample(sessions, rng.randint(1, len(sessions))))
    block = [i for i in order if by_id[i].session_id in moving]
    if rng.random() < 0.3:
        rng.shuffle(block)
    rest = [i for i in order if i not in block]
    # Anywhere among the placed pages, but not between two pages at the same place: there is no room there.
    placed = sum(layout.placements[i].sort_value is not None for i in rest)
    place = [layout.placements[i].sort_value for i in rest]
    at = rng.choice([k for k in range(placed + 1) if k in (0, placed) or place[k - 1] != place[k]])
    positions, _ = put_order(pages, rest[:at] + block + rest[at:])
    assert set(given(positions)) <= set(block)


class TestTheOrdering:
    class TestTheParseDetectedNumbersFunction:
        class TestWhenATextIsAnArabicNumber:
            @pytest.fixture(
                params=[
                    (["42"], 42),
                    (["- 12 -"], 12),
                    (["— 7 —"], 7),
                    (["Page 9"], 9),
                    (["p. 15"], 15),
                    (["(23)"], 23),
                ],
                ids=["alone", "between hyphens", "between dashes", "after the word page", "after p.", "in parentheses"],
            )
            def reading(self, request: pytest.FixtureRequest) -> Reading:
                texts, value = request.param
                return Reading(page_number=parse_detected_numbers(texts), expected_page_number=PageNumber(value))

            def test_should_read_the_number_without_what_is_printed_around_it(self, reading: Reading) -> None:
                assert reading.page_number == reading.expected_page_number

        class TestWhenNoTextHoldsAPageNumber:
            @pytest.fixture(
                params=[["0"], ["12345"], ["1/2"], [""], []],
                ids=["zero", "five digits", "a fraction", "an empty text", "no text"],
            )
            def page_number(self, request: pytest.FixtureRequest) -> PageNumber | None:
                return parse_detected_numbers(request.param)

            def test_should_return_none(self, page_number: PageNumber | None) -> None:
                assert page_number is None

        class TestWhenTheTextsHoldTwoConsecutiveNumbers:
            @pytest.fixture(
                params=[(["42", "43"], 42), (["43", "42"], 42), (["12-13"], 12), (["3", "42", "43"], 42)],
                ids=["in order", "the right page read first", "joined by a hyphen", "after another number"],
            )
            def reading(self, request: pytest.FixtureRequest) -> Reading:
                texts, first_page = request.param
                return Reading(
                    page_number=parse_detected_numbers(texts),
                    expected_page_number=PageNumber(first_page, first_page + 1),
                )

            def test_should_read_a_spread_of_two_pages(self, reading: Reading) -> None:
                assert reading.page_number == reading.expected_page_number

        class TestWhenTheTextsHoldTwoNumbersThatAreNotConsecutive:
            @pytest.fixture
            def page_number(self) -> PageNumber | None:
                return parse_detected_numbers(["42", "57"])

            def test_should_read_the_first_one(self, page_number: PageNumber | None) -> None:
                assert page_number == PageNumber(42)

        class TestWhenATextIsARomanNumeral:
            @pytest.fixture(
                params=[(["xii"], 12, "xii"), (["XIV"], 14, "xiv"), (["- iv -"], 4, "iv"), (["cxc"], 190, "cxc")],
                ids=["in lowercase", "in uppercase", "between hyphens", "in the hundreds"],
            )
            def roman_reading(self, request: pytest.FixtureRequest) -> RomanReading:
                texts, value, label = request.param
                page_number = parse_detected_numbers(texts)
                return RomanReading(
                    page_number=page_number, label=label_of(page_number), expected_value=value, expected_label=label
                )

            def test_should_read_it_as_front_matter(self, roman_reading: RomanReading) -> None:
                assert roman_reading.page_number == PageNumber(roman_reading.expected_value, front_matter=True)

            def test_should_label_it_in_lowercase_roman_numerals(self, roman_reading: RomanReading) -> None:
                assert roman_reading.label == roman_reading.expected_label

        class TestWhenATextIsAWordOrANonCanonicalRomanNumeral:
            @pytest.fixture(
                params=["mix", "dim", "iiii", "vx", "civil", "M", "abc"],
                ids=[
                    "a word with an m",
                    "a word with a d",
                    "four ones",
                    "five before ten",
                    "a word of roman letters",
                    "a thousand, beyond front matter",
                    "a word",
                ],
            )
            def page_number(self, request: pytest.FixtureRequest) -> PageNumber | None:
                return parse_detected_numbers([request.param])

            def test_should_return_none_so_that_a_stray_word_never_numbers_a_page(
                self, page_number: PageNumber | None
            ) -> None:
                assert page_number is None

        class TestWhenTheTextsHoldAnArabicAndARomanNumber:
            @pytest.fixture
            def page_number(self) -> PageNumber | None:
                return parse_detected_numbers(["iv", "5"])

            def test_should_read_the_arabic_number(self, page_number: PageNumber | None) -> None:
                assert page_number == PageNumber(5)

    class TestTheRomanToIntFunction:
        class TestWhenTheNumeralIsWrittenByIntToRoman:
            @pytest.fixture
            def values_read_back(self) -> dict[int, int | None]:
                return {value: roman_to_int(int_to_roman(value)) for value in range(1, 400)}

            def test_should_read_back_every_value_from_1_to_399(self, values_read_back: dict[int, int | None]) -> None:
                assert len(values_read_back) == 399
                assert [value for value, read_back in values_read_back.items() if read_back != value] == []

    class TestThePageNumberLabelProperty:
        class TestWhenThePageNumberIsArabic:
            @pytest.fixture
            def label(self) -> str:
                return PageNumber(42).label

            def test_should_be_the_number(self, label: str) -> None:
                assert label == "42"

        class TestWhenThePageNumberIsASpread:
            @pytest.fixture
            def label(self) -> str:
                return PageNumber(42, 43).label

            def test_should_join_its_two_numbers_with_an_en_dash(self, label: str) -> None:
                assert label == "42–43"

        class TestWhenThePageNumberIsFrontMatter:
            @pytest.fixture
            def label(self) -> str:
                return PageNumber(12, front_matter=True).label

            def test_should_be_its_lowercase_roman_numeral(self, label: str) -> None:
                assert label == "xii"

    class TestTheComputeLayoutFunction:
        class TestWhenPagesHaveATypedAFoundOrAHintedNumber:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("a", manual=5, detected=("7",), hint=9),
                        page("b", detected=("7",), hint=9, ts=1),
                        page("c", hint=9, ts=2),
                    ]
                )

            def test_should_take_the_typed_number_then_the_one_found_then_the_hint(self, layout: Layout) -> None:
                assert numbers_and_sources(layout, ["a", "b", "c"]) == [
                    (PageNumber(5), "manual"),
                    (PageNumber(7), "detected"),
                    (PageNumber(9), "hint"),
                ]

        class TestWhenANumberIsTypedOnASpread:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout([page("a", manual=10, detected=("42", "43"))])

            def test_should_replace_the_spread(self, layout: Layout) -> None:
                assert layout.placements["a"].number == PageNumber(10)

        class TestWhenPagesFollowANumberedPageInTheirSession:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("a", seq=0, detected=("10",)),
                        page("b", seq=1, ts=1),
                        page("c", seq=2, ts=2),
                    ]
                )

            def test_should_count_on_from_it(self, layout: Layout) -> None:
                assert labels(layout) == ["10", "11", "12"]

            def test_should_mark_their_numbers_as_inferred(self, layout: Layout) -> None:
                assert [layout.placements[i].source for i in ("b", "c")] == ["inferred", "inferred"]

        class TestWhenPagesComeBeforeTheFirstNumberedPageOfTheirSession:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("a", seq=0),
                        page("b", seq=1, ts=1),
                        page("c", seq=2, ts=2, detected=("5",)),
                    ]
                )

            def test_should_count_back_from_it(self, layout: Layout) -> None:
                assert labels(layout, ["a", "b", "c"]) == ["3", "4", "5"]

        class TestWhenCountingBackWouldGoBelowPage1:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout([page("a", seq=0), page("b", seq=1, ts=1, detected=("1",))])

            def test_should_leave_the_page_unnumbered(self, layout: Layout) -> None:
                assert layout.placements["a"].number is None

        class TestWhenShotsWereDeletedBetweenTwoPagesOfASession:
            @pytest.fixture
            def layout(self) -> Layout:
                # Shots 1 and 2 went, say blurry ones scanned again elsewhere.
                return compute_layout([page("a", seq=0, detected=("10",)), page("b", seq=3, ts=1)])

            def test_should_count_the_distance_in_shots(self, layout: Layout) -> None:
                assert layout.placements["b"].number == PageNumber(13)

        class TestWhenAnUnnumberedPlateLiesBetweenTwoConsecutivePages:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("p10", seq=0, detected=("10",)),
                        page("plate", seq=1, ts=1),
                        page("p11", seq=2, ts=2, detected=("11",)),
                    ]
                )

            def test_should_leave_the_plate_unnumbered_rather_than_give_it_the_number_of_the_next_page(
                self, layout: Layout
            ) -> None:
                assert layout.placements["plate"].number is None

            def test_should_keep_the_plate_in_the_document(self, layout: Layout) -> None:
                assert layout.placements["plate"].in_document

            def test_should_not_take_the_next_page_for_a_duplicate(self, layout: Layout) -> None:
                assert layout.placements["p11"].duplicate_of is None

        class TestWhenTheNumberedPageBeforeIsASpread:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout([page("a", seq=0, detected=("42", "43")), page("b", seq=1, ts=1)])

            def test_should_count_on_from_its_last_page(self, layout: Layout) -> None:
                assert layout.placements["b"].number == PageNumber(44)

        class TestWhenTheNumberedPageBeforeIsFrontMatter:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout([page("a", seq=0, detected=("ix",)), page("b", seq=1, ts=1)])

            def test_should_count_on_in_the_front_matter(self, layout: Layout) -> None:
                assert layout.placements["b"].number == PageNumber(10, front_matter=True)

            def test_should_label_the_page_in_roman_numerals(self, layout: Layout) -> None:
                assert labels(layout, ["b"]) == ["x"]

        class TestWhenTheNumberedPageWasScannedInAnotherSessionOrWithoutOne:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("a", session="s1", seq=0, detected=("10",)),
                        page("b", session="s2", seq=1, ts=1),
                        page("c", session=None, seq=1, ts=2),
                    ]
                )

            def test_should_leave_the_page_of_another_session_unnumbered(self, layout: Layout) -> None:
                assert layout.placements["b"].number is None

            def test_should_leave_the_page_without_a_session_unnumbered(self, layout: Layout) -> None:
                assert layout.placements["c"].number is None

        class TestWhenTheNumberedPageBeforeIsExcluded:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout([page("a", seq=0, detected=("10",), excluded=True), page("b", seq=1, ts=1)])

            def test_should_not_count_from_it(self, layout: Layout) -> None:
                assert layout.placements["b"].number is None

        class TestWhenThePageBeforeWaitsForOcrWithAHint:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout([page("a", seq=0, hint=20, status="queued"), page("b", seq=1, ts=1)])

            def test_should_count_on_from_the_hint(self, layout: Layout) -> None:
                assert layout.placements["b"].number == PageNumber(21)

        class TestWhenABookIsScannedFromItsFrontMatterIntoItsMainTextInOneSession:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(book_with_roman_front_matter())

            def test_should_number_the_two_pages_between_xxv_and_3_as_pages_1_and_2_not_xxvi_and_xxvii(
                self, layout: Layout
            ) -> None:
                scanned = [f"s{seq}" for seq in range(1, 26)]
                front_matter = "i ii iii iv v vi vii viii ix x xi xii xiii xiv xv xvi xvii xviii xix xx xxi xxv".split()
                assert labels(layout, scanned) == [*front_matter, "1", "2", "3"]

            def test_should_mark_the_numbers_of_those_two_pages_as_inferred_and_that_of_page_3_as_found(
                self, layout: Layout
            ) -> None:
                sources = [layout.placements[i].source for i in ("s23", "s24", "s25")]
                assert sources == ["inferred", "inferred", "detected"]

            def test_should_keep_the_pages_in_the_order_of_the_scan(self, layout: Layout) -> None:
                assert layout.reading_order == tuple(f"s{seq}" for seq in range(1, 26))

            def test_should_place_every_page_by_its_number(self, layout: Layout) -> None:
                assert placed_by(layout) == ["number"] * 25

            def test_should_cover_pages_1_to_3_and_count_no_page_as_unnumbered(self, layout: Layout) -> None:
                assert (layout.coverage.label, layout.coverage.unnumbered) == ("1–3", 0)

        class TestWhenTheUserTypedTheNumbersItWouldInfer:
            @pytest.fixture
            def compared_layouts(self) -> ComparedLayouts:
                return ComparedLayouts(
                    typed_layout=compute_layout(book_with_roman_front_matter({23: 1, 24: 2})),
                    inferred_layout=compute_layout(book_with_roman_front_matter()),
                )

            def test_should_keep_the_typed_numbers(self, compared_layouts: ComparedLayouts) -> None:
                assert numbers_and_sources(compared_layouts.typed_layout, ["s23", "s24"]) == [
                    (PageNumber(1), "manual"),
                    (PageNumber(2), "manual"),
                ]

            def test_should_infer_the_same_numbers_without_them(self, compared_layouts: ComparedLayouts) -> None:
                assert numbers_and_sources(compared_layouts.inferred_layout, ["s23", "s24"]) == [
                    (PageNumber(1), "inferred"),
                    (PageNumber(2), "inferred"),
                ]

            def test_should_keep_the_same_order(self, compared_layouts: ComparedLayouts) -> None:
                assert compared_layouts.typed_layout.reading_order == compared_layouts.inferred_layout.reading_order

        class TestWhenTheUserTypedPage1OnThePageReadAsXxv:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(book_with_roman_front_matter({22: 1}))

            def test_should_end_the_front_matter_before_it_count_on_from_it_and_leave_an_extra_photo_before_page_3(
                self, layout: Layout
            ) -> None:
                assert labels(layout, ["s21", "s22", "s23", "s24", "s25"]) == ["xxi", "1", "2", None, "3"]

            def test_should_keep_the_typed_number(self, layout: Layout) -> None:
                assert layout.placements["s22"].source == "manual"

        class TestWhenTheNumberingSystemChangesWithinASession:
            class TestWhenTheFrontMatterLeadsIntoTheMainText:
                @pytest.fixture(
                    params=[
                        (["xxv", "", "", "3"], ["xxv", "1", "2", "3"]),
                        (["xxv", "", "", "4-5"], ["xxv", "2", "3", "4–5"]),
                    ],
                    ids=["up to a page", "up to a spread"],
                )
                def session_reading(self, request: pytest.FixtureRequest) -> SessionReading:
                    detected, expected = request.param
                    return SessionReading(labels=session_labels(detected), expected_labels=expected)

                def test_should_count_back_from_the_main_text_which_starts_at_page_1(
                    self, session_reading: SessionReading
                ) -> None:
                    assert session_reading.labels == session_reading.expected_labels

            class TestWhenTheMainTextCannotHoldThePagesBeforeIt:
                @pytest.fixture(
                    params=[
                        (["xxv", "", "", "2"], ["xxv", "xxvi", "1", "2"]),
                        (["xxv", "", "", "1"], ["xxv", "xxvi", "xxvii", "1"]),
                    ],
                    ids=["before page 2", "before page 1"],
                )
                def session_reading(self, request: pytest.FixtureRequest) -> SessionReading:
                    detected, expected = request.param
                    return SessionReading(labels=session_labels(detected), expected_labels=expected)

                def test_should_count_on_the_front_matter_for_them(self, session_reading: SessionReading) -> None:
                    assert session_reading.labels == session_reading.expected_labels

            class TestWhenTheFrontMatterIsScannedAfterTheMainText:
                @pytest.fixture(
                    params=[
                        (["5", "", "ii"], ["5", "6", "ii"]),
                        (["4-5", "", "", "ii", "7"], ["4–5", "6", None, "ii", "7"]),
                    ],
                    ids=["after a page", "after a spread"],
                )
                def session_reading(self, request: pytest.FixtureRequest) -> SessionReading:
                    detected, expected = request.param
                    return SessionReading(labels=session_labels(detected), expected_labels=expected)

                def test_should_count_on_the_main_text_below_its_next_page_and_count_back_no_roman_number(
                    self, session_reading: SessionReading
                ) -> None:
                    assert session_reading.labels == session_reading.expected_labels

            class TestWhenAPageNumberedInTheSameSystemLiesOnTheOtherSide:
                @pytest.fixture(
                    params=[
                        (["2", "iii", "", "", "4"], ["2", "iii", "iv", "3", "4"]),
                        (["xii", "", "1", "xiii"], ["xii", None, "1", "xiii"]),
                    ],
                    ids=["front matter within the main text", "the main text within front matter"],
                )
                def session_reading(self, request: pytest.FixtureRequest) -> SessionReading:
                    detected, expected = request.param
                    return SessionReading(labels=session_labels(detected), expected_labels=expected)

                def test_should_infer_no_number_that_reaches_it(self, session_reading: SessionReading) -> None:
                    assert session_reading.labels == session_reading.expected_labels

        class TestWhenABookIsScannedInOrderAndTheOcrMissesSomeNumbers:
            @pytest.fixture(scope="class", params=range(300), ids=lambda seed: f"seed {seed}")
            @classmethod
            def scanned_book(cls, request: pytest.FixtureRequest) -> BookScannedInOrder:
                pages, real = book_scanned_in_order(random.Random(request.param), skipping=False)
                layout = compute_layout(pages)
                scan_order = tuple(p.id for p in pages)
                return BookScannedInOrder(
                    scan_order=scan_order,
                    reading_order=layout.reading_order,
                    labels=labels(layout, scan_order),
                    expected_labels=expected_labels(pages, real),
                    coverage=layout.coverage,
                )

            def test_should_give_each_page_its_real_number_when_a_number_found_on_it_or_around_it_tells_it(
                self, scanned_book: BookScannedInOrder
            ) -> None:
                assert scanned_book.labels == scanned_book.expected_labels

            def test_should_keep_the_pages_in_the_order_of_the_scan(self, scanned_book: BookScannedInOrder) -> None:
                assert scanned_book.reading_order == scanned_book.scan_order

            def test_should_cover_the_numbers_of_the_main_text_it_gives(self, scanned_book: BookScannedInOrder) -> None:
                covered = {number for start, end in scanned_book.coverage.ranges for number in range(start, end + 1)}
                numbers_given = {
                    int(label) for label in scanned_book.expected_labels if label is not None and label.isdigit()
                }
                assert covered == numbers_given

            def test_should_count_the_pages_it_leaves_unnumbered(self, scanned_book: BookScannedInOrder) -> None:
                assert scanned_book.coverage.unnumbered == scanned_book.expected_labels.count(None)

        class TestWhenABookIsScannedInOrderSkippingPagesAndTheOcrMissesSomeNumbers:
            @pytest.fixture(scope="class", params=range(300), ids=lambda seed: f"seed {seed}")
            @classmethod
            def scanned_book(cls, request: pytest.FixtureRequest) -> BookScannedSkippingPages:
                pages, real = book_scanned_in_order(random.Random(request.param), skipping=True)
                layout = compute_layout(pages)
                numbers = [layout.placements[p.id].number for p in pages]
                found = [parse_detected_numbers(p.detected_numbers) is not None for p in pages]
                return BookScannedSkippingPages(
                    scan_order=tuple(p.id for p in pages),
                    reading_order=layout.reading_order,
                    naturals=[number.natural for number in numbers if number is not None],
                    labels_of_the_numbers_found=[
                        label_of(number) for number, is_found in zip(numbers, found, strict=True) if is_found
                    ],
                    real_labels_of_the_numbers_found=[
                        label for label, is_found in zip(real, found, strict=True) if is_found
                    ],
                )

            def test_should_keep_the_pages_in_the_order_of_the_scan(
                self, scanned_book: BookScannedSkippingPages
            ) -> None:
                assert scanned_book.reading_order == scanned_book.scan_order

            def test_should_number_the_pages_in_increasing_order_without_duplicates(
                self, scanned_book: BookScannedSkippingPages
            ) -> None:
                assert scanned_book.naturals == sorted(set(scanned_book.naturals))

            def test_should_keep_the_numbers_found(self, scanned_book: BookScannedSkippingPages) -> None:
                assert scanned_book.labels_of_the_numbers_found == scanned_book.real_labels_of_the_numbers_found

        class TestWhenASessionHoldsNumbersOfEveryKindInAnyOrder:
            @pytest.fixture(scope="class", params=range(500), ids=lambda seed: f"seed {seed}")
            @classmethod
            def findings(cls, request: pytest.FixtureRequest) -> InferenceFindings:
                pages = random_session(random.Random(request.param))
                return check_inference(pages, compute_layout(pages))

            def test_should_check_every_page_of_the_session(self, findings: InferenceFindings) -> None:
                assert findings.checked_page_ids == findings.page_ids

            def test_should_keep_the_number_of_a_page_typed_then_found_then_hinted(
                self, findings: InferenceFindings
            ) -> None:
                assert findings.own_number_changed == []

            def test_should_count_back_from_the_main_text_after_front_matter_unless_it_reaches_0_or_earlier_main_text(
                self, findings: InferenceFindings
            ) -> None:
                assert findings.not_counted_back_from_the_main_text == []

            def test_should_mark_the_numbers_it_infers_as_inferred(self, findings: InferenceFindings) -> None:
                assert findings.not_marked_inferred == []

            def test_should_infer_no_number_below_1_nor_a_roman_number_above_399(
                self, findings: InferenceFindings
            ) -> None:
                assert findings.out_of_range == []

            def test_should_infer_a_number_strictly_between_the_nearest_pages_numbered_in_its_system_never_on_one(
                self, findings: InferenceFindings
            ) -> None:
                assert findings.on_a_numbered_page == []

            def test_should_count_on_from_the_page_before_or_back_from_the_next_only_with_none_or_front_matter_before(
                self, findings: InferenceFindings
            ) -> None:
                assert findings.counted_from_elsewhere == []

        class TestWhenTheSessionsWereScannedOutOfOrder:
            @pytest.fixture
            def layout(self) -> Layout:
                # Pages 6–10 were scanned first, pages 1–5 in a later session.
                first = [
                    page(f"p{n}", session="first", seq=n - 6, ts=100 + n, detected=(str(n),)) for n in range(6, 11)
                ]
                second = [
                    page(f"p{n}", session="second", seq=n - 1, ts=200 + n, detected=(str(n),)) for n in range(1, 6)
                ]
                return compute_layout(first + second)

            def test_should_merge_them_by_number(self, layout: Layout) -> None:
                assert labels(layout) == [str(n) for n in range(1, 11)]

            def test_should_cover_every_number(self, layout: Layout) -> None:
                assert layout.coverage.label == "1–10"

        class TestWhenTheDocumentHasRomanFrontMatter:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("p2", detected=("2",), ts=1),
                        page("p1", detected=("1",), ts=2),
                        page("pii", detected=("ii",), ts=3),
                        page("pi", detected=("i",), ts=4),
                    ]
                )

            def test_should_put_the_front_matter_first(self, layout: Layout) -> None:
                assert labels(layout) == ["i", "ii", "1", "2"]

            def test_should_leave_the_front_matter_out_of_the_coverage(self, layout: Layout) -> None:
                assert layout.coverage.ranges == ((1, 2),)

        class TestWhenSomePagesHaveNeitherANumberNorASession:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("u2", session=None, ts=50),
                        page("n2", detected=("2",), ts=10),
                        page("u1", session=None, ts=40),
                        page("n1", detected=("1",), ts=20),
                    ]
                )

            def test_should_put_them_last_by_capture_time(self, layout: Layout) -> None:
                assert layout.reading_order == ("n1", "n2", "u1", "u2")

            def test_should_count_the_document_as_numbered(self, layout: Layout) -> None:
                assert layout.numbered

            def test_should_count_them_as_unnumbered(self, layout: Layout) -> None:
                assert layout.coverage.unnumbered == 2

        class TestWhenNoPageHasANumber:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("x0", session="x", seq=0, ts=50),
                        page("x1", session="x", seq=1, ts=45),  # a clock oddity
                        page("y1", session="y", seq=1, ts=12),
                        page("y0", session="y", seq=0, ts=10),
                    ]
                )

            def test_should_count_the_document_as_not_numbered(self, layout: Layout) -> None:
                assert not layout.numbered

            def test_should_order_the_sessions_by_capture_time_and_their_pages_by_shot_whatever_the_clock_says(
                self, layout: Layout
            ) -> None:
                assert layout.reading_order == ("y0", "y1", "x0", "x1")

            def test_should_cover_no_number(self, layout: Layout) -> None:
                assert layout.coverage.ranges == ()

            def test_should_count_every_page_as_unnumbered(self, layout: Layout) -> None:
                assert layout.coverage.unnumbered == 4

        class TestWhenTwoPagesHaveTheSameNumber:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("old", session="a", detected=("7",), ts=10),
                        page("new", session="b", detected=("7",), ts=20),
                    ]
                )

            def test_should_keep_the_most_recent_capture(self, layout: Layout) -> None:
                assert layout.reading_order == ("new",)

            def test_should_mark_the_older_one_as_its_duplicate(self, layout: Layout) -> None:
                assert layout.placements["old"].duplicate_of == "new"

            def test_should_leave_the_older_one_out_of_the_document(self, layout: Layout) -> None:
                assert not layout.placements["old"].in_document

        class TestWhenThePagesSharingANumberAreExcludedOrWaitForOcr:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("done", detected=("7",), ts=10),
                        page("excluded", detected=("7",), ts=20, excluded=True),
                        page("queued", hint=7, ts=30, status="queued"),
                    ]
                )

            def test_should_keep_the_page_that_is_done_in_the_document(self, layout: Layout) -> None:
                assert layout.reading_order == ("done",)

            def test_should_mark_no_page_as_a_duplicate(self, layout: Layout) -> None:
                assert [placement.duplicate_of for placement in layout.placements.values()] == [None, None, None]

        class TestWhenFrontMatterAndTheMainTextShareAValue:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout([page("roman", detected=("v",)), page("arabic", detected=("5",), ts=1)])

            def test_should_keep_both_pages(self, layout: Layout) -> None:
                assert set(layout.reading_order) == {"roman", "arabic"}

        class TestWhenPagesAreDuplicatedExcludedOrNotDone:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("dup", detected=("1",), ts=1),
                        page("ok", detected=("1",), ts=9),
                        page("excl", detected=("2",), ts=2, excluded=True),
                        page("err", ts=4, status="error"),
                        page("queued", ts=3, status="queued"),
                        page("proc", ts=5, status="processing"),
                    ]
                )

            def test_should_list_the_reading_order_then_the_pages_not_done_excluded_and_duplicated_each_by_capture_time(
                self, layout: Layout
            ) -> None:
                assert layout.order == ("ok", "queued", "err", "proc", "excl", "dup")

            def test_should_rank_each_page_by_its_place_in_that_list(self, layout: Layout) -> None:
                assert [layout.placements[i].rank for i in layout.order] == list(range(6))

        class TestWhenNumbersAreMissingBetweenPagesAndASpread:
            @pytest.fixture
            def layout(self) -> Layout:
                pages = [page(f"p{n}", detected=(str(n),), ts=n) for n in (1, 2, 3, 7, 8)]
                return compute_layout([*pages, page("spread", detected=("10", "11"), ts=20)])

            def test_should_cover_the_ranges_of_the_numbers_present_both_pages_of_the_spread_included(
                self, layout: Layout
            ) -> None:
                assert layout.coverage.ranges == ((1, 3), (7, 8), (10, 11))

        class TestWhenTheDocumentHasNoPage:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout([])

            def test_should_order_no_page(self, layout: Layout) -> None:
                assert layout.order == ()

        class TestWhenUnnumberedPagesAreScannedBeforePage1InItsSession:
            @pytest.fixture
            def layout(self) -> Layout:
                # A title page, a preface... 20 pages without a number, then pages 1–5, in one session.
                front = [page(f"f{i}", seq=i, ts=i) for i in range(20)]
                body = [page(f"p{n}", seq=19 + n, ts=19 + n, detected=(str(n),)) for n in range(1, 6)]
                return compute_layout(body + front)

            def test_should_open_the_document_with_them(self, layout: Layout) -> None:
                assert layout.reading_order == tuple(f"f{i}" for i in range(20)) + tuple(f"p{n}" for n in range(1, 6))

            def test_should_place_them_by_their_session(self, layout: Layout) -> None:
                assert placed_by(layout) == ["session"] * 20 + ["number"] * 5

            def test_should_place_the_last_one_a_session_step_before_page_1(self, layout: Layout) -> None:
                assert layout.placements["f19"].sort_value == pytest.approx(1 - SESSION_STEP)

            def test_should_place_the_first_one_20_session_steps_before_page_1(self, layout: Layout) -> None:
                assert layout.placements["f0"].sort_value == pytest.approx(1 - 20 * SESSION_STEP)

            def test_should_leave_them_unnumbered(self, layout: Layout) -> None:
                assert labels(layout) == [None] * 20 + ["1", "2", "3", "4", "5"]

            def test_should_count_them_as_unnumbered_outside_the_coverage(self, layout: Layout) -> None:
                assert (layout.coverage.label, layout.coverage.unnumbered) == ("1–5", 20)

        class TestWhenAnUnnumberedPlateIsScannedAfterAPage:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("p13", seq=2, ts=2, detected=("13",)),
                        page("plate", seq=1, ts=1),
                        page("p12", seq=0, ts=0, detected=("12",)),
                    ]
                )

            def test_should_keep_the_plate_after_that_page(self, layout: Layout) -> None:
                assert layout.reading_order == ("p12", "plate", "p13")

            def test_should_place_the_plate_by_its_session_without_a_number(self, layout: Layout) -> None:
                plate = layout.placements["plate"]
                assert (plate.number, plate.placed_by) == (None, "session")

            def test_should_place_the_plate_a_session_step_after_that_page(self, layout: Layout) -> None:
                assert layout.placements["plate"].sort_value == pytest.approx(12 + SESSION_STEP)

            def test_should_place_the_page_at_its_number(self, layout: Layout) -> None:
                assert layout.placements["p12"].sort_value == 12

        class TestWhenUnnumberedPagesAreScannedInASessionOfTheirOwn:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("p1", session="book", seq=0, ts=10, detected=("1",)),
                        page("p2", session="book", seq=1, ts=11, detected=("2",)),
                        page("u2", session="loose", seq=1, ts=1),
                        page("u1", session="loose", seq=0, ts=2),
                    ]
                )

            def test_should_put_them_last_in_the_order_of_their_shots(self, layout: Layout) -> None:
                assert layout.reading_order == ("p1", "p2", "u1", "u2")

            def test_should_leave_them_unplaced(self, layout: Layout) -> None:
                assert placed_by(layout) == ["number", "number", "unplaced", "unplaced"]

            def test_should_give_them_no_place_on_the_number_line(self, layout: Layout) -> None:
                assert layout.placements["u1"].sort_value is None

        class TestWhenTheShotsOfASessionHaveNoSeq:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("p5", ts=0, detected=("5",)),
                        page("b", ts=2),
                        page("a", ts=1),
                        page("p6", ts=3, detected=("6",)),
                    ]
                )

            def test_should_place_the_unnumbered_pages_in_the_order_of_their_capture(self, layout: Layout) -> None:
                assert layout.reading_order == ("p5", "a", "b", "p6")

            def test_should_count_the_session_steps_in_captures(self, layout: Layout) -> None:
                assert layout.placements["b"].sort_value == pytest.approx(5 + 2 * SESSION_STEP)

        class TestWhenFrontMatterWithAPlateIsScannedApartFromPage1:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("p1", session="b", seq=0, ts=10, detected=("1",)),
                        page("ii", session="a", seq=0, ts=1, detected=("ii",)),
                        page("plate", session="a", seq=1, ts=2),
                        page("iii", session="a", seq=2, ts=3, detected=("iii",)),
                    ]
                )

            def test_should_order_the_front_matter_and_its_plate_before_page_1(self, layout: Layout) -> None:
                assert labels(layout) == ["ii", None, "iii", "1"]

            def test_should_place_the_front_matter_before_page_1_on_the_number_line(self, layout: Layout) -> None:
                assert sort_values(layout) == pytest.approx([2 - 10_000, 2 - 10_000 + SESSION_STEP, 3 - 10_000, 1])

        class TestWhenAPlateIsScannedAfterASpread:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("spread", seq=0, detected=("42", "43")),
                        page("plate", seq=1, ts=1),
                        page("p44", seq=2, ts=2, detected=("44",)),
                        page("p41", session="other", ts=3, detected=("41",)),
                    ]
                )

            def test_should_order_the_spread_by_its_first_page(self, layout: Layout) -> None:
                assert labels(layout) == ["41", "42–43", None, "44"]

            def test_should_place_the_spread_at_its_first_page(self, layout: Layout) -> None:
                assert layout.placements["spread"].sort_value == 42

            def test_should_place_the_plate_a_session_step_after_the_first_page_of_the_spread(
                self, layout: Layout
            ) -> None:
                assert layout.placements["plate"].sort_value == pytest.approx(42 + SESSION_STEP)

        class TestWhenAPageHasAPosition:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("p1", detected=("1",), ts=1),
                        page("p2", detected=("2",), ts=2),
                        page("p3", detected=("3",), ts=3, position=1.5),
                    ]
                )

            def test_should_put_the_page_at_its_position(self, layout: Layout) -> None:
                assert layout.reading_order == ("p1", "p3", "p2")

            def test_should_keep_its_number_and_place_it_by_its_position(self, layout: Layout) -> None:
                moved = layout.placements["p3"]
                assert (moved.number, moved.source, moved.placed_by, moved.sort_value) == (
                    PageNumber(3),
                    "detected",
                    "manual",
                    1.5,
                )

            def test_should_keep_the_coverage(self, layout: Layout) -> None:
                assert layout.coverage.label == "1–3"

        class TestWhenTwoPagesHaveTheSamePlace:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("late", session="a", detected=("4",), ts=20),
                        page("early", session="b", ts=10, position=4.0),
                    ]
                )

            def test_should_order_them_by_capture_time(self, layout: Layout) -> None:
                assert layout.reading_order == ("early", "late")

        class TestWhenADuplicateHasAPosition:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("old", session="a", detected=("7",), ts=10, position=0.5),
                        page("p6", session="b", seq=0, detected=("6",), ts=19),
                        page("new", session="b", seq=1, detected=("7",), ts=20),
                    ]
                )

            def test_should_still_take_it_for_a_duplicate_and_leave_it_unplaced(self, layout: Layout) -> None:
                old = layout.placements["old"]
                assert (old.duplicate_of, old.in_document, old.placed_by, old.sort_value) == ("new", False, None, None)

            def test_should_order_the_other_pages_by_number(self, layout: Layout) -> None:
                assert layout.reading_order == ("p6", "new")

            def test_should_place_the_other_pages_by_their_number(self, layout: Layout) -> None:
                assert placed_by(layout) == ["number", "number"]

        class TestWhenAPageIsScannedAgainLater:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("p11", session="a", seq=0, ts=0, detected=("11",)),
                        page("old12", session="a", seq=1, ts=1, detected=("12",)),
                        page("plate", session="a", seq=2, ts=2),
                        page("p13", session="a", seq=3, ts=3, detected=("13",)),
                        page("new12", session="b", seq=0, ts=10, detected=("12",)),
                    ]
                )

            def test_should_take_the_first_shot_for_a_duplicate(self, layout: Layout) -> None:
                assert layout.placements["old12"].duplicate_of == "new12"

            def test_should_keep_the_plate_scanned_after_the_first_shot_after_that_page(self, layout: Layout) -> None:
                assert layout.reading_order == ("p11", "new12", "plate", "p13")

        class TestWhenThePageBeforeAPlateWaitsForOcr:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("p11", seq=0, detected=("11",)),
                        page("p12", seq=1, ts=1, detected=("12",), status="queued"),
                        page("plate", seq=2, ts=2),
                        page("p13", seq=3, ts=3, detected=("13",)),
                    ]
                )

            def test_should_still_place_the_plate_after_it_since_it_may_be_read_again(self, layout: Layout) -> None:
                assert layout.placements["plate"].sort_value == pytest.approx(12 + SESSION_STEP)

        class TestWhenThePageBeforeAPlateIsExcluded:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("p11", seq=0, detected=("11",)),
                        page("p12", seq=1, ts=1, detected=("12",), excluded=True),
                        page("plate", seq=2, ts=2),
                        page("p13", seq=3, ts=3, detected=("13",)),
                    ]
                )

            def test_should_place_the_plate_after_the_page_before_the_excluded_one(self, layout: Layout) -> None:
                assert layout.placements["plate"].sort_value == pytest.approx(11 + 2 * SESSION_STEP)

        class TestWhenAPageWithAPositionComesBeforeOthersOfItsSession:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        page("p1", session="a", seq=0, detected=("1",)),
                        page("p2", session="a", seq=1, ts=1, detected=("2",)),
                        page("map", session="b", seq=0, ts=5, position=1.5),
                        page("legend", session="b", seq=1, ts=6),
                    ]
                )

            def test_should_keep_them_after_it(self, layout: Layout) -> None:
                assert layout.reading_order == ("p1", "map", "legend", "p2")

            def test_should_place_them_by_their_session(self, layout: Layout) -> None:
                assert placed_by(layout) == ["number", "manual", "session", "number"]

    class TestTheCoverageGapsProperty:
        class TestWhenNumbersAreMissingBetweenTheRanges:
            @pytest.fixture
            def gaps(self) -> tuple[tuple[int, int], ...]:
                return COVERAGE_WITH_GAPS.gaps

            def test_should_give_the_ranges_of_the_missing_numbers(self, gaps: tuple[tuple[int, int], ...]) -> None:
                assert gaps == ((4, 6), (9, 9))

    class TestTheCoverageLabelProperty:
        class TestWhenNumbersAreMissingBetweenTheRanges:
            @pytest.fixture
            def label(self) -> str:
                return COVERAGE_WITH_GAPS.label

            def test_should_list_the_ranges(self, label: str) -> None:
                assert label == "1–3, 7–8, 10–11"

    class TestTheCoverageMissingLabelProperty:
        class TestWhenNumbersAreMissingBetweenTheRanges:
            @pytest.fixture
            def missing_label(self) -> str:
                return COVERAGE_WITH_GAPS.missing_label

            def test_should_list_the_missing_ranges_and_numbers(self, missing_label: str) -> None:
                assert missing_label == "4–6, 9"

    class TestTheCoverageMinAndMaxProperties:
        class TestWhenNumbersAreMissingBetweenTheRanges:
            @pytest.fixture
            def bounds(self) -> tuple[int | None, int | None]:
                return (COVERAGE_WITH_GAPS.min, COVERAGE_WITH_GAPS.max)

            def test_should_give_the_first_and_the_last_number_covered(
                self, bounds: tuple[int | None, int | None]
            ) -> None:
                assert bounds == (1, 11)

    class TestTheCoverageToJsonMethod:
        class TestWhenNumbersAreMissingBetweenTheRanges:
            @pytest.fixture
            def coverage_json(self) -> CoverageJson:
                return COVERAGE_WITH_GAPS.to_json()

            def test_should_give_the_gaps_as_lists(self, coverage_json: CoverageJson) -> None:
                assert coverage_json["gaps"] == [[4, 6], [9, 9]]

        class TestWhenTheDocumentHasNoPage:
            @pytest.fixture
            def coverage_json(self) -> CoverageJson:
                return compute_layout([]).coverage.to_json()

            def test_should_give_no_range_no_bound_and_no_unnumbered_page(self, coverage_json: CoverageJson) -> None:
                assert coverage_json == {
                    "ranges": [],
                    "label": "",
                    "gaps": [],
                    "min": None,
                    "max": None,
                    "unnumbered": 0,
                }
