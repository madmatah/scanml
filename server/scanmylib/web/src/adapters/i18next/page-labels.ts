import type { TFunction } from 'i18next';

export interface LabeledPage {
  readonly page_label: string | null;
}

export type LabelTone = 'neutral' | 'ok' | 'info' | 'warn' | 'danger';

export interface PageStatusLabel {
  readonly label: string;
  readonly tone: LabelTone;
}

export interface DescribedLabel {
  readonly label: string;
  readonly description: string;
}

export const pageShortLabel = (t: TFunction, page: LabeledPage): string => {
  return page.page_label ? t('p. {{label}}', { label: page.page_label }) : t('No number');
};

export interface TitledPage {
  readonly pageLabel: string | null;
  readonly numberEnd: number | null;
}

export const pageTitle = (t: TFunction, page: TitledPage): string => {
  if (!page.pageLabel) return t('Page with no number');
  return page.numberEnd === null
    ? t('Page {{label}}', { label: page.pageLabel })
    : t('Pages {{label}}', { label: page.pageLabel });
};

export const pageStatusLabel = (t: TFunction, status: string): PageStatusLabel => {
  switch (status) {
    case 'queued':
      return { label: t('Queued'), tone: 'warn' };
    case 'processing':
      return { label: t('Reading…'), tone: 'info' };
    case 'done':
      return { label: t('Text ready', { context: 'page status' }), tone: 'ok' };
    case 'error':
      return { label: t('Failed', { context: 'page status' }), tone: 'danger' };
    default:
      return { label: status, tone: 'neutral' };
  }
};

export const numberSourceLabel = (t: TFunction, source: string | null): DescribedLabel | null => {
  switch (source) {
    case null:
      return null;
    case 'manual':
      return { label: t('manual'), description: t('Number typed by hand') };
    case 'detected':
      return { label: t('detected'), description: t('Number detected on the page') };
    case 'hint':
      return { label: t('hint'), description: t('Number given from the phone') };
    case 'inferred':
      return {
        label: t('inferred'),
        description: t('Number inferred from the neighboring pages (same photo series)'),
      };
    default:
      return { label: source, description: '' };
  }
};

export const pagePlacementLabel = (t: TFunction, placement: string | null): DescribedLabel | null => {
  switch (placement) {
    case 'manual':
      return { label: t('moved'), description: t('Placed by hand with “Organize”: it keeps this place.') };
    case 'session':
      return {
        label: t('placed by session'),
        description: t('No number: placed next to the pages photographed just before or just after it.'),
      };
    case 'unplaced':
      return {
        label: t('to place'),
        description: t('No number, and no numbered page in its photo series: added at the end of the document.'),
      };
    default:
      return null;
  }
};
