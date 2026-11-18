import type { DocumentWithPages } from '../domain/document-details.ts';
import { isNotFound } from './document-loader.ts';

export type ReaderLoad =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly failure: unknown }
  | {
      readonly phase: 'loaded';
      readonly document: DocumentWithPages;
      readonly sanitizedHtml: string;
      readonly returnsToPageRead: boolean;
    };

export interface ReaderLoaderOptions {
  readonly readDocument: (signal: AbortSignal) => Promise<DocumentWithPages>;
  readonly readDocumentHtml: (signal: AbortSignal) => Promise<string>;
  readonly leaving: AbortSignal;
  readonly onChange: (load: ReaderLoad) => void;
  readonly onRefreshFailed: (failure: unknown) => void;
}

export interface ReaderLoader {
  load(): Promise<void>;
}

export function createReaderLoader({
  readDocument,
  readDocumentHtml,
  leaving,
  onChange,
  onRefreshFailed,
}: ReaderLoaderOptions): ReaderLoader {
  let isShown = false;
  let isLoading = false;

  async function load(): Promise<void> {
    if (isLoading) return;
    isLoading = true;
    const returnsToPageRead = !isShown;
    if (!isShown) onChange({ phase: 'loading' });
    try {
      const [document, sanitizedHtml] = await Promise.all([readDocument(leaving), readDocumentHtml(leaving)]);
      isShown = true;
      onChange({ phase: 'loaded', document, sanitizedHtml, returnsToPageRead });
    } catch (failure) {
      if (leaving.aborted) return;
      if (isShown && !isNotFound(failure)) {
        onRefreshFailed(failure);
        return;
      }
      isShown = false;
      onChange({ phase: 'failed', failure });
    } finally {
      isLoading = false;
    }
  }

  return { load };
}
