"""PDF reports (TECH-07, NG-F13, NG-N01, A-08, A-26, A-27, A-49, A-51, A-54).

The checks here use their own reading of the PDF (pypdf), not the QA gate they test (B2). Tests that print
are marked ``pdf``: skipped without the browser, failing without it when NEUROGRID_REQUIRE_PDF=1. The
others (HTML side of the pipeline, all-or-nothing without a browser) always run.

Every folder of these tests lies below the short browser folder of tests/conftest.py (tmp_path is browser_tmp
here), so that the browser's profile paths stay short whatever --basetemp is.
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
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pypdf
import pytest
from fontTools.ttLib import TTFont
from pypdf.generic import DictionaryObject

from neurogrid import pipeline
from neurogrid.kernel import canonical, fonts, pdf
from neurogrid.kernel.errors import NeuroGridError, PdfError
from neurogrid.kernel.findings import SourceStatus, TimeRange
from neurogrid.kernel.fonts import (
    FONT_FAMILY,
    font_codepoints,
    postscript_names,
    shared_glyphs,
    subset_font_css,
)
from neurogrid.kernel.pdf import CSP, PdfExpect, PdfMeta, PdfPrinter, PrintedPdf, ShellInstall, qa_gate
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


@pytest.fixture
def tmp_path(browser_tmp: Path) -> Path:
    return browser_tmp


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
def written(results: Results, pdf_shell: ShellInstall, browser_root: Path) -> dict[str, Path]:
    """The four reports of ``results`` (needs the browser: skipped or failed like every pdf test)."""
    folder = Path(tempfile.mkdtemp(prefix="pdf-", dir=browser_root)) / "报告 out"
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


@pytest.mark.pdf
def test_rule_ids_do_not_break_inside_in_the_pdf(results: Results, written: dict[str, Path]) -> None:
    """Every rule ID of the finding tables stands on one line of the PDF text (the verifier saw
    'BIDS / -STO / -002' in the portrait table of this branch). The landscape finding tables with fixed
    columns are the report area's (B1, REP-00); without them the check is skipped, after the merge it
    guards the layout of the printed tables."""
    for lang in ("zh", "en"):
        if "@page wide" not in written[f"report.{lang}.html"].read_text(encoding="utf-8"):
            pytest.skip("the landscape finding tables of the report area (B1) are not in this build")
        lines = "\n".join(_texts(written[f"report.{lang}.pdf"].read_bytes())).splitlines()
        broken = sorted({f.rule_id for f in results.findings if not any(f.rule_id in line for line in lines)})
        assert not broken, (lang, broken)


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
    work = tmp_path / "work"
    with PdfPrinter(pdf_shell, work) as printer:
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
    netlog = tmp_path / "netlog.json"
    work = tmp_path / "work"
    flags = (f"--log-net-log={netlog}", "--net-log-capture-mode=Everything")
    with PdfPrinter(pdf_shell, work, extra_flags=flags) as printer:
        source = work / "report.en.html"
        source.write_text(html_document(results, "en"), encoding="utf-8")
        printed = printer.print(source, PdfMeta(translator("en").t("report.title"), AS_OF))
    assert printed.log.seen == 1 and printed.log.unexpected == 0
    events = _netlog_events(netlog)
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


def _tree(folder: Path, *, undone: Path) -> dict[str, tuple[int, int] | None]:
    """Size and modification time of every file and folder below ``folder``; for the folder ``undone`` (the
    one of the executable) only that it exists. A debug.log that a child process of the shell writes there
    during a run is removed again when the printer closes (kernel/pdf.py, A-54), and other NeuroGrid runs on
    the same browser folder do the same: that changes only the time of this one folder, never its content."""
    return {
        str(p.relative_to(folder)): None if p == undone else (p.stat().st_size, p.stat().st_mtime_ns)
        for p in folder.rglob("*")
    }


def test_shell_folder_tree_ignores_only_the_time_of_the_executable_folder(tmp_path: Path) -> None:
    shell = tmp_path / "chrome-headless-shell-1243"
    exe_dir = shell / "chrome-headless-shell-win64"
    (exe_dir / "locales").mkdir(parents=True)
    (exe_dir / "chrome-headless-shell.exe").write_bytes(b"MZ")
    (exe_dir / "locales" / "en-US.pak").write_bytes(b"pak")
    before = _tree(shell, undone=exe_dir)
    (exe_dir / "debug.log").write_bytes(b"[ERROR] line\n")  # written by a child process, undone at close
    (exe_dir / "debug.log").unlink()
    stamp = exe_dir.stat().st_mtime_ns + 10**9
    os.utime(exe_dir, ns=(stamp, stamp))
    assert _tree(shell, undone=exe_dir) == before
    (exe_dir / "debug.log").write_bytes(b"left behind\n")
    assert _tree(shell, undone=exe_dir) != before
    (exe_dir / "debug.log").unlink()
    (exe_dir / "chrome-headless-shell.exe").write_bytes(b"MZ!")
    assert _tree(shell, undone=exe_dir) != before
    (exe_dir / "chrome-headless-shell.exe").write_bytes(b"MZ")
    os.utime(exe_dir / "chrome-headless-shell.exe", ns=(10**18, 10**18))
    assert _tree(shell, undone=exe_dir) != before  # a file's time still counts
    os.utime(exe_dir / "locales", ns=(stamp, stamp))
    assert _tree(shell, undone=exe_dir) != before  # and the time of every other folder


@pytest.mark.pdf
def test_no_files_left_in_temp_and_shell_folder_unchanged(
    results: Results, pdf_shell: ShellInstall, tmp_path: Path
) -> None:
    """A-54: driver and browser use the run's work folder. A run with its own, empty temporary and user
    data folders leaves all of them empty (no Playwright folder, no browser profile), leaves the browser
    folder unchanged (the shell would otherwise write debug.log next to its executable) and the output
    folder holds only the reports."""
    source = tmp_path / "results.json"
    source.write_bytes(canonical.dumps(results))
    private = {
        name: tmp_path / name.lower() for name in ("TEMP", "LOCALAPPDATA", "APPDATA", "XDG_CACHE_HOME")
    }
    for folder in private.values():
        folder.mkdir()
    env = {
        **os.environ,
        **{name: str(folder) for name, folder in private.items()},
        "TMP": str(private["TEMP"]),
        "TMPDIR": str(private["TEMP"]),
        "XDG_CONFIG_HOME": str(private["XDG_CACHE_HOME"]),
        "XDG_DATA_HOME": str(private["XDG_CACHE_HOME"]),
        pdf.ENV_BROWSER_DIR: str(pdf_shell.folder),
        "PYTHONIOENCODING": "utf-8",
    }
    before_shell = _tree(pdf_shell.shell_dir, undone=pdf_shell.executable.parent)
    out = tmp_path / "out"
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "neurogrid",
            "report",
            str(source),
            "--lang",
            "zh,en",
            "--format",
            "pdf",
            "--out",
            str(out),
        ],
        capture_output=True,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert sorted(p.name for p in out.iterdir()) == ["report.en.pdf", "report.zh.pdf"]
    assert {name: sorted(p.name for p in folder.iterdir()) for name, folder in private.items()} == {
        name: [] for name in private
    }
    assert _tree(pdf_shell.shell_dir, undone=pdf_shell.executable.parent) == before_shell


@pytest.mark.pdf
@pytest.mark.skipif(sys.platform != "win32", reason="the fallback to the current folder is Windows logging")
def test_fallback_log_of_a_long_work_folder_stays_in_the_work_folder(
    pdf_shell: ShellInstall, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A-51/A-54: from a work folder of 198 characters on, the paths of the browser's profile pass 260
    characters and Chromium's logging falls back to debug.log in the current folder (measured with revision
    1243; from 210 characters the shell no longer starts). That folder is the work folder, removed after the
    run, never the user's current folder (it was, with the paths of the work folder in it)."""
    here = tmp_path / "current"
    here.mkdir()
    monkeypatch.chdir(here)
    work = tmp_path / "w"
    work = work / ("w" * (204 - len(str(work)) - 1))
    assert len(str(work)) == 204
    source = tmp_path / "page.html"
    source.write_text(_page("<p>x</p>"), encoding="utf-8")
    with PdfPrinter(pdf_shell, work) as printer:
        printed = printer.print(source, PdfMeta("t", AS_OF))
    assert printed.data.startswith(b"%PDF-")
    assert sorted(here.iterdir()) == []
    assert (work / pdf.CHILD_LOG).is_file()  # the fallback happened, in the work folder


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
    work = tmp_path / "work"

    def printed(name: str) -> str:
        source = work / f"{name}.html"
        source.write_text(_page(body, css=NG_CSS, font_css=subset_font_css(FONT_FILES, body)), "utf-8")
        result = printer.print(source, expect.meta)
        assert qa_gate(result.data, expect, log=result.log) == []
        return "".join(_texts(result.data))

    with PdfPrinter(pdf_shell, work) as printer:
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


def test_write_reports_prints_each_language_with_its_locale(
    results: Results, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec D5: the zh report is printed in a zh-CN browser context, the en report in en-US (without a
    browser: printer, start check and gate replaced)."""
    printed: list[tuple[str, str]] = []

    class Printer:
        def __init__(self, shell: object, work: Path) -> None:
            pass

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
    paths = write_reports(results, ["zh", "en"], ["pdf"], tmp_path, environ={})
    assert printed == [("report.zh.html", "zh-CN"), ("report.en.html", "en-US")]
    assert [p.read_bytes() for p in paths] == [b"%PDF", b"%PDF"]
    assert output.LOCALES == {"zh": "zh-CN", "en": "en-US"} and set(output.LOCALES.values()) == pdf.LOCALES


@pytest.mark.pdf
def test_context_locale_leaves_the_pdf_bytes_unchanged(
    results: Results, written: dict[str, Path], pdf_shell: ShellInstall, tmp_path: Path
) -> None:
    """Decision (6) of the repair: zh-CN for the zh report and en-US for the en report only because the
    output stays byte-identical. Each delivered HTML printed in a zh-CN and in an en-US context gives the
    same bytes, and they are the bytes write_reports delivered (the HTML names its language, JavaScript is
    off, the fonts are embedded)."""
    work = tmp_path / "work"
    with PdfPrinter(pdf_shell, work) as printer:
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
    printed = pdf.print_pdf(
        source, target, meta=expect.meta, expect=expect, shell=pdf_shell, work=tmp_path / "w"
    )
    assert target.read_bytes() == printed.data and printed.log.seen == 1
    assert sorted(p.name for p in target.parent.iterdir()) == ["page.pdf"]
    other = tmp_path / "other" / "page.pdf"
    wrong = PdfExpect(meta=expect.meta, fonts=FONTS, every_page=("absent phrase",))
    with pytest.raises(PdfError) as info:
        pdf.print_pdf(source, other, meta=expect.meta, expect=wrong, shell=pdf_shell, work=tmp_path / "w2")
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
