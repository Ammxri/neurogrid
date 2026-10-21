"""Block-wise access to the EEG signals of one recording (A-24, KONZEPT 1.5, NG-N02).

Two sources:

- ``EdfSignals`` reads EDF/EDF+/BDF/BDF+ itself through a memory map of the data records. Every channel is
  read at its own native rate (EDF allows one rate per signal), as digital values and in µV. Data records
  of EDF+D carry their start time in the time-stamped annotation list; time ranges therefore follow the
  recording time, not the sample count (A-12, A-77). Only complete data records are read, so a truncated
  file is measured on the data it holds (M01-02 reports the truncation).
- ``MneSignals`` reads BrainVision, EEGLAB and FIF through MNE with ``preload=False`` (EEGLAB with embedded
  data is loaded by MNE as a whole, R14).

Both give µV as float64 and never load more than one block per channel.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from neurogrid.io.edf import EdfHeader, parse_header
from neurogrid.model.dataset import Recording

_UNIT_TO_UV = {
    "uv": 1.0,
    "µv": 1.0,
    "μv": 1.0,
    "microvolt": 1.0,
    "mv": 1e3,
    "v": 1e6,
    "nv": 1e-3,
}
_TAL_ONSET = re.compile(rb"^([+-]\d+(?:\.\d+)?)\x14\x14")


def unit_scale(unit: str | None) -> float:
    """Factor from a header unit to µV; an empty or unknown unit is taken as µV (MNE does the same)."""
    return _UNIT_TO_UV.get((unit or "").strip().lower(), 1.0)


def unique_names(names: Sequence[str]) -> list[str]:
    """Channel names made unique the way MNE does it: every occurrence of a repeated name gets "-0", "-1", …
    (a suffix that is already taken is skipped). The signal metrics key their values by these names."""
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    taken = set(names)
    out: list[str] = []
    next_suffix: dict[str, int] = {}
    for name in names:
        if counts[name] == 1:
            out.append(name)
            continue
        suffix = next_suffix.get(name, 0)
        while f"{name}-{suffix}" in taken:
            suffix += 1
        out.append(f"{name}-{suffix}")
        taken.add(out[-1])
        next_suffix[name] = suffix + 1
    return out


@dataclass(frozen=True)
class SignalChannel:
    """One EEG channel as the signal metrics see it."""

    name: str
    rate_hz: float
    lsb_uv: float | None  # one digital step in µV; None for floating-point data
    digital_limits: tuple[int, int] | None  # digital minimum and maximum (EDF/BDF): the range limit
    n_samples: int


class SignalSource(Protocol):
    channels: tuple[SignalChannel, ...]
    clipping_method: str  # "range" (digital limits known) or "plateau"

    def read(self, index: int, start: int, stop: int) -> np.ndarray:
        """Samples [start, stop) of channel ``index`` in µV."""
        ...

    def read_digital(self, index: int, start: int, stop: int) -> np.ndarray | None:
        """The same samples as digital values, where the format has them (EDF/BDF)."""
        ...

    def read_many(self, indices: Sequence[int], start: int, stop: int) -> np.ndarray:
        """Samples [start, stop) of channels with the same rate, one row per channel, in µV."""
        ...

    def positions(self) -> dict[str, tuple[float, float, float]]:
        """Channel positions stored in the file (head frame, m); empty if the format has none."""
        ...

    def time_s(self, index: int, sample: int) -> float:
        """Recording time in seconds of a sample index of channel ``index``."""
        ...

    def close(self) -> None: ...


class EdfSignals:
    """EDF/BDF data records through a read-only memory map."""

    clipping_method = "range"

    def __init__(self, path: Path, recording: Recording, eeg_names: Sequence[str]) -> None:
        header = parse_header(path)
        self.header = header
        bps = 3 if header.variant == "BDF" else 2
        self._bps = bps
        spr = [s.samples_per_record or 0 for s in header.signals]
        if header.header_bytes is None or not header.record_duration or header.record_duration <= 0:
            raise ValueError("no valid data record duration")
        self._record_bytes = sum(spr) * bps
        if self._record_bytes <= 0:
            raise ValueError("no samples per data record")
        size = path.stat().st_size
        available = max(0, (size - header.header_bytes) // self._record_bytes)
        declared = header.n_records if header.n_records is not None and header.n_records >= 0 else available
        self._records = min(available, declared)
        self._duration = header.record_duration
        self._offsets = [sum(spr[:i]) * bps for i in range(len(spr))]
        self._spr = spr
        if self._records:
            self._map: np.memmap[Any, np.dtype[np.uint8]] | None = np.memmap(
                path,
                dtype=np.uint8,
                mode="r",
                offset=header.header_bytes,
                shape=(self._records, self._record_bytes),
            )
        else:
            self._map = None
        wanted = set(eeg_names)
        labels = unique_names([signal.label for signal in header.signals])
        self._indices: list[int] = []
        channels: list[SignalChannel] = []
        for index, signal in enumerate(header.signals):
            if signal.label not in wanted or not spr[index]:
                continue
            scale = unit_scale(signal.unit)
            lsb = None
            limits = None
            if (
                signal.physical_min is not None
                and signal.physical_max is not None
                and signal.digital_min is not None
                and signal.digital_max is not None
                and signal.digital_max > signal.digital_min
            ):
                lsb = abs(signal.physical_max - signal.physical_min) / (
                    signal.digital_max - signal.digital_min
                )
                lsb *= scale
                limits = (signal.digital_min, signal.digital_max)
            rate = float(Fraction(spr[index]) / header.record_duration)
            channels.append(
                SignalChannel(
                    name=labels[index],
                    rate_hz=rate,
                    lsb_uv=lsb,
                    digital_limits=limits,
                    n_samples=self._records * spr[index],
                )
            )
            self._indices.append(index)
        self.channels = tuple(channels)
        self._onsets = self._record_onsets() if header.plus == "D" else None

    def _record_onsets(self) -> list[float] | None:
        """Start time of every data record from the first TAL of the annotation signal (EDF+D)."""
        annotation = next(
            (
                i
                for i, s in enumerate(self.header.signals)
                if s.label.strip().upper() in ("EDF ANNOTATIONS", "BDF ANNOTATIONS")
            ),
            None,
        )
        if annotation is None or self._map is None:
            return None
        start = self._offsets[annotation]
        width = self._spr[annotation] * self._bps
        onsets: list[float] = []
        for record in range(self._records):
            raw = bytes(self._map[record, start : start + width])
            match = _TAL_ONSET.match(raw)
            if match is None:
                return None  # not a valid EDF+ record: fall back to the record count
            onsets.append(float(match.group(1)))
        return onsets

    def _digital(self, index: int, start: int, stop: int) -> np.ndarray:
        signal = self._indices[index]
        spr = self._spr[signal]
        if self._map is None or stop <= start:
            return np.zeros(0, dtype=np.int32)
        first, last = start // spr, (stop - 1) // spr + 1
        offset = self._offsets[signal]
        block = self._map[first:last, offset : offset + spr * self._bps]
        raw = np.ascontiguousarray(block).reshape(-1)
        if self._bps == 2:
            values = raw.view("<i2").astype(np.int32)
        else:
            triples = raw.reshape(-1, 3).astype(np.int32)
            values = triples[:, 0] | (triples[:, 1] << 8) | (triples[:, 2] << 16)
            values = np.where(values >= 1 << 23, values - (1 << 24), values)
        skip = start - first * spr
        return np.asarray(values[skip : skip + (stop - start)])

    def read_digital(self, index: int, start: int, stop: int) -> np.ndarray | None:
        return self._digital(index, start, stop)

    def positions(self) -> dict[str, tuple[float, float, float]]:
        return {}  # EDF/BDF headers hold no electrode positions

    def read_many(self, indices: Sequence[int], start: int, stop: int) -> np.ndarray:
        return np.vstack([self.read(i, start, stop) for i in indices]) if indices else np.zeros((0, 0))

    def read(self, index: int, start: int, stop: int) -> np.ndarray:
        signal = self.header.signals[self._indices[index]]
        digital = self._digital(index, start, stop).astype(np.float64)
        scale = unit_scale(signal.unit)
        if (
            signal.physical_min is None
            or signal.physical_max is None
            or signal.digital_min is None
            or signal.digital_max is None
            or signal.digital_max == signal.digital_min
        ):
            return digital * scale
        gain = (signal.physical_max - signal.physical_min) / (signal.digital_max - signal.digital_min)
        return ((digital - signal.digital_min) * gain + signal.physical_min) * scale

    def time_s(self, index: int, sample: int) -> float:
        spr = self._spr[self._indices[index]]
        record, within = divmod(sample, spr)
        rate = float(Fraction(spr) / self._duration)
        if self._onsets is not None and record < len(self._onsets):
            return self._onsets[record] + within / rate
        return float(record * self._duration) + within / rate

    def close(self) -> None:
        self._map = None


class MneSignals:
    """BrainVision, EEGLAB and FIF through MNE (``preload=False``)."""

    clipping_method = "plateau"

    def __init__(self, path: Path, recording: Recording, eeg_names: Sequence[str], reader: Any) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.raw = reader(path, preload=False, verbose="error")
        rate = float(self.raw.info["sfreq"])
        # MNE makes repeated names unique; the same names find the channels of the recording
        by_name = dict(
            zip(unique_names([ch.name for ch in recording.channels]), recording.channels, strict=True)
        )
        present = set(self.raw.ch_names)
        names = [name for name in eeg_names if name in present]
        self._picks = [self.raw.ch_names.index(name) for name in names]
        floating = _floating_point(path, recording)
        channels = []
        for name in names:
            channel = by_name.get(name)
            lsb = None
            if not floating and channel is not None and channel.resolution:
                lsb = abs(channel.resolution) * unit_scale(channel.unit)
            channels.append(
                SignalChannel(
                    name=name, rate_hz=rate, lsb_uv=lsb, digital_limits=None, n_samples=int(self.raw.n_times)
                )
            )
        self.channels = tuple(channels)
        self._rate = rate

    def read(self, index: int, start: int, stop: int) -> np.ndarray:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            data = self.raw.get_data(picks=[self._picks[index]], start=start, stop=stop, verbose="error")
        return np.asarray(data[0], dtype=np.float64) * 1e6  # MNE gives EEG in volts

    def read_digital(self, index: int, start: int, stop: int) -> np.ndarray | None:
        return None

    def positions(self) -> dict[str, tuple[float, float, float]]:
        """Positions stored in the file, in the head frame as MNE reads them (m); none in another frame."""
        from neurogrid.quality.positions import usable

        montage = self.raw.get_montage() if self.raw is not None else None
        if montage is None:
            return {}
        found = montage.get_positions()
        if found.get("coord_frame") != "head":
            return {}
        names = {c.name for c in self.channels}
        return usable({name: value for name, value in found["ch_pos"].items() if name in names})

    def read_many(self, indices: Sequence[int], start: int, stop: int) -> np.ndarray:
        """Samples [start, stop) of several channels at once (one read of the multiplexed block)."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            data = self.raw.get_data(picks=[self._picks[i] for i in indices], start=start, stop=stop)
        return np.asarray(data, dtype=np.float64) * 1e6

    def time_s(self, index: int, sample: int) -> float:
        return sample / self._rate

    def close(self) -> None:
        self.raw = None


def _floating_point(path: Path, recording: Recording) -> bool:
    """EEGLAB and FIF hold floating-point samples; BrainVision only with IEEE_FLOAT_32 (A-18)."""
    if recording.format != "BrainVision":
        return True
    from neurogrid.io.brainvision import parse_vhdr

    try:
        header = parse_vhdr(path)
    except Exception:  # the adapter already reported the header; float is the cautious assumption
        return True
    return header.binary.get("binaryformat", "").upper() == "IEEE_FLOAT_32"


def open_signals(path: Path, recording: Recording) -> SignalSource:
    """The signal source for the EEG channels of a recording (types after A-04 merging)."""
    if recording.format in ("EDF", "BDF"):
        return EdfSignals(path, recording, [ch.name for ch in recording.channels if ch.type == "EEG"])
    labels = unique_names([ch.name for ch in recording.channels])
    eeg = [label for label, ch in zip(labels, recording.channels, strict=True) if ch.type == "EEG"]
    import mne

    readers = {
        "BrainVision": mne.io.read_raw_brainvision,
        "EEGLAB": mne.io.read_raw_eeglab,
        "FIF": lambda p, **kw: mne.io.read_raw_fif(p, allow_maxshield=True, **kw),
    }
    return MneSignals(path, recording, eeg, readers[recording.format])


__all__ = ["EdfHeader", "SignalChannel", "SignalSource", "open_signals", "unique_names", "unit_scale"]
