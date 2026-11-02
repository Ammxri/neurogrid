"""Which NeuroGrid report a file is (NV-F07, A-96): the part 'report' of the export takes only NeuroGrid's own
reports. The HTML side and the refusals without a browser; the printed reports and the dossier are identified
in tests/integration/test_dossier.py (pdf)."""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pypdf
import pytest

from neurogrid import pipeline
from neurogrid.kernel.errors import InputError
from neurogrid.kernel.pdf import pdf_date
from neurogrid.model.results import Results
from neurogrid.report.identify import DOSSIER_FILE, IdentifiedReport, dossier_title, identify
from neurogrid.report.output import html_document
from neurogrid.report.texts import disclaimer, translator

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = date(2026, 10, 11)


@pytest.fixture(scope="module")
def results() -> Results:
    return pipeline.run_check(FIX / "bids_ok", pipeline.CheckOptions(as_of=AS_OF))


@pytest.fixture(scope="module")
def documents(results: Results) -> dict[str, str]:
    return {lang: html_document(results, lang) for lang in ("zh", "en")}


def _invalid(data: bytes) -> None:
    with pytest.raises(InputError) as info:
        identify(data, 3)
    assert info.value.message_key == "export.report_invalid" and info.value.params == {"index": 3}


def test_reports_are_identified_by_their_head(documents: dict[str, str]) -> None:
    for lang, document in documents.items():
        found = identify(document.encode("utf-8"))
        assert found == IdentifiedReport("html", lang) and not found.dossier
        assert found.name == f"report.{lang}.html"
    assert IdentifiedReport("pdf", None).name == DOSSIER_FILE == "dossier.pdf"
    assert IdentifiedReport("pdf", "zh").name == "report.zh.pdf"


def test_an_html_file_that_is_no_neurogrid_report_is_refused(documents: dict[str, str]) -> None:
    document = documents["en"]
    csp = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:"
    assert csp in document and '<meta name="generator" content="NeuroGrid ' in document
    changed = (
        document.replace(csp, "default-src *"),  # no CSP of A-08
        document.replace('content="NeuroGrid ', 'content="Other '),  # another generator
        document.replace('<html lang="en">', '<html lang="de">'),  # a language without a report
        document.replace(disclaimer("en"), disclaimer("zh"), 1),  # the fixed sentence of another language
        document.replace(
            '<meta name="generator"', '<meta name="generator" content="NeuroGrid 1">\n<meta name="generator"'
        ),  # two generators
        document.replace("</head>", ""),
        "<html><head><title>notes</title></head><body>NeuroGrid</body></html>",
    )
    for text in changed:
        assert text != document
        _invalid(text.encode("utf-8"))
    _invalid(document.encode("utf-16"))  # not UTF-8
    _invalid(b"\xff\xfe" + document.encode("utf-8"))
    _invalid(b"")


def _pdf(title: str, stamp: str) -> bytes:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(595, 842)
    writer.add_metadata(
        {
            "/Title": title,
            "/Creator": "Chromium",
            "/Producer": "Skia/PDF m153",
            "/CreationDate": stamp,
            "/ModDate": stamp,
        }
    )
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_a_pdf_must_carry_a_report_title_the_reference_date_and_pass_the_qa_gate() -> None:
    """A PDF with the right title and date but without the fixed sentence and the report fonts is refused:
    the title alone is no proof (A-96)."""
    stamp = pdf_date(AS_OF)
    for title in (translator("zh").t("report.title"), translator("en").t("report.title"), dossier_title()):
        _invalid(_pdf(title, stamp))  # a blank page fails the QA gate
    _invalid(_pdf("Some other report", stamp))
    _invalid(_pdf(translator("en").t("report.title"), "D:20261011183612+02'00'"))  # Chromium's own stamp
    _invalid(b"%PDF-1.4\nnot a pdf")


def test_the_dossier_title_holds_both_languages() -> None:
    title = dossier_title()
    assert (
        title
        == f"{translator('zh').t('report.dossier.title')} / {translator('en').t('report.dossier.title')}"
    )
    assert "证明材料汇编" in title  # zh core term (owner answer 5)
