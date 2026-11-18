import { ApiError, NetworkError } from '../../application/api-errors.ts';
import type { DocumentCatalog } from '../../application/document-catalog.ts';
import type { ServerStatusSource } from '../../application/engine-status.ts';
import type { PairingSource } from '../../application/pairing-source.ts';
import type { SessionServer } from '../../application/session.ts';
import { decodeDocumentList, decodeDocumentSummary } from './document-summary-decoder.ts';
import { decodeErrorDetail } from './error-detail.ts';
import { decodePairingDetails } from './pairing-decoder.ts';
import { decodeServerStatus } from './server-status-decoder.ts';

export type Fetch = (path: string, init: RequestInit) => Promise<Response>;

export type ApiClient = SessionServer & ServerStatusSource & DocumentCatalog & PairingSource;

// The api refuses a request that changes state, authenticated by the session cookie, without this header: another page
// cannot add it without the api's consent (docs/API.md > Authentication).
const CSRF_HEADER = 'X-ScanMyLib';
const SESSION_PATH = '/api/session';
const STATUS_PATH = '/api/status';
const DOCUMENTS_PATH = '/api/documents';
const PAIRING_PATH = '/api/pairing';
const UNAUTHORIZED = 401;

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export function createApiClient(fetchFromApi: Fetch, onUnauthorized: () => void): ApiClient {
  async function request(method: string, path: string, json?: unknown, signal?: AbortSignal): Promise<Response> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (method !== 'GET') headers[CSRF_HEADER] = '1';
    const init: RequestInit = { method, headers, credentials: 'same-origin', cache: 'no-store' };
    if (json !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(json);
    }
    if (signal !== undefined) init.signal = signal;
    let response: Response;
    try {
      response = await fetchFromApi(path, init);
    } catch (failure) {
      // A request that its caller gave up is no failure of the network.
      if (signal?.aborted === true) throw failure;
      throw new NetworkError();
    }
    if (!response.ok) {
      // A 401 on the sign-in itself only refuses a token; elsewhere, the session this browser held has ended.
      if (response.status === UNAUTHORIZED && path !== SESSION_PATH) onUnauthorized();
      throw new ApiError(response.status, decodeErrorDetail(await readJson(response)));
    }
    return response;
  }

  return {
    pairingQrCodeUrl: `${PAIRING_PATH}/qr.svg`,
    apkQrCodeUrl: `${PAIRING_PATH}/apk-qr.svg`,
    apkDownloadUrl: '/download/scanmylib.apk',
    async checkSession() {
      await request('GET', STATUS_PATH);
    },
    async signIn(token) {
      await request('POST', SESSION_PATH, { token });
    },
    async signOut() {
      await request('DELETE', SESSION_PATH);
    },
    async readStatus() {
      return decodeServerStatus(await readJson(await request('GET', STATUS_PATH)));
    },
    async listDocuments(signal) {
      return decodeDocumentList(await readJson(await request('GET', DOCUMENTS_PATH, undefined, signal)));
    },
    async readPairing(signal) {
      return decodePairingDetails(await readJson(await request('GET', PAIRING_PATH, undefined, signal)));
    },
    async createDocument(id, fields) {
      // PUT with an id that the browser chose: a request sent again creates no second document.
      const path = `${DOCUMENTS_PATH}/${encodeURIComponent(id)}`;
      return decodeDocumentSummary(await readJson(await request('PUT', path, fields)));
    },
  };
}
