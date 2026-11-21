import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { sampleDocument } from './document-summary.test-support.ts';
import {
  countPages,
  type DocumentKind,
  formatPageRanges,
  NEW_DOCUMENT_KIND,
  unwarpsByDefault,
} from './document-summary.ts';

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

  describe('The NEW_DOCUMENT_KIND constant', () => {
    it('should be a book, so that a new document starts as one', () => {
      assert.equal(NEW_DOCUMENT_KIND, 'book');
    });
  });

  describe('The unwarpsByDefault() function', () => {
    const rows: { kind: DocumentKind; rule: string; isUnwarped: boolean }[] = [
      {
        kind: 'book',
        rule: 'should flatten the pages of a book, since a book is photographed open, its pages curved near the binding',
        isUnwarped: true,
      },
      {
        kind: 'document',
        rule: 'should leave the pages of a document as they are, since a document lies flat',
        isUnwarped: false,
      },
    ];

    for (const { kind, rule, isUnwarped } of rows) {
      describe(`When the document is a ${kind}`, () => {
        let unwarps: boolean;
        beforeEach(() => {
          unwarps = unwarpsByDefault(kind);
        });

        it(rule, () => {
          assert.equal(unwarps, isUnwarped);
        });
      });
    }
  });
});
