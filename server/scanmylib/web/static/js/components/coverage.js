/**
 * Coverage of a document: which page numbers between the lowest and the
 * highest scanned one are present, and which are missing.
 */
import { h } from '../lib/dom.js';
import { formatPercent, formatRange, formatRanges } from '../lib/format.js';
import { t, tc, tNodes, tn } from '../lib/i18n.js';

/** Minimum distance between two axis labels, as a fraction of the bar width. */
const MIN_LABEL_SPACING = 0.09;

function rangeTitle([start, end], missing) {
  if (start === end) {
    return missing ? t('Page {page}: missing', { page: start }) : t('Page {page}: scanned', { page: start });
  }
  const range = formatRange([start, end]);
  return missing ? t('Pages {range}: missing', { range }) : t('Pages {range}: scanned', { range });
}

/**
 * Axis labels at the start of each segment, plus the last page number at the
 * right end; labels too close to the previous one are dropped.
 */
function axisLabels(segments, min, max) {
  if (min === max) return [{ value: min, position: 0 }];
  const span = max - min + 1;
  const labels = [];
  for (const { range } of segments) {
    const position = (range[0] - min) / span;
    const previous = labels.at(-1);
    if (!previous || position - previous.position >= MIN_LABEL_SPACING) labels.push({ value: range[0], position });
  }
  // The right end always shows the last page number.
  while (labels.length > 1 && 1 - labels.at(-1).position < MIN_LABEL_SPACING) labels.pop();
  labels.push({ value: max, position: 1, end: true });
  return labels;
}

export function renderCoverage(coverage) {
  const unnumbered = coverage?.unnumbered ?? 0;
  const unnumberedNote =
    unnumbered > 0 &&
    h('p', { class: 'coverage-note' }, `+ ${tn('{count} unnumbered page', '{count} unnumbered pages', unnumbered)}`);

  if (coverage?.min === null || coverage?.min === undefined || coverage?.max === null || coverage?.max === undefined) {
    return h(
      'div',
      { class: 'coverage' },
      h(
        'p',
        { class: 'muted' },
        t('No page number known yet: the coverage will appear once the PC has read numbered pages.'),
      ),
      unnumberedNote,
    );
  }

  const { min, max } = coverage;
  const ranges = coverage.ranges ?? [];
  const gaps = coverage.gaps ?? [];
  const span = max - min + 1;
  const scanned = ranges.reduce((total, [start, end]) => total + end - start + 1, 0);
  const segments = [
    ...ranges.map((range) => ({ range, missing: false })),
    ...gaps.map((range) => ({ range, missing: true })),
  ].sort((a, b) => a.range[0] - b.range[0]);

  const scannedLabel = coverage.label || formatRanges(ranges);
  const description = gaps.length
    ? t('Scanned pages: {scanned}. Missing pages: {missing}.', { scanned: scannedLabel, missing: formatRanges(gaps) })
    : t('All pages from {min} to {max} are scanned.', { min, max });

  const bar = h(
    'div',
    { class: 'coverage-bar', role: 'img', 'aria-label': description },
    segments.map(({ range, missing }) =>
      h('span', {
        class: ['coverage-segment', missing ? 'is-missing' : 'is-scanned'],
        style: { flexGrow: String(range[1] - range[0] + 1) },
        title: rangeTitle(range, missing),
      }),
    ),
  );

  const axis = h(
    'div',
    { class: 'coverage-axis', 'aria-hidden': 'true' },
    axisLabels(segments, min, max).map(({ value, position, end }) =>
      h(
        'span',
        {
          class: ['coverage-tick', position === 0 && 'is-first', end && 'is-last'],
          style: { left: `${position * 100}%` },
        },
        String(value),
      ),
    ),
  );

  return h(
    'div',
    { class: 'coverage' },
    h(
      'p',
      { class: 'coverage-headline' },
      tNodes('{fraction} pages between {min} and {max} ({percent})', {
        fraction: h('strong', {}, `${scanned} / ${span}`),
        min,
        max,
        percent: formatPercent(scanned / span),
      }),
    ),
    bar,
    axis,
    h(
      'dl',
      { class: 'coverage-details' },
      h(
        'div',
        {},
        h('dt', {}, h('span', { class: 'swatch is-scanned', 'aria-hidden': 'true' }), t('Scanned')),
        h('dd', {}, scannedLabel || '—'),
      ),
      h(
        'div',
        {},
        h('dt', {}, h('span', { class: 'swatch is-missing', 'aria-hidden': 'true' }), t('Missing')),
        h('dd', {}, gaps.length ? formatRanges(gaps) : tc('missing pages', 'none')),
      ),
    ),
    unnumberedNote,
  );
}
