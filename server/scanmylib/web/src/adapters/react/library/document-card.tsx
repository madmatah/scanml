import type { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { type DocumentSummary, doneRatio } from '../../../domain/document-summary.ts';
import { type DateFormatting, wholePercent } from '../../../domain/formatting.ts';
import { formatRelativeTime } from '../../i18next/formatted-text.ts';
import { Icon } from '../shell/icon.tsx';
import { documentPath } from '../shell/navigation.ts';
import { versionedUrl } from '../shell/versioned-url.ts';
import { type ChipTone, coverageText, progressText, statusChips } from './library-text.ts';

const CHIP_CLASSES: Readonly<Record<ChipTone, string>> = {
  neutral: 'chip',
  info: 'chip chip-info',
  warn: 'chip chip-warn',
  danger: 'chip chip-danger',
};

export interface DocumentCardProps {
  readonly document: DocumentSummary;
  readonly dates: DateFormatting;
  readonly nowMilliseconds: number;
}

export const DocumentCard: FC<DocumentCardProps> = ({ document, dates, nowMilliseconds }) => {
  const { t } = useTranslation();
  const { coverThumbnailUrl } = document;
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
          <h2 className="doc-card-title">{document.title}</h2>
          {document.author !== '' && <p className="doc-card-author">{document.author}</p>}
          <p className="doc-card-progress">
            <span className="meter" aria-hidden="true">
              <span className="meter-fill" style={{ width: `${wholePercent(doneRatio(document.stats))}%` }} />
            </span>
            <span>{progressText(t, document.stats)}</span>
          </p>
          <p className="doc-card-coverage">{coverageText(t, document.coverage)}</p>
          {/* biome-ignore lint/a11y/noRedundantRoles: Safari drops the role of a list drawn without its markers. */}
          <ul className="chips" role="list">
            {statusChips(t, document).map(({ name, text, tone }) => (
              <li key={name} className={CHIP_CLASSES[tone]}>
                {text}
              </li>
            ))}
          </ul>
          <p className="doc-card-updated">
            {t('Updated {{time}}', { time: formatRelativeTime(t, dates, document.updatedAt, nowMilliseconds) })}
          </p>
        </div>
      </Link>
    </li>
  );
};
