import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

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

const PAGES = ['a', 'b', 'c', 'd', 'e', 'f'];

function layOutGrid(
  cardCount,
  { columnCount = 3, topPixels = 0, widthPixels = 100, heightPixels = 130, gapPixels = 10 } = {},
) {
  return Array.from({ length: cardCount }, (_, cardIndex) => {
    const left = (cardIndex % columnCount) * (widthPixels + gapPixels);
    const top = topPixels + Math.floor(cardIndex / columnCount) * (heightPixels + gapPixels);
    return { left, top, right: left + widthPixels, bottom: top + heightPixels };
  });
}

// The second grid stands for the organizer's group of unplaced pages.
const CARDS = [...layOutGrid(7), ...layOutGrid(2, { topPixels: 480 })];

describe('The reading order', () => {
  describe('The moveBlock() function', () => {
    describe('When one page moves forward', () => {
      const movingPages = ['b'];
      const indexOfPageE = 4;
      let order;
      beforeEach(() => {
        order = moveBlock(PAGES, movingPages, indexOfPageE);
      });

      it('should put it before the page at the index', () => {
        assert.deepEqual(order, ['a', 'c', 'd', 'b', 'e', 'f']);
      });
    });

    describe('When one page moves backward', () => {
      const movingPages = ['e'];
      const indexOfPageB = 1;
      let order;
      beforeEach(() => {
        order = moveBlock(PAGES, movingPages, indexOfPageB);
      });

      it('should put it before the page at the index', () => {
        assert.deepEqual(order, ['a', 'e', 'b', 'c', 'd', 'f']);
      });
    });

    describe('When one page moves to the end', () => {
      const movingPages = ['a'];
      const endIndex = PAGES.length;
      let order;
      beforeEach(() => {
        order = moveBlock(PAGES, movingPages, endIndex);
      });

      it('should put it last', () => {
        assert.deepEqual(order, ['b', 'c', 'd', 'e', 'f', 'a']);
      });
    });

    describe('When the pages were selected in click order', () => {
      const clickedPages = ['e', 'b'];
      const firstPosition = 0;
      let order;
      beforeEach(() => {
        order = moveBlock(PAGES, clickedPages, firstPosition);
      });

      it('should move them in reading order', () => {
        assert.deepEqual(order, ['b', 'e', 'a', 'c', 'd', 'f']);
      });
    });

    describe('When pages apart move together to the end', () => {
      const clickedPages = ['e', 'b'];
      const endIndex = PAGES.length;
      let order;
      beforeEach(() => {
        order = moveBlock(PAGES, clickedPages, endIndex);
      });

      it('should close them up at the end, in reading order', () => {
        assert.deepEqual(order, ['a', 'c', 'd', 'f', 'b', 'e']);
      });
    });

    describe('When pages apart move together into the middle', () => {
      const movingPages = ['a', 'f'];
      const indexOfPageD = 3;
      let order;
      beforeEach(() => {
        order = moveBlock(PAGES, movingPages, indexOfPageD);
      });

      it('should close them up before the page at the index', () => {
        assert.deepEqual(order, ['b', 'c', 'a', 'f', 'd', 'e']);
      });
    });

    describe('When a block of pages drops inside or next to itself', () => {
      const movingPages = ['b', 'c'];
      const drops = [
        { situation: 'When it drops before its first page', index: 1 },
        { situation: 'When it drops between its pages', index: 2 },
        { situation: 'When it drops right after its last page', index: 3 },
      ];

      for (const { situation, index } of drops) {
        describe(situation, () => {
          let order;
          beforeEach(() => {
            order = moveBlock(PAGES, movingPages, index);
          });

          it('should leave the order as it was', () => {
            assert.deepEqual(order, PAGES);
          });
        });
      }
    });

    describe('When no page moves', () => {
      const movingPages = [];
      const indexOfPageC = 2;
      let order;
      beforeEach(() => {
        order = moveBlock(PAGES, movingPages, indexOfPageC);
      });

      it('should leave the order as it was', () => {
        assert.deepEqual(order, PAGES);
      });
    });
  });

  describe('The moveNextTo() function', () => {
    describe('When pages move before a page', () => {
      const movingPages = ['e', 'f'];
      const targetPage = 'a';
      let order;
      beforeEach(() => {
        order = moveNextTo(PAGES, movingPages, targetPage, 'before');
      });

      it('should put them just before it', () => {
        assert.deepEqual(order, ['e', 'f', 'a', 'b', 'c', 'd']);
      });
    });

    describe('When a page moves after a page', () => {
      const movingPages = ['a'];
      const targetPage = 'c';
      let order;
      beforeEach(() => {
        order = moveNextTo(PAGES, movingPages, targetPage, 'after');
      });

      it('should put it just after it', () => {
        assert.deepEqual(order, ['b', 'c', 'a', 'd', 'e', 'f']);
      });
    });

    describe('When a page moves after the last page', () => {
      const movingPages = ['a'];
      const lastPage = 'f';
      let order;
      beforeEach(() => {
        order = moveNextTo(PAGES, movingPages, lastPage, 'after');
      });

      it('should put it last', () => {
        assert.deepEqual(order, ['b', 'c', 'd', 'e', 'f', 'a']);
      });
    });

    describe('When the target page is unknown', () => {
      const movingPages = ['a'];
      const unknownPage = 'unknown';
      let givenOrder;
      let order;
      beforeEach(() => {
        givenOrder = [...PAGES];
        order = moveNextTo(givenOrder, movingPages, unknownPage, 'after');
      });

      it('should leave the order as it was', () => {
        assert.deepEqual(order, PAGES);
      });

      it('should return a new array, not the order it was given', () => {
        assert.notEqual(order, givenOrder);
      });

      it('should leave the order it was given unchanged', () => {
        assert.deepEqual(givenOrder, PAGES);
      });
    });
  });

  describe('The moveByOne() function', () => {
    const backwardStep = -1;
    const forwardStep = 1;

    describe('When a page moves one place backward', () => {
      const movingPage = 'c';
      let order;
      beforeEach(() => {
        order = moveByOne(PAGES, movingPage, backwardStep);
      });

      it('should swap it with the page before it', () => {
        assert.deepEqual(order, ['a', 'c', 'b', 'd', 'e', 'f']);
      });
    });

    describe('When a page moves one place forward', () => {
      const movingPage = 'c';
      let order;
      beforeEach(() => {
        order = moveByOne(PAGES, movingPage, forwardStep);
      });

      it('should swap it with the page after it', () => {
        assert.deepEqual(order, ['a', 'b', 'd', 'c', 'e', 'f']);
      });
    });

    describe('When the first page moves backward', () => {
      const firstPage = 'a';
      let givenOrder;
      let order;
      beforeEach(() => {
        givenOrder = [...PAGES];
        order = moveByOne(givenOrder, firstPage, backwardStep);
      });

      it('should leave the order as it was, not moving the page beyond the start', () => {
        assert.deepEqual(order, PAGES);
      });

      it('should return a new array, not the order it was given', () => {
        assert.notEqual(order, givenOrder);
      });

      it('should leave the order it was given unchanged', () => {
        assert.deepEqual(givenOrder, PAGES);
      });
    });

    describe('When the last page moves forward', () => {
      const lastPage = 'f';
      let order;
      beforeEach(() => {
        order = moveByOne(PAGES, lastPage, forwardStep);
      });

      it('should leave the order as it was, not moving the page beyond the end', () => {
        assert.deepEqual(order, PAGES);
      });
    });

    describe('When the page is unknown', () => {
      const unknownPage = 'unknown';
      let order;
      beforeEach(() => {
        order = moveByOne(PAGES, unknownPage, forwardStep);
      });

      it('should leave the order as it was', () => {
        assert.deepEqual(order, PAGES);
      });
    });
  });

  describe('The rangeOf() function', () => {
    describe('When the anchor comes before the clicked page', () => {
      const anchorPage = 'b';
      const clickedPage = 'd';
      let range;
      beforeEach(() => {
        range = rangeOf(PAGES, anchorPage, clickedPage);
      });

      it('should hold the pages from the anchor to the clicked page, both included', () => {
        assert.deepEqual(range, ['b', 'c', 'd']);
      });
    });

    describe('When the anchor comes after the clicked page', () => {
      const anchorPage = 'e';
      const clickedPage = 'c';
      let range;
      beforeEach(() => {
        range = rangeOf(PAGES, anchorPage, clickedPage);
      });

      it('should hold the pages between them in reading order, both included', () => {
        assert.deepEqual(range, ['c', 'd', 'e']);
      });
    });

    describe('When the anchor is the clicked page', () => {
      const clickedPage = 'c';
      let range;
      beforeEach(() => {
        range = rangeOf(PAGES, clickedPage, clickedPage);
      });

      it('should hold that page alone', () => {
        assert.deepEqual(range, ['c']);
      });
    });

    describe('When there is no anchor', () => {
      const noAnchor = null;
      const clickedPage = 'd';
      let range;
      beforeEach(() => {
        range = rangeOf(PAGES, noAnchor, clickedPage);
      });

      it('should hold the clicked page alone', () => {
        assert.deepEqual(range, ['d']);
      });
    });

    describe('When the anchor is no longer in the order', () => {
      const goneAnchor = 'gone';
      const clickedPage = 'd';
      let range;
      beforeEach(() => {
        range = rangeOf(PAGES, goneAnchor, clickedPage);
      });

      it('should hold the clicked page alone', () => {
        assert.deepEqual(range, ['d']);
      });
    });

    describe('When the clicked page is not in the order', () => {
      const anchorPage = 'b';
      const goneClickedPage = 'gone';
      let range;
      beforeEach(() => {
        range = rangeOf(PAGES, anchorPage, goneClickedPage);
      });

      it('should be empty', () => {
        assert.deepEqual(range, []);
      });
    });
  });

  describe('The spanOf() function', () => {
    describe('When the selection has holes', () => {
      const selectedPages = ['e', 'b'];
      let span;
      beforeEach(() => {
        span = spanOf(PAGES, selectedPages);
      });

      it('should fill them, from its first page to its last in reading order', () => {
        assert.deepEqual(span, ['b', 'c', 'd', 'e']);
      });
    });

    describe('When the selection is one page', () => {
      const selectedPages = ['c'];
      let span;
      beforeEach(() => {
        span = spanOf(PAGES, selectedPages);
      });

      it('should be that page', () => {
        assert.deepEqual(span, ['c']);
      });
    });

    describe('When no selected page is in the order', () => {
      const selectedPages = ['gone'];
      let span;
      beforeEach(() => {
        span = spanOf(PAGES, selectedPages);
      });

      it('should be empty', () => {
        assert.deepEqual(span, []);
      });
    });
  });

  describe('The inOrder() function', () => {
    describe('When the selection holds pages out of reading order and an unknown id', () => {
      const selectedIds = new Set(['f', 'a', 'gone']);
      let selectedPages;
      beforeEach(() => {
        selectedPages = inOrder(PAGES, selectedIds);
      });

      it('should give the known pages in reading order, the unknown id dropped', () => {
        assert.deepEqual(selectedPages, ['a', 'f']);
      });
    });
  });

  describe('The sameOrder() function', () => {
    describe('When both orders hold the same pages in the same order', () => {
      const firstOrder = ['a', 'b'];
      const secondOrder = ['a', 'b'];
      let isSameOrder;
      beforeEach(() => {
        isSameOrder = sameOrder(firstOrder, secondOrder);
      });

      it('should be true', () => {
        assert.equal(isSameOrder, true);
      });
    });

    describe('When both orders hold the same pages in another order', () => {
      const firstOrder = ['a', 'b'];
      const secondOrder = ['b', 'a'];
      let isSameOrder;
      beforeEach(() => {
        isSameOrder = sameOrder(firstOrder, secondOrder);
      });

      it('should be false', () => {
        assert.equal(isSameOrder, false);
      });
    });

    describe('When one order holds more pages than the other', () => {
      const shorterOrder = ['a'];
      const longerOrder = ['a', 'b'];
      let isSameOrder;
      beforeEach(() => {
        isSameOrder = sameOrder(shorterOrder, longerOrder);
      });

      it('should be false', () => {
        assert.equal(isSameOrder, false);
      });
    });
  });

  describe('The gridRows() function', () => {
    describe('When the cards lie in two grids, one under the other', () => {
      let rows;
      beforeEach(() => {
        rows = gridRows(CARDS);
      });

      it('should group the cards whose tops are level into rows', () => {
        assert.deepEqual(
          rows.map(({ first, last }) => [first, last]),
          [
            [0, 2],
            [3, 5],
            [6, 6],
            [7, 8],
          ],
        );
      });
    });

    describe('When there is no card', () => {
      const noCards = [];
      let rows;
      beforeEach(() => {
        rows = gridRows(noCards);
      });

      it('should have no row', () => {
        assert.deepEqual(rows, []);
      });
    });
  });

  describe('The dropTarget() function', () => {
    const drops = [
      {
        situation: 'When the pointer is over the left half of a card',
        pointerPixels: { x: 20, y: 60 },
        rule: 'should drop before that card',
        expectedTarget: { index: 0, card: 0, side: 'before' },
      },
      {
        situation: 'When the pointer is over the right half of the first card of a row',
        pointerPixels: { x: 80, y: 60 },
        rule: 'should drop before the next card of the row',
        expectedTarget: { index: 1, card: 1, side: 'before' },
      },
      {
        situation: 'When the pointer is over the right half of the middle card of a lower row',
        pointerPixels: { x: 170, y: 200 },
        rule: 'should drop before the next card of that row',
        expectedTarget: { index: 5, card: 5, side: 'before' },
      },
      {
        situation: 'When the pointer is over the right half of the last card of a row',
        pointerPixels: { x: 290, y: 60 },
        rule: 'should drop after that card, not before the next row',
        expectedTarget: { index: 3, card: 2, side: 'after' },
      },
      {
        situation: 'When the pointer is past the end of a row',
        pointerPixels: { x: 900, y: 60 },
        rule: 'should drop after the last card of the row, not before the next row',
        expectedTarget: { index: 3, card: 2, side: 'after' },
      },
      {
        situation: 'When the pointer is past the only card of a row',
        pointerPixels: { x: 200, y: 300 },
        rule: 'should drop after that card, not before the next row',
        expectedTarget: { index: 7, card: 6, side: 'after' },
      },
      {
        situation: 'When the pointer is in the gap between two rows, closer to the upper one',
        pointerPixels: { x: 20, y: 134 },
        rule: 'should drop in the upper row',
        expectedTarget: { index: 0, card: 0, side: 'before' },
      },
      {
        situation: 'When the pointer is in the gap between two rows, closer to the lower one',
        pointerPixels: { x: 20, y: 137 },
        rule: 'should drop in the lower row',
        expectedTarget: { index: 3, card: 3, side: 'before' },
      },
      {
        situation: 'When the pointer is between two grids, closer to the upper one',
        pointerPixels: { x: 20, y: 440 },
        rule: 'should drop in the last row of the upper grid',
        expectedTarget: { index: 6, card: 6, side: 'before' },
      },
      {
        situation: 'When the pointer is over the heading of the lower grid',
        pointerPixels: { x: 20, y: 460 },
        rule: 'should drop in the first row of the lower grid, the nearest',
        expectedTarget: { index: 7, card: 7, side: 'before' },
      },
      {
        situation: 'When the pointer is above the cards',
        pointerPixels: { x: 20, y: -50 },
        rule: 'should drop in the first row, the nearest',
        expectedTarget: { index: 0, card: 0, side: 'before' },
      },
      {
        situation: 'When the pointer is below and right of the cards',
        pointerPixels: { x: 500, y: 2000 },
        rule: 'should drop after the last card, in the nearest row',
        expectedTarget: { index: 9, card: 8, side: 'after' },
      },
    ];

    for (const { situation, pointerPixels, rule, expectedTarget } of drops) {
      describe(situation, () => {
        let target;
        beforeEach(() => {
          target = dropTarget(CARDS, pointerPixels.x, pointerPixels.y);
        });

        it(rule, () => {
          assert.deepEqual(target, expectedTarget);
        });
      });
    }

    describe('When there is no card', () => {
      const noCards = [];
      const pointerPixels = { x: 0, y: 0 };
      let target;
      beforeEach(() => {
        target = dropTarget(noCards, pointerPixels.x, pointerPixels.y);
      });

      it('should give no target', () => {
        assert.equal(target, null);
      });
    });
  });

  describe('The columnGap() function', () => {
    describe('When a row has two cards', () => {
      let gapPixels;
      beforeEach(() => {
        gapPixels = columnGap(CARDS);
      });

      it('should be the space between them', () => {
        assert.equal(gapPixels, 10);
      });
    });

    describe('When no row has two cards', () => {
      const cardsInOneColumn = layOutGrid(3, { columnCount: 1 });
      const fallbackPixels = 16;
      let gapPixels;
      beforeEach(() => {
        gapPixels = columnGap(cardsInOneColumn, fallbackPixels);
      });

      it('should be the fallback', () => {
        assert.equal(gapPixels, fallbackPixels);
      });
    });
  });

  describe('The insertionMark() function', () => {
    const gapPixels = 10;
    const marks = [
      {
        situation: 'When the target is before a card that follows another on its row',
        target: { index: 1, card: 1, side: 'before' },
        rule: 'should stand in the middle of the gap between them, as high as the card',
        expectedMark: { x: 105, top: 0, bottom: 130 },
      },
      {
        situation: 'When the target is before the first card of a row',
        target: { index: 3, card: 3, side: 'before' },
        rule: 'should stand half a gap before the card, as high as the card',
        expectedMark: { x: -5, top: 140, bottom: 270 },
      },
      {
        situation: 'When the target is after the last card of a row',
        target: { index: 3, card: 2, side: 'after' },
        rule: 'should stand half a gap after the card, as high as the card',
        expectedMark: { x: 325, top: 0, bottom: 130 },
      },
      {
        situation: 'When the target is after the only card of a row',
        target: { index: 7, card: 6, side: 'after' },
        rule: 'should stand half a gap after the card, as high as the card',
        expectedMark: { x: 105, top: 280, bottom: 410 },
      },
      {
        situation: 'When the target is after a card that another follows on its row',
        target: { index: 8, card: 7, side: 'after' },
        rule: 'should stand in the middle of the gap between them, as high as the card',
        expectedMark: { x: 105, top: 480, bottom: 610 },
      },
    ];

    for (const { situation, target, rule, expectedMark } of marks) {
      describe(situation, () => {
        let mark;
        beforeEach(() => {
          mark = insertionMark(CARDS, target, gapPixels);
        });

        it(rule, () => {
          assert.deepEqual(mark, expectedMark);
        });
      });
    }
  });

  describe('The autoScrollStep() function', () => {
    const coveredTopPixels = 100;
    const viewportBottomPixels = 900;
    const zonePixels = 50;
    const maxStepPixels = 20;
    const scrollZone = { zone: zonePixels, maxStep: maxStepPixels };

    const restingPointers = [
      { situation: 'When the pointer is away from the edges', pointerPixels: 500 },
      {
        situation: 'When the pointer is at the inner edge of the top zone',
        pointerPixels: coveredTopPixels + zonePixels,
      },
      {
        situation: 'When the pointer is at the inner edge of the bottom zone',
        pointerPixels: viewportBottomPixels - zonePixels,
      },
    ];

    for (const { situation, pointerPixels } of restingPointers) {
      describe(situation, () => {
        let pixelsPerFrame;
        beforeEach(() => {
          pixelsPerFrame = autoScrollStep(pointerPixels, coveredTopPixels, viewportBottomPixels, scrollZone);
        });

        it('should not scroll', () => {
          assert.equal(pixelsPerFrame, 0);
        });
      });
    }

    describe('When the pointer moves toward the covered top within the top zone', () => {
      const inZonePixels = 140;
      const closerToTheTopPixels = 110;
      let pixelsPerFrameInZone;
      let pixelsPerFrameCloserToTheTop;
      beforeEach(() => {
        pixelsPerFrameInZone = autoScrollStep(inZonePixels, coveredTopPixels, viewportBottomPixels, scrollZone);
        pixelsPerFrameCloserToTheTop = autoScrollStep(
          closerToTheTopPixels,
          coveredTopPixels,
          viewportBottomPixels,
          scrollZone,
        );
      });

      it('should scroll up', () => {
        assert.ok(pixelsPerFrameInZone < 0);
      });

      it('should scroll up faster closer to the top', () => {
        assert.ok(pixelsPerFrameCloserToTheTop < pixelsPerFrameInZone);
      });
    });

    describe('When the pointer moves toward the bottom within the bottom zone', () => {
      const inZonePixels = 860;
      const closerToTheBottomPixels = 890;
      let pixelsPerFrameInZone;
      let pixelsPerFrameCloserToTheBottom;
      beforeEach(() => {
        pixelsPerFrameInZone = autoScrollStep(inZonePixels, coveredTopPixels, viewportBottomPixels, scrollZone);
        pixelsPerFrameCloserToTheBottom = autoScrollStep(
          closerToTheBottomPixels,
          coveredTopPixels,
          viewportBottomPixels,
          scrollZone,
        );
      });

      it('should scroll down', () => {
        assert.ok(pixelsPerFrameInZone > 0);
      });

      it('should scroll down faster closer to the bottom', () => {
        assert.ok(pixelsPerFrameCloserToTheBottom > pixelsPerFrameInZone);
      });
    });

    const edgePointers = [
      {
        situation: 'When the pointer reaches the covered top',
        pointerPixels: coveredTopPixels,
        rule: 'should scroll up at the highest speed',
        expectedPixelsPerFrame: -maxStepPixels,
      },
      {
        situation: 'When the pointer is over what covers the top, such as the sticky header',
        pointerPixels: 20,
        rule: 'should scroll up at the highest speed, no faster',
        expectedPixelsPerFrame: -maxStepPixels,
      },
      {
        situation: 'When the pointer reaches the bottom',
        pointerPixels: viewportBottomPixels,
        rule: 'should scroll down at the highest speed',
        expectedPixelsPerFrame: maxStepPixels,
      },
      {
        situation: 'When the pointer is below the bottom',
        pointerPixels: 2000,
        rule: 'should scroll down at the highest speed, no faster',
        expectedPixelsPerFrame: maxStepPixels,
      },
    ];

    for (const { situation, pointerPixels, rule, expectedPixelsPerFrame } of edgePointers) {
      describe(situation, () => {
        let pixelsPerFrame;
        beforeEach(() => {
          pixelsPerFrame = autoScrollStep(pointerPixels, coveredTopPixels, viewportBottomPixels, scrollZone);
        });

        it(rule, () => {
          assert.equal(pixelsPerFrame, expectedPixelsPerFrame);
        });
      });
    }
  });
});
