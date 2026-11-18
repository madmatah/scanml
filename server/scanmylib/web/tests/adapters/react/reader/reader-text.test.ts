// French is written only in the French catalog, so these tests compare with its entries instead of quoting it.
import assert from 'node:assert/strict';
import { before, beforeEach, describe, it } from 'node:test';

import type { TFunction } from 'i18next';
import frenchCatalog from '../../../../locales/fr.json' with { type: 'json' };
import { CATALOGS } from '../../../../src/adapters/i18next/catalogs.ts';
import { emptyReadingMessage, waitingPagesNotice } from '../../../../src/adapters/react/reader/reader-text.ts';
import { type DocumentChanges, sampleDocument } from '../../../domain/document-summary-samples.ts';
import { createLocalizationFor } from '../../i18next/browser-languages.ts';

const WAITING_KEY = '{{count, number}} page is still waiting to be read: its text will be added once ready.';

describe('The reader text', () => {
  let englishT: TFunction;
  let frenchT: TFunction;
  before(async () => {
    englishT = (await createLocalizationFor(['en-US'], CATALOGS)).i18next.t;
    frenchT = (await createLocalizationFor(['fr-FR'], CATALOGS)).i18next.t;
  });

  describe('The waitingPagesNotice() function', () => {
    describe('When one page waits, in English', () => {
      let notice: string;
      beforeEach(() => {
        notice = waitingPagesNotice(englishT, 1);
      });

      it('should speak of one page', () => {
        assert.equal(notice, '1 page is still waiting to be read: its text will be added once ready.');
      });
    });

    describe('When several pages wait, in English', () => {
      let notice: string;
      beforeEach(() => {
        notice = waitingPagesNotice(englishT, 3);
      });

      it('should speak of several pages', () => {
        assert.equal(notice, '3 pages are still waiting to be read: their text will be added once ready.');
      });
    });

    describe('When a thousand pages wait, in French', () => {
      let notice: string;
      beforeEach(() => {
        notice = waitingPagesNotice(frenchT, 1000);
      });

      it('should use the French plural, with the count in the French way', () => {
        assert.equal(notice, frenchCatalog[`${WAITING_KEY}_other`].replace('{{count, number}}', '1\u202f000'));
      });
    });
  });

  describe('The emptyReadingMessage() function', () => {
    const rows: { situation: string; changes: DocumentChanges; expected: string }[] = [
      {
        situation: 'When its pages are waiting for their text',
        changes: { stats: { pageCount: 2, doneCount: 0, queuedCount: 1, processingCount: 1 } },
        expected: 'Its pages are still waiting to be read: their text will appear here once ready.',
      },
      {
        situation: 'When none of its pages is in the document',
        changes: { stats: { pageCount: 2, doneCount: 0, errorCount: 1, excludedCount: 1 } },
        expected: 'None of its pages is in the document: they couldn’t be read, are excluded or are duplicates.',
      },
      {
        situation: 'When it has no page',
        changes: { stats: { pageCount: 0, doneCount: 0 } },
        expected: 'This document has no page yet: add some from its screen or with the Android app.',
      },
    ];

    for (const { situation, changes, expected } of rows) {
      describe(situation, () => {
        let message: string;
        beforeEach(() => {
          message = emptyReadingMessage(englishT, sampleDocument(changes).stats);
        });

        it('should say why there is nothing to read', () => {
          assert.equal(message, expected);
        });
      });
    }
  });
});
