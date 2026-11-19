import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { PageDetails } from '../../../domain/page-details.ts';
import { Icon } from '../shell/icon.tsx';
import { scanDescription } from './page-text.ts';
import { layScan, scanHeightLimitPixels } from './scan-layout.ts';

const APP_HEADER_ID = 'app-header';

export const ScanPane = ({ page }: { readonly page: PageDetails }) => {
  const { t } = useTranslation();
  const [isFullWidth, setFullWidth] = useState(false);
  const viewport = useRef<HTMLDivElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  const image = useRef<HTMLImageElement>(null);
  const { rotation } = page;

  // The sizes come from the window, the pane and the decoded image, which React does not see; they go through the
  // CSSOM, which the Content Security Policy allows.
  useEffect(() => {
    const paneViewport = viewport.current;
    const scanFrame = frame.current;
    const scanImage = image.current;
    if (paneViewport === null || scanFrame === null || scanImage === null) return;
    let layoutFrame = 0;
    let lastPaneWidthPixels = 0;

    const layOut = (): void => {
      if (paneViewport === null || scanFrame === null || scanImage === null) return;
      layoutFrame = 0;
      lastPaneWidthPixels = paneViewport.clientWidth;
      const headerHeightPixels = document.getElementById(APP_HEADER_ID)?.offsetHeight ?? 0;
      const layout = layScan({
        imagePixels: { width: scanImage.naturalWidth, height: scanImage.naturalHeight },
        rotationDegrees: rotation,
        paneWidthPixels: lastPaneWidthPixels,
        heightLimitPixels: isFullWidth ? null : scanHeightLimitPixels(window.innerHeight, headerHeightPixels),
      });
      if (layout === null) return;
      scanFrame.style.width = `${layout.framePixels.width}px`;
      scanFrame.style.height = `${layout.framePixels.height}px`;
      scanImage.style.width = `${layout.imagePixels.width}px`;
      scanImage.style.height = `${layout.imagePixels.height}px`;
      scanImage.style.transform = layout.transform;
    };

    // In the next frame: a size changed inside the observer's own callback would call it again within the same frame.
    const scheduleLayout = (): void => {
      if (layoutFrame === 0) layoutFrame = requestAnimationFrame(layOut);
    };

    const resizeObserver = new ResizeObserver(() => {
      if (paneViewport.clientWidth !== lastPaneWidthPixels) scheduleLayout();
    });
    resizeObserver.observe(paneViewport);
    scanImage.addEventListener('load', scheduleLayout);
    window.addEventListener('resize', scheduleLayout);
    scheduleLayout();
    return () => {
      cancelAnimationFrame(layoutFrame);
      resizeObserver.disconnect();
      scanImage.removeEventListener('load', scheduleLayout);
      window.removeEventListener('resize', scheduleLayout);
    };
  }, [rotation, isFullWidth]);

  return (
    <section className="pane scan-pane" aria-labelledby="scan-title">
      <div className="pane-header">
        <h2 id="scan-title" className="pane-title">
          {t('Scan')}
        </h2>
        <div className="pane-tools">
          <button
            type="button"
            className="btn btn-small"
            aria-pressed={isFullWidth}
            onClick={() => setFullWidth(!isFullWidth)}
          >
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
