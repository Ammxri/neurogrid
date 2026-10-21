"""M06 and M09 on the deterministic sample (D-04, A-19, A-60, A-79): segment selection, the sample as it is
reported, preconditions, montage sources, failing methods, determinism, and detection on synthetic EEG.

The synthetic EEG is written as EDF in tmp_path with fixed seeds: 1/f sources with smooth scalp patterns
mixed to standard 10-20/10-10 channels, a posterior 10 Hz rhythm and 1 µV sensor noise (after
tools/gen_large_edf.py). Every measurement runs the real pyprep, autoreject and ICLabel; patches only make a
method raise.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import mne
import numpy as np
import pytest
from scipy.signal import butter, sosfiltfilt

import gen_fixtures
from neurogrid.io.edf import EdfAdapter
from neurogrid.model.dataset import Recording
from neurogrid.quality import QualityJob, QualitySettings, compute_all
from neurogrid.quality import sample as sample_module
from neurogrid.quality.positions import Position
from neurogrid.quality.sample import MethodResult, SampleResult, measure_sample, select_segments
from neurogrid.quality.source import open_signals

RATE = 250
SETTINGS = QualitySettings()
PHYSICAL = (-3200.0, 3200.0)  # µV; room for the 500 µV transients of M09a
DIGITAL = (-32768, 32767)
CAP_32 = tuple(
    "Fp1 Fp2 AF3 AF4 F7 F3 Fz F4 F8 FC5 FC1 FC2 FC6 T7 C3 Cz "
    "C4 T8 CP5 CP1 CP2 CP6 P7 P3 Pz P4 P8 PO3 PO4 O1 Oz O2".split()
)
CAP_20 = tuple("Fp1 Fp2 F7 F3 Fz F4 F8 T7 C3 Cz C4 T8 P7 P3 Pz P4 P8 O1 Oz O2".split())
CAP_16 = ("Fp1", "Fp2", "F7", "F3", "F4", "F8", "T7", "C3", "C4", "T8", "P7", "P3", "P4", "P8", "O1", "O2")
EXTERNAL = ("EXG1", "EXG2", "EXG3", "EXG4")  # BioSemi external electrodes: no standard name, no position
NOISY = ("F3", "P4")  # M06 target: additive white noise of 10 times the channel's standard deviation
FLAT = "C4"  # constant
UNRELATED = "O1"  # replaced by independent white noise of the same standard deviation
OCCIPITAL = np.array([0.0, -0.115, 0.015])  # centre of the alpha rhythm (near Oz), m


# --- synthetic EEG as EDF ---------------------------------------------------------------------------------


def _field(value: object, width: int) -> bytes:
    raw = str(value).encode("ascii")
    assert len(raw) <= width, value
    return raw.ljust(width, b" ")


def _write_edf(path: Path, names: Sequence[str], uv: np.ndarray, rate: int = RATE) -> Path:
    """Plain EDF, one-second data records, 16 bit over ±3200 µV (LSB about 0.1 µV)."""
    count = len(names)
    seconds = uv.shape[1] // rate
    header = bytearray()
    header += _field("0", 8) + _field("X X X X", 80) + _field("Startdate X X X X", 80)
    header += _field("01.01.85", 8) + _field("00.00.00", 8) + _field(256 * (count + 1), 8)
    header += _field("", 44) + _field(seconds, 8) + _field(1, 8) + _field(count, 4)
    per_signal: list[tuple[object, int]] = [
        ("AgAgCl electrode", 80),
        ("uV", 8),
        (f"{PHYSICAL[0]:g}", 8),
        (f"{PHYSICAL[1]:g}", 8),
        (DIGITAL[0], 8),
        (DIGITAL[1], 8),
        ("HP:0.1Hz LP:100Hz", 80),
        (rate, 8),
        ("", 32),
    ]
    header += b"".join(_field(name, 16) for name in names)
    for value, width in per_signal:
        header += _field(value, width) * count
    scale = (DIGITAL[1] - DIGITAL[0]) / (PHYSICAL[1] - PHYSICAL[0])
    digital = np.round((uv[:, : seconds * rate] - PHYSICAL[0]) * scale + DIGITAL[0])
    samples = np.clip(digital, *DIGITAL).astype("<i2")
    body = samples.reshape(count, seconds, rate).transpose(1, 0, 2).tobytes()
    path.write_bytes(bytes(header) + body)
    return path


def _recording(path: Path) -> Recording:
    return EdfAdapter().read(path, recording_id=path.stem, relative_path=path.name)


def _measure(path: Path, line_hz: float = 50.0, **overrides: Any) -> SampleResult:
    """measure_sample on an EDF file with the default settings (QualitySettings) and ``overrides``."""
    options: dict[str, Any] = {
        "mode": SETTINGS.mode,
        "segments": SETTINGS.segments,
        "segment_s": SETTINGS.segment_s,
        "seed": SETTINGS.seed,
        "min_seconds": SETTINGS.min_seconds,
        "min_channels": SETTINGS.min_channels,
        "channel_map": {},
    }
    options.update(overrides)
    source = open_signals(path, _recording(path))
    try:
        return measure_sample(source, line_hz, **options)
    finally:
        source.close()


def _positions(names: Sequence[str]) -> np.ndarray:
    found = mne.channels.make_standard_montage("colin27_1005").get_positions()["ch_pos"]
    return np.array([found[name] for name in names])


def _pink(rng: np.random.Generator, count: int, n: int, rate: int) -> np.ndarray:
    """``count`` independent 1/f signals of unit standard deviation."""
    spectrum = np.fft.rfft(rng.normal(0.0, 1.0, (count, n)), axis=1)
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    spectrum[:, 0] = 0.0
    spectrum[:, 1:] /= np.sqrt(freqs[1:])
    signals = np.fft.irfft(spectrum, n=n, axis=1)
    return np.asarray(signals / signals.std(axis=1, keepdims=True))


def _blob(positions: np.ndarray, centre: np.ndarray, sigma: float) -> np.ndarray:
    """A smooth scalp pattern around ``centre`` (Gaussian of the distance, m)."""
    return np.asarray(np.exp(-np.sum((positions - centre) ** 2, axis=-1) / (2 * sigma**2)))


def eeg_like(
    names: Sequence[str], seconds: int, seed: int, rate: int = RATE, sources: int = 24, spread: float = 0.04
) -> np.ndarray:
    """EEG-like signals in µV, one row per channel (standard names, for the scalp patterns).

    ``spread`` (m) is the width of the source patterns; a sparse cap needs wider ones, or neighbouring
    channels share too little signal and pyprep finds them uncorrelated.
    """
    rng = np.random.default_rng(seed)
    n = seconds * rate
    positions = _positions(names)
    centres = positions[rng.choice(len(names), sources)] + rng.normal(0.0, 0.01, (sources, 3))
    patterns = _blob(positions[None, :, :], centres[:, None, :], spread)
    patterns *= rng.choice([-1.0, 1.0], sources)[:, None]
    uv = 12.0 * (patterns.T @ _pink(rng, sources, n, rate))
    t = np.arange(n) / rate
    envelope = 1.0 + 0.15 * _pink(rng, 1, n, rate)[0]
    uv += 10.0 * _blob(positions, OCCIPITAL, 0.05)[:, None] * (envelope * np.sin(2 * np.pi * 10 * t))[None, :]
    uv += rng.normal(0.0, 1.0, uv.shape)
    return np.asarray(uv)


def _with_external(uv: np.ndarray, seed: int) -> np.ndarray:
    """Four external channels (1/f noise of 10 µV) after the cap channels."""
    rng = np.random.default_rng(seed)
    return np.vstack([uv, 10.0 * _pink(rng, len(EXTERNAL), uv.shape[1], RATE)])


def _with_bad_channels(uv: np.ndarray, names: Sequence[str]) -> np.ndarray:
    """M06 target: 2 noisy, 1 flat and 1 unrelated channel."""
    rng = np.random.default_rng(99)
    out = uv.copy()
    for name in NOISY:
        index = names.index(name)
        out[index] += rng.normal(0.0, 10 * uv[index].std(), uv.shape[1])
    out[names.index(FLAT)] = 37.0
    index = names.index(UNRELATED)
    out[index] = rng.normal(0.0, uv[index].std(), uv.shape[1])
    return out


def _with_transients(uv: np.ndarray, share: float, rate: int = RATE) -> np.ndarray:
    """M09a target: a 500 µV transient (0.2-s Hann pulse) in ``share`` of the 2-s epochs, on every channel.

    The polarity alternates from channel to channel, so the average reference keeps the transient; its
    position inside the epoch varies, so that the median epoch stays clean.
    """
    rng = np.random.default_rng(5)
    epochs = uv.shape[1] // (2 * rate)
    chosen = sorted(rng.permutation(epochs)[: round(share * epochs)])
    polarity = np.where(np.arange(uv.shape[0]) % 2 == 0, 1.0, -1.0)
    pulse = np.hanning(int(0.2 * rate))
    out = uv.copy()
    for epoch in chosen:
        start = int((2 * epoch + rng.uniform(0.3, 1.5)) * rate)
        out[:, start : start + len(pulse)] += 500.0 * polarity[:, None] * pulse[None, :]
    return out


def _with_artefact_sources(uv: np.ndarray, names: Sequence[str], rate: int = RATE) -> np.ndarray:
    """M09b target: blink-like frontal pulses (150 µV, mainly Fp1/Fp2/AF3/AF4) and muscle bursts
    (20–100 Hz, 30 µV, around T7 and T8)."""
    rng = np.random.default_rng(11)
    positions = _positions(names)
    n = uv.shape[1]
    out = uv.copy()
    frontal = _blob(positions, (positions[names.index("Fp1")] + positions[names.index("Fp2")]) / 2, 0.03)
    blinks = np.zeros(n)
    shape = np.hanning(int(0.4 * rate))
    start = rate
    while start + len(shape) < n:
        blinks[start : start + len(shape)] += shape
        start += int(rng.uniform(2.0, 6.0) * rate)
    out += 150.0 * frontal[:, None] * blinks[None, :]
    band = butter(4, [20, 100], btype="bandpass", fs=rate, output="sos")
    smooth = np.hanning(25) / np.hanning(25).sum()
    for centre in ("T7", "T8"):
        pattern = _blob(positions, positions[names.index(centre)], 0.04)
        noise = sosfiltfilt(band, rng.normal(0.0, 1.0, n))
        noise /= noise.std()
        gate = np.zeros(n)
        start = 0
        while start < n:
            length = int(rng.uniform(0.5, 2.0) * rate)
            if rng.uniform() < 0.5:
                gate[start : start + length] = 1.0
            start += length
        out += 30.0 * pattern[:, None] * (np.convolve(gate, smooth, mode="same") * noise)[None, :]
    return out


# --- select_segments ---------------------------------------------------------------------------------------


def test_short_recording_is_used_whole() -> None:
    """D-04: a recording up to segments × segment_s is used whole."""
    assert select_segments(600.0, "sample", 10, 60.0) == [(0.0, 600.0)]
    assert select_segments(300.0, "sample", 10, 60.0) == [(0.0, 300.0)]
    assert select_segments(61.5, "sample", 10, 60.0) == [(0.0, 61.5)]


def test_long_recording_gives_centred_segments() -> None:
    """D-04: 10 × 60 s, each centred in one of 10 equal parts."""
    chosen = select_segments(1200.0, "sample", 10, 60.0)
    assert chosen == [(30.0 + 120.0 * index, 60.0) for index in range(10)]
    for index, (start, length) in enumerate(chosen):
        assert start + length / 2 == pytest.approx((index + 0.5) * 120.0)
    other = select_segments(1000.0, "sample", 4, 30.0)
    assert other == [(110.0, 30.0), (360.0, 30.0), (610.0, 30.0), (860.0, 30.0)]
    just_over = select_segments(600.5, "sample", 10, 60.0)
    assert len(just_over) == 10 and all(0 <= s and s + d <= 600.5 for s, d in just_over)


def test_mode_full_uses_the_whole_recording() -> None:
    assert select_segments(7200.0, "full", 10, 60.0) == [(0.0, 7200.0)]


# --- SampleResult.describe ---------------------------------------------------------------------------------


def test_describe_lists_the_sample() -> None:
    """KONZEPT 1.5: the sample as reported in results.json ("sample") and the report."""
    measured = MethodResult(state="measured", value=0.1)
    result = SampleResult(
        mode="sample",
        segments=((30.0, 60.0), (150.0, 60.0)),
        seed=7,
        channels=20,
        positions="standard_montage",
        notch_hz=(60.0, 120.0),
        m06=measured,
        m09a=measured,
        m09b=measured,
        excluded=("EXG1", "EXG2"),
        positions_unused={"sidecar": "frame_unsupported"},
    )
    assert result.describe() == {
        "mode": "sample",
        "segments": [{"start_s": 30.0, "duration_s": 60.0}, {"start_s": 150.0, "duration_s": 60.0}],
        "seed": 7,
        "channels": 20,
        "excluded_channels": ["EXG1", "EXG2"],
        "positions": "standard_montage",
        "positions_unused": {"sidecar": "frame_unsupported"},
        "resample_hz": 250.0,
        "band_hz": [1.0, 100.0],
        "notch_hz": [60.0, 120.0],
        "epoch_s": 2.0,
    }


def test_segments_are_reported_in_recording_time(tmp_path: Path) -> None:
    """A-12, A-77: segment starts follow the record onsets of EDF+D, not the sample count."""
    path = tmp_path / "gap.edf"
    onsets = tuple(range(600)) + tuple(range(700, 1300))  # a gap of 100 s after 600 s of data
    gen_fixtures.write_edf(path, sfreq=200, seconds=1200, plus="D", record_onsets=onsets, label_prefix="")
    result = _measure(path)  # 8 channels: the methods do not run, the sample is still reported
    assert result.m06.reason == "quality.too_few_channels"
    starts = [30.0 + 120.0 * index for index in range(10)]
    expected = [start if start < 600 else start + 100.0 for start in starts]
    assert result.describe()["segments"] == [{"start_s": s, "duration_s": 60.0} for s in expected]
    assert result.mode == "sample" and result.seed == SETTINGS.seed
    full = _measure(path, mode="full").describe()
    assert full["mode"] == "full" and full["segments"] == [{"start_s": 0.0, "duration_s": 1200.0}]


@pytest.mark.parametrize(("line_hz", "notch"), [(50.0, [50.0, 100.0]), (60.0, [60.0, 120.0])])
def test_notch_at_line_frequency_and_harmonic_below_125_hz(
    tmp_path: Path, line_hz: float, notch: list[float]
) -> None:
    """A-19: notch at f0 and its harmonic below the Nyquist frequency of 250 Hz."""
    path = tmp_path / "short.edf"
    gen_fixtures.write_edf(path, sfreq=250, seconds=61, label_prefix="")
    assert _measure(path, line_hz=line_hz).describe()["notch_hz"] == notch


# --- preconditions (A-60, A-79) ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "sfreq", "count", "overrides", "reason", "details"),
    [
        (59, 250, 16, {}, "quality.too_short", {"seconds": 59.0, "min_seconds": 60.0}),
        (100, 250, 16, {"min_seconds": 120.0}, "quality.too_short", {"seconds": 100.0, "min_seconds": 120.0}),
        (61, 199, 16, {}, "quality.rate_too_low", {"rate_hz": 199.0, "min_rate_hz": 200.0}),
        (61, 128, 16, {}, "quality.rate_too_low", {"rate_hz": 128.0, "min_rate_hz": 200.0}),
        (61, 250, 15, {}, "quality.too_few_channels", {"channels": 15, "min_channels": 16}),
        (61, 250, 16, {"min_channels": 32}, "quality.too_few_channels", {"channels": 16, "min_channels": 32}),
        (59, 128, 8, {}, "quality.too_short", {"seconds": 59.0, "min_seconds": 60.0}),
    ],
)
def test_preconditions_make_all_methods_not_checkable(
    tmp_path: Path,
    seconds: int,
    sfreq: int,
    count: int,
    overrides: dict[str, Any],
    reason: str,
    details: dict[str, Any],
) -> None:
    """At least 60 s, 200 Hz (1–100 Hz band) and 16 EEG channels for M06, M09a and M09b."""
    labels = CAP_16[:count]
    path = tmp_path / "pre.edf"
    gen_fixtures.write_edf(path, sfreq=sfreq, seconds=seconds, labels=labels, label_prefix="")
    result = _measure(path, **overrides)
    expected = MethodResult(state="not_checkable", reason=reason, details=details)
    assert (result.m06, result.m09a, result.m09b) == (expected, expected, expected)
    assert result.channels == count and result.positions == "none"
    assert result.describe()["segments"] == [{"start_s": 0.0, "duration_s": float(seconds)}]


def test_no_eeg_channels(tmp_path: Path) -> None:
    path = tmp_path / "polygraphy.edf"
    gen_fixtures.write_edf(path, sfreq=250, seconds=61, labels=("ECG", "EMG chin"), label_prefix="")
    result = _measure(path)
    missing = MethodResult(state="not_checkable", reason="signal.no_eeg_channels")
    assert (result.m06, result.m09a, result.m09b) == (missing, missing, missing)
    assert result.channels == 0 and result.segments == ()


def test_limits_are_inclusive_and_m09b_counts_good_channels(tmp_path: Path) -> None:
    """Exactly 60 s, 200 Hz and 16 channels are enough; one flat channel leaves 15 good channels, fewer
    than M09b needs (A-79), while M06 and M09a are measured."""
    uv = eeg_like(CAP_16, 60, seed=3, rate=200, spread=0.06)
    uv[CAP_16.index("C3")] = 25.0
    result = _measure(_write_edf(tmp_path / "flat.edf", CAP_16, uv, rate=200))
    assert result.channels == 16 and result.positions == "standard_montage"
    assert result.m06.state == "measured" and "C3" in result.m06.details["bad_channels"]
    good = 16 - len(result.m06.details["bad_channels"])
    assert result.m09a.state == "measured" and result.m09a.details["epochs"] == 30
    assert result.m09b == MethodResult(
        state="not_checkable",
        reason="quality.too_few_channels",
        details={"channels": good, "min_channels": 16},
    )


# --- montage sources in measure_sample (A-60, A-79) --------------------------------------------------------


@pytest.fixture(scope="module")
def small(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """64 s at 250 Hz: 20 cap channels plus EXG1..EXG4, and the same 20 signals under non-standard names."""
    folder = tmp_path_factory.mktemp("small")
    cap = eeg_like(CAP_20, 64, seed=21, spread=0.06)
    return {
        "external": _write_edf(folder / "external.edf", CAP_20 + EXTERNAL, _with_external(cap, seed=22)),
        "unnamed": _write_edf(folder / "unnamed.edf", [f"Ch{i:02d}" for i in range(1, 21)], cap),
    }


@pytest.fixture(scope="module")
def baseline(small: dict[str, Path]) -> SampleResult:
    """The external-electrode recording; the electrodes.tsv of the data set was not usable."""
    return _measure(small["external"], sidecar_reason="frame_unsupported")


def test_channels_without_template_position_are_left_out(baseline: SampleResult) -> None:
    """A-79: 20 standard channels and EXG1..EXG4 -> template montage for the 20, the EXG channels listed."""
    described = baseline.describe()
    assert described["positions"] == "standard_montage"
    assert described["channels"] == 20
    assert described["excluded_channels"] == list(EXTERNAL)
    assert described["positions_unused"] == {"sidecar": "frame_unsupported"}
    assert described["segments"] == [{"start_s": 0.0, "duration_s": 64.0}]
    assert all(m.state == "measured" for m in (baseline.m06, baseline.m09a, baseline.m09b))
    assert baseline.m06.details["channels"] == 20 and baseline.m06.details["ransac"] is True
    assert baseline.m09a.details["epochs"] == 32
    assert baseline.m09b.details["components"] == 19  # at most one less than the channels


def test_sidecar_positions_win_over_the_template(
    small: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A-60: electrodes.tsv > header > template; with positions for all 24 channels nothing is left out."""
    found = _positions(CAP_20 + ("TP9", "TP10", "FT9", "FT10"))
    sidecar: dict[str, Position] = {
        name: (float(x) * 1.05, float(y) * 1.05, float(z) * 1.05)
        for name, (x, y, z) in zip(CAP_20 + EXTERNAL, found, strict=True)
    }
    used: list[Mapping[str, Position] | None] = []
    prepared = sample_module._prepared

    def spy(source: Any, chosen: Any, indices: Any, positions: Any, notch: Any) -> Any:
        used.append(positions)
        return prepared(source, chosen, indices, positions, notch)

    monkeypatch.setattr(sample_module, "_prepared", spy)  # observes the montage, changes nothing
    result = _measure(small["external"], sidecar=sidecar)
    assert result.positions == "sidecar" and result.channels == 24 and result.excluded == ()
    assert result.positions_unused == {}
    assert used == [sidecar]
    assert result.m06.state == "measured" and result.m06.details["channels"] == 24


def test_without_positions_m06_runs_without_ransac(small: dict[str, Path]) -> None:
    """Non-standard names and no sidecar: M06 without RANSAC, M09a/M09b not_checkable (A-60)."""
    result = _measure(small["unnamed"])
    assert result.positions == "none" and result.channels == 20 and result.excluded == ()
    assert result.m06.state == "measured" and result.m06.details["ransac"] is False
    assert result.m06.details["channels"] == 20
    no_positions = MethodResult(state="not_checkable", reason="quality.no_positions")
    assert result.m09a == no_positions and result.m09b == no_positions


def test_60_hz_mains_runs_with_the_120_hz_notch(small: dict[str, Path]) -> None:
    """A-19 with 60 Hz mains: the harmonic at 120 Hz is below the Nyquist frequency and is filtered."""
    result = _measure(small["unnamed"], line_hz=60.0)
    assert result.notch_hz == (60.0, 120.0)
    assert result.m06.state == "measured"


# --- failing methods and determinism -----------------------------------------------------------------------


class InjectedFailure(RuntimeError):
    """Raised by a patched method step."""


def _fail(*args: Any, **kwargs: Any) -> Any:
    raise InjectedFailure("injected")


@pytest.mark.parametrize(
    ("failing", "target"),
    [
        ("m06", "pyprep.find_noisy_channels.NoisyChannels"),
        ("m09a", "autoreject.AutoReject"),
        ("m09b", "mne.preprocessing.ICA.fit"),
    ],
)
def test_a_failing_method_is_not_checkable(
    small: dict[str, Path],
    baseline: SampleResult,
    monkeypatch: pytest.MonkeyPatch,
    failing: str,
    target: str,
) -> None:
    """A-60: a raising method gives quality.method_failed with the exception's class name; the others are
    measured as without the failure. A failing M06 leaves the bad channels unknown, so M09a/M09b are
    not_checkable (they need the average reference without them, A-19, A-79)."""
    assert baseline.m06.details["bad_channels"] == []  # so M09 sees the same channels without M06
    monkeypatch.setattr(target, _fail)
    result = _measure(small["external"], sidecar_reason="frame_unsupported")
    failed = MethodResult(
        state="not_checkable", reason="quality.method_failed", details={"error_type": "InjectedFailure"}
    )
    assert getattr(result, failing) == failed
    unknown = MethodResult(state="not_checkable", reason="quality.bad_channels_unknown")
    for other in ("m06", "m09a", "m09b"):
        if other != failing:
            expected = unknown if failing == "m06" else getattr(baseline, other)
            assert getattr(result, other) == expected, other
    assert result.describe() == baseline.describe()


def test_same_seed_gives_the_same_result(small: dict[str, Path], baseline: SampleResult) -> None:
    """A-11, NG-N03: the sample metrics are deterministic for a seed."""
    again = _measure(small["external"], sidecar_reason="frame_unsupported")
    assert again == baseline


# --- detection (32 channels, 250 Hz, 300 s: the whole recording is the sample) ----------------------------


def detection_results(folder: Path) -> dict[str, SampleResult]:
    """The real computation on the clean recording and on each artefact variant, one process per job."""
    clean = eeg_like(CAP_32, 300, seed=7)
    variants = {
        "clean": clean,
        "bad_channels": _with_bad_channels(clean, CAP_32),
        "transients_20": _with_transients(clean, 0.2),
        "transients_50": _with_transients(clean, 0.5),
        "artefact_sources": _with_artefact_sources(clean, CAP_32),
    }
    jobs = []
    for name, uv in variants.items():
        path = _write_edf(folder / f"{name}.edf", CAP_32, uv)
        jobs.append(QualityJob(path=str(path), recording=_recording(path), settings=SETTINGS, stream=False))
    found: dict[str, SampleResult] = {}
    for name, result in zip(variants, compute_all(jobs, workers=len(jobs)), strict=True):
        assert result.reason is None and result.sample is not None, (name, result)
        found[name] = result.sample
    return found


@pytest.fixture(scope="module")
def detection(tmp_path_factory: pytest.TempPathFactory) -> dict[str, SampleResult]:
    return detection_results(tmp_path_factory.mktemp("detection"))


def test_whole_recording_sample(detection: dict[str, SampleResult]) -> None:
    """D-04: 300 s is used whole; template positions for all 32 standard channels."""
    assert detection["clean"].describe() == {
        "mode": "sample",
        "segments": [{"start_s": 0.0, "duration_s": 300.0}],
        "seed": SETTINGS.seed,
        "channels": 32,
        "excluded_channels": [],
        "positions": "standard_montage",
        "positions_unused": {},
        "resample_hz": 250.0,
        "band_hz": [1.0, 100.0],
        "notch_hz": [50.0, 100.0],
        "epoch_s": 2.0,
    }


def test_m06_detects_bad_channels(detection: dict[str, SampleResult]) -> None:
    """M06: 2 noisy, 1 flat and 1 unrelated channel of 32 are found, at most one false positive; the clean
    recording has at most one bad channel."""
    clean = detection["clean"].m06
    assert clean.state == "measured" and clean.value is not None and clean.value <= 1 / 32
    bad = detection["bad_channels"].m06
    assert bad.state == "measured" and bad.value is not None
    assert set(NOISY + (FLAT, UNRELATED)) <= set(bad.details["bad_channels"])
    assert 4 / 32 <= bad.value <= 5 / 32
    assert bad.details["ransac"] is True


def test_m09a_follows_the_share_of_artefact_epochs(detection: dict[str, SampleResult]) -> None:
    """M09a: 500 µV transients in a share p of the 2-s epochs -> about p rejected, non-decreasing in p."""
    shares = {0.0: "clean", 0.2: "transients_20", 0.5: "transients_50"}
    values: dict[float, float] = {}
    for share, name in shares.items():
        method = detection[name].m09a
        assert method.state == "measured" and method.value is not None, name
        assert method.details["epochs"] == 150
        values[share] = method.value
    assert values[0.0] <= 0.05
    assert values[0.0] <= values[0.2] <= values[0.5]
    for share in (0.2, 0.5):
        assert 0.8 * share <= values[share] <= share + 0.1, (share, values[share])


def test_m09b_rises_with_artefact_sources(detection: dict[str, SampleResult]) -> None:
    """M09b: blink-like and muscle sources raise the share of non-brain ICA components."""
    clean, artefacts = detection["clean"].m09b, detection["artefact_sources"].m09b
    assert clean.state == "measured" and artefacts.state == "measured"
    assert clean.value is not None and artefacts.value is not None
    assert artefacts.value > clean.value
    # the rise comes from artefact classes, not from components moving to "other"
    assert artefacts.details["share_without_other"] > clean.details["share_without_other"]
    assert {"eye blink", "muscle artifact"} & set(artefacts.details["labels"])


class _Noisy:
    """The NoisyChannels attributes that pyprep's RANSAC preconditions read."""

    def __init__(self, usable: int, correlation: int = 0, deviation: int = 0, dropout: int = 0) -> None:
        self.ch_names_new = np.array([f"C{i}" for i in range(usable)])
        names = [f"C{i}" for i in range(usable)]
        self.bad_by_correlation = names[:correlation]
        self.bad_by_deviation = names[correlation : correlation + deviation]
        self.bad_by_dropout = names[correlation + deviation : correlation + deviation + dropout]


@pytest.mark.parametrize(
    ("noisy", "possible"),
    [
        (_Noisy(13), False),  # round(0.25 · 13) = 3 predictors: pyprep refuses ("too few channels")
        (_Noisy(14), True),  # round(0.25 · 14) = 4 (numpy rounds half to even), 14 good >= 5
        (_Noisy(16, correlation=11), True),  # 4 predictors, 5 good channels left
        (_Noisy(16, correlation=10, deviation=1, dropout=1), False),  # 4 good < 5 ("too many noisy channels")
        (_Noisy(0), False),  # every channel flat or NaN
    ],
)
def test_ransac_runs_only_when_pyprep_accepts_the_channels(noisy: _Noisy, possible: bool) -> None:
    """M06 (A-79): RANSAC follows pyprep's own preconditions instead of failing the whole metric."""
    assert sample_module._ransac_possible(noisy) is possible


def test_onnxruntime_telemetry_is_switched_off_before_iclabel(
    small: dict[str, Path], baseline: SampleResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NG-N01, CON-04 (KONZEPT 3): ICLabel runs through onnxruntime only after its telemetry is disabled."""
    import mne_icalabel
    import onnxruntime

    events: list[str] = []
    disable = onnxruntime.disable_telemetry_events
    label = mne_icalabel.label_components

    def spy_disable() -> None:
        events.append("disable")
        disable()

    def spy_label(*args: Any, **kwargs: Any) -> Any:
        events.append("label")
        return label(*args, **kwargs)

    monkeypatch.setattr(onnxruntime, "disable_telemetry_events", spy_disable)
    monkeypatch.setattr(mne_icalabel, "label_components", spy_label)
    result = _measure(small["external"], sidecar_reason="frame_unsupported")
    assert result.m09b == baseline.m09b and result.m09b.state == "measured"
    assert events == ["disable", "label"]
