export type UiLanguage = 'en' | 'fr';
export type ByteUnit = 'B' | 'KB' | 'MB' | 'GB';

export interface ByteSize {
  readonly amount: number;
  readonly unit: ByteUnit;
}

export interface NumberFormatting {
  readonly formatNumber: (value: number) => string;
  readonly formatDecimal: (value: number) => string;
}

const DEFAULT_LOCALES: Readonly<Record<UiLanguage, string>> = { en: 'en-US', fr: 'fr-FR' };
const BYTE_UNITS: readonly ByteUnit[] = ['B', 'KB', 'MB', 'GB'];
const BYTES_PER_UNIT = 1024;

export function formattingLocale(languageTag: string, language: UiLanguage): string {
  if (!languageTag.includes('-')) return DEFAULT_LOCALES[language];
  try {
    return Intl.getCanonicalLocales(languageTag)[0] ?? DEFAULT_LOCALES[language];
  } catch {
    return DEFAULT_LOCALES[language];
  }
}

export function createNumberFormatting(locale: string): NumberFormatting {
  const integers = new Intl.NumberFormat(locale);
  const decimals = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });
  return {
    formatNumber: (value) => integers.format(value),
    formatDecimal: (value) => decimals.format(value),
  };
}

export function byteSize(sizeBytes: number): ByteSize {
  let amount = sizeBytes;
  let unitIndex = 0;
  while (amount >= BYTES_PER_UNIT && unitIndex < BYTE_UNITS.length - 1) {
    amount /= BYTES_PER_UNIT;
    unitIndex += 1;
  }
  return { amount, unit: BYTE_UNITS[unitIndex] ?? 'B' };
}

export function wholePercent(ratio: number): number {
  return Math.round(ratio * 100);
}

export type RelativeTimeUnit = 'second' | 'minute' | 'hour' | 'day';

export type ElapsedTime =
  | { readonly kind: 'just-now' }
  | { readonly kind: 'relative'; readonly amount: number; readonly unit: RelativeTimeUnit }
  | { readonly kind: 'absolute' };

export interface DateFormatting {
  readonly formatDateTime: (date: Date) => string;
  readonly formatRelativeTime: (amount: number, unit: RelativeTimeUnit) => string;
}

const MILLISECONDS_PER_SECOND = 1000;
const JUST_NOW_SECONDS = 45;
const RELATIVE_TIME_UNITS: readonly (readonly [unit: RelativeTimeUnit, countInNextUnit: number])[] = [
  ['second', 60],
  ['minute', 60],
  ['hour', 24],
  ['day', 7],
];

export function elapsedTime(dateMilliseconds: number, nowMilliseconds: number): ElapsedTime {
  let amount = (dateMilliseconds - nowMilliseconds) / MILLISECONDS_PER_SECOND;
  if (Math.abs(amount) < JUST_NOW_SECONDS) return { kind: 'just-now' };
  for (const [unit, countInNextUnit] of RELATIVE_TIME_UNITS) {
    if (Math.abs(amount) < countInNextUnit) return { kind: 'relative', amount: Math.round(amount), unit };
    amount /= countInNextUnit;
  }
  return { kind: 'absolute' };
}

export function createDateFormatting(locale: string): DateFormatting {
  const dateTimes = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' });
  const relativeTimes = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  return {
    formatDateTime: (date) => dateTimes.format(date),
    formatRelativeTime: (amount, unit) => relativeTimes.format(amount, unit),
  };
}
