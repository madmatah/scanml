"""Page numbering, reading order, duplicates and coverage of a document.

Implements "Page numbering & ordering" of docs/ARCHITECTURE.md for pages that
were scanned in any order, over any number of sessions:

* detected numbers: arabic (``42``), roman front matter (``xii``), and two
  consecutive arabic numbers on one image for a two-page spread (``42–43``);
* effective number = manual ?? detected ?? hint ?? inferred;
* inference along a scanning session (ordered by ``seq``), from the nearest
  previous numbered page, else from the nearest following one, without
  carrying roman front matter into the main text (from page 1) or back;
* duplicates: the most recently captured page wins;
* placement on a number line where page n sits at n and roman front matter
  before page 1: the position chosen by the user, else the page number, else
  next to the neighboring pages of the same scanning session;
* the fewest explicit positions that produce an order chosen by the user,
  given only to the pages that moved;
* reading order and coverage (ranges of numbers present, gaps in between).

Everything here is pure: the library feeds page rows in and stores the result.
"""

from __future__ import annotations

import dataclasses
import math
import re
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable, Sequence, Set
from dataclasses import dataclass
from itertools import pairwise
from typing import TypedDict

DONE = "done"

SOURCE_MANUAL = "manual"
SOURCE_DETECTED = "detected"
SOURCE_HINT = "hint"
SOURCE_INFERRED = "inferred"

# How the place of a page in the reading order was decided.
PLACEMENT_NUMBER = "number"  # its effective page number
PLACEMENT_MANUAL = "manual"  # its position, set by reordering the pages
PLACEMENT_SESSION = "session"  # next to a placed page of its scanning session
PLACEMENT_UNPLACED = "unplaced"  # nothing: after the placed pages, in capture order

#: Roman front matter v sits at v − 10000 on the number line, before page 1.
FRONT_MATTER_OFFSET = 10_000
#: Distance on the number line, per step of seq, between a page placed by its
#: session and the page it is placed next to (far below the gap between two numbers).
SESSION_STEP = 1e-4
#: Work allowed to `positions_for_order` to find the pages that can stay
#: without position, in pages laid out (pages × trial layouts): about a
#: second. On a huge document, the pages not tried in time get a position.
REORDER_BUDGET = 300_000

_ARABIC = re.compile(r"[0-9]{1,4}")
# Canonical roman numerals up to 399: front matter never goes further, and
# excluding d/m avoids reading words or OCR noise ("mix", "dim") as numbers.
_ROMAN = re.compile(r"c{0,3}(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})")
_ROMAN_VALUES = (
    (100, "c"),
    (90, "xc"),
    (50, "l"),
    (40, "xl"),
    (10, "x"),
    (9, "ix"),
    (5, "v"),
    (4, "iv"),
    (1, "i"),
)
# Decorations printed around page numbers: "- 12 -", "(xii)", "12.", "— 7 —".
_NUMBER_DECORATION = "-–—_.,;:·•|()[]{}*«»\"'"
_TOKEN_SPLIT = re.compile(r"[\s\-–—]+")


def roman_to_int(text: str) -> int | None:
    """Value of a canonical lowercase/uppercase roman numeral (1–399), else None."""
    lowered = text.lower()
    if not lowered or not _ROMAN.fullmatch(lowered):
        return None
    value, index = 0, 0
    for amount, symbol in _ROMAN_VALUES:
        while lowered.startswith(symbol, index):
            value += amount
            index += len(symbol)
    return value


def int_to_roman(value: int) -> str:
    """Lowercase roman numeral of 1 ≤ value ≤ 399."""
    parts = []
    for amount, symbol in _ROMAN_VALUES:
        count, value = divmod(value, amount)
        parts.append(symbol * count)
    return "".join(parts)


@dataclass(frozen=True)
class PageNumber:
    """An effective page number: arabic, arabic spread (value–end) or roman front matter."""

    value: int
    end: int | None = None
    front_matter: bool = False

    @property
    def last(self) -> int:
        return self.end if self.end is not None else self.value

    @property
    def label(self) -> str:
        if self.front_matter:
            return int_to_roman(self.value)
        if self.end is not None:
            return f"{self.value}–{self.end}"
        return str(self.value)

    @property
    def natural(self) -> int:
        """Place on the number line: n for page n or the spread n–n+1; front matter before page 1."""
        return self.value - FRONT_MATTER_OFFSET if self.front_matter else self.value


def parse_detected_numbers(texts: Iterable[str]) -> PageNumber | None:
    """Page number from the strings found in page-number blocks of one image.

    Two consecutive arabic numbers make a spread; otherwise the first arabic
    number wins, then the first roman one.
    """
    arabic: list[int] = []
    roman: list[int] = []
    for text in texts:
        for token in _TOKEN_SPLIT.split(text):
            token = token.strip(_NUMBER_DECORATION)
            if _ARABIC.fullmatch(token):
                if int(token) > 0:
                    arabic.append(int(token))
            elif (value := roman_to_int(token)) is not None:
                roman.append(value)
    present = set(arabic)
    for value in arabic:
        if value + 1 in present:
            return PageNumber(value, end=value + 1)
    if arabic:
        return PageNumber(arabic[0])
    if roman:
        return PageNumber(roman[0], front_matter=True)
    return None


@dataclass(frozen=True)
class PageInput:
    """What the algorithm needs to know about one page."""

    id: str
    session_id: str | None
    seq: int | None
    captured_ts: float
    status: str
    excluded: bool = False
    manual_number: int | None = None
    hint_number: int | None = None
    detected_numbers: tuple[str, ...] = ()
    #: Place on the number line chosen by the user (see `order_positions`).
    position: float | None = None

    @property
    def capture_key(self) -> tuple[float, int, str]:
        return (self.captured_ts, self.seq or 0, self.id)


@dataclass(frozen=True)
class Placement:
    """Where a page ends up: its effective number and its place in the document."""

    number: PageNumber | None
    source: str | None
    duplicate_of: str | None
    in_document: bool
    #: How its place in the reading order was decided (PLACEMENT_*), None outside of it.
    placed_by: str | None
    #: Its value on the number line (None: unplaced, or not in the reading order).
    sort_value: float | None
    #: Index of the page in `Layout.order`.
    rank: int


class CoverageJson(TypedDict):
    ranges: list[list[int]]
    label: str
    gaps: list[list[int]]
    min: int | None
    max: int | None
    unnumbered: int


@dataclass(frozen=True)
class Coverage:
    """Arabic page numbers present in the document, as ranges, and the gaps between."""

    ranges: tuple[tuple[int, int], ...]
    unnumbered: int

    @property
    def gaps(self) -> tuple[tuple[int, int], ...]:
        return tuple((previous[1] + 1, current[0] - 1) for previous, current in pairwise(self.ranges))

    @property
    def min(self) -> int | None:
        return self.ranges[0][0] if self.ranges else None

    @property
    def max(self) -> int | None:
        return self.ranges[-1][1] if self.ranges else None

    @property
    def label(self) -> str:
        return format_ranges(self.ranges)

    @property
    def missing_label(self) -> str:
        return format_ranges(self.gaps)

    def to_json(self) -> CoverageJson:
        return {
            "ranges": [list(r) for r in self.ranges],
            "label": self.label,
            "gaps": [list(g) for g in self.gaps],
            "min": self.min,
            "max": self.max,
            "unnumbered": self.unnumbered,
        }


def format_range(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}–{end}"


def format_ranges(ranges: Iterable[tuple[int, int]]) -> str:
    return ", ".join(format_range(start, end) for start, end in ranges)


def _to_ranges(numbers: Iterable[int]) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    for number in sorted(set(numbers)):
        if ranges and number == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], number)
        else:
            ranges.append((number, number))
    return tuple(ranges)


@dataclass(frozen=True)
class Layout:
    """Result of `compute_layout` for one document."""

    placements: dict[str, Placement]
    #: Every page: reading order, then pending (queued/processing/error),
    #: excluded and duplicate pages, each group by capture time.
    order: tuple[str, ...]
    #: Pages that make up document.md, in reading order: the placed pages by
    #: their value on the number line, then the unplaced ones by capture.
    reading_order: tuple[str, ...]
    #: False when no page of the document has a number (letters, forms...).
    numbered: bool
    coverage: Coverage


@dataclass
class _Work:
    page: PageInput
    number: PageNumber | None = None
    source: str | None = None
    duplicate_of: str | None = None
    sort_value: float | None = None
    placed_by: str | None = None

    @property
    def included(self) -> bool:
        return self.page.status == DONE and not self.page.excluded and self.duplicate_of is None

    @property
    def pinned(self) -> float | None:
        """Place of the page on the number line given by itself: its position, else its number."""
        if self.page.position is not None:
            return self.page.position
        return self.number.natural if self.number is not None else None


def _own_number(page: PageInput) -> tuple[PageNumber | None, str | None]:
    """Number known for the page itself: manual, then detected, then the phone's hint."""
    if page.manual_number is not None:
        return PageNumber(page.manual_number), SOURCE_MANUAL
    detected = parse_detected_numbers(page.detected_numbers)
    if detected is not None:
        return detected, SOURCE_DETECTED
    if page.hint_number is not None:
        return PageNumber(page.hint_number), SOURCE_HINT
    return None, None


def _session_steps(members: list[_Work]) -> list[int]:
    """Sort the pages of one session by seq; return their steps (seq, or index if one has none)."""
    members.sort(key=lambda w: (w.page.seq or 0, w.page.captured_ts, w.page.id))
    use_seq = all(w.page.seq is not None for w in members)
    return [w.page.seq if use_seq and w.page.seq is not None else index for index, w in enumerate(members)]


def _infer_session(members: list[_Work]) -> None:
    """Number the unnumbered pages of one session from their numbered neighbors.

    A page at distance d (in seq) after the nearest previous numbered page gets
    its number + d, in the same numbering system (arabic, or roman front
    matter), unless that would reach the next page numbered in that system (an
    extra photo, e.g. an unnumbered plate, must not collide with a real page).
    Without a previous numbered page, it gets next number − d when that is ≥ 1.

    No system is carried across the boundary between the front matter and the
    main text, which starts at page 1. Between a roman page and an arabic page
    n, a page d before n is page n − d of the main text when that is ≥ 1 (and
    above the previous arabic page of the session, if any), else front matter
    (previous number + d). Between an arabic page and a roman one (front matter
    scanned after the main text), only previous number + d applies: no roman
    number is counted back.
    """
    steps = _session_steps(members)
    anchors = [
        (step, work.number)
        for step, work in zip(steps, members, strict=True)
        if work.number is not None and not work.page.excluded
    ]
    if not anchors:
        return
    anchor_steps = [step for step, _ in anchors]  # sorted, like the members
    for step, work in zip(steps, members, strict=True):
        if work.number is not None:
            continue
        before, after = bisect_left(anchor_steps, step), bisect_right(anchor_steps, step)
        previous = anchors[before - 1] if before else None
        following = anchors[after] if after < len(anchors) else None
        inferred: PageNumber | None = None
        if following is not None and (previous is None or (previous[1].front_matter and not following[1].front_matter)):
            f_step, f_num = following
            value = f_num.value - (f_step - step)
            # The pages numbered in that system before this one, nearest first.
            below = (n.last for _, n in reversed(anchors[:before]) if n.front_matter == f_num.front_matter)
            if value > next(below, 0):
                inferred = PageNumber(value, front_matter=f_num.front_matter)
        if inferred is None and previous is not None:
            p_step, p_num = previous
            value = p_num.last + (step - p_step)
            # The pages numbered in that system after this one, nearest first.
            above = (n.value for _, n in anchors[after:] if n.front_matter == p_num.front_matter)
            if value < next(above, math.inf):
                inferred = PageNumber(value, front_matter=p_num.front_matter)
        if inferred is not None and (not inferred.front_matter or inferred.value <= 399):
            work.number, work.source = inferred, SOURCE_INFERRED


def _anchor_session(members: list[_Work]) -> None:
    """Place the pages of one session that have neither position nor number.

    A page at distance d (in seq) after the nearest previous page of the
    session that has a position or a number is placed d × SESSION_STEP after
    it; without one, d × SESSION_STEP before the nearest following one: an
    unnumbered plate stays after the page it was scanned with, a title page
    scanned before page 1 stays before it. Excluded pages are not anchors;
    duplicates and pages waiting for OCR are (their number still tells where
    the session was in the book).
    """
    steps = _session_steps(members)
    anchors = [
        (step, value)
        for step, work in zip(steps, members, strict=True)
        if (value := work.pinned) is not None and not work.page.excluded
    ]
    if not anchors:
        return
    anchor_steps = [step for step, _ in anchors]  # sorted, like the members
    for step, work in zip(steps, members, strict=True):
        if not work.included or work.pinned is not None:
            continue
        before, after = bisect_left(anchor_steps, step), bisect_right(anchor_steps, step)
        previous = anchors[before - 1] if before else None
        following = anchors[after] if after < len(anchors) else None
        if previous is not None:
            work.sort_value = previous[1] + (step - previous[0]) * SESSION_STEP
        elif following is not None:
            work.sort_value = following[1] - (following[0] - step) * SESSION_STEP
        else:
            continue
        work.placed_by = PLACEMENT_SESSION


def _mark_duplicates(works: Sequence[_Work]) -> None:
    """Among done, non-excluded pages sharing a number, the latest capture wins."""
    groups: dict[tuple[bool, int], list[_Work]] = defaultdict(list)
    for work in works:
        if work.page.status == DONE and not work.page.excluded and work.number is not None:
            groups[(work.number.front_matter, work.number.value)].append(work)
    for group in groups.values():
        winner = max(group, key=lambda w: w.page.capture_key)
        for work in group:
            if work is not winner:
                work.duplicate_of = winner.page.id


def compute_layout(pages: Sequence[PageInput]) -> Layout:
    """Number, deduplicate, place and order the pages of one document."""
    works = [_Work(page) for page in pages]
    for work in works:
        work.number, work.source = _own_number(work.page)

    sessions: dict[str, list[_Work]] = defaultdict(list)
    for work in works:
        if work.page.session_id:
            sessions[work.page.session_id].append(work)
    for members in sessions.values():
        _infer_session(members)

    _mark_duplicates(works)

    included = [w for w in works if w.included]
    for work in included:
        if work.page.position is not None:
            work.sort_value, work.placed_by = work.page.position, PLACEMENT_MANUAL
        elif work.number is not None:
            work.sort_value, work.placed_by = work.number.natural, PLACEMENT_NUMBER
    for members in sessions.values():
        _anchor_session(members)

    # Unplaced pages keep their capture order (that of the whole document when
    # no page has a place: letters, forms...). A page without session is a
    # session of its own.
    session_start: dict[str, float] = {}
    for work in works:
        session = work.page.session_id or work.page.id
        session_start[session] = min(session_start.get(session, work.page.captured_ts), work.page.captured_ts)
    unplaced = sorted(
        (w for w in included if w.sort_value is None),
        key=lambda w: (
            session_start[w.page.session_id or w.page.id],
            w.page.session_id or w.page.id,
            w.page.seq or 0,
            w.page.captured_ts,
            w.page.id,
        ),
    )
    for work in unplaced:
        work.placed_by = PLACEMENT_UNPLACED
    placed = sorted(
        (w for w in included if w.sort_value is not None),
        key=lambda w: (w.sort_value, w.page.captured_ts, w.page.id),
    )
    reading = placed + unplaced

    def by_capture(items: Iterable[_Work]) -> list[_Work]:
        return sorted(items, key=lambda w: w.page.capture_key)

    pending = by_capture(w for w in works if not w.page.excluded and w.page.status != DONE)
    excluded = by_capture(w for w in works if w.page.excluded)
    duplicates = by_capture(w for w in works if w.duplicate_of is not None)
    ordered = reading + pending + excluded + duplicates

    reading_ids = {w.page.id for w in reading}
    placements = {
        work.page.id: Placement(
            number=work.number,
            source=work.source,
            duplicate_of=work.duplicate_of,
            in_document=work.page.id in reading_ids,
            placed_by=work.placed_by,
            sort_value=work.sort_value,
            rank=rank,
        )
        for rank, work in enumerate(ordered)
    }
    numbered = [w for w in included if w.number is not None]
    arabic: set[int] = set()
    for work in numbered:
        assert work.number is not None
        if not work.number.front_matter:
            arabic.update(range(work.number.value, work.number.last + 1))
    return Layout(
        placements=placements,
        order=tuple(w.page.id for w in ordered),
        reading_order=tuple(w.page.id for w in reading),
        numbered=bool(numbered),
        coverage=Coverage(ranges=_to_ranges(arabic), unnumbered=len(included) - len(numbered)),
    )


def _kept_pages(naturals: Sequence[int | None], positioned: Sequence[bool]) -> list[int]:
    """Indices of a longest strictly increasing subsequence of `naturals` (None: never kept).

    Among the longest ones, one keeping the most pages without a position.
    O(n log n): a Fenwick tree gives the best subsequence ending below each value.
    """
    ranks = {value: rank for rank, value in enumerate(sorted({n for n in naturals if n is not None}), start=1)}
    # Score of a subsequence: length × weight + number of pages without position
    # (that number is < weight): the length counts first.
    weight = len(naturals) + 1
    tree = [(0, -1)] * (len(ranks) + 1)  # (score, index of its last page) per node
    previous: dict[int, int] = {}
    best = (0, -1)
    for index, natural in enumerate(naturals):
        if natural is None:
            continue
        rank = ranks[natural]
        below, node = (0, -1), rank - 1
        while node > 0:
            below = max(below, tree[node])
            node -= node & -node
        previous[index] = below[1]
        entry = (below[0] + weight + (0 if positioned[index] else 1), index)
        best = max(best, entry)
        node = rank
        while node < len(tree):
            tree[node] = max(tree[node], entry)
            node += node & -node
    kept: list[int] = []
    index = best[1]
    while index >= 0:
        kept.append(index)
        index = previous[index]
    return kept[::-1]


def order_positions(naturals: Sequence[int | None], positioned: Sequence[bool]) -> list[float | None]:
    """Positions that put pages in a chosen order, as few of them as possible.

    `naturals[i]` is the place of the i-th page of the chosen order on the
    number line (`PageNumber.natural`, None without number), `positioned[i]`
    whether it has a position now. The pages of a longest strictly increasing
    subsequence of natural places stay where their numbers put them (None;
    preferably pages without position), so that pages scanned later still
    slot in by number. Every other page gets a position between its kept
    neighbors a and b: a + (b − a) × k / (m + 1) for the k-th of m pages,
    b − m … b − 1 before the first kept page, a + 1, a + 2… after the last;
    1…N if no page has a number.
    """
    count = len(naturals)
    kept = _kept_pages(naturals, positioned)
    if not kept:
        return [float(index + 1) for index in range(count)]

    def place(index: int) -> float:
        natural = naturals[index]
        assert natural is not None  # kept pages have a number
        return float(natural)

    positions: list[float | None] = [None] * count
    first, last = kept[0], kept[-1]
    for index in range(first):
        positions[index] = place(first) - (first - index)
    for left, right in pairwise(kept):
        low, high, run = place(left), place(right), right - left - 1
        for k in range(1, run + 1):
            positions[left + k] = low + (high - low) * k / (run + 1)
    for index in range(last + 1, count):
        positions[index] = place(last) + (index - last)
    return positions


def _longest_increasing(values: Sequence[int]) -> list[int]:
    """Indices of a longest strictly increasing subsequence of `values` (patience sorting)."""
    tails: list[int] = []  # per length, the smallest last value of such a subsequence...
    ends: list[int] = []  # ...and its index
    previous = [-1] * len(values)
    for index, value in enumerate(values):
        length = bisect_left(tails, value)
        if length == len(tails):
            tails.append(value)
            ends.append(index)
        else:
            tails[length], ends[length] = value, index
        previous[index] = ends[length - 1] if length else -1
    chosen: list[int] = []
    index = ends[-1] if ends else -1
    while index >= 0:
        chosen.append(index)
        index = previous[index]
    return chosen[::-1]


def _spread(low: float | None, high: float | None, count: int) -> list[float]:
    """`count` increasing places strictly between `low` and `high` (None: no bound).

    Evenly spaced between two bounds; with one bound, the integers just below
    `high` or just above `low`; 1…count without any.
    """
    if low is not None and high is not None:
        return [low + (high - low) * k / (count + 1) for k in range(1, count + 1)]
    if high is not None:
        top = math.ceil(high) - 1
        return [float(top - count + k) for k in range(1, count + 1)]
    start = math.floor(low) if low is not None else 0
    return [float(start + k) for k in range(1, count + 1)]


class _OrderSearch:
    """Trial layouts for `positions_for_order`: which pages can stay without position."""

    def __init__(self, pages: Sequence[PageInput], wanted: tuple[str, ...], base: dict[str, float | None]) -> None:
        self._pages = pages
        self._wanted = wanted
        #: `order_positions` for every page of `wanted`: None for the numbered pages it keeps.
        self._base = base
        #: Candidates held at their automatic place (set by `hold`) while they have a position.
        self._held: dict[str, float] = {}
        self._budget = REORDER_BUDGET

    @property
    def exhausted(self) -> bool:
        return self._budget <= 0

    def layout(self, positions: dict[str, float | None]) -> Layout:
        """Layout of the pages when the pages of `wanted` have these positions."""
        self._budget -= len(self._pages)
        return compute_layout(
            [
                page
                if (position := positions.get(page.id, page.position)) == page.position
                else dataclasses.replace(page, position=position)
                for page in self._pages
            ]
        )

    def gives_wanted(self, positions: dict[str, float | None]) -> bool:
        return self.layout(positions).reading_order == self._wanted

    def in_order(self, loose: Sequence[str], reference: Layout) -> list[str]:
        """The largest group of `loose` pages whose places in `reference` follow the wanted order.

        Their places increase along the wanted order, with those of the
        numbered pages that `base` keeps; unplaced pages can only end the
        order, in their own order (nothing placed can follow them); two of
        them at the same place leave no room for pages moved between them.
        """
        placements = reference.placements
        loose_set = set(loose)
        tail: list[str] = []
        for page_id in reversed(self._wanted):
            placement = placements[page_id]
            if (
                page_id not in loose_set
                or placement.sort_value is not None
                or (tail and placement.rank > placements[tail[-1]].rank)
            ):
                break
            tail.append(page_id)
        chosen = set(tail)
        # Between two numbered pages that keep their place, the longest run of
        # loose pages placed between them, in increasing order.
        gap: list[str] = []
        low = -1
        for wanted_id in (*self._wanted[: len(self._wanted) - len(tail)], None):
            if wanted_id is None or self._base[wanted_id] is None:
                high = len(placements) if wanted_id is None else placements[wanted_id].rank
                inside = [gap_id for gap_id in gap if low < placements[gap_id].rank < high]
                increasing = _longest_increasing([placements[gap_id].rank for gap_id in inside])
                chosen.update(inside[index] for index in increasing)
                gap, low = [], high
            elif wanted_id in loose_set and placements[wanted_id].sort_value is not None:
                gap.append(wanted_id)
        while tie := self._tie(chosen, placements):
            chosen.discard(tie)
        return [page_id for page_id in self._wanted if page_id in chosen]

    def _tie(self, chosen: Set[str], placements: dict[str, Placement]) -> str | None:
        """A page of `chosen` at the same place as the previous page staying in place, with pages between."""
        previous: str | None = None
        between = False
        for page_id in self._wanted:
            value = placements[page_id].sort_value
            if value is None or (page_id not in chosen and self._base[page_id] is not None):
                between = True
                continue
            if between and previous is not None and value == placements[previous].sort_value:
                return page_id if page_id in chosen else previous
            previous, between = page_id, False
        return None

    def hold(self, candidates: Iterable[str], reference: Layout) -> None:
        """Hold the placed `candidates`, while they have a position, at their place in `reference`.

        A page placed by its session next to a held page lands where it would
        anyway: freeing pages does not move the others.
        """
        self._held = {
            page_id: value for page_id in candidates if (value := reference.placements[page_id].sort_value) is not None
        }

    def fit(self, free: Set[str], layout: Layout | None = None) -> dict[str, float | None] | None:
        """Positions leaving the pages of `free` without position, if they give the wanted order.

        The held pages keep their place; the other pages keep their `base`
        position, except a run of them that does not fall between the places
        of its neighbors: it is spread between those (`_spread`). `layout`:
        the one of these positions before any spreading, if already known.
        """
        trial = {
            page_id: None if page_id in free else self._held.get(page_id, position)
            for page_id, position in self._base.items()
        }
        if layout is None:
            layout = self.layout(trial)
        positions = dict(trial)
        run: list[str] = []
        low: float | None = None
        for page_id in (*self._wanted, None):
            if page_id is not None and trial[page_id] is not None and page_id not in self._held:
                run.append(page_id)
                continue
            high = None if page_id is None else layout.placements[page_id].sort_value
            if run:
                first, last = trial[run[0]], trial[run[-1]]
                assert first is not None and last is not None
                if (low is not None and first <= low) or (high is not None and last >= high):
                    positions.update(zip(run, _spread(low, high, len(run)), strict=True))
            run, low = [], high
        if positions != trial:
            layout = self.layout(positions)
        return positions if layout.reading_order == self._wanted else None

    def by_halves(
        self,
        group: list[str],
        kept: frozenset[str],
        found: dict[str, float | None],
        *,
        tried: bool = False,
    ) -> tuple[frozenset[str], dict[str, float | None]]:
        """Leave the pages of `group` without position where the wanted order allows it.

        The whole group at once (unless `tried` already), else each half in
        the wanted order, down to single pages. `kept`: the pages already left
        without position, `found` the positions that go with them.
        """
        if not tried and not self.exhausted:
            positions = self.fit(kept | set(group))
            if positions is not None:
                return kept | set(group), positions
        if len(group) < 2 or self.exhausted:
            return kept, found
        middle = len(group) // 2
        kept, found = self.by_halves(group[:middle], kept, found)
        return self.by_halves(group[middle:], kept, found)

    def drop_needless(self, pages: Sequence[str], found: dict[str, float | None]) -> dict[str, float | None]:
        """Clear the position of each of `pages` that the wanted order does not need, until none is left."""
        changed = True
        while changed and not self.exhausted:
            changed = False
            for page_id in pages:
                if found[page_id] is not None and not self.exhausted:
                    trial = {**found, page_id: None}
                    if self.gives_wanted(trial):
                        found, changed = trial, True
        return found


def positions_for_order(pages: Sequence[PageInput], wanted: Sequence[str]) -> dict[str, float | None]:
    """Positions that put the pages of the reading order in the order `wanted` (their ids).

    Returns the position of every page of `wanted` (None: no position), so
    that only the pages that moved get one:

    * numbered pages: `order_positions`, a longest increasing subsequence of
      their natural places keeps them (pages without position first);
    * pages with neither number nor position ("loose"): their automatic
      places are the ones they get when they all stay without position and
      the other pages have their `order_positions` position. The largest
      group of them whose places already follow `wanted` (between the kept
      numbered pages; unplaced ones only at the end, in their order) are the
      candidates to stay without position: all at once if that gives
      `wanted`; else, held at their place by a position meanwhile, by halves
      in the order of `wanted`, down to single pages; finally a candidate
      that still has a position loses it if the order stays `wanted` without
      it. The other loose pages moved: they get a position, as every page
      that had one;
    * a run of pages with a position keeps the `order_positions` positions if
      they fall between the places of its neighbors, else it is spread
      between those places (`_spread`).

    Each trial is a real layout (`compute_layout`), within REORDER_BUDGET,
    and so is the final check: the result always gives `wanted`. Sending the
    current order again changes nothing. ValueError if `wanted` is not the
    reading order of `pages`.
    """
    layout = compute_layout(pages)
    wanted = tuple(wanted)
    if len(set(wanted)) != len(wanted) or set(wanted) != set(layout.reading_order):
        raise ValueError("not the pages of the reading order")
    by_id = {page.id: page for page in pages}
    if wanted == layout.reading_order:
        return {page_id: by_id[page_id].position for page_id in wanted}
    numbers = [layout.placements[page_id].number for page_id in wanted]
    base = dict(
        zip(
            wanted,
            order_positions(
                [number.natural if number is not None else None for number in numbers],
                [by_id[page_id].position is not None for page_id in wanted],
            ),
            strict=True,
        )
    )
    loose = [
        page_id
        for page_id, number in zip(wanted, numbers, strict=True)
        if number is None and by_id[page_id].position is None
    ]
    search = _OrderSearch(pages, wanted, base)
    reference = search.layout({**base, **dict.fromkeys(loose)})
    candidates = search.in_order(loose, reference)
    found = search.fit(set(candidates), reference if len(candidates) == len(loose) else None)
    if found is None:
        search.hold(candidates, reference)
        start = search.fit(set())
        _, found = search.by_halves(candidates, frozenset(), base if start is None else start, tried=True)
    found = search.drop_needless(candidates, found)
    if not search.gives_wanted(found):
        raise RuntimeError("the positions found do not give the wanted order")
    return found
