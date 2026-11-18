import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  createDocumentLoader,
  type DocumentLoad,
  type DocumentLoader,
  REFRESH_INTERVAL_MILLISECONDS,
  UPLOAD_RELOAD_DELAY_MILLISECONDS,
} from '../../../../src/adapters/react/document/document-loader.ts';
import { ApiError, NetworkError } from '../../../../src/application/api-errors.ts';
import type { DocumentWithPages } from '../../../../src/domain/document-details.ts';
import type { DocumentStats } from '../../../../src/domain/document-summary.ts';
import { createFakeScheduler, type FakeScheduler } from '../../../application/scheduler-fake.ts';
import { sampleDocument } from '../../../domain/document-summary-samples.ts';

interface PendingRead {
  readonly signal: AbortSignal;
  readonly answer: (document: DocumentWithPages) => Promise<void>;
  readonly fail: (failure: unknown) => Promise<void>;
}

interface FakeReader {
  readonly reads: PendingRead[];
  readonly read: (signal: AbortSignal) => Promise<DocumentWithPages>;
}

interface Arrangement {
  readonly reader: FakeReader;
  readonly scheduler: FakeScheduler;
  readonly leaving: AbortController;
  readonly loads: DocumentLoad[];
  readonly deletions: string[];
  readonly loader: DocumentLoader;
}

interface ArrangementOptions {
  readonly isUploading: boolean;
}

const NOT_FOUND = 404;
const SERVER_ERROR = 500;

// Lets the loader take the answer and run what follows it before the test goes on.
async function settle(): Promise<void> {
  await new Promise((resolve) => setImmediate(resolve));
}

function createFakeReader(): FakeReader {
  const reads: PendingRead[] = [];
  return {
    reads,
    read: (signal) =>
      new Promise((resolve, reject) => {
        reads.push({
          signal,
          answer: async (document) => {
            resolve(document);
            await settle();
          },
          fail: async (failure) => {
            reject(failure);
            await settle();
          },
        });
      }),
  };
}

function documentWith(title: string, stats: Partial<DocumentStats> = {}): DocumentWithPages {
  return {
    ...sampleDocument({ title, stats }),
    slug: 'example-book',
    notes: '',
    unwarp: true,
    folder: '/data/USER/scanmylib/library/example-book',
    pages: [],
  };
}

function arrange({ isUploading }: ArrangementOptions = { isUploading: false }): Arrangement {
  const reader = createFakeReader();
  const scheduler = createFakeScheduler();
  const leaving = new AbortController();
  const loads: DocumentLoad[] = [];
  const deletions: string[] = [];
  const loader = createDocumentLoader({
    read: reader.read,
    scheduler,
    isUploading: () => isUploading,
    leaving: leaving.signal,
    onChange: (load) => loads.push(load),
    onDeleted: () => deletions.push('deleted'),
  });
  return { reader, scheduler, leaving, loads, deletions, loader };
}

function titlesOf(loads: readonly DocumentLoad[]): string[] {
  return loads.map((load) => (load.phase === 'loaded' ? load.document.title : load.phase));
}

describe('The document loader', () => {
  describe('The load() method', () => {
    describe('When the document comes with every text read', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.loader.load();
        await arrangement.reader.reads[0]?.answer(documentWith('Example Book'));
      });

      it('should show it', () => {
        assert.deepEqual(titlesOf(arrangement.loads), ['Example Book']);
      });

      it('should read it with the signal of the screen, so that leaving the screen cancels the request', () => {
        assert.equal(arrangement.reader.reads[0]?.signal, arrangement.leaving.signal);
      });

      it('should not refresh it, since nothing changes', () => {
        assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), []);
      });
    });

    describe('When pages of the document wait for their text', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.loader.load();
        await arrangement.reader.reads[0]?.answer(documentWith('Example Book', { queuedCount: 2 }));
      });

      it('should read it again a few seconds later', () => {
        assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), [REFRESH_INTERVAL_MILLISECONDS]);
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

    describe('When photos of the document are being uploaded', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange({ isUploading: true });
        arrangement.loader.load();
        await arrangement.reader.reads[0]?.answer(documentWith('Example Book'));
      });

      it('should read it again a few seconds later, so that their pages show as they arrive', () => {
        assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), [REFRESH_INTERVAL_MILLISECONDS]);
      });
    });

    describe('When a load is asked while another runs', () => {
      let arrangement: Arrangement;
      let readCountDuringFirst: number;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.loader.load();
        arrangement.loader.load();
        arrangement.loader.load();
        readCountDuringFirst = arrangement.reader.reads.length;
        await arrangement.reader.reads[0]?.answer(documentWith('Example Book'));
        await arrangement.reader.reads[1]?.answer(documentWith('Example Book, edited'));
      });

      it('should send one request at a time', () => {
        assert.equal(readCountDuringFirst, 1);
      });

      it('should read the document once more after the first answer, however many loads were asked', () => {
        assert.deepEqual(titlesOf(arrangement.loads), ['Example Book', 'Example Book, edited']);
      });
    });

    describe('When the first load fails', () => {
      let arrangement: Arrangement;
      const failure = new ApiError(SERVER_ERROR, 'database locked');
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.loader.load();
        await arrangement.reader.reads[0]?.fail(failure);
      });

      it('should show the failure', () => {
        assert.deepEqual(arrangement.loads, [{ phase: 'failed', failure }]);
      });

      it('should not refresh, so that the screen waits for its Retry', () => {
        assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), []);
      });
    });

    describe('When a refresh fails for a while', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.loader.load();
        await arrangement.reader.reads[0]?.answer(documentWith('Example Book', { processingCount: 1 }));
        arrangement.scheduler.runPending();
        await arrangement.reader.reads[1]?.fail(new NetworkError());
      });

      it('should keep the last document on screen', () => {
        assert.deepEqual(titlesOf(arrangement.loads), ['Example Book']);
      });

      it('should try again at the next refresh', () => {
        assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), [REFRESH_INTERVAL_MILLISECONDS]);
      });
    });

    describe('When the document is deleted while it is shown', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.loader.load();
        await arrangement.reader.reads[0]?.answer(documentWith('Example Book'));
        arrangement.loader.load();
        await arrangement.reader.reads[1]?.fail(new ApiError(NOT_FOUND, 'document not found'));
      });

      it('should tell that it was deleted, once', () => {
        assert.deepEqual(arrangement.deletions, ['deleted']);
      });

      it('should change nothing on screen', () => {
        assert.deepEqual(titlesOf(arrangement.loads), ['Example Book']);
      });
    });

    describe('When the screen is left before the answer', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.loader.load();
        arrangement.loader.load();
        arrangement.leaving.abort();
        await arrangement.reader.reads[0]?.fail(new DOMException('The operation was aborted.', 'AbortError'));
      });

      it('should show nothing, and read nothing more', () => {
        assert.deepEqual(
          { loads: arrangement.loads, readCount: arrangement.reader.reads.length },
          {
            loads: [],
            readCount: 1,
          },
        );
      });
    });
  });

  describe('The loadAfterUpload() method', () => {
    describe('When photos are sent one after another', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.loader.load();
        await arrangement.reader.reads[0]?.answer(documentWith('Example Book'));
        arrangement.loader.loadAfterUpload();
        arrangement.loader.loadAfterUpload();
      });

      it('should wait a moment once, so that their pages show in one load', () => {
        assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), [UPLOAD_RELOAD_DELAY_MILLISECONDS]);
      });

      describe('When the moment has passed', () => {
        beforeEach(async () => {
          arrangement.scheduler.runPending();
          await arrangement.reader.reads[1]?.answer(documentWith('Example Book, with its new pages'));
        });

        it('should read the document again', () => {
          assert.deepEqual(titlesOf(arrangement.loads), ['Example Book', 'Example Book, with its new pages']);
        });
      });

      describe('When the screen is left before the moment has passed', () => {
        beforeEach(() => {
          arrangement.leaving.abort();
        });

        it('should drop the load', () => {
          assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), []);
        });
      });
    });
  });

  describe('The replace() method', () => {
    describe('When the document was edited', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.loader.load();
        await arrangement.reader.reads[0]?.answer(documentWith('Example Book'));
        arrangement.loader.replace(documentWith('Example Book, second edition'));
      });

      it('should show the document it is given', () => {
        assert.deepEqual(titlesOf(arrangement.loads), ['Example Book', 'Example Book, second edition']);
      });
    });
  });
});
