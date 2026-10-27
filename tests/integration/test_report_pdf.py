"""PDF reports (TECH-07, NG-F13, NG-N01, A-08, A-26, A-27, A-49, A-51, A-54).

The checks here use their own reading of the PDF (pypdf), not the QA gate they test (B2). Tests that print
are marked ``pdf``: skipped without the browser, failing without it when NEUROGRID_REQUIRE_PDF=1. The
others (HTML side of the pipeline, all-or-nothing without a browser) always run.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import html.parser
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pypdf
import pytest
from fontTools.ttLib import TTFont
from pypdf.generic import ContentStream, DictionaryObject

from conftest import folder_content, fresh_shell, long_path, short_folder  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.kernel import canonical, fonts, pdf
from neurogrid.kernel.errors import InputError, NeuroGridError, PdfError
from neurogrid.kernel.findings import SourceStatus, TimeRange
from neurogrid.kernel.fonts import (
    FONT_FAMILY,
    font_codepoints,
    postscript_names,
    shared_glyphs,
    subset_font_css,
)
from neurogrid.kernel.pdf import CSP, PdfExpect, PdfMeta, PdfPrinter, PrintedPdf, ShellInstall, qa_gate
from neurogrid.kernel.safety import WORK_LOCK
from neurogrid.model.results import Results
from neurogrid.report import output, texts
from neurogrid.report.output import html_document, write_reports
from neurogrid.report.render import page_text
from neurogrid.report.texts import FONT_FILES, translator

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = date(2026, 10, 11)
STAMP = "D:20261011000000+00'00'"
REPORT_FONT = re.compile(r"^/[A-Z]{6}\+NotoSansSC-(Regular|Bold)$")
FONTS = postscript_names(FONT_FILES)


@pytest.fixture(scope="module")
def results() -> Results:
    """bids_issues with core + bids + gxdsl008: errors, warnings, notes, dataset-level and manual findings;
    one finding gets 25 time ranges (A-10: 20 shown plus the count)."""
    checked = pipeline.run_check(
        FIX / "bids_issues", pipeline.CheckOptions(rulepacks=("bids", "gxdsl008"), as_of=AS_OF)
    )
    copy = checked.model_copy(deep=True)
    index = next(i for i, f in enumerate(copy.findings) if f.file is not None)
    ranges = [TimeRange(start_s=float(i), end_s=i + 0.5) for i in range(20)]
    copy.findings[index] = copy.findings[index].model_copy(
        update={"time_ranges": ranges, "time_ranges_total": 25}
    )
    return copy


@pytest.fixture(scope="module")
def written(
    results: Results, pdf_shell: ShellInstall, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, Path]:
    """The four reports of ``results`` (needs the browser: skipped or failed like every pdf test)."""
    folder = tmp_path_factory.mktemp("pdf") / "报告 out"
    paths = write_reports(results, ["zh", "en"], ["html", "pdf"], folder, environ=os.environ)
    assert [p.name for p in paths] == ["report.zh.html", "report.zh.pdf", "report.en.html", "report.en.pdf"]
    return {p.name: p for p in paths}


def _squeeze(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _texts(data: bytes) -> list[str]:
    return [page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(data)).pages]


def _fonts(resources: Any, found: list[dict[str, Any]]) -> None:
    """Own walk over fonts of a resource dictionary and its form XObjects (test oracle)."""
    resources = resources.get_object() if resources is not None else None
    if not isinstance(resources, DictionaryObject):
        return
    for ref in (resources.get("/Font") or {}).values():
        font = ref.get_object()
        entry: dict[str, Any] = {"subtype": font.get("/Subtype"), "base": str(font.get("/BaseFont"))}
        if font.get("/Subtype") == "/Type0":
            descendant = font["/DescendantFonts"][0].get_object()
            descriptor = descendant["/FontDescriptor"].get_object()
            entry.update(
                cid=descendant.get("/Subtype"),
                files=sorted(k for k in descriptor if k.startswith("/FontFile")),
                tounicode="/ToUnicode" in font,
            )
        found.append(entry)
    for ref in (resources.get("/XObject") or {}).values():
        xobject = ref.get_object()
        if xobject.get("/Subtype") == "/Form":
            _fonts(xobject.get("/Resources"), found)


def _font_list(data: bytes) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for page in pypdf.PdfReader(io.BytesIO(data)).pages:
        _fonts(page.get("/Resources"), found)
    return found


@pytest.mark.pdf
@pytest.mark.parametrize("lang", ["zh", "en"])
def test_pdf_qa_gate_green_zh_en(results: Results, written: dict[str, Path], lang: str) -> None:
    data = written[f"report.{lang}.pdf"].read_bytes()
    fonts = _font_list(data)
    assert fonts and {f["subtype"] for f in fonts} == {"/Type0"}  # no Type3, no simple system font
    for font in fonts:
        assert REPORT_FONT.match(font["base"]), font
        assert font["cid"] == "/CIDFontType2" and font["files"] == ["/FontFile2"] and font["tounicode"]
    assert {re.sub(r"^/[A-Z]{6}\+", "", f["base"]) for f in fonts} == {
        "NotoSansSC-Regular",
        "NotoSansSC-Bold",
    }
    text = "".join(_texts(data))
    assert not [ch for ch in text if 0x2E80 <= ord(ch) <= 0x2FDF or 0xF900 <= ord(ch) <= 0xFAFF]
    # the delivered HTML is exactly what was printed, and the runtime gate agrees
    document = written[f"report.{lang}.html"].read_text(encoding="utf-8")
    assert document == html_document(results, lang)
    assert qa_gate(data, output.pdf_expectation(results, lang, document)) == []


@pytest.mark.pdf
def test_metadata_title_dates_and_no_other_keys(results: Results, written: dict[str, Path]) -> None:
    for lang in ("zh", "en"):
        reader = pypdf.PdfReader(io.BytesIO(written[f"report.{lang}.pdf"].read_bytes()))
        info = {key: str(value) for key, value in (reader.metadata or {}).items()}
        assert sorted(info) == ["/CreationDate", "/Creator", "/ModDate", "/Producer", "/Title"]  # no /Subject
        assert info["/CreationDate"] == info["/ModDate"] == STAMP  # the reference date (A-11)
        assert info["/Title"] == translator(lang).t("report.title")  # neutral: no dataset name, no path
        assert info["/Creator"] == "Chromium" and info["/Producer"].startswith("Skia/PDF")
        root = reader.root_object
        assert "/Metadata" not in root and "/ID" not in reader.trailer


# Chromium's page content: the page's own flip (0.24 = 72/300) and then the CSS-pixel scale of the body,
# 3.125 x 0.24 = 0.75 pt per px (96 dpi). Shrink-to-fit (content wider than the page) lowers the latter.
_CM = re.compile(rb"(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+) -?[\d.]+ -?[\d.]+ cm")
DESIGNED_SCALE = b"3.125"


def _page_scales(data: bytes) -> list[set[bytes]]:
    """Per page the scale factors of every transformation of the content (test oracle), the page flip
    left out."""
    scales = []
    for page in pypdf.PdfReader(io.BytesIO(data)).pages:
        found = set()
        contents = page.get_contents()
        assert contents is not None
        for match in _CM.finditer(contents.get_data()):
            a, b, c, d = match.groups()
            assert b == c == b"0" and abs(float(a)) == abs(float(d)), match.group(0)
            if float(d) > 0:
                found.add(a)
        scales.append(found)
    return scales


@pytest.mark.pdf
def test_every_page_keeps_the_designed_scale(written: dict[str, Path]) -> None:
    """Review R01: nothing in the report is wider than its page, so Chromium never shrinks the print to fit.
    Before the repair the header 'Comment / justification' of the evidence table overflowed its column,
    the table its page, and every page of these reports was printed at 99.5 %."""
    for lang in ("zh", "en"):
        scales = _page_scales(written[f"report.{lang}.pdf"].read_bytes())
        assert scales and all(found == {DESIGNED_SCALE} for found in scales), (lang, scales)


@pytest.mark.pdf
def test_long_unbreakable_values_wrap_and_keep_the_page_scale(
    results: Results, written: dict[str, Path], tmp_path: Path
) -> None:
    """Review R01 (REP-00): a dataset name of 200 characters without a break (the limit of a real check
    run), a licence URL of 180 and a version of 120 (a hand-edited results.json) wrap in the cover table.
    Every page keeps the designed scale, the report keeps its page count, and every value is in the PDF in
    full. Before the repair the cover table widened the page: every page shrank to 2/3, the en report had 12
    pages instead of 21, and the name and the licence were clipped."""
    long_values = {
        "name": "N" * 200,
        "license": "https://example.org/" + "l" * 160,
        "version": "v" * 120,
    }
    changed = results.model_copy(deep=True)
    changed.dataset = changed.dataset.model_copy(update=long_values)
    paths = write_reports(changed, ["zh", "en"], ["pdf"], tmp_path, environ=os.environ)
    for lang, path in zip(("zh", "en"), paths, strict=True):
        data = path.read_bytes()
        scales = _page_scales(data)
        assert all(found == {DESIGNED_SCALE} for found in scales), (lang, scales)
        baseline = pypdf.PdfReader(io.BytesIO(written[f"report.{lang}.pdf"].read_bytes())).pages
        assert len(scales) == len(baseline), lang
        text = _squeeze("".join(_texts(data)))
        assert all(value in text for value in long_values.values()), lang


# The body cells of the auto-layout tables that hold NeuroGrid's own words, by table and column: the source
# status of a rule pack, the phase and its light, the coverage, the origin of a threshold, 'used'/'expired'.
# Every header holds own words too, except the AI label scopes (names from the dataset) after the first.
OWN_BODY_COLUMNS = {"rulepacks": [2], "phases": [0, 1], "coverage": [1], "params": [3], "exceptions": [5, 6]}
# The content width of the portrait page and of the landscape page 'wide' in CSS px (A4, 13 mm side margins,
# render.page_css), rounded down; the sections of the landscape page (report.css).
PAGE_WIDTHS = {False: int((210 - 26) / 25.4 * 96), True: int((297 - 26) / 25.4 * 96)}
WIDE_SECTIONS = "section#findings, section#metrics, section#evidence, section#appendix"
_OWN_WORDS_JS = """
([wide, sections, own]) => {
  const broken = [], checked = [];
  for (const table of document.querySelectorAll('table')) {
    if (getComputedStyle(table).tableLayout !== 'auto' || !!table.closest(sections) !== wide) continue;
    const name = table.className;
    for (const row of table.rows) {
      Array.from(row.cells).forEach((cell, index) => {
        const header = cell.tagName === 'TH';
        if (header ? name === 'labels' && row.parentElement.tagName === 'THEAD' && index > 0
                   : !(own[name] || []).includes(index)) return;
        const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          for (const match of node.data.matchAll(/\\S+/g)) {
            const range = document.createRange();
            range.setStart(node, match.index);
            range.setEnd(node, match.index + match[0].length);
            const lines = new Set(Array.from(range.getClientRects()).filter((r) => r.width > 0)
                                  .map((r) => Math.round(r.top)));
            checked.push(name + ': ' + match[0]);
            if (lines.size > 1) broken.push(name + ': ' + match[0]);
          }
        }
      });
    }
  }
  return [broken, checked];
}
"""


@pytest.mark.pdf
def test_own_words_never_break_in_the_auto_layout_tables(
    results: Results, written: dict[str, Path], pdf_shell: ShellInstall, tmp_path: Path
) -> None:
    """Review R01 follow-up (REP-00): overflow-wrap: anywhere on body lowers the min-content width of every
    cell, so in an auto-layout table a long column squeezed the others below NeuroGrid's own words: the
    rule-pack table on the cover printed 'Versio|n' in every en report (base and with long dataset values),
    c3be509 did not. Every whitespace-separated word of every header and of the own-vocabulary cells of the
    auto-layout tables stands on one line, laid out by the real shell at the content width of its page in
    print media, for the reports of ``results`` and with long dataset values, in zh and en."""
    long_values = {"name": "N" * 200, "license": "https://example.org/" + "l" * 160, "version": "v" * 120}
    changed = results.model_copy(deep=True)
    changed.dataset = changed.dataset.model_copy(update=long_values)
    extra = write_reports(changed, ["zh", "en"], ["html"], tmp_path / "long", environ=os.environ)
    documents = [written["report.zh.html"], written["report.en.html"], *extra]
    broken: list[tuple[str, bool, str]] = []
    with _measuring_page(pdf_shell) as (page, _work):
        page.emulate_media(media="print")
        for document in documents:
            lang = document.name.split(".")[1]
            for wide, width in PAGE_WIDTHS.items():
                page.set_viewport_size({"width": width, "height": 1200})
                page.goto(document.as_uri())
                page.evaluate("document.fonts.ready")
                assert page.evaluate("document.fonts.check(\"8pt 'NG Sans'\")"), document
                found, checked = page.evaluate(_OWN_WORDS_JS, [wide, WIDE_SECTIONS, OWN_BODY_COLUMNS])
                broken += [(document.parent.name + "/" + document.name, wide, word) for word in found]
                if not wide:  # the header the verifier saw broken is among the words checked
                    version = translator(lang).t("report.label.version")
                    assert f"rulepacks: {version.split()[0]}" in checked, (document, checked)
                else:
                    assert any(word.startswith("params: ") for word in checked), (document, checked)
    assert not broken, broken


# Other glyph metrics than the font's, simulated: every glyph one CSS pixel wider than its advance (on top of
# the monospace look), about twice what whole-pixel positions put a glyph off its advance (the Linux shell
# with its default 'full' hinting); a rule ID must stay on one line with it.
WIDER_GLYPHS = (
    "*, *::before, *::after { letter-spacing: 1px !important; } "
    ".mono, .mono * { letter-spacing: calc(0.03em + 1px) !important; }"
)
_RULE_IDS_JS = """
([wide, sections, ids]) => {
  const broken = [];
  let checked = 0;
  const pattern = new RegExp('(?<![A-Za-z0-9-])(' + ids.join('|') + ')(?![A-Za-z0-9-])', 'g');
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!!node.parentElement.closest(sections) !== wide) continue;
    for (const match of node.data.matchAll(pattern)) {
      const range = document.createRange();
      range.setStart(node, match.index);
      range.setEnd(node, match.index + match[0].length);
      const lines = new Set(Array.from(range.getClientRects()).filter((r) => r.width > 0)
                            .map((r) => Math.round(r.top)));
      checked += 1;
      if (lines.size > 1) {
        const cell = node.parentElement.closest('td, th, h4, p, li');
        broken.push((cell ? cell.tagName.toLowerCase() + '.' + cell.className + ' ' : '') + match[0]);
      }
    }
  }
  return [broken, checked];
}
"""


def _rule_ids(results: Results) -> list[str]:
    return sorted({rule.id for rule in results.rules} | {f.rule_id for f in results.findings})


@pytest.mark.pdf
def test_rule_ids_never_break_whatever_the_glyph_metrics(
    results: Results, written: dict[str, Path], pdf_shell: ShellInstall, tmp_path: Path
) -> None:
    """A rule ID never breaks inside, on any platform (REP-00, NG-F13; CI run of 55335ca: rule IDs did not
    stand on one line of the zh PDF printed on ubuntu-24.04). Every occurrence of a rule ID in the reports
    of ``results`` and with long dataset values, zh and en (the finding tables, the group headings, the
    evidence table, the appendix tables, the cross references in the title cells, running text), stands on
    one line, laid out by the real shell in print media at the content width of its page: with the font's
    metrics and with every glyph a pixel wider (WIDER_GLYPHS). Before the repair (measured on Windows) the
    zh cross reference '另见 CORE-M05-02' broke after the hyphen in its title cell with the font's metrics;
    with wider glyphs also 'also reported as CORE-M05-02', the evidence table's 'GXDSL008-ACC-001
    (gxdsl008)' and the threshold notes of three chart captions."""
    long_values = {"name": "N" * 200, "license": "https://example.org/" + "l" * 160, "version": "v" * 120}
    changed = results.model_copy(deep=True)
    changed.dataset = changed.dataset.model_copy(update=long_values)
    extra = write_reports(changed, ["zh", "en"], ["html"], tmp_path / "long", environ=os.environ)
    documents = [written["report.zh.html"], written["report.en.html"], *extra]
    ids = _rule_ids(results)
    broken: list[tuple[str, bool, str, str]] = []
    with _measuring_page(pdf_shell) as (page, _work):
        page.emulate_media(media="print")
        for document in documents:
            for metrics in ("font", "wider"):
                for wide, width in PAGE_WIDTHS.items():
                    page.set_viewport_size({"width": width, "height": 1200})
                    page.goto(document.as_uri())
                    if metrics == "wider":
                        page.add_style_tag(content=WIDER_GLYPHS)
                    page.evaluate("document.fonts.ready")
                    found, checked = page.evaluate(_RULE_IDS_JS, [wide, WIDE_SECTIONS, ids])
                    assert checked or not wide, (document, metrics)  # the landscape sections hold rule IDs
                    name = document.parent.name + "/" + document.name
                    broken += [(name, wide, metrics, where) for where in found]
    assert not broken, broken


def _page_counter(number: int, total: int) -> re.Pattern[str]:
    """The page counter 'x / y' in the squeezed page text, with up to three characters of words around the
    slash ('1/19', '第1页/共19页'), whatever words the report's counter uses. The digit before 'x' is not
    excluded: the running head's date ends in a digit right before the counter ('2026-10-111/15')."""
    return re.compile(rf"{number}\D{{0,3}}/\D{{0,3}}(?<!\d){total}(?!\d)")


def test_page_counter_pattern() -> None:
    assert _page_counter(1, 19).search("x1/19y") and _page_counter(1, 19).search("第1页/共19页")
    assert _page_counter(3, 12).search("Page3/12") and _page_counter(1, 15).search("2026-10-111/15")
    assert not _page_counter(1, 19).search("1/190") and not _page_counter(1, 19).search("1/219")
    assert not _page_counter(1, 19).search("1 and then much later /19")
    assert not _page_counter(2, 19).search("1/19")


@pytest.mark.pdf
def test_disclaimer_in_footer_of_every_page(results: Results, written: dict[str, Path]) -> None:
    """A-08: the fixed sentence in the footer of every page, with the page counter 'x / y' (B1)."""
    for lang in ("zh", "en"):
        pages = [_squeeze(t) for t in _texts(written[f"report.{lang}.pdf"].read_bytes())]
        assert len(pages) >= 2
        sentence = _squeeze(translator(lang).t("disclaimer"))
        for number, page in enumerate(pages, start=1):
            assert sentence in page, number
            assert _page_counter(number, len(pages)).search(page), number


class _Cells(html.parser.HTMLParser):
    """The text of every table cell of an HTML document, in document order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: list[str] = []
        self._open: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("td", "th"):
            self._open.append([])

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._open:
            self.cells.append("".join(self._open.pop()))

    def handle_data(self, data: str) -> None:
        if self._open:
            self._open[-1].append(data)


def _cells(document: str) -> list[str]:
    parser = _Cells()
    parser.feed(document)
    parser.close()
    return parser.cells


@pytest.mark.pdf
def test_every_finding_field_in_pdf_text(results: Results, written: dict[str, Path]) -> None:
    """NG-F13: the PDF is a print of the delivered HTML, so every table cell of the HTML (rule ID, clause,
    measured value, threshold, file, time range or '–' with reason of every shown finding, A-09/A-10) is
    in the PDF text. The oracle reads the cells from the HTML, independent of how the report formats them."""
    assert len({f.severity for f in results.findings}) == 3 and any(f.file is None for f in results.findings)
    assert any(f.status.value == "evidence_open" for f in results.findings)
    long = next(f for f in results.findings if f.time_ranges_total == 25)
    for lang in ("zh", "en"):
        text = _squeeze("".join(_texts(written[f"report.{lang}.pdf"].read_bytes())))
        cells = [
            _squeeze(cell) for cell in _cells(written[f"report.{lang}.html"].read_text(encoding="utf-8"))
        ]
        assert len(cells) > 100
        missing = [cell for cell in cells if cell not in text]
        assert not missing, (lang, missing[:5])
        # the cells hold the findings: every rule ID and file, the 20 shown ranges of the long finding
        for finding in results.findings:
            assert finding.rule_id in cells or any(finding.rule_id in cell for cell in cells), finding.rule_id
            if finding.file is not None:
                assert any(_squeeze(finding.file) in cell for cell in cells), finding.file
        assert all(f"{r.start_s:.3f}" in text for r in long.time_ranges)


def _type0_tables(font: Any) -> tuple[dict[int, str], dict[int, float], float]:
    """ToUnicode (bfchar, bfrange) and widths (/W, /DW) of a Type0 font as Chromium writes it (own
    reading)."""
    data = font["/ToUnicode"].get_object().get_data().decode("latin-1")
    chars: dict[int, str] = {}
    for block in re.findall(r"beginbfchar(.*?)endbfchar", data, re.S):
        for code, text in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            chars[int(code, 16)] = bytes.fromhex(text).decode("utf-16-be", "replace")
    for block in re.findall(r"beginbfrange(.*?)endbfrange", data, re.S):
        for low, high, start in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            for offset, code in enumerate(range(int(low, 16), int(high, 16) + 1)):
                chars[code] = chr(int(start, 16) + offset)
    descendant = font["/DescendantFonts"][0].get_object()
    widths: dict[int, float] = {}
    items = list(descendant.get("/W", []))
    while items:
        first = int(items.pop(0))
        if isinstance(items[0], list):
            widths.update({first + k: float(w) for k, w in enumerate(items.pop(0))})
        else:
            last, width = int(items.pop(0)), float(items.pop(0))
            widths.update(dict.fromkeys(range(first, last + 1), width))
    return chars, widths, float(descendant.get("/DW", 1000))


def _drawn_glyphs(data: bytes) -> list[list[tuple[str, float, float, float, float]]]:
    """Per page the glyphs of the Type0 fonts in drawing order, (character, x, y, advance, size) in text
    space (CSS px), read from Tf, Tm, Td and Tj as Skia writes them (own reading of the PDF)."""
    reader = pypdf.PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        fonts = page["/Resources"].get("/Font") or {}
        tables = {
            name: _type0_tables(ref.get_object())
            for name, ref in fonts.items()
            if ref.get_object().get("/Subtype") == "/Type0"
        }
        glyphs: list[tuple[str, float, float, float, float]] = []
        font, size, scale, flip, line = None, 0.0, 1.0, 1.0, (0.0, 0.0)
        x, y = line
        for operands, operator in ContentStream(page.get_contents(), reader).operations:
            if operator == b"Tf":
                font, size = tables.get(operands[0]), float(operands[1])
            elif operator == b"Tm":
                scale, flip, line = (
                    float(operands[0]),
                    float(operands[3]),
                    (float(operands[4]), float(operands[5])),
                )
                x, y = line
            elif operator == b"Td":
                line = (line[0] + float(operands[0]) * scale, line[1] + float(operands[1]) * flip)
                x, y = line
            elif operator == b"Tj" and font is not None:
                chars, widths, default = font
                raw = operands[0].original_bytes
                for at in range(0, len(raw) - 1, 2):
                    code = int.from_bytes(raw[at : at + 2], "big")
                    advance = widths.get(code, default) * size / 1000 * scale
                    glyphs.append((chars.get(code, "?"), x, y, advance, size))
                    x += advance
        pages.append(glyphs)
    return pages


def _how_split(rule_id: str, text: str, pages: list[list[tuple[str, float, float, float, float]]]) -> str:
    """How the PDF holds a rule ID that no line of its text holds: the text around its characters (a line
    break shown as '|', a space as '_') and, from its glyphs in drawing order, the pair whose distance
    differs most from the advance of the first glyph and the number of baselines (diagnostics: a CI run's
    annotation shows the first line of a failure only)."""
    forms = sorted({m.group(0) for m in re.finditer(r"\s*".join(map(re.escape, rule_id)), text)} - {rule_id})
    shown = ",".join(repr(form.replace("\n", "|").replace(" ", "_")) for form in forms[:2]) or "not as text"
    for glyphs in pages:
        chars = "".join(glyph[0] for glyph in glyphs)
        if (at := chars.find(rule_id)) == -1:
            continue
        run = glyphs[at : at + len(rule_id)]
        gaps = [(b[1] - a[1] - a[3], a[0] + b[0]) for a, b in zip(run, run[1:], strict=False)]
        gap, pair = max(gaps, key=lambda item: abs(item[0]))
        baselines = len({glyph[2] for glyph in run})
        return f"{rule_id} as {shown}, gap {pair} {gap:+.2f}px at {run[0][4]:.1f}px, {baselines} baseline(s)"
    return f"{rule_id} as {shown}, glyphs not in one run"


@pytest.mark.pdf
def test_rule_ids_do_not_break_inside_in_the_pdf(results: Results, written: dict[str, Path]) -> None:
    """Every rule ID of the finding tables stands on one line of the PDF text (the verifier saw
    'BIDS / -STO / -002' in the portrait table of this branch). The landscape finding tables with fixed
    columns are the report area's (B1, REP-00); without them the check is skipped, after the merge it
    guards the layout of the printed tables.

    CI run of 55335ca (ubuntu-24.04): in the zh PDF printed there no line held BIDS-STO-001/002/003 or
    GXDSL008-STO-002 (their characters were all in the text, test_every_finding_field_in_pdf_text passed).
    The headless shell's default 'full' hinting puts every glyph at a whole-pixel position on Linux; the
    repair prints with --font-render-hinting=none (kernel.pdf.TEXT_LAYOUT_FLAG). Simulated on Windows with
    letter spacing in the zh report (measured): from 1.2 CSS px more per glyph pypdf reads a space into
    'BIDS -STO-001/002/003' first, from 2 px into every rule ID. Both languages are checked before the
    assertion, whose message names for each split ID how the text holds it and the glyph distances that
    split it, so a CI annotation shows the cause."""
    found: list[str] = []
    for lang in ("zh", "en"):
        if "@page wide" not in written[f"report.{lang}.html"].read_text(encoding="utf-8"):
            pytest.skip("the landscape finding tables of the report area (B1) are not in this build")
        if split := _split_rule_ids(written[f"report.{lang}.pdf"].read_bytes(), results):
            found.append(f"{lang}: {split}")
    assert not found, " | ".join(found)


def _split_rule_ids(data: bytes, results: Results) -> str:
    """The rule IDs of ``results``' findings that no line of the PDF's text holds, each with how the PDF
    holds it (_how_split); empty when every one stands on a line."""
    text = "\n".join(_texts(data))
    lines = text.splitlines()
    broken = sorted({f.rule_id for f in results.findings if not any(f.rule_id in line for line in lines)})
    if not broken:
        return ""
    pages = _drawn_glyphs(data)
    return "; ".join(_how_split(rule_id, text, pages) for rule_id in broken)


@pytest.mark.pdf
def test_font_render_hinting_is_read_by_the_shell(
    results: Results, written: dict[str, Path], pdf_shell: ShellInstall
) -> None:
    """kernel.pdf.TEXT_LAYOUT_FLAG: the shell of revision 1243 reads --font-render-hinting on every
    platform (an unknown value stops its start: pdf.launch_failed; the last value given counts). On Windows
    the renderer applies no hinting preference (DirectWrite) and the switch changes nothing: the zh report
    printed with 'full' is the delivered one byte for byte (measured). On Linux 'full' is the headless
    default the CI run of 55335ca printed with (rule IDs on no line of the zh text); this negative control
    prints the zh report with it again and names how the IDs split, while the delivered report (printed
    with 'none') holds every ID on a line (test_rule_ids_do_not_break_inside_in_the_pdf)."""
    meta = PdfMeta(translator("zh").t("report.title"), results.config.as_of)
    with pdf.browser_work() as work:
        source = work / "report.zh.html"
        source.write_bytes(written["report.zh.html"].read_bytes())
        with (
            pytest.raises(PdfError) as info,
            PdfPrinter(pdf_shell, work, extra_flags=("--font-render-hinting=x",)),
        ):
            pass
        assert info.value.message_key == "pdf.launch_failed"
        with PdfPrinter(pdf_shell, work, extra_flags=("--font-render-hinting=full",)) as printer:
            full = printer.print(source, meta, locale="zh-CN").data
    delivered = written["report.zh.pdf"].read_bytes()
    if sys.platform == "win32":
        assert full == delivered
    else:  # the condition of the CI run of 55335ca, reproduced
        assert full != delivered, "the zh report printed with 'full' hinting is the one printed with 'none'"
        assert _split_rule_ids(full, results), "'full' hinting splits no rule ID of the zh report here"


@pytest.mark.pdf
def test_pdf_byte_identical_two_processes_and_language_order(results: Results, tmp_path: Path) -> None:
    source = tmp_path / "results.json"
    source.write_bytes(canonical.dumps(results))
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    runs = (("zh,en", "html,pdf", "a"), ("en,zh", "pdf,html", "b"))
    for languages, formats, folder in runs:
        done = subprocess.run(
            [
                sys.executable,
                "-m",
                "neurogrid",
                "report",
                str(source),
                "--lang",
                languages,
                "--format",
                formats,
                "--out",
                str(tmp_path / folder),
            ],
            capture_output=True,
            env=env,
            check=False,
        )
        assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    for name in ("report.zh.html", "report.zh.pdf", "report.en.html", "report.en.pdf"):
        first, second = (tmp_path / "a" / name).read_bytes(), (tmp_path / "b" / name).read_bytes()
        assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest(), name


def _page(body: str, *, css: str = "", font_css: str = "", csp: bool = True) -> str:
    policy = f'<meta http-equiv="Content-Security-Policy" content="{CSP}">' if csp else ""
    return (
        f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">{policy}<title>Control</title>'
        f"<style>{font_css}{css}</style></head><body>{body}</body></html>"
    )


NG_CSS = (
    f'*, *::before, *::after {{ font-family: "{FONT_FAMILY}" !important; }} html {{ font-synthesis: none; }}'
)


def _print(
    printer: PdfPrinter, work: Path, name: str, html: str, expect: PdfExpect, meta: PdfMeta | None = None
) -> list[str]:
    path = work / f"{name}.html"
    path.write_text(html, encoding="utf-8")
    printed = printer.print(path, meta or expect.meta)
    return qa_gate(printed.data, expect, log=printed.log)


@pytest.mark.pdf
def test_qa_gate_negative_controls(
    pdf_shell: ShellInstall, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = "Hello 数据 <b>bold 粗体</b>"
    both = subset_font_css(FONT_FILES, text + "Control")
    regular_only = subset_font_css({400: FONT_FILES[400]}, text + "Control")
    expect = PdfExpect(meta=PdfMeta("Control", AS_OF), fonts=FONTS, every_page=("Hello",), once=("bold",))
    outside = "file:///C:/Windows/win.ini" if os.name == "nt" else "file:///etc/passwd"
    with pdf.browser_work() as work, PdfPrinter(pdf_shell, work) as printer:
        assert _print(printer, work, "ok", _page(text, css=NG_CSS, font_css=both), expect) == []
        system = _print(
            printer, work, "system", _page(text, css="body { font-family: Arial, sans-serif; }"), expect
        )
        assert "font_not_report_font" in system or "font_not_cid_truetype" in system
        synthetic = "* { font-family: 'NG Sans' !important; }"  # bold without a bold face, synthesis on
        assert "font_type3" in _print(
            printer, work, "bold", _page(text, css=synthetic, font_css=regular_only), expect
        )
        emoji = _print(printer, work, "emoji", _page(text + " \U0001f600", css=NG_CSS, font_css=both), expect)
        assert {"font_type3", "font_not_report_font"} & set(emoji)
        cross = _print(printer, work, "cross", _page(text + " \u2717", css=NG_CSS, font_css=both), expect)
        assert "font_not_report_font" in cross
        radical = _print(printer, work, "radical", _page(text + " \u2f63", css=NG_CSS, font_css=both), expect)
        assert {"font_not_report_font", "radical_codepoint"} & set(radical)
        missing = PdfExpect(
            meta=expect.meta, fonts=FONTS, every_page=("absent phrase",), once=("also absent",)
        )
        assert _print(printer, work, "phrases", _page(text, css=NG_CSS, font_css=both), missing) == [
            "phrase_missing",
            "phrase_missing_on_page",
        ]
        image = f'{text}<img src="https://example.com/a.png"><img src="{outside}">'
        blocked = _print(printer, work, "csp", _page(image, css=NG_CSS, font_css=both), expect)
        assert "requests_failed" in blocked and "requests_unexpected" in blocked  # CSP stops them first
        with pytest.raises(PdfError) as info:
            _print(printer, work, "nocsp", _page(text, css=NG_CSS, font_css=both, csp=False), expect)
        assert info.value.params == {"checks": "html_csp_missing"}
        monkeypatch.setattr(pdf, "has_csp", lambda document: True)  # the router is the second layer
        routed = _print(printer, work, "router", _page(image, css=NG_CSS, font_css=both, csp=False), expect)
        assert "requests_aborted" in routed
        wrong = PdfExpect(meta=PdfMeta("Other title", date(2026, 1, 1)), fonts=FONTS)
        page = _page(text, css=NG_CSS, font_css=both)
        assert _print(printer, work, "meta", page, wrong, meta=expect.meta) == [
            "metadata_dates",
            "metadata_title",
        ]


def _netlog_events(path: Path) -> set[str]:
    raw = path.read_text(encoding="utf-8").rstrip()
    if not raw.endswith("}"):  # a log the browser could not finish
        raw = raw.rstrip(",") + "]}"
    data = json.loads(raw)
    names = {number: name for name, number in data["constants"]["logEventTypes"].items()}
    return {names[event["type"]] for event in data.get("events", [])}


@pytest.mark.pdf
def test_no_network_events_in_chromium_netlog(
    results: Results, pdf_shell: ShellInstall, tmp_path: Path
) -> None:
    """NG-N01 for the browser process (Windows, process level): its own network log records no request,
    socket, connection, name resolution or proxy detection while it prints a report."""
    with pdf.browser_work() as work:
        netlog = work / "netlog.json"
        flags = (f"--log-net-log={netlog}", "--net-log-capture-mode=Everything")
        with PdfPrinter(pdf_shell, work, extra_flags=flags) as printer:
            source = work / "report.en.html"
            source.write_text(html_document(results, "en"), encoding="utf-8")
            printed = printer.print(source, PdfMeta(translator("en").t("report.title"), AS_OF))
        events = _netlog_events(netlog)
    assert printed.log.seen == 1 and printed.log.unexpected == 0
    banned = ("URL_REQUEST", "SOCKET", "TCP_", "UDP_", "HOST_RESOLVER", "PAC_FILE", "PROXY_", "SSL_", "HTTP_")
    assert events and not sorted(e for e in events if e.startswith(banned) or e == "QUIC_SESSION"), events


NETGUARD_PROBE = """
import json, os, socket, sys
from pathlib import Path

events = []


def spy(event, args):
    if event.startswith("socket."):
        events.append((event, repr([a for a in args if not isinstance(a, socket.socket)])))


sys.addaudithook(spy)
from neurogrid.kernel import netguard

netguard.install()
from neurogrid.model.results import Results
from neurogrid.report.output import write_reports

results = Results.model_validate_json(Path(sys.argv[1]).read_bytes())
write_reports(results, ["zh"], ["pdf"], Path(sys.argv[2]), environ=os.environ)
blocked, during = netguard.blocked_count(), list(events)
try:
    socket.create_connection(("192.0.2.1", 9), timeout=1)
    probe = "connected"
except Exception as exc:
    probe = type(exc).__name__
print(json.dumps({"blocked": blocked, "events": during, "after": events[len(during) :], "probe": probe}))
"""


@pytest.mark.pdf
def test_netguard_blocks_nothing_and_counts_zero(results: Results, tmp_path: Path) -> None:
    """A-49: Playwright's asyncio loop in the NeuroGrid process (on Windows a loopback socket pair) passes
    the network guard; any other connection is still blocked."""
    source = tmp_path / "results.json"
    source.write_bytes(canonical.dumps(results))
    done = subprocess.run(
        [sys.executable, "-c", NETGUARD_PROBE, str(source), str(tmp_path / "out")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert done.returncode == 0, done.stderr
    report = json.loads(done.stdout.strip().splitlines()[-1])
    assert report["blocked"] == 0 and report["probe"] == "NetworkBlockedError"
    addressed = [args for event, args in report["events"] if event in ("socket.connect", "socket.sendto")]
    assert all("127.0.0.1" in args or "::1" in args for args in addressed), addressed  # loopback only
    if os.name == "nt":
        assert addressed  # the proactor's socket pair (measured: one connect to 127.0.0.1)
    assert "192.0.2.1" in report["after"][0][1]  # the probe, refused before any packet
    assert (tmp_path / "out" / "report.zh.pdf").is_file()


@pytest.mark.pdf
def test_no_files_left_in_temp_and_shell_folder_unchanged(results: Results, pdf_shell: ShellInstall) -> None:
    """A-54, P1: driver and browser use the run's work folder. The first print after a fresh installation
    (a copy of the installed shell that no browser has run from) with its own, empty temporary and user data
    folders and an empty current folder leaves all of them empty (no Playwright folder, no browser profile,
    no debug.log), leaves the browser folder unchanged byte for byte (conftest.folder_content: entries,
    sizes, times and SHA-256; the shell would otherwise write debug.log next to its executable) and the
    output folder holds only the reports. Measured for P1: Chromium writes nothing below its folder (no
    change notification while it starts and prints a report, plain text or hyphenated text); it reads the
    executable, the .pak, .dat, .bin and Vulkan files and, for 'hyphens: auto' in English text only,
    hyphen-data/hyph-en-us.hyb. The failure once seen (hyphen-data size 0 -> 12288) was the old snapshot
    reading NTFS's cache state. Negative control: a debug.log written and removed again next to the
    executable is seen."""
    with short_folder("ng-env-") as root, fresh_shell(pdf_shell) as shell:
        source = root / "results.json"
        source.write_bytes(canonical.dumps(results))
        private = {
            name: root / name.lower() for name in ("TEMP", "LOCALAPPDATA", "APPDATA", "XDG_CACHE_HOME", "CWD")
        }
        for folder in private.values():
            folder.mkdir()
        env = {
            **os.environ,
            **{name: str(folder) for name, folder in private.items() if name != "CWD"},
            "TMP": str(private["TEMP"]),
            "TMPDIR": str(private["TEMP"]),
            "XDG_CONFIG_HOME": str(private["XDG_CACHE_HOME"]),
            "XDG_DATA_HOME": str(private["XDG_CACHE_HOME"]),
            pdf.ENV_BROWSER_DIR: str(shell.folder),
            "PYTHONIOENCODING": "utf-8",
        }
        before = folder_content(shell.folder)
        out = root / "out"
        command = ["report", str(source), "--lang", "zh,en", "--format", "pdf", "--out", str(out)]
        done = subprocess.run(
            [sys.executable, "-m", "neurogrid", *command],
            capture_output=True,
            env=env,
            cwd=private["CWD"],
            check=False,
        )
        assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
        assert sorted(p.name for p in out.iterdir()) == ["report.en.pdf", "report.zh.pdf"]
        assert {name: sorted(p.name for p in folder.iterdir()) for name, folder in private.items()} == {
            name: [] for name in private
        }
        assert folder_content(shell.folder) == before
        child_log = shell.executable.parent / pdf.CHILD_LOG
        child_log.write_bytes(b"[1026/120000.000:ERROR:example.cc(1)] written and undone\n")
        child_log.unlink()
        assert folder_content(shell.folder) != before


# Browser tests of this module and of the CLI that print below their tmp_path (results, sources, --out).
LONG_BASETEMP_TESTS = (
    "tests/integration/test_report_pdf.py::test_pdf_qa_gate_green_zh_en",
    "tests/integration/test_report_pdf.py::test_print_pdf_writes_only_a_passing_pdf",
    "tests/integration/test_report_pdf.py::test_glyph_twins_extract_as_their_own_codepoints",
    "tests/integration/test_report_pdf.py::test_no_network_events_in_chromium_netlog",
    "tests/cli/test_report_pdf_cli.py::test_glyph_twins_in_the_dataset_name_exit_0_with_the_name_as_written",
)


@contextlib.contextmanager
def _entries_seen(folder: Path) -> Iterator[dict[str, set[str]]]:
    """Every name that appears in a folder below ``folder`` while the block runs, also one that is gone again
    at its end (polled every 20 ms in a thread), by folder (as in conftest.folder_content), and under the key
    'debug.log' the first line of each debug.log seen (who wrote it and why). A diagnostic: a created and
    removed entry changes only its folder's modification time, which folder_content cannot explain."""

    def names() -> dict[str, set[str]]:
        return {here: set(folders) | set(files) for here, folders, files in os.walk(folder)}

    known = names()
    seen: dict[str, set[str]] = {}
    stop = threading.Event()

    def poll() -> None:
        while not stop.wait(0.02):
            for here, now in names().items():
                new = now - known.get(here, set())
                if not new:
                    continue
                seen.setdefault(Path(here).relative_to(folder).as_posix() + "/", set()).update(new)
                if pdf.CHILD_LOG in new:
                    with contextlib.suppress(OSError):
                        text = (Path(here) / pdf.CHILD_LOG).read_bytes()[:400].decode("utf-8", "replace")
                        seen.setdefault(pdf.CHILD_LOG, set()).add(text.splitlines()[0] if text else "(empty)")

    thread = threading.Thread(target=poll, daemon=True)
    thread.start()
    try:
        yield seen
    finally:
        stop.set()
        thread.join()


def test_entries_seen_names_a_debug_log_written_and_removed_again(tmp_path: Path) -> None:
    """The diagnostic of the long-basetemp check (CI run 40355705974: only the modification time of the
    executable's folder, the fourth entry of folder_content, differed, so an entry was created and removed
    there): a debug.log that exists only for a moment is named with its folder and first line."""
    shell = tmp_path / "chrome-headless-shell-win64"
    shell.mkdir()
    (shell / "kept.pak").write_bytes(b"x")
    with _entries_seen(tmp_path) as seen:
        log = shell / pdf.CHILD_LOG
        log.write_bytes(b"[1026/120000.000:ERROR:example.cc(1)] child error\nsecond line\n")
        deadline = time.monotonic() + 10
        while pdf.CHILD_LOG not in seen and time.monotonic() < deadline:
            threading.Event().wait(0.01)
        log.unlink()
    assert seen == {
        "chrome-headless-shell-win64/": {pdf.CHILD_LOG},
        pdf.CHILD_LOG: {"[1026/120000.000:ERROR:example.cc(1)] child error"},
    }


@pytest.mark.pdf
def test_pdf_tests_pass_with_a_long_basetemp(pdf_shell: ShellInstall, tmp_path: Path) -> None:
    """P2: the browser's work folder never follows the paths a caller uses (kernel.pdf.browser_work; the
    tests take theirs from it too), so a long pytest basetemp changes nothing: with one of 200 characters
    (the tests' tmp_path then about 230) a selection of browser tests that write below tmp_path passes.
    Verification of P2: before it, such a run left a debug.log with local paths next to the installed
    shell's executable (work folders below tmp_path); here the selection runs with a fresh installation
    (conftest.fresh_shell) that stays unchanged byte for byte (conftest.folder_content)."""
    basetemp = long_path(tmp_path / "b", 200)
    assert len(str(basetemp)) >= 200
    basetemp.parent.mkdir(parents=True)  # pytest creates the basetemp itself, not its parents
    with fresh_shell(pdf_shell) as shell:
        before = folder_content(shell.folder)
        with _entries_seen(shell.folder) as seen:
            done = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={basetemp}"]
                + list(LONG_BASETEMP_TESTS),
                capture_output=True,
                cwd=Path(__file__).parent.parent.parent,
                env={
                    **os.environ,
                    pdf.ENV_BROWSER_DIR: str(shell.folder),
                    "NEUROGRID_REQUIRE_PDF": "1",
                    "PYTHONIOENCODING": "utf-8",
                },
                check=False,
            )
        after = folder_content(shell.folder)
    report = done.stdout.decode("utf-8", "replace")
    assert done.returncode == 0, report[-3000:]
    summary = report.strip().splitlines()[-1]
    assert re.match(r"^6 passed\b", summary) and "skipped" not in summary, summary

    # the differing entries first, on one line: CI shows only the first line of a failure without a login
    def change(key: str) -> str:
        old, new = before.get(key), after.get(key)
        if old is None or new is None:
            return f"{key} {'added' if old is None else 'removed'}"
        if key.endswith("/"):  # (entries, size, mtime): name the entries that differ
            entries = sorted(set(old[0]) ^ set(new[0]))
            return f"{key} entries {entries}, size {old[1]} -> {new[1]}, mtime {old[2]} -> {new[2]}"
        return f"{key} (size, mtime, sha256) {old} -> {new}"

    changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
    transient = "; ".join(f"{key} {sorted(names)}" for key, names in sorted(seen.items()))
    assert after == before, (
        "changed in the browser folder: "
        + "; ".join(change(key) for key in changed)
        + f" | seen during the run: {transient or 'nothing'}"
    )


@pytest.mark.pdf
@pytest.mark.skipif(sys.platform != "win32", reason="the fallback to the current folder is Windows logging")
def test_fallback_log_of_a_long_work_folder_stays_in_the_work_folder(
    pdf_shell: ShellInstall, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A-51/A-54: from a work folder of 197 characters on, the paths of the browser's profile pass 260
    characters and Chromium's logging falls back to debug.log in the current folder (measured with revision
    1243; from 210 characters the shell no longer starts). That folder is the work folder, removed after the
    run, never the user's current folder (it was, with the paths of the work folder in it).

    The product never starts the browser in such a folder (WORK_PATH_LIMIT, P2); the limit is lifted here
    to show that the driver's current folder still keeps such a log out of the caller's folder. A fresh copy
    of the shell takes the debug.log that the network service then appends next to the executable."""
    monkeypatch.setattr(pdf, "WORK_PATH_LIMIT", 10_000)
    with short_folder("ng-fb-") as root, fresh_shell(pdf_shell) as shell:
        here = root / "current"
        here.mkdir()
        monkeypatch.chdir(here)
        work = root / "w"
        work = work / ("w" * (204 - len(str(work)) - 1))
        assert len(str(work)) == 204
        source = root / "page.html"
        source.write_text(_page("<p>x</p>"), encoding="utf-8")
        with PdfPrinter(shell, work) as printer:
            printed = printer.print(source, PdfMeta("t", AS_OF))
        assert printed.data.startswith(b"%PDF-")
        assert sorted(here.iterdir()) == []
        assert (work / pdf.CHILD_LOG).is_file()  # the fallback happened, in the work folder
        assert not (shell.executable.parent / pdf.CHILD_LOG).exists()
        monkeypatch.chdir(root.parent)  # out of the folder before it is removed


@pytest.mark.pdf
def test_dataset_text_without_glyph_never_fails(results: Results, tmp_path: Path) -> None:
    """Dataset data never ends with exit 2: characters the fonts cannot draw become [U+XXXX] in HTML and
    PDF alike, so the browser never falls back to a system font."""
    hostile = results.model_copy(deep=True)
    hostile.dataset.name = "EEG \U0001f600 \u2717 \u2f63 \x07 数据"
    paths = write_reports(hostile, ["zh"], ["html", "pdf"], tmp_path, environ=os.environ)
    html = paths[0].read_text(encoding="utf-8")
    assert "EEG [U+1F600] [U+2717] [U+2F63] [U+0007] 数据" in html
    text = _squeeze("".join(_texts(paths[1].read_bytes())))
    assert _squeeze("EEG [U+1F600] [U+2717] [U+2F63] [U+0007] 数据") in text
    assert {ord(ch) for ch in text} <= font_codepoints(FONT_FILES) | {ord("\n")}


@contextlib.contextmanager
def _shared_glyphs_kept(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Negative control: font subsets as before the repair, glyphs shared by several code points stay
    shared. The subset cache is emptied before and after, so no other test sees such a subset."""
    fonts._subset.cache_clear()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(fonts, "separate_shared_glyphs", lambda font: {})
            yield
    finally:
        fonts._subset.cache_clear()


def _twin_tokens(text: str) -> list[str]:
    """The '|...|' tokens of the printed text without line breaks, spaces and soft hyphens (U+00AD is not
    drawn; the extraction puts a space where it was)."""
    return [re.sub("[\n \u00ad]", "", token) for token in re.findall(r"\|([^|]*)\|", text)]


def _plain(text: str) -> str:
    """``text`` without white space and soft hyphens (U+00AD is not drawn)."""
    return re.sub("[\\s\u00ad]", "", text)


# The characters of the repair note (U+2013, U+00AD, U+2011, U+00B7) next to code points that share their
# glyph in the static cuts: U+2012 (with U+2013), U+002D (with U+00AD and U+2011), U+2027 (with U+00B7) and
# the ideograph twins U+3B35/U+80F6 (\u80f6).
TWIN_NAME = "EEG \u2012\u2013 -\u00ad\u2011 \u00b7\u2027 \u3b35\u80f6"


@pytest.mark.pdf
def test_glyph_twins_extract_as_their_own_codepoints(
    pdf_shell: ShellInstall, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B2/A-27: every code point of the 95 glyphs the static cuts share (U+2012/U+2013, U+002D/U+2011,
    U+00B7/U+2027, U+3B35/U+80F6, ...) comes back from the PDF text as itself, in both weights. Negative
    control with shared glyphs kept: Skia's ToUnicode gives the lowest code point of the embedded font, so
    every en dash reads as a figure dash."""
    groups = sorted(shared_glyphs(TTFont(FONT_FILES[400], lazy=True)).values())
    assert len(groups) == 95
    line = " ".join("|" + "".join(chr(cp) for cp in group) + "|" for group in groups)
    body = f"<p>{line}</p><p><b>{line}</b></p>"
    wanted = [re.sub("[ \u00ad]", "", "".join(chr(cp) for cp in group)) for group in groups] * 2
    expect = PdfExpect(meta=PdfMeta("Control", AS_OF), fonts=FONTS, once=("|",))

    def printed(name: str) -> str:
        source = work / f"{name}.html"
        source.write_text(_page(body, css=NG_CSS, font_css=subset_font_css(FONT_FILES, body)), "utf-8")
        result = printer.print(source, expect.meta)
        assert qa_gate(result.data, expect, log=result.log) == []
        return "".join(_texts(result.data))

    with pdf.browser_work() as work, PdfPrinter(pdf_shell, work) as printer:
        assert _twin_tokens(printed("separated")) == wanted
        with _shared_glyphs_kept(monkeypatch):
            kept = _twin_tokens(printed("kept"))
    dash = groups.index([0x2012, 0x2013])
    assert kept[dash] == kept[dash + len(groups)] == "\u2012\u2012" and kept != wanted


@pytest.mark.pdf
def test_glyph_twins_in_dataset_text_never_fail_the_gate(
    results: Results, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verifier's case: with the zh title 'NeuroGrid – 预检报告' quoted in B2 (a phrase the gate
    requires) and a dataset name with the glyph twins of TWIN_NAME (U+2012 shares the glyph of '–'), the
    report passes and the PDF text keeps every twin apart; /Title is the HTML title. Negative control with
    shared glyphs kept: every '–' reads as U+2012, the title goes missing and the run ends with exit 2
    (pdf.qa_failed)."""
    title = "NeuroGrid \u2013 预检报告"
    monkeypatch.setitem(texts.tables()["zh"], "report.title", title)
    twin = results.model_copy(deep=True)
    twin.dataset.name = TWIN_NAME
    paths = write_reports(twin, ["zh"], ["html", "pdf"], tmp_path / "ok", environ=os.environ)
    reader = pypdf.PdfReader(io.BytesIO(paths[1].read_bytes()))
    assert reader.metadata is not None and reader.metadata.get("/Title") == title
    text = "".join(page.extract_text() or "" for page in reader.pages)
    visible = _Text()
    visible.feed(paths[0].read_text(encoding="utf-8"))
    body = "".join(visible.parts)
    assert TWIN_NAME in body
    for char in "\u2012\u2011\u2027\u3b35":  # only in the dataset name: in the body, not in a margin box
        assert text.count(char) == body.count(char) >= 1, f"U+{ord(char):04X}"
    assert text.count("\u2013") >= body.count("\u2013") > 1  # the empty-cell dashes and the title
    assert _squeeze(title) in _squeeze(text) and _plain(TWIN_NAME) in _plain(text)
    with _shared_glyphs_kept(monkeypatch), pytest.raises(PdfError) as info:
        write_reports(twin, ["zh"], ["html", "pdf"], tmp_path / "kept", environ=os.environ)
    assert info.value.message_key == "pdf.qa_failed" and "phrase_missing" in str(info.value.params["checks"])
    assert not (tmp_path / "kept").exists()


@contextlib.contextmanager
def _copies_without_layout(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Negative control (the state before P3): copies of shared glyphs in no GSUB/GPOS lookup. The subset
    cache is emptied before and after."""
    real = fonts.separate_shared_glyphs
    fonts._subset.cache_clear()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(fonts, "separate_shared_glyphs", lambda font: real(font, layout=False))
            yield
    finally:
        fonts._subset.cache_clear()


@contextlib.contextmanager
def _measuring_page(shell: ShellInstall) -> Iterator[tuple[Any, Path]]:
    """A page of the real shell with JavaScript on, for measurements only (the printer keeps it off),
    started like the printer: kernel.pdf's launch arguments and environments in a browser_work folder."""
    from playwright.sync_api import sync_playwright

    child_log = pdf._ChildLog(shell.executable)
    with pdf.browser_work() as work:
        try:
            with pdf.driver_environment(work):
                playwright = sync_playwright().start()
            try:
                browser = playwright.chromium.launch(
                    executable_path=str(shell.executable),
                    args=pdf.launch_arguments(work),
                    env=pdf.browser_environment(work),
                    chromium_sandbox=False,
                )
                try:
                    context = browser.new_context(offline=True)
                    context.route(
                        "**/*",
                        lambda route: (
                            route.continue_() if route.request.url.startswith("file:") else route.abort()
                        ),
                    )
                    yield context.new_page(), work
                finally:
                    browser.close()
            finally:
                playwright.stop()
        finally:
            child_log.restore()


TWIN_SAMPLE = "T–T L–L"  # the en dash is kerned with T and L (class kerning, both weights)


def _rendered(page: Any, work: Path) -> tuple[dict[str, float], dict[str, bytes]]:
    """Widths of TWIN_SAMPLE in a subset without U+2012 (no copy) and in one with it (U+2013 is a copy),
    both weights; element screenshots of 'a…b' and 'a⋯b' (twins of one glyph that locl replaces in Latin
    text) in the subset with copies."""
    plain = subset_font_css(FONT_FILES, TWIN_SAMPLE + "ab…", family="NG Plain")
    twin = subset_font_css(FONT_FILES, TWIN_SAMPLE + "ab…‒⋯", family="NG Twin")
    cells = "".join(
        f'<div><span id="{family}{weight}" style="font-family: \'NG {family}\'; font-weight: {weight}">'
        f"{TWIN_SAMPLE}</span></div>"
        for family in ("Plain", "Twin")
        for weight in (400, 700)
    )
    cells += '<div><span id="horizontal" class="e">a…b</span></div>'
    cells += '<div><span id="midline" class="e">a⋯b</span></div>'
    source = work / "measure.html"
    source.write_text(
        f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><style>{plain}{twin} span {{ '
        "font-size: 100px; line-height: 120px; white-space: pre; display: inline-block; } "
        ".e { font-family: 'NG Twin'; width: 300px; } div { height: 140px; }</style></head>"
        f"<body>{cells}</body></html>",
        encoding="utf-8",
    )
    page.goto(source.as_uri())
    page.evaluate("document.fonts.ready")
    widths = {
        key: float(page.evaluate(f"document.getElementById('{key}').getBoundingClientRect().width"))
        for key in ("Plain400", "Twin400", "Plain700", "Twin700")
    }
    shots = {key: page.locator(f"#{key}").screenshot() for key in ("horizontal", "midline")}
    return widths, shots


@pytest.mark.pdf
def test_glyph_copies_keep_kerning_and_localized_forms_in_the_shell(
    pdf_shell: ShellInstall, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P3 in the real shell: 'T–T L–L' with the en dash as a copy (U+2012 in the text) is exactly as wide
    as with the shared glyph (kerning applies to the copy), in both weights; '⋯' (U+22EF, a copy of the
    ellipsis glyph) gets the ellipsis' localized form in Latin text, i.e. renders like '…'. Negative
    control with the copies in no lookup (before P3): wider by the kerning, and the CJK form."""
    with _measuring_page(pdf_shell) as (page, work):
        fonts._subset.cache_clear()
        widths, shots = _rendered(page, work)
        with _copies_without_layout(monkeypatch):
            kept_widths, kept_shots = _rendered(page, work)
    assert widths["Twin400"] == widths["Plain400"] and widths["Twin700"] == widths["Plain700"], widths
    assert shots["midline"] == shots["horizontal"]
    assert kept_widths["Plain400"] == widths["Plain400"] and kept_widths["Plain700"] == widths["Plain700"]
    assert kept_widths["Twin400"] > kept_widths["Plain400"] + 15  # -84 -55 -63 units at 100 px
    assert kept_widths["Twin700"] > kept_widths["Plain700"] + 15
    assert kept_shots["midline"] != kept_shots["horizontal"]


LOCL_TWINS = ("a…b⋯c", "x⋯y…z")


@pytest.mark.pdf
def test_localized_forms_of_glyph_twins_keep_their_codepoints_in_the_pdf(
    pdf_shell: ShellInstall, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P3: in Latin text locl replaces the ellipsis glyph that U+2026 and U+22EF share; each copy gets its
    own copy of the substitute, so the PDF text keeps both code points and the gate passes (dataset data
    never ends with exit 2). Negative control with the substitute shared by both (the copies only added to
    the lookups): Skia names the substitute after the first text it drew, U+22EF reads as U+2026."""
    body = "".join(f"<p>|{token}|</p><p><b>|{token}|</b></p>" for token in LOCL_TWINS)
    expect = PdfExpect(meta=PdfMeta("Control", AS_OF), fonts=FONTS, once=LOCL_TWINS)

    def printed(printer: PdfPrinter, work: Path) -> tuple[list[str], list[str]]:
        source = work / "locl.html"
        source.write_text(_page(body, css=NG_CSS, font_css=subset_font_css(FONT_FILES, body)), "utf-8")
        result = printer.print(source, expect.meta)
        return _twin_tokens("".join(_texts(result.data))), qa_gate(result.data, expect, log=result.log)

    with pdf.browser_work() as work, PdfPrinter(pdf_shell, work) as printer:
        fonts._subset.cache_clear()
        assert printed(printer, work) == ([LOCL_TWINS[0], LOCL_TWINS[0], LOCL_TWINS[1], LOCL_TWINS[1]], [])
        fonts._subset.cache_clear()
        try:
            with monkeypatch.context() as patch:
                patch.setattr(fonts.GlyphCopies, "close_substitutions", lambda self: None)
                patch.setattr(fonts.GlyphCopies, "_substitute", staticmethod(lambda name, suffix: name))
                patch.setattr(fonts.GlyphCopies, "_ligature_suffix", lambda self, components: "")
                tokens, violations = printed(printer, work)
        finally:
            fonts._subset.cache_clear()
    assert tokens[0] == "a…b…c" and violations == ["phrase_missing"]


def test_write_reports_prints_each_language_with_its_locale(
    results: Results, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec D5: the zh report is printed in a zh-CN browser context, the en report in en-US (without a
    browser: printer, start check and gate replaced). P2: the printer works in a private folder in the
    computer's temporary folder (kernel.pdf.browser_work), not below the output folder, and the folder is
    gone afterwards."""
    printed: list[tuple[str, str]] = []
    folders: list[Path] = []

    class Printer:
        def __init__(self, shell: object, work: Path) -> None:
            folders.append(work)
            assert work.is_dir() and [p.name for p in work.iterdir()] == [WORK_LOCK]  # nothing but its lock

        def __enter__(self) -> Printer:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def print(self, source: Path, meta: PdfMeta, *, locale: str) -> PrintedPdf:
            printed.append((source.name, locale))
            return PrintedPdf(data=b"%PDF")

    shell = ShellInstall(tmp_path, tmp_path, tmp_path / "shell.exe", "win64")
    monkeypatch.setattr(output, "locate_shell", lambda environ: shell)
    monkeypatch.setattr(output, "preflight", lambda shell: None)
    monkeypatch.setattr(output, "PdfPrinter", Printer)
    monkeypatch.setattr(output, "qa_gate", lambda *args, **kwargs: [])
    out = tmp_path / "out"
    paths = write_reports(results, ["zh", "en"], ["pdf"], out, environ={})
    assert printed == [("report.zh.html", "zh-CN"), ("report.en.html", "en-US")]
    assert [p.read_bytes() for p in paths] == [b"%PDF", b"%PDF"]
    assert sorted(p.name for p in out.iterdir()) == ["report.en.pdf", "report.zh.pdf"]
    (work,) = folders
    assert work.parent == Path(tempfile.gettempdir()).absolute() and work.name.startswith(pdf.WORK_PREFIX)
    assert not work.exists()
    assert output.LOCALES == {"zh": "zh-CN", "en": "en-US"} and set(output.LOCALES.values()) == pdf.LOCALES


def test_output_that_cannot_be_written_ends_before_the_browser_starts(
    results: Results, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repair of P2: the browser's work folder no longer lies below --out, so the output folder is checked
    on its own before the browser starts (without a browser: printer and start check replaced). A file in
    the way of the folder or a folder that takes no new file ends with output.not_writable, a folder in the
    place of a report with output.is_directory; nothing is rendered or printed, nothing is written, a
    folder created for nothing is removed. The check leaves nothing behind when the folder is writable."""
    started: list[Path] = []
    rendered: list[str] = []
    real = output.render_report

    def spy(results: Results, lang: str, **kwargs: Any) -> str:
        rendered.append(lang)
        return real(results, lang, **kwargs)

    class Printer:
        def __init__(self, shell: object, work: Path) -> None:
            started.append(work)

        def __enter__(self) -> Printer:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def print(self, source: Path, meta: PdfMeta, *, locale: str) -> PrintedPdf:
            return PrintedPdf(data=b"%PDF")

    shell = ShellInstall(tmp_path, tmp_path, tmp_path / "shell.exe", "win64")
    monkeypatch.setattr(output, "locate_shell", lambda environ: shell)
    monkeypatch.setattr(output, "preflight", lambda shell: None)
    monkeypatch.setattr(output, "PdfPrinter", Printer)
    monkeypatch.setattr(output, "qa_gate", lambda *args, **kwargs: [])
    monkeypatch.setattr(output, "render_report", spy)
    blocker = tmp_path / "a file"
    blocker.write_text("in the way", encoding="utf-8")
    with pytest.raises(InputError) as info:
        write_reports(results, ["zh", "en"], ["html", "pdf"], blocker / "out", environ={})
    assert info.value.message_key == "output.not_writable" and started == [] and rendered == []
    occupied = tmp_path / "occupied"
    (occupied / "report.en.pdf").mkdir(parents=True)
    with pytest.raises(InputError) as info:
        write_reports(results, ["en"], ["html", "pdf"], occupied, environ={})
    assert info.value.message_key == "output.is_directory" and started == [] and rendered == []
    assert [p.name for p in occupied.iterdir()] == ["report.en.pdf"]
    real_create = output.create_temporary  # tempfile.mkstemp with the mode of any new file (kernel.safety)

    def refused(*args: Any, **kwargs: Any) -> tuple[int, str]:
        raise PermissionError(13, "no permission")

    new_folder = tmp_path / "new"
    with monkeypatch.context() as patch:
        patch.setattr(output, "create_temporary", refused)
        with pytest.raises(InputError) as info:
            write_reports(results, ["en"], ["pdf"], new_folder, environ={})
    assert output.create_temporary is real_create
    assert info.value.message_key == "output.not_writable" and started == [] and rendered == []
    assert not new_folder.exists()  # created by the check, removed again
    paths = write_reports(results, ["en"], ["html", "pdf"], new_folder, environ={})
    assert len(started) == 1 and sorted(p.name for p in new_folder.iterdir()) == [p.name for p in paths]


REPORT_NAMES = ("report.zh.html", "report.zh.pdf", "report.en.html", "report.en.pdf")


def _earlier_reports(folder: Path, names: tuple[str, ...] = REPORT_NAMES) -> dict[str, bytes]:
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(f"earlier {name}".encode())
    return {path.name: path.read_bytes() for path in folder.iterdir()}


def _new_reports(folder: Path) -> dict[Path, bytes]:
    return {folder / name: f"new {name}".encode() for name in REPORT_NAMES}


@pytest.mark.parametrize("failing_call", range(1, 9))
def test_write_all_restores_the_earlier_reports_when_a_rename_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing_call: int
) -> None:
    """Review R00 (B1 all-or-nothing): a rename that fails part way (the 1st to 4th moves an earlier report
    aside, the 5th to 8th moves a new one in) restores every earlier report byte for byte and leaves no new,
    staged or backup file behind. Before the repair the renames had no rollback: report.zh.html was new and
    the other three old."""
    before = _earlier_reports(tmp_path)
    real_replace = os.replace
    calls: list[str] = []

    def replace(source: Any, target: Any) -> None:
        calls.append(Path(source).name)
        if len(calls) == failing_call:
            raise PermissionError(13, "in use by another process")
        real_replace(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", replace)
        with pytest.raises(InputError) as info:
            output.write_all(_new_reports(tmp_path))
    assert info.value.message_key == "output.not_writable"
    assert len(calls) >= failing_call
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_write_all_without_earlier_reports_leaves_nothing_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Some targets are new: a failure while moving in removes the new files already placed."""
    before = _earlier_reports(tmp_path, ("report.en.pdf",))
    real_replace = os.replace

    def replace(source: Any, target: Any) -> None:
        if Path(target).name == "report.en.pdf" and Path(source).suffix == ".tmp":
            raise PermissionError(13, "in use by another process")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", replace)
    with pytest.raises(InputError):
        output.write_all(_new_reports(tmp_path))
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_write_all_replaces_every_report_and_removes_the_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Success: the new bytes, no backup or staged file; a backup that cannot be deleted afterwards does
    not fail the run (the new reports are complete)."""
    _earlier_reports(tmp_path)
    files = _new_reports(tmp_path)
    output.write_all(files)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == {
        path.name: data for path, data in files.items()
    }
    real_unlink = Path.unlink

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self.suffix == ".bak":
            raise PermissionError(13, "in use by another process")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    newer = {path: data + b" again" for path, data in files.items()}
    output.write_all(newer)
    assert all(path.read_bytes() == data for path, data in newer.items())
    backups = [path for path in tmp_path.iterdir() if path.suffix == ".bak"]
    assert len(backups) == 4 and all(path.name.startswith(".report.") for path in backups)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows locks a file that a program holds open")
@pytest.mark.parametrize("locked", REPORT_NAMES)
def test_write_all_with_a_report_open_in_a_viewer_changes_nothing(tmp_path: Path, locked: str) -> None:
    """Review R00, the real case: a report held open like a PDF viewer does (Python's open() shares no
    delete access, so the file cannot be renamed). Exit 2 (output.not_writable) and all four earlier
    reports unchanged, whichever one is open."""
    before = _earlier_reports(tmp_path)
    with (tmp_path / locked).open("rb"):
        with pytest.raises(InputError) as info:
            output.write_all(_new_reports(tmp_path))
    assert info.value.message_key == "output.not_writable"
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


@pytest.mark.pdf
def test_context_locale_leaves_the_pdf_bytes_unchanged(
    results: Results, written: dict[str, Path], pdf_shell: ShellInstall, tmp_path: Path
) -> None:
    """Decision (6) of the repair: zh-CN for the zh report and en-US for the en report only because the
    output stays byte-identical. Each delivered HTML printed in a zh-CN and in an en-US context gives the
    same bytes, and they are the bytes write_reports delivered (the HTML names its language, JavaScript is
    off, the fonts are embedded)."""
    with pdf.browser_work() as work, PdfPrinter(pdf_shell, work) as printer:
        for lang in ("zh", "en"):
            source = work / f"report.{lang}.html"
            source.write_bytes(written[f"report.{lang}.html"].read_bytes())
            meta = PdfMeta(translator(lang).t("report.title"), results.config.as_of)
            printed = {
                locale: printer.print(source, meta, locale=locale).data for locale in sorted(pdf.LOCALES)
            }
            assert printed["zh-CN"] == printed["en-US"], lang
            assert printed[output.LOCALES[lang]] == written[f"report.{lang}.pdf"].read_bytes(), lang


@pytest.mark.pdf
def test_failed_gate_writes_nothing(
    results: Results, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(output, "qa_gate", lambda *args, **kwargs: ["font_type3"])
    new_folder = tmp_path / "new"
    with pytest.raises(PdfError) as info:
        write_reports(results, ["zh", "en"], ["html", "pdf"], new_folder, environ=os.environ)
    assert info.value.message_key == "pdf.qa_failed" and info.value.params == {"checks": "font_type3"}
    assert not new_folder.exists()  # created for nothing, removed again
    kept = tmp_path / "kept"
    kept.mkdir()
    (kept / "report.en.html").write_text("older report", encoding="utf-8")
    with pytest.raises(PdfError):
        write_reports(results, ["en"], ["html", "pdf"], kept, environ=os.environ)
    assert [p.name for p in kept.iterdir()] == ["report.en.html"]
    assert (kept / "report.en.html").read_text(encoding="utf-8") == "older report"


@pytest.mark.pdf
def test_placeholder_banner_required_once(results: Results, tmp_path: Path) -> None:
    placeholder = results.model_copy(deep=True)
    placeholder.rulepacks[-1].source_status = SourceStatus.PLACEHOLDER
    document = html_document(placeholder, "en")
    expect = output.pdf_expectation(placeholder, "en", document)
    banner = translator("en").t("report.placeholder_banner")
    assert banner in expect.once and translator("en").t("disclaimer") in expect.every_page
    paths = write_reports(placeholder, ["en"], ["pdf"], tmp_path, environ=os.environ)
    assert _squeeze(banner) in _squeeze("".join(_texts(paths[0].read_bytes())))
    assert banner not in output.pdf_expectation(results, "en", html_document(results, "en")).once


@pytest.mark.pdf
def test_print_pdf_writes_only_a_passing_pdf(pdf_shell: ShellInstall, tmp_path: Path) -> None:
    """kernel.pdf.print_pdf (one document): print, QA gate, then an atomic write; a failing gate writes
    nothing."""
    text = "Hello 数据 <b>bold 粗体</b>"
    page = _page(text, css=NG_CSS, font_css=subset_font_css(FONT_FILES, text + "Control"))
    source = tmp_path / "page.html"
    source.write_text(page, encoding="utf-8")
    expect = PdfExpect(meta=PdfMeta("Control", AS_OF), fonts=FONTS, every_page=("Hello",), once=("bold",))
    target = tmp_path / "out" / "page.pdf"
    with pdf.browser_work() as work:
        printed = pdf.print_pdf(source, target, meta=expect.meta, expect=expect, shell=pdf_shell, work=work)
    assert target.read_bytes() == printed.data and printed.log.seen == 1
    assert sorted(p.name for p in target.parent.iterdir()) == ["page.pdf"]
    other = tmp_path / "other" / "page.pdf"
    wrong = PdfExpect(meta=expect.meta, fonts=FONTS, every_page=("absent phrase",))
    with pytest.raises(PdfError) as info, pdf.browser_work() as work:
        pdf.print_pdf(source, other, meta=expect.meta, expect=wrong, shell=pdf_shell, work=work)
    assert info.value.params == {"checks": "phrase_missing_on_page"} and not other.exists()


class _Text(html.parser.HTMLParser):
    """The text a reader sees in the body (no style, no head)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self._body = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._body = self._body or tag == "body"
        self._skip += tag in ("style", "script")

    def handle_endtag(self, tag: str) -> None:
        self._skip -= tag in ("style", "script")

    def handle_data(self, data: str) -> None:
        if self._body and not self._skip:
            self.parts.append(data)


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_gate_phrases_and_margin_texts_are_in_the_html(results: Results, lang: str) -> None:
    """Without a browser: what the runtime QA gate requires of the PDF is in the delivered HTML (title and
    section headings in the body, the fixed sentence in the footer's CSS), the font subsets cover the
    margin-box texts, the HTML carries the CSP of A-08 and the neutral title (no dataset name)."""
    document = html_document(results, lang)
    expect = output.pdf_expectation(results, lang, document)
    reader = _Text()
    reader.feed(document)
    body = _squeeze("".join(reader.parts))
    assert all(_squeeze(phrase) in body for phrase in expect.once), expect.once
    assert expect.every_page == (translator(lang).t("disclaimer"),)
    assert all(phrase in page_text(lang) for phrase in expect.every_page)
    assert (
        expect.meta.title == translator(lang).t("report.title")
        and results.dataset.name not in expect.meta.title
    )
    assert expect.meta.as_of == results.config.as_of and pdf.has_csp(document)
    css = re.findall(r"base64,([A-Za-z0-9+/=]+)", document)
    assert len(css) == 2  # weights 400 and 700, embedded in the HTML too (B1)
    covered = font_codepoints(FONT_FILES)
    wanted = {ord(ch) for ch in page_text(lang) if ord(ch) in covered}
    for data in css:
        assert wanted <= set(TTFont(io.BytesIO(base64.b64decode(data))).getBestCmap())


def test_pdf_needs_the_browser_before_anything_is_rendered(
    results: Results, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B1/A-26: with pdf requested and no browser, exit 2 before any rendering and nothing written; HTML
    alone never needs the browser."""
    environ = {pdf.ENV_BROWSER_DIR: str(tmp_path / "no-browser")}
    rendered: list[str] = []
    real = output.render_report

    def spy(results: Results, lang: str, **kwargs: Any) -> str:
        rendered.append(lang)
        return real(results, lang, **kwargs)

    monkeypatch.setattr(output, "render_report", spy)
    folder = tmp_path / "out"
    for formats in (["pdf"], ["html", "pdf"]):
        with pytest.raises(PdfError) as info:
            write_reports(results, ["zh", "en"], formats, folder, environ=environ)
        assert info.value.message_key == "pdf.shell_missing" and info.value.hint == ("pdf.install.docs", {})
    assert rendered == [] and not folder.exists()
    paths = write_reports(results, ["zh", "en"], ["html"], folder, environ=environ)
    assert [p.name for p in paths] == ["report.zh.html", "report.en.html"] and rendered == [
        "zh",
        "zh",
        "en",
        "en",
    ]
    assert sorted(p.name for p in folder.iterdir()) == ["report.en.html", "report.zh.html"]
    with pytest.raises(NeuroGridError) as unknown:
        write_reports(results, ["en"], ["html", "docx"], tmp_path / "x", environ=environ)
    assert unknown.value.params == {"format": "docx"} and not (tmp_path / "x").exists()
