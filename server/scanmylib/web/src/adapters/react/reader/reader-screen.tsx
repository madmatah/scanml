import type { TFunction } from 'i18next';
import { Fragment, type ReactNode, useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useParams } from 'react-router';
import { isNotFound } from '../../../application/document-loader.ts';
import type { DocumentStore } from '../../../application/document-store.ts';
import { createReaderLoader, type ReaderLoad, type ReaderLoader } from '../../../application/reader-loader.ts';
import { type DocumentWithPages, type PageSummary, waitingPageCount } from '../../../domain/document-details.ts';
import { type ReadingPart, readingOutline } from '../../../domain/reading.ts';
import type { LabeledPage } from '../../i18next/page-labels.ts';
import { outlineEntryLabel } from '../../i18next/reading-text.ts';
import { localizeMarkers } from '../sanitized-html/page-markers.ts';
import { type FormulaTypesetter, useSanitizedHtml } from '../sanitized-html/use-sanitized-html.ts';
import { EmptyState } from '../shell/empty-state.tsx';
import { errorMessage } from '../shell/error-message.ts';
import { ErrorState } from '../shell/error-state.tsx';
import { Icon } from '../shell/icon.tsx';
import { LoadingState } from '../shell/loading-state.tsx';
import { documentPath, documentTitle, idOfAddress, PATHS, pagePath } from '../shell/navigation.ts';
import type { Toasts } from '../shell/toasts.ts';
import { versionedUrl } from '../shell/versioned-url.ts';
import { type GroupedOutlineEntry, outlineGroups } from './outline-groups.ts';
import { isAddressOf, pageReadIn, withPageRead } from './page-read-memory.ts';
import { emptyReadingMessage, waitingPagesNotice } from './reader-text.ts';
import { documentParts } from './reading-parts.ts';
import { createReadingTracker, type ReadingTracker } from './reading-tracker.ts';

export interface ReaderScreenProps {
  readonly documents: DocumentStore;
  readonly toasts: Toasts;
  readonly typesetFormulas: FormulaTypesetter;
}

// Each document has a reader of its own, which starts afresh.
export const ReaderScreen = (props: ReaderScreenProps) => {
  const documentId = idOfAddress(useParams().documentId);
  if (documentId === null) return null;
  return <ReaderView key={documentId} documentId={documentId} {...props} />;
};

interface ReaderViewProps extends ReaderScreenProps {
  readonly documentId: string;
}

const ReaderView = ({ documentId, documents, toasts, typesetFormulas }: ReaderViewProps) => {
  const { t } = useTranslation();
  const [load, setLoad] = useState<ReaderLoad>({ phase: 'loading' });
  const loader = useRef<ReaderLoader | null>(null);
  const screenTitle = load.phase === 'loaded' ? `${t('Reading')} · ${load.document.title}` : null;

  // The title of the previous screen stays until the document's own is known.
  useEffect(() => {
    if (screenTitle !== null) document.title = documentTitle(screenTitle);
  }, [screenTitle]);

  useEffect(() => {
    const leaving = new AbortController();
    const readerLoader = createReaderLoader({
      readDocument: (signal) => documents.readDocument(documentId, signal),
      readDocumentHtml: (signal) => documents.readDocumentHtml(documentId, signal),
      leaving: leaving.signal,
      onChange: setLoad,
      onRefreshFailed: (failure) => toasts.show(errorMessage(t, failure, t('Could not refresh.')), 'error'),
    });
    loader.current = readerLoader;
    void readerLoader.load();
    return () => leaving.abort();
  }, [documentId, documents, toasts, t]);

  // The loader tells its failures itself, so its promise never rejects.
  const reload = useCallback(() => void loader.current?.load(), []);

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
          {...(isMissing ? {} : { onRetry: reload })}
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
      markdownUrl={documents.markdownUrl(documentId)}
      typesetFormulas={typesetFormulas}
      onReload={reload}
    />
  );
};

const BackToDocument = ({ documentId }: { readonly documentId: string }) => {
  const { t } = useTranslation();
  return (
    <Link className="btn" to={documentPath(documentId)}>
      <Icon name="chevron-left" />
      {t('Back to the document')}
    </Link>
  );
};

const ReloadButton = ({ onReload }: { readonly onReload: () => void }) => {
  const { t } = useTranslation();
  return (
    <button type="button" className="btn btn-small" onClick={onReload}>
      <Icon name="refresh" />
      {t('Refresh')}
    </button>
  );
};

const removeTitle = (content: DocumentFragment): void => {
  if (content.firstElementChild?.tagName === 'H1') content.firstElementChild.remove();
};

// The parts of the document's HTML that the "Page" list shows, read from a copy of its own: the text shown is parsed
// and prepared again where it is placed.
const readingPartsOf = (t: TFunction, sanitizedHtml: string): ReadingPart[] => {
  const template = document.createElement('template');
  template.innerHTML = sanitizedHtml;
  removeTitle(template.content);
  localizeMarkers(t, template.content);
  return documentParts(template.content.children).parts;
};

interface ReaderDocumentProps {
  readonly document: DocumentWithPages;
  readonly sanitizedHtml: string;
  readonly returnsToPageRead: boolean;
  readonly markdownUrl: string;
  readonly typesetFormulas: FormulaTypesetter;
  readonly onReload: () => void;
}

const ReaderDocument = ({
  document: shownDocument,
  sanitizedHtml,
  returnsToPageRead,
  markdownUrl,
  typesetFormulas,
  onReload,
}: ReaderDocumentProps) => {
  const { t } = useTranslation();
  const titleId = useId();
  const parts = useMemo(() => readingPartsOf(t, sanitizedHtml), [t, sanitizedHtml]);
  const pageCount = parts.filter((part) => part.type === 'page').length;
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
      parts={parts}
      pageCount={pageCount}
      pages={shownDocument.pages}
      sanitizedHtml={sanitizedHtml}
      returnsToPageRead={returnsToPageRead}
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
  readonly parts: readonly ReadingPart[];
  readonly pageCount: number;
  readonly pages: readonly PageSummary[];
  readonly sanitizedHtml: string;
  readonly returnsToPageRead: boolean;
  readonly titleId: string;
  readonly typesetFormulas: FormulaTypesetter;
}

const preparePage = (t: TFunction, section: Element, page: PageSummary | undefined): void => {
  const marker = section.querySelector(':scope > .page-marker');
  const pageId = page === undefined ? null : idOfAddress(page.id);
  if (marker !== null && pageId !== null) {
    const link = document.createElement('a');
    link.href = `#${pagePath(pageId)}`;
    link.title = t('Open this page: scan, number, recognized text');
    link.textContent = marker.textContent;
    marker.replaceChildren(link);
  }
  for (const illustration of section.querySelectorAll('img[src]')) {
    const address = illustration.getAttribute('src');
    // A new reading of the page's text rewrites its illustrations in place.
    if (address !== null) illustration.setAttribute('src', versionedUrl(address, page?.readAt ?? ''));
    illustration.setAttribute('loading', 'lazy');
    illustration.setAttribute('decoding', 'async');
  }
};

// As in the legend of the document's coverage.
const missingPagesSwatch = (): HTMLElement => {
  const swatch = document.createElement('span');
  swatch.className = 'swatch is-missing';
  swatch.setAttribute('aria-hidden', 'true');
  return swatch;
};

// The screen's element is rendered here, with the "Page" bar and the text, so that all three exist when the text is
// placed and the tracker starts.
const ReadingText = ({
  children,
  parts,
  pageCount,
  pages,
  sanitizedHtml,
  returnsToPageRead,
  titleId,
  typesetFormulas,
}: ReadingTextProps) => {
  const { t } = useTranslation();
  const { pathname, search } = useLocation();
  const selectId = useId();
  const view = useRef<HTMLElement>(null);
  const toolbar = useRef<HTMLDivElement>(null);
  const tracker = useRef<ReadingTracker | null>(null);
  const [currentIndex, setCurrentIndex] = useState(-1);
  const pagesByKey = useMemo(() => new Map(pages.map((page) => [page.key, page])), [pages]);
  const outline = useMemo(() => {
    const labeledPages = new Map<string, LabeledPage>(pages.map((page) => [page.key, { page_label: page.pageLabel }]));
    return outlineGroups(readingOutline(parts, labeledPages));
  }, [parts, pages]);
  const readerAddress = `${pathname}${search}`;

  const prepare = useCallback(
    (content: DocumentFragment) => {
      removeTitle(content);
      localizeMarkers(t, content);
      for (const element of content.children) {
        if (element.matches('section.page')) {
          preparePage(t, element, pagesByKey.get(element.getAttribute('data-key') ?? ''));
        } else if (element.matches('.missing-pages')) {
          element.prepend(missingPagesSwatch());
        }
      }
    },
    [t, pagesByKey],
  );

  // The tracker starts with the first text placed, once the elements it follows exist.
  const followPages = useCallback(
    (textElement: HTMLElement) => {
      const viewElement = view.current;
      const toolbarElement = toolbar.current;
      if (viewElement === null || toolbarElement === null) return;
      tracker.current ??= createReadingTracker(
        {
          view: viewElement,
          toolbar: toolbarElement,
          text: textElement,
          appHeader: document.getElementById('app-header'),
        },
        {
          onPageRead: setCurrentIndex,
          onRememberPage: (pageKey) => {
            // The router may have left the reader's history entry before the screen goes.
            if (isAddressOf(window.location.hash, readerAddress)) {
              window.history.replaceState(withPageRead(window.history.state, pageKey), '');
            }
          },
        },
      );
      const placedPages = [...textElement.querySelectorAll<HTMLElement>(':scope > section.page')];
      tracker.current.follow(placedPages, returnsToPageRead ? pageReadIn(window.history.state) : null);
    },
    [readerAddress, returnsToPageRead],
  );
  const text = useSanitizedHtml<HTMLElement>(sanitizedHtml, prepare, typesetFormulas, followPages);

  useEffect(
    () => () => {
      tracker.current?.destroy();
      tracker.current = null;
    },
    [],
  );

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
          onChange={(event) => tracker.current?.goToPage(Number(event.target.value))}
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

const OutlineOption = ({ entry }: { readonly entry: GroupedOutlineEntry<LabeledPage> }) => {
  const { t } = useTranslation();
  if (entry.type === 'gap') return <option disabled>{outlineEntryLabel(t, entry)}</option>;
  return <option value={String(entry.index)}>{outlineEntryLabel(t, entry)}</option>;
};
