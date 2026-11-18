// French is written only in the French catalog, so these tests compare with its entries instead of quoting it.
import assert from 'node:assert/strict';
import { before, beforeEach, describe, it } from 'node:test';

import type { TFunction } from 'i18next';
import frenchCatalog from '../../../../locales/fr.json' with { type: 'json' };
import { CATALOGS } from '../../../../src/adapters/i18next/catalogs.ts';
import {
  coverageDescription,
  coverageRangeTitle,
  missingPagesText,
  type PageGroupHeading,
  pageGroupHeading,
  type StatTile,
  statTiles,
  unnumberedPagesNote,
} from '../../../../src/adapters/react/document/document-text.ts';
import { sampleDocument } from '../../../domain/document-summary-samples.ts';
import { createLocalizationFor } from '../../i18next/browser-languages.ts';

const NUMBERED = { hasPlacedPages: true, hasPagesPlacedByHand: false };

describe('The document text', () => {
  let englishT: TFunction;
  before(async () => {
    englishT = (await createLocalizationFor(['en-US'], CATALOGS)).i18next.t;
  });

  describe('The pageGroupHeading() function', () => {
    describe('When the pages are placed by their numbers', () => {
      let heading: PageGroupHeading;
      beforeEach(() => {
        heading = pageGroupHeading(englishT, 'placed', NUMBERED);
      });

      it('should call them the document, in the reading order of its Markdown', () => {
        assert.deepEqual(heading, { title: 'In the document', hint: 'In the reading order of document.md.' });
      });
    });

    describe('When some pages were placed by hand', () => {
      let heading: PageGroupHeading;
      beforeEach(() => {
        heading = pageGroupHeading(englishT, 'placed', { hasPlacedPages: true, hasPagesPlacedByHand: true });
      });

      it('should say so in the hint', () => {
        assert.equal(heading.hint, 'In the reading order of document.md, with pages placed by hand.');
      });
    });

    describe('When unnumbered pages follow numbered ones', () => {
      let heading: PageGroupHeading;
      beforeEach(() => {
        heading = pageGroupHeading(englishT, 'unplaced', NUMBERED);
      });

      it('should set them apart as pages to place', () => {
        assert.equal(heading.title, 'Unnumbered pages');
      });
    });

    describe('When no page of the document is numbered', () => {
      let heading: PageGroupHeading;
      beforeEach(() => {
        heading = pageGroupHeading(englishT, 'unplaced', { hasPlacedPages: false, hasPagesPlacedByHand: false });
      });

      it('should call them the document, in capture order', () => {
        assert.deepEqual(heading, { title: 'In the document', hint: 'No numbered page: capture order.' });
      });
    });

    describe('When the pages are duplicates', () => {
      let heading: PageGroupHeading;
      beforeEach(() => {
        heading = pageGroupHeading(englishT, 'duplicate', NUMBERED);
      });

      it('should say that newer scans replaced them', () => {
        assert.deepEqual(heading, {
          title: 'Duplicates',
          hint: 'Replaced by a newer scan of the same page number.',
        });
      });
    });
  });

  describe('The statTiles() function', () => {
    describe('When given the counts of a document', () => {
      let tiles: StatTile[];
      beforeEach(() => {
        const stats = { queuedCount: 1, processingCount: 2, errorCount: 3, excludedCount: 4, duplicateCount: 5 };
        tiles = statTiles(englishT, sampleDocument({ stats }).stats);
      });

      it('should give each count its label and its tone, in the order of the screen', () => {
        assert.deepEqual(tiles, [
          { name: 'pages', label: 'Pages', count: 11, tone: null },
          { name: 'done', label: 'Text ready', count: 11, tone: null },
          { name: 'queued', label: 'Queued', count: 1, tone: 'warn' },
          { name: 'processing', label: 'Being read', count: 2, tone: 'info' },
          { name: 'error', label: 'Couldn’t be read', count: 3, tone: 'danger' },
          { name: 'excluded', label: 'Excluded', count: 4, tone: null },
          { name: 'duplicates', label: 'Duplicates', count: 5, tone: null },
        ]);
      });
    });
  });

  describe('The coverageRangeTitle() function', () => {
    describe('When given single pages and ranges, scanned or missing', () => {
      let titles: string[];
      beforeEach(() => {
        titles = [
          coverageRangeTitle(englishT, [16, 16], true),
          coverageRangeTitle(englishT, [16, 16], false),
          coverageRangeTitle(englishT, [16, 17], true),
          coverageRangeTitle(englishT, [16, 17], false),
        ];
      });

      it('should name the page or the range, and whether it is scanned', () => {
        assert.deepEqual(titles, [
          'Page 16: not scanned yet',
          'Page 16: scanned',
          'Pages 16–17: not scanned yet',
          'Pages 16–17: scanned',
        ]);
      });
    });
  });

  describe('The coverageDescription() function', () => {
    describe('When pages are missing', () => {
      let description: string;
      beforeEach(() => {
        description = coverageDescription(englishT, '11–15, 18–21', [[16, 17]], 11, 21);
      });

      it('should name the scanned pages and the missing ones', () => {
        assert.equal(description, 'Scanned pages: 11–15, 18–21. Not scanned yet: 16–17.');
      });
    });

    describe('When no page is missing', () => {
      let description: string;
      beforeEach(() => {
        description = coverageDescription(englishT, '11–21', [], 11, 21);
      });

      it('should say that every page between the lowest and the highest number is scanned', () => {
        assert.equal(description, 'All pages from 11 to 21 are scanned.');
      });
    });
  });

  describe('The missingPagesText() function', () => {
    describe('When no page is missing, in French', () => {
      let text: string;
      beforeEach(async () => {
        const { i18next } = await createLocalizationFor(['fr-FR'], CATALOGS);
        text = missingPagesText(i18next.t, []);
      });

      it('should say none in the gender of the missing pages', () => {
        assert.equal(text, frenchCatalog['none_missing pages']);
      });
    });

    describe('When pages are missing', () => {
      let text: string;
      beforeEach(() => {
        text = missingPagesText(englishT, [
          [16, 17],
          [30, 30],
        ]);
      });

      it('should list their ranges', () => {
        assert.equal(text, '16–17, 30');
      });
    });
  });

  describe('The unnumberedPagesNote() function', () => {
    describe('When the document holds two unnumbered pages', () => {
      let note: string;
      beforeEach(() => {
        note = unnumberedPagesNote(englishT, 2);
      });

      it('should add them to the coverage', () => {
        assert.equal(note, '+ 2 unnumbered pages');
      });
    });
  });
});
