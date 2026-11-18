export interface PixelSize {
  readonly width: number;
  readonly height: number;
}

export interface ScanFit {
  readonly imagePixels: PixelSize;
  readonly rotationDegrees: number;
  readonly paneWidthPixels: number;
  readonly heightLimitPixels: number | null;
}

export interface ScanLayout {
  readonly framePixels: PixelSize;
  readonly imagePixels: PixelSize;
  readonly transform: string;
}

// Room kept above and below the scan, under the sticky header, when the whole page fits the screen.
const FIT_MARGIN_PIXELS = 112;
// A short window still shows the scan at a size where it can be read.
const LOWEST_HEIGHT_LIMIT_PIXELS = 240;
const HALF_TURN_DEGREES = 180;

export function scanHeightLimitPixels(windowHeightPixels: number, headerHeightPixels: number): number {
  return Math.max(LOWEST_HEIGHT_LIMIT_PIXELS, windowHeightPixels - headerHeightPixels - FIT_MARGIN_PIXELS);
}

export function layScan({
  imagePixels,
  rotationDegrees,
  paneWidthPixels,
  heightLimitPixels,
}: ScanFit): ScanLayout | null {
  const { width, height } = imagePixels;
  if (width <= 0 || height <= 0) return null;
  const isQuarterTurn = rotationDegrees % HALF_TURN_DEGREES !== 0;
  const shownWidth = isQuarterTurn ? height : width;
  const shownHeight = isQuarterTurn ? width : height;
  const scaleRatio = Math.min(paneWidthPixels / shownWidth, (heightLimitPixels ?? Infinity) / shownHeight);
  return {
    framePixels: { width: shownWidth * scaleRatio, height: shownHeight * scaleRatio },
    imagePixels: { width: width * scaleRatio, height: height * scaleRatio },
    transform: `translate(-50%, -50%) rotate(${rotationDegrees}deg)`,
  };
}
