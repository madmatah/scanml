import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { MAX_UPLOAD_BYTES } from '../domain/photo-upload.ts';
import { ApiError, NetworkError } from './api-errors.ts';
import { createFakePageUploader, createFixedClock, type FakePageUploader, photo } from './upload-queue.test-support.ts';
import {
  createUploadQueue,
  inFileNameOrder,
  type PhotoFile,
  type SettledUploads,
  summarizeUploads,
  type UploadItem,
  type UploadQueue,
  type UploadSummary,
} from './upload-queue.ts';
import { createCountingUuidSource } from './uuid-source.test-support.ts';

interface Arrangement {
  readonly uploader: FakePageUploader;
  readonly queue: UploadQueue<PhotoFile>;
  readonly settled: SettledUploads[];
}

const DOCUMENT_ID = '95bbeb79-4351-432f-a53c-d3658892ff50';
const OTHER_DOCUMENT_ID = '2d0f7a54-11c5-4b8e-9b0e-3f6a7c8d9e10';
const SESSION_ID = 'c3a7e2d1-5b4f-4e6a-8d9c-1f2e3d4c5b6a';
const NOW_MILLISECONDS = Date.UTC(2026, 10, 18, 14, 30, 0);
const UNSUPPORTED_MEDIA_TYPE = 415;
const SERVER_ERROR = 500;

const arrange = (): Arrangement => {
  const uploader = createFakePageUploader();
  const queue = createUploadQueue(uploader, createCountingUuidSource(), createFixedClock(NOW_MILLISECONDS));
  const settled: SettledUploads[] = [];
  queue.watchSettled((counts) => settled.push(counts));
  return { uploader, queue, settled };
};

const statesOf = (uploads: readonly UploadItem[]): string[] => {
  return uploads.map((upload) => `${upload.name}: ${upload.state}`);
};

const uploadedItem = (overrides: Partial<UploadItem>): UploadItem => {
  return {
    pageId: '00000000-0000-4000-8000-000000000001',
    documentId: DOCUMENT_ID,
    name: 'IMG_0001.jpg',
    size: 1000,
    state: 'pending',
    progress: 0,
    problem: null,
    ...overrides,
  };
};

describe('The upload queue', () => {
  describe('The add() method', () => {
    describe('When three photos are added', () => {
      let arrangement: Arrangement;
      beforeEach(() => {
        arrangement = arrange();
        arrangement.queue.add(DOCUMENT_ID, [photo('IMG_0001.jpg'), photo('IMG_0002.jpg'), photo('IMG_0003.jpg')], {
          sessionId: SESSION_ID,
          firstSeq: 4,
        });
      });

      it('should send two at a time, and keep the third waiting', () => {
        assert.deepEqual(statesOf(arrangement.queue.getSnapshot()), [
          'IMG_0001.jpg: uploading',
          'IMG_0002.jpg: uploading',
          'IMG_0003.jpg: pending',
        ]);
      });

      it('should number them in their capture session from the first sequence number, in the order given', () => {
        assert.deepEqual(
          arrangement.uploader.started.map(({ upload }) => [upload.sessionId, upload.seq]),
          [
            [SESSION_ID, 4],
            [SESSION_ID, 5],
          ],
        );
      });

      it('should give each page an id of its own, for the document', () => {
        assert.deepEqual(
          arrangement.uploader.started.map(({ upload }) => [upload.documentId, upload.pageId]),
          [
            [DOCUMENT_ID, '00000000-0000-4000-8000-000000000001'],
            [DOCUMENT_ID, '00000000-0000-4000-8000-000000000002'],
          ],
        );
      });

      it('should date each photo at its last modification', () => {
        assert.equal(Date.parse(arrangement.uploader.started[0]?.upload.capturedAt ?? ''), photo('').lastModified);
      });

      it('should be busy for that document', () => {
        assert.equal(arrangement.queue.isBusy(DOCUMENT_ID), true);
      });

      it('should not be busy for another document', () => {
        assert.equal(arrangement.queue.isBusy(OTHER_DOCUMENT_ID), false);
      });
    });

    describe('When a photo has no modification time nor name', () => {
      let arrangement: Arrangement;
      beforeEach(() => {
        arrangement = arrange();
        arrangement.queue.add(DOCUMENT_ID, [photo('', { lastModified: 0 })], { sessionId: SESSION_ID, firstSeq: 7 });
      });

      it('should date it now', () => {
        assert.equal(Date.parse(arrangement.uploader.started[0]?.upload.capturedAt ?? ''), NOW_MILLISECONDS);
      });

      it('should name it after its sequence number', () => {
        assert.equal(arrangement.queue.getSnapshot()[0]?.name, 'photo-7');
      });
    });

    describe('When photos fail the checks of the browser', () => {
      let arrangement: Arrangement;
      beforeEach(() => {
        arrangement = arrange();
        arrangement.queue.add(
          DOCUMENT_ID,
          [
            photo('scan.gif', { type: 'image/gif' }),
            photo('huge.jpg', { size: MAX_UPLOAD_BYTES + 1 }),
            photo('empty.jpg', { size: 0 }),
            photo('picked.jpg', { type: '' }),
          ],
          { sessionId: SESSION_ID, firstSeq: 1 },
        );
      });

      it('should refuse them, each with its reason, and send none', () => {
        assert.deepEqual(
          arrangement.queue.getSnapshot().map((upload) => [upload.name, upload.state, upload.problem?.kind ?? null]),
          [
            ['scan.gif', 'rejected', 'unsupported-format'],
            ['huge.jpg', 'rejected', 'too-large'],
            ['empty.jpg', 'rejected', 'empty'],
            ['picked.jpg', 'uploading', null],
          ],
        );
      });

      it('should send a photo without a type, which some Android pickers give, for the server to decide', () => {
        assert.deepEqual(
          arrangement.uploader.started.map(({ upload }) => upload.file.name),
          ['picked.jpg'],
        );
      });
    });

    describe('When every photo added fails the checks of the browser', () => {
      let arrangement: Arrangement;
      beforeEach(() => {
        arrangement = arrange();
        arrangement.queue.add(DOCUMENT_ID, [photo('scan.gif', { type: 'image/gif' })], {
          sessionId: SESSION_ID,
          firstSeq: 1,
        });
      });

      it('should tell at once that the queue has settled, with the refusal', () => {
        assert.deepEqual(arrangement.settled, [{ sentCount: 0, failedCount: 0, rejectedCount: 1 }]);
      });
    });
  });

  describe('When uploads go on', () => {
    describe('When the browser tells how much of a photo is sent', () => {
      let arrangement: Arrangement;
      beforeEach(() => {
        arrangement = arrange();
        arrangement.queue.add(DOCUMENT_ID, [photo('IMG_0001.jpg')], { sessionId: SESSION_ID, firstSeq: 1 });
        arrangement.uploader.started[0]?.reportProgress(0.5);
      });

      it('should show its progress', () => {
        assert.equal(arrangement.queue.getSnapshot()[0]?.progress, 0.5);
      });
    });

    describe('When the first of three uploads succeeds', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.queue.add(DOCUMENT_ID, [photo('IMG_0001.jpg'), photo('IMG_0002.jpg'), photo('IMG_0003.jpg')], {
          sessionId: SESSION_ID,
          firstSeq: 1,
        });
        await arrangement.uploader.started[0]?.succeed();
      });

      it('should mark it sent, and send the photo that waited', () => {
        assert.deepEqual(statesOf(arrangement.queue.getSnapshot()), [
          'IMG_0001.jpg: sent',
          'IMG_0002.jpg: uploading',
          'IMG_0003.jpg: uploading',
        ]);
      });

      it('should not tell yet that the queue has settled', () => {
        assert.deepEqual(arrangement.settled, []);
      });
    });

    describe('When uploads fail', () => {
      let arrangement: Arrangement;
      const unreachable = new NetworkError();
      const refusal = new ApiError(UNSUPPORTED_MEDIA_TYPE, 'not an image');
      const serverFailure = new ApiError(SERVER_ERROR, 'database locked');
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.queue.add(DOCUMENT_ID, [photo('IMG_0001.jpg'), photo('IMG_0002.jpg'), photo('IMG_0003.jpg')], {
          sessionId: SESSION_ID,
          firstSeq: 1,
        });
        await arrangement.uploader.started[0]?.fail(unreachable);
        await arrangement.uploader.started[1]?.fail(refusal);
        await arrangement.uploader.started[2]?.fail(serverFailure);
      });

      it('should keep for a retry those that a retry may send, and refuse for good those the server refused', () => {
        assert.deepEqual(
          arrangement.queue.getSnapshot().map((upload) => [upload.state, upload.problem]),
          [
            ['failed', { kind: 'upload-failed', failure: unreachable }],
            ['rejected', { kind: 'upload-failed', failure: refusal }],
            ['failed', { kind: 'upload-failed', failure: serverFailure }],
          ],
        );
      });

      it('should tell once that the queue has settled, with its failures and refusals', () => {
        assert.deepEqual(arrangement.settled, [{ sentCount: 0, failedCount: 2, rejectedCount: 1 }]);
      });
    });

    describe('When every upload succeeds', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.queue.add(DOCUMENT_ID, [photo('IMG_0001.jpg'), photo('IMG_0002.jpg')], {
          sessionId: SESSION_ID,
          firstSeq: 1,
        });
        await arrangement.uploader.started[0]?.succeed();
        await arrangement.uploader.started[1]?.succeed();
      });

      it('should tell once that the queue has settled, with the photos sent', () => {
        assert.deepEqual(arrangement.settled, [{ sentCount: 2, failedCount: 0, rejectedCount: 0 }]);
      });

      it('should no longer be busy', () => {
        assert.equal(arrangement.queue.isBusy(), false);
      });
    });
  });

  describe('The retryFailed() method', () => {
    describe('When a failure is sent again before the queue has settled', () => {
      let arrangement: Arrangement;
      let stateAfterRetry: string[];
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.queue.add(DOCUMENT_ID, [photo('IMG_0001.jpg'), photo('IMG_0002.jpg')], {
          sessionId: SESSION_ID,
          firstSeq: 1,
        });
        await arrangement.uploader.started[0]?.fail(new NetworkError());
        arrangement.queue.retryFailed(DOCUMENT_ID);
        stateAfterRetry = statesOf(arrangement.queue.getSnapshot());
        await arrangement.uploader.started[2]?.succeed();
        await arrangement.uploader.started[1]?.succeed();
      });

      it('should send it again with the same page id, which the server takes once', () => {
        assert.deepEqual(
          arrangement.uploader.started.map(({ upload }) => upload.pageId),
          [
            '00000000-0000-4000-8000-000000000001',
            '00000000-0000-4000-8000-000000000002',
            '00000000-0000-4000-8000-000000000001',
          ],
        );
      });

      it('should send it at once', () => {
        assert.deepEqual(stateAfterRetry, ['IMG_0001.jpg: uploading', 'IMG_0002.jpg: uploading']);
      });

      it('should count it once, with the outcome of its retry', () => {
        assert.deepEqual(arrangement.settled, [{ sentCount: 2, failedCount: 0, rejectedCount: 0 }]);
      });
    });

    describe('When photos of another document failed', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.queue.add(OTHER_DOCUMENT_ID, [photo('IMG_0001.jpg')], { sessionId: SESSION_ID, firstSeq: 1 });
        await arrangement.uploader.started[0]?.fail(new NetworkError());
        arrangement.queue.retryFailed(DOCUMENT_ID);
      });

      it('should leave them as they are', () => {
        assert.deepEqual(statesOf(arrangement.queue.getSnapshot()), ['IMG_0001.jpg: failed']);
      });
    });
  });

  describe('The clearFinished() method', () => {
    describe('When the list of a document holds finished and running uploads', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.queue.add(OTHER_DOCUMENT_ID, [photo('IMG_0009.jpg')], { sessionId: SESSION_ID, firstSeq: 1 });
        await arrangement.uploader.started[0]?.succeed();
        arrangement.queue.add(
          DOCUMENT_ID,
          [
            photo('IMG_0001.jpg'),
            photo('IMG_0002.jpg'),
            photo('IMG_0003.jpg'),
            photo('scan.gif', { type: 'image/gif' }),
          ],
          { sessionId: SESSION_ID, firstSeq: 1 },
        );
        await arrangement.uploader.started[1]?.succeed();
        await arrangement.uploader.started[2]?.fail(new NetworkError());
        arrangement.queue.clearFinished(DOCUMENT_ID);
      });

      it('should remove its sent, failed and refused photos, and keep the running ones and other documents', () => {
        assert.deepEqual(statesOf(arrangement.queue.getSnapshot()), ['IMG_0009.jpg: sent', 'IMG_0003.jpg: uploading']);
      });
    });
  });

  describe('The inFileNameOrder() function', () => {
    describe('When the names hold numbers of different lengths', () => {
      let ordered: string[];
      beforeEach(() => {
        ordered = inFileNameOrder([photo('IMG_10.jpg'), photo('IMG_9.jpg'), photo('IMG_100.jpg')]).map(
          (file) => file.name,
        );
      });

      it('should sort them by their numbers, the shooting order of cameras and scanners', () => {
        assert.deepEqual(ordered, ['IMG_9.jpg', 'IMG_10.jpg', 'IMG_100.jpg']);
      });
    });
  });

  describe('The summarizeUploads() function', () => {
    describe('When uploads are sent, running, waiting, failed and refused', () => {
      const failure = { kind: 'upload-failed', failure: new NetworkError() } as const;
      const items: UploadItem[] = [
        uploadedItem({ name: 'refused.gif', state: 'rejected', size: 5000, problem: { kind: 'unsupported-format' } }),
        uploadedItem({ name: 'sent.jpg', state: 'sent', size: 1000, progress: 1 }),
        uploadedItem({ name: 'running.jpg', state: 'uploading', size: 2000, progress: 0.5 }),
        uploadedItem({ name: 'waiting.jpg', state: 'pending', size: 1000 }),
        uploadedItem({ name: 'failed.jpg', state: 'failed', size: 1000, problem: failure }),
      ];
      let summary: UploadSummary;
      beforeEach(() => {
        summary = summarizeUploads(items);
      });

      it('should count the photos sent, accepted and waiting, and tell that uploads run', () => {
        assert.deepEqual(
          {
            sentCount: summary.sentCount,
            acceptedCount: summary.acceptedCount,
            waitingCount: summary.waitingCount,
            isBusy: summary.isBusy,
          },
          { sentCount: 1, acceptedCount: 4, waitingCount: 1, isBusy: true },
        );
      });

      it('should measure the progress in bytes, without the refused photos', () => {
        assert.equal(summary.progress, 2000 / 5000);
      });

      it('should list the failures before the refusals', () => {
        assert.deepEqual(
          summary.failures.map((upload) => upload.name),
          ['failed.jpg', 'refused.gif'],
        );
      });
    });

    describe('When every photo was refused', () => {
      let summary: UploadSummary;
      beforeEach(() => {
        summary = summarizeUploads([uploadedItem({ state: 'rejected', problem: { kind: 'empty' } })]);
      });

      it('should count the progress as complete, since nothing is left to send', () => {
        assert.equal(summary.progress, 1);
      });
    });
  });
});
