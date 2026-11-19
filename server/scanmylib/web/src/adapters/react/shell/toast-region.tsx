import { type FC, useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';

import { Icon } from './icon.tsx';
import type { Toasts } from './toasts.ts';

export const ToastRegion: FC<{ readonly toasts: Toasts }> = ({ toasts }) => {
  const { t } = useTranslation();
  const shown = useSyncExternalStore(toasts.subscribe, toasts.getSnapshot);
  return (
    <div className="toasts" id="toasts">
      {shown.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.tone}`} role={toast.tone === 'error' ? 'alert' : 'status'}>
          <p className="toast-message">{toast.message}</p>
          <button
            type="button"
            className="toast-close"
            aria-label={t('Close notification')}
            onClick={() => toasts.dismiss(toast.id)}
          >
            <Icon name="x" />
          </button>
        </div>
      ))}
    </div>
  );
};
