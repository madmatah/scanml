import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { SEARCH_THRESHOLD_DOCUMENTS } from './document-search.ts';
import { sampleDocument } from './document-summary.test-support.ts';
import type { DocumentSummary } from './document-summary.ts';
import { isLibraryView, type LibraryView, libraryViewInEffect } from './library-view.ts';

const libraryOf = (documentCount: number): DocumentSummary[] => {
  return Array.from({ length: documentCount }, (_, position) => sampleDocument({ id: `document-${position}` }));
};

describe('The library view', () => {
  describe('The isLibraryView() function', () => {
    const situations: { situation: string; text: string; rule: string; expected: boolean }[] = [
      { situation: 'When the text names the cards', text: 'cards', rule: 'should accept it', expected: true },
      { situation: 'When the text names the list', text: 'list', rule: 'should accept it', expected: true },
      {
        situation: 'When the text names no view, as an older or a tampered value would',
        text: 'table',
        rule: 'should refuse it',
        expected: false,
      },
    ];

    for (const { situation, text, rule, expected } of situations) {
      describe(situation, () => {
        let isView: boolean;
        beforeEach(() => {
          isView = isLibraryView(text);
        });

        it(rule, () => {
          assert.equal(isView, expected);
        });
      });
    }
  });

  describe('The libraryViewInEffect() function', () => {
    const situations: { situation: string; documents: DocumentSummary[]; rule: string; expected: LibraryView }[] = [
      {
        situation: 'When the list is chosen and the library shows its toolbar',
        documents: libraryOf(SEARCH_THRESHOLD_DOCUMENTS),
        rule: 'should show the list',
        expected: 'list',
      },
      {
        situation: 'When the list is chosen and the library is too small for its toolbar',
        documents: libraryOf(SEARCH_THRESHOLD_DOCUMENTS - 1),
        rule: 'should show the cards, since the switch that would bring them back is hidden',
        expected: 'cards',
      },
    ];

    for (const { situation, documents, rule, expected } of situations) {
      describe(situation, () => {
        let view: LibraryView;
        beforeEach(() => {
          view = libraryViewInEffect(documents, 'list');
        });

        it(rule, () => {
          assert.equal(view, expected);
        });
      });
    }
  });
});
