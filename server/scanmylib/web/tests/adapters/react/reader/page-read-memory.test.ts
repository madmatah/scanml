import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { isAddressOf, pageReadIn, withPageRead } from '../../../../src/adapters/react/reader/page-read-memory.ts';

const READER_PATH = '/documents/95bbeb79-4351-432f-a53c-d3658892ff50/read';

describe('The memory of the page read', () => {
  describe('The pageReadIn() function', () => {
    const rows: { situation: string; historyState: unknown; expected: string | null }[] = [
      {
        situation: 'When the entry holds the page read, beside the router’s state',
        historyState: { usr: null, key: 'default', idx: 2, readingPage: 'k-12' },
        expected: 'k-12',
      },
      { situation: 'When the entry holds no page read', historyState: { idx: 0 }, expected: null },
      { situation: 'When the entry has no state', historyState: null, expected: null },
      { situation: 'When the page read is not a text', historyState: { readingPage: 12 }, expected: null },
    ];

    for (const { situation, historyState, expected } of rows) {
      describe(situation, () => {
        let pageKey: string | null;
        beforeEach(() => {
          pageKey = pageReadIn(historyState);
        });

        it(`should give ${expected === null ? 'none' : 'it'}`, () => {
          assert.equal(pageKey, expected);
        });
      });
    }
  });

  describe('The withPageRead() function', () => {
    describe('When the entry holds the router’s state', () => {
      let historyState: Record<string, unknown>;
      beforeEach(() => {
        historyState = withPageRead({ usr: null, key: 'default', idx: 2, readingPage: 'k-12' }, 'k-45');
      });

      it('should keep the router’s state and replace the page read, under the name earlier releases gave it', () => {
        assert.deepEqual(historyState, { usr: null, key: 'default', idx: 2, readingPage: 'k-45' });
      });
    });

    describe('When the entry has no state', () => {
      let historyState: Record<string, unknown>;
      beforeEach(() => {
        historyState = withPageRead(null, 'k-45');
      });

      it('should hold only the page read', () => {
        assert.deepEqual(historyState, { readingPage: 'k-45' });
      });
    });
  });

  describe('The isAddressOf() function', () => {
    describe('When the address bar shows the reader', () => {
      let isReaderAddress: boolean;
      beforeEach(() => {
        isReaderAddress = isAddressOf(`#${READER_PATH}`, READER_PATH);
      });

      it('should say yes', () => {
        assert.equal(isReaderAddress, true);
      });
    });

    describe('When the address bar already shows another screen', () => {
      let isReaderAddress: boolean;
      beforeEach(() => {
        isReaderAddress = isAddressOf('#/pages/de215798-031a-4b20-a867-49c12e3baabe', READER_PATH);
      });

      it('should say no, so that the page read is not written into another screen’s entry', () => {
        assert.equal(isReaderAddress, false);
      });
    });
  });
});
