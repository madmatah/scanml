import { type RefObject, useEffect, useRef } from 'react';

import { layScan, scanHeightLimitPixels } from './scan-layout.ts';

const APP_HEADER_ID = 'app-header';

export interface ScanLayout {
  readonly viewport: RefObject<HTMLDivElement | null>;
  readonly frame: RefObject<HTMLDivElement | null>;
  readonly image: RefObject<HTMLImageElement | null>;
}

export const useScanLayout = (rotation: number, isFullWidth: boolean): ScanLayout => {
  const viewport = useRef<HTMLDivElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  const image = useRef<HTMLImageElement>(null);

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

  return { viewport, frame, image };
};
