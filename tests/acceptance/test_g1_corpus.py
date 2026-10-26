"""G1 on the public test corpus (KONZEPT §6 G1, PRD §19 G1, V-01, NG-F13, NG-F14, NG-N03, NG-N05, REP-00,
V-06): the acceptance run of tools/acceptance_g1.py - per data set scan, check (core + bids + gxdsl008,
--jobs 4), report (zh + en, HTML + PDF), manifest and verify as real processes, twice, plus check --jobs 1
on ds004148 - once per session, then one test per data set and criterion. About 25 minutes for all six data
sets; with ``-k <data set>`` only the selected data sets run. Markers ``corpus`` (the corpus in
.local/corpus, python tools/corpus.py fetch) and ``pdf``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import acceptance_g1 as g1  # type: ignore[import-not-found]

pytestmark = [pytest.mark.corpus, pytest.mark.pdf]

ROOT = Path(__file__).parent.parent.parent
CORPUS = ROOT / ".local" / "corpus"
NAMES = [entry["local_dir"] for entry in g1.corpus_datasets()]


def _selected(request: pytest.FixtureRequest) -> list[str]:
    """The data sets the selected tests of this module need: all of them as soon as one selected test is
    about the whole run (minimum coverage, --jobs 1, corpus unchanged, V-01)."""
    names: set[str] = set()
    for item in request.session.items:
        if item.module is not request.module:
            continue
        params = getattr(getattr(item, "callspec", None), "params", {})
        if "name" not in params:
            return NAMES
        names.add(params["name"])
    return [name for name in NAMES if name in names] or NAMES


@pytest.fixture(scope="module")
def summary(
    request: pytest.FixtureRequest, pdf_shell: object, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, Any]:
    if not CORPUS.is_dir():
        pytest.skip("the corpus is not in .local/corpus (python tools/corpus.py fetch)")
    out = tmp_path_factory.mktemp("g1")
    try:
        return g1.run_acceptance(CORPUS, out, names=_selected(request))
    except g1.ToolError as exc:  # corpus changed or incomplete, browser missing: no G1 statement possible
        pytest.fail(f"acceptance tool error: {exc}")


def _entry(summary: dict[str, Any], name: str) -> dict[str, Any]:
    entries = [entry for entry in summary["datasets"] if entry["name"] == name]
    assert len(entries) == 1, name
    return entries[0]


def _problems(entry: dict[str, Any], category: str) -> list[str]:
    return [problem for problem in entry["problems"] if problem.startswith(f"{category}: ")]


@pytest.mark.parametrize("name", NAMES)
def test_check_and_report_without_exit_2(summary: dict[str, Any], name: str) -> None:
    entry = _entry(summary, name)
    assert entry["check_exit"] in (0, 1) and entry["report_exit"] == 0
    assert all(code != 2 for code in entry["exit"].values()), entry["exit"]
    assert _problems(entry, "exit") == []


@pytest.mark.parametrize("name", NAMES)
def test_console_streams_are_clean_utf8(summary: dict[str, Any], name: str) -> None:
    assert _problems(_entry(summary, name), "console") == []


@pytest.mark.parametrize("name", NAMES)
def test_output_files_and_results_json(summary: dict[str, Any], name: str) -> None:
    entry = _entry(summary, name)
    assert _problems(entry, "files") == [] and _problems(entry, "json") == []


@pytest.mark.parametrize("name", NAMES)
def test_every_finding_row_has_all_cells(summary: dict[str, Any], name: str) -> None:
    entry = _entry(summary, name)
    assert _problems(entry, "rows") == []
    assert entry["rows_checked"]["zh"] == entry["rows_checked"]["en"] > 0


@pytest.mark.parametrize("name", NAMES)
def test_pdf_quality_gate_and_independent_reading(summary: dict[str, Any], name: str) -> None:
    entry = _entry(summary, name)
    assert _problems(entry, "pdf") == []
    assert entry["pdf_pages"]["zh"] > 0 and entry["pdf_pages"]["en"] > 0


@pytest.mark.parametrize("name", NAMES)
def test_no_host_path_or_header_data_in_outputs(summary: dict[str, Any], name: str) -> None:
    entry = _entry(summary, name)
    assert _problems(entry, "privacy") == []
    assert entry["forbidden_values_checked"] > 0


@pytest.mark.parametrize("name", NAMES)
def test_two_runs_are_byte_identical(summary: dict[str, Any], name: str) -> None:
    entry = _entry(summary, name)
    assert _problems(entry, "determinism") == [] and entry["identical"]


@pytest.mark.parametrize("name", NAMES)
def test_only_core_bids_gxdsl008_and_no_norm_content(summary: dict[str, Any], name: str) -> None:
    entry = _entry(summary, name)
    assert entry["packs"] == ["core", "bids", "gxdsl008"] and entry["v06"] == []


def test_minimum_g1_coverage(summary: dict[str, Any]) -> None:
    result = summary["g1"]
    assert result["minimum_met"], result  # PRD §19: at least 3 data sets in at least 2 formats
    assert result["all_met"] and set(result["formats_ok"]) == set(g1.FORMATS)


def test_jobs_1_and_4_identical(summary: dict[str, Any]) -> None:
    jobs1 = summary["jobs1"]
    assert jobs1 is not None and jobs1["identical"] and jobs1["problems"] == []


def test_corpus_unchanged_and_all_criteria(summary: dict[str, Any]) -> None:
    assert summary["corpus_unchanged"]
    assert summary["g1"]["criteria_met"]


def test_v01_checklist(summary: dict[str, Any]) -> None:
    items = summary["v01_checklist"]
    assert [item["number"] for item in items] == list(range(1, 8))
    assert [item["item"] for item in items if item["status"] != "fulfilled"] == []
    assert summary["v01_fulfilled"]
