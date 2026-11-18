import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { createTimerScheduler, type Timers } from '../../../src/adapters/browser/timer-scheduler.ts';

const DELAY_MILLISECONDS = 3000;
const TIMER = 7;

interface RecordingTimers extends Timers {
  readonly started: { readonly task: () => void; readonly delayMilliseconds: number }[];
  readonly cleared: number[];
}

function createRecordingTimers(): RecordingTimers {
  const started: RecordingTimers['started'] = [];
  const cleared: number[] = [];
  return {
    started,
    cleared,
    setTimeout(task, delayMilliseconds) {
      started.push({ task, delayMilliseconds });
      return TIMER;
    },
    clearTimeout(timer) {
      cleared.push(timer);
    },
  };
}

describe('The timer scheduler', () => {
  describe('The schedule() method', () => {
    describe('When a task is scheduled', () => {
      const task = () => {};
      let timers: RecordingTimers;
      beforeEach(() => {
        timers = createRecordingTimers();
        createTimerScheduler(timers).schedule(task, DELAY_MILLISECONDS);
      });

      it("should start a browser's timer for the task, after its delay", () => {
        assert.deepEqual(timers.started, [{ task, delayMilliseconds: DELAY_MILLISECONDS }]);
      });
    });

    describe('When a scheduled task is cancelled', () => {
      let timers: RecordingTimers;
      beforeEach(() => {
        timers = createRecordingTimers();
        const cancel = createTimerScheduler(timers).schedule(() => {}, DELAY_MILLISECONDS);
        cancel();
      });

      it('should clear its timer', () => {
        assert.deepEqual(timers.cleared, [TIMER]);
      });
    });
  });
});
