import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { SAMPLE_DOCUMENT_ID, SAMPLE_PAGE_ID } from '../../domain/page-details.test-support.ts';
import type { PageDetails } from '../../domain/page-details.ts';
import { decodePageDetails, decodePageHtml } from './page-details-decoder.ts';

const readingBody = (): Record<string, unknown> => {
  return { engine: 'example-engine', duration_s: 2.3, at: '2026-11-14T15:32:00+00:00', images: 2, chars: 1234 };
};

// A page of GET /api/pages/{id}, as docs/API.md gives it.
const pageBody = (): Record<string, unknown> => {
  return {
    id: SAMPLE_PAGE_ID,
    document_id: SAMPLE_DOCUMENT_ID,
    key: 'p0011',
    session_id: '6b1f0c3e-63c1-4a3f-9d43-0f1b0c9a1b2c',
    seq: 3,
    captured_at: '2026-11-14T15:31:00+00:00',
    uploaded_at: '2026-11-14T15:31:05+00:00',
    status: 'done',
    error: null,
    number: 11,
    number_end: null,
    page_label: '11',
    number_source: 'detected',
    detected_numbers: ['11'],
    hint_number: 10,
    manual_number: null,
    excluded: false,
    duplicate_of: null,
    in_document: true,
    position: null,
    placement: 'number',
    rotation: 90,
    width: 1011,
    height: 800,
    ocr: readingBody(),
    thumb_url: `/api/pages/${SAMPLE_PAGE_ID}/thumb`,
    image_url: `/api/pages/${SAMPLE_PAGE_ID}/image`,
    markdown: 'Example text.',
  };
};

const DECODED_PAGE: PageDetails = {
  id: SAMPLE_PAGE_ID,
  documentId: SAMPLE_DOCUMENT_ID,
  key: 'p0011',
  sessionId: '6b1f0c3e-63c1-4a3f-9d43-0f1b0c9a1b2c',
  sequence: 3,
  capturedAt: '2026-11-14T15:31:00+00:00',
  uploadedAt: '2026-11-14T15:31:05+00:00',
  status: 'done',
  error: null,
  number: 11,
  numberEnd: null,
  pageLabel: '11',
  numberSource: 'detected',
  detectedNumbers: ['11'],
  hintNumber: 10,
  manualNumber: null,
  isExcluded: false,
  duplicateOf: null,
  placement: 'number',
  rotation: 90,
  width: 1011,
  height: 800,
  reading: {
    engine: 'example-engine',
    durationSeconds: 2.3,
    readAt: '2026-11-14T15:32:00+00:00',
    illustrationCount: 2,
    characterCount: 1234,
  },
  imageUrl: `/api/pages/${SAMPLE_PAGE_ID}/image`,
  markdown: 'Example text.',
};

describe('The page details decoder', () => {
  describe('The decodePageDetails() function', () => {
    describe('When the answer has the documented shape', () => {
      let page: PageDetails;
      beforeEach(() => {
        page = decodePageDetails(pageBody());
      });

      it('should give each field that the page screen shows its value, and leave out the others', () => {
        assert.deepEqual(page, DECODED_PAGE);
      });
    });

    describe('When the answer holds a field this UI does not know', () => {
      let page: PageDetails;
      beforeEach(() => {
        page = decodePageDetails({ ...pageBody(), lens: 'wide' });
      });

      it('should ignore it, so that a newer api still serves this UI', () => {
        assert.deepEqual(page, DECODED_PAGE);
      });
    });

    describe('When the text of the page is not read yet', () => {
      let page: PageDetails;
      beforeEach(() => {
        page = decodePageDetails({ ...pageBody(), status: 'queued', ocr: null });
      });

      it('should give no reading', () => {
        assert.equal(page.reading, null);
      });
    });

    describe('When an older reading did not record some of its values', () => {
      let page: PageDetails;
      beforeEach(() => {
        const reading = { engine: null, duration_s: null, at: null, images: null, chars: null };
        page = decodePageDetails({ ...pageBody(), ocr: reading });
      });

      it('should keep their absence', () => {
        assert.deepEqual(page.reading, {
          engine: null,
          durationSeconds: null,
          readAt: null,
          illustrationCount: null,
          characterCount: null,
        });
      });
    });

    describe('When the answer lacks a field', () => {
      let act: () => PageDetails;
      beforeEach(() => {
        const { markdown: _markdown, ...body } = pageBody();
        act = () => decodePageDetails(body);
      });

      it('should refuse it, naming the field', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid markdown" });
      });
    });

    describe('When a number read on the page has the wrong type', () => {
      let act: () => PageDetails;
      beforeEach(() => {
        act = () => decodePageDetails({ ...pageBody(), detected_numbers: ['11', 12] });
      });

      it('should refuse it, naming the number', () => {
        assert.throws(act, {
          name: 'ResponseShapeError',
          message: "The api's answer holds no valid detected_numbers[1]",
        });
      });
    });

    describe('When a value of the reading has the wrong type', () => {
      let act: () => PageDetails;
      beforeEach(() => {
        act = () => decodePageDetails({ ...pageBody(), ocr: { ...readingBody(), chars: '1234' } });
      });

      it('should refuse it, naming the value', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid ocr.chars" });
      });
    });

    describe('When the address of the scan is not one of the api', () => {
      let act: () => PageDetails;
      beforeEach(() => {
        act = () => decodePageDetails({ ...pageBody(), image_url: 'https://example.invalid/scan.jpg' });
      });

      it('should refuse it, so that no outside address reaches an image or a link', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid image_url" });
      });
    });
  });

  describe('The decodePageHtml() function', () => {
    describe('When the answer holds the HTML', () => {
      let sanitizedHtml: string;
      beforeEach(() => {
        sanitizedHtml = decodePageHtml({ html: '<p>Example text.</p>' });
      });

      it('should give it as it is', () => {
        assert.equal(sanitizedHtml, '<p>Example text.</p>');
      });
    });

    describe('When the answer holds no HTML', () => {
      let act: () => string;
      beforeEach(() => {
        act = () => decodePageHtml({ markdown: 'Example text.' });
      });

      it('should refuse it, naming the field', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid html" });
      });
    });
  });
});
