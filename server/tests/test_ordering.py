"""Page numbering and ordering (docs/ARCHITECTURE.md), on hand-built pages."""

from __future__ import annotations

import dataclasses
import itertools
import random
from collections.abc import Callable, Mapping, Sequence
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

COVERAGE_WITH_GAPS = Coverage(ranges=((1, 3), (7, 8), (10, 11)), unnumbered=0)
PLACEMENTS_OF_THE_BOOK_PAGES = ["session"] * 20 + ["number"] * 5 + ["session"] + ["number"] * 5
SEEDS = range(300)


def make_page(
    page_id: str,
    *,
    session_id: str | None = "s1",
    seq: int | None = None,
    captured_ts: float = 0.0,
    status: str = "done",
    excluded: bool = False,
    manual_number: int | None = None,
    hint_number: int | None = None,
    detected_numbers: tuple[str, ...] = (),
    position: float | None = None,
) -> PageInput:
    return PageInput(
        id=page_id,
        session_id=session_id,
        seq=seq,
        captured_ts=captured_ts,
        status=status,
        excluded=excluded,
        manual_number=manual_number,
        hint_number=hint_number,
        detected_numbers=detected_numbers,
        position=position,
    )


def read_labels(layout: Layout, page_ids: Sequence[str] | None = None) -> list[str | None]:
    page_ids = layout.reading_order if page_ids is None else page_ids
    return [number.label if (number := layout.placements[page_id].number) else None for page_id in page_ids]


def read_label(page_number: PageNumber | None) -> str | None:
    return page_number.label if page_number is not None else None


class Reading(NamedTuple):
    page_number: PageNumber | None
    expected_page_number: PageNumber


class RomanReading(NamedTuple):
    page_number: PageNumber | None
    label: str | None
    expected_number: int
    expected_label: str


def read_placements(layout: Layout, page_ids: Sequence[str] | None = None) -> list[str | None]:
    page_ids = layout.reading_order if page_ids is None else page_ids
    return [layout.placements[page_id].placed_by for page_id in page_ids]


def read_places_on_the_number_line(layout: Layout, page_ids: Sequence[str] | None = None) -> list[float | None]:
    page_ids = layout.reading_order if page_ids is None else page_ids
    return [layout.placements[page_id].sort_value for page_id in page_ids]


def read_numbers_and_sources(layout: Layout, page_ids: Sequence[str]) -> list[tuple[PageNumber | None, str | None]]:
    return [(layout.placements[page_id].number, layout.placements[page_id].source) for page_id in page_ids]


def make_book_with_roman_front_matter(typed_numbers_by_seq: dict[int, int] | None = None) -> list[PageInput]:
    numbers_the_ocr_read_by_seq = {11: ("1X",), 15: ("XV",), 22: ("XXV",), 24: ("$ x_{0} $",), 25: ("3",)}
    typed_numbers_by_seq = typed_numbers_by_seq or {}
    return [
        make_page(
            f"s{seq}",
            seq=seq,
            captured_ts=seq,
            detected_numbers=numbers_the_ocr_read_by_seq.get(seq, ()),
            manual_number=typed_numbers_by_seq.get(seq),
        )
        for seq in range(1, 26)
    ]


def label_a_session(number_found_on_each_page: Sequence[str]) -> list[str | None]:
    pages = [
        make_page(f"s{seq}", seq=seq, captured_ts=seq, detected_numbers=(text,) if text else ())
        for seq, text in enumerate(number_found_on_each_page)
    ]
    return read_labels(compute_layout(pages), [page.id for page in pages])


def scan_a_book_in_order(random_generator: random.Random, *, skips_pages: bool) -> tuple[list[PageInput], list[str]]:
    book = [int_to_roman(number) for number in range(1, random_generator.randint(0, 30) + 1)]
    book += [str(number) for number in range(1, random_generator.randint(1, 40) + 1)]
    start = random_generator.randrange(len(book))
    run = book[start : random_generator.randint(start + 1, len(book))]
    real_labels = [label for label in run if not skips_pages or random_generator.random() < 0.7] or run[:1]
    share_of_the_numbers_read = random_generator.random()
    pages = []
    for seq, label in enumerate(real_labels, start=1):
        detected: tuple[str, ...]
        if random_generator.random() < share_of_the_numbers_read:
            detected = (random_generator.choice([label, label.upper()]),)
        else:
            detected = random_generator.choice([(), ("1X",), ("$ x_{0} $",)])
        pages.append(make_page(f"s{seq}", seq=seq, captured_ts=seq, detected_numbers=detected))
    return pages, real_labels


def predict_labels(pages: Sequence[PageInput], real_labels: Sequence[str]) -> list[str | None]:
    found = [index for index, page in enumerate(pages) if parse_detected_numbers(page.detected_numbers)]
    labels: list[str | None] = []
    for index, label in enumerate(real_labels):
        before = [found_index for found_index in found if found_index <= index]
        after = [found_index for found_index in found if found_index > index]
        if before and (after or real_labels[before[-1]].isdigit() == label.isdigit()):
            labels.append(label)
        elif before:
            last_found = roman_to_int(real_labels[before[-1]])
            if last_found is None:
                raise ValueError(
                    "the front matter does not come first: the last number found before the page is not roman"
                )
            labels.append(int_to_roman(last_found + index - before[-1]))
        elif after and real_labels[after[0]].isdigit() == label.isdigit():
            labels.append(label)
        else:
            labels.append(None)
    return labels


def find_own_number(page: PageInput) -> tuple[PageNumber | None, str | None]:
    if page.manual_number is not None:
        return PageNumber(page.manual_number), "manual"
    if (detected := parse_detected_numbers(page.detected_numbers)) is not None:
        return detected, "detected"
    if page.hint_number is not None:
        return PageNumber(page.hint_number), "hint"
    return None, None


def generate_a_session(random_generator: random.Random) -> list[PageInput]:
    pages, seq = [], 0
    for index in range(random_generator.randint(1, 12)):
        seq += random_generator.choice([1, 1, 1, 2, 3])
        kind = random_generator.choice(["arabic", "roman", "spread", "none", "none", "none"])
        number = random_generator.randint(1, 30)
        detected = {
            "arabic": (str(number),),
            "roman": (int_to_roman(number),),
            "spread": (str(number), str(number + 1)),
        }.get(kind, ())
        pages.append(
            make_page(
                f"x{index}",
                seq=seq,
                captured_ts=index,
                detected_numbers=detected,
                manual_number=random_generator.choice([None] * 9 + [random_generator.randint(1, 30)]),
                hint_number=random_generator.choice([None] * 9 + [random_generator.randint(1, 30)]),
                excluded=random_generator.random() < 0.1,
                status=random_generator.choice(["done"] * 9 + ["queued"]),
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
    own = {page.id: find_own_number(page) for page in pages}
    anchors = [
        (page.seq, anchor)
        for page in pages
        if (anchor := own[page.id][0]) is not None and page.seq is not None and not page.excluded
    ]
    findings = InferenceFindings([page.id for page in pages], [], [], [], [], [], [], [])
    for page in pages:
        seq = page.seq
        if seq is None:
            continue
        findings.checked_page_ids.append(page.id)
        number, source = layout.placements[page.id].number, layout.placements[page.id].source
        if own[page.id][0] is not None:
            if (number, source) != own[page.id]:
                findings.own_number_changed.append(page.id)
            continue
        before = [(step, anchor) for step, anchor in anchors if step < seq]
        after = [(step, anchor) for step, anchor in anchors if step > seq]
        previous = before[-1][1] if before else None
        following = after[0][1] if after else None
        if previous is not None and following is not None and previous.front_matter and not following.front_matter:
            number_counted_back = following.value - (after[0][0] - seq)
            main_text_before = next((anchor.last for _, anchor in reversed(before) if not anchor.front_matter), 0)
            if number_counted_back > main_text_before and number != PageNumber(number_counted_back):
                findings.not_counted_back_from_the_main_text.append(page.id)
        if number is None:
            continue
        if source != "inferred":
            findings.not_marked_inferred.append(page.id)
        if number.value < 1 or (number.front_matter and number.value > 399):
            findings.out_of_range.append(page.id)
        lower = [anchor for _, anchor in before if anchor.front_matter == number.front_matter]
        upper = [anchor for _, anchor in after if anchor.front_matter == number.front_matter]
        if (lower and lower[-1].last >= number.value) or (upper and number.value >= upper[0].value):
            findings.on_a_numbered_page.append(page.id)
        is_counted_on = previous is not None and number == PageNumber(
            previous.last + seq - before[-1][0], front_matter=previous.front_matter
        )
        is_counted_back = following is not None and number == PageNumber(
            following.value - (after[0][0] - seq), front_matter=following.front_matter
        )
        may_count_back = following is not None and (
            previous is None or (previous.front_matter and not following.front_matter)
        )
        if not is_counted_on and not (is_counted_back and may_count_back):
            findings.counted_from_elsewhere.append(page.id)
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


class Reordering(NamedTuple):
    wanted: tuple[str, ...]
    positions: list[float | None]
    moved_pages: list[PageInput]
    layout: Layout


class OrderPut(NamedTuple):
    pages: list[PageInput]
    layout_before: Layout
    wanted: tuple[str, ...]
    positions: dict[str, float | None]
    moved_pages: list[PageInput]
    layout: Layout


class ShuffledOrder(NamedTuple):
    wanted: tuple[str, ...]
    reading_order: tuple[str, ...]
    kept_score: tuple[int, int]
    best_kept_score: tuple[int, int]
    numbers_before: list[PageNumber | None]
    numbers_after: list[PageNumber | None]


class OrderRound(NamedTuple):
    wanted: tuple[str, ...]
    reading_order: tuple[str, ...]
    numbers_before: list[PageNumber | None]
    numbers_after: list[PageNumber | None]
    kept_score: tuple[int, int]
    best_kept_score: tuple[int, int]
    examined_unnumbered_page_ids: list[str]
    unnumbered_pages_that_lost_their_position: list[str]
    moved_unnumbered_pages_without_position: list[str]
    needless_positions: list[str]
    positions: dict[str, float | None]
    positions_asked_again: dict[str, float | None]


class TwoOrders(NamedTuple):
    first: OrderRound
    second: OrderRound


class LooseSessionsMoved(NamedTuple):
    order_put: OrderPut
    moved_page_ids: set[str]


def reorder(pages: list[PageInput], wanted: list[str]) -> Reordering:
    layout = compute_layout(pages)
    by_id = {page.id: page for page in pages}
    numbers = [layout.placements[page_id].number for page_id in wanted]
    positions = order_positions(
        [number.natural if number is not None else None for number in numbers],
        [by_id[page_id].position is not None for page_id in wanted],
    )
    new_positions = dict(zip(wanted, positions, strict=True))
    moved = [
        dataclasses.replace(page, position=new_positions[page.id]) if page.id in new_positions else page
        for page in pages
    ]
    return Reordering(wanted=tuple(wanted), positions=positions, moved_pages=moved, layout=compute_layout(moved))


def make_numbered_pages(*numbers: int) -> list[PageInput]:
    return [
        make_page(f"p{number}", seq=number, captured_ts=number, detected_numbers=(str(number),)) for number in numbers
    ]


def find_best_kept_score_by_brute_force(naturals: list[int | None], is_positioned: list[bool]) -> tuple[int, int]:
    best = (0, 0)
    for size in range(len(naturals), 0, -1):
        for indices in itertools.combinations(range(len(naturals)), size):
            kept_naturals = [natural for index in indices if (natural := naturals[index]) is not None]
            if len(kept_naturals) == size and all(
                lower < higher for lower, higher in itertools.pairwise(kept_naturals)
            ):
                best = max(best, (size, sum(not is_positioned[index] for index in indices)))
    return best


def shuffle_any_order(random_generator: random.Random) -> ShuffledOrder:
    pages = []
    for index in range(random_generator.randint(1, 9)):
        kind = random_generator.choice(["arabic", "arabic", "roman", "spread", "loose", "plate"])
        number = random_generator.randint(1, 30)
        detected = {
            "arabic": (str(number),),
            "roman": (int_to_roman(number),),
            "spread": (str(number), str(number + 1)),
        }.get(kind, ())
        position = random_generator.choice([None, None, random_generator.uniform(-5, 35)])
        session = f"s{index}" if kind == "loose" else random_generator.choice(["a", "b"])
        pages.append(
            make_page(
                f"x{index}",
                session_id=session,
                seq=index,
                captured_ts=index,
                detected_numbers=detected,
                position=position,
            )
        )
    layout = compute_layout(pages)
    wanted = list(layout.reading_order)
    random_generator.shuffle(wanted)
    reordering = reorder(pages, wanted)
    by_id = {page.id: page for page in pages}
    naturals = [
        page_number.natural if (page_number := layout.placements[page_id].number) else None for page_id in wanted
    ]
    is_positioned = [by_id[page_id].position is not None for page_id in wanted]
    kept = [index for index, position in enumerate(reordering.positions) if position is None]
    return ShuffledOrder(
        wanted=tuple(wanted),
        reading_order=reordering.layout.reading_order,
        kept_score=(len(kept), sum(not is_positioned[index] for index in kept)),
        best_kept_score=find_best_kept_score_by_brute_force(naturals, is_positioned),
        numbers_before=[layout.placements[page_id].number for page_id in wanted],
        numbers_after=[reordering.layout.placements[page_id].number for page_id in wanted],
    )


def set_positions(pages: list[PageInput], positions: Mapping[str, float | None]) -> list[PageInput]:
    return [dataclasses.replace(page, position=positions[page.id]) if page.id in positions else page for page in pages]


def put_order(pages: list[PageInput], wanted: Sequence[str]) -> OrderPut:
    layout_before = compute_layout(pages)
    positions = positions_for_order(pages, wanted)
    moved = set_positions(pages, positions)
    return OrderPut(
        pages=pages,
        layout_before=layout_before,
        wanted=tuple(wanted),
        positions=positions,
        moved_pages=moved,
        layout=compute_layout(moved),
    )


def select_the_given_positions(positions: dict[str, float | None]) -> dict[str, float]:
    return {page_id: position for page_id, position in positions.items() if position is not None}


def move_page_before(order: Sequence[str], page_id: str, before: str) -> list[str]:
    wanted = [other_id for other_id in order if other_id != page_id]
    wanted.insert(wanted.index(before), page_id)
    return wanted


def make_book_with_front_pages_a_plate_and_loose_pages() -> list[PageInput]:
    front = [make_page(f"f{index}", session_id="book", seq=index, captured_ts=index) for index in range(20)]
    first = [
        make_page(
            f"p{number}", session_id="book", seq=19 + number, captured_ts=19 + number, detected_numbers=(str(number),)
        )
        for number in range(1, 6)
    ]
    plate = make_page("plate", session_id="book", seq=25, captured_ts=25)
    rest = [
        make_page(
            f"p{number}", session_id="book", seq=20 + number, captured_ts=20 + number, detected_numbers=(str(number),)
        )
        for number in range(6, 11)
    ]
    loose = [make_page(f"u{index}", session_id="loose", seq=index, captured_ts=100 + index) for index in range(3)]
    return [*front, *first, plate, *rest, *loose]


def make_pages_before_page_1_in_two_sessions() -> list[PageInput]:
    return [
        make_page("a0", session_id="a", seq=0, captured_ts=0),
        make_page("a1", session_id="a", seq=1, captured_ts=1, detected_numbers=("1",)),
        make_page("b0", session_id="b", seq=0, captured_ts=10),
        make_page("b1", session_id="b", seq=1, captured_ts=11, detected_numbers=("1",)),
        make_page("x", session_id="x", seq=0, captured_ts=20),
    ]


def find_loose_groups(pages: list[PageInput], wanted: list[str]) -> tuple[set[str], set[str]]:
    layout = compute_layout(pages)
    by_id = {page.id: page for page in pages}
    numbers = [layout.placements[page_id].number for page_id in wanted]
    base = order_positions(
        [number.natural if number else None for number in numbers],
        [by_id[page_id].position is not None for page_id in wanted],
    )
    kept = {page_id for page_id, position in zip(wanted, base, strict=True) if position is None}
    loose = [
        page_id
        for page_id, number in zip(wanted, numbers, strict=True)
        if number is None and by_id[page_id].position is None
    ]
    reference = compute_layout(set_positions(pages, {**dict(zip(wanted, base, strict=True)), **dict.fromkeys(loose)}))
    placements = reference.placements

    def stays(group: set[str]) -> bool:
        staying = [page_id for page_id in wanted if page_id in kept or page_id in group]
        if any(placements[earlier].rank >= placements[later].rank for earlier, later in itertools.pairwise(staying)):
            return False
        unplaced = [
            index for index, page_id in enumerate(wanted) if page_id in group and placements[page_id].sort_value is None
        ]
        return not unplaced or all(page_id in group for page_id in wanted[unplaced[0] :])

    for size in range(len(loose), -1, -1):
        largest = [set(group) for group in itertools.combinations(loose, size) if stays(set(group))]
        if largest:
            return set.intersection(*largest), set.union(*largest)
    raise RuntimeError("the empty group always stays")


def generate_pages(random_generator: random.Random) -> list[PageInput]:
    pages = []
    for index in range(random_generator.randint(1, 10)):
        kind = random_generator.choice(
            ["arabic", "arabic", "roman", "spread", "unnumbered", "unnumbered", "loose", "loose"]
        )
        number = random_generator.randint(1, 30)
        detected = {
            "arabic": (str(number),),
            "roman": (int_to_roman(number),),
            "spread": (str(number), str(number + 1)),
        }.get(kind, ())
        session = (
            random_generator.choice([f"own{index}", "loose"])
            if kind == "loose"
            else random_generator.choice(["a", "b"])
        )
        pages.append(
            make_page(
                f"x{index}",
                session_id=session,
                seq=random_generator.choice([index, index, None]),
                captured_ts=index,
                detected_numbers=detected,
                position=random_generator.choice([None, None, None, random_generator.uniform(-5, 35)]),
                excluded=random_generator.random() < 0.1,
                status=random_generator.choice(["done"] * 9 + ["queued"]),
            )
        )
    return pages


def holds_two_pages_to_order_or_more(pages: list[PageInput]) -> bool:
    return len(compute_layout(pages).reading_order) >= 2


def holds_an_unnumbered_page_among_two_to_order_or_more(pages: list[PageInput]) -> bool:
    layout = compute_layout(pages)
    return len(layout.reading_order) >= 2 and any(
        layout.placements[page_id].number is None for page_id in layout.reading_order
    )


def generate_pages_until(
    random_generator: random.Random, is_wanted: Callable[[list[PageInput]], bool]
) -> list[PageInput]:
    pages = generate_pages(random_generator)
    while not is_wanted(pages):
        pages = generate_pages(random_generator)
    return pages


def move_a_block(random_generator: random.Random, order: list[str]) -> list[str]:
    size = random_generator.randint(1, max(1, len(order) // 3))
    start = random_generator.randrange(len(order) - size + 1)
    block, rest = order[start : start + size], order[:start] + order[start + size :]
    insertion_index = random_generator.randint(0, len(rest))
    return rest[:insertion_index] + block + rest[insertion_index:]


def draw_another_order(random_generator: random.Random, current: list[str]) -> list[str]:
    if len(current) < 2:
        raise ValueError("a reading order of fewer than two pages has no other order")
    wanted = current
    while wanted == current:
        if random_generator.random() < 0.5:
            wanted = move_a_block(random_generator, current)
        else:
            wanted = random_generator.sample(current, len(current))
    return wanted


def ask_another_order(random_generator: random.Random, pages: list[PageInput]) -> OrderRound:
    layout = compute_layout(pages)
    wanted = draw_another_order(random_generator, list(layout.reading_order))
    order_put = put_order(pages, wanted)
    positions = order_put.positions
    by_id = {page.id: page for page in pages}
    naturals = [
        page_number.natural if (page_number := layout.placements[page_id].number) else None for page_id in wanted
    ]
    is_positioned_before = [by_id[page_id].position is not None for page_id in wanted]
    kept = [index for index, page_id in enumerate(wanted) if naturals[index] is not None and positions[page_id] is None]
    in_every, in_some = find_loose_groups(pages, wanted)
    examined_unnumbered_page_ids, pages_that_lost_their_position, moved_pages_without_position = [], [], []
    pages_with_a_needless_position = []
    for page_id, natural, was_positioned in zip(wanted, naturals, is_positioned_before, strict=True):
        if natural is not None:
            continue
        examined_unnumbered_page_ids.append(page_id)
        if was_positioned and positions[page_id] is None:
            pages_that_lost_their_position.append(page_id)
        if not was_positioned and page_id not in in_some and positions[page_id] is None:
            moved_pages_without_position.append(page_id)
        if (
            page_id in in_every
            and positions[page_id] is not None
            and compute_layout(set_positions(order_put.moved_pages, {page_id: None})).reading_order == tuple(wanted)
        ):
            pages_with_a_needless_position.append(page_id)
    return OrderRound(
        wanted=tuple(wanted),
        reading_order=order_put.layout.reading_order,
        numbers_before=[layout.placements[page_id].number for page_id in wanted],
        numbers_after=[order_put.layout.placements[page_id].number for page_id in wanted],
        kept_score=(len(kept), sum(not is_positioned_before[index] for index in kept)),
        best_kept_score=find_best_kept_score_by_brute_force(naturals, is_positioned_before),
        examined_unnumbered_page_ids=examined_unnumbered_page_ids,
        unnumbered_pages_that_lost_their_position=pages_that_lost_their_position,
        moved_unnumbered_pages_without_position=moved_pages_without_position,
        needless_positions=pages_with_a_needless_position,
        positions=positions,
        positions_asked_again=positions_for_order(order_put.moved_pages, wanted),
    )


def ask_two_other_orders(seed: int, are_wanted_pages: Callable[[list[PageInput]], bool]) -> TwoOrders:
    random_generator = random.Random(seed)
    pages = generate_pages_until(random_generator, are_wanted_pages)
    first = ask_another_order(random_generator, pages)
    second = ask_another_order(random_generator, set_positions(pages, first.positions))
    return TwoOrders(first=first, second=second)


def generate_a_book(random_generator: random.Random) -> list[PageInput]:
    pages, captured_ts, number = [], 0.0, 1
    for book in range(random_generator.randint(1, 3)):
        kinds = ["front"] * random_generator.randint(0, 6) + ["roman"] * (
            random_generator.randint(0, 6) if book == 0 else 0
        )
        for _ in range(random_generator.randint(1, 8)):
            kinds += ["number", "plate"] if random_generator.random() < 0.25 else ["number"]
        missed, roman = random_generator.choice([0, 0, 0.3]), 1
        for seq, kind in enumerate(kinds):
            detected: tuple[str, ...] = ()
            if kind == "roman":
                detected, roman = (int_to_roman(roman),), roman + 1
            elif kind == "number":
                detected, number = (str(number),), number + 1
            if random_generator.random() < missed:
                detected = ()
            pages.append(
                make_page(
                    f"b{book}-{seq}",
                    session_id=f"book{book}",
                    seq=seq,
                    captured_ts=captured_ts,
                    detected_numbers=detected,
                )
            )
            captured_ts += 1
        number += random_generator.randint(0, 5)
    for loose in range(random_generator.randint(1, 4)):
        for seq in range(random_generator.randint(1, 4)):
            pages.append(
                make_page(f"u{loose}-{seq}", session_id=f"loose{loose}", seq=seq, captured_ts=1000 + captured_ts)
            )
            captured_ts += 1
    return pages


def move_loose_sessions_into_a_book(seed: int) -> LooseSessionsMoved:
    random_generator = random.Random(seed)
    pages = generate_a_book(random_generator)
    by_id = {page.id: page for page in pages}
    layout = compute_layout(pages)
    order = list(layout.reading_order)
    sessions = sorted(
        {session for page in pages if (session := page.session_id) is not None and session.startswith("loose")}
    )
    moving = set(random_generator.sample(sessions, random_generator.randint(1, len(sessions))))
    block = [page_id for page_id in order if by_id[page_id].session_id in moving]
    if random_generator.random() < 0.3:
        random_generator.shuffle(block)
    rest = [page_id for page_id in order if page_id not in block]
    placed = sum(layout.placements[page_id].sort_value is not None for page_id in rest)
    places = [layout.placements[page_id].sort_value for page_id in rest]
    indexes_among_the_placed_pages_but_not_between_two_at_the_same_place = [
        index for index in range(placed + 1) if index in (0, placed) or places[index - 1] != places[index]
    ]
    insertion_index = random_generator.choice(indexes_among_the_placed_pages_but_not_between_two_at_the_same_place)
    return LooseSessionsMoved(
        order_put=put_order(pages, rest[:insertion_index] + block + rest[insertion_index:]), moved_page_ids=set(block)
    )


@pytest.fixture(scope="module", params=SEEDS, ids=lambda seed: f"seed {seed}")
def two_other_orders(request: pytest.FixtureRequest) -> TwoOrders:
    return ask_two_other_orders(request.param, holds_two_pages_to_order_or_more)


@pytest.fixture(scope="module", params=SEEDS, ids=lambda seed: f"seed {seed}")
def two_other_orders_of_pages_with_an_unnumbered_one(request: pytest.FixtureRequest) -> TwoOrders:
    return ask_two_other_orders(request.param, holds_an_unnumbered_page_among_two_to_order_or_more)


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
                texts, number = request.param
                return Reading(page_number=parse_detected_numbers(texts), expected_page_number=PageNumber(number))

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
                texts, number, label = request.param
                page_number = parse_detected_numbers(texts)
                return RomanReading(
                    page_number=page_number, label=read_label(page_number), expected_number=number, expected_label=label
                )

            def test_should_read_it_as_front_matter(self, roman_reading: RomanReading) -> None:
                assert roman_reading.page_number == PageNumber(roman_reading.expected_number, front_matter=True)

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
            def numbers_read_back(self) -> dict[int, int | None]:
                return {number: roman_to_int(int_to_roman(number)) for number in range(1, 400)}

            def test_should_read_back_every_number_from_1_to_399(
                self, numbers_read_back: dict[int, int | None]
            ) -> None:
                assert len(numbers_read_back) == 399
                assert [number for number, read_back in numbers_read_back.items() if read_back != number] == []

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
                        make_page("a", manual_number=5, detected_numbers=("7",), hint_number=9),
                        make_page("b", detected_numbers=("7",), hint_number=9, captured_ts=1),
                        make_page("c", hint_number=9, captured_ts=2),
                    ]
                )

            def test_should_take_the_typed_number_then_the_one_found_then_the_hint(self, layout: Layout) -> None:
                assert read_numbers_and_sources(layout, ["a", "b", "c"]) == [
                    (PageNumber(5), "manual"),
                    (PageNumber(7), "detected"),
                    (PageNumber(9), "hint"),
                ]

        class TestWhenANumberIsTypedOnASpread:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout([make_page("a", manual_number=10, detected_numbers=("42", "43"))])

            def test_should_replace_the_spread(self, layout: Layout) -> None:
                assert layout.placements["a"].number == PageNumber(10)

        class TestWhenPagesFollowANumberedPageInTheirSession:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("a", seq=0, detected_numbers=("10",)),
                        make_page("b", seq=1, captured_ts=1),
                        make_page("c", seq=2, captured_ts=2),
                    ]
                )

            def test_should_count_on_from_it(self, layout: Layout) -> None:
                assert read_labels(layout) == ["10", "11", "12"]

            def test_should_mark_their_numbers_as_inferred(self, layout: Layout) -> None:
                assert [layout.placements[page_id].source for page_id in ("b", "c")] == ["inferred", "inferred"]

        class TestWhenPagesComeBeforeTheFirstNumberedPageOfTheirSession:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("a", seq=0),
                        make_page("b", seq=1, captured_ts=1),
                        make_page("c", seq=2, captured_ts=2, detected_numbers=("5",)),
                    ]
                )

            def test_should_count_back_from_it(self, layout: Layout) -> None:
                assert read_labels(layout, ["a", "b", "c"]) == ["3", "4", "5"]

        class TestWhenCountingBackWouldGoBelowPage1:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [make_page("a", seq=0), make_page("b", seq=1, captured_ts=1, detected_numbers=("1",))]
                )

            def test_should_leave_the_page_unnumbered(self, layout: Layout) -> None:
                assert layout.placements["a"].number is None

        class TestWhenShotsWereDeletedBetweenTwoPagesOfASession:
            @pytest.fixture
            def layout(self) -> Layout:
                shot_0_of_page_10 = make_page("a", seq=0, detected_numbers=("10",))
                shot_3_after_two_deleted_shots = make_page("b", seq=3, captured_ts=1)
                return compute_layout([shot_0_of_page_10, shot_3_after_two_deleted_shots])

            def test_should_count_the_distance_in_shots(self, layout: Layout) -> None:
                assert layout.placements["b"].number == PageNumber(13)

        class TestWhenAnUnnumberedPlateLiesBetweenTwoConsecutivePages:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("p10", seq=0, detected_numbers=("10",)),
                        make_page("plate", seq=1, captured_ts=1),
                        make_page("p11", seq=2, captured_ts=2, detected_numbers=("11",)),
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
                return compute_layout(
                    [make_page("a", seq=0, detected_numbers=("42", "43")), make_page("b", seq=1, captured_ts=1)]
                )

            def test_should_count_on_from_its_last_page(self, layout: Layout) -> None:
                assert layout.placements["b"].number == PageNumber(44)

        class TestWhenTheNumberedPageBeforeIsFrontMatter:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [make_page("a", seq=0, detected_numbers=("ix",)), make_page("b", seq=1, captured_ts=1)]
                )

            def test_should_count_on_in_the_front_matter(self, layout: Layout) -> None:
                assert layout.placements["b"].number == PageNumber(10, front_matter=True)

            def test_should_label_the_page_in_roman_numerals(self, layout: Layout) -> None:
                assert read_labels(layout, ["b"]) == ["x"]

        class TestWhenTheNumberedPageWasScannedInAnotherSessionOrWithoutOne:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("a", session_id="s1", seq=0, detected_numbers=("10",)),
                        make_page("b", session_id="s2", seq=1, captured_ts=1),
                        make_page("c", session_id=None, seq=1, captured_ts=2),
                    ]
                )

            def test_should_leave_the_page_of_another_session_unnumbered(self, layout: Layout) -> None:
                assert layout.placements["b"].number is None

            def test_should_leave_the_page_without_a_session_unnumbered(self, layout: Layout) -> None:
                assert layout.placements["c"].number is None

        class TestWhenTheNumberedPageBeforeIsExcluded:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("a", seq=0, detected_numbers=("10",), excluded=True),
                        make_page("b", seq=1, captured_ts=1),
                    ]
                )

            def test_should_not_count_from_it(self, layout: Layout) -> None:
                assert layout.placements["b"].number is None

        class TestWhenThePageBeforeWaitsForOcrWithAHint:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [make_page("a", seq=0, hint_number=20, status="queued"), make_page("b", seq=1, captured_ts=1)]
                )

            def test_should_count_on_from_the_hint(self, layout: Layout) -> None:
                assert layout.placements["b"].number == PageNumber(21)

        class TestWhenABookIsScannedFromItsFrontMatterIntoItsMainTextInOneSession:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(make_book_with_roman_front_matter())

            def test_should_number_the_two_pages_between_xxv_and_3_as_pages_1_and_2_not_xxvi_and_xxvii(
                self, layout: Layout
            ) -> None:
                scanned = [f"s{seq}" for seq in range(1, 26)]
                front_matter = "i ii iii iv v vi vii viii ix x xi xii xiii xiv xv xvi xvii xviii xix xx xxi xxv".split()
                assert read_labels(layout, scanned) == [*front_matter, "1", "2", "3"]

            def test_should_mark_the_numbers_of_those_two_pages_as_inferred_and_that_of_page_3_as_found(
                self, layout: Layout
            ) -> None:
                sources = [layout.placements[page_id].source for page_id in ("s23", "s24", "s25")]
                assert sources == ["inferred", "inferred", "detected"]

            def test_should_keep_the_pages_in_the_order_of_the_scan(self, layout: Layout) -> None:
                assert layout.reading_order == tuple(f"s{seq}" for seq in range(1, 26))

            def test_should_place_every_page_by_its_number(self, layout: Layout) -> None:
                assert read_placements(layout) == ["number"] * 25

            def test_should_cover_pages_1_to_3_and_count_no_page_as_unnumbered(self, layout: Layout) -> None:
                assert (layout.coverage.label, layout.coverage.unnumbered) == ("1–3", 0)

        class TestWhenTheUserTypedTheNumbersItWouldInfer:
            @pytest.fixture
            def compared_layouts(self) -> ComparedLayouts:
                return ComparedLayouts(
                    typed_layout=compute_layout(make_book_with_roman_front_matter({23: 1, 24: 2})),
                    inferred_layout=compute_layout(make_book_with_roman_front_matter()),
                )

            def test_should_keep_the_typed_numbers(self, compared_layouts: ComparedLayouts) -> None:
                assert read_numbers_and_sources(compared_layouts.typed_layout, ["s23", "s24"]) == [
                    (PageNumber(1), "manual"),
                    (PageNumber(2), "manual"),
                ]

            def test_should_infer_the_same_numbers_without_them(self, compared_layouts: ComparedLayouts) -> None:
                assert read_numbers_and_sources(compared_layouts.inferred_layout, ["s23", "s24"]) == [
                    (PageNumber(1), "inferred"),
                    (PageNumber(2), "inferred"),
                ]

            def test_should_keep_the_same_order(self, compared_layouts: ComparedLayouts) -> None:
                assert compared_layouts.typed_layout.reading_order == compared_layouts.inferred_layout.reading_order

        class TestWhenTheUserTypedPage1OnThePageReadAsXxv:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(make_book_with_roman_front_matter({22: 1}))

            def test_should_end_the_front_matter_before_it_count_on_from_it_and_leave_an_extra_photo_before_page_3(
                self, layout: Layout
            ) -> None:
                assert read_labels(layout, ["s21", "s22", "s23", "s24", "s25"]) == ["xxi", "1", "2", None, "3"]

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
                    return SessionReading(labels=label_a_session(detected), expected_labels=expected)

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
                    return SessionReading(labels=label_a_session(detected), expected_labels=expected)

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
                    return SessionReading(labels=label_a_session(detected), expected_labels=expected)

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
                    return SessionReading(labels=label_a_session(detected), expected_labels=expected)

                def test_should_infer_no_number_that_reaches_it(self, session_reading: SessionReading) -> None:
                    assert session_reading.labels == session_reading.expected_labels

        class TestWhenABookIsScannedInOrderAndTheOcrMissesSomeNumbers:
            @pytest.fixture(scope="class", params=range(300), ids=lambda seed: f"seed {seed}")
            @classmethod
            def scanned_book(cls, request: pytest.FixtureRequest) -> BookScannedInOrder:
                pages, real_labels = scan_a_book_in_order(random.Random(request.param), skips_pages=False)
                layout = compute_layout(pages)
                scan_order = tuple(page.id for page in pages)
                return BookScannedInOrder(
                    scan_order=scan_order,
                    reading_order=layout.reading_order,
                    labels=read_labels(layout, scan_order),
                    expected_labels=predict_labels(pages, real_labels),
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
                pages, real_labels = scan_a_book_in_order(random.Random(request.param), skips_pages=True)
                layout = compute_layout(pages)
                numbers = [layout.placements[page.id].number for page in pages]
                found = [parse_detected_numbers(page.detected_numbers) is not None for page in pages]
                return BookScannedSkippingPages(
                    scan_order=tuple(page.id for page in pages),
                    reading_order=layout.reading_order,
                    naturals=[number.natural for number in numbers if number is not None],
                    labels_of_the_numbers_found=[
                        read_label(number) for number, is_found in zip(numbers, found, strict=True) if is_found
                    ],
                    real_labels_of_the_numbers_found=[
                        label for label, is_found in zip(real_labels, found, strict=True) if is_found
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
                pages = generate_a_session(random.Random(request.param))
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
                pages_6_to_10_scanned_first = [
                    make_page(
                        f"p{number}",
                        session_id="first",
                        seq=number - 6,
                        captured_ts=100 + number,
                        detected_numbers=(str(number),),
                    )
                    for number in range(6, 11)
                ]
                pages_1_to_5_scanned_later = [
                    make_page(
                        f"p{number}",
                        session_id="second",
                        seq=number - 1,
                        captured_ts=200 + number,
                        detected_numbers=(str(number),),
                    )
                    for number in range(1, 6)
                ]
                return compute_layout(pages_6_to_10_scanned_first + pages_1_to_5_scanned_later)

            def test_should_merge_them_by_number(self, layout: Layout) -> None:
                assert read_labels(layout) == [str(number) for number in range(1, 11)]

            def test_should_cover_every_number(self, layout: Layout) -> None:
                assert layout.coverage.label == "1–10"

        class TestWhenTheDocumentHasRomanFrontMatter:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("p2", detected_numbers=("2",), captured_ts=1),
                        make_page("p1", detected_numbers=("1",), captured_ts=2),
                        make_page("pii", detected_numbers=("ii",), captured_ts=3),
                        make_page("pi", detected_numbers=("i",), captured_ts=4),
                    ]
                )

            def test_should_put_the_front_matter_first(self, layout: Layout) -> None:
                assert read_labels(layout) == ["i", "ii", "1", "2"]

            def test_should_leave_the_front_matter_out_of_the_coverage(self, layout: Layout) -> None:
                assert layout.coverage.ranges == ((1, 2),)

        class TestWhenSomePagesHaveNeitherANumberNorASession:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("u2", session_id=None, captured_ts=50),
                        make_page("n2", detected_numbers=("2",), captured_ts=10),
                        make_page("u1", session_id=None, captured_ts=40),
                        make_page("n1", detected_numbers=("1",), captured_ts=20),
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
                        make_page("x0", session_id="x", seq=0, captured_ts=50),
                        make_page("x1", session_id="x", seq=1, captured_ts=45),
                        make_page("y1", session_id="y", seq=1, captured_ts=12),
                        make_page("y0", session_id="y", seq=0, captured_ts=10),
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
                        make_page("old", session_id="a", detected_numbers=("7",), captured_ts=10),
                        make_page("new", session_id="b", detected_numbers=("7",), captured_ts=20),
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
                        make_page("done", detected_numbers=("7",), captured_ts=10),
                        make_page("excluded", detected_numbers=("7",), captured_ts=20, excluded=True),
                        make_page("queued", hint_number=7, captured_ts=30, status="queued"),
                    ]
                )

            def test_should_keep_the_page_that_is_done_in_the_document(self, layout: Layout) -> None:
                assert layout.reading_order == ("done",)

            def test_should_mark_no_page_as_a_duplicate(self, layout: Layout) -> None:
                assert [placement.duplicate_of for placement in layout.placements.values()] == [None, None, None]

        class TestWhenFrontMatterAndTheMainTextShareAValue:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("roman", detected_numbers=("v",)),
                        make_page("arabic", detected_numbers=("5",), captured_ts=1),
                    ]
                )

            def test_should_keep_both_pages(self, layout: Layout) -> None:
                assert set(layout.reading_order) == {"roman", "arabic"}

        class TestWhenPagesAreDuplicatedExcludedOrNotDone:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("dup", detected_numbers=("1",), captured_ts=1),
                        make_page("ok", detected_numbers=("1",), captured_ts=9),
                        make_page("excl", detected_numbers=("2",), captured_ts=2, excluded=True),
                        make_page("err", captured_ts=4, status="error"),
                        make_page("queued", captured_ts=3, status="queued"),
                        make_page("proc", captured_ts=5, status="processing"),
                    ]
                )

            def test_should_list_the_reading_order_then_the_pages_not_done_excluded_and_duplicated_each_by_capture_time(
                self, layout: Layout
            ) -> None:
                assert layout.order == ("ok", "queued", "err", "proc", "excl", "dup")

            def test_should_rank_each_page_by_its_place_in_that_list(self, layout: Layout) -> None:
                assert [layout.placements[page_id].rank for page_id in layout.order] == list(range(6))

        class TestWhenNumbersAreMissingBetweenPagesAndASpread:
            @pytest.fixture
            def layout(self) -> Layout:
                pages = [
                    make_page(f"p{number}", detected_numbers=(str(number),), captured_ts=number)
                    for number in (1, 2, 3, 7, 8)
                ]
                return compute_layout([*pages, make_page("spread", detected_numbers=("10", "11"), captured_ts=20)])

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
                twenty_unnumbered_front_pages = [
                    make_page(f"f{index}", seq=index, captured_ts=index) for index in range(20)
                ]
                pages_1_to_5 = [
                    make_page(f"p{number}", seq=19 + number, captured_ts=19 + number, detected_numbers=(str(number),))
                    for number in range(1, 6)
                ]
                return compute_layout(pages_1_to_5 + twenty_unnumbered_front_pages)

            def test_should_open_the_document_with_them(self, layout: Layout) -> None:
                assert layout.reading_order == tuple(f"f{index}" for index in range(20)) + tuple(
                    f"p{number}" for number in range(1, 6)
                )

            def test_should_place_them_by_their_session(self, layout: Layout) -> None:
                assert read_placements(layout) == ["session"] * 20 + ["number"] * 5

            def test_should_place_the_last_one_a_session_step_before_page_1(self, layout: Layout) -> None:
                assert layout.placements["f19"].sort_value == pytest.approx(1 - SESSION_STEP)

            def test_should_place_the_first_one_20_session_steps_before_page_1(self, layout: Layout) -> None:
                assert layout.placements["f0"].sort_value == pytest.approx(1 - 20 * SESSION_STEP)

            def test_should_leave_them_unnumbered(self, layout: Layout) -> None:
                assert read_labels(layout) == [None] * 20 + ["1", "2", "3", "4", "5"]

            def test_should_count_them_as_unnumbered_outside_the_coverage(self, layout: Layout) -> None:
                assert (layout.coverage.label, layout.coverage.unnumbered) == ("1–5", 20)

        class TestWhenAnUnnumberedPlateIsScannedAfterAPage:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("p13", seq=2, captured_ts=2, detected_numbers=("13",)),
                        make_page("plate", seq=1, captured_ts=1),
                        make_page("p12", seq=0, captured_ts=0, detected_numbers=("12",)),
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
                        make_page("p1", session_id="book", seq=0, captured_ts=10, detected_numbers=("1",)),
                        make_page("p2", session_id="book", seq=1, captured_ts=11, detected_numbers=("2",)),
                        make_page("u2", session_id="loose", seq=1, captured_ts=1),
                        make_page("u1", session_id="loose", seq=0, captured_ts=2),
                    ]
                )

            def test_should_put_them_last_in_the_order_of_their_shots(self, layout: Layout) -> None:
                assert layout.reading_order == ("p1", "p2", "u1", "u2")

            def test_should_leave_them_unplaced(self, layout: Layout) -> None:
                assert read_placements(layout) == ["number", "number", "unplaced", "unplaced"]

            def test_should_give_them_no_place_on_the_number_line(self, layout: Layout) -> None:
                assert layout.placements["u1"].sort_value is None

        class TestWhenTheShotsOfASessionHaveNoSeq:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("p5", captured_ts=0, detected_numbers=("5",)),
                        make_page("b", captured_ts=2),
                        make_page("a", captured_ts=1),
                        make_page("p6", captured_ts=3, detected_numbers=("6",)),
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
                        make_page("p1", session_id="b", seq=0, captured_ts=10, detected_numbers=("1",)),
                        make_page("ii", session_id="a", seq=0, captured_ts=1, detected_numbers=("ii",)),
                        make_page("plate", session_id="a", seq=1, captured_ts=2),
                        make_page("iii", session_id="a", seq=2, captured_ts=3, detected_numbers=("iii",)),
                    ]
                )

            def test_should_order_the_front_matter_and_its_plate_before_page_1(self, layout: Layout) -> None:
                assert read_labels(layout) == ["ii", None, "iii", "1"]

            def test_should_place_the_front_matter_before_page_1_on_the_number_line(self, layout: Layout) -> None:
                assert read_places_on_the_number_line(layout) == pytest.approx(
                    [2 - 10_000, 2 - 10_000 + SESSION_STEP, 3 - 10_000, 1]
                )

        class TestWhenAPlateIsScannedAfterASpread:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("spread", seq=0, detected_numbers=("42", "43")),
                        make_page("plate", seq=1, captured_ts=1),
                        make_page("p44", seq=2, captured_ts=2, detected_numbers=("44",)),
                        make_page("p41", session_id="other", captured_ts=3, detected_numbers=("41",)),
                    ]
                )

            def test_should_order_the_spread_by_its_first_page(self, layout: Layout) -> None:
                assert read_labels(layout) == ["41", "42–43", None, "44"]

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
                        make_page("p1", detected_numbers=("1",), captured_ts=1),
                        make_page("p2", detected_numbers=("2",), captured_ts=2),
                        make_page("p3", detected_numbers=("3",), captured_ts=3, position=1.5),
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
                        make_page("late", session_id="a", detected_numbers=("4",), captured_ts=20),
                        make_page("early", session_id="b", captured_ts=10, position=4.0),
                    ]
                )

            def test_should_order_them_by_capture_time(self, layout: Layout) -> None:
                assert layout.reading_order == ("early", "late")

        class TestWhenADuplicateHasAPosition:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("old", session_id="a", detected_numbers=("7",), captured_ts=10, position=0.5),
                        make_page("p6", session_id="b", seq=0, detected_numbers=("6",), captured_ts=19),
                        make_page("new", session_id="b", seq=1, detected_numbers=("7",), captured_ts=20),
                    ]
                )

            def test_should_still_take_it_for_a_duplicate_and_leave_it_unplaced(self, layout: Layout) -> None:
                old = layout.placements["old"]
                assert (old.duplicate_of, old.in_document, old.placed_by, old.sort_value) == ("new", False, None, None)

            def test_should_order_the_other_pages_by_number(self, layout: Layout) -> None:
                assert layout.reading_order == ("p6", "new")

            def test_should_place_the_other_pages_by_their_number(self, layout: Layout) -> None:
                assert read_placements(layout) == ["number", "number"]

        class TestWhenAPageIsScannedAgainLater:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("p11", session_id="a", seq=0, captured_ts=0, detected_numbers=("11",)),
                        make_page("old12", session_id="a", seq=1, captured_ts=1, detected_numbers=("12",)),
                        make_page("plate", session_id="a", seq=2, captured_ts=2),
                        make_page("p13", session_id="a", seq=3, captured_ts=3, detected_numbers=("13",)),
                        make_page("new12", session_id="b", seq=0, captured_ts=10, detected_numbers=("12",)),
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
                        make_page("p11", seq=0, detected_numbers=("11",)),
                        make_page("p12", seq=1, captured_ts=1, detected_numbers=("12",), status="queued"),
                        make_page("plate", seq=2, captured_ts=2),
                        make_page("p13", seq=3, captured_ts=3, detected_numbers=("13",)),
                    ]
                )

            def test_should_still_place_the_plate_after_it_since_it_may_be_read_again(self, layout: Layout) -> None:
                assert layout.placements["plate"].sort_value == pytest.approx(12 + SESSION_STEP)

        class TestWhenThePageBeforeAPlateIsExcluded:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("p11", seq=0, detected_numbers=("11",)),
                        make_page("p12", seq=1, captured_ts=1, detected_numbers=("12",), excluded=True),
                        make_page("plate", seq=2, captured_ts=2),
                        make_page("p13", seq=3, captured_ts=3, detected_numbers=("13",)),
                    ]
                )

            def test_should_place_the_plate_after_the_page_before_the_excluded_one(self, layout: Layout) -> None:
                assert layout.placements["plate"].sort_value == pytest.approx(11 + 2 * SESSION_STEP)

        class TestWhenAPageWithAPositionComesBeforeOthersOfItsSession:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(
                    [
                        make_page("p1", session_id="a", seq=0, detected_numbers=("1",)),
                        make_page("p2", session_id="a", seq=1, captured_ts=1, detected_numbers=("2",)),
                        make_page("map", session_id="b", seq=0, captured_ts=5, position=1.5),
                        make_page("legend", session_id="b", seq=1, captured_ts=6),
                    ]
                )

            def test_should_keep_them_after_it(self, layout: Layout) -> None:
                assert layout.reading_order == ("p1", "map", "legend", "p2")

            def test_should_place_them_by_their_session(self, layout: Layout) -> None:
                assert read_placements(layout) == ["number", "manual", "session", "number"]

        class TestWhenABookHasFrontPagesAPlateAndPagesScannedOnTheirOwn:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(make_book_with_front_pages_a_plate_and_loose_pages())

            def test_should_put_the_pages_scanned_on_their_own_last(self, layout: Layout) -> None:
                assert layout.reading_order[-3:] == ("u0", "u1", "u2")

            def test_should_place_the_book_by_its_numbers_and_session_and_leave_the_other_pages_unplaced(
                self, layout: Layout
            ) -> None:
                assert read_placements(layout) == [*PLACEMENTS_OF_THE_BOOK_PAGES, "unplaced", "unplaced", "unplaced"]

        class TestWhenPagesOfTwoSessionsAreScannedJustBeforeTheSamePage1:
            @pytest.fixture
            def layout(self) -> Layout:
                return compute_layout(make_pages_before_page_1_in_two_sessions())

            def test_should_order_both_before_the_page_1_kept(self, layout: Layout) -> None:
                assert layout.reading_order == ("a0", "b0", "b1", "x")

            def test_should_give_them_the_same_place_a_session_step_before_page_1(self, layout: Layout) -> None:
                places = read_places_on_the_number_line(layout, ["a0", "b0"])
                assert places[0] == places[1] == pytest.approx(1 - SESSION_STEP)

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

    class TestTheOrderPositionsFunction:
        class TestWhenOnePageIsMoved:
            @pytest.fixture
            def reordering(self) -> Reordering:
                return reorder(
                    make_numbered_pages(*range(1, 11)), ["p1", "p2", "p7", "p3", "p4", "p5", "p6", "p8", "p9", "p10"]
                )

            def test_should_give_exactly_one_position(self, reordering: Reordering) -> None:
                assert reordering.positions == [None, None, 2.5, None, None, None, None, None, None, None]

            def test_should_give_the_wanted_order(self, reordering: Reordering) -> None:
                assert reordering.layout.reading_order == reordering.wanted

            class TestWhenTheSameOrderIsAskedAgain:
                @pytest.fixture
                def positions_asked_again(self, reordering: Reordering) -> list[float | None]:
                    return reorder(reordering.moved_pages, list(reordering.wanted)).positions

                def test_should_give_the_same_positions(
                    self, reordering: Reordering, positions_asked_again: list[float | None]
                ) -> None:
                    assert positions_asked_again == reordering.positions

        class TestWhenUnplacedPagesAreMovedBeforePage1:
            @pytest.fixture
            def reordering(self) -> Reordering:
                body = make_numbered_pages(1, 2, 3, 4, 5)
                front = [
                    make_page(f"f{index}", session_id="loose", seq=index, captured_ts=100 + index)
                    for index in range(20)
                ]
                return reorder(body + front, [page.id for page in front + body])

            def test_should_count_their_positions_back_from_page_1_one_by_one(self, reordering: Reordering) -> None:
                assert reordering.positions == [float(position) for position in range(-19, 1)] + [None] * 5

            class TestWhenPage6IsScannedLater:
                @pytest.fixture
                def layout(self, reordering: Reordering) -> Layout:
                    return compute_layout(
                        [
                            *reordering.moved_pages,
                            make_page("p6", session_id="later", captured_ts=200, detected_numbers=("6",)),
                        ]
                    )

                def test_should_slot_it_in_after_page_5(self, reordering: Reordering, layout: Layout) -> None:
                    assert layout.reading_order == (*reordering.wanted, "p6")

        class TestWhenPagesAreMovedBetweenTwoPagesThatStay:
            @pytest.fixture
            def reordering(self) -> Reordering:
                pages = [
                    *make_numbered_pages(1, 2),
                    make_page("x", session_id="x", captured_ts=10),
                    make_page("y", session_id="y", captured_ts=11),
                ]
                return reorder(pages, ["p1", "x", "y", "p2"])

            def test_should_share_the_gap_between_them(self, reordering: Reordering) -> None:
                assert reordering.positions == pytest.approx([None, 1 + 1 / 3, 1 + 2 / 3, None])

            def test_should_give_the_wanted_order(self, reordering: Reordering) -> None:
                assert reordering.layout.reading_order == reordering.wanted

        class TestWhenPagesAreMovedAfterTheLastPageThatStays:
            @pytest.fixture
            def reordering(self) -> Reordering:
                pages = [
                    *make_numbered_pages(4, 5),
                    make_page("x", session_id="x", captured_ts=10),
                    make_page("y", session_id="y", captured_ts=11),
                ]
                return reorder(pages, ["p4", "p5", "y", "x"])

            def test_should_place_them_after_it_one_by_one(self, reordering: Reordering) -> None:
                assert reordering.positions == [None, None, 6.0, 7.0]

        class TestWhenNoPageHasANumber:
            @pytest.fixture
            def reordering(self) -> Reordering:
                return reorder(
                    [make_page(letter, session_id=letter, captured_ts=index) for index, letter in enumerate("abc")],
                    ["c", "a", "b"],
                )

            def test_should_give_the_positions_1_to_n(self, reordering: Reordering) -> None:
                assert reordering.positions == [1.0, 2.0, 3.0]

            def test_should_give_the_wanted_order(self, reordering: Reordering) -> None:
                assert reordering.layout.reading_order == reordering.wanted

            def test_should_place_every_page_by_its_position(self, reordering: Reordering) -> None:
                assert read_placements(reordering.layout) == ["manual"] * 3

        class TestWhenTwoPagesAreSwappedSoThatEitherOneNeedsAPosition:
            class TestWhenPage2AlreadyHasAPosition:
                @pytest.fixture
                def reordering(self) -> Reordering:
                    pages = set_positions(make_numbered_pages(1, 2, 3, 4), {"p2": 3.5})
                    return reorder(pages, ["p1", "p3", "p2", "p4"])

                def test_should_give_the_position_to_that_page_rather_than_to_the_other(
                    self, reordering: Reordering
                ) -> None:
                    assert reordering.positions == [None, None, 3.5, None]

            class TestWhenPage3AlreadyHasAPosition:
                @pytest.fixture
                def reordering(self) -> Reordering:
                    pages = set_positions(make_numbered_pages(1, 2, 3, 4), {"p3": 1.5})
                    return reorder(pages, ["p1", "p3", "p2", "p4"])

                def test_should_give_the_position_to_that_page_rather_than_to_the_other(
                    self, reordering: Reordering
                ) -> None:
                    assert reordering.positions == [None, 1.5, None, None]

        class TestWhenPagesWithAPositionAreOrderedByTheirNumbersAgain:
            @pytest.fixture
            def reordering(self) -> Reordering:
                pages = set_positions(make_numbered_pages(1, 2, 3, 4), {"p2": 3.5})
                return reorder(pages, ["p1", "p2", "p3", "p4"])

            def test_should_give_no_position(self, reordering: Reordering) -> None:
                assert reordering.positions == [None] * 4

        class TestWhenAnyOrderIsAsked:
            @pytest.fixture(scope="class", params=range(200), ids=lambda seed: f"seed {seed}")
            @classmethod
            def shuffled_order(cls, request: pytest.FixtureRequest) -> ShuffledOrder:
                return shuffle_any_order(random.Random(request.param))

            def test_should_give_the_wanted_order(self, shuffled_order: ShuffledOrder) -> None:
                assert shuffled_order.reading_order == shuffled_order.wanted

            def test_should_keep_the_most_pages_in_place_those_without_a_position_first(
                self, shuffled_order: ShuffledOrder
            ) -> None:
                assert shuffled_order.kept_score == shuffled_order.best_kept_score

            def test_should_keep_the_number_of_every_page(self, shuffled_order: ShuffledOrder) -> None:
                assert shuffled_order.numbers_after == shuffled_order.numbers_before

    class TestThePositionsForOrderFunction:
        class TestWhenPagesScannedOnTheirOwnAreMovedToTheFrontOfABook:
            @pytest.fixture
            def order_put(self) -> OrderPut:
                pages = make_book_with_front_pages_a_plate_and_loose_pages()
                order = compute_layout(pages).reading_order
                return put_order(pages, [*order[-3:], *order[:-3]])

            def test_should_give_the_wanted_order(self, order_put: OrderPut) -> None:
                assert order_put.layout.reading_order == order_put.wanted

            def test_should_give_positions_to_those_pages_only_counting_back_from_the_first_page(
                self, order_put: OrderPut
            ) -> None:
                assert select_the_given_positions(order_put.positions) == {"u0": -22.0, "u1": -21.0, "u2": -20.0}

            def test_should_leave_the_front_pages_and_the_plate_placed_by_their_session(
                self, order_put: OrderPut
            ) -> None:
                assert read_placements(order_put.layout) == ["manual"] * 3 + PLACEMENTS_OF_THE_BOOK_PAGES

        class TestWhenPagesScannedOnTheirOwnAreMovedBetweenTheFrontPagesAndPage1:
            @pytest.fixture
            def order_put(self) -> OrderPut:
                pages = make_book_with_front_pages_a_plate_and_loose_pages()
                order = compute_layout(pages).reading_order
                return put_order(pages, [*order[:20], *order[-3:], *order[20:-3]])

            def test_should_give_the_wanted_order(self, order_put: OrderPut) -> None:
                assert order_put.layout.reading_order == order_put.wanted

            def test_should_place_them_between_the_place_of_the_last_front_page_and_page_1(
                self, order_put: OrderPut
            ) -> None:
                last_front = 1 - SESSION_STEP
                expected = {f"u{index}": last_front + SESSION_STEP * (index + 1) / 4 for index in range(3)}
                assert select_the_given_positions(order_put.positions) == pytest.approx(expected)

            def test_should_leave_the_other_pages_placed_as_they_were(self, order_put: OrderPut) -> None:
                assert (
                    read_placements(order_put.layout)
                    == PLACEMENTS_OF_THE_BOOK_PAGES[:20] + ["manual"] * 3 + PLACEMENTS_OF_THE_BOOK_PAGES[20:]
                )

            def test_should_leave_the_last_front_page_at_its_place(self, order_put: OrderPut) -> None:
                assert order_put.layout.placements["f19"].sort_value == pytest.approx(1 - SESSION_STEP)

        class TestWhenThePlateIsMovedBeforePage9:
            @pytest.fixture
            def order_put(self) -> OrderPut:
                pages = make_book_with_front_pages_a_plate_and_loose_pages()
                return put_order(pages, move_page_before(compute_layout(pages).reading_order, "plate", before="p9"))

            def test_should_give_the_wanted_order(self, order_put: OrderPut) -> None:
                assert order_put.layout.reading_order == order_put.wanted

            def test_should_give_a_position_to_the_plate_only(self, order_put: OrderPut) -> None:
                assert select_the_given_positions(order_put.positions) == {"plate": 8.5}

            def test_should_leave_the_other_pages_placed_as_they_were(self, order_put: OrderPut) -> None:
                placements = read_placements(order_put.layout, ["f0", "f19", "plate", "u0"])
                assert placements == ["session", "session", "manual", "unplaced"]

            class TestWhenThePlateIsPutBackAfterPage5:
                @pytest.fixture
                def plate_put_back(self, order_put: OrderPut) -> OrderPut:
                    return put_order(order_put.moved_pages, order_put.layout_before.reading_order)

                def test_should_give_the_wanted_order(self, plate_put_back: OrderPut) -> None:
                    assert plate_put_back.layout.reading_order == plate_put_back.wanted

                def test_should_keep_a_position_for_it_since_only_numbered_pages_get_theirs_cleared(
                    self, plate_put_back: OrderPut
                ) -> None:
                    assert select_the_given_positions(plate_put_back.positions) == {"plate": 5.5}

        class TestWhenAFrontPageIsMovedIntoTheMainText:
            @pytest.fixture
            def order_put(self) -> OrderPut:
                pages = make_book_with_front_pages_a_plate_and_loose_pages()
                return put_order(pages, move_page_before(compute_layout(pages).reading_order, "f5", before="p4"))

            def test_should_give_the_wanted_order(self, order_put: OrderPut) -> None:
                assert order_put.layout.reading_order == order_put.wanted

            def test_should_hold_the_pages_scanned_next_to_it_at_their_place_with_a_position(
                self, order_put: OrderPut
            ) -> None:
                expected = {"f4": 1 - 16 * SESSION_STEP, "f6": 1 - 14 * SESSION_STEP, "f5": 3.5}
                assert select_the_given_positions(order_put.positions) == pytest.approx(expected)

            def test_should_leave_every_other_front_page_at_its_place(self, order_put: OrderPut) -> None:
                front = order_put.wanted[:19]
                before = read_places_on_the_number_line(order_put.layout_before, front)
                assert read_places_on_the_number_line(order_put.layout, front) == pytest.approx(before)

            def test_should_leave_the_other_front_pages_placed_by_their_session(self, order_put: OrderPut) -> None:
                assert read_placements(order_put.layout, order_put.wanted[:19]).count("session") == 17

        class TestWhenThePageThatAPlateFollowsIsMoved:
            @pytest.fixture
            def order_put(self) -> OrderPut:
                pages = make_book_with_front_pages_a_plate_and_loose_pages()
                return put_order(pages, move_page_before(compute_layout(pages).reading_order, "p5", before="p9"))

            def test_should_give_the_wanted_order(self, order_put: OrderPut) -> None:
                assert order_put.layout.reading_order == order_put.wanted

            def test_should_hold_the_plate_between_pages_4_and_6_with_a_position(self, order_put: OrderPut) -> None:
                assert select_the_given_positions(order_put.positions) == {"plate": 5.0, "p5": 8.5}

        class TestWhenAnUnplacedPageIsMovedBeforeTheOthers:
            @pytest.fixture
            def order_put(self) -> OrderPut:
                return put_order(
                    [make_page(letter, session_id=letter, captured_ts=index) for index, letter in enumerate("abc")],
                    ["c", "a", "b"],
                )

            def test_should_give_the_wanted_order(self, order_put: OrderPut) -> None:
                assert order_put.layout.reading_order == order_put.wanted

            def test_should_give_a_position_to_that_page_only(self, order_put: OrderPut) -> None:
                assert select_the_given_positions(order_put.positions) == {"c": 1.0}

            def test_should_leave_the_others_unplaced(self, order_put: OrderPut) -> None:
                assert read_placements(order_put.layout) == ["manual", "unplaced", "unplaced"]

        class TestWhenTheLastPageOfASessionWithoutNumbersIsMovedFirst:
            @pytest.fixture
            def order_put(self) -> OrderPut:
                pages = [
                    make_page(letter, session_id="letter", seq=index, captured_ts=index)
                    for index, letter in enumerate("abcd")
                ]
                return put_order(pages, ["d", "a", "b", "c"])

            def test_should_give_the_wanted_order(self, order_put: OrderPut) -> None:
                assert order_put.layout.reading_order == order_put.wanted

            def test_should_hold_the_page_scanned_just_before_it_at_the_end_since_the_others_follow_it(
                self, order_put: OrderPut
            ) -> None:
                assert select_the_given_positions(order_put.positions) == {"d": 1.0, "c": 4.0}

            def test_should_place_the_others_by_their_session(self, order_put: OrderPut) -> None:
                assert read_placements(order_put.layout) == ["manual", "session", "session", "manual"]

        class TestWhenAPageIsMovedBetweenTwoPagesAtTheSamePlace:
            @pytest.fixture
            def order_put(self) -> OrderPut:
                return put_order(make_pages_before_page_1_in_two_sessions(), ["a0", "x", "b0", "b1"])

            def test_should_give_the_wanted_order(self, order_put: OrderPut) -> None:
                assert order_put.layout.reading_order == order_put.wanted

            def test_should_give_a_position_to_one_of_them_too_since_there_is_no_room_between_them(
                self, order_put: OrderPut
            ) -> None:
                assert set(select_the_given_positions(order_put.positions)) == {"x", "b0"}

            def test_should_leave_the_other_pages_placed_as_they_were(self, order_put: OrderPut) -> None:
                assert read_placements(order_put.layout) == ["session", "manual", "manual", "number"]

        class TestWhenTheOrderIsTheCurrentOne:
            @pytest.fixture
            def order_put(self) -> OrderPut:
                needless_positions_an_older_version_set = {f"f{index}": float(index - 22) for index in range(20)}
                pages = set_positions(
                    make_book_with_front_pages_a_plate_and_loose_pages(), needless_positions_an_older_version_set
                )
                return put_order(pages, compute_layout(pages).reading_order)

            def test_should_keep_every_position_even_those_not_needed(self, order_put: OrderPut) -> None:
                assert order_put.positions == {page.id: page.position for page in order_put.pages}

        class TestWhenTheOrderHoldsOtherPagesThanTheReadingOrder:
            @pytest.fixture(
                params=[["p1", "p2"], ["p1", "p2", "p3", "p3"], ["p1", "p2", "p3", "p4"], []],
                ids=["a page missing", "a page twice", "a page that is not in it", "no page"],
            )
            def put_the_order(self, request: pytest.FixtureRequest) -> Callable[[], object]:
                wanted: list[str] = request.param
                return lambda: positions_for_order(make_numbered_pages(1, 2, 3), wanted)

            def test_should_refuse_it(self, put_the_order: Callable[[], object]) -> None:
                with pytest.raises(ValueError, match="not the pages of the reading order"):
                    put_the_order()

        class TestWhenTheSearchHasNoBudgetLeft:
            @pytest.fixture
            def order_put(self, monkeypatch: pytest.MonkeyPatch) -> OrderPut:
                # As on a huge document, where the search stops early.
                monkeypatch.setattr(ordering, "REORDER_BUDGET", 0)
                pages = make_book_with_front_pages_a_plate_and_loose_pages()
                return put_order(pages, move_page_before(compute_layout(pages).reading_order, "f5", before="p4"))

            def test_should_still_give_the_wanted_order(self, order_put: OrderPut) -> None:
                assert order_put.layout.reading_order == order_put.wanted

            def test_should_give_positions_to_more_pages_than_needed(self, order_put: OrderPut) -> None:
                assert {"f4", "f5", "f6"} < set(select_the_given_positions(order_put.positions))

        class TestWhenAnOrderOtherThanTheCurrentOneIsAsked:
            def test_should_give_the_wanted_order(self, two_other_orders: TwoOrders) -> None:
                assert two_other_orders.first.reading_order == two_other_orders.first.wanted

            def test_should_keep_the_number_of_every_page(self, two_other_orders: TwoOrders) -> None:
                assert two_other_orders.first.numbers_after == two_other_orders.first.numbers_before

            def test_should_keep_the_most_numbered_pages_in_place_those_without_a_position_first(
                self, two_other_orders: TwoOrders
            ) -> None:
                assert two_other_orders.first.kept_score == two_other_orders.first.best_kept_score

            def test_should_give_the_same_positions_when_the_same_order_is_asked_again(
                self, two_other_orders: TwoOrders
            ) -> None:
                assert two_other_orders.first.positions_asked_again == two_other_orders.first.positions

            class TestWhenAnotherOrderIsAskedFromThePositionsItGave:
                def test_should_give_the_wanted_order(self, two_other_orders: TwoOrders) -> None:
                    assert two_other_orders.second.reading_order == two_other_orders.second.wanted

                def test_should_keep_the_number_of_every_page(self, two_other_orders: TwoOrders) -> None:
                    assert two_other_orders.second.numbers_after == two_other_orders.second.numbers_before

                def test_should_keep_the_most_numbered_pages_in_place_those_without_a_position_first(
                    self, two_other_orders: TwoOrders
                ) -> None:
                    assert two_other_orders.second.kept_score == two_other_orders.second.best_kept_score

                def test_should_give_the_same_positions_when_the_same_order_is_asked_again(
                    self, two_other_orders: TwoOrders
                ) -> None:
                    assert two_other_orders.second.positions_asked_again == two_other_orders.second.positions

        class TestWhenAnOrderOtherThanTheCurrentOneIsAskedOfPagesSomeOfWhichHaveNoNumber:
            def test_should_keep_a_position_for_each_unnumbered_page_that_had_one(
                self, two_other_orders_of_pages_with_an_unnumbered_one: TwoOrders
            ) -> None:
                asked_order = two_other_orders_of_pages_with_an_unnumbered_one.first
                assert asked_order.examined_unnumbered_page_ids != []
                assert asked_order.unnumbered_pages_that_lost_their_position == []

            def test_should_give_a_position_to_each_unnumbered_page_that_moved(
                self, two_other_orders_of_pages_with_an_unnumbered_one: TwoOrders
            ) -> None:
                asked_order = two_other_orders_of_pages_with_an_unnumbered_one.first
                assert asked_order.examined_unnumbered_page_ids != []
                assert asked_order.moved_unnumbered_pages_without_position == []

            def test_should_give_a_position_to_an_unnumbered_page_that_stays_in_place_only_if_the_order_needs_it(
                self, two_other_orders_of_pages_with_an_unnumbered_one: TwoOrders
            ) -> None:
                asked_order = two_other_orders_of_pages_with_an_unnumbered_one.first
                assert asked_order.examined_unnumbered_page_ids != []
                assert asked_order.needless_positions == []

            class TestWhenAnotherOrderIsAskedFromThePositionsItGave:
                def test_should_keep_a_position_for_each_unnumbered_page_that_had_one(
                    self, two_other_orders_of_pages_with_an_unnumbered_one: TwoOrders
                ) -> None:
                    asked_order = two_other_orders_of_pages_with_an_unnumbered_one.second
                    assert asked_order.examined_unnumbered_page_ids != []
                    assert asked_order.unnumbered_pages_that_lost_their_position == []

                def test_should_give_a_position_to_each_unnumbered_page_that_moved(
                    self, two_other_orders_of_pages_with_an_unnumbered_one: TwoOrders
                ) -> None:
                    asked_order = two_other_orders_of_pages_with_an_unnumbered_one.second
                    assert asked_order.examined_unnumbered_page_ids != []
                    assert asked_order.moved_unnumbered_pages_without_position == []

                def test_should_give_a_position_to_an_unnumbered_page_that_stays_in_place_only_if_the_order_needs_it(
                    self, two_other_orders_of_pages_with_an_unnumbered_one: TwoOrders
                ) -> None:
                    asked_order = two_other_orders_of_pages_with_an_unnumbered_one.second
                    assert asked_order.examined_unnumbered_page_ids != []
                    assert asked_order.needless_positions == []

        class TestWhenTheReadingOrderHoldsNoPage:
            @pytest.fixture
            def order_put(self) -> OrderPut:
                return put_order([make_page("queued", status="queued", position=1.5)], [])

            def test_should_give_the_empty_order(self, order_put: OrderPut) -> None:
                assert order_put.layout.reading_order == ()

            def test_should_give_no_position(self, order_put: OrderPut) -> None:
                assert order_put.positions == {}

        class TestWhenTheReadingOrderHoldsASinglePage:
            @pytest.fixture
            def order_put(self) -> OrderPut:
                pages = [make_page("kept", position=2.5), make_page("excluded", excluded=True, position=0.5)]
                return put_order(pages, ["kept"])

            def test_should_give_the_order_of_that_page(self, order_put: OrderPut) -> None:
                assert order_put.layout.reading_order == ("kept",)

            def test_should_keep_its_position(self, order_put: OrderPut) -> None:
                assert order_put.positions == {"kept": 2.5}

        class TestWhenSessionsScannedOnTheirOwnAreMovedIntoABook:
            @pytest.fixture(scope="class", params=range(200), ids=lambda seed: f"seed {seed}")
            @classmethod
            def loose_sessions_moved(cls, request: pytest.FixtureRequest) -> LooseSessionsMoved:
                return move_loose_sessions_into_a_book(request.param)

            def test_should_give_the_wanted_order(self, loose_sessions_moved: LooseSessionsMoved) -> None:
                order_put = loose_sessions_moved.order_put
                assert order_put.layout.reading_order == order_put.wanted

            def test_should_give_positions_to_their_pages_only(self, loose_sessions_moved: LooseSessionsMoved) -> None:
                positioned = set(select_the_given_positions(loose_sessions_moved.order_put.positions))
                assert positioned <= loose_sessions_moved.moved_page_ids
