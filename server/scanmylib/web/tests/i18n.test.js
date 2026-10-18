/**
 * Unit tests of the translation of the UI (static/js/lib/i18n.js and the
 * French catalog static/js/locales/fr.js), with Node's built-in test runner
 * (see math.test.js for the command).
 *
 * The sources are scanned for the messages given to t(), tc(), tn() and
 * tNodes(), and for the static text of index.html: the French catalog must
 * translate each of them, and nothing else. French is written only in that
 * catalog, so these tests compare with its entries instead of quoting it.
 */
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { describe, test } from 'node:test';

import { formatBytes, formatNumber, formatPercent, formatSeconds, quoted } from '../static/js/lib/format.js';
import { currentLanguage, currentLocale, negotiate, setLocale, t, tc, tn, tNodes } from '../static/js/lib/i18n.js';
import FRENCH from '../static/js/locales/fr.js';

const WEB = new URL('../', import.meta.url);
const JS = new URL('static/js/', WEB);
const CATALOG_FILE = new URL('locales/fr.js', JS);
const HELPER_FILE = new URL('lib/i18n.js', JS);

/** The translation functions and the number of literal messages each one takes first. */
const FUNCTIONS = { t: 1, tc: 2, tn: 2, tNodes: 1 };

const NBSP = '\u00a0';

// --- a small JavaScript lexer, enough for this code base ---------------------

const ESCAPES = { n: '\n', t: '\t', r: '\r', b: '\b', f: '\f', v: '\v', 0: '\0' };

/** Value of the escape sequence at `source[index]` (after the backslash), and its length. */
function unescape(source, index) {
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
            const [text, length] = unescape(source, index + 1);
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
            const [text, length] = unescape(source, index + 1);
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

function sourceFiles(directory = JS) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const url = new URL(entry.name + (entry.isDirectory() ? '/' : ''), directory);
    if (entry.isDirectory()) return url.href === new URL('locales/', JS).href ? [] : sourceFiles(url);
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
    if (attribute('data-i18n')) messages.push({ key: key(text.trim()), plural: false, where: 'index.html' });
    for (const name of attribute('data-i18n-attr')?.[1]?.split(/\s+/) ?? []) {
      messages.push({ key: key(attribute(name)[1]), plural: false, where: `index.html [${name}]` });
    }
  }
  return messages;
}

/** Every message of the UI: { key (catalog key), plural, english: [forms], values (keys given), where }. */
function usedMessages() {
  const messages = htmlMessages().map((message) => ({
    ...message,
    english: [message.key.split('|').at(-1)],
    values: [],
  }));
  const dynamic = [];
  for (const file of sourceFiles()) {
    for (const call of translationCalls(readFileSync(file, 'utf8'))) {
      const where = `${relative(file)}:${call.line}`;
      if (call.dynamic) dynamic.push(`${where}: ${call.name}() needs literal messages`);
      else if (call.name === 'tn') {
        messages.push({ key: call.args[0], plural: true, english: call.args, values: call.values, where });
      } else if (call.name === 'tc') {
        const [context, message] = call.args;
        messages.push({ key: `${context}|${message}`, plural: false, english: [message], values: call.values, where });
      } else {
        messages.push({ key: call.args[0], plural: false, english: [call.args[0]], values: call.values, where });
      }
    }
  }
  return { messages, dynamic };
}

const placeholders = (text) => [...new Set([...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]))].sort();

describe('the French catalog', () => {
  const { messages, dynamic } = usedMessages();

  test('the scan finds the messages of every screen', () => {
    // Guards the scan itself: a few messages from different files and functions.
    const keys = new Set(messages.map((message) => message.key));
    for (const key of [
      'Skip to content',
      'header|Sign out',
      'Library',
      'page status|Done',
      '{count} page',
      'Drag a page to move it: if it is selected, the whole selection follows it. Click: select, Shift+click: ' +
        'range, Ctrl+click: add or remove. Esc cancels a move.',
      'Markdown files and illustrations are stored in {folder}',
      'Unnumbered page',
    ]) {
      assert.ok(keys.has(key), key);
    }
    assert.ok(messages.length > 300, `${messages.length} messages`);
  });

  test('messages are literals', () => {
    assert.deepEqual(dynamic, []);
  });

  test('translates every message of the UI', () => {
    const missing = messages.filter(({ key }) => !Object.hasOwn(FRENCH, key));
    assert.deepEqual(
      missing.map(({ key, where }) => `${where}: ${key}`),
      [],
    );
  });

  test('has no entry that the UI does not use', () => {
    const used = new Set(messages.map(({ key }) => key));
    assert.deepEqual(
      Object.keys(FRENCH).filter((key) => !used.has(key)),
      [],
    );
  });

  test('has plural forms exactly for the messages given to tn()', () => {
    const wrong = messages.filter(({ key, plural }) => {
      const entry = FRENCH[key];
      if (entry === undefined) return false;
      if (!plural) return typeof entry !== 'string';
      return (
        typeof entry?.one !== 'string' ||
        typeof entry?.other !== 'string' ||
        Object.keys(entry).some((category) => !['zero', 'one', 'two', 'few', 'many', 'other'].includes(category))
      );
    });
    assert.deepEqual(
      wrong.map(({ key, where }) => `${where}: ${key}`),
      [],
    );
  });

  test('keeps the placeholders of the English messages', () => {
    const wrong = [];
    for (const { key, english, where } of messages) {
      const entry = FRENCH[key];
      if (entry === undefined) continue;
      const expected = placeholders(english.join(' '));
      for (const form of typeof entry === 'string' ? [entry] : Object.values(entry)) {
        if (placeholders(form).join() !== expected.join()) wrong.push(`${where}: ${form}`);
      }
    }
    assert.deepEqual(wrong, []);
  });

  test('every placeholder gets a value where the message is used, and only those', () => {
    const wrong = [];
    for (const { english, plural, values, where } of messages) {
      if (values === null) continue; // values passed as a variable
      const own = (names) => names.filter((name) => !(plural && name === 'count')); // tn() fills {count}
      const expected = own(placeholders(english.join(' ')));
      const given = own([...new Set(values)].sort());
      if (expected.join() !== given.join()) wrong.push(`${where}: {${expected}} needs values, given {${given}}`);
    }
    assert.deepEqual(wrong, []);
  });

  test('has each key once', () => {
    const source = readFileSync(CATALOG_FILE, 'utf8');
    const keys = [...source.matchAll(/^ {2}'((?:[^'\\]|\\.)*)':/gm)].map((match) => match[1]);
    assert.equal(keys.length, Object.keys(FRENCH).length);
  });

  test('contexts never appear in plain messages', () => {
    const plain = messages.filter(({ key, english }) => key === english[0] && key.includes('|'));
    assert.deepEqual(
      plain.map(({ where }) => where),
      [],
    );
  });
});

describe('French stays in the French catalog', () => {
  // Letters and signs of French that English text does not use (written as escapes, not to match this file).
  const FRENCH_CHARACTERS = new RegExp(
    '[\u00e0\u00e2\u00e6\u00e7\u00e8-\u00eb\u00ee\u00ef\u00f4\u00f9\u00fb' + '\u00fc\u00ff\u0153\u00ab\u00bb]',
    'i',
  );

  function webFiles(directory = WEB) {
    return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
      const url = new URL(entry.name + (entry.isDirectory() ? '/' : ''), directory);
      if (entry.isDirectory()) return entry.name === 'vendor' || entry.name === 'icons' ? [] : webFiles(url);
      return /\.(js|html|css|webmanifest)$/.test(entry.name) && url.href !== CATALOG_FILE.href ? [url] : [];
    });
  }

  test('no French letters elsewhere', () => {
    const found = [];
    for (const file of webFiles()) {
      readFileSync(file, 'utf8')
        .split('\n')
        .forEach((line, index) => {
          if (FRENCH_CHARACTERS.test(line)) found.push(`${relative(file)}:${index + 1}: ${line.trim()}`);
        });
    }
    assert.deepEqual(found, []);
  });

  test('no French translation written as a string of the code', () => {
    const translations = new Set(
      Object.entries(FRENCH).flatMap(([key, entry]) =>
        (typeof entry === 'string' ? [entry] : Object.values(entry)).filter((form) => form !== key.split('|').at(-1)),
      ),
    );
    const found = [];
    for (const file of sourceFiles()) {
      for (const token of lex(readFileSync(file, 'utf8'))) {
        if (token.type === 'string' && translations.has(token.value)) {
          found.push(`${relative(file)}:${token.line}: ${token.value}`);
        }
      }
    }
    assert.deepEqual(found, []);
  });
});

describe('the language', () => {
  test('is the first French or English one the browser prefers', () => {
    assert.deepEqual(negotiate(['fr-FR', 'fr', 'en-US']), { language: 'fr', locale: 'fr-FR' });
    assert.deepEqual(negotiate(['fr']), { language: 'fr', locale: 'fr-FR' });
    assert.deepEqual(negotiate(['fr-CA']), { language: 'fr', locale: 'fr-CA' });
    assert.deepEqual(negotiate(['FR-be']), { language: 'fr', locale: 'fr-BE' });
    assert.deepEqual(negotiate(['de-DE', 'fr-CH']), { language: 'fr', locale: 'fr-CH' });
    assert.deepEqual(negotiate(['en-GB', 'fr-FR']), { language: 'en', locale: 'en-GB' });
    assert.deepEqual(negotiate(['en']), { language: 'en', locale: 'en-US' });
  });

  test('is English otherwise', () => {
    assert.deepEqual(negotiate(['de-DE', 'es']), { language: 'en', locale: 'en-US' });
    assert.deepEqual(negotiate([]), { language: 'en', locale: 'en-US' });
    assert.deepEqual(negotiate(undefined), { language: 'en', locale: 'en-US' });
    assert.deepEqual(negotiate(['fr-!!']), { language: 'fr', locale: 'fr-FR' }); // malformed tag
  });

  test('can be switched', () => {
    setLocale(['fr-FR']);
    assert.equal(currentLanguage(), 'fr');
    assert.equal(currentLocale(), 'fr-FR');
    assert.equal(t('Library'), FRENCH.Library);
    setLocale(['en-US']);
    assert.equal(currentLanguage(), 'en');
    assert.equal(t('Library'), 'Library');
  });
});

describe('messages', () => {
  test('English is the message itself, with its placeholders filled', () => {
    setLocale(['en-US']);
    assert.equal(t('Library'), 'Library');
    assert.equal(t('Delete {title}?', { title: '“Example Book”' }), 'Delete “Example Book”?');
    assert.equal(t('{a} and {b}', { a: 1, b: 0 }), '1 and 0');
    assert.equal(t('{a} and {b}', { a: 'x' }), 'x and {b}'); // a missing value leaves the placeholder
    assert.equal(t('{a}', { a: '{b}', b: 'no' }), '{b}'); // values are not interpolated again
    assert.equal(tc('page status', 'Done'), 'Done');
  });

  test('French comes from the catalog, with a context when the English is ambiguous', () => {
    setLocale(['fr-FR']);
    assert.equal(t('Delete {title}?', { title: 'X' }), FRENCH['Delete {title}?'].replace('{title}', 'X'));
    assert.equal(tc('page status', 'Done'), FRENCH['page status|Done']);
    assert.equal(t('Done'), FRENCH.Done);
    assert.notEqual(FRENCH['page status|Done'], FRENCH.Done);
    assert.equal(t('A message without translation'), 'A message without translation');
    setLocale(['en-US']);
  });

  test('plurals follow the rules of the language', () => {
    setLocale(['en-US']);
    const pages = (count) => tn('{count} page', '{count} pages', count);
    assert.deepEqual([0, 1, 2, 1234].map(pages), ['0 pages', '1 page', '2 pages', '1,234 pages']);
    assert.equal(tn('{count} page', '{count} pages', 2, { count: 'two' }), 'two pages');

    setLocale(['fr-FR']);
    const { one, other } = FRENCH['{count} page'];
    const french = (template, count) => template.replace('{count}', count);
    assert.equal(pages(0), french(one, '0')); // French uses the singular below 2
    assert.equal(pages(1), french(one, '1'));
    assert.equal(pages(2), french(other, '2'));
    assert.equal(pages(1234), french(other, new Intl.NumberFormat('fr-FR').format(1234)));
    assert.equal(pages(1_000_000), french(other, new Intl.NumberFormat('fr-FR').format(1_000_000))); // "many"
    setLocale(['en-US']);
  });

  test('nodes are kept as they are, text around them is merged', () => {
    setLocale(['en-US']);
    const node = { nodeType: 1 };
    assert.deepEqual(tNodes('{fraction} pages between {min} and {max}', { fraction: node, min: 1, max: 9 }), [
      node,
      ' pages between 1 and 9',
    ]);
    assert.deepEqual(tNodes('In {folder}', { folder: node }), ['In ', node]);
    assert.deepEqual(tNodes('Plain text'), ['Plain text']);
  });
});

describe('formats', () => {
  test('English', () => {
    setLocale(['en-US']);
    assert.equal(formatNumber(1234), '1,234');
    assert.equal(formatPercent(0.473), '47%');
    assert.equal(formatSeconds(2.345), '2.3 s');
    assert.equal(formatBytes(512), '512 B');
    assert.equal(formatBytes(3.2 * 1024 * 1024), '3.2 MB');
    assert.equal(quoted('Example Book'), '“Example Book”');
  });

  test('French: numbers by Intl, units and quotation marks by the catalog, as before', () => {
    setLocale(['fr-FR']);
    const decimal = (value) => new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 }).format(value);
    assert.equal(formatNumber(1234), new Intl.NumberFormat('fr-FR').format(1234));
    assert.equal(formatPercent(0.473), `47${NBSP}%`);
    assert.equal(formatSeconds(2.345), `${decimal(2.3)}${NBSP}s`);
    assert.equal(formatBytes(3.2 * 1024 * 1024), FRENCH['{size} MB'].replace('{size}', decimal(3.2)));
    assert.equal(quoted('Example Book'), FRENCH['“{text}”'].replace('{text}', 'Example Book'));
    setLocale(['en-US']);
  });
});
