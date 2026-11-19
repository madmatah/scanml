import { ApiError, NetworkError } from '../../application/api-errors.ts';
import type { PageUploader } from '../../application/upload-queue.ts';
import { decodeErrorDetail } from './error-detail.ts';

export interface UploadProgress {
  readonly lengthComputable: boolean;
  readonly loaded: number;
  readonly total: number;
}

export interface UploadRequest {
  responseType: string;
  readonly status: number;
  readonly response: unknown;
  readonly upload: {
    addEventListener(type: 'progress', listener: (progress: UploadProgress) => void): void;
  };
  open(method: string, url: string): void;
  setRequestHeader(name: string, value: string): void;
  addEventListener(type: 'load' | 'error' | 'timeout', listener: () => void): void;
  send(body: FormData): void;
}

// The api refuses a request that changes state without this header (docs/API.md > Authentication).
const CSRF_HEADER = 'X-ScanMyLib';
const UNAUTHORIZED = 401;
const FIRST_SUCCESS = 200;
const FIRST_FAILURE = 300;

// An XMLHttpRequest rather than fetch(), which cannot tell how much of a request's body is sent.
export const createPageUploader = (
  createRequest: () => UploadRequest,
  onUnauthorized: () => void,
): PageUploader<File> => {
  return {
    uploadPage({ documentId, pageId, sessionId, seq, capturedAt, file }, onProgress) {
      return new Promise((resolve, reject) => {
        const request = createRequest();
        request.open('POST', `/api/documents/${encodeURIComponent(documentId)}/pages`);
        request.responseType = 'json';
        request.setRequestHeader('Accept', 'application/json');
        request.setRequestHeader(CSRF_HEADER, '1');
        request.upload.addEventListener('progress', (progress) => {
          if (progress.lengthComputable) onProgress(progress.loaded / progress.total);
        });
        request.addEventListener('load', () => {
          if (request.status >= FIRST_SUCCESS && request.status < FIRST_FAILURE) {
            resolve();
            return;
          }
          if (request.status === UNAUTHORIZED) onUnauthorized();
          reject(new ApiError(request.status, decodeErrorDetail(request.response)));
        });
        request.addEventListener('error', () => reject(new NetworkError()));
        request.addEventListener('timeout', () => reject(new NetworkError()));
        const form = new FormData();
        form.append('page_id', pageId);
        form.append('session_id', sessionId);
        form.append('seq', String(seq));
        form.append('captured_at', capturedAt);
        form.append('file', file, file.name);
        request.send(form);
      });
    },
  };
};
