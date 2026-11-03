"""Smoke runs of area C (F11 B, marker smoke): the runner in mode smoke with both decoders (EEGNet with
SMOKE_EEGNET_EPOCHS), run twice, compared exactly (DoD 1 in small). No download."""

from __future__ import annotations

from pathlib import Path

import pytest

from _smoke import SMOKE_CONFIG, SmokeRuns
from neuroarena import compare, paths, records, runner
from neuroarena.runner import RunConfig


@pytest.mark.smoke
def test_runner_twice_identical_in_process(tmp_path: Path, area_b: None, inline_pool: list) -> None:
    """The runner's whole decoder path with MOABB's real paradigms and both real decoders; area B's functions
    and the worker pool are the doubles of conftest.py (this test does not need area B)."""
    config = RunConfig(
        run_id="s1",
        mode="smoke",
        datasets=("Zhou2016", "Kalunga2016"),
        conditions=("clean",),
        subjects={"Zhou2016": (1,), "Kalunga2016": (2,)},
    )
    first = runner.run(config, runs=tmp_path / "runs", work=tmp_path / "work")
    second = runner.run(
        RunConfig(**{**config.__dict__, "run_id": "s2"}), tmp_path / "runs", tmp_path / "work"
    )
    comparison = compare.compare_runs(first, second)
    assert comparison.exact and comparison.ok, comparison.differences[:5]
    assert comparison.compared == {"quality": 2, "neurogrid": 2 * 2, "fold": 2 * 2 * 2 * 5}
    sessions = records.read_sessions(first / paths.SESSIONS_FILE)
    assert {(s.dataset, s.decoder, s.subject) for s in sessions} == {
        (dataset, decoder, subject)
        for dataset, subject in (("Zhou2016", 1), ("Kalunga2016", 2))
        for decoder in ("csp_lda", "eegnet")
    }
    assert {s.chance for s in sessions if s.dataset == "Kalunga2016"} == {0.25}
    curve = records.read_curve(first / paths.CURVE_FILE)
    assert {(p.dataset, p.decoder) for p in curve if p.axis == "quality"} == {
        (d, k) for d in ("Zhou2016", "Kalunga2016") for k in ("csp_lda", "eegnet")
    }
    eegnet = records.read_folds(paths.folds_file("s1", "Kalunga2016", "clean", "eegnet", tmp_path / "runs"))
    assert len(eegnet) == 10 and all(row.n_train + row.n_test == 40 for row in eegnet)


@pytest.mark.smoke
def test_smoke_run_with_area_b_twice_identical(tmp_path: Path, smoke_runs: SmokeRuns) -> None:
    """End to end with area B's real functions (synthetic.fake_dataset, datasets.degraded_dataset,
    quality.assess with NeuroGrid's command line): two spawned workers, both decoders, two conditions, run
    twice and compared exactly (quality.json, NeuroGrid's metrics, every fold). Needs area B. The two runs are
    conftest's ``smoke_runs`` (SMOKE_CONFIG), shared with the smoke tests of area D."""
    assert SMOKE_CONFIG.processes == 2 and SMOKE_CONFIG.conditions == ("clean", "line_noise-5")
    first, second, work = smoke_runs.first, smoke_runs.second, smoke_runs.work
    comparison = compare.compare_runs(first, second)
    assert comparison.exact and comparison.ok, comparison.differences[:5]
    assert comparison.compared["quality"] == 4 and comparison.compared["neurogrid"] > 0
    assert comparison.compared["fold"] > 0
    for folder in (first, second):
        assert (folder / paths.SESSIONS_FILE).is_file() and (folder / paths.CURVE_FILE).is_file()
    assert not (work / "smoke-a").exists() and not (work / "smoke-b").exists()
    assert compare.main([str(first), str(second), "--out", str(tmp_path / paths.RUN_COMPARE_FILE)]) == 0
