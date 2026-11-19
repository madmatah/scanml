import type { TFunction } from 'i18next';
import type { FC } from 'react';
import { useTranslation } from 'react-i18next';

import { type DescribedLabel, pagePlacementLabel } from '../../i18next/page-labels.ts';

export interface PlacedPage {
  readonly placement: string | null;
}

export interface PlacementChipProps {
  readonly page: PlacedPage;
  readonly showsUnplaced: boolean;
}

export const shownPlacement = (t: TFunction, page: PlacedPage, showsUnplaced: boolean): DescribedLabel | null => {
  return page.placement === 'unplaced' && !showsUnplaced ? null : pagePlacementLabel(t, page.placement);
};

export const PlacementChip: FC<PlacementChipProps> = ({ page, showsUnplaced }) => {
  const { t } = useTranslation();
  const placement = shownPlacement(t, page, showsUnplaced);
  if (placement === null) return null;
  return (
    <span className={`chip chip-placement placement-${page.placement}`} title={placement.description}>
      {placement.label}
    </span>
  );
};
