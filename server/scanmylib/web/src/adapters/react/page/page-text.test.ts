// French is written only in the French catalog, so these tests compare with its entries instead of quoting it.
import assert from 'node:assert/strict';
import { before, beforeEach, describe, it } from 'node:test';

import frenchCatalog from '../../../../locales/fr.json' with { type: 'json' };
import { samplePageDetails } from '../../../domain/page-details.test-support.ts';
import { CATALOGS } from '../../i18next/catalogs.ts';
import { createLocalizationFor } from '../../i18next/localization.test-support.ts';
import type { Localization } from '../../i18next/localization.ts';
import { type DetailRow, detailRows, numberHelp, scanDescription } from './page-text.ts';

const NARROW_NO_BREAK_SPACE = '\u202f';

const describedRows = (rows: readonly DetailRow[]): Record<string, string> => {
  return Object.fromEntries(rows.map(({ term, description }) => [term, description]));
};

describe('The page text', () => {
  let english: Localization;
  let french: Localization;
  before(async () => {
    english = await createLocalizationFor(['en-US'], CATALOGS);
    french = await createLocalizationFor(['fr-FR'], CATALOGS);
  });

  describe('The detailRows() function', () => {
    describe('When the text of the page is read', () => {
      let rows: DetailRow[];
      beforeEach(() => {
        const { i18next, formatting, dates } = english;
        rows = detailRows(i18next.t, samplePageDetails({ hintNumber: 10 }), { numbers: formatting, dates });
      });

      it('should list what the api knows of the page, in its order', () => {
        assert.deepEqual(
          rows.map(({ term }) => term),
          [
            'Status',
            'Number',
            'Numbers read on the page',
            'Number given by the phone',
            'Captured',
            'Received',
            'Photo series',
            'Rotation',
            'Dimensions',
            'Text recognition engine',
            'Text recognition time',
            'Recognized text',
            'Illustrations',
            'Text read on',
            'File key',
          ],
        );
      });

      it('should describe each, the number with its source and the series by the start of its id', () => {
        assert.deepEqual(describedRows(rows), {
          Status: 'Text ready',
          Number: '11 (detected)',
          'Numbers read on the page': '11',
          'Number given by the phone': '10',
          Captured: english.dates.formatDateTime(new Date('2026-11-14T15:31:00+00:00')),
          Received: english.dates.formatDateTime(new Date('2026-11-14T15:31:05+00:00')),
          'Photo series': '6b1f0c3e · photo no. 3',
          Rotation: '0°',
          Dimensions: '800 × 1011 px',
          'Text recognition engine': 'example-engine',
          'Text recognition time': '2.3 s',
          'Recognized text': '1,234 characters',
          Illustrations: '2',
          'Text read on': english.dates.formatDateTime(new Date('2026-11-14T15:32:00+00:00')),
          'File key': 'p0011',
        });
      });

      it('should show the key of the files alone as code', () => {
        assert.deepEqual(
          rows.filter(({ isCode }) => isCode).map(({ term }) => term),
          ['File key'],
        );
      });
    });

    describe('When the text of the page is not read yet', () => {
      let rows: DetailRow[];
      beforeEach(() => {
        const { i18next, formatting, dates } = english;
        const page = samplePageDetails({
          status: 'queued',
          reading: null,
          pageLabel: null,
          number: null,
          numberSource: null,
          detectedNumbers: [],
          sessionId: null,
        });
        rows = detailRows(i18next.t, page, { numbers: formatting, dates });
      });

      it('should leave out what is not known, and say none for the numbers', () => {
        assert.deepEqual(describedRows(rows), {
          Status: 'Queued',
          Number: 'none',
          'Numbers read on the page': 'none',
          Captured: english.dates.formatDateTime(new Date('2026-11-14T15:31:00+00:00')),
          Received: english.dates.formatDateTime(new Date('2026-11-14T15:31:05+00:00')),
          Rotation: '0°',
          Dimensions: '800 × 1011 px',
          'File key': 'p0011',
        });
      });
    });

    describe('When a photo of a series has no place in it', () => {
      let rows: DetailRow[];
      beforeEach(() => {
        const { i18next, formatting, dates } = english;
        rows = detailRows(i18next.t, samplePageDetails({ sequence: null }), { numbers: formatting, dates });
      });

      it('should show no value for its place', () => {
        assert.equal(describedRows(rows)['Photo series'], '6b1f0c3e · photo no. —');
      });
    });

    describe('When the reading counts one character', () => {
      let rows: DetailRow[];
      beforeEach(() => {
        const { i18next, formatting, dates } = english;
        const page = samplePageDetails({
          reading: { engine: null, durationSeconds: null, readAt: null, illustrationCount: 0, characterCount: 1 },
        });
        rows = detailRows(i18next.t, page, { numbers: formatting, dates });
      });

      it('should count it in the singular, and keep a count of no illustration', () => {
        assert.deepEqual(
          { recognized: describedRows(rows)['Recognized text'], illustrations: describedRows(rows).Illustrations },
          { recognized: '1 character', illustrations: '0' },
        );
      });
    });

    describe('When the UI is in French', () => {
      let rows: DetailRow[];
      beforeEach(() => {
        const { i18next, formatting, dates } = french;
        rows = detailRows(i18next.t, samplePageDetails(), { numbers: formatting, dates });
      });

      it('should count the characters with the French catalog and the French digit groups', () => {
        assert.equal(
          describedRows(rows)[frenchCatalog['Recognized text']],
          frenchCatalog['{{count, number}} character_other'].replace(
            '{{count, number}}',
            `1${NARROW_NO_BREAK_SPACE}234`,
          ),
        );
      });
    });
  });

  describe('The numberHelp() function', () => {
    const rows: { situation: string; changes: Parameters<typeof samplePageDetails>[0]; expected: string }[] = [
      {
        situation: 'When the number was detected on the page',
        changes: { numberSource: 'detected' },
        expected: 'Number detected on the page.',
      },
      {
        situation: 'When the number was typed by hand',
        changes: { numberSource: 'manual', manualNumber: 11 },
        expected: 'Typed by hand. “Clear” goes back to the detected or inferred number.',
      },
      {
        situation: 'When the page has no number and was placed with Organize',
        changes: { numberSource: null, placement: 'manual' },
        expected: 'No known number: the page is at the place chosen with “Organize”.',
      },
      {
        situation: 'When the page has no number and is placed by its photo series',
        changes: { numberSource: null, placement: 'session' },
        expected: 'No known number: the page is placed next to the pages photographed just before or just after it.',
      },
      {
        situation: 'When the page has no number and no place',
        changes: { numberSource: null, placement: 'unplaced' },
        expected: 'No known number: the page is filed with the unnumbered pages, at the end of the document.',
      },
    ];

    for (const { situation, changes, expected } of rows) {
      describe(situation, () => {
        let help: string;
        beforeEach(() => {
          help = numberHelp(english.i18next.t, samplePageDetails(changes));
        });

        it('should say so', () => {
          assert.equal(help, expected);
        });
      });
    }
  });

  describe('The scanDescription() function', () => {
    describe('When the page has a number', () => {
      let description: string;
      beforeEach(() => {
        description = scanDescription(english.i18next.t, samplePageDetails({ pageLabel: '11' }));
      });

      it('should name the page within the sentence', () => {
        assert.equal(description, 'Original scan, page 11');
      });
    });
  });
});
