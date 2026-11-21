export type PageRange = readonly [start: number, end: number];

export interface DocumentStats {
  readonly pageCount: number;
  readonly doneCount: number;
  readonly queuedCount: number;
  readonly processingCount: number;
  readonly errorCount: number;
  readonly excludedCount: number;
  readonly duplicateCount: number;
}

export interface PageCoverage {
  readonly ranges: readonly PageRange[];
  readonly label: string;
  readonly gaps: readonly PageRange[];
  readonly lowestNumber: number | null;
  readonly highestNumber: number | null;
  readonly unnumberedCount: number;
}

export interface DocumentSummary {
  readonly id: string;
  readonly title: string;
  readonly author: string;
  readonly kind: string;
  readonly updatedAt: string;
  readonly stats: DocumentStats;
  readonly coverage: PageCoverage;
  readonly coverThumbnailUrl: string | null;
}

export const DOCUMENT_KINDS = ['book', 'document'] as const;

export type DocumentKind = (typeof DOCUMENT_KINDS)[number];

export const isDocumentKind = (kind: string): kind is DocumentKind => {
  return DOCUMENT_KINDS.some((documentKind) => documentKind === kind);
};

export const NEW_DOCUMENT_KIND: DocumentKind = 'book';

export const unwarpsByDefault = (kind: DocumentKind): boolean => {
  return kind === 'book';
};

export const countPages = (documents: readonly DocumentSummary[]): number => {
  return documents.reduce((total, document) => total + document.stats.pageCount, 0);
};

export const formatPageRange = ([start, end]: PageRange): string => {
  return start === end ? String(start) : `${start}–${end}`;
};

export const formatPageRanges = (ranges: readonly PageRange[]): string => {
  return ranges.map(formatPageRange).join(', ');
};
