import { NetworkError } from '../../../application/api-errors.ts';
import type { DocumentSummary } from '../../../domain/document-summary.ts';

export type LibraryLoad =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly failure: unknown }
  | { readonly phase: 'loaded'; readonly documents: readonly DocumentSummary[] };

export interface LoadFailure {
  readonly load: LibraryLoad;
  readonly isToldInToast: boolean;
}

export const SEARCH_THRESHOLD_DOCUMENTS = 4;

export const showsSearch = (load: LibraryLoad): boolean => {
  return load.phase === 'loaded' && load.documents.length >= SEARCH_THRESHOLD_DOCUMENTS;
};

export const afterLoadFailure = (load: LibraryLoad, failure: unknown): LoadFailure => {
  if (load.phase === 'loaded') return { load, isToldInToast: !(failure instanceof NetworkError) };
  return { load: { phase: 'failed', failure }, isToldInToast: false };
};
