import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { sampleDocument } from '../domain/document-summary.test-support.ts';
import type { DocumentSummary } from '../domain/document-summary.ts';
import { ApiError, NetworkError } from './api-errors.ts';
import { createLibraryLoader, type LibraryLoad, type LibraryLoader } from './library-loader.ts';

interface PendingList {
  readonly signal: AbortSignal;
  readonly answer: (documents: readonly DocumentSummary[]) => Promise<void>;
  readonly fail: (failure: unknown) => Promise<void>;
}

interface Arrangement {
  readonly lists: PendingList[];
  readonly leaving: AbortController;
  readonly loads: LibraryLoad[];
  readonly refreshFailures: unknown[];
  readonly loader: LibraryLoader;
}

const INTERNAL_SERVER_ERROR = 500;
const FIRST_DOCUMENTS = [sampleDocument({ id: 'example-book' })];
const REFRESHED_DOCUMENTS = [sampleDocument({ id: 'example-book' }), sampleDocument({ id: 'field-notes' })];

const settle = async (): Promise<void> => {
  await new Promise((resolve) => setImmediate(resolve));
};

const arrange = (): Arrangement => {
  const lists: PendingList[] = [];
  const leaving = new AbortController();
  const loads: LibraryLoad[] = [];
  const refreshFailures: unknown[] = [];
  const loader = createLibraryLoader({
    listDocuments: (signal) =>
      new Promise((resolve, reject) => {
        lists.push({
          signal,
          answer: async (documents) => {
            resolve(documents);
            await settle();
          },
          fail: async (failure) => {
            reject(failure);
            await settle();
          },
        });
      }),
    leaving: leaving.signal,
    onChange: (load) => loads.push(load),
    onRefreshFailed: (failure) => refreshFailures.push(failure),
  });
  return { lists, leaving, loads, refreshFailures, loader };
};

const showFirstList = async (): Promise<Arrangement> => {
  const arrangement = arrange();
  arrangement.loader.load();
  await arrangement.lists[0]?.answer(FIRST_DOCUMENTS);
  return arrangement;
};

describe('The library loader', () => {
  describe('The load() method', () => {
    describe('When the documents come', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await showFirstList();
      });

      it('should show them', () => {
        assert.deepEqual(arrangement.loads, [{ phase: 'loaded', documents: FIRST_DOCUMENTS }]);
      });

      it('should list them with the signal of the screen', () => {
        assert.equal(arrangement.lists[0]?.signal, arrangement.leaving.signal);
      });
    });

    describe('When the first load fails', () => {
      const failure = new ApiError(INTERNAL_SERVER_ERROR, 'disk full');
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.loader.load();
        await arrangement.lists[0]?.fail(failure);
      });

      it('should show the failure in place of the list, without telling it otherwise', () => {
        assert.deepEqual(
          { loads: arrangement.loads, refreshFailures: arrangement.refreshFailures },
          { loads: [{ phase: 'failed', failure }], refreshFailures: [] },
        );
      });

      describe('When the load is tried again', () => {
        beforeEach(() => {
          arrangement.loader.load();
        });

        it('should keep the failure shown, with no loading state, until the load settles', () => {
          assert.deepEqual(arrangement.loads, [{ phase: 'failed', failure }]);
        });

        describe('When the documents then come', () => {
          beforeEach(async () => {
            await arrangement.lists[1]?.answer(FIRST_DOCUMENTS);
          });

          it('should show them in place of the failure', () => {
            assert.deepEqual(arrangement.loads.slice(1), [{ phase: 'loaded', documents: FIRST_DOCUMENTS }]);
          });
        });
      });
    });

    describe('When a reload fails while the list shows', () => {
      const failure = new ApiError(INTERNAL_SERVER_ERROR, 'disk full');
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await showFirstList();
        arrangement.loader.load();
        await arrangement.lists[1]?.fail(failure);
      });

      it('should keep the list, and tell the failure', () => {
        assert.deepEqual(
          { loads: arrangement.loads, refreshFailures: arrangement.refreshFailures },
          { loads: [{ phase: 'loaded', documents: FIRST_DOCUMENTS }], refreshFailures: [failure] },
        );
      });
    });

    describe('When a reload cannot reach the server while the list shows', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await showFirstList();
        arrangement.loader.load();
        await arrangement.lists[1]?.fail(new NetworkError());
      });

      it('should keep the list and tell nothing, since the banner already says the server is unreachable', () => {
        assert.deepEqual(
          { loads: arrangement.loads, refreshFailures: arrangement.refreshFailures },
          { loads: [{ phase: 'loaded', documents: FIRST_DOCUMENTS }], refreshFailures: [] },
        );
      });
    });

    describe('When a load is asked while another runs', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.loader.load();
        arrangement.loader.load();
        await arrangement.lists[0]?.answer(FIRST_DOCUMENTS);
        await arrangement.lists[1]?.answer(REFRESHED_DOCUMENTS);
      });

      it('should send both, and show each list as it comes', () => {
        assert.deepEqual(arrangement.loads, [
          { phase: 'loaded', documents: FIRST_DOCUMENTS },
          { phase: 'loaded', documents: REFRESHED_DOCUMENTS },
        ]);
      });
    });

    describe('When the screen is left before the answer', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.loader.load();
        arrangement.leaving.abort();
        await arrangement.lists[0]?.fail(new DOMException('The screen was left.', 'AbortError'));
      });

      it('should show and tell nothing', () => {
        assert.deepEqual(
          { loads: arrangement.loads, refreshFailures: arrangement.refreshFailures },
          { loads: [], refreshFailures: [] },
        );
      });
    });
  });
});
