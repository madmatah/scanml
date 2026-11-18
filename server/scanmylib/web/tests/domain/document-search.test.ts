import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { documentsMatching } from '../../src/domain/document-search.ts';
import type { DocumentSummary } from '../../src/domain/document-summary.ts';
import { sampleDocument } from './document-summary-samples.ts';

const ACCENTED_TITLE = 'Caf\u00e9 Notes';
const FIELD_NOTES = sampleDocument({ id: 'field-notes', title: 'Field Notes', author: 'John Roe' });
const CAFE_NOTES = sampleDocument({ id: 'cafe-notes', title: ACCENTED_TITLE, author: '' });
const EXAMPLE_BOOK = sampleDocument({ id: 'example-book', title: 'Example Book', author: 'Jane Doe' });
const LIBRARY = [FIELD_NOTES, CAFE_NOTES, EXAMPLE_BOOK];

function idsOf(documents: readonly DocumentSummary[]): string[] {
  return documents.map((document) => document.id);
}

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
});
