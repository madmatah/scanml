import type { TFunction } from 'i18next';

import type { EngineStatusState } from '../../../application/engine-status.ts';
import type { NumberFormatting } from '../../../domain/formatting.ts';
import { countPendingPages, type GraphicsCard } from '../../../domain/server-status.ts';
import { quoted } from '../../i18next/formatted-text.ts';

export type Tone = 'neutral' | 'ok' | 'info' | 'warn' | 'danger';

export interface DisplayedEngineState {
  readonly label: string;
  readonly tone: Tone;
  readonly description: string;
}

export interface EngineDetail {
  readonly term: string;
  readonly description: string;
  readonly isPath: boolean;
}

export interface EngineBanner {
  readonly title: string;
  readonly message: string;
}

const MEBIBYTES_PER_GIBIBYTE = 1024;

function displayedEngineState(t: TFunction, engineState: string | null): DisplayedEngineState {
  switch (engineState) {
    case 'idle':
      return {
        label: t('OCR idle'),
        tone: 'neutral',
        description: t('Engine stopped, graphics memory freed. It restarts on its own with the next page.'),
      };
    case 'starting':
      return { label: t('OCR starting'), tone: 'warn', description: t('Loading the model on the graphics card…') };
    case 'ready':
      return { label: t('OCR ready'), tone: 'ok', description: t('Engine loaded, ready to process pages.') };
    case 'stopping':
      return { label: t('OCR stopping'), tone: 'warn', description: t('Freeing graphics memory…') };
    case 'error':
      return { label: t('OCR error'), tone: 'danger', description: t('The engine could not start.') };
    case 'unreachable':
      return {
        label: t('OCR unreachable'),
        tone: 'danger',
        description: t('The OCR container is not responding.'),
      };
    default:
      return { label: t('OCR: {{state}}', { state: engineState ?? t('unknown') }), tone: 'neutral', description: '' };
  }
}

export function engineStateOf(t: TFunction, { connection, status }: EngineStatusState): DisplayedEngineState {
  if (connection === 'offline') {
    return {
      label: t('Server unreachable'),
      tone: 'danger',
      description: t('The ScanMyLib server is not responding.'),
    };
  }
  if (status === null) return { label: t('OCR…'), tone: 'neutral', description: '' };
  return displayedEngineState(t, status.engine.isReachable ? status.engine.state : 'unreachable');
}

export function pendingPagesText(
  t: TFunction,
  formatting: NumberFormatting,
  { connection, status }: EngineStatusState,
): string | null {
  if (connection === 'offline' || status === null) return null;
  const pendingPages = countPendingPages(status.queue);
  return pendingPages === 0 ? null : t('{{pages}} in queue', { pages: formatting.formatNumber(pendingPages) });
}

function graphicsMemoryText(t: TFunction, formatting: NumberFormatting, card: GraphicsCard | null): string | null {
  const used = card?.memoryUsedMebibytes ?? null;
  const total = card?.memoryTotalMebibytes ?? null;
  if (used === null || total === null || total === 0) return null;
  return t('{{used}} / {{total}} GB used', {
    used: formatting.formatDecimal(used / MEBIBYTES_PER_GIBIBYTE),
    total: formatting.formatDecimal(total / MEBIBYTES_PER_GIBIBYTE),
  });
}

export function engineDetails(
  t: TFunction,
  formatting: NumberFormatting,
  { connection, status }: EngineStatusState,
  stateLabel: string,
): EngineDetail[] {
  const details: { term: string; description: string | null; isPath?: boolean }[] = [
    { term: t('State'), description: stateLabel },
  ];
  if (status !== null && connection !== 'offline') {
    const { engine, queue } = status;
    details.push(
      {
        term: t('Queue'),
        description: t('{{queued}} waiting, {{processing}} in progress', {
          queued: formatting.formatNumber(queue.queuedCount),
          processing: formatting.formatNumber(queue.processingCount),
        }),
      },
      { term: t('Pages processed'), description: formatting.formatNumber(queue.doneCount) },
      {
        term: t('Failed'),
        description:
          queue.errorCount > 0
            ? t('{{count, number}} page', {
                count: queue.errorCount,
                defaultValue_one: '{{count, number}} page',
                defaultValue_other: '{{count, number}} pages',
              })
            : null,
      },
      { term: t('Backend'), description: engine.backend },
      { term: t('Graphics card'), description: engine.graphicsCard?.name ?? null },
      { term: t('Graphics memory'), description: graphicsMemoryText(t, formatting, engine.graphicsCard) },
      { term: t('Last error'), description: engine.lastError },
      { term: t('Library'), description: status.libraryDirectory, isPath: true },
      { term: t('Version'), description: status.version },
    );
  }
  return details.flatMap(({ term, description, isPath = false }) =>
    description === null || description === '' ? [] : [{ term, description, isPath }],
  );
}

export function engineBanner(t: TFunction, { connection, status }: EngineStatusState): EngineBanner | null {
  if (connection === 'offline') {
    return {
      title: t('The ScanMyLib server is not responding.'),
      message: t('Retrying every 3 seconds. Check that the PC is on and that the {{service}} service is running.', {
        service: quoted(t, 'api'),
      }),
    };
  }
  if (status === null) return null;
  const { engine } = status;
  if (!engine.isReachable || engine.state === 'unreachable') {
    return {
      title: t('Text recognition isn’t available.'),
      message: t(
        'Received pages wait on the PC: their text will be read as soon as the {{container}} container responds again.',
        { container: quoted(t, 'ocr') },
      ),
    };
  }
  if (engine.state === 'error') {
    return {
      title: t('Text recognition is failing.'),
      message:
        engine.lastError === null || engine.lastError === ''
          ? t('Check the logs of the {{container}} container. The pages stay in the queue.', {
              container: quoted(t, 'ocr'),
            })
          : engine.lastError,
    };
  }
  return null;
}
