// French is written only in the French catalog, so these tests compare with its entries instead of quoting it.
import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import frenchCatalog from '../../../locales/fr.json' with { type: 'json' };
import { CATALOGS } from '../../../src/adapters/i18next/catalogs.ts';
import type { Localization } from '../../../src/adapters/i18next/localization.ts';
import type { LabeledPage } from '../../../src/adapters/i18next/page-labels.ts';
import {
  missingPagesText,
  outlineEntryLabel,
  pageMarkerText,
  unnumberedHeadingText,
} from '../../../src/adapters/i18next/reading-text.ts';
import { type ReadingPart, readingOutline } from '../../../src/domain/reading.ts';
import { createLocalizationFor } from './browser-languages.ts';

const ENGLISH_LANGUAGES = ['en-US'];
const FRENCH_LANGUAGES = ['fr-FR'];

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
const PAGES_BY_KEY = new Map<string, LabeledPage>([
  ['k-i', { page_label: 'i' }],
  ['k-1', { page_label: '1' }],
  ['k-plate', { page_label: null }],
  ['k-2', { page_label: '2' }],
  ['k-6', { page_label: '6–7' }],
  ['k-notes', { page_label: null }],
]);
const FIRST_THREE_PARTS = PARTS.slice(0, 3);

function fillTemplate(template: string, placeholderValues: Readonly<Record<string, string>>): string {
  return Object.entries(placeholderValues).reduce(
    (text, [placeholderName, placeholderValue]) => text.replaceAll(`{{${placeholderName}}}`, () => placeholderValue),
    template,
  );
}

describe('The reading text', () => {
  let localization: Localization;
  beforeEach(async () => {
    localization = await createLocalizationFor(ENGLISH_LANGUAGES, CATALOGS);
  });

  describe('The outlineEntryLabel() function', () => {
    describe('When the document has numbered pages, missing pages and unnumbered ones', () => {
      let labels: string[];
      beforeEach(() => {
        labels = readingOutline(PARTS, PAGES_BY_KEY).map((entry) => outlineEntryLabel(localization.i18next.t, entry));
      });

      it('should label the pages by their number, and the unnumbered ones by their position', () => {
        assert.deepEqual(labels, [
          'p. i',
          'p. 1',
          'No number (position 3)',
          'p. 2',
          'Pages not scanned yet: 3–5',
          'p. 6–7',
          'Unnumbered pages',
          'No number (position 6)',
        ]);
      });
    });

    describe('When the document data lacks the pages of the HTML, having changed meanwhile', () => {
      const noPagesByKey = new Map<string, LabeledPage>();
      let labels: string[];
      beforeEach(() => {
        labels = readingOutline(FIRST_THREE_PARTS, noPagesByKey).map((entry) =>
          outlineEntryLabel(localization.i18next.t, entry),
        );
      });

      it('should label each page with its marker in the HTML', () => {
        assert.deepEqual(labels, ['Page i', 'Page 1', 'Unnumbered page']);
      });
    });

    describe('When no page of the document has a number, as in a letter', () => {
      const letterKeys = ['a', 'b', 'c'];
      const letterParts = letterKeys.map((key): ReadingPart => ({ type: 'page', key, marker: 'Unnumbered page' }));
      const letterPagesByKey = new Map(letterKeys.map((key): [string, LabeledPage] => [key, { page_label: null }]));
      let labels: string[];
      beforeEach(() => {
        labels = readingOutline(letterParts, letterPagesByKey).map((entry) =>
          outlineEntryLabel(localization.i18next.t, entry),
        );
      });

      it('should tell the pages apart by their position in the reading order', () => {
        assert.deepEqual(labels, ['No number (position 1)', 'No number (position 2)', 'No number (position 3)']);
      });
    });

    describe('When the UI is in French', () => {
      const unnumberedThirdPageLabel = fillTemplate(frenchCatalog['{{label}} (position {{position}})'], {
        label: frenchCatalog['No number'],
        position: '3',
      });
      let labels: string[];
      beforeEach(async () => {
        const french = await createLocalizationFor(FRENCH_LANGUAGES, CATALOGS);
        labels = readingOutline(FIRST_THREE_PARTS, PAGES_BY_KEY).map((entry) =>
          outlineEntryLabel(french.i18next.t, entry),
        );
      });

      it('should label the pages in French', () => {
        assert.deepEqual(labels, ['p. i', 'p. 1', unnumberedThirdPageLabel]);
      });
    });
  });

  describe('The pageMarkerText() function', () => {
    describe('When the page has a number', () => {
      const label = '42';
      let marker: string;
      beforeEach(() => {
        marker = pageMarkerText(localization.i18next.t, label);
      });

      it('should write the page and its number in English, as the server does', () => {
        assert.equal(marker, 'Page 42');
      });
    });

    describe('When the page has a range of numbers', () => {
      const label = '42–43';
      let marker: string;
      beforeEach(() => {
        marker = pageMarkerText(localization.i18next.t, label);
      });

      it('should write the page and its range in English, as the server does', () => {
        assert.equal(marker, 'Page 42–43');
      });
    });

    describe('When the page has no number', () => {
      const noLabel = '';
      let marker: string;
      beforeEach(() => {
        marker = pageMarkerText(localization.i18next.t, noLabel);
      });

      it('should write in English that the page is unnumbered, as the server does', () => {
        assert.equal(marker, 'Unnumbered page');
      });
    });
  });

  describe('The missingPagesText() function', () => {
    describe('When several pages are not scanned yet', () => {
      const range = '13–44';
      let marker: string;
      beforeEach(() => {
        marker = missingPagesText(localization.i18next.t, range);
      });

      it('should name a range of pages not scanned yet in the words of the coverage', () => {
        assert.equal(marker, 'Pages not scanned yet: 13–44');
      });
    });

    describe('When one page is not scanned yet', () => {
      const range = '13';
      let marker: string;
      beforeEach(() => {
        marker = missingPagesText(localization.i18next.t, range);
      });

      it('should name one page not scanned yet in the singular, in the words of the coverage', () => {
        assert.equal(marker, 'Page not scanned yet: 13');
      });
    });
  });

  describe('The unnumberedHeadingText() function', () => {
    let heading: string;
    beforeEach(() => {
      heading = unnumberedHeadingText(localization.i18next.t);
    });

    it('should write in English the heading of the unnumbered pages, as the server does', () => {
      assert.equal(heading, 'Unnumbered pages');
    });
  });
});
