import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { setLocale } from '../static/js/lib/i18n.js';
import {
  localizeMarkers,
  missingPagesText,
  pageAtLine,
  pageMarkerText,
  readingOutline,
  unnumberedHeadingText,
} from '../static/js/lib/reading.js';
import FRENCH from '../static/js/locales/fr.js';

const ENGLISH_PREFERENCES = ['en-US'];
const FRENCH_PREFERENCES = ['fr-FR'];

function fillTemplate(template, placeholderValues) {
  return Object.entries(placeholderValues).reduce(
    (text, [placeholderName, placeholderValue]) => text.replaceAll(`{${placeholderName}}`, () => placeholderValue),
    template,
  );
}

function summarize(outline) {
  return outline.map(({ type, index, label }) => (type === 'page' ? [index, label] : [type, label]));
}

// A stand-in for the elements of the document HTML, with what localizeMarkers() uses of the DOM.
function buildElement(selector, { attributes = {}, text = '', children = [] } = {}) {
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

function buildPage(label, markerText) {
  return buildElement('section.page', {
    attributes: { 'data-key': `k-${label}` },
    children: [
      buildElement('p.page-marker', { attributes: { 'data-label': label }, text: markerText }),
      buildElement('p'),
    ],
  });
}

function buildDocumentContent() {
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

function buildOlderServerContent() {
  return {
    children: [buildElement('section.page', { children: [buildElement('p.page-marker', { text: 'Page 99' })] })],
  };
}

function readTexts(content) {
  return content.children.map((child) =>
    child.matches('section.page') ? child.querySelector(':scope > .page-marker').textContent : child.textContent,
  );
}

describe('The reading view', () => {
  beforeEach(() => {
    setLocale(ENGLISH_PREFERENCES);
  });

  describe('The readingOutline() function', () => {
    // Parts of GET /api/documents/{id}/html, and the API's pages by key.
    const parts = [
      { type: 'page', key: 'k-i', marker: 'Page i' },
      { type: 'page', key: 'k-1', marker: 'Page 1' },
      { type: 'page', key: 'k-plate', marker: 'Unnumbered page' },
      { type: 'page', key: 'k-2', marker: 'Page 2' },
      { type: 'gap', text: 'Missing pages: 3–5' },
      { type: 'page', key: 'k-6', marker: 'Page 6–7' },
      { type: 'heading', text: 'Unnumbered pages' },
      { type: 'page', key: 'k-notes', marker: 'Unnumbered page' },
    ];
    const pagesByKey = new Map([
      ['k-i', { id: 'i', page_label: 'i' }],
      ['k-1', { id: '1', page_label: '1' }],
      ['k-plate', { id: 'plate', page_label: null }],
      ['k-2', { id: '2', page_label: '2' }],
      ['k-6', { id: '6', page_label: '6–7', number_end: 7 }],
      ['k-notes', { id: 'notes', page_label: null }],
    ]);
    const firstThreeParts = parts.slice(0, 3);

    describe('When the document has numbered pages, missing pages and unnumbered ones', () => {
      let outline;
      beforeEach(() => {
        outline = readingOutline(parts, pagesByKey);
      });

      it('should list the pages in reading order, with the missing pages and the unnumbered ones', () => {
        assert.deepEqual(summarize(outline), [
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

      it('should give each page entry its page', () => {
        assert.deepEqual(
          outline.filter((entry) => entry.type === 'page').map((entry) => [entry.key, entry.page.id]),
          [
            ['k-i', 'i'],
            ['k-1', '1'],
            ['k-plate', 'plate'],
            ['k-2', '2'],
            ['k-6', '6'],
            ['k-notes', 'notes'],
          ],
        );
      });
    });

    describe('When the document data lacks the pages of the HTML, having changed meanwhile', () => {
      const noPagesByKey = new Map();
      let outline;
      beforeEach(() => {
        outline = readingOutline(firstThreeParts, noPagesByKey);
      });

      it('should label each page with its marker in the HTML', () => {
        assert.deepEqual(summarize(outline), [
          [0, 'Page i'],
          [1, 'Page 1'],
          [2, 'Unnumbered page'],
        ]);
      });

      it('should give the page entries no page', () => {
        assert.deepEqual(
          outline.map((entry) => entry.page),
          [null, null, null],
        );
      });
    });

    describe('When no page of the document has a number, as in a letter', () => {
      const letterKeys = ['a', 'b', 'c'];
      const letterParts = letterKeys.map((key) => ({ type: 'page', key, marker: 'Unnumbered page' }));
      const letterPagesByKey = new Map(letterKeys.map((key) => [key, { page_label: null }]));
      let outline;
      beforeEach(() => {
        outline = readingOutline(letterParts, letterPagesByKey);
      });

      it('should tell the pages apart by their position in the reading order', () => {
        assert.deepEqual(
          outline.map((entry) => entry.label),
          ['No number (position 1)', 'No number (position 2)', 'No number (position 3)'],
        );
      });
    });

    describe('When the UI is in French', () => {
      const unnumberedThirdPageLabel = fillTemplate(FRENCH['{label} (position {position})'], {
        label: FRENCH['No number'],
        position: '3',
      });
      let outline;
      beforeEach(() => {
        setLocale(FRENCH_PREFERENCES);
        outline = readingOutline(firstThreeParts, pagesByKey);
      });

      it('should label the pages in French', () => {
        assert.deepEqual(
          outline.map((entry) => entry.label),
          ['p. i', 'p. 1', unnumberedThirdPageLabel],
        );
      });
    });

    describe('When the document has nothing to read', () => {
      const noParts = [];
      let outline;
      beforeEach(() => {
        outline = readingOutline(noParts, pagesByKey);
      });

      it('should be empty', () => {
        assert.deepEqual(outline, []);
      });
    });
  });

  describe('The pageMarkerText() function', () => {
    describe('When the page has a number', () => {
      const label = '42';
      let marker;
      beforeEach(() => {
        marker = pageMarkerText(label);
      });

      it('should write the page and its number in English, as the server does', () => {
        assert.equal(marker, 'Page 42');
      });
    });

    describe('When the page has a range of numbers', () => {
      const label = '42–43';
      let marker;
      beforeEach(() => {
        marker = pageMarkerText(label);
      });

      it('should write the page and its range in English, as the server does', () => {
        assert.equal(marker, 'Page 42–43');
      });
    });

    describe('When the page has no number', () => {
      const noLabel = '';
      let marker;
      beforeEach(() => {
        marker = pageMarkerText(noLabel);
      });

      it('should write in English that the page is unnumbered, as the server does', () => {
        assert.equal(marker, 'Unnumbered page');
      });
    });
  });

  describe('The missingPagesText() function', () => {
    describe('When several pages are missing', () => {
      const range = '13–44';
      let marker;
      beforeEach(() => {
        marker = missingPagesText(range);
      });

      it('should write in English that the pages of the range are missing, as the server does', () => {
        assert.equal(marker, 'Missing pages: 13–44');
      });
    });

    describe('When one page is missing', () => {
      const range = '13';
      let marker;
      beforeEach(() => {
        marker = missingPagesText(range);
      });

      it('should write in English that the page is missing, in the singular, as the server does', () => {
        assert.equal(marker, 'Missing page: 13');
      });
    });
  });

  describe('The unnumberedHeadingText() function', () => {
    let heading;
    beforeEach(() => {
      heading = unnumberedHeadingText();
    });

    it('should write in English the heading of the unnumbered pages, as the server does', () => {
      assert.equal(heading, 'Unnumbered pages');
    });
  });

  describe('The localizeMarkers() function', () => {
    describe('When the UI is in English', () => {
      describe('When the markers carry their data attributes', () => {
        let content;
        let textsBefore;
        let textsAfter;
        beforeEach(() => {
          content = buildDocumentContent();
          textsBefore = readTexts(content);
          localizeMarkers(content);
          textsAfter = readTexts(content);
        });

        it('should leave the markers as the server wrote them', () => {
          assert.deepEqual(textsAfter, textsBefore);
        });
      });

      describe('When a marker has no data attribute, from an older server', () => {
        let content;
        let textsBefore;
        let textsAfter;
        beforeEach(() => {
          content = buildOlderServerContent();
          textsBefore = readTexts(content);
          localizeMarkers(content);
          textsAfter = readTexts(content);
        });

        it('should leave the marker as the server wrote it', () => {
          assert.deepEqual(textsAfter, textsBefore);
        });
      });
    });

    describe('When the UI is in French', () => {
      beforeEach(() => {
        setLocale(FRENCH_PREFERENCES);
      });

      describe('When the markers carry their data attributes', () => {
        let content;
        beforeEach(() => {
          content = buildDocumentContent();
          localizeMarkers(content);
        });

        it('should translate each marker from its data attributes', () => {
          assert.deepEqual(readTexts(content), [
            fillTemplate(FRENCH['Page {label}'], { label: '12' }),
            fillTemplate(FRENCH['Missing pages: {range}'], { range: '13–44' }),
            fillTemplate(FRENCH['Page {label}'], { label: '45' }),
            fillTemplate(FRENCH['Missing page: {range}'], { range: '46' }),
            fillTemplate(FRENCH['Page {label}'], { label: '47–48' }),
            FRENCH['Unnumbered pages'],
            FRENCH['Unnumbered page'],
          ]);
        });
      });

      describe('When a marker has no data attribute, from an older server', () => {
        let content;
        beforeEach(() => {
          content = buildOlderServerContent();
          localizeMarkers(content);
        });

        it('should keep the text the server wrote', () => {
          assert.deepEqual(readTexts(content), ['Page 99']);
        });
      });
    });
  });

  describe('The pageAtLine() function', () => {
    describe('When pages of different heights are laid out from above the screen', () => {
      const pageTopsPixels = [-2000, 120, 900, 930, 2400];
      const lines = [
        {
          situation: 'When the reading line is above the top of the second page',
          linePixels: 100,
          rule: 'should be the first page, whose top has scrolled past the line',
          expectedPageIndex: 0,
        },
        {
          situation: 'When the reading line is one pixel above the top of the second page',
          linePixels: 119,
          rule: 'should still be the first page',
          expectedPageIndex: 0,
        },
        {
          situation: 'When the reading line is at the top of the second page',
          linePixels: 120,
          rule: 'should be the second page, whose top has reached the line',
          expectedPageIndex: 1,
        },
        {
          situation: 'When the reading line is one pixel above the top of the third page',
          linePixels: 899,
          rule: 'should still be the second page',
          expectedPageIndex: 1,
        },
        {
          situation: 'When the reading line is within the short third page',
          linePixels: 915,
          rule: 'should be the third page',
          expectedPageIndex: 2,
        },
        {
          situation: 'When the reading line is at the top of the fourth page, right after the short one',
          linePixels: 930,
          rule: 'should be the fourth page',
          expectedPageIndex: 3,
        },
        {
          situation: 'When the reading line is far below the top of the last page',
          linePixels: 5000,
          rule: 'should be the last page',
          expectedPageIndex: 4,
        },
      ];

      for (const { situation, linePixels, rule, expectedPageIndex } of lines) {
        describe(situation, () => {
          let pageIndex;
          beforeEach(() => {
            pageIndex = pageAtLine(pageTopsPixels.length, (index) => pageTopsPixels[index], linePixels);
          });

          it(rule, () => {
            assert.equal(pageIndex, expectedPageIndex);
          });
        });
      }
    });

    describe('When the text has not reached the reading line yet', () => {
      const pageCount = 3;
      const firstTopPixels = 500;
      const pageHeightPixels = 800;
      const linePixels = 140;
      let pageIndex;
      beforeEach(() => {
        pageIndex = pageAtLine(pageCount, (index) => firstTopPixels + index * pageHeightPixels, linePixels);
      });

      it('should be the first page', () => {
        assert.equal(pageIndex, 0);
      });
    });

    describe('When the reader is in the middle of a long book', () => {
      const pageCount = 1000;
      const pageHeightPixels = 1000;
      const scrolledPixels = 400_000;
      const linePixels = 120;
      const maxTopReadCount = 11;
      let topReadCount;
      let pageIndex;
      beforeEach(() => {
        topReadCount = 0;
        pageIndex = pageAtLine(
          pageCount,
          (index) => {
            topReadCount += 1;
            return index * pageHeightPixels - scrolledPixels;
          },
          linePixels,
        );
      });

      it('should find the page at the reading line', () => {
        assert.equal(pageIndex, 400);
      });

      it('should read the tops of a few pages only, since it runs while the reader scrolls', () => {
        assert.ok(topReadCount <= maxTopReadCount, `${topReadCount} reads`);
      });
    });
  });
});
