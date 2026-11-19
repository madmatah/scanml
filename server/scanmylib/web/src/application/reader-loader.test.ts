import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import type { DocumentWithPages } from '../domain/document-details.ts';
import { sampleDocument } from '../domain/document-summary.test-support.ts';
import { ApiError, NetworkError } from './api-errors.ts';
import { createReaderLoader, type ReaderLoad, type ReaderLoader } from './reader-loader.ts';

interface PendingCall<Answer> {
  readonly signal: AbortSignal;
  readonly answer: (answer: Answer) => Promise<void>;
  readonly fail: (failure: unknown) => Promise<void>;
}

interface FakeCalls<Answer> {
  readonly calls: PendingCall<Answer>[];
  readonly call: (signal: AbortSignal) => Promise<Answer>;
}

interface Arrangement {
  readonly documentReads: FakeCalls<DocumentWithPages>;
  readonly htmlReads: FakeCalls<string>;
  readonly leaving: AbortController;
  readonly loads: ReaderLoad[];
  readonly refreshFailures: unknown[];
  readonly loader: ReaderLoader;
}

const NOT_FOUND = 404;
const SERVER_ERROR = 500;
const FIRST_HTML = '<h1>Math Notes</h1><section class="page" data-key="k-1"></section>';
const REFRESHED_HTML = `${FIRST_HTML}<section class="page" data-key="k-2"></section>`;

const settle = async (): Promise<void> => {
  await new Promise((resolve) => setImmediate(resolve));
};

const createFakeCalls = <Answer>(): FakeCalls<Answer> => {
  const calls: PendingCall<Answer>[] = [];
  return {
    calls,
    call: (signal) =>
      new Promise((resolve, reject) => {
        calls.push({
          signal,
          answer: async (answer) => {
            resolve(answer);
            await settle();
          },
          fail: async (failure) => {
            reject(failure);
            await settle();
          },
        });
      }),
  };
};

const documentWith = (title: string): DocumentWithPages => {
  return {
    ...sampleDocument({ title }),
    slug: 'math-notes',
    notes: '',
    unwarp: false,
    folder: '/data/USER/scanmylib/library/math-notes',
    pages: [],
  };
};

const arrange = (): Arrangement => {
  const documentReads = createFakeCalls<DocumentWithPages>();
  const htmlReads = createFakeCalls<string>();
  const leaving = new AbortController();
  const loads: ReaderLoad[] = [];
  const refreshFailures: unknown[] = [];
  const loader = createReaderLoader({
    readDocument: (signal) => documentReads.call(signal),
    readDocumentHtml: (signal) => htmlReads.call(signal),
    leaving: leaving.signal,
    onChange: (load) => loads.push(load),
    onRefreshFailed: (failure) => refreshFailures.push(failure),
  });
  return { documentReads, htmlReads, leaving, loads, refreshFailures, loader };
};

const answerLoad = async (arrangement: Arrangement, callIndex: number, title: string, html: string): Promise<void> => {
  await arrangement.documentReads.calls[callIndex]?.answer(documentWith(title));
  await arrangement.htmlReads.calls[callIndex]?.answer(html);
};

const showFirstLoad = async (): Promise<Arrangement> => {
  const arrangement = arrange();
  void arrangement.loader.load();
  await answerLoad(arrangement, 0, 'Math Notes', FIRST_HTML);
  return arrangement;
};

const phasesOf = (loads: readonly ReaderLoad[]): string[] => {
  return loads.map((load) => (load.phase === 'loaded' ? `loaded ${load.sanitizedHtml.length}` : load.phase));
};

describe('The reader loader', () => {
  describe('The load() method', () => {
    describe('When the document and its HTML come', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await showFirstLoad();
      });

      it('should show the loading state, then the document and its HTML, going back to the page read before', () => {
        assert.deepEqual(arrangement.loads, [
          { phase: 'loading' },
          {
            phase: 'loaded',
            document: documentWith('Math Notes'),
            sanitizedHtml: FIRST_HTML,
            returnsToPageRead: true,
          },
        ]);
      });

      it('should read both with the signal of the screen', () => {
        assert.deepEqual(
          [arrangement.documentReads.calls[0]?.signal, arrangement.htmlReads.calls[0]?.signal],
          [arrangement.leaving.signal, arrangement.leaving.signal],
        );
      });
    });

    describe('When the reader refreshes a document shown', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await showFirstLoad();
        void arrangement.loader.load();
        await answerLoad(arrangement, 1, 'Math Notes', REFRESHED_HTML);
      });

      it('should keep the text on screen meanwhile, and stay where the reader is', () => {
        assert.deepEqual(arrangement.loads.slice(2), [
          {
            phase: 'loaded',
            document: documentWith('Math Notes'),
            sanitizedHtml: REFRESHED_HTML,
            returnsToPageRead: false,
          },
        ]);
      });
    });

    describe('When a load is asked while another runs', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        void arrangement.loader.load();
        void arrangement.loader.load();
        await answerLoad(arrangement, 0, 'Math Notes', FIRST_HTML);
      });

      it('should drop it', () => {
        assert.equal(arrangement.documentReads.calls.length, 1);
      });
    });

    describe('When the first load fails', () => {
      const failure = new ApiError(SERVER_ERROR, 'internal error');
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        void arrangement.loader.load();
        await arrangement.documentReads.calls[0]?.fail(failure);
      });

      it('should show the failure', () => {
        assert.deepEqual(arrangement.loads, [{ phase: 'loading' }, { phase: 'failed', failure }]);
      });

      describe('When the load is tried again and succeeds', () => {
        beforeEach(async () => {
          void arrangement.loader.load();
          await answerLoad(arrangement, 1, 'Math Notes', FIRST_HTML);
        });

        it('should show the loading state again, then the document, going back to the page read before', () => {
          assert.deepEqual(phasesOf(arrangement.loads.slice(2)), ['loading', `loaded ${FIRST_HTML.length}`]);
        });
      });
    });

    describe('When a refresh fails', () => {
      const failure = new NetworkError();
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await showFirstLoad();
        void arrangement.loader.load();
        await arrangement.htmlReads.calls[1]?.fail(failure);
      });

      it('should tell the failure and leave the text on screen', () => {
        assert.deepEqual(
          { refreshFailures: arrangement.refreshFailures, phases: phasesOf(arrangement.loads) },
          { refreshFailures: [failure], phases: ['loading', `loaded ${FIRST_HTML.length}`] },
        );
      });
    });

    describe('When a refresh finds the document gone', () => {
      const failure = new ApiError(NOT_FOUND, 'document not found');
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await showFirstLoad();
        void arrangement.loader.load();
        await arrangement.documentReads.calls[1]?.fail(failure);
      });

      it('should show the failure in place of the text', () => {
        assert.deepEqual(arrangement.loads.slice(2), [{ phase: 'failed', failure }]);
      });
    });

    describe('When the screen is left before the answer', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        void arrangement.loader.load();
        arrangement.leaving.abort();
        await arrangement.documentReads.calls[0]?.fail(new DOMException('The screen was left.', 'AbortError'));
      });

      it('should show nothing more', () => {
        assert.deepEqual(arrangement.loads, [{ phase: 'loading' }]);
      });
    });
  });
});
