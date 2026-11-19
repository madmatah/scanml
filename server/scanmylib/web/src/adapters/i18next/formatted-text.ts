import type { TFunction } from 'i18next';

import {
  byteSize,
  type DateFormatting,
  elapsedTime,
  type NumberFormatting,
  wholePercent,
} from '../../domain/formatting.ts';

const NO_VALUE = '—';

export const formatBytes = (t: TFunction, formatting: NumberFormatting, sizeBytes: number): string => {
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
};

export const formatSeconds = (t: TFunction, formatting: NumberFormatting, seconds: number | null): string => {
  return seconds === null ? NO_VALUE : t('{{seconds}} s', { seconds: formatting.formatDecimal(seconds) });
};

export const formatPercent = (t: TFunction, formatting: NumberFormatting, ratio: number): string => {
  return t('{{percent}}%', { percent: formatting.formatNumber(wholePercent(ratio)) });
};

export const quoted = (t: TFunction, text: string): string => {
  return t('“{{text}}”', { text });
};

export const formatRelativeTime = (
  t: TFunction,
  dates: DateFormatting,
  isoDate: string,
  nowMilliseconds: number,
): string => {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return NO_VALUE;
  const elapsed = elapsedTime(date.getTime(), nowMilliseconds);
  switch (elapsed.kind) {
    case 'just-now':
      return t('just now');
    case 'relative':
      return dates.formatRelativeTime(elapsed.amount, elapsed.unit);
    case 'absolute':
      return dates.formatDateTime(date);
  }
};

export const formatDateTime = (dates: DateFormatting, isoDate: string): string => {
  const date = new Date(isoDate);
  return Number.isNaN(date.getTime()) ? NO_VALUE : dates.formatDateTime(date);
};
