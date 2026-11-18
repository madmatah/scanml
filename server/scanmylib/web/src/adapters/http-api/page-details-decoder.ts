import type { PageDetails, PageReading } from '../../domain/page-details.ts';
import { type ResponseFields, readResponseFields } from './response-fields.ts';

function readPageReading(reading: ResponseFields): PageReading {
  return {
    engine: reading.nullableString('engine'),
    durationSeconds: reading.nullableNumber('duration_s'),
    readAt: reading.nullableString('at'),
    illustrationCount: reading.nullableNumber('images'),
    characterCount: reading.nullableNumber('chars'),
  };
}

export function decodePageDetails(body: unknown): PageDetails {
  const page = readResponseFields(body);
  const reading = page.nullableObject('ocr');
  return {
    id: page.string('id'),
    documentId: page.string('document_id'),
    key: page.string('key'),
    sessionId: page.nullableString('session_id'),
    sequence: page.nullableNumber('seq'),
    capturedAt: page.string('captured_at'),
    uploadedAt: page.string('uploaded_at'),
    status: page.string('status'),
    error: page.nullableString('error'),
    number: page.nullableNumber('number'),
    numberEnd: page.nullableNumber('number_end'),
    pageLabel: page.nullableString('page_label'),
    numberSource: page.nullableString('number_source'),
    detectedNumbers: page.stringList('detected_numbers'),
    hintNumber: page.nullableNumber('hint_number'),
    manualNumber: page.nullableNumber('manual_number'),
    isExcluded: page.boolean('excluded'),
    duplicateOf: page.nullableString('duplicate_of'),
    placement: page.nullableString('placement'),
    rotation: page.number('rotation'),
    width: page.number('width'),
    height: page.number('height'),
    reading: reading === null ? null : readPageReading(reading),
    imageUrl: page.apiPath('image_url'),
    markdown: page.string('markdown'),
  };
}

export function decodePageHtml(body: unknown): string {
  return readResponseFields(body).string('html');
}
