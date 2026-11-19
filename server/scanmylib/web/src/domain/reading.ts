export type ReadingPart =
  | { readonly type: 'page'; readonly key: string; readonly marker: string }
  | { readonly type: 'gap'; readonly text: string }
  | { readonly type: 'heading'; readonly text: string };

export type OutlineEntry<Page> =
  | {
      readonly type: 'page';
      readonly index: number;
      readonly key: string;
      readonly page: Page | null;
      readonly marker: string;
    }
  | { readonly type: 'gap'; readonly label: string }
  | { readonly type: 'group'; readonly label: string };

const PAGE_RANGE_DASH = /[–-]/;

export const namesSeveralPages = (range: string): boolean => {
  return PAGE_RANGE_DASH.test(range);
};

export const readingOutline = <Page>(
  parts: readonly ReadingPart[],
  pagesByKey: ReadonlyMap<string, Page>,
): OutlineEntry<Page>[] => {
  const entries: OutlineEntry<Page>[] = [];
  let pageCount = 0;
  for (const part of parts) {
    if (part.type === 'page') {
      const page = pagesByKey.get(part.key) ?? null;
      entries.push({ type: 'page', index: pageCount, key: part.key, page, marker: part.marker });
      pageCount += 1;
    } else {
      entries.push({ type: part.type === 'gap' ? 'gap' : 'group', label: part.text });
    }
  }
  return entries;
};

// A binary search: a long book has hundreds of pages, and this runs while the reader scrolls.
export const pageAtLine = (
  pageCount: number,
  topPixelsOf: (pageIndex: number) => number,
  linePixels: number,
): number => {
  let low = 0;
  let high = pageCount - 1;
  let found = 0;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    if (topPixelsOf(middle) <= linePixels) {
      found = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return found;
};
