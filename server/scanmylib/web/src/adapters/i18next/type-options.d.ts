import type englishCatalog from '../../../locales/en.json';

// The keys of t() are those of the English catalog: a key it lacks, or a key typed as any string, fails to compile.
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: { translation: typeof englishCatalog };
  }
}
