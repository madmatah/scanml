import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { sampleServerStatus } from './server-status.test-support.ts';
import { hasQueueMoved, queueKeyOf } from './server-status.ts';

describe('The server status', () => {
  describe('The queueKeyOf() function', () => {
    describe('When no status is known', () => {
      let key: string | null;
      beforeEach(() => {
        key = queueKeyOf(null);
      });

      it('should give none', () => {
        assert.equal(key, null);
      });
    });

    describe('When two statuses differ only by the done count of the queue', () => {
      let keys: (string | null)[];
      beforeEach(() => {
        keys = [
          queueKeyOf(sampleServerStatus({ queue: { doneCount: 10 } })),
          queueKeyOf(sampleServerStatus({ queue: { doneCount: 11 } })),
        ];
      });

      it('should give each its own key, since a page whose text is ready changes a document', () => {
        assert.notEqual(keys[0], keys[1]);
      });
    });

    describe('When two statuses differ only by the state of the engine', () => {
      let keys: (string | null)[];
      beforeEach(() => {
        keys = [
          queueKeyOf(sampleServerStatus({ engine: { state: 'idle' } })),
          queueKeyOf(sampleServerStatus({ engine: { state: 'ready' } })),
        ];
      });

      it('should give them the same key, since no document changed', () => {
        assert.equal(keys[0], keys[1]);
      });
    });
  });

  describe('The hasQueueMoved() function', () => {
    const situations: {
      situation: string;
      previousKey: string | null;
      key: string;
      rule: string;
      expected: boolean;
    }[] = [
      {
        situation: 'When the first status comes',
        previousKey: null,
        key: '0/0/7/0',
        rule: 'should not count it as a move, since the list was just loaded',
        expected: false,
      },
      {
        situation: 'When the queue is as it was',
        previousKey: '0/0/7/0',
        key: '0/0/7/0',
        rule: 'should not count it as a move',
        expected: false,
      },
      {
        situation: 'When the queue changed',
        previousKey: '0/1/7/0',
        key: '0/0/8/0',
        rule: 'should count it as a move, so that the library loads again',
        expected: true,
      },
    ];

    for (const { situation, previousKey, key, rule, expected } of situations) {
      describe(situation, () => {
        let hasMoved: boolean;
        beforeEach(() => {
          hasMoved = hasQueueMoved(previousKey, key);
        });

        it(rule, () => {
          assert.equal(hasMoved, expected);
        });
      });
    }
  });
});
