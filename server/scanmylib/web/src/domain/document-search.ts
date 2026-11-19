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
