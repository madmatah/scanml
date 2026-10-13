/**
 * Translation of the user interface, gettext style.
 *
 * The English text written in the source code is the reference, and the key
 * of its translations: `t('Library')` gives "Library" in English and the
 * entry of locales/fr.js in French. The language is the first of the
 * browser's preferred languages (navigator.languages) that the UI speaks: any
 * French locale ("fr", "fr-FR", "fr-CA"…) gives French, anything else
 * English. Dates and numbers are formatted by Intl for that locale
 * (lib/format.js).
 *
 * - t(message, values): `{name}` in the message is replaced by `values.name`.
 * - tc(context, message, values): for an English message that needs
 *   different translations depending on where it appears ("Done" for a
 *   button, or for a page status); its catalog key is "context|message".
 * - tn(singular, plural, count, values): the form for `count`, chosen by the
 *   plural rules of the language; `{count}` is the number formatted for the
 *   locale, unless `values.count` is given.
 * - tNodes(message, values): like t(), but values may be DOM nodes; returns
 *   the parts to append to an element (strings and nodes).
 *
 * Messages are always written as literals in these calls, so that
 * tests/i18n.test.js can check that the French catalog translates every one
 * of them, and nothing else.
 */
import FRENCH from '../locales/fr.js';

const CATALOGS = { fr: FRENCH };

/** Languages of the UI, with the locale used when the browser gives no region. */
const DEFAULT_LOCALES = { en: 'en-US', fr: 'fr-FR' };

const PLACEHOLDER = /\{(\w+)\}/g;

let state;

function validLocale(tag) {
  try {
    return Intl.getCanonicalLocales(tag)[0] ?? null;
  } catch {
    return null; // not a well-formed language tag
  }
}

/**
 * The UI language and the Intl locale for a list of preferred locales, most
 * wanted first: the first French or English one decides; English otherwise.
 */
export function negotiate(preferences) {
  for (const tag of preferences ?? []) {
    const language = String(tag).toLowerCase().split(/[-_]/)[0];
    if (Object.hasOwn(DEFAULT_LOCALES, language)) {
      // "fr" alone formats like "fr-FR"; a region given by the browser ("en-GB") is kept.
      const locale = String(tag).includes('-') ? validLocale(tag) : null;
      return { language, locale: locale ?? DEFAULT_LOCALES[language] };
    }
  }
  return { language: 'en', locale: DEFAULT_LOCALES.en };
}

/** Switches the language (the browser's preferences at startup; tests choose theirs). */
export function setLocale(preferences) {
  const { language, locale } = negotiate(preferences);
  state = {
    language,
    locale,
    catalog: CATALOGS[language] ?? null,
    plurals: new Intl.PluralRules(locale),
    numbers: new Intl.NumberFormat(locale),
  };
}

/** "en" or "fr". */
export function currentLanguage() {
  return state.language;
}

/** Locale for Intl: "en-US", "fr-FR", "en-GB"… */
export function currentLocale() {
  return state.locale;
}

function browserPreferences() {
  const { navigator } = globalThis;
  if (!navigator) return [];
  return navigator.languages?.length ? navigator.languages : [navigator.language].filter(Boolean);
}

setLocale(browserPreferences());

function lookup(key) {
  return state.catalog && Object.hasOwn(state.catalog, key) ? state.catalog[key] : undefined;
}

function interpolate(template, values) {
  if (!values) return template;
  return template.replace(PLACEHOLDER, (match, name) => (
    Object.hasOwn(values, name) ? String(values[name]) : match));
}

function translate(message, context) {
  const translated = lookup(context ? `${context}|${message}` : message);
  return typeof translated === 'string' ? translated : message;
}

export function t(message, values) {
  return interpolate(translate(message), values);
}

export function tc(context, message, values) {
  return interpolate(translate(message, context), values);
}

export function tn(singular, plural, count, values = {}) {
  const category = state.plurals.select(count);
  const forms = lookup(singular);
  let template;
  if (forms && typeof forms === 'object') template = forms[category] ?? forms.other;
  else template = category === 'one' ? singular : plural;
  return interpolate(template, { count: state.numbers.format(count), ...values });
}

export function tNodes(message, values = {}) {
  const parts = [];
  // split() with a capturing group alternates text and placeholder names.
  translate(message).split(PLACEHOLDER).forEach((part, index) => {
    let value = part;
    if (index % 2 === 1) value = Object.hasOwn(values, part) ? values[part] : `{${part}}`;
    if (value === null || value === undefined || value === '') return;
    if (typeof value === 'object') parts.push(value); // a DOM node
    else if (typeof parts.at(-1) === 'string') parts[parts.length - 1] += String(value);
    else parts.push(String(value));
  });
  return parts;
}

/**
 * Translates the static text of index.html: the text of the elements marked
 * `data-i18n`, and the attributes listed in `data-i18n-attr` (with the
 * context of `data-i18n-context`, if any). Sets <html lang>, and
 * `data-i18n-ready`, which shows that text (app.css hides it until then).
 */
export function localizeDocument(doc = document) {
  const root = doc.documentElement;
  root.lang = state.language;
  for (const element of doc.querySelectorAll('[data-i18n], [data-i18n-attr]')) {
    const context = element.dataset.i18nContext;
    if (element.hasAttribute('data-i18n')) element.textContent = translate(element.textContent.trim(), context);
    for (const name of (element.dataset.i18nAttr ?? '').split(/\s+/).filter(Boolean)) {
      const value = element.getAttribute(name);
      if (value) element.setAttribute(name, translate(value, context));
    }
  }
  root.dataset.i18nReady = '';
}
