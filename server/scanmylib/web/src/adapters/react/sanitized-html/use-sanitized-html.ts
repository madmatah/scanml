import { type RefObject, useLayoutEffect, useRef } from 'react';

// Typesets the formulas of HTML placed in the page; the composition root gives the one of the KaTeX adapter.
export type FormulaTypesetter = (root: Element) => void;

// Changes the parsed HTML before it is placed, while nothing of it has loaded.
export type HtmlPreparation = (content: DocumentFragment) => void;

// Places the HTML that the api's allowlist sanitizer wrote into the element given the returned ref, which React renders
// empty and so never reconciles. It is parsed in an inert <template>, where no image loads and no script runs, so that
// the preparation can rewrite the addresses of its illustrations before the browser fetches them; then, in the page,
// its formulas are typeset before the browser paints. The Content Security Policy forbids inline scripts besides.
export function useSanitizedHtml(
  sanitizedHtml: string,
  prepare: HtmlPreparation,
  typesetFormulas: FormulaTypesetter,
): RefObject<HTMLDivElement | null> {
  const container = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = container.current;
    if (element === null) return;
    const template = document.createElement('template');
    template.innerHTML = sanitizedHtml;
    prepare(template.content);
    element.replaceChildren(template.content);
    typesetFormulas(element);
  }, [sanitizedHtml, prepare, typesetFormulas]);
  return container;
}
