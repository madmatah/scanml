import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { formatBytes, formatNumber, formatPercent, formatSeconds, quoted } from '../static/js/lib/format.js';
import { setLocale } from '../static/js/lib/i18n.js';
import FRENCH from '../static/js/locales/fr.js';

const ENGLISH_PREFERENCES = ['en-US'];
const FRENCH_PREFERENCES = ['fr-FR'];
const NO_BREAK_SPACE = '\u00a0';
const FRENCH_DECIMALS = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 });

describe('The formats', () => {
  describe('The formatNumber() function', () => {
    const number = 1234;

    describe('When the UI is in English', () => {
      let text;
      beforeEach(() => {
        setLocale(ENGLISH_PREFERENCES);
        text = formatNumber(number);
      });

      it('should group the thousands with a comma', () => {
        assert.equal(text, '1,234');
      });
    });

    describe('When the UI is in French', () => {
      const frenchIntegers = new Intl.NumberFormat('fr-FR');
      let text;
      beforeEach(() => {
        setLocale(FRENCH_PREFERENCES);
        text = formatNumber(number);
      });

      it('should write the number as Intl does for French', () => {
        assert.equal(text, frenchIntegers.format(number));
      });
    });
  });

  describe('The formatPercent() function', () => {
    const ratio = 0.473;

    describe('When the UI is in English', () => {
      let text;
      beforeEach(() => {
        setLocale(ENGLISH_PREFERENCES);
        text = formatPercent(ratio);
      });

      it('should write the ratio as a whole percentage', () => {
        assert.equal(text, '47%');
      });
    });

    describe('When the UI is in French', () => {
      let text;
      beforeEach(() => {
        setLocale(FRENCH_PREFERENCES);
        text = formatPercent(ratio);
      });

      it('should write a whole percentage, with a no-break space before the percent sign', () => {
        assert.equal(text, `47${NO_BREAK_SPACE}%`);
      });
    });
  });

  describe('The formatSeconds() function', () => {
    const seconds = 2.345;

    describe('When the UI is in English', () => {
      let text;
      beforeEach(() => {
        setLocale(ENGLISH_PREFERENCES);
        text = formatSeconds(seconds);
      });

      it('should write the seconds to a tenth, with their unit', () => {
        assert.equal(text, '2.3 s');
      });
    });

    describe('When the UI is in French', () => {
      let text;
      beforeEach(() => {
        setLocale(FRENCH_PREFERENCES);
        text = formatSeconds(seconds);
      });

      it('should write the seconds to a tenth as Intl does for French, with a no-break space before the unit', () => {
        assert.equal(text, `${FRENCH_DECIMALS.format(2.3)}${NO_BREAK_SPACE}s`);
      });
    });
  });

  describe('The formatBytes() function', () => {
    const megabyteSizeBytes = 3.2 * 1024 * 1024;

    describe('When the UI is in English', () => {
      beforeEach(() => {
        setLocale(ENGLISH_PREFERENCES);
      });

      describe('When the size is less than a kilobyte', () => {
        const sizeBytes = 512;
        let text;
        beforeEach(() => {
          text = formatBytes(sizeBytes);
        });

        it('should write it in bytes', () => {
          assert.equal(text, '512 B');
        });
      });

      describe('When the size is in megabytes', () => {
        let text;
        beforeEach(() => {
          text = formatBytes(megabyteSizeBytes);
        });

        it('should write it in megabytes, to a tenth', () => {
          assert.equal(text, '3.2 MB');
        });
      });
    });

    describe('When the UI is in French', () => {
      beforeEach(() => {
        setLocale(FRENCH_PREFERENCES);
      });

      describe('When the size is in megabytes', () => {
        let text;
        beforeEach(() => {
          text = formatBytes(megabyteSizeBytes);
        });

        it('should write the decimal as Intl does for French, and the unit from the catalog', () => {
          assert.equal(text, FRENCH['{size} MB'].replace('{size}', FRENCH_DECIMALS.format(3.2)));
        });
      });
    });
  });

  describe('The quoted() function', () => {
    const title = 'Example Book';

    describe('When the UI is in English', () => {
      let text;
      beforeEach(() => {
        setLocale(ENGLISH_PREFERENCES);
        text = quoted(title);
      });

      it('should put the text between English quotation marks', () => {
        assert.equal(text, '“Example Book”');
      });
    });

    describe('When the UI is in French', () => {
      let text;
      beforeEach(() => {
        setLocale(FRENCH_PREFERENCES);
        text = quoted(title);
      });

      it('should put the text between the quotation marks of the catalog', () => {
        assert.equal(text, FRENCH['“{text}”'].replace('{text}', title));
      });
    });
  });
});
