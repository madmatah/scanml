import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { keepShownPages, NO_SELECTION, type Selection, selectPage, selectSpan } from '../../src/domain/selection.ts';

const ORDER = ['a', 'b', 'c', 'd', 'e', 'f'];
const PLAIN_CLICK = { isToggle: false, isRange: false };
const CTRL_CLICK = { isToggle: true, isRange: false };
const SHIFT_CLICK = { isToggle: false, isRange: true };
const CTRL_SHIFT_CLICK = { isToggle: true, isRange: true };

function selectionOf(pageIds: readonly string[], anchor: string | null): Selection {
  return { selected: new Set(pageIds), anchor };
}

function plainOf(selection: Selection): { selected: string[]; anchor: string | null } {
  return { selected: [...selection.selected].sort(), anchor: selection.anchor };
}

describe('The selection of the pages to organize', () => {
  describe('The selectPage() function', () => {
    describe('When a page is clicked', () => {
      let selection: Selection;
      beforeEach(() => {
        selection = selectPage(selectionOf(['a', 'b'], 'a'), ORDER, 'd', PLAIN_CLICK);
      });

      it('should select it alone, and start the next range from it', () => {
        assert.deepEqual(plainOf(selection), { selected: ['d'], anchor: 'd' });
      });
    });

    describe('When a page is clicked with Ctrl', () => {
      let selection: Selection;
      beforeEach(() => {
        selection = selectPage(selectionOf(['a'], 'a'), ORDER, 'd', CTRL_CLICK);
      });

      it('should add it to the selection, and start the next range from it', () => {
        assert.deepEqual(plainOf(selection), { selected: ['a', 'd'], anchor: 'd' });
      });
    });

    describe('When a selected page is clicked with Ctrl', () => {
      let selection: Selection;
      beforeEach(() => {
        selection = selectPage(selectionOf(['a', 'd'], 'a'), ORDER, 'd', CTRL_CLICK);
      });

      it('should remove it from the selection', () => {
        assert.deepEqual(plainOf(selection), { selected: ['a'], anchor: 'd' });
      });
    });

    describe('When a page is clicked with Shift', () => {
      let selection: Selection;
      beforeEach(() => {
        selection = selectPage(selectionOf(['a', 'f'], 'e'), ORDER, 'c', SHIFT_CLICK);
      });

      it('should select the range from the anchor to it, alone, and keep the anchor', () => {
        assert.deepEqual(plainOf(selection), { selected: ['c', 'd', 'e'], anchor: 'e' });
      });
    });

    describe('When a page is clicked with Ctrl and Shift', () => {
      let selection: Selection;
      beforeEach(() => {
        selection = selectPage(selectionOf(['a'], 'c'), ORDER, 'd', CTRL_SHIFT_CLICK);
      });

      it('should add the range to the selection', () => {
        assert.deepEqual(plainOf(selection), { selected: ['a', 'c', 'd'], anchor: 'c' });
      });
    });

    describe('When a page is clicked with Shift before any page was clicked', () => {
      let selection: Selection;
      beforeEach(() => {
        selection = selectPage(NO_SELECTION, ORDER, 'c', SHIFT_CLICK);
      });

      it('should select it alone, as a plain click does', () => {
        assert.deepEqual(plainOf(selection), { selected: ['c'], anchor: 'c' });
      });
    });
  });

  describe('The selectSpan() function', () => {
    describe('When the selected pages are scattered', () => {
      let selection: Selection;
      beforeEach(() => {
        selection = selectSpan(selectionOf(['e', 'b'], 'e'), ORDER);
      });

      it('should select every page from the first to the last, and keep the anchor', () => {
        assert.deepEqual(plainOf(selection), { selected: ['b', 'c', 'd', 'e'], anchor: 'e' });
      });
    });
  });

  describe('The keepShownPages() function', () => {
    describe('When pages left the reading order', () => {
      let selection: Selection;
      beforeEach(() => {
        selection = keepShownPages(selectionOf(['a', 'x', 'c'], 'c'), ORDER);
      });

      it('should drop them from the selection, and keep the anchor that stays', () => {
        assert.deepEqual(plainOf(selection), { selected: ['a', 'c'], anchor: 'c' });
      });
    });

    describe('When the anchor left the reading order', () => {
      let selection: Selection;
      beforeEach(() => {
        selection = keepShownPages(selectionOf(['a'], 'x'), ORDER);
      });

      it('should drop it, so that no range starts from a page that is gone', () => {
        assert.equal(selection.anchor, null);
      });
    });
  });
});
