"""LaTeX formulas found by the OCR: kept as written in the library, marked in the HTML previews."""

from __future__ import annotations

from support import AUTH, create_document, page_image, upload, wait_until_processed

from scanmylib.devtools import fake_ocr

DISPLAY = r"$$\frac{a}{b}=\sqrt{x^2+1}$$"
# As PaddleOCR-VL writes a table read as a formula, with a missing brace (KaTeX cannot parse it).
BROKEN = r"$$ \begin{array}{c|c}{X=1}&{X=2,5}\\ {Y=7,5&{Y=8} \end{array} $$"
MARKDOWN = f"## Formulas\n\n{DISPLAY}\n\nRésumé: $E=mc^2$. Prices: 5 $ and 10 $.\n\n{BROKEN}\n"


def test_formulas_are_latex_in_the_library_and_marked_in_previews(client, library_dir, monkeypatch):
    canned_page = fake_ocr.canned_page

    def page_with_formulas(width: int, height: int, request_id: str | None) -> dict:
        return {**canned_page(width, height, request_id), "markdown": MARKDOWN}

    monkeypatch.setattr(fake_ocr, "canned_page", page_with_formulas)
    document_id = create_document(client)
    page = upload(client, document_id, page_image(3)).json()
    wait_until_processed(client, document_id)

    page_md = (library_dir / "sample-cafe-guide" / "pages" / f"{page['key']}.md").read_text()
    document_md = client.get(f"/api/documents/{document_id}/markdown", headers=AUTH).text
    for markdown in (page_md, document_md):
        for latex in (DISPLAY, "$E=mc^2$", "5 $ and 10 $", BROKEN):
            assert latex in markdown

    page_html = client.get(f"/api/pages/{page['id']}/html", headers=AUTH).json()["html"]
    document_html = client.get(f"/api/documents/{document_id}/html", headers=AUTH).json()["html"]
    for html in (page_html, document_html):
        assert r'<div class="math-display">\frac{a}{b}=\sqrt{x^2+1}</div>' in html
        assert '<p>Résumé: <span class="math-inline">E=mc^2</span>. Prices: 5 $ and 10 $.</p>' in html
        assert (
            r'<div class="math-display">\begin{array}{c|c}{X=1}&amp;{X=2,5}\\ {Y=7,5&amp;{Y=8} \end{array}</div>'
            in html
        )
