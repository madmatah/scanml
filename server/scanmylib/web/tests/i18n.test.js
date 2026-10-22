// French is written only in the French catalog, so these tests compare with its entries instead of quoting it.
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { before, beforeEach, describe, it } from 'node:test';

import { currentLanguage, currentLocale, negotiate, setLocale, t, tc, tNodes, tn } from '../static/js/lib/i18n.js';
import FRENCH from '../static/js/locales/fr.js';

const WEB = new URL('../', import.meta.url);
const JS = new URL('static/js/', WEB);
const CATALOG_FILE = new URL('locales/fr.js', JS);
const HELPER_FILE = new URL('lib/i18n.js', JS);

const ENGLISH_PREFERENCES = ['en-US'];
const FRENCH_PREFERENCES = ['fr-FR'];

/** The translation functions and the number of literal messages each one takes first. */
const FUNCTIONS = { t: 1, tc: 2, tn: 2, tNodes: 1 };

// --- a small JavaScript lexer, enough for this code base ---------------------

const ESCAPES = { n: '\n', t: '\t', r: '\r', b: '\b', f: '\f', v: '\v', 0: '\0' };

/** Value of the escape sequence at `source[index]` (after the backslash), and its length. */
function readEscape(source, index) {
  const char = source[index];
  if (char === 'u' && source[index + 1] === '{') {
    const end = source.indexOf('}', index);
    return [String.fromCodePoint(Number.parseInt(source.slice(index + 2, end), 16)), end - index + 1];
  }
  if (char === 'u') return [String.fromCharCode(Number.parseInt(source.slice(index + 1, index + 5), 16)), 5];
  if (char === 'x') return [String.fromCharCode(Number.parseInt(source.slice(index + 1, index + 3), 16)), 3];
  if (char === '\n') return ['', 1];
  return [ESCAPES[char] ?? char, 1];
}

/** Tokens that may come right before a regular expression literal (else "/" divides). */
const BEFORE_REGEX = new Set([
  '',
  '(',
  ',',
  '=',
  ':',
  '[',
  '!',
  '&',
  '|',
  '?',
  '{',
  '}',
  ';',
  '+',
  '-',
  '*',
  '%',
  '<',
  '>',
  '~',
  '^',
  'return',
  'typeof',
  'case',
  'do',
  'else',
  'in',
  'of',
  'new',
  'delete',
  'void',
  'throw',
]);

/**
 * Tokens of `source`: { type: 'string', value, line } for string literals and
 * templates without substitution, { type: 'template', line } for the others
 * (whose substitutions are lexed too), { type: 'name', value } and
 * { type: 'punct', value }. Comments are dropped.
 */
function lex(source) {
  const tokens = [];
  let index = 0;
  let line = 1;
  const advance = (count) => {
    for (let k = 0; k < count; k += 1) if (source[index + k] === '\n') line += 1;
    index += count;
  };
  const previous = () => {
    const token = tokens.at(-1);
    return !token ? '' : token.type === 'name' || token.type === 'punct' ? token.value : 'literal';
  };

  function lexCode(untilBrace) {
    let depth = 0;
    while (index < source.length) {
      const char = source[index];
      if (untilBrace && char === '}' && depth === 0) {
        advance(1);
        return;
      }
      if (/\s/.test(char)) {
        advance(1);
      } else if (source.startsWith('//', index)) {
        const end = source.indexOf('\n', index);
        advance((end < 0 ? source.length : end) - index);
      } else if (source.startsWith('/*', index)) {
        const end = source.indexOf('*/', index + 2);
        advance((end < 0 ? source.length : end + 2) - index);
      } else if (char === "'" || char === '"') {
        const start = line;
        let value = '';
        advance(1);
        while (index < source.length && source[index] !== char) {
          if (source[index] === '\\') {
            const [text, length] = readEscape(source, index + 1);
            value += text;
            advance(length + 1);
          } else {
            value += source[index];
            advance(1);
          }
        }
        advance(1);
        tokens.push({ type: 'string', value, line: start });
      } else if (char === '`') {
        const start = line;
        let value = '';
        let substitutions = false;
        advance(1);
        while (index < source.length && source[index] !== '`') {
          if (source[index] === '\\') {
            const [text, length] = readEscape(source, index + 1);
            value += text;
            advance(length + 1);
          } else if (source.startsWith('${', index)) {
            substitutions = true;
            advance(2);
            lexCode(true);
          } else {
            value += source[index];
            advance(1);
          }
        }
        advance(1);
        tokens.push(substitutions ? { type: 'template', line: start } : { type: 'string', value, line: start });
      } else if (char === '/' && BEFORE_REGEX.has(previous())) {
        let inClass = false;
        advance(1);
        while (index < source.length && (inClass || source[index] !== '/')) {
          if (source[index] === '\\') advance(1);
          else if (source[index] === '[') inClass = true;
          else if (source[index] === ']') inClass = false;
          advance(1);
        }
        advance(1);
        while (/[a-z]/i.test(source[index] ?? '')) advance(1);
        tokens.push({ type: 'regex' });
      } else if (/[\w$]/.test(char)) {
        const match = /^[\w$]+/.exec(source.slice(index, index + 100));
        tokens.push({ type: 'name', value: match[0] });
        advance(match[0].length);
      } else {
        if (char === '{') depth += 1;
        if (char === '}') depth -= 1;
        tokens.push({ type: 'punct', value: char });
        advance(1);
      }
    }
  }

  lexCode(false);
  return tokens;
}

const isPunct = (token, chars) => token?.type === 'punct' && chars.includes(token.value);

/** Keys of the object literal whose "{" is tokens[start]; null when it spreads another object. */
function objectKeys(tokens, start) {
  const keys = [];
  let depth = 0;
  for (let index = start; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (isPunct(token, '{([')) {
      depth += 1;
    } else if (isPunct(token, '})]')) {
      depth -= 1;
      if (depth === 0) return keys;
    } else if (depth === 1 && isPunct(tokens[index - 1], '{,')) {
      if (isPunct(token, '.')) return null;
      if (['name', 'string'].includes(token.type) && isPunct(tokens[index + 1], ':,}')) keys.push(token.value);
    }
  }
  return null;
}

/**
 * Keys of the values given to a call whose literal arguments end at tokens[position]: [] without
 * values, null when they are not an object literal. tn() takes the count first.
 */
function valueKeys(tokens, position, name) {
  let cursor = position;
  if (name === 'tn' && isPunct(tokens[cursor], ',')) {
    cursor += 1;
    for (let depth = 0; cursor < tokens.length; cursor += 1) {
      if (isPunct(tokens[cursor], '({[')) depth += 1;
      else if (isPunct(tokens[cursor], ')}]') && depth-- === 0) break;
      else if (depth === 0 && isPunct(tokens[cursor], ',')) break;
    }
  }
  if (!isPunct(tokens[cursor], ',')) return [];
  return isPunct(tokens[cursor + 1], '{') ? objectKeys(tokens, cursor + 1) : null;
}

/**
 * Calls of the translation functions in `source`: { name, args, values, line }, args being the
 * leading literal arguments (adjacent literals joined by "+") and values the keys of the values
 * given (see valueKeys), or { name, dynamic: true, line } when an argument is not a literal.
 */
function translationCalls(source) {
  const tokens = lex(source);
  const calls = [];
  tokens.forEach((token, index) => {
    if (token.type !== 'name' || !Object.hasOwn(FUNCTIONS, token.value)) return;
    const before = tokens[index - 1];
    const spread = before?.value === '.' && tokens[index - 2]?.value === '.' && tokens[index - 3]?.value === '.';
    const member = before?.value === '.' && !spread; // something.t(…) is another function
    if (tokens[index + 1]?.value !== '(' || member || before?.value === 'function') return;
    let position = index + 2;
    const args = [];
    let line = null;
    for (let arg = 0; arg < FUNCTIONS[token.value]; arg += 1) {
      if (arg > 0) {
        if (tokens[position]?.value !== ',') break;
        position += 1;
      }
      let value = null;
      while (tokens[position]?.type === 'string') {
        line ??= tokens[position].line;
        value = (value ?? '') + tokens[position].value;
        position += 1;
        if (tokens[position]?.value !== '+' || tokens[position + 1]?.type !== 'string') break;
        position += 1;
      }
      const next = tokens[position]?.value;
      if (value === null || (next !== ',' && next !== ')')) break;
      args.push(value);
    }
    if (args.length === FUNCTIONS[token.value]) {
      calls.push({ name: token.value, args, values: valueKeys(tokens, position, token.value), line });
    } else calls.push({ name: token.value, dynamic: true, line: line ?? tokens[index + 2]?.line });
  });
  return calls;
}

function listSourceFiles(directory = JS) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const url = new URL(entry.name + (entry.isDirectory() ? '/' : ''), directory);
    if (entry.isDirectory()) return url.href === new URL('locales/', JS).href ? [] : listSourceFiles(url);
    return entry.name.endsWith('.js') && url.href !== HELPER_FILE.href ? [url] : [];
  });
}

const relative = (url) => url.href.slice(WEB.href.length);

/** Messages of the static text of index.html: elements marked data-i18n, attributes listed in data-i18n-attr. */
function htmlMessages() {
  const html = readFileSync(new URL('index.html', WEB), 'utf8');
  const messages = [];
  for (const [, attributes, text] of html.matchAll(/<[a-z][a-z0-9]*\b([^>]*)>([^<]*)/gi)) {
    const attribute = (name) => new RegExp(`\\s${name}(?:="([^"]*)")?(?=\\s|/?$)`).exec(attributes);
    const context = attribute('data-i18n-context')?.[1];
    const key = (message) => (context ? `${context}|${message}` : message);
    if (attribute('data-i18n')) messages.push({ key: key(text.trim()), isPlural: false, where: 'index.html' });
    for (const name of attribute('data-i18n-attr')?.[1]?.split(/\s+/) ?? []) {
      messages.push({ key: key(attribute(name)[1]), isPlural: false, where: `index.html [${name}]` });
    }
  }
  return messages;
}

function scanUsedMessages() {
  const messages = htmlMessages().map((message) => ({
    ...message,
    english: [message.key.split('|').at(-1)],
    values: [],
  }));
  const dynamic = [];
  let callCount = 0;
  for (const file of listSourceFiles()) {
    for (const call of translationCalls(readFileSync(file, 'utf8'))) {
      callCount += 1;
      const where = `${relative(file)}:${call.line}`;
      if (call.dynamic) dynamic.push(`${where}: ${call.name}() needs literal messages`);
      else if (call.name === 'tn') {
        messages.push({ key: call.args[0], isPlural: true, english: call.args, values: call.values, where });
      } else if (call.name === 'tc') {
        const [context, message] = call.args;
        messages.push({
          key: `${context}|${message}`,
          isPlural: false,
          english: [message],
          values: call.values,
          where,
        });
      } else {
        messages.push({ key: call.args[0], isPlural: false, english: [call.args[0]], values: call.values, where });
      }
    }
  }
  return { messages, dynamic, callCount };
}

const placeholders = (text) => [...new Set([...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]))].sort();

function listWebFiles(directory = WEB) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const url = new URL(entry.name + (entry.isDirectory() ? '/' : ''), directory);
    if (entry.isDirectory()) return entry.name === 'vendor' || entry.name === 'icons' ? [] : listWebFiles(url);
    return /\.(js|html|css|webmanifest)$/.test(entry.name) && url.href !== CATALOG_FILE.href ? [url] : [];
  });
}

const PLURAL_CATEGORIES = ['zero', 'one', 'two', 'few', 'many', 'other'];

function listForms(entry) {
  return typeof entry === 'string' ? [entry] : Object.values(entry);
}

function isPluralEntry(entry) {
  return (
    typeof entry?.one === 'string' &&
    typeof entry?.other === 'string' &&
    Object.keys(entry).every((category) => PLURAL_CATEGORIES.includes(category))
  );
}

function hasFormsOfItsCall(entry, isPlural) {
  return isPlural ? isPluralEntry(entry) : typeof entry === 'string';
}

function listTranslatedForms(messages) {
  return messages
    .filter(({ key }) => Object.hasOwn(FRENCH, key))
    .flatMap(({ key, english, where }) => listForms(FRENCH[key]).map((form) => ({ form, english, where })));
}

// tn() fills {count} itself.
function dropTheCountOfTn(names, isPlural) {
  return names.filter((name) => !(isPlural && name === 'count'));
}

function pairPlaceholdersWithValues({ english, isPlural, values, where }) {
  return {
    where,
    placeholderNames: dropTheCountOfTn(placeholders(english.join(' ')), isPlural).join(),
    valueNames: dropTheCountOfTn([...new Set(values)].sort(), isPlural).join(),
  };
}

function fillTemplate(template, placeholderValues) {
  return Object.entries(placeholderValues).reduce(
    (text, [placeholderName, placeholderValue]) => text.replaceAll(`{${placeholderName}}`, () => placeholderValue),
    template,
  );
}

describe('The translation', () => {
  let messages;
  let dynamicCalls;
  let callCount;
  before(() => {
    ({ messages, dynamic: dynamicCalls, callCount } = scanUsedMessages());
  });

  describe('When the UI gives messages to the translation functions', () => {
    const sampleKeys = [
      'Skip to content',
      'header|Sign out',
      'Library',
      'page status|Failed',
      '{count} page',
      'Drag a page to move it: if it is selected, the whole selection follows it. Click: select, Shift+click: ' +
        'range, Ctrl+click: add or remove. Esc cancels a move.',
      'Markdown files and illustrations are stored in {folder}',
      'Unnumbered page',
    ];
    const messageCountToExceed = 300;

    it('should be found by the scan of the sources, in the HTML and the code, whatever the function', () => {
      const foundKeys = new Set(messages.map(({ key }) => key));
      assert.deepEqual(
        sampleKeys.filter((key) => !foundKeys.has(key)),
        [],
      );
    });

    it('should be found by the scan by the hundreds', () => {
      assert.ok(messages.length > messageCountToExceed, `${messages.length} messages`);
    });

    it('should give literal messages, so that the French catalog can be checked against them', () => {
      assert.notEqual(callCount, 0);
      assert.deepEqual(dynamicCalls, []);
    });

    it('should give a value to every placeholder of a message, and to no other', () => {
      // The values given as a variable are out of the scan's reach.
      const valuesInPlace = messages.filter(({ values }) => values !== null).map(pairPlaceholdersWithValues);
      assert.notEqual(valuesInPlace.length, 0);
      assert.deepEqual(
        valuesInPlace.filter(({ placeholderNames, valueNames }) => placeholderNames !== valueNames),
        [],
      );
    });

    it('should never put a context in a plain message, where it would read as the context of a key', () => {
      const plainMessages = messages.filter(({ key, english }) => key === english[0]);
      assert.notEqual(plainMessages.length, 0);
      assert.deepEqual(
        plainMessages.filter(({ key }) => key.includes('|')).map(({ where }) => where),
        [],
      );
    });
  });

  describe('The French catalog', () => {
    // Letters and signs of French that English text does not use (written as escapes, not to match this file).
    const frenchCharacters = new RegExp(
      '[\u00e0\u00e2\u00e6\u00e7\u00e8-\u00eb\u00ee\u00ef\u00f4\u00f9\u00fb' + '\u00fc\u00ff\u0153\u00ab\u00bb]',
      'i',
    );
    let catalogSourceKeys;
    let webLines;
    let codeStrings;
    before(() => {
      catalogSourceKeys = [...readFileSync(CATALOG_FILE, 'utf8').matchAll(/^ {2}'((?:[^'\\]|\\.)*)':/gm)].map(
        (match) => match[1],
      );
      webLines = listWebFiles().flatMap((file) =>
        readFileSync(file, 'utf8')
          .split('\n')
          .map((line, index) => ({ where: `${relative(file)}:${index + 1}`, line })),
      );
      codeStrings = listSourceFiles().flatMap((file) =>
        lex(readFileSync(file, 'utf8'))
          .filter((token) => token.type === 'string')
          .map((token) => ({ where: `${relative(file)}:${token.line}`, text: token.value })),
      );
    });

    it('should translate every message of the UI', () => {
      assert.notEqual(messages.length, 0);
      assert.deepEqual(
        messages.filter(({ key }) => !Object.hasOwn(FRENCH, key)).map(({ key, where }) => `${where}: ${key}`),
        [],
      );
    });

    it('should have no entry that the UI does not use', () => {
      const usedKeys = new Set(messages.map(({ key }) => key));
      const entryKeys = Object.keys(FRENCH);
      assert.notEqual(entryKeys.length, 0);
      assert.deepEqual(
        entryKeys.filter((key) => !usedKeys.has(key)),
        [],
      );
    });

    it('should have plural forms exactly for the messages given to tn()', () => {
      const translatedMessages = messages.filter(({ key }) => Object.hasOwn(FRENCH, key));
      assert.notEqual(translatedMessages.length, 0);
      assert.deepEqual(
        translatedMessages
          .filter(({ key, isPlural }) => !hasFormsOfItsCall(FRENCH[key], isPlural))
          .map(({ key, where }) => `${where}: ${key}`),
        [],
      );
    });

    it('should keep the placeholders of the English messages', () => {
      const forms = listTranslatedForms(messages);
      assert.notEqual(forms.length, 0);
      assert.deepEqual(
        forms
          .filter(({ form, english }) => placeholders(form).join() !== placeholders(english.join(' ')).join())
          .map(({ form, where }) => `${where}: ${form}`),
        [],
      );
    });

    it('should hold each key once', () => {
      assert.deepEqual(
        catalogSourceKeys.filter((key, index) => catalogSourceKeys.indexOf(key) !== index),
        [],
      );
      assert.equal(catalogSourceKeys.length, Object.keys(FRENCH).length);
    });

    it('should hold the only French letters of the web UI', () => {
      assert.notEqual(webLines.length, 0);
      assert.deepEqual(
        webLines.filter(({ line }) => frenchCharacters.test(line)).map(({ where, line }) => `${where}: ${line.trim()}`),
        [],
      );
    });

    it('should hold the only French translations of the web UI, which no code writes as a string', () => {
      const translations = new Set(
        Object.entries(FRENCH).flatMap(([key, entry]) =>
          listForms(entry).filter((form) => form !== key.split('|').at(-1)),
        ),
      );
      assert.notEqual(codeStrings.length, 0);
      assert.deepEqual(
        codeStrings.filter(({ text }) => translations.has(text)).map(({ where, text }) => `${where}: ${text}`),
        [],
      );
    });
  });

  describe('The negotiate() function', () => {
    const negotiations = [
      {
        situation: 'When the browser prefers French in France first',
        preferences: ['fr-FR', 'fr', 'en-US'],
        rule: 'should choose French, in that locale',
        expectedChoice: { language: 'fr', locale: 'fr-FR' },
      },
      {
        situation: 'When the browser prefers French without a region',
        preferences: ['fr'],
        rule: 'should choose French, in the locale of France',
        expectedChoice: { language: 'fr', locale: 'fr-FR' },
      },
      {
        situation: 'When the browser prefers French in another region',
        preferences: ['fr-CA'],
        rule: 'should choose French, in the region of the browser',
        expectedChoice: { language: 'fr', locale: 'fr-CA' },
      },
      {
        situation: 'When the browser writes its language tag in another letter case',
        preferences: ['FR-be'],
        rule: 'should choose French, writing the locale in its canonical case',
        expectedChoice: { language: 'fr', locale: 'fr-BE' },
      },
      {
        situation: 'When the browser prefers a language that the UI does not speak, then French',
        preferences: ['de-DE', 'fr-CH'],
        rule: 'should choose French, the first language that the UI speaks',
        expectedChoice: { language: 'fr', locale: 'fr-CH' },
      },
      {
        situation: 'When the browser prefers English, then French',
        preferences: ['en-GB', 'fr-FR'],
        rule: 'should choose English, the first language that the UI speaks, in the region of the browser',
        expectedChoice: { language: 'en', locale: 'en-GB' },
      },
      {
        situation: 'When the browser prefers English without a region',
        preferences: ['en'],
        rule: 'should choose English, in the locale of the United States',
        expectedChoice: { language: 'en', locale: 'en-US' },
      },
      {
        situation: 'When the browser prefers only languages that the UI does not speak',
        preferences: ['de-DE', 'es'],
        rule: 'should choose English, in the locale of the United States',
        expectedChoice: { language: 'en', locale: 'en-US' },
      },
      {
        situation: 'When the browser prefers no language',
        preferences: [],
        rule: 'should choose English, in the locale of the United States',
        expectedChoice: { language: 'en', locale: 'en-US' },
      },
      {
        situation: 'When the browser gives no preferences',
        preferences: undefined,
        rule: 'should choose English, in the locale of the United States',
        expectedChoice: { language: 'en', locale: 'en-US' },
      },
      {
        situation: 'When the browser prefers French with a malformed tag',
        preferences: ['fr-!!'],
        rule: 'should choose French, in the locale of France',
        expectedChoice: { language: 'fr', locale: 'fr-FR' },
      },
    ];

    for (const { situation, preferences, rule, expectedChoice } of negotiations) {
      describe(situation, () => {
        let choice;
        beforeEach(() => {
          choice = negotiate(preferences);
        });

        it(rule, () => {
          assert.deepEqual(choice, expectedChoice);
        });
      });
    }
  });

  describe('The setLocale() function', () => {
    describe('When it switches to French in a region of the browser', () => {
      const canadianFrenchPreferences = ['fr-CA'];
      let language;
      let locale;
      let libraryText;
      beforeEach(() => {
        setLocale(canadianFrenchPreferences);
        language = currentLanguage();
        locale = currentLocale();
        libraryText = t('Library');
      });

      it('should make French the language of the UI', () => {
        assert.equal(language, 'fr');
      });

      it('should take the locale of the browser', () => {
        assert.equal(locale, 'fr-CA');
      });

      it('should translate the messages from the French catalog', () => {
        assert.equal(libraryText, FRENCH.Library);
      });

      describe('When it switches back to English', () => {
        let languageBack;
        let libraryTextBack;
        beforeEach(() => {
          setLocale(ENGLISH_PREFERENCES);
          languageBack = currentLanguage();
          libraryTextBack = t('Library');
        });

        it('should make English the language of the UI again', () => {
          assert.equal(languageBack, 'en');
        });

        it('should give the messages in English again', () => {
          assert.equal(libraryTextBack, 'Library');
        });
      });
    });
  });

  describe('The t() function', () => {
    describe('When the UI is in English', () => {
      beforeEach(() => {
        setLocale(ENGLISH_PREFERENCES);
      });

      describe('When the message has no placeholder', () => {
        let text;
        beforeEach(() => {
          text = t('Library');
        });

        it('should give the message itself', () => {
          assert.equal(text, 'Library');
        });
      });

      describe('When the message has a placeholder', () => {
        const values = { title: '“Example Book”' };
        let text;
        beforeEach(() => {
          text = t('Delete {title}?', values);
        });

        it('should fill the placeholder with its value', () => {
          assert.equal(text, 'Delete “Example Book”?');
        });
      });

      describe('When the values are numbers, zero among them', () => {
        const values = { first: 1, second: 0 };
        let text;
        beforeEach(() => {
          text = t('{first} and {second}', values);
        });

        it('should write every number, zero included', () => {
          assert.equal(text, '1 and 0');
        });
      });

      describe('When a placeholder has no value', () => {
        const values = { first: 'x' };
        let text;
        beforeEach(() => {
          text = t('{first} and {second}', values);
        });

        it('should leave the placeholder as written', () => {
          assert.equal(text, 'x and {second}');
        });
      });

      describe('When a value holds a placeholder', () => {
        const values = { first: '{second}', second: 'no' };
        let text;
        beforeEach(() => {
          text = t('{first}', values);
        });

        it('should leave it as written, since the values are never filled in again', () => {
          assert.equal(text, '{second}');
        });
      });
    });

    describe('When the UI is in French', () => {
      beforeEach(() => {
        setLocale(FRENCH_PREFERENCES);
      });

      describe('When the message has a placeholder', () => {
        const values = { title: 'X' };
        let text;
        beforeEach(() => {
          text = t('Delete {title}?', values);
        });

        it('should fill the placeholder of the translation from the catalog', () => {
          assert.equal(text, fillTemplate(FRENCH['Delete {title}?'], values));
        });
      });

      describe('When the catalog also translates the message in a context', () => {
        let text;
        beforeEach(() => {
          text = t('Failed');
        });

        it('should take the translation without context', () => {
          assert.equal(text, FRENCH.Failed);
        });
      });

      describe('When the catalog does not translate the message', () => {
        let text;
        beforeEach(() => {
          text = t('A message without translation');
        });

        it('should give the English message', () => {
          assert.equal(text, 'A message without translation');
        });
      });
    });
  });

  describe('The tc() function', () => {
    describe('When the UI is in English', () => {
      let text;
      beforeEach(() => {
        setLocale(ENGLISH_PREFERENCES);
        text = tc('page status', 'Failed');
      });

      it('should give the message itself, without its context', () => {
        assert.equal(text, 'Failed');
      });
    });

    describe('When the UI is in French', () => {
      let textInContext;
      let textWithoutContext;
      beforeEach(() => {
        setLocale(FRENCH_PREFERENCES);
        textInContext = tc('page status', 'Failed');
        textWithoutContext = t('Failed');
      });

      it('should take the translation of the message in its context', () => {
        assert.equal(textInContext, FRENCH['page status|Failed']);
      });

      it('should translate the message otherwise than without context, where the English is ambiguous', () => {
        assert.notEqual(textInContext, textWithoutContext);
      });
    });
  });

  describe('The tn() function', () => {
    const singular = '{count} page';
    const plural = '{count} pages';

    describe('When the UI is in English', () => {
      beforeEach(() => {
        setLocale(ENGLISH_PREFERENCES);
      });

      const counts = [
        { situation: 'When the count is 0', count: 0, rule: 'should take the plural', expectedText: '0 pages' },
        { situation: 'When the count is 1', count: 1, rule: 'should take the singular', expectedText: '1 page' },
        { situation: 'When the count is 2', count: 2, rule: 'should take the plural', expectedText: '2 pages' },
        {
          situation: 'When the count is in the thousands',
          count: 1234,
          rule: 'should write the count for the locale',
          expectedText: '1,234 pages',
        },
      ];

      for (const { situation, count, rule, expectedText } of counts) {
        describe(situation, () => {
          let text;
          beforeEach(() => {
            text = tn(singular, plural, count);
          });

          it(rule, () => {
            assert.equal(text, expectedText);
          });
        });
      }

      describe('When the values give the count', () => {
        const count = 2;
        const values = { count: 'two' };
        let text;
        beforeEach(() => {
          text = tn(singular, plural, count, values);
        });

        it('should write the count as given', () => {
          assert.equal(text, 'two pages');
        });
      });
    });

    describe('When the UI is in French', () => {
      const { one, other } = FRENCH[singular];
      const frenchNumbers = new Intl.NumberFormat('fr-FR');
      beforeEach(() => {
        setLocale(FRENCH_PREFERENCES);
      });

      const counts = [
        {
          situation: 'When the count is 0',
          count: 0,
          rule: 'should take the singular, as French does below 2',
          form: one,
        },
        { situation: 'When the count is 1', count: 1, rule: 'should take the singular', form: one },
        { situation: 'When the count is 2', count: 2, rule: 'should take the plural', form: other },
        {
          situation: 'When the count is in the thousands',
          count: 1234,
          rule: 'should take the plural, with the count written for the locale',
          form: other,
        },
        {
          situation: 'When the count is a million, of the category many that the catalog does not give',
          count: 1_000_000,
          rule: 'should take the plural',
          form: other,
        },
      ];

      for (const { situation, count, rule, form } of counts) {
        describe(situation, () => {
          let text;
          beforeEach(() => {
            text = tn(singular, plural, count);
          });

          it(rule, () => {
            assert.equal(text, fillTemplate(form, { count: frenchNumbers.format(count) }));
          });
        });
      }
    });
  });

  describe('The tNodes() function', () => {
    const node = { nodeType: 1 };

    describe('When the UI is in English', () => {
      beforeEach(() => {
        setLocale(ENGLISH_PREFERENCES);
      });

      describe('When a node comes before text values', () => {
        const values = { fraction: node, min: 1, max: 9 };
        let parts;
        beforeEach(() => {
          parts = tNodes('{fraction} pages between {min} and {max}', values);
        });

        it('should keep the node, then merge the text and the values after it into one string', () => {
          assert.deepEqual(parts, [node, ' pages between 1 and 9']);
        });
      });

      describe('When a node comes after text', () => {
        const values = { folder: node };
        let parts;
        beforeEach(() => {
          parts = tNodes('In {folder}', values);
        });

        it('should keep the text, then the node', () => {
          assert.deepEqual(parts, ['In ', node]);
        });
      });

      describe('When the message has no placeholder', () => {
        let parts;
        beforeEach(() => {
          parts = tNodes('Plain text');
        });

        it('should give the message as one string', () => {
          assert.deepEqual(parts, ['Plain text']);
        });
      });
    });
  });
});
