// French is written only in the French catalog, so these tests compare with its entries instead of quoting it.
import assert from 'node:assert/strict';
import { before, beforeEach, describe, it } from 'node:test';

import type { TFunction } from 'i18next';
import frenchCatalog from '../../../../locales/fr.json' with { type: 'json' };
import { ApiError } from '../../../application/api-errors.ts';
import { samplePage } from '../../../domain/document-details.test-support.ts';
import { CATALOGS } from '../../i18next/catalogs.ts';
import { createLocalizationFor } from '../../i18next/localization.test-support.ts';
import {
  type MoveChoice,
  moveChoices,
  moveSummaryText,
  moveText,
  type OrganizerNotice,
  organizerNotice,
  outsideText,
  pageName,
  placedHintText,
  selectedPagesText,
  selectionStatusText,
  spanLongText,
} from './organizer-text.ts';

const A_THOUSAND = 1000;
const UNPROCESSABLE = 422;
const FRENCH_THOUSAND = '1\u202f000';
const PAGES = new Map([
  ['a', samplePage('a', { pageLabel: '11' })],
  ['b', samplePage('b', { pageLabel: '12-13', numberEnd: 13 })],
  ['c', samplePage('c', { pageLabel: null })],
]);
const ORDER = ['a', 'b', 'c'];

describe('The texts of the organizer', () => {
  let englishT: TFunction;
  let frenchT: TFunction;
  before(async () => {
    englishT = (await createLocalizationFor(['en-US'], CATALOGS)).i18next.t;
    frenchT = (await createLocalizationFor(['fr-FR'], CATALOGS)).i18next.t;
  });

  describe('The pageName() function', () => {
    describe('When given a numbered page and a page with no number', () => {
      let names: string[];
      beforeEach(() => {
        names = [pageName(englishT, { pageLabel: '11' }, 0), pageName(englishT, { pageLabel: null }, 2)];
      });

      it('should name each by its place, which tells apart the pages that have no number', () => {
        assert.deepEqual(names, ['the page at position 1 (p. 11)', 'the page at position 3 (no number)']);
      });
    });
  });

  describe('The selectionStatusText() function', () => {
    describe('When no page is selected, then one, then a thousand', () => {
      let texts: string[];
      beforeEach(() => {
        texts = [0, 1, A_THOUSAND].map((count) => selectionStatusText(englishT, count, A_THOUSAND));
      });

      it('should count them, formatting the count and not the total, as before', () => {
        assert.deepEqual(texts, [
          'No page selected',
          '1 page selected out of 1000',
          '1,000 pages selected out of 1000',
        ]);
      });
    });

    describe('When a thousand pages are selected in French', () => {
      let text: string;
      beforeEach(() => {
        text = selectionStatusText(frenchT, A_THOUSAND, A_THOUSAND);
      });

      it('should format the count in the French way, in the plural', () => {
        const form = frenchCatalog['{{count, number}} page selected out of {{total}}_other'];
        assert.equal(text, form.replace('{{count, number}}', FRENCH_THOUSAND).replace('{{total}}', String(A_THOUSAND)));
      });
    });
  });

  describe('The spanLongText() function', () => {
    describe('When the range holds one page, then three', () => {
      let texts: string[];
      beforeEach(() => {
        texts = [1, 3].map((count) => spanLongText(englishT, count));
      });

      it('should count its pages', () => {
        assert.deepEqual(texts, ['Select the range (1 page)', 'Select the range (3 pages)']);
      });
    });
  });

  describe('The placedHintText() function', () => {
    describe('When the reading order is empty, numbered, or only in capture order', () => {
      let hints: string[];
      beforeEach(() => {
        hints = [
          placedHintText(englishT, 0, false),
          placedHintText(englishT, 2, true),
          placedHintText(englishT, 2, false),
        ];
      });

      it('should say where the order comes from', () => {
        assert.deepEqual(hints, [
          'No page is in the document yet.',
          'The order of document.md.',
          'No numbered page: capture order.',
        ]);
      });
    });
  });

  describe('The outsideText() function', () => {
    describe('When a thousand pages are outside the document', () => {
      let text: string;
      beforeEach(() => {
        text = outsideText(englishT, A_THOUSAND);
      });

      it('should write the count as it is, as before', () => {
        assert.equal(
          text,
          '1000 pages are outside the document (waiting to be read, couldn’t be read, excluded or duplicates): they are not affected.',
        );
      });
    });
  });

  describe('The moveText() function', () => {
    describe('When one page moved, then several', () => {
      let texts: string[];
      beforeEach(() => {
        texts = [moveText(englishT, PAGES, ORDER, ['b']), moveText(englishT, PAGES, ORDER, ['b', 'c'])];
      });

      it('should tell where they are now, a spread named in the plural', () => {
        assert.deepEqual(texts, ['Pages 12-13: position 2 of 3.', '2 pages moved: positions 2 to 3 of 3.']);
      });
    });
  });

  describe('The moveChoices() function', () => {
    describe('When a page is about to move', () => {
      let choices: MoveChoice[];
      beforeEach(() => {
        choices = moveChoices(englishT, PAGES, ORDER, ['b']);
      });

      it('should offer every other page, by its place and its label', () => {
        assert.deepEqual(choices, [
          { pageId: 'a', label: '1 · p. 11', name: 'the page at position 1 (p. 11)' },
          { pageId: 'c', label: '3 · No number', name: 'the page at position 3 (no number)' },
        ]);
      });
    });
  });

  describe('The selectedPagesText() function', () => {
    describe('When one page is selected, then two', () => {
      let texts: string[];
      beforeEach(() => {
        texts = [selectedPagesText(englishT, 1), selectedPagesText(englishT, 2)];
      });

      it('should count them', () => {
        assert.deepEqual(texts, ['1 page selected.', '2 selected pages, in their current order.']);
      });
    });
  });

  describe('The moveSummaryText() function', () => {
    describe('When one page, then several, go before or after a page', () => {
      let summaries: string[];
      beforeEach(() => {
        const page = 'the page at position 3 (no number)';
        summaries = [
          moveSummaryText(englishT, 1, 'before', page),
          moveSummaryText(englishT, 1, 'after', page),
          moveSummaryText(englishT, 2, 'before', page),
          moveSummaryText(englishT, 2, 'after', page),
        ];
      });

      it('should say where they will go', () => {
        assert.deepEqual(summaries, [
          'The page will go before the page at position 3 (no number).',
          'The page will go after the page at position 3 (no number).',
          'The 2 pages will go before the page at position 3 (no number).',
          'The 2 pages will go after the page at position 3 (no number).',
        ]);
      });
    });
  });

  describe('The organizerNotice() function', () => {
    describe('When given each event of the organizer', () => {
      let notices: OrganizerNotice[];
      beforeEach(() => {
        notices = [
          organizerNotice(englishT, { kind: 'conflict' }),
          organizerNotice(englishT, { kind: 'save-failed', failure: new TypeError('a bug') }),
          organizerNotice(englishT, { kind: 'reset-done' }),
          organizerNotice(englishT, { kind: 'reset-failed', failure: new TypeError('a bug') }),
        ];
      });

      it('should tell each, a success as such and the failures as errors', () => {
        assert.deepEqual(notices, [
          { message: 'The list of pages changed: try again.', tone: 'error' },
          { message: 'The new order could not be saved.', tone: 'error' },
          { message: 'Automatic order restored.', tone: 'success' },
          { message: 'The automatic order could not be restored.', tone: 'error' },
        ]);
      });
    });

    describe('When the api refuses the order with a reason', () => {
      let notice: OrganizerNotice;
      beforeEach(() => {
        notice = organizerNotice(englishT, {
          kind: 'save-failed',
          failure: new ApiError(UNPROCESSABLE, 'unknown page'),
        });
      });

      it('should give the reason after the message', () => {
        assert.deepEqual(notice, { message: 'The new order could not be saved. (unknown page)', tone: 'error' });
      });
    });
  });
});
