import type { TFunction } from 'i18next';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import type { Clipboard } from '../../../application/clipboard.ts';
import type { DocumentStore } from '../../../application/document-store.ts';
import {
  createPageActions,
  type PageAction,
  type PageActionOutcome,
  type PageDeletion,
} from '../../../application/page-actions.ts';
import { createPageLoader, type PageLoad, type PageLoader } from '../../../application/page-loader.ts';
import type { PageStore } from '../../../application/page-store.ts';
import type { Scheduler } from '../../../application/scheduler.ts';
import { type PageNeighbors, pageNeighbors } from '../../../domain/page-details.ts';
import { pageTitle } from '../../i18next/page-labels.ts';
import { errorMessage } from '../shell/error-message.ts';
import { documentPath, documentTitle, pagePath } from '../shell/navigation.ts';
import type { Toasts } from '../shell/toasts.ts';

export interface PageScreenServices {
  readonly pages: PageStore;
  readonly documents: Pick<DocumentStore, 'readDocument'>;
  readonly scheduler: Scheduler;
  readonly toasts: Toasts;
  readonly clipboard: Clipboard;
}

export interface PageScreenState {
  readonly load: PageLoad;
  readonly neighbors: PageNeighbors | null;
  readonly isBusy: boolean;
  readonly isConfirmingDelete: boolean;
  readonly isScanFullWidth: boolean;
  readonly showsMarkdown: boolean;
  readonly onRetry: () => void;
  readonly onSaveNumber: (number: number) => void;
  readonly onInvalidNumber: () => void;
  readonly onClearNumber: () => void;
  readonly onRotate: (rotation: number) => void;
  readonly onExclude: (isExcluded: boolean) => void;
  readonly onReadAgain: () => void;
  readonly onDelete: () => void;
  readonly onDeleteClosed: (isConfirmed: boolean) => void;
  readonly onToggleFullWidth: () => void;
  readonly onToggleMarkdown: () => void;
  readonly onCopyMarkdown: (markdown: string) => void;
}

const isTypingTarget = (target: EventTarget | null): boolean => {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.tagName === 'SELECT')
  );
};

const actionSuccessMessage = (t: TFunction, action: PageAction): string => {
  switch (action.kind) {
    case 'saveNumber':
      return t('Number {{number}} saved.', { number: action.number });
    case 'clearNumber':
      return t('Manual number cleared.');
    case 'rotate':
      return t('Page rotated: its text will be read again.');
    case 'setExclusion':
      return action.isExcluded ? t('Page excluded from the document.') : t('Page put back in the document.');
    case 'readAgain':
      return t('The text of this page will be read again.');
  }
};

export const usePageScreen = (
  pageId: string,
  { pages, documents, scheduler, toasts, clipboard }: PageScreenServices,
): PageScreenState => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [load, setLoad] = useState<PageLoad>({ phase: 'loading' });
  const [isBusy, setBusy] = useState(false);
  const [isConfirmingDelete, setConfirmingDelete] = useState(false);
  const [isScanFullWidth, setScanFullWidth] = useState(false);
  const [showsMarkdown, setShowsMarkdown] = useState(false);
  const loader = useRef<PageLoader | null>(null);
  const [actions] = useState(() =>
    createPageActions({
      pageId,
      pages,
      reload: async () => {
        await loader.current?.load();
      },
      onBusyChange: setBusy,
    }),
  );
  const screenTitle = load.phase === 'loaded' ? `${pageTitle(t, load.page)} · ${load.document.title}` : null;
  const neighbors = load.phase === 'loaded' ? pageNeighbors(load.document.pages, load.page.id) : null;
  const previousId = neighbors?.previous?.id ?? null;
  const nextId = neighbors?.next?.id ?? null;

  // The title of the previous screen stays until the page's own is known.
  useEffect(() => {
    if (screenTitle !== null) document.title = documentTitle(screenTitle);
  }, [screenTitle]);

  useEffect(() => {
    const leaving = new AbortController();
    const pageLoader = createPageLoader({
      readPage: (signal) => pages.readPage(pageId, signal),
      readDocument: (documentId, signal) => documents.readDocument(documentId, signal),
      readPageHtml: (signal) => pages.readPageHtml(pageId, signal),
      scheduler,
      leaving: leaving.signal,
      onChange: setLoad,
      onRefreshFailed: (failure) => toasts.show(errorMessage(t, failure, t('Could not refresh the page.')), 'error'),
    });
    loader.current = pageLoader;
    void pageLoader.load();
    return () => leaving.abort();
  }, [pageId, pages, documents, scheduler, toasts, t]);

  useEffect(() => {
    const goToNeighbor = (event: KeyboardEvent): void => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (isTypingTarget(event.target) || document.querySelector('dialog[open]') !== null) return;
      const targetId = event.key === 'ArrowLeft' ? previousId : event.key === 'ArrowRight' ? nextId : null;
      if (targetId === null) return;
      event.preventDefault();
      void navigate(pagePath(targetId));
    };
    document.addEventListener('keydown', goToNeighbor);
    return () => document.removeEventListener('keydown', goToNeighbor);
  }, [previousId, nextId, navigate]);

  const tellOutcome = (outcome: PageActionOutcome): void => {
    if (outcome.kind === 'succeeded') toasts.show(actionSuccessMessage(t, outcome.action), 'success');
    else toasts.show(errorMessage(t, outcome.failure, t('Action failed.')), 'error');
  };

  const runAction = (action: PageAction): void => {
    // The actions tell their outcome, failures included, so their promise never rejects.
    void actions.run(action, tellOutcome);
  };

  const deleteClosed = (isConfirmed: boolean): void => {
    setConfirmingDelete(false);
    if (!isConfirmed || load.phase !== 'loaded') return;
    const { documentId } = load.page;
    const destination = neighbors?.next ?? neighbors?.previous ?? null;
    const tellDeletion = (deletion: PageDeletion): void => {
      if (deletion.kind === 'failed') {
        toasts.show(errorMessage(t, deletion.failure, t('Could not delete.')), 'error');
        return;
      }
      toasts.show(t('Page deleted.'), 'success');
      void navigate(destination === null ? documentPath(documentId) : pagePath(destination.id), { replace: true });
    };
    // The deletion tells its outcome, its failure included, so its promise never rejects.
    void actions.deletePage(tellDeletion);
  };

  const copyMarkdown = async (markdown: string): Promise<void> => {
    if (await clipboard.copyText(markdown)) toasts.show(t('Markdown copied.'), 'success');
    else toasts.show(t('Could not copy.'), 'error');
  };

  return {
    load,
    neighbors,
    isBusy,
    isConfirmingDelete,
    isScanFullWidth,
    showsMarkdown,
    onRetry: () => void loader.current?.load(),
    onSaveNumber: (number) => runAction({ kind: 'saveNumber', number }),
    onInvalidNumber: () => toasts.show(t('Enter a whole page number between 1 and 9999.'), 'error'),
    onClearNumber: () => runAction({ kind: 'clearNumber' }),
    onRotate: (rotation) => runAction({ kind: 'rotate', rotation }),
    onExclude: (isExcluded) => runAction({ kind: 'setExclusion', isExcluded }),
    onReadAgain: () => runAction({ kind: 'readAgain' }),
    onDelete: () => setConfirmingDelete(true),
    onDeleteClosed: deleteClosed,
    onToggleFullWidth: () => setScanFullWidth(!isScanFullWidth),
    onToggleMarkdown: () => setShowsMarkdown(!showsMarkdown),
    onCopyMarkdown: (markdown) => {
      // copyMarkdown tells its outcome in a toast, and the clipboard's copy never rejects.
      void copyMarkdown(markdown);
    },
  };
};
