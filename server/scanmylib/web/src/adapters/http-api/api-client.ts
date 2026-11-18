import { ApiError, NetworkError } from '../../application/api-errors.ts';
import type { SessionServer } from '../../application/session.ts';
import { decodeErrorDetail } from './error-detail.ts';

export type Fetch = (path: string, init: RequestInit) => Promise<Response>;

// The api refuses a request that changes state, authenticated by the session cookie, without this header: another page
// cannot add it without the api's consent (docs/API.md > Authentication).
const CSRF_HEADER = 'X-ScanMyLib';
const SESSION_PATH = '/api/session';
const STATUS_PATH = '/api/status';

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export function createApiClient(fetchFromApi: Fetch): SessionServer {
  async function request(method: string, path: string, json?: unknown): Promise<void> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (method !== 'GET') headers[CSRF_HEADER] = '1';
    const init: RequestInit = { method, headers, credentials: 'same-origin', cache: 'no-store' };
    if (json !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(json);
    }
    let response: Response;
    try {
      response = await fetchFromApi(path, init);
    } catch {
      throw new NetworkError();
    }
    if (!response.ok) throw new ApiError(response.status, decodeErrorDetail(await readJson(response)));
  }

  return {
    checkSession: () => request('GET', STATUS_PATH),
    signIn: (token) => request('POST', SESSION_PATH, { token }),
    signOut: () => request('DELETE', SESSION_PATH),
  };
}
