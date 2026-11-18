import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { createApiClient, type Fetch } from '../../../src/adapters/http-api/api-client.ts';
import type { SessionServer } from '../../../src/application/session.ts';
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
const NO_CONTENT = 204;
const OK = 200;
const UNAUTHORIZED = 401;
const UNPROCESSABLE = 422;
const BAD_GATEWAY = 502;

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

function headersOf(request: SentRequest | undefined): Record<string, string> {
  return Object.fromEntries(new Headers(request?.init.headers).entries());
}

describe('The api client', () => {
  describe('The checkSession() call', () => {
    describe('When the api answers', () => {
      let sent: Exchange;
      beforeEach(async () => {
        sent = exchange(() => jsonResponse(OK, { ocr: 'ready' }));
        await createApiClient(sent.fetchFromApi).checkSession();
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
        });
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
        await createApiClient(sent.fetchFromApi).signIn(TOKEN);
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
        const client: SessionServer = createApiClient(exchange(() => jsonResponse(UNPROCESSABLE, body)).fetchFromApi);
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

  describe('The signOut() call', () => {
    describe('When the api closes the session', () => {
      let sent: Exchange;
      beforeEach(async () => {
        sent = exchange(noContent);
        await createApiClient(sent.fetchFromApi).signOut();
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
        status = await createApiClient(sent.fetchFromApi).readStatus();
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
        const client = createApiClient(exchange(() => new Response('<html>Hello</html>', { status: OK })).fetchFromApi);
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
        });
        act = () => client.readStatus();
      });

      it('should fail with a network failure, so that the header says the server is unreachable', async () => {
        await assert.rejects(act(), { name: 'NetworkError' });
      });
    });
  });
});
