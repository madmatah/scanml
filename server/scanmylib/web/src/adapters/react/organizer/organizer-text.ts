import type { TFunction } from 'i18next';
import type { OrganizerEvent } from '../../../application/organizer-store.ts';
import type { PageSummary } from '../../../domain/document-details.ts';
import type { PageId, ReadingOrder, Side } from '../../../domain/reading-order.ts';
import { pageShortLabel, pageTitle } from '../../i18next/page-labels.ts';
import { errorMessage } from '../shell/error-message.ts';
import type { ToastTone } from '../shell/toasts.ts';

export interface OrganizerNotice {
  readonly message: string;
  readonly tone: ToastTone;
}

export interface MoveChoice {
  readonly pageId: PageId;
  readonly label: string;
  readonly name: string;
}

type NamedPage = Pick<PageSummary, 'pageLabel'>;

export const conflictText = (t: TFunction): string => {
  return t('The list of pages changed: try again.');
};

// Unnumbered pages all sound alike to a screen reader: their place in the reading order tells them apart.
export const pageName = (t: TFunction, page: NamedPage, index: number): string => {
  const position = index + 1;
  return page.pageLabel
    ? t('the page at position {{position}} (p. {{label}})', { position, label: page.pageLabel })
    : t('the page at position {{position}} (no number)', { position });
};

export const selectionStatusText = (t: TFunction, selectedCount: number, total: number): string => {
  if (selectedCount === 0) return t('No page selected');
  return t('{{count, number}} page selected out of {{total}}', {
    count: selectedCount,
    total,
    defaultValue_one: '{{count, number}} page selected out of {{total}}',
    defaultValue_other: '{{count, number}} pages selected out of {{total}}',
  });
};

export const spanLongText = (t: TFunction, spanCount: number): string => {
  return t('Select the range ({{count, number}} page)', {
    count: spanCount,
    defaultValue_one: 'Select the range ({{count, number}} page)',
    defaultValue_other: 'Select the range ({{count, number}} pages)',
  });
};

export const spanShortText = (t: TFunction, spanCount: number): string => {
  return t('Range ({{pageCount}})', { pageCount: spanCount });
};

export const placedHeadingText = (t: TFunction, pageCount: number): string => {
  return t('Reading order ({{pageCount}})', { pageCount });
};

export const placedHintText = (t: TFunction, pageCount: number, hasPlacedPages: boolean): string => {
  if (pageCount === 0) return t('No page is in the document yet.');
  return hasPlacedPages ? t('The order of document.md.') : t('No numbered page: capture order.');
};

export const unplacedHeadingText = (t: TFunction, pageCount: number): string => {
  return t('Unnumbered pages ({{pageCount}})', { pageCount });
};

export const outsideText = (t: TFunction, outsideCount: number): string => {
  return t(
    '{{count}} page is outside the document (waiting to be read, couldn’t be read, excluded or duplicate): it is not affected.',
    {
      count: outsideCount,
      defaultValue_one:
        '{{count}} page is outside the document (waiting to be read, couldn’t be read, excluded or duplicate): it is not affected.',
      defaultValue_other:
        '{{count}} pages are outside the document (waiting to be read, couldn’t be read, excluded or duplicates): they are not affected.',
    },
  );
};

export const moveText = (
  t: TFunction,
  pages: ReadonlyMap<PageId, PageSummary>,
  order: ReadingOrder,
  moved: readonly PageId[],
): string => {
  const positions = moved.map((pageId) => order.indexOf(pageId) + 1);
  const [first] = moved;
  const page = first === undefined ? undefined : pages.get(first);
  if (moved.length === 1 && page !== undefined) {
    return t('{{page}}: position {{position}} of {{total}}.', {
      page: pageTitle(t, page),
      position: positions[0],
      total: order.length,
    });
  }
  return t('{{pageCount}} pages moved: positions {{first}} to {{last}} of {{total}}.', {
    pageCount: moved.length,
    first: positions[0],
    last: positions.at(-1),
    total: order.length,
  });
};

export const organizerNotice = (t: TFunction, event: OrganizerEvent): OrganizerNotice => {
  switch (event.kind) {
    case 'conflict':
      return { message: conflictText(t), tone: 'error' };
    case 'save-failed':
      return { message: errorMessage(t, event.failure, t('The new order could not be saved.')), tone: 'error' };
    case 'reset-done':
      return { message: t('Automatic order restored.'), tone: 'success' };
    case 'reset-failed':
      return {
        message: errorMessage(t, event.failure, t('The automatic order could not be restored.')),
        tone: 'error',
      };
  }
};

export const moveChoices = (
  t: TFunction,
  pages: ReadonlyMap<PageId, PageSummary>,
  order: ReadingOrder,
  moving: readonly PageId[],
): MoveChoice[] => {
  const isMoving = new Set(moving);
  return order.flatMap((pageId, index) => {
    const page = pages.get(pageId);
    if (page === undefined || isMoving.has(pageId)) return [];
    const label = `${index + 1} · ${pageShortLabel(t, { page_label: page.pageLabel })}`;
    return [{ pageId, label, name: pageName(t, page, index) }];
  });
};

export const selectedPagesText = (t: TFunction, count: number): string => {
  if (count === 1) return t('1 page selected.');
  const selected = t('{{count, number}} selected page', {
    count,
    defaultValue_one: '{{count, number}} selected page',
    defaultValue_other: '{{count, number}} selected pages',
  });
  return t('{{selected}}, in their current order.', { selected });
};

export const moveSummaryText = (t: TFunction, count: number, side: Side, page: string): string => {
  if (count > 1) {
    return side === 'after'
      ? t('The {{pageCount}} pages will go after {{page}}.', { pageCount: count, page })
      : t('The {{pageCount}} pages will go before {{page}}.', { pageCount: count, page });
  }
  return side === 'after'
    ? t('The page will go after {{page}}.', { page })
    : t('The page will go before {{page}}.', { page });
};
