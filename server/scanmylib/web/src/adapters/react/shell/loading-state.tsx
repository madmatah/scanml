import type { FC } from 'react';
import { useTranslation } from 'react-i18next';

export const LoadingState: FC<{ readonly message?: string }> = ({ message }) => {
  const { t } = useTranslation();
  return (
    <div className="state state-loading" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{message ?? t('Loading…')}</span>
    </div>
  );
};
