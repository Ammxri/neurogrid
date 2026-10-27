"""Findings of the P3 review, each with the case that showed it (A-60, A-75, A-79, NG-N03).

- compute() never raises: an unreadable source or a damaged block is read.failed; a failing sample
  preparation leaves the streaming values in place.
- A worker that really dies (not a simulated future) costs only its own recording.
- The pool never asks for more workers than the platform allows (Windows: 61).
- Positions from electrodes.tsv (sidecar) and from the file (header) are used end to end.
- Repeated channel labels are kept apart; non-finite or absurd values and an infinite line frequency never
  give exit 2; a seed beyond 2^32 still gives sample values.
- CORE-M07-02 when the other line band lies above the Nyquist frequency.
- The report renders a sample block of another shape.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))  # the helpers of test_quality_pipeline, also when run alone

from test_quality_pipeline import (  # type: ignore[import-not-found,unused-ignore]  # noqa: E402
    CAP_8,
    CAP_19,
    PoolLog,
    check_args,
    cli,
    eeg_like,
    fake_pool,
    load,
    outcomes,
    write_edf,
)

from conftest import documented_config  # type: ignore[import-not-found,unused-ignore]  # noqa: E402
from neurogrid import quality  # noqa: E402
from neurogrid.io.edf import EdfAdapter  # noqa: E402
from neurogrid.kernel import processes  # noqa: E402
from neurogrid.quality import QualityJob, QualitySettings  # noqa: E402
from neurogrid.quality import sample as sample_module  # noqa: E402
from neurogrid.quality import source as source_module  # noqa: E402

RATE = 250


def _job(path: Path, **settings: Any) -> QualityJob:
    recording = EdfAdapter().read(path, recording_id=path.name, relative_path=path.name)
    return QualityJob(path=str(path), recording=recording, settings=QualitySettings(**settings))


def _head_positions(names: tuple[str, ...]) -> dict[str, tuple[float, float, float]]:
    import mne

    montage = mne.channels.transform_to_head(mne.channels.make_standard_montage("colin27_1005"))
    positions = montage.get_positions()["ch_pos"]
    return {name: tuple(float(v) for v in positions[name]) for name in names}  # type: ignore[misc]


@pytest.fixture(scope="module")
def cap19(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A sample-capable EDF: 19 standard channels, 250 Hz, 64 s."""
    folder = tmp_path_factory.mktemp("cap19")
    return write_edf(folder / "rec.edf", CAP_19, eeg_like(CAP_19, 64, RATE, 31), RATE)


@pytest.fixture(scope="module")
def cap19_result(cap19: Path) -> quality.QualityResult:
    return quality.compute(_job(cap19))


# --- compute() never raises ---------------------------------------------------------------------------------


def test_an_unreadable_source_is_read_failed(cap19: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: object) -> None:
        raise OSError("device gone")

    monkeypatch.setattr(source_module, "open_signals", broken)
    result = quality.compute(_job(cap19))
    assert (result.reason, result.error_type, result.stream, result.sample) == (
        "read.failed",
        "OSError",
        None,
        None,
    )
    assert quality.describe(result) == {"state": "not_checkable", "reason": "read.failed"}


def test_a_damaged_block_in_the_middle_is_read_failed(cap19: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = source_module.EdfSignals.read_many

    def damaged(self: Any, indices: Any, start: int, stop: int) -> np.ndarray:
        if start > 0:
            raise OSError("bad sector")
        return original(self, indices, start, stop)

    monkeypatch.setattr(source_module.EdfSignals, "read_many", damaged)
    result = quality.compute(_job(cap19))
    assert (result.reason, result.error_type) == ("read.failed", "OSError")


def test_a_failing_sample_preparation_keeps_the_streaming_values(
    cap19: Path, cap19_result: quality.QualityResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object) -> None:
        raise ValueError("montage")

    monkeypatch.setattr(sample_module, "_prepared", broken)
    result = quality.compute(_job(cap19))
    assert result.reason is None and result.stream == cap19_result.stream
    assert result.sample is not None
    failed = sample_module.MethodResult(
        "not_checkable", reason="quality.method_failed", details={"error_type": "ValueError"}
    )
    assert (result.sample.m06, result.sample.m09a, result.sample.m09b) == (failed, failed, failed)


# --- workers ------------------------------------------------------------------------------------------------


class _DiesWhenUnpickled:
    """Unpickling this calls os._exit in the worker, so the process really dies (as an out-of-memory kill)."""

    def __reduce__(self) -> tuple[Any, tuple[int]]:
        return (os._exit, (3,))


def test_a_worker_that_really_dies_costs_only_its_own_recording(tmp_path: Path) -> None:
    paths = [
        write_edf(tmp_path / f"rec_{i}.edf", CAP_8, eeg_like(CAP_8, 12, 256, 40 + i), 256) for i in range(3)
    ]
    jobs = [dataclasses.replace(_job(path), sample=False) for path in paths]
    killer = dataclasses.replace(jobs[1], channel_map={"x": _DiesWhenUnpickled()})  # type: ignore[dict-item]
    results = quality.compute_all([jobs[0], killer, jobs[2]], workers=2)
    assert results[0] == quality.compute(jobs[0]) and results[2] == quality.compute(jobs[2])
    assert (results[1].reason, results[1].error_type) == ("quality.worker_failed", "BrokenProcessPool")


def test_the_pool_never_exceeds_the_platform_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--jobs allows 64, ProcessPoolExecutor on Windows at most 61 workers."""
    log = PoolLog()
    monkeypatch.setattr(quality, "ProcessPoolExecutor", fake_pool({}, log))
    path = write_edf(tmp_path / "rec.edf", CAP_8, eeg_like(CAP_8, 4, 256, 9), 256)
    job = dataclasses.replace(_job(path), sample=False)
    quality.compute_all([job] * 70, workers=64)
    assert log.workers == [quality.MAX_WORKERS]
    assert log.contexts == [processes.pool_context()]  # its processes start on the null device (A-51)
    assert quality.MAX_WORKERS == (61 if sys.platform == "win32" else 64)


# --- montage sources end to end -----------------------------------------------------------------------------


def _bids(root: Path, system: str, units: str, space: str = "CapTrak") -> Path:
    eeg = root / "sub-01" / "eeg"
    write_edf(eeg / "sub-01_task-rest_eeg.edf", CAP_19, eeg_like(CAP_19, 64, RATE, 33), RATE)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "positions", "BIDSVersion": "1.9.0"}), encoding="utf-8"
    )
    rows = ["name\tx\ty\tz"] + [
        f"{n}\t{x:.6f}\t{y:.6f}\t{z:.6f}" for n, (x, y, z) in _head_positions(CAP_19).items()
    ]
    (eeg / f"sub-01_space-{space}_electrodes.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (eeg / f"sub-01_space-{space}_coordsystem.json").write_text(
        json.dumps({"EEGCoordinateSystem": system, "EEGCoordinateUnits": units}), encoding="utf-8"
    )
    return root


@pytest.mark.parametrize(
    ("system", "positions", "unused"),
    [
        ("CapTrak", "sidecar", {}),
        ("Other", "standard_montage", {"sidecar": "frame_unsupported"}),
    ],
)
def test_electrodes_tsv_positions_end_to_end(
    tmp_path: Path, system: str, positions: str, unused: dict[str, str]
) -> None:
    """A-60/A-79: a CapTrak electrodes.tsv is the montage; with "Other" the template is used and the reason
    is reported."""
    root = _bids(tmp_path / "bids", system, "m", space="CapTrak" if system == "CapTrak" else "Other")
    out = tmp_path / "results.json"
    assert cli(check_args(root, out, documented_config(tmp_path))) in (0, 1)
    (rec,) = load(out)["recordings"]
    assert rec["sample"]["positions"] == positions and rec["sample"]["positions_unused"] == unused
    assert all(rec["metrics"][key]["state"] == "measured" for key in ("M06", "M09a", "M09b"))


def test_positions_stored_in_a_fif_file_end_to_end(tmp_path: Path) -> None:
    """A-79: positions in the file (MNE head frame) come before the template."""
    import mne

    raw = mne.io.RawArray(eeg_like(CAP_19, 64, RATE, 34) * 1e-6, mne.create_info(list(CAP_19), RATE, "eeg"))
    raw.set_montage("colin27_1005")
    folder = tmp_path / "dataset"
    folder.mkdir()
    raw.save(folder / "rec_raw.fif", fmt="double", verbose="error")
    out = tmp_path / "results.json"
    assert cli(check_args(folder, out, documented_config(tmp_path))) in (0, 1)
    (rec,) = load(out)["recordings"]
    assert rec["sample"]["positions"] == "header" and rec["sample"]["channels"] == 19


# --- odd data never give exit 2 -----------------------------------------------------------------------------


def test_repeated_labels_are_kept_apart(tmp_path: Path) -> None:
    """Two signals labelled Fp1 are two channels ("Fp1-0", "Fp1-1", as MNE names them). They have no single
    template position, so the sample runs on the 18 other channels and names both."""
    names = (*CAP_19, "Fp1")
    folder = tmp_path / "dataset"
    write_edf(folder / "dup.edf", names, eeg_like(names, 64, RATE, 35), RATE)
    out = tmp_path / "results.json"
    assert cli(check_args(folder, out, documented_config(tmp_path))) in (0, 1)
    (rec,) = load(out)["recordings"]
    assert len(rec["metrics"]["M07"]["channels"]) == 20
    assert {"Fp1-0", "Fp1-1"} <= set(rec["metrics"]["M07"]["channels"])
    assert rec["sample"]["excluded_channels"] == ["Fp1-0", "Fp1-1"] and rec["sample"]["channels"] == 18
    assert rec["metrics"]["M06"]["state"] == "measured"


def test_absurd_values_and_an_infinite_line_frequency_never_give_exit_2(tmp_path: Path) -> None:
    """A-75: a FIF channel near 1e154 µV and line_freq = inf: the run ends with exit 0/1, the channel is not
    judged (unusable samples), the line frequency falls back to 50 Hz."""
    import mne

    data = eeg_like(CAP_19, 64, RATE, 36) * 1e-6
    data[18] *= 1e160
    raw = mne.io.RawArray(data, mne.create_info(list(CAP_19), RATE, "eeg"), verbose="error")
    raw.info["line_freq"] = math.inf
    folder = tmp_path / "dataset"
    folder.mkdir()
    raw.save(folder / "rec_raw.fif", fmt="double", verbose="error")
    out = tmp_path / "results.json"
    assert cli(check_args(folder, out, documented_config(tmp_path))) in (0, 1)
    (rec,) = load(out)["recordings"]
    m07 = rec["metrics"]["M07"]
    assert m07["line_frequency_hz"] == 50.0
    assert m07["channels"]["O2"] == {"state": "not_checkable", "reason": "quality.unusable_samples"}
    assert rec["metrics"]["M08"]["channels"]["O2"]["windows"] == 0


def test_a_seed_beyond_two_to_the_32_still_gives_sample_values(
    cap19: Path, cap19_result: quality.QualityResult
) -> None:
    """A-75 allows seeds up to 2^63 − 1; the libraries get the seed modulo 2^32."""
    result = quality.compute(_job(cap19, seed=2**32 + QualitySettings().seed))
    assert result.sample is not None and cap19_result.sample is not None
    assert result.sample.seed == 2**32 + QualitySettings().seed
    assert (result.sample.m06, result.sample.m09a, result.sample.m09b) == (
        cap19_result.sample.m06,
        cap19_result.sample.m09a,
        cap19_result.sample.m09b,
    )


@pytest.mark.parametrize(
    ("rate", "status", "reason"),
    [
        (110, "not_checkable", "quality.rate_below_other_band"),
        (100, "not_applicable", "quality.rate_below_line_band"),
    ],
)
def test_line_frequency_check_when_a_band_lies_above_nyquist(
    tmp_path: Path, rate: int, status: str, reason: str
) -> None:
    """A-47: at 110 Hz the 50-Hz band is measured but not the 60-Hz band; at 100 Hz neither."""
    folder = tmp_path / "dataset"
    write_edf(folder / "slow.edf", CAP_8, eeg_like(CAP_8, 20, rate, 37), rate)
    out = tmp_path / "results.json"
    assert cli(check_args(folder, out, documented_config(tmp_path), "--show-paths")) in (0, 1)
    (finding,) = outcomes(load(out), "slow.edf")["CORE-M07-02"]
    assert (finding["status"], finding["reason"]) == (status, reason)


# --- report -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        {"band_hz": [1.0]},
        {"positions_unused": ["sidecar"]},
        {"excluded_channels": 3},
        {"segments": "all"},
        None,  # the sample reduced to {"mode": "sample"}
    ],
)
def test_report_renders_a_sample_of_another_shape(
    cap19: Path, tmp_path: Path, change: dict[str, Any] | None
) -> None:
    out = tmp_path / "results.json"
    assert cli(check_args(cap19.parent, out, documented_config(tmp_path))) in (0, 1)
    data = json.loads(out.read_text(encoding="utf-8"))
    sample = data["recordings"][0]["sample"]
    if change is None:
        data["recordings"][0]["sample"] = {"mode": "sample"}
    else:
        sample.update(change)
    out.write_text(json.dumps(data), encoding="utf-8")
    assert cli(["report", str(out), "--lang", "en", "--out", str(tmp_path)]) == 0
    assert "report.en.html" in {p.name for p in tmp_path.iterdir()}


def test_finite_values_replaces_every_non_finite_float() -> None:
    """A-61/A-75: the metric values bypass the rule engine; a non-finite float becomes null, never exit 2."""
    nested = {"a": math.nan, "b": [1.0, math.inf, {"c": -math.inf}], "d": (2, "x"), "e": None}
    assert quality.finite_values(nested) == {
        "a": None,
        "b": [1.0, None, {"c": None}],
        "d": [2, "x"],
        "e": None,
    }


# --- D-14: the parts of one recording in parallel -----------------------------------------------------------


def test_one_recording_with_jobs_4_equals_jobs_1(cap19: Path, cap19_result: quality.QualityResult) -> None:
    """D-14, NG-N03: stream next to the sample, autoreject (over loky processes) next to the ICA: the same
    result as one process, and the pool ends without waiting for idle loky workers (300 s by default)."""
    import time

    started = time.perf_counter()
    (result,) = quality.compute_all([_job(cap19)], workers=4)
    assert result == cap19_result
    assert result.sample is not None and result.sample.m09a.state == "measured"
    assert time.perf_counter() - started < 120


def _loky_state() -> tuple[bool, str]:
    """Runs in a loky worker: is the network guard installed, are library warnings ignored?"""
    import warnings

    from neurogrid.kernel import netguard

    return bool(netguard._state["installed"]), str(warnings.filters[0][0])


def test_loky_workers_start_with_the_network_guard() -> None:
    """A-49, NG-N01: autoreject's loky workers install the network guard, compute with one BLAS thread and
    keep library warnings off the console, like the workers of --jobs."""
    import joblib

    from neurogrid.quality.workers import loky_processes

    with loky_processes():
        states = joblib.Parallel(n_jobs=2)(joblib.delayed(_loky_state)() for _ in range(4))
    assert set(states) == {(True, "ignore")}


@pytest.fixture(scope="module")
def cap19_stage(cap19: Path) -> sample_module.Stage:
    part = quality.sample_part(_job(cap19))
    assert part.reason is None and part.value.good is not None
    return part.value


def _epochs(stage: sample_module.Stage) -> Any:
    import mne

    return mne.make_fixed_length_epochs(stage.good, duration=2.0, preload=True, verbose="error")


def test_autoreject_over_loky_equals_one_process(cap19_stage: sample_module.Stage) -> None:
    """D-14: the threshold search over loky processes gives the same model as in one process."""
    epochs = _epochs(cap19_stage)
    serial = sample_module._fitted_autoreject(epochs, [1, 4], 10, 7, n_jobs=1)
    loky = sample_module._fitted_autoreject(epochs, [1, 4], 10, 7, n_jobs=2)
    assert serial.threshes_ == loky.threshes_
    assert np.array_equal(
        serial.get_reject_log(epochs).labels, loky.get_reject_log(epochs).labels, equal_nan=True
    )


def test_a_dying_loky_worker_makes_autoreject_fit_again_in_process(
    cap19_stage: sample_module.Stage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-14: a loky worker that dies (out of memory) does not change the value: the fit runs again here."""
    import autoreject
    from joblib.externals.loky.process_executor import TerminatedWorkerError

    epochs = _epochs(cap19_stage)
    expected = sample_module._fitted_autoreject(epochs, [1, 4], 10, 7, n_jobs=1)
    original = autoreject.AutoReject.fit
    calls: list[int] = []

    def fit(self: Any, data: Any) -> Any:
        calls.append(self.n_jobs)
        if self.n_jobs > 1:
            raise TerminatedWorkerError(
                "A worker process managed by the executor was unexpectedly terminated."
            )
        return original(self, data)

    monkeypatch.setattr(autoreject.AutoReject, "fit", fit)
    again = sample_module._fitted_autoreject(epochs, [1, 4], 10, 7, n_jobs=3)
    assert calls == [3, 1] and again.threshes_ == expected.threshes_


def test_autoreject_and_ica_never_raise(
    cap19: Path, cap19_result: quality.QualityResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A-60: an error outside the methods' own steps (e.g. MemoryError) gives quality.method_failed for that
    metric; the stream values and M06 remain, the run never exits 2."""

    def out_of_memory(*args: object) -> None:
        raise MemoryError

    monkeypatch.setattr(sample_module, "_autoreject", out_of_memory)
    monkeypatch.setattr(sample_module, "_iclabel", out_of_memory)
    result = quality.compute(_job(cap19))
    assert result.reason is None and result.stream == cap19_result.stream
    assert result.sample is not None and cap19_result.sample is not None
    failed = sample_module.MethodResult(
        "not_checkable", reason="quality.method_failed", details={"error_type": "MemoryError"}
    )
    assert (result.sample.m06, result.sample.m09a, result.sample.m09b) == (
        cap19_result.sample.m06,
        failed,
        failed,
    )


def test_a_task_whose_result_cannot_be_delivered_runs_its_job_alone(
    cap19: Path, cap19_result: quality.QualityResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-14: a part whose result does not arrive (e.g. the prepared sample could not be pickled: MemoryError)
    is no tool error: the job runs again on its own and gives the result of one process."""
    from concurrent.futures import Future

    class Pool:
        def __init__(
            self, max_workers: int | None = None, initializer: Any = None, mp_context: Any = None
        ) -> None:
            pass

        def __enter__(self) -> Pool:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def submit(self, fn: Any, *args: Any) -> Future[Any]:
            future: Future[Any] = Future()
            if fn is quality.autoreject_part:  # the M09a task (run_autoreject in the pool process)
                future.set_exception(MemoryError("pickling the prepared sample"))
            else:
                future.set_result(fn(*args))
            return future

    monkeypatch.setattr(quality, "ProcessPoolExecutor", Pool)
    (result,) = quality.compute_all([_job(cap19)], workers=4)
    assert result == cap19_result


def test_a_dying_loky_worker_is_named_once(
    cap19: Path, cap19_result: quality.QualityResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A-89: a loky process that dies during autoreject's fit makes the pool process fit again (same value,
    D-14); compute_all names that recording through on_recompute, which check prints as a translated note."""
    import autoreject
    from joblib.externals.loky.process_executor import TerminatedWorkerError

    original = autoreject.AutoReject.fit
    calls: list[int] = []

    def fit(self: Any, data: Any) -> Any:
        calls.append(self.n_jobs)
        if self.n_jobs > 1:
            raise TerminatedWorkerError(
                "A worker process managed by the executor was unexpectedly terminated."
            )
        return original(self, data)

    monkeypatch.setattr(autoreject.AutoReject, "fit", fit)
    monkeypatch.setattr(sample_module, "AUTOREJECT_PARALLEL_MIN_CHANNELS", 2)  # loky also for 19 channels
    monkeypatch.setattr(quality, "ProcessPoolExecutor", fake_pool({}, PoolLog()))  # tasks in this process
    counts: list[int] = []
    (result,) = quality.compute_all([_job(cap19)], workers=4, on_recompute=counts.append)
    assert calls == [3, 1]  # three loky processes (--jobs 4 without the pool's own), then in its process
    assert result == cap19_result and counts == [1]


def test_small_samples_do_not_start_loky(
    cap19_stage: sample_module.Stage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-14: below 64 channels the loky start costs more than it saves; autoreject runs in its process."""
    from neurogrid.quality import workers

    def refused() -> None:
        raise AssertionError("loky must not start for 19 channels")

    monkeypatch.setattr(workers, "loky_processes", refused)
    assert sample_module.run_autoreject(cap19_stage, n_jobs=4).state == "measured"
