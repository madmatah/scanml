import type { TFunction } from 'i18next';

import { ApiError, NetworkError } from '../../../application/api-errors.ts';

export function errorMessage(
  t: TFunction,
  failure: unknown,
  fallback: string = t('An unexpected error occurred.'),
): string {
  if (failure instanceof NetworkError) {
    return t('The ScanMyLib server is not responding. Check that it is running and that you are on the same network.');
  }
  if (!(failure instanceof ApiError)) return fallback;
  switch (failure.status) {
    case 401:
      return t('Session expired: please sign in again.');
    case 404:
      return t('Item not found: it may have been deleted.');
    case 413:
      return t('File too large (40 MiB maximum).');
    case 415:
      return t('Unsupported format (JPEG, PNG or WebP only).');
    default:
      return failure.detail === ''
        ? fallback
        : t('{{message}} ({{detail}})', { message: fallback, detail: failure.detail });
  }
}
