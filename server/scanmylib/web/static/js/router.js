/**
 * Hash routing: #/ (library), #/documents/<id>, #/documents/<id>/read,
 * #/pages/<id>, #/pairing and #/login.
 */

const UUID = '([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})';

const ROUTES = [
  { name: 'library', pattern: /^\/$/ },
  { name: 'document', pattern: new RegExp(`^/documents/${UUID}$`) },
  { name: 'reader', pattern: new RegExp(`^/documents/${UUID}/read$`) },
  { name: 'page', pattern: new RegExp(`^/pages/${UUID}$`) },
  { name: 'pairing', pattern: /^\/pairing$/ },
  { name: 'login', pattern: /^\/login$/ },
];

export const paths = {
  library: () => '/',
  document: (id) => `/documents/${id}`,
  reader: (id) => `/documents/${id}/read`,
  page: (id) => `/pages/${id}`,
  pairing: () => '/pairing',
  login: () => '/login',
};

/** `href` value for an in-app link. */
export function href(path) {
  return `#${path}`;
}

/** Parses the current hash into `{ name, path, id }`; unknown paths give `notFound`. */
export function currentRoute() {
  const path = location.hash.replace(/^#/, '') || '/';
  for (const { name, pattern } of ROUTES) {
    const match = pattern.exec(path);
    if (match) return { name, path, id: match[1]?.toLowerCase() ?? null };
  }
  return { name: 'notFound', path, id: null };
}

let routeListener = null;

/** Calls `listener(route)` now and on every navigation. */
export function startRouter(listener) {
  routeListener = listener;
  window.addEventListener('hashchange', () => routeListener(currentRoute()));
  routeListener(currentRoute());
}

/**
 * Goes to an in-app path. With `replace`, the current history entry is
 * replaced (used for redirects, so that "Back" does not bounce).
 */
export function navigate(path, { replace = false } = {}) {
  const hash = href(path);
  if (replace) {
    history.replaceState(null, '', hash);
    routeListener?.(currentRoute());
  } else if (location.hash === hash) {
    routeListener?.(currentRoute());
  } else {
    location.hash = hash;
  }
}

/**
 * Reads and removes a login token passed as "#token=…" (pairing links).
 * The fragment never reaches the server; it is stripped from the address bar
 * and from the history entry before anything else happens.
 */
export function takeTokenFromUrl() {
  const match = /^#token=([^&]*)/.exec(location.hash);
  if (!match) return null;
  history.replaceState(null, '', `${location.pathname}${location.search}${href(paths.library())}`);
  try {
    return decodeURIComponent(match[1]).trim() || null;
  } catch {
    return null;
  }
}
