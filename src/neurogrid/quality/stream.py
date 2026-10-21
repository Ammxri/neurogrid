"""One streaming pass over the full length of a recording (KONZEPT 1.5, D-04, A-18, A-21, A-47).

Blocks of 60 s are read per group of channels with the same rate; only one block is in memory. The channels
of a block are computed in min(4, cores) threads (KONZEPT 1.5); every channel stays in one thread and its
blocks are taken in order, so the values do not depend on the number of threads.

- **M07 (line noise):** Welch with 2-s windows, a periodic Hann window and no overlap (the mean of every
  window is removed). Per block and channel the ratio P(f0 ± 1 Hz) / P(1–40 Hz) is formed from the summed
  bins; the channel value is the median over the blocks. The same is measured at the other line frequency
  (50 ↔ 60 Hz, A-47) where the rate allows it. Not applicable when the rate is below 2·(f0 + 1). A constant
  segment carries no power (its mean is removed exactly), so a constant channel has no signal power.
- **M08 (flat line, clipping):** per 1-s window. Clipped: a value at the digital range limit where the format
  has one (EDF/BDF); otherwise a plateau of ≥ ``plateau_samples`` equal values at the extreme of a window that
  is not flat. Flat: peak-to-peak below one digital step (EDF/BDF/BrainVision) or below
  ``flat_tolerance_uv`` for floating-point data. A clipped window is not also counted as flat. A window needs
  at least two samples (rate ≥ 1.5 Hz); below that M08 cannot be judged.
- **Unusable samples:** windows and Welch segments with a non-finite value or a value beyond ±1e100 µV (a
  damaged file) are not judged; a channel with nothing else gets ``quality.unusable_samples``.
- **Signal hash ``NG-SIGHASH-v1`` (A-21):** over the EEG channels in file order; per channel the rate as a
  fixed decimal string and int64 of rint(µV · 10), limited to ±2^62, non-finite values as the int64 minimum.
  Kept for duplicate detection (M12), never written out.
"""

from __future__ import annotations

import hashlib
import math
import os
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from neurogrid.quality.source import SignalChannel, SignalSource

BLOCK_WINDOWS = 60  # one block = 60 windows of 1 s
WELCH_WINDOWS = 2  # Welch segment = 2 windows of 1 s
LINE_HALF_WIDTH_HZ = 1.0
REFERENCE_BAND_HZ = (1.0, 40.0)
MAX_RANGES = 100  # time ranges kept per channel and condition; the total is counted
MIN_WINDOW_SAMPLES = 2  # a peak-to-peak needs two samples: one sample per window would always look flat
HASH_LIMIT = float(2**62)  # rint(µV · 10) beyond this is limited, so the int64 cast is always defined
USABLE_LIMIT_UV = 1e100  # beyond this, power sums overflow; no EEG comes near it
HASH_VERSION = "NG-SIGHASH-v1"
THREADS = min(4, os.cpu_count() or 1)  # KONZEPT 1.5: min(4, cores) threads over groups of channels


def other_line_frequency(line_hz: float) -> float:
    return 60.0 if abs(line_hz - 50.0) < abs(line_hz - 60.0) else 50.0


@dataclass(frozen=True)
class Ranges:
    """Flagged 1-s windows of one channel: count, seconds, and merged time ranges (at most MAX_RANGES)."""

    windows: int = 0
    seconds: float = 0.0
    ranges: tuple[tuple[float, float], ...] = ()
    total: int = 0


@dataclass(frozen=True)
class ChannelStream:
    name: str
    rate_hz: float
    windows: int  # complete 1-s windows that were judged
    line_ratio: float | None
    other_ratio: float | None
    line_state: str  # measured | not_applicable | not_checkable
    line_reason: str | None
    flat: Ranges
    clipped: Ranges
    windows_reason: str | None = None  # why M08 has no windows although there are samples
    unusable_windows: int = 0  # complete 1-s windows with unusable samples, not judged


@dataclass(frozen=True)
class StreamResult:
    line_frequency_hz: float
    other_frequency_hz: float
    clipping_method: str
    channels: tuple[ChannelStream, ...]
    signal_hash: str | None
    data_seconds: float


@dataclass
class _Collector:
    """Running state of one channel during the pass."""

    channel: SignalChannel
    line: list[float] = field(default_factory=list)
    other: list[float] = field(default_factory=list)
    flat: list[tuple[int, int]] = field(default_factory=list)  # (start sample, stop sample)
    clipped: list[tuple[int, int]] = field(default_factory=list)
    windows: int = 0
    unusable_windows: int = 0
    welch_segments: int = 0
    usable_segments: int = 0
    digest: hashlib._Hash = field(default_factory=hashlib.sha256)


def _hash_values(values: np.ndarray) -> bytes:
    scaled = np.rint(values * 10.0)
    finite = np.isfinite(scaled)
    out = np.clip(np.where(finite, scaled, 0.0), -HASH_LIMIT, HASH_LIMIT).astype("<i8")
    out[~finite] = np.iinfo(np.int64).min
    return out.tobytes()


def _band_ratios(
    segments: np.ndarray, rate: float, line_hz: float, other_hz: float
) -> tuple[float | None, float | None]:
    """Welch ratios of one block: segments (n_segments, n) without mean, periodic Hann window. The ratio at
    the other line frequency is None when that band lies above the Nyquist frequency."""
    n = segments.shape[1]
    window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)  # periodic Hann
    spectrum = np.abs(np.fft.rfft(segments * window, axis=1)) ** 2
    power = spectrum.mean(axis=0)
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    low, high = REFERENCE_BAND_HZ
    reference = float(power[(freqs >= low) & (freqs <= high)].sum())
    if not (math.isfinite(reference) and reference > 0):
        return None, None
    line = float(power[np.abs(freqs - line_hz) <= LINE_HALF_WIDTH_HZ].sum()) / reference
    if not math.isfinite(line):
        return None, None
    if rate < 2 * (other_hz + LINE_HALF_WIDTH_HZ):
        return line, None
    other = float(power[np.abs(freqs - other_hz) <= LINE_HALF_WIDTH_HZ].sum()) / reference
    return line, (other if math.isfinite(other) else None)


def _usable(rows: np.ndarray) -> np.ndarray:
    """Per row: every value finite and within ±USABLE_LIMIT_UV."""
    return np.asarray((np.abs(rows) <= USABLE_LIMIT_UV).all(axis=1))


def _longest_runs(mask: np.ndarray) -> np.ndarray:
    """Length of the longest run of True per row."""
    rows, cols = mask.shape
    padded = np.zeros((rows, cols + 2), dtype=np.int8)
    padded[:, 1:-1] = mask
    steps = np.diff(padded, axis=1)
    starts = np.argwhere(steps == 1)
    ends = np.argwhere(steps == -1)
    longest = np.zeros(rows, dtype=np.int64)
    if len(starts):
        np.maximum.at(longest, starts[:, 0], ends[:, 1] - starts[:, 1])
    return longest


def _window_flags(
    values: np.ndarray,
    digital: np.ndarray | None,
    channel: SignalChannel,
    method: str,
    flat_tolerance_uv: float,
    plateau_samples: int,
) -> tuple[np.ndarray, np.ndarray]:
    """(flat, clipped) per window; values and digital are (windows, samples)."""
    if digital is not None and channel.digital_limits is not None and method == "range":
        low, high = channel.digital_limits
        clipped = ((digital <= low) | (digital >= high)).any(axis=1)
        flat = (digital.max(axis=1) - digital.min(axis=1)) == 0
    else:
        peak = values.max(axis=1) - values.min(axis=1)
        tolerance = channel.lsb_uv * 0.5 if channel.lsb_uv else flat_tolerance_uv
        flat = peak < tolerance
        at_max = values == values.max(axis=1, keepdims=True)
        at_min = values == values.min(axis=1, keepdims=True)
        plateau = np.maximum(_longest_runs(at_max), _longest_runs(at_min)) >= plateau_samples
        clipped = plateau & ~flat
    return np.asarray(flat & ~clipped), np.asarray(clipped)


def _ranges(source: SignalSource, index: int, spans: list[tuple[int, int]], rate: float) -> Ranges:
    if not spans:
        return Ranges()
    merged: list[tuple[float, float]] = []
    seconds = 0.0
    for start, stop in spans:
        begin = source.time_s(index, start)
        end = source.time_s(index, stop - 1) + 1.0 / rate
        seconds += (stop - start) / rate
        if merged and abs(merged[-1][1] - begin) < 1e-9:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((begin, end))
    return Ranges(
        windows=len(spans),
        seconds=seconds,
        ranges=tuple((round(float(a), 6), round(float(b), 6)) for a, b in merged[:MAX_RANGES]),
        total=len(merged),
    )


def _median(values: list[float]) -> float | None:
    return float(np.median(values)) if values else None


def measure_stream(
    source: SignalSource,
    line_hz: float,
    *,
    flat_tolerance_uv: float = 0.1,
    plateau_samples: int = 10,
) -> StreamResult:
    other_hz = other_line_frequency(line_hz)
    collectors = [_Collector(channel=ch) for ch in source.channels]
    by_rate: dict[float, list[int]] = {}
    for index, channel in enumerate(source.channels):
        by_rate.setdefault(channel.rate_hz, []).append(index)
    settings = _Settings(line_hz, other_hz, flat_tolerance_uv, plateau_samples, source.clipping_method)
    threads = min(THREADS, len(source.channels))
    with ThreadPoolExecutor(max_workers=max(1, threads)) as pool:
        for rate, indices in sorted(by_rate.items()):
            total = min(source.channels[i].n_samples for i in indices)
            block = max(1, round(rate)) * BLOCK_WINDOWS
            groups = [list(range(n, len(indices), threads)) for n in range(threads)] if threads > 1 else []
            for start in range(0, total, block):
                stop = min(start + block, total)
                data = source.read_many(indices, start, stop)
                if not groups:
                    _rows(source, collectors, indices, range(len(indices)), data, start, stop, rate, settings)
                    continue
                futures = [
                    pool.submit(_rows, source, collectors, indices, rows, data, start, stop, rate, settings)
                    for rows in groups
                    if rows
                ]
                for future in futures:
                    future.result()
    channels = []
    for index, collector in enumerate(collectors):
        channel = collector.channel
        rate = channel.rate_hz
        if rate < 2 * (line_hz + LINE_HALF_WIDTH_HZ):
            state, reason = "not_applicable", "quality.rate_below_line_band"
        elif not collector.welch_segments:
            state, reason = "not_checkable", "quality.too_short"
        elif not collector.usable_segments:
            state, reason = "not_checkable", "quality.unusable_samples"
        elif not collector.line:
            state, reason = "not_checkable", "quality.no_signal_power"
        else:
            state, reason = "measured", None
        channels.append(
            ChannelStream(
                name=channel.name,
                rate_hz=rate,
                windows=collector.windows,
                line_ratio=_median(collector.line) if state == "measured" else None,
                other_ratio=_median(collector.other) if state == "measured" else None,
                line_state=state,
                line_reason=reason,
                flat=_ranges(source, index, collector.flat, rate),
                clipped=_ranges(source, index, collector.clipped, rate),
                windows_reason=(
                    "quality.window_too_few_samples"
                    if round(rate) < MIN_WINDOW_SAMPLES
                    else "quality.unusable_samples"
                    if not collector.windows and collector.unusable_windows
                    else None
                ),
                unusable_windows=collector.unusable_windows,
            )
        )
    return StreamResult(
        line_frequency_hz=line_hz,
        other_frequency_hz=other_hz,
        clipping_method=source.clipping_method,
        channels=tuple(channels),
        signal_hash=_combined_hash(collectors) if collectors else None,
        data_seconds=max((c.n_samples / c.rate_hz for c in source.channels), default=0.0),
    )


@dataclass(frozen=True)
class _Settings:
    line_hz: float
    other_hz: float
    flat_tolerance_uv: float
    plateau_samples: int
    clipping_method: str


def _rows(
    source: SignalSource,
    collectors: list[_Collector],
    indices: Sequence[int],
    rows: Sequence[int],
    data: np.ndarray,
    start: int,
    stop: int,
    rate: float,
    settings: _Settings,
) -> None:
    """One block of the channels ``rows`` (positions in ``indices``); a channel is only ever handled by one
    thread, and its blocks in order, so the result does not depend on the number of threads."""
    with np.errstate(
        invalid="ignore", over="ignore", divide="ignore"
    ):  # NaN/inf in float data (A-75); per thread
        _rows_unchecked(source, collectors, indices, rows, data, start, stop, rate, settings)


def _rows_unchecked(
    source: SignalSource,
    collectors: list[_Collector],
    indices: Sequence[int],
    rows: Sequence[int],
    data: np.ndarray,
    start: int,
    stop: int,
    rate: float,
    settings: _Settings,
) -> None:
    window = max(1, round(rate))
    welch = window * WELCH_WINDOWS
    line_possible = rate >= 2 * (settings.line_hz + LINE_HALF_WIDTH_HZ)
    for row in rows:
        index = indices[row]
        values = data[row]
        collector = collectors[index]
        collector.digest.update(_hash_values(values))
        full = (stop - start) // window if window >= MIN_WINDOW_SAMPLES else 0
        if full:
            shaped = values[: full * window].reshape(full, window)
            digital = source.read_digital(index, start, start + full * window)
            digital_shaped = digital.reshape(full, window) if digital is not None else None
            flat, clipped = _window_flags(
                shaped,
                digital_shaped,
                source.channels[index],
                settings.clipping_method,
                settings.flat_tolerance_uv,
                settings.plateau_samples,
            )
            usable = _usable(shaped)  # NaN compares false: such windows would be neither flat nor clipped
            flat &= usable
            clipped &= usable
            judged = int(usable.sum())
            collector.windows += judged
            collector.unusable_windows += full - judged
            for offset in np.flatnonzero(flat).tolist():
                collector.flat.append((start + offset * window, start + (offset + 1) * window))
            for offset in np.flatnonzero(clipped).tolist():
                collector.clipped.append((start + offset * window, start + (offset + 1) * window))
        segments = (stop - start) // welch
        if not (line_possible and segments):
            continue
        collector.welch_segments += segments
        parts = values[: segments * welch].reshape(segments, welch)
        parts = parts[_usable(parts)]
        collector.usable_segments += len(parts)
        if not len(parts):
            continue
        constant = (parts.max(axis=1) - parts.min(axis=1)) == 0
        parts = parts - parts.mean(axis=1, keepdims=True)
        parts[constant] = 0.0  # the mean of a constant is not always exact in floating point
        line, other = _band_ratios(parts, rate, settings.line_hz, settings.other_hz)
        if line is not None:
            collector.line.append(line)
            if other is not None:
                collector.other.append(other)


def _combined_hash(collectors: Sequence[_Collector]) -> str:
    combined = hashlib.sha256(HASH_VERSION.encode("ascii"))
    for collector in collectors:
        combined.update(f"{collector.channel.rate_hz:.6f}:".encode("ascii"))
        combined.update(collector.digest.digest())
    return combined.hexdigest()


def finite(value: float | None) -> float | None:
    return value if value is not None and math.isfinite(value) else None
