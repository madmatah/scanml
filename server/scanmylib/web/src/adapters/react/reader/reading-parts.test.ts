import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { type DocumentParts, documentParts, type PartElement } from './reading-parts.ts';

interface StandInElement extends PartElement {
  readonly name: string;
}

interface ElementParts {
  readonly attributes?: Readonly<Record<string, string>>;
  readonly text?: string;
  readonly markerText?: string;
}

const buildElement = (
  selector: string,
  name: string,
  { attributes = {}, text = '', markerText }: ElementParts = {},
) => {
  const [tag, ...classes] = selector.split('.');
  const element: StandInElement = {
    name,
    textContent: text,
    matches: (query) => {
      const [queryTag, ...queryClasses] = query.split('.');
      return (!queryTag || queryTag === tag) && queryClasses.every((className) => classes.includes(className));
    },
    querySelector: (query) =>
      query === ':scope > .page-marker' && markerText !== undefined ? { textContent: markerText } : null,
    getAttribute: (attributeName) => attributes[attributeName] ?? null,
  };
  return element;
};

describe('The reading parts', () => {
  describe('The documentParts() function', () => {
    describe('When the document holds pages, missing pages, unnumbered pages and other elements', () => {
      let documentPartsRead: DocumentParts<StandInElement>;
      beforeEach(() => {
        documentPartsRead = documentParts([
          buildElement('section.page', 'page 12', { attributes: { 'data-key': 'k-12' }, markerText: 'Page 12' }),
          buildElement('p.missing-pages', 'gap', { text: 'Pages not scanned yet: 13–44' }),
          buildElement('section.page', 'page 45', { attributes: { 'data-key': 'k-45' }, markerText: 'Page 45' }),
          buildElement('h2.unnumbered', 'heading', { text: 'Unnumbered pages' }),
          buildElement('p', 'stray paragraph', { text: 'Example text.' }),
          buildElement('section.page', 'plate', {
            attributes: { 'data-key': 'k-plate' },
            markerText: 'Unnumbered page',
          }),
        ]);
      });

      it('should list the pages, the missing pages and the heading in reading order, and nothing else', () => {
        assert.deepEqual(documentPartsRead.parts, [
          { type: 'page', key: 'k-12', marker: 'Page 12' },
          { type: 'gap', text: 'Pages not scanned yet: 13–44' },
          { type: 'page', key: 'k-45', marker: 'Page 45' },
          { type: 'heading', text: 'Unnumbered pages' },
          { type: 'page', key: 'k-plate', marker: 'Unnumbered page' },
        ]);
      });

      it('should give the elements of the pages, in the same order', () => {
        assert.deepEqual(
          documentPartsRead.sections.map((section) => section.name),
          ['page 12', 'page 45', 'plate'],
        );
      });
    });

    describe('When a page has neither its key nor its marker, from an older server', () => {
      let documentPartsRead: DocumentParts<StandInElement>;
      beforeEach(() => {
        documentPartsRead = documentParts([buildElement('section.page', 'page')]);
      });

      it('should still list it, with an empty key and marker', () => {
        assert.deepEqual(documentPartsRead.parts, [{ type: 'page', key: '', marker: '' }]);
      });
    });
  });
});
