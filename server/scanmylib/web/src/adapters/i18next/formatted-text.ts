import type { TFunction } from 'i18next';

import { byteSize, type NumberFormatting, wholePercent } from '../../domain/formatting.ts';

const NO_VALUE = '—';

export function formatBytes(t: TFunction, formatting: NumberFormatting, sizeBytes: number): string {
  const { amount, unit } = byteSize(sizeBytes);
  switch (unit) {
    case 'B':
      return t('{{size}} B', { size: formatting.formatNumber(amount) });
    case 'KB':
      return t('{{size}} KB', { size: formatting.formatDecimal(amount) });
    case 'MB':
      return t('{{size}} MB', { size: formatting.formatDecimal(amount) });
    case 'GB':
      return t('{{size}} GB', { size: formatting.formatDecimal(amount) });
  }
}

export function formatSeconds(t: TFunction, formatting: NumberFormatting, seconds: number | null): string {
  return seconds === null ? NO_VALUE : t('{{seconds}} s', { seconds: formatting.formatDecimal(seconds) });
}

export function formatPercent(t: TFunction, formatting: NumberFormatting, ratio: number): string {
  return t('{{percent}}%', { percent: formatting.formatNumber(wholePercent(ratio)) });
}

export function quoted(t: TFunction, text: string): string {
  return t('“{{text}}”', { text });
}
