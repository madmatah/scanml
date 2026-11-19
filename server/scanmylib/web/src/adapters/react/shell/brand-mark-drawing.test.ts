import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { before, describe, it } from 'node:test';

import { BRAND_MARK_HREF } from './brand-mark-drawing.ts';

const WEB = new URL('../../../../', import.meta.url);

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
});
