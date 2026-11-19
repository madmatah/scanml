import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Icon } from './icon.tsx';

export interface ErrorStateProps {
  readonly title?: string;
  readonly message?: string;
  readonly onRetry?: () => void;
  readonly actions?: ReactNode;
}

export const ErrorState = ({ title, message, onRetry, actions }: ErrorStateProps) => {
  const { t } = useTranslation();
  return (
    <div className="state state-error" role="alert">
      <span className="state-icon">
        <Icon name="alert" />
      </span>
      <h2 className="state-title">{title ?? t('Could not load')}</h2>
      {message !== undefined && message !== '' && <p className="state-text">{message}</p>}
      <div className="state-actions">
        {onRetry !== undefined && (
          <button type="button" className="btn" onClick={onRetry}>
            <Icon name="refresh" />
            {t('Retry')}
          </button>
        )}
        {actions}
      </div>
    </div>
  );
};
