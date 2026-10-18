/**
 * Browser session: signing in with the access token (login form or
 * "#token=…" link), signing out, and checking an existing session.
 *
 * The session cookie is HttpOnly, so scripts cannot see it. A non-secret
 * "signed in" flag in localStorage tells whether one probably exists: on a
 * first visit the UI then shows the login screen directly instead of probing
 * the API (and logging a 401 in the console).
 */
import { ApiError, api } from './api.js';

const SIGNED_IN_KEY = 'scanmylib.signed-in';

export function probablySignedIn() {
  try {
    return localStorage.getItem(SIGNED_IN_KEY) === '1';
  } catch {
    return true; // storage disabled: probe the server instead
  }
}

export function rememberSignedIn(signedIn) {
  try {
    if (signedIn) localStorage.setItem(SIGNED_IN_KEY, '1');
    else localStorage.removeItem(SIGNED_IN_KEY);
  } catch {
    // Storage disabled: the next visit will probe the server.
  }
}

/** Exchanges the access token for the session cookie. Throws ApiError(401) for a wrong token. */
export async function signIn(token) {
  await api.login(token);
  rememberSignedIn(true);
}

export async function signOut() {
  await api.logout();
  rememberSignedIn(false);
}

/**
 * Asks the server whether the session cookie is still valid. Resolves to
 * true or false; other failures (server down…) are thrown.
 */
export async function checkSession() {
  try {
    await api.status();
    return true;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      rememberSignedIn(false);
      return false;
    }
    throw error;
  }
}
