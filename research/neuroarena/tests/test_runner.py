"""The runner's own logic (area C): unit order, resumability, atomic units, run.json, configuration check, the
aggregated CSV files, curve rows and exit codes. Area B's functions and the worker pool are test doubles
(conftest.py); the spawned pool is tested on its own."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import pytest

from neuroarena import determinism, evaluation, paths, records, runner
from neuroarena.keys import Condition
from neuroarena.records import SessionRecord
from neuroarena.runner import RunConfig, Unit

CONFIG = RunConfig(
    run_id="r1",
    mode="smoke",
    datasets=("Zhou2016", "Kalunga2016"),
    conditions=("clean", "line_noise-5"),
)


def fake_evaluate(
    dataset: Any, spec: Any, condition: Condition, decoder: str, subject: int, mode: str
) -> dict[str, Any]:
    """A fast decoder unit: two sessions, five folds of 8 test trials, deterministic accuracies."""
    folds, sessions = [], []
    for session in ("0", "1"):
        sessions.append({"session": session, "n_trials": 40, "chance": 0.25, "labels": {"a": 20, "b": 20}})
        for fold in range(5):
            correct = (subject + fold + len(decoder) + condition.level) % 9
            folds.append(
                {
                    "dataset": spec.name,
                    "condition": condition.id,
                    "kind": condition.kind,
                    "level": condition.level,
                    "subject": subject,
                    "session": session,
                    "decoder": decoder,
                    "fold": fold,
                    "seed": determinism.derive_seed(spec.name, subject, session, fold),
                    "n_train": 32,
                    "n_test": 8,
                    "n_correct": correct,
                    "accuracy": correct / 8,
                    "fit_seconds": 0.01,
                }
            )
    return {"sessions": sessions, "folds": folds}


@pytest.fixture
def fast(monkeypatch: pytest.MonkeyPatch, area_b: None, inline_pool: list) -> list:
    calls: list[tuple[str, str, str, int]] = []

    def evaluate(dataset: Any, spec: Any, condition: Condition, decoder: str, subject: int, mode: str) -> Any:
        calls.append((spec.name, condition.id, decoder, subject))
        return fake_evaluate(dataset, spec, condition, decoder, subject, mode)

    monkeypatch.setattr(runner, "evaluate_subject", evaluate)
    return calls


def test_units_are_planned_in_order() -> None:
    units = runner.plan(CONFIG, {"Zhou2016": (1, 2), "Kalunga2016": (3,)})
    assert [u.id for u in units[:6]] == [
        "quality Zhou2016 clean",
        "csp_lda Zhou2016 clean subject 1",
        "csp_lda Zhou2016 clean subject 2",
        "eegnet Zhou2016 clean subject 1",
        "eegnet Zhou2016 clean subject 2",
        "quality Zhou2016 line_noise-5",
    ]
    assert len(units) == 2 * 5 + 2 * 3
    assert units[-1] == Unit("Kalunga2016", "line_noise-5", "eegnet", 3)
    assert Unit("Zhou2016", "clean").file(Path("r")) == Path("r/units/Zhou2016/clean/quality.json")
    assert Unit("Zhou2016", "clean", "eegnet", 2).file(Path("r")) == Path(
        "r/units/Zhou2016/clean/eegnet/2.json"
    )


def test_run_writes_run_json_folds_sessions_and_curve(tmp_path: Path, fast: list, inline_pool: list) -> None:
    folder = runner.run(CONFIG, runs=tmp_path / "runs", work=tmp_path / "work")
    assert folder == tmp_path / "runs" / "r1"
    assert [u.id for u in inline_pool[0].submitted] == [
        u.id for u in runner.plan(CONFIG, runner._subjects(CONFIG))
    ]
    document = json.loads((folder / paths.RUN_FILE).read_text(encoding="utf-8"))
    assert document["config"] == {
        "run_id": "r1",
        "mode": "smoke",
        "datasets": ["Zhou2016", "Kalunga2016"],
        "conditions": ["clean", "line_noise-5"],
        "decoders": ["csp_lda", "eegnet"],
        "subjects": None,
        "processes": 1,
        "neurogrid_jobs": 1,
    }
    assert document["subjects"] == {"Zhou2016": [1, 2], "Kalunga2016": [1, 2]}
    assert document["base_seed"] == determinism.BASE_SEED
    assert set(document["locks"]) == {"research/neuroarena/uv.lock", "uv.lock"}
    assert all(len(value) == 64 for value in document["locks"].values())
    assert document["versions"]["torch"].startswith("2.15.0") and document["versions"]["moabb"] == "1.7.2"
    assert document["decoders"]["eegnet_epochs_in_this_mode"] == runner.SMOKE_EEGNET_EPOCHS
    assert document["decoders"]["eegnet_patience"] == 50 and document["decoders"]["csp_filters"] == 6
    [attempt] = document["attempts"]
    assert attempt["units"] == attempt["pending"] == 20 and attempt["failed"] == [] and attempt["finished"]
    assert "node" not in json.dumps(document["machine"])
    # Area B's files per dataset and condition, C's folds per cell, the work folder removed (F1).
    for dataset in CONFIG.datasets:
        for condition in CONFIG.conditions:
            assert (
                paths.neurogrid_dir("r1", dataset, condition, tmp_path / "runs") / "quality.json"
            ).is_file()
            for decoder in ("csp_lda", "eegnet"):
                rows = records.read_folds(
                    paths.folds_file("r1", dataset, condition, decoder, tmp_path / "runs")
                )
                assert len(rows) == 2 * 2 * 5 and {r.decoder for r in rows} == {decoder}
    assert not (tmp_path / "work" / "r1").exists()
    sessions = records.read_sessions(folder / paths.SESSIONS_FILE)
    assert len(sessions) == 2 * 2 * 2 * 2 * 2
    row = next(
        s
        for s in sessions
        if (s.dataset, s.condition, s.subject, s.session, s.decoder)
        == ("Kalunga2016", "line_noise-5", 2, "1", "eegnet")
    )
    assert row.paradigm == "ssvep" and row.kind == "line_noise" and row.level == 5
    assert row.quality_level is None and row.runs_without_level == 1 and row.chance == 0.25
    expected = sum((2 + f + 6 + 5) % 9 for f in range(5)) / 40
    assert row.n_trials == 40 and row.accuracy == expected
    curve = records.read_curve(folder / paths.CURVE_FILE)
    assert curve == records.read_curve(records.write_csv(runner.curve_points(sessions), tmp_path / "c.csv"))


def test_rerun_skips_finished_units_and_redoes_missing_ones(tmp_path: Path, fast: list) -> None:
    runs, work = tmp_path / "runs", tmp_path / "work"
    folder = runner.run(CONFIG, runs=runs, work=work)
    first = (folder / paths.CURVE_FILE).read_bytes()
    assert len(fast) == 16
    fast.clear()
    runner.run(CONFIG, runs=runs, work=work)
    assert fast == []
    Unit("Kalunga2016", "clean", "eegnet", 2).file(folder).unlink()
    Unit("Zhou2016", "line_noise-5").file(folder).unlink()
    paths.folds_file("r1", "Kalunga2016", "clean", "eegnet", runs).unlink()
    runner.run(CONFIG, runs=runs, work=work)
    assert fast == [("Kalunga2016", "clean", "eegnet", 2)]
    assert (folder / paths.CURVE_FILE).read_bytes() == first
    assert paths.folds_file("r1", "Kalunga2016", "clean", "eegnet", runs).is_file()
    document = json.loads((folder / paths.RUN_FILE).read_text(encoding="utf-8"))
    assert [a["pending"] for a in document["attempts"]] == [20, 0, 2]


def test_a_failed_unit_keeps_the_others_and_is_rerun(
    tmp_path: Path, fast: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs, work = tmp_path / "runs", tmp_path / "work"
    good = runner.evaluate_subject

    def flaky(dataset: Any, spec: Any, condition: Condition, decoder: str, subject: int, mode: str) -> Any:
        if (spec.name, condition.id, decoder, subject) == ("Zhou2016", "clean", "csp_lda", 2):
            raise ValueError("every class needs at least 5 trials")
        return good(dataset, spec, condition, decoder, subject, mode)

    monkeypatch.setattr(runner, "evaluate_subject", flaky)
    with pytest.raises(runner.UnitError, match="csp_lda Zhou2016 clean subject 2"):
        runner.run(CONFIG, runs=runs, work=work)
    folder = runs / "r1"
    assert not Unit("Zhou2016", "clean", "csp_lda", 2).file(folder).exists()
    assert Unit("Zhou2016", "clean", "csp_lda", 1).file(folder).is_file()
    assert not paths.folds_file("r1", "Zhou2016", "clean", "csp_lda", runs).exists()
    assert paths.folds_file("r1", "Zhou2016", "clean", "eegnet", runs).is_file()
    assert not (folder / paths.SESSIONS_FILE).exists() and not (folder / paths.CURVE_FILE).exists()
    attempt = json.loads((folder / paths.RUN_FILE).read_text(encoding="utf-8"))["attempts"][-1]
    assert attempt["failed"] == [
        {
            "unit": "csp_lda Zhou2016 clean subject 2",
            "error": "ValueError: every class needs at least 5 trials",
        }
    ]
    monkeypatch.setattr(runner, "evaluate_subject", good)
    fast.clear()
    runner.run(CONFIG, runs=runs, work=work)
    assert fast == [("Zhou2016", "clean", "csp_lda", 2)]
    assert (folder / paths.CURVE_FILE).is_file()


def test_an_interrupted_unit_file_is_not_a_finished_unit(tmp_path: Path, fast: list) -> None:
    runs = tmp_path / "runs"
    folder = runner.run(CONFIG, runs=runs, work=tmp_path / "work")
    Unit("Zhou2016", "clean", "eegnet", 1).file(folder).write_text(
        '{"version": 1, "folds": [', encoding="utf-8"
    )
    quality = paths.neurogrid_dir("r1", "Kalunga2016", "clean", runs) / paths.QUALITY_FILE
    quality.unlink()  # area B's file gone although the marker exists: the quality step runs again
    # An interrupted NeuroGrid step leaves FIF files behind; assess refuses a non-empty work folder.
    stale = paths.work_dir("r1", "Kalunga2016", "clean", tmp_path / "work")
    stale.mkdir(parents=True)
    (stale / "sub-001_ses-0_run-0_eeg.fif").write_bytes(b"partial")
    (quality.parent / "results.json").write_text("{", encoding="utf-8")
    fast.clear()
    runner.run(CONFIG, runs=runs, work=tmp_path / "work")
    assert fast == [("Zhou2016", "clean", "eegnet", 1)]
    assert quality.is_file() and json.loads((quality.parent / "results.json").read_text(encoding="utf-8"))
    assert not list(folder.rglob("*.tmp")) and not (tmp_path / "work" / "r1").exists()


def test_storage_is_configured_in_every_process_outside_the_smoke_mode(
    tmp_path: Path, fast: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B's note: configure_storage (MNE_DATA, MOABB folders, upstream download provider) in the main process
    and in every worker before a real loader; not needed for the synthetic stand-ins."""
    calls = []
    monkeypatch.setattr(runner.datasets, "configure_storage", lambda *args: calls.append(args))
    config = RunConfig("c1", mode="full", datasets=("Kalunga2016",), conditions=("clean",))
    runner.run(config, runs=tmp_path / "runs", work=tmp_path / "work")
    assert len(calls) == 1 + 5  # the main process, then each of the 5 units (1 quality, 2 x 2 decoder)
    calls.clear()
    smoke = RunConfig("c2", mode="smoke", datasets=("Kalunga2016",), conditions=("clean",))
    runner.run(smoke, runs=tmp_path / "runs", work=tmp_path / "work")
    assert calls == []


def test_another_configuration_is_refused(tmp_path: Path, fast: list) -> None:
    runs, work = tmp_path / "runs", tmp_path / "work"
    runner.run(CONFIG, runs=runs, work=work)
    with pytest.raises(ValueError, match="another configuration"):
        runner.run(RunConfig("r1", mode="smoke", datasets=("Zhou2016",), conditions=("clean",)), runs, work)
    with pytest.raises(ValueError, match="another configuration"):
        runner.run(
            RunConfig("r1", mode="pilot", datasets=CONFIG.datasets, conditions=CONFIG.conditions), runs, work
        )
    # The number of processes and NeuroGrid jobs change the wall time only.
    runner.run(RunConfig(**{**CONFIG.__dict__, "processes": 3, "neurogrid_jobs": 2}), runs, work)
    with pytest.raises(ValueError, match="unknown condition"):
        runner.run(RunConfig("r2", mode="smoke", conditions=("hum-1",)), runs, work)
    with pytest.raises(ValueError, match="once each"):
        runner.run(RunConfig("r2", mode="smoke", datasets=("Zhou2016", "Zhou2016")), runs, work)
    with pytest.raises(ValueError, match="run id"):
        runner.run(RunConfig("../r2", mode="smoke"), runs, work)


def session_row(
    condition: str, subject: int, accuracy: float, level: int | None, decoder: str = "csp_lda"
) -> SessionRecord:
    c = Condition.from_id(condition)
    return SessionRecord(
        "Zhou2016",
        "imagery",
        condition,
        c.kind,
        c.level,
        subject,
        "0",
        decoder,
        40,
        accuracy,
        1 / 3,
        level,
        0 if level else 1,
    )


def test_curve_points_on_both_axes() -> None:
    """F5f: quality axis over all conditions (pairs without a level counted), degradation axis per kind with
    the clean pairs at x = 0; a level without pairs has no row (DoD 2)."""
    rows = [
        session_row("clean", 1, 0.9, 1),
        session_row("clean", 2, 0.7, 2),
        session_row("channels-1", 1, 0.6, 5),
        session_row("channels-1", 2, 0.5, 5),
        session_row("line_noise-3", 1, 0.8, None),
    ]
    points = {(p.axis, p.kind, p.x): p for p in runner.curve_points(rows)}
    assert set(points) == {
        ("quality", "all", 1),
        ("quality", "all", 2),
        ("quality", "all", 5),
        *(("degradation", kind, 0) for kind in ("line_noise", "channels", "artifacts")),
        ("degradation", "channels", 1),
        ("degradation", "line_noise", 3),
    }
    q5 = points[("quality", "all", 5)]
    assert (q5.n_sessions, q5.n_without_level, q5.mean_chance) == (2, 1, 1 / 3)
    assert q5.mean_accuracy == math.fsum([0.6, 0.5]) / 2
    seed = determinism.derive_seed("curve", "Zhou2016", "csp_lda", "quality", "all", 5)
    assert (q5.ci_low, q5.ci_high) == evaluation.bootstrap_ci([0.6, 0.5], seed)
    assert math.isnan(points[("quality", "all", 1)].ci_low)
    clean = points[("degradation", "artifacts", 0)]
    assert (clean.n_sessions, clean.n_without_level) == (2, 0)
    assert clean.mean_accuracy == math.fsum([0.9, 0.7]) / 2
    assert points[("degradation", "line_noise", 3)].n_sessions == 1
    assert {p.decoder for p in runner.curve_points([*rows, session_row("clean", 1, 0.5, 1, "eegnet")])} == {
        "csp_lda",
        "eegnet",
    }


def test_main_exit_codes(tmp_path: Path, fast: list, monkeypatch: pytest.MonkeyPatch) -> None:
    original = runner.run
    monkeypatch.setattr(runner, "run", lambda config: original(config, tmp_path / "runs", tmp_path / "work"))
    arguments = ["--run-id", "m1", "--mode", "smoke", "--datasets", "Kalunga2016", "--conditions", "clean"]
    assert runner.main(arguments) == 0
    assert (
        runner.main(["--run-id", "m1", "--mode", "smoke", "--datasets", "Kalunga2016"]) == 2
    )  # other config
    assert runner.main(["--mode", "smoke"]) == 2  # no run id
    assert runner.main([*arguments[:-1], "hum-1"]) == 2
    assert runner.main([*arguments, "--processes", "0"]) == 2

    def broken(*args: Any) -> Any:
        raise ValueError("every class needs at least 5 trials")

    monkeypatch.setattr(runner, "evaluate_subject", broken)
    assert (
        runner.main(
            ["--run-id", "m2", "--mode", "smoke", "--datasets", "Kalunga2016", "--conditions", "clean"]
        )
        == 1
    )


def test_pilot_defaults_to_clean_and_repeats_eegnet(
    tmp_path: Path, fast: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A-109: the pilot measures the clean condition and fits EEGNet twice on one subject."""
    original = runner.run
    seen: list[RunConfig] = []

    def spy(config: RunConfig) -> Path:
        seen.append(config)
        return original(config, tmp_path / "runs", tmp_path / "work")

    monkeypatch.setattr(runner, "run", spy)
    assert runner.main(["--run-id", "p1", "--mode", "pilot", "--datasets", "Zhou2016"]) == 0
    assert seen[0].conditions == ("clean",)
    document = json.loads((tmp_path / "runs" / "p1" / paths.RUN_FILE).read_text(encoding="utf-8"))
    assert document["pilot"] == {
        "eegnet_repeat": [
            {
                "dataset": "Zhou2016",
                "condition": "clean",
                "subject": 1,
                "folds": 10,
                "identical": True,
                "max_trial_difference": 0,
            }
        ]
    }
    assert fast[-1] == ("Zhou2016", "clean", "eegnet", 1) and len(fast) == 5


def test_the_spawned_pool_starts_workers_with_the_worker_environment() -> None:
    """A-106: workers start (spawn) with WORKER_ENVIRONMENT, set before their interpreter starts; the
    environment of this process is left as it was."""
    before = {name: os.environ.get(name) for name in determinism.WORKER_ENVIRONMENT}
    with runner._pool(2) as executor:
        pids = {executor.submit(runner._worker_ready).result() for _ in range(6)}
        assert executor.submit(determinism.check_environment).result() is None
        assert executor.submit(determinism.derive_seed, "x").result() == determinism.derive_seed("x")
    assert os.getpid() not in pids and 1 <= len(pids) <= 2
    assert {name: os.environ.get(name) for name in determinism.WORKER_ENVIRONMENT} == before
