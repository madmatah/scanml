import { localIsoString } from '../domain/formatting.ts';
import { checkPhoto, type PhotoRejection } from '../domain/photo-upload.ts';
import { ApiError } from './api-errors.ts';
import type { UuidSource } from './uuid-source.ts';

export interface PhotoFile {
  readonly name: string;
  readonly size: number;
  readonly type: string;
  readonly lastModified: number;
}

export interface PageUpload<F extends PhotoFile> {
  readonly documentId: string;
  readonly pageId: string;
  readonly sessionId: string;
  readonly seq: number;
  readonly capturedAt: string;
  readonly file: F;
}

export interface PageUploader<F extends PhotoFile> {
  uploadPage(upload: PageUpload<F>, onProgress: (ratio: number) => void): Promise<void>;
}

export interface Clock {
  readTimeMilliseconds(): number;
}

export type UploadState = 'pending' | 'uploading' | 'sent' | 'failed' | 'rejected';

export type UploadProblem = PhotoRejection | { readonly kind: 'upload-failed'; readonly failure: unknown };

export interface UploadItem {
  readonly pageId: string;
  readonly documentId: string;
  readonly name: string;
  readonly size: number;
  readonly state: UploadState;
  readonly progress: number;
  readonly problem: UploadProblem | null;
}

export interface FailedUpload extends UploadItem {
  readonly problem: UploadProblem;
}

export interface SettledUploads {
  readonly sentCount: number;
  readonly failedCount: number;
  readonly rejectedCount: number;
}

// The photos of one call share a capture session, numbered from its first sequence number in the order given; the
// server infers a missing page number from the neighbors of a page within its session.
export interface CaptureSeries {
  readonly sessionId: string;
  readonly firstSeq: number;
}

export interface UploadQueue<F extends PhotoFile> {
  subscribe(listener: () => void): () => void;
  getSnapshot(): readonly UploadItem[];
  watchSettled(listener: (settled: SettledUploads) => void): () => void;
  add(documentId: string, files: readonly F[], series: CaptureSeries): void;
  isBusy(documentId?: string): boolean;
  retryFailed(documentId: string): void;
  clearFinished(documentId: string): void;
}

export interface UploadSummary {
  readonly sentCount: number;
  readonly acceptedCount: number;
  readonly waitingCount: number;
  readonly uploading: readonly UploadItem[];
  readonly failed: readonly FailedUpload[];
  readonly failures: readonly FailedUpload[];
  readonly isBusy: boolean;
  readonly progress: number;
}

export const CONCURRENT_UPLOADS = 2;
export const PERMANENT_FAILURES: readonly number[] = [400, 404, 409, 413, 415, 422];

interface QueuedUpload<F extends PhotoFile> extends UploadItem {
  // The request still to send, dropped once it can no longer be sent, so that the browser frees the photo.
  readonly request: PageUpload<F> | null;
}

const NOTHING_SETTLED: SettledUploads = { sentCount: 0, failedCount: 0, rejectedCount: 0 };

const isActive = (item: UploadItem): boolean => {
  return item.state === 'pending' || item.state === 'uploading';
};

const hasProblem = (item: UploadItem): item is FailedUpload => {
  return item.problem !== null;
};

export const settledCount = (settled: SettledUploads): number => {
  return settled.sentCount + settled.failedCount + settled.rejectedCount;
};

export const hasFailures = (settled: SettledUploads): boolean => {
  return settled.failedCount + settled.rejectedCount > 0;
};

export const uploadsOf = (items: readonly UploadItem[], documentId: string): UploadItem[] => {
  return items.filter((item) => item.documentId === documentId);
};

const sentCountOf = (items: readonly UploadItem[], documentId: string): number => {
  return items.filter((item) => item.documentId === documentId && item.state === 'sent').length;
};

export const watchSentUploads = (
  queue: Pick<UploadQueue<PhotoFile>, 'subscribe' | 'getSnapshot'>,
  documentId: string,
  onMoreSent: () => void,
): (() => void) => {
  let sentCount = sentCountOf(queue.getSnapshot(), documentId);
  return queue.subscribe(() => {
    const nextSentCount = sentCountOf(queue.getSnapshot(), documentId);
    if (nextSentCount > sentCount) onMoreSent();
    sentCount = nextSentCount;
  });
};

// The names that cameras and scanners give their files sort in shooting order.
export const inFileNameOrder = <F extends PhotoFile>(files: readonly F[]): F[] => {
  return [...files].sort((first, second) => first.name.localeCompare(second.name, undefined, { numeric: true }));
};

export const summarizeUploads = (items: readonly UploadItem[]): UploadSummary => {
  const inState = (state: UploadState) => items.filter((item) => item.state === state);
  const uploading = inState('uploading');
  const failed = inState('failed').filter(hasProblem);
  const rejected = inState('rejected').filter(hasProblem);
  const waitingCount = inState('pending').length;
  let totalBytes = 0;
  let sentBytes = 0;
  for (const item of items) {
    if (item.state !== 'rejected') totalBytes += item.size;
    if (item.state === 'sent') sentBytes += item.size;
    if (item.state === 'uploading') sentBytes += item.size * item.progress;
  }
  return {
    sentCount: inState('sent').length,
    acceptedCount: items.length - inState('rejected').length,
    waitingCount,
    uploading,
    failed,
    failures: [...failed, ...rejected],
    isBusy: uploading.length + waitingCount > 0,
    progress: totalBytes === 0 ? 1 : sentBytes / totalBytes,
  };
};

// The queue lives outside the screens: uploads go on while the user browses, and a document's screen shows their
// progress whenever it is open. The server is idempotent on a page's id, so a failed upload is sent again safely.
export const createUploadQueue = <F extends PhotoFile>(
  uploader: PageUploader<F>,
  uuids: UuidSource,
  clock: Clock,
): UploadQueue<F> => {
  let items: readonly QueuedUpload<F>[] = [];
  let runningCount = 0;
  let settled = NOTHING_SETTLED;
  const listeners = new Set<() => void>();
  const settledListeners = new Set<(settled: SettledUploads) => void>();

  const replace = (next: readonly QueuedUpload<F>[]): void => {
    items = next;
    for (const listener of [...listeners]) listener();
  };

  const update = (pageId: string, change: Partial<QueuedUpload<F>>): void => {
    replace(items.map((item) => (item.pageId === pageId ? { ...item, ...change } : item)));
  };

  const isBusy = (documentId?: string): boolean => {
    return items.some((item) => (documentId === undefined || item.documentId === documentId) && isActive(item));
  };

  const settleIfIdle = (): void => {
    if (isBusy() || settledCount(settled) === 0) return;
    const counts = settled;
    settled = NOTHING_SETTLED;
    for (const listener of [...settledListeners]) listener(counts);
  };

  const send = async (request: PageUpload<F>): Promise<void> => {
    const { pageId } = request;
    runningCount += 1;
    update(pageId, { state: 'uploading' });
    let outcome: Partial<QueuedUpload<F>>;
    try {
      await uploader.uploadPage(request, (progress) => update(pageId, { progress }));
      outcome = { state: 'sent', progress: 1, request: null };
      settled = { ...settled, sentCount: settled.sentCount + 1 };
    } catch (failure) {
      const problem: UploadProblem = { kind: 'upload-failed', failure };
      if (failure instanceof ApiError && PERMANENT_FAILURES.includes(failure.status)) {
        outcome = { state: 'rejected', problem, request: null };
        settled = { ...settled, rejectedCount: settled.rejectedCount + 1 };
      } else {
        outcome = { state: 'failed', problem };
        settled = { ...settled, failedCount: settled.failedCount + 1 };
      }
    }
    runningCount -= 1;
    update(pageId, outcome);
    pump();
    settleIfIdle();
  };

  const pump = (): void => {
    while (runningCount < CONCURRENT_UPLOADS) {
      const request = items.find((item) => item.state === 'pending')?.request;
      if (request === undefined || request === null) return;
      // send tells its failures through the item's state, so its promise never rejects.
      void send(request);
    }
  };

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getSnapshot: () => items,
    watchSettled(listener) {
      settledListeners.add(listener);
      return () => {
        settledListeners.delete(listener);
      };
    },
    add(documentId, files, { sessionId, firstSeq }) {
      const added = files.map((file, index): QueuedUpload<F> => {
        const seq = firstSeq + index;
        const pageId = uuids.createUuid();
        const problem = checkPhoto(file);
        if (problem !== null) settled = { ...settled, rejectedCount: settled.rejectedCount + 1 };
        const capturedAt = localIsoString(new Date(file.lastModified || clock.readTimeMilliseconds()));
        return {
          pageId,
          documentId,
          name: file.name || `photo-${seq}`,
          size: file.size,
          state: problem === null ? 'pending' : 'rejected',
          progress: 0,
          problem,
          request: problem === null ? { documentId, pageId, sessionId, seq, capturedAt, file } : null,
        };
      });
      replace([...items, ...added]);
      pump();
      settleIfIdle();
    },
    isBusy,
    retryFailed(documentId) {
      let retriedCount = 0;
      const next = items.map((item): QueuedUpload<F> => {
        if (item.documentId !== documentId || item.state !== 'failed') return item;
        retriedCount += 1;
        return { ...item, state: 'pending', progress: 0, problem: null };
      });
      // The failures not told yet are told again with the outcome of their retry.
      settled = { ...settled, failedCount: Math.max(0, settled.failedCount - retriedCount) };
      replace(next);
      pump();
    },
    clearFinished(documentId) {
      replace(items.filter((item) => item.documentId !== documentId || isActive(item)));
    },
  };
};
