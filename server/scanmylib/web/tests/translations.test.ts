// French is written only in the French catalogs, so this file writes its letters as escapes and reads its translations
// from the catalog.
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { before, describe, it } from 'node:test';

import englishCatalog from '../locales/en.json' with { type: 'json' };
import frenchCatalog from '../locales/fr.json' with { type: 'json' };

interface Line {
  readonly where: string;
  readonly text: string;
}

const WEB = new URL('../', import.meta.url);
const FRENCH_CATALOG_FILES = new Set(['locales/fr.json']);
const SOURCE_DIRECTORIES = ['src/'];
const UNREAD_DIRECTORIES = new Set(['node_modules', 'icons']);
const TEXT_FILE = /\.(ts|tsx|js|json|html|css|webmanifest)$/;
const SOURCE_FILE = /\.(ts|tsx|js)$/;
// Letters and signs of French that English text does not use.
const FRENCH_CHARACTERS = new RegExp(
  '[\u00e0\u00e2\u00e6\u00e7\u00e8-\u00eb\u00ee\u00ef\u00f4\u00f9\u00fb' + '\u00fc\u00ff\u0153\u00ab\u00bb]',
  'i',
);
const PLACEHOLDER = /\{\{[^}]*\}\}/g;
const COMPONENT_TAG = /<\/?([A-Za-z0-9]+)\s*\/?>/g;
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;
const SEPARATOR = '_';
const ESCAPE_SEQUENCE = /\\u\{([0-9a-fA-F]+)\}|\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})/g;

function listFiles(directory: URL, pattern: RegExp): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (entry.isDirectory()) {
      return UNREAD_DIRECTORIES.has(entry.name) ? [] : listFiles(new URL(`${entry.name}/`, directory), pattern);
    }
    const path = new URL(entry.name, directory).href.slice(WEB.href.length);
    return pattern.test(entry.name) && !FRENCH_CATALOG_FILES.has(path) ? [path] : [];
  });
}

function readLines(path: string): Line[] {
  return readFileSync(new URL(path, WEB), 'utf8')
    .split('\n')
    .map((text, index) => ({ where: `${path}:${index + 1}`, text }));
}

function readUnescaped(path: string): string {
  return readFileSync(new URL(path, WEB), 'utf8').replace(ESCAPE_SEQUENCE, (_sequence, braced, fourDigits, twoDigits) =>
    String.fromCodePoint(Number.parseInt(braced ?? fourDigits ?? twoDigits, 16)),
  );
}

function listMarks(text: string): string {
  const placeholders = [...text.matchAll(PLACEHOLDER)].map((match) => match[0]);
  const tags = [...text.matchAll(COMPONENT_TAG)].map((match) => `<${match[1]}>`);
  return [...new Set([...placeholders, ...tags])].sort().join(' ');
}

function listEnglishMarks(frenchKey: string): string {
  const baseKey = frenchKey.replace(PLURAL_SUFFIX, '');
  const englishForms = Object.entries(englishCatalog)
    .filter(([key]) => key.replace(PLURAL_SUFFIX, '') === baseKey)
    .map(([, form]) => form);
  return listMarks(englishForms.join(' '));
}

function writeDelimited(text: string): string[] {
  return [`'${text}'`, `"${text}"`, `\`${text}\``, `>${text}<`];
}

describe('The translation catalogs', () => {
  describe('The English catalog', () => {
    it('should not be empty, so that an extraction that found nothing fails on every key as unused', () => {
      assert.notEqual(Object.keys(englishCatalog).length, 0);
    });

    it('should hold no text with the separator of contexts and plurals, so that each one in a key is a suffix', () => {
      const texts = Object.values(englishCatalog);
      assert.notEqual(texts.length, 0);
      assert.deepEqual(
        texts.filter((text) => text.includes(SEPARATOR)),
        [],
      );
    });
  });

  describe('The French catalog', () => {
    let webLines: Line[];
    let sources: { readonly path: string; readonly text: string }[];
    before(() => {
      webLines = listFiles(WEB, TEXT_FILE).flatMap(readLines);
      sources = SOURCE_DIRECTORIES.flatMap((directory) => listFiles(new URL(directory, WEB), SOURCE_FILE)).map(
        (path) => ({ path, text: readUnescaped(path) }),
      );
    });

    it('should not be empty, so that an extraction that found nothing fails on every key as unused', () => {
      assert.notEqual(Object.keys(frenchCatalog).length, 0);
    });

    it('should keep the placeholders, with their formats, and the component tags of the English text', () => {
      const entries = Object.entries(frenchCatalog);
      assert.notEqual(entries.length, 0);
      assert.deepEqual(
        entries.filter(([key, form]) => listMarks(form) !== listEnglishMarks(key)).map(([key]) => key),
        [],
      );
    });

    it('should hold the only French letters of the web UI', () => {
      assert.notEqual(webLines.length, 0);
      assert.deepEqual(
        webLines
          .filter(({ text }) => FRENCH_CHARACTERS.test(text))
          .map(({ where, text }) => `${where}: ${text.trim()}`),
        [],
      );
    });

    it('should hold the only French translations of the web UI, which no source writes as a text', () => {
      const englishTexts = new Set(Object.values(englishCatalog));
      const translations = Object.values(frenchCatalog).filter((form) => form !== '' && !englishTexts.has(form));
      assert.notEqual(sources.length, 0);
      assert.deepEqual(
        sources.flatMap(({ path, text }) =>
          translations
            .filter((translation) => writeDelimited(translation).some((written) => text.includes(written)))
            .map((translation) => `${path}: ${translation}`),
        ),
        [],
      );
    });
  });
});
