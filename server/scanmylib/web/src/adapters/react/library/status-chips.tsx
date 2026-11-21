import type { FC } from 'react';
import { useTranslation } from 'react-i18next';

import type { DocumentSummary } from '../../../domain/document-summary.ts';
import { type ChipTone, statusChips } from './library-text.ts';

const CHIP_CLASSES: Readonly<Record<ChipTone, string>> = {
  neutral: 'chip',
  info: 'chip chip-info',
  warn: 'chip chip-warn',
  danger: 'chip chip-danger',
};

export interface StatusChipsProps {
  readonly document: DocumentSummary;
}

export const StatusChips: FC<StatusChipsProps> = ({ document }) => {
  const { t } = useTranslation();
  return (
    // biome-ignore lint/a11y/noRedundantRoles: Safari drops the role of a list drawn without its markers.
    <ul className="chips" role="list">
      {statusChips(t, document).map(({ name, text, tone }) => (
        <li key={name} className={CHIP_CLASSES[tone]}>
          {text}
        </li>
      ))}
    </ul>
  );
};
