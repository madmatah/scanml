import type { TFunction } from 'i18next';

import type { SettledUploads, UploadItem, UploadProblem, UploadSummary } from '../../../application/upload-queue.ts';
import type { NumberFormatting } from '../../../domain/formatting.ts';
import { formatBytes, formatPercent } from '../../i18next/formatted-text.ts';
import { errorMessage } from '../shell/error-message.ts';

function sentPhotosText(t: TFunction, count: number): string {
  return t('{{count, number}} photo sent', {
    count,
    defaultValue_one: '{{count, number}} photo sent',
    defaultValue_other: '{{count, number}} photos sent',
  });
}

function failuresText(t: TFunction, count: number): string {
  return t('{{count, number}} failure', {
    count,
    defaultValue_one: '{{count, number}} failure',
    defaultValue_other: '{{count, number}} failures',
  });
}

export function uploadProblemText(t: TFunction, problem: UploadProblem): string {
  switch (problem.kind) {
    case 'unsupported-format':
      return t('Unsupported format (JPEG, PNG or WebP only).');
    case 'too-large':
      return t('File too large (40 MiB maximum).');
    case 'empty':
      return t('Empty file.');
    case 'upload-failed':
      return errorMessage(t, problem.failure, t('Upload refused by the server.'));
  }
}

export function uploadHeadline(t: TFunction, formatting: NumberFormatting, summary: UploadSummary): string {
  if (summary.isBusy) {
    return t('Uploading: {{sent}} / {{total}} ({{percent}})', {
      sent: summary.sentCount,
      total: t('{{count, number}} photo', {
        count: summary.acceptedCount,
        defaultValue_one: '{{count, number}} photo',
        defaultValue_other: '{{count, number}} photos',
      }),
      percent: formatPercent(t, formatting, summary.progress),
    });
  }
  const sent = sentPhotosText(t, summary.sentCount);
  if (summary.failures.length === 0) return t('Upload finished: {{sent}}', { sent });
  return t('Upload finished: {{sent}}, {{failures}}', { sent, failures: failuresText(t, summary.failures.length) });
}

export function uploadProgressText(t: TFunction, formatting: NumberFormatting, upload: UploadItem): string {
  return t('{{percent}} of {{size}}', {
    percent: formatPercent(t, formatting, upload.progress),
    size: formatBytes(t, formatting, upload.size),
  });
}

export function waitingPhotosText(t: TFunction, count: number): string {
  return t('{{count, number}} photo waiting to be uploaded', {
    count,
    defaultValue_one: '{{count, number}} photo waiting to be uploaded',
    defaultValue_other: '{{count, number}} photos waiting to be uploaded',
  });
}

export function settledUploadsText(t: TFunction, settled: SettledUploads): string {
  const sent = sentPhotosText(t, settled.sentCount);
  const failureCount = settled.failedCount + settled.rejectedCount;
  if (failureCount === 0) return t('{{sent}}: the PC will read their text.', { sent });
  return t('{{sent}}, {{failures}}: see the document’s upload list.', {
    sent,
    failures: failuresText(t, failureCount),
  });
}
