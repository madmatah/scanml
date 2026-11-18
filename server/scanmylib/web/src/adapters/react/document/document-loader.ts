import { ApiError } from '../../../application/api-errors.ts';
import type { CancelTask, Scheduler } from '../../../application/scheduler.ts';
import { type DocumentWithPages, isTextPending } from '../../../domain/document-details.ts';

export type DocumentLoad =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly failure: unknown }
  | { readonly phase: 'loaded'; readonly document: DocumentWithPages };

export interface DocumentLoaderOptions {
  readonly read: (signal: AbortSignal) => Promise<DocumentWithPages>;
  readonly scheduler: Scheduler;
  readonly isUploading: () => boolean;
  readonly leaving: AbortSignal;
  readonly onChange: (load: DocumentLoad) => void;
  readonly onDeleted: () => void;
}

export interface DocumentLoader {
  load(): void;
  loadAfterUpload(): void;
  replace(document: DocumentWithPages): void;
}

// While the PC reads the text of its pages, the document refreshes itself at the pace of the engine's status.
export const REFRESH_INTERVAL_MILLISECONDS = 3000;
// The pages of photos sent one after another show together, in one load.
export const UPLOAD_RELOAD_DELAY_MILLISECONDS = 400;
const NOT_FOUND = 404;

export function isNotFound(failure: unknown): boolean {
  return failure instanceof ApiError && failure.status === NOT_FOUND;
}

export function createDocumentLoader({
  read,
  scheduler,
  isUploading,
  leaving,
  onChange,
  onDeleted,
}: DocumentLoaderOptions): DocumentLoader {
  let document: DocumentWithPages | null = null;
  let loading: Promise<void> | null = null;
  let isReloadQueued = false;
  let cancelRefresh: CancelTask | null = null;
  let cancelUploadReload: CancelTask | null = null;

  function stopRefresh(): void {
    cancelRefresh?.();
    cancelRefresh = null;
  }

  function stopUploadReload(): void {
    cancelUploadReload?.();
    cancelUploadReload = null;
  }

  function scheduleRefresh(): void {
    stopRefresh();
    if (leaving.aborted || document === null) return;
    if (!isTextPending(document.stats) && !isUploading()) return;
    cancelRefresh = scheduler.schedule(load, REFRESH_INTERVAL_MILLISECONDS);
  }

  function loadAfterUpload(): void {
    stopUploadReload();
    if (leaving.aborted) return;
    cancelUploadReload = scheduler.schedule(() => {
      cancelUploadReload = null;
      load();
    }, UPLOAD_RELOAD_DELAY_MILLISECONDS);
  }

  function show(next: DocumentWithPages): void {
    document = next;
    onChange({ phase: 'loaded', document: next });
  }

  async function fetchDocument(): Promise<void> {
    stopRefresh();
    try {
      show(await read(leaving));
    } catch (failure) {
      if (leaving.aborted) return;
      if (document === null) {
        onChange({ phase: 'failed', failure });
        return;
      }
      if (isNotFound(failure)) {
        onDeleted();
        return;
      }
      // A passing failure keeps the last document on screen, and the next refresh tries again.
    }
    scheduleRefresh();
  }

  // A load asked while another runs comes once more after it, so that its answer is never older than the request.
  function load(): void {
    if (loading !== null) {
      isReloadQueued = true;
      return;
    }
    loading = fetchDocument().finally(() => {
      loading = null;
      if (isReloadQueued && !leaving.aborted) {
        isReloadQueued = false;
        load();
      }
    });
  }

  leaving.addEventListener(
    'abort',
    () => {
      stopRefresh();
      stopUploadReload();
    },
    { once: true },
  );

  return { load, loadAfterUpload, replace: show };
}
