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
