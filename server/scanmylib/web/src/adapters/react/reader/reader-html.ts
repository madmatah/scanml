import type { TFunction } from 'i18next';

import type { ReadingPart } from '../../../domain/reading.ts';
import { localizeMarkers } from '../sanitized-html/page-markers.ts';
import { documentParts } from './reading-parts.ts';

export const removeTitle = (content: DocumentFragment): void => {
  if (content.firstElementChild?.tagName === 'H1') content.firstElementChild.remove();
};

// The parts of the document's HTML that the "Page" list shows, read from a copy of its own: the text shown is parsed
// and prepared again where it is placed.
export const readingPartsOf = (t: TFunction, sanitizedHtml: string): ReadingPart[] => {
  const template = document.createElement('template');
  template.innerHTML = sanitizedHtml;
  removeTitle(template.content);
  localizeMarkers(t, template.content);
  return documentParts(template.content.children).parts;
};
