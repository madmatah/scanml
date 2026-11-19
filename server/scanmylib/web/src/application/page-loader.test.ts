import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import type { DocumentWithPages } from '../domain/document-details.ts';
import { sampleDocument } from '../domain/document-summary.test-support.ts';
import { SAMPLE_DOCUMENT_ID, samplePageDetails } from '../domain/page-details.test-support.ts';
import type { PageDetails } from '../domain/page-details.ts';
import { ApiError, NetworkError } from './api-errors.ts';
import { createPageLoader, type PageLoad, type PageLoader, REFRESH_INTERVAL_MILLISECONDS } from './page-loader.ts';
import { createFakeScheduler, type FakeScheduler } from './scheduler.test-support.ts';

interface PendingCall<Answer> {
  readonly arguments: readonly unknown[];
  readonly answer: (answer: Answer) => Promise<void>;
  readonly fail: (failure: unknown) => Promise<void>;
}

interface FakeCalls<Answer> {
  readonly calls: PendingCall<Answer>[];
  readonly call: (...callArguments: unknown[]) => Promise<Answer>;
}

interface Arrangement {
  readonly pageReads: FakeCalls<PageDetails>;
  readonly documentReads: FakeCalls<DocumentWithPages>;
  readonly htmlReads: FakeCalls<string>;
  readonly scheduler: FakeScheduler;
  readonly leaving: AbortController;
  readonly loads: PageLoad[];
  readonly refreshFailures: unknown[];
  readonly loader: PageLoader;
}

const NOT_FOUND = 404;
const SERVER_ERROR = 500;
const SANITIZED_HTML = '<p>Example text.</p>';

const settle = async (): Promise<void> => {
  await new Promise((resolve) => setImmediate(resolve));
};

const createFakeCalls = <Answer>(): FakeCalls<Answer> => {
  const calls: PendingCall<Answer>[] = [];
  return {
    calls,
    call: (...callArguments) =>
      new Promise((resolve, reject) => {
        calls.push({
          arguments: callArguments,
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
  const pageReads = createFakeCalls<PageDetails>();
  const documentReads = createFakeCalls<DocumentWithPages>();
  const htmlReads = createFakeCalls<string>();
  const scheduler = createFakeScheduler();
  const leaving = new AbortController();
  const loads: PageLoad[] = [];
  const refreshFailures: unknown[] = [];
  const loader = createPageLoader({
    readPage: (signal) => pageReads.call(signal),
    readDocument: (documentId, signal) => documentReads.call(documentId, signal),
    readPageHtml: (signal) => htmlReads.call(signal),
    scheduler,
    leaving: leaving.signal,
    onChange: (load) => loads.push(load),
    onRefreshFailed: (failure) => refreshFailures.push(failure),
  });
  return { pageReads, documentReads, htmlReads, scheduler, leaving, loads, refreshFailures, loader };
};

const showReadPage = async (arrangement: Arrangement, callIndex: number, markdown: string): Promise<void> => {
  await arrangement.pageReads.calls[callIndex]?.answer(samplePageDetails({ markdown }));
  await arrangement.documentReads.calls[callIndex]?.answer(documentWith('Math Notes'));
  await arrangement.htmlReads.calls[callIndex]?.answer(SANITIZED_HTML);
};

const phasesOf = (loads: readonly PageLoad[]): string[] => {
  return loads.map((load) => (load.phase === 'loaded' ? load.page.markdown : load.phase));
};

describe('The page loader', () => {
  describe('The load() method', () => {
    describe('When the text of the page is read', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        void arrangement.loader.load();
        await settle();
        await showReadPage(arrangement, 0, 'Example text.');
      });

      it('should show the page with its document and its HTML', () => {
        assert.deepEqual(arrangement.loads, [
          {
            phase: 'loaded',
            page: samplePageDetails({ markdown: 'Example text.' }),
            document: documentWith('Math Notes'),
            sanitizedHtml: SANITIZED_HTML,
          },
        ]);
      });

      it('should read the page, its document and its HTML with the signal of the screen', () => {
        assert.deepEqual(
          [
            arrangement.pageReads.calls[0]?.arguments,
            arrangement.documentReads.calls[0]?.arguments,
            arrangement.htmlReads.calls[0]?.arguments,
          ],
          [
            [arrangement.leaving.signal],
            [SAMPLE_DOCUMENT_ID, arrangement.leaving.signal],
            [arrangement.leaving.signal],
          ],
        );
      });

      it('should not refresh it, since nothing changes', () => {
        assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), []);
      });
    });

    describe('When the page waits for its text', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        void arrangement.loader.load();
        await arrangement.pageReads.calls[0]?.answer(samplePageDetails({ status: 'queued', reading: null }));
        await arrangement.documentReads.calls[0]?.answer(documentWith('Math Notes'));
      });

      it('should show it without asking for an HTML that does not exist yet', () => {
        assert.deepEqual(
          {
            htmlReadCount: arrangement.htmlReads.calls.length,
            sanitizedHtml: arrangement.loads.map((load) => (load.phase === 'loaded' ? load.sanitizedHtml : null)),
          },
          { htmlReadCount: 0, sanitizedHtml: [''] },
        );
      });

      it('should read it again a few seconds later', () => {
        assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), [REFRESH_INTERVAL_MILLISECONDS]);
      });

      describe('When the refresh comes', () => {
        beforeEach(() => {
          arrangement.scheduler.runPending();
        });

        it('should read the page again', () => {
          assert.equal(arrangement.pageReads.calls.length, 2);
        });
      });

      describe('When the screen is left before the refresh', () => {
        beforeEach(() => {
          arrangement.leaving.abort();
        });

        it('should drop the refresh', () => {
          assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), []);
        });
      });
    });

    describe('When the first load fails', () => {
      const failure = new ApiError(SERVER_ERROR, 'storage unavailable');
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        void arrangement.loader.load();
        await arrangement.pageReads.calls[0]?.fail(failure);
      });

      it('should show the failure, since there is no page to keep on screen', () => {
        assert.deepEqual(arrangement.loads, [{ phase: 'failed', failure }]);
      });

      it('should not tell it again in a toast', () => {
        assert.deepEqual(arrangement.refreshFailures, []);
      });
    });

    describe('When the page was shown', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        void arrangement.loader.load();
        await settle();
        await showReadPage(arrangement, 0, 'Example text.');
        void arrangement.loader.load();
        await settle();
      });

      describe('When the page was deleted since', () => {
        const failure = new ApiError(NOT_FOUND, 'page not found');
        beforeEach(async () => {
          await arrangement.pageReads.calls[1]?.fail(failure);
        });

        it('should show that it is gone', () => {
          assert.deepEqual(phasesOf(arrangement.loads), ['Example text.', 'failed']);
        });
      });

      describe('When the api cannot be reached', () => {
        beforeEach(async () => {
          await arrangement.pageReads.calls[1]?.fail(new NetworkError());
        });

        it('should keep the page on screen and say nothing, since the banner of the engine says it', () => {
          assert.deepEqual(
            { phases: phasesOf(arrangement.loads), refreshFailures: arrangement.refreshFailures },
            { phases: ['Example text.'], refreshFailures: [] },
          );
        });
      });

      describe('When the api refuses the refresh', () => {
        const failure = new ApiError(SERVER_ERROR, 'storage unavailable');
        beforeEach(async () => {
          await arrangement.pageReads.calls[1]?.fail(failure);
        });

        it('should keep the page on screen and tell the failure', () => {
          assert.deepEqual(
            { phases: phasesOf(arrangement.loads), refreshFailures: arrangement.refreshFailures },
            { phases: ['Example text.'], refreshFailures: [failure] },
          );
        });
      });
    });

    describe('When a load is asked while another runs', () => {
      let arrangement: Arrangement;
      let readCountDuringFirst: number;
      beforeEach(async () => {
        arrangement = arrange();
        void arrangement.loader.load();
        void arrangement.loader.load();
        void arrangement.loader.load();
        await settle();
        readCountDuringFirst = arrangement.pageReads.calls.length;
        await showReadPage(arrangement, 0, 'Example text.');
        await showReadPage(arrangement, 1, 'Example text, read again.');
      });

      it('should wait for the first one', () => {
        assert.equal(readCountDuringFirst, 1);
      });

      it('should load once more after it, so that the page shown is never older than the request', () => {
        assert.deepEqual(phasesOf(arrangement.loads), ['Example text.', 'Example text, read again.']);
      });
    });

    describe('When the screen is left before the answer', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        void arrangement.loader.load();
        await settle();
        arrangement.leaving.abort();
        await arrangement.pageReads.calls[0]?.fail(new DOMException('The screen was left', 'AbortError'));
      });

      it('should show nothing more', () => {
        assert.deepEqual(arrangement.loads, []);
      });
    });
  });
});
