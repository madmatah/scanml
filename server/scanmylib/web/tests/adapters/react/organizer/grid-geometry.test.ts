import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  autoScrollStep,
  columnGap,
  type DropTarget,
  dropTarget,
  type GridRow,
  gridRows,
  type InsertionMark,
  insertionMark,
  type PixelRectangle,
} from '../../../../src/adapters/react/organizer/grid-geometry.ts';

type GridLayout = {
  readonly columnCount?: number;
  readonly topPixels?: number;
  readonly widthPixels?: number;
  readonly heightPixels?: number;
  readonly gapPixels?: number;
};

function layOutGrid(
  cardCount: number,
  { columnCount = 3, topPixels = 0, widthPixels = 100, heightPixels = 130, gapPixels = 10 }: GridLayout = {},
): PixelRectangle[] {
  return Array.from({ length: cardCount }, (_, cardIndex) => {
    const left = (cardIndex % columnCount) * (widthPixels + gapPixels);
    const top = topPixels + Math.floor(cardIndex / columnCount) * (heightPixels + gapPixels);
    return { left, top, right: left + widthPixels, bottom: top + heightPixels };
  });
}

// The second grid stands for the organizer's group of unplaced pages.
const CARDS = [...layOutGrid(7), ...layOutGrid(2, { topPixels: 480 })];

describe('The grid of the organizer', () => {
  describe('The gridRows() function', () => {
    describe('When the cards lie in two grids, one under the other', () => {
      let rows: GridRow[];
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
      const noCards: PixelRectangle[] = [];
      let rows: GridRow[];
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
        let target: DropTarget | null;
        beforeEach(() => {
          target = dropTarget(CARDS, pointerPixels);
        });

        it(rule, () => {
          assert.deepEqual(target, expectedTarget);
        });
      });
    }

    describe('When there is no card', () => {
      const noCards: PixelRectangle[] = [];
      const pointerPixels = { x: 0, y: 0 };
      let target: DropTarget | null;
      beforeEach(() => {
        target = dropTarget(noCards, pointerPixels);
      });

      it('should give no target', () => {
        assert.equal(target, null);
      });
    });
  });

  describe('The columnGap() function', () => {
    describe('When a row has two cards', () => {
      let gapPixels: number;
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
      let gapPixels: number;
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
    const marks: readonly { situation: string; target: DropTarget; rule: string; expectedMark: InsertionMark }[] = [
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
        let mark: InsertionMark;
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
    const scrollZone = { zonePixels, maxStepPixels };

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
        let pixelsPerFrame: number;
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
      let pixelsPerFrameInZone: number;
      let pixelsPerFrameCloserToTheTop: number;
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
      let pixelsPerFrameInZone: number;
      let pixelsPerFrameCloserToTheBottom: number;
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
        let pixelsPerFrame: number;
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
