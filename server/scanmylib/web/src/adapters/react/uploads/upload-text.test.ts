import assert from 'node:assert/strict';
import { before, beforeEach, describe, it } from 'node:test';

import type { TFunction } from 'i18next';
import frenchCatalog from '../../../../locales/fr.json' with { type: 'json' };
import { ApiError, NetworkError } from '../../../application/api-errors.ts';
import type { FailedUpload, SettledUploads, UploadProblem, UploadSummary } from '../../../application/upload-queue.ts';
import type { NumberFormatting } from '../../../domain/formatting.ts';
import { CATALOGS } from '../../i18next/catalogs.ts';
import { createLocalizationFor } from '../../i18next/localization.test-support.ts';
import {
  settledUploadsText,
  uploadHeadline,
  uploadProblemText,
  uploadProgressText,
  waitingPhotosText,
} from './upload-text.ts';

interface Text {
  readonly t: TFunction;
  readonly formatting: NumberFormatting;
}

const ENGLISH_LANGUAGES = ['en-US'];
const FRENCH_LANGUAGES = ['fr-FR'];
const UNPROCESSABLE = 422;
const UNSUPPORTED_MEDIA_TYPE = 415;

async function textFor(languages: readonly string[]): Promise<Text> {
  const { i18next, formatting } = await createLocalizationFor(languages, CATALOGS);
  return { t: i18next.t, formatting };
}

function summary(overrides: Partial<UploadSummary>): UploadSummary {
  return {
    sentCount: 0,
    acceptedCount: 0,
    waitingCount: 0,
    uploading: [],
    failed: [],
    failures: [],
    isBusy: false,
    progress: 1,
    ...overrides,
  };
}

function failures(count: number): FailedUpload[] {
  return [...Array(count).keys()].map(
    (index): FailedUpload => ({
      pageId: `page-${index}`,
      documentId: 'document',
      name: `IMG_${index}.jpg`,
      size: 1000,
      state: 'failed',
      progress: 0,
      problem: { kind: 'upload-failed', failure: new NetworkError() },
    }),
  );
}

describe('The upload text', () => {
  let english: Text;
  before(async () => {
    english = await textFor(ENGLISH_LANGUAGES);
  });

  describe('The uploadProblemText() function', () => {
    const situations: { situation: string; problem: UploadProblem; rule: string; expected: string }[] = [
      {
        situation: 'When the format is not one the server reads',
        problem: { kind: 'unsupported-format' },
        rule: 'should name the formats it reads',
        expected: 'Unsupported format (JPEG, PNG or WebP only).',
      },
      {
        situation: 'When the photo is too large',
        problem: { kind: 'too-large' },
        rule: 'should give the largest size',
        expected: 'File too large (40 MiB maximum).',
      },
      {
        situation: 'When the photo is empty',
        problem: { kind: 'empty' },
        rule: 'should say so',
        expected: 'Empty file.',
      },
      {
        situation: 'When the server refused the photo with a detail',
        problem: { kind: 'upload-failed', failure: new ApiError(UNPROCESSABLE, 'page_id: not a UUID') },
        rule: 'should say that the server refused it, with its detail',
        expected: 'Upload refused by the server. (page_id: not a UUID)',
      },
      {
        situation: 'When the server refused the photo for its format',
        problem: { kind: 'upload-failed', failure: new ApiError(UNSUPPORTED_MEDIA_TYPE, '') },
        rule: 'should name the formats it reads, as the server’s status tells',
        expected: 'Unsupported format (JPEG, PNG or WebP only).',
      },
    ];

    for (const { situation, problem, rule, expected } of situations) {
      describe(situation, () => {
        let text: string;
        beforeEach(() => {
          text = uploadProblemText(english.t, problem);
        });

        it(rule, () => {
          assert.equal(text, expected);
        });
      });
    }
  });

  describe('The uploadHeadline() function', () => {
    const situations: { situation: string; uploads: UploadSummary; rule: string; expected: string }[] = [
      {
        situation: 'When photos are being sent',
        uploads: summary({ sentCount: 1, acceptedCount: 3, isBusy: true, progress: 0.456 }),
        rule: 'should count the photos sent out of those accepted, with the share of their bytes sent',
        expected: 'Uploading: 1 / 3 photos (46%)',
      },
      {
        situation: 'When one photo is being sent',
        uploads: summary({ sentCount: 0, acceptedCount: 1, isBusy: true, progress: 0 }),
        rule: 'should write the photo in the singular',
        expected: 'Uploading: 0 / 1 photo (0%)',
      },
      {
        situation: 'When every photo is sent',
        uploads: summary({ sentCount: 1, acceptedCount: 1 }),
        rule: 'should count the photos sent',
        expected: 'Upload finished: 1 photo sent',
      },
      {
        situation: 'When the uploads ended with failures',
        uploads: summary({ sentCount: 2, acceptedCount: 4, failures: failures(2) }),
        rule: 'should count the photos sent and the failures',
        expected: 'Upload finished: 2 photos sent, 2 failures',
      },
    ];

    for (const { situation, uploads, rule, expected } of situations) {
      describe(situation, () => {
        let headline: string;
        beforeEach(() => {
          headline = uploadHeadline(english.t, english.formatting, uploads);
        });

        it(rule, () => {
          assert.equal(headline, expected);
        });
      });
    }
  });

  describe('The uploadProgressText() function', () => {
    describe('When a photo is half sent', () => {
      let text: string;
      beforeEach(() => {
        text = uploadProgressText(english.t, english.formatting, {
          pageId: 'page',
          documentId: 'document',
          name: 'IMG_0001.jpg',
          size: 3 * 1024 * 1024,
          state: 'uploading',
          progress: 0.5,
          problem: null,
        });
      });

      it('should give the share sent of its size', () => {
        assert.equal(text, '50% of 3 MB');
      });
    });
  });

  describe('The waitingPhotosText() function', () => {
    describe('When photos wait for their turn', () => {
      let text: string;
      beforeEach(() => {
        text = waitingPhotosText(english.t, 2);
      });

      it('should count them', () => {
        assert.equal(text, '2 photos waiting to be uploaded');
      });
    });
  });

  describe('The settledUploadsText() function', () => {
    const situations: { situation: string; settled: SettledUploads; rule: string; expected: string }[] = [
      {
        situation: 'When every photo was sent',
        settled: { sentCount: 3, failedCount: 0, rejectedCount: 0 },
        rule: 'should say that the PC will read them',
        expected: '3 photos sent: the PC will read their text.',
      },
      {
        situation: 'When photos failed or were refused',
        settled: { sentCount: 1, failedCount: 1, rejectedCount: 1 },
        rule: 'should count the failures and the refusals together, and point at the upload list',
        expected: '1 photo sent, 2 failures: see the document’s upload list.',
      },
    ];

    for (const { situation, settled, rule, expected } of situations) {
      describe(situation, () => {
        let text: string;
        beforeEach(() => {
          text = settledUploadsText(english.t, settled);
        });

        it(rule, () => {
          assert.equal(text, expected);
        });
      });
    }

    describe('When the photos are counted in French', () => {
      let text: string;
      beforeEach(async () => {
        const french = await textFor(FRENCH_LANGUAGES);
        text = settledUploadsText(french.t, { sentCount: 1000, failedCount: 0, rejectedCount: 0 });
      });

      it('should format the count in the French way, in the plural', () => {
        const sent = frenchCatalog['{{count, number}} photo sent_other'].replace('{{count, number}}', '1\u202f000');
        assert.equal(text, frenchCatalog['{{sent}}: the PC will read their text.'].replace('{{sent}}', sent));
      });
    });
  });
});
