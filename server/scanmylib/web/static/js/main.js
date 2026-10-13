/**
 * ScanMyLib web UI — entry point.
 *
 * Translates the static text of index.html (lib/i18n.js), then wires the
 * session (login, "#token=…" links, logout, expired sessions), the router,
 * the status monitor behind the header badge, and the screens. Each screen is
 * a `mount(root, context)` function that may return a cleanup function;
 * `context.signal` is aborted when the user leaves the screen.
 */
import { ApiError, onUnauthorized } from './api.js';
import { confirmDialog } from './components/dialogs.js';
import { mountBanners, mountEngineStatus } from './components/engine-status.js';
import { toast } from './components/toast.js';
import { errorMessage } from './lib/errors.js';
import { localizeDocument, t, tn } from './lib/i18n.js';
import { currentRoute, navigate, paths, startRouter, takeTokenFromUrl } from './router.js';
import { checkSession, probablySignedIn, rememberSignedIn, signIn, signOut } from './session.js';
import { StatusMonitor } from './status.js';
import { uploads } from './uploads.js';
import { mountDocument } from './views/document.js';
import { mountLibrary } from './views/library.js';
import { mountLogin } from './views/login.js';
import { mountPage } from './views/page.js';
import { mountPairing } from './views/pairing.js';
import { mountReader } from './views/reader.js';

const SCREENS = {
  library: { mount: mountLibrary, section: 'library' },
  document: { mount: mountDocument, section: 'library' },
  reader: { mount: mountReader, section: 'library' },
  page: { mount: mountPage, section: 'library' },
  pairing: { mount: mountPairing, section: 'pairing' },
};

const main = document.getElementById('main');
const header = document.getElementById('app-header');
const monitor = new StatusMonitor();

const session = {
  authenticated: false,
  /** Path to open after logging in. */
  returnTo: null,
  /** Explanation shown on the login screen (expired session, bad link…). */
  loginMessage: null,
};

let leaveScreen = null;
let firstRender = true;

function setTitle(title) {
  document.title = title ? `${title} · ScanMyLib` : 'ScanMyLib';
}

function highlightNavigation(section) {
  for (const link of header.querySelectorAll('[data-section]')) {
    if (link.dataset.section === section) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
}

function render(route) {
  leaveScreen?.();
  leaveScreen = null;

  if (!session.authenticated && route.name !== 'login') {
    session.returnTo = route.name === 'notFound' ? null : route.path;
    navigate(paths.login(), { replace: true });
    return;
  }
  if (session.authenticated && (route.name === 'login' || route.name === 'notFound')) {
    navigate(paths.library(), { replace: true });
    return;
  }

  header.hidden = !session.authenticated;
  // Screen readers start reading the new screen; Tab continues from there.
  if (!firstRender) main.focus({ preventScroll: true });
  firstRender = false;
  window.scrollTo(0, 0);

  const controller = new AbortController();
  const context = { route, signal: controller.signal, monitor, setTitle };
  let cleanup;
  if (route.name === 'login') {
    highlightNavigation(null);
    mountLogin(main, { ...context, onSignedIn, message: session.loginMessage });
    session.loginMessage = null;
  } else {
    const screen = SCREENS[route.name];
    highlightNavigation(screen.section);
    cleanup = screen.mount(main, context);
  }
  leaveScreen = () => {
    controller.abort();
    cleanup?.();
  };
}

/** Called by the login screen once the session cookie is set. */
function onSignedIn() {
  session.authenticated = true;
  monitor.start();
  const target = session.returnTo ?? paths.library();
  session.returnTo = null;
  navigate(target, { replace: true });
}

function onSessionExpired() {
  if (!session.authenticated) return;
  session.authenticated = false;
  session.loginMessage = t('Your session has expired: please sign in again.');
  rememberSignedIn(false);
  monitor.stop();
  const route = currentRoute();
  session.returnTo = route.name === 'login' ? null : route.path;
  navigate(paths.login(), { replace: true });
}

/** Checks an existing session cookie; a server failure is explained on the login screen. */
async function restoreSession() {
  try {
    return await checkSession();
  } catch (error) {
    session.loginMessage = errorMessage(error, t('The ScanMyLib server is not responding correctly.'));
    return false;
  }
}

/**
 * Signs in with the token of a "#token=…" link (already stripped from the
 * address bar by takeTokenFromUrl). A still-valid session wins over a stale link.
 */
async function signInWithLink(token) {
  if (!token) return;
  try {
    await signIn(token);
    session.authenticated = true;
    session.loginMessage = null;
  } catch (error) {
    if (probablySignedIn() && await restoreSession()) {
      session.authenticated = true;
      return;
    }
    session.authenticated = false;
    session.loginMessage = error instanceof ApiError && error.status === 401
      ? t('The sign-in link contains an invalid or expired token.')
      : errorMessage(error, t('Could not sign in.'));
  }
}

function onRoute(route) {
  if (!location.hash.startsWith('#token=')) {
    render(route);
    return;
  }
  // A "#token=…" link opened while the app is already running.
  signInWithLink(takeTokenFromUrl()).then(() => {
    if (session.authenticated) monitor.start();
    else monitor.stop();
    render(currentRoute());
  });
}

async function logout() {
  if (uploads.isBusy()) {
    const confirmed = await confirmDialog({
      title: t('Sign out now?'),
      message: t('Photos are still being uploaded: they will fail if you sign out.'),
      confirmLabel: t('Sign out'),
      danger: true,
    });
    if (!confirmed) return;
  }
  try {
    await signOut();
  } catch (error) {
    if (!(error instanceof ApiError)) {
      toast(errorMessage(error, t('Could not sign out.')), { tone: 'error' });
      return;
    }
    rememberSignedIn(false);
  }
  session.authenticated = false;
  monitor.stop();
  navigate(paths.login());
}

function reportSettledUploads({ detail: counts }) {
  const sent = tn('{count} photo sent', '{count} photos sent', counts.done);
  const failed = counts.failed + counts.rejected;
  if (failed) {
    const failures = tn('{count} failure', '{count} failures', failed);
    toast(t('{sent}, {failures}: see the document’s upload list.', { sent, failures }), { tone: 'error' });
  } else {
    toast(t('{sent}: OCR will process them.', { sent }), { tone: 'success' });
  }
}

async function boot() {
  // Before anything else, so that the secret never lingers in the address bar or history.
  const linkToken = takeTokenFromUrl();
  localizeDocument();

  mountEngineStatus(document.getElementById('engine-status'), monitor);
  mountBanners(document.getElementById('banners'), monitor);
  document.getElementById('logout-button').addEventListener('click', logout);
  document.getElementById('skip-link').addEventListener('click', () => main.focus());
  onUnauthorized(onSessionExpired);
  uploads.addEventListener('settled', reportSettledUploads);
  window.addEventListener('beforeunload', (event) => {
    if (!uploads.isBusy()) return;
    event.preventDefault();
    event.returnValue = ''; // still required by some browsers to show the prompt
  });

  if (linkToken) {
    await signInWithLink(linkToken);
  } else if (probablySignedIn()) {
    session.authenticated = await restoreSession();
  }
  if (session.authenticated) monitor.start();
  startRouter(onRoute);
}

boot();
