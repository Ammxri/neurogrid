"""The report files (CLI-05, NG-F13, A-08, A-26, A-27): ``report.<lang>.html`` and ``report.<lang>.pdf`` per
language, written all or nothing.

1. ``pdf`` requested: the PDF browser is located and checked before anything is rendered, so a missing or
   wrong browser or missing Linux libraries end with exit 2 and nothing written (``html`` alone never needs
   the browser, A-26). Then the output folder is checked (check_output_folder): an output that cannot be
   written ends with exit 2 before the browser starts, not after both PDFs were printed.
2. Per language the report is rendered twice: once to learn its characters, once with the @font-face rules
   of the font subsets that cover them (fonts embedded in HTML and PDF alike). Characters the fonts cannot
   draw are written as ``[U+XXXX]`` (report.glyphs.glyph_safe), so dataset text never makes the browser
   use a system font.
3. The PDF is a print of exactly the HTML that is delivered; every PDF passes the QA gate. The browser works
   in a private folder in the computer's temporary folder (kernel.pdf.browser_work), not below the output
   folder, so a long output path never reaches the browser's profile.
4. Only then are all files written, each atomically; a failure leaves none of them behind.
"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from neurogrid.kernel.errors import InputError, NeuroGridError, PdfError
from neurogrid.kernel.fonts import FONT_FAMILY, font_codepoints, postscript_names, subset_font_css
from neurogrid.kernel.pdf import (
    PdfExpect,
    PdfMeta,
    PdfPrinter,
    ShellInstall,
    browser_work,
    html_title,
    locate_shell,
    preflight,
    qa_gate,
)
from neurogrid.model.results import Results
from neurogrid.report.glyphs import glyph_safe
from neurogrid.report.render import page_text, render_report
from neurogrid.report.texts import FONT_FILES, translator

FORMATS = ("html", "pdf")
# the browser context's locale per report language (kernel.pdf.LOCALES)
LOCALES = {"zh": "zh-CN", "en": "en-US"}
# phrases the QA gate requires once per PDF: title and the six section headings (PRD §14)
REQUIRED_ONCE = (
    "report.title",
    "report.section.cover",
    "report.section.summary",
    "report.section.findings",
    "report.section.metrics",
    "report.section.evidence",
    "report.section.appendix",
)


def glyph_safe_document(document: str, covered: frozenset[int]) -> str:
    """``document`` with every character the report fonts cannot draw written as ``[U+XXXX]``, through
    report.glyphs.glyph_safe (the one place that writes the replacement). Only the distinct characters are
    tested, so a document that is glyph-safe already (markup and CSS are ASCII) costs one set()."""
    unsafe = sorted(char for char in set(document) if glyph_safe(char, covered) != char)
    if not unsafe:
        return document
    pattern = re.compile("[" + "".join(re.escape(char) for char in unsafe) + "]")
    return pattern.sub(lambda match: glyph_safe(match.group(0), covered), document)


def html_document(results: Results, lang: str) -> str:
    """The delivered HTML of one language, with the embedded font subsets (deterministic)."""
    covered = font_codepoints(FONT_FILES)
    draft = glyph_safe_document(render_report(results, lang), covered)
    css = subset_font_css(FONT_FILES, draft + page_text(lang), family=FONT_FAMILY)
    return glyph_safe_document(render_report(results, lang, font_css=css), covered)


def pdf_expectation(results: Results, lang: str, document: str) -> PdfExpect:
    """The fixed sentence on every page (A-08); title, headings and the placeholder banner once (A-41)."""
    tr = translator(lang).t
    once = [tr(key) for key in REQUIRED_ONCE]
    if any(pack.source_status.value == "placeholder" for pack in results.rulepacks):
        once.append(tr("report.placeholder_banner"))
    meta = PdfMeta(title=html_title(document), as_of=results.config.as_of)
    return PdfExpect(
        meta=meta, fonts=postscript_names(FONT_FILES), every_page=(tr("disclaimer"),), once=tuple(once)
    )


def _print_all(results: Results, documents: Mapping[str, str], shell: ShellInstall) -> dict[str, bytes]:
    pdfs: dict[str, bytes] = {}
    with browser_work() as work, PdfPrinter(shell, work) as printer:
        for lang, document in documents.items():
            source = work / f"report.{lang}.html"
            source.write_bytes(document.encode("utf-8"))
            expect = pdf_expectation(results, lang, document)
            printed = printer.print(source, expect.meta, locale=LOCALES[lang])
            violations = qa_gate(printed.data, expect, log=printed.log)
            if violations:
                raise PdfError("pdf.qa_failed", checks=",".join(violations))
            pdfs[lang] = printed.data
    return pdfs


def _stage(target: Path, data: bytes) -> Path:
    if target.is_dir():
        raise InputError("output.is_directory")
    handle, name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def check_output_folder(folder: Path, targets: Sequence[Path]) -> None:
    """Before the browser starts: no target is a folder (output.is_directory) and the output folder exists
    or can be created and takes a new file (output.not_writable), the checks write_all makes when it
    writes. The browser's work folder no longer lies below the output folder, so without this an output
    that cannot be written would end the run only after both PDFs were printed."""
    for target in targets:
        if target.is_dir():
            raise InputError("output.is_directory")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(dir=folder, prefix=".report.", suffix=".tmp")
        os.close(handle)
        Path(name).unlink()
    except OSError:
        raise InputError("output.not_writable") from None


def write_all(files: Mapping[Path, bytes]) -> None:
    """Every file is staged next to its target first and renamed only when all were staged, so a full disk
    or a missing permission leaves none of the new files behind."""
    staged: list[tuple[Path, Path]] = []
    try:
        for target, data in files.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            staged.append((_stage(target, data), target))
        for temporary, target in staged:
            temporary.replace(target)
    except OSError:
        raise InputError("output.not_writable") from None
    finally:
        for temporary, _target in staged:
            temporary.unlink(missing_ok=True)


def write_reports(
    results: Results,
    languages: Sequence[str],
    formats: Sequence[str],
    folder: Path,
    *,
    environ: Mapping[str, str],
) -> list[Path]:
    """Write ``report.<lang>.<format>`` for every language and format into ``folder``; returns the paths in
    the order languages × formats. PdfError (exit 2) or InputError leave no report file behind."""
    unknown = [name for name in formats if name not in FORMATS]
    if unknown:
        raise NeuroGridError("errors.report.format_unavailable", format=unknown[0])
    shell = None
    if "pdf" in formats:  # before any rendering (A-26)
        shell = locate_shell(environ)
        preflight(shell)
    existed = folder.exists()
    targets = {(lang, name): folder / f"report.{lang}.{name}" for lang in languages for name in formats}
    try:
        check_output_folder(folder, list(targets.values()))
        documents = {lang: html_document(results, lang) for lang in languages}
        pdfs = _print_all(results, documents, shell) if shell is not None else {}
        files = {
            target: documents[lang].encode("utf-8") if name == "html" else pdfs[lang]
            for (lang, name), target in targets.items()
        }
        write_all(files)
    except BaseException:
        if not existed and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()  # a folder this run created for nothing
        raise
    return list(files)
