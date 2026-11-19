import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import type { ServerStatus } from '../../domain/server-status.ts';
import { decodeServerStatus } from './server-status-decoder.ts';

// The answer of GET /api/status, as docs/API.md gives it.
const statusBody = (): Record<string, unknown> => {
  return {
    version: '0.2.3',
    ocr: {
      reachable: true,
      state: 'idle',
      backend: 'vllm',
      last_error: null,
      gpu: { name: 'Example GPU', memory_used_mb: 4608, memory_total_mb: 8192 },
    },
    queue: { queued: 3, processing: 1, error: 0, done: 120 },
    library_dir: '/home/user/Documents/ScanMyLib',
  };
};

const DECODED_STATUS: ServerStatus = {
  version: '0.2.3',
  engine: {
    isReachable: true,
    state: 'idle',
    backend: 'vllm',
    lastError: null,
    graphicsCard: { name: 'Example GPU', memoryUsedMebibytes: 4608, memoryTotalMebibytes: 8192 },
  },
  queue: { queuedCount: 3, processingCount: 1, errorCount: 0, doneCount: 120 },
  libraryDirectory: '/home/user/Documents/ScanMyLib',
};

describe('The server status decoder', () => {
  describe('The decodeServerStatus() function', () => {
    describe('When the answer has the documented shape', () => {
      let status: ServerStatus;
      beforeEach(() => {
        status = decodeServerStatus(statusBody());
      });

      it('should give each field its value', () => {
        assert.deepEqual(status, DECODED_STATUS);
      });
    });

    describe('When the engine reports no graphics card and no state', () => {
      let status: ServerStatus;
      beforeEach(() => {
        const body = statusBody();
        body.ocr = { reachable: false, state: null, backend: null, last_error: 'timed out', gpu: null };
        status = decodeServerStatus(body);
      });

      it('should keep their absence', () => {
        assert.deepEqual(status.engine, {
          isReachable: false,
          state: null,
          backend: null,
          lastError: 'timed out',
          graphicsCard: null,
        });
      });
    });

    describe('When the answer holds a field the client does not know', () => {
      let status: ServerStatus;
      beforeEach(() => {
        status = decodeServerStatus({ ...statusBody(), uptime_seconds: 42 });
      });

      it('should ignore it, so that the api can grow without breaking the UI', () => {
        assert.deepEqual(status, DECODED_STATUS);
      });
    });

    describe('When the answer lacks a field', () => {
      let act: () => ServerStatus;
      beforeEach(() => {
        const { library_dir: _libraryDirectory, ...body } = statusBody();
        act = () => decodeServerStatus(body);
      });

      it('should refuse it, naming the field', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid library_dir" });
      });
    });

    describe('When a nested field has the wrong type', () => {
      let act: () => ServerStatus;
      beforeEach(() => {
        const body = statusBody();
        body.queue = { queued: '3', processing: 1, error: 0, done: 120 };
        act = () => decodeServerStatus(body);
      });

      it('should refuse it, naming the field with its path', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid queue.queued" });
      });
    });

    describe('When a number is not finite', () => {
      let act: () => ServerStatus;
      beforeEach(() => {
        const body = statusBody();
        body.queue = { queued: 3, processing: Number.NaN, error: 0, done: 120 };
        act = () => decodeServerStatus(body);
      });

      it('should refuse it', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid queue.processing" });
      });
    });

    describe('When the answer is not an object', () => {
      let act: () => ServerStatus;
      beforeEach(() => {
        act = () => decodeServerStatus(['0.2.3']);
      });

      it('should refuse it whole', () => {
        assert.throws(act, { name: 'ResponseShapeError', message: "The api's answer holds no valid body" });
      });
    });
  });
});
