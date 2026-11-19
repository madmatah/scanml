import type { OutlineEntry } from '../../../domain/reading.ts';

export type GroupedOutlineEntry<Page> = Exclude<OutlineEntry<Page>, { readonly type: 'group' }>;

export interface OutlineGroup<Page> {
  readonly label: string | null;
  readonly entries: GroupedOutlineEntry<Page>[];
}

export const outlineGroups = <Page>(outline: readonly OutlineEntry<Page>[]): OutlineGroup<Page>[] => {
  const groups: OutlineGroup<Page>[] = [{ label: null, entries: [] }];
  for (const entry of outline) {
    if (entry.type === 'group') groups.push({ label: entry.label, entries: [] });
    else groups.at(-1)?.entries.push(entry);
  }
  return groups.filter((group) => group.label !== null || group.entries.length > 0);
};
