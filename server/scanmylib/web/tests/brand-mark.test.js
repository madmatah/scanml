import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { before, describe, it } from 'node:test';

import { BRAND_MARK_HREF, BRAND_MARK_VIEW_BOX } from '../static/js/components/brand-mark.js';

const WEB = new URL('../', import.meta.url);

function readAttribute(tag, name) {
  const attribute = tag.match(new RegExp(`\\s${name}="([^"]*)"`));
  if (!attribute) {
    throw new Error(`no ${name} in ${tag}`);
  }
  return attribute[1];
}

describe('The brand mark', () => {
  describe('The BRAND_MARK_HREF constant', () => {
    const [drawingPath, fragment] = BRAND_MARK_HREF.split('#');
    let groupIds;
    before(() => {
      const drawing = readFileSync(new URL(drawingPath.replace(/^\//, ''), WEB), 'utf8');
      groupIds = [...drawing.matchAll(/<g\s[^>]*\bid="([^"]*)"/g)].map((group) => group[1]);
    });

    it("should name a group of icon.svg, so that the page draws the icon's own mark", () => {
      assert.ok(groupIds.includes(fragment));
    });
  });

  describe('When the header of index.html draws the mark', () => {
    let headerMark;
    before(() => {
      const page = readFileSync(new URL('index.html', WEB), 'utf8');
      const svg = page.match(/<svg class="brand-mark"[^>]*>/)[0];
      const use = page.match(/<svg class="brand-mark"[^>]*>\s*(<use\s[^>]*>)/)[1];
      headerMark = { viewBox: readAttribute(svg, 'viewBox'), href: readAttribute(use, 'href') };
    });

    it('should frame and name it with BRAND_MARK_VIEW_BOX and BRAND_MARK_HREF, so that the header and the sign-in show one drawing', () => {
      assert.deepEqual(headerMark, { viewBox: BRAND_MARK_VIEW_BOX, href: BRAND_MARK_HREF });
    });
  });
});
