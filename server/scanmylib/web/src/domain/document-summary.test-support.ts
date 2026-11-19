import type { DocumentStats, DocumentSummary, PageCoverage } from './document-summary.ts';

export interface DocumentChanges {
  readonly id?: string;
  readonly title?: string;
  readonly author?: string;
  readonly kind?: string;
  readonly stats?: Partial<DocumentStats>;
  readonly coverage?: Partial<PageCoverage>;
}

export const sampleDocument = (changes: DocumentChanges = {}): DocumentSummary => {
  return {
    id: changes.id ?? '95bbeb79-4351-432f-a53c-d3658892ff50',
    title: changes.title ?? 'Example Book',
    author: changes.author ?? 'Jane Doe',
    kind: changes.kind ?? 'book',
    updatedAt: '2026-11-14T15:41:03+00:00',
    stats: {
      pageCount: 11,
      doneCount: 11,
      queuedCount: 0,
      processingCount: 0,
      errorCount: 0,
      excludedCount: 0,
      duplicateCount: 0,
      ...changes.stats,
    },
    coverage: {
      ranges: [
        [11, 15],
        [18, 21],
      ],
      label: '11–15, 18–21',
      gaps: [[16, 17]],
      lowestNumber: 11,
      highestNumber: 21,
      unnumberedCount: 0,
      ...changes.coverage,
    },
    coverThumbnailUrl: '/api/pages/de215798-031a-4b20-a867-49c12e3baabe/thumb',
  };
};
