// French is written only in the French catalog, so these tests compare with its entries instead of quoting it.
import assert from 'node:assert/strict';
import { before, beforeEach, describe, it } from 'node:test';

import type { TFunction } from 'i18next';
import frenchCatalog from '../../../locales/fr.json' with { type: 'json' };
import { CATALOGS } from '../../../src/adapters/i18next/catalogs.ts';
import {
  type DescribedLabel,
  numberSourceLabel,
  type PageStatusLabel,
  pagePlacementLabel,
  pageStatusLabel,
  pageTitle,
} from '../../../src/adapters/i18next/page-labels.ts';
import { createLocalizationFor } from './browser-languages.ts';

describe('The page labels', () => {
  let englishT: TFunction;
  before(async () => {
    englishT = (await createLocalizationFor(['en-US'], CATALOGS)).i18next.t;
  });

  describe('The pageStatusLabel() function', () => {
    describe('When given each status of a page', () => {
      let labels: PageStatusLabel[];
      beforeEach(() => {
        labels = ['queued', 'processing', 'done', 'error'].map((status) => pageStatusLabel(englishT, status));
      });

      it('should name it, in the tone of its state', () => {
        assert.deepEqual(labels, [
          { label: 'Queued', tone: 'warn' },
          { label: 'Reading…', tone: 'info' },
          { label: 'Text ready', tone: 'ok' },
          { label: 'Failed', tone: 'danger' },
        ]);
      });
    });

    describe('When the UI is in French and the text of the page is read', () => {
      let label: PageStatusLabel;
      beforeEach(async () => {
        const { i18next } = await createLocalizationFor(['fr-FR'], CATALOGS);
        label = pageStatusLabel(i18next.t, 'done');
      });

      it('should use the translation of the page status, which differs from that of the count of read pages', () => {
        assert.equal(label.label, frenchCatalog['Text ready_page status']);
      });
    });

    describe('When the status is one this UI does not know', () => {
      let label: PageStatusLabel;
      beforeEach(() => {
        label = pageStatusLabel(englishT, 'archived');
      });

      it('should show it as it is, in a neutral tone', () => {
        assert.deepEqual(label, { label: 'archived', tone: 'neutral' });
      });
    });
  });

  describe('The numberSourceLabel() function', () => {
    describe('When the page has a number typed by hand', () => {
      let label: DescribedLabel | null;
      beforeEach(() => {
        label = numberSourceLabel(englishT, 'manual');
      });

      it('should name the source and describe it', () => {
        assert.deepEqual(label, { label: 'manual', description: 'Number typed by hand' });
      });
    });

    describe('When the page has no number', () => {
      let label: DescribedLabel | null;
      beforeEach(() => {
        label = numberSourceLabel(englishT, null);
      });

      it('should give no label', () => {
        assert.equal(label, null);
      });
    });

    describe('When the source is one this UI does not know', () => {
      let label: DescribedLabel | null;
      beforeEach(() => {
        label = numberSourceLabel(englishT, 'barcode');
      });

      it('should show it as it is, without a description', () => {
        assert.deepEqual(label, { label: 'barcode', description: '' });
      });
    });
  });

  describe('The pagePlacementLabel() function', () => {
    describe('When the page was placed by its capture session', () => {
      let label: DescribedLabel | null;
      beforeEach(() => {
        label = pagePlacementLabel(englishT, 'session');
      });

      it('should name the placement and describe it', () => {
        assert.deepEqual(label, {
          label: 'placed by session',
          description: 'No number: placed next to the pages photographed just before or just after it.',
        });
      });
    });

    describe('When the page is placed by its number', () => {
      let label: DescribedLabel | null;
      beforeEach(() => {
        label = pagePlacementLabel(englishT, 'number');
      });

      it('should give no label, since its number says its place', () => {
        assert.equal(label, null);
      });
    });
  });

  describe('The pageTitle() function', () => {
    describe('When given a page with one number, a spread and a page with no number', () => {
      let titles: string[];
      beforeEach(() => {
        titles = [
          { pageLabel: '11', numberEnd: null },
          { pageLabel: '12-13', numberEnd: 13 },
          { pageLabel: null, numberEnd: null },
        ].map((page) => pageTitle(englishT, page));
      });

      it('should name each, a spread in the plural', () => {
        assert.deepEqual(titles, ['Page 11', 'Pages 12-13', 'Page with no number']);
      });
    });
  });
});
