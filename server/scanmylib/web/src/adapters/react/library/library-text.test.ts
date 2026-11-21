// French is written only in the French catalog, so these tests compare with its entries instead of quoting it.
import assert from 'node:assert/strict';
import { before, beforeEach, describe, it } from 'node:test';

import type { TFunction } from 'i18next';
import frenchCatalog from '../../../../locales/fr.json' with { type: 'json' };
import { type DocumentChanges, sampleDocument } from '../../../domain/document-summary.test-support.ts';
import { createNumberFormatting } from '../../../domain/formatting.ts';
import { CATALOGS } from '../../i18next/catalogs.ts';
import { createLocalizationFor } from '../../i18next/localization.test-support.ts';
import {
  bylineText,
  coverageSummaryText,
  librarySummaryText,
  type StatusChip,
  statusChips,
  type TextStatus,
  textStatus,
} from './library-text.ts';

const ENGLISH_NUMBERS = createNumberFormatting('en-US');

describe('The library text', () => {
  let englishT: TFunction;
  before(async () => {
    englishT = (await createLocalizationFor(['en-US'], CATALOGS)).i18next.t;
  });

  describe('The statusChips() function', () => {
    describe('When every page of a book has its text', () => {
      let chips: StatusChip[];
      beforeEach(() => {
        chips = statusChips(englishT, sampleDocument());
      });

      it('should show only its kind', () => {
        assert.deepEqual(chips, [{ name: 'kind', text: 'Book', tone: 'neutral' }]);
      });
    });

    describe('When pages wait, are read, failed, are excluded or duplicated', () => {
      let chips: StatusChip[];
      beforeEach(() => {
        const stats = { processingCount: 1, queuedCount: 1200, errorCount: 2, excludedCount: 1, duplicateCount: 3 };
        chips = statusChips(englishT, sampleDocument({ kind: 'document', stats }));
      });

      it('should show a chip for each, in the tone of its state, the queue written as a plain number', () => {
        assert.deepEqual(chips, [
          { name: 'kind', text: 'Other', tone: 'neutral' },
          { name: 'processing', text: '1 being read', tone: 'info' },
          { name: 'queued', text: '1200 queued', tone: 'warn' },
          { name: 'error', text: '2 couldn’t be read', tone: 'danger' },
          { name: 'excluded', text: '1 excluded', tone: 'neutral' },
          { name: 'duplicates', text: '3 duplicates', tone: 'neutral' },
        ]);
      });
    });

    describe('When the UI is in French and one page is a duplicate', () => {
      let chips: StatusChip[];
      beforeEach(async () => {
        const { i18next } = await createLocalizationFor(['fr-FR'], CATALOGS);
        chips = statusChips(i18next.t, sampleDocument({ stats: { duplicateCount: 1 } }));
      });

      it('should take the singular form of the catalog', () => {
        assert.equal(
          chips.at(-1)?.text,
          frenchCatalog['{{count, number}} duplicate_one'].replace('{{count, number}}', '1'),
        );
      });
    });
  });

  describe('The bylineText() function', () => {
    const situations: { situation: string; changes: DocumentChanges; rule: string; expected: string }[] = [
      {
        situation: 'When the document has an author',
        changes: { author: 'Jane Doe' },
        rule: 'should name the author',
        expected: 'Jane Doe',
      },
      {
        situation: 'When the document has no author',
        changes: { author: '' },
        rule: 'should say so, so that the line keeps its place and the cards line up',
        expected: 'No author',
      },
    ];

    for (const { situation, changes, rule, expected } of situations) {
      describe(situation, () => {
        let byline: string;
        beforeEach(() => {
          byline = bylineText(englishT, sampleDocument(changes));
        });

        it(rule, () => {
          assert.equal(byline, expected);
        });
      });
    }
  });

  describe('The coverageSummaryText() function', () => {
    const situations: {
      situation: string;
      changes: DocumentChanges;
      rule: string;
      expected: string;
    }[] = [
      {
        situation: 'When the numbered pages leave gaps',
        changes: { coverage: {} },
        rule: 'should count the pages scanned between the lowest and the highest, with their share, in one line',
        expected: '9 of pages 11–21 scanned (82%)',
      },
      {
        situation: 'When a single page is missing from a long span',
        changes: {
          coverage: {
            ranges: [
              [1, 150],
              [152, 300],
            ],
            label: '1–150, 152–300',
            gaps: [[151, 151]],
            lowestNumber: 1,
            highestNumber: 300,
          },
        },
        rule: 'should keep the share below 100%, which only a span with no gap reads',
        expected: '299 of pages 1–300 scanned (99%)',
      },
      {
        situation: 'When only the first and the last page of a long span are scanned',
        changes: {
          coverage: {
            ranges: [
              [1, 1],
              [500, 500],
            ],
            label: '1, 500',
            gaps: [[2, 499]],
            lowestNumber: 1,
            highestNumber: 500,
          },
        },
        rule: 'should keep the share above 0%, since pages are scanned',
        expected: '2 of pages 1–500 scanned (1%)',
      },
      {
        situation: 'When the numbered pages leave no gap',
        changes: { coverage: { ranges: [[6, 44]], label: '6–44', gaps: [], lowestNumber: 6, highestNumber: 44 } },
        rule: 'should say that every page between the lowest and the highest is scanned',
        expected: 'Pages 6–44, all scanned',
      },
      {
        situation: 'When one numbered page is scanned',
        changes: { coverage: { ranges: [[12, 12]], label: '12', gaps: [], lowestNumber: 12, highestNumber: 12 } },
        rule: 'should name the page alone',
        expected: 'Page 12',
      },
      {
        situation: 'When no page is numbered',
        changes: {
          coverage: { ranges: [], label: '', gaps: [], lowestNumber: null, highestNumber: null, unnumberedCount: 2 },
        },
        rule: 'should count the unnumbered pages',
        expected: '2 unnumbered pages',
      },
      {
        situation: 'When the document has no page',
        changes: {
          coverage: { ranges: [], label: '', gaps: [], lowestNumber: null, highestNumber: null, unnumberedCount: 0 },
        },
        rule: 'should say that no page is numbered',
        expected: 'No numbered page',
      },
    ];

    for (const { situation, changes, rule, expected } of situations) {
      describe(situation, () => {
        let summary: string;
        beforeEach(() => {
          summary = coverageSummaryText(englishT, ENGLISH_NUMBERS, sampleDocument(changes).coverage);
        });

        it(rule, () => {
          assert.equal(summary, expected);
        });
      });
    }
  });

  describe('The textStatus() function', () => {
    const situations: { situation: string; changes: DocumentChanges; rule: string; expected: TextStatus }[] = [
      {
        situation: 'When every page has its text',
        changes: { stats: { pageCount: 11, doneCount: 11 } },
        rule: 'should say that the text is ready, in the tone of a page done',
        expected: { text: 'Text ready', tone: 'ok' },
      },
      {
        situation: 'When some pages have their text',
        changes: { stats: { pageCount: 30, doneCount: 12 } },
        rule: 'should count the pages whose text is ready, without saying they are being read, which a stopped engine would belie',
        expected: { text: 'Text ready for 12 of 30 pages', tone: 'info' },
      },
      {
        situation: 'When pages in the thousands have their text',
        changes: { stats: { pageCount: 1200, doneCount: 1050 } },
        rule: 'should format both counts alike',
        expected: { text: 'Text ready for 1,050 of 1,200 pages', tone: 'info' },
      },
      {
        situation: 'When the one page of a document waits for its text',
        changes: { stats: { pageCount: 1, doneCount: 0 } },
        rule: 'should take the singular',
        expected: { text: 'Text ready for 0 of 1 page', tone: 'info' },
      },
      {
        situation: 'When the document has no page',
        changes: { stats: { pageCount: 0, doneCount: 0 } },
        rule: 'should say that it has no page yet, rather than that its text is ready',
        expected: { text: 'No pages yet', tone: 'neutral' },
      },
    ];

    for (const { situation, changes, rule, expected } of situations) {
      describe(situation, () => {
        let status: TextStatus;
        beforeEach(() => {
          status = textStatus(englishT, sampleDocument(changes).stats);
        });

        it(rule, () => {
          assert.deepEqual(status, expected);
        });
      });
    }
  });

  describe('The librarySummaryText() function', () => {
    describe('When the library holds documents', () => {
      let text: string;
      beforeEach(() => {
        const documents = [sampleDocument({ stats: { pageCount: 1000 } }), sampleDocument({ stats: { pageCount: 6 } })];
        text = librarySummaryText(englishT, documents);
      });

      it('should count the documents and their pages, with the numbers formatted', () => {
        assert.equal(text, '2 documents · 1,006 pages');
      });
    });

    describe('When the library is empty', () => {
      let text: string;
      beforeEach(() => {
        text = librarySummaryText(englishT, []);
      });

      it('should be empty, since the screen says so in its place', () => {
        assert.equal(text, '');
      });
    });
  });
});
