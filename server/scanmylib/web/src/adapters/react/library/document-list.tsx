import type { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import type { DocumentSummary } from '../../../domain/document-summary.ts';
import type { DateFormatting, NumberFormatting } from '../../../domain/formatting.ts';
import { formatRelativeTime } from '../../i18next/formatted-text.ts';
import { documentPath } from '../shell/navigation.ts';
import { CoverageBar } from './coverage-bar.tsx';
import { DocumentCover } from './document-cover.tsx';
import { bylineText, coverageSummaryText, shortTextStatus, type TextStatusTone, textStatus } from './library-text.ts';
import { StatusChips } from './status-chips.tsx';

const STATUS_CLASSES: Readonly<Record<TextStatusTone, string>> = {
  neutral: 'doc-row-status',
  info: 'doc-row-status is-info',
  ok: 'doc-row-status is-ok',
};

interface DocumentRowProps {
  readonly document: DocumentSummary;
  readonly dates: DateFormatting;
  readonly formatting: NumberFormatting;
  readonly nowMilliseconds: number;
}

// Both forms of the status are rendered, since the stylesheet picks the layout: the table shows the long one, and the
// compact row, which has no room for it, the short one.
const DocumentRow: FC<DocumentRowProps> = ({ document, dates, formatting, nowMilliseconds }) => {
  const { t } = useTranslation();
  const { coverage } = document;
  const status = textStatus(t, document.stats);
  const shortStatus = shortTextStatus(t, document.stats);
  const updated = formatRelativeTime(t, dates, document.updatedAt, nowMilliseconds);
  return (
    <li className="doc-row">
      <Link className="doc-row-link" to={documentPath(document.id)}>
        <DocumentCover document={document} className="doc-row-cover" />
        <div className="doc-row-heading">
          <p className="doc-row-title" title={document.title}>
            {document.title}
          </p>
          <p className="doc-row-author">{bylineText(t, document)}</p>
        </div>
        <div className="doc-row-coverage">
          <CoverageBar coverage={coverage} />
          <p className="doc-row-coverage-text">{coverageSummaryText(t, formatting, coverage)}</p>
        </div>
        <div className="doc-row-text">
          <p className={STATUS_CLASSES[status.tone]}>
            <span className="doc-row-status-long">{status.text}</span>
            <span className="doc-row-status-short">{shortStatus.text}</span>
          </p>
          <StatusChips document={document} />
        </div>
        <p className="doc-row-updated" title={updated}>
          {updated}
        </p>
      </Link>
    </li>
  );
};

export interface DocumentListProps {
  readonly documents: readonly DocumentSummary[];
  readonly dates: DateFormatting;
  readonly formatting: NumberFormatting;
  readonly nowMilliseconds: number;
}

export const DocumentList: FC<DocumentListProps> = ({ documents, dates, formatting, nowMilliseconds }) => {
  const { t } = useTranslation();
  return (
    <div className="doc-list">
      {/* The rows say what each column holds in their own words: the titles only guide the eye. */}
      <div className="doc-list-header" aria-hidden="true">
        <span className="doc-list-header-document">{t('Document')}</span>
        <span>{t('Pages scanned')}</span>
        <span>{t('Text', { context: 'column' })}</span>
        <span>{t('Updated', { context: 'column' })}</span>
      </div>
      {/* biome-ignore lint/a11y/noRedundantRoles: Safari drops the role of a list drawn without its markers. */}
      <ul className="doc-list-rows" role="list">
        {documents.map((document) => (
          <DocumentRow
            key={document.id}
            document={document}
            dates={dates}
            formatting={formatting}
            nowMilliseconds={nowMilliseconds}
          />
        ))}
      </ul>
    </div>
  );
};
