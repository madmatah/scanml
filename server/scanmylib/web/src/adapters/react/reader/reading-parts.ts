import type { ReadingPart } from '../../../domain/reading.ts';

export interface PartElement {
  matches(selectors: string): boolean;
  querySelector(selectors: string): { readonly textContent: string | null } | null;
  getAttribute(qualifiedName: string): string | null;
  readonly textContent: string | null;
}

export interface DocumentParts<Section> {
  readonly parts: ReadingPart[];
  readonly sections: Section[];
}

export const documentParts = <Element extends PartElement>(children: Iterable<Element>): DocumentParts<Element> => {
  const parts: ReadingPart[] = [];
  const sections: Element[] = [];
  for (const element of children) {
    if (element.matches('section.page')) {
      const marker = element.querySelector(':scope > .page-marker');
      parts.push({ type: 'page', key: element.getAttribute('data-key') ?? '', marker: marker?.textContent ?? '' });
      sections.push(element);
    } else if (element.matches('.missing-pages')) {
      parts.push({ type: 'gap', text: element.textContent ?? '' });
    } else if (element.matches('.unnumbered')) {
      parts.push({ type: 'heading', text: element.textContent ?? '' });
    }
  }
  return { parts, sections };
};
