import { type DocumentWithPages, isTextPending } from '../domain/document-details.ts';
import { ApiError } from './api-errors.ts';
import type { CancelTask, Scheduler } from './scheduler.ts';

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
  writeOrder(request: () => Promise<DocumentWithPages>): Promise<DocumentWithPages>;
}

// While the PC reads the text of its pages, the document refreshes itself at the pace of the engine's status.
export const REFRESH_INTERVAL_MILLISECONDS = 3000;
// The pages of photos sent one after another show together, in one load.
export const UPLOAD_RELOAD_DELAY_MILLISECONDS = 400;
const NOT_FOUND = 404;

export const isNotFound = (failure: unknown): boolean => {
  return failure instanceof ApiError && failure.status === NOT_FOUND;
};

export const createDocumentLoader = ({
  read,
  scheduler,
  isUploading,
  leaving,
  onChange,
  onDeleted,
}: DocumentLoaderOptions): DocumentLoader => {
  let document: DocumentWithPages | null = null;
  let loading: Promise<void> | null = null;
  let isReloadQueued = false;
  let cancelRefresh: CancelTask | null = null;
  let cancelUploadReload: CancelTask | null = null;
  // A change of the order and a refresh can cross: a refresh sent before the change, or answered while it is sent,
  // would bring the old order back.
  let orderWriteCount = 0;
  let orderVersion = 0;
  let isReloadAfterWritesQueued = false;

  const stopRefresh = (): void => {
    cancelRefresh?.();
    cancelRefresh = null;
  };

  const stopUploadReload = (): void => {
    cancelUploadReload?.();
    cancelUploadReload = null;
  };

  const scheduleRefresh = (): void => {
    stopRefresh();
    if (leaving.aborted || document === null) return;
    if (!isTextPending(document.stats) && !isUploading()) return;
    cancelRefresh = scheduler.schedule(load, REFRESH_INTERVAL_MILLISECONDS);
  };

  const loadAfterUpload = (): void => {
    stopUploadReload();
    if (leaving.aborted) return;
    cancelUploadReload = scheduler.schedule(() => {
      cancelUploadReload = null;
      load();
    }, UPLOAD_RELOAD_DELAY_MILLISECONDS);
  };

  const show = (next: DocumentWithPages): void => {
    document = next;
    onChange({ phase: 'loaded', document: next });
  };

  const fetchDocument = async (): Promise<void> => {
    stopRefresh();
    const version = orderVersion;
    try {
      const fresh = await read(leaving);
      if (orderWriteCount > 0) isReloadAfterWritesQueued = true;
      else if (version !== orderVersion) isReloadQueued = true;
      else show(fresh);
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
  };

  const load = (): void => {
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
  };

  const writeOrder = async (request: () => Promise<DocumentWithPages>): Promise<DocumentWithPages> => {
    orderWriteCount += 1;
    orderVersion += 1;
    try {
      const written = await request();
      show(written);
      return written;
    } finally {
      orderWriteCount -= 1;
      if (orderWriteCount === 0 && isReloadAfterWritesQueued) {
        isReloadAfterWritesQueued = false;
        load();
      }
    }
  };

  leaving.addEventListener(
    'abort',
    () => {
      stopRefresh();
      stopUploadReload();
    },
    { once: true },
  );

  return { load, loadAfterUpload, replace: show, writeOrder };
};
