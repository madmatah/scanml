import type { DocumentSummary, PageCoverage } from '../../domain/document-summary.ts';
import { type ResponseFields, ResponseShapeError, readResponseFields } from './response-fields.ts';

// The image of a cover reaches an <img> as it is: it may only be one of the api's own files.
const API_PATH_PREFIX = '/api/';

function decodeApiPath(path: string | null, field: string): string | null {
  if (path !== null && !path.startsWith(API_PATH_PREFIX)) throw new ResponseShapeError(field);
  return path;
}

function decodeCoverage(coverage: ResponseFields): PageCoverage {
  return {
    ranges: coverage.numberPairs('ranges'),
    label: coverage.string('label'),
    gaps: coverage.numberPairs('gaps'),
    lowestNumber: coverage.nullableNumber('min'),
    unnumberedCount: coverage.number('unnumbered'),
  };
}

function decodeDocument(document: ResponseFields): DocumentSummary {
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
    coverThumbnailUrl: decodeApiPath(document.nullableString('cover_thumb_url'), 'cover_thumb_url'),
  };
}

export function decodeDocumentSummary(body: unknown): DocumentSummary {
  return decodeDocument(readResponseFields(body));
}

export function decodeDocumentList(body: unknown): DocumentSummary[] {
  return readResponseFields(body).objectList('documents').map(decodeDocument);
}
