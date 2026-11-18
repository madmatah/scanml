import type { TFunction } from 'i18next';

import type { PageGroupKind } from '../../../domain/document-details.ts';
import {
  type DocumentStats,
  formatPageRange,
  formatPageRanges,
  type PageRange,
} from '../../../domain/document-summary.ts';

export interface PageGroupHeading {
  readonly title: string;
  readonly hint: string;
}

export interface PageGroupSituation {
  readonly hasPlacedPages: boolean;
  readonly hasPagesPlacedByHand: boolean;
}

export type StatTone = 'warn' | 'info' | 'danger';

export interface StatTile {
  readonly name: string;
  readonly label: string;
  readonly count: number;
  readonly tone: StatTone | null;
}

export function pageGroupHeading(t: TFunction, kind: PageGroupKind, situation: PageGroupSituation): PageGroupHeading {
  switch (kind) {
    case 'placed':
      return {
        title: t('In the document'),
        hint: situation.hasPagesPlacedByHand
          ? t('In the reading order of document.md, with pages placed by hand.')
          : t('In the reading order of document.md.'),
      };
    case 'unplaced':
      if (!situation.hasPlacedPages) {
        return { title: t('In the document'), hint: t('No numbered page: capture order.') };
      }
      return {
        title: t('Unnumbered pages'),
        hint: t(
          'Nothing tells where they go: they are at the end of the document, in capture order. “Organize” can put them in their place.',
        ),
      };
    case 'pending':
      return {
        title: t('Not in the document yet'),
        hint: t('Waiting to be read, or couldn’t be read: they will join the document once their text is ready.'),
      };
    case 'excluded':
      return { title: t('Excluded'), hint: t('Left out of document.md.') };
    case 'duplicate':
      return { title: t('Duplicates'), hint: t('Replaced by a newer scan of the same page number.') };
  }
}

export function statTiles(t: TFunction, stats: DocumentStats): StatTile[] {
  return [
    { name: 'pages', label: t('Pages'), count: stats.pageCount, tone: null },
    { name: 'done', label: t('Text ready'), count: stats.doneCount, tone: null },
    { name: 'queued', label: t('Queued'), count: stats.queuedCount, tone: 'warn' },
    { name: 'processing', label: t('Being read'), count: stats.processingCount, tone: 'info' },
    { name: 'error', label: t('Couldn’t be read'), count: stats.errorCount, tone: 'danger' },
    { name: 'excluded', label: t('Excluded'), count: stats.excludedCount, tone: null },
    { name: 'duplicates', label: t('Duplicates'), count: stats.duplicateCount, tone: null },
  ];
}

export function coverageRangeTitle(t: TFunction, range: PageRange, isMissing: boolean): string {
  const [start, end] = range;
  if (start === end) {
    return isMissing
      ? t('Page {{page}}: not scanned yet', { page: start })
      : t('Page {{page}}: scanned', { page: start });
  }
  const pages = formatPageRange(range);
  return isMissing
    ? t('Pages {{range}}: not scanned yet', { range: pages })
    : t('Pages {{range}}: scanned', { range: pages });
}

export function coverageDescription(
  t: TFunction,
  scannedLabel: string,
  gaps: readonly PageRange[],
  lowestNumber: number,
  highestNumber: number,
): string {
  if (gaps.length === 0) {
    return t('All pages from {{lowest}} to {{highest}} are scanned.', { lowest: lowestNumber, highest: highestNumber });
  }
  return t('Scanned pages: {{scanned}}. Not scanned yet: {{missing}}.', {
    scanned: scannedLabel,
    missing: formatPageRanges(gaps),
  });
}

export function missingPagesText(t: TFunction, gaps: readonly PageRange[]): string {
  return gaps.length === 0 ? t('none', { context: 'missing pages' }) : formatPageRanges(gaps);
}

export function unnumberedPagesNote(t: TFunction, unnumberedCount: number): string {
  const pages = t('{{count, number}} unnumbered page', {
    count: unnumberedCount,
    defaultValue_one: '{{count, number}} unnumbered page',
    defaultValue_other: '{{count, number}} unnumbered pages',
  });
  return `+ ${pages}`;
}
