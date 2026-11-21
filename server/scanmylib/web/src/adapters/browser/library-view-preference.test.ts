import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import type { LibraryView } from '../../domain/library-view.ts';
import type { KeyValueStorage } from './key-value-storage.ts';
import { createLibraryViewPreference } from './library-view-preference.ts';

// The key that browsers which chose a view hold: another one would forget their choice.
const LIBRARY_VIEW_KEY = 'scanmylib.library-view';

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

describe('The library view preference', () => {
  describe('The save() method', () => {
    describe('When a view is chosen', () => {
      let storage: ReturnType<typeof createStorage>;
      beforeEach(() => {
        storage = createStorage({ [LIBRARY_VIEW_KEY]: 'cards' });
        createLibraryViewPreference(() => storage).save('list');
      });

      it('should store it under its key, in place of the view chosen before', () => {
        assert.deepEqual([...storage.entries], [[LIBRARY_VIEW_KEY, 'list']]);
      });
    });

    describe('When the storage is disabled', () => {
      let act: () => void;
      beforeEach(() => {
        act = () => createLibraryViewPreference(disabledStorage).save('list');
      });

      it('should not fail, since the next visit shows the cards instead', () => {
        assert.doesNotThrow(act);
      });
    });
  });

  describe('The readSaved() method', () => {
    const situations: {
      situation: string;
      openStorage: () => KeyValueStorage;
      rule: string;
      expected: LibraryView | null;
    }[] = [
      {
        situation: 'When the list was chosen',
        openStorage: () => createStorage({ [LIBRARY_VIEW_KEY]: 'list' }),
        rule: 'should read the list',
        expected: 'list',
      },
      {
        situation: 'When no view was chosen',
        openStorage: () => createStorage(),
        rule: 'should read nothing',
        expected: null,
      },
      {
        situation: 'When the key holds a value that names no view',
        openStorage: () => createStorage({ [LIBRARY_VIEW_KEY]: 'table' }),
        rule: 'should read nothing, rather than a view the screen cannot draw',
        expected: null,
      },
      {
        situation: 'When the storage is disabled',
        openStorage: disabledStorage,
        rule: 'should read nothing',
        expected: null,
      },
    ];

    for (const { situation, openStorage, rule, expected } of situations) {
      describe(situation, () => {
        let saved: LibraryView | null;
        beforeEach(() => {
          saved = createLibraryViewPreference(openStorage).readSaved();
        });

        it(rule, () => {
          assert.equal(saved, expected);
        });
      });
    }
  });
});
