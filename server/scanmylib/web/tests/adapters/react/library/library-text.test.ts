// French is written only in the French catalog, so these tests compare with its entries instead of quoting it.
import assert from 'node:assert/strict';
import { before, beforeEach, describe, it } from 'node:test';

import type { TFunction } from 'i18next';
import frenchCatalog from '../../../../locales/fr.json' with { type: 'json' };
import { CATALOGS } from '../../../../src/adapters/i18next/catalogs.ts';
import {
  coverageText,
  librarySummaryText,
  progressText,
  type StatusChip,
  statusChips,
} from '../../../../src/adapters/react/library/library-text.ts';
import { type DocumentChanges, sampleDocument } from '../../../domain/document-summary-samples.ts';
import { createLocalizationFor } from '../../i18next/browser-languages.ts';

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

  describe('The coverageText() function', () => {
    const situations: {
      situation: string;
      changes: DocumentChanges;
      rule: string;
      expected: string;
    }[] = [
      {
        situation: 'When the numbered pages leave a gap',
        changes: { coverage: {} },
        rule: 'should give the pages covered, then those not scanned yet',
        expected: 'Pages 11–15, 18–21 · not scanned yet: 16–17',
      },
      {
        situation: 'When the numbered pages leave no gap',
        changes: { coverage: { ranges: [[1, 6]], label: '1–6', gaps: [], lowestNumber: 1 } },
        rule: 'should give the pages covered alone',
        expected: 'Pages 1–6',
      },
      {
        situation: 'When the api gives no label for the pages covered',
        changes: { coverage: { ranges: [[1, 6]], label: '', gaps: [], lowestNumber: 1 } },
        rule: 'should write the ranges of the pages covered',
        expected: 'Pages 1–6',
      },
      {
        situation: 'When no page is numbered',
        changes: { coverage: { ranges: [], label: '', gaps: [], lowestNumber: null, unnumberedCount: 2 } },
        rule: 'should count the unnumbered pages',
        expected: '2 unnumbered pages',
      },
      {
        situation: 'When the document has no page',
        changes: { coverage: { ranges: [], label: '', gaps: [], lowestNumber: null, unnumberedCount: 0 } },
        rule: 'should say that no page is numbered',
        expected: 'No numbered page',
      },
    ];

    for (const { situation, changes, rule, expected } of situations) {
      describe(situation, () => {
        let text: string;
        beforeEach(() => {
          text = coverageText(englishT, sampleDocument(changes).coverage);
        });

        it(rule, () => {
          assert.equal(text, expected);
        });
      });
    }
  });

  describe('The progressText() function', () => {
    describe('When some pages have their text', () => {
      let text: string;
      beforeEach(() => {
        text = progressText(englishT, sampleDocument({ stats: { pageCount: 11, doneCount: 6 } }).stats);
      });

      it('should count the pages whose text is ready out of all of them', () => {
        assert.equal(text, '6 / 11 pages: text ready');
      });
    });

    describe('When the document has one page', () => {
      let text: string;
      beforeEach(() => {
        text = progressText(englishT, sampleDocument({ stats: { pageCount: 1, doneCount: 1 } }).stats);
      });

      it('should take the singular', () => {
        assert.equal(text, '1 / 1 page: text ready');
      });
    });
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
