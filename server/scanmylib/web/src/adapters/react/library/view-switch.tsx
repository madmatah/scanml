import type { FC } from 'react';
import { useTranslation } from 'react-i18next';

import { LIBRARY_VIEWS, type LibraryView } from '../../../domain/library-view.ts';
import { Icon, type IconName } from '../shell/icon.tsx';
import { libraryViewLabel } from './library-text.ts';

const VIEW_ICONS: Readonly<Record<LibraryView, IconName>> = {
  cards: 'grid',
  list: 'list',
};

export interface ViewSwitchProps {
  readonly view: LibraryView;
  readonly onViewChange: (view: LibraryView) => void;
}

export const ViewSwitch: FC<ViewSwitchProps> = ({ view, onViewChange }) => {
  const { t } = useTranslation();
  return (
    <fieldset className="toggle-group view-switch" aria-label={t('View')}>
      {LIBRARY_VIEWS.map((shownView) => {
        const label = libraryViewLabel(t, shownView);
        return (
          <button
            key={shownView}
            type="button"
            className="toggle-button toggle-icon-button"
            aria-pressed={shownView === view}
            aria-label={label}
            title={label}
            onClick={() => onViewChange(shownView)}
          >
            <Icon name={VIEW_ICONS[shownView]} />
          </button>
        );
      })}
    </fieldset>
  );
};
