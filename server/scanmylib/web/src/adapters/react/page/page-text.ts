import type { TFunction } from 'i18next';

import type { DateFormatting, NumberFormatting } from '../../../domain/formatting.ts';
import type { PageDetails, PageReading } from '../../../domain/page-details.ts';
import { formatDateTime, formatSeconds, quoted } from '../../i18next/formatted-text.ts';
import { numberSourceLabel, pageStatusLabel, pageTitle } from '../../i18next/page-labels.ts';

export interface DetailRow {
  readonly term: string;
  readonly description: string;
  readonly isCode: boolean;
}

export interface DetailFormatting {
  readonly numbers: NumberFormatting;
  readonly dates: DateFormatting;
}

const NO_VALUE = '—';
// The start of a photo series' id tells it apart from the others of the document.
const SERIES_ID_LENGTH = 8;

const formatCharacterCount = (t: TFunction, count: number): string => {
  return t('{{count, number}} character', {
    count,
    defaultValue_one: '{{count, number}} character',
    defaultValue_other: '{{count, number}} characters',
  });
};

const numberDescription = (t: TFunction, page: PageDetails): string => {
  if (page.pageLabel === null || page.pageLabel === '') return t('none', { context: 'page number' });
  const source = numberSourceLabel(t, page.numberSource);
  return source === null ? page.pageLabel : `${page.pageLabel} (${source.label})`;
};

const seriesDescription = (t: TFunction, page: PageDetails): string | null => {
  if (page.sessionId === null || page.sessionId === '') return null;
  return t('{{series}} · photo no. {{sequence}}', {
    series: page.sessionId.slice(0, SERIES_ID_LENGTH),
    sequence: page.sequence ?? NO_VALUE,
  });
};

const dimensionsDescription = (page: PageDetails): string | null => {
  return page.width > 0 && page.height > 0 ? `${page.width} × ${page.height} px` : null;
};

const readingRows = (
  t: TFunction,
  reading: PageReading,
  { numbers, dates }: DetailFormatting,
): (readonly [term: string, description: string | null])[] => {
  const { engine, durationSeconds, characterCount, illustrationCount, readAt } = reading;
  return [
    [t('Text recognition engine'), engine],
    [t('Text recognition time'), durationSeconds === null ? null : formatSeconds(t, numbers, durationSeconds)],
    [t('Recognized text'), characterCount === null ? null : formatCharacterCount(t, characterCount)],
    [t('Illustrations'), illustrationCount === null ? null : String(illustrationCount)],
    [t('Text read on'), readAt === null || readAt === '' ? null : formatDateTime(dates, readAt)],
  ];
};

export const detailRows = (t: TFunction, page: PageDetails, formatting: DetailFormatting): DetailRow[] => {
  const { dates } = formatting;
  const none = t('none', { context: 'page number' });
  const rows: (readonly [term: string, description: string | null])[] = [
    [t('Status'), pageStatusLabel(t, page.status).label],
    [t('Number'), numberDescription(t, page)],
    [t('Numbers read on the page'), page.detectedNumbers.length > 0 ? page.detectedNumbers.join(', ') : none],
    [t('Number given by the phone'), page.hintNumber === null ? null : String(page.hintNumber)],
    [t('Captured'), formatDateTime(dates, page.capturedAt)],
    [t('Received'), formatDateTime(dates, page.uploadedAt)],
    [t('Photo series'), seriesDescription(t, page)],
    [t('Rotation'), `${page.rotation}°`],
    [t('Dimensions'), dimensionsDescription(page)],
    ...(page.reading === null ? [] : readingRows(t, page.reading, formatting)),
  ];
  const textRows = rows.flatMap(([term, description]) =>
    description === null || description === '' ? [] : [{ term, description, isCode: false }],
  );
  return page.key === '' ? textRows : [...textRows, { term: t('File key'), description: page.key, isCode: true }];
};

export const numberHelp = (t: TFunction, page: PageDetails): string => {
  const source = numberSourceLabel(t, page.numberSource);
  if (source === null) {
    switch (page.placement) {
      case 'manual':
        return t('No known number: the page is at the place chosen with “Organize”.');
      case 'session':
        return t('No known number: the page is placed next to the pages photographed just before or just after it.');
      default:
        return t('No known number: the page is filed with the unnumbered pages, at the end of the document.');
    }
  }
  if (page.numberSource === 'manual') {
    return t('Typed by hand. {{clear}} goes back to the detected or inferred number.', {
      clear: quoted(t, t('Clear')),
    });
  }
  return `${source.description}.`;
};

export const scanDescription = (t: TFunction, page: PageDetails): string => {
  return t('Original scan, {{page}}', { page: pageTitle(t, page).toLowerCase() });
};
