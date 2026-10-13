/**
 * LaTeX formulas of the OCR previews, typeset with KaTeX (static/vendor/katex,
 * loaded by index.html; see scripts/vendor-katex.sh).
 *
 * The server marks formulas as <div class="math-display"> and
 * <span class="math-inline"> elements holding the TeX as text
 * (scanmylib/preview.py). KaTeX replaces that text with the formula; one it
 * cannot parse shows its source in the error color, the reason as tooltip.
 * Without KaTeX (file not loaded), the source stays as it is.
 *
 * An inline formula written against a word or a punctuation mark, like the
 * superscripts of 19$^{th}$ or Doe$^{12}$, stays on the same line as them.
 */

/**
 * KaTeX options for one formula: a new object each time, as KaTeX stores in
 * `macros` what a formula defines with \gdef, which must not change the others.
 */
export function katexOptions(displayMode = false) {
  return {
    displayMode,
    throwOnError: false,
    errorColor: 'var(--danger)',
    trust: false, // OCR text is untrusted: no \href, \url, \includegraphics, \htmlClass…
    // Text characters in math mode (™, accented letters…) are typeset as text, as XeLaTeX
    // does, without a console warning for each one (or an error with a stricter setting).
    strict: 'ignore',
    maxSize: 20,
    maxExpand: 500,
    output: 'htmlAndMathml',
    // ® is text in math mode too, as KaTeX does for ©: an upright R, not a math italic one.
    macros: { '®': '\\TextOrMath{\\textregistered}{\\text{\\textregistered}}' },
  };
}

/** Spaces where a line may break; the no-break ones (U+00A0, U+202F…) bind their neighbors. */
const BREAKABLE_SPACE = /[\t\n\f\r \u1680\u2000-\u2006\u2008-\u200b\u205f\u3000]/;

/** Start of the last word of `text`, the part written against what follows it. */
export function boundStart(text) {
  let start = text.length;
  while (start > 0 && !BREAKABLE_SPACE.test(text[start - 1])) start -= 1;
  return start;
}

/** Length of the first word of `text`, the part written against what precedes it. */
export function boundLength(text) {
  let length = 0;
  while (length < text.length && !BREAKABLE_SPACE.test(text[length])) length += 1;
  return length;
}

/**
 * Runs `render` with `style` attributes applied through the CSSOM. KaTeX
 * styles its output through the CSSOM, which the Content Security Policy
 * allows, except for a few `style` attributes (error messages, SVG parts of
 * tall delimiters and of \vec, some MathML) that it would block.
 */
function withStyleAttributesThroughCssom(render) {
  const { setAttribute } = Element.prototype;
  Element.prototype.setAttribute = function setAttributeThroughCssom(name, value) {
    if (name === 'style' && this.style) this.style.cssText = value;
    else setAttribute.call(this, name, value);
  };
  try {
    render();
  } finally {
    Element.prototype.setAttribute = setAttribute;
  }
}

/**
 * Puts an inline formula and the text written against it (no breakable space
 * in between) in one <span class="math-word">. Browsers may otherwise break
 * a line on either side of a typeset formula, sending the superscript of
 * 19$^{th}$, or the comma after a formula, to the next line. A formula
 * following another one in this way joins its group.
 */
function keepWithWord(formula) {
  const before = formula.previousSibling;
  const after = formula.nextSibling;
  let word = before instanceof Element && before.classList.contains('math-word') ? before : null;
  const start = !word && before?.nodeType === Node.TEXT_NODE ? boundStart(before.data) : -1;
  const length = after?.nodeType === Node.TEXT_NODE ? boundLength(after.data) : 0;
  const boundBefore = start >= 0 && start < before.data.length;
  if (!word && !boundBefore && length === 0) return;
  if (!word) {
    word = document.createElement('span');
    word.className = 'math-word';
    formula.before(word);
    if (boundBefore) word.append(start === 0 ? before : before.splitText(start));
  }
  word.append(formula);
  if (length > 0) {
    if (length < after.data.length) after.splitText(length);
    word.append(after);
  }
}

/** Typesets the formulas found inside `root`. */
export function renderMath(root) {
  const { katex } = globalThis;
  const formulas = root.querySelectorAll('.math-display, .math-inline');
  if (!katex || formulas.length === 0) return;
  withStyleAttributesThroughCssom(() => {
    for (const formula of formulas) {
      const tex = formula.textContent;
      const displayMode = formula.classList.contains('math-display');
      try {
        katex.render(tex, formula, katexOptions(displayMode));
      } catch {
        formula.textContent = tex; // an internal KaTeX error (parse errors are shown in place)
      }
      if (!displayMode) keepWithWord(formula);
    }
  });
}
