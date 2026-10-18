/**
 * Unit tests of static/js/lib/order.js, with Node's built-in test runner (no
 * dependency to install). From the repository root:
 *
 *   docker run --rm --network none --read-only --user 1000:1000 \
 *     -v "$PWD/server/scanmylib/web:/web:ro" node:22-bookworm-slim node --test '/web/tests/*.test.js'
 */
import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
  autoScrollStep,
  columnGap,
  dropTarget,
  gridRows,
  inOrder,
  insertionMark,
  moveBlock,
  moveByOne,
  moveNextTo,
  rangeOf,
  sameOrder,
  spanOf,
} from '../static/js/lib/order.js';

const ORDER = ['a', 'b', 'c', 'd', 'e', 'f'];

describe('moving pages', () => {
  test('one page moves forward or backward', () => {
    assert.deepEqual(moveBlock(ORDER, ['b'], 4), ['a', 'c', 'd', 'b', 'e', 'f']);
    assert.deepEqual(moveBlock(ORDER, ['e'], 1), ['a', 'e', 'b', 'c', 'd', 'f']);
    assert.deepEqual(moveBlock(ORDER, ['a'], ORDER.length), ['b', 'c', 'd', 'e', 'f', 'a']);
  });

  test('pages moving together keep their relative order and close up', () => {
    // The selection is given in click order; it lands in reading order.
    assert.deepEqual(moveBlock(ORDER, ['e', 'b'], 0), ['b', 'e', 'a', 'c', 'd', 'f']);
    assert.deepEqual(moveBlock(ORDER, ['e', 'b'], ORDER.length), ['a', 'c', 'd', 'f', 'b', 'e']);
    assert.deepEqual(moveBlock(ORDER, ['a', 'f'], 3), ['b', 'c', 'a', 'f', 'd', 'e']);
  });

  test('a drop inside or next to the moving block changes nothing', () => {
    for (const index of [1, 2, 3]) assert.ok(sameOrder(moveBlock(ORDER, ['b', 'c'], index), ORDER));
    assert.equal(moveBlock(ORDER, [], 2).join(''), ORDER.join(''));
  });

  test('before or after a page', () => {
    assert.deepEqual(moveNextTo(ORDER, ['e', 'f'], 'a', 'before'), ['e', 'f', 'a', 'b', 'c', 'd']);
    assert.deepEqual(moveNextTo(ORDER, ['a'], 'c', 'after'), ['b', 'c', 'a', 'd', 'e', 'f']);
    assert.deepEqual(moveNextTo(ORDER, ['a'], 'f', 'after'), ['b', 'c', 'd', 'e', 'f', 'a']);
    assert.deepEqual(moveNextTo(ORDER, ['a'], 'unknown', 'after'), ORDER);
  });

  test('one place at a time, not beyond the ends', () => {
    assert.deepEqual(moveByOne(ORDER, 'c', -1), ['a', 'c', 'b', 'd', 'e', 'f']);
    assert.deepEqual(moveByOne(ORDER, 'c', 1), ['a', 'b', 'd', 'c', 'e', 'f']);
    assert.deepEqual(moveByOne(ORDER, 'a', -1), ORDER);
    assert.deepEqual(moveByOne(ORDER, 'f', 1), ORDER);
    assert.deepEqual(moveByOne(ORDER, 'unknown', 1), ORDER);
  });

  test('results are new arrays', () => {
    const order = ORDER.slice();
    assert.notEqual(moveByOne(order, 'a', -1), order);
    assert.notEqual(moveNextTo(order, ['a'], 'unknown', 'after'), order);
    assert.deepEqual(order, ORDER);
  });
});

describe('selections', () => {
  test('ranges go both ways and include both ends', () => {
    assert.deepEqual(rangeOf(ORDER, 'b', 'd'), ['b', 'c', 'd']);
    assert.deepEqual(rangeOf(ORDER, 'e', 'c'), ['c', 'd', 'e']);
    assert.deepEqual(rangeOf(ORDER, 'c', 'c'), ['c']);
  });

  test('a range without a known anchor is the clicked page alone', () => {
    assert.deepEqual(rangeOf(ORDER, null, 'd'), ['d']);
    assert.deepEqual(rangeOf(ORDER, 'gone', 'd'), ['d']);
    assert.deepEqual(rangeOf(ORDER, 'b', 'gone'), []);
  });

  test('the span of a selection fills its holes', () => {
    assert.deepEqual(spanOf(ORDER, ['e', 'b']), ['b', 'c', 'd', 'e']);
    assert.deepEqual(spanOf(ORDER, ['c']), ['c']);
    assert.deepEqual(spanOf(ORDER, ['gone']), []);
  });

  test('selected ids in reading order, unknown ids dropped', () => {
    assert.deepEqual(inOrder(ORDER, new Set(['f', 'a', 'gone'])), ['a', 'f']);
    assert.ok(sameOrder(['a', 'b'], ['a', 'b']));
    assert.ok(!sameOrder(['a', 'b'], ['b', 'a']));
    assert.ok(!sameOrder(['a'], ['a', 'b']));
  });
});

/**
 * A grid of 100×130 cards, 3 per row with a gap of 10, then (as in the
 * organizer's group of unplaced pages) a second grid 60 px lower.
 */
function grid(count, { columns = 3, top = 0, width = 100, height = 130, gap = 10 } = {}) {
  return Array.from({ length: count }, (_, index) => {
    const left = (index % columns) * (width + gap);
    const rowTop = top + Math.floor(index / columns) * (height + gap);
    return { left, top: rowTop, right: left + width, bottom: rowTop + height };
  });
}

const RECTS = [...grid(7), ...grid(2, { top: 480 })]; // rows at 0, 140, 280 (one card), 480

describe('drop target in a grid', () => {
  test('rows follow the tops of the cards', () => {
    assert.deepEqual(
      gridRows(RECTS).map(({ first, last }) => [first, last]),
      [
        [0, 2],
        [3, 5],
        [6, 6],
        [7, 8],
      ],
    );
    assert.deepEqual(gridRows([]), []);
  });

  test('before the card under the left half, after it under the right half', () => {
    assert.deepEqual(dropTarget(RECTS, 20, 60), { index: 0, card: 0, side: 'before' });
    assert.deepEqual(dropTarget(RECTS, 80, 60), { index: 1, card: 1, side: 'before' });
    assert.deepEqual(dropTarget(RECTS, 170, 200), { index: 5, card: 5, side: 'before' });
  });

  test('past the last card of a row: after it, not before the next row', () => {
    assert.deepEqual(dropTarget(RECTS, 290, 60), { index: 3, card: 2, side: 'after' });
    assert.deepEqual(dropTarget(RECTS, 900, 60), { index: 3, card: 2, side: 'after' });
    assert.deepEqual(dropTarget(RECTS, 200, 300), { index: 7, card: 6, side: 'after' });
  });

  test('between rows or groups, outside the grid: the nearest row', () => {
    assert.deepEqual(dropTarget(RECTS, 20, 134), { index: 0, card: 0, side: 'before' }); // gap, closer to row 1
    assert.deepEqual(dropTarget(RECTS, 20, 137), { index: 3, card: 3, side: 'before' }); // gap, closer to row 2
    assert.deepEqual(dropTarget(RECTS, 20, 440), { index: 6, card: 6, side: 'before' }); // closer to row 3
    assert.deepEqual(dropTarget(RECTS, 20, 460), { index: 7, card: 7, side: 'before' }); // heading of group 2
    assert.deepEqual(dropTarget(RECTS, 20, -50), { index: 0, card: 0, side: 'before' });
    assert.deepEqual(dropTarget(RECTS, 500, 2000), { index: 9, card: 8, side: 'after' });
    assert.equal(dropTarget([], 0, 0), null);
  });

  test('insertion mark in the gap between cards, or beside the end of a row', () => {
    assert.equal(columnGap(RECTS), 10);
    assert.equal(columnGap(grid(3, { columns: 1 }), 12), 12);
    assert.deepEqual(insertionMark(RECTS, { index: 1, card: 1, side: 'before' }, 10), { x: 105, top: 0, bottom: 130 });
    assert.deepEqual(insertionMark(RECTS, { index: 3, card: 3, side: 'before' }, 10), { x: -5, top: 140, bottom: 270 });
    assert.deepEqual(insertionMark(RECTS, { index: 3, card: 2, side: 'after' }, 10), { x: 325, top: 0, bottom: 130 });
    assert.deepEqual(insertionMark(RECTS, { index: 7, card: 6, side: 'after' }, 10), { x: 105, top: 280, bottom: 410 });
    assert.deepEqual(insertionMark(RECTS, { index: 8, card: 7, side: 'after' }, 10), { x: 105, top: 480, bottom: 610 });
  });
});

describe('auto-scroll', () => {
  const step = (y) => autoScrollStep(y, 100, 900, { zone: 50, maxStep: 20 });

  test('nothing away from the edges', () => {
    assert.equal(step(500), 0);
    assert.equal(step(150), 0);
    assert.equal(step(850), 0);
  });

  test('up under the covered top, down near the bottom, faster closer to the edge', () => {
    assert.ok(step(140) < 0 && step(110) < step(140));
    assert.equal(step(100), -20);
    assert.equal(step(20), -20); // over the sticky header
    assert.ok(step(860) > 0 && step(890) > step(860));
    assert.equal(step(900), 20);
    assert.equal(step(2000), 20);
  });
});
