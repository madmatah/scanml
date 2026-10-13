/** Dates, numbers, sizes and page ranges, formatted for the UI language (lib/i18n.js). */
import { currentLocale, t } from './i18n.js';

const formatters = new Map();

/** An Intl formatter for the current locale, created once per locale and kind. */
function formatter(kind, create) {
  const key = `${kind}/${currentLocale()}`;
  if (!formatters.has(key)) formatters.set(key, create(currentLocale()));
  return formatters.get(key);
}

const dateTimeFormat = () => formatter('date-time',
  (locale) => new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }));
const relativeFormat = () => formatter('relative',
  (locale) => new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }));
const integerFormat = () => formatter('integer', (locale) => new Intl.NumberFormat(locale));
const decimalFormat = () => formatter('decimal',
  (locale) => new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }));

function parseDate(value) {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "Oct 12, 2026, 8:15 PM" */
export function formatDateTime(value) {
  const date = parseDate(value);
  return date ? dateTimeFormat().format(date) : '—';
}

/** Units used by formatRelative, each with the number of them in the next unit. */
const RELATIVE_UNITS = [['second', 60], ['minute', 60], ['hour', 24], ['day', 7]];

/** "just now", "5 minutes ago", "yesterday"… then an absolute date after a week. */
export function formatRelative(value, now = Date.now()) {
  const date = parseDate(value);
  if (!date) return '—';
  let amount = (date.getTime() - now) / 1000;
  if (Math.abs(amount) < 45) return t('just now');
  for (const [unit, size] of RELATIVE_UNITS) {
    if (Math.abs(amount) < size) return relativeFormat().format(Math.round(amount), unit);
    amount /= size;
  }
  return dateTimeFormat().format(date);
}

/** "1,234" */
export function formatNumber(value) {
  return integerFormat().format(value);
}

/** "3.2" (at most one decimal) */
export function formatDecimal(value) {
  return decimalFormat().format(value);
}

/** "3.2 MB" */
export function formatBytes(bytes) {
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < 3) {
    value /= 1024;
    unit += 1;
  }
  const size = unit === 0 ? formatNumber(value) : formatDecimal(value);
  switch (unit) {
    case 0: return t('{size} B', { size });
    case 1: return t('{size} KB', { size });
    case 2: return t('{size} MB', { size });
    default: return t('{size} GB', { size });
  }
}

/** "2.3 s" */
export function formatSeconds(seconds) {
  return seconds === null || seconds === undefined ? '—' : t('{seconds} s', { seconds: formatDecimal(seconds) });
}

/** "47%" */
export function formatPercent(ratio) {
  return t('{percent}%', { percent: formatNumber(Math.round(ratio * 100)) });
}

/** [12, 12] → "12", [13, 44] → "13–44" */
export function formatRange([start, end]) {
  return start === end ? String(start) : `${start}–${end}`;
}

/** [[1, 12], [45, 60]] → "1–12, 45–60" */
export function formatRanges(ranges) {
  return ranges.map(formatRange).join(', ');
}

/** Quotation marks of the UI language: “text” */
export function quoted(text) {
  return t('“{text}”', { text });
}

/** ISO-8601 local time with its UTC offset: "2026-10-12T20:15:30+02:00". */
export function toLocalIsoString(date) {
  const pad = (number) => String(number).padStart(2, '0');
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? '+' : '-';
  const offsetText = `${sign}${pad(Math.floor(Math.abs(offset) / 60))}:${pad(Math.abs(offset) % 60)}`;
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}${offsetText}`;
}
