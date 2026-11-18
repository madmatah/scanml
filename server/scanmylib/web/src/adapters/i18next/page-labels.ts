import type { TFunction } from 'i18next';

export interface LabeledPage {
  readonly page_label: string | null;
}

export function pageShortLabel(t: TFunction, page: LabeledPage): string {
  return page.page_label ? t('p. {{label}}', { label: page.page_label }) : t('No number');
}
