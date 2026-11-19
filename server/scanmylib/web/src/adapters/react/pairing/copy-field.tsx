import { type FC, useId } from 'react';
import { useTranslation } from 'react-i18next';

import { Icon } from '../shell/icon.tsx';

export interface SecretVisibility {
  readonly isShown: boolean;
  readonly onToggleShown: () => void;
}

export interface CopyFieldProps {
  readonly label: string;
  readonly text: string;
  readonly secret: SecretVisibility | null;
  readonly copiedMessage: string;
  readonly onCopy: (text: string, copiedMessage: string) => void;
}

export const CopyField: FC<CopyFieldProps> = ({ label, text, secret, copiedMessage, onCopy }) => {
  const { t } = useTranslation();
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="input-group">
        <input
          id={id}
          className="input input-mono"
          type={secret !== null && !secret.isShown ? 'password' : 'text'}
          value={text}
          readOnly
          autoComplete="off"
          spellCheck={false}
        />
        {secret !== null && (
          <button
            type="button"
            className="btn btn-icon"
            aria-pressed={secret.isShown}
            aria-label={secret.isShown ? t('Hide the access token') : t('Show the access token')}
            onClick={secret.onToggleShown}
          >
            <Icon name={secret.isShown ? 'eye-off' : 'eye'} />
          </button>
        )}
        <button
          type="button"
          className="btn"
          aria-label={t('Copy: {{label}}', { label })}
          onClick={() => onCopy(text, copiedMessage)}
        >
          <Icon name="copy" />
          <span className="btn-label">{t('Copy')}</span>
        </button>
      </div>
    </div>
  );
};
