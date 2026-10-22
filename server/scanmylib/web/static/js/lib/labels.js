/**
 * Labels (in the UI language) and visual tones for the API's enumerations.
 * Tones map to CSS modifiers: neutral, ok, info, warn, danger.
 */
import { t, tc } from './i18n.js';

const PAGE_STATUS = {
  queued: () => ({ label: t('Queued'), tone: 'warn' }),
  processing: () => ({ label: t('Reading…'), tone: 'info' }),
  done: () => ({ label: t('Text ready'), tone: 'ok' }),
  error: () => ({ label: tc('page status', 'Failed'), tone: 'danger' }),
};

const NUMBER_SOURCE = {
  manual: () => ({ label: t('manual'), description: t('Number typed by hand') }),
  detected: () => ({ label: t('detected'), description: t('Number detected on the page') }),
  hint: () => ({ label: t('hint'), description: t('Number given from the phone') }),
  inferred: () => ({
    label: t('inferred'),
    description: t('Number inferred from the neighboring pages (same photo series)'),
  }),
};

/** How a page of the reading order got its place; "number" (its page number) needs no badge. */
const PAGE_PLACEMENT = {
  manual: () => ({ label: t('moved'), description: t('Placed by hand with “Organize”: it keeps this place.') }),
  session: () => ({
    label: t('placed by session'),
    description: t('No number: placed next to the pages photographed just before or just after it.'),
  }),
  unplaced: () => ({
    label: t('to place'),
    description: t('No number, and no numbered page in its photo series: added at the end of the document.'),
  }),
};

const ENGINE_STATE = {
  idle: () => ({
    label: t('OCR idle'),
    tone: 'neutral',
    description: t('Engine stopped, graphics memory freed. It restarts on its own with the next page.'),
  }),
  starting: () => ({
    label: t('OCR starting'),
    tone: 'warn',
    description: t('Loading the model on the graphics card…'),
  }),
  ready: () => ({ label: t('OCR ready'), tone: 'ok', description: t('Engine loaded, ready to process pages.') }),
  stopping: () => ({ label: t('OCR stopping'), tone: 'warn', description: t('Freeing graphics memory…') }),
  error: () => ({ label: t('OCR error'), tone: 'danger', description: t('The engine could not start.') }),
  unreachable: () => ({
    label: t('OCR unreachable'),
    tone: 'danger',
    description: t('The OCR container is not responding.'),
  }),
};

const DOCUMENT_KIND = {
  book: () => t('Book'),
  document: () => t('Document'),
};

/** The entry of `map` for an API value, translated now; null for unknown values. */
function entry(map, key) {
  return typeof key === 'string' && Object.hasOwn(map, key) ? map[key]() : null;
}

export function pageStatus(status) {
  return entry(PAGE_STATUS, status) ?? { label: status ?? '—', tone: 'neutral' };
}

/** `null` when the page has no number. */
export function numberSource(source) {
  if (!source) return null;
  return entry(NUMBER_SOURCE, source) ?? { label: source, description: '' };
}

/** Badge of a page's placement, or `null` (placed by its number, or not in the document). */
export function pagePlacement(placement) {
  return entry(PAGE_PLACEMENT, placement);
}

export function engineState(state) {
  return (
    entry(ENGINE_STATE, state) ?? {
      label: t('OCR: {state}', { state: state ?? t('unknown') }),
      tone: 'neutral',
      description: '',
    }
  );
}

/** The kinds of document, `[value, label]`, in the order of the document form. */
export function documentKinds() {
  return Object.entries(DOCUMENT_KIND).map(([value, label]) => [value, label()]);
}

export function documentKind(kind) {
  return entry(DOCUMENT_KIND, kind) ?? kind ?? '';
}

/** Short label for grids: "p. 42", "p. xii", "p. 42–43", "No number". */
export function pageShortLabel(page) {
  return page.page_label ? t('p. {label}', { label: page.page_label }) : t('No number');
}

/** Title of the page screen: "Page 42", "Pages 42–43", "Page with no number". */
export function pageTitle(page) {
  if (!page.page_label) return t('Page with no number');
  return page.number_end === null || page.number_end === undefined
    ? t('Page {label}', { label: page.page_label })
    : t('Pages {label}', { label: page.page_label });
}
