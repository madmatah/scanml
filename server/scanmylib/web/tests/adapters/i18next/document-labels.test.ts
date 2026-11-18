// French is written only in the French catalog, so these tests compare with its entries instead of quoting it.
import assert from 'node:assert/strict';
import { before, beforeEach, describe, it } from 'node:test';

import type { TFunction } from 'i18next';
import frenchCatalog from '../../../locales/fr.json' with { type: 'json' };
import { CATALOGS } from '../../../src/adapters/i18next/catalogs.ts';
import {
  type DocumentKindChoice,
  documentKindChoices,
  documentKindLabel,
} from '../../../src/adapters/i18next/document-labels.ts';
import { createLocalizationFor } from './browser-languages.ts';

describe('The document labels', () => {
  let englishT: TFunction;
  before(async () => {
    englishT = (await createLocalizationFor(['en-US'], CATALOGS)).i18next.t;
  });

  describe('The documentKindLabel() function', () => {
    describe('When the kind is a book', () => {
      let label: string;
      beforeEach(() => {
        label = documentKindLabel(englishT, 'book');
      });

      it('should name it', () => {
        assert.equal(label, 'Book');
      });
    });

    describe('When the kind is a document', () => {
      let label: string;
      beforeEach(() => {
        label = documentKindLabel(englishT, 'document');
      });

      it('should call it other, as the form that creates it does', () => {
        assert.equal(label, 'Other');
      });
    });

    describe('When the kind is one that the UI does not know', () => {
      let label: string;
      beforeEach(() => {
        label = documentKindLabel(englishT, 'magazine');
      });

      it('should show it as the api names it, so that a newer api never shows an empty chip', () => {
        assert.equal(label, 'magazine');
      });
    });

    describe('When the UI is in French', () => {
      let label: string;
      beforeEach(async () => {
        const { i18next } = await createLocalizationFor(['fr-FR'], CATALOGS);
        label = documentKindLabel(i18next.t, 'book');
      });

      it('should name it from the catalog', () => {
        assert.equal(label, frenchCatalog.Book);
      });
    });
  });

  describe('The documentKindChoices() function', () => {
    let choices: DocumentKindChoice[];
    beforeEach(() => {
      choices = documentKindChoices(englishT);
    });

    it('should offer the book first, then the other documents', () => {
      assert.deepEqual(choices, [
        { kind: 'book', label: 'Book' },
        { kind: 'document', label: 'Other' },
      ]);
    });
  });
});
