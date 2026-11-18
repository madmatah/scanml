export interface FormulaTypesetting {
  readonly displayMode: boolean;
  readonly throwOnError: false;
  readonly errorColor: string;
  readonly trust: false;
  readonly strict: 'ignore';
  readonly maxSize: number;
  readonly maxExpand: number;
  readonly output: 'htmlAndMathml';
  readonly macros: Record<string, string>;
}

// Spaces where a line may break; the no-break ones (U+00A0, U+202F…) bind their neighbors.
const BREAKABLE_SPACE = /[\t\n\f\r \u1680\u2000-\u2006\u2008-\u200b\u205f\u3000]/;

// A new object for each formula, since KaTeX stores in `macros` what a formula defines with \gdef, which must not change
// the next ones.
export function katexOptions(displayMode = false): FormulaTypesetting {
  return {
    displayMode,
    throwOnError: false,
    errorColor: 'var(--danger)',
    // The text of the OCR is untrusted: no \href, \url, \includegraphics, \htmlClass…
    trust: false,
    // Text characters in math mode (™, accented letters…) are typeset as text, as XeLaTeX does, without a console
    // warning for each one, or an error with a stricter setting.
    strict: 'ignore',
    maxSize: 20,
    maxExpand: 500,
    output: 'htmlAndMathml',
    // ® is text in math mode too, as KaTeX does for ©: an upright R, not a math italic one.
    macros: { '®': '\\TextOrMath{\\textregistered}{\\text{\\textregistered}}' },
  };
}

export function boundStart(text: string): number {
  let start = text.length;
  while (start > 0 && !BREAKABLE_SPACE.test(text.charAt(start - 1))) start -= 1;
  return start;
}

export function boundLength(text: string): number {
  let length = 0;
  while (length < text.length && !BREAKABLE_SPACE.test(text.charAt(length))) length += 1;
  return length;
}
