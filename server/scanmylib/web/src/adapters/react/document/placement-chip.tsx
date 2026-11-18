import { useTranslation } from 'react-i18next';

import type { PageSummary } from '../../../domain/document-details.ts';
import { pagePlacementLabel } from '../../i18next/page-labels.ts';

export interface PlacementChipProps {
  readonly page: PageSummary;
  // "To place" only means something when other pages have a place.
  readonly showsUnplaced: boolean;
}

export function PlacementChip({ page, showsUnplaced }: PlacementChipProps) {
  const { t } = useTranslation();
  const placement = page.placement === 'unplaced' && !showsUnplaced ? null : pagePlacementLabel(t, page.placement);
  if (placement === null) return null;
  return (
    <span className={`chip chip-placement placement-${page.placement}`} title={placement.description}>
      {placement.label}
    </span>
  );
}
