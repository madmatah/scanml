import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { type OutlineEntry, pageAtLine, type ReadingPart, readingOutline } from '../../src/domain/reading.ts';

interface Page {
  readonly id: string;
  readonly page_label: string | null;
}

// Parts of GET /api/documents/{id}/html, and the API's pages by key.
const PARTS: readonly ReadingPart[] = [
  { type: 'page', key: 'k-i', marker: 'Page i' },
  { type: 'page', key: 'k-1', marker: 'Page 1' },
  { type: 'page', key: 'k-plate', marker: 'Unnumbered page' },
  { type: 'page', key: 'k-2', marker: 'Page 2' },
  { type: 'gap', text: 'Pages not scanned yet: 3–5' },
  { type: 'page', key: 'k-6', marker: 'Page 6–7' },
  { type: 'heading', text: 'Unnumbered pages' },
  { type: 'page', key: 'k-notes', marker: 'Unnumbered page' },
];
const PAGES_BY_KEY = new Map<string, Page>([
  ['k-i', { id: 'i', page_label: 'i' }],
  ['k-1', { id: '1', page_label: '1' }],
  ['k-plate', { id: 'plate', page_label: null }],
  ['k-2', { id: '2', page_label: '2' }],
  ['k-6', { id: '6', page_label: '6–7' }],
  ['k-notes', { id: 'notes', page_label: null }],
]);

function summarize(outline: readonly OutlineEntry<Page>[]): (string | number)[][] {
  return outline.map((entry) => (entry.type === 'page' ? [entry.index, entry.key] : [entry.type, entry.label]));
}

describe('The reading', () => {
  describe('The readingOutline() function', () => {
    describe('When the document has numbered pages, missing pages and unnumbered ones', () => {
      let outline: OutlineEntry<Page>[];
      beforeEach(() => {
        outline = readingOutline(PARTS, PAGES_BY_KEY);
      });

      it('should list the pages in reading order, with the missing pages and the unnumbered ones', () => {
        assert.deepEqual(summarize(outline), [
          [0, 'k-i'],
          [1, 'k-1'],
          [2, 'k-plate'],
          [3, 'k-2'],
          ['gap', 'Pages not scanned yet: 3–5'],
          [4, 'k-6'],
          ['group', 'Unnumbered pages'],
          [5, 'k-notes'],
        ]);
      });

      it('should give each page entry its page', () => {
        assert.deepEqual(
          outline.flatMap((entry) => (entry.type === 'page' ? [[entry.key, entry.page?.id]] : [])),
          [
            ['k-i', 'i'],
            ['k-1', '1'],
            ['k-plate', 'plate'],
            ['k-2', '2'],
            ['k-6', '6'],
            ['k-notes', 'notes'],
          ],
        );
      });
    });

    describe('When the document data lacks the pages of the HTML, having changed meanwhile', () => {
      const firstThreeParts = PARTS.slice(0, 3);
      const noPagesByKey = new Map<string, Page>();
      let outline: OutlineEntry<Page>[];
      beforeEach(() => {
        outline = readingOutline(firstThreeParts, noPagesByKey);
      });

      it('should give the page entries no page', () => {
        assert.deepEqual(
          outline.map((entry) => (entry.type === 'page' ? entry.page : undefined)),
          [null, null, null],
        );
      });
    });

    describe('When the document has nothing to read', () => {
      const noParts: ReadingPart[] = [];
      let outline: OutlineEntry<Page>[];
      beforeEach(() => {
        outline = readingOutline(noParts, PAGES_BY_KEY);
      });

      it('should be empty', () => {
        assert.deepEqual(outline, []);
      });
    });
  });

  describe('The pageAtLine() function', () => {
    describe('When pages of different heights are laid out from above the screen', () => {
      const pageTopsPixels = [-2000, 120, 900, 930, 2400];
      const lines = [
        {
          situation: 'When the reading line is above the top of the second page',
          linePixels: 100,
          rule: 'should be the first page, whose top has scrolled past the line',
          expectedPageIndex: 0,
        },
        {
          situation: 'When the reading line is one pixel above the top of the second page',
          linePixels: 119,
          rule: 'should still be the first page',
          expectedPageIndex: 0,
        },
        {
          situation: 'When the reading line is at the top of the second page',
          linePixels: 120,
          rule: 'should be the second page, whose top has reached the line',
          expectedPageIndex: 1,
        },
        {
          situation: 'When the reading line is one pixel above the top of the third page',
          linePixels: 899,
          rule: 'should still be the second page',
          expectedPageIndex: 1,
        },
        {
          situation: 'When the reading line is within the short third page',
          linePixels: 915,
          rule: 'should be the third page',
          expectedPageIndex: 2,
        },
        {
          situation: 'When the reading line is at the top of the fourth page, right after the short one',
          linePixels: 930,
          rule: 'should be the fourth page',
          expectedPageIndex: 3,
        },
        {
          situation: 'When the reading line is far below the top of the last page',
          linePixels: 5000,
          rule: 'should be the last page',
          expectedPageIndex: 4,
        },
      ];

      for (const { situation, linePixels, rule, expectedPageIndex } of lines) {
        describe(situation, () => {
          let pageIndex: number;
          beforeEach(() => {
            pageIndex = pageAtLine(pageTopsPixels.length, (index) => pageTopsPixels[index] ?? Number.NaN, linePixels);
          });

          it(rule, () => {
            assert.equal(pageIndex, expectedPageIndex);
          });
        });
      }
    });

    describe('When the text has not reached the reading line yet', () => {
      const pageCount = 3;
      const firstTopPixels = 500;
      const pageHeightPixels = 800;
      const linePixels = 140;
      let pageIndex: number;
      beforeEach(() => {
        pageIndex = pageAtLine(pageCount, (index) => firstTopPixels + index * pageHeightPixels, linePixels);
      });

      it('should be the first page', () => {
        assert.equal(pageIndex, 0);
      });
    });

    describe('When the reader is in the middle of a long book', () => {
      const pageCount = 1000;
      const pageHeightPixels = 1000;
      const scrolledPixels = 400_000;
      const linePixels = 120;
      const maxTopReadCount = 11;
      let topReadCount: number;
      let pageIndex: number;
      beforeEach(() => {
        topReadCount = 0;
        pageIndex = pageAtLine(
          pageCount,
          (index) => {
            topReadCount += 1;
            return index * pageHeightPixels - scrolledPixels;
          },
          linePixels,
        );
      });

      it('should find the page at the reading line', () => {
        assert.equal(pageIndex, 400);
      });

      it('should read the tops of a few pages only, since it runs while the reader scrolls', () => {
        assert.ok(topReadCount <= maxTopReadCount, `${topReadCount} reads`);
      });
    });
  });
});
