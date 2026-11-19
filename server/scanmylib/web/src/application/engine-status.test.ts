import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { sampleServerStatus } from '../domain/server-status.test-support.ts';
import { ApiError, NetworkError } from './api-errors.ts';
import {
  createFakePageVisibility,
  createFakeStatusSource,
  type FakePageVisibility,
  type FakeStatusSource,
  settle,
} from './engine-status.test-support.ts';
import {
  createEngineStatus,
  type EngineStatus,
  type EngineStatusState,
  POLL_INTERVAL_MILLISECONDS,
} from './engine-status.ts';
import { createFakeScheduler, type FakeScheduler } from './scheduler.test-support.ts';

const UNAUTHORIZED = 401;
const BAD_GATEWAY = 502;
const STATUS = sampleServerStatus();
const UNKNOWN: EngineStatusState = { connection: 'unknown', status: null };

interface Arrangement {
  readonly source: FakeStatusSource;
  readonly visibility: FakePageVisibility;
  readonly scheduler: FakeScheduler;
  readonly engineStatus: EngineStatus;
}

function arrange(isVisible: boolean): Arrangement {
  const source = createFakeStatusSource();
  const visibility = createFakePageVisibility(isVisible);
  const scheduler = createFakeScheduler();
  return { source, visibility, scheduler, engineStatus: createEngineStatus(source, visibility, scheduler) };
}

async function startOnline(): Promise<Arrangement> {
  const arrangement = arrange(true);
  arrangement.engineStatus.start();
  arrangement.source.answer(STATUS);
  await settle();
  return arrangement;
}

describe('The engine status', () => {
  describe('The POLL_INTERVAL_MILLISECONDS constant', () => {
    it('should be three seconds, as the banner of an unreachable server says', () => {
      assert.equal(POLL_INTERVAL_MILLISECONDS, 3000);
    });
  });

  describe('The getSnapshot() method', () => {
    describe('When the engine status has not started', () => {
      let state: EngineStatusState;
      beforeEach(() => {
        state = arrange(true).engineStatus.getSnapshot();
      });

      it('should know neither the connection nor the status', () => {
        assert.deepEqual(state, UNKNOWN);
      });
    });
  });

  describe('The start() method', () => {
    describe('When the page is visible and the api answers', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await startOnline();
      });

      it('should be online, with the status of the api', () => {
        assert.deepEqual(arrangement.engineStatus.getSnapshot(), { connection: 'online', status: STATUS });
      });

      it('should ask the api once', () => {
        assert.equal(arrangement.source.requestCount(), 1);
      });

      it('should plan the next poll after the interval', () => {
        assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), [POLL_INTERVAL_MILLISECONDS]);
      });

      describe('When the next poll is due', () => {
        beforeEach(() => {
          arrangement.scheduler.runPending();
        });

        it('should ask the api again', () => {
          assert.equal(arrangement.source.requestCount(), 2);
        });
      });
    });

    describe('When the page is hidden', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(false);
        arrangement.engineStatus.start();
        arrangement.source.answer(STATUS);
        await settle();
      });

      it('should still ask the api once, so that the header shows a state', () => {
        assert.equal(arrangement.source.requestCount(), 1);
      });

      it('should plan no other poll, so that a hidden page costs the api nothing', () => {
        assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), []);
      });
    });

    describe('When it has already started', () => {
      let source: FakeStatusSource;
      beforeEach(() => {
        const arrangement = arrange(true);
        source = arrangement.source;
        arrangement.engineStatus.start();
        arrangement.engineStatus.start();
      });

      it('should not ask the api a second time', () => {
        assert.equal(source.requestCount(), 1);
      });
    });
  });

  describe('When a poll fails', () => {
    const failures: { situation: string; failure: Error; rule: string; expectedState: EngineStatusState }[] = [
      {
        situation: 'When the api cannot be reached',
        failure: new NetworkError(),
        rule: 'should be offline, and keep the last status the api gave',
        expectedState: { connection: 'offline', status: STATUS },
      },
      {
        situation: 'When the api fails on its side',
        failure: new ApiError(BAD_GATEWAY, ''),
        rule: 'should be offline, and keep the last status the api gave',
        expectedState: { connection: 'offline', status: STATUS },
      },
      {
        situation: 'When the api no longer knows the session',
        failure: new ApiError(UNAUTHORIZED, 'unauthorized'),
        rule: 'should stay online, since the session handles a refused session',
        expectedState: { connection: 'online', status: STATUS },
      },
    ];

    for (const { situation, failure, rule, expectedState } of failures) {
      describe(situation, () => {
        let arrangement: Arrangement;
        beforeEach(async () => {
          arrangement = await startOnline();
          arrangement.scheduler.runPending();
          arrangement.source.fail(failure);
          await settle();
        });

        it(rule, () => {
          assert.deepEqual(arrangement.engineStatus.getSnapshot(), expectedState);
        });

        it('should plan the next poll all the same', () => {
          assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), [POLL_INTERVAL_MILLISECONDS]);
        });
      });
    }

    describe('When the api cannot be reached and then answers again', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await startOnline();
        arrangement.scheduler.runPending();
        arrangement.source.fail(new NetworkError());
        await settle();
        arrangement.scheduler.runPending();
        arrangement.source.answer(STATUS);
        await settle();
      });

      it('should be online again', () => {
        assert.equal(arrangement.engineStatus.getSnapshot().connection, 'online');
      });
    });
  });

  describe('When the page becomes hidden', () => {
    let arrangement: Arrangement;
    beforeEach(async () => {
      arrangement = await startOnline();
      arrangement.visibility.hide();
    });

    it('should cancel the next poll', () => {
      assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), []);
    });

    describe('When the page becomes visible again', () => {
      beforeEach(async () => {
        arrangement.visibility.show();
        arrangement.source.answer(STATUS);
        await settle();
      });

      it('should ask the api at once, without waiting for the interval', () => {
        assert.equal(arrangement.source.requestCount(), 2);
      });

      it('should plan the next poll', () => {
        assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), [POLL_INTERVAL_MILLISECONDS]);
      });
    });
  });

  describe('When the page becomes visible while a poll waits for the api', () => {
    let arrangement: Arrangement;
    beforeEach(async () => {
      arrangement = arrange(true);
      arrangement.engineStatus.start();
      arrangement.visibility.hide();
      arrangement.visibility.show();
      arrangement.source.answer(STATUS);
      await settle();
    });

    it('should share the request in flight, so that the api is asked once at a time', () => {
      assert.equal(arrangement.source.requestCount(), 1);
    });

    it('should plan a single next poll', () => {
      assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), [POLL_INTERVAL_MILLISECONDS]);
    });
  });

  describe('The stop() method', () => {
    describe('When the engine status was online', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = await startOnline();
        arrangement.engineStatus.stop();
      });

      it('should forget the connection and the status, so that a signed-out header shows nothing stale', () => {
        assert.deepEqual(arrangement.engineStatus.getSnapshot(), UNKNOWN);
      });

      it('should cancel the next poll', () => {
        assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), []);
      });

      it('should stop watching the visibility of the page', () => {
        assert.equal(arrangement.visibility.watcherCount(), 0);
      });
    });

    describe('When the api answers a poll after the stop', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange(true);
        arrangement.engineStatus.start();
        arrangement.engineStatus.stop();
        arrangement.source.answer(STATUS);
        await settle();
      });

      it('should keep forgetting the status', () => {
        assert.deepEqual(arrangement.engineStatus.getSnapshot(), UNKNOWN);
      });

      it('should plan no other poll', () => {
        assert.deepEqual(arrangement.scheduler.pendingDelaysMilliseconds(), []);
      });
    });
  });

  describe('The subscribe() method', () => {
    describe('When a poll changes the state', () => {
      let changeCount: number;
      beforeEach(async () => {
        const { source, engineStatus } = arrange(true);
        changeCount = 0;
        engineStatus.subscribe(() => {
          changeCount += 1;
        });
        engineStatus.start();
        source.answer(STATUS);
        await settle();
      });

      it('should tell the listener', () => {
        assert.equal(changeCount, 1);
      });
    });
  });
});
