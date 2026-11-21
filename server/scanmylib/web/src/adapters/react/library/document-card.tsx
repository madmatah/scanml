import type { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import type { DocumentSummary } from '../../../domain/document-summary.ts';
import type { DateFormatting, NumberFormatting } from '../../../domain/formatting.ts';
import { formatRelativeTime } from '../../i18next/formatted-text.ts';
import { coverageSegments, pageCount } from '../document/coverage-layout.ts';
import { Icon } from '../shell/icon.tsx';
import { documentPath } from '../shell/navigation.ts';
import { versionedUrl } from '../shell/versioned-url.ts';
import {
  bylineText,
  type ChipTone,
  coverageSummaryText,
  statusChips,
  type TextStatusTone,
  textStatus,
} from './library-text.ts';

const CHIP_CLASSES: Readonly<Record<ChipTone, string>> = {
  neutral: 'chip',
  info: 'chip chip-info',
  warn: 'chip chip-warn',
  danger: 'chip chip-danger',
};

const STATUS_CLASSES: Readonly<Record<TextStatusTone, string>> = {
  neutral: 'doc-card-status',
  info: 'doc-card-status is-info',
  ok: 'doc-card-status is-ok',
};

export interface DocumentCardProps {
  readonly document: DocumentSummary;
  readonly dates: DateFormatting;
  readonly formatting: NumberFormatting;
  readonly nowMilliseconds: number;
}

export const DocumentCard: FC<DocumentCardProps> = ({ document, dates, formatting, nowMilliseconds }) => {
  const { t } = useTranslation();
  const { coverThumbnailUrl, coverage } = document;
  const status = textStatus(t, document.stats);
  const updated = t('Updated {{time}}', {
    time: formatRelativeTime(t, dates, document.updatedAt, nowMilliseconds),
  });
  return (
    <li className="doc-card">
      <Link className="doc-card-link" to={documentPath(document.id)}>
        <div className="doc-cover">
          {coverThumbnailUrl === null ? (
            <span className="doc-cover-placeholder" aria-hidden="true">
              <Icon name="book" />
            </span>
          ) : (
            // The cover may change or be rotated: its thumbnail follows the document's version.
            <img src={versionedUrl(coverThumbnailUrl, document.updatedAt)} alt="" loading="lazy" decoding="async" />
          )}
        </div>
        <div className="doc-card-body">
          <div className="doc-card-heading">
            <h2 className="doc-card-title" title={document.title}>
              {document.title}
            </h2>
            <p className="doc-card-author">{bylineText(t, document)}</p>
          </div>
          <div className="doc-card-coverage">
            <span className="doc-card-coverage-bar" aria-hidden="true">
              {coverageSegments(coverage.ranges, coverage.gaps).map(({ range, isMissing }) => (
                <span
                  key={range[0]}
                  className={isMissing ? 'coverage-segment is-missing' : 'coverage-segment is-scanned'}
                  style={{ flexGrow: String(pageCount(range)) }}
                />
              ))}
            </span>
            <p className="doc-card-coverage-text">{coverageSummaryText(t, formatting, coverage)}</p>
          </div>
          <p className={STATUS_CLASSES[status.tone]}>{status.text}</p>
          <div className="doc-card-footer">
            {/* biome-ignore lint/a11y/noRedundantRoles: Safari drops the role of a list drawn without its markers. */}
            <ul className="chips" role="list">
              {statusChips(t, document).map(({ name, text, tone }) => (
                <li key={name} className={CHIP_CLASSES[tone]}>
                  {text}
                </li>
              ))}
            </ul>
            <p className="doc-card-updated" title={updated}>
              {updated}
            </p>
          </div>
        </div>
      </Link>
    </li>
  );
};
