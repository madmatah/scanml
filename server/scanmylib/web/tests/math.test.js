/**
 * Unit tests of static/js/lib/math.js, with the KaTeX served to the browser
 * (static/vendor/katex) and Node's built-in test runner. From the repository
 * root:
 *
 *   docker run --rm --network none --read-only --user 1000:1000 \
 *     -v "$PWD/server/scanmylib/web:/web:ro" node:22-bookworm-slim node --test '/web/tests/*.test.js'
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { describe, mock, test } from 'node:test';

import { boundLength, boundStart, katexOptions } from '../static/js/lib/math.js';

const katex = createRequire(import.meta.url)('../static/vendor/katex/katex.min.js');

/** KaTeX's HTML for `tex`, and the number of console warnings it gave meanwhile. */
function typeset(tex, options = katexOptions()) {
  const warn = mock.method(console, 'warn', () => {});
  try {
    return { html: katex.renderToString(tex, options), warnings: warn.mock.callCount() };
  } finally {
    warn.mock.restore();
  }
}

/** The text a reader sees in KaTeX's HTML (its MathML copy and the tags left out). */
function visibleText(html) {
  return html.replace(/<span class="katex-mathml">.*?<\/math><\/span>/s, '').replace(/<[^>]+>/g, '');
}

// Typographic LaTeX as PaddleOCR-VL writes it (invented examples): 19$ ^{th} $ century,
// Doe$ ^{12} $, Acme$ ^{™} $, Example$ ^{®} $, $ 8^{\text{va}} $, superscript letters ($ ^{e} $)…
const TYPOGRAPHIC = ['^{e}', '^{12}', '^{™}', '^{®}', '^{\\text{™}}', '^{\\text{®}}', '8^{\\text{va}}', '^{th}', '^{m}'];

describe('typographic LaTeX from the OCR', () => {
  test('is typeset without error or console warning', () => {
    for (const tex of TYPOGRAPHIC) {
      const { html, warnings } = typeset(tex);
      assert.ok(!html.includes('katex-error'), tex);
      assert.equal(warnings, 0, tex);
    }
  });

  test('keeps its characters', () => {
    assert.equal(visibleText(typeset('^{™}').html), '™');
    assert.equal(visibleText(typeset('^{\\text{™}}').html), '™');
    assert.equal(visibleText(typeset('^{e}').html), 'e');
    assert.equal(visibleText(typeset('8^{\\text{va}}').html), '8va');
  });

  test('® is drawn as a circled upright R, as in text', () => {
    for (const tex of ['^{®}', '^{\\text{®}}']) {
      const { html } = typeset(tex);
      assert.match(visibleText(html), /^R/, tex);
      assert.ok(!html.includes('mathnormal'), `${tex}: no math italic R`);
      assert.ok(html.includes('<mtext>®</mtext>'), `${tex}: ® in the MathML read by screen readers`);
    }
  });

  test('needs strict: "ignore" (KaTeX warns about ™ by default, rejects it when strict)', () => {
    assert.ok(typeset('^{™}', { ...katexOptions(), strict: 'warn' }).warnings > 0);
    assert.ok(typeset('^{™}', { ...katexOptions(), strict: 'error' }).html.includes('katex-error'));
  });

  test('a formula cannot change the next ones with \\gdef', () => {
    const options = katexOptions();
    typeset('\\gdef\\frac#1#2{X}\\gdef\\ocrmacro{X}', options);
    assert.notEqual(options.macros, katexOptions().macros);
    assert.equal(visibleText(typeset('\\ocrmacro').html), '\\ocrmacro'); // unknown command, shown as written
    assert.ok(typeset('\\frac{a}{b}').html.includes('mfrac'));
  });

  test('stays untrusted', () => {
    const { html } = typeset('\\href{https://example.com}{x} \\htmlClass{evil}{y}');
    assert.ok(!html.includes('<a ') && !html.includes('href="') && !html.includes('evil"'), html);
  });
});

describe('text written against an inline formula', () => {
  test('the end of the word before it', () => {
    assert.equal(boundStart('In the 19'), 7); // In the 19$^{th}$ century: "19"
    assert.equal(boundStart('the handbook by Doe'), 16);
    assert.equal(boundStart('19'), 0); // all of it
    assert.equal(boundStart('In '), 3); // none: a space comes first
    assert.equal(boundStart(''), 0);
  });

  test('the start of what follows it', () => {
    assert.equal(boundLength(', then'), 1); // Doe$^{12}$, then: the comma
    assert.equal(boundLength('.'), 1);
    assert.equal(boundLength('),'), 2);
    assert.equal(boundLength(' century'), 0);
    assert.equal(boundLength(''), 0);
  });

  test('no-break spaces bind, other spaces do not', () => {
    // Punctuation after a narrow no-break space, as in French typography.
    assert.equal(boundLength('\u202f; and so on'), 2);
    assert.equal(boundStart('see p.\u00a012'), 4);
    assert.equal(boundStart('a\tb'), 2);
    assert.equal(boundStart('a\nb'), 2);
    assert.equal(boundLength('\u2009x'), 0); // thin space: a line may break there
  });
});
