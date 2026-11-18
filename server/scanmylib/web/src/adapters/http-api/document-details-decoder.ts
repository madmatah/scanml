import type { DocumentDetails, DocumentWithPages, PageSummary } from '../../domain/document-details.ts';
import { readDocumentSummary } from './document-summary-decoder.ts';
import { type ResponseFields, readResponseFields } from './response-fields.ts';

function readDocumentDetails(document: ResponseFields): DocumentDetails {
  return {
    ...readDocumentSummary(document),
    slug: document.string('slug'),
    notes: document.string('notes'),
    unwarp: document.boolean('unwarp'),
    folder: document.string('folder'),
  };
}

function readPageSummary(page: ResponseFields): PageSummary {
  return {
    id: page.string('id'),
    status: page.string('status'),
    pageLabel: page.nullableString('page_label'),
    numberSource: page.nullableString('number_source'),
    isExcluded: page.boolean('excluded'),
    duplicateOf: page.nullableString('duplicate_of'),
    isInDocument: page.boolean('in_document'),
    placement: page.nullableString('placement'),
    rotation: page.number('rotation'),
    thumbnailUrl: page.apiPath('thumb_url'),
  };
}

export function decodeDocumentDetails(body: unknown): DocumentDetails {
  return readDocumentDetails(readResponseFields(body));
}

export function decodeDocumentWithPages(body: unknown): DocumentWithPages {
  const document = readResponseFields(body);
  return { ...readDocumentDetails(document), pages: document.objectList('pages').map(readPageSummary) };
}
