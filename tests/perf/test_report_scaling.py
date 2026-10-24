"""Report scaling (A-59, KONZEPT 4 "Skalierung 1000 x 64", B1): a synthetic results.json of 1000 recordings
x 64 channels from tools/gen_fixtures.py (scale_results; the worst case has every channel failing M07 and
M08-01, about 128 000 findings), rendered by the real ``neurogrid report`` process.

Excluded by default (marker ``perf``); run with ``pytest tests/perf -m perf -s``. Each test prints its
measurements (wall time and peak memory of the process tree, file sizes, pages) and writes them to
.local/perf/report_scaling.json. The asserted part is the A-59 structure (at most 50 rows per rule, the exact
remainder named, one metrics row per recording) and determinism; the time and size limits are fixed after the
measurement on the real fonts (A-88). The PDF test needs the PDF pipeline and the Chrome Headless Shell
(tools/install_pdf_browser.py); without them it is skipped, unless NEUROGRID_REQUIRE_PDF=1.
"""

from __future__ import annotations

import html as html_lib
import importlib.util
import json
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
