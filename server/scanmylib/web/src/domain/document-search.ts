import type { DocumentSummary } from './document-summary.ts';

export const SEARCH_THRESHOLD_DOCUMENTS = 4;

export const normalizedForSearch = (text: string): string => {
  return text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase();
};

export const documentsMatching = (documents: readonly DocumentSummary[], query: string): readonly DocumentSummary[] => {
  const needle = normalizedForSearch(query.trim());
  if (needle === '') return documents;
  return documents.filter((document) => normalizedForSearch(`${document.title} ${document.author}`).includes(needle));
};

export const showsSearch = (documents: readonly DocumentSummary[]): boolean => {
  return documents.length >= SEARCH_THRESHOLD_DOCUMENTS;
};

export const KIND_FILTERS = ['all', 'book', 'other'] as const;

export type KindFilter = (typeof KIND_FILTERS)[number];

// A kind the UI does not know yet, which a later api may send, falls with the documents that are not books.
const kindGroupOf = (document: DocumentSummary): Exclude<KindFilter, 'all'> => {
  return document.kind === 'book' ? 'book' : 'other';
};

export const documentsOfKind = (
  documents: readonly DocumentSummary[],
  filter: KindFilter,
): readonly DocumentSummary[] => {
  if (filter === 'all') return documents;
  return documents.filter((document) => kindGroupOf(document) === filter);
};

export const showsKindFilter = (documents: readonly DocumentSummary[]): boolean => {
  return showsSearch(documents) && new Set(documents.map(kindGroupOf)).size > 1;
};

export const kindFilterInEffect = (documents: readonly DocumentSummary[], filter: KindFilter): KindFilter => {
  return showsKindFilter(documents) ? filter : 'all';
};

export const documentsShown = (
  documents: readonly DocumentSummary[],
  filter: KindFilter,
  query: string,
): readonly DocumentSummary[] => {
  return documentsMatching(documentsOfKind(documents, filter), query);
};

export type EmptySearchReason = 'no-document-of-kind' | 'no-document-matches' | 'no-document-of-kind-matches';

export const emptySearchReason = (
  documents: readonly DocumentSummary[],
  filter: KindFilter,
  query: string,
): EmptySearchReason | null => {
  if (documents.length === 0 || documentsShown(documents, filter, query).length > 0) return null;
  if (query.trim() === '') return 'no-document-of-kind';
  if (filter !== 'all' && documentsMatching(documents, query).length > 0) return 'no-document-of-kind-matches';
  return 'no-document-matches';
};
