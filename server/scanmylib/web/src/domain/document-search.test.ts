import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { documentsMatching, SEARCH_THRESHOLD_DOCUMENTS, showsSearch } from './document-search.ts';
import { sampleDocument } from './document-summary.test-support.ts';
import type { DocumentSummary } from './document-summary.ts';

const ACCENTED_TITLE = 'Caf\u00e9 Notes';
const FIELD_NOTES = sampleDocument({ id: 'field-notes', title: 'Field Notes', author: 'John Roe' });
const CAFE_NOTES = sampleDocument({ id: 'cafe-notes', title: ACCENTED_TITLE, author: '' });
const EXAMPLE_BOOK = sampleDocument({ id: 'example-book', title: 'Example Book', author: 'Jane Doe' });
const LIBRARY = [FIELD_NOTES, CAFE_NOTES, EXAMPLE_BOOK];

const idsOf = (documents: readonly DocumentSummary[]): string[] => {
  return documents.map((document) => document.id);
};

const libraryOf = (documentCount: number): DocumentSummary[] => {
  return Array.from({ length: documentCount }, (_, position) => sampleDocument({ id: `document-${position}` }));
};

describe('The document search', () => {
  describe('The documentsMatching() function', () => {
    const situations: { situation: string; query: string; rule: string; expectedIds: string[] }[] = [
      {
        situation: 'When the query is empty or blank',
        query: '   ',
        rule: 'should keep every document',
        expectedIds: ['field-notes', 'cafe-notes', 'example-book'],
      },
      {
        situation: 'When the query is part of a title, in another case',
        query: 'NOTES',
        rule: 'should find the documents whose title holds it, whatever the case',
        expectedIds: ['field-notes', 'cafe-notes'],
      },
      {
        situation: 'When the query leaves out the accents of a title',
        query: 'cafe',
        rule: 'should find the title with its accents',
        expectedIds: ['cafe-notes'],
      },
      {
        situation: 'When the query names an author',
        query: 'jane',
        rule: 'should find the documents of that author',
        expectedIds: ['example-book'],
      },
      {
        situation: 'When the query is surrounded by spaces',
        query: '  roe ',
        rule: 'should search for the query without them',
        expectedIds: ['field-notes'],
      },
      {
        situation: 'When nothing holds the query',
        query: 'atlas',
        rule: 'should find no document',
        expectedIds: [],
      },
    ];

    for (const { situation, query, rule, expectedIds } of situations) {
      describe(situation, () => {
        let found: readonly DocumentSummary[];
        beforeEach(() => {
          found = documentsMatching(LIBRARY, query);
        });

        it(rule, () => {
          assert.deepEqual(idsOf(found), expectedIds);
        });
      });
    }
  });

  describe('The showsSearch() function', () => {
    const situations: { situation: string; documents: DocumentSummary[]; rule: string; expected: boolean }[] = [
      {
        situation: 'When the library holds one document less than the threshold',
        documents: libraryOf(SEARCH_THRESHOLD_DOCUMENTS - 1),
        rule: 'should hide the search, since the documents fit in a glance',
        expected: false,
      },
      {
        situation: 'When the library holds as many documents as the threshold',
        documents: libraryOf(SEARCH_THRESHOLD_DOCUMENTS),
        rule: 'should show the search',
        expected: true,
      },
    ];

    for (const { situation, documents, rule, expected } of situations) {
      describe(situation, () => {
        let isShown: boolean;
        beforeEach(() => {
          isShown = showsSearch(documents);
        });

        it(rule, () => {
          assert.equal(isShown, expected);
        });
      });
    }
  });
});
