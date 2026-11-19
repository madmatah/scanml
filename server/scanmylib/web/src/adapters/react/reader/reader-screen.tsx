import { type FC, Fragment, type ReactNode, useId } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { isNotFound } from '../../../application/document-loader.ts';
import type { DocumentStore } from '../../../application/document-store.ts';
import { type DocumentWithPages, type PageSummary, waitingPageCount } from '../../../domain/document-details.ts';
import type { LabeledPage } from '../../i18next/page-labels.ts';
import { outlineEntryLabel } from '../../i18next/reading-text.ts';
import type { FormulaTypesetter } from '../sanitized-html/use-sanitized-html.ts';
import { EmptyState } from '../shell/empty-state.tsx';
import { errorMessage } from '../shell/error-message.ts';
import { ErrorState } from '../shell/error-state.tsx';
import { Icon } from '../shell/icon.tsx';
import { LoadingState } from '../shell/loading-state.tsx';
import { documentPath, PATHS } from '../shell/navigation.ts';
import type { Toasts } from '../shell/toasts.ts';
import { useRouteId } from '../shell/use-route-id.ts';
import type { GroupedOutlineEntry, OutlineGroup } from './outline-groups.ts';
import { emptyReadingMessage, waitingPagesNotice } from './reader-text.ts';
import { useReaderScreen } from './use-reader-screen.ts';
import { useReaderText } from './use-reader-text.ts';

export interface ReaderScreenProps {
  readonly documents: DocumentStore;
  readonly toasts: Toasts;
  readonly typesetFormulas: FormulaTypesetter;
}

// Each document has a reader of its own, which starts afresh.
export const ReaderScreen: FC<ReaderScreenProps> = (props) => {
  const documentId = useRouteId('documentId');
  if (documentId === null) return null;
  return <ReaderView key={documentId} documentId={documentId} {...props} />;
};

interface ReaderViewProps extends ReaderScreenProps {
  readonly documentId: string;
}

const ReaderView: FC<ReaderViewProps> = ({ documentId, documents, toasts, typesetFormulas }) => {
  const { t } = useTranslation();
  const { load, outline, pageCount, readerAddress, markdownUrl, onReload } = useReaderScreen(documentId, {
    documents,
    toasts,
  });

  if (load.phase === 'loading') {
    return (
      <section className="view reader-view">
        <LoadingState message={t('Loading the document…')} />
      </section>
    );
  }
  if (load.phase === 'failed') {
    const isMissing = isNotFound(load.failure);
    return (
      <section className="view reader-view">
        <ErrorState
          title={isMissing ? t('Document not found') : t('Could not load')}
          message={isMissing ? t('This document does not exist or has been deleted.') : errorMessage(t, load.failure)}
          {...(isMissing ? {} : { onRetry: onReload })}
          actions={
            isMissing ? (
              <Link className="btn" to={PATHS.home}>
                {t('Back to the library')}
              </Link>
            ) : (
              <BackToDocument documentId={documentId} />
            )
          }
        />
      </section>
    );
  }
  return (
    <ReaderDocument
      document={load.document}
      sanitizedHtml={load.sanitizedHtml}
      returnsToPageRead={load.returnsToPageRead}
      outline={outline}
      pageCount={pageCount}
      readerAddress={readerAddress}
      markdownUrl={markdownUrl}
      typesetFormulas={typesetFormulas}
      onReload={onReload}
    />
  );
};

const BackToDocument: FC<{ readonly documentId: string }> = ({ documentId }) => {
  const { t } = useTranslation();
  return (
    <Link className="btn" to={documentPath(documentId)}>
      <Icon name="chevron-left" />
      {t('Back to the document')}
    </Link>
  );
};

const ReloadButton: FC<{ readonly onReload: () => void }> = ({ onReload }) => {
  const { t } = useTranslation();
  return (
    <button type="button" className="btn btn-small" onClick={onReload}>
      <Icon name="refresh" />
      {t('Refresh')}
    </button>
  );
};

interface ReaderDocumentProps {
  readonly document: DocumentWithPages;
  readonly sanitizedHtml: string;
  readonly returnsToPageRead: boolean;
  readonly outline: readonly OutlineGroup<LabeledPage>[];
  readonly pageCount: number;
  readonly readerAddress: string;
  readonly markdownUrl: string;
  readonly typesetFormulas: FormulaTypesetter;
  readonly onReload: () => void;
}

const ReaderDocument: FC<ReaderDocumentProps> = ({
  document: shownDocument,
  sanitizedHtml,
  returnsToPageRead,
  outline,
  pageCount,
  readerAddress,
  markdownUrl,
  typesetFormulas,
  onReload,
}) => {
  const { t } = useTranslation();
  const titleId = useId();
  const waitingCount = waitingPageCount(shownDocument.stats);

  const breadcrumb = (
    <nav className="breadcrumb" aria-label={t('Breadcrumb')}>
      <Link to={PATHS.home}>{t('Library')}</Link>
      <span className="breadcrumb-separator" aria-hidden="true">
        ›
      </span>
      <Link to={documentPath(shownDocument.id)}>{shownDocument.title}</Link>
      <span className="breadcrumb-separator" aria-hidden="true">
        ›
      </span>
      <span aria-current="page">{t('Reading')}</span>
    </nav>
  );
  const header = (
    <header className="doc-header reader-header">
      <div className="view-heading">
        <h1 id={titleId}>{shownDocument.title}</h1>
        <p className="doc-author" hidden={!shownDocument.author}>
          {shownDocument.author}
        </p>
      </div>
      <div className="view-actions">
        <a className="btn" href={markdownUrl} download={`${shownDocument.slug}.md`}>
          <Icon name="download" />
          {t('Download document.md')}
        </a>
      </div>
    </header>
  );

  if (pageCount === 0) {
    return (
      <section className="view reader-view">
        {breadcrumb}
        {header}
        <EmptyState
          iconName="book"
          title={t('Nothing to read yet')}
          message={emptyReadingMessage(t, shownDocument.stats)}
          actions={
            <>
              {waitingCount > 0 && <ReloadButton onReload={onReload} />}
              <BackToDocument documentId={shownDocument.id} />
            </>
          }
        />
      </section>
    );
  }
  return (
    <ReadingText
      outline={outline}
      pageCount={pageCount}
      pages={shownDocument.pages}
      sanitizedHtml={sanitizedHtml}
      returnsToPageRead={returnsToPageRead}
      readerAddress={readerAddress}
      titleId={titleId}
      typesetFormulas={typesetFormulas}
    >
      {breadcrumb}
      {header}
      <div className="notice reader-notice" role="status" hidden={waitingCount === 0}>
        {waitingCount > 0 && (
          <>
            <p>{waitingPagesNotice(t, waitingCount)}</p>
            <ReloadButton onReload={onReload} />
          </>
        )}
      </div>
    </ReadingText>
  );
};

interface ReadingTextProps {
  readonly children: ReactNode;
  readonly outline: readonly OutlineGroup<LabeledPage>[];
  readonly pageCount: number;
  readonly pages: readonly PageSummary[];
  readonly sanitizedHtml: string;
  readonly returnsToPageRead: boolean;
  readonly readerAddress: string;
  readonly titleId: string;
  readonly typesetFormulas: FormulaTypesetter;
}

// The screen's element is rendered here, with the "Page" bar and the text, so that all three exist when the text is
// placed and the tracker starts.
const ReadingText: FC<ReadingTextProps> = ({
  children,
  outline,
  pageCount,
  pages,
  sanitizedHtml,
  returnsToPageRead,
  readerAddress,
  titleId,
  typesetFormulas,
}) => {
  const { t } = useTranslation();
  const selectId = useId();
  const { view, toolbar, text, currentIndex, onGoToPage } = useReaderText(sanitizedHtml, {
    pages,
    returnsToPageRead,
    readerAddress,
    typesetFormulas,
  });

  return (
    <section ref={view} className="view reader-view">
      {children}
      <div ref={toolbar} className="reader-toolbar">
        <label className="reader-select-label" htmlFor={selectId}>
          {t('Page')}
        </label>
        <select
          id={selectId}
          className="input reader-select"
          value={String(currentIndex)}
          onChange={(event) => onGoToPage(Number(event.target.value))}
        >
          {outline.map((group) =>
            group.label === null ? (
              <Fragment key="ungrouped">
                {group.entries.map((entry) => (
                  <OutlineOption key={optionKey(entry)} entry={entry} />
                ))}
              </Fragment>
            ) : (
              <optgroup key={`group-${group.label}`} label={group.label}>
                {group.entries.map((entry) => (
                  <OutlineOption key={optionKey(entry)} entry={entry} />
                ))}
              </optgroup>
            ),
          )}
        </select>
        <span className="reader-position">{currentIndex < 0 ? '' : `${currentIndex + 1} / ${pageCount}`}</span>
      </div>
      <article ref={text} className="ocr-render reader-text" aria-labelledby={titleId} />
    </section>
  );
};

const optionKey = (entry: GroupedOutlineEntry<LabeledPage>): string => {
  return entry.type === 'page' ? `page-${entry.index}` : `gap-${entry.label}`;
};

const OutlineOption: FC<{ readonly entry: GroupedOutlineEntry<LabeledPage> }> = ({ entry }) => {
  const { t } = useTranslation();
  if (entry.type === 'gap') return <option disabled>{outlineEntryLabel(t, entry)}</option>;
  return <option value={String(entry.index)}>{outlineEntryLabel(t, entry)}</option>;
};
