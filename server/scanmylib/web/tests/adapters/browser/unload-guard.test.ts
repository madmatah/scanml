import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { guardUnload, type LeavingEvent } from '../../../src/adapters/browser/unload-guard.ts';

interface StubEvent extends LeavingEvent {
  isPrevented: boolean;
}

function createStubEvent(): StubEvent {
  const event: StubEvent = {
    isPrevented: false,
    returnValue: undefined,
    preventDefault: () => {
      event.isPrevented = true;
    },
  };
  return event;
}

function leaveGuardedPage(isWorking: boolean): StubEvent {
  const listeners: ((event: LeavingEvent) => void)[] = [];
  guardUnload({ addEventListener: (_type, listener) => listeners.push(listener) }, () => isWorking);
  const event = createStubEvent();
  for (const listener of listeners) listener(event);
  return event;
}

describe('The unload guard', () => {
  describe('The guardUnload() function', () => {
    describe('When the page is left while work runs', () => {
      let event: StubEvent;
      beforeEach(() => {
        event = leaveGuardedPage(true);
      });

      it('should make the browser ask, in the ways every browser reads', () => {
        assert.deepEqual(
          { isPrevented: event.isPrevented, returnValue: event.returnValue },
          {
            isPrevented: true,
            returnValue: '',
          },
        );
      });
    });

    describe('When the page is left with nothing running', () => {
      let event: StubEvent;
      beforeEach(() => {
        event = leaveGuardedPage(false);
      });

      it('should let it go without a question', () => {
        assert.deepEqual(
          { isPrevented: event.isPrevented, returnValue: event.returnValue },
          {
            isPrevented: false,
            returnValue: undefined,
          },
        );
      });
    });
  });
});
