import { useTranslation } from 'react-i18next';

export function LoadingState({ message }: { readonly message?: string }) {
  const { t } = useTranslation();
  return (
    <div className="state state-loading" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{message ?? t('Loading…')}</span>
    </div>
  );
}
