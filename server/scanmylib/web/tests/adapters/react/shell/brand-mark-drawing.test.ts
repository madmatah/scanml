import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { before, describe, it } from 'node:test';

import { BRAND_MARK_HREF, BRAND_MARK_VIEW_BOX } from '../../../../src/adapters/react/shell/brand-mark-drawing.ts';

interface Mark {
  readonly viewBox: string;
  readonly href: string;
}

const WEB = new URL('../../../../', import.meta.url);

function readAttribute(tag: string, name: string): string {
  const attribute = tag.match(new RegExp(`\\s${name}="([^"]*)"`))?.[1];
  if (attribute === undefined) {
    throw new Error(`no ${name} in ${tag}`);
  }
  return attribute;
}

function readMatch(text: string, pattern: RegExp, group = 0): string {
  const match = text.match(pattern)?.[group];
  if (match === undefined) {
    throw new Error(`no match of ${pattern}`);
  }
  return match;
}

describe('The brand mark drawing', () => {
  describe('The BRAND_MARK_HREF constant', () => {
    const [drawingPath = '', fragment = ''] = BRAND_MARK_HREF.split('#');
    let groupIds: string[];
    before(() => {
      const drawing = readFileSync(new URL(drawingPath.replace(/^\//, ''), WEB), 'utf8');
      groupIds = [...drawing.matchAll(/<g\s[^>]*\bid="([^"]*)"/g)].map((group) => group[1] ?? '');
    });

    it("should name a group of icon.svg, so that the page draws the icon's own mark", () => {
      assert.ok(groupIds.includes(fragment));
    });
  });

  describe('When the header of index.html draws the mark', () => {
    let headerMark: Mark;
    before(() => {
      const page = readFileSync(new URL('index.html', WEB), 'utf8');
      const svg = readMatch(page, /<svg class="brand-mark"[^>]*>/);
      const use = readMatch(page, /<svg class="brand-mark"[^>]*>\s*(<use\s[^>]*>)/, 1);
      headerMark = { viewBox: readAttribute(svg, 'viewBox'), href: readAttribute(use, 'href') };
    });

    it('should frame and name it with BRAND_MARK_VIEW_BOX and BRAND_MARK_HREF, so that the header and the sign-in show one drawing', () => {
      assert.deepEqual(headerMark, { viewBox: BRAND_MARK_VIEW_BOX, href: BRAND_MARK_HREF });
    });
  });
});
