"""The committed results and reports of the two final runs (NG-F17, NA-01, NA-05, DoD 1, DoD 2; A-107,
F8 A): every file present, the full configuration (three approved datasets, all 16 conditions, both
decoders, every subject), both decoders for every dataset on both axes, the comparison of the two runs ok,
and the reports in en and zh rendered from exactly these results. Strict: it fails until the lead commits
the results of the final runs (``python -m neuroarena.report publish RUN_A RUN_B`` and ``render``); it
needs no run folder."""

from __future__ import annotations

import csv
import json
from collections import Counter

import pytest

import _wording
from neuroarena import paths, records, report
from neuroarena.datasets import DATASETS
from neuroarena.decoders import DECODERS
from neuroarena.keys import CONDITIONS, KINDS, LEVELS

RESULTS = paths.RESULTS
REPORTS = {"en": paths.REPORT_EN / report.REPORT_FILE, "zh": paths.REPORT_ZH / report.REPORT_FILE}


@pytest.fixture(scope="module")
def method() -> dict:
    missing = [name for name in report.PUBLISHED if not (RESULTS / name).is_file()]
    missing += [path.name for path in REPORTS.values() if not path.is_file()]
    assert not missing, f"not published: {missing}"
    return json.loads((RESULTS / report.METHOD_FILE).read_text(encoding="utf-8"))


def test_the_final_runs_are_full_runs_of_the_approved_configuration(method: dict) -> None:
    """F1 B, F2 A, F4a A, F7 A: Zhou2016, Cho2017, Kalunga2016, all 16 conditions, both decoders, every
    subject of the loaders, mode full; two different run ids."""
    assert method["mode"] == "full"
    assert method["config"]["datasets"] == list(DATASETS)
    assert method["config"]["conditions"] == [condition.id for condition in CONDITIONS]
    assert method["config"]["decoders"] == list(DECODERS)
    assert method["config"]["subjects"] is None
    for name, spec in DATASETS.items():
        assert len(method["subjects"][name]) == spec.n_subjects, name
    assert len(method["runs"]) == 2 and method["runs"][0] != method["runs"][1]


def test_run_compare_of_the_two_final_runs_is_ok(method: dict) -> None:
    """DoD 1: the two final runs are equal within the documented tolerance (F3)."""
    comparison = json.loads((RESULTS / paths.RUN_COMPARE_FILE).read_text(encoding="utf-8"))
    assert comparison["ok"] is True, comparison["differences"][:5]
    assert comparison["runs"] == method["runs"]
    n_conditions = len(method["config"]["conditions"]) * len(method["config"]["datasets"])
    assert comparison["compared"]["quality"] == n_conditions
    assert comparison["compared"]["neurogrid"] > 0 and comparison["compared"]["fold"] > 0
    assert not [d for d in comparison["differences"] if d["what"] == "missing"]


def test_curve_data_has_both_decoders_every_dataset(method: dict) -> None:
    """DoD 2 on the committed curve.csv: every dataset and decoder at every degradation level of every kind
    (clean at 0) and on the quality axis with every pair that has a level; the pairs without a level match
    sessions.csv; nothing is invented (a level without pairs has no row)."""
    curve = records.read_curve(RESULTS / paths.CURVE_FILE)
    sessions = records.read_sessions(RESULTS / paths.SESSIONS_FILE)
    for dataset in DATASETS:
        for decoder in DECODERS:
            for kind in KINDS:
                xs = {
                    p.x
                    for p in curve
                    if (p.dataset, p.decoder, p.axis, p.kind) == (dataset, decoder, "degradation", kind)
                }
                assert xs == {0, *LEVELS}, (dataset, decoder, kind, xs)
            pairs = [s for s in sessions if (s.dataset, s.decoder) == (dataset, decoder)]
            assert pairs, (dataset, decoder)
            with_level = Counter(s.quality_level for s in pairs if s.quality_level is not None)
            quality = {
                p.x: p for p in curve if (p.dataset, p.decoder, p.axis) == (dataset, decoder, "quality")
            }
            assert {x: p.n_sessions for x, p in quality.items()} == dict(with_level), (dataset, decoder)
            without = sum(1 for s in pairs if s.quality_level is None)
            assert all(p.n_without_level == without for p in quality.values()), (dataset, decoder)


def test_sessions_cover_every_dataset_condition_and_decoder(method: dict) -> None:
    sessions = records.read_sessions(RESULTS / paths.SESSIONS_FILE)
    found = {(s.dataset, s.condition, s.decoder) for s in sessions}
    expected = {(d, c.id, k) for d in DATASETS for c in CONDITIONS for k in DECODERS}
    assert found == expected, sorted(expected - found)[:5]


def test_quality_summary_matches_sessions(method: dict) -> None:
    """quality_summary.csv counts the same session levels as sessions.csv (per decoder, each session once)."""
    with (RESULTS / report.QUALITY_SUMMARY_FILE).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert list(rows[0]) == list(report.QUALITY_SUMMARY_COLUMNS)
    assert len(rows) == len(DATASETS) * len(CONDITIONS)
    sessions = records.read_sessions(RESULTS / paths.SESSIONS_FILE)
    for row in rows:
        for decoder in DECODERS:
            levels = Counter(
                s.quality_level
                for s in sessions
                if (s.dataset, s.condition, s.decoder) == (row["dataset"], row["condition"], decoder)
            )
            for level in LEVELS:
                assert levels.get(level, 0) == int(row[f"sessions_q{level}"]), (
                    row["dataset"],
                    row["condition"],
                )
            assert levels.get(None, 0) == int(row["sessions_without_level"]), (
                row["dataset"],
                row["condition"],
            )


def test_reports_are_rendered_from_exactly_these_results(method: dict) -> None:
    """A-107: report/en and report/zh are what render writes from the committed results/ (no hand edit, every
    number from results/)."""
    data = report.load_results(RESULTS)
    for language, path in REPORTS.items():
        expected = report.report_text(data, language, report.figure_links(RESULTS, path.parent))
        assert path.read_bytes() == expected.encode("utf-8"), (
            f"{language}: render again (python -m neuroarena.report render)"
        )


def test_published_files_hold_no_paths_names_or_forbidden_words(method: dict) -> None:
    """A-57 on both reports; no absolute path, user or host name in any committed result or report."""
    names = _wording.private_names(paths.REPO, paths.PROJECT)
    for path in [*(RESULTS / name for name in report.PUBLISHED), *REPORTS.values()]:
        data = path.read_bytes()
        assert not _wording.private_hits(data, names), path.name
        if path.suffix in (".csv", ".json", ".md", ".svg"):
            assert b"\r\n" not in data and not data.startswith(b"\xef\xbb\xbf"), path.name
    for language, path in REPORTS.items():
        text = path.read_text(encoding="utf-8")
        assert not _wording.hits(text), (language, _wording.hits(text))
        for spec in DATASETS.values():
            for value in (spec.citation, spec.paper_doi, spec.source, spec.licence):
                assert value in text, (language, spec.name, value)
