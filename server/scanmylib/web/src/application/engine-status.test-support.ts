import type { ServerStatus } from '../domain/server-status.ts';
import type { PageVisibility, ServerStatusSource } from './engine-status.ts';

interface PendingRequest {
  readonly resolve: (status: ServerStatus) => void;
  readonly reject: (failure: Error) => void;
}

export interface FakeStatusSource extends ServerStatusSource {
  readonly requestCount: () => number;
  readonly answer: (status: ServerStatus) => void;
  readonly fail: (failure: Error) => void;
}

export function createFakeStatusSource(): FakeStatusSource {
  const waiting: PendingRequest[] = [];
  let requestCount = 0;
  function takeOldest(): PendingRequest {
    const oldest = waiting.shift();
    if (oldest === undefined) throw new Error('No request of the status is waiting for an answer');
    return oldest;
  }
  return {
    readStatus() {
      requestCount += 1;
      return new Promise((resolve, reject) => {
        waiting.push({ resolve, reject });
      });
    },
    requestCount: () => requestCount,
    answer: (status) => takeOldest().resolve(status),
    fail: (failure) => takeOldest().reject(failure),
  };
}

export interface FakePageVisibility extends PageVisibility {
  readonly watcherCount: () => number;
  readonly show: () => void;
  readonly hide: () => void;
}

export function createFakePageVisibility(isVisible: boolean): FakePageVisibility {
  let visible = isVisible;
  const watchers = new Set<() => void>();
  function change(next: boolean): void {
    visible = next;
    for (const watcher of [...watchers]) watcher();
  }
  return {
    isVisible: () => visible,
    watch(listener) {
      const watcher = () => listener();
      watchers.add(watcher);
      return () => {
        watchers.delete(watcher);
      };
    },
    watcherCount: () => watchers.size,
    show: () => change(true),
    hide: () => change(false),
  };
}

// The promises that an answer settles run their continuations before this resolves.
export function settle(): Promise<void> {
  return new Promise((resolve) => {
    setImmediate(resolve);
  });
}
