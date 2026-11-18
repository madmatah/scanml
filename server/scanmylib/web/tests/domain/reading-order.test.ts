import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  inOrder,
  moveBlock,
  moveByOne,
  moveNextTo,
  type PageId,
  type Placement,
  placeSelection,
  type ReadingOrderGroups,
  rangeOf,
  readingOrderGroups,
  sameOrder,
  spanOf,
} from '../../src/domain/reading-order.ts';
import { samplePage } from './document-details-samples.ts';

const PAGES = ['a', 'b', 'c', 'd', 'e', 'f'];

describe('The reading order', () => {
  describe('The moveBlock() function', () => {
    describe('When one page moves forward', () => {
      const movingPages = ['b'];
      const indexOfPageE = 4;
      let order: PageId[];
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
      let order: PageId[];
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
      let order: PageId[];
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
      let order: PageId[];
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
      let order: PageId[];
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
      let order: PageId[];
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
          let order: PageId[];
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
      const movingPages: PageId[] = [];
      const indexOfPageC = 2;
      let order: PageId[];
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
      let order: PageId[];
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
      let order: PageId[];
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
      let order: PageId[];
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
      let givenOrder: PageId[];
      let order: PageId[];
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
      let order: PageId[];
      beforeEach(() => {
        order = moveByOne(PAGES, movingPage, backwardStep);
      });

      it('should swap it with the page before it', () => {
        assert.deepEqual(order, ['a', 'c', 'b', 'd', 'e', 'f']);
      });
    });

    describe('When a page moves one place forward', () => {
      const movingPage = 'c';
      let order: PageId[];
      beforeEach(() => {
        order = moveByOne(PAGES, movingPage, forwardStep);
      });

      it('should swap it with the page after it', () => {
        assert.deepEqual(order, ['a', 'b', 'd', 'c', 'e', 'f']);
      });
    });

    describe('When the first page moves backward', () => {
      const firstPage = 'a';
      let givenOrder: PageId[];
      let order: PageId[];
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
      let order: PageId[];
      beforeEach(() => {
        order = moveByOne(PAGES, lastPage, forwardStep);
      });

      it('should leave the order as it was, not moving the page beyond the end', () => {
        assert.deepEqual(order, PAGES);
      });
    });

    describe('When the page is unknown', () => {
      const unknownPage = 'unknown';
      let order: PageId[];
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
      let range: PageId[];
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
      let range: PageId[];
      beforeEach(() => {
        range = rangeOf(PAGES, anchorPage, clickedPage);
      });

      it('should hold the pages between them in reading order, both included', () => {
        assert.deepEqual(range, ['c', 'd', 'e']);
      });
    });

    describe('When the anchor is the clicked page', () => {
      const clickedPage = 'c';
      let range: PageId[];
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
      let range: PageId[];
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
      let range: PageId[];
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
      let range: PageId[];
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
      let span: PageId[];
      beforeEach(() => {
        span = spanOf(PAGES, selectedPages);
      });

      it('should fill them, from its first page to its last in reading order', () => {
        assert.deepEqual(span, ['b', 'c', 'd', 'e']);
      });
    });

    describe('When the selection is one page', () => {
      const selectedPages = ['c'];
      let span: PageId[];
      beforeEach(() => {
        span = spanOf(PAGES, selectedPages);
      });

      it('should be that page', () => {
        assert.deepEqual(span, ['c']);
      });
    });

    describe('When no selected page is in the order', () => {
      const selectedPages = ['gone'];
      let span: PageId[];
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
      let selectedPages: PageId[];
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
      let isSameOrder: boolean;
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
      let isSameOrder: boolean;
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
      let isSameOrder: boolean;
      beforeEach(() => {
        isSameOrder = sameOrder(shorterOrder, longerOrder);
      });

      it('should be false', () => {
        assert.equal(isSameOrder, false);
      });
    });
  });

  describe('The readingOrderGroups() function', () => {
    const rows: {
      situation: string;
      rule: string;
      placements: Record<string, string>;
      expected: ReadingOrderGroups;
    }[] = [
      {
        situation: 'the reading order ends with pages that nothing places',
        rule: 'should put only the pages at the end that nothing places in a group of their own',
        placements: { a: 'number', b: 'unplaced', c: 'number', d: 'unplaced', e: 'unplaced' },
        expected: { placed: ['a', 'b', 'c'], unplaced: ['d', 'e'], hasPlacedPages: true },
      },
      {
        situation: 'no page has a place',
        rule: 'should keep every page in one group, since the reading order is then the capture order',
        placements: { a: 'unplaced', b: 'unplaced' },
        expected: { placed: ['a', 'b'], unplaced: [], hasPlacedPages: false },
      },
    ];

    for (const { situation, rule, placements, expected } of rows) {
      describe(`When ${situation}`, () => {
        let groups: ReadingOrderGroups;
        beforeEach(() => {
          const order = Object.keys(placements);
          const pages = new Map(
            order.map((pageId) => [pageId, samplePage(pageId, { placement: placements[pageId] ?? null })]),
          );
          groups = readingOrderGroups(order, pages);
        });

        it(rule, () => {
          assert.deepEqual(groups, expected);
        });
      });
    }
  });

  describe('The placeSelection() function', () => {
    const order = ['a', 'b', 'c', 'd'];
    const rows: { situation: string; moving: string[]; targetId: string; expected: Placement }[] = [
      {
        situation: 'the pages go after a later page',
        moving: ['a', 'b'],
        targetId: 'c',
        expected: { kind: 'moved', order: ['c', 'a', 'b', 'd'], moved: ['a', 'b'] },
      },
      {
        situation: 'the pages are already there',
        moving: ['b'],
        targetId: 'a',
        expected: { kind: 'unchanged' },
      },
      {
        situation: 'the target page left the reading order while the dialog was open',
        moving: ['a'],
        targetId: 'x',
        expected: { kind: 'conflict' },
      },
      {
        situation: 'a moving page left the reading order while the dialog was open',
        moving: ['a', 'x'],
        targetId: 'c',
        expected: { kind: 'conflict' },
      },
    ];

    for (const { situation, moving, targetId, expected } of rows) {
      describe(`When ${situation}`, () => {
        let placement: Placement;
        beforeEach(() => {
          placement = placeSelection(order, moving, targetId, 'after');
        });

        it(`should give "${expected.kind}"`, () => {
          assert.deepEqual(placement, expected);
        });
      });
    }
  });
});
