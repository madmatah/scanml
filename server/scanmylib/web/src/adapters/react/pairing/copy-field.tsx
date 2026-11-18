import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Clipboard } from '../../../application/clipboard.ts';
import { Icon } from '../shell/icon.tsx';
import type { Toasts } from '../shell/toasts.ts';

export interface CopyFieldProps {
  readonly label: string;
  readonly text: string;
  readonly isSecret: boolean;
  readonly copiedMessage: string;
  readonly clipboard: Clipboard;
  readonly toasts: Toasts;
}

export function CopyField({ label, text, isSecret, copiedMessage, clipboard, toasts }: CopyFieldProps) {
  const { t } = useTranslation();
  const id = useId();
  const [isShown, setShown] = useState(false);

  async function copy(): Promise<void> {
    if (await clipboard.copyText(text)) toasts.show(copiedMessage, 'success');
    else toasts.show(t('Could not copy: select the text by hand.'), 'error');
  }

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="input-group">
        <input
          id={id}
          className="input input-mono"
          type={isSecret && !isShown ? 'password' : 'text'}
          value={text}
          readOnly
          autoComplete="off"
          spellCheck={false}
        />
        {isSecret && (
          <button
            type="button"
            className="btn btn-icon"
            aria-pressed={isShown}
            aria-label={isShown ? t('Hide the access token') : t('Show the access token')}
            onClick={() => setShown(!isShown)}
          >
            <Icon name={isShown ? 'eye-off' : 'eye'} />
          </button>
        )}
        <button
          type="button"
          className="btn"
          aria-label={t('Copy: {{label}}', { label })}
          onClick={() => {
            // copy tells its outcome in a toast, and the clipboard's copy never rejects.
            void copy();
          }}
        >
          <Icon name="copy" />
          <span className="btn-label">{t('Copy')}</span>
        </button>
      </div>
    </div>
  );
}
