import type { TFunction } from 'i18next';

import { namesSeveralPages, type OutlineEntry } from '../../domain/reading.ts';
import { type LabeledPage, pageShortLabel } from './page-labels.ts';

export function pageMarkerText(t: TFunction, label: string): string {
  return label ? t('Page {{label}}', { label }) : t('Unnumbered page');
}

export function missingPagesText(t: TFunction, range: string): string {
  return namesSeveralPages(range)
    ? t('Pages not scanned yet: {{range}}', { range })
    : t('Page not scanned yet: {{range}}', { range });
}

export function unnumberedHeadingText(t: TFunction): string {
  return t('Unnumbered pages');
}

export function outlineEntryLabel(t: TFunction, entry: OutlineEntry<LabeledPage>): string {
  switch (entry.type) {
    case 'gap':
    case 'group':
      return entry.label;
    case 'page':
      if (entry.page === null) return entry.marker;
      if (entry.page.page_label) return pageShortLabel(t, entry.page);
      return t('{{label}} (position {{position}})', {
        label: pageShortLabel(t, entry.page),
        position: entry.index + 1,
      });
  }
}
