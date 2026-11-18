import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { createNumberFormatting } from '../../src/domain/formatting.ts';

const ENGLISH_LOCALE = 'en-US';
const FRENCH_LOCALE = 'fr-FR';

describe('The formatting', () => {
  describe('The formatNumber() function of a number formatting', () => {
    const number = 1234;

    describe('When the locale is English', () => {
      let text: string;
      beforeEach(() => {
        text = createNumberFormatting(ENGLISH_LOCALE).formatNumber(number);
      });

      it('should group the thousands with a comma', () => {
        assert.equal(text, '1,234');
      });
    });

    describe('When the locale is French', () => {
      const frenchIntegers = new Intl.NumberFormat(FRENCH_LOCALE);
      let text: string;
      beforeEach(() => {
        text = createNumberFormatting(FRENCH_LOCALE).formatNumber(number);
      });

      it('should write the number as Intl does for French', () => {
        assert.equal(text, frenchIntegers.format(number));
      });
    });
  });
});
