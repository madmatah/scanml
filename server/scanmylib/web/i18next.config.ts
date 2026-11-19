import { defineConfig } from 'i18next-cli';

export default defineConfig({
  locales: ['en', 'fr'],
  extract: {
    input: ['src/**/*.{ts,tsx}'],
    // The tests and their support sit beside the modules, and hold no text of the UI.
    ignore: ['src/**/*.test.ts', 'src/**/*.test-support.ts'],
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
