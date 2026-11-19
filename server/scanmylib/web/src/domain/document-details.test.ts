import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { samplePage } from './document-details.test-support.ts';
import {
  canOrganize,
  groupPages,
  hasPagesPlacedByHand,
  hasPagesPositionedByHand,
  hasPlacedPages,
  isTextPending,
  type PageGroup,
  type PageGroupKind,
  type PageSummary,
  pageGroupOf,
  waitingPageCount,
} from './document-details.ts';
import { sampleDocument } from './document-summary.test-support.ts';

const PLACED = samplePage('placed');
const UNPLACED = samplePage('unplaced', { placement: 'unplaced', pageLabel: null, numberSource: null });
const PENDING = samplePage('pending', { status: 'queued', isInDocument: false, placement: null });
const EXCLUDED = samplePage('excluded', { isExcluded: true, isInDocument: false, placement: null });
const DUPLICATE = samplePage('duplicate', { duplicateOf: 'placed', isInDocument: false, placement: null });

describe('The document details', () => {
  describe('The pageGroupOf() function', () => {
    const rows: { situation: string; page: PageSummary; expectedKind: PageGroupKind }[] = [
      { situation: 'a page placed in the reading order', page: PLACED, expectedKind: 'placed' },
      { situation: 'a page of the document that nothing places', page: UNPLACED, expectedKind: 'unplaced' },
      { situation: 'a page waiting for its text', page: PENDING, expectedKind: 'pending' },
      { situation: 'an excluded page', page: EXCLUDED, expectedKind: 'excluded' },
      { situation: 'a duplicate', page: DUPLICATE, expectedKind: 'duplicate' },
      {
        situation: 'an excluded duplicate',
        page: samplePage('both', { isExcluded: true, duplicateOf: 'placed', isInDocument: false }),
        expectedKind: 'excluded',
      },
    ];

    for (const { situation, page, expectedKind } of rows) {
      describe(`When given ${situation}`, () => {
        let kind: PageGroupKind;
        beforeEach(() => {
          kind = pageGroupOf(page);
        });

        it(`should put it in the group "${expectedKind}"`, () => {
          assert.equal(kind, expectedKind);
        });
      });
    }
  });

  describe('The groupPages() function', () => {
    describe('When the pages come in the order of the api', () => {
      let groups: PageGroup[];
      beforeEach(() => {
        groups = groupPages([PLACED, samplePage('placed-2'), UNPLACED, PENDING, EXCLUDED, DUPLICATE]);
      });

      it('should group consecutive pages of one kind, in that order', () => {
        assert.deepEqual(
          groups.map((group) => ({ key: group.key, pages: group.pages.map((page) => page.id) })),
          [
            { key: 'placed', pages: ['placed', 'placed-2'] },
            { key: 'unplaced', pages: ['unplaced'] },
            { key: 'pending', pages: ['pending'] },
            { key: 'excluded', pages: ['excluded'] },
            { key: 'duplicate', pages: ['duplicate'] },
          ],
        );
      });
    });

    describe('When a kind comes back after another', () => {
      let groups: PageGroup[];
      beforeEach(() => {
        groups = groupPages([PENDING, EXCLUDED, samplePage('pending-2', { status: 'error', isInDocument: false })]);
      });

      it('should give it a group of its own, under a key of its own', () => {
        assert.deepEqual(
          groups.map((group) => group.key),
          ['pending', 'excluded', 'pending-1'],
        );
      });
    });

    describe('When the document has no page', () => {
      let groups: PageGroup[];
      beforeEach(() => {
        groups = groupPages([]);
      });

      it('should give no group', () => {
        assert.deepEqual(groups, []);
      });
    });
  });

  describe('The hasPlacedPages() function', () => {
    describe('When only unplaced pages are in the document', () => {
      let hasPlaced: boolean;
      beforeEach(() => {
        hasPlaced = hasPlacedPages(groupPages([UNPLACED, PENDING]));
      });

      it('should say no, so that the unplaced pages are not marked as pages to place', () => {
        assert.equal(hasPlaced, false);
      });
    });

    describe('When a page is placed', () => {
      let hasPlaced: boolean;
      beforeEach(() => {
        hasPlaced = hasPlacedPages(groupPages([PLACED, UNPLACED]));
      });

      it('should say yes', () => {
        assert.equal(hasPlaced, true);
      });
    });
  });

  describe('The hasPagesPlacedByHand() function', () => {
    describe('When a page of the document was moved by hand', () => {
      let isPlacedByHand: boolean;
      beforeEach(() => {
        isPlacedByHand = hasPagesPlacedByHand([PLACED, samplePage('moved', { placement: 'manual' })]);
      });

      it('should say yes', () => {
        assert.equal(isPlacedByHand, true);
      });
    });

    describe('When every page keeps the place of its number', () => {
      let isPlacedByHand: boolean;
      beforeEach(() => {
        isPlacedByHand = hasPagesPlacedByHand([PLACED, UNPLACED]);
      });

      it('should say no', () => {
        assert.equal(isPlacedByHand, false);
      });
    });
  });

  describe('The hasPagesPositionedByHand() function', () => {
    describe('When a page outside the reading order keeps a place chosen by hand', () => {
      let isPositioned: boolean;
      beforeEach(() => {
        isPositioned = hasPagesPositionedByHand([PLACED, samplePage('excluded', { ...EXCLUDED, position: 2.5 })]);
      });

      it('should say yes, since restoring the automatic order would still forget that place', () => {
        assert.equal(isPositioned, true);
      });
    });

    describe('When every page has its automatic place', () => {
      let isPositioned: boolean;
      beforeEach(() => {
        isPositioned = hasPagesPositionedByHand([PLACED, UNPLACED, EXCLUDED]);
      });

      it('should say no', () => {
        assert.equal(isPositioned, false);
      });
    });
  });

  describe('The canOrganize() function', () => {
    describe('When two pages are in the document', () => {
      let isOrganizable: boolean;
      beforeEach(() => {
        isOrganizable = canOrganize([PLACED, UNPLACED, PENDING]);
      });

      it('should say yes', () => {
        assert.equal(isOrganizable, true);
      });
    });

    describe('When only one page is in the document', () => {
      let isOrganizable: boolean;
      beforeEach(() => {
        isOrganizable = canOrganize([PLACED, PENDING, EXCLUDED, DUPLICATE]);
      });

      it('should say no, since one page has no order to change', () => {
        assert.equal(isOrganizable, false);
      });
    });
  });

  describe('The isTextPending() function', () => {
    const rows: { situation: string; queuedCount: number; processingCount: number; expected: boolean }[] = [
      { situation: 'pages are queued', queuedCount: 2, processingCount: 0, expected: true },
      { situation: 'a page is being read', queuedCount: 0, processingCount: 1, expected: true },
      { situation: 'every text is read', queuedCount: 0, processingCount: 0, expected: false },
    ];

    for (const { situation, queuedCount, processingCount, expected } of rows) {
      describe(`When ${situation}`, () => {
        let isPending: boolean;
        beforeEach(() => {
          isPending = isTextPending(sampleDocument({ stats: { queuedCount, processingCount } }).stats);
        });

        it(`should say ${expected ? 'yes' : 'no'}`, () => {
          assert.equal(isPending, expected);
        });
      });
    }
  });

  describe('The waitingPageCount() function', () => {
    describe('When pages are queued and one is being read', () => {
      const queuedCount = 2;
      const processingCount = 1;
      let count: number;
      beforeEach(() => {
        count = waitingPageCount(sampleDocument({ stats: { queuedCount, processingCount } }).stats);
      });

      it('should count both', () => {
        assert.equal(count, queuedCount + processingCount);
      });
    });
  });
});
