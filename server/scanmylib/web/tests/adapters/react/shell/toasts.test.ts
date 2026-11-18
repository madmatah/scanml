import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  createToasts,
  MOST_TOASTS_SHOWN,
  TOAST_DURATION_MILLISECONDS,
  type Toast,
  type Toasts,
} from '../../../../src/adapters/react/shell/toasts.ts';
import { createFakeScheduler, type FakeScheduler } from '../../../application/scheduler-fake.ts';

const SAVED = 'Details saved.';
const FAILED = 'Could not sign out.';

function messagesOf(toasts: readonly Toast[]): string[] {
  return toasts.map((toast) => toast.message);
}

describe('The toasts', () => {
  describe('The TOAST_DURATION_MILLISECONDS constant', () => {
    it('should keep an error longer than other news, so that there is time to read what went wrong', () => {
      assert.deepEqual(TOAST_DURATION_MILLISECONDS, { info: 4000, success: 4000, error: 9000 });
    });
  });

  describe('The show() method', () => {
    describe('When a toast is shown', () => {
      let scheduler: FakeScheduler;
      let shown: readonly Toast[];
      beforeEach(() => {
        scheduler = createFakeScheduler();
        const toasts = createToasts(scheduler);
        toasts.show(FAILED, 'error');
        shown = toasts.getSnapshot();
      });

      it('should show its message in its tone', () => {
        assert.deepEqual(
          shown.map(({ message, tone }) => ({ message, tone })),
          [{ message: FAILED, tone: 'error' }],
        );
      });

      it('should plan its dismissal after the duration of its tone', () => {
        assert.deepEqual(scheduler.pendingDelaysMilliseconds(), [TOAST_DURATION_MILLISECONDS.error]);
      });
    });

    describe('When the duration of a toast has passed', () => {
      let toasts: Toasts;
      beforeEach(() => {
        const scheduler = createFakeScheduler();
        toasts = createToasts(scheduler);
        toasts.show(SAVED, 'success');
        scheduler.runPending();
      });

      it('should dismiss it', () => {
        assert.deepEqual(toasts.getSnapshot(), []);
      });
    });

    describe('When more toasts are shown than the screen keeps', () => {
      const messages = ['first', 'second', 'third', 'fourth'];
      let toasts: Toasts;
      beforeEach(() => {
        toasts = createToasts(createFakeScheduler());
        for (const message of messages) toasts.show(message, 'info');
      });

      it('should drop the oldest, so that the newest always shows', () => {
        assert.deepEqual(messagesOf(toasts.getSnapshot()), messages.slice(-MOST_TOASTS_SHOWN));
      });
    });

    describe('When the same message is shown twice', () => {
      let shown: readonly Toast[];
      beforeEach(() => {
        const toasts = createToasts(createFakeScheduler());
        toasts.show(SAVED, 'success');
        toasts.show(SAVED, 'success');
        shown = toasts.getSnapshot();
      });

      it('should give each toast its own id, so that each is dismissed on its own', () => {
        assert.equal(new Set(shown.map((toast) => toast.id)).size, 2);
      });
    });
  });

  describe('The dismiss() method', () => {
    describe('When one of the toasts is dismissed', () => {
      let toasts: Toasts;
      beforeEach(() => {
        toasts = createToasts(createFakeScheduler());
        toasts.show(SAVED, 'success');
        toasts.show(FAILED, 'error');
        toasts.dismiss(toasts.getSnapshot()[0]?.id ?? Number.NaN);
      });

      it('should remove it alone', () => {
        assert.deepEqual(messagesOf(toasts.getSnapshot()), [FAILED]);
      });
    });

    describe('When a toast is dismissed before its duration has passed, and the duration then passes', () => {
      let changeCount: number;
      beforeEach(() => {
        const scheduler = createFakeScheduler();
        const toasts = createToasts(scheduler);
        toasts.show(SAVED, 'success');
        toasts.dismiss(toasts.getSnapshot()[0]?.id ?? Number.NaN);
        changeCount = 0;
        toasts.subscribe(() => {
          changeCount += 1;
        });
        scheduler.runPending();
      });

      it('should change nothing more', () => {
        assert.equal(changeCount, 0);
      });
    });
  });

  describe('The subscribe() method', () => {
    describe('When a toast is shown', () => {
      let changeCount: number;
      beforeEach(() => {
        const toasts = createToasts(createFakeScheduler());
        changeCount = 0;
        toasts.subscribe(() => {
          changeCount += 1;
        });
        toasts.show(SAVED, 'success');
      });

      it('should tell the listener', () => {
        assert.equal(changeCount, 1);
      });
    });

    describe('When the listener has unsubscribed', () => {
      let changeCount: number;
      beforeEach(() => {
        const toasts = createToasts(createFakeScheduler());
        changeCount = 0;
        const unsubscribe = toasts.subscribe(() => {
          changeCount += 1;
        });
        unsubscribe();
        toasts.show(SAVED, 'success');
      });

      it('should no longer tell it', () => {
        assert.equal(changeCount, 0);
      });
    });
  });
});
