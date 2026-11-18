import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { decodeDocumentList, decodeDocumentSummary } from '../../../src/adapters/http-api/document-summary-decoder.ts';
import type { DocumentSummary } from '../../../src/domain/document-summary.ts';

// A document of GET /api/documents and of PUT /api/documents/{id}, as docs/API.md gives it.
function documentBody(): Record<string, unknown> {
  return {
    id: '95bbeb79-4351-432f-a53c-d3658892ff50',
    slug: 'example-book',
    title: 'Example Book',
    author: 'Jane Doe',
    kind: 'book',
    notes: '',
    unwarp: true,
    created_at: '2026-11-14T15:30:00+00:00',
    updated_at: '2026-11-14T15:41:03+00:00',
    stats: { pages: 11, done: 10, queued: 1, processing: 0, error: 0, excluded: 0, duplicates: 1 },
    coverage: { ranges: [[11, 15]], label: '11–15', gaps: [[16, 17]], min: 11, max: 15, unnumbered: 0 },
    cover_thumb_url: '/api/pages/de215798-031a-4b20-a867-49c12e3baabe/thumb',
    folder: '/data/USER/scanmylib/library/example-book',
  };
}

const DECODED_DOCUMENT: DocumentSummary = {
  id: '95bbeb79-4351-432f-a53c-d3658892ff50',
  title: 'Example Book',
  author: 'Jane Doe',
  kind: 'book',
  updatedAt: '2026-11-14T15:41:03+00:00',
  stats: {
    pageCount: 11,
    doneCount: 10,
    queuedCount: 1,
    processingCount: 0,
    errorCount: 0,
    excludedCount: 0,
    duplicateCount: 1,
  },
  coverage: { ranges: [[11, 15]], label: '11–15', gaps: [[16, 17]], lowestNumber: 11, unnumberedCount: 0 },
  coverThumbnailUrl: '/api/pages/de215798-031a-4b20-a867-49c12e3baabe/thumb',
};

describe('The document summary decoder', () => {
  describe('The decodeDocumentSummary() function', () => {
    describe('When the answer has the documented shape', () => {
      let document: DocumentSummary;
      beforeEach(() => {
        document = decodeDocumentSummary(documentBody());
      });

      it('should give each field the library shows its value, and leave out the others', () => {
        assert.deepEqual(document, DECODED_DOCUMENT);
      });
    });

    describe('When the document has no page yet', () => {
      let document: DocumentSummary;
      beforeEach(() => {
        const body = documentBody();
        body.coverage = { ranges: [], label: '', gaps: [], min: null, max: null, unnumbered: 0 };
        body.cover_thumb_url = null;
        document = decodeDocumentSummary(body);
      });

      it('should keep the absence of a lowest number and of a cover', () => {
        assert.deepEqual(
          { lowestNumber: document.coverage.lowestNumber, coverThumbnailUrl: document.coverThumbnailUrl },
          { lowestNumber: null, coverThumbnailUrl: null },
        );
      });
    });

    describe('When the answer holds a field the client does not know', () => {
      let document: DocumentSummary;
      beforeEach(() => {
        document = decodeDocumentSummary({ ...documentBody(), language: 'en' });
      });

      it('should ignore it, so that the api can grow without breaking the UI', () => {
        assert.deepEqual(document, DECODED_DOCUMENT);
      });
    });

    describe('When the answer lacks a field', () => {
      let act: () => DocumentSummary;
      beforeEach(() => {
        const { updated_at: _updatedAt, ...body } = documentBody();
        act = () => decodeDocumentSummary(body);
      });

      it('should refuse it, naming the field', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid updated_at" });
      });
    });

    describe('When a count has the wrong type', () => {
      let act: () => DocumentSummary;
      beforeEach(() => {
        const body = documentBody();
        body.stats = { pages: '11', done: 10, queued: 1, processing: 0, error: 0, excluded: 0, duplicates: 1 };
        act = () => decodeDocumentSummary(body);
      });

      it('should refuse it, naming the field with its path', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid stats.pages" });
      });
    });

    describe('When a range of the coverage is not a pair of numbers', () => {
      let act: () => DocumentSummary;
      beforeEach(() => {
        const body = documentBody();
        body.coverage = { ranges: [[11, 15, 18]], label: '', gaps: [], min: 11, max: 18, unnumbered: 0 };
        act = () => decodeDocumentSummary(body);
      });

      it('should refuse it, naming the range with its place', () => {
        assert.throws(act, {
          name: 'ResponseShapeError',
          message: "The api's answer holds no valid coverage.ranges[0]",
        });
      });
    });

    describe('When the cover is an address outside the api', () => {
      let act: () => DocumentSummary;
      beforeEach(() => {
        const body = documentBody();
        body.cover_thumb_url = 'https://example.invalid/cover.png';
        act = () => decodeDocumentSummary(body);
      });

      it('should refuse it, so that no image of the library loads from elsewhere', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid cover_thumb_url" });
      });
    });
  });

  describe('The decodeDocumentList() function', () => {
    describe('When the answer lists documents', () => {
      let documents: DocumentSummary[];
      beforeEach(() => {
        documents = decodeDocumentList({ documents: [documentBody(), { ...documentBody(), id: 'second' }] });
      });

      it('should decode each, in the order of the api', () => {
        assert.deepEqual(
          documents.map((document) => document.id),
          ['95bbeb79-4351-432f-a53c-d3658892ff50', 'second'],
        );
      });
    });

    describe('When the list is not a list', () => {
      let act: () => DocumentSummary[];
      beforeEach(() => {
        act = () => decodeDocumentList({ documents: documentBody() });
      });

      it('should refuse it', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid documents" });
      });
    });

    describe('When a document of the list lacks a field', () => {
      let act: () => DocumentSummary[];
      beforeEach(() => {
        const { title: _title, ...second } = documentBody();
        act = () => decodeDocumentList({ documents: [documentBody(), second] });
      });

      it('should refuse the list, naming the document by its place', () => {
        assert.throws(act, {
          name: 'ResponseShapeError',
          message: "The api's answer holds no valid documents[1].title",
        });
      });
    });
  });
});
