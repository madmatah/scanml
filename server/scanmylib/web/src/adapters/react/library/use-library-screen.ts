import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import type { DocumentCatalog, DocumentFields } from '../../../application/document-catalog.ts';
import type { EngineStatus } from '../../../application/engine-status.ts';
import { createLibraryLoader, type LibraryLoad } from '../../../application/library-loader.ts';
import { watchQueueMoves } from '../../../application/queue-moves.ts';
import type { UuidSource } from '../../../application/uuid-source.ts';
import { showsSearch } from '../../../domain/document-search.ts';
import type { DocumentSummary } from '../../../domain/document-summary.ts';
import { quoted } from '../../i18next/formatted-text.ts';
import { errorMessage } from '../shell/error-message.ts';
import { documentPath } from '../shell/navigation.ts';
import type { Toasts } from '../shell/toasts.ts';
import { useDocumentTitle } from '../shell/use-document-title.ts';

export interface LibraryScreenState {
  readonly load: LibraryLoad;
  readonly nowMilliseconds: number;
  readonly libraryDirectory: string;
  readonly query: string;
  readonly isSearchShown: boolean;
  readonly newDocumentId: string | null;
  readonly onQueryChange: (query: string) => void;
  readonly onRetry: () => void;
  readonly onNewDocument: () => void;
  readonly onCreateDocument: (id: string, fields: DocumentFields) => Promise<DocumentSummary>;
  readonly onNewDocumentClosed: (created: DocumentSummary | null) => void;
}

// Keeps "Updated 5 minutes ago" true while the screen stays open.
const RELATIVE_DATES_REFRESH_MILLISECONDS = 60_000;

export const useLibraryScreen = (
  catalog: DocumentCatalog,
  engineStatus: Pick<EngineStatus, 'subscribe' | 'getSnapshot'>,
  toasts: Toasts,
  uuids: UuidSource,
): LibraryScreenState => {
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
    const loader = createLibraryLoader({
      listDocuments: (signal) => catalog.listDocuments(signal),
      leaving: leaving.signal,
      onChange: (next) => {
        if (next.phase === 'loaded') setNow(Date.now());
        setLoad(next);
      },
      onRefreshFailed: (failure) => {
        toasts.show(errorMessage(t, failure, t('Could not refresh the library.')), 'error');
      },
    });
    const loadAgain = (): void => loader.load();

    // New pages from the phone, or pages whose text is now read, change the documents' counts.
    const stopWatchingQueue = watchQueueMoves(engineStatus, loadAgain, { from: null });
    const loadWhenShown = (): void => {
      if (!document.hidden) loadAgain();
    };
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

  const isSearchShown = load.phase === 'loaded' && showsSearch(load.documents);
  // A search left typed while the field hides would keep filtering the list out of sight.
  if (!isSearchShown && query !== '') setQuery('');

  const newDocumentClosed = (created: DocumentSummary | null): void => {
    setNewDocumentId(null);
    if (created === null) return;
    toasts.show(t('Document {{title}} created.', { title: quoted(t, created.title) }), 'success');
    void navigate(documentPath(created.id));
  };

  return {
    load,
    nowMilliseconds,
    libraryDirectory,
    query,
    isSearchShown,
    newDocumentId,
    onQueryChange: setQuery,
    onRetry: () => reload.current(),
    // One id per dialog, so that a request sent again from it stays the same creation.
    onNewDocument: () => setNewDocumentId(uuids.createUuid()),
    onCreateDocument: (id, fields) => catalog.createDocument(id, fields),
    onNewDocumentClosed: newDocumentClosed,
  };
};
