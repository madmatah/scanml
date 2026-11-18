import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { type OutlineGroup, outlineGroups } from '../../../../src/adapters/react/reader/outline-groups.ts';
import type { OutlineEntry } from '../../../../src/domain/reading.ts';

interface Page {
  readonly id: string;
}

function pageEntry(index: number): OutlineEntry<Page> {
  return { type: 'page', index, key: `k-${index}`, page: { id: String(index) }, marker: `Page ${index + 1}` };
}

function summarize(groups: readonly OutlineGroup<Page>[]): (string | null | (string | number)[])[][] {
  return groups.map((group) => [
    group.label,
    group.entries.map((entry) => (entry.type === 'page' ? entry.index : entry.label)),
  ]);
}

describe('The outline groups', () => {
  describe('The outlineGroups() function', () => {
    describe('When pages and a missing range come before the heading of the unnumbered pages', () => {
      let groups: OutlineGroup<Page>[];
      beforeEach(() => {
        groups = outlineGroups([
          pageEntry(0),
          { type: 'gap', label: 'Pages not scanned yet: 2–4' },
          pageEntry(1),
          { type: 'group', label: 'Unnumbered pages' },
          pageEntry(2),
          pageEntry(3),
        ]);
      });

      it('should keep the entries before the heading outside any group, and put the others under it', () => {
        assert.deepEqual(summarize(groups), [
          [null, [0, 'Pages not scanned yet: 2–4', 1]],
          ['Unnumbered pages', [2, 3]],
        ]);
      });
    });

    describe('When the outline starts with the heading, no page being numbered', () => {
      let groups: OutlineGroup<Page>[];
      beforeEach(() => {
        groups = outlineGroups([{ type: 'group', label: 'Unnumbered pages' }, pageEntry(0)]);
      });

      it('should show no empty group before it', () => {
        assert.deepEqual(summarize(groups), [['Unnumbered pages', [0]]]);
      });
    });
  });
});
