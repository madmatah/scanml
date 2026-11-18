import { READING_LINE_OFFSET_PIXELS, readingPosition } from './reading-position.ts';

export interface ReadingTrackerElements {
  readonly view: HTMLElement;
  readonly toolbar: HTMLElement;
  readonly text: HTMLElement;
  readonly appHeader: HTMLElement | null;
}

export interface ReadingTrackerCallbacks {
  readonly onPageRead: (pageIndex: number) => void;
  readonly onRememberPage: (pageKey: string) => void;
}

export interface ReadingTracker {
  follow(pages: readonly HTMLElement[], pageKeyToReturnTo: string | null): void;
  goToPage(pageIndex: number): void;
  destroy(): void;
}

const REMEMBER_DELAY_MILLISECONDS = 300;
const USER_SCROLL_EVENTS = ['wheel', 'touchstart', 'keydown', 'pointerdown'] as const;

function pageKeyOf(page: HTMLElement | undefined): string {
  return page?.dataset.key ?? '';
}

export function createReadingTracker(
  { view, toolbar, text, appHeader }: ReadingTrackerElements,
  { onPageRead, onRememberPage }: ReadingTrackerCallbacks,
): ReadingTracker {
  let pages: readonly HTMLElement[] = [];
  let currentIndex = -1;
  let heldIndex: number | null = null;
  let trackingFrame = 0;
  let rememberTimer: ReturnType<typeof setTimeout> | undefined;

  // The "Page" bar sticks under the sticky app header; the pages jumped to stay clear of both.
  function updateStickyOffsets(): void {
    const headerHeightPixels = appHeader !== null && !appHeader.hidden ? appHeader.offsetHeight : 0;
    view.style.setProperty('--reader-top', `${headerHeightPixels}px`);
    const barTopPixels = Number.parseFloat(getComputedStyle(toolbar).top) || 0;
    view.style.setProperty('--reader-covered', `${barTopPixels + toolbar.offsetHeight}px`);
  }

  function rememberPage(pageKey: string): void {
    clearTimeout(rememberTimer);
    onRememberPage(pageKey);
  }

  function setCurrent(pageIndex: number): void {
    if (pageIndex === currentIndex) return;
    currentIndex = pageIndex;
    onPageRead(pageIndex);
    clearTimeout(rememberTimer);
    const pageKey = pageKeyOf(pages[pageIndex]);
    rememberTimer = setTimeout(() => rememberPage(pageKey), REMEMBER_DELAY_MILLISECONDS);
  }

  function trackReading(): void {
    trackingFrame = 0;
    const position = readingPosition(
      {
        pageCount: pages.length,
        readingLinePixels: toolbar.getBoundingClientRect().bottom + READING_LINE_OFFSET_PIXELS,
        viewportHeightPixels: window.innerHeight,
        scrolledPixels: window.scrollY,
        textHeightPixels: document.documentElement.scrollHeight,
        pageTopPixels: (pageIndex) => pages[pageIndex]?.getBoundingClientRect().top ?? 0,
        pageBottomPixels: (pageIndex) => pages[pageIndex]?.getBoundingClientRect().bottom ?? 0,
      },
      heldIndex,
    );
    if (position === null) return;
    heldIndex = position.heldPageIndex;
    setCurrent(position.pageIndex);
  }

  function scheduleTracking(): void {
    trackingFrame ||= requestAnimationFrame(trackReading);
  }

  // Holds a page at the top until the reader scrolls: the illustrations above it, loaded as they come into view, would
  // push it down or pull it up when they get their height.
  function goToPage(pageIndex: number): void {
    const page = pages[pageIndex];
    if (page === undefined) return;
    heldIndex = pageIndex;
    page.scrollIntoView({ block: 'start' });
    setCurrent(pageIndex);
  }

  function holdPage(event: Event): void {
    if (heldIndex === null || !(event.target instanceof HTMLImageElement)) return;
    const page = pages[heldIndex];
    if (page !== undefined && page.compareDocumentPosition(event.target) & Node.DOCUMENT_POSITION_PRECEDING) {
      page.scrollIntoView({ block: 'start' });
    }
  }

  function releasePage(): void {
    heldIndex = null;
  }

  // "Back" from the page screen returns to the page whose marker was followed.
  function rememberFollowedPage(event: MouseEvent): void {
    if (!(event.target instanceof Element)) return;
    const page = event.target.closest('.page-marker a')?.closest('section.page');
    if (page instanceof HTMLElement) rememberPage(pageKeyOf(page));
  }

  const resizeObserver = new ResizeObserver(updateStickyOffsets);
  if (appHeader !== null) resizeObserver.observe(appHeader);
  resizeObserver.observe(toolbar);
  text.addEventListener('click', rememberFollowedPage);
  // An image's load does not bubble.
  text.addEventListener('load', holdPage, true);
  window.addEventListener('scroll', scheduleTracking, { passive: true });
  window.addEventListener('resize', scheduleTracking);
  for (const type of USER_SCROLL_EVENTS) window.addEventListener(type, releasePage, { passive: true });

  return {
    follow(placedPages, pageKeyToReturnTo) {
      pages = placedPages;
      currentIndex = -1;
      heldIndex = null;
      updateStickyOffsets();
      const returnIndex =
        pageKeyToReturnTo === null ? -1 : pages.findIndex((page) => pageKeyOf(page) === pageKeyToReturnTo);
      if (returnIndex >= 0) goToPage(returnIndex);
      else trackReading();
    },
    goToPage,
    destroy() {
      cancelAnimationFrame(trackingFrame);
      clearTimeout(rememberTimer);
      resizeObserver.disconnect();
      text.removeEventListener('click', rememberFollowedPage);
      text.removeEventListener('load', holdPage, true);
      window.removeEventListener('scroll', scheduleTracking);
      window.removeEventListener('resize', scheduleTracking);
      for (const type of USER_SCROLL_EVENTS) window.removeEventListener(type, releasePage);
    },
  };
}
