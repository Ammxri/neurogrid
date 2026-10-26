"""Report scaling (A-59, KONZEPT 4 "Skalierung 1000 x 64", B1): a synthetic results.json of 1000 recordings
x 64 channels from tools/gen_fixtures.py (scale_results; the worst case has every channel failing M07 and
M08-01, about 128 000 findings), rendered by the real ``neurogrid report`` process.

Excluded by default (marker ``perf``); run with ``pytest tests/perf -m perf -s``. Each test prints its
measurements (wall time and peak memory of the process tree, file sizes, pages) and writes them to
.local/perf/report_scaling.json. Asserted are the A-59 structure (at most 50 rows per rule, the exact
remainder named, one metrics row per recording), determinism, a passing QA gate and the regression limits
(A-88): each limit is the measurement on the real fonts and shell (MEASURED) plus a 50 % reserve, rounded up.
PRD and KONZEPT set no limit for the report; the limits guard against regressions and hold for a machine like
the measuring one. The PDF tests need the PDF pipeline and the Chrome Headless Shell
(tools/install_pdf_browser.py); without them they are skipped, unless NEUROGRID_REQUIRE_PDF=1.
"""

from __future__ import annotations

import html as html_lib
import importlib.util
import io
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from neurogrid.kernel import canonical
from neurogrid.model.results import Results
from neurogrid.report.render import MAX_ROWS_PER_RULE
from neurogrid.report.texts import translator

if TYPE_CHECKING:
    import psutil

pytestmark = pytest.mark.perf

ROOT = Path(__file__).parent.parent.parent
MEASUREMENTS = ROOT / ".local" / "perf" / "report_scaling.json"
RECORDINGS, CHANNELS = 1000, 64
RESERVE = 1.5  # A-88: +50 % on the measurement
# Measured 2026-10-26 (NeuroGrid 0.1.0rc1, Windows 11 Home build 26200, AMD Ryzen 9 6900HX 8 cores / 16
# threads, 31 GB RAM, Python 3.12.15, Playwright 1.63.0, Chrome Headless Shell revision 1243, the static
# Noto Sans SC cuts of A-27). Worst case: 128 742 findings (149 MB results.json); typical: 6 110 findings.
# html_* / pdf_*: the ``report --lang zh,en`` process with --format html resp. html,pdf (wall time, peak
# memory of the process tree); parse/render/print/gate: the stages of that process one by one, per language
# the larger value; bytes and pages per language.
MEASURED: dict[str, dict[str, Any]] = {
    "worst": {
        "html_wall_s": 18.5,
        "html_peak_rss_mb": 1703,
        "pdf_wall_s": 88.1,
        "pdf_peak_rss_mb": 1866,
        "html_bytes": {"zh": 1_252_705, "en": 1_026_261},
        "pdf_bytes": {"zh": 730_131, "en": 728_364},
        "pages": {"zh": 99, "en": 106},
        "parse_s": 3.4,
        "render_s": 5.5,
        "print_s": 4.2,
        "gate_s": 29.9,
    },
    "typical": {
        "html_wall_s": 9.5,
        "html_peak_rss_mb": 364,
        "pdf_wall_s": 80.4,
        "pdf_peak_rss_mb": 1255,
        "html_bytes": {"zh": 1_309_136, "en": 1_081_128},
        "pdf_bytes": {"zh": 835_710, "en": 854_455},
        "pages": {"zh": 136, "en": 142},
        "parse_s": 0.5,
        "render_s": 3.3,
        "print_s": 4.4,
        "gate_s": 34.6,
    },
}


def limit(case: str, name: str, lang: str | None = None) -> int:
    """The regression limit: the measurement plus RESERVE, rounded up (whole seconds, MB, bytes, pages)."""
    value = MEASURED[case][name]
    return math.ceil((value[lang] if lang else value) * RESERVE)


def _within(case: str, name: str, value: float, lang: str | None = None) -> None:
    bound = limit(case, name, lang)
    assert value <= bound, f"{case} {name}{f' ({lang})' if lang else ''}: {value} > limit {bound}"


def _tree_rss(process: psutil.Process) -> int:
    import psutil  # dev dependency (pyproject), imported only when a perf test runs

    total = 0
    try:
        total += process.memory_info().rss
        for child in process.children(recursive=True):
            try:
                total += child.memory_info().rss
            except psutil.Error:
                continue
    except psutil.Error:
        pass
    return total


def _report(results_file: Path, out: Path, formats: str) -> dict[str, Any]:
    command = [sys.executable, "-m", "neurogrid", "report", str(results_file), "--lang", "zh,en"]
    command += ["--format", formats, "--out", str(out)]
    import psutil  # dev dependency (pyproject), imported only when a perf test runs

    start = time.perf_counter()
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    watched = psutil.Process(process.pid)
    peak = 0
    while process.poll() is None:
        peak = max(peak, _tree_rss(watched))
        time.sleep(0.05)
    stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
    return {
        "exit_code": process.returncode,
        "wall_s": round(time.perf_counter() - start, 1),
        "peak_rss_mb": round(peak / 1e6),
        "stderr_tail": stderr[-300:],
    }


def _record(name: str, row: dict[str, Any]) -> None:
    print(name, json.dumps(row, ensure_ascii=False))
    MEASUREMENTS.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(MEASUREMENTS.read_text(encoding="utf-8")) if MEASUREMENTS.is_file() else {}
    data[name] = row
    MEASUREMENTS.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture(scope="module", params=["worst", "typical"])
def scaled(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> tuple[str, Path, Results]:
    from gen_fixtures import scale_results  # type: ignore[import-not-found]

    start = time.perf_counter()
    results = scale_results(RECORDINGS, CHANNELS, worst_case=request.param == "worst")
    path = tmp_path_factory.mktemp(f"scale-{request.param}") / "results.json"
    path.write_bytes(canonical.dumps(results))
    seconds = round(time.perf_counter() - start, 1)
    _record(
        f"generate-{request.param}",
        {"findings": len(results.findings), "json_bytes": path.stat().st_size, "seconds": seconds},
    )
    return request.param, path, results


def test_report_html_scales_to_1000_recordings_x_64_channels(
    scaled: tuple[str, Path, Results], tmp_path: Path
) -> None:
    case, results_file, results = scaled
    if case == "worst":
        assert len(results.findings) >= 2 * RECORDINGS * CHANNELS
    first = _report(results_file, tmp_path / "a", "html")
    second = _report(results_file, tmp_path / "b", "html")
    assert first["exit_code"] == 0 and second["exit_code"] == 0, first["stderr_tail"]
    totals: dict[str, int] = {}
    for finding in results.findings:
        totals[finding.rule_id] = totals.get(finding.rule_id, 0) + 1
    sizes = {}
    for lang in ("zh", "en"):
        html = (tmp_path / "a" / f"report.{lang}.html").read_text(encoding="utf-8")
        assert html == (tmp_path / "b" / f"report.{lang}.html").read_text(encoding="utf-8")  # NG-N03
        sizes[lang] = len(html.encode("utf-8"))
        tr = translator(lang).t
        for rule, total in totals.items():
            shown = len(re.findall(rf'<tr data-key="[0-9a-f]+"><td class="c-rule mono">{rule}</td>', html))
            assert shown == min(total, MAX_ROWS_PER_RULE), rule
            if total > shown:
                assert tr("report.text.rule_more", count=total - shown, rule=rule) in html_lib.unescape(html)
        assert html.count('<tr data-recording="') == RECORDINGS
    _record(f"report-html-{case}", {**first, "html_bytes": sizes, "rules": totals})
    _within(case, "html_wall_s", first["wall_s"])
    _within(case, "html_peak_rss_mb", first["peak_rss_mb"])
    for lang, size in sizes.items():
        _within(case, "html_bytes", size, lang)


def test_report_pdf_scales_to_1000_recordings_x_64_channels(
    scaled: tuple[str, Path, Results], tmp_path: Path
) -> None:
    """The same with ``--format html,pdf``: the PDF pipeline prints the HTML and runs its QA gate on every
    PDF (fixed sentence on every page, embedded fonts only) inside the measured process."""
    if importlib.util.find_spec("neurogrid.kernel.pdf") is None:
        pytest.skip("the PDF pipeline (kernel/pdf.py) is not part of this build")
    from neurogrid.kernel import pdf  # type: ignore[attr-defined,unused-ignore]

    try:
        pdf.locate_shell(os.environ)
    except Exception as exc:  # no shell installed: like the pdf area's tests (B2)
        if os.environ.get("NEUROGRID_REQUIRE_PDF") == "1":
            raise
        pytest.skip(
            f"Chrome Headless Shell not installed ({type(exc).__name__}); tools/install_pdf_browser.py"
        )
    import pypdf

    case, results_file, _results = scaled
    row = _report(results_file, tmp_path, "html,pdf")
    assert row["exit_code"] == 0, row["stderr_tail"]
    pages = {}
    for lang in ("zh", "en"):
        document = tmp_path / f"report.{lang}.pdf"
        pages[lang] = {"pages": len(pypdf.PdfReader(document).pages), "pdf_bytes": document.stat().st_size}
    _record(f"report-html-pdf-{case}", {**row, "pdf": pages})
    _within(case, "pdf_wall_s", row["wall_s"])
    _within(case, "pdf_peak_rss_mb", row["peak_rss_mb"])
    for lang, measured in pages.items():
        _within(case, "pages", measured["pages"], lang)
        _within(case, "pdf_bytes", measured["pdf_bytes"], lang)


@pytest.mark.pdf
def test_report_stages_render_print_and_gate(
    scaled: tuple[str, Path, Results], pdf_shell: object, tmp_path: Path
) -> None:
    """The stages of the report process timed one by one on the same results (A-59, A-88): parsing
    results.json, rendering the delivered HTML (two passes, the second with the font subsets), printing it
    (one browser for both languages, as in the product) and the QA gate on each PDF, which must pass."""
    import pypdf

    from neurogrid.kernel.pdf import PdfPrinter, ShellInstall, qa_gate
    from neurogrid.report.output import LOCALES, html_document, pdf_expectation

    assert isinstance(pdf_shell, ShellInstall)
    case, results_file, _results = scaled
    start = time.perf_counter()
    results = Results.model_validate_json(results_file.read_bytes())
    row: dict[str, Any] = {"parse_s": round(time.perf_counter() - start, 1)}
    with PdfPrinter(pdf_shell, tmp_path / "work") as printer:
        for lang in ("zh", "en"):
            start = time.perf_counter()
            document = html_document(results, lang)
            render_s = time.perf_counter() - start
            source = tmp_path / f"report.{lang}.html"
            source.write_bytes(document.encode("utf-8"))
            expect = pdf_expectation(results, lang, document)
            start = time.perf_counter()
            printed = printer.print(source, expect.meta, locale=LOCALES[lang])
            print_s = time.perf_counter() - start
            start = time.perf_counter()
            violations = qa_gate(printed.data, expect, log=printed.log)
            gate_s = time.perf_counter() - start
            assert violations == [], (lang, violations)
            row[lang] = {
                "render_s": round(render_s, 1),
                "print_s": round(print_s, 1),
                "gate_s": round(gate_s, 1),
                "html_bytes": len(document.encode("utf-8")),
                "pdf_bytes": len(printed.data),
                "pages": len(pypdf.PdfReader(io.BytesIO(printed.data)).pages),
            }
    _record(f"report-stages-{case}", row)
    _within(case, "parse_s", row["parse_s"])
    for lang in ("zh", "en"):
        for name in ("render_s", "print_s", "gate_s"):
            _within(case, name, row[lang][name])
        _within(case, "html_bytes", row[lang]["html_bytes"], lang)
        _within(case, "pdf_bytes", row[lang]["pdf_bytes"], lang)
        _within(case, "pages", row[lang]["pages"], lang)
