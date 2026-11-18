import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { decodeErrorDetail } from '../../../src/adapters/http-api/error-detail.ts';

describe('The error detail', () => {
  describe('The decodeErrorDetail() function', () => {
    const bodies = [
      {
        situation: 'When the detail is a text',
        body: { detail: 'Document not found' },
        rule: 'should give the text',
        expectedDetail: 'Document not found',
      },
      {
        situation: 'When the detail lists the errors of a validation',
        body: { detail: [{ msg: 'Field required', loc: ['body', 'token'] }, { msg: 'Value too long' }] },
        rule: 'should join their messages',
        expectedDetail: 'Field required; Value too long',
      },
      {
        situation: 'When some errors of a validation have no message that is a text',
        body: { detail: [{ loc: ['body'] }, { msg: 42 }, 'Field required', null, { msg: 'Value too long' }] },
        rule: 'should keep only the messages that are texts',
        expectedDetail: 'Value too long',
      },
      {
        situation: 'When the detail is neither a text nor a list',
        body: { detail: { msg: 'Field required' } },
        rule: 'should give no detail',
        expectedDetail: '',
      },
      {
        situation: 'When the body holds no detail',
        body: { error: 'Bad gateway' },
        rule: 'should give no detail',
        expectedDetail: '',
      },
      {
        situation: 'When the body is not an object',
        body: 'Bad gateway',
        rule: 'should give no detail',
        expectedDetail: '',
      },
      {
        situation: 'When there is no body',
        body: null,
        rule: 'should give no detail',
        expectedDetail: '',
      },
    ];

    for (const { situation, body, rule, expectedDetail } of bodies) {
      describe(situation, () => {
        let detail: string;
        beforeEach(() => {
          detail = decodeErrorDetail(body);
        });

        it(rule, () => {
          assert.equal(detail, expectedDetail);
        });
      });
    }
  });
});
