import { type RefObject, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import type { Clipboard } from '../../../application/clipboard.ts';
import type { DocumentFields } from '../../../application/document-catalog.ts';
import { createDocumentLoader, type DocumentLoad, type DocumentLoader } from '../../../application/document-loader.ts';
import type { DocumentStore } from '../../../application/document-store.ts';
import type { EngineStatus } from '../../../application/engine-status.ts';
import { watchQueueMoves } from '../../../application/queue-moves.ts';
import type { Scheduler } from '../../../application/scheduler.ts';
import { type UploadQueue, watchSentUploads } from '../../../application/upload-queue.ts';
import type { DocumentDetails, DocumentWithPages } from '../../../domain/document-details.ts';
import type { ReadingOrder } from '../../../domain/reading-order.ts';
import { quoted } from '../../i18next/formatted-text.ts';
import { errorMessage } from '../shell/error-message.ts';
import { documentTitle, PATHS } from '../shell/navigation.ts';
import type { Toasts } from '../shell/toasts.ts';

export type OpenDialog = 'edit' | 'delete' | null;

export interface DocumentScreenServices {
  readonly store: DocumentStore;
  readonly engineStatus: EngineStatus;
  readonly scheduler: Scheduler;
  readonly toasts: Toasts;
  readonly clipboard: Clipboard;
  readonly uploads: UploadQueue<File>;
}

export interface DocumentScreenState {
  readonly load: DocumentLoad;
  readonly openDialog: OpenDialog;
  readonly isOrganizing: boolean;
  readonly includesScans: boolean;
  readonly markdownUrl: string;
  readonly archiveUrl: string;
  readonly heading: RefObject<HTMLHeadingElement | null>;
  readonly organizeButton: RefObject<HTMLButtonElement | null>;
  readonly onEdit: () => void;
  readonly onDelete: () => void;
  readonly onSaveDetails: (fields: DocumentFields) => Promise<DocumentDetails>;
  readonly onEditClosed: (saved: DocumentDetails | null) => void;
  readonly onDeleteClosed: (isConfirmed: boolean, deletedTitle: string) => void;
  readonly onOrganize: () => void;
  readonly onSaveOrder: (order: ReadingOrder) => Promise<DocumentWithPages>;
  readonly onResetOrder: () => Promise<DocumentWithPages>;
  readonly onReload: () => void;
  readonly onDoneOrganizing: () => void;
  readonly onIncludesScansChange: (includesScans: boolean) => void;
  readonly onCopyFolder: (folder: string) => void;
}

export const useDocumentScreen = (
  documentId: string,
  { store, engineStatus, scheduler, toasts, clipboard, uploads }: DocumentScreenServices,
): DocumentScreenState => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [load, setLoad] = useState<DocumentLoad>({ phase: 'loading' });
  const [openDialog, setOpenDialog] = useState<OpenDialog>(null);
  const [isOrganizing, setOrganizing] = useState(false);
  const [includesScans, setIncludesScans] = useState(false);
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
    // New pages from the phone, or pages whose text is now read, show without waiting for a refresh, counted from the
    // last known status, so that a page read before the first poll after opening is not missed.
    const stopWatchingQueue = watchQueueMoves(engineStatus, () => documentLoader.load(), {
      from: engineStatus.getSnapshot().status,
    });
    // The pages of the photos sent from this screen show shortly after their upload.
    const stopWatchingUploads = watchSentUploads(uploads, documentId, () => documentLoader.loadAfterUpload());
    loader.current = documentLoader;
    documentLoader.load();
    return () => {
      leaving.abort();
      stopWatchingQueue();
      stopWatchingUploads();
    };
  }, [documentId, store, engineStatus, scheduler, uploads, toasts, t, navigate]);

  const edited = (saved: DocumentDetails | null): void => {
    setOpenDialog(null);
    if (saved === null || load.phase !== 'loaded') return;
    loader.current?.replace({ ...saved, pages: load.document.pages });
    toasts.show(t('Details saved.'), 'success');
  };

  const deleteDocument = async (deletedTitle: string): Promise<void> => {
    try {
      await store.deleteDocument(documentId);
      toasts.show(t('Document {{title}} moved to the trash.', { title: quoted(t, deletedTitle) }), 'success');
      await navigate(PATHS.home, { replace: true });
    } catch (failure) {
      toasts.show(errorMessage(t, failure, t('Could not delete.')), 'error');
    }
  };

  // A change of the order and a refresh cannot cross: the loader tells them apart.
  const writeOrder = async (request: () => Promise<DocumentWithPages>): Promise<DocumentWithPages> => {
    const documentLoader = loader.current;
    if (documentLoader === null) throw new Error('The document is organized before it is loaded');
    return await documentLoader.writeOrder(request);
  };

  const stopOrganizing = (): void => {
    flushSync(() => setOrganizing(false));
    const button = organizeButton.current;
    // The button stays hidden when too few pages are left to organize.
    (button === null || button.hidden ? heading.current : button)?.focus();
  };

  const deleteClosed = (isConfirmed: boolean, deletedTitle: string): void => {
    setOpenDialog(null);
    // deleteDocument tells its failures in a toast, so its promise never rejects.
    if (isConfirmed) void deleteDocument(deletedTitle);
  };

  const copyFolder = async (folder: string): Promise<void> => {
    if (await clipboard.copyText(folder)) toasts.show(t('Folder path copied.'), 'success');
    else toasts.show(t('Could not copy: select the path by hand.'), 'error');
  };

  return {
    load,
    openDialog,
    isOrganizing,
    includesScans,
    markdownUrl: store.markdownUrl(documentId),
    archiveUrl: store.archiveUrl(documentId, includesScans),
    heading,
    organizeButton,
    onEdit: () => setOpenDialog('edit'),
    onDelete: () => setOpenDialog('delete'),
    onSaveDetails: (fields) => store.updateDocument(documentId, fields),
    onEditClosed: edited,
    onDeleteClosed: deleteClosed,
    onOrganize: () => setOrganizing(true),
    onSaveOrder: (order) => writeOrder(() => store.reorderPages(documentId, order)),
    onResetOrder: () => writeOrder(() => store.resetPageOrder(documentId)),
    onReload: () => loader.current?.load(),
    onDoneOrganizing: stopOrganizing,
    onIncludesScansChange: setIncludesScans,
    onCopyFolder: (folder) => {
      // copyFolder tells its outcome in a toast, and the clipboard's copy never rejects.
      void copyFolder(folder);
    },
  };
};
