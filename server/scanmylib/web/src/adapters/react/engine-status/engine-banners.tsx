import type { FC } from 'react';
import { useTranslation } from 'react-i18next';

import type { EngineStatusState } from '../../../application/engine-status.ts';
import { Icon } from '../shell/icon.tsx';
import { engineBanner } from './engine-status-text.ts';

export const EngineBanners: FC<{ readonly engine: EngineStatusState }> = ({ engine }) => {
  const { t } = useTranslation();
  const banner = engineBanner(t, engine);
  return (
    <div className="banners" id="banners">
      {banner !== null && (
        // Keyed by its text, so that a screen reader announces a new banner, and a poll that changes nothing is silent.
        <div key={`${banner.title} ${banner.message}`} className="banner banner-danger" role="alert">
          <Icon name="alert" />
          <div>
            <p className="banner-title">{banner.title}</p>
            <p>{banner.message}</p>
          </div>
        </div>
      )}
    </div>
  );
};
