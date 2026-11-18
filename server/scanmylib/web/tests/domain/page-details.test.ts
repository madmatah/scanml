import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  isBeingRead,
  type PageDetails,
  type PageNeighbors,
  type PageNumberEntry,
  pageNeighbors,
  readPageNumberEntry,
  turnedLeft,
  turnedRight,
  typedNumberOf,
} from '../../src/domain/page-details.ts';
import { samplePage } from './document-details-samples.ts';
import { samplePageDetails } from './page-details-samples.ts';

describe('The page details', () => {
  describe('The isBeingRead() function', () => {
    const rows: { status: string; expected: boolean; rule: string }[] = [
      { status: 'queued', expected: true, rule: 'should be true for a page waiting for its text' },
      { status: 'processing', expected: true, rule: 'should be true for a page whose text is being read' },
      { status: 'done', expected: false, rule: 'should be false for a page whose text is read' },
      { status: 'error', expected: false, rule: 'should be false for a page that could not be read' },
    ];

    for (const { status, expected, rule } of rows) {
      describe(`When the page is ${status}`, () => {
        let isRead: boolean;
        beforeEach(() => {
          isRead = isBeingRead(status);
        });

        it(rule, () => {
          assert.equal(isRead, expected);
        });
      });
    }
  });

  describe('The pageNeighbors() function', () => {
    const pages = [samplePage('first'), samplePage('middle'), samplePage('last')];

    describe('When the page is between two others', () => {
      let neighbors: PageNeighbors;
      beforeEach(() => {
        neighbors = pageNeighbors(pages, 'middle');
      });

      it('should give the pages before and after it, and its place among them', () => {
        assert.deepEqual(
          { previous: neighbors.previous?.id, next: neighbors.next?.id, position: neighbors.position },
          { previous: 'first', next: 'last', position: { index: 1, count: 3 } },
        );
      });
    });

    describe('When the page is the first one', () => {
      let neighbors: PageNeighbors;
      beforeEach(() => {
        neighbors = pageNeighbors(pages, 'first');
      });

      it('should give no previous page', () => {
        assert.deepEqual(
          { previous: neighbors.previous, next: neighbors.next?.id },
          { previous: null, next: 'middle' },
        );
      });
    });

    describe('When the page is the last one', () => {
      let neighbors: PageNeighbors;
      beforeEach(() => {
        neighbors = pageNeighbors(pages, 'last');
      });

      it('should give no next page', () => {
        assert.deepEqual(
          { previous: neighbors.previous?.id, next: neighbors.next },
          { previous: 'middle', next: null },
        );
      });
    });

    describe('When the document no longer lists the page', () => {
      let neighbors: PageNeighbors;
      beforeEach(() => {
        neighbors = pageNeighbors(pages, 'deleted');
      });

      it('should give no neighbor and no place, rather than the last page as the previous one', () => {
        assert.deepEqual(neighbors, { previous: null, next: null, position: null });
      });
    });
  });

  describe('The typedNumberOf() function', () => {
    const rows: { situation: string; changes: Partial<PageDetails>; expected: number | null; rule: string }[] = [
      {
        situation: 'When the page has a detected number',
        changes: { number: 11, pageLabel: '11' },
        expected: 11,
        rule: 'should be that number',
      },
      {
        situation: 'When the number was typed by hand',
        changes: { number: 12, pageLabel: '12', manualNumber: 12 },
        expected: 12,
        rule: 'should be the number typed',
      },
      {
        situation: 'When the page is numbered in roman numerals',
        changes: { number: -9996, pageLabel: 'iv' },
        expected: null,
        rule: 'should be none, since a number field takes digits only',
      },
      {
        situation: 'When the page has no number',
        changes: { number: null, pageLabel: null },
        expected: null,
        rule: 'should be none',
      },
    ];

    for (const { situation, changes, expected, rule } of rows) {
      describe(situation, () => {
        let typedNumber: number | null;
        beforeEach(() => {
          typedNumber = typedNumberOf(samplePageDetails(changes));
        });

        it(rule, () => {
          assert.equal(typedNumber, expected);
        });
      });
    }
  });

  describe('The readPageNumberEntry() function', () => {
    const rows: { situation: string; text: string; expected: PageNumberEntry }[] = [
      { situation: 'When a whole number is typed', text: '42', expected: { isValid: true, number: 42 } },
      { situation: 'When the lowest number is typed', text: '1', expected: { isValid: true, number: 1 } },
      { situation: 'When the highest number is typed', text: '9999', expected: { isValid: true, number: 9999 } },
      { situation: 'When nothing is typed', text: '', expected: { isValid: false } },
      { situation: 'When only spaces are typed', text: '  ', expected: { isValid: false } },
      { situation: 'When zero is typed', text: '0', expected: { isValid: false } },
      { situation: 'When a number above the highest is typed', text: '10000', expected: { isValid: false } },
      { situation: 'When a decimal number is typed', text: '4.5', expected: { isValid: false } },
      { situation: 'When a word is typed', text: 'iv', expected: { isValid: false } },
    ];

    for (const { situation, text, expected } of rows) {
      describe(situation, () => {
        let entry: PageNumberEntry;
        beforeEach(() => {
          entry = readPageNumberEntry(text);
        });

        it(expected.isValid ? 'should give that number' : 'should refuse it', () => {
          assert.deepEqual(entry, expected);
        });
      });
    }
  });

  describe('The turnedLeft() function', () => {
    describe('When the page is upright', () => {
      let rotation: number;
      beforeEach(() => {
        rotation = turnedLeft(0);
      });

      it('should turn it to three quarters, never to a negative angle', () => {
        assert.equal(rotation, 270);
      });
    });

    describe('When the page is turned a quarter', () => {
      let rotation: number;
      beforeEach(() => {
        rotation = turnedLeft(90);
      });

      it('should bring it upright', () => {
        assert.equal(rotation, 0);
      });
    });
  });

  describe('The turnedRight() function', () => {
    describe('When the page is upright', () => {
      let rotation: number;
      beforeEach(() => {
        rotation = turnedRight(0);
      });

      it('should turn it a quarter', () => {
        assert.equal(rotation, 90);
      });
    });

    describe('When the page is turned three quarters', () => {
      let rotation: number;
      beforeEach(() => {
        rotation = turnedRight(270);
      });

      it('should bring it upright, never past a whole turn', () => {
        assert.equal(rotation, 0);
      });
    });
  });
});
