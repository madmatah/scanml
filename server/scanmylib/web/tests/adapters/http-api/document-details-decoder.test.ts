import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  decodeDocumentDetails,
  decodeDocumentHtml,
  decodeDocumentWithPages,
} from '../../../src/adapters/http-api/document-details-decoder.ts';
import type { DocumentDetails, DocumentWithPages, PageSummary } from '../../../src/domain/document-details.ts';

const PAGE_ID = 'de215798-031a-4b20-a867-49c12e3baabe';

// A document of PATCH /api/documents/{id}, as docs/API.md gives it.
function documentBody(): Record<string, unknown> {
  return {
    id: '95bbeb79-4351-432f-a53c-d3658892ff50',
    slug: 'example-book',
    title: 'Example Book',
    author: 'Jane Doe',
    kind: 'book',
    notes: 'Second edition',
    unwarp: true,
    created_at: '2026-11-14T15:30:00+00:00',
    updated_at: '2026-11-14T15:41:03+00:00',
    stats: { pages: 1, done: 1, queued: 0, processing: 0, error: 0, excluded: 0, duplicates: 0 },
    coverage: { ranges: [[11, 11]], label: '11', gaps: [], min: 11, max: 11, unnumbered: 0 },
    cover_thumb_url: `/api/pages/${PAGE_ID}/thumb`,
    folder: '/data/USER/scanmylib/library/example-book',
  };
}

// A page of GET /api/documents/{id}, as docs/API.md gives it.
function pageBody(): Record<string, unknown> {
  return {
    id: PAGE_ID,
    document_id: '95bbeb79-4351-432f-a53c-d3658892ff50',
    key: 'p0011',
    session_id: '6b1f0c3e-63c1-4a3f-9d43-0f1b0c9a1b2c',
    seq: 1,
    captured_at: '2026-11-14T15:31:00+00:00',
    uploaded_at: '2026-11-14T15:31:05+00:00',
    status: 'done',
    error: null,
    number: 11,
    number_end: null,
    page_label: '11',
    number_source: 'detected',
    detected_numbers: [11],
    hint_number: null,
    manual_number: null,
    excluded: false,
    duplicate_of: null,
    in_document: true,
    position: 0,
    placement: 'number',
    rotation: 90,
    width: 800,
    height: 1011,
    ocr: null,
    thumb_url: `/api/pages/${PAGE_ID}/thumb`,
    image_url: `/api/pages/${PAGE_ID}/image`,
  };
}

const DECODED_PAGE: PageSummary = {
  id: PAGE_ID,
  key: 'p0011',
  status: 'done',
  pageLabel: '11',
  numberEnd: null,
  numberSource: 'detected',
  isExcluded: false,
  duplicateOf: null,
  isInDocument: true,
  placement: 'number',
  position: 0,
  rotation: 90,
  thumbnailUrl: `/api/pages/${PAGE_ID}/thumb`,
  readAt: null,
};

describe('The document details decoder', () => {
  describe('The decodeDocumentDetails() function', () => {
    describe('When the answer has the documented shape', () => {
      let document: DocumentDetails;
      beforeEach(() => {
        document = decodeDocumentDetails(documentBody());
      });

      it('should add what the document screen shows to the summary', () => {
        assert.deepEqual(
          { slug: document.slug, notes: document.notes, unwarp: document.unwarp, folder: document.folder },
          {
            slug: 'example-book',
            notes: 'Second edition',
            unwarp: true,
            folder: '/data/USER/scanmylib/library/example-book',
          },
        );
      });

      it('should keep the summary of the document', () => {
        assert.deepEqual(
          { title: document.title, highestNumber: document.coverage.highestNumber },
          { title: 'Example Book', highestNumber: 11 },
        );
      });
    });

    describe('When the answer lacks a field', () => {
      let act: () => DocumentDetails;
      beforeEach(() => {
        const { folder: _folder, ...body } = documentBody();
        act = () => decodeDocumentDetails(body);
      });

      it('should refuse it, naming the field', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid folder" });
      });
    });

    describe('When the choice to flatten the pages has the wrong type', () => {
      let act: () => DocumentDetails;
      beforeEach(() => {
        act = () => decodeDocumentDetails({ ...documentBody(), unwarp: 'yes' });
      });

      it('should refuse it, naming the field', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid unwarp" });
      });
    });
  });

  describe('The decodeDocumentWithPages() function', () => {
    describe('When the answer has the documented shape', () => {
      let document: DocumentWithPages;
      beforeEach(() => {
        document = decodeDocumentWithPages({ ...documentBody(), pages: [pageBody()] });
      });

      it('should give each field of a page that the document screen shows its value, and leave out the others', () => {
        assert.deepEqual(document.pages, [DECODED_PAGE]);
      });
    });

    describe('When a page has no number', () => {
      let page: PageSummary | undefined;
      beforeEach(() => {
        const body = { ...pageBody(), page_label: null, number_source: null, placement: null, in_document: false };
        page = decodeDocumentWithPages({ ...documentBody(), pages: [body] }).pages[0];
      });

      it('should keep the absence of its label, of its source and of its place', () => {
        assert.deepEqual(
          { pageLabel: page?.pageLabel, numberSource: page?.numberSource, placement: page?.placement },
          { pageLabel: null, numberSource: null, placement: null },
        );
      });
    });

    describe('When a page keeps its automatic place and holds two numbers', () => {
      let page: PageSummary | undefined;
      beforeEach(() => {
        const body = { ...pageBody(), number: 11, number_end: 12, page_label: '11-12', position: null };
        page = decodeDocumentWithPages({ ...documentBody(), pages: [body] }).pages[0];
      });

      it('should keep its last number and the absence of a place chosen by hand', () => {
        assert.deepEqual({ numberEnd: page?.numberEnd, position: page?.position }, { numberEnd: 12, position: null });
      });
    });

    describe('When the text of a page is read', () => {
      const readAt = '2026-11-14T15:32:00+00:00';
      let page: PageSummary | undefined;
      beforeEach(() => {
        const reading = { engine: 'example-engine', duration_s: 2.3, at: readAt, images: 1, chars: 1234 };
        page = decodeDocumentWithPages({ ...documentBody(), pages: [{ ...pageBody(), ocr: reading }] }).pages[0];
      });

      it('should keep when it was read, which versions its illustrations', () => {
        assert.equal(page?.readAt, readAt);
      });
    });

    describe('When a page lacks its reading', () => {
      let act: () => DocumentWithPages;
      beforeEach(() => {
        const { ocr: _ocr, ...body } = pageBody();
        act = () => decodeDocumentWithPages({ ...documentBody(), pages: [body] });
      });

      it('should refuse it, naming the field with its path', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid pages[0].ocr" });
      });
    });

    describe('When the place of a page has the wrong type', () => {
      let act: () => DocumentWithPages;
      beforeEach(() => {
        act = () => decodeDocumentWithPages({ ...documentBody(), pages: [{ ...pageBody(), position: '0' }] });
      });

      it('should refuse it, naming the field with its path', () => {
        assert.throws(act, {
          name: 'ResponseShapeError',
          message: "The api's answer holds no valid pages[0].position",
        });
      });
    });

    describe('When a page holds a field the client does not know', () => {
      let document: DocumentWithPages;
      beforeEach(() => {
        document = decodeDocumentWithPages({ ...documentBody(), pages: [{ ...pageBody(), language: 'en' }] });
      });

      it('should ignore it, so that the api can grow without breaking the UI', () => {
        assert.deepEqual(document.pages, [DECODED_PAGE]);
      });
    });

    describe('When a page lacks a field', () => {
      let act: () => DocumentWithPages;
      beforeEach(() => {
        const { in_document: _inDocument, ...page } = pageBody();
        act = () => decodeDocumentWithPages({ ...documentBody(), pages: [pageBody(), page] });
      });

      it('should refuse the document, naming the page by its place', () => {
        assert.throws(act, {
          name: 'ResponseShapeError',
          message: "The api's answer holds no valid pages[1].in_document",
        });
      });
    });

    describe('When the rotation of a page has the wrong type', () => {
      let act: () => DocumentWithPages;
      beforeEach(() => {
        act = () => decodeDocumentWithPages({ ...documentBody(), pages: [{ ...pageBody(), rotation: '90' }] });
      });

      it('should refuse it, naming the field with its path', () => {
        assert.throws(act, {
          name: 'ResponseShapeError',
          message: "The api's answer holds no valid pages[0].rotation",
        });
      });
    });

    describe('When the thumbnail of a page is an address outside the api', () => {
      let act: () => DocumentWithPages;
      beforeEach(() => {
        const page = { ...pageBody(), thumb_url: 'https://example.invalid/thumb.png' };
        act = () => decodeDocumentWithPages({ ...documentBody(), pages: [page] });
      });

      it('should refuse it, so that no image of the document loads from elsewhere', () => {
        assert.throws(act, {
          name: 'ResponseShapeError',
          message: "The api's answer holds no valid pages[0].thumb_url",
        });
      });
    });

    describe('When the pages are not a list', () => {
      let act: () => DocumentWithPages;
      beforeEach(() => {
        act = () => decodeDocumentWithPages({ ...documentBody(), pages: pageBody() });
      });

      it('should refuse it', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid pages" });
      });
    });
  });

  describe('The decodeDocumentHtml() function', () => {
    describe('When the answer holds the HTML', () => {
      let sanitizedHtml: string;
      beforeEach(() => {
        sanitizedHtml = decodeDocumentHtml({ html: '<h1>Example Book</h1>' });
      });

      it('should give it as it is', () => {
        assert.equal(sanitizedHtml, '<h1>Example Book</h1>');
      });
    });

    describe('When the answer holds no HTML', () => {
      let act: () => string;
      beforeEach(() => {
        act = () => decodeDocumentHtml({ markdown: '# Example Book' });
      });

      it('should refuse it, naming the field', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid html" });
      });
    });
  });
});
