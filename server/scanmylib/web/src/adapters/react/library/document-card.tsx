import type { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import type { DocumentSummary } from '../../../domain/document-summary.ts';
import type { DateFormatting, NumberFormatting } from '../../../domain/formatting.ts';
import { formatRelativeTime } from '../../i18next/formatted-text.ts';
import { documentPath } from '../shell/navigation.ts';
import { CoverageBar } from './coverage-bar.tsx';
import { DocumentCover } from './document-cover.tsx';
import { bylineText, coverageSummaryText, type TextStatusTone, textStatus } from './library-text.ts';
import { StatusChips } from './status-chips.tsx';

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
  const { coverage } = document;
  const status = textStatus(t, document.stats);
  const updated = t('Updated {{time}}', {
    time: formatRelativeTime(t, dates, document.updatedAt, nowMilliseconds),
  });
  return (
    <li className="doc-card">
      <Link className="doc-card-link" to={documentPath(document.id)}>
        <DocumentCover document={document} className="doc-cover" />
        <div className="doc-card-body">
          <div className="doc-card-heading">
            <h2 className="doc-card-title" title={document.title}>
              {document.title}
            </h2>
            <p className="doc-card-author">{bylineText(t, document)}</p>
          </div>
          <div className="doc-card-coverage">
            <CoverageBar coverage={coverage} />
            <p className="doc-card-coverage-text">{coverageSummaryText(t, formatting, coverage)}</p>
          </div>
          <p className={STATUS_CLASSES[status.tone]}>{status.text}</p>
          <div className="doc-card-footer">
            <StatusChips document={document} />
            <p className="doc-card-updated" title={updated}>
              {updated}
            </p>
          </div>
        </div>
      </Link>
    </li>
  );
};
