// French is written only in the French catalog, so these tests compare with its entries instead of quoting it.
import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import frenchCatalog from '../../../../locales/fr.json' with { type: 'json' };
import { ApiError, NetworkError } from '../../../application/api-errors.ts';
import { CATALOGS } from '../../i18next/catalogs.ts';
import { createLocalizationFor } from '../../i18next/localization.test-support.ts';
import { errorMessage } from './error-message.ts';

const ENGLISH_LANGUAGES = ['en-US'];
const FRENCH_LANGUAGES = ['fr-FR'];
const FALLBACK = 'Could not sign in.';
const SERVER_FAILURE = 500;

describe('The error message', () => {
  describe('The errorMessage() function', () => {
    const failures = [
      {
        situation: 'When the api cannot be reached',
        failure: new NetworkError(),
        rule: 'should say that the server is not responding, and what to check',
        expectedMessage:
          'The ScanMyLib server is not responding. Check that it is running and that you are on the same network.',
      },
      {
        situation: 'When the api no longer knows the session',
        failure: new ApiError(401, 'unauthorized'),
        rule: 'should say that the session expired',
        expectedMessage: 'Session expired: please sign in again.',
      },
      {
        situation: 'When the api does not find the item',
        failure: new ApiError(404, 'Document not found'),
        rule: 'should say that the item may have been deleted',
        expectedMessage: 'Item not found: it may have been deleted.',
      },
      {
        situation: 'When the api refuses a file too large',
        failure: new ApiError(413, 'Request body too large'),
        rule: 'should give the largest size',
        expectedMessage: 'File too large (40 MiB maximum).',
      },
      {
        situation: 'When the api refuses the format of a file',
        failure: new ApiError(415, 'Unsupported media type'),
        rule: 'should give the formats it accepts',
        expectedMessage: 'Unsupported format (JPEG, PNG or WebP only).',
      },
      {
        situation: 'When the api refuses for another reason, with a detail',
        failure: new ApiError(SERVER_FAILURE, 'database is locked'),
        rule: 'should give the message of the caller, followed by the detail of the api',
        expectedMessage: `${FALLBACK} (database is locked)`,
      },
      {
        situation: 'When the api refuses for another reason, without a detail',
        failure: new ApiError(SERVER_FAILURE, ''),
        rule: 'should give the message of the caller',
        expectedMessage: FALLBACK,
      },
      {
        situation: 'When the failure does not come from the api',
        failure: new TypeError('response.json is not a function'),
        rule: 'should give the message of the caller, and nothing of the failure',
        expectedMessage: FALLBACK,
      },
    ];

    for (const { situation, failure, rule, expectedMessage } of failures) {
      describe(situation, () => {
        let message: string;
        beforeEach(async () => {
          const { i18next } = await createLocalizationFor(ENGLISH_LANGUAGES, CATALOGS);
          message = errorMessage(i18next.t, failure, FALLBACK);
        });

        it(rule, () => {
          assert.equal(message, expectedMessage);
        });
      });
    }

    describe('When the caller gives no message of its own', () => {
      let message: string;
      beforeEach(async () => {
        const { i18next } = await createLocalizationFor(ENGLISH_LANGUAGES, CATALOGS);
        message = errorMessage(i18next.t, new TypeError('response.json is not a function'));
      });

      it('should say that an unexpected error occurred', () => {
        assert.equal(message, 'An unexpected error occurred.');
      });
    });

    describe('When the UI is in French and the api refuses with a detail', () => {
      let message: string;
      beforeEach(async () => {
        const { i18next } = await createLocalizationFor(FRENCH_LANGUAGES, CATALOGS);
        message = errorMessage(i18next.t, new ApiError(SERVER_FAILURE, 'database is locked'));
      });

      it('should give the French message, followed by the detail of the api as it came', () => {
        assert.equal(message, `${frenchCatalog['An unexpected error occurred.']} (database is locked)`);
      });
    });
  });
});
