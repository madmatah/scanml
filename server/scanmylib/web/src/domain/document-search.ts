import type { DocumentSummary } from './document-summary.ts';

export function normalizedForSearch(text: string): string {
  return text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase();
}

export function documentsMatching(documents: readonly DocumentSummary[], query: string): readonly DocumentSummary[] {
  const needle = normalizedForSearch(query.trim());
  if (needle === '') return documents;
  return documents.filter((document) => normalizedForSearch(`${document.title} ${document.author}`).includes(needle));
}
