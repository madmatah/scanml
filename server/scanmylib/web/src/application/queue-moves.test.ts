import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { sampleServerStatus } from '../domain/server-status.test-support.ts';
import type { ServerStatus } from '../domain/server-status.ts';
import {
  createFakePageVisibility,
  createFakeStatusSource,
  type FakeStatusSource,
  settle,
} from './engine-status.test-support.ts';
import { createEngineStatus, type EngineStatus } from './engine-status.ts';
import { watchQueueMoves } from './queue-moves.ts';
import { createFakeScheduler, type FakeScheduler } from './scheduler.test-support.ts';

const QUEUE_BEFORE = sampleServerStatus({ queue: { processingCount: 1, doneCount: 7 } });
const QUEUE_AFTER = sampleServerStatus({ queue: { processingCount: 0, doneCount: 8 } });
const ENGINE_IDLE = sampleServerStatus({ queue: { processingCount: 1, doneCount: 7 }, engine: { state: 'idle' } });

interface Arrangement {
  readonly source: FakeStatusSource;
  readonly scheduler: FakeScheduler;
  readonly engineStatus: EngineStatus;
  readonly moves: (ServerStatus | null)[];
}

const arrange = (): Arrangement => {
  const source = createFakeStatusSource();
  const scheduler = createFakeScheduler();
  const engineStatus = createEngineStatus(source, createFakePageVisibility(true), scheduler);
  return { source, scheduler, engineStatus, moves: [] };
};

const recordMoves = (arrangement: Arrangement): (() => void) => {
  return () => {
    arrangement.moves.push(arrangement.engineStatus.getSnapshot().status);
  };
};

const answerFirstPoll = async (arrangement: Arrangement, status = QUEUE_BEFORE): Promise<void> => {
  arrangement.engineStatus.start();
  arrangement.source.answer(status);
  await settle();
};

const answerNextPoll = async (arrangement: Arrangement, status = QUEUE_AFTER): Promise<void> => {
  arrangement.scheduler.runPending();
  arrangement.source.answer(status);
  await settle();
};

describe('The queue moves', () => {
  describe('The watchQueueMoves() function', () => {
    describe('When the watch starts from no known status', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        watchQueueMoves(arrangement.engineStatus, recordMoves(arrangement), { from: null });
        await answerFirstPoll(arrangement);
      });

      it('should not count the first status as a move, since the screen has just loaded', () => {
        assert.deepEqual(arrangement.moves, []);
      });

      describe('When the queue then changes', () => {
        beforeEach(async () => {
          await answerNextPoll(arrangement);
        });

        it('should count it as a move, so that the screen loads again', () => {
          assert.deepEqual(arrangement.moves, [QUEUE_AFTER]);
        });
      });

      describe('When only the state of the engine then changes', () => {
        beforeEach(async () => {
          await answerNextPoll(arrangement, ENGINE_IDLE);
        });

        it('should count no move, since no document changed', () => {
          assert.deepEqual(arrangement.moves, []);
        });
      });
    });

    describe('When the watch starts from the status known when the screen opens', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        watchQueueMoves(arrangement.engineStatus, recordMoves(arrangement), { from: QUEUE_BEFORE });
        await answerFirstPoll(arrangement, QUEUE_AFTER);
      });

      it('should count the first status that differs as a move, so that a page read before it is not missed', () => {
        assert.deepEqual(arrangement.moves, [QUEUE_AFTER]);
      });
    });

    describe('When a status without a queue comes, then another queue', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        await answerFirstPoll(arrangement);
        watchQueueMoves(arrangement.engineStatus, recordMoves(arrangement), {
          from: arrangement.engineStatus.getSnapshot().status,
        });
        arrangement.engineStatus.stop();
        await answerFirstPoll(arrangement, QUEUE_AFTER);
      });

      it('should count a move from the queue known before, since a status without a queue says nothing of it', () => {
        assert.deepEqual(arrangement.moves, [QUEUE_AFTER]);
      });
    });

    describe('When the watch has stopped', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        const stopWatching = watchQueueMoves(arrangement.engineStatus, recordMoves(arrangement), {
          from: QUEUE_BEFORE,
        });
        stopWatching();
        await answerFirstPoll(arrangement, QUEUE_AFTER);
      });

      it('should count no move, so that a screen left loads nothing', () => {
        assert.deepEqual(arrangement.moves, []);
      });
    });
  });
});
