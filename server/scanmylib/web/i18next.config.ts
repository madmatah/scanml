import { defineConfig } from 'i18next-cli';

export default defineConfig({
  locales: ['en', 'fr'],
  extract: {
    input: ['src/**/*.{ts,tsx}'],
    output: 'locales/{{language}}.json',
    // The English text is the key, and holds dots and colons.
    keySeparator: false,
    nsSeparator: false,
    defaultNS: false,
  },
  lint: {
    checkTranslationPlaceholders: 'error',
  },
});
