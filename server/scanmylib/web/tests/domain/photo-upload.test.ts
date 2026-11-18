import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { checkPhoto, MAX_UPLOAD_BYTES, type Photo, type PhotoRejection } from '../../src/domain/photo-upload.ts';

const JPEG_SIZE_BYTES = 2_000_000;

describe('The photo upload', () => {
  describe('The checkPhoto() function', () => {
    const rows: { situation: string; rule: string; photo: Photo; expected: PhotoRejection | null }[] = [
      {
        situation: 'the photo is a JPEG of a usual size',
        rule: 'should accept it',
        photo: { type: 'image/jpeg', size: JPEG_SIZE_BYTES },
        expected: null,
      },
      {
        situation: 'the photo is a PNG',
        rule: 'should accept it',
        photo: { type: 'image/png', size: JPEG_SIZE_BYTES },
        expected: null,
      },
      {
        situation: 'the photo is a WebP',
        rule: 'should accept it',
        photo: { type: 'image/webp', size: JPEG_SIZE_BYTES },
        expected: null,
      },
      {
        situation: 'the photo is in a format the api does not read',
        rule: 'should refuse it for its format',
        photo: { type: 'image/gif', size: JPEG_SIZE_BYTES },
        expected: { kind: 'unsupported-format' },
      },
      {
        situation: 'the photo has no type',
        rule: 'should accept it, since some Android pickers give none and the server decides then',
        photo: { type: '', size: JPEG_SIZE_BYTES },
        expected: null,
      },
      {
        situation: 'the photo is larger than the most the api takes',
        rule: 'should refuse it for its size',
        photo: { type: 'image/jpeg', size: MAX_UPLOAD_BYTES + 1 },
        expected: { kind: 'too-large' },
      },
      {
        situation: 'the photo is exactly the most the api takes',
        rule: 'should accept it',
        photo: { type: 'image/jpeg', size: MAX_UPLOAD_BYTES },
        expected: null,
      },
      {
        situation: 'the photo is empty',
        rule: 'should refuse it as empty',
        photo: { type: 'image/jpeg', size: 0 },
        expected: { kind: 'empty' },
      },
    ];

    for (const { situation, rule, photo, expected } of rows) {
      describe(`When ${situation}`, () => {
        let rejection: PhotoRejection | null;
        beforeEach(() => {
          rejection = checkPhoto(photo);
        });

        it(rule, () => {
          assert.deepEqual(rejection, expected);
        });
      });
    }
  });

  describe('The MAX_UPLOAD_BYTES constant', () => {
    it('should be 40 MiB, the most the api takes', () => {
      assert.equal(MAX_UPLOAD_BYTES, 40 * 1024 * 1024);
    });
  });
});
