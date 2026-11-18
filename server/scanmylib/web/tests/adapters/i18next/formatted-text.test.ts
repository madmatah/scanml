// French is written only in the French catalog, so these tests compare with its entries instead of quoting it.
import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import frenchCatalog from '../../../locales/fr.json' with { type: 'json' };
import { CATALOGS } from '../../../src/adapters/i18next/catalogs.ts';
import { formatBytes, formatPercent, formatSeconds, quoted } from '../../../src/adapters/i18next/formatted-text.ts';
import type { Localization } from '../../../src/adapters/i18next/localization.ts';
import { createLocalizationFor } from './browser-languages.ts';

const ENGLISH_LANGUAGES = ['en-US'];
const FRENCH_LANGUAGES = ['fr-FR'];
const NO_BREAK_SPACE = ' ';
const FRENCH_DECIMALS = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 });

describe('The formatted text', () => {
  describe('The formatPercent() function', () => {
    const ratio = 0.473;

    describe('When the UI is in English', () => {
      let text: string;
      beforeEach(async () => {
        const { i18next, formatting } = await createLocalizationFor(ENGLISH_LANGUAGES, CATALOGS);
        text = formatPercent(i18next.t, formatting, ratio);
      });

      it('should write the ratio as a whole percentage', () => {
        assert.equal(text, '47%');
      });
    });

    describe('When the UI is in French', () => {
      let text: string;
      beforeEach(async () => {
        const { i18next, formatting } = await createLocalizationFor(FRENCH_LANGUAGES, CATALOGS);
        text = formatPercent(i18next.t, formatting, ratio);
      });

      it('should write a whole percentage, with a no-break space before the percent sign', () => {
        assert.equal(text, `47${NO_BREAK_SPACE}%`);
      });
    });
  });

  describe('The formatSeconds() function', () => {
    const seconds = 2.345;

    describe('When the UI is in English', () => {
      let text: string;
      beforeEach(async () => {
        const { i18next, formatting } = await createLocalizationFor(ENGLISH_LANGUAGES, CATALOGS);
        text = formatSeconds(i18next.t, formatting, seconds);
      });

      it('should write the seconds to a tenth, with their unit', () => {
        assert.equal(text, '2.3 s');
      });
    });

    describe('When the UI is in French', () => {
      let text: string;
      beforeEach(async () => {
        const { i18next, formatting } = await createLocalizationFor(FRENCH_LANGUAGES, CATALOGS);
        text = formatSeconds(i18next.t, formatting, seconds);
      });

      it('should write the seconds to a tenth as Intl does for French, with a no-break space before the unit', () => {
        assert.equal(text, `${FRENCH_DECIMALS.format(2.3)}${NO_BREAK_SPACE}s`);
      });
    });
  });

  describe('The formatBytes() function', () => {
    const megabyteSizeBytes = 3.2 * 1024 * 1024;

    describe('When the UI is in English', () => {
      let localization: Localization;
      beforeEach(async () => {
        localization = await createLocalizationFor(ENGLISH_LANGUAGES, CATALOGS);
      });

      describe('When the size is less than a kilobyte', () => {
        const sizeBytes = 512;
        let text: string;
        beforeEach(() => {
          text = formatBytes(localization.i18next.t, localization.formatting, sizeBytes);
        });

        it('should write it in bytes', () => {
          assert.equal(text, '512 B');
        });
      });

      describe('When the size is in megabytes', () => {
        let text: string;
        beforeEach(() => {
          text = formatBytes(localization.i18next.t, localization.formatting, megabyteSizeBytes);
        });

        it('should write it in megabytes, to a tenth', () => {
          assert.equal(text, '3.2 MB');
        });
      });
    });

    describe('When the UI is in French', () => {
      let localization: Localization;
      beforeEach(async () => {
        localization = await createLocalizationFor(FRENCH_LANGUAGES, CATALOGS);
      });

      describe('When the size is in megabytes', () => {
        let text: string;
        beforeEach(() => {
          text = formatBytes(localization.i18next.t, localization.formatting, megabyteSizeBytes);
        });

        it('should write the decimal as Intl does for French, and the unit from the catalog', () => {
          assert.equal(text, frenchCatalog['{{size}} MB'].replace('{{size}}', FRENCH_DECIMALS.format(3.2)));
        });
      });
    });
  });

  describe('The quoted() function', () => {
    const title = 'Example Book';

    describe('When the UI is in English', () => {
      let text: string;
      beforeEach(async () => {
        const { i18next } = await createLocalizationFor(ENGLISH_LANGUAGES, CATALOGS);
        text = quoted(i18next.t, title);
      });

      it('should put the text between English quotation marks', () => {
        assert.equal(text, '“Example Book”');
      });
    });

    describe('When the UI is in French', () => {
      let text: string;
      beforeEach(async () => {
        const { i18next } = await createLocalizationFor(FRENCH_LANGUAGES, CATALOGS);
        text = quoted(i18next.t, title);
      });

      it('should put the text between the quotation marks of the catalog', () => {
        assert.equal(text, frenchCatalog['“{{text}}”'].replace('{{text}}', title));
      });
    });
  });
});
