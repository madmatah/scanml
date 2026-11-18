import { type ReactNode, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';

import type { DocumentCatalog } from '../../../application/document-catalog.ts';
import type { EngineStatus } from '../../../application/engine-status.ts';
import type { UuidSource } from '../../../application/uuid-source.ts';
import { documentsMatching } from '../../../domain/document-search.ts';
import type { DocumentSummary } from '../../../domain/document-summary.ts';
import type { DateFormatting } from '../../../domain/formatting.ts';
import { quoted } from '../../i18next/formatted-text.ts';
import { DocumentDialog } from '../dialogs/document-dialog.tsx';
import { EmptyState } from '../shell/empty-state.tsx';
import { errorMessage } from '../shell/error-message.ts';
import { ErrorState } from '../shell/error-state.tsx';
import { Icon } from '../shell/icon.tsx';
import { LoadingState } from '../shell/loading-state.tsx';
import { documentPath, PATHS } from '../shell/navigation.ts';
import type { Toasts } from '../shell/toasts.ts';
import { useDocumentTitle } from '../shell/use-document-title.ts';
import { DocumentCard } from './document-card.tsx';
import { afterLoadFailure, hasQueueMoved, type LibraryLoad, queueKeyOf, showsSearch } from './library-loading.ts';
import { librarySummaryText } from './library-text.ts';

// Keeps "Updated 5 minutes ago" true while the screen stays open.
const RELATIVE_DATES_REFRESH_MILLISECONDS = 60_000;

export interface LibraryProps {
  readonly catalog: DocumentCatalog;
  readonly engineStatus: Pick<EngineStatus, 'subscribe' | 'getSnapshot'>;
  readonly toasts: Toasts;
  readonly uuids: UuidSource;
  readonly dates: DateFormatting;
}

export function Library({ catalog, engineStatus, toasts, uuids, dates }: LibraryProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const libraryDirectory = useSyncExternalStore(
    engineStatus.subscribe,
    () => engineStatus.getSnapshot().status?.libraryDirectory ?? '',
  );
  const [load, setLoad] = useState<LibraryLoad>({ phase: 'loading' });
  const [nowMilliseconds, setNow] = useState(() => Date.now());
  const [query, setQuery] = useState('');
  const [newDocumentId, setNewDocumentId] = useState<string | null>(null);
  const reload = useRef<() => void>(() => {});
  useDocumentTitle(t('Library'));

  useEffect(() => {
    const leaving = new AbortController();
    let current: LibraryLoad = { phase: 'loading' };
    let lastQueueKey: string | null = null;

    function enter(next: LibraryLoad): void {
      current = next;
      setLoad(next);
    }

    async function loadDocuments(): Promise<void> {
      try {
        const documents = await catalog.listDocuments(leaving.signal);
        setNow(Date.now());
        enter({ phase: 'loaded', documents });
      } catch (failure) {
        if (leaving.signal.aborted) return;
        const outcome = afterLoadFailure(current, failure);
        enter(outcome.load);
        if (outcome.isToldInToast) toasts.show(errorMessage(t, failure, t('Could not refresh the library.')), 'error');
      }
    }

    function loadAgain(): void {
      // loadDocuments handles its own failures, so its promise never rejects.
      void loadDocuments();
    }

    // New pages from the phone, or pages whose text is now read, change the documents' counts.
    const stopWatchingQueue = engineStatus.subscribe(() => {
      const key = queueKeyOf(engineStatus.getSnapshot().status);
      if (key === null) return;
      if (hasQueueMoved(lastQueueKey, key)) loadAgain();
      lastQueueKey = key;
    });
    function loadWhenShown(): void {
      if (!document.hidden) loadAgain();
    }
    document.addEventListener('visibilitychange', loadWhenShown);
    const clock = window.setInterval(() => setNow(Date.now()), RELATIVE_DATES_REFRESH_MILLISECONDS);
    reload.current = loadAgain;
    loadAgain();
    return () => {
      leaving.abort();
      stopWatchingQueue();
      document.removeEventListener('visibilitychange', loadWhenShown);
      window.clearInterval(clock);
    };
  }, [catalog, engineStatus, toasts, t]);

  const isSearchShown = showsSearch(load);
  // A search left typed while the field hides would keep filtering the list out of sight.
  if (!isSearchShown && query !== '') setQuery('');

  function documentCreated(created: DocumentSummary | null): void {
    setNewDocumentId(null);
    if (created === null) return;
    toasts.show(t('Document {{title}} created.', { title: quoted(t, created.title) }), 'success');
    void navigate(documentPath(created.id));
  }

  // One id per dialog, so that a request sent again from it stays the same creation.
  const openNewDocument = () => setNewDocumentId(uuids.createUuid());
  const newDocumentButton = (
    <button type="button" className="btn btn-primary" onClick={openNewDocument}>
      <Icon name="plus" />
      {t('New document')}
    </button>
  );

  return (
    <section className="view library">
      <header className="view-header">
        <div className="view-heading">
          <h1 tabIndex={-1}>{t('Library')}</h1>
          <p className="view-subtitle">{load.phase === 'loaded' ? librarySummaryText(t, load.documents) : ''}</p>
        </div>
        <div className="view-actions">
          <div className="search-field" hidden={!isSearchShown}>
            <Icon name="search" />
            <input
              type="search"
              className="input"
              placeholder={t('Search for a title, an author…')}
              aria-label={t('Search the library')}
              autoComplete="off"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          {newDocumentButton}
        </div>
      </header>
      <div className="library-content">
        <LibraryContent
          load={load}
          query={query}
          dates={dates}
          nowMilliseconds={nowMilliseconds}
          emptyActions={
            <>
              {newDocumentButton}
              <Link className="btn" to={PATHS.pairing}>
                <Icon name="phone" />
                {t('Pair the phone')}
              </Link>
            </>
          }
          onRetry={() => reload.current()}
        />
      </div>
      <p className="library-footer" hidden={libraryDirectory === ''}>
        {libraryDirectory !== '' && (
          <Trans
            t={t}
            i18nKey="Markdown files and illustrations are stored in <folder>{{folder}}</folder>"
            values={{ folder: libraryDirectory }}
            components={{ folder: <code className="path" /> }}
          />
        )}
      </p>
      {newDocumentId !== null && (
        <DocumentDialog
          key={newDocumentId}
          heading={t('New document')}
          submitLabel={t('Create document')}
          onSubmit={(fields) => catalog.createDocument(newDocumentId, fields)}
          onClosed={documentCreated}
        />
      )}
    </section>
  );
}

interface LibraryContentProps {
  readonly load: LibraryLoad;
  readonly query: string;
  readonly dates: DateFormatting;
  readonly nowMilliseconds: number;
  readonly emptyActions: ReactNode;
  readonly onRetry: () => void;
}

function LibraryContent({ load, query, dates, nowMilliseconds, emptyActions, onRetry }: LibraryContentProps) {
  const { t } = useTranslation();
  switch (load.phase) {
    case 'loading':
      return <LoadingState />;
    case 'failed':
      return <ErrorState message={errorMessage(t, load.failure)} onRetry={onRetry} />;
    case 'loaded':
      break;
  }
  if (load.documents.length === 0) {
    return (
      <EmptyState
        iconName="book"
        title={t('Your library is empty')}
        message={t(
          'Create a document, then add photos to it from this browser, or scan directly with the Android app.',
        )}
        actions={emptyActions}
      />
    );
  }
  const shownDocuments = documentsMatching(load.documents, query);
  if (shownDocuments.length === 0) {
    return <p className="state">{t('No document matches {{query}}.', { query: quoted(t, query.trim()) })}</p>;
  }
  return (
    // biome-ignore lint/a11y/noRedundantRoles: Safari drops the role of a list drawn without its markers.
    <ul className="doc-grid" role="list">
      {shownDocuments.map((document) => (
        <DocumentCard key={document.id} document={document} dates={dates} nowMilliseconds={nowMilliseconds} />
      ))}
    </ul>
  );
}
