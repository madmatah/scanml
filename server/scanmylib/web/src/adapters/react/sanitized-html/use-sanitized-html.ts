import { type RefObject, useLayoutEffect, useRef } from 'react';

export type FormulaTypesetter = (root: Element) => void;

export type HtmlPreparation = (content: DocumentFragment) => void;

// Places the HTML that the api's allowlist sanitizer wrote into the element given the returned ref, which React renders
// empty and so never reconciles. It is parsed in an inert <template>, where no image loads and no script runs, so that
// the preparation can rewrite the addresses of its illustrations before the browser fetches them; then, in the page,
// its formulas are typeset before the browser paints, and the caller is told, which may then measure what was placed.
// The Content Security Policy forbids inline scripts besides.
export function useSanitizedHtml<Container extends HTMLElement = HTMLDivElement>(
  sanitizedHtml: string,
  prepare: HtmlPreparation,
  typesetFormulas: FormulaTypesetter,
  onPlaced?: (container: Container) => void,
): RefObject<Container | null> {
  const container = useRef<Container>(null);
  useLayoutEffect(() => {
    const element = container.current;
    if (element === null) return;
    const template = document.createElement('template');
    template.innerHTML = sanitizedHtml;
    prepare(template.content);
    element.replaceChildren(template.content);
    typesetFormulas(element);
    onPlaced?.(element);
  }, [sanitizedHtml, prepare, typesetFormulas, onPlaced]);
  return container;
}
