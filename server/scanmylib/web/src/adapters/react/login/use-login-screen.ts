import { type RefObject, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';

import type { Session, SignedOutNotice } from '../../../application/session.ts';
import { useDocumentTitle } from '../shell/use-document-title.ts';
import type { LoginError } from './login-messages.ts';

export interface LoginScreenState {
  readonly token: string;
  readonly isTokenShown: boolean;
  readonly isSigningIn: boolean;
  readonly error: LoginError | null;
  readonly notice: SignedOutNotice | null;
  readonly tokenInput: RefObject<HTMLInputElement | null>;
  readonly onTokenChange: (token: string) => void;
  readonly onToggleToken: () => void;
  readonly onSubmit: () => void;
}

export const useLoginScreen = (session: Session): LoginScreenState => {
  const { t } = useTranslation();
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const [token, setToken] = useState('');
  const [isTokenShown, setTokenShown] = useState(false);
  const [isSigningIn, setSigningIn] = useState(false);
  const [error, setError] = useState<LoginError | null>(null);
  const tokenInput = useRef<HTMLInputElement>(null);
  useDocumentTitle(t('Sign in', { context: 'screen title' }));

  useEffect(() => {
    tokenInput.current?.focus();
  }, []);

  // The notice explains why the login shows, until the login leaves the screen.
  useEffect(() => () => session.dismissNotice(), [session]);

  const signIn = async (signInToken: string): Promise<void> => {
    setSigningIn(true);
    try {
      await session.signIn(signInToken);
    } catch (failure) {
      setError({ reason: 'refused', failure });
      tokenInput.current?.select();
    } finally {
      setSigningIn(false);
    }
  };

  const submit = (): void => {
    const trimmedToken = token.trim();
    if (trimmedToken === '') {
      setError({ reason: 'missing-token' });
      tokenInput.current?.focus();
      return;
    }
    // signIn handles its own failures, so its promise never rejects.
    void signIn(trimmedToken);
  };

  return {
    token,
    isTokenShown,
    isSigningIn,
    error,
    notice: state.phase === 'signed-out' ? state.notice : null,
    tokenInput,
    onTokenChange: setToken,
    onToggleToken: () => setTokenShown(!isTokenShown),
    onSubmit: submit,
  };
};
