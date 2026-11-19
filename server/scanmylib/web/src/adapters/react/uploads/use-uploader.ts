import { useMemo, useRef, useSyncExternalStore } from 'react';

import {
  type CaptureSession,
  createCaptureSession,
  inFileNameOrder,
  type UploadItem,
  type UploadQueue,
  uploadsOf,
} from '../../../application/upload-queue.ts';
import type { UuidSource } from '../../../application/uuid-source.ts';

export interface UploaderState {
  readonly items: readonly UploadItem[];
  readonly onFilesChosen: (files: readonly File[]) => void;
  readonly onPhotosTaken: (files: readonly File[]) => void;
  readonly onRetryFailed: () => void;
  readonly onClearFinished: () => void;
}

export const useUploader = (documentId: string, uploads: UploadQueue<File>, uuids: UuidSource): UploaderState => {
  // The successive shots of the camera form one capture session, which another document starts afresh.
  const cameraSessionRef = useRef<CaptureSession | null>(null);
  if (cameraSessionRef.current === null) cameraSessionRef.current = createCaptureSession(uuids);
  const cameraSession = cameraSessionRef.current;
  const queued = useSyncExternalStore(uploads.subscribe, uploads.getSnapshot);
  const items = useMemo(() => uploadsOf(queued, documentId), [queued, documentId]);

  return {
    items,
    onFilesChosen: (chosen) => {
      const files = inFileNameOrder(chosen);
      if (files.length > 0) uploads.add(documentId, files, { sessionId: uuids.createUuid(), firstSeq: 1 });
    },
    onPhotosTaken: (files) => {
      if (files.length > 0) uploads.add(documentId, files, cameraSession.next(files.length));
    },
    onRetryFailed: () => uploads.retryFailed(documentId),
    onClearFinished: () => uploads.clearFinished(documentId),
  };
};
