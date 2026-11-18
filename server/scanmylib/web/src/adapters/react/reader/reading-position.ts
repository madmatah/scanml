import { pageAtLine } from '../../../domain/reading.ts';

export const READING_LINE_OFFSET_PIXELS = 24;
const END_OF_TEXT_TOLERANCE_PIXELS = 2;

export interface ReadingView {
  readonly pageCount: number;
  readonly readingLinePixels: number;
  readonly viewportHeightPixels: number;
  readonly scrolledPixels: number;
  readonly textHeightPixels: number;
  pageTopPixels(pageIndex: number): number;
  pageBottomPixels(pageIndex: number): number;
}

export interface ReadingPosition {
  readonly pageIndex: number;
  readonly heldPageIndex: number | null;
}

export function readingPosition(view: ReadingView, heldPageIndex: number | null): ReadingPosition | null {
  if (view.pageCount === 0) return null;
  if (heldPageIndex !== null) {
    const isStillShown =
      view.pageBottomPixels(heldPageIndex) > view.readingLinePixels &&
      view.pageTopPixels(heldPageIndex) < view.viewportHeightPixels;
    if (isStillShown) return { pageIndex: heldPageIndex, heldPageIndex };
  }
  const isAtTheEnd =
    view.scrolledPixels > 0 &&
    view.viewportHeightPixels + view.scrolledPixels >= view.textHeightPixels - END_OF_TEXT_TOLERANCE_PIXELS;
  if (isAtTheEnd) return { pageIndex: view.pageCount - 1, heldPageIndex: null };
  return {
    pageIndex: pageAtLine(view.pageCount, (pageIndex) => view.pageTopPixels(pageIndex), view.readingLinePixels),
    heldPageIndex: null,
  };
}
