import type { TFunction } from 'i18next';

import {
  countPages,
  type DocumentStats,
  type DocumentSummary,
  formatPageRanges,
  type PageCoverage,
} from '../../../domain/document-summary.ts';
import { documentKindLabel } from '../../i18next/document-labels.ts';

export type ChipTone = 'neutral' | 'info' | 'warn' | 'danger';

export interface StatusChip {
  readonly name: string;
  readonly text: string;
  readonly tone: ChipTone;
}

export function statusChips(t: TFunction, document: DocumentSummary): StatusChip[] {
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
}

export function coverageText(t: TFunction, coverage: PageCoverage): string {
  if (coverage.lowestNumber === null) {
    if (coverage.unnumberedCount === 0) return t('No numbered page');
    return t('{{count, number}} unnumbered page', {
      count: coverage.unnumberedCount,
      defaultValue_one: '{{count, number}} unnumbered page',
      defaultValue_other: '{{count, number}} unnumbered pages',
    });
  }
  const label = coverage.label === '' ? formatPageRanges(coverage.ranges) : coverage.label;
  const parts = [t('Pages {{label}}', { label })];
  if (coverage.gaps.length > 0) {
    parts.push(t('not scanned yet: {{ranges}}', { ranges: formatPageRanges(coverage.gaps) }));
  }
  return parts.join(' · ');
}

export function progressText(t: TFunction, stats: DocumentStats): string {
  const pages = t('{{count, number}} page: text ready', {
    count: stats.pageCount,
    defaultValue_one: '{{count, number}} page: text ready',
    defaultValue_other: '{{count, number}} pages: text ready',
  });
  return `${stats.doneCount} / ${pages}`;
}

export function librarySummaryText(t: TFunction, documents: readonly DocumentSummary[]): string {
  if (documents.length === 0) return '';
  const documentCount = t('{{count, number}} document', {
    count: documents.length,
    defaultValue_one: '{{count, number}} document',
    defaultValue_other: '{{count, number}} documents',
  });
  const pageCount = t('{{count, number}} page', {
    count: countPages(documents),
    defaultValue_one: '{{count, number}} page',
    defaultValue_other: '{{count, number}} pages',
  });
  return `${documentCount} · ${pageCount}`;
}
