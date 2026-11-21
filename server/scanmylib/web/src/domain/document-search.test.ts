import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  documentsMatching,
  documentsOfKind,
  documentsShown,
  type EmptySearchReason,
  emptySearchReason,
  type KindFilter,
  kindFilterInEffect,
  SEARCH_THRESHOLD_DOCUMENTS,
  showsKindFilter,
  showsSearch,
} from './document-search.ts';
import { sampleDocument } from './document-summary.test-support.ts';
import type { DocumentSummary } from './document-summary.ts';

const ACCENTED_TITLE = 'Caf\u00e9 Notes';
const FIELD_NOTES = sampleDocument({ id: 'field-notes', title: 'Field Notes', author: 'John Roe' });
const CAFE_NOTES = sampleDocument({ id: 'cafe-notes', title: ACCENTED_TITLE, author: '' });
const EXAMPLE_BOOK = sampleDocument({ id: 'example-book', title: 'Example Book', author: 'Jane Doe' });
const LIBRARY = [FIELD_NOTES, CAFE_NOTES, EXAMPLE_BOOK];
const FIELD_JOURNAL = sampleDocument({ id: 'field-journal', title: 'Field Journal', author: '', kind: 'document' });
const BOOKS_AND_JOURNAL = [FIELD_NOTES, EXAMPLE_BOOK, FIELD_JOURNAL];

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

  describe('The documentsOfKind() function', () => {
    const NOTES = sampleDocument({ id: 'notes', kind: 'document' });
    const ATLAS = sampleDocument({ id: 'atlas', kind: 'atlas' });
    const MIXED_LIBRARY = [EXAMPLE_BOOK, NOTES, ATLAS];
    const situations: { situation: string; filter: KindFilter; rule: string; expectedIds: string[] }[] = [
      {
        situation: 'When every kind is asked for',
        filter: 'all',
        rule: 'should keep every document',
        expectedIds: ['example-book', 'notes', 'atlas'],
      },
      {
        situation: 'When the books are asked for',
        filter: 'book',
        rule: 'should keep the books alone',
        expectedIds: ['example-book'],
      },
      {
        situation: 'When the other kinds are asked for',
        filter: 'other',
        rule: 'should keep every document that is not a book, a kind the UI does not know included',
        expectedIds: ['notes', 'atlas'],
      },
    ];

    for (const { situation, filter, rule, expectedIds } of situations) {
      describe(situation, () => {
        let found: readonly DocumentSummary[];
        beforeEach(() => {
          found = documentsOfKind(MIXED_LIBRARY, filter);
        });

        it(rule, () => {
          assert.deepEqual(idsOf(found), expectedIds);
        });
      });
    }
  });

  describe('The showsKindFilter() function', () => {
    const books = libraryOf(SEARCH_THRESHOLD_DOCUMENTS);
    const situations: { situation: string; documents: DocumentSummary[]; rule: string; expected: boolean }[] = [
      {
        situation: 'When the library holds books alone',
        documents: books,
        rule: 'should hide the filter, which would have nothing to tell apart',
        expected: false,
      },
      {
        situation: 'When the library mixes books and other documents',
        documents: [...books.slice(1), sampleDocument({ id: 'notes', kind: 'document' })],
        rule: 'should show the filter',
        expected: true,
      },
      {
        situation: 'When a library too small for the search mixes kinds',
        documents: [sampleDocument({ id: 'book' }), sampleDocument({ id: 'notes', kind: 'document' })],
        rule: 'should hide the filter with the search, since the documents fit in a glance',
        expected: false,
      },
    ];

    for (const { situation, documents, rule, expected } of situations) {
      describe(situation, () => {
        let isShown: boolean;
        beforeEach(() => {
          isShown = showsKindFilter(documents);
        });

        it(rule, () => {
          assert.equal(isShown, expected);
        });
      });
    }
  });

  describe('The kindFilterInEffect() function', () => {
    const mixedLibrary = [...libraryOf(SEARCH_THRESHOLD_DOCUMENTS - 1), FIELD_JOURNAL];
    const situations: {
      situation: string;
      documents: DocumentSummary[];
      filter: KindFilter;
      rule: string;
      expected: KindFilter;
    }[] = [
      {
        situation: 'When the filter is shown',
        documents: mixedLibrary,
        filter: 'other',
        rule: 'should keep the kind chosen',
        expected: 'other',
      },
      {
        situation: 'When the library no longer mixes kinds',
        documents: libraryOf(SEARCH_THRESHOLD_DOCUMENTS),
        filter: 'other',
        rule: 'should show every kind, since a hidden filter would keep documents out of sight',
        expected: 'all',
      },
      {
        situation: 'When the library has not loaded',
        documents: [],
        filter: 'book',
        rule: 'should show every kind',
        expected: 'all',
      },
    ];

    for (const { situation, documents, filter, rule, expected } of situations) {
      describe(situation, () => {
        let filterInEffect: KindFilter;
        beforeEach(() => {
          filterInEffect = kindFilterInEffect(documents, filter);
        });

        it(rule, () => {
          assert.equal(filterInEffect, expected);
        });
      });
    }
  });

  describe('The documentsShown() function', () => {
    const situations: { situation: string; filter: KindFilter; query: string; rule: string; expectedIds: string[] }[] =
      [
        {
          situation: 'When a kind is chosen and a query typed',
          filter: 'book',
          query: 'field',
          rule: 'should keep the documents of that kind that match the query',
          expectedIds: ['field-notes'],
        },
        {
          situation: 'When the other kinds are chosen and a query typed',
          filter: 'other',
          query: 'field',
          rule: 'should keep the documents that are not books and match the query',
          expectedIds: ['field-journal'],
        },
        {
          situation: 'When a kind is chosen without a query',
          filter: 'other',
          query: '',
          rule: 'should keep every document of that kind',
          expectedIds: ['field-journal'],
        },
        {
          situation: 'When every kind is shown and a query typed',
          filter: 'all',
          query: 'field',
          rule: 'should keep every document that matches the query, whatever its kind',
          expectedIds: ['field-notes', 'field-journal'],
        },
      ];

    for (const { situation, filter, query, rule, expectedIds } of situations) {
      describe(situation, () => {
        let shown: readonly DocumentSummary[];
        beforeEach(() => {
          shown = documentsShown(BOOKS_AND_JOURNAL, filter, query);
        });

        it(rule, () => {
          assert.deepEqual(idsOf(shown), expectedIds);
        });
      });
    }
  });

  describe('The emptySearchReason() function', () => {
    const books = [FIELD_NOTES, EXAMPLE_BOOK];
    const situations: {
      situation: string;
      documents: DocumentSummary[];
      filter: KindFilter;
      query: string;
      rule: string;
      expected: EmptySearchReason | null;
    }[] = [
      {
        situation: 'When documents are shown',
        documents: BOOKS_AND_JOURNAL,
        filter: 'book',
        query: 'notes',
        rule: 'should give no reason',
        expected: null,
      },
      {
        situation: 'When the library is empty',
        documents: [],
        filter: 'all',
        query: '',
        rule: 'should give no reason, since the screen says that the library is empty',
        expected: null,
      },
      {
        situation: 'When no document is of the kind chosen and no query is typed',
        documents: books,
        filter: 'other',
        query: '  ',
        rule: 'should blame the kind',
        expected: 'no-document-of-kind',
      },
      {
        situation: 'When every kind is shown and nothing matches the query',
        documents: BOOKS_AND_JOURNAL,
        filter: 'all',
        query: 'atlas',
        rule: 'should blame the query',
        expected: 'no-document-matches',
      },
      {
        situation: 'When a kind is chosen and only documents of another kind match the query',
        documents: BOOKS_AND_JOURNAL,
        filter: 'book',
        query: 'journal',
        rule: 'should blame the kind and the query together, since the other kind holds a match',
        expected: 'no-document-of-kind-matches',
      },
      {
        situation: 'When a kind is chosen and no document of any kind matches the query',
        documents: BOOKS_AND_JOURNAL,
        filter: 'book',
        query: 'atlas',
        rule: 'should blame the query alone, since no other kind would show a match',
        expected: 'no-document-matches',
      },
    ];

    for (const { situation, documents, filter, query, rule, expected } of situations) {
      describe(situation, () => {
        let reason: EmptySearchReason | null;
        beforeEach(() => {
          reason = emptySearchReason(documents, filter, query);
        });

        it(rule, () => {
          assert.equal(reason, expected);
        });
      });
    }
  });
});
