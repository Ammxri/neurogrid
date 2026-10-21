"""Signal quality in the check pipeline (P3, NG-F07, D-04, A-11, A-18, A-19, A-60, A-79, KONZEPT 1.5).

- results.json holds per recording M07/M08 (per channel), data_seconds, M06/M09a/M09b and the sample, and
  validates against results.schema.json (in-process CLI and a real ``python -m neurogrid`` process).
- NG-N03 (KONZEPT DoD P3): ``--jobs 1`` and ``--jobs 4``, and 1 and 4 BLAS threads, give byte-identical
  results.json.
- Edge cases never give exit 2; what cannot be measured is not_checkable/not_applicable with its reason.
- ``compute_all`` keeps the order of the jobs; a dying worker costs only its own recording.
- [quality] and [sampling] reach the computation; invalid values are a configuration error (exit 2).
- The report shows the sample; only rules that need the quality job make it run.

All data are synthetic and written to tmp_path with fixed seeds. The EEG-like signals are 1/f sources with
smooth scalp patterns over the template positions of the channel names, a posterior 10 Hz rhythm, a small
50 Hz component and 1 µV sensor noise (after tools/gen_large_edf.py). Every metric is computed for real;
patches only make a method raise or a worker die.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
import pytest
from markupsafe import escape

import gen_fixtures  # type: ignore[import-not-found,unused-ignore]
from conftest import documented_config  # type: ignore[import-not-found,unused-ignore]
from neurogrid import quality
from neurogrid.checks.quality import CALIBRATED
from neurogrid.cli import main
from neurogrid.io.edf import EdfAdapter
from neurogrid.quality import QualityJob, QualityResult, QualitySettings
from neurogrid.report.texts import translator

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "src" / "neurogrid" / "schemas" / "results.schema.json").read_text(
        encoding="utf-8"
    )
)
AS_OF = "2026-10-11"
DEFAULT_SEED = 20261011
CAP_19 = tuple("Fp1 Fp2 F7 F3 Fz F4 F8 T7 C3 Cz C4 T8 P7 P3 Pz P4 P8 O1 O2".split())
CAP_16 = CAP_19[:16]
CAP_8 = CAP_19[:8]
EXTERNAL = ("EXG1", "EXG2")  # no standard name, so no template position (A-79)
SOURCES = 6
POSTERIOR = np.array([0.0, -1.0, 0.2])  # direction of the 10 Hz rhythm's maximum
PHYSICAL = (-3200.0, 3200.0)  # µV
DIGITAL = (-32768, 32767)
SAMPLING_TOML = "\n[sampling]\nsegments = 3\nsegment_s = 20\n"  # 3 × 20 s of a 90-s recording
QUALITY_RULES = (
    "CORE-M06-01",
    "CORE-M07-01",
    "CORE-M07-02",
    "CORE-M08-01",
    "CORE-M08-02",
    "CORE-M09-01",
    "CORE-M09-02",
)
SAMPLE_RULES = ("CORE-M06-01", "CORE-M09-01", "CORE-M09-02")
SAMPLE_KEYS = ("M06", "M09a", "M09b")


# --- synthetic recordings -----------------------------------------------------------------------------------


def eeg_like(names: Sequence[str], seconds: float, rate: int, seed: int) -> np.ndarray:
    """µV, channels × samples. A name without a template position gets a random direction."""
    import mne

    template = mne.channels.make_standard_montage("colin27_1005").get_positions()["ch_pos"]
    rng = np.random.default_rng(seed)
    directions = np.array(
        [template[name] if name in template else rng.normal(0.0, 1.0, 3) for name in names], dtype=float
    )
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    n = round(seconds * rate)
    t = np.arange(n) / rate
    spectrum = np.fft.rfft(rng.normal(0.0, 1.0, (SOURCES, n)), axis=1)
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    spectrum[:, 0] = 0
    spectrum[:, 1:] /= np.sqrt(freqs[1:])
    sources = np.fft.irfft(spectrum, n=n, axis=1)
    sources /= sources.std(axis=1, keepdims=True)
    centres = rng.normal(0.0, 1.0, (SOURCES, 3))
    centres /= np.linalg.norm(centres, axis=1, keepdims=True)
    mixing = np.exp(-((directions[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2) / 0.8)
    rhythm_pattern = np.exp(-((directions - POSTERIOR) ** 2).sum(axis=1) / 0.8)
    rhythm = np.sin(2 * np.pi * 10.0 * t) * (1.0 + 0.3 * sources[0])
    uv = 20.0 * (mixing @ sources) + 10.0 * np.outer(rhythm_pattern, rhythm)
    uv += 0.5 * np.sin(2 * np.pi * 50.0 * t) + rng.normal(0.0, 1.0, (len(names), n))
    return np.asarray(uv)


def _field(value: object, width: int) -> bytes:
    raw = str(value).encode("ascii")
    assert len(raw) <= width, value
    return raw.ljust(width, b" ")


def write_edf(path: Path, names: Sequence[str], uv: np.ndarray, rate: int) -> Path:
    """Plain EDF with one-second data records, 16 bit over ±3200 µV; values beyond are clipped."""
    count, samples = uv.shape
    records = samples // rate
    scale = (DIGITAL[1] - DIGITAL[0]) / (PHYSICAL[1] - PHYSICAL[0])
    digital = np.clip(np.round((uv - PHYSICAL[0]) * scale + DIGITAL[0]), *DIGITAL).astype("<i2")
    header = bytearray()
    header += _field("0", 8) + _field("X X X X", 80) + _field("Startdate X X X X", 80)
    header += _field("01.01.85", 8) + _field("00.00.00", 8) + _field(256 * (count + 1), 8)
    header += _field("", 44) + _field(records, 8) + _field(1, 8) + _field(count, 4)
    signal_fields: tuple[tuple[object, int], ...] = (
        ("AgAgCl electrode", 80),
        ("uV", 8),
        (f"{PHYSICAL[0]:g}", 8),
        (f"{PHYSICAL[1]:g}", 8),
        (DIGITAL[0], 8),
        (DIGITAL[1], 8),
        ("HP:0.1Hz LP:100Hz", 80),
        (rate, 8),
        ("", 32),
    )
    header += b"".join(_field(name, 16) for name in names)
    for value, width in signal_fields:
        header += _field(value, width) * count
    body = digital[:, : records * rate].reshape(count, records, rate).transpose(1, 0, 2).tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(header) + body)
    return path


def write_annotations_only(path: Path) -> Path:
    """EDF+C with only the 'EDF Annotations' signal, like a hypnogram (A-74, A-77)."""
    spr = 60
    tal = b"+0\x14\x14\x00+0\x1530\x14Sleep stage W\x14\x00"
    header = bytearray()
    header += _field("0", 8) + _field("X X X X", 80) + _field("Startdate X X X X", 80)
    header += _field("01.01.85", 8) + _field("00.00.00", 8) + _field(512, 8) + _field("EDF+C", 44)
    header += _field(1, 8) + _field(30, 8) + _field(1, 4)
    header += _field("EDF Annotations", 16) + _field("", 80) + _field("", 8)
    header += _field(-1, 8) + _field(1, 8) + _field(DIGITAL[0], 8) + _field(DIGITAL[1], 8)
    header += _field("", 80) + _field(spr, 8) + _field("", 32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(header) + tal.ljust(2 * spr, b"\x00"))
    return path


def _truncate(path: Path, keep: int) -> None:
    path.write_bytes(path.read_bytes()[:keep])


def _eeg_like_writer(names: Sequence[str]) -> Callable[[int, int, int, int], list[np.ndarray]]:
    """Stand-in for gen_fixtures._microvolts, so that its EEGLAB/BrainVision writers carry EEG-like data."""

    def microvolts(sfreq: int, seconds: int, channels: int, seed: int) -> list[np.ndarray]:
        assert channels == len(names)
        return list(eeg_like(names, seconds, sfreq, seed))

    return microvolts


# --- running the CLI ----------------------------------------------------------------------------------------


def cli(args: Sequence[str]) -> int:
    """``neurogrid`` in-process, like tests/cli/test_cli.py: the exit code."""
    with pytest.raises(SystemExit) as info:
        main(list(args))
    return int(info.value.code or 0)


def cli_output(args: Sequence[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = cli(args)
    out, err = capsys.readouterr()
    return code, out, err


def check_args(target: Path, out: Path, config: Path, *extra: str) -> list[str]:
    return ["check", str(target), "--out", str(out), "--config", str(config), "--as-of", AS_OF, *extra]


def load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.validate(data, SCHEMA)
    return data


def recordings(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {rec["id"]: rec for rec in data["recordings"]}


def outcomes(data: dict[str, Any], obj: str) -> dict[str, list[dict[str, Any]]]:
    """Findings of one recording per rule; passed checks appear as {"status": "passed"} entries."""
    found: dict[str, list[dict[str, Any]]] = {}
    for finding in data["findings"]:
        if finding["object"] == obj:
            found.setdefault(finding["rule_id"], []).append(finding)
    for passed in data["passed"]:
        if passed["object"] == obj:
            found.setdefault(passed["rule_id"], []).append({"status": "passed", "count": passed["count"]})
    return found


def _blas_env(threads: int) -> dict[str, str]:
    value = str(threads)
    return {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "OMP_NUM_THREADS": value,
        "OPENBLAS_NUM_THREADS": value,
        "MKL_NUM_THREADS": value,
    }


# --- NG-N03 dataset: three sample-capable recordings --------------------------------------------------------


@dataclass(frozen=True)
class Runs:
    folder: Path
    config: Path
    outputs: dict[str, Path]
    codes: dict[str, int]
    logs: dict[str, Path] = field(default_factory=dict)


@pytest.fixture(scope="module")
def ng_n03(tmp_path_factory: pytest.TempPathFactory) -> Runs:
    """One dataset, four runs: in-process --jobs 1 and --jobs 4, and two real processes with 1 and 4 BLAS
    threads (started first, they run while the in-process runs compute)."""
    base = tmp_path_factory.mktemp("ng_n03")
    folder = base / "dataset"
    write_edf(folder / "rest_s1.edf", CAP_19, eeg_like(CAP_19, 90, 256, 101), 256)
    with_external = CAP_19 + EXTERNAL
    write_edf(folder / "rest_s2.edf", with_external, eeg_like(with_external, 90, 256, 102), 256)
    write_edf(folder / "rest_s3.edf", CAP_19, eeg_like(CAP_19, 90, 250, 103), 250)
    config = documented_config(base, SAMPLING_TOML)
    names = ("jobs1", "jobs4", "blas1", "blas4")
    outputs = {name: base / name / "results.json" for name in names}
    logs = {name: base / f"{name}.log" for name in ("blas1", "blas4")}
    for path in outputs.values():
        path.parent.mkdir()
    processes: dict[str, subprocess.Popen[bytes]] = {}
    codes: dict[str, int] = {}
    try:
        for name, threads in (("blas1", 1), ("blas4", 4)):
            with logs[name].open("wb") as log:
                processes[name] = subprocess.Popen(
                    [sys.executable, "-m", "neurogrid", *check_args(folder, outputs[name], config)],
                    env=_blas_env(threads),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
        codes["jobs1"] = cli(check_args(folder, outputs["jobs1"], config, "--jobs", "1"))
        codes["jobs4"] = cli(check_args(folder, outputs["jobs4"], config, "--jobs", "4"))
        for name, process in processes.items():
            codes[name] = process.wait(timeout=900)
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.kill()
                process.wait()
    return Runs(folder=folder, config=config, outputs=outputs, codes=codes, logs=logs)


def _log(runs: Runs, name: str) -> str:
    path = runs.logs.get(name)
    return path.read_text(encoding="utf-8", errors="replace") if path and path.is_file() else ""


def test_results_do_not_depend_on_jobs_or_blas_threads(ng_n03: Runs) -> None:
    """NG-N03, A-11 (KONZEPT DoD P3): --jobs 1/4 and 1/4 BLAS threads give byte-identical results.json."""
    for name, code in ng_n03.codes.items():
        assert code in (0, 1), (name, _log(ng_n03, name))
    reference = ng_n03.outputs["jobs1"].read_bytes()
    assert ng_n03.outputs["jobs4"].read_bytes() == reference
    assert ng_n03.outputs["blas4"].read_bytes() == ng_n03.outputs["blas1"].read_bytes()
    assert ng_n03.outputs["blas1"].read_bytes() == reference  # a real process computes the same
    data = json.loads(reference)
    assert data["environment"]["blas_threads"] == 1
    # the equality covers real values: every sample method measured something on every recording
    for rec in data["recordings"]:
        assert [rec["metrics"][key]["state"] for key in SAMPLE_KEYS] == ["measured"] * 3, rec["id"]


@pytest.mark.parametrize("run", ["jobs1", "blas1"])
def test_results_json_holds_metrics_and_sample(ng_n03: Runs, run: str) -> None:
    """NG-F07, KONZEPT 1.5: per recording M07/M08 per channel, data_seconds, M06/M09 and the sample; the
    in-process CLI and a real 'python -m neurogrid' process write the same schema-valid results.json."""
    data = load(ng_n03.outputs[run])
    assert data["config"]["sampling"] == {"mode": "sample", "segments": 3, "segment_s": 20.0}
    found = recordings(data)
    assert all(re.fullmatch(r"rec-[0-9a-f]{8}", rec_id) for rec_id in found)  # raw folder: pseudonymous
    assert "rest_s" not in ng_n03.outputs[run].read_text(encoding="utf-8")
    shapes = sorted((rec["n_eeg_channels"], rec["sampling_rate_hz"]) for rec in found.values())
    assert shapes == [(19, 250.0), (19, 256.0), (21, 256.0)]
    for rec_id, rec in found.items():
        external = rec["n_eeg_channels"] == 21  # rest_s2.edf
        names = CAP_19 + EXTERNAL if external else CAP_19
        metrics = rec["metrics"]
        assert set(metrics) == {"M06", "M07", "M08", "M09a", "M09b", "data_seconds"}
        assert metrics["data_seconds"] == 90.0
        m07 = metrics["M07"]
        assert (m07["line_frequency_hz"], m07["other_frequency_hz"]) == (50.0, 60.0)
        assert m07["line_frequency_source"] == "config"  # [metadata.defaults] of documented.toml
        assert list(m07["channels"]) == sorted(names)
        for ratios in m07["channels"].values():
            assert set(ratios) == {"ratio", "other_ratio"}
            limit = CALIBRATED["line_noise"]
            assert 0.0 < ratios["ratio"] < limit and 0.0 < ratios["other_ratio"] < limit
        m08 = metrics["M08"]
        assert (m08["window_s"], m08["clipping_method"]) == (1.0, "range")
        assert list(m08["channels"]) == sorted(names)
        for entry in m08["channels"].values():
            assert entry == {"windows": 90, "flat_fraction": 0.0, "clipped_fraction": 0.0}
        for key in SAMPLE_KEYS:
            entry = metrics[key]
            assert entry["state"] == "measured" and 0.0 <= entry["value"] <= 1.0, (rec_id, key, entry)
            assert "reason" not in entry
        assert metrics["M06"]["channels"] == 19 and metrics["M06"]["ransac"] is True
        assert (metrics["M09a"]["epochs"], metrics["M09a"]["cv"]) == (30, 10)
        assert metrics["M09a"]["n_interpolate"] == [1, 4]
        assert 1 <= metrics["M09b"]["components"] <= 18
        assert sum(metrics["M09b"]["labels"].values()) == metrics["M09b"]["components"]
        assert rec["sample"] == {
            "mode": "sample",
            "segments": [{"start_s": start, "duration_s": 20.0} for start in (5.0, 35.0, 65.0)],
            "seed": DEFAULT_SEED,
            "channels": 19,
            "excluded_channels": list(EXTERNAL) if external else [],
            "positions": "standard_montage",
            "positions_unused": {},
            "resample_hz": 250.0,
            "band_hz": [1.0, 100.0],
            "notch_hz": [50.0, 100.0],
            "epoch_s": 2.0,
        }
        rules = outcomes(data, rec_id)
        assert all(rule in rules for rule in QUALITY_RULES), sorted(rules)
        channel_rules = ("CORE-M07-01", "CORE-M08-01", "CORE-M08-02")
        for rule in channel_rules:  # one result per channel
            assert sum(entry.get("count", 1) for entry in rules[rule]) == len(names), rule


def test_a_sample_method_that_raises_is_not_checkable(
    ng_n03: Runs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A-60: a raising method gives quality.method_failed with the exception's class name, never exit 2. When
    M06 fails, the bad channels are unknown and M09a/M09b are not_checkable (A-19, A-79)."""
    import autoreject
    import mne
    from pyprep.find_noisy_channels import NoisyChannels

    def raises(error: type[Exception]) -> Callable[..., Any]:
        def method(*args: object, **kwargs: object) -> Any:
            raise error("synthetic failure")

        return method

    def run(name: str) -> tuple[dict[str, Any], dict[str, Any]]:
        out = tmp_path / f"{name}.json"
        code = cli(check_args(ng_n03.folder / "rest_s1.edf", out, ng_n03.config, "--show-paths"))
        assert code in (0, 1)
        data = load(out)
        metrics = recordings(data)["rest_s1.edf"]["metrics"]
        assert set(metrics["M07"]["channels"]) == set(CAP_19)  # the streaming metrics are unaffected
        return metrics, outcomes(data, "rest_s1.edf")

    with monkeypatch.context() as patch:
        patch.setattr(NoisyChannels, "find_all_bads", raises(ZeroDivisionError))
        metrics, rules = run("m06")
    assert metrics["M06"] == {
        "state": "not_checkable",
        "reason": "quality.method_failed",
        "error_type": "ZeroDivisionError",
    }
    (finding,) = rules["CORE-M06-01"]
    assert finding["status"] == "not_checkable" and finding["details"]["error_type"] == "ZeroDivisionError"
    for key, rule in (("M09a", "CORE-M09-01"), ("M09b", "CORE-M09-02")):
        assert metrics[key] == {"state": "not_checkable", "reason": "quality.bad_channels_unknown"}
        (finding,) = rules[rule]
        assert finding["status"] == "not_checkable" and finding["reason"] == "quality.bad_channels_unknown"

    with monkeypatch.context() as patch:
        patch.setattr(autoreject.AutoReject, "fit", raises(ValueError))
        patch.setattr(mne.preprocessing.ICA, "fit", raises(np.linalg.LinAlgError))
        metrics, rules = run("m09")
    assert metrics["M06"]["state"] == "measured"
    expected = {"M09a": "ValueError", "M09b": "LinAlgError"}
    for key, error_type in expected.items():
        assert metrics[key] == {
            "state": "not_checkable",
            "reason": "quality.method_failed",
            "error_type": error_type,
        }
    for rule, error_type in zip(("CORE-M09-01", "CORE-M09-02"), expected.values(), strict=True):
        (finding,) = rules[rule]
        assert finding["status"] == "not_checkable" and finding["reason"] == "quality.method_failed"
        assert finding["details"]["error_type"] == error_type


# --- edge cases -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EdgeRun:
    code: int
    data: dict[str, Any]
    html: str


@pytest.fixture(scope="module")
def edge_run(tmp_path_factory: pytest.TempPathFactory) -> EdgeRun:
    base = tmp_path_factory.mktemp("edge")
    folder = base / "dataset"
    write_annotations_only(folder / "hypno.edf")
    (folder / "garbage.edf").write_bytes(b"not an EDF header " * 40)
    trunc = write_edf(folder / "trunc.edf", CAP_8, eeg_like(CAP_8, 20, 256, 11), 256)
    _truncate(trunc, trunc.stat().st_size - 8 * 256)  # the last data record is half missing
    trunc0 = write_edf(folder / "trunc0.edf", CAP_8, eeg_like(CAP_8, 2, 256, 12), 256)
    _truncate(trunc0, 256 * 9 + 100)  # not even one complete data record
    write_edf(folder / "short.edf", CAP_19, eeg_like(CAP_19, 30, 256, 13), 256)
    write_edf(folder / "slow.edf", CAP_19, eeg_like(CAP_19, 61, 128, 14), 128)
    write_edf(folder / "few.edf", CAP_8, eeg_like(CAP_8, 61, 256, 15), 256)
    write_edf(folder / "single.edf", ("Cz",), eeg_like(("Cz",), 61, 256, 16), 256)
    clipped = eeg_like(CAP_8, 20, 256, 17)
    clipped[0, 5 * 256 : 8 * 256] = 5000.0  # beyond the physical range: digital maximum for 3 s
    write_edf(folder / "clipped.edf", CAP_8, clipped, 256)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(gen_fixtures, "_microvolts", _eeg_like_writer(CAP_16))
        gen_fixtures.write_eeglab(
            folder / "embedded.set", sfreq=256, seconds=61, labels=CAP_16, embedded=True
        )
        gen_fixtures.write_brainvision(folder / "vision.vhdr", sfreq=500, seconds=61, labels=CAP_16, seed=18)
    out = base / "results.json"
    code = cli(check_args(folder, out, documented_config(base), "--show-paths"))
    html = ""
    if out.is_file():
        assert cli(["report", str(out), "--lang", "en", "--out", str(base)]) == 0
        html = (base / "report.en.html").read_text(encoding="utf-8")
    return EdgeRun(code=code, data=load(out) if out.is_file() else {}, html=html)


def test_edge_cases_never_give_exit_2(edge_run: EdgeRun) -> None:
    """NG-F14, A-60: no recording turns the run into a tool error; the report renders them all."""
    assert edge_run.code == 1  # failed error rules (truncation, missing metadata, clipping), not a crash
    assert edge_run.data["summary"]["exit_code"] == 1
    assert sorted(recordings(edge_run.data)) == sorted(
        [
            "clipped.edf",
            "embedded.set",
            "few.edf",
            "garbage.edf",
            "hypno.edf",
            "short.edf",
            "single.edf",
            "slow.edf",
            "trunc.edf",
            "trunc0.edf",
            "vision.vhdr",
        ]
    )
    assert 'id="metrics"' in edge_run.html and "single.edf" in edge_run.html
    tr = translator("en").t
    for reason in (
        "recording.annotations_only",
        "header.unreadable",
        "quality.too_short",
        "quality.rate_too_low",
        "quality.too_few_channels",
    ):
        assert str(escape(tr(f"reason.{reason}"))) in edge_run.html, reason


@pytest.mark.parametrize(
    ("rec_id", "status", "reason"),
    [
        ("hypno.edf", "not_applicable", "recording.annotations_only"),
        ("garbage.edf", "not_checkable", "header.unreadable"),
    ],
)
def test_recordings_without_signals_are_not_measured(
    edge_run: EdgeRun, rec_id: str, status: str, reason: str
) -> None:
    """A-74/A-77: an annotations-only EDF+ is no recording; an unreadable header has nothing to measure."""
    rec = recordings(edge_run.data)[rec_id]
    # No signal metric. hypno.edf matches no signal recording, so it is an M10 object of its own and carries
    # the M10 summary (P4, A-80: recordings[].metrics["annotation"], critic X10).
    assert set(rec["metrics"]) == ({"annotation"} if rec_id == "hypno.edf" else set())
    assert rec["sample"] is None
    rules = outcomes(edge_run.data, rec_id)
    for rule in QUALITY_RULES:
        (finding,) = rules[rule]
        assert (finding["status"], finding["reason"]) == (status, reason), rule


@pytest.mark.parametrize(
    ("rec_id", "reason", "details"),
    [
        ("short.edf", "quality.too_short", {"seconds": 30.0, "min_seconds": 60.0}),
        ("trunc.edf", "quality.too_short", {"seconds": 19.0, "min_seconds": 60.0}),
        ("slow.edf", "quality.rate_too_low", {"rate_hz": 128.0, "min_rate_hz": 200.0}),
        ("few.edf", "quality.too_few_channels", {"channels": 8, "min_channels": 16}),
        ("single.edf", "quality.too_few_channels", {"channels": 1, "min_channels": 16}),
    ],
)
def test_sample_preconditions_give_their_reason(
    edge_run: EdgeRun, rec_id: str, reason: str, details: dict[str, Any]
) -> None:
    """A-60, A-79: under 60 s, under 200 Hz or under 16 EEG channels M06/M09 are not_checkable with the
    precondition as reason, while M07/M08 are measured over the full length."""
    rec = recordings(edge_run.data)[rec_id]
    metrics = rec["metrics"]
    for key in SAMPLE_KEYS:
        assert metrics[key] == {"state": "not_checkable", "reason": reason, **details}, key
    rules = outcomes(edge_run.data, rec_id)
    for rule in SAMPLE_RULES:
        (finding,) = rules[rule]
        assert (finding["status"], finding["reason"]) == ("not_checkable", reason)
        assert finding["details"] == details
    assert rec["sample"]["mode"] == "sample" and rec["sample"]["positions"] == "none"
    for channel in metrics["M07"]["channels"].values():
        assert set(channel) == {"ratio", "other_ratio"}
    windows = int(metrics["data_seconds"])
    for channel in metrics["M08"]["channels"].values():
        assert channel == {"windows": windows, "flat_fraction": 0.0, "clipped_fraction": 0.0}


def test_truncated_edf_is_measured_on_its_complete_records(edge_run: EdgeRun) -> None:
    """A-24: only complete data records are read; M01-02 reports the truncation."""
    rec = recordings(edge_run.data)["trunc.edf"]
    assert rec["duration_s"] == 20.0 and rec["metrics"]["data_seconds"] == 19.0
    assert outcomes(edge_run.data, "trunc.edf")["CORE-M01-02"][0]["status"] == "failed"
    nothing = recordings(edge_run.data)["trunc0.edf"]
    assert nothing["metrics"]["data_seconds"] == 0.0
    for channel in nothing["metrics"]["M07"]["channels"].values():  # not one 2-s Welch segment
        assert channel == {"state": "not_checkable", "reason": "quality.too_short"}
    for channel in nothing["metrics"]["M08"]["channels"].values():
        assert channel == {"windows": 0, "flat_fraction": None, "clipped_fraction": None}
    rules = outcomes(edge_run.data, "trunc0.edf")
    for rule, reason in (
        ("CORE-M07-01", "quality.too_short"),
        ("CORE-M07-02", "quality.too_short"),
        ("CORE-M08-01", "quality.too_short"),
        ("CORE-M08-02", "quality.too_short"),
        ("CORE-M06-01", "quality.too_short"),
        ("CORE-M09-01", "quality.too_short"),
        ("CORE-M09-02", "quality.too_short"),
    ):
        assert {(f["status"], f["reason"]) for f in rules[rule]} == {("not_checkable", reason)}, rule


def test_single_channel_recording_is_streamed(edge_run: EdgeRun) -> None:
    """A single EEG channel: M07/M08 for that channel, M06/M09 not_checkable (too few channels)."""
    metrics = recordings(edge_run.data)["single.edf"]["metrics"]
    assert list(metrics["M07"]["channels"]) == ["Cz"] and list(metrics["M08"]["channels"]) == ["Cz"]
    rules = outcomes(edge_run.data, "single.edf")
    assert [entry["status"] for entry in rules["CORE-M07-01"]] == ["passed"]


def test_clipping_is_reported_with_its_time_range(edge_run: EdgeRun) -> None:
    """M08 (EDF): values at the digital limit for 3 of 20 one-second windows on one channel."""
    channels = recordings(edge_run.data)["clipped.edf"]["metrics"]["M08"]["channels"]
    assert channels["Fp1"] == {"windows": 20, "flat_fraction": 0.0, "clipped_fraction": 0.15}
    assert all(channels[name]["clipped_fraction"] == 0.0 for name in CAP_8[1:])
    (finding,) = [f for f in outcomes(edge_run.data, "clipped.edf")["CORE-M08-02"] if f["status"] != "passed"]
    assert (finding["status"], finding["channel"], finding["measured_value"]) == ("failed", "Fp1", 0.15)
    assert finding["time_ranges"] == [{"start_s": 5.0, "end_s": 8.0}]
    assert (finding["time_ranges_total"], finding["time_ranges_duration_s"]) == (1, 3.0)
    assert "5.000–8.000 s" in edge_run.html


@pytest.mark.parametrize(
    ("rec_id", "fmt", "m09b_state"),
    [("embedded.set", "EEGLAB", "not_checkable"), ("vision.vhdr", "BrainVision", "measured")],
)
def test_eeglab_with_embedded_data_and_brainvision_are_measured(
    edge_run: EdgeRun, rec_id: str, fmt: str, m09b_state: str
) -> None:
    """R14, A-18: EEGLAB with the data inside the .set and BrainVision go through MNE: plateau clipping, the
    whole recording as sample (61 s), positions from the standard names."""
    rec = recordings(edge_run.data)[rec_id]
    metrics = rec["metrics"]
    assert rec["format"] == fmt and metrics["data_seconds"] == 61.0
    assert metrics["M08"]["clipping_method"] == "plateau"
    assert list(metrics["M07"]["channels"]) == sorted(CAP_16)
    for channel in metrics["M08"]["channels"].values():
        assert channel == {"windows": 61, "flat_fraction": 0.0, "clipped_fraction": 0.0}
    assert rec["sample"]["segments"] == [{"start_s": 0.0, "duration_s": 61.0}]
    assert rec["sample"]["positions"] == "standard_montage" and rec["sample"]["channels"] == 16
    assert metrics["M06"]["state"] == "measured" and metrics["M09a"]["state"] == "measured"
    m09b = metrics["M09b"]  # deterministic data: one outcome per format
    assert m09b["state"] == m09b_state, m09b
    if m09b_state == "measured":
        assert m09b["components"] > 0
    else:  # one bad channel leaves 15 good ones, fewer than the 16 that M09b needs
        bads = len(metrics["M06"]["bad_channels"])
        assert m09b == {
            "state": "not_checkable",
            "reason": "quality.too_few_channels",
            "channels": 16 - bads,
            "min_channels": 16,
        }


def test_all_zero_recording_has_no_measured_sample_values(edge_run: EdgeRun, tmp_path: Path) -> None:
    """A recording without any signal: M07 has no power, M08 is all flat, M06 finds every channel bad (flat),
    and M09 is not_checkable – autoreject and ICA must not report values computed on the filters' round-off
    (A-60, A-79)."""
    folder = tmp_path / "dataset"
    write_edf(folder / "zero.edf", CAP_19, np.zeros((19, 61 * 256)), 256)
    out = tmp_path / "results.json"
    code = cli(check_args(folder, out, documented_config(tmp_path), "--show-paths"))
    assert code == 1  # CORE-M08-01 (flat line, error) fails
    data = load(out)
    metrics = recordings(data)["zero.edf"]["metrics"]
    for name in CAP_19:
        assert metrics["M07"]["channels"][name] == {
            "state": "not_checkable",
            "reason": "quality.no_signal_power",
        }
        assert metrics["M08"]["channels"][name] == {
            "windows": 61,
            "flat_fraction": 1.0,
            "clipped_fraction": 0.0,
        }
    rules = outcomes(data, "zero.edf")
    assert {f["status"] for f in rules["CORE-M08-01"]} == {"failed"}
    assert metrics["M06"]["state"] == "measured" and metrics["M06"]["value"] == 1.0
    assert metrics["M06"]["bad_channels"] == sorted(CAP_19)
    assert {f["status"] for f in rules["CORE-M06-01"]} == {"failed"}
    for key in ("M09a", "M09b"):
        assert metrics[key]["state"] == "not_checkable", f"{key} measured on a recording without signal"
        assert metrics[key]["reason"] == "quality.too_few_channels" and metrics[key]["channels"] == 0
    for rule in ("CORE-M09-01", "CORE-M09-02"):
        assert {f["status"] for f in rules[rule]} == {"not_checkable"}, rule


# --- compute_all: order and dying workers -------------------------------------------------------------------


@pytest.fixture(scope="module")
def cheap(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Three short 8-channel recordings of different length (only the streaming metrics have work to do)."""
    folder = tmp_path_factory.mktemp("cheap") / "dataset"
    for name, seconds, seed in (("rec_a.edf", 16, 21), ("rec_b.edf", 12, 22), ("rec_c.edf", 20, 23)):
        write_edf(folder / name, CAP_8, eeg_like(CAP_8, seconds, 256, seed), 256)
    return folder


def _jobs(folder: Path, names: Sequence[str], *, sample: bool = True) -> list[QualityJob]:
    jobs = []
    for name in names:
        path = folder / name
        recording = EdfAdapter().read(path, recording_id=name, relative_path=name)
        jobs.append(
            QualityJob(path=str(path), recording=recording, settings=QualitySettings(), sample=sample)
        )
    return jobs


def test_compute_all_keeps_the_order_of_the_jobs(cheap: Path) -> None:
    """KONZEPT 1.4: with a process pool the results come back in the order of the jobs, equal to the
    results computed in this process."""
    jobs = _jobs(cheap, ["rec_a.edf", "rec_b.edf", "rec_c.edf"], sample=False)
    results = quality.compute_all(jobs, workers=2)
    assert [r.stream.data_seconds if r.stream else None for r in results] == [16.0, 12.0, 20.0]
    assert results == [quality.compute(job) for job in jobs]


@dataclass
class PoolLog:
    workers: list[int | None] = field(default_factory=list)  # max_workers of every pool created
    submitted: list[str] = field(default_factory=list)


def fake_pool(breaks: dict[str, int], log: PoolLog) -> type:
    """A stand-in for ProcessPoolExecutor that runs every task in this process. A job named in ``breaks``
    kills its worker in that many pools: there, every task of the job ends with BrokenProcessPool, as all
    pending work does when a real worker dies. Tasks that take a job are logged by the job's file name."""
    left = dict(breaks)

    class FakePool:
        def __init__(self, max_workers: int | None = None, initializer: Callable[[], None] | None = None):
            log.workers.append(max_workers)
            self.dying: set[str] = set()
            self.seen: set[str] = set()

        def __enter__(self) -> FakePool:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def submit(self, fn: Callable[..., Any], *args: Any) -> Future[Any]:
            future: Future[Any] = Future()
            name = Path(args[0].path).name if isinstance(args[0], QualityJob) else ""
            if name:
                log.submitted.append(name)
                if name not in self.seen and left.get(name, 0) > 0:
                    left[name] -= 1
                    self.dying.add(name)
                self.seen.add(name)
            if name in self.dying:
                future.set_exception(BrokenProcessPool("A child process terminated abruptly"))
            else:
                future.set_result(fn(*args))
            return future

    return FakePool


@pytest.fixture
def isolated_calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    calls: list[str] = []
    original = quality._isolated

    def spy(job: QualityJob) -> QualityResult:
        calls.append(Path(job.path).name)
        return original(job)

    monkeypatch.setattr(quality, "_isolated", spy)
    yield calls


def test_broken_pool_retries_jobs_one_at_a_time(
    cheap: Path, monkeypatch: pytest.MonkeyPatch, isolated_calls: list[str]
) -> None:
    """A dying worker costs only its own recording: the jobs it took down run again in a pool of their own;
    a job whose worker dies again gives quality.worker_failed (error type BrokenProcessPool)."""
    log = PoolLog()
    monkeypatch.setattr(quality, "ProcessPoolExecutor", fake_pool({"rec_a.edf": 1, "rec_b.edf": 2}, log))
    jobs = _jobs(cheap, ["rec_a.edf", "rec_b.edf", "rec_c.edf"])
    results = quality.compute_all(jobs, workers=4)
    assert isolated_calls == ["rec_a.edf", "rec_b.edf"]
    assert log.workers == [4, 1, 1]  # D-14: a pool of --jobs processes for the parts of all recordings
    # stream and sample part of every recording in the pool, then the two broken jobs on their own
    pool_tasks = ["rec_a.edf", "rec_a.edf", "rec_b.edf", "rec_b.edf", "rec_c.edf", "rec_c.edf"]
    assert log.submitted == [*pool_tasks, "rec_a.edf", "rec_b.edf"]
    assert results[0] == quality.compute(jobs[0])  # retried with success
    assert results[1] == QualityResult(
        line_frequency_hz=50.0,
        line_frequency_source="default",
        reason="quality.worker_failed",
        error_type="BrokenProcessPool",
    )
    assert results[2] == quality.compute(jobs[2])  # untouched
    assert quality.describe(results[1]) == {"state": "not_checkable", "reason": "quality.worker_failed"}


def test_a_worker_that_dies_twice_does_not_end_the_run(
    cheap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_calls: list[str]
) -> None:
    """--jobs 2 with one recording whose worker always dies: exit 0/1, never 2; the others are measured. A
    recording not yet started when the pool broke runs on its own (a broken pool takes no more work)."""
    log = PoolLog()
    monkeypatch.setattr(quality, "ProcessPoolExecutor", fake_pool({"rec_b.edf": 2}, log))
    out = tmp_path / "results.json"
    code = cli(check_args(cheap, out, documented_config(tmp_path), "--jobs", "2", "--show-paths"))
    assert code in (0, 1)
    assert isolated_calls == ["rec_b.edf", "rec_c.edf"] and log.workers == [2, 1, 1]
    data = load(out)
    found = recordings(data)
    assert found["rec_b.edf"]["metrics"] == {"state": "not_checkable", "reason": "quality.worker_failed"}
    assert found["rec_b.edf"]["sample"] is None
    for rule in QUALITY_RULES:
        (finding,) = outcomes(data, "rec_b.edf")[rule]
        assert (finding["status"], finding["reason"]) == ("not_checkable", "quality.worker_failed")
        assert finding["details"] == {"error_type": "BrokenProcessPool"}
    for name in ("rec_a.edf", "rec_c.edf"):
        assert set(found[name]["metrics"]) == {"M06", "M07", "M08", "M09a", "M09b", "data_seconds"}
    assert translator("en").has("reason.quality.worker_failed")
    assert translator("zh").has("reason.quality.worker_failed")


# --- only rules that need the quality job make it run -------------------------------------------------------

LAB_PACK = """rulepack: lab
version: "1.0"
source: Lab SOP 7
source_status: final
rules:
  - id: LAB-Q-001
    clause: "SOP-7 4.1"
    title_zh: 实验室规则
    title_en: Lab rule
    phase: acquisition
    check: {check}
    params: {params}
    severity: warning
    verification: automatic
"""


@pytest.mark.parametrize(
    ("check", "params", "metric_keys", "sampled"),
    [
        ("signal.sampling_rate_min", "{min_hz: 200}", set(), False),
        ("quality.flatline", "{max_fraction: 0.05}", {"M07", "M08", "data_seconds"}, False),
        ("quality.bad_channels", "{max_fraction: 0.3}", {"M06", "M09a", "M09b"}, True),
    ],
)
def test_quality_job_runs_only_for_loaded_quality_rules(
    cheap: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    check: str,
    params: str,
    metric_keys: set[str],
    sampled: bool,
) -> None:
    """pipeline.run_check: no quality rule, no quality job (metrics empty); a stream-only rule computes no
    sample, a sample-only rule no streaming pass."""
    from neurogrid.checks import context

    calls: list[int] = []
    original = context.compute_all

    def spy(jobs: Sequence[QualityJob], workers: int = 1) -> list[QualityResult]:
        calls.append(len(jobs))
        return original(jobs, workers)

    monkeypatch.setattr(context, "compute_all", spy)
    (tmp_path / "lab.yaml").write_text(LAB_PACK.format(check=check, params=params), encoding="utf-8")
    config = documented_config(tmp_path, '\n[check]\nrulepacks = ["lab.yaml"]\n')
    out = tmp_path / "results.json"
    assert cli(check_args(cheap, out, config, "--show-paths")) in (0, 1)
    data = load(out)
    assert [pack["name"] for pack in data["rulepacks"]] == ["lab"]
    assert calls == ([3] if metric_keys else [])
    for rec in data["recordings"]:
        assert set(rec["metrics"]) == metric_keys, rec["id"]
        assert (rec["sample"] is not None) is sampled, rec["id"]


# --- configuration ------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def settings_folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """An 8-channel 40-s EDF, a float EEGLAB file and a BrainVision file whose first channel has a plateau
    of 6 equal samples at the maximum of every second."""
    folder = tmp_path_factory.mktemp("settings") / "dataset"
    write_edf(folder / "eight.edf", CAP_8, eeg_like(CAP_8, 40, 256, 31), 256)
    gen_fixtures.write_eeglab(folder / "float.set", sfreq=256, seconds=10, labels=CAP_8, seed=32)
    vhdr = folder / "plateau.vhdr"
    gen_fixtures.write_brainvision(vhdr, sfreq=500, seconds=10, labels=CAP_8, seed=33)
    steps = np.round(eeg_like(CAP_8, 10, 500, 34) / 0.1).astype(np.int64)  # resolution 0.1 µV
    for second in range(10):
        window = steps[0, second * 500 : (second + 1) * 500]
        window[200:206] = window.max() + 10
    vhdr.with_suffix(".eeg").write_bytes(np.clip(steps.T, *DIGITAL).astype("<i2").tobytes())
    return folder


@pytest.fixture(scope="module")
def settings_runs(
    settings_folder: Path, tmp_path_factory: pytest.TempPathFactory
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    """The folder checked with changed [quality]/[sampling]/[check] values, and with only mode = "full":
    the recordings of both runs and the second results.json."""
    base = tmp_path_factory.mktemp("settings_runs")
    custom = documented_config(
        base,
        "\n[check]\nseed = 7\n"
        "[quality]\nmin_channels = 4\nmin_seconds = 30\nflat_tolerance_uv = 1000\nplateau_samples = 5\n"
        "[sampling]\nsegments = 2\nsegment_s = 10\n",
        name="custom.toml",
    )
    full = documented_config(base, '\n[sampling]\nmode = "full"\n', name="full.toml")
    assert cli(check_args(settings_folder, base / "custom.json", custom, "--show-paths")) in (0, 1)
    assert cli(check_args(settings_folder, base / "full.json", full, "--show-paths")) in (0, 1)
    full_data = load(base / "full.json")
    return recordings(load(base / "custom.json")), recordings(full_data), full_data


def test_quality_and_sampling_settings_reach_the_computation(
    settings_runs: tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]],
) -> None:
    """A-18, A-60, A-79, D-04: [quality] min_channels/min_seconds/flat_tolerance_uv/plateau_samples,
    [sampling] mode/segments/segment_s and [check] seed change what is computed."""
    changed, default, full_data = settings_runs
    eight = changed["eight.edf"]
    assert eight["sample"]["mode"] == "sample" and eight["sample"]["seed"] == 7
    assert eight["sample"]["segments"] == [
        {"start_s": 5.0, "duration_s": 10.0},
        {"start_s": 25.0, "duration_s": 10.0},
    ]
    assert eight["sample"]["channels"] == 8 and eight["sample"]["positions"] == "standard_montage"
    assert eight["metrics"]["M06"].get("reason") != "quality.too_few_channels"  # 8 >= min_channels 4
    assert eight["metrics"]["M09a"]["state"] == "measured" and eight["metrics"]["M09a"]["epochs"] == 10
    assert eight["metrics"]["M09b"]["state"] == "measured" and eight["metrics"]["M09b"]["components"] == 7
    unchanged = default["eight.edf"]
    assert unchanged["sample"]["mode"] == "full" and unchanged["sample"]["seed"] == DEFAULT_SEED
    assert unchanged["sample"]["segments"] == [{"start_s": 0.0, "duration_s": 40.0}]
    for key in SAMPLE_KEYS:  # 40 s < the default min_seconds (checked before the channel count)
        assert unchanged["metrics"][key] == {
            "state": "not_checkable",
            "reason": "quality.too_short",
            "seconds": 40.0,
            "min_seconds": 60.0,
        }

    assert changed["float.set"]["metrics"]["M06"]["reason"] == "quality.too_short"
    assert changed["float.set"]["metrics"]["M06"]["min_seconds"] == 30.0
    flat_custom = changed["float.set"]["metrics"]["M08"]["channels"]
    flat_default = default["float.set"]["metrics"]["M08"]["channels"]
    assert {entry["flat_fraction"] for entry in flat_custom.values()} == {1.0}  # p2p < 1000 µV
    assert {entry["flat_fraction"] for entry in flat_default.values()} == {0.0}

    plateau_custom = changed["plateau.vhdr"]["metrics"]["M08"]["channels"]
    plateau_default = default["plateau.vhdr"]["metrics"]["M08"]["channels"]
    assert plateau_custom["Fp1"]["clipped_fraction"] == 1.0  # 6 equal samples >= plateau_samples 5
    assert plateau_default["Fp1"]["clipped_fraction"] == 0.0  # 6 < 10
    for name in CAP_8[1:]:
        assert plateau_custom[name]["clipped_fraction"] == 0.0
    assert full_data["config"]["sampling"] == {"mode": "full", "segments": 10, "segment_s": 60.0}


def test_bad_channels_are_measured_below_the_default_channel_minimum(
    settings_runs: tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]],
) -> None:
    """A-79: min_channels = 4 (allowed from 2) makes an 8-channel recording with positions sample-capable,
    so M06 is measured on its 8 channels – RANSAC needs more channels than that and must not take the
    other pyprep criteria down with it."""
    m06 = settings_runs[0]["eight.edf"]["metrics"]["M06"]
    assert m06["state"] == "measured" and m06["channels"] == 8, m06
    assert m06["ransac"] is False and m06["ransac_skipped"] == "too_few_channels", m06


@pytest.mark.parametrize(
    ("toml", "field_name"),
    [
        ("[quality]\nmin_channels = 0\n", "quality.min_channels"),
        ("[quality]\nmin_channels = -3\n", "quality.min_channels"),
        ("[quality]\nmin_seconds = 0\n", "quality.min_seconds"),
        ("[quality]\nflat_tolerance_uv = -0.1\n", "quality.flat_tolerance_uv"),
        ("[quality]\nplateau_samples = 1\n", "quality.plateau_samples"),
        ("[quality]\nmin_channel = 4\n", "quality.min_channel"),
        ('[sampling]\nmode = "fast"\n', "sampling.mode"),
        ("[sampling]\nsegments = 0\n", "sampling.segments"),
        ("[sampling]\nsegment_s = -60\n", "sampling.segment_s"),
        ("[sampling]\nwindow = 2\n", "sampling.window"),
    ],
)
def test_invalid_quality_settings_are_configuration_errors(
    cheap: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], toml: str, field_name: str
) -> None:
    """NG-F18: out-of-range values and unknown keys are refused with the field, as a tool error (exit 2)."""
    config = documented_config(tmp_path, "\n" + toml)
    out = tmp_path / "results.json"
    code, _, err = cli_output(check_args(cheap, out, config), capsys)
    assert code == 2 and f"'{field_name}'" in err and "Invalid configuration" in err
    assert not out.exists()


@pytest.mark.parametrize("jobs", ["0", "65", "x"])
def test_jobs_outside_1_to_64_are_refused(
    cheap: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], jobs: str
) -> None:
    code, _, err = cli_output(
        ["check", str(cheap), "--out", str(tmp_path / "r.json"), "--jobs", jobs], capsys
    )
    assert code == 2 and "--jobs" in err


# --- report ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_report_shows_the_sample(ng_n03: Runs, tmp_path: Path, lang: str) -> None:
    """KONZEPT 1.5, NG-F13: the metrics section lists the sample per recording: segments in recording time,
    seed, analysed channels, montage source and the channels left out, in the report language."""
    folder = tmp_path / "report"
    assert cli(["report", str(ng_n03.outputs["jobs1"]), "--lang", lang, "--out", str(folder)]) == 0
    html = (folder / f"report.{lang}.html").read_text(encoding="utf-8")
    metrics = html[html.index('id="metrics"') : html.index('id="evidence"')]
    tr = translator(lang).t
    for key in ("sample", "sample_mode", "segments", "seed", "analysed_channels", "positions", "notch"):
        assert tr(f"report.label.{key}") in metrics, key
    assert tr("report.sample_mode.sample") in metrics
    assert tr("report.text.sample_method", resample_hz="250", low="1", high="100", epoch_s="2") in metrics
    assert metrics.count("5.000–25.000 s, 35.000–55.000 s, 65.000–85.000 s") == 3
    assert metrics.count(f"<td>{DEFAULT_SEED}</td>") == 3
    montage = tr("report.positions.standard_montage")
    assert metrics.count(montage) == 3
    excluded = tr("report.text.positions_excluded", names="EXG1, EXG2")
    assert f"{montage}; {excluded}" in metrics
    assert metrics.count(excluded) == 1


def test_report_renders_unknown_sample_values(ng_n03: Runs, tmp_path: Path) -> None:
    """A-61: results.json of another version with a montage source, mode or reason without a text still
    renders; the raw value is shown (fmt.label)."""
    data = json.loads(ng_n03.outputs["jobs1"].read_text(encoding="utf-8"))
    sample = data["recordings"][0]["sample"]
    sample.update(mode="adaptive", positions="digitizer_v2", positions_unused={"photogrammetry": "blurred"})
    sample["segments"].append({"start_s": "late", "duration_s": None})  # malformed entries are skipped
    results = tmp_path / "results.json"
    results.write_text(json.dumps(data), encoding="utf-8")
    assert cli(["report", str(results), "--lang", "en", "--out", str(tmp_path)]) == 0
    html = (tmp_path / "report.en.html").read_text(encoding="utf-8")
    tr = translator("en").t
    assert "<td>adaptive</td>" in html and "digitizer_v2" in html
    assert tr("report.text.positions_unused", source="photogrammetry", reason="blurred") in html
    assert "5.000–25.000 s, 35.000–55.000 s, 65.000–85.000 s</td>" in html
