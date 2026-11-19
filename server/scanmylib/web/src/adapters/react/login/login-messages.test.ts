import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { ApiError, NetworkError } from '../../../application/api-errors.ts';
import type { SignedOutNotice } from '../../../application/session.ts';
import { CATALOGS } from '../../i18next/catalogs.ts';
import { createLocalizationFor } from '../../i18next/localization.test-support.ts';
import { type LoginError, loginErrorText, signedOutNoticeText } from './login-messages.ts';

const ENGLISH_LANGUAGES = ['en-US'];
const UNAUTHORIZED = 401;
const SERVER_FAILURE = 500;
const NOT_RESPONDING =
  'The ScanMyLib server is not responding. Check that it is running and that you are on the same network.';

describe('The login messages', () => {
  describe('The loginErrorText() function', () => {
    const errors: { situation: string; error: LoginError; rule: string; expectedText: string }[] = [
      {
        situation: 'When the token is missing',
        error: { reason: 'missing-token' },
        rule: 'should ask for it',
        expectedText: 'Enter the access token.',
      },
      {
        situation: 'When the api refuses the token',
        error: { reason: 'refused', failure: new ApiError(UNAUTHORIZED, 'invalid token') },
        rule: 'should say that the token is invalid, rather than that a session expired',
        expectedText: 'Invalid access token. Check it and try again.',
      },
      {
        situation: 'When the api cannot be reached',
        error: { reason: 'refused', failure: new NetworkError() },
        rule: 'should say that the server is not responding',
        expectedText: NOT_RESPONDING,
      },
      {
        situation: 'When the api fails for another reason',
        error: { reason: 'refused', failure: new ApiError(SERVER_FAILURE, 'database is locked') },
        rule: 'should say that the sign-in failed, with the detail of the api',
        expectedText: 'Could not sign in. (database is locked)',
      },
    ];

    for (const { situation, error, rule, expectedText } of errors) {
      describe(situation, () => {
        let text: string;
        beforeEach(async () => {
          const { i18next } = await createLocalizationFor(ENGLISH_LANGUAGES, CATALOGS);
          text = loginErrorText(i18next.t, error);
        });

        it(rule, () => {
          assert.equal(text, expectedText);
        });
      });
    }
  });

  describe('The signedOutNoticeText() function', () => {
    const notices: { situation: string; notice: SignedOutNotice; rule: string; expectedText: string }[] = [
      {
        situation: 'When the session of a signed-in browser has expired',
        notice: { reason: 'expired' },
        rule: 'should ask to sign in again',
        expectedText: 'Your session has expired: please sign in again.',
      },
      {
        situation: 'When the api refused the token of a sign-in link',
        notice: { reason: 'link-refused' },
        rule: 'should say that the link holds an invalid or expired token',
        expectedText: 'The sign-in link contains an invalid or expired token.',
      },
      {
        situation: 'When a sign-in link failed for another reason',
        notice: { reason: 'link-failed', failure: new ApiError(SERVER_FAILURE, 'database is locked') },
        rule: 'should say that the sign-in failed, with the detail of the api',
        expectedText: 'Could not sign in. (database is locked)',
      },
      {
        situation: 'When the check of the session could not reach the api',
        notice: { reason: 'check-failed', failure: new NetworkError() },
        rule: 'should say that the server is not responding',
        expectedText: NOT_RESPONDING,
      },
      {
        situation: 'When the check of the session failed for another reason',
        notice: { reason: 'check-failed', failure: new ApiError(SERVER_FAILURE, '') },
        rule: 'should say that the server is not responding correctly',
        expectedText: 'The ScanMyLib server is not responding correctly.',
      },
    ];

    for (const { situation, notice, rule, expectedText } of notices) {
      describe(situation, () => {
        let text: string;
        beforeEach(async () => {
          const { i18next } = await createLocalizationFor(ENGLISH_LANGUAGES, CATALOGS);
          text = signedOutNoticeText(i18next.t, notice);
        });

        it(rule, () => {
          assert.equal(text, expectedText);
        });
      });
    }
  });
});
