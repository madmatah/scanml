/**
 * Unit tests of static/js/lib/reading.js (the reading view), with Node's
 * built-in test runner (see math.test.js for the command).
 */
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { setLocale } from '../static/js/lib/i18n.js';
import {
  localizeMarkers, missingPagesText, pageAtLine, pageMarkerText, readingOutline, unnumberedHeadingText,
} from '../static/js/lib/reading.js';
import FRENCH from '../static/js/locales/fr.js';

beforeEach(() => setLocale(['en-US']));
afterEach(() => setLocale(['en-US']));

/** Parts of GET /api/documents/{id}/html, and the API's pages by key. */
const PARTS = [
  { type: 'page', key: 'k-i', marker: 'Page i' },
  { type: 'page', key: 'k-1', marker: 'Page 1' },
  { type: 'page', key: 'k-plate', marker: 'Unnumbered page' },
  { type: 'page', key: 'k-2', marker: 'Page 2' },
  { type: 'gap', text: 'Missing pages: 3–5' },
  { type: 'page', key: 'k-6', marker: 'Page 6–7' },
  { type: 'heading', text: 'Unnumbered pages' },
  { type: 'page', key: 'k-notes', marker: 'Unnumbered page' },
];
const PAGES = new Map([
  ['k-i', { id: 'i', page_label: 'i' }],
  ['k-1', { id: '1', page_label: '1' }],
  ['k-plate', { id: 'plate', page_label: null }],
  ['k-2', { id: '2', page_label: '2' }],
  ['k-6', { id: '6', page_label: '6–7', number_end: 7 }],
  ['k-notes', { id: 'notes', page_label: null }],
]);

const summary = (outline) => outline.map(({ type, index, label }) => (type === 'page' ? [index, label] : [type, label]));

describe('the "Page" list', () => {
  test('the pages in reading order, with the missing pages and the unnumbered ones', () => {
    assert.deepEqual(summary(readingOutline(PARTS, PAGES)), [
      [0, 'p. i'],
      [1, 'p. 1'],
      [2, 'No number (position 3)'],
      [3, 'p. 2'],
      ['gap', 'Missing pages: 3–5'],
      [4, 'p. 6–7'],
      ['group', 'Unnumbered pages'],
      [5, 'No number (position 6)'],
    ]);
  });

  test('each page entry knows its page', () => {
    const entries = readingOutline(PARTS, PAGES).filter((entry) => entry.type === 'page');
    assert.deepEqual(entries.map((entry) => [entry.key, entry.page.id]), [
      ['k-i', 'i'], ['k-1', '1'], ['k-plate', 'plate'], ['k-2', '2'], ['k-6', '6'], ['k-notes', 'notes'],
    ]);
  });

  test('a page missing from the document data (changed meanwhile) keeps the marker of the HTML', () => {
    const outline = readingOutline(PARTS.slice(0, 3), new Map());
    assert.deepEqual(summary(outline), [[0, 'Page i'], [1, 'Page 1'], [2, 'Unnumbered page']]);
    assert.equal(outline[0].page, null);
  });

  test('a letter without page numbers', () => {
    const parts = ['a', 'b', 'c'].map((key) => ({ type: 'page', key, marker: 'Unnumbered page' }));
    const pages = new Map(['a', 'b', 'c'].map((key) => [key, { page_label: null }]));
    assert.deepEqual(summary(readingOutline(parts, pages)).map(([, label]) => label), [
      'No number (position 1)', 'No number (position 2)', 'No number (position 3)',
    ]);
  });

  test('in French', () => {
    setLocale(['fr-FR']);
    const labels = summary(readingOutline(PARTS.slice(0, 3), PAGES)).map(([, label]) => label);
    const position3 = FRENCH['{label} (position {position})']
      .replace('{label}', FRENCH['No number']).replace('{position}', '3');
    assert.deepEqual(labels, ['p. i', 'p. 1', position3]);
  });

  test('nothing to read', () => {
    assert.deepEqual(readingOutline([], PAGES), []);
  });
});

/** Stand-in for the elements of the document HTML: what localizeMarkers uses of the DOM. */
function element(selector, { attributes = {}, text = '', children = [] } = {}) {
  const [tag, ...classes] = selector.split('.');
  return {
    tag,
    classes,
    attributes,
    textContent: text,
    children,
    matches(query) {
      const [queryTag, ...queryClasses] = query.split('.');
      return (!queryTag || queryTag === this.tag) && queryClasses.every((name) => this.classes.includes(name));
    },
    querySelector(query) {
      const child = query.replace(/^:scope > /, '');
      return this.children.find((candidate) => candidate.matches(child)) ?? null;
    },
    hasAttribute(name) {
      return Object.hasOwn(this.attributes, name);
    },
    getAttribute(name) {
      return this.attributes[name] ?? null;
    },
  };
}

/** The document HTML of the shared contract, with English markers. */
function documentContent() {
  const page = (label, text) => element('section.page', {
    attributes: { 'data-key': `k-${label}` },
    children: [element('p.page-marker', { attributes: { 'data-label': label }, text }), element('p')],
  });
  return {
    children: [
      page('12', 'Page 12'),
      element('p.missing-pages', { attributes: { 'data-range': '13–44' }, text: 'Missing pages: 13–44' }),
      page('45', 'Page 45'),
      element('p.missing-pages', { attributes: { 'data-range': '46' }, text: 'Missing page: 46' }),
      page('47–48', 'Page 47–48'),
      element('h2.unnumbered', { text: 'Unnumbered pages' }),
      page('', 'Unnumbered page'),
      // An older server: no data attribute, the text is kept.
      element('section.page', { children: [element('p.page-marker', { text: 'Page 99' })] }),
    ],
  };
}

const texts = (content) => content.children.map((child) => (
  child.matches('section.page') ? child.querySelector(':scope > .page-marker').textContent : child.textContent));

describe('the markers of the document HTML', () => {
  test('are written in English as the server writes them', () => {
    assert.equal(pageMarkerText('42'), 'Page 42');
    assert.equal(pageMarkerText('42–43'), 'Page 42–43');
    assert.equal(pageMarkerText(''), 'Unnumbered page');
    assert.equal(missingPagesText('13–44'), 'Missing pages: 13–44');
    assert.equal(missingPagesText('13'), 'Missing page: 13');
    assert.equal(unnumberedHeadingText(), 'Unnumbered pages');
    const content = documentContent();
    const before = texts(content);
    localizeMarkers(content);
    assert.deepEqual(texts(content), before);
  });

  test('are translated from their data attributes', () => {
    setLocale(['fr-FR']);
    const content = documentContent();
    localizeMarkers(content);
    const fill = (template, values) => Object.entries(values)
      .reduce((text, [name, value]) => text.replace(`{${name}}`, value), template);
    assert.deepEqual(texts(content), [
      fill(FRENCH['Page {label}'], { label: '12' }),
      fill(FRENCH['Missing pages: {range}'], { range: '13–44' }),
      fill(FRENCH['Page {label}'], { label: '45' }),
      fill(FRENCH['Missing page: {range}'], { range: '46' }),
      fill(FRENCH['Page {label}'], { label: '47–48' }),
      FRENCH['Unnumbered pages'],
      FRENCH['Unnumbered page'],
      'Page 99',
    ]);
  });
});

describe('the page being read', () => {
  // Tops of the pages on screen, in px: page 2 is short, page 3 starts right after it.
  const TOPS = [-2000, 120, 900, 930, 2400];
  const at = (line) => pageAtLine(TOPS.length, (index) => TOPS[index], line);

  test('is the last page whose top has reached the line', () => {
    assert.equal(at(100), 0);
    assert.equal(at(119), 0);
    assert.equal(at(120), 1);
    assert.equal(at(899), 1);
    assert.equal(at(915), 2);
    assert.equal(at(930), 3);
    assert.equal(at(5000), 4);
  });

  test('is the first page before the text reaches the line', () => {
    assert.equal(pageAtLine(3, (index) => 500 + index * 800, 140), 0);
  });

  test('is found in a few reads, even in a long book', () => {
    let reads = 0;
    const index = pageAtLine(1000, (page) => {
      reads += 1;
      return page * 1000 - 400_000;
    }, 120);
    assert.equal(index, 400);
    assert.ok(reads <= 11, `${reads} reads`);
  });
});
