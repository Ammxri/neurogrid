"""DoD 1: two runs compared with the documented tolerance (F3, A-106)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from neuroarena import compare, paths, records, runner
from neuroarena.compare import EegnetTolerance
from neuroarena.records import FoldRecord

CONFIG = runner.RunConfig(
    run_id="a", mode="smoke", datasets=("Zhou2016",), conditions=("clean",), decoders=("csp_lda", "eegnet")
)
SUBJECTS = {"Zhou2016": (1,)}


def fold(decoder: str, session: str, index: int, n_correct: int, n_test: int = 10) -> FoldRecord:
    return FoldRecord(
        dataset="Zhou2016",
        condition="clean",
        kind="clean",
        level=0,
        subject=1,
        session=session,
        decoder=decoder,
        fold=index,
        seed=1000 + index,
        n_train=4 * n_test,
        n_test=n_test,
        n_correct=n_correct,
        accuracy=n_correct / n_test,
        fit_seconds=1.0,
    )


def make_run(base: Path, run_id: str, eegnet_correct: dict[tuple[str, int], int] | None = None) -> Path:
    """A complete run folder of CONFIG: run.json, quality.json, results.json and both folds files."""
    folder = base / run_id
    document = runner._document(dataclasses.replace(CONFIG, run_id=run_id), SUBJECTS)
    document["attempts"] = [{"started": run_id, "finished": run_id}]  # times differ between runs
    document["machine"] = {"system": run_id}
    runner._write_json(folder / paths.RUN_FILE, document)
    neurogrid = folder / "neurogrid" / "Zhou2016" / "clean"
    quality = {"version": 1, "sessions": [{"subject": 1, "session": "0", "level": 2}]}
    runner._write_json(neurogrid / paths.QUALITY_FILE, quality)
    results = {
        "environment": {"host": run_id},
        "config": {"as_of": run_id},
        "recordings": [
            {
                "id": "sub-001_ses-0_run-0_eeg.fif",
                "format": "fif",
                "duration_s": float(len(run_id)),
                "metrics": {
                    "M06": {"value": 0.125, "state": "ok"},
                    "M07": {"channels": [{"ratio": float("nan")}]},
                },
            },
        ],
    }
    runner._write_json(neurogrid / paths.RESULTS_FILE, results)
    eegnet_correct = eegnet_correct or {}
    for decoder in ("csp_lda", "eegnet"):
        rows = []
        for session in ("0", "1"):
            for index in range(5):
                correct = 7 if decoder == "csp_lda" else eegnet_correct.get((session, index), 6)
                rows.append(fold(decoder, session, index, correct))
        records.write_csv(rows, paths.folds_file(run_id, "Zhou2016", "clean", decoder, base))
    return folder


def test_equal_runs_are_exactly_equal(tmp_path: Path) -> None:
    a, b = make_run(tmp_path, "run1"), make_run(tmp_path, "run2")
    comparison = compare.compare_runs(a, b)
    assert comparison.ok and comparison.exact and comparison.differences == ()
    assert comparison.compared == {"quality": 1, "neurogrid": 1, "fold": 20}
    assert compare.main([str(a), str(b)]) == 0


def test_any_difference_is_found_exactly(tmp_path: Path) -> None:
    a = make_run(tmp_path, "run1")
    b = make_run(tmp_path, "run2", {("1", 3): 7})
    quality = b / "neurogrid" / "Zhou2016" / "clean" / paths.QUALITY_FILE
    runner._write_json(quality, {"version": 1, "sessions": [{"subject": 1, "session": "0", "level": 3}]})
    results = b / "neurogrid" / "Zhou2016" / "clean" / paths.RESULTS_FILE
    document = json.loads(results.read_text(encoding="utf-8"))
    document["recordings"][0]["metrics"]["M06"]["value"] = 0.25
    runner._write_json(results, document)
    comparison = compare.compare_runs(a, b)
    assert not comparison.ok and not comparison.exact
    assert [(d.what, d.where, d.a, d.b) for d in comparison.differences] == [
        ("fold", "folds/Zhou2016/clean/eegnet.csv subject=1 session=1 fold=3 field=accuracy", "0.6", "0.7"),
        ("fold", "folds/Zhou2016/clean/eegnet.csv subject=1 session=1 fold=3 field=n_correct", "6", "7"),
        (
            "neurogrid",
            "neurogrid/Zhou2016/clean/results.json recording=sub-001_ses-0_run-0_eeg.fif $.M06.value",
            "0.125",
            "0.25",
        ),
        ("quality", "neurogrid/Zhou2016/clean/quality.json $.sessions[0].level", "2", "3"),
    ]
    assert compare.main([str(a), str(b)]) == 1


def test_eegnet_tolerance_within_and_beyond(tmp_path: Path) -> None:
    """F3: at most 1 test trial per fold and 0.5 percentage points in the mean of a cell; CSP+LDA exact."""
    a = make_run(tmp_path, "run1")
    # 1 trial in one fold of 10 folds over 2 sessions: the cell mean moves by 0.1 / 5 / 2 = 1 point.
    beyond_cell = compare.compare_runs(a, make_run(tmp_path, "run2", {("0", 1): 7}), EegnetTolerance())
    assert not beyond_cell.ok and [d.what for d in beyond_cell.differences] == ["cell", "fold", "fold"]
    assert all("(within tolerance)" in d.where for d in beyond_cell.differences if d.what == "fold")
    # +1 and -1 in two folds of the same session: every fold within 1 trial, the cell mean unchanged.
    within = compare.compare_runs(
        a, make_run(tmp_path, "run3", {("0", 1): 7, ("0", 2): 5}), EegnetTolerance()
    )
    assert within.ok and not within.exact and within.compared["cell"] == 1
    assert compare.compare_runs(a, make_run(tmp_path, "run3b", {("0", 1): 7, ("0", 2): 5})).ok is False
    # 2 trials in one fold: beyond the fold tolerance whatever the mean.
    beyond_fold = compare.compare_runs(
        a, make_run(tmp_path, "run4", {("0", 1): 8, ("0", 2): 4}), EegnetTolerance()
    )
    assert not beyond_fold.ok
    assert any(d.what == "fold" and "(within tolerance)" not in d.where for d in beyond_fold.differences)
    assert compare.main([str(a), str(tmp_path / "run3"), "--eegnet-tolerance"]) == 0
    # CSP+LDA never gets the tolerance.
    csp = make_run(tmp_path, "run5")
    path = paths.folds_file("run5", "Zhou2016", "clean", "csp_lda", tmp_path)
    rows = records.read_folds(path)
    rows[0] = dataclasses.replace(rows[0], n_correct=6, accuracy=0.6)
    records.write_csv(rows, path)
    assert not compare.compare_runs(a, csp, EegnetTolerance()).ok


def test_times_and_run_specific_blocks_are_never_compared(tmp_path: Path) -> None:
    a = make_run(tmp_path, "run1")
    b = make_run(tmp_path, "run22")  # other run id, times, machine, environment, as_of and duration_s
    path = paths.folds_file("run22", "Zhou2016", "clean", "eegnet", tmp_path)
    records.write_csv([dataclasses.replace(r, fit_seconds=9.5) for r in records.read_folds(path)], path)
    assert compare.compare_runs(a, b).exact


def test_a_missing_file_is_reported_and_exits_2(tmp_path: Path) -> None:
    a, b = make_run(tmp_path, "run1"), make_run(tmp_path, "run2")
    paths.folds_file("run2", "Zhou2016", "clean", "eegnet", tmp_path).unlink()
    comparison = compare.compare_runs(a, b)
    assert not comparison.ok
    assert comparison.differences == (
        compare.Difference("missing", "folds/Zhou2016/clean/eegnet.csv", "present", "missing"),
    )
    assert compare.main([str(a), str(b)]) == 2
    (b / paths.RUN_FILE).unlink()
    with pytest.raises(ValueError, match="run.json"):
        compare.compare_runs(a, b)
    assert compare.main([str(a), str(b)]) == 2


def test_another_configuration_cannot_be_compared(tmp_path: Path) -> None:
    a, b = make_run(tmp_path, "run1"), make_run(tmp_path, "run2")
    document = json.loads((b / paths.RUN_FILE).read_text(encoding="utf-8"))
    document["config"]["conditions"] = ["clean", "channels-1"]
    runner._write_json(b / paths.RUN_FILE, document)
    with pytest.raises(ValueError, match="configurations"):
        compare.compare_runs(a, b)
    assert compare.main([str(a), str(b)]) == 2
    assert compare.main(["--unknown"]) == 2


def test_written_comparison_has_no_paths_or_machine_names(tmp_path: Path) -> None:
    a = make_run(tmp_path, "run1")
    b = make_run(tmp_path, "run2", {("1", 0): 5})
    out = tmp_path / "results" / paths.RUN_COMPARE_FILE
    assert compare.main([str(a), str(b), "--eegnet-tolerance", "--out", str(out)]) == 1
    data = out.read_bytes()
    assert b"\r" not in data and data.endswith(b"}\n")
    document = json.loads(data)
    assert document["ok"] is False and document["exact"] is False
    assert document["tolerance"] == {"max_trials_per_fold": 1, "max_mean_points_per_cell": 0.5}
    assert document["compared"] == {"cell": 1, "fold": 20, "neurogrid": 1, "quality": 1}
    text = data.decode("utf-8")
    assert str(tmp_path) not in text and str(tmp_path).replace("\\", "/") not in text
    assert "run1" not in text and "run2" not in text
    assert list(document) == sorted(document)
