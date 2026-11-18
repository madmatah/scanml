import { NetworkError } from '../../../application/api-errors.ts';
import type { DocumentSummary } from '../../../domain/document-summary.ts';
import type { ServerStatus } from '../../../domain/server-status.ts';

export type LibraryLoad =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly failure: unknown }
  | { readonly phase: 'loaded'; readonly documents: readonly DocumentSummary[] };

export interface LoadFailure {
  readonly load: LibraryLoad;
  readonly isToldInToast: boolean;
}

export const SEARCH_THRESHOLD_DOCUMENTS = 4;

export function showsSearch(load: LibraryLoad): boolean {
  return load.phase === 'loaded' && load.documents.length >= SEARCH_THRESHOLD_DOCUMENTS;
}

export function afterLoadFailure(load: LibraryLoad, failure: unknown): LoadFailure {
  if (load.phase === 'loaded') return { load, isToldInToast: !(failure instanceof NetworkError) };
  return { load: { phase: 'failed', failure }, isToldInToast: false };
}

export function queueKeyOf(status: ServerStatus | null): string | null {
  if (status === null) return null;
  const { queuedCount, processingCount, doneCount, errorCount } = status.queue;
  return [queuedCount, processingCount, doneCount, errorCount].join('/');
}

export function hasQueueMoved(previousKey: string | null, key: string): boolean {
  return previousKey !== null && key !== previousKey;
}
