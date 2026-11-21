import type { FC, ReactNode } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import type { DocumentCatalog } from '../../../application/document-catalog.ts';
import type { EngineStatus } from '../../../application/engine-status.ts';
import type { LibraryLoad } from '../../../application/library-loader.ts';
import type { UuidSource } from '../../../application/uuid-source.ts';
import { documentsMatching } from '../../../domain/document-search.ts';
import type { DateFormatting, NumberFormatting } from '../../../domain/formatting.ts';
import { quoted } from '../../i18next/formatted-text.ts';
import { DocumentDialog } from '../dialogs/document-dialog.tsx';
import { EmptyState } from '../shell/empty-state.tsx';
import { errorMessage } from '../shell/error-message.ts';
import { ErrorState } from '../shell/error-state.tsx';
import { Icon } from '../shell/icon.tsx';
import { LoadingState } from '../shell/loading-state.tsx';
import { PATHS } from '../shell/navigation.ts';
import type { Toasts } from '../shell/toasts.ts';
import { DocumentCard } from './document-card.tsx';
import { librarySummaryText } from './library-text.ts';
import { useLibraryScreen } from './use-library-screen.ts';

export interface LibraryScreenProps {
  readonly catalog: DocumentCatalog;
  readonly engineStatus: Pick<EngineStatus, 'subscribe' | 'getSnapshot'>;
  readonly toasts: Toasts;
  readonly uuids: UuidSource;
  readonly dates: DateFormatting;
  readonly formatting: NumberFormatting;
}

export const LibraryScreen: FC<LibraryScreenProps> = ({ catalog, engineStatus, toasts, uuids, dates, formatting }) => {
  const { t } = useTranslation();
  const {
    load,
    nowMilliseconds,
    libraryDirectory,
    query,
    isSearchShown,
    newDocumentId,
    onQueryChange,
    onRetry,
    onNewDocument,
    onCreateDocument,
    onNewDocumentClosed,
  } = useLibraryScreen(catalog, engineStatus, toasts, uuids);

  const newDocumentButton = (
    <button type="button" className="btn btn-primary" onClick={onNewDocument}>
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
              onChange={(event) => onQueryChange(event.target.value)}
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
          formatting={formatting}
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
          onRetry={onRetry}
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
          onSubmit={(fields) => onCreateDocument(newDocumentId, fields)}
          onClosed={onNewDocumentClosed}
        />
      )}
    </section>
  );
};

interface LibraryContentProps {
  readonly load: LibraryLoad;
  readonly query: string;
  readonly dates: DateFormatting;
  readonly formatting: NumberFormatting;
  readonly nowMilliseconds: number;
  readonly emptyActions: ReactNode;
  readonly onRetry: () => void;
}

const LibraryContent: FC<LibraryContentProps> = ({
  load,
  query,
  dates,
  formatting,
  nowMilliseconds,
  emptyActions,
  onRetry,
}) => {
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
        <DocumentCard
          key={document.id}
          document={document}
          dates={dates}
          formatting={formatting}
          nowMilliseconds={nowMilliseconds}
        />
      ))}
    </ul>
  );
};
