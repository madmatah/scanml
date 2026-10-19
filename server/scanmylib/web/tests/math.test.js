import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { beforeEach, describe, it, mock } from 'node:test';

import { boundLength, boundStart, katexOptions } from '../static/js/lib/math.js';

const katex = createRequire(import.meta.url)('../static/vendor/katex/katex.min.js');

function typeset(tex, options) {
  const warn = mock.method(console, 'warn', () => {});
  try {
    return { html: katex.renderToString(tex, options), warningCount: warn.mock.callCount() };
  } finally {
    warn.mock.restore();
  }
}

// KaTeX's HTML holds a MathML copy of the formula for screen readers, which a reader does not see.
function readVisibleText(html) {
  return html.replace(/<span class="katex-mathml">.*?<\/math><\/span>/s, '').replace(/<[^>]+>/g, '');
}

describe('The math typesetting', () => {
  describe('The katexOptions() function', () => {
    describe('When KaTeX typesets the typographic LaTeX of the OCR with them', () => {
      // As PaddleOCR-VL writes it against words (invented examples): 19$ ^{th} $ century, Doe$ ^{12} $,
      // Acme$ ^{™} $, Example$ ^{®} $, $ 8^{\text{va}} $.
      const formulas = [
        { kind: 'a superscript letter', tex: '^{e}' },
        { kind: 'a superscript number', tex: '^{12}' },
        { kind: 'a trademark sign in math', tex: '^{™}' },
        { kind: 'a registered sign in math', tex: '^{®}' },
        { kind: 'a trademark sign in text', tex: '^{\\text{™}}' },
        { kind: 'a registered sign in text', tex: '^{\\text{®}}' },
        { kind: 'an octave mark', tex: '8^{\\text{va}}' },
        { kind: 'an ordinal suffix', tex: '^{th}' },
        { kind: 'another superscript letter', tex: '^{m}' },
      ];

      for (const { kind, tex } of formulas) {
        describe(`When the formula is ${kind}, ${tex}`, () => {
          let typesetFormula;
          beforeEach(() => {
            typesetFormula = typeset(tex, katexOptions());
          });

          it('should typeset it without an error', () => {
            assert.doesNotMatch(typesetFormula.html, /katex-error/);
          });

          it('should give no console warning', () => {
            assert.equal(typesetFormula.warningCount, 0);
          });
        });
      }
    });

    describe('When KaTeX typesets characters of text in a formula with them', () => {
      const formulas = [
        { tex: '^{™}', text: '™' },
        { tex: '^{\\text{™}}', text: '™' },
        { tex: '^{e}', text: 'e' },
        { tex: '8^{\\text{va}}', text: '8va' },
      ];

      for (const { tex, text } of formulas) {
        describe(`When the formula is ${tex}`, () => {
          let typesetFormula;
          beforeEach(() => {
            typesetFormula = typeset(tex, katexOptions());
          });

          it(`should keep its characters, showing ${text}`, () => {
            assert.equal(readVisibleText(typesetFormula.html), text);
          });
        });
      }
    });

    for (const tex of ['^{®}', '^{\\text{®}}']) {
      describe(`When KaTeX typesets the registered sign ${tex} with them`, () => {
        let typesetFormula;
        beforeEach(() => {
          typesetFormula = typeset(tex, katexOptions());
        });

        it('should draw it with an R, as in text', () => {
          assert.match(readVisibleText(typesetFormula.html), /^R/);
        });

        it('should draw the R upright, not as a math italic one', () => {
          assert.doesNotMatch(typesetFormula.html, /mathnormal/);
        });

        it('should keep ® in the MathML that screen readers read', () => {
          assert.match(typesetFormula.html, /<mtext>®<\/mtext>/);
        });
      });
    }

    describe('When KaTeX typesets the trademark sign with them, but its strict mode set to warn, as by default', () => {
      const tex = '^{™}';
      let typesetFormula;
      beforeEach(() => {
        typesetFormula = typeset(tex, { ...katexOptions(), strict: 'warn' });
      });

      it('should warn on the console, which is why the options ignore the strict mode', () => {
        assert.ok(typesetFormula.warningCount > 0);
      });
    });

    describe('When KaTeX typesets the trademark sign with them, but its strict mode set to error', () => {
      const tex = '^{™}';
      let typesetFormula;
      beforeEach(() => {
        typesetFormula = typeset(tex, { ...katexOptions(), strict: 'error' });
      });

      it('should show an error, which is why the options ignore the strict mode', () => {
        assert.match(typesetFormula.html, /katex-error/);
      });
    });

    describe('When a formula typeset with them defines macros with \\gdef', () => {
      const definingTex = '\\gdef\\frac#1#2{X}\\gdef\\ocrmacro{X}';
      const macroTex = '\\ocrmacro';
      const fractionTex = '\\frac{a}{b}';
      let definingOptions;
      let nextOptions;
      let nextMacroHtml;
      let nextFractionHtml;
      beforeEach(() => {
        definingOptions = katexOptions();
        typeset(definingTex, definingOptions);
        nextOptions = katexOptions();
        nextMacroHtml = typeset(macroTex, nextOptions).html;
        nextFractionHtml = typeset(fractionTex, katexOptions()).html;
      });

      it('should give the next formula macros of its own', () => {
        assert.notEqual(nextOptions.macros, definingOptions.macros);
      });

      it('should leave a macro it defined unknown to the next formula, which shows it as written', () => {
        assert.equal(readVisibleText(nextMacroHtml), macroTex);
      });

      it('should leave a command it redefined as KaTeX defines it for the next formula', () => {
        assert.match(nextFractionHtml, /mfrac/);
      });
    });

    describe('When a formula typeset with them asks for a link and a class of its own', () => {
      const tex = '\\href{https://example.com}{x} \\htmlClass{evil}{y}';
      let html;
      beforeEach(() => {
        html = typeset(tex, katexOptions()).html;
      });

      it('should draw no link, since the text of the OCR is untrusted', () => {
        assert.doesNotMatch(html, /<a |href="/);
      });

      it('should add no class of the formula, since the text of the OCR is untrusted', () => {
        assert.doesNotMatch(html, /evil"/);
      });
    });
  });

  describe('The boundStart() function', () => {
    const texts = [
      {
        situation: 'When the text before an inline formula ends with a number, as in 19$^{th}$',
        text: 'In the 19',
        start: 7,
        rule: 'should start at the number, which stays with the formula',
      },
      {
        situation: 'When the text before an inline formula ends with a name, as in Doe$^{12}$',
        text: 'the handbook by Doe',
        start: 16,
        rule: 'should start at the name, which stays with the formula',
      },
      {
        situation: 'When the text before an inline formula is one word',
        text: '19',
        start: 0,
        rule: 'should start at the start of the text, all of which stays with the formula',
      },
      {
        situation: 'When the text before an inline formula ends with a space',
        text: 'In ',
        start: 3,
        rule: 'should start at the end of the text, none of which stays with the formula',
      },
      {
        situation: 'When there is no text before an inline formula',
        text: '',
        start: 0,
        rule: 'should start at the end of the empty text',
      },
      {
        situation: 'When a no-break space comes before the last word',
        text: 'see p.\u00a012',
        start: 4,
        rule: 'should start at the word before the no-break space, which binds them',
      },
      {
        situation: 'When a tab comes before the last word',
        text: 'a\tb',
        start: 2,
        rule: 'should start after the tab, where a line may break',
      },
      {
        situation: 'When a line feed comes before the last word',
        text: 'a\nb',
        start: 2,
        rule: 'should start after the line feed, where a line may break',
      },
    ];

    for (const { situation, text, start: expectedStart, rule } of texts) {
      describe(situation, () => {
        let start;
        beforeEach(() => {
          start = boundStart(text);
        });

        it(rule, () => {
          assert.equal(start, expectedStart);
        });
      });
    }
  });

  describe('The boundLength() function', () => {
    const texts = [
      {
        situation: 'When a comma follows an inline formula, as in Doe$^{12}$, then',
        text: ', then',
        length: 1,
        rule: 'should bind the comma to the formula',
      },
      {
        situation: 'When a period alone follows an inline formula',
        text: '.',
        length: 1,
        rule: 'should bind the period to the formula',
      },
      {
        situation: 'When two punctuation marks follow an inline formula',
        text: '),',
        length: 2,
        rule: 'should bind both to the formula',
      },
      {
        situation: 'When a space follows an inline formula',
        text: ' century',
        length: 0,
        rule: 'should bind nothing to the formula',
      },
      {
        situation: 'When nothing follows an inline formula',
        text: '',
        length: 0,
        rule: 'should bind nothing to the formula',
      },
      {
        situation: 'When a narrow no-break space comes before a punctuation mark, as in French typography',
        text: '\u202f; and so on',
        length: 2,
        rule: 'should bind both to the formula',
      },
      {
        situation: 'When a thin space follows an inline formula',
        text: '\u2009x',
        length: 0,
        rule: 'should bind nothing to the formula, since a line may break at a thin space',
      },
    ];

    for (const { situation, text, length: expectedLength, rule } of texts) {
      describe(situation, () => {
        let length;
        beforeEach(() => {
          length = boundLength(text);
        });

        it(rule, () => {
          assert.equal(length, expectedLength);
        });
      });
    }
  });
});
