import type { DocumentSummary } from '../domain/document-summary.ts';
import { NetworkError } from './api-errors.ts';

export type LibraryLoad =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly failure: unknown }
  | { readonly phase: 'loaded'; readonly documents: readonly DocumentSummary[] };

export interface LibraryLoaderOptions {
  readonly listDocuments: (signal: AbortSignal) => Promise<readonly DocumentSummary[]>;
  readonly leaving: AbortSignal;
  readonly onChange: (load: LibraryLoad) => void;
  readonly onRefreshFailed: (failure: unknown) => void;
}

export interface LibraryLoader {
  load(): void;
}

export const createLibraryLoader = ({
  listDocuments,
  leaving,
  onChange,
  onRefreshFailed,
}: LibraryLoaderOptions): LibraryLoader => {
  let current: LibraryLoad = { phase: 'loading' };

  const enter = (next: LibraryLoad): void => {
    current = next;
    onChange(next);
  };

  const fetchDocuments = async (): Promise<void> => {
    try {
      enter({ phase: 'loaded', documents: await listDocuments(leaving) });
    } catch (failure) {
      if (leaving.aborted) return;
      if (current.phase !== 'loaded') {
        enter({ phase: 'failed', failure });
        return;
      }
      if (!(failure instanceof NetworkError)) onRefreshFailed(failure);
    }
  };

  const load = (): void => {
    // fetchDocuments handles its own failures, so its promise never rejects.
    void fetchDocuments();
  };

  return { load };
};
