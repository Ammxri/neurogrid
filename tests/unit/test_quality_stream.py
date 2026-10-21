"""Streaming pass of the signal quality metrics: M07 line noise, M08 flat line and clipping, signal hash
(NG-F07, KONZEPT 1.5, A-18, A-21, A-47).

Detection tests write synthetic EDF/BDF/BrainVision/FIF files with fixed seeds into tmp_path and run the
production adapter, signal source and kernels on them. The in-memory source below only serves the unit tests
of the kernels (exact sines, tolerances, ranges, blocks).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from pathlib import Path

import mne
import numpy as np
import pytest

import gen_fixtures
from neurogrid.checks.quality import CALIBRATED
from neurogrid.io import ADAPTERS
from neurogrid.quality.source import SignalChannel, open_signals
from neurogrid.quality.stream import (
    BLOCK_WINDOWS,
    HASH_VERSION,
    MAX_RANGES,
    ChannelStream,
    Ranges,
    StreamResult,
    _longest_runs,
    finite,
    measure_stream,
    other_line_frequency,
)

LINE_THRESHOLD = CALIBRATED["line_noise"]  # calibrated max_ratio of CORE-M07-01 (A-20)
EDF_LIMITS = (-32768, 32767)
BDF_LIMITS = (-(1 << 23), (1 << 23) - 1)
LABELS = (
    "Fp1", "Fp2", "F7", "F3", "Fz", "F4", "F8", "FC5", "FC1", "FC2", "FC6", "T7", "C3", "Cz", "C4", "T8",
    "CP5", "CP1", "CP2", "CP6", "P7", "P3", "Pz", "P4", "P8", "PO9", "O1", "Oz", "O2", "PO10", "AF7", "AF8",
)  # fmt: skip
HUM_CHANNELS = frozenset(range(0, 32, 4))  # 8 of 32 channels carry the line hum
STEP_0_1_UV = (-3276.8, 3276.7)  # physical range of a 16-bit EDF in which one digital step is 0.1 µV


class ArraySource:
    """In-memory SignalSource in µV (float64); records every block read for the block tests."""

    def __init__(
        self,
        data: Sequence[np.ndarray],
        rate: float | Sequence[float],
        *,
        method: str = "plateau",
        lsb_uv: float | None = None,
    ) -> None:
        rates = [float(rate)] * len(data) if isinstance(rate, int | float) else [float(r) for r in rate]
        self._data = [np.asarray(row, dtype=np.float64) for row in data]
        self.clipping_method = method
        self.channels: tuple[SignalChannel, ...] = tuple(
            SignalChannel(name=f"C{i}", rate_hz=r, lsb_uv=lsb_uv, digital_limits=None, n_samples=len(row))
            for i, (row, r) in enumerate(zip(self._data, rates, strict=True))
        )
        self.reads: list[tuple[tuple[int, ...], int, int]] = []

    def read(self, index: int, start: int, stop: int) -> np.ndarray:
        return self._data[index][start:stop]

    def read_digital(self, index: int, start: int, stop: int) -> np.ndarray | None:
        return None

    def read_many(self, indices: Sequence[int], start: int, stop: int) -> np.ndarray:
        self.reads.append((tuple(indices), start, stop))
        return np.vstack([self._data[i][start:stop] for i in indices])

    def positions(self) -> dict[str, tuple[float, float, float]]:
        return {}

    def time_s(self, index: int, sample: int) -> float:
        return sample / self.channels[index].rate_hz

    def close(self) -> None:
        pass


# --- helpers ------------------------------------------------------------------------------------------


def _eeg_like(rng: np.random.Generator, rate: int, seconds: int) -> np.ndarray:
    """EEG-like µV signal: 1/f noise (SD 8 µV) plus a slowly modulated 10-Hz alpha rhythm (8 µV).

    Amplitude about ±20 µV: RMS about 10 µV, 1st-99th percentile spread about 45 µV.
    """
    n = rate * seconds
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    spectrum[0] = 0.0
    spectrum[1:] /= np.sqrt(freqs[1:])
    pink = np.fft.irfft(spectrum, n)
    pink *= 8.0 / pink.std()
    t = np.arange(n) / rate
    envelope = 1.0 + 0.3 * np.sin(2 * np.pi * 0.1 * t + rng.uniform(0.0, 2 * np.pi))
    alpha = 8.0 * envelope * np.sin(2 * np.pi * 10.0 * t + rng.uniform(0.0, 2 * np.pi))
    return np.asarray(pink + alpha)


def _sine(rate: float, seconds: float, hz: float, amplitude: float, phase: float = 0.0) -> np.ndarray:
    t = np.arange(round(rate * seconds)) / rate
    return np.asarray(amplitude * np.sin(2 * np.pi * hz * t + phase))


def _to_digital(
    microvolts: np.ndarray, *, bdf: bool = False, physical: tuple[float, float] = (-500.0, 500.0)
) -> np.ndarray:
    low, high = BDF_LIMITS if bdf else EDF_LIMITS
    scale = (high - low) / (physical[1] - physical[0])
    return np.clip(np.round((microvolts - physical[0]) * scale + low), low, high).astype(np.int64)


def _write_edf(
    path: Path,
    digital: np.ndarray,
    rate: int,
    *,
    bdf: bool = False,
    plus: str = "",
    onsets: tuple[int, ...] | None = None,
    physical: tuple[float, float] = (-500.0, 500.0),
) -> Path:
    """gen_fixtures.write_edf for header and record layout, then ``digital`` (channels x samples) as the data
    of the EEG signals, so that every digital value is exactly the intended one."""
    channels, samples = digital.shape
    seconds = samples // rate
    assert seconds * rate == samples
    gen_fixtures.write_edf(
        path,
        sfreq=rate,
        seconds=seconds,
        labels=LABELS[:channels],
        bdf=bdf,
        plus=plus,
        record_onsets=onsets,
        physical=physical,
    )
    width = 3 if bdf else 2
    header = 256 * (channels + (2 if plus else 1))
    data_bytes = channels * rate * width
    record = data_bytes + (gen_fixtures.ANNOTATION_SAMPLES * width if plus else 0)
    if bdf:
        raw = digital.astype("<i4").view(np.uint8).reshape(channels, samples, 4)[:, :, :3]
    else:
        raw = digital.astype("<i2").view(np.uint8).reshape(channels, samples, 2)
    by_record = raw.reshape(channels, seconds, rate * width).transpose(1, 0, 2).reshape(seconds, data_bytes)
    content = bytearray(path.read_bytes())
    assert len(content) == header + seconds * record
    body = np.frombuffer(content, dtype=np.uint8, offset=header).reshape(seconds, record)
    body[:, :data_bytes] = by_record
    path.write_bytes(bytes(content))
    return path


def _stream(path: Path, line_hz: float = 50.0) -> StreamResult:
    """measure_stream on a file through the production adapter and signal source."""
    recording = ADAPTERS[path.suffix].read(path, recording_id="rec-1", relative_path=path.name)
    source = open_signals(path, recording)
    try:
        return measure_stream(source, line_hz)
    finally:
        source.close()


def _ratio(channel: ChannelStream) -> float:
    assert channel.line_state == "measured" and channel.line_ratio is not None, channel
    return channel.line_ratio


def _other(channel: ChannelStream) -> float:
    assert channel.line_state == "measured" and channel.other_ratio is not None, channel
    return channel.other_ratio


def _starts(ranges: Ranges) -> list[float]:
    return [begin for begin, _ in ranges.ranges]


# --- kernels --------------------------------------------------------------------------------------------


def test_other_line_frequency_and_finite() -> None:
    """A-47: the other line frequency of 50 Hz is 60 Hz and vice versa; finite() drops NaN and infinity."""
    assert other_line_frequency(50.0) == 60.0
    assert other_line_frequency(60.0) == 50.0
    assert finite(0.25) == 0.25
    assert finite(None) is None and finite(float("nan")) is None and finite(float("inf")) is None


def test_longest_runs_per_row() -> None:
    """M08 plateau: the longest run of True per window."""
    mask = np.array(
        [
            [True, True, False, True, True, True],
            [False] * 6,
            [True] * 6,
            [True, False, True, False, True, False],
        ]
    )
    assert _longest_runs(mask).tolist() == [3, 0, 6, 1]


def test_m07_ratio_of_pure_sines_is_exact() -> None:
    """M07: P(f0 ± 1 Hz) / P(1-40 Hz) from the summed Welch bins. Whole-Hz sines fall on bins of the 2-s
    periodic Hann window, so equal amplitudes give exactly 1; a 45-Hz sine is in neither band, a DC offset is
    removed with the mean, a 53-Hz sine is outside f0 ± 1 Hz."""
    rate, seconds = 250, 120
    alpha = _sine(rate, seconds, 10.0, 10.0)
    rows = [
        alpha + _sine(rate, seconds, 50.0, 10.0),
        alpha + _sine(rate, seconds, 50.0, 5.0),
        alpha + _sine(rate, seconds, 50.0, 10.0) + _sine(rate, seconds, 45.0, 10.0) + 1000.0,
        alpha + _sine(rate, seconds, 53.0, 10.0),
        alpha + _sine(rate, seconds, 60.0, 10.0, phase=0.3),
    ]
    result = measure_stream(ArraySource(rows, rate), 50.0)
    assert result.line_frequency_hz == 50.0 and result.other_frequency_hz == 60.0
    ratios = [_ratio(ch) for ch in result.channels]
    assert ratios[0] == pytest.approx(1.0, rel=1e-9)
    assert ratios[1] == pytest.approx(0.25, rel=1e-9)
    assert ratios[2] == pytest.approx(1.0, rel=1e-9)
    assert ratios[3] == pytest.approx(0.0, abs=1e-12)
    assert ratios[4] == pytest.approx(0.0, abs=1e-12)
    assert _other(result.channels[0]) == pytest.approx(0.0, abs=1e-12)
    assert _other(result.channels[4]) == pytest.approx(1.0, rel=1e-9)
    at_60 = measure_stream(ArraySource(rows, rate), 60.0)
    assert at_60.other_frequency_hz == 50.0
    assert _ratio(at_60.channels[4]) == pytest.approx(1.0, rel=1e-9)
    assert _other(at_60.channels[0]) == pytest.approx(1.0, rel=1e-9)


@pytest.mark.parametrize(("line_hz", "below", "at_limit"), [(50.0, 100.0, 102.0), (60.0, 120.0, 122.0)])
def test_m07_not_applicable_below_twice_the_line_band(line_hz: float, below: float, at_limit: float) -> None:
    """A-18: M07 is not applicable when the rate is below 2·(f0 + 1); at exactly that rate it is measured.
    M08 still judges the windows of the low-rate channel."""
    rng = np.random.default_rng(70)
    seconds = 20
    rows = [rng.normal(0.0, 10.0, round(rate * seconds)) for rate in (below, at_limit)]
    result = measure_stream(ArraySource(rows, [below, at_limit]), line_hz)
    low, limit = result.channels
    assert (low.line_state, low.line_reason) == ("not_applicable", "quality.rate_below_line_band")
    assert low.line_ratio is None and low.other_ratio is None
    assert low.windows == seconds
    assert limit.line_state == "measured" and limit.line_reason is None
    assert 0.0 <= _ratio(limit) < 1.0


def test_m07_all_zero_channel_has_no_signal_power() -> None:
    """M07: a channel of zeros has no power in 1-40 Hz: not_checkable with quality.no_signal_power. Blocks
    without power are left out of the median, so zeros in one block do not hide the others."""
    rate, seconds = 256, 180
    zeros = np.zeros(rate * seconds)
    signal = _sine(rate, seconds, 10.0, 10.0) + _sine(rate, seconds, 50.0, 10.0)
    first_block_zero = signal.copy()
    first_block_zero[: BLOCK_WINDOWS * rate] = 0.0
    result = measure_stream(ArraySource([zeros, first_block_zero], rate), 50.0)
    empty, partly = result.channels
    assert (empty.line_state, empty.line_reason) == ("not_checkable", "quality.no_signal_power")
    assert empty.line_ratio is None and empty.other_ratio is None
    assert empty.flat.windows == seconds  # M08 still sees the flat line
    assert _ratio(partly) == pytest.approx(1.0, rel=1e-9)


@pytest.mark.parametrize("value", [1234, 15000, -12345])
def test_m07_constant_channel_has_no_signal_power(tmp_path: Path, value: int) -> None:
    """M07: a channel stuck at one digital value (e.g. a disconnected electrode) has no power in 1-40 Hz after
    the mean is removed, so it is not_checkable with quality.no_signal_power, whatever the constant is; a
    ratio of rounding residue must not be reported as measured."""
    rate, seconds = 256, 120
    rng = np.random.default_rng(72)
    digital = _to_digital(np.vstack([_eeg_like(rng, rate, seconds), np.zeros(rate * seconds)]))
    digital[1] = value
    result = _stream(_write_edf(tmp_path / "rec.edf", digital, rate))
    stuck = result.channels[1]
    assert stuck.flat.windows == seconds
    assert (stuck.line_state, stuck.line_reason, stuck.line_ratio) == (
        "not_checkable",
        "quality.no_signal_power",
        None,
    )
    assert result.channels[0].line_state == "measured"


# --- M07 detection --------------------------------------------------------------------------------------


def _hum_recording(rate: int, hum_hz: float, seconds: int = 180) -> np.ndarray:
    """32 EEG-like channels; the channels in HUM_CHANNELS carry a 10-µV sine at ``hum_hz``."""
    rng = np.random.default_rng(7000 + rate)
    rows = []
    for index in range(32):
        signal = _eeg_like(rng, rate, seconds)
        if index in HUM_CHANNELS:
            signal = signal + _sine(rate, seconds, hum_hz, 10.0, phase=rng.uniform(0.0, 2 * np.pi))
        rows.append(signal)
    return np.vstack(rows)


@pytest.fixture(scope="module")
def hum_file(tmp_path_factory: pytest.TempPathFactory) -> Callable[[int, float], Path]:
    """EDF files of _hum_recording, written once per (rate, hum frequency)."""
    made: dict[tuple[int, float], Path] = {}

    def make(rate: int, hum_hz: float) -> Path:
        if (rate, hum_hz) not in made:
            path = tmp_path_factory.mktemp("m07") / f"hum_{rate}_{hum_hz:.0f}.edf"
            made[rate, hum_hz] = _write_edf(path, _to_digital(_hum_recording(rate, hum_hz)), rate)
        return made[rate, hum_hz]

    return make


@pytest.mark.parametrize("rate", [250, 500])
@pytest.mark.parametrize("hum_hz", [50.0, 60.0])
def test_m07_detects_line_hum_on_exactly_the_hum_channels(
    hum_file: Callable[[int, float], Path], rate: int, hum_hz: float
) -> None:
    """M07 detection target: 32 channels, 180 s; the 8 channels with a 10-µV hum at the documented line
    frequency exceed the calibrated 0.407669, every one of the 24 clean channels stays below it."""
    result = _stream(hum_file(rate, hum_hz), line_hz=hum_hz)
    assert len(result.channels) == 32
    hum = [_ratio(ch) for i, ch in enumerate(result.channels) if i in HUM_CHANNELS]
    clean = [_ratio(ch) for i, ch in enumerate(result.channels) if i not in HUM_CHANNELS]
    assert len(hum) == 8 and len(clean) == 24
    assert min(hum) > LINE_THRESHOLD, hum
    assert max(clean) < LINE_THRESHOLD, clean


@pytest.mark.parametrize("rate", [250, 500])
def test_m07_other_line_frequency_fits_better_when_documented_wrongly(
    hum_file: Callable[[int, float], Path], rate: int
) -> None:
    """A-47 detection target: 50-Hz hum measured with line_hz = 60: on every hum channel the ratio at the
    other frequency (50 Hz) is more than twice the ratio at the documented 60 Hz; the clean channels stay
    below the threshold at 60 Hz."""
    result = _stream(hum_file(rate, 50.0), line_hz=60.0)
    assert result.line_frequency_hz == 60.0 and result.other_frequency_hz == 50.0
    for index, channel in enumerate(result.channels):
        if index in HUM_CHANNELS:
            assert _other(channel) > 2 * _ratio(channel), channel
        assert _ratio(channel) < LINE_THRESHOLD, channel


def test_m07_02_flags_a_wrongly_documented_line_frequency_by_the_channel_medians(tmp_path: Path) -> None:
    """A-47 at rule level: CORE-M07-02 compares the channel medians. With 50-Hz hum on every channel and
    line_hz = 60, the median at 50 Hz is more than min_factor (2.0) times the median at 60 Hz."""
    import statistics

    rng = np.random.default_rng(91)
    rate = 250
    digital = np.vstack(
        [
            _to_digital(_eeg_like(rng, rate, 120) + _sine(rate, 120, 50.0, 10.0, rng.uniform(0, 6.3)))
            for _ in LABELS[:16]
        ]
    )
    result = _stream(_write_edf(tmp_path / "hum.edf", digital, rate), line_hz=60.0)
    documented = statistics.median(_ratio(channel) for channel in result.channels)
    other = statistics.median(_other(channel) for channel in result.channels)
    assert other > 2.0 * documented, (other, documented)


def test_m07_hum_in_one_of_three_blocks_does_not_dominate(tmp_path: Path) -> None:
    """M07: the channel value is the median over the 60-s blocks. Hum in 1 of 3 blocks stays at the level of
    a clean channel; hum in 2 of 3 blocks or throughout is detected."""
    rate, seconds = 250, 180
    block = BLOCK_WINDOWS * rate
    rng = np.random.default_rng(71)
    rows = [_eeg_like(rng, rate, seconds) for _ in range(4)]
    hum = _sine(rate, seconds, 50.0, 10.0)
    rows[1][block : 2 * block] += hum[block : 2 * block]
    rows[2][block:] += hum[block:]
    rows[3] += hum
    result = _stream(_write_edf(tmp_path / "rec.edf", _to_digital(np.vstack(rows)), rate))
    clean, one_block, two_blocks, throughout = (_ratio(ch) for ch in result.channels)
    assert one_block < LINE_THRESHOLD
    assert one_block < 0.05 and clean < 0.05  # the hum block is outvoted, not averaged in
    assert two_blocks > LINE_THRESHOLD
    assert throughout > LINE_THRESHOLD


# --- M08 on EDF/BDF (method "range") ------------------------------------------------------------------

M08_RATE, M08_SECONDS = 256, 100


def _m08_digital(bdf: bool) -> np.ndarray:
    """10 EEG-like channels, 100 s; channel 0 clean, the others with one inserted problem each."""
    rng = np.random.default_rng(81)
    low, high = BDF_LIMITS if bdf else EDF_LIMITS
    rows = np.vstack([_eeg_like(rng, M08_RATE, M08_SECONDS) for _ in range(10)])
    digital = _to_digital(rows, bdf=bdf)

    def span(begin: float, end: float) -> slice:
        return slice(round(begin * M08_RATE), round(end * M08_RATE))

    for channel, (begin, end) in ((1, (30, 39)), (2, (55, 64)), (3, (30.5, 39.5))):
        stretch = span(begin, end)
        digital[channel, stretch] = digital[channel, stretch.start]  # constant digital value
    digital[4, span(40, 46)] = high
    digital[5, span(40, 46)] = high - 1
    digital[6, span(70, 76)] = low
    digital[7, span(70, 76)] = low + 1
    digital[8, span(40.5, 46.5)] = high
    digital[9, round(80.3 * M08_RATE)] = high  # one sample at the limit
    return digital


@pytest.fixture(scope="module", params=["edf", "bdf"])
def m08_result(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> StreamResult:
    suffix = str(request.param)
    path = tmp_path_factory.mktemp("m08") / f"rec.{suffix}"
    _write_edf(path, _m08_digital(suffix == "bdf"), M08_RATE, bdf=suffix == "bdf")
    return _stream(path)


def test_m08_clean_channel_has_no_flags(m08_result: StreamResult) -> None:
    """M08: an EEG-like channel gives neither flat nor clipped windows; all 100 windows are judged."""
    assert m08_result.clipping_method == "range"
    assert [ch.windows for ch in m08_result.channels] == [M08_SECONDS] * 10
    clean = m08_result.channels[0]
    assert clean.flat == Ranges() and clean.clipped == Ranges()
    assert m08_result.data_seconds == M08_SECONDS


def test_m08_flat_stretch_aligned_to_seconds_is_exact(m08_result: StreamResult) -> None:
    """M08 detection target: one digital value for exactly 9 s of 100 s gives exactly 9 flat windows and the
    inserted interval as the range, also across the 60-s block boundary."""
    for index, begin in ((1, 30.0), (2, 55.0)):
        channel = m08_result.channels[index]
        assert channel.flat == Ranges(windows=9, seconds=9.0, ranges=((begin, begin + 9.0),), total=1)
        assert channel.clipped == Ranges()


def test_m08_flat_stretch_not_aligned_loses_at_most_one_window(m08_result: StreamResult) -> None:
    """M08 detection target: a 9-s flat stretch from 30.5 s to 39.5 s gives 9 ± 1 flat windows and a range
    within 1 s of the inserted interval (only whole flat windows count)."""
    channel = m08_result.channels[3]
    assert abs(channel.flat.windows - 9) <= 1
    ((begin, end),) = channel.flat.ranges
    assert abs(begin - 30.5) <= 1.0 and abs(end - 39.5) <= 1.0
    assert 30.5 <= begin < end <= 39.5  # a flagged window lies inside the flat stretch
    assert channel.clipped == Ranges()


def test_m08_clipping_at_the_digital_limits(m08_result: StreamResult) -> None:
    """M08 detection target (EDF and BDF, method range): 6 s at the digital maximum (or minimum) give exactly
    6 clipped windows that are not also flat; one step inside the limit is not clipped (but flat)."""
    at_max, below_max, at_min, above_min = m08_result.channels[4:8]
    assert at_max.clipped == Ranges(windows=6, seconds=6.0, ranges=((40.0, 46.0),), total=1)
    assert at_max.flat == Ranges()
    assert at_min.clipped == Ranges(windows=6, seconds=6.0, ranges=((70.0, 76.0),), total=1)
    assert at_min.flat == Ranges()
    assert below_max.clipped == Ranges() and above_min.clipped == Ranges()
    assert below_max.flat == Ranges(windows=6, seconds=6.0, ranges=((40.0, 46.0),), total=1)
    assert above_min.flat == Ranges(windows=6, seconds=6.0, ranges=((70.0, 76.0),), total=1)


def test_m08_clipping_counts_every_window_that_touches_the_limit(m08_result: StreamResult) -> None:
    """M08 range method: a window is clipped if any value is at the limit; 6 s from 40.5 s touch 7 windows and
    one single sample at the limit flags its window."""
    shifted, single = m08_result.channels[8:10]
    assert shifted.clipped == Ranges(windows=7, seconds=7.0, ranges=((40.0, 47.0),), total=1)
    assert shifted.flat == Ranges()
    assert single.clipped == Ranges(windows=1, seconds=1.0, ranges=((80.0, 81.0),), total=1)


# --- M08 plateau method and float/LSB tolerance -----------------------------------------------------------


def _plateau(row: np.ndarray, rate: int, window: int, length: int, extreme: str) -> None:
    """``length`` equal samples beyond the maximum (or minimum) of a window, from sample 100 of the window."""
    segment = row[window * rate : (window + 1) * rate]
    value = segment.max() + 5.0 if extreme == "max" else segment.min() - 5.0
    start = window * rate + 100
    row[start : start + length] = value


def _plateau_rows(rate: int, seconds: int, seed: int) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    rows = [rng.normal(0.0, 10.0, rate * seconds) for _ in range(6)]
    _plateau(rows[0], rate, 3, 10, "max")
    _plateau(rows[1], rate, 3, 9, "max")
    _plateau(rows[2], rate, 5, 10, "min")
    _plateau(rows[3], rate, 5, 9, "min")
    rows[4][5 * rate + 100 : 5 * rate + 110] = 0.0  # 10 equal samples inside the range of the window
    rows[5][7 * rate : 8 * rate] = 3.0  # a flat window
    return rows


def test_m08_plateau_of_ten_equal_samples_at_the_extreme_is_clipped() -> None:
    """A-18 plateau method (no known range): >= plateau_samples (10) equal samples at the window maximum or
    minimum are clipped, 9 are not, 10 equal samples inside the range are not; a flat window is flat, not
    clipped. plateau_samples is honoured."""
    rate = 256
    rows = _plateau_rows(rate, 12, seed=82)
    result = measure_stream(ArraySource(rows, rate), 50.0)
    assert result.clipping_method == "plateau"
    assert [ch.clipped.ranges for ch in result.channels] == [((3.0, 4.0),), (), ((5.0, 6.0),), (), (), ()]
    assert [ch.flat.ranges for ch in result.channels] == [(), (), (), (), (), ((7.0, 8.0),)]
    nine = measure_stream(ArraySource(rows, rate), 50.0, plateau_samples=9)
    assert [ch.clipped.ranges for ch in nine.channels] == [
        ((3.0, 4.0),),
        ((3.0, 4.0),),
        ((5.0, 6.0),),
        ((5.0, 6.0),),
        (),
        (),
    ]


def test_m08_plateau_method_on_a_floating_point_file(tmp_path: Path) -> None:
    """A-18 on a real float file (FIF through MNE, preload=False): plateau method, 10 equal samples at the
    maximum are clipped, 9 are not; the flat window is flat and not clipped."""
    rate, seconds = 256, 12
    rows = _plateau_rows(rate, seconds, seed=85)
    info = mne.create_info([f"EEG{i:03d}" for i in range(len(rows))], rate, ch_types="eeg")
    path = tmp_path / "rec_raw.fif"
    mne.io.RawArray(np.vstack(rows) * 1e-6, info, verbose="error").save(path, verbose="error")
    result = _stream(path)
    assert result.clipping_method == "plateau"
    assert [ch.windows for ch in result.channels] == [seconds] * 6
    assert [ch.clipped.ranges for ch in result.channels] == [((3.0, 4.0),), (), ((5.0, 6.0),), (), (), ()]
    assert [ch.flat.ranges for ch in result.channels] == [(), (), (), (), (), ((7.0, 8.0),)]


@pytest.mark.parametrize(
    ("lsb_uv", "tolerance_uv", "flat_windows"),
    [(0.1, 0.1, [2.0]), (None, 0.1, [2.0, 4.0, 6.0]), (None, 0.2, [2.0, 4.0, 6.0, 8.0])],
)
def test_m08_flat_tolerance_for_float_data_and_lsb(
    lsb_uv: float | None, tolerance_uv: float, flat_windows: list[float]
) -> None:
    """A-18: with an LSB a window is flat below 0.5·LSB (0.04 µV yes, 0.06 µV no for 0.1 µV); float data is
    flat below flat_tolerance_uv (0.1 µV by default, configurable)."""
    rate, seconds = 256, 10
    row = np.random.default_rng(84).normal(0.0, 10.0, rate * seconds)
    alternating = np.arange(rate) % 2
    for window, peak_to_peak in ((2, 0.04), (4, 0.06), (6, 0.09), (8, 0.11)):
        row[window * rate : (window + 1) * rate] = 5.0 + peak_to_peak * alternating
    result = measure_stream(ArraySource([row], rate, lsb_uv=lsb_uv), 50.0, flat_tolerance_uv=tolerance_uv)
    (channel,) = result.channels
    assert _starts(channel.flat) == flat_windows
    assert channel.clipped == Ranges()


def test_m08_brainvision_resolution_sets_the_flat_step(tmp_path: Path) -> None:
    """A-18 on BrainVision INT_16 with 0.1 µV resolution: one digital value per window is flat, one step of
    0.1 µV is not (flat below 0.5·LSB); 10 equal digital samples at the maximum are clipped, 9 are not."""
    rate, seconds = 500, 12
    vhdr = tmp_path / "rec.vhdr"
    gen_fixtures.write_brainvision(vhdr, sfreq=rate, seconds=seconds, labels=LABELS[:4], seed=83)
    digital = np.round(np.random.default_rng(83).normal(0.0, 100.0, (4, rate * seconds))).astype(np.int64)
    digital[0, 2 * rate : 3 * rate] = 57
    digital[1, 2 * rate : 3 * rate] = 57 + np.arange(rate) % 2
    for channel, length in ((2, 10), (3, 9)):
        top = digital[channel, 4 * rate : 5 * rate].max()
        digital[channel, 4 * rate + 100 : 4 * rate + 100 + length] = top + 3
    vhdr.with_suffix(".eeg").write_bytes(digital.T.astype("<i2").tobytes())  # multiplexed
    result = _stream(vhdr)
    assert result.clipping_method == "plateau"
    assert [ch.flat.ranges for ch in result.channels] == [((2.0, 3.0),), (), (), ()]
    assert [ch.clipped.ranges for ch in result.channels] == [(), (), ((4.0, 5.0),), ()]


# --- ranges, windows, blocks ----------------------------------------------------------------------------


def test_m08_adjacent_windows_merge_into_one_range() -> None:
    """M08: adjacent flagged windows form one time range; separate ones stay separate."""
    rate, seconds = 64, 30
    row = np.random.default_rng(86).normal(0.0, 10.0, rate * seconds)
    for begin, end in ((10, 15), (20, 21), (22, 23)):
        row[begin * rate : end * rate] = 1.0
    (channel,) = measure_stream(ArraySource([row], rate), 50.0).channels
    assert channel.flat == Ranges(
        windows=7, seconds=7.0, ranges=((10.0, 15.0), (20.0, 21.0), (22.0, 23.0)), total=3
    )


def test_m08_more_than_max_ranges_keeps_the_first_and_counts_all() -> None:
    """M08: at most MAX_RANGES ranges are kept (the first ones in time); total counts every range and the
    window count and seconds stay complete."""
    rate, separate = 64, MAX_RANGES + 25
    row = np.random.default_rng(87).normal(0.0, 10.0, rate * 2 * separate)
    for window in range(0, 2 * separate, 2):
        row[window * rate : (window + 1) * rate] = 2.0
    flat = measure_stream(ArraySource([row], rate), 50.0).channels[0].flat
    assert flat.windows == separate and flat.seconds == float(separate)
    assert flat.total == separate
    assert len(flat.ranges) == MAX_RANGES
    assert flat.ranges[0] == (0.0, 1.0)
    assert flat.ranges[-1] == (2.0 * (MAX_RANGES - 1), 2.0 * (MAX_RANGES - 1) + 1.0)


def test_m08_incomplete_last_window_is_not_judged() -> None:
    """M08: only complete 1-s windows are judged; data_seconds is the full length."""
    rate = 256
    row = np.random.default_rng(88).normal(0.0, 10.0, rate * 10 + rate // 2)
    row[-(rate // 2) :] = 0.0  # flat, but only half a window
    result = measure_stream(ArraySource([row], rate), 50.0)
    (channel,) = result.channels
    assert channel.windows == 10
    assert channel.flat == Ranges()
    assert result.data_seconds == 10.5


def test_m08_needs_two_samples_per_window() -> None:
    """M08: with fewer than two samples per window a peak-to-peak is meaningless; no windows are judged and
    the reason is quality.window_too_few_samples. Two samples per window are enough."""
    seconds = 120
    rng = np.random.default_rng(89)
    rows = [rng.normal(0.0, 10.0, seconds), rng.normal(0.0, 10.0, 2 * seconds)]
    one, two = measure_stream(ArraySource(rows, [1.0, 2.0]), 50.0).channels
    assert (one.windows, one.windows_reason, one.flat) == (0, "quality.window_too_few_samples", Ranges())
    assert (two.windows, two.windows_reason) == (seconds, None)


def test_stream_reads_blocks_of_sixty_seconds_per_rate_group() -> None:
    """KONZEPT 1.5: blocks of 60 s, read per group of channels with the same rate; the last block is
    partial."""
    seconds = 150
    rng = np.random.default_rng(90)
    rows = [rng.normal(0.0, 10.0, rate * seconds) for rate in (100, 64, 100)]
    source = ArraySource(rows, [100, 64, 100])
    measure_stream(source, 50.0)
    assert source.reads == [
        ((1,), 0, 3840),
        ((1,), 3840, 7680),
        ((1,), 7680, 9600),
        ((0, 2), 0, 6000),
        ((0, 2), 6000, 12000),
        ((0, 2), 12000, 15000),
    ]


def test_mixed_rates_are_measured_at_their_native_rate() -> None:
    """KONZEPT 1.5 (EDF with mixed rates): every channel at its own rate; M07 per channel, windows and time
    ranges at the channel's rate."""
    seconds = 70
    rng = np.random.default_rng(91)
    fast = rng.normal(0.0, 10.0, 256 * seconds)
    slow = rng.normal(0.0, 10.0, 100 * seconds)
    fast[65 * 256 : 67 * 256] = 1.0
    slow[65 * 100 : 67 * 100] = 1.0
    result = measure_stream(ArraySource([fast, slow], [256.0, 100.0]), 50.0)
    fast_ch, slow_ch = result.channels
    assert (fast_ch.rate_hz, slow_ch.rate_hz) == (256.0, 100.0)
    assert fast_ch.windows == slow_ch.windows == seconds
    assert fast_ch.line_state == "measured" and slow_ch.line_state == "not_applicable"
    for channel in result.channels:
        assert channel.flat == Ranges(windows=2, seconds=2.0, ranges=((65.0, 67.0),), total=1)
    assert result.data_seconds == seconds


@pytest.mark.parametrize(
    ("plus", "onsets", "flat", "clipped"),
    [
        ("D", (0, 1, 2, 3, 4, 10, 11, 12, 13, 14), ((4.0, 5.0), (10.0, 11.0)), ((11.0, 13.0),)),
        ("C", None, ((4.0, 6.0),), ((6.0, 8.0),)),
        ("", None, ((4.0, 6.0),), ((6.0, 8.0),)),
    ],
)
def test_m08_time_ranges_follow_edf_plus_d_record_onsets(
    tmp_path: Path,
    plus: str,
    onsets: tuple[int, ...] | None,
    flat: tuple[tuple[float, float], ...],
    clipped: tuple[tuple[float, float], ...],
) -> None:
    """A-12, A-77: in EDF+D the time ranges are recording time from the record onsets, so windows on both
    sides of a gap (4 s -> 10 s) do not merge; EDF+C and plain EDF count from the start of the data."""
    rate, seconds = 256, 10
    rng = np.random.default_rng(92)
    digital = _to_digital(np.vstack([_eeg_like(rng, rate, seconds) for _ in range(3)]))
    digital[0, 4 * rate : 6 * rate] = digital[0, 4 * rate]
    digital[1, 6 * rate : 8 * rate] = EDF_LIMITS[1]
    path = _write_edf(tmp_path / "rec.edf", digital, rate, plus=plus, onsets=onsets)
    result = _stream(path)
    assert len(result.channels) == 3  # the annotation signal is not an EEG channel
    first, second, clean = result.channels
    assert first.flat == Ranges(windows=2, seconds=2.0, ranges=flat, total=len(flat))
    assert second.clipped == Ranges(windows=2, seconds=2.0, ranges=clipped, total=len(clipped))
    assert first.clipped == Ranges() and second.flat == Ranges()
    assert clean.flat == Ranges() and clean.clipped == Ranges()
    assert result.data_seconds == seconds


# --- signal hash NG-SIGHASH-v1 ----------------------------------------------------------------------------


def _hash_digital(channels: int, rate: int, seconds: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.round(rng.normal(0.0, 200.0, (channels, rate * seconds))).astype(np.int64)


def test_signal_hash_is_reproducible_and_sees_one_digital_step(tmp_path: Path) -> None:
    """A-21: the same data gives the same hash (in another file, and in a second run); one sample changed by
    one digital step (0.1 µV) gives a different hash."""
    rate = 256
    digital = _hash_digital(4, rate, 70, seed=93)
    first = _write_edf(tmp_path / "a.edf", digital, rate, physical=STEP_0_1_UV)
    copy = _write_edf(tmp_path / "copy" / "b.edf", digital.copy(), rate, physical=STEP_0_1_UV)
    changed = digital.copy()
    changed[2, 12_345] += 1
    other = _write_edf(tmp_path / "c.edf", changed, rate, physical=STEP_0_1_UV)
    hashes = [_stream(path).signal_hash for path in (first, first, copy, other)]
    assert hashes[0] is not None and len(hashes[0]) == 64
    assert hashes[0] == hashes[1] == hashes[2]
    assert hashes[3] != hashes[0]


def test_signal_hash_follows_the_ng_sighash_v1_recipe(tmp_path: Path) -> None:
    """A-21: sha256 over "NG-SIGHASH-v1", then per EEG channel in file order the rate as "%.6f:" and the
    sha256 of int64 rint(µV · 10). With a step of exactly 0.1 µV, rint(µV · 10) is the digital value; three
    blocks (the last one partial) hash like one piece."""
    rate = 256
    digital = _hash_digital(3, rate, 130, seed=94)
    result = _stream(_write_edf(tmp_path / "rec.edf", digital, rate, physical=STEP_0_1_UV))
    expected = hashlib.sha256(HASH_VERSION.encode("ascii"))
    for row in digital:
        expected.update(b"256.000000:")
        expected.update(hashlib.sha256(row.astype("<i8").tobytes()).digest())
    assert result.signal_hash == expected.hexdigest()


def test_signal_hash_depends_on_rate_and_channel_order() -> None:
    """A-21: the rate and the file order of the channels are part of the hash; no EEG channel, no hash."""
    rng = np.random.default_rng(95)
    rows = [rng.normal(0.0, 10.0, 256 * 20) for _ in range(2)]
    base = measure_stream(ArraySource(rows, 256), 50.0).signal_hash
    assert measure_stream(ArraySource(rows, 256), 50.0).signal_hash == base
    assert measure_stream(ArraySource(rows, 250), 50.0).signal_hash != base
    assert measure_stream(ArraySource(rows[::-1], 256), 50.0).signal_hash != base
    empty = measure_stream(ArraySource([], 256), 50.0)
    assert empty.signal_hash is None and empty.channels == () and empty.data_seconds == 0.0


def test_m07_other_line_frequency_above_nyquist_is_not_measured() -> None:
    """A-47: at 110 Hz the 60-Hz band (59–61 Hz) lies above the Nyquist frequency. The documented 50 Hz is
    measured; the other line frequency is None, not 0.0. At 122 Hz both are measured."""
    rng = np.random.default_rng(96)
    (low,) = measure_stream(ArraySource([_eeg_like(rng, 110, 120)], 110), 50.0).channels
    assert low.line_state == "measured" and low.line_ratio is not None and low.other_ratio is None
    (high,) = measure_stream(ArraySource([_eeg_like(rng, 122, 120)], 122), 50.0).channels
    assert high.line_ratio is not None and high.other_ratio is not None


def test_m07_recording_shorter_than_one_welch_segment_is_too_short() -> None:
    """Less than one 2-s Welch segment: the reason is the length, not the signal power."""
    rng = np.random.default_rng(97)
    (channel,) = measure_stream(ArraySource([_eeg_like(rng, 250, 1)], 250), 50.0).channels
    assert (channel.line_state, channel.line_reason, channel.line_ratio) == (
        "not_checkable",
        "quality.too_short",
        None,
    )


def test_signal_hash_is_defined_for_non_finite_and_huge_values() -> None:
    """A-21, A-75: NaN and ±inf hash as the int64 minimum and values beyond ±2^62 are limited, so the cast
    to int64 is always defined, without numpy warnings. Every window here has such a value: none is judged."""
    import warnings

    pattern = [0.0, np.nan, np.inf, -np.inf, 1e300, -1e300, 1.0, 2.0]
    row = np.array(pattern * 125)  # 1000 samples at 50 Hz = 20 s, one block
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = measure_stream(ArraySource([row], 50), 50.0)
    marker = np.iinfo(np.int64).min
    ints = np.array([0, marker, marker, marker, 2**62, -(2**62), 10, 20] * 125, dtype="<i8")
    expected = hashlib.sha256(HASH_VERSION.encode("ascii"))
    expected.update(b"50.000000:")
    expected.update(hashlib.sha256(ints.tobytes()).digest())
    assert result.signal_hash == expected.hexdigest()
    (channel,) = result.channels
    assert (channel.windows, channel.unusable_windows) == (0, 20)
    assert channel.windows_reason == "quality.unusable_samples"
    assert channel.flat.windows == 0 and channel.clipped.windows == 0


def test_windows_and_segments_with_unusable_samples_are_not_judged() -> None:
    """A-75: 1-s windows and Welch segments with NaN, ±inf or values beyond ±1e100 µV are left out of M08 and
    M07 (counted as unusable); a channel with nothing else is not_checkable; numpy does not warn."""
    import warnings

    rng = np.random.default_rng(98)
    rate = 256
    clean = _eeg_like(rng, rate, 120) + _sine(rate, 120, 50.0, 10.0)
    partly = clean.copy()
    partly[10 * rate : 30 * rate : 7] = np.nan  # at least one NaN in each window from 10 s to 30 s
    partly[60 * rate + 5] = 1e300  # one absurd value in the window from 60 s
    nothing = np.full(120 * rate, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = measure_stream(ArraySource([clean, partly, nothing], rate), 50.0)
    base, part, none = result.channels
    assert (base.windows, base.unusable_windows, base.line_state) == (120, 0, "measured")
    assert (part.windows, part.unusable_windows) == (99, 21)
    assert part.line_state == "measured" and part.line_ratio == pytest.approx(_ratio(base), rel=0.1)
    assert (none.line_state, none.line_reason, none.line_ratio) == (
        "not_checkable",
        "quality.unusable_samples",
        None,
    )
    assert (none.windows, none.unusable_windows, none.windows_reason) == (0, 120, "quality.unusable_samples")


def test_threads_do_not_change_the_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """KONZEPT 1.5, NG-N03: the channels of a block are computed in threads; one thread or four give the
    same values and the same hash."""
    from neurogrid.quality import stream as stream_module

    rng = np.random.default_rng(99)
    rows = [_eeg_like(rng, 256, 150) + _sine(256, 150, 50.0, 3.0 * (i % 3)) for i in range(9)]
    results = []
    for threads in (1, 4):
        monkeypatch.setattr(stream_module, "THREADS", threads)
        results.append(measure_stream(ArraySource(rows, 256), 50.0))
    assert results[0] == results[1]
