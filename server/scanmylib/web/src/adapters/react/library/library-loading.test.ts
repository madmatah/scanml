import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { ApiError, NetworkError } from '../../../application/api-errors.ts';
import { sampleDocument } from '../../../domain/document-summary.test-support.ts';
import { sampleServerStatus } from '../../../domain/server-status.test-support.ts';
import {
  afterLoadFailure,
  hasQueueMoved,
  type LibraryLoad,
  type LoadFailure,
  queueKeyOf,
  SEARCH_THRESHOLD_DOCUMENTS,
  showsSearch,
} from './library-loading.ts';

const INTERNAL_SERVER_ERROR = 500;

function loadedLibrary(documentCount: number): LibraryLoad {
  const documents = Array.from({ length: documentCount }, (_, position) =>
    sampleDocument({ id: `document-${position}` }),
  );
  return { phase: 'loaded', documents };
}

describe('The library loading', () => {
  describe('The showsSearch() function', () => {
    const situations: { situation: string; load: LibraryLoad; rule: string; expected: boolean }[] = [
      {
        situation: 'When the documents are still loading',
        load: { phase: 'loading' },
        rule: 'should hide the search',
        expected: false,
      },
      {
        situation: 'When the library holds one document less than the threshold',
        load: loadedLibrary(SEARCH_THRESHOLD_DOCUMENTS - 1),
        rule: 'should hide the search, since the documents fit in a glance',
        expected: false,
      },
      {
        situation: 'When the library holds as many documents as the threshold',
        load: loadedLibrary(SEARCH_THRESHOLD_DOCUMENTS),
        rule: 'should show the search',
        expected: true,
      },
    ];

    for (const { situation, load, rule, expected } of situations) {
      describe(situation, () => {
        let isShown: boolean;
        beforeEach(() => {
          isShown = showsSearch(load);
        });

        it(rule, () => {
          assert.equal(isShown, expected);
        });
      });
    }
  });

  describe('The afterLoadFailure() function', () => {
    describe('When the first load fails', () => {
      const failure = new ApiError(INTERNAL_SERVER_ERROR, 'disk full');
      let outcome: LoadFailure;
      beforeEach(() => {
        outcome = afterLoadFailure({ phase: 'loading' }, failure);
      });

      it('should show the failure in place of the list, without a toast', () => {
        assert.deepEqual(outcome, { load: { phase: 'failed', failure }, isToldInToast: false });
      });
    });

    describe('When a reload fails while the list shows', () => {
      const shown = loadedLibrary(2);
      let outcome: LoadFailure;
      beforeEach(() => {
        outcome = afterLoadFailure(shown, new ApiError(INTERNAL_SERVER_ERROR, 'disk full'));
      });

      it('should keep the list, and tell the failure in a toast', () => {
        assert.deepEqual(outcome, { load: shown, isToldInToast: true });
      });
    });

    describe('When a reload cannot reach the server while the list shows', () => {
      const shown = loadedLibrary(2);
      let outcome: LoadFailure;
      beforeEach(() => {
        outcome = afterLoadFailure(shown, new NetworkError());
      });

      it('should keep the list without a toast, since the banner already says the server is unreachable', () => {
        assert.deepEqual(outcome, { load: shown, isToldInToast: false });
      });
    });
  });

  describe('The queueKeyOf() function', () => {
    describe('When no status is known', () => {
      let key: string | null;
      beforeEach(() => {
        key = queueKeyOf(null);
      });

      it('should give none', () => {
        assert.equal(key, null);
      });
    });

    describe('When two statuses differ only by the done count of the queue', () => {
      let keys: (string | null)[];
      beforeEach(() => {
        keys = [
          queueKeyOf(sampleServerStatus({ queue: { doneCount: 10 } })),
          queueKeyOf(sampleServerStatus({ queue: { doneCount: 11 } })),
        ];
      });

      it('should give each its own key, since a page whose text is ready changes a document', () => {
        assert.notEqual(keys[0], keys[1]);
      });
    });

    describe('When two statuses differ only by the state of the engine', () => {
      let keys: (string | null)[];
      beforeEach(() => {
        keys = [
          queueKeyOf(sampleServerStatus({ engine: { state: 'idle' } })),
          queueKeyOf(sampleServerStatus({ engine: { state: 'ready' } })),
        ];
      });

      it('should give them the same key, since no document changed', () => {
        assert.equal(keys[0], keys[1]);
      });
    });
  });

  describe('The hasQueueMoved() function', () => {
    const situations: {
      situation: string;
      previousKey: string | null;
      key: string;
      rule: string;
      expected: boolean;
    }[] = [
      {
        situation: 'When the first status comes',
        previousKey: null,
        key: '0/0/7/0',
        rule: 'should not count it as a move, since the list was just loaded',
        expected: false,
      },
      {
        situation: 'When the queue is as it was',
        previousKey: '0/0/7/0',
        key: '0/0/7/0',
        rule: 'should not count it as a move',
        expected: false,
      },
      {
        situation: 'When the queue changed',
        previousKey: '0/1/7/0',
        key: '0/0/8/0',
        rule: 'should count it as a move, so that the library loads again',
        expected: true,
      },
    ];

    for (const { situation, previousKey, key, rule, expected } of situations) {
      describe(situation, () => {
        let hasMoved: boolean;
        beforeEach(() => {
          hasMoved = hasQueueMoved(previousKey, key);
        });

        it(rule, () => {
          assert.equal(hasMoved, expected);
        });
      });
    }
  });
});
