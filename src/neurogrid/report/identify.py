"""Which NeuroGrid report a file is (NV-F07, REP-08; A-96, A-99). ``vault export`` packs only NeuroGrid's own
reports as its part 'report', each under a fixed name: ``report.<lang>.<html|pdf>`` or ``dossier.pdf``. The
pipeline identifies them here and hands them to vault.export, which never imports the report (ARC-01).

- HTML: UTF-8 text whose head declares the Content-Security-Policy of A-08 (kernel.pdf.has_csp), a
  ``<meta name="generator">`` that starts with "NeuroGrid " and a ``<meta name="description">`` holding the
  fixed sentence of the language its ``<html lang>`` names (zh-CN or en), as report.html.j2 writes them.
- PDF: its /Info Title is the report title of a language (report.title) or the dossier title (both
  languages), its /CreationDate the reference date in NeuroGrid's form, and it passes the QA gate
  (kernel.pdf.qa_gate) with the report fonts, the five /Info keys and that language's fixed sentence on every
  page; the dossier with the fixed sentence of at least one language on every page (every_page_any).

Anything else is errors.export.report_invalid {index} (exit 2): the position of the file among the --report
options, never its name (any file an operator gave, A-51). Only NeuroGrid's own words are compared: a report
of an earlier version with the same title and fixed sentence is a NeuroGrid report too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal

from neurogrid.kernel.errors import InputError
from neurogrid.kernel.fonts import postscript_names
from neurogrid.kernel.pdf import PdfExpect, PdfMeta, document_info, has_csp, qa_gate, reference_date
from neurogrid.report.texts import FONT_FILES, REPORT_LANGUAGES, disclaimer, translator

ReportFormat = Literal["html", "pdf"]
PDF_MAGIC = b"%PDF-"
GENERATOR_PREFIX = "NeuroGrid "  # <meta name="generator" content="NeuroGrid <version>">
HTML_LANGUAGES = {"zh-CN": "zh", "en": "en"}  # <html lang> of report.html.j2 -> report language
TITLE_KEY = "report.title"
DOSSIER_TITLE_KEY = "report.dossier.title"
DOSSIER_FILE = "dossier.pdf"
_HEAD_END = re.compile(r"</head\s*>", re.IGNORECASE)


def dossier_title() -> str:
    """The title of the dossier in both report languages (zh / en): the <title> of its index part and the
    /Info Title of dossier.pdf (A-99)."""
    return " / ".join(translator(lang).t(DOSSIER_TITLE_KEY) for lang in REPORT_LANGUAGES)


@dataclass(frozen=True)
class IdentifiedReport:
    """A NeuroGrid report: its format and language; ``lang`` None is the dossier (both languages)."""

    format: ReportFormat
    lang: str | None

    @property
    def dossier(self) -> bool:
        return self.lang is None

    @property
    def name(self) -> str:
        """The fixed name in the export (A-96): report.<lang>.<format> or dossier.pdf."""
        return DOSSIER_FILE if self.lang is None else f"report.{self.lang}.{self.format}"


class _Head(HTMLParser):
    """The language of <html> and the generator and description of the <meta> elements in the head."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang: str | None = None
        self.meta: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value or "" for name, value in attrs}
        if tag == "html" and self.lang is None:
            self.lang = values.get("lang", "")
        elif tag == "meta" and "name" in values:
            self.meta.setdefault(values["name"].strip().lower(), []).append(values.get("content", ""))


def _invalid(index: int) -> InputError:
    return InputError("export.report_invalid", index=index)


def _identify_html(data: bytes, index: int) -> IdentifiedReport:
    try:
        document = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _invalid(index) from None
    end = _HEAD_END.search(document)
    if end is None:
        raise _invalid(index)
    head = _Head()
    head.feed(document[: end.end()])
    head.close()
    lang = HTML_LANGUAGES.get(head.lang or "")
    generators = head.meta.get("generator", [])
    if (
        lang is None
        or not has_csp(document)
        or len(generators) != 1
        or not generators[0].startswith(GENERATOR_PREFIX)
        or head.meta.get("description") != [disclaimer(lang)]
    ):
        raise _invalid(index)
    return IdentifiedReport("html", lang)


def _identify_pdf(data: bytes, index: int) -> IdentifiedReport:
    info = document_info(data)
    title = info.get("/Title", "")
    as_of = reference_date(info.get("/CreationDate", ""))
    titles = {translator(lang).t(TITLE_KEY): lang for lang in REPORT_LANGUAGES}
    meta = PdfMeta(title=title, as_of=as_of) if as_of is not None else None
    if meta is None:
        raise _invalid(index)
    fonts = postscript_names(FONT_FILES)
    if title == dossier_title():
        lang = None
        expect = PdfExpect(
            meta=meta, fonts=fonts, every_page_any=tuple(disclaimer(code) for code in REPORT_LANGUAGES)
        )
    elif title in titles:
        lang = titles[title]
        expect = PdfExpect(meta=meta, fonts=fonts, every_page=(disclaimer(lang),))
    else:
        raise _invalid(index)
    if qa_gate(data, expect):
        raise _invalid(index)
    return IdentifiedReport("pdf", lang)


def identify(data: bytes, index: int = 1) -> IdentifiedReport:
    """The NeuroGrid report in ``data`` (a PDF by its magic bytes, else HTML), or errors.export.report_invalid
    {index} (InputError, exit 2; ``index``: the 1-based position of the file among the --report options)."""
    if data.startswith(PDF_MAGIC):
        return _identify_pdf(data, index)
    return _identify_html(data, index)
