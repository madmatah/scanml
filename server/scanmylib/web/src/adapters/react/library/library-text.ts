import type { TFunction } from 'i18next';

import type { EmptySearchReason, KindFilter } from '../../../domain/document-search.ts';
import {
  countPages,
  type DocumentStats,
  type DocumentSummary,
  type PageCoverage,
} from '../../../domain/document-summary.ts';
import type { NumberFormatting } from '../../../domain/formatting.ts';
import { documentKindLabel } from '../../i18next/document-labels.ts';
import { formatPartialPercent, quoted } from '../../i18next/formatted-text.ts';
import { pageCount, scannedPageCount } from '../document/coverage-layout.ts';

export type ChipTone = 'neutral' | 'info' | 'warn' | 'danger';

export interface StatusChip {
  readonly name: string;
  readonly text: string;
  readonly tone: ChipTone;
}

export type TextStatusTone = 'neutral' | 'info' | 'ok';

export interface TextStatus {
  readonly text: string;
  readonly tone: TextStatusTone;
}

export const statusChips = (t: TFunction, document: DocumentSummary): StatusChip[] => {
  const { stats } = document;
  const chips: StatusChip[] = [{ name: 'kind', text: documentKindLabel(t, document.kind), tone: 'neutral' }];
  if (stats.processingCount > 0) {
    chips.push({ name: 'processing', text: t('{{pages}} being read', { pages: stats.processingCount }), tone: 'info' });
  }
  if (stats.queuedCount > 0) {
    chips.push({ name: 'queued', text: t('{{pages}} queued', { pages: stats.queuedCount }), tone: 'warn' });
  }
  if (stats.errorCount > 0) {
    const text = t('{{count, number}} couldn’t be read', {
      count: stats.errorCount,
      defaultValue_one: '{{count, number}} couldn’t be read',
      defaultValue_other: '{{count, number}} couldn’t be read',
    });
    chips.push({ name: 'error', text, tone: 'danger' });
  }
  if (stats.excludedCount > 0) {
    const text = t('{{count, number}} excluded', {
      count: stats.excludedCount,
      defaultValue_one: '{{count, number}} excluded',
      defaultValue_other: '{{count, number}} excluded',
    });
    chips.push({ name: 'excluded', text, tone: 'neutral' });
  }
  if (stats.duplicateCount > 0) {
    const text = t('{{count, number}} duplicate', {
      count: stats.duplicateCount,
      defaultValue_one: '{{count, number}} duplicate',
      defaultValue_other: '{{count, number}} duplicates',
    });
    chips.push({ name: 'duplicates', text, tone: 'neutral' });
  }
  return chips;
};

export const bylineText = (t: TFunction, document: DocumentSummary): string => {
  return document.author === '' ? t('No author') : document.author;
};

export const coverageSummaryText = (t: TFunction, formatting: NumberFormatting, coverage: PageCoverage): string => {
  const { lowestNumber, highestNumber, ranges, gaps, unnumberedCount } = coverage;
  if (lowestNumber === null || highestNumber === null) {
    if (unnumberedCount === 0) return t('No numbered page');
    return t('{{count, number}} unnumbered page', {
      count: unnumberedCount,
      defaultValue_one: '{{count, number}} unnumbered page',
      defaultValue_other: '{{count, number}} unnumbered pages',
    });
  }
  if (gaps.length === 0) {
    if (lowestNumber === highestNumber) return t('Page {{page}}', { page: lowestNumber });
    return t('Pages {{lowest}}–{{highest}}, all scanned', { lowest: lowestNumber, highest: highestNumber });
  }
  const scanned = scannedPageCount(ranges);
  return t('{{scanned}} of pages {{lowest}}–{{highest}} scanned ({{percent}})', {
    scanned: formatting.formatNumber(scanned),
    lowest: lowestNumber,
    highest: highestNumber,
    percent: formatPartialPercent(t, formatting, scanned / pageCount([lowestNumber, highestNumber])),
  });
};

export const textStatus = (t: TFunction, stats: DocumentStats): TextStatus => {
  if (stats.pageCount === 0) return { text: t('No pages yet'), tone: 'neutral' };
  if (stats.doneCount === stats.pageCount) return { text: t('Text ready', { context: 'document' }), tone: 'ok' };
  const text = t('Text ready for {{done, number}} of {{count, number}} pages', {
    count: stats.pageCount,
    done: stats.doneCount,
    defaultValue_one: 'Text ready for {{done, number}} of {{count, number}} page',
    defaultValue_other: 'Text ready for {{done, number}} of {{count, number}} pages',
  });
  return { text, tone: 'info' };
};

export const kindFilterLabel = (t: TFunction, filter: KindFilter): string => {
  switch (filter) {
    case 'all':
      return t('All', { context: 'kinds' });
    case 'book':
      return t('Books');
    case 'other':
      return t('Other', { context: 'kinds' });
  }
};

export const emptySearchText = (t: TFunction, reason: EmptySearchReason, query: string): string => {
  switch (reason) {
    case 'no-document-of-kind':
      return t('No document of this kind.');
    case 'no-document-matches':
      return t('No document matches {{query}}.', { query: quoted(t, query.trim()) });
    case 'no-document-of-kind-matches':
      return t('No document of this kind matches {{query}}.', { query: quoted(t, query.trim()) });
  }
};

export const librarySummaryText = (t: TFunction, documents: readonly DocumentSummary[]): string => {
  if (documents.length === 0) return '';
  const documentCount = t('{{count, number}} document', {
    count: documents.length,
    defaultValue_one: '{{count, number}} document',
    defaultValue_other: '{{count, number}} documents',
  });
  const pageTotal = t('{{count, number}} page', {
    count: countPages(documents),
    defaultValue_one: '{{count, number}} page',
    defaultValue_other: '{{count, number}} pages',
  });
  return `${documentCount} · ${pageTotal}`;
};
