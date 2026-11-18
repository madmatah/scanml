import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { createApiClient, type Fetch } from '../../../src/adapters/http-api/api-client.ts';
import type { SessionServer } from '../../../src/application/session.ts';
import type { DocumentSummary } from '../../../src/domain/document-summary.ts';
import type { PairingDetails } from '../../../src/domain/pairing-details.ts';
import type { ServerStatus } from '../../../src/domain/server-status.ts';

interface SentRequest {
  readonly path: string;
  readonly init: RequestInit;
}

interface Exchange {
  readonly requests: SentRequest[];
  readonly fetchFromApi: Fetch;
}

const TOKEN = 'a-token';
const DOCUMENT_ID = '95bbeb79-4351-432f-a53c-d3658892ff50';
const NO_CONTENT = 204;
const OK = 200;
const UNAUTHORIZED = 401;
const UNPROCESSABLE = 422;
const BAD_GATEWAY = 502;

function ignoreUnauthorized(): void {}

function exchange(answer: () => Response): Exchange {
  const requests: SentRequest[] = [];
  return {
    requests,
    fetchFromApi: async (path, init) => {
      requests.push({ path, init });
      return answer();
    },
  };
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function noContent(): Response {
  return new Response(null, { status: NO_CONTENT });
}

function documentBody(): Record<string, unknown> {
  return {
    id: DOCUMENT_ID,
    title: 'Example Book',
    author: 'Jane Doe',
    kind: 'book',
    updated_at: '2026-11-14T15:41:03+00:00',
    stats: { pages: 1, done: 1, queued: 0, processing: 0, error: 0, excluded: 0, duplicates: 0 },
    coverage: { ranges: [[11, 11]], label: '11', gaps: [], min: 11, max: 11, unnumbered: 0 },
    cover_thumb_url: null,
  };
}

function headersOf(request: SentRequest | undefined): Record<string, string> {
  return Object.fromEntries(new Headers(request?.init.headers).entries());
}

describe('The api client', () => {
  describe('The checkSession() call', () => {
    describe('When the api answers', () => {
      let sent: Exchange;
      beforeEach(async () => {
        sent = exchange(() => jsonResponse(OK, { ocr: 'ready' }));
        await createApiClient(sent.fetchFromApi, ignoreUnauthorized).checkSession();
      });

      it('should ask for the status of the api', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => `${init.method} ${path}`),
          ['GET /api/status'],
        );
      });

      it('should send the session cookie of the api alone, and keep no cached answer', () => {
        assert.deepEqual(
          { credentials: sent.requests[0]?.init.credentials, cache: sent.requests[0]?.init.cache },
          { credentials: 'same-origin', cache: 'no-store' },
        );
      });

      it('should not send the header that guards the changes of state, since it changes nothing', () => {
        assert.deepEqual(headersOf(sent.requests[0]), { accept: 'application/json' });
      });
    });

    describe('When the api no longer knows the session', () => {
      let act: () => Promise<void>;
      beforeEach(() => {
        const client = createApiClient(
          exchange(() => jsonResponse(UNAUTHORIZED, { detail: 'unauthorized' })).fetchFromApi,
          ignoreUnauthorized,
        );
        act = () => client.checkSession();
      });

      it('should fail with its status and its detail', async () => {
        await assert.rejects(act(), { name: 'ApiError', status: UNAUTHORIZED, detail: 'unauthorized' });
      });
    });

    describe('When the api answers an error without a body it can read', () => {
      let act: () => Promise<void>;
      beforeEach(() => {
        const client = createApiClient(
          exchange(() => new Response('<html>Bad gateway</html>', { status: BAD_GATEWAY })).fetchFromApi,
          ignoreUnauthorized,
        );
        act = () => client.checkSession();
      });

      it('should fail with its status, an empty detail and a message that names the status', async () => {
        await assert.rejects(act(), {
          name: 'ApiError',
          status: BAD_GATEWAY,
          detail: '',
          message: `HTTP ${BAD_GATEWAY}`,
        });
      });
    });

    describe('When the api cannot be reached', () => {
      let act: () => Promise<void>;
      beforeEach(() => {
        const client = createApiClient(async () => {
          throw new TypeError('fetch failed');
        }, ignoreUnauthorized);
        act = () => client.checkSession();
      });

      it('should fail with a network failure, whatever the browser threw', async () => {
        await assert.rejects(act(), { name: 'NetworkError', message: 'Network error' });
      });
    });
  });

  describe('The signIn() call', () => {
    describe('When the api accepts the token', () => {
      let sent: Exchange;
      beforeEach(async () => {
        sent = exchange(noContent);
        await createApiClient(sent.fetchFromApi, ignoreUnauthorized).signIn(TOKEN);
      });

      it('should post the token as JSON to the session of the api', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => ({ method: init.method, path, body: init.body })),
          [{ method: 'POST', path: '/api/session', body: JSON.stringify({ token: TOKEN }) }],
        );
      });

      it('should send the header that guards the changes of state, with the type of its body', () => {
        assert.deepEqual(headersOf(sent.requests[0]), {
          accept: 'application/json',
          'content-type': 'application/json',
          'x-scanmylib': '1',
        });
      });
    });

    describe('When the api refuses a request whose body it cannot validate', () => {
      let act: () => Promise<void>;
      beforeEach(() => {
        const body = { detail: [{ msg: 'Field required' }, { msg: 'String too short' }] };
        const client: SessionServer = createApiClient(
          exchange(() => jsonResponse(UNPROCESSABLE, body)).fetchFromApi,
          ignoreUnauthorized,
        );
        act = () => client.signIn(TOKEN);
      });

      it('should fail with the messages of its validation as its detail', async () => {
        await assert.rejects(act(), {
          name: 'ApiError',
          status: UNPROCESSABLE,
          detail: 'Field required; String too short',
        });
      });
    });
  });

  describe('When the api refuses the token of a sign-in', () => {
    let unauthorizedCount: number;
    beforeEach(async () => {
      unauthorizedCount = 0;
      const client = createApiClient(
        exchange(() => jsonResponse(UNAUTHORIZED, { detail: 'unauthorized' })).fetchFromApi,
        () => {
          unauthorizedCount += 1;
        },
      );
      await client.signIn(TOKEN).catch(() => {});
    });

    it('should not report an ended session, since the refusal only means a wrong token', () => {
      assert.equal(unauthorizedCount, 0);
    });
  });

  describe('When the api no longer knows the session of a signed-in call', () => {
    let unauthorizedCount: number;
    let act: () => Promise<ServerStatus>;
    beforeEach(async () => {
      unauthorizedCount = 0;
      const client = createApiClient(
        exchange(() => jsonResponse(UNAUTHORIZED, { detail: 'unauthorized' })).fetchFromApi,
        () => {
          unauthorizedCount += 1;
        },
      );
      act = () => client.readStatus();
      await act().catch(() => {});
    });

    it('should report that the session has ended, so that the browser goes back to the login', () => {
      assert.equal(unauthorizedCount, 1);
    });

    it('should still fail with the refusal', async () => {
      await assert.rejects(act(), { name: 'ApiError', status: UNAUTHORIZED });
    });
  });

  describe('The signOut() call', () => {
    describe('When the api closes the session', () => {
      let sent: Exchange;
      beforeEach(async () => {
        sent = exchange(noContent);
        await createApiClient(sent.fetchFromApi, ignoreUnauthorized).signOut();
      });

      it('should delete the session of the api, without a body', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => ({ method: init.method, path, body: init.body })),
          [{ method: 'DELETE', path: '/api/session', body: undefined }],
        );
      });

      it('should send the header that guards the changes of state', () => {
        assert.deepEqual(headersOf(sent.requests[0]), { accept: 'application/json', 'x-scanmylib': '1' });
      });
    });
  });
  describe('The readStatus() call', () => {
    describe('When the api answers its status', () => {
      let sent: Exchange;
      let status: ServerStatus;
      beforeEach(async () => {
        sent = exchange(() =>
          jsonResponse(OK, {
            version: '0.2.3',
            ocr: { reachable: true, state: 'ready', backend: 'vllm', last_error: null, gpu: null },
            queue: { queued: 0, processing: 0, error: 0, done: 7 },
            library_dir: '/library',
          }),
        );
        status = await createApiClient(sent.fetchFromApi, ignoreUnauthorized).readStatus();
      });

      it('should ask for the status of the api', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => `${init.method} ${path}`),
          ['GET /api/status'],
        );
      });

      it('should give the decoded status', () => {
        assert.deepEqual(status.queue, { queuedCount: 0, processingCount: 0, errorCount: 0, doneCount: 7 });
      });
    });

    describe('When the api answers a body that is not JSON', () => {
      let act: () => Promise<ServerStatus>;
      beforeEach(() => {
        const client = createApiClient(
          exchange(() => new Response('<html>Hello</html>', { status: OK })).fetchFromApi,
          ignoreUnauthorized,
        );
        act = () => client.readStatus();
      });

      it('should refuse its shape', async () => {
        await assert.rejects(act(), { name: 'ResponseShapeError' });
      });
    });

    describe('When the api cannot be reached', () => {
      let act: () => Promise<ServerStatus>;
      beforeEach(() => {
        const client = createApiClient(async () => {
          throw new TypeError('fetch failed');
        }, ignoreUnauthorized);
        act = () => client.readStatus();
      });

      it('should fail with a network failure, so that the header says the server is unreachable', async () => {
        await assert.rejects(act(), { name: 'NetworkError' });
      });
    });
  });

  describe('The listDocuments() call', () => {
    describe('When the api lists the documents', () => {
      const screen = new AbortController();
      let sent: Exchange;
      let documents: DocumentSummary[];
      beforeEach(async () => {
        sent = exchange(() => jsonResponse(OK, { documents: [documentBody()] }));
        documents = await createApiClient(sent.fetchFromApi, ignoreUnauthorized).listDocuments(screen.signal);
      });

      it('should give the request the signal of the screen, so that the browser cancels it when the screen is left', () => {
        assert.equal(sent.requests[0]?.init.signal, screen.signal);
      });

      it('should ask for the documents of the library', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => `${init.method} ${path}`),
          ['GET /api/documents'],
        );
      });

      it('should give the decoded documents', () => {
        assert.deepEqual(
          documents.map((document) => document.title),
          ['Example Book'],
        );
      });
    });

    describe('When the screen that asked is left before the answer', () => {
      let act: () => Promise<DocumentSummary[]>;
      beforeEach(() => {
        const leaving = new AbortController();
        const client = createApiClient(async () => {
          leaving.abort();
          throw new DOMException('The operation was aborted.', 'AbortError');
        }, ignoreUnauthorized);
        act = () => client.listDocuments(leaving.signal);
      });

      it('should fail with the abort, not with a network failure that the screen would show', async () => {
        await assert.rejects(act(), { name: 'AbortError' });
      });
    });
  });

  describe('The createDocument() call', () => {
    const fields = { title: 'Example Book', author: 'Jane Doe', kind: 'book', unwarp: true };

    describe('When the api creates the document', () => {
      let sent: Exchange;
      let document: DocumentSummary;
      beforeEach(async () => {
        sent = exchange(() => jsonResponse(OK, documentBody()));
        document = await createApiClient(sent.fetchFromApi, ignoreUnauthorized).createDocument(DOCUMENT_ID, fields);
      });

      it('should put the fields as JSON at the id the browser chose, so that a request sent again creates no second document', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => ({ method: init.method, path, body: init.body })),
          [{ method: 'PUT', path: `/api/documents/${DOCUMENT_ID}`, body: JSON.stringify(fields) }],
        );
      });

      it('should send the header that guards the changes of state', () => {
        assert.equal(headersOf(sent.requests[0])['x-scanmylib'], '1');
      });

      it('should give the decoded document', () => {
        assert.equal(document.id, DOCUMENT_ID);
      });
    });
  });

  describe('The readPairing() call', () => {
    describe('When the api answers the pairing', () => {
      const screen = new AbortController();
      let sent: Exchange;
      let pairing: PairingDetails;
      beforeEach(async () => {
        sent = exchange(() =>
          jsonResponse(OK, {
            url: 'http://192.168.1.10:8765',
            token: 'EXAMPLE-TOKEN',
            pair_uri: 'scanmylib://pair',
            apk_available: false,
            apk_url: 'http://192.168.1.10:8765/download/scanmylib.apk',
          }),
        );
        pairing = await createApiClient(sent.fetchFromApi, ignoreUnauthorized).readPairing(screen.signal);
      });

      it('should ask for the pairing of the api, with the signal of the screen', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => ({ request: `${init.method} ${path}`, signal: init.signal })),
          [{ request: 'GET /api/pairing', signal: screen.signal }],
        );
      });

      it('should give the decoded pairing', () => {
        assert.equal(pairing.isApkAvailable, false);
      });
    });
  });

  describe('The addresses that the pairing screen shows as they are', () => {
    let addresses: string[];
    beforeEach(() => {
      const client = createApiClient(exchange(noContent).fetchFromApi, ignoreUnauthorized);
      addresses = [client.pairingQrCodeUrl, client.apkQrCodeUrl, client.apkDownloadUrl];
    });

    it('should name the QR codes of the api and the download of the app', () => {
      assert.deepEqual(addresses, ['/api/pairing/qr.svg', '/api/pairing/apk-qr.svg', '/download/scanmylib.apk']);
    });
  });
});
