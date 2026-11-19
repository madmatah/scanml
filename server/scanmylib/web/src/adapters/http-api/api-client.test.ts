import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import type { PageChanges } from '../../application/page-store.ts';
import type { SessionServer } from '../../application/session.ts';
import type { DocumentDetails, DocumentWithPages } from '../../domain/document-details.ts';
import type { DocumentSummary } from '../../domain/document-summary.ts';
import type { PageDetails } from '../../domain/page-details.ts';
import type { PairingDetails } from '../../domain/pairing-details.ts';
import type { ServerStatus } from '../../domain/server-status.ts';
import { createApiClient, type Fetch } from './api-client.ts';

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
const PAGE_ID = 'de215798-031a-4b20-a867-49c12e3baabe';
const NO_CONTENT = 204;
const OK = 200;
const ACCEPTED = 202;
const UNAUTHORIZED = 401;
const NOT_FOUND = 404;
const CONFLICT = 409;
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

function documentDetailsBody(): Record<string, unknown> {
  return {
    ...documentBody(),
    slug: 'example-book',
    notes: '',
    unwarp: true,
    folder: '/data/USER/scanmylib/library/example-book',
  };
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

function pageBody(): Record<string, unknown> {
  return {
    id: PAGE_ID,
    document_id: DOCUMENT_ID,
    key: 'p0011',
    session_id: null,
    seq: null,
    captured_at: '2026-11-14T15:31:00+00:00',
    uploaded_at: '2026-11-14T15:31:05+00:00',
    status: 'queued',
    error: null,
    number: null,
    number_end: null,
    page_label: null,
    number_source: null,
    detected_numbers: [],
    hint_number: null,
    manual_number: null,
    excluded: false,
    duplicate_of: null,
    placement: null,
    rotation: 0,
    width: 800,
    height: 1011,
    ocr: null,
    image_url: `/api/pages/${PAGE_ID}/image`,
    markdown: '',
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

  describe('The readDocument() call', () => {
    describe('When the api answers the document with its pages', () => {
      const screen = new AbortController();
      let sent: Exchange;
      let document: DocumentWithPages;
      beforeEach(async () => {
        sent = exchange(() => jsonResponse(OK, { ...documentDetailsBody(), pages: [] }));
        document = await createApiClient(sent.fetchFromApi, ignoreUnauthorized).readDocument(
          DOCUMENT_ID,
          screen.signal,
        );
      });

      it('should ask for the document, with the signal of the screen', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => ({ request: `${init.method} ${path}`, signal: init.signal })),
          [{ request: `GET /api/documents/${DOCUMENT_ID}`, signal: screen.signal }],
        );
      });

      it('should give the decoded document', () => {
        assert.deepEqual({ slug: document.slug, pages: document.pages }, { slug: 'example-book', pages: [] });
      });
    });

    describe('When the document does not exist', () => {
      let act: () => Promise<DocumentWithPages>;
      beforeEach(() => {
        const client = createApiClient(
          exchange(() => jsonResponse(NOT_FOUND, { detail: 'document not found' })).fetchFromApi,
          ignoreUnauthorized,
        );
        act = () => client.readDocument(DOCUMENT_ID, new AbortController().signal);
      });

      it('should fail with its status, which the screen tells apart from other failures', async () => {
        await assert.rejects(act(), { name: 'ApiError', status: NOT_FOUND });
      });
    });
  });

  describe('The readDocumentHtml() call', () => {
    describe('When the api answers the HTML of the document', () => {
      const screen = new AbortController();
      let sent: Exchange;
      let sanitizedHtml: string;
      beforeEach(async () => {
        sent = exchange(() => jsonResponse(OK, { html: '<h1>Example Book</h1>' }));
        sanitizedHtml = await createApiClient(sent.fetchFromApi, ignoreUnauthorized).readDocumentHtml(
          DOCUMENT_ID,
          screen.signal,
        );
      });

      it('should ask for the HTML of the document, with the signal of the screen', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => ({ request: `${init.method} ${path}`, signal: init.signal })),
          [{ request: `GET /api/documents/${DOCUMENT_ID}/html`, signal: screen.signal }],
        );
      });

      it('should give the HTML as the api wrote it', () => {
        assert.equal(sanitizedHtml, '<h1>Example Book</h1>');
      });
    });
  });

  describe('The updateDocument() call', () => {
    const fields = { title: 'Example Book', author: 'Jane Doe', kind: 'book', unwarp: false, notes: 'Second edition' };

    describe('When the api saves the changes', () => {
      let sent: Exchange;
      let document: DocumentDetails;
      beforeEach(async () => {
        sent = exchange(() => jsonResponse(OK, documentDetailsBody()));
        document = await createApiClient(sent.fetchFromApi, ignoreUnauthorized).updateDocument(DOCUMENT_ID, fields);
      });

      it('should patch the document with the fields as JSON', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => ({ method: init.method, path, body: init.body })),
          [{ method: 'PATCH', path: `/api/documents/${DOCUMENT_ID}`, body: JSON.stringify(fields) }],
        );
      });

      it('should send the header that guards the changes of state', () => {
        assert.equal(headersOf(sent.requests[0])['x-scanmylib'], '1');
      });

      it('should give the decoded document', () => {
        assert.equal(document.folder, '/data/USER/scanmylib/library/example-book');
      });
    });
  });

  describe('The deleteDocument() call', () => {
    describe('When the api moves the document to the trash', () => {
      let sent: Exchange;
      beforeEach(async () => {
        sent = exchange(noContent);
        await createApiClient(sent.fetchFromApi, ignoreUnauthorized).deleteDocument(DOCUMENT_ID);
      });

      it('should delete the document, with the header that guards the changes of state', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => ({
            request: `${init.method} ${path}`,
            guard: headersOf({ path, init })['x-scanmylib'],
          })),
          [{ request: `DELETE /api/documents/${DOCUMENT_ID}`, guard: '1' }],
        );
      });
    });
  });

  describe('The reorderPages() call', () => {
    const pageIds = ['3c1f0e2a-1111-4c0d-8d3e-0a1b2c3d4e5f', '3c1f0e2a-2222-4c0d-8d3e-0a1b2c3d4e5f'];

    describe('When the api saves the new order', () => {
      let sent: Exchange;
      let document: DocumentWithPages;
      beforeEach(async () => {
        sent = exchange(() => jsonResponse(OK, { ...documentDetailsBody(), pages: [] }));
        document = await createApiClient(sent.fetchFromApi, ignoreUnauthorized).reorderPages(DOCUMENT_ID, pageIds);
      });

      it('should put the ids of the reading order, in their new order, with the header that guards the changes', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => ({
            request: `${init.method} ${path}`,
            body: init.body,
            guard: headersOf({ path, init })['x-scanmylib'],
          })),
          [
            {
              request: `PUT /api/documents/${DOCUMENT_ID}/order`,
              body: JSON.stringify({ page_ids: pageIds }),
              guard: '1',
            },
          ],
        );
      });

      it('should give the decoded document', () => {
        assert.deepEqual({ slug: document.slug, pages: document.pages }, { slug: 'example-book', pages: [] });
      });
    });

    describe('When pages joined or left the reading order meanwhile', () => {
      let act: () => Promise<DocumentWithPages>;
      beforeEach(() => {
        const client = createApiClient(
          exchange(() => jsonResponse(CONFLICT, { detail: 'page set changed' })).fetchFromApi,
          ignoreUnauthorized,
        );
        act = () => client.reorderPages(DOCUMENT_ID, pageIds);
      });

      it('should fail with its status, which the organizer tells apart from other failures', async () => {
        await assert.rejects(act(), { name: 'ApiError', status: CONFLICT });
      });
    });
  });

  describe('The resetPageOrder() call', () => {
    describe('When the api restores the automatic order', () => {
      let sent: Exchange;
      let document: DocumentWithPages;
      beforeEach(async () => {
        sent = exchange(() => jsonResponse(OK, { ...documentDetailsBody(), pages: [] }));
        document = await createApiClient(sent.fetchFromApi, ignoreUnauthorized).resetPageOrder(DOCUMENT_ID);
      });

      it('should delete the order chosen by hand, with the header that guards the changes', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => ({
            request: `${init.method} ${path}`,
            body: init.body,
            guard: headersOf({ path, init })['x-scanmylib'],
          })),
          [{ request: `DELETE /api/documents/${DOCUMENT_ID}/order`, body: undefined, guard: '1' }],
        );
      });

      it('should give the decoded document', () => {
        assert.equal(document.slug, 'example-book');
      });
    });
  });

  describe('The readPage() call', () => {
    describe('When the api answers the page', () => {
      const screen = new AbortController();
      let sent: Exchange;
      let page: PageDetails;
      beforeEach(async () => {
        sent = exchange(() => jsonResponse(OK, pageBody()));
        page = await createApiClient(sent.fetchFromApi, ignoreUnauthorized).readPage(PAGE_ID, screen.signal);
      });

      it('should ask for the page, with the signal of the screen', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => ({ request: `${init.method} ${path}`, signal: init.signal })),
          [{ request: `GET /api/pages/${PAGE_ID}`, signal: screen.signal }],
        );
      });

      it('should give the decoded page', () => {
        assert.deepEqual(
          { documentId: page.documentId, markdown: page.markdown },
          { documentId: DOCUMENT_ID, markdown: '' },
        );
      });
    });

    describe('When the page does not exist', () => {
      let act: () => Promise<PageDetails>;
      beforeEach(() => {
        const client = createApiClient(
          exchange(() => jsonResponse(NOT_FOUND, { detail: 'page not found' })).fetchFromApi,
          ignoreUnauthorized,
        );
        act = () => client.readPage(PAGE_ID, new AbortController().signal);
      });

      it('should fail with its status, which the screen tells apart from other failures', async () => {
        await assert.rejects(act(), { name: 'ApiError', status: NOT_FOUND });
      });
    });
  });

  describe('The readPageHtml() call', () => {
    describe('When the api answers the HTML of the page', () => {
      const screen = new AbortController();
      let sent: Exchange;
      let sanitizedHtml: string;
      beforeEach(async () => {
        sent = exchange(() => jsonResponse(OK, { html: '<p>Example text.</p>' }));
        sanitizedHtml = await createApiClient(sent.fetchFromApi, ignoreUnauthorized).readPageHtml(
          PAGE_ID,
          screen.signal,
        );
      });

      it('should ask for the HTML of the page, with the signal of the screen', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => ({ request: `${init.method} ${path}`, signal: init.signal })),
          [{ request: `GET /api/pages/${PAGE_ID}/html`, signal: screen.signal }],
        );
      });

      it('should give the HTML as the api wrote it', () => {
        assert.equal(sanitizedHtml, '<p>Example text.</p>');
      });
    });
  });

  describe('The updatePage() call', () => {
    const rows: { situation: string; changes: PageChanges; expectedBody: Record<string, unknown> }[] = [
      {
        situation: 'When a number is typed by hand',
        changes: { manualNumber: 42 },
        expectedBody: { manual_number: 42 },
      },
      {
        situation: 'When the number typed by hand is cleared',
        changes: { manualNumber: null },
        expectedBody: { manual_number: null },
      },
      { situation: 'When the page is excluded', changes: { isExcluded: true }, expectedBody: { excluded: true } },
      { situation: 'When the page is turned', changes: { rotation: 270 }, expectedBody: { rotation: 270 } },
    ];

    for (const { situation, changes, expectedBody } of rows) {
      describe(situation, () => {
        let sent: Exchange;
        beforeEach(async () => {
          sent = exchange(() => jsonResponse(OK, pageBody()));
          await createApiClient(sent.fetchFromApi, ignoreUnauthorized).updatePage(PAGE_ID, changes);
        });

        it('should patch the page with that change alone, in the names of the api, and the guard header', () => {
          assert.deepEqual(
            sent.requests.map(({ path, init }) => ({
              request: `${init.method} ${path}`,
              body: init.body,
              guard: headersOf({ path, init })['x-scanmylib'],
            })),
            [{ request: `PATCH /api/pages/${PAGE_ID}`, body: JSON.stringify(expectedBody), guard: '1' }],
          );
        });
      });
    }
  });

  describe('The readPageAgain() call', () => {
    describe('When the api queues the page again', () => {
      let sent: Exchange;
      beforeEach(async () => {
        sent = exchange(() => jsonResponse(ACCEPTED, pageBody()));
        await createApiClient(sent.fetchFromApi, ignoreUnauthorized).readPageAgain(PAGE_ID);
      });

      it('should ask the api to read its text again, with the header that guards the changes of state', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => ({
            request: `${init.method} ${path}`,
            guard: headersOf({ path, init })['x-scanmylib'],
          })),
          [{ request: `POST /api/pages/${PAGE_ID}/reprocess`, guard: '1' }],
        );
      });
    });
  });

  describe('The deletePage() call', () => {
    describe('When the api moves the page to the trash', () => {
      let sent: Exchange;
      beforeEach(async () => {
        sent = exchange(noContent);
        await createApiClient(sent.fetchFromApi, ignoreUnauthorized).deletePage(PAGE_ID);
      });

      it('should delete the page, with the header that guards the changes of state', () => {
        assert.deepEqual(
          sent.requests.map(({ path, init }) => ({
            request: `${init.method} ${path}`,
            guard: headersOf({ path, init })['x-scanmylib'],
          })),
          [{ request: `DELETE /api/pages/${PAGE_ID}`, guard: '1' }],
        );
      });
    });
  });

  describe('The addresses of the exports of a document', () => {
    let addresses: string[];
    beforeEach(() => {
      const client = createApiClient(exchange(noContent).fetchFromApi, ignoreUnauthorized);
      addresses = [
        client.markdownUrl(DOCUMENT_ID),
        client.archiveUrl(DOCUMENT_ID, false),
        client.archiveUrl(DOCUMENT_ID, true),
      ];
    });

    it('should name its Markdown, and its archive with or without the original photos', () => {
      assert.deepEqual(addresses, [
        `/api/documents/${DOCUMENT_ID}/markdown`,
        `/api/documents/${DOCUMENT_ID}/export.zip?scans=0`,
        `/api/documents/${DOCUMENT_ID}/export.zip?scans=1`,
      ]);
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
