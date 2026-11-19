import { type FC, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { summarizeUploads, type UploadItem, type UploadQueue } from '../../../application/upload-queue.ts';
import type { UuidSource } from '../../../application/uuid-source.ts';
import type { NumberFormatting } from '../../../domain/formatting.ts';
import { Icon } from '../shell/icon.tsx';
import { uploadHeadline, uploadProblemText, uploadProgressText, waitingPhotosText } from './upload-text.ts';
import { useUploader } from './use-uploader.ts';

export interface UploaderProps {
  readonly documentId: string;
  readonly uploads: UploadQueue<File>;
  readonly uuids: UuidSource;
  readonly formatting: NumberFormatting;
}

const takeFiles = (input: HTMLInputElement): File[] => {
  const files = [...(input.files ?? [])];
  // So that choosing the same photos again is a change too.
  input.value = '';
  return files;
};

export const Uploader: FC<UploaderProps> = ({ documentId, uploads, uuids, formatting }) => {
  const { t } = useTranslation();
  const filesInput = useRef<HTMLInputElement>(null);
  const cameraInput = useRef<HTMLInputElement>(null);
  const { items, onFilesChosen, onPhotosTaken, onRetryFailed, onClearFinished } = useUploader(
    documentId,
    uploads,
    uuids,
  );

  return (
    <div className="uploader">
      <div className="button-row">
        <button type="button" className="btn btn-primary" onClick={() => filesInput.current?.click()}>
          <Icon name="upload" />
          {t('Import photos')}
        </button>
        <button type="button" className="btn" onClick={() => cameraInput.current?.click()}>
          <Icon name="camera" />
          {t('Take a photo')}
        </button>
      </div>
      <p className="hint">
        {t('JPEG, PNG or WebP, 40 MiB maximum per photo. Photos are uploaded in the order of their file names.')}
      </p>
      <input
        ref={filesInput}
        type="file"
        accept="image/*"
        multiple
        hidden
        data-upload="files"
        onChange={(event) => onFilesChosen(takeFiles(event.currentTarget))}
      />
      <input
        ref={cameraInput}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        data-upload="camera"
        onChange={(event) => onPhotosTaken(takeFiles(event.currentTarget))}
      />
      <UploadPanel
        items={items}
        formatting={formatting}
        onRetryFailed={onRetryFailed}
        onClearFinished={onClearFinished}
      />
    </div>
  );
};

interface UploadPanelProps {
  readonly items: readonly UploadItem[];
  readonly formatting: NumberFormatting;
  readonly onRetryFailed: () => void;
  readonly onClearFinished: () => void;
}

const UploadPanel: FC<UploadPanelProps> = ({ items, formatting, onRetryFailed, onClearFinished }) => {
  const { t } = useTranslation();
  if (items.length === 0) return <div className="upload-panel" hidden />;
  const summary = summarizeUploads(items);
  const rowCount = summary.uploading.length + summary.failures.length + (summary.waitingCount > 0 ? 1 : 0);
  return (
    <div className="upload-panel">
      <p className="upload-headline">{uploadHeadline(t, formatting, summary)}</p>
      <progress
        className="upload-progress"
        max={1}
        value={summary.progress}
        aria-label={t('Upload progress')}
        hidden={!summary.isBusy}
      />
      {/* biome-ignore lint/a11y/noRedundantRoles: Safari drops the role of a list drawn without its markers. */}
      <ul className="upload-list" role="list" hidden={rowCount === 0}>
        {summary.uploading.map((upload) => (
          <li key={upload.pageId} className="upload-item">
            <span className="upload-name">{upload.name}</span>
            <span className="upload-state">{uploadProgressText(t, formatting, upload)}</span>
          </li>
        ))}
        {summary.failures.map((upload) => (
          <li key={upload.pageId} className="upload-item is-error">
            <span className="upload-name">{upload.name}</span>
            <span className="upload-state">{uploadProblemText(t, upload.problem)}</span>
          </li>
        ))}
        {summary.waitingCount > 0 && (
          <li className="upload-item is-muted">{waitingPhotosText(t, summary.waitingCount)}</li>
        )}
      </ul>
      <div className="upload-actions">
        <button type="button" className="btn btn-small" hidden={summary.failed.length === 0} onClick={onRetryFailed}>
          <Icon name="refresh" />
          {t('Retry failed uploads')}
        </button>
        <button type="button" className="btn btn-small btn-ghost" hidden={summary.isBusy} onClick={onClearFinished}>
          {t('Clear the list')}
        </button>
      </div>
    </div>
  );
};
