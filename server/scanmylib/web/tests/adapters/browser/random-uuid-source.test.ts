import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { createRandomUuidSource, type RandomValues } from '../../../src/adapters/browser/random-uuid-source.ts';

const VERSION_4_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function fixedRandomValues(byte: number): RandomValues {
  return {
    getRandomValues(array) {
      array.fill(byte);
      return array;
    },
  };
}

describe('The random uuid source', () => {
  describe('The createUuid() function', () => {
    describe('When every random byte has all its bits set', () => {
      let uuid: string;
      beforeEach(() => {
        uuid = createRandomUuidSource(fixedRandomValues(0xff)).createUuid();
      });

      it('should still mark it as a random uuid of version 4 and of the standard variant', () => {
        assert.equal(uuid, 'ffffffff-ffff-4fff-bfff-ffffffffffff');
      });
    });

    describe('When every random byte is zero', () => {
      let uuid: string;
      beforeEach(() => {
        uuid = createRandomUuidSource(fixedRandomValues(0)).createUuid();
      });

      it('should still mark it as a random uuid of version 4 and of the standard variant', () => {
        assert.equal(uuid, '00000000-0000-4000-8000-000000000000');
      });
    });

    describe('When the bytes come from the platform', () => {
      let uuids: string[];
      beforeEach(() => {
        const source = createRandomUuidSource(crypto);
        uuids = [source.createUuid(), source.createUuid()];
      });

      it('should write each in the form of a version 4 uuid, which the api accepts as a document id', () => {
        assert.deepEqual(
          uuids.map((uuid) => VERSION_4_UUID.test(uuid)),
          [true, true],
        );
      });

      it('should give a new one each time', () => {
        assert.notEqual(uuids[0], uuids[1]);
      });
    });
  });
});
