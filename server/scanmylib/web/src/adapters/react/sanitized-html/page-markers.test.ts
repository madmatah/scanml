// French is written only in the French catalog, so these tests compare with its entries instead of quoting it.
import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import frenchCatalog from '../../../../locales/fr.json' with { type: 'json' };
import { CATALOGS } from '../../i18next/catalogs.ts';
import { createLocalizationFor } from '../../i18next/localization.test-support.ts';
import type { Localization } from '../../i18next/localization.ts';
import { localizeMarkers, type MarkerContent, type MarkerElement } from './page-markers.ts';

interface StandInElement extends MarkerElement {
  readonly children: readonly StandInElement[];
}

interface StandInContent extends MarkerContent {
  readonly children: readonly StandInElement[];
}

interface ElementParts {
  readonly attributes?: Readonly<Record<string, string>>;
  readonly text?: string;
  readonly children?: readonly StandInElement[];
}

const ENGLISH_LANGUAGES = ['en-US'];
const FRENCH_LANGUAGES = ['fr-FR'];

function fillTemplate(template: string, placeholderValues: Readonly<Record<string, string>>): string {
  return Object.entries(placeholderValues).reduce(
    (text, [placeholderName, placeholderValue]) => text.replaceAll(`{{${placeholderName}}}`, () => placeholderValue),
    template,
  );
}

function buildElement(
  selector: string,
  { attributes = {}, text = '', children = [] }: ElementParts = {},
): StandInElement {
  const [tag, ...classes] = selector.split('.');
  const matchesQuery = (query: string): boolean => {
    const [queryTag, ...queryClasses] = query.split('.');
    return (!queryTag || queryTag === tag) && queryClasses.every((name) => classes.includes(name));
  };
  return {
    children,
    textContent: text,
    matches: matchesQuery,
    querySelector: (query) => children.find((candidate) => candidate.matches(query.replace(/^:scope > /, ''))) ?? null,
    getAttribute: (name) => attributes[name] ?? null,
  };
}

function buildPage(label: string, markerText: string): StandInElement {
  return buildElement('section.page', {
    attributes: { 'data-key': `k-${label}` },
    children: [
      buildElement('p.page-marker', { attributes: { 'data-label': label }, text: markerText }),
      buildElement('p'),
    ],
  });
}

function buildDocumentContent(): StandInContent {
  return {
    children: [
      buildPage('12', 'Page 12'),
      buildElement('p.missing-pages', { attributes: { 'data-range': '13–44' }, text: 'Missing pages: 13–44' }),
      buildPage('45', 'Page 45'),
      buildElement('p.missing-pages', { attributes: { 'data-range': '46' }, text: 'Missing page: 46' }),
      buildPage('47–48', 'Page 47–48'),
      buildElement('h2.unnumbered', { text: 'Unnumbered pages' }),
      buildPage('', 'Unnumbered page'),
    ],
  };
}

function buildOlderServerContent(): StandInContent {
  return {
    children: [
      buildElement('section.page', { children: [buildElement('p.page-marker', { text: 'Page 99' })] }),
      buildElement('p.missing-pages', { text: 'Missing pages: 100–104' }),
    ],
  };
}

function readTexts(content: StandInContent): (string | null)[] {
  return content.children.map((child) =>
    child.matches('section.page')
      ? (child.querySelector(':scope > .page-marker')?.textContent ?? null)
      : child.textContent,
  );
}

describe('The page markers', () => {
  describe('The localizeMarkers() function', () => {
    describe('When the UI is in English', () => {
      let localization: Localization;
      beforeEach(async () => {
        localization = await createLocalizationFor(ENGLISH_LANGUAGES, CATALOGS);
      });

      describe('When the markers carry their data attributes', () => {
        let content: StandInContent;
        beforeEach(() => {
          content = buildDocumentContent();
          localizeMarkers(localization.i18next.t, content);
        });

        it('should write the gaps in the words of the coverage, rather than the server’s', () => {
          assert.deepEqual(readTexts(content), [
            'Page 12',
            'Pages not scanned yet: 13–44',
            'Page 45',
            'Page not scanned yet: 46',
            'Page 47–48',
            'Unnumbered pages',
            'Unnumbered page',
          ]);
        });
      });

      describe('When a marker has no data attribute, from an older server', () => {
        let content: StandInContent;
        let textsBefore: (string | null)[];
        let textsAfter: (string | null)[];
        beforeEach(() => {
          content = buildOlderServerContent();
          textsBefore = readTexts(content);
          localizeMarkers(localization.i18next.t, content);
          textsAfter = readTexts(content);
        });

        it('should leave the markers as the server wrote them', () => {
          assert.deepEqual(textsAfter, textsBefore);
        });
      });
    });

    describe('When the UI is in French', () => {
      let localization: Localization;
      beforeEach(async () => {
        localization = await createLocalizationFor(FRENCH_LANGUAGES, CATALOGS);
      });

      describe('When the markers carry their data attributes', () => {
        let content: StandInContent;
        beforeEach(() => {
          content = buildDocumentContent();
          localizeMarkers(localization.i18next.t, content);
        });

        it('should translate each marker from its data attributes', () => {
          assert.deepEqual(readTexts(content), [
            fillTemplate(frenchCatalog['Page {{label}}'], { label: '12' }),
            fillTemplate(frenchCatalog['Pages not scanned yet: {{range}}'], { range: '13–44' }),
            fillTemplate(frenchCatalog['Page {{label}}'], { label: '45' }),
            fillTemplate(frenchCatalog['Page not scanned yet: {{range}}'], { range: '46' }),
            fillTemplate(frenchCatalog['Page {{label}}'], { label: '47–48' }),
            frenchCatalog['Unnumbered pages'],
            frenchCatalog['Unnumbered page'],
          ]);
        });
      });

      describe('When a marker has no data attribute, from an older server', () => {
        let content: StandInContent;
        beforeEach(() => {
          content = buildOlderServerContent();
          localizeMarkers(localization.i18next.t, content);
        });

        it('should keep the text the server wrote, since only the data attributes give what to write', () => {
          assert.deepEqual(readTexts(content), ['Page 99', 'Missing pages: 100–104']);
        });
      });
    });
  });
});
