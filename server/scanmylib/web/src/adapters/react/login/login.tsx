import { type FormEvent, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Trans, useTranslation } from 'react-i18next';

import type { Session } from '../../../application/session.ts';
import { BrandMark } from '../shell/brand-mark.tsx';
import { Icon } from '../shell/icon.tsx';
import { BRAND_NAME } from '../shell/navigation.ts';
import { useDocumentTitle } from '../shell/use-document-title.ts';
import { type LoginError, loginErrorText, signedOutNoticeText } from './login-messages.ts';

const BRAND_MARK_PIXELS = 48;
const TOKEN_FILE = 'state/token';
const SIGN_IN_LINK_FORM = 'http://…/#token=…';

export function Login({ session }: { readonly session: Session }) {
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

  const notice = state.phase === 'signed-out' ? state.notice : null;
  let errorText: string | null = null;
  if (error !== null) errorText = loginErrorText(t, error);
  else if (notice !== null) errorText = signedOutNoticeText(t, notice);

  async function signIn(signInToken: string): Promise<void> {
    setSigningIn(true);
    try {
      await session.signIn(signInToken);
    } catch (failure) {
      setError({ reason: 'refused', failure });
      tokenInput.current?.select();
    } finally {
      setSigningIn(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const trimmedToken = token.trim();
    if (trimmedToken === '') {
      setError({ reason: 'missing-token' });
      tokenInput.current?.focus();
      return;
    }
    // signIn handles its own failures, so its promise never rejects.
    void signIn(trimmedToken);
  }

  return (
    <section className="view login">
      <form className="card login-card" noValidate onSubmit={submit}>
        <div className="login-brand">
          <BrandMark sizePixels={BRAND_MARK_PIXELS} />
          <div>
            <h1 tabIndex={-1}>{BRAND_NAME}</h1>
            <p className="muted">{t('Your digitized library')}</p>
          </div>
        </div>
        {/* Lets password managers store the token under a recognizable name. */}
        <input type="text" name="username" autoComplete="username" value={BRAND_NAME} hidden readOnly />
        <div className="field">
          <label htmlFor="login-token">{t('Access token')}</label>
          <div className="input-group">
            <input
              ref={tokenInput}
              id="login-token"
              name="token"
              type={isTokenShown ? 'text' : 'password'}
              className="input input-mono"
              required
              autoComplete="current-password"
              autoCapitalize="none"
              spellCheck={false}
              aria-describedby="login-help"
              value={token}
              onChange={(event) => setToken(event.target.value)}
            />
            <button
              type="button"
              className="btn btn-icon"
              aria-pressed={isTokenShown}
              aria-label={isTokenShown ? t('Hide the access token') : t('Show the access token')}
              onClick={() => setTokenShown(!isTokenShown)}
            >
              <Icon name={isTokenShown ? 'eye-off' : 'eye'} />
            </button>
          </div>
          <p id="login-help" className="hint">
            <Trans
              t={t}
              i18nKey="The server creates this token the first time it starts, in the file <file>{{file}}</file> of its data folder. A link of the form <signInLink>{{link}}</signInLink> signs you in directly."
              values={{ file: TOKEN_FILE, link: SIGN_IN_LINK_FORM }}
              components={{ file: <code />, signInLink: <code /> }}
            />
          </p>
        </div>
        <p className="form-error" role="alert" hidden={errorText === null}>
          {errorText ?? ''}
        </p>
        <button type="submit" className="btn btn-primary btn-block" disabled={isSigningIn}>
          {isSigningIn ? t('Signing in…') : t('Sign in')}
        </button>
      </form>
    </section>
  );
}
