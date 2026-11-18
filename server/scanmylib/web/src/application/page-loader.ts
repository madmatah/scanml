import type { DocumentWithPages } from '../domain/document-details.ts';
import { isBeingRead, type PageDetails } from '../domain/page-details.ts';
import { NetworkError } from './api-errors.ts';
import { isNotFound } from './document-loader.ts';
import type { CancelTask, Scheduler } from './scheduler.ts';

export type PageLoad =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly failure: unknown }
  | {
      readonly phase: 'loaded';
      readonly page: PageDetails;
      readonly document: DocumentWithPages;
      readonly sanitizedHtml: string;
    };

export interface PageLoaderOptions {
  readonly readPage: (signal: AbortSignal) => Promise<PageDetails>;
  readonly readDocument: (documentId: string, signal: AbortSignal) => Promise<DocumentWithPages>;
  readonly readPageHtml: (signal: AbortSignal) => Promise<string>;
  readonly scheduler: Scheduler;
  readonly leaving: AbortSignal;
  readonly onChange: (load: PageLoad) => void;
  readonly onRefreshFailed: (failure: unknown) => void;
}

export interface PageLoader {
  load(): Promise<void>;
}

// While the PC reads the text of the page, the page refreshes itself at the pace of the engine's status.
export const REFRESH_INTERVAL_MILLISECONDS = 3000;

export function createPageLoader({
  readPage,
  readDocument,
  readPageHtml,
  scheduler,
  leaving,
  onChange,
  onRefreshFailed,
}: PageLoaderOptions): PageLoader {
  let latestPage: PageDetails | null = null;
  let hasShownPage = false;
  let loading: Promise<void> | null = null;
  let isReloadQueued = false;
  let cancelRefresh: CancelTask | null = null;

  function stopRefresh(): void {
    cancelRefresh?.();
    cancelRefresh = null;
  }

  async function fetchPage(): Promise<void> {
    stopRefresh();
    try {
      const page = await readPage(leaving);
      latestPage = page;
      const [document, sanitizedHtml] = await Promise.all([
        readDocument(page.documentId, leaving),
        page.status === 'done' ? readPageHtml(leaving) : '',
      ]);
      hasShownPage = true;
      onChange({ phase: 'loaded', page, document, sanitizedHtml });
    } catch (failure) {
      if (leaving.aborted) return;
      if (!hasShownPage || isNotFound(failure)) {
        onChange({ phase: 'failed', failure });
        return;
      }
      // While the api cannot be reached, the banner of the engine's status says so, and the last page stays on screen.
      if (!(failure instanceof NetworkError)) onRefreshFailed(failure);
    }
    if (latestPage !== null && isBeingRead(latestPage.status)) {
      cancelRefresh = scheduler.schedule(() => {
        void load();
      }, REFRESH_INTERVAL_MILLISECONDS);
    }
  }

  function load(): Promise<void> {
    if (loading !== null) {
      isReloadQueued = true;
      return loading;
    }
    const current = fetchPage().finally(() => {
      loading = null;
      if (isReloadQueued && !leaving.aborted) {
        isReloadQueued = false;
        void load();
      }
    });
    loading = current;
    return current;
  }

  leaving.addEventListener('abort', stopRefresh, { once: true });

  return { load };
}
