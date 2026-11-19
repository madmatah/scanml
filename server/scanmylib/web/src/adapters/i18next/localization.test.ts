// The French side of these catalogs is a stand-in, marked [fr]: French is written only in the UI's own catalog.
import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { createLocalizationFor } from './localization.test-support.ts';
import type { Localization } from './localization.ts';

const CATALOGS = {
  en: {
    translation: {
      Library: 'Library',
      'Delete {{title}}?': 'Delete {{title}}?',
      '{{first}} and {{second}}': '{{first}} and {{second}}',
      '{{first}}': '{{first}}',
      Untranslated: 'Untranslated',
      Failed: 'Failed',
      'Failed_page status': 'Failed',
      '{{count, number}} page_one': '{{count, number}} page',
      '{{count, number}} page_other': '{{count, number}} pages',
      '{{amount}} page_one': '{{amount}} page',
      '{{amount}} page_other': '{{amount}} pages',
    },
  },
  fr: {
    translation: {
      Library: '[fr] Library',
      'Delete {{title}}?': '[fr] Delete {{title}}?',
      Failed: '[fr] Failed',
      'Failed_page status': '[fr] Failed, as a page status',
      '{{count, number}} page_one': '[fr] {{count, number}} page',
      '{{count, number}} page_many': '[fr] {{count, number}} pages',
      '{{count, number}} page_other': '[fr] {{count, number}} pages',
    },
  },
};
const FRENCH = CATALOGS.fr.translation;
const ENGLISH_LANGUAGES = ['en-US'];
const FRENCH_LANGUAGES = ['fr-FR'];
const COUNT_PLACEHOLDER = '{{count, number}}';

describe('The localization', () => {
  describe('The createLocalization() function', () => {
    const detections = [
      {
        situation: 'When the browser prefers French in France first',
        browserLanguages: ['fr-FR', 'fr', 'en-US'],
        rule: 'should choose French, in that locale',
        expectedChoice: { language: 'fr', locale: 'fr-FR' },
      },
      {
        situation: 'When the browser prefers French without a region',
        browserLanguages: ['fr'],
        rule: 'should choose French, in the locale of France',
        expectedChoice: { language: 'fr', locale: 'fr-FR' },
      },
      {
        situation: 'When the browser prefers French in another region',
        browserLanguages: ['fr-CA'],
        rule: 'should choose French, in the region of the browser',
        expectedChoice: { language: 'fr', locale: 'fr-CA' },
      },
      {
        situation: 'When the browser writes its language tag in another letter case',
        browserLanguages: ['FR-be'],
        rule: 'should choose French, writing the locale in its canonical case',
        expectedChoice: { language: 'fr', locale: 'fr-BE' },
      },
      {
        situation: 'When the browser prefers a language that the UI does not speak, then French',
        browserLanguages: ['de-DE', 'fr-CH'],
        rule: 'should choose French, the first language that the UI speaks',
        expectedChoice: { language: 'fr', locale: 'fr-CH' },
      },
      {
        situation: 'When the browser prefers English, then French',
        browserLanguages: ['en-GB', 'fr-FR'],
        rule: 'should choose English, the first language that the UI speaks, in the region of the browser',
        expectedChoice: { language: 'en', locale: 'en-GB' },
      },
      {
        situation: 'When the browser prefers English without a region',
        browserLanguages: ['en'],
        rule: 'should choose English, in the locale of the United States',
        expectedChoice: { language: 'en', locale: 'en-US' },
      },
      {
        situation: 'When the browser prefers only languages that the UI does not speak',
        browserLanguages: ['de-DE', 'es'],
        rule: 'should choose English, in the locale of the United States',
        expectedChoice: { language: 'en', locale: 'en-US' },
      },
      {
        situation: 'When the browser prefers no language',
        browserLanguages: [],
        rule: 'should choose English, in the locale of the United States',
        expectedChoice: { language: 'en', locale: 'en-US' },
      },
      {
        situation: 'When the browser gives no preferences',
        browserLanguages: undefined,
        rule: 'should choose English, in the locale of the United States',
        expectedChoice: { language: 'en', locale: 'en-US' },
      },
      {
        situation: 'When the browser prefers French with a malformed tag',
        browserLanguages: ['fr-x'],
        rule: 'should choose French, in the locale of France',
        expectedChoice: { language: 'fr', locale: 'fr-FR' },
      },
      {
        situation: 'When the browser prefers French with a tag holding characters that no language code holds',
        browserLanguages: ['fr-!!'],
        rule: 'should choose English, since the language detector drops such a tag before i18next reads it',
        expectedChoice: { language: 'en', locale: 'en-US' },
      },
    ];

    for (const { situation, browserLanguages, rule, expectedChoice } of detections) {
      describe(situation, () => {
        let localization: Localization;
        beforeEach(async () => {
          localization = await createLocalizationFor(browserLanguages, CATALOGS);
        });

        it(rule, () => {
          assert.deepEqual({ language: localization.language, locale: localization.locale }, expectedChoice);
        });
      });
    }
  });

  describe('The t() function of its instance', () => {
    describe('When the UI is in English', () => {
      let localization: Localization;
      beforeEach(async () => {
        localization = await createLocalizationFor(ENGLISH_LANGUAGES, CATALOGS);
      });

      describe('When the message has no placeholder', () => {
        let text: string;
        beforeEach(() => {
          text = localization.i18next.t('Library');
        });

        it('should give the message itself', () => {
          assert.equal(text, 'Library');
        });
      });

      describe('When the message has a placeholder', () => {
        const values = { title: '“Example Book”' };
        let text: string;
        beforeEach(() => {
          text = localization.i18next.t('Delete {{title}}?', values);
        });

        it('should fill the placeholder with its value', () => {
          assert.equal(text, 'Delete “Example Book”?');
        });
      });

      describe('When the values are numbers, zero among them', () => {
        const values = { first: 1, second: 0 };
        let text: string;
        beforeEach(() => {
          text = localization.i18next.t('{{first}} and {{second}}', values);
        });

        it('should write every number, zero included', () => {
          assert.equal(text, '1 and 0');
        });
      });

      describe('When a placeholder has no value', () => {
        const values = { first: 'x' };
        let text: string;
        beforeEach(() => {
          text = localization.i18next.t('{{first}} and {{second}}', values);
        });

        it('should leave the placeholder as written', () => {
          assert.equal(text, 'x and {{second}}');
        });
      });

      describe('When a value holds a placeholder', () => {
        const values = { first: '{{second}}', second: 'no' };
        let text: string;
        beforeEach(() => {
          text = localization.i18next.t('{{first}}', values);
        });

        it('should leave it as written, since the values are never filled in again', () => {
          assert.equal(text, '{{second}}');
        });
      });

      describe('When the message has a context', () => {
        const context = { context: 'page status' };
        let text: string;
        beforeEach(() => {
          text = localization.i18next.t('Failed', context);
        });

        it('should give the message itself, without its context', () => {
          assert.equal(text, 'Failed');
        });
      });

      describe('When the message has a count', () => {
        const counts = [
          { situation: 'When the count is 0', count: 0, rule: 'should take the plural', expectedText: '0 pages' },
          { situation: 'When the count is 1', count: 1, rule: 'should take the singular', expectedText: '1 page' },
          { situation: 'When the count is 2', count: 2, rule: 'should take the plural', expectedText: '2 pages' },
          {
            situation: 'When the count is in the thousands',
            count: 1234,
            rule: 'should write the count for the locale',
            expectedText: '1,234 pages',
          },
        ];

        for (const { situation, count, rule, expectedText } of counts) {
          describe(situation, () => {
            let text: string;
            beforeEach(() => {
              text = localization.i18next.t('{{count, number}} page', { count });
            });

            it(rule, () => {
              assert.equal(text, expectedText);
            });
          });
        }
      });

      describe('When the message shows a value of its own in place of its count', () => {
        const values = { count: 2, amount: 'two' };
        let text: string;
        beforeEach(() => {
          text = localization.i18next.t('{{amount}} page', values);
        });

        it('should write the value as given, in the form the count chooses', () => {
          assert.equal(text, 'two pages');
        });
      });
    });

    describe('When the UI is in French', () => {
      let localization: Localization;
      beforeEach(async () => {
        localization = await createLocalizationFor(FRENCH_LANGUAGES, CATALOGS);
      });

      describe('When the message has a placeholder', () => {
        const values = { title: 'X' };
        let text: string;
        beforeEach(() => {
          text = localization.i18next.t('Delete {{title}}?', values);
        });

        it('should fill the placeholder of the translation from the catalog', () => {
          assert.equal(text, FRENCH['Delete {{title}}?'].replace('{{title}}', values.title));
        });
      });

      describe('When the catalog also translates the message in a context', () => {
        let text: string;
        beforeEach(() => {
          text = localization.i18next.t('Failed');
        });

        it('should take the translation without context', () => {
          assert.equal(text, FRENCH.Failed);
        });
      });

      describe('When the catalog does not translate the message', () => {
        let text: string;
        beforeEach(() => {
          text = localization.i18next.t('Untranslated');
        });

        it('should give the English message', () => {
          assert.equal(text, 'Untranslated');
        });
      });

      describe('When the message has a context', () => {
        const context = { context: 'page status' };
        let textInContext: string;
        let textWithoutContext: string;
        beforeEach(() => {
          textInContext = localization.i18next.t('Failed', context);
          textWithoutContext = localization.i18next.t('Failed');
        });

        it('should take the translation of the message in its context', () => {
          assert.equal(textInContext, FRENCH['Failed_page status']);
        });

        it('should translate the message otherwise than without context, where the English is ambiguous', () => {
          assert.notEqual(textInContext, textWithoutContext);
        });
      });

      describe('When the message has a count', () => {
        const frenchNumbers = new Intl.NumberFormat('fr-FR');
        const counts = [
          {
            situation: 'When the count is 0',
            count: 0,
            rule: 'should take the singular, as French does below 2',
            form: FRENCH['{{count, number}} page_one'],
          },
          {
            situation: 'When the count is 1',
            count: 1,
            rule: 'should take the singular',
            form: FRENCH['{{count, number}} page_one'],
          },
          {
            situation: 'When the count is 2',
            count: 2,
            rule: 'should take the plural',
            form: FRENCH['{{count, number}} page_other'],
          },
          {
            situation: 'When the count is in the thousands',
            count: 1234,
            rule: 'should take the plural, with the count written for the locale',
            form: FRENCH['{{count, number}} page_other'],
          },
          {
            situation: 'When the count is a million, of the plural category many',
            count: 1_000_000,
            rule: 'should take the form of that category, which repeats the plural',
            form: FRENCH['{{count, number}} page_many'],
          },
        ];

        for (const { situation, count, rule, form } of counts) {
          describe(situation, () => {
            let text: string;
            beforeEach(() => {
              text = localization.i18next.t('{{count, number}} page', { count });
            });

            it(rule, () => {
              assert.equal(text, form.replace(COUNT_PLACEHOLDER, frenchNumbers.format(count)));
            });
          });
        }
      });
    });

    describe('When the count of a message is a thousand', () => {
      const count = 1000;
      const narrowNoBreakSpace = '\u202f';
      const noBreakSpace = '\u00a0';
      let frenchText: string;
      let canadianFrenchText: string;
      let malformedTagText: string;
      beforeEach(async () => {
        const french = await createLocalizationFor(FRENCH_LANGUAGES, CATALOGS);
        const canadianFrench = await createLocalizationFor(['fr-CA'], CATALOGS);
        const malformedTag = await createLocalizationFor(['fr-x'], CATALOGS);
        frenchText = french.i18next.t('{{count, number}} page', { count });
        canadianFrenchText = canadianFrench.i18next.t('{{count, number}} page', { count });
        malformedTagText = malformedTag.i18next.t('{{count, number}} page', { count });
      });

      it('should group its thousands with a narrow no-break space in the locale of France', () => {
        assert.equal(
          frenchText,
          FRENCH['{{count, number}} page_other'].replace(COUNT_PLACEHOLDER, `1${narrowNoBreakSpace}000`),
        );
      });

      it('should group its thousands as the region of the browser does', () => {
        assert.equal(
          canadianFrenchText,
          FRENCH['{{count, number}} page_other'].replace(COUNT_PLACEHOLDER, `1${noBreakSpace}000`),
        );
      });

      it('should group its thousands as the locale of France does when the tag is malformed', () => {
        assert.equal(malformedTagText, frenchText);
      });
    });
  });
});
