import type { FC } from 'react';
import { useTranslation } from 'react-i18next';

import { KIND_FILTERS, type KindFilter } from '../../../domain/document-search.ts';
import { kindFilterLabel } from './library-text.ts';

export interface KindFilterButtonsProps {
  readonly kindFilter: KindFilter;
  readonly onKindFilterChange: (kindFilter: KindFilter) => void;
}

export const KindFilterButtons: FC<KindFilterButtonsProps> = ({ kindFilter, onKindFilterChange }) => {
  const { t } = useTranslation();
  return (
    <fieldset className="segmented" aria-label={t('Kind of document')}>
      {KIND_FILTERS.map((filter) => (
        <button
          key={filter}
          type="button"
          className="segmented-button"
          aria-pressed={filter === kindFilter}
          onClick={() => onKindFilterChange(filter)}
        >
          {kindFilterLabel(t, filter)}
        </button>
      ))}
    </fieldset>
  );
};
