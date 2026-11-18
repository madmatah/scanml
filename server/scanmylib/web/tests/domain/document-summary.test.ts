import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { countPages, doneRatio, formatPageRanges } from '../../src/domain/document-summary.ts';
import { sampleDocument } from './document-summary-samples.ts';

describe('The document summary', () => {
  describe('The countPages() function', () => {
    describe('When the library holds several documents', () => {
      const documents = [sampleDocument({ stats: { pageCount: 11 } }), sampleDocument({ stats: { pageCount: 6 } })];
      let pageCount: number;
      beforeEach(() => {
        pageCount = countPages(documents);
      });

      it('should add up the pages of every document', () => {
        assert.equal(pageCount, 17);
      });
    });
  });

  describe('The doneRatio() function', () => {
    describe('When some pages have their text', () => {
      const { stats } = sampleDocument({ stats: { pageCount: 4, doneCount: 1 } });
      let ratio: number;
      beforeEach(() => {
        ratio = doneRatio(stats);
      });

      it('should be the share of the pages whose text is ready', () => {
        assert.equal(ratio, 0.25);
      });
    });

    describe('When the document has no page', () => {
      const { stats } = sampleDocument({ stats: { pageCount: 0, doneCount: 0 } });
      let ratio: number;
      beforeEach(() => {
        ratio = doneRatio(stats);
      });

      it('should be zero, so that an empty document shows an empty meter', () => {
        assert.equal(ratio, 0);
      });
    });
  });

  describe('The formatPageRanges() function', () => {
    describe('When the ranges hold a single page and a span', () => {
      const ranges = [
        [12, 12],
        [13, 44],
      ] as const;
      let text: string;
      beforeEach(() => {
        text = formatPageRanges(ranges);
      });

      it('should write the page alone, the span with an en dash, and separate them with commas', () => {
        assert.equal(text, '12, 13–44');
      });
    });
  });
});
