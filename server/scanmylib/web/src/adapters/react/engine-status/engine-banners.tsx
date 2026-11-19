import { useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';

import type { EngineStatus } from '../../../application/engine-status.ts';
import { Icon } from '../shell/icon.tsx';
import { engineBanner } from './engine-status-text.ts';

export const EngineBanners = ({ engineStatus }: { readonly engineStatus: EngineStatus }) => {
  const { t } = useTranslation();
  const state = useSyncExternalStore(engineStatus.subscribe, engineStatus.getSnapshot);
  const banner = engineBanner(t, state);
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
