"""Signal sources of the quality metrics: the own EDF/BDF reader and the MNE reader for BrainVision, EEGLAB
and FIF (A-12, A-18, A-24, A-60, A-77, M07, M08, NG-N02).

The EDF/BDF files are written by hand here, so that every digital value, unit, range and record onset is known
exactly; the generators of tools/gen_fixtures.py are used where their output is the realistic case.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import gen_fixtures
from neurogrid.io import ADAPTERS
from neurogrid.model.dataset import Recording
from neurogrid.quality.source import (
    EdfSignals,
    MneSignals,
    SignalChannel,
    open_signals,
    unique_names,
    unit_scale,
)

ANNOTATION_SPR = 16  # samples of the EDF+/BDF+ annotation signal per data record in the hand-written files
EDF_LIMITS = (-32768, 32767)
BDF_LIMITS = (-8388608, 8388607)


# --- writers ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Signal:
    """One data signal of a hand-written EDF/BDF file: its digital samples, one data record after another."""

    label: str
    digital: np.ndarray
    spr: int
    unit: str = "uV"
    physical: tuple[str, str] = ("-3276.8", "3276.7")
    limits: tuple[int, int] = EDF_LIMITS


def _field(text: str, width: int) -> bytes:
    raw = text.encode("ascii")
    assert len(raw) <= width, text
    return raw.ljust(width, b" ")


def _samples(values: np.ndarray, bdf: bool) -> bytes:
    """Little-endian 16-bit (EDF) or 24-bit two's complement (BDF) samples."""
    if bdf:
        return np.asarray(values, dtype="<i4").view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    return np.asarray(values, dtype="<i2").tobytes()


def _write_edf(
    path: Path,
    signals: Sequence[_Signal],
    *,
    duration: str = "1",
    bdf: bool = False,
    plus: str = "",
    onsets: Sequence[str] | None = None,
    declared_records: str | None = None,
    truncate_bytes: int = 0,
) -> Path:
    """EDF/BDF (``plus``: EDF+/BDF+ with an annotation signal whose first TAL per record holds ``onsets``)."""
    records = max((len(s.digital) // s.spr for s in signals if s.spr), default=0)
    assert all(len(s.digital) == records * s.spr for s in signals)
    bps = 3 if bdf else 2
    entries = [(s.label, s.unit, s.physical, s.limits, s.spr) for s in signals]
    if plus:
        limits = BDF_LIMITS if bdf else EDF_LIMITS
        label = "BDF Annotations" if bdf else "EDF Annotations"
        entries.append((label, "", ("-1", "1"), limits, ANNOTATION_SPR))
        onsets = onsets if onsets is not None else [f"+{record}" for record in range(records)]
        assert len(onsets) == records
    ns = len(entries)
    header = bytearray(b"\xffBIOSEMI" if bdf else _field("0", 8))
    header += _field("X X X X", 80) + _field("Startdate X X X X", 80)
    header += _field("01.01.85", 8) + _field("00.00.00", 8)
    header += _field(str(256 * (ns + 1)), 8)
    header += _field(f"{'BDF' if bdf else 'EDF'}+{plus}" if plus else ("24BIT" if bdf else ""), 44)
    header += _field(declared_records if declared_records is not None else str(records), 8)
    header += _field(duration, 8)
    header += _field(str(ns), 4)
    columns: list[tuple[list[str], int]] = [
        ([e[0] for e in entries], 16),
        (["AgAgCl electrode"] * ns, 80),
        ([e[1] for e in entries], 8),
        ([e[2][0] for e in entries], 8),
        ([e[2][1] for e in entries], 8),
        ([str(e[3][0]) for e in entries], 8),
        ([str(e[3][1]) for e in entries], 8),
        (["HP:0.1Hz LP:100Hz"] * ns, 80),
        ([str(e[4]) for e in entries], 8),
        ([""] * ns, 32),
    ]
    for values, width in columns:
        for value in values:
            header += _field(value, width)
    assert len(header) == 256 * (ns + 1)
    body = bytearray()
    for record in range(records):
        for signal in signals:
            body += _samples(signal.digital[record * signal.spr : (record + 1) * signal.spr], bdf)
        if plus and onsets is not None:
            tal = f"{onsets[record]}\x14\x14\x00".encode("ascii")
            body += tal.ljust(ANNOTATION_SPR * bps, b"\x00")
    data = bytes(header) + bytes(body)
    path.write_bytes(data[: len(data) - truncate_bytes])
    return path


def _write_brainvision(
    vhdr: Path,
    data: np.ndarray,
    labels: Sequence[str],
    *,
    binary_format: str,
    resolutions: Sequence[str],
    units: Sequence[str],
    sfreq: int = 500,
) -> Path:
    """BrainVision triple, multiplexed; ``data`` is channel x time in the stored (digital or float) values."""
    channels = "".join(
        f"Ch{i}={label},,{resolution},{unit}\n"
        for i, (label, resolution, unit) in enumerate(zip(labels, resolutions, units, strict=True), start=1)
    )
    vhdr.write_bytes(
        (
            "Brain Vision Data Exchange Header File Version 1.0\n\n"
            f"[Common Infos]\nCodepage=UTF-8\nDataFile={vhdr.stem}.eeg\nMarkerFile={vhdr.stem}.vmrk\n"
            "DataFormat=BINARY\nDataOrientation=MULTIPLEXED\n"
            f"NumberOfChannels={len(labels)}\nSamplingInterval={1_000_000 // sfreq}\n\n"
            f"[Binary Infos]\nBinaryFormat={binary_format}\n\n[Channel Infos]\n{channels}"
        ).encode()
    )
    vhdr.with_suffix(".vmrk").write_bytes(
        (
            "Brain Vision Data Exchange Marker File, Version 1.0\n\n"
            f"[Common Infos]\nCodepage=UTF-8\nDataFile={vhdr.stem}.eeg\n\n"
            "[Marker Infos]\nMk1=New Segment,,1,1,0\n"
        ).encode()
    )
    dtype = "<f4" if binary_format == "IEEE_FLOAT_32" else "<i2"
    vhdr.with_suffix(".eeg").write_bytes(np.ascontiguousarray(data.T).astype(dtype).tobytes())
    return vhdr


def _write_eeglab(
    path: Path,
    data_uv: np.ndarray,
    labels: Sequence[str],
    types: Sequence[str],
    positions_mm: dict[str, tuple[float, float, float]],
    sfreq: float = 250.0,
) -> Path:
    """EEGLAB .set + float32 .fdt with chanlocs X/Y/Z in mm (EEGLAB frame: X to the nose, Y to the left)."""
    import scipy.io

    empty = np.array([])
    chanlocs = np.zeros((1, len(labels)), dtype=[(key, "O") for key in ("labels", "type", "X", "Y", "Z")])
    for index, (label, kind) in enumerate(zip(labels, types, strict=True)):
        xyz = positions_mm.get(label)
        coords: tuple[Any, Any, Any] = xyz if xyz is not None else (empty, empty, empty)
        chanlocs[0, index] = (label, kind, *coords)
    fdt = path.with_suffix(".fdt")
    points = data_uv.shape[1]
    eeg: dict[str, Any] = {
        "setname": "synthetic",
        "filename": path.name,
        "filepath": "",
        "nbchan": float(len(labels)),
        "trials": 1.0,
        "pnts": float(points),
        "srate": float(sfreq),
        "xmin": 0.0,
        "xmax": (points - 1) / sfreq,
        "times": empty,
        "data": fdt.name,
        "datfile": fdt.name,
        "icaact": empty,
        "icawinv": empty,
        "icasphere": empty,
        "icaweights": empty,
        "icachansind": empty,
        "chanlocs": chanlocs,
        "urchanlocs": empty,
        "chaninfo": {"plotrad": empty, "shrink": empty, "nosedir": "+X"},
        "ref": "common",
        "event": empty,
        "urevent": empty,
        "epoch": empty,
        "reject": empty,
        "stats": empty,
        "etc": empty,
        "history": "",
    }
    fdt.write_bytes(np.asarray(data_uv, dtype="<f4").T.tobytes())
    scipy.io.savemat(path, {"EEG": eeg}, appendmat=False, format="5", oned_as="row")
    return path


def _write_fif(
    path: Path,
    data_v: np.ndarray,
    names: Sequence[str],
    types: Sequence[str],
    positions_m: dict[str, tuple[float, float, float]] | None,
    sfreq: float = 250.0,
) -> Path:
    """Raw FIF in double precision, with a head-frame montage when ``positions_m`` is given."""
    import mne

    info = mne.create_info(list(names), sfreq, list(types))
    raw = mne.io.RawArray(data_v, info, verbose="error")
    if positions_m is not None:
        montage = mne.channels.make_dig_montage(ch_pos=positions_m, coord_frame="head")
        raw.set_montage(montage, on_missing="ignore", verbose="error")
    raw.save(path, fmt="double", overwrite=True, verbose="error")
    return path


def _recording(path: Path) -> Recording:
    """The data model of the file as the format adapter reads it (the input of open_signals)."""
    return ADAPTERS[path.suffix].read(path, recording_id="rec", relative_path=path.name)


def _ramp(n: int, start: int, step: int, limits: tuple[int, int]) -> np.ndarray:
    return np.clip(start + step * np.arange(n, dtype=np.int64), *limits)


# --- unit_scale -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("unit", "factor"),
    [
        ("uV", 1.0),
        ("UV", 1.0),
        ("µV", 1.0),  # micro sign U+00B5
        ("μV", 1.0),  # Greek mu U+03BC
        ("microvolt", 1.0),
        ("mV", 1e3),
        (" mV ", 1e3),
        ("V", 1e6),
        ("v", 1e6),
        ("nV", 1e-3),
        ("", 1.0),
        (None, 1.0),
        ("furlong", 1.0),
        ("%", 1.0),
    ],
)
def test_unit_scale_converts_header_units_to_microvolts(unit: str | None, factor: float) -> None:
    """A-18, A-77: header units to µV; an empty or unknown unit is taken as µV, as MNE does."""
    assert unit_scale(unit) == pytest.approx(factor, rel=1e-15)


# --- EdfSignals: values, units, ranges --------------------------------------------------------------------


def test_edf_reads_digital_values_and_scales_them_to_microvolts(tmp_path: Path) -> None:
    """A-24, M08: digital values as written; physical = (d - dmin) * gain + pmin, converted to µV per unit."""
    spr = 8
    fp1 = np.array([-32768, -1, 0, 1, 32767, 10, -10, 1234] * 2)  # 0.1 µV per step, symmetric
    fp2 = np.array([-1000, -200, 0, 200, 1000, 1, -1, 7] * 2)  # mV: 5 µV per step
    cz = np.array([-100, -50, 0, 50, 100, 1, -1, 2] * 2)  # 0..100 µV on -100..100: an offset
    pz = np.array([-100, -50, 0, 50, 100, 1, -1, 2] * 2)  # physical max below min: inverted polarity
    path = _write_edf(
        tmp_path / "rec.edf",
        [
            _Signal("EEG Fp1", fp1, spr),
            _Signal("EEG Fp2", fp2, spr, unit="mV", physical=("-5", "5"), limits=(-1000, 1000)),
            _Signal("EEG Cz", cz, spr, unit="uV", physical=("0", "100"), limits=(-100, 100)),
            _Signal("EEG Pz", pz, spr, unit="uV", physical=("100", "-100"), limits=(-100, 100)),
        ],
    )
    source = open_signals(path, _recording(path))
    assert isinstance(source, EdfSignals)
    assert [ch.name for ch in source.channels] == ["EEG Fp1", "EEG Fp2", "EEG Cz", "EEG Pz"]
    expected_uv = [fp1 * 0.1, fp2 * 5.0, (cz + 100) * 0.5, -pz.astype(np.float64)]
    for index, (digital, physical) in enumerate(zip([fp1, fp2, cz, pz], expected_uv, strict=True)):
        read_digital = source.read_digital(index, 0, len(digital))
        assert read_digital is not None
        np.testing.assert_array_equal(read_digital, digital)
        values = source.read(index, 0, len(digital))
        assert values.dtype == np.float64
        np.testing.assert_allclose(values, physical, rtol=0, atol=1e-9)
    lsb = [ch.lsb_uv for ch in source.channels]
    assert lsb == pytest.approx([6553.5 / 65535, 5.0, 0.5, 1.0], rel=1e-12)
    assert [ch.digital_limits for ch in source.channels] == [
        EDF_LIMITS,
        (-1000, 1000),
        (-100, 100),
        (-100, 100),
    ]
    assert {ch.rate_hz for ch in source.channels} == {8.0}
    assert {ch.n_samples for ch in source.channels} == {16}
    assert source.clipping_method == "range"
    assert source.positions() == {}  # EDF headers hold no electrode positions


def test_bdf_reads_24_bit_values_with_sign_extension(tmp_path: Path) -> None:
    """A-24: BDF samples are 24-bit two's complement; negative values are sign-extended, limits are exact."""
    values = np.array(
        [-8388608, -8388607, -65536, -256, -255, -1, 0, 1, 127, 128, 255, 256, 65535, 65536, -4660, 8388607]
    )
    physical = ("-8388608", "8388607")  # one µV (or nV) per digital step
    path = _write_edf(
        tmp_path / "rec.bdf",
        [
            _Signal("Fp1", values, 16, unit="uV", physical=physical, limits=BDF_LIMITS),
            _Signal("Fp2", values[::-1].copy(), 16, unit="nV", physical=physical, limits=BDF_LIMITS),
        ],
        bdf=True,
    )
    assert path.stat().st_size == 256 * 3 + 2 * 16 * 3  # three bytes per sample
    source = open_signals(path, _recording(path))
    assert isinstance(source, EdfSignals)
    digital = source.read_digital(0, 0, 16)
    assert digital is not None
    np.testing.assert_array_equal(digital, values)
    reversed_digital = source.read_digital(1, 0, 16)
    assert reversed_digital is not None
    np.testing.assert_array_equal(reversed_digital, values[::-1])
    np.testing.assert_allclose(source.read(0, 0, 16), values.astype(np.float64), rtol=0, atol=1e-9)
    np.testing.assert_allclose(source.read(1, 0, 16), values[::-1] * 1e-3, rtol=0, atol=1e-12)
    assert [ch.lsb_uv for ch in source.channels] == pytest.approx([1.0, 1e-3], rel=1e-12)
    assert [ch.digital_limits for ch in source.channels] == [BDF_LIMITS, BDF_LIMITS]
    assert [ch.rate_hz for ch in source.channels] == [16.0, 16.0]


def test_edf_channel_without_a_digital_range_has_no_lsb_and_no_limits(tmp_path: Path) -> None:
    """M08, A-24: digital min = max gives no gain: no LSB, no range limits (no range clipping), and the
    values are the digital numbers in the channel unit; the other channels are unaffected."""
    values = np.array([3, -2, 100, 0, 7, 7, -1, 1])
    path = _write_edf(
        tmp_path / "rec.edf",
        [
            _Signal("EEG Fp1", values, 4, unit="mV", limits=(100, 100)),
            _Signal("EEG Fp2", values, 4, unit="uV", physical=("-5", "5"), limits=(-10, 10)),
        ],
    )
    source = open_signals(path, _recording(path))
    assert [(ch.lsb_uv, ch.digital_limits) for ch in source.channels] == [
        (None, None),
        (pytest.approx(0.5), (-10, 10)),
    ]
    np.testing.assert_allclose(source.read(0, 0, 8), values * 1e3, rtol=0, atol=1e-9)
    np.testing.assert_allclose(source.read(1, 0, 8), values * 0.5, rtol=0, atol=1e-9)


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (["Fp1", "Fp2", "Cz"], ["Fp1", "Fp2", "Cz"]),
        (["Fp1", "Cz", "Fp1"], ["Fp1-0", "Cz", "Fp1-1"]),
        (["Fp1", "Fp1-0", "Fp1"], ["Fp1-1", "Fp1-0", "Fp1-2"]),  # a suffix that is taken is skipped
    ],
)
def test_unique_names_follow_mne(names: list[str], expected: list[str]) -> None:
    """Repeated labels get MNE's "-0", "-1" suffixes, so values are keyed by unique names."""
    assert unique_names(names) == expected


def test_repeated_edf_labels_are_streamed_as_separate_channels(tmp_path: Path) -> None:
    """Two signals with the same label are two channels (named like MNE names them), not one."""
    path = tmp_path / "dup.edf"
    gen_fixtures.write_edf(path, seed=5, labels=("Fp1", "Fp2", "Fp1", "Cz"))
    recording = ADAPTERS[".edf"].read(path, recording_id="dup", relative_path=path.name)
    source = open_signals(path, recording)
    assert [c.name for c in source.channels] == ["EEG Fp1-0", "EEG Fp2", "EEG Fp1-1", "EEG Cz"]


@pytest.mark.parametrize("bdf", [False, True])
def test_gen_fixtures_recording_reads_back_within_half_a_step(tmp_path: Path, bdf: bool) -> None:
    """A-24: the generator's µV signal comes back within half a digital step, the digital values exactly."""
    path = tmp_path / ("rec.bdf" if bdf else "rec.edf")
    gen_fixtures.write_edf(path, seed=41, bdf=bdf)
    microvolts = gen_fixtures._microvolts(512, 10, len(gen_fixtures.EEG_LABELS), 41)
    limits = BDF_LIMITS if bdf else EDF_LIMITS
    scale = (limits[1] - limits[0]) / 1000.0
    source = open_signals(path, _recording(path))
    assert [ch.name for ch in source.channels] == [f"EEG {label}" for label in gen_fixtures.EEG_LABELS]
    for index, signal in enumerate(microvolts):
        channel = source.channels[index]
        assert channel.digital_limits == limits and channel.n_samples == 5120 and channel.rate_hz == 512.0
        assert channel.lsb_uv == pytest.approx(1 / scale, rel=1e-12)
        expected_digital = np.clip(np.round((signal + 500.0) * scale + limits[0]), *limits)
        read_digital = source.read_digital(index, 0, 5120)
        assert read_digital is not None
        np.testing.assert_array_equal(read_digital, expected_digital)
        error = np.abs(source.read(index, 0, 5120) - signal)
        assert float(error.max()) <= 0.5 / scale + 1e-9


def test_edf_selects_the_eeg_channels_only(tmp_path: Path) -> None:
    """A-04, A-18: annotation and non-EEG signals are no signal channels; types follow the merged
    recording."""
    spr = 4
    path = _write_edf(
        tmp_path / "rec.edf",
        [
            _Signal("EEG Fp1", _ramp(8, 0, 1, EDF_LIMITS), spr),
            _Signal("ECG II", _ramp(8, 100, 1, EDF_LIMITS), spr),
            _Signal("EOG L", _ramp(8, 200, 1, EDF_LIMITS), spr),
            _Signal("EEG C3", _ramp(8, 300, 1, EDF_LIMITS), spr),
            _Signal("EEG O1", _ramp(8, 400, 1, EDF_LIMITS), spr),
        ],
        plus="C",
    )
    recording = _recording(path)
    assert [ch.type for ch in recording.channels] == ["EEG", "ECG", "EOG", "EEG", "EEG", "ANNOT"]
    source = open_signals(path, recording)
    assert [ch.name for ch in source.channels] == ["EEG Fp1", "EEG C3", "EEG O1"]
    np.testing.assert_array_equal(source.read_digital(1, 0, 8), _ramp(8, 300, 1, EDF_LIMITS))
    # a channel the sidecar types as EOG (merged into the recording, A-04) is not read as EEG
    recording.channels[3] = recording.channels[3].model_copy(update={"type": "EOG"})
    merged = open_signals(path, recording)
    assert [ch.name for ch in merged.channels] == ["EEG Fp1", "EEG O1"]
    np.testing.assert_array_equal(merged.read_digital(1, 0, 8), _ramp(8, 400, 1, EDF_LIMITS))


def test_edf_signal_without_samples_is_no_channel(tmp_path: Path) -> None:
    """A-24: an EEG signal with 0 samples per record holds no data and is left out."""
    path = _write_edf(
        tmp_path / "rec.edf",
        [
            _Signal("EEG Fp1", _ramp(8, 0, 1, EDF_LIMITS), 4),
            _Signal("EEG Fp2", np.zeros(0, dtype=np.int64), 0),
        ],
    )
    source = open_signals(path, _recording(path))
    assert [ch.name for ch in source.channels] == ["EEG Fp1"]
    np.testing.assert_array_equal(source.read_digital(0, 0, 8), np.arange(8))


def test_edf_rates_per_channel_follow_the_record_duration(tmp_path: Path) -> None:
    """A-24, A-77: each signal has its own rate, samples per record / record duration (here 0.5 s)."""
    records = 3
    fast = _ramp(8 * records, -500, 3, EDF_LIMITS)
    slow = _ramp(4 * records, 700, -5, EDF_LIMITS)
    path = _write_edf(
        tmp_path / "rec.edf",
        [_Signal("EEG Fp1", fast, 8), _Signal("EEG Fp2", slow, 4), _Signal("EEG Cz", fast[::-1].copy(), 8)],
        duration="0.5",
    )
    source = open_signals(path, _recording(path))
    assert source.channels == (
        SignalChannel("EEG Fp1", 16.0, pytest.approx(0.1), EDF_LIMITS, 24),
        SignalChannel("EEG Fp2", 8.0, pytest.approx(0.1), EDF_LIMITS, 12),
        SignalChannel("EEG Cz", 16.0, pytest.approx(0.1), EDF_LIMITS, 24),
    )
    np.testing.assert_array_equal(source.read_digital(1, 0, 12), slow)
    # without record onsets the time is the record count times the duration
    assert source.time_s(0, 0) == 0.0
    assert source.time_s(0, 5) == pytest.approx(5 / 16)
    assert source.time_s(0, 8) == pytest.approx(0.5)
    assert source.time_s(0, 19) == pytest.approx(19 / 16)
    assert source.time_s(1, 4) == pytest.approx(0.5)
    assert source.time_s(1, 11) == pytest.approx(11 / 8)


def test_edf_reads_across_data_records(tmp_path: Path) -> None:
    """NG-N02: any sample range is read from the records it spans; the end is clamped to the data."""
    spr, records = 5, 4
    first = _ramp(spr * records, -1000, 37, EDF_LIMITS)
    second = _ramp(spr * records, 900, -11, EDF_LIMITS)
    path = _write_edf(tmp_path / "rec.edf", [_Signal("EEG Fp1", first, spr), _Signal("EEG Fp2", second, spr)])
    source = open_signals(path, _recording(path))
    for start, stop in [(0, 20), (3, 9), (4, 5), (5, 10), (7, 18), (19, 20)]:
        np.testing.assert_array_equal(source.read_digital(0, start, stop), first[start:stop])
        np.testing.assert_allclose(source.read(1, start, stop), second[start:stop] * 0.1, atol=1e-9)
    assert len(source.read(0, 17, 40)) == 3  # the end of the recording
    assert source.read(0, 6, 6).size == 0 and source.read(0, 9, 3).size == 0
    digital = source.read_digital(0, 6, 6)
    assert digital is not None and digital.size == 0


def test_edf_read_many_rows_equal_read(tmp_path: Path) -> None:
    """NG-N02: read_many gives one row per channel, each equal to read of that channel."""
    spr = 6
    signals = [
        _Signal(f"EEG {name}", _ramp(spr * 3, 10 * k, k + 1, EDF_LIMITS), spr) for k, name in enumerate("ABC")
    ]
    path = _write_edf(tmp_path / "rec.edf", signals)
    source = open_signals(path, _recording(path))
    block = source.read_many([2, 0, 1], 4, 15)
    assert block.shape == (3, 11)
    for row, index in zip(block, [2, 0, 1], strict=True):
        np.testing.assert_array_equal(row, source.read(index, 4, 15))
    assert source.read_many([], 0, 10).shape == (0, 0)


# --- EdfSignals: complete records, EDF+D ---------------------------------------------------------------


@pytest.mark.parametrize("bdf", [False, True])
def test_truncated_last_record_is_ignored(tmp_path: Path, bdf: bool) -> None:
    """A-24, M01-02: only complete data records are read; the samples of a cut-off record are not used."""
    spr, records = 4, 3
    limits = BDF_LIMITS if bdf else EDF_LIMITS
    first = _ramp(spr * records, -7, 3, limits)
    second = _ramp(spr * records, 5, -2, limits)
    path = _write_edf(
        tmp_path / ("rec.bdf" if bdf else "rec.edf"),
        [_Signal("EEG Fp1", first, spr, limits=limits), _Signal("EEG Fp2", second, spr, limits=limits)],
        bdf=bdf,
        truncate_bytes=(3 if bdf else 2) * spr + 1,  # the last record misses its second signal and a byte
    )
    source = open_signals(path, _recording(path))
    assert [ch.n_samples for ch in source.channels] == [8, 8]
    np.testing.assert_array_equal(source.read_digital(0, 0, 12), first[:8])
    np.testing.assert_array_equal(source.read_digital(1, 0, 12), second[:8])


def test_record_count_is_the_smaller_of_declared_and_complete(tmp_path: Path) -> None:
    """A-24: a header declaring fewer records than present limits the read; -1 (unknown) reads them all."""
    spr = 4
    values = _ramp(spr * 3, 1, 1, EDF_LIMITS)
    declared_two = _write_edf(tmp_path / "two.edf", [_Signal("EEG Fp1", values, spr)], declared_records="2")
    source = open_signals(declared_two, _recording(declared_two))
    assert source.channels[0].n_samples == 8
    np.testing.assert_array_equal(source.read_digital(0, 0, 12), values[:8])
    unknown = _write_edf(tmp_path / "unknown.edf", [_Signal("EEG Fp1", values, spr)], declared_records="-1")
    source = open_signals(unknown, _recording(unknown))
    assert source.channels[0].n_samples == 12
    np.testing.assert_array_equal(source.read_digital(0, 0, 12), values)


def test_edf_without_a_complete_record_has_no_samples(tmp_path: Path) -> None:
    """A-24: a file cut inside its first record is measured on nothing, without an error."""
    path = _write_edf(
        tmp_path / "rec.edf", [_Signal("EEG Fp1", _ramp(8, 0, 1, EDF_LIMITS), 8)], truncate_bytes=1
    )
    source = open_signals(path, _recording(path))
    assert [ch.n_samples for ch in source.channels] == [0]
    assert source.read(0, 0, 8).size == 0
    assert source.time_s(0, 0) == 0.0


@pytest.mark.parametrize("bdf", [False, True])
def test_edf_plus_d_time_follows_the_record_onsets(tmp_path: Path, bdf: bool) -> None:
    """A-12, A-77: EDF+D/BDF+D times follow the onsets of the first TAL per record, gaps included."""
    limits = BDF_LIMITS if bdf else EDF_LIMITS
    fast = _ramp(4 * 4, 0, 1, limits)
    slow = _ramp(2 * 4, 0, 1, limits)
    path = _write_edf(
        tmp_path / ("rec.bdf" if bdf else "rec.edf"),
        [_Signal("EEG Fp1", fast, 4, limits=limits), _Signal("EEG Fp2", slow, 2, limits=limits)],
        bdf=bdf,
        plus="D",
        onsets=["+0", "+1", "+5", "+6.5"],
    )
    recording = _recording(path)
    assert recording.discontinuous
    source = open_signals(path, recording)
    assert [ch.name for ch in source.channels] == ["EEG Fp1", "EEG Fp2"]  # not the annotation signal
    assert [ch.n_samples for ch in source.channels] == [16, 8]  # the sample count ignores the gaps
    times = [source.time_s(0, sample) for sample in (0, 3, 4, 7, 8, 10, 12, 15)]
    assert times == pytest.approx([0.0, 0.75, 1.0, 1.75, 5.0, 5.5, 6.5, 7.25])
    assert [source.time_s(1, sample) for sample in (0, 2, 3, 4, 5, 6, 7)] == pytest.approx(
        [0.0, 1.0, 1.5, 5.0, 5.5, 6.5, 7.0]
    )
    np.testing.assert_array_equal(source.read_digital(0, 0, 16), fast)  # the TAL bytes are no samples


def test_edf_plus_d_without_valid_tal_follows_the_record_count(tmp_path: Path) -> None:
    """A-12: a record without a valid time-keeping TAL makes the record count the time base."""
    path = _write_edf(
        tmp_path / "rec.edf",
        [_Signal("EEG Fp1", _ramp(12, 0, 1, EDF_LIMITS), 4)],
        plus="D",
        onsets=["+0", "+5", "no-onset"],
    )
    source = open_signals(path, _recording(path))
    assert [source.time_s(0, sample) for sample in (0, 4, 9)] == pytest.approx([0.0, 1.0, 2.25])


def test_edf_plus_d_without_annotation_signal_follows_the_record_count(tmp_path: Path) -> None:
    """A-12: an EDF+D header without an annotation signal has no record onsets; the record count is used."""
    path = _write_edf(
        tmp_path / "rec.edf", [_Signal("EEG Fp1", _ramp(12, 0, 1, EDF_LIMITS), 4)], duration="2"
    )
    content = bytearray(path.read_bytes())
    content[192:236] = _field("EDF+D", 44)
    path.write_bytes(bytes(content))
    recording = _recording(path)
    assert recording.discontinuous
    source = open_signals(path, recording)
    assert [source.time_s(0, sample) for sample in (0, 3, 4, 11)] == pytest.approx([0.0, 1.5, 2.0, 5.5])


def test_edf_plus_d_fixture_has_its_gap(tmp_path: Path) -> None:
    """A-12: the generator's EDF+D recording (records at 0-4 s and 10-14 s) gives times with the gap."""
    path = tmp_path / "rec.edf"
    gen_fixtures.write_edf(path, seed=20, plus="D", record_onsets=(0, 1, 2, 3, 4, 10, 11, 12, 13, 14))
    source = open_signals(path, _recording(path))
    assert len(source.channels) == len(gen_fixtures.EEG_LABELS)
    assert source.time_s(0, 4 * 512 + 511) == pytest.approx(4 + 511 / 512)
    assert source.time_s(0, 5 * 512) == pytest.approx(10.0)
    assert source.time_s(7, 9 * 512 + 256) == pytest.approx(14.5)


# --- EdfSignals: invalid headers and close ----------------------------------------------------------------


@pytest.mark.parametrize("duration", ["0", "-1", "abc", ""])
def test_invalid_record_duration_raises(tmp_path: Path, duration: str) -> None:
    """A-24: without a positive record duration there is no time base; the job reports read.failed."""
    path = _write_edf(
        tmp_path / "rec.edf", [_Signal("EEG Fp1", _ramp(8, 0, 1, EDF_LIMITS), 4)], duration=duration
    )
    with pytest.raises(ValueError, match="record duration"):
        open_signals(path, _recording(path))


def test_zero_samples_per_record_raises(tmp_path: Path) -> None:
    """A-24: a header whose data records hold no samples cannot be read."""
    path = _write_edf(
        tmp_path / "rec.edf",
        [
            _Signal("EEG Fp1", np.zeros(0, dtype=np.int64), 0),
            _Signal("EEG Fp2", np.zeros(0, dtype=np.int64), 0),
        ],
        declared_records="3",
    )
    with pytest.raises(ValueError, match="no samples per data record"):
        EdfSignals(path, _recording(path), ["EEG Fp1", "EEG Fp2"])


def test_edf_close_releases_the_file(tmp_path: Path) -> None:
    """A-24: close() drops the memory map, so the file is no longer held open (Windows locks mapped files)."""
    path = _write_edf(tmp_path / "rec.edf", [_Signal("EEG Fp1", _ramp(16, 0, 1, EDF_LIMITS), 8)])
    source = open_signals(path, _recording(path))
    source.read(0, 0, 16)
    if sys.platform == "win32":
        with pytest.raises(PermissionError):
            path.unlink()  # still mapped
    source.close()
    path.unlink()
    assert not path.exists()


# --- MneSignals --------------------------------------------------------------------------------------------


def test_brainvision_int16_lsb_from_resolution(tmp_path: Path) -> None:
    """A-18: INT_16 BrainVision: one step = resolution in the channel's unit; values in µV as written."""
    digital = np.array([[-32768, -1, 0, 1, 32767, 100, -100, 7]] * 4, dtype=np.int64)
    digital[1] *= -1
    digital = np.clip(digital, -32768, 32767)
    vhdr = _write_brainvision(
        tmp_path / "rec.vhdr",
        digital,
        ["Fp1", "Fp2", "VEOG", "Cz"],
        binary_format="INT_16",
        resolutions=["0.1", "0.0005", "1", "0.5"],
        units=["µV", "mV", "µV", "uV"],
    )
    source = open_signals(vhdr, _recording(vhdr))
    assert isinstance(source, MneSignals)
    assert source.clipping_method == "plateau"
    assert source.channels == (
        SignalChannel("Fp1", 500.0, pytest.approx(0.1), None, 8),
        SignalChannel("Fp2", 500.0, pytest.approx(0.5), None, 8),
        SignalChannel("Cz", 500.0, pytest.approx(0.5), None, 8),
    )
    expected = digital[[0, 1, 3]] * np.array([[0.1], [0.5], [0.5]])
    for index in range(3):
        np.testing.assert_allclose(source.read(index, 0, 8), expected[index], rtol=1e-12, atol=1e-12)
        assert source.read_digital(index, 0, 8) is None
    np.testing.assert_allclose(source.read(2, 2, 6), expected[2, 2:6], rtol=1e-12, atol=1e-12)
    assert source.positions() == {}  # no [Coordinates] in the header
    assert source.time_s(0, 250) == pytest.approx(0.5)


def test_brainvision_fixture_reads_the_written_microvolts(tmp_path: Path) -> None:
    """A-18: the generator's BrainVision file (INT_16, 0.1 µV) comes back as the quantised µV signal."""
    vhdr = tmp_path / "rec.vhdr"
    gen_fixtures.write_brainvision(vhdr, seed=12)
    microvolts = np.stack(gen_fixtures._microvolts(500, 10, len(gen_fixtures.EEG_LABELS), 12))
    source = open_signals(vhdr, _recording(vhdr))
    assert [ch.name for ch in source.channels] == list(gen_fixtures.EEG_LABELS)
    assert [ch.lsb_uv for ch in source.channels] == pytest.approx([0.1] * len(gen_fixtures.EEG_LABELS))
    assert {ch.n_samples for ch in source.channels} == {5000}
    block = source.read_many(range(len(source.channels)), 0, 5000)
    np.testing.assert_allclose(block, np.round(microvolts / 0.1) * 0.1, rtol=0, atol=1e-9)


def test_brainvision_float32_has_no_lsb(tmp_path: Path) -> None:
    """A-18: IEEE_FLOAT_32 data have no digital step; values are the stored floats times the resolution."""
    values = np.array([[1.5, -2.25, 1e-3, 123.456, -0.0, 7.0]] * 2, dtype=np.float32)
    vhdr = _write_brainvision(
        tmp_path / "rec.vhdr",
        values,
        ["C3", "C4"],
        binary_format="IEEE_FLOAT_32",
        resolutions=["1", "0.5"],
        units=["µV", "µV"],
    )
    source = open_signals(vhdr, _recording(vhdr))
    assert [ch.lsb_uv for ch in source.channels] == [None, None]
    assert [ch.digital_limits for ch in source.channels] == [None, None]
    np.testing.assert_allclose(source.read(0, 0, 6), values[0].astype(np.float64), rtol=1e-12)
    np.testing.assert_allclose(source.read(1, 0, 6), values[1].astype(np.float64) * 0.5, rtol=1e-12)


@pytest.mark.parametrize("embedded", [False, True])
def test_eeglab_float_data_in_microvolts(tmp_path: Path, embedded: bool) -> None:
    """A-18, R14: EEGLAB holds float µV (no LSB); the read values are the written float32 samples."""
    path = tmp_path / "rec.set"
    gen_fixtures.write_eeglab(path, seed=17, embedded=embedded)
    written = np.stack(gen_fixtures._microvolts(512, 4, len(gen_fixtures.EEG_LABELS), 17)).astype("<f4")
    source = open_signals(path, _recording(path))
    assert isinstance(source, MneSignals) and source.clipping_method == "plateau"
    assert [ch.name for ch in source.channels] == list(gen_fixtures.EEG_LABELS)
    assert {(ch.rate_hz, ch.lsb_uv, ch.digital_limits, ch.n_samples) for ch in source.channels} == {
        (512.0, None, None, 2048)
    }
    np.testing.assert_allclose(source.read_many(range(8), 0, 2048), written.astype(np.float64), rtol=1e-12)
    np.testing.assert_allclose(source.read(3, 100, 300), written[3, 100:300].astype(np.float64), rtol=1e-12)
    assert source.read_digital(0, 0, 10) is None
    assert source.positions() == {}  # chanlocs without X/Y/Z


def test_eeglab_header_positions_in_head_frame(tmp_path: Path) -> None:
    """A-60: EEGLAB chanlocs (mm, X to the nose, Y to the left) become head-frame metres (-Y, X, Z) / 1000;
    channels that are no EEG or have no position are left out."""
    labels = ["Fp1", "Fp2", "Cz", "HEOG", "Oz", "T7"]
    types = ["EEG", "EEG", "EEG", "EOG", "EEG", "EEG"]
    positions_mm = {
        "Fp1": (84.0, 29.0, -7.0),
        "Fp2": (84.0, -29.0, -7.0),
        "Cz": (0.0, 0.0, 95.0),
        "HEOG": (70.0, 60.0, -30.0),
        "Oz": (-95.0, 0.0, 10.0),
    }
    data = (np.arange(6 * 500, dtype=np.float64).reshape(6, 500) / 7.0 - 200.0).astype(np.float32)
    path = _write_eeglab(tmp_path / "pos.set", data, labels, types, positions_mm)
    source = open_signals(path, _recording(path))
    assert [ch.name for ch in source.channels] == ["Fp1", "Fp2", "Cz", "Oz", "T7"]
    found = source.positions()
    expected = {
        name: (-y / 1000, x / 1000, z / 1000) for name, (x, y, z) in positions_mm.items() if name != "HEOG"
    }
    assert set(found) == set(expected)
    for name, position in expected.items():
        assert found[name] == pytest.approx(position, abs=1e-12)
    np.testing.assert_allclose(
        source.read_many([0, 3, 4], 0, 500), data[[0, 4, 5]].astype(np.float64), rtol=1e-12, atol=1e-12
    )


def test_fif_float_values_and_header_positions(tmp_path: Path) -> None:
    """A-18, A-60: FIF holds float volts (read in µV, no LSB) and head-frame positions of the EEG channels."""
    rng = np.random.default_rng(7)
    data = rng.normal(0.0, 20e-6, (5, 1000))
    positions = {"Fp1": (-0.03, 0.08, 0.0), "Fp2": (0.03, 0.08, 0.0), "Cz": (0.0, 0.0, 0.1)}
    path = _write_fif(
        tmp_path / "rec_raw.fif",
        data,
        ["Fp1", "Fp2", "Cz", "EOG1", "STI 014"],
        ["eeg", "eeg", "eeg", "eog", "stim"],
        positions,
    )
    source = open_signals(path, _recording(path))
    assert isinstance(source, MneSignals) and source.clipping_method == "plateau"
    assert source.channels == tuple(
        SignalChannel(name, 250.0, None, None, 1000) for name in ("Fp1", "Fp2", "Cz")
    )
    np.testing.assert_allclose(source.read_many([0, 1, 2], 0, 1000), data[:3] * 1e6, rtol=1e-12)
    np.testing.assert_allclose(source.read(2, 10, 20), data[2, 10:20] * 1e6, rtol=1e-12)
    for index in range(3):
        np.testing.assert_array_equal(source.read_many([index], 5, 50)[0], source.read(index, 5, 50))
    found = source.positions()
    assert set(found) == set(positions)
    for name, position in positions.items():
        assert found[name] == pytest.approx(position, abs=1e-7)  # FIF stores positions as float32
    assert source.time_s(1, 500) == pytest.approx(2.0)


def test_fif_without_positions_has_none(tmp_path: Path) -> None:
    """A-60: a FIF without a montage gives no header positions (the next montage source is tried)."""
    data = np.random.default_rng(8).normal(0.0, 10e-6, (3, 500))
    path = _write_fif(tmp_path / "rec_raw.fif", data, ["Fp1", "Fp2", "Cz"], ["eeg"] * 3, None)
    source = open_signals(path, _recording(path))
    assert [ch.name for ch in source.channels] == ["Fp1", "Fp2", "Cz"]
    assert source.positions() == {}


def test_mne_positions_in_another_frame_are_not_used(tmp_path: Path) -> None:
    """A-60: positions MNE holds in a frame other than head (here MRI) are not header positions.

    MNE's FIF writer stores head coordinates, so the reader hands over an in-memory recording instead."""
    import mne

    names = ["Fp1", "Fp2", "Cz"]
    positions = {"Fp1": (-0.03, 0.08, 0.0), "Fp2": (0.03, 0.08, 0.0), "Cz": (0.0, 0.0, 0.1)}
    path = _write_fif(tmp_path / "rec_raw.fif", np.zeros((3, 500)), names, ["eeg"] * 3, positions)
    recording = _recording(path)
    montage = mne.channels.make_dig_montage(
        ch_pos=positions, coord_frame="mri", nasion=(0, 0.09, 0), lpa=(-0.07, 0, 0), rpa=(0.07, 0, 0)
    )

    def reader(file: Path, **kwargs: Any) -> Any:
        raw = mne.io.read_raw_fif(file, **kwargs)
        with raw.info._unlock():
            raw.info["dig"] = montage.dig
        return raw

    source = MneSignals(path, recording, names, reader)
    assert source.raw.get_montage().get_positions()["coord_frame"] == "mri"
    assert source.positions() == {}


def test_mne_signals_skip_names_the_file_does_not_have(tmp_path: Path) -> None:
    """A-24: only EEG names present in the file become channels, in the order of the recording."""
    import mne

    data = np.random.default_rng(9).normal(0.0, 10e-6, (3, 500))
    path = _write_fif(tmp_path / "rec_raw.fif", data, ["Fp1", "Fp2", "Cz"], ["eeg"] * 3, None)
    source = MneSignals(path, _recording(path), ["Cz", "Missing", "Fp1"], mne.io.read_raw_fif)
    assert [ch.name for ch in source.channels] == ["Cz", "Fp1"]
    np.testing.assert_allclose(source.read(0, 0, 500), data[2] * 1e6, rtol=1e-12)
    np.testing.assert_allclose(source.read(1, 0, 500), data[0] * 1e6, rtol=1e-12)


def test_mne_signals_close_drops_the_reader(tmp_path: Path) -> None:
    """NG-N02: close() releases the MNE raw object; positions() of a closed source is empty."""
    positions = {"Fp1": (-0.03, 0.08, 0.0), "Fp2": (0.03, 0.08, 0.0), "Cz": (0.0, 0.0, 0.1)}
    path = _write_fif(
        tmp_path / "rec_raw.fif", np.zeros((3, 500)), ["Fp1", "Fp2", "Cz"], ["eeg"] * 3, positions
    )
    source = open_signals(path, _recording(path))
    assert isinstance(source, MneSignals) and source.positions()
    source.close()
    assert source.raw is None
    assert source.positions() == {}
    path.unlink()  # MNE reads without preload but holds no open handle after close


# --- open_signals ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "kind", "clipping"),
    [
        ("rec.edf", EdfSignals, "range"),
        ("rec.bdf", EdfSignals, "range"),
        ("rec.vhdr", MneSignals, "plateau"),
        ("rec.set", MneSignals, "plateau"),
        ("rec_raw.fif", MneSignals, "plateau"),
    ],
)
def test_open_signals_picks_the_reader_by_format(
    tmp_path: Path, name: str, kind: type[EdfSignals | MneSignals], clipping: str
) -> None:
    """A-24: EDF/BDF go through the own memmap reader, BrainVision/EEGLAB/FIF through MNE."""
    path = tmp_path / name
    if name.endswith(".edf"):
        gen_fixtures.write_edf(path, seed=51)
    elif name.endswith(".bdf"):
        gen_fixtures.write_edf(path, seed=52, bdf=True)
    elif name.endswith(".vhdr"):
        gen_fixtures.write_brainvision(path, seed=53)
    elif name.endswith(".set"):
        gen_fixtures.write_eeglab(path, seed=54)
    else:
        labels = list(gen_fixtures.EEG_LABELS)
        _write_fif(path, np.zeros((8, 500)), labels, ["eeg"] * 8, None)
    recording = _recording(path)
    source = open_signals(path, recording)
    try:
        assert type(source) is kind
        assert source.clipping_method == clipping
        assert [ch.name for ch in source.channels] == [ch.name for ch in recording.eeg_channels]
        assert all(ch.n_samples > 0 for ch in source.channels)
        assert (source.read_digital(0, 0, 4) is not None) == (kind is EdfSignals)
    finally:
        source.close()
