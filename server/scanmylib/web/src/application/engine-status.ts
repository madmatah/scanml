import type { ServerStatus } from '../domain/server-status.ts';
import { ApiError, NetworkError } from './api-errors.ts';
import type { CancelTask, Scheduler } from './scheduler.ts';

export interface ServerStatusSource {
  readStatus(): Promise<ServerStatus>;
}

export interface PageVisibility {
  isVisible(): boolean;
  watch(listener: () => void): () => void;
}

export type Connection = 'unknown' | 'online' | 'offline';

export interface EngineStatusState {
  readonly connection: Connection;
  readonly status: ServerStatus | null;
}

export interface EngineStatus {
  subscribe(listener: () => void): () => void;
  getSnapshot(): EngineStatusState;
  start(): void;
  stop(): void;
}

export const POLL_INTERVAL_MILLISECONDS = 3000;

const UNKNOWN: EngineStatusState = { connection: 'unknown', status: null };
const FIRST_SERVER_FAILURE = 500;

const isServerUnreachable = (failure: unknown): boolean => {
  return failure instanceof NetworkError || (failure instanceof ApiError && failure.status >= FIRST_SERVER_FAILURE);
};

export const createEngineStatus = (
  source: ServerStatusSource,
  visibility: PageVisibility,
  scheduler: Scheduler,
): EngineStatus => {
  let state = UNKNOWN;
  let isRunning = false;
  let pollCount = 0;
  let inFlight: Promise<void> | null = null;
  let cancelNextPoll: CancelTask | null = null;
  let stopWatching: (() => void) | null = null;
  const listeners = new Set<() => void>();

  const enter = (next: EngineStatusState): void => {
    if (next.connection === state.connection && next.status === state.status) return;
    state = next;
    for (const listener of listeners) listener();
  };

  const cancelScheduledPoll = (): void => {
    cancelNextPoll?.();
    cancelNextPoll = null;
  };

  const fetchStatus = async (): Promise<void> => {
    try {
      const status = await source.readStatus();
      if (isRunning) enter({ connection: 'online', status });
    } catch (failure) {
      // A refused session is the session's to handle, and leaves the connection as it was.
      if (isRunning && isServerUnreachable(failure)) enter({ connection: 'offline', status: state.status });
    }
  };

  const refresh = (): Promise<void> => {
    inFlight ??= fetchStatus().finally(() => {
      inFlight = null;
    });
    return inFlight;
  };

  const poll = async (): Promise<void> => {
    pollCount += 1;
    const thisPoll = pollCount;
    cancelScheduledPoll();
    await refresh();
    if (isRunning && visibility.isVisible() && thisPoll === pollCount) {
      cancelNextPoll = scheduler.schedule(() => {
        // poll handles its own failures, so its promise never rejects.
        void poll();
      }, POLL_INTERVAL_MILLISECONDS);
    }
  };

  const followVisibility = (): void => {
    if (!isRunning) return;
    if (visibility.isVisible()) void poll();
    else cancelScheduledPoll();
  };

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getSnapshot: () => state,
    start() {
      if (isRunning) return;
      isRunning = true;
      stopWatching = visibility.watch(followVisibility);
      void poll();
    },
    stop() {
      isRunning = false;
      pollCount += 1;
      cancelScheduledPoll();
      stopWatching?.();
      stopWatching = null;
      enter(UNKNOWN);
    },
  };
};
