import type { DocumentSummary, PageCoverage } from '../../domain/document-summary.ts';
import { type ResponseFields, readResponseFields } from './response-fields.ts';

const decodeCoverage = (coverage: ResponseFields): PageCoverage => {
  return {
    ranges: coverage.numberPairs('ranges'),
    label: coverage.string('label'),
    gaps: coverage.numberPairs('gaps'),
    lowestNumber: coverage.nullableNumber('min'),
    highestNumber: coverage.nullableNumber('max'),
    unnumberedCount: coverage.number('unnumbered'),
  };
};

export const readDocumentSummary = (document: ResponseFields): DocumentSummary => {
  const stats = document.object('stats');
  return {
    id: document.string('id'),
    title: document.string('title'),
    author: document.string('author'),
    kind: document.string('kind'),
    updatedAt: document.string('updated_at'),
    stats: {
      pageCount: stats.number('pages'),
      doneCount: stats.number('done'),
      queuedCount: stats.number('queued'),
      processingCount: stats.number('processing'),
      errorCount: stats.number('error'),
      excludedCount: stats.number('excluded'),
      duplicateCount: stats.number('duplicates'),
    },
    coverage: decodeCoverage(document.object('coverage')),
    coverThumbnailUrl: document.nullableApiPath('cover_thumb_url'),
  };
};

export const decodeDocumentSummary = (body: unknown): DocumentSummary => {
  return readDocumentSummary(readResponseFields(body));
};

export const decodeDocumentList = (body: unknown): DocumentSummary[] => {
  return readResponseFields(body).objectList('documents').map(readDocumentSummary);
};
