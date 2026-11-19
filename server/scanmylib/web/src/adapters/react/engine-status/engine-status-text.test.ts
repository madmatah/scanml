import assert from 'node:assert/strict';
import { before, beforeEach, describe, it } from 'node:test';

import type { TFunction } from 'i18next';
import frenchCatalog from '../../../../locales/fr.json' with { type: 'json' };
import type { EngineStatusState } from '../../../application/engine-status.ts';
import type { NumberFormatting } from '../../../domain/formatting.ts';
import { sampleServerStatus } from '../../../domain/server-status.test-support.ts';
import { CATALOGS } from '../../i18next/catalogs.ts';
import { createLocalizationFor } from '../../i18next/localization.test-support.ts';
import {
  type DisplayedEngineState,
  type EngineBanner,
  type EngineDetail,
  engineBanner,
  engineDetails,
  engineStateOf,
  pendingPagesText,
} from './engine-status-text.ts';

const ENGLISH_LANGUAGES = ['en-US'];
const FRENCH_LANGUAGES = ['fr-FR'];
const ONLINE: EngineStatusState = { connection: 'online', status: sampleServerStatus() };
const STATE_LABEL = 'OCR ready';

interface Text {
  readonly t: TFunction;
  readonly formatting: NumberFormatting;
}

async function textFor(languages: readonly string[]): Promise<Text> {
  const { i18next, formatting } = await createLocalizationFor(languages, CATALOGS);
  return { t: i18next.t, formatting };
}

describe('The engine status text', () => {
  let english: Text;
  before(async () => {
    english = await textFor(ENGLISH_LANGUAGES);
  });

  describe('The engineStateOf() function', () => {
    const situations: { situation: string; state: EngineStatusState; rule: string; expected: DisplayedEngineState }[] =
      [
        {
          situation: 'When the server cannot be reached',
          state: { connection: 'offline', status: ONLINE.status },
          rule: 'should say so, in the danger tone, whatever the engine last reported',
          expected: {
            label: 'Server unreachable',
            tone: 'danger',
            description: 'The ScanMyLib server is not responding.',
          },
        },
        {
          situation: 'When no status has come yet',
          state: { connection: 'unknown', status: null },
          rule: 'should wait, in the neutral tone',
          expected: { label: 'OCR…', tone: 'neutral', description: '' },
        },
        {
          situation: 'When the engine is idle',
          state: { connection: 'online', status: sampleServerStatus({ engine: { state: 'idle' } }) },
          rule: 'should say that it restarts with the next page',
          expected: {
            label: 'OCR idle',
            tone: 'neutral',
            description: 'Engine stopped, graphics memory freed. It restarts on its own with the next page.',
          },
        },
        {
          situation: 'When the engine is starting',
          state: { connection: 'online', status: sampleServerStatus({ engine: { state: 'starting' } }) },
          rule: 'should say that it loads the model, in the warning tone',
          expected: { label: 'OCR starting', tone: 'warn', description: 'Loading the model on the graphics card…' },
        },
        {
          situation: 'When the engine is ready',
          state: ONLINE,
          rule: 'should say that it is ready, in the ok tone',
          expected: { label: 'OCR ready', tone: 'ok', description: 'Engine loaded, ready to process pages.' },
        },
        {
          situation: 'When the engine is stopping',
          state: { connection: 'online', status: sampleServerStatus({ engine: { state: 'stopping' } }) },
          rule: 'should say that it frees the memory, in the warning tone',
          expected: { label: 'OCR stopping', tone: 'warn', description: 'Freeing graphics memory…' },
        },
        {
          situation: 'When the engine failed',
          state: { connection: 'online', status: sampleServerStatus({ engine: { state: 'error' } }) },
          rule: 'should say that it could not start, in the danger tone',
          expected: { label: 'OCR error', tone: 'danger', description: 'The engine could not start.' },
        },
        {
          situation: 'When the sandbox does not answer, whatever state it reported last',
          state: {
            connection: 'online',
            status: sampleServerStatus({ engine: { isReachable: false, state: 'ready' } }),
          },
          rule: 'should say that the OCR is unreachable, in the danger tone',
          expected: { label: 'OCR unreachable', tone: 'danger', description: 'The OCR container is not responding.' },
        },
        {
          situation: 'When the engine reports a state the UI does not know',
          state: { connection: 'online', status: sampleServerStatus({ engine: { state: 'warming' } }) },
          rule: 'should name the state as given, in the neutral tone',
          expected: { label: 'OCR: warming', tone: 'neutral', description: '' },
        },
        {
          situation: 'When the engine reports no state',
          state: { connection: 'online', status: sampleServerStatus({ engine: { state: null } }) },
          rule: 'should say that the state is unknown',
          expected: { label: 'OCR: unknown', tone: 'neutral', description: '' },
        },
      ];

    for (const { situation, state, rule, expected } of situations) {
      describe(situation, () => {
        let displayed: DisplayedEngineState;
        beforeEach(() => {
          displayed = engineStateOf(english.t, state);
        });

        it(rule, () => {
          assert.deepEqual(displayed, expected);
        });
      });
    }
  });

  describe('The pendingPagesText() function', () => {
    const situations: { situation: string; state: EngineStatusState; rule: string; expectedText: string | null }[] = [
      {
        situation: 'When pages wait or are being read',
        state: {
          connection: 'online',
          status: sampleServerStatus({ queue: { queuedCount: 1200, processingCount: 1 } }),
        },
        rule: 'should count them both, formatted',
        expectedText: '1,201 in queue',
      },
      {
        situation: 'When no page waits',
        state: { connection: 'online', status: sampleServerStatus({ queue: { queuedCount: 0, processingCount: 0 } }) },
        rule: 'should say nothing',
        expectedText: null,
      },
      {
        situation: 'When the server cannot be reached',
        state: { connection: 'offline', status: ONLINE.status },
        rule: 'should say nothing, since the count may be stale',
        expectedText: null,
      },
      {
        situation: 'When no status has come yet',
        state: { connection: 'unknown', status: null },
        rule: 'should say nothing',
        expectedText: null,
      },
    ];

    for (const { situation, state, rule, expectedText } of situations) {
      describe(situation, () => {
        let text: string | null;
        beforeEach(() => {
          text = pendingPagesText(english.t, english.formatting, state);
        });

        it(rule, () => {
          assert.equal(text, expectedText);
        });
      });
    }
  });

  describe('The engineDetails() function', () => {
    describe('When the server reports its whole status', () => {
      let details: EngineDetail[];
      beforeEach(() => {
        const status = sampleServerStatus({ queue: { queuedCount: 1200, errorCount: 2 } });
        details = engineDetails(english.t, english.formatting, { connection: 'online', status }, STATE_LABEL);
      });

      it('should list each detail, in order, the library as a path', () => {
        assert.deepEqual(details, [
          { term: 'State', description: STATE_LABEL, isPath: false },
          { term: 'Queue', description: '1,200 waiting, 1 in progress', isPath: false },
          { term: 'Pages processed', description: '1,200', isPath: false },
          { term: 'Failed', description: '2 pages', isPath: false },
          { term: 'Backend', description: 'vllm', isPath: false },
          { term: 'Graphics card', description: 'Example GPU', isPath: false },
          { term: 'Graphics memory', description: '4.5 / 8 GB used', isPath: false },
          { term: 'Library', description: '/home/user/Documents/ScanMyLib', isPath: true },
          { term: 'Version', description: '0.2.3', isPath: false },
        ]);
      });
    });

    describe('When a single page failed', () => {
      let failed: string | undefined;
      beforeEach(() => {
        const status = sampleServerStatus({ queue: { errorCount: 1 } });
        failed = engineDetails(english.t, english.formatting, { connection: 'online', status }, STATE_LABEL).find(
          (detail) => detail.term === 'Failed',
        )?.description;
      });

      it('should count it in the singular', () => {
        assert.equal(failed, '1 page');
      });
    });

    describe('When the engine reports no graphics card, backend or error, and no page failed', () => {
      let terms: string[];
      beforeEach(() => {
        const status = sampleServerStatus({ engine: { backend: '', graphicsCard: null, lastError: null } });
        terms = engineDetails(english.t, english.formatting, { connection: 'online', status }, STATE_LABEL).map(
          (detail) => detail.term,
        );
      });

      it('should leave out the details it lacks', () => {
        assert.deepEqual(terms, ['State', 'Queue', 'Pages processed', 'Library', 'Version']);
      });
    });

    describe('When the graphics card reports no total memory', () => {
      let terms: string[];
      beforeEach(() => {
        const graphicsCard = { name: 'Example GPU', memoryUsedMebibytes: 512, memoryTotalMebibytes: 0 };
        const status = sampleServerStatus({ engine: { graphicsCard } });
        terms = engineDetails(english.t, english.formatting, { connection: 'online', status }, STATE_LABEL).map(
          (detail) => detail.term,
        );
      });

      it('should leave out its memory', () => {
        assert.equal(terms.includes('Graphics memory'), false);
      });
    });

    describe('When the server cannot be reached', () => {
      let details: EngineDetail[];
      beforeEach(() => {
        details = engineDetails(
          english.t,
          english.formatting,
          { connection: 'offline', status: ONLINE.status },
          STATE_LABEL,
        );
      });

      it('should give the state alone, since the rest may be stale', () => {
        assert.deepEqual(details, [{ term: 'State', description: STATE_LABEL, isPath: false }]);
      });
    });

    describe('When the counts are written in French', () => {
      let details: EngineDetail[];
      beforeEach(async () => {
        const french = await textFor(FRENCH_LANGUAGES);
        const status = sampleServerStatus({ queue: { errorCount: 1000 } });
        details = engineDetails(french.t, french.formatting, { connection: 'online', status }, STATE_LABEL);
      });

      it('should format the count of failed pages in the French way, in the plural', () => {
        const pages = frenchCatalog['{{count, number}} page_other'].replace('{{count, number}}', '1\u202f000');
        assert.equal(details.find((detail) => detail.term === frenchCatalog.Failed)?.description, pages);
      });
    });
  });

  describe('The engineBanner() function', () => {
    const situations: { situation: string; state: EngineStatusState; rule: string; expected: EngineBanner | null }[] = [
      {
        situation: 'When the server cannot be reached',
        state: { connection: 'offline', status: ONLINE.status },
        rule: 'should say that it retries, and which service to check',
        expected: {
          title: 'The ScanMyLib server is not responding.',
          message: 'Retrying every 3 seconds. Check that the PC is on and that the “api” service is running.',
        },
      },
      {
        situation: 'When the sandbox does not answer',
        state: { connection: 'online', status: sampleServerStatus({ engine: { isReachable: false } }) },
        rule: 'should say that the pages wait for the OCR container',
        expected: {
          title: 'Text recognition isn’t available.',
          message:
            'Received pages wait on the PC: their text will be read as soon as the “ocr” container responds again.',
        },
      },
      {
        situation: 'When the engine reports itself unreachable',
        state: { connection: 'online', status: sampleServerStatus({ engine: { state: 'unreachable' } }) },
        rule: 'should say that the pages wait for the OCR container',
        expected: {
          title: 'Text recognition isn’t available.',
          message:
            'Received pages wait on the PC: their text will be read as soon as the “ocr” container responds again.',
        },
      },
      {
        situation: 'When the engine failed with an error',
        state: {
          connection: 'online',
          status: sampleServerStatus({ engine: { state: 'error', lastError: 'out of memory' } }),
        },
        rule: 'should give the error of the engine',
        expected: { title: 'Text recognition is failing.', message: 'out of memory' },
      },
      {
        situation: 'When the engine failed without an error',
        state: { connection: 'online', status: sampleServerStatus({ engine: { state: 'error', lastError: null } }) },
        rule: 'should point to the logs of the OCR container',
        expected: {
          title: 'Text recognition is failing.',
          message: 'Check the logs of the “ocr” container. The pages stay in the queue.',
        },
      },
      {
        situation: 'When the engine works',
        state: ONLINE,
        rule: 'should show no banner',
        expected: null,
      },
      {
        situation: 'When no status has come yet',
        state: { connection: 'unknown', status: null },
        rule: 'should show no banner',
        expected: null,
      },
    ];

    for (const { situation, state, rule, expected } of situations) {
      describe(situation, () => {
        let banner: EngineBanner | null;
        beforeEach(() => {
          banner = engineBanner(english.t, state);
        });

        it(rule, () => {
          assert.deepEqual(banner, expected);
        });
      });
    }
  });
});
