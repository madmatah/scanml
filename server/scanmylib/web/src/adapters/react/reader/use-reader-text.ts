import type { TFunction } from 'i18next';
import { type RefObject, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { PageSummary } from '../../../domain/document-details.ts';
import { localizeMarkers } from '../sanitized-html/page-markers.ts';
import { type FormulaTypesetter, useSanitizedHtml } from '../sanitized-html/use-sanitized-html.ts';
import { idOfAddress, pagePath } from '../shell/navigation.ts';
import { versionedUrl } from '../shell/versioned-url.ts';
import { isAddressOf, pageReadIn, withPageRead } from './page-read-memory.ts';
import { removeTitle } from './reader-html.ts';
import { createReadingTracker, type ReadingTracker } from './reading-tracker.ts';

export interface ReaderTextOptions {
  readonly pages: readonly PageSummary[];
  readonly returnsToPageRead: boolean;
  readonly readerAddress: string;
  readonly typesetFormulas: FormulaTypesetter;
}

export interface ReaderText {
  readonly view: RefObject<HTMLElement | null>;
  readonly toolbar: RefObject<HTMLDivElement | null>;
  readonly text: RefObject<HTMLElement | null>;
  readonly currentIndex: number;
  readonly onGoToPage: (pageIndex: number) => void;
}

const preparePage = (t: TFunction, section: Element, page: PageSummary | undefined): void => {
  const marker = section.querySelector(':scope > .page-marker');
  const pageId = page === undefined ? null : idOfAddress(page.id);
  if (marker !== null && pageId !== null) {
    const link = document.createElement('a');
    link.href = `#${pagePath(pageId)}`;
    link.title = t('Open this page: scan, number, recognized text');
    link.textContent = marker.textContent;
    marker.replaceChildren(link);
  }
  for (const illustration of section.querySelectorAll('img[src]')) {
    const address = illustration.getAttribute('src');
    // A new reading of the page's text rewrites its illustrations in place.
    if (address !== null) illustration.setAttribute('src', versionedUrl(address, page?.readAt ?? ''));
    illustration.setAttribute('loading', 'lazy');
    illustration.setAttribute('decoding', 'async');
  }
};

// As in the legend of the document's coverage.
const missingPagesSwatch = (): HTMLElement => {
  const swatch = document.createElement('span');
  swatch.className = 'swatch is-missing';
  swatch.setAttribute('aria-hidden', 'true');
  return swatch;
};

export const useReaderText = (
  sanitizedHtml: string,
  { pages, returnsToPageRead, readerAddress, typesetFormulas }: ReaderTextOptions,
): ReaderText => {
  const { t } = useTranslation();
  const view = useRef<HTMLElement>(null);
  const toolbar = useRef<HTMLDivElement>(null);
  const tracker = useRef<ReadingTracker | null>(null);
  const [currentIndex, setCurrentIndex] = useState(-1);
  const pagesByKey = useMemo(() => new Map(pages.map((page) => [page.key, page])), [pages]);

  const prepare = useCallback(
    (content: DocumentFragment) => {
      removeTitle(content);
      localizeMarkers(t, content);
      for (const element of content.children) {
        if (element.matches('section.page')) {
          preparePage(t, element, pagesByKey.get(element.getAttribute('data-key') ?? ''));
        } else if (element.matches('.missing-pages')) {
          element.prepend(missingPagesSwatch());
        }
      }
    },
    [t, pagesByKey],
  );

  // The tracker starts with the first text placed, once the elements it follows exist.
  const followPages = useCallback(
    (textElement: HTMLElement) => {
      const viewElement = view.current;
      const toolbarElement = toolbar.current;
      if (viewElement === null || toolbarElement === null) return;
      tracker.current ??= createReadingTracker(
        {
          view: viewElement,
          toolbar: toolbarElement,
          text: textElement,
          appHeader: document.getElementById('app-header'),
        },
        {
          onPageRead: setCurrentIndex,
          onRememberPage: (pageKey) => {
            // The router may have left the reader's history entry before the screen goes.
            if (isAddressOf(window.location.hash, readerAddress)) {
              window.history.replaceState(withPageRead(window.history.state, pageKey), '');
            }
          },
        },
      );
      const placedPages = [...textElement.querySelectorAll<HTMLElement>(':scope > section.page')];
      tracker.current.follow(placedPages, returnsToPageRead ? pageReadIn(window.history.state) : null);
    },
    [readerAddress, returnsToPageRead],
  );
  const text = useSanitizedHtml<HTMLElement>(sanitizedHtml, prepare, typesetFormulas, followPages);

  useEffect(
    () => () => {
      tracker.current?.destroy();
      tracker.current = null;
    },
    [],
  );

  return {
    view,
    toolbar,
    text,
    currentIndex,
    onGoToPage: (pageIndex) => tracker.current?.goToPage(pageIndex),
  };
};
