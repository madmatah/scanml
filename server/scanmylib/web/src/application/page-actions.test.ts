import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { ApiError } from './api-errors.ts';
import {
  createPageActions,
  type PageAction,
  type PageActionOutcome,
  type PageActions,
  type PageDeletion,
} from './page-actions.ts';
import type { PageChanges } from './page-store.ts';

type PageRequest =
  | { readonly kind: 'update'; readonly pageId: string; readonly changes: PageChanges }
  | { readonly kind: 'readAgain'; readonly pageId: string }
  | { readonly kind: 'delete'; readonly pageId: string };

type Observed =
  | { readonly kind: 'request'; readonly request: PageRequest }
  | { readonly kind: 'busy'; readonly isBusy: boolean }
  | { readonly kind: 'outcome'; readonly outcome: PageActionOutcome }
  | { readonly kind: 'deletion'; readonly deletion: PageDeletion }
  | { readonly kind: 'reload' };

interface PendingRequest {
  readonly answer: () => Promise<void>;
  readonly fail: (failure: unknown) => Promise<void>;
}

interface Arrangement {
  readonly observed: Observed[];
  readonly requests: PendingRequest[];
  readonly actions: PageActions;
}

const PAGE_ID = '0b9a6c1e-2f4d-4e8a-9c3b-5d7e1f2a4b6c';
const INTERNAL_SERVER_ERROR = 500;
const SAVED_NUMBER = 12;

const settle = async (): Promise<void> => {
  await new Promise((resolve) => setImmediate(resolve));
};

const arrange = (): Arrangement => {
  const observed: Observed[] = [];
  const requests: PendingRequest[] = [];
  const send = (request: PageRequest): Promise<void> => {
    observed.push({ kind: 'request', request });
    return new Promise((resolve, reject) => {
      requests.push({
        answer: async () => {
          resolve();
          await settle();
        },
        fail: async (failure) => {
          reject(failure);
          await settle();
        },
      });
    });
  };
  const actions = createPageActions({
    pageId: PAGE_ID,
    pages: {
      updatePage: (pageId, changes) => send({ kind: 'update', pageId, changes }),
      readPageAgain: (pageId) => send({ kind: 'readAgain', pageId }),
      deletePage: (pageId) => send({ kind: 'delete', pageId }),
    },
    // The page's load never settles, so that what comes during it can be observed.
    reload: () => {
      observed.push({ kind: 'reload' });
      return new Promise(() => {});
    },
    onBusyChange: (isBusy) => observed.push({ kind: 'busy', isBusy }),
  });
  return { observed, requests, actions };
};

const recordOutcome =
  (observed: Observed[]) =>
  (outcome: PageActionOutcome): void => {
    observed.push({ kind: 'outcome', outcome });
  };

const recordDeletion =
  (observed: Observed[]) =>
  (deletion: PageDeletion): void => {
    observed.push({ kind: 'deletion', deletion });
  };

const requestsOf = (observed: readonly Observed[]): PageRequest[] => {
  return observed.flatMap((entry) => (entry.kind === 'request' ? [entry.request] : []));
};

describe('The page actions', () => {
  describe('The run() method', () => {
    describe('When each action is asked', () => {
      const rows: readonly { readonly name: string; readonly action: PageAction; readonly request: PageRequest }[] = [
        {
          name: 'a number saved',
          action: { kind: 'saveNumber', number: SAVED_NUMBER },
          request: { kind: 'update', pageId: PAGE_ID, changes: { manualNumber: SAVED_NUMBER } },
        },
        {
          name: 'the number cleared',
          action: { kind: 'clearNumber' },
          request: { kind: 'update', pageId: PAGE_ID, changes: { manualNumber: null } },
        },
        {
          name: 'a rotation',
          action: { kind: 'rotate', rotation: 90 },
          request: { kind: 'update', pageId: PAGE_ID, changes: { rotation: 90 } },
        },
        {
          name: 'the page excluded',
          action: { kind: 'setExclusion', isExcluded: true },
          request: { kind: 'update', pageId: PAGE_ID, changes: { isExcluded: true } },
        },
        {
          name: 'the page put back',
          action: { kind: 'setExclusion', isExcluded: false },
          request: { kind: 'update', pageId: PAGE_ID, changes: { isExcluded: false } },
        },
        {
          name: 'the text read again',
          action: { kind: 'readAgain' },
          request: { kind: 'readAgain', pageId: PAGE_ID },
        },
      ];
      for (const { name, action, request } of rows) {
        describe(`When the action is ${name}`, () => {
          let arrangement: Arrangement;
          beforeEach(() => {
            arrangement = arrange();
            void arrangement.actions.run(action, recordOutcome(arrangement.observed));
          });

          it('should send its request for the page', () => {
            assert.deepEqual(requestsOf(arrangement.observed), [request]);
          });
        });
      }
    });

    describe('When the action succeeds', () => {
      const action: PageAction = { kind: 'saveNumber', number: SAVED_NUMBER };
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        void arrangement.actions.run(action, recordOutcome(arrangement.observed));
        await arrangement.requests[0]?.answer();
      });

      it('should tell its steps in order: busy, its request, its success, no longer busy, then the page loaded again', () => {
        assert.deepEqual(arrangement.observed, [
          { kind: 'busy', isBusy: true },
          { kind: 'request', request: { kind: 'update', pageId: PAGE_ID, changes: { manualNumber: SAVED_NUMBER } } },
          { kind: 'outcome', outcome: { kind: 'succeeded', action } },
          { kind: 'busy', isBusy: false },
          { kind: 'reload' },
        ]);
      });
    });

    describe('When the action fails', () => {
      const action: PageAction = { kind: 'setExclusion', isExcluded: true };
      const failure = new ApiError(INTERNAL_SERVER_ERROR, 'disk full');
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        void arrangement.actions.run(action, recordOutcome(arrangement.observed));
        await arrangement.requests[0]?.fail(failure);
      });

      it('should tell the failure itself with its action, then load the page again once no longer busy', () => {
        assert.deepEqual(arrangement.observed, [
          { kind: 'busy', isBusy: true },
          { kind: 'request', request: { kind: 'update', pageId: PAGE_ID, changes: { isExcluded: true } } },
          { kind: 'outcome', outcome: { kind: 'failed', action, failure } },
          { kind: 'busy', isBusy: false },
          { kind: 'reload' },
        ]);
      });
    });

    describe('When a second action is asked while one runs', () => {
      let arrangement: Arrangement;
      beforeEach(() => {
        arrangement = arrange();
        void arrangement.actions.run({ kind: 'rotate', rotation: 90 }, recordOutcome(arrangement.observed));
        void arrangement.actions.run({ kind: 'rotate', rotation: 180 }, recordOutcome(arrangement.observed));
      });

      it('should drop it, so that a double click acts once', () => {
        assert.deepEqual(requestsOf(arrangement.observed), [
          { kind: 'update', pageId: PAGE_ID, changes: { rotation: 90 } },
        ]);
      });
    });

    describe('When another action is asked while the page loads again after one', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        void arrangement.actions.run({ kind: 'rotate', rotation: 90 }, recordOutcome(arrangement.observed));
        await arrangement.requests[0]?.answer();
        void arrangement.actions.run({ kind: 'readAgain' }, recordOutcome(arrangement.observed));
      });

      it('should run it', () => {
        assert.deepEqual(requestsOf(arrangement.observed), [
          { kind: 'update', pageId: PAGE_ID, changes: { rotation: 90 } },
          { kind: 'readAgain', pageId: PAGE_ID },
        ]);
      });
    });

    describe('When an action is asked while the page is deleted', () => {
      let arrangement: Arrangement;
      beforeEach(() => {
        arrangement = arrange();
        void arrangement.actions.deletePage(recordDeletion(arrangement.observed));
        void arrangement.actions.run({ kind: 'clearNumber' }, recordOutcome(arrangement.observed));
      });

      it('should drop it', () => {
        assert.deepEqual(requestsOf(arrangement.observed), [{ kind: 'delete', pageId: PAGE_ID }]);
      });
    });
  });

  describe('The deletePage() method', () => {
    describe('When the deletion succeeds', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        void arrangement.actions.deletePage(recordDeletion(arrangement.observed));
        await arrangement.requests[0]?.answer();
      });

      it('should tell it and stay busy without loading the page again, since the screen is left', () => {
        assert.deepEqual(arrangement.observed, [
          { kind: 'busy', isBusy: true },
          { kind: 'request', request: { kind: 'delete', pageId: PAGE_ID } },
          { kind: 'deletion', deletion: { kind: 'deleted' } },
        ]);
      });

      describe('When an action is then asked', () => {
        beforeEach(() => {
          void arrangement.actions.run({ kind: 'readAgain' }, recordOutcome(arrangement.observed));
        });

        it('should drop it', () => {
          assert.deepEqual(requestsOf(arrangement.observed), [{ kind: 'delete', pageId: PAGE_ID }]);
        });
      });
    });

    describe('When the deletion fails', () => {
      const failure = new ApiError(INTERNAL_SERVER_ERROR, 'disk full');
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        void arrangement.actions.deletePage(recordDeletion(arrangement.observed));
        await arrangement.requests[0]?.fail(failure);
      });

      it('should tell the failure itself, then be no longer busy, without loading the page again', () => {
        assert.deepEqual(arrangement.observed, [
          { kind: 'busy', isBusy: true },
          { kind: 'request', request: { kind: 'delete', pageId: PAGE_ID } },
          { kind: 'deletion', deletion: { kind: 'failed', failure } },
          { kind: 'busy', isBusy: false },
        ]);
      });
    });

    describe('When the deletion is asked while an action runs', () => {
      let arrangement: Arrangement;
      beforeEach(() => {
        arrangement = arrange();
        void arrangement.actions.run({ kind: 'rotate', rotation: 90 }, recordOutcome(arrangement.observed));
        void arrangement.actions.deletePage(recordDeletion(arrangement.observed));
      });

      it('should send it all the same, since its button is refused while busy', () => {
        assert.deepEqual(requestsOf(arrangement.observed), [
          { kind: 'update', pageId: PAGE_ID, changes: { rotation: 90 } },
          { kind: 'delete', pageId: PAGE_ID },
        ]);
      });
    });
  });
});
