import type { FC } from 'react';
import { useTranslation } from 'react-i18next';

import { Icon } from './icon.tsx';
import type { Toast } from './toasts.ts';

export interface ToastRegionProps {
  readonly shownToasts: readonly Toast[];
  readonly onDismiss: (id: number) => void;
}

export const ToastRegion: FC<ToastRegionProps> = ({ shownToasts, onDismiss }) => {
  const { t } = useTranslation();
  return (
    <div className="toasts" id="toasts">
      {shownToasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.tone}`} role={toast.tone === 'error' ? 'alert' : 'status'}>
          <p className="toast-message">{toast.message}</p>
          <button
            type="button"
            className="toast-close"
            aria-label={t('Close notification')}
            onClick={() => onDismiss(toast.id)}
          >
            <Icon name="x" />
          </button>
        </div>
      ))}
    </div>
  );
};
