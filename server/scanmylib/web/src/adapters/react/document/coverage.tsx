import { Trans, useTranslation } from 'react-i18next';

import { formatPageRanges, type PageCoverage } from '../../../domain/document-summary.ts';
import type { NumberFormatting } from '../../../domain/formatting.ts';
import { formatPercent } from '../../i18next/formatted-text.ts';
import { axisLabels, coverageSegments, pageCount, scannedPageCount } from './coverage-layout.ts';
import { coverageDescription, coverageRangeTitle, missingPagesText, unnumberedPagesNote } from './document-text.ts';

const NO_RANGE = '—';

export interface CoverageProps {
  readonly coverage: PageCoverage;
  readonly formatting: NumberFormatting;
}

export function Coverage({ coverage, formatting }: CoverageProps) {
  const { t } = useTranslation();
  const { lowestNumber, highestNumber, ranges, gaps, unnumberedCount } = coverage;
  const unnumberedNote = unnumberedCount > 0 && (
    <p className="coverage-note">{unnumberedPagesNote(t, unnumberedCount)}</p>
  );

  if (lowestNumber === null || highestNumber === null) {
    return (
      <div className="coverage">
        <p className="muted">
          {t('No page number known yet: the coverage will appear once the PC has read numbered pages.')}
        </p>
        {unnumberedNote}
      </div>
    );
  }

  const span = pageCount([lowestNumber, highestNumber]);
  const scanned = scannedPageCount(ranges);
  const segments = coverageSegments(ranges, gaps);
  const scannedLabel = coverage.label === '' ? formatPageRanges(ranges) : coverage.label;

  return (
    <div className="coverage">
      <p className="coverage-headline">
        <Trans
          t={t}
          i18nKey="<fraction>{{fraction}}</fraction> pages between {{lowest}} and {{highest}} ({{percent}})"
          values={{
            fraction: `${scanned} / ${span}`,
            lowest: lowestNumber,
            highest: highestNumber,
            percent: formatPercent(t, formatting, scanned / span),
          }}
          components={{ fraction: <strong /> }}
        />
      </p>
      <div
        className="coverage-bar"
        role="img"
        aria-label={coverageDescription(t, scannedLabel, gaps, lowestNumber, highestNumber)}
      >
        {segments.map(({ range, isMissing }) => (
          <span
            key={range[0]}
            className={isMissing ? 'coverage-segment is-missing' : 'coverage-segment is-scanned'}
            style={{ flexGrow: String(pageCount(range)) }}
            title={coverageRangeTitle(t, range, isMissing)}
          />
        ))}
      </div>
      <div className="coverage-axis" aria-hidden="true">
        {axisLabels(segments, lowestNumber, highestNumber).map(({ pageNumber, positionRatio, isLast }) => (
          <span
            key={isLast ? 'last' : pageNumber}
            className={axisLabelClass(positionRatio, isLast)}
            style={{ left: `${positionRatio * 100}%` }}
          >
            {String(pageNumber)}
          </span>
        ))}
      </div>
      <dl className="coverage-details">
        <div>
          <dt>
            <span className="swatch is-scanned" aria-hidden="true" />
            {t('Scanned')}
          </dt>
          <dd>{scannedLabel === '' ? NO_RANGE : scannedLabel}</dd>
        </div>
        <div>
          <dt>
            <span className="swatch is-missing" aria-hidden="true" />
            {t('Not scanned yet')}
          </dt>
          <dd>{missingPagesText(t, gaps)}</dd>
        </div>
      </dl>
      {unnumberedNote}
    </div>
  );
}

function axisLabelClass(positionRatio: number, isLast: boolean): string {
  if (isLast) return 'coverage-tick is-last';
  return positionRatio === 0 ? 'coverage-tick is-first' : 'coverage-tick';
}
