import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  createNumberFormatting,
  type ElapsedTime,
  elapsedTime,
  type LocalDate,
  localIsoString,
  partialWholePercent,
} from './formatting.ts';

const ENGLISH_LOCALE = 'en-US';
const FRENCH_LOCALE = 'fr-FR';

describe('The formatting', () => {
  describe('The formatNumber() function of a number formatting', () => {
    const number = 1234;

    describe('When the locale is English', () => {
      let text: string;
      beforeEach(() => {
        text = createNumberFormatting(ENGLISH_LOCALE).formatNumber(number);
      });

      it('should group the thousands with a comma', () => {
        assert.equal(text, '1,234');
      });
    });

    describe('When the locale is French', () => {
      const frenchIntegers = new Intl.NumberFormat(FRENCH_LOCALE);
      let text: string;
      beforeEach(() => {
        text = createNumberFormatting(FRENCH_LOCALE).formatNumber(number);
      });

      it('should write the number as Intl does for French', () => {
        assert.equal(text, frenchIntegers.format(number));
      });
    });
  });

  describe('The partialWholePercent() function', () => {
    const situations: { situation: string; ratio: number; rule: string; expected: number }[] = [
      {
        situation: 'When the part is almost the whole',
        ratio: 299 / 300,
        rule: 'should read 99, since only the whole reads 100',
        expected: 99,
      },
      {
        situation: 'When the part is almost nothing',
        ratio: 2 / 500,
        rule: 'should read 1, since only nothing reads 0',
        expected: 1,
      },
      {
        situation: 'When the part is well inside the whole',
        ratio: 9 / 11,
        rule: 'should round to the nearest whole percent',
        expected: 82,
      },
    ];

    for (const { situation, ratio, rule, expected } of situations) {
      describe(situation, () => {
        let percent: number;
        beforeEach(() => {
          percent = partialWholePercent(ratio);
        });

        it(rule, () => {
          assert.equal(percent, expected);
        });
      });
    }
  });

  describe('The elapsedTime() function', () => {
    const nowMilliseconds = Date.UTC(2026, 10, 18, 12, 0, 0);
    const secondMilliseconds = 1000;
    const minuteMilliseconds = 60 * secondMilliseconds;
    const hourMilliseconds = 60 * minuteMilliseconds;
    const dayMilliseconds = 24 * hourMilliseconds;
    const situations: { situation: string; ageMilliseconds: number; rule: string; expected: ElapsedTime }[] = [
      {
        situation: 'When the date is less than 45 seconds old',
        ageMilliseconds: 44 * secondMilliseconds,
        rule: 'should be just now',
        expected: { kind: 'just-now' },
      },
      {
        situation: 'When the date is less than 45 seconds ahead',
        ageMilliseconds: -44 * secondMilliseconds,
        rule: 'should be just now too, so that a clock slightly behind the api says nothing odd',
        expected: { kind: 'just-now' },
      },
      {
        situation: 'When the date is 50 seconds old',
        ageMilliseconds: 50 * secondMilliseconds,
        rule: 'should count the seconds before now',
        expected: { kind: 'relative', amount: -50, unit: 'second' },
      },
      {
        situation: 'When the date is 9 minutes and 20 seconds old',
        ageMilliseconds: 9 * minuteMilliseconds + 20 * secondMilliseconds,
        rule: 'should count the whole minutes, rounded',
        expected: { kind: 'relative', amount: -9, unit: 'minute' },
      },
      {
        situation: 'When the date is 5 hours old',
        ageMilliseconds: 5 * hourMilliseconds,
        rule: 'should count the hours',
        expected: { kind: 'relative', amount: -5, unit: 'hour' },
      },
      {
        situation: 'When the date is 4 days old',
        ageMilliseconds: 4 * dayMilliseconds,
        rule: 'should count the days',
        expected: { kind: 'relative', amount: -4, unit: 'day' },
      },
      {
        situation: 'When the date is a week old',
        ageMilliseconds: 7 * dayMilliseconds,
        rule: 'should give the date itself',
        expected: { kind: 'absolute' },
      },
    ];

    for (const { situation, ageMilliseconds, rule, expected } of situations) {
      describe(situation, () => {
        let elapsed: ElapsedTime;
        beforeEach(() => {
          elapsed = elapsedTime(nowMilliseconds - ageMilliseconds, nowMilliseconds);
        });

        it(rule, () => {
          assert.deepEqual(elapsed, expected);
        });
      });
    }
  });

  describe('The localIsoString() function', () => {
    const localDate = (offsetMinutes: number): LocalDate => {
      return {
        getFullYear: () => 2026,
        getMonth: () => 2,
        getDate: () => 7,
        getHours: () => 9,
        getMinutes: () => 5,
        getSeconds: () => 3,
        getTimezoneOffset: () => offsetMinutes,
      };
    };

    const situations: { situation: string; offsetMinutes: number; rule: string; expected: string }[] = [
      {
        situation: 'When the browser is two hours ahead of UTC',
        offsetMinutes: -120,
        rule: 'should write the local time, padded, with a positive offset',
        expected: '2026-03-07T09:05:03+02:00',
      },
      {
        situation: 'When the browser is five hours and a half behind UTC',
        offsetMinutes: 330,
        rule: 'should write a negative offset with its minutes',
        expected: '2026-03-07T09:05:03-05:30',
      },
      {
        situation: 'When the browser is at UTC',
        offsetMinutes: 0,
        rule: 'should write a zero offset as positive',
        expected: '2026-03-07T09:05:03+00:00',
      },
    ];

    for (const { situation, offsetMinutes, rule, expected } of situations) {
      describe(situation, () => {
        let written: string;
        beforeEach(() => {
          written = localIsoString(localDate(offsetMinutes));
        });

        it(rule, () => {
          assert.equal(written, expected);
        });
      });
    }
  });
});
