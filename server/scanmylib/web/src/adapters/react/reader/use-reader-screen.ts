import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router';

import type { DocumentStore } from '../../../application/document-store.ts';
import { createReaderLoader, type ReaderLoad, type ReaderLoader } from '../../../application/reader-loader.ts';
import { readingOutline } from '../../../domain/reading.ts';
import type { LabeledPage } from '../../i18next/page-labels.ts';
import { errorMessage } from '../shell/error-message.ts';
import { documentTitle } from '../shell/navigation.ts';
import type { Toasts } from '../shell/toasts.ts';
import { type OutlineGroup, outlineGroups } from './outline-groups.ts';
import { readingPartsOf } from './reader-html.ts';

export interface ReaderScreenServices {
  readonly documents: DocumentStore;
  readonly toasts: Toasts;
}

export interface ReaderScreenState {
  readonly load: ReaderLoad;
  readonly outline: readonly OutlineGroup<LabeledPage>[];
  readonly pageCount: number;
  readonly readerAddress: string;
  readonly markdownUrl: string;
  readonly onReload: () => void;
}

export const useReaderScreen = (documentId: string, { documents, toasts }: ReaderScreenServices): ReaderScreenState => {
  const { t } = useTranslation();
  const { pathname, search } = useLocation();
  const [load, setLoad] = useState<ReaderLoad>({ phase: 'loading' });
  const loader = useRef<ReaderLoader | null>(null);
  const screenTitle = load.phase === 'loaded' ? `${t('Reading')} · ${load.document.title}` : null;
  const sanitizedHtml = load.phase === 'loaded' ? load.sanitizedHtml : null;
  const pages = load.phase === 'loaded' ? load.document.pages : null;
  const parts = useMemo(() => (sanitizedHtml === null ? null : readingPartsOf(t, sanitizedHtml)), [t, sanitizedHtml]);
  const outline = useMemo(() => {
    if (parts === null || pages === null) return [];
    const labeledPages = new Map<string, LabeledPage>(pages.map((page) => [page.key, { page_label: page.pageLabel }]));
    return outlineGroups(readingOutline(parts, labeledPages));
  }, [parts, pages]);

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

  return {
    load,
    outline,
    pageCount: parts?.filter((part) => part.type === 'page').length ?? 0,
    readerAddress: `${pathname}${search}`,
    markdownUrl: documents.markdownUrl(documentId),
    // The loader tells its failures itself, so its promise never rejects.
    onReload: () => void loader.current?.load(),
  };
};
