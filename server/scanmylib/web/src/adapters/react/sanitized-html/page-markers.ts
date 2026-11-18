import type { TFunction } from 'i18next';

import { missingPagesText, pageMarkerText, unnumberedHeadingText } from '../../i18next/reading-text.ts';

export interface MarkerElement {
  matches(selectors: string): boolean;
  querySelector(selectors: string): MarkerElement | null;
  getAttribute(qualifiedName: string): string | null;
  textContent: string | null;
}

export interface MarkerContent {
  readonly children: Iterable<MarkerElement>;
}

// The server writes the markers of a document's HTML in English, with its own words for a gap, and gives their data as
// attributes; a marker without its attribute, from an older server, keeps the server's text.
export function localizeMarkers(t: TFunction, content: MarkerContent): void {
  for (const element of content.children) {
    if (element.matches('section.page')) {
      const marker = element.querySelector(':scope > .page-marker');
      const label = marker?.getAttribute('data-label') ?? null;
      if (marker && label !== null) marker.textContent = pageMarkerText(t, label);
    } else if (element.matches('.missing-pages')) {
      const range = element.getAttribute('data-range');
      if (range !== null) element.textContent = missingPagesText(t, range);
    } else if (element.matches('h2.unnumbered')) {
      element.textContent = unnumberedHeadingText(t);
    }
  }
}
