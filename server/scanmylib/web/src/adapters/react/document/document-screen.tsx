import { type ReactNode, type RefObject, useEffect, useId, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router';

import type { Clipboard } from '../../../application/clipboard.ts';
import type { DocumentStore } from '../../../application/document-store.ts';
import type { EngineStatus } from '../../../application/engine-status.ts';
import type { Scheduler } from '../../../application/scheduler.ts';
import { sentCountOf, type UploadQueue } from '../../../application/upload-queue.ts';
import type { UuidSource } from '../../../application/uuid-source.ts';
import { canOrganize, type DocumentDetails, type DocumentWithPages } from '../../../domain/document-details.ts';
import type { NumberFormatting } from '../../../domain/formatting.ts';
import type { ReadingOrder } from '../../../domain/reading-order.ts';
import { documentKindLabel } from '../../i18next/document-labels.ts';
import { quoted } from '../../i18next/formatted-text.ts';
import { ConfirmDialog } from '../dialogs/confirm-dialog.tsx';
import { DocumentDialog } from '../dialogs/document-dialog.tsx';
import { hasQueueMoved, queueKeyOf } from '../library/library-loading.ts';
import { PageOrganizer } from '../organizer/page-organizer.tsx';
import { EmptyState } from '../shell/empty-state.tsx';
import { errorMessage } from '../shell/error-message.ts';
import { ErrorState } from '../shell/error-state.tsx';
import { Icon } from '../shell/icon.tsx';
import { LoadingState } from '../shell/loading-state.tsx';
import { documentTitle, idOfAddress, PATHS, readerPath } from '../shell/navigation.ts';
import type { Toasts } from '../shell/toasts.ts';
import { Uploader } from '../uploads/uploader.tsx';
import { Coverage } from './coverage.tsx';
import { createDocumentLoader, type DocumentLoad, type DocumentLoader, isNotFound } from './document-loader.ts';
import { type StatTone, statTiles } from './document-text.ts';
import { PageGrid } from './page-grid.tsx';

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

type OpenDialog = 'edit' | 'delete' | null;

// A file name, the same in every language.
const MARKDOWN_FILE_NAME = 'document.md';

// Each document has a screen of its own, so that going from one to another starts the next one afresh.
export function DocumentScreen(props: DocumentScreenProps) {
  const documentId = idOfAddress(useParams().documentId);
  if (documentId === null) return null;
  return <DocumentView key={documentId} documentId={documentId} {...props} />;
}

interface DocumentViewProps extends DocumentScreenProps {
  readonly documentId: string;
}

function DocumentView({
  documentId,
  store,
  engineStatus,
  scheduler,
  toasts,
  clipboard,
  formatting,
  uploads,
  uuids,
}: DocumentViewProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [load, setLoad] = useState<DocumentLoad>({ phase: 'loading' });
  const [openDialog, setOpenDialog] = useState<OpenDialog>(null);
  const [isOrganizing, setOrganizing] = useState(false);
  const loader = useRef<DocumentLoader | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const organizeButton = useRef<HTMLButtonElement>(null);
  const title = load.phase === 'loaded' ? load.document.title : null;

  // The title of the previous screen stays until the document's own is known.
  useEffect(() => {
    if (title !== null) document.title = documentTitle(title);
  }, [title]);

  useEffect(() => {
    const leaving = new AbortController();
    const documentLoader = createDocumentLoader({
      read: (signal) => store.readDocument(documentId, signal),
      scheduler,
      isUploading: () => uploads.isBusy(documentId),
      leaving: leaving.signal,
      onChange: setLoad,
      onDeleted: () => {
        toasts.show(t('This document has been deleted.'), 'error');
        void navigate(PATHS.home, { replace: true });
      },
    });
    // From the last known status, so that a page read before the first poll after opening is not missed.
    let lastQueueKey = queueKeyOf(engineStatus.getSnapshot().status);
    // New pages from the phone, or pages whose text is now read, show without waiting for a refresh.
    const stopWatchingQueue = engineStatus.subscribe(() => {
      const key = queueKeyOf(engineStatus.getSnapshot().status);
      if (key === null) return;
      if (hasQueueMoved(lastQueueKey, key)) documentLoader.load();
      lastQueueKey = key;
    });
    // The pages of the photos sent from this screen show shortly after their upload.
    let sentCount = sentCountOf(uploads.getSnapshot(), documentId);
    const stopWatchingUploads = uploads.subscribe(() => {
      const nextSentCount = sentCountOf(uploads.getSnapshot(), documentId);
      if (nextSentCount > sentCount) documentLoader.loadAfterUpload();
      sentCount = nextSentCount;
    });
    loader.current = documentLoader;
    documentLoader.load();
    return () => {
      leaving.abort();
      stopWatchingQueue();
      stopWatchingUploads();
    };
  }, [documentId, store, engineStatus, scheduler, uploads, toasts, t, navigate]);

  function edited(saved: DocumentDetails | null): void {
    setOpenDialog(null);
    if (saved === null || load.phase !== 'loaded') return;
    loader.current?.replace({ ...saved, pages: load.document.pages });
    toasts.show(t('Details saved.'), 'success');
  }

  async function deleteDocument(deletedTitle: string): Promise<void> {
    try {
      await store.deleteDocument(documentId);
      toasts.show(t('Document {{title}} moved to the trash.', { title: quoted(t, deletedTitle) }), 'success');
      await navigate(PATHS.home, { replace: true });
    } catch (failure) {
      toasts.show(errorMessage(t, failure, t('Could not delete.')), 'error');
    }
  }

  // A change of the order and a refresh cannot cross: the loader tells them apart.
  async function writeOrder(request: () => Promise<DocumentWithPages>): Promise<DocumentWithPages> {
    const documentLoader = loader.current;
    if (documentLoader === null) throw new Error('The document is organized before it is loaded');
    return await documentLoader.writeOrder(request);
  }

  function stopOrganizing(): void {
    flushSync(() => setOrganizing(false));
    const button = organizeButton.current;
    // The button stays hidden when too few pages are left to organize.
    (button === null || button.hidden ? heading.current : button)?.focus();
  }

  function deleteClosed(isConfirmed: boolean, deletedTitle: string): void {
    setOpenDialog(null);
    // deleteDocument tells its failures in a toast, so its promise never rejects.
    if (isConfirmed) void deleteDocument(deletedTitle);
  }

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
          {...(isMissing ? {} : { onRetry: () => loader.current?.load() })}
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
          <button type="button" className="btn" onClick={() => setOpenDialog('edit')}>
            <Icon name="edit" />
            {t('Edit')}
          </button>
          <button type="button" className="btn btn-danger" onClick={() => setOpenDialog('delete')}>
            <Icon name="trash" />
            {t('Delete')}
          </button>
        </div>
      </header>
      <DocumentOverview
        document={shown}
        store={store}
        toasts={toasts}
        clipboard={clipboard}
        formatting={formatting}
        uploads={uploads}
        uuids={uuids}
      />
      <PagesSection
        document={shown}
        organizeButton={organizeButton}
        onOrganize={isOrganizing ? null : () => setOrganizing(true)}
        organizer={
          isOrganizing && (
            <PageOrganizer
              document={shown}
              save={(order: ReadingOrder) => writeOrder(() => store.reorderPages(documentId, order))}
              reset={() => writeOrder(() => store.resetPageOrder(documentId))}
              reload={() => loader.current?.load()}
              toasts={toasts}
              onDone={stopOrganizing}
            />
          )
        }
      />
      {openDialog === 'edit' && (
        <DocumentDialog
          heading={t('Edit document')}
          submitLabel={t('Save')}
          initial={shown}
          withNotes
          onSubmit={(fields) => store.updateDocument(documentId, fields)}
          onClosed={edited}
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
          onClosed={(isConfirmed) => deleteClosed(isConfirmed, shown.title)}
        />
      )}
    </section>
  );
}

interface DocumentOverviewProps {
  readonly document: DocumentWithPages;
  readonly store: DocumentStore;
  readonly toasts: Toasts;
  readonly clipboard: Clipboard;
  readonly formatting: NumberFormatting;
  readonly uploads: UploadQueue<File>;
  readonly uuids: UuidSource;
}

function DocumentOverview({ document, store, toasts, clipboard, formatting, uploads, uuids }: DocumentOverviewProps) {
  const { t } = useTranslation();
  const withScansId = useId();
  const [withScans, setWithScans] = useState(false);

  async function copyFolder(): Promise<void> {
    if (await clipboard.copyText(document.folder)) toasts.show(t('Folder path copied.'), 'success');
    else toasts.show(t('Could not copy: select the path by hand.'), 'error');
  }

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
            <a className="btn" href={store.markdownUrl(document.id)} download={`${document.slug}.md`}>
              <Icon name="download" />
              {MARKDOWN_FILE_NAME}
            </a>
            <a className="btn" href={store.archiveUrl(document.id, withScans)} download={`${document.slug}.zip`}>
              <Icon name="archive" />
              {t('.zip archive')}
            </a>
          </div>
          <label className="checkbox checkbox-inline" htmlFor={withScansId}>
            <input
              type="checkbox"
              id={withScansId}
              checked={withScans}
              onChange={(event) => setWithScans(event.target.checked)}
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
                onClick={() => {
                  // copyFolder tells its outcome in a toast, and the clipboard's copy never rejects.
                  void copyFolder();
                }}
              >
                <Icon name="copy" />
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function statClass(count: number, tone: StatTone | null): string {
  if (count === 0) return 'stat is-zero';
  return tone === null ? 'stat' : `stat stat-${tone}`;
}

interface PagesSectionProps {
  readonly document: DocumentWithPages;
  readonly organizeButton: RefObject<HTMLButtonElement | null>;
  readonly onOrganize: (() => void) | null;
  readonly organizer: ReactNode;
}

function PagesSection({ document, organizeButton, onOrganize, organizer }: PagesSectionProps) {
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
}

function PageGroups({ pages }: { readonly pages: DocumentWithPages['pages'] }) {
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
}
