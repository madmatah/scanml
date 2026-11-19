import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { ApiError, NetworkError } from '../../application/api-errors.ts';
import type { PageUpload } from '../../application/upload-queue.ts';
import { createPageUploader, type UploadProgress, type UploadRequest } from './page-uploader.ts';

interface FakeRequest extends UploadRequest {
  readonly opened: string[];
  readonly headers: Record<string, string>;
  readonly sent: FormData[];
  readonly reportProgress: (progress: UploadProgress) => void;
  readonly answer: (status: number, response: unknown) => void;
  readonly breakConnection: (type: 'error' | 'timeout') => void;
}

interface Arrangement {
  readonly request: FakeRequest;
  readonly progress: number[];
  readonly unauthorizedCount: () => number;
  readonly outcome: Promise<unknown>;
}

const DOCUMENT_ID = '95bbeb79-4351-432f-a53c-d3658892ff50';
const PAGE_ID = '0b6d1f1e-7c1e-4f53-9a8f-7d2c3a1b9e40';
const SESSION_ID = 'c3a7e2d1-5b4f-4e6a-8d9c-1f2e3d4c5b6a';
const SEQUENCE_NUMBER = 3;
const CAPTURED_AT = '2026-03-07T09:05:03+02:00';
const PHOTO_NAME = 'IMG_0003.jpg';
const PHOTO_BYTES = 'not really a photo';
const CREATED = 201;
const UNAUTHORIZED = 401;
const UNSUPPORTED_MEDIA_TYPE = 415;

const createFakeRequest = (): FakeRequest => {
  const opened: string[] = [];
  const headers: Record<string, string> = {};
  const sent: FormData[] = [];
  const progressListeners: ((progress: UploadProgress) => void)[] = [];
  const listeners = new Map<string, (() => void)[]>();
  let status = 0;
  let response: unknown = null;
  const dispatch = (type: string): void => {
    for (const listener of listeners.get(type) ?? []) listener();
  };
  return {
    responseType: '',
    get status() {
      return status;
    },
    get response() {
      return response;
    },
    upload: {
      addEventListener: (_type, listener) => {
        progressListeners.push(listener);
      },
    },
    opened,
    headers,
    sent,
    open: (method, url) => {
      opened.push(`${method} ${url}`);
    },
    setRequestHeader: (name, value) => {
      headers[name] = value;
    },
    addEventListener: (type, listener) => {
      listeners.set(type, [...(listeners.get(type) ?? []), listener]);
    },
    send: (body) => {
      sent.push(body);
    },
    reportProgress: (progress) => {
      for (const listener of progressListeners) listener(progress);
    },
    answer: (answerStatus, answerResponse) => {
      status = answerStatus;
      response = answerResponse;
      dispatch('load');
    },
    breakConnection: (type) => dispatch(type),
  };
};

const pageUpload = (): PageUpload<File> => {
  return {
    documentId: DOCUMENT_ID,
    pageId: PAGE_ID,
    sessionId: SESSION_ID,
    seq: SEQUENCE_NUMBER,
    capturedAt: CAPTURED_AT,
    file: new File([PHOTO_BYTES], PHOTO_NAME, { type: 'image/jpeg' }),
  };
};

const arrange = (): Arrangement => {
  const request = createFakeRequest();
  const progress: number[] = [];
  let unauthorizedCount = 0;
  const uploader = createPageUploader(
    () => request,
    () => {
      unauthorizedCount += 1;
    },
  );
  const outcome = uploader
    .uploadPage(pageUpload(), (ratio) => progress.push(ratio))
    .then(
      () => null,
      (failure: unknown) => failure,
    );
  return { request, progress, unauthorizedCount: () => unauthorizedCount, outcome };
};

const fieldsOf = (form: FormData | undefined): Record<string, string> => {
  const fields: Record<string, string> = {};
  for (const [name, field] of form?.entries() ?? []) fields[name] = typeof field === 'string' ? field : field.name;
  return fields;
};

describe('The page uploader', () => {
  describe('The uploadPage() method', () => {
    describe('When a photo is sent', () => {
      let arrangement: Arrangement;
      beforeEach(() => {
        arrangement = arrange();
      });

      it('should post it to the pages of its document', () => {
        assert.deepEqual(arrangement.request.opened, [`POST /api/documents/${DOCUMENT_ID}/pages`]);
      });

      it('should mark the request as the web UI’s, which the api requires of a change', () => {
        assert.deepEqual(arrangement.request.headers, { Accept: 'application/json', 'X-ScanMyLib': '1' });
      });

      it('should send the page’s id, its capture session, its sequence number, its time and the photo', () => {
        assert.deepEqual(fieldsOf(arrangement.request.sent[0]), {
          page_id: PAGE_ID,
          session_id: SESSION_ID,
          seq: String(SEQUENCE_NUMBER),
          captured_at: CAPTURED_AT,
          file: PHOTO_NAME,
        });
      });

      it('should read the answer as JSON, for the detail of a refusal', () => {
        assert.equal(arrangement.request.responseType, 'json');
      });
    });

    describe('When the browser tells how much of the photo is sent', () => {
      let arrangement: Arrangement;
      beforeEach(() => {
        arrangement = arrange();
        arrangement.request.reportProgress({ lengthComputable: true, loaded: 250, total: 1000 });
        arrangement.request.reportProgress({ lengthComputable: false, loaded: 500, total: 0 });
      });

      it('should report the share sent, whenever the browser knows the whole size', () => {
        assert.deepEqual(arrangement.progress, [0.25]);
      });
    });

    describe('When the api creates the page', () => {
      let outcome: unknown;
      beforeEach(async () => {
        const arrangement = arrange();
        arrangement.request.answer(CREATED, { id: PAGE_ID });
        outcome = await arrangement.outcome;
      });

      it('should succeed', () => {
        assert.equal(outcome, null);
      });
    });

    describe('When the api refuses the photo', () => {
      let outcome: unknown;
      beforeEach(async () => {
        const arrangement = arrange();
        arrangement.request.answer(UNSUPPORTED_MEDIA_TYPE, { detail: 'not an image' });
        outcome = await arrangement.outcome;
      });

      it('should fail with the status and the detail of the refusal', () => {
        assert.deepEqual(outcome, new ApiError(UNSUPPORTED_MEDIA_TYPE, 'not an image'));
      });
    });

    describe('When the session of the browser has ended', () => {
      let arrangement: Arrangement;
      beforeEach(async () => {
        arrangement = arrange();
        arrangement.request.answer(UNAUTHORIZED, { detail: 'not signed in' });
        await arrangement.outcome;
      });

      it('should report it, so that the browser goes back to the login', () => {
        assert.equal(arrangement.unauthorizedCount(), 1);
      });
    });

    for (const type of ['error', 'timeout'] as const) {
      describe(`When the connection breaks (${type})`, () => {
        let outcome: unknown;
        beforeEach(async () => {
          const arrangement = arrange();
          arrangement.request.breakConnection(type);
          outcome = await arrangement.outcome;
        });

        it('should fail as a network failure, which a retry may overcome', () => {
          assert.ok(outcome instanceof NetworkError);
        });
      });
    }
  });
});
