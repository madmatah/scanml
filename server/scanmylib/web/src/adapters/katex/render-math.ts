import katex from 'katex';

import { boundLength, boundStart, katexOptions } from '../../domain/formulas.ts';

const FORMULAS = '.math-display, .math-inline';
const DISPLAY_FORMULA = 'math-display';
const WORD_WITH_FORMULA = 'math-word';

const hasStyle = (element: Element): element is Element & ElementCSSInlineStyle => {
  return 'style' in element && element.style instanceof CSSStyleDeclaration;
};

// KaTeX styles its output through the CSSOM, which the Content Security Policy allows, except for a few `style`
// attributes (error messages, the SVG parts of tall delimiters and of \vec, some MathML) that it would block.
const withStyleAttributesThroughCssom = (render: () => void): void => {
  const { setAttribute } = Element.prototype;
  Element.prototype.setAttribute = function setAttributeThroughCssom(this: Element, name: string, value: string) {
    if (name === 'style' && hasStyle(this)) this.style.cssText = value;
    else setAttribute.call(this, name, value);
  };
  try {
    render();
  } finally {
    Element.prototype.setAttribute = setAttribute;
  }
};

// A browser may break a line on either side of a typeset formula, sending the superscript of 19$^{th}$, or the comma
// after a formula, to the next line: the formula and the text written against it, with no breakable space between
// them, go in one <span class="math-word">, which a formula following in this way joins.
const keepWithWord = (formula: Element): void => {
  const before = formula.previousSibling;
  const after = formula.nextSibling;
  let word = before instanceof Element && before.classList.contains(WORD_WITH_FORMULA) ? before : null;
  const textBefore = word === null && before instanceof Text ? before : null;
  const textAfter = after instanceof Text ? after : null;
  const start = textBefore === null ? -1 : boundStart(textBefore.data);
  const length = textAfter === null ? 0 : boundLength(textAfter.data);
  const isBoundBefore = textBefore !== null && start >= 0 && start < textBefore.data.length;
  if (word === null && !isBoundBefore && length === 0) return;
  if (word === null) {
    word = document.createElement('span');
    word.className = WORD_WITH_FORMULA;
    formula.before(word);
    if (isBoundBefore) word.append(start === 0 ? textBefore : textBefore.splitText(start));
  }
  word.append(formula);
  if (textAfter !== null && length > 0) {
    if (length < textAfter.data.length) textAfter.splitText(length);
    word.append(textAfter);
  }
};

export const renderMath = (root: Element): void => {
  const formulas = [...root.querySelectorAll(FORMULAS)];
  if (formulas.length === 0) return;
  withStyleAttributesThroughCssom(() => {
    for (const formula of formulas) {
      if (!(formula instanceof HTMLElement)) continue;
      const tex = formula.textContent;
      const displayMode = formula.classList.contains(DISPLAY_FORMULA);
      try {
        katex.render(tex, formula, katexOptions(displayMode));
      } catch {
        // An internal error of KaTeX, since it shows the errors of parsing in place.
        formula.textContent = tex;
      }
      if (!displayMode) keepWithWord(formula);
    }
  });
};
