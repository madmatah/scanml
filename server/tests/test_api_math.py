"""LaTeX formulas found by the OCR: kept as written in the library, marked in the HTML previews."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from scanmylib.devtools import fake_ocr
from scanmylib.devtools.fake_ocr import ParseResponse, canned_page
from support import AUTH, create_document, page_image, running_api, upload, wait_until_processed

DISPLAY = r"$$\frac{a}{b}=\sqrt{x^2+1}$$"
INLINE = "$E=mc^2$"
DOLLAR_AMOUNTS = "5 $ and 10 $"
# As PaddleOCR-VL writes a table read as a formula, with a missing brace (KaTeX cannot parse it).
BROKEN = r"$$ \begin{array}{c|c}{X=1}&{X=2,5}\\ {Y=7,5&{Y=8} \end{array} $$"
MARKDOWN = f"## Formulas\n\n{DISPLAY}\n\nRésumé: {INLINE}. Prices: {DOLLAR_AMOUNTS}.\n\n{BROKEN}\n"


def build_page_with_formulas(width: int, height: int, request_id: str | None) -> ParseResponse:
    return {**canned_page(width, height, request_id), "markdown": MARKDOWN}


@dataclass(frozen=True)
class FormulaPage:
    markdown_files: dict[str, str]
    previews: dict[str, str]


@pytest.fixture(scope="module")
def formula_page(tmp_path_factory: pytest.TempPathFactory) -> FormulaPage:
    with pytest.MonkeyPatch.context() as patch, running_api(tmp_path_factory.mktemp("api")) as api:
        patch.setattr(fake_ocr, "canned_page", build_page_with_formulas)
        document_id = create_document(api.client)
        page = upload(api.client, document_id, page_image(3)).json()
        wait_until_processed(api.client, document_id)
        page_file = api.settings.library_dir / "sample-cafe-guide" / "pages" / f"{page['key']}.md"
        return FormulaPage(
            markdown_files={
                "page": page_file.read_text(),
                "document": api.client.get(f"/api/documents/{document_id}/markdown", headers=AUTH).text,
            },
            previews={
                "page": api.client.get(f"/api/pages/{page['id']}/html", headers=AUTH).json()["html"],
                "document": api.client.get(f"/api/documents/{document_id}/html", headers=AUTH).json()["html"],
            },
        )


class TestAPageWhoseOcrFoundFormulas:
    class TestWhenItsMarkdownIsWrittenToTheLibrary:
        def test_should_keep_a_display_formula_as_latex(self, formula_page: FormulaPage) -> None:
            assert {name: DISPLAY in text for name, text in formula_page.markdown_files.items()} == {
                "page": True,
                "document": True,
            }

        def test_should_keep_an_inline_formula_as_latex(self, formula_page: FormulaPage) -> None:
            assert {name: INLINE in text for name, text in formula_page.markdown_files.items()} == {
                "page": True,
                "document": True,
            }

        def test_should_leave_dollar_amounts_as_they_are(self, formula_page: FormulaPage) -> None:
            assert {name: DOLLAR_AMOUNTS in text for name, text in formula_page.markdown_files.items()} == {
                "page": True,
                "document": True,
            }

        def test_should_keep_a_formula_that_katex_cannot_parse_as_latex(self, formula_page: FormulaPage) -> None:
            assert {name: BROKEN in text for name, text in formula_page.markdown_files.items()} == {
                "page": True,
                "document": True,
            }

    class TestWhenItIsPreviewedAsHtml:
        def test_should_mark_a_display_formula_for_the_math_renderer(self, formula_page: FormulaPage) -> None:
            marked = r'<div class="math-display">\frac{a}{b}=\sqrt{x^2+1}</div>'
            assert {name: marked in html for name, html in formula_page.previews.items()} == {
                "page": True,
                "document": True,
            }

        def test_should_mark_an_inline_formula_but_not_dollar_amounts(self, formula_page: FormulaPage) -> None:
            marked = '<p>Résumé: <span class="math-inline">E=mc^2</span>. Prices: 5 $ and 10 $.</p>'
            assert {name: marked in html for name, html in formula_page.previews.items()} == {
                "page": True,
                "document": True,
            }

        def test_should_mark_a_formula_that_katex_cannot_parse_with_its_markup_escaped(
            self, formula_page: FormulaPage
        ) -> None:
            marked = (
                r'<div class="math-display">\begin{array}{c|c}{X=1}&amp;{X=2,5}\\ {Y=7,5&amp;{Y=8} \end{array}</div>'
            )
            assert {name: marked in html for name, html in formula_page.previews.items()} == {
                "page": True,
                "document": True,
            }
