import type { TFunction } from 'i18next';

import { waitingPageCount } from '../../../domain/document-details.ts';
import type { DocumentStats } from '../../../domain/document-summary.ts';

export const waitingPagesNotice = (t: TFunction, count: number): string => {
  return t('{{count, number}} page is still waiting to be read: its text will be added once ready.', {
    count,
    defaultValue_one: '{{count, number}} page is still waiting to be read: its text will be added once ready.',
    defaultValue_other: '{{count, number}} pages are still waiting to be read: their text will be added once ready.',
  });
};

export const emptyReadingMessage = (t: TFunction, stats: DocumentStats): string => {
  if (waitingPageCount(stats) > 0) {
    return t('Its pages are still waiting to be read: their text will appear here once ready.');
  }
  if (stats.pageCount > 0) {
    return t('None of its pages is in the document: they couldn’t be read, are excluded or are duplicates.');
  }
  return t('This document has no page yet: add some from its screen or with the Android app.');
};
