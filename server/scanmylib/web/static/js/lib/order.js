/**
 * Editing a reading order (pure functions, no DOM): moving pages, ranges of
 * selected pages, and where a page dragged over a grid of cards would land.
 *
 * An order is an array of page ids. Pages that move together keep their
 * relative order. Rectangles are `{ left, top, right, bottom }` in one
 * coordinate space, listed in the order of the cards.
 */

/** Two cards whose tops differ by less than this are on the same grid row, in px. */
const ROW_TOLERANCE = 2;

export function sameOrder(a, b) {
  return a.length === b.length && a.every((id, index) => id === b[index]);
}

/** The ids of `ids` that are in `order`, in the order of `order`. */
export function inOrder(order, ids) {
  const wanted = new Set(ids);
  return order.filter((id) => wanted.has(id));
}

/**
 * `order` with the `moving` pages taken out and put back together, in their
 * current relative order, where the item at `index` of `order` was
 * (`index` = `order.length`: at the end).
 */
export function moveBlock(order, moving, index) {
  const movingSet = new Set(moving);
  const stays = (id) => !movingSet.has(id);
  return [
    ...order.slice(0, index).filter(stays),
    ...order.filter((id) => movingSet.has(id)),
    ...order.slice(index).filter(stays),
  ];
}

/** Moves the `moving` pages just before or just after the page `targetId` ('before' | 'after'). */
export function moveNextTo(order, moving, targetId, side) {
  const index = order.indexOf(targetId);
  if (index < 0) return order.slice();
  return moveBlock(order, moving, side === 'after' ? index + 1 : index);
}

/** Moves one page one place toward the start (`step` = -1) or the end (`step` = 1). */
export function moveByOne(order, id, step) {
  const index = order.indexOf(id);
  const neighbor = order[index + step];
  if (index < 0 || neighbor === undefined) return order.slice();
  return moveNextTo(order, [id], neighbor, step < 0 ? 'before' : 'after');
}

/** The pages from `fromId` to `toId`, both included, in the order of `order` (either direction). */
export function rangeOf(order, fromId, toId) {
  const from = order.indexOf(fromId);
  const to = order.indexOf(toId);
  if (to < 0) return [];
  if (from < 0) return [toId];
  return order.slice(Math.min(from, to), Math.max(from, to) + 1);
}

/** All the pages between the first and the last of `ids`, both included. */
export function spanOf(order, ids) {
  const positions = inOrder(order, ids).map((id) => order.indexOf(id));
  if (!positions.length) return [];
  return order.slice(positions[0], positions.at(-1) + 1);
}

/** True when the card `next` follows the card `previous` on the same grid row. */
function followsOnRow(previous, next) {
  return Math.abs(previous.top - next.top) <= ROW_TOLERANCE && next.left > previous.left;
}

/** Rows of a grid of cards: `{ first, last, top, bottom }` (indices into `rects`). */
export function gridRows(rects) {
  const rows = [];
  rects.forEach((rect, index) => {
    const row = rows.at(-1);
    if (row && followsOnRow(rects[index - 1], rect)) {
      row.last = index;
      row.bottom = Math.max(row.bottom, rect.bottom);
    } else {
      rows.push({ first: index, last: index, top: rect.top, bottom: rect.bottom });
    }
  });
  return rows;
}

/**
 * Where a card dragged to (x, y) would be inserted: `index` in the list
 * (0 … rects.length), and the card the insertion mark is drawn against,
 * `card` with `side` 'before' or 'after'. Uses the row under the pointer,
 * else the nearest row; within it, the first card whose middle is right of
 * the pointer. Null without cards.
 */
export function dropTarget(rects, x, y) {
  let row = null;
  let rowDistance = Infinity;
  for (const candidate of gridRows(rects)) {
    const distance = Math.max(candidate.top - y, y - candidate.bottom, 0);
    if (distance < rowDistance) {
      row = candidate;
      rowDistance = distance;
    }
  }
  if (!row) return null;
  for (let index = row.first; index <= row.last; index += 1) {
    if (x < (rects[index].left + rects[index].right) / 2) return { index, card: index, side: 'before' };
  }
  return { index: row.last + 1, card: row.last, side: 'after' };
}

/** Horizontal space between two cards of a row (`fallback` when no row has two cards). */
export function columnGap(rects, fallback = 12) {
  for (let index = 1; index < rects.length; index += 1) {
    if (followsOnRow(rects[index - 1], rects[index])) return rects[index].left - rects[index - 1].right;
  }
  return fallback;
}

/**
 * Insertion mark of a drop target: a vertical bar at `x`, from `top` to
 * `bottom`, centered in the gap next to the target card.
 */
export function insertionMark(rects, target, gap) {
  const card = rects[target.card];
  let x;
  if (target.side === 'before') {
    const previous = rects[target.card - 1];
    x = previous && followsOnRow(previous, card) ? (previous.right + card.left) / 2 : card.left - gap / 2;
  } else {
    const next = rects[target.card + 1];
    x = next && followsOnRow(card, next) ? (card.right + next.left) / 2 : card.right + gap / 2;
  }
  return { x, top: card.top, bottom: card.bottom };
}

/**
 * Scrolling speed while dragging, in px per frame, for a pointer at `y`
 * (viewport coordinates): negative in the `zone` px under `top` (the bottom
 * of what covers the top of the viewport), positive in the `zone` px above
 * `bottom`, faster closer to the edge.
 */
export function autoScrollStep(y, top, bottom, { zone = 64, maxStep = 18 } = {}) {
  if (y < top + zone) return -Math.ceil(maxStep * Math.min(1, (top + zone - y) / zone));
  if (y > bottom - zone) return Math.ceil(maxStep * Math.min(1, (y - (bottom - zone)) / zone));
  return 0;
}
