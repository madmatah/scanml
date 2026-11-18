import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  type ReadingPosition,
  type ReadingView,
  readingPosition,
} from '../../../../src/adapters/react/reader/reading-position.ts';

interface ViewLayout {
  readonly pageTopsPixels: readonly number[];
  readonly pageHeightPixels?: number;
  readonly scrolledPixels?: number;
  readonly textHeightPixels?: number;
}

const READING_LINE_PIXELS = 120;
const VIEWPORT_HEIGHT_PIXELS = 900;

function viewOf({
  pageTopsPixels,
  pageHeightPixels = 600,
  scrolledPixels = 1000,
  textHeightPixels = 10000,
}: ViewLayout) {
  const view: ReadingView = {
    pageCount: pageTopsPixels.length,
    readingLinePixels: READING_LINE_PIXELS,
    viewportHeightPixels: VIEWPORT_HEIGHT_PIXELS,
    scrolledPixels,
    textHeightPixels,
    pageTopPixels: (pageIndex) => pageTopsPixels[pageIndex] ?? 0,
    pageBottomPixels: (pageIndex) => (pageTopsPixels[pageIndex] ?? 0) + pageHeightPixels,
  };
  return view;
}

describe('The reading position', () => {
  describe('The readingPosition() function', () => {
    describe('When no page is held, in the middle of the text', () => {
      let position: ReadingPosition | null;
      beforeEach(() => {
        position = readingPosition(viewOf({ pageTopsPixels: [-1100, -500, 100, 700] }), null);
      });

      it('should read the last page whose top has passed the line', () => {
        assert.deepEqual(position, { pageIndex: 2, heldPageIndex: null });
      });
    });

    describe('When the text is scrolled to its end', () => {
      let position: ReadingPosition | null;
      beforeEach(() => {
        position = readingPosition(
          viewOf({ pageTopsPixels: [-1100, -500, 100, 700], scrolledPixels: 9100, textHeightPixels: 10000 }),
          null,
        );
      });

      it('should read the last page, which may be too short to reach the line', () => {
        assert.deepEqual(position, { pageIndex: 3, heldPageIndex: null });
      });
    });

    describe('When the text is short enough to show whole, at the top', () => {
      let position: ReadingPosition | null;
      beforeEach(() => {
        position = readingPosition(
          viewOf({ pageTopsPixels: [200, 400], scrolledPixels: 0, textHeightPixels: VIEWPORT_HEIGHT_PIXELS }),
          null,
        );
      });

      it('should read the first page, the top of the text not being its end', () => {
        assert.deepEqual(position, { pageIndex: 0, heldPageIndex: null });
      });
    });

    describe('When a page jumped to is still on the screen, below the line', () => {
      let position: ReadingPosition | null;
      beforeEach(() => {
        position = readingPosition(
          viewOf({ pageTopsPixels: [-1100, -500, 100, 700], scrolledPixels: 9100, textHeightPixels: 10000 }),
          2,
        );
      });

      it('should keep reading it, even at the end of the text', () => {
        assert.deepEqual(position, { pageIndex: 2, heldPageIndex: 2 });
      });
    });

    describe('When the page jumped to has left the screen', () => {
      let position: ReadingPosition | null;
      beforeEach(() => {
        position = readingPosition(viewOf({ pageTopsPixels: [-1100, -500, 100, 700] }), 0);
      });

      it('should let it go and read the page at the line', () => {
        assert.deepEqual(position, { pageIndex: 2, heldPageIndex: null });
      });
    });

    describe('When the text holds no page', () => {
      let position: ReadingPosition | null;
      beforeEach(() => {
        position = readingPosition(viewOf({ pageTopsPixels: [] }), null);
      });

      it('should read none', () => {
        assert.equal(position, null);
      });
    });
  });
});
