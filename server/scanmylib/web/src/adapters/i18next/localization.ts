import { createInstance, type i18n, type Resource } from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import {
  createDateFormatting,
  createNumberFormatting,
  type DateFormatting,
  formattingLocale,
  type NumberFormatting,
  type UiLanguage,
} from '../../domain/formatting.ts';

export interface Localization {
  readonly i18next: i18n;
  readonly language: UiLanguage;
  readonly locale: string;
  readonly formatting: NumberFormatting;
  readonly dates: DateFormatting;
}

export async function createLocalization(catalogs: Resource): Promise<Localization> {
  const instance = createInstance();
  await instance.use(LanguageDetector).init({
    resources: catalogs,
    supportedLngs: ['en', 'fr'],
    nonExplicitSupportedLngs: true,
    fallbackLng: 'en',
    detection: { order: ['navigator'], caches: [] },
    keySeparator: false,
    nsSeparator: false,
    // React escapes what it renders, and a value escaped here too would show its entities.
    interpolation: { escapeValue: false },
  });
  const language: UiLanguage = instance.resolvedLanguage === 'fr' ? 'fr' : 'en';
  const locale = formattingLocale(instance.language, language);
  const formatting = createNumberFormatting(locale);
  // i18next's own number format would take the bare language, losing the region the browser gives.
  instance.services.formatter?.add('number', (value) =>
    typeof value === 'number' ? formatting.formatNumber(value) : String(value),
  );
  return { i18next: instance, language, locale, formatting, dates: createDateFormatting(locale) };
}
