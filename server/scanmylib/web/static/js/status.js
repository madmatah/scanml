import { ApiError, api, NetworkError } from './api.js';

const POLL_INTERVAL_MS = 3000;

/**
 * Polls GET /api/status every 3 s while the tab is visible and dispatches a
 * `change` event after each attempt. Feeds the header badge, the warning
 * banners and the screens that refresh when the OCR queue moves.
 */
export class StatusMonitor extends EventTarget {
  /** Last successful /api/status payload, or null. */
  status = null;

  /** 'unknown' until the first answer, then 'online' or 'offline'. */
  connection = 'unknown';

  #running = false;
  #timer = 0;
  #generation = 0;
  #inFlight = null;

  constructor() {
    super();
    document.addEventListener('visibilitychange', () => {
      if (!this.#running) return;
      if (document.hidden) this.#cancelTimer();
      else this.#poll();
    });
  }

  start() {
    if (this.#running) return;
    this.#running = true;
    this.#poll();
  }

  stop() {
    this.#running = false;
    this.#generation += 1;
    this.#cancelTimer();
    this.status = null;
    this.connection = 'unknown';
    this.dispatchEvent(new Event('change'));
  }

  /** Fetches the status now; concurrent calls share the same request. */
  refresh() {
    this.#inFlight ??= this.#fetch().finally(() => {
      this.#inFlight = null;
    });
    return this.#inFlight;
  }

  /** Number of pages waiting for or undergoing OCR, or null when unknown. */
  get pendingPages() {
    const queue = this.status?.queue;
    return queue ? (queue.queued ?? 0) + (queue.processing ?? 0) : null;
  }

  async #fetch() {
    try {
      this.status = await api.status();
      this.connection = 'online';
    } catch (error) {
      if (error instanceof NetworkError || (error instanceof ApiError && error.status >= 500)) {
        this.connection = 'offline';
      }
      // A 401 is handled globally (back to the login screen).
    }
    if (this.#running) this.dispatchEvent(new Event('change'));
  }

  async #poll() {
    const generation = ++this.#generation;
    this.#cancelTimer();
    await this.refresh();
    if (this.#running && !document.hidden && generation === this.#generation) {
      this.#timer = setTimeout(() => this.#poll(), POLL_INTERVAL_MS);
    }
  }

  #cancelTimer() {
    clearTimeout(this.#timer);
    this.#timer = 0;
  }
}
