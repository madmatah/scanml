import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { ApiError, NetworkError } from '../../../application/api-errors.ts';
import { sampleDocument } from '../../../domain/document-summary.test-support.ts';
import {
  afterLoadFailure,
  type LibraryLoad,
  type LoadFailure,
  SEARCH_THRESHOLD_DOCUMENTS,
  showsSearch,
} from './library-loading.ts';

const INTERNAL_SERVER_ERROR = 500;

const loadedLibrary = (documentCount: number): LibraryLoad => {
  const documents = Array.from({ length: documentCount }, (_, position) =>
    sampleDocument({ id: `document-${position}` }),
  );
  return { phase: 'loaded', documents };
};

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
});
