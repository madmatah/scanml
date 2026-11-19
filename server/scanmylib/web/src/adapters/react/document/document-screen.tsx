import { type FC, type ReactNode, type RefObject, useId } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import type { Clipboard } from '../../../application/clipboard.ts';
import { isNotFound } from '../../../application/document-loader.ts';
import type { DocumentStore } from '../../../application/document-store.ts';
import type { EngineStatus } from '../../../application/engine-status.ts';
import type { Scheduler } from '../../../application/scheduler.ts';
import type { UploadQueue } from '../../../application/upload-queue.ts';
import type { UuidSource } from '../../../application/uuid-source.ts';
import { canOrganize, type DocumentWithPages } from '../../../domain/document-details.ts';
import type { NumberFormatting } from '../../../domain/formatting.ts';
import { documentKindLabel } from '../../i18next/document-labels.ts';
import { quoted } from '../../i18next/formatted-text.ts';
import { ConfirmDialog } from '../dialogs/confirm-dialog.tsx';
import { DocumentDialog } from '../dialogs/document-dialog.tsx';
import { PageOrganizer } from '../organizer/page-organizer.tsx';
import { EmptyState } from '../shell/empty-state.tsx';
import { errorMessage } from '../shell/error-message.ts';
import { ErrorState } from '../shell/error-state.tsx';
import { Icon } from '../shell/icon.tsx';
import { LoadingState } from '../shell/loading-state.tsx';
import { PATHS, readerPath } from '../shell/navigation.ts';
import type { Toasts } from '../shell/toasts.ts';
import { useRouteId } from '../shell/use-route-id.ts';
import { Uploader } from '../uploads/uploader.tsx';
import { Coverage } from './coverage.tsx';
import { type StatTone, statTiles } from './document-text.ts';
import { PageGrid } from './page-grid.tsx';
import { useDocumentScreen } from './use-document-screen.ts';

export interface DocumentScreenProps {
  readonly store: DocumentStore;
  readonly engineStatus: EngineStatus;
  readonly scheduler: Scheduler;
  readonly toasts: Toasts;
  readonly clipboard: Clipboard;
  readonly formatting: NumberFormatting;
  readonly uploads: UploadQueue<File>;
  readonly uuids: UuidSource;
}

// A file name, the same in every language.
const MARKDOWN_FILE_NAME = 'document.md';

// Each document has a screen of its own, so that going from one to another starts the next one afresh.
export const DocumentScreen: FC<DocumentScreenProps> = (props) => {
  const documentId = useRouteId('documentId');
  if (documentId === null) return null;
  return <DocumentView key={documentId} documentId={documentId} {...props} />;
};

interface DocumentViewProps extends DocumentScreenProps {
  readonly documentId: string;
}

const DocumentView: FC<DocumentViewProps> = ({
  documentId,
  store,
  engineStatus,
  scheduler,
  toasts,
  clipboard,
  formatting,
  uploads,
  uuids,
}) => {
  const { t } = useTranslation();
  const {
    load,
    openDialog,
    isOrganizing,
    includesScans,
    markdownUrl,
    archiveUrl,
    heading,
    organizeButton,
    onEdit,
    onDelete,
    onSaveDetails,
    onEditClosed,
    onDeleteClosed,
    onOrganize,
    onSaveOrder,
    onResetOrder,
    onReload,
    onDoneOrganizing,
    onIncludesScansChange,
    onCopyFolder,
  } = useDocumentScreen(documentId, { store, engineStatus, scheduler, toasts, clipboard, uploads });

  if (load.phase === 'loading') {
    return (
      <section className="view document-view">
        <LoadingState />
      </section>
    );
  }
  if (load.phase === 'failed') {
    const isMissing = isNotFound(load.failure);
    return (
      <section className="view document-view">
        <ErrorState
          title={isMissing ? t('Document not found') : t('Could not load')}
          message={isMissing ? t('This document does not exist or has been deleted.') : errorMessage(t, load.failure)}
          {...(isMissing ? {} : { onRetry: onReload })}
          actions={
            <Link className="btn" to={PATHS.home}>
              {t('Back to the library')}
            </Link>
          }
        />
      </section>
    );
  }

  const shown = load.document;
  return (
    <section className="view document-view">
      <nav className="breadcrumb" aria-label={t('Breadcrumb')}>
        <Link to={PATHS.home}>
          <Icon name="chevron-left" />
          {t('Library')}
        </Link>
      </nav>
      <header className="doc-header">
        <div className="view-heading">
          <h1 ref={heading} tabIndex={-1}>
            {shown.title}
          </h1>
          <p className="doc-author" hidden={shown.author === ''}>
            {shown.author}
          </p>
          {/* biome-ignore lint/a11y/noRedundantRoles: Safari drops the role of a list drawn without its markers. */}
          <ul className="chips doc-meta" role="list">
            <li className="chip">{documentKindLabel(t, shown.kind)}</li>
            {shown.unwarp && <li className="chip chip-accent">{t('Curved pages flattened')}</li>}
          </ul>
          <p className="doc-notes" hidden={shown.notes === ''}>
            {shown.notes}
          </p>
        </div>
        <div className="view-actions">
          <Link className="btn btn-primary" to={readerPath(documentId)}>
            <Icon name="book" />
            {t('Read document')}
          </Link>
          <button type="button" className="btn" onClick={onEdit}>
            <Icon name="edit" />
            {t('Edit')}
          </button>
          <button type="button" className="btn btn-danger" onClick={onDelete}>
            <Icon name="trash" />
            {t('Delete')}
          </button>
        </div>
      </header>
      <DocumentOverview
        document={shown}
        markdownUrl={markdownUrl}
        archiveUrl={archiveUrl}
        includesScans={includesScans}
        formatting={formatting}
        uploads={uploads}
        uuids={uuids}
        onIncludesScansChange={onIncludesScansChange}
        onCopyFolder={onCopyFolder}
      />
      <PagesSection
        document={shown}
        organizeButton={organizeButton}
        onOrganize={isOrganizing ? null : onOrganize}
        organizer={
          isOrganizing && (
            <PageOrganizer
              document={shown}
              save={onSaveOrder}
              reset={onResetOrder}
              reload={onReload}
              toasts={toasts}
              onDone={onDoneOrganizing}
            />
          )
        }
      />
      {openDialog === 'edit' && (
        <DocumentDialog
          heading={t('Edit document')}
          submitLabel={t('Save')}
          initial={shown}
          showsNotes
          onSubmit={onSaveDetails}
          onClosed={onEditClosed}
        />
      )}
      {openDialog === 'delete' && (
        <ConfirmDialog
          title={t('Delete {{title}}?', { title: quoted(t, shown.title) })}
          message={t(
            'Its folder (Markdown, illustrations and photos) will be moved to the library’s trash (.trash): nothing is permanently erased.',
          )}
          confirmLabel={t('Delete document')}
          isDanger
          onClosed={(isConfirmed) => onDeleteClosed(isConfirmed, shown.title)}
        />
      )}
    </section>
  );
};

interface DocumentOverviewProps {
  readonly document: DocumentWithPages;
  readonly markdownUrl: string;
  readonly archiveUrl: string;
  readonly includesScans: boolean;
  readonly formatting: NumberFormatting;
  readonly uploads: UploadQueue<File>;
  readonly uuids: UuidSource;
  readonly onIncludesScansChange: (includesScans: boolean) => void;
  readonly onCopyFolder: (folder: string) => void;
}

const DocumentOverview: FC<DocumentOverviewProps> = ({
  document,
  markdownUrl,
  archiveUrl,
  includesScans,
  formatting,
  uploads,
  uuids,
  onIncludesScansChange,
  onCopyFolder,
}) => {
  const { t } = useTranslation();
  const withScansId = useId();

  return (
    <div className="doc-overview">
      <section className="card" aria-labelledby="coverage-title">
        <h2 id="coverage-title" className="card-title">
          {t('Coverage')}
        </h2>
        <div>
          <Coverage coverage={document.coverage} formatting={formatting} />
        </div>
        <dl className="stats">
          {statTiles(t, document.stats).map(({ name, label, count, tone }) => (
            <div key={name} className={statClass(count, tone)}>
              <dt className="stat-label">{label}</dt>
              <dd className="stat-value">{String(count)}</dd>
            </div>
          ))}
        </dl>
      </section>
      <div className="doc-side">
        <section className="card" aria-labelledby="upload-title">
          <h2 id="upload-title" className="card-title">
            {t('Add pages')}
          </h2>
          <Uploader documentId={document.id} uploads={uploads} uuids={uuids} formatting={formatting} />
        </section>
        <section className="card" aria-labelledby="export-title">
          <h2 id="export-title" className="card-title">
            {t('Export')}
          </h2>
          <div className="button-row">
            <a className="btn" href={markdownUrl} download={`${document.slug}.md`}>
              <Icon name="download" />
              {MARKDOWN_FILE_NAME}
            </a>
            <a className="btn" href={archiveUrl} download={`${document.slug}.zip`}>
              <Icon name="archive" />
              {t('.zip archive')}
            </a>
          </div>
          <label className="checkbox checkbox-inline" htmlFor={withScansId}>
            <input
              type="checkbox"
              id={withScansId}
              checked={includesScans}
              onChange={(event) => onIncludesScansChange(event.target.checked)}
            />
            <span>{t('Include the original photos in the archive')}</span>
          </label>
          <div className="folder-path" hidden={document.folder === ''}>
            <span className="hint">{t('Folder on the PC')}</span>
            <div className="copy-line">
              <code className="path">{document.folder}</code>
              <button
                type="button"
                className="btn btn-icon btn-small"
                aria-label={t('Copy the folder path')}
                onClick={() => onCopyFolder(document.folder)}
              >
                <Icon name="copy" />
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

const statClass = (count: number, tone: StatTone | null): string => {
  if (count === 0) return 'stat is-zero';
  return tone === null ? 'stat' : `stat stat-${tone}`;
};

interface PagesSectionProps {
  readonly document: DocumentWithPages;
  readonly organizeButton: RefObject<HTMLButtonElement | null>;
  readonly onOrganize: (() => void) | null;
  readonly organizer: ReactNode;
}

const PagesSection: FC<PagesSectionProps> = ({ document, organizeButton, onOrganize, organizer }) => {
  const { t } = useTranslation();
  const { pages } = document;
  return (
    <section className="pages-section" aria-labelledby="pages-title">
      <div className="section-header">
        <h2 id="pages-title" className="section-title">
          {t('Pages')} <span className="section-count">{pages.length > 0 ? `(${pages.length})` : ''}</span>
        </h2>
        <button
          ref={organizeButton}
          type="button"
          className="btn btn-small"
          hidden={onOrganize === null || !canOrganize(pages)}
          onClick={() => onOrganize?.()}
        >
          <Icon name="reorder" />
          {t('Organize')}
        </button>
      </div>
      {organizer || <PageGroups pages={pages} />}
    </section>
  );
};

const PageGroups: FC<{ readonly pages: DocumentWithPages['pages'] }> = ({ pages }) => {
  const { t } = useTranslation();
  if (pages.length > 0) return <PageGrid pages={pages} />;
  return (
    <div className="page-groups">
      <EmptyState
        iconName="camera"
        title={t('No pages yet')}
        message={t('Import photos above, or scan this document with the Android app.')}
      />
    </div>
  );
};
