/**
 * Photo uploads from the browser (document screen).
 *
 * Each file becomes a page with a client-generated `page_id`; the server is
 * idempotent on it, so failed uploads can be retried safely. The queue lives
 * outside the screens: uploads continue while the user browses, and the
 * document screen shows their progress whenever it is open.
 *
 * Events: `change` (detail: { documentId }) on any state change, `progress`
 * (same detail) while bytes are sent, and `settled` (detail: counts) when the
 * queue becomes idle.
 */
import { ApiError, uploadPage } from './api.js';
import { errorMessage } from './lib/errors.js';
import { toLocalIsoString } from './lib/format.js';
import { t } from './lib/i18n.js';
import { randomUuid } from './lib/uuid.js';

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_UPLOAD_BYTES = 40 * 1024 * 1024;
const CONCURRENT_UPLOADS = 2;

/** Statuses for which retrying the same request cannot succeed. */
const PERMANENT_FAILURES = [400, 404, 409, 413, 415, 422];

/** Why the server would refuse this file, or null. */
function rejectionReason(file) {
  // Some Android pickers give no MIME type: let the server decide then.
  if (file.type && !ACCEPTED_TYPES.includes(file.type)) {
    return t('Unsupported format (JPEG, PNG or WebP only).');
  }
  if (file.size > MAX_UPLOAD_BYTES) return t('File too large (40 MiB maximum).');
  if (file.size === 0) return t('Empty file.');
  return null;
}

/**
 * Item states: pending → uploading → done | failed (retryable) | rejected
 * (refused by the browser-side checks or permanently by the server).
 */
class UploadQueue extends EventTarget {
  #items = [];
  #running = 0;
  #settledCounts = { done: 0, failed: 0, rejected: 0 };

  /**
   * Queues photos for a document. Files of one call share the capture
   * session `sessionId`, numbered from `firstSeq` in the given order.
   */
  add(documentId, files, { sessionId, firstSeq = 1 }) {
    files.forEach((file, index) => {
      const reason = rejectionReason(file);
      this.#items.push({
        pageId: randomUuid(),
        documentId,
        file: reason ? null : file,
        name: file.name || `photo-${firstSeq + index}`,
        size: file.size,
        sessionId,
        seq: firstSeq + index,
        capturedAt: toLocalIsoString(new Date(file.lastModified || Date.now())),
        state: reason ? 'rejected' : 'pending',
        progress: 0,
        error: reason,
      });
      if (reason) this.#settledCounts.rejected += 1;
    });
    this.#emit('change', documentId);
    this.#pump();
    this.#settleIfIdle();
  }

  /** Items of one document, in the order they were added. */
  items(documentId) {
    return this.#items.filter((item) => item.documentId === documentId);
  }

  /** True while uploads are pending or running, for one document or any. */
  isBusy(documentId) {
    return this.#items.some((item) => (documentId === undefined || item.documentId === documentId)
      && (item.state === 'pending' || item.state === 'uploading'));
  }

  retryFailed(documentId) {
    let retried = 0;
    for (const item of this.items(documentId)) {
      if (item.state !== 'failed') continue;
      item.state = 'pending';
      item.progress = 0;
      item.error = null;
      retried += 1;
    }
    // Failures not reported yet will be counted again with the retry's outcome.
    this.#settledCounts.failed = Math.max(0, this.#settledCounts.failed - retried);
    this.#emit('change', documentId);
    this.#pump();
  }

  /** Removes the finished items (sent, failed or rejected) of a document. */
  clearFinished(documentId) {
    this.#items = this.#items.filter((item) => item.documentId !== documentId
      || item.state === 'pending' || item.state === 'uploading');
    this.#emit('change', documentId);
  }

  #pump() {
    while (this.#running < CONCURRENT_UPLOADS) {
      const item = this.#items.find((candidate) => candidate.state === 'pending');
      if (!item) return;
      this.#upload(item);
    }
  }

  async #upload(item) {
    this.#running += 1;
    item.state = 'uploading';
    this.#emit('change', item.documentId);
    try {
      await uploadPage(item.documentId, item, {
        onProgress: (ratio) => {
          item.progress = ratio;
          this.#emit('progress', item.documentId);
        },
      });
      item.state = 'done';
      item.progress = 1;
      item.file = null; // let the browser free the photo
      this.#settledCounts.done += 1;
    } catch (error) {
      const permanent = error instanceof ApiError && PERMANENT_FAILURES.includes(error.status);
      item.state = permanent ? 'rejected' : 'failed';
      item.error = errorMessage(error, t('Upload refused by the server.'));
      if (permanent) item.file = null;
      this.#settledCounts[item.state] += 1;
    } finally {
      this.#running -= 1;
      this.#emit('change', item.documentId);
      this.#pump();
      this.#settleIfIdle();
    }
  }

  #settleIfIdle() {
    const counts = this.#settledCounts;
    if (this.isBusy() || counts.done + counts.failed + counts.rejected === 0) return;
    this.#settledCounts = { done: 0, failed: 0, rejected: 0 };
    this.dispatchEvent(new CustomEvent('settled', { detail: counts }));
  }

  #emit(type, documentId) {
    this.dispatchEvent(new CustomEvent(type, { detail: { documentId } }));
  }
}

/** The application-wide upload queue. */
export const uploads = new UploadQueue();
