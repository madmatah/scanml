import type { DocumentStats, DocumentSummary } from './document-summary.ts';

// A document as the api gives it alone, after a change: its summary, and what its own screen shows besides.
export interface DocumentDetails extends DocumentSummary {
  readonly slug: string;
  readonly notes: string;
  readonly unwarp: boolean;
  readonly folder: string;
}

export interface PageSummary {
  readonly id: string;
  readonly status: string;
  readonly pageLabel: string | null;
  // The last number of a page that holds several, such as a spread.
  readonly numberEnd: number | null;
  readonly numberSource: string | null;
  readonly isExcluded: boolean;
  readonly duplicateOf: string | null;
  readonly isInDocument: boolean;
  readonly placement: string | null;
  // The place chosen by hand on the line of the page numbers, or null when the page has its automatic place.
  readonly position: number | null;
  readonly rotation: number;
  readonly thumbnailUrl: string;
}

// The api lists the pages in reading order (the placed pages, then those it could not place), then the pages waiting
// for their text, the excluded ones and the duplicates.
export interface DocumentWithPages extends DocumentDetails {
  readonly pages: readonly PageSummary[];
}

export type PageGroupKind = 'placed' | 'unplaced' | 'pending' | 'excluded' | 'duplicate';

export interface PageGroup {
  readonly key: string;
  readonly kind: PageGroupKind;
  readonly pages: readonly PageSummary[];
}

const PAGES_TO_ORGANIZE = 2;

export function pageGroupOf(page: PageSummary): PageGroupKind {
  if (page.isInDocument) return page.placement === 'unplaced' ? 'unplaced' : 'placed';
  if (page.isExcluded) return 'excluded';
  if (page.duplicateOf !== null) return 'duplicate';
  return 'pending';
}

// Consecutive pages of one kind form a group, in the api's order; a kind that comes back later forms a group of its
// own, with a key of its own.
export function groupPages(pages: readonly PageSummary[]): PageGroup[] {
  const groups: { readonly kind: PageGroupKind; readonly pages: PageSummary[] }[] = [];
  for (const page of pages) {
    const kind = pageGroupOf(page);
    const last = groups.at(-1);
    if (last?.kind === kind) last.pages.push(page);
    else groups.push({ kind, pages: [page] });
  }
  const occurrences = new Map<PageGroupKind, number>();
  return groups.map(({ kind, pages: groupPages }) => {
    const occurrence = occurrences.get(kind) ?? 0;
    occurrences.set(kind, occurrence + 1);
    return { key: occurrence === 0 ? kind : `${kind}-${occurrence}`, kind, pages: groupPages };
  });
}

export function hasPlacedPages(groups: readonly PageGroup[]): boolean {
  return groups.some((group) => group.kind === 'placed');
}

export function hasPagesPlacedByHand(pages: readonly PageSummary[]): boolean {
  return pages.some((page) => page.isInDocument && page.placement === 'manual');
}

export function canOrganize(pages: readonly PageSummary[]): boolean {
  return pages.filter((page) => page.isInDocument).length >= PAGES_TO_ORGANIZE;
}

export function isTextPending(stats: DocumentStats): boolean {
  return stats.queuedCount > 0 || stats.processingCount > 0;
}

export function hasPagesPositionedByHand(pages: readonly PageSummary[]): boolean {
  return pages.some((page) => page.position !== null);
}
