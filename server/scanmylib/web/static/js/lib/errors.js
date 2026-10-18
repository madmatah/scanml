import { ApiError, NetworkError } from '../api.js';
import { t } from './i18n.js';

/** User-facing message, in the UI language, for an error thrown by the API client. */
export function errorMessage(error, fallback = t('An unexpected error occurred.')) {
  if (error instanceof NetworkError) {
    return t('The ScanMyLib server is not responding. Check that it is running and that you are on the same network.');
  }
  if (error instanceof ApiError) {
    switch (error.status) {
      case 401:
        return t('Session expired: please sign in again.');
      case 404:
        return t('Item not found: it may have been deleted.');
      case 413:
        return t('File too large (40 MiB maximum).');
      case 415:
        return t('Unsupported format (JPEG, PNG or WebP only).');
      default:
        return error.detail ? `${fallback} (${error.detail})` : fallback;
    }
  }
  return fallback;
}

/** True for errors caused by aborting a request (the view was left). */
export function isAbort(error) {
  return error?.name === 'AbortError';
}
