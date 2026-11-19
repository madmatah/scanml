import type { FC } from 'react';
import { Trans, useTranslation } from 'react-i18next';

import type { Session } from '../../../application/session.ts';
import { BrandMark } from '../shell/brand-mark.tsx';
import { Icon } from '../shell/icon.tsx';
import { BRAND_NAME } from '../shell/navigation.ts';
import { loginErrorText, signedOutNoticeText } from './login-messages.ts';
import { useLoginScreen } from './use-login-screen.ts';

const BRAND_MARK_PIXELS = 48;
const TOKEN_FILE = 'state/token';
const SIGN_IN_LINK_FORM = 'http://…/#token=…';

export const LoginScreen: FC<{ readonly session: Session }> = ({ session }) => {
  const { t } = useTranslation();
  const { token, isTokenShown, isSigningIn, error, notice, tokenInput, onTokenChange, onToggleToken, onSubmit } =
    useLoginScreen(session);

  let errorText: string | null = null;
  if (error !== null) errorText = loginErrorText(t, error);
  else if (notice !== null) errorText = signedOutNoticeText(t, notice);

  return (
    <section className="view login">
      <form
        className="card login-card"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
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
              onChange={(event) => onTokenChange(event.target.value)}
            />
            <button
              type="button"
              className="btn btn-icon"
              aria-pressed={isTokenShown}
              aria-label={isTokenShown ? t('Hide the access token') : t('Show the access token')}
              onClick={onToggleToken}
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
};
