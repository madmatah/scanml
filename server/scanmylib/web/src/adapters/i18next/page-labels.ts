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

export function pageShortLabel(t: TFunction, page: LabeledPage): string {
  return page.page_label ? t('p. {{label}}', { label: page.page_label }) : t('No number');
}

// A value that a newer api sends and this UI does not know yet is shown as it is.
export function pageStatusLabel(t: TFunction, status: string): PageStatusLabel {
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
}

export function numberSourceLabel(t: TFunction, source: string | null): DescribedLabel | null {
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
}

// A page placed by its number needs no badge, and neither does one outside the reading order.
export function pagePlacementLabel(t: TFunction, placement: string | null): DescribedLabel | null {
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
}
