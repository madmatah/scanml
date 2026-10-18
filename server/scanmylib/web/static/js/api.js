/**
 * Client for the ScanMyLib HTTP API (docs/API.md).
 *
 * The browser authenticates with the HttpOnly session cookie obtained from
 * POST /api/session. Every state-changing request also carries the
 * `X-ScanMyLib: 1` header that the server requires as a CSRF guard.
 */

const CSRF_HEADER = 'X-ScanMyLib';
const SESSION_PATH = '/api/session';

/** The server answered with an error status. */
export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

/** The server could not be reached at all (stopped, restarting, offline…). */
export class NetworkError extends Error {
  constructor() {
    super('Network error');
    this.name = 'NetworkError';
  }
}

const unauthorizedListeners = new Set();

/** Registers a callback run whenever an authenticated request gets a 401. */
export function onUnauthorized(listener) {
  unauthorizedListeners.add(listener);
}

function notifyUnauthorized() {
  for (const listener of unauthorizedListeners) listener();
}

/** FastAPI's `detail` is a string, or a list of validation errors. */
function detailFrom(body) {
  const detail = body?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail
      .map((item) => item?.msg)
      .filter(Boolean)
      .join('; ');
  return '';
}

function failure(status, body, path) {
  // A 401 on the login request itself only means "wrong token".
  if (status === 401 && path !== SESSION_PATH) notifyUnauthorized();
  return new ApiError(status, detailFrom(body));
}

async function request(method, path, { json, signal } = {}) {
  const headers = { Accept: 'application/json' };
  if (method !== 'GET') headers[CSRF_HEADER] = '1';
  const init = { method, headers, signal, credentials: 'same-origin', cache: 'no-store' };
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(json);
  }

  let response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new NetworkError();
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw failure(response.status, body, path);
  }
  return response.status === 204 ? null : response.json();
}

const enc = encodeURIComponent;

export const api = {
  login: (token) => request('POST', SESSION_PATH, { json: { token } }),
  logout: () => request('DELETE', SESSION_PATH),

  status: (options) => request('GET', '/api/status', options),
  pairing: (options) => request('GET', '/api/pairing', options),

  listDocuments: async (options) => (await request('GET', '/api/documents', options)).documents,
  getDocument: (id, options) => request('GET', `/api/documents/${enc(id)}`, options),
  /** Sanitized HTML of the whole document, pages in reading order. */
  getDocumentHtml: async (id, options) => (await request('GET', `/api/documents/${enc(id)}/html`, options)).html,
  /** Creates the document `id` (a client-generated UUID; PUT is idempotent). */
  createDocument: (id, fields) => request('PUT', `/api/documents/${enc(id)}`, { json: fields }),
  updateDocument: (id, fields) => request('PATCH', `/api/documents/${enc(id)}`, { json: fields }),
  deleteDocument: (id) => request('DELETE', `/api/documents/${enc(id)}`),
  /**
   * Sets the reading order: `pageIds` lists exactly the pages that are in the
   * document, in the wanted order (409 when that set changed meanwhile).
   * Resolves with the document and its pages, like getDocument.
   */
  reorderPages: (id, pageIds) => request('PUT', `/api/documents/${enc(id)}/order`, { json: { page_ids: pageIds } }),
  /** Forgets the places chosen by hand: back to the automatic order. Resolves with the document. */
  resetPageOrder: (id) => request('DELETE', `/api/documents/${enc(id)}/order`),

  getPage: (id, options) => request('GET', `/api/pages/${enc(id)}`, options),
  getPageHtml: async (id, options) => (await request('GET', `/api/pages/${enc(id)}/html`, options)).html,
  updatePage: (id, fields) => request('PATCH', `/api/pages/${enc(id)}`, { json: fields }),
  reprocessPage: (id) => request('POST', `/api/pages/${enc(id)}/reprocess`),
  deletePage: (id) => request('DELETE', `/api/pages/${enc(id)}`),
};

/**
 * Adds a version to an image URL. Browsers reuse an image already loaded in
 * the page for the same URL without revalidating it, so images regenerated in
 * place by the server (thumbnails after a rotation, illustrations after a new
 * OCR) need a URL that changes with them.
 */
export function versionedUrl(url, version) {
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}v=${encodeURIComponent(version)}`;
}

/** URLs used directly by links and images (authenticated by the cookie). */
export const links = {
  markdown: (id) => `/api/documents/${enc(id)}/markdown`,
  exportZip: (id, withScans) => `/api/documents/${enc(id)}/export.zip?scans=${withScans ? 1 : 0}`,
  pairingQr: '/api/pairing/qr.svg',
  apkQr: '/api/pairing/apk-qr.svg',
  apk: '/download/scanmylib.apk',
};

/**
 * Uploads one photo as a new page of a document; resolves with the Page.
 *
 * Uses XMLHttpRequest because fetch() cannot report upload progress. The
 * server is idempotent on `page_id`, so a retried upload is safe.
 */
export function uploadPage(documentId, { file, pageId, sessionId, seq, capturedAt }, { onProgress } = {}) {
  const path = `/api/documents/${enc(documentId)}/pages`;
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', path);
    xhr.responseType = 'json';
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.setRequestHeader(CSRF_HEADER, '1');
    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total);
    });
    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response);
      } else {
        reject(failure(xhr.status, xhr.response, path));
      }
    });
    xhr.addEventListener('error', () => reject(new NetworkError()));
    xhr.addEventListener('timeout', () => reject(new NetworkError()));

    const form = new FormData();
    form.append('page_id', pageId);
    form.append('session_id', sessionId);
    form.append('seq', String(seq));
    form.append('captured_at', capturedAt);
    form.append('file', file, file.name);
    xhr.send(form);
  });
}
