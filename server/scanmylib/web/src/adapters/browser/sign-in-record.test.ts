import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { createSignInRecord, type KeyValueStorage } from './sign-in-record.ts';

// The key and the value that browsers signed in to earlier releases hold: another one would sign them out.
const SIGNED_IN_KEY = 'scanmylib.signed-in';
const SIGNED_IN = '1';

const createStorage = (
  entries: Record<string, string> = {},
): KeyValueStorage & { readonly entries: Map<string, string> } => {
  const stored = new Map(Object.entries(entries));
  return {
    entries: stored,
    getItem: (key) => stored.get(key) ?? null,
    setItem: (key, value) => {
      stored.set(key, value);
    },
    removeItem: (key) => {
      stored.delete(key);
    },
  };
};

const disabledStorage = (): KeyValueStorage => {
  throw new DOMException('The operation is insecure.', 'SecurityError');
};

describe('The sign-in record', () => {
  describe('The record() method', () => {
    describe('When this browser signs in', () => {
      let storage: ReturnType<typeof createStorage>;
      beforeEach(() => {
        storage = createStorage();
        createSignInRecord(() => storage).record(true);
      });

      it('should store the value of a sign-in under its key', () => {
        assert.deepEqual([...storage.entries], [[SIGNED_IN_KEY, SIGNED_IN]]);
      });
    });

    describe('When this browser signs out', () => {
      let storage: ReturnType<typeof createStorage>;
      beforeEach(() => {
        storage = createStorage({ [SIGNED_IN_KEY]: SIGNED_IN });
        createSignInRecord(() => storage).record(false);
      });

      it('should remove the key', () => {
        assert.deepEqual([...storage.entries], []);
      });
    });

    describe('When the storage is disabled', () => {
      let act: () => void;
      beforeEach(() => {
        act = () => createSignInRecord(disabledStorage).record(true);
      });

      it('should not fail, since the next visit asks the api instead', () => {
        assert.doesNotThrow(act);
      });
    });
  });

  describe('The readRecorded() method', () => {
    const records = [
      {
        situation: 'When the key holds the value of a sign-in',
        entries: { [SIGNED_IN_KEY]: SIGNED_IN },
        rule: 'should say that this browser signed in',
        expectedRecord: true,
      },
      {
        situation: 'When the key is missing',
        entries: {},
        rule: 'should say that this browser did not sign in',
        expectedRecord: false,
      },
      {
        situation: 'When the key holds another value',
        entries: { [SIGNED_IN_KEY]: 'true' },
        rule: 'should say that this browser did not sign in',
        expectedRecord: false,
      },
    ];

    for (const { situation, entries, rule, expectedRecord } of records) {
      describe(situation, () => {
        let recorded: boolean | null;
        beforeEach(() => {
          const storage = createStorage(entries);
          recorded = createSignInRecord(() => storage).readRecorded();
        });

        it(rule, () => {
          assert.equal(recorded, expectedRecord);
        });
      });
    }

    describe('When the storage is disabled', () => {
      let recorded: boolean | null;
      beforeEach(() => {
        recorded = createSignInRecord(disabledStorage).readRecorded();
      });

      it('should say that it cannot tell', () => {
        assert.equal(recorded, null);
      });
    });
  });
});
