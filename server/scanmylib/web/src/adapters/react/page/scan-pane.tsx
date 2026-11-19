import type { FC } from 'react';
import { useTranslation } from 'react-i18next';

import type { PageDetails } from '../../../domain/page-details.ts';
import { Icon } from '../shell/icon.tsx';
import { scanDescription } from './page-text.ts';
import { useScanLayout } from './use-scan-layout.ts';

export interface ScanPaneProps {
  readonly page: PageDetails;
  readonly isFullWidth: boolean;
  readonly onToggleFullWidth: () => void;
}

export const ScanPane: FC<ScanPaneProps> = ({ page, isFullWidth, onToggleFullWidth }) => {
  const { t } = useTranslation();
  const { viewport, frame, image } = useScanLayout(page.rotation, isFullWidth);

  return (
    <section className="pane scan-pane" aria-labelledby="scan-title">
      <div className="pane-header">
        <h2 id="scan-title" className="pane-title">
          {t('Scan')}
        </h2>
        <div className="pane-tools">
          <button type="button" className="btn btn-small" aria-pressed={isFullWidth} onClick={onToggleFullWidth}>
            <Icon name="expand" />
            {t('Full width')}
          </button>
          <a className="btn btn-small btn-ghost" href={page.imageUrl} target="_blank" rel="noopener">
            <Icon name="external" />
            {t('Original')}
          </a>
        </div>
      </div>
      <div ref={viewport} className={isFullWidth ? 'scan-viewport is-full-width' : 'scan-viewport'}>
        <div ref={frame} className="scan-frame">
          <img ref={image} src={page.imageUrl} alt={scanDescription(t, page)} decoding="async" />
        </div>
      </div>
    </section>
  );
};
