import type { TFunction } from 'i18next';

import { ApiError } from '../../../application/api-errors.ts';
import type { SignedOutNotice } from '../../../application/session.ts';
import { errorMessage } from '../shell/error-message.ts';

export type LoginError =
  | { readonly reason: 'missing-token' }
  | { readonly reason: 'refused'; readonly failure: unknown };

const UNAUTHORIZED = 401;

export const loginErrorText = (t: TFunction, error: LoginError): string => {
  switch (error.reason) {
    case 'missing-token':
      return t('Enter the access token.');
    case 'refused':
      return error.failure instanceof ApiError && error.failure.status === UNAUTHORIZED
        ? t('Invalid access token. Check it and try again.')
        : errorMessage(t, error.failure, t('Could not sign in.'));
  }
};

export const signedOutNoticeText = (t: TFunction, notice: SignedOutNotice): string => {
  switch (notice.reason) {
    case 'expired':
      return t('Your session has expired: please sign in again.');
    case 'link-refused':
      return t('The sign-in link contains an invalid or expired token.');
    case 'link-failed':
      return errorMessage(t, notice.failure, t('Could not sign in.'));
    case 'check-failed':
      return errorMessage(t, notice.failure, t('The ScanMyLib server is not responding correctly.'));
  }
};
