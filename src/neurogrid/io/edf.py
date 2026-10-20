"""EDF/EDF+ and BDF/BDF+ adapters (NG-F01, M01, A-24).

The header is parsed by NeuroGrid itself (layout per EDF/EDF+ specification; BDF differs only in the version
field and 24-bit samples). EDF headers are cross-checked with edfio as the PRD requires for M01; edfio does
not read BDF. Data readability is checked with MNE. EDF+D files are read like continuous files; their
record onsets matter only for time ranges of the signal metrics (P3).
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from pathlib import Path

from neurogrid.io.base import HeaderInspection, HeaderUnreadable, mne_read_check
from neurogrid.io.channels import ANNOTATION_LABELS, classify
from neurogrid.io.identifying import (
    DATE_PLACEHOLDER,
    LONG_NUMBER,
    NON_ASCII,
    looks_identifying,
    placeholder,
    real_dates,
)
from neurogrid.model.dataset import Channel, Recording

FIXED_HEADER_BYTES = 256
SIGNAL_HEADER_BYTES = 256
MAX_SIGNALS = 4096

# Per-signal header fields in file order with their widths (EDF specification); offsets follow from them.
SIGNAL_FIELDS: tuple[tuple[str, int], ...] = (
    ("label", 16),
    ("transducer", 80),
    ("unit", 8),
    ("pmin", 8),
    ("pmax", 8),
    ("dmin", 8),
    ("dmax", 8),
    ("prefilter", 80),
    ("spr", 8),
    ("reserved", 32),
)
assert sum(width for _name, width in SIGNAL_FIELDS) == SIGNAL_HEADER_BYTES

# Numeric header fields are plain ASCII decimals (EDF specification). An exponent of at most two digits is
# tolerated; anything else is a header issue. This also bounds every derived value (no overflow, no huge
# powers).
_NUMBER = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d{1,2})?$")

_STARTDATE = re.compile(r"^\d\d\.\d\d\.\d\d$")
_STARTDATE_PLACEHOLDER = re.compile(r"^01\.01\.\d\d$")
_EDFPLUS_SEX = frozenset({"M", "F", "X"})


@dataclass(frozen=True)
class EdfSignal:
    label: str
    unit: str
    physical_min: float | None
    physical_max: float | None
    digital_min: int | None
    digital_max: int | None
    samples_per_record: int | None


@dataclass(frozen=True)
class EdfHeader:
    variant: str  # "EDF" or "BDF"
    plus: str | None  # "C", "D" or None
    n_records: int | None
    record_duration: Fraction | None  # exact value of the ASCII field
    header_bytes: int | None
    signals: tuple[EdfSignal, ...]
    issues: tuple[str, ...]
    identifying_fields: tuple[str, ...]

    @property
    def record_duration_s(self) -> float | None:
        return None if self.record_duration is None else float(self.record_duration)


def _text(raw: bytes) -> tuple[str, bool]:
    ascii_ok = all(32 <= b < 127 for b in raw)
    return raw.decode("ascii", "replace").strip(), ascii_ok


def _fraction(raw: bytes) -> Fraction | None:
    """Exact value of a numeric ASCII field; anything that is not a plain decimal number is None."""
    text = raw.decode("ascii", "replace").strip()
    if not _NUMBER.match(text):
        return None
    return Fraction(text)


def _float(raw: bytes) -> float | None:
    value = _fraction(raw)
    return None if value is None else float(value)


def _int(raw: bytes) -> int | None:
    value = _fraction(raw)
    if value is None or value.denominator != 1:
        return None
    return int(value)


def _valid_startdate(text: str) -> bool:
    """dd.mm.yy that exists in the calendar (EDF specification)."""
    if not _STARTDATE.match(text):
        return False
    try:
        datetime.strptime(text, "%d.%m.%y")
    except ValueError:
        return False
    return True


def _identifying(patient: str, recording: str, startdate: str, plus: str | None) -> tuple[str, ...]:
    """Flag header fields with person identifiers or a real date (A-64). Only field names are returned."""
    found: set[str] = set()
    if plus is not None:
        # EDF+ patient field: code sex birthdate name[ more]. "X" marks an unknown value.
        parts = patient.split()
        sex = parts[1] if len(parts) > 1 else "X"
        personal = [part for index, part in enumerate(parts) if index != 1]
        if any(part.upper() != "X" for part in personal) or sex.upper() not in _EDFPLUS_SEX:
            found.add("patient")
        rec_parts = recording.split()
        if rec_parts[:1] == ["Startdate"]:
            # Startdate dd-MMM-yyyy admin_code technician equipment[ more]; the equipment is not personal.
            date_part = rec_parts[1] if len(rec_parts) > 1 else "X"
            if date_part.upper() != "X" and not DATE_PLACEHOLDER.match(date_part):
                found.add("date")
            if any(part.upper() != "X" for part in rec_parts[2:4]):
                found.add("recording")
            extra = " ".join(rec_parts[5:])
            if real_dates(extra):
                found.add("date")
            if looks_identifying(extra):
                found.add("recording")
        else:
            if real_dates(recording):
                found.add("date")
            if not placeholder(recording) and looks_identifying(recording):
                found.add("recording")
    else:
        # Plain EDF: the patient field is free text, so anything but a placeholder counts.
        if not placeholder(patient):
            found.add("patient")
        if real_dates(recording):
            found.add("date")
        if LONG_NUMBER.search(recording) or NON_ASCII in recording:
            found.add("recording")
    if _valid_startdate(startdate) and not _STARTDATE_PLACEHOLDER.match(startdate):
        found.add("date")
    return tuple(name for name in ("patient", "recording", "date") if name in found)


def parse_header(path: Path) -> EdfHeader:
    size = path.stat().st_size
    with path.open("rb") as handle:
        fixed = handle.read(FIXED_HEADER_BYTES)
        if len(fixed) < FIXED_HEADER_BYTES:
            raise HeaderUnreadable("header.too_short")
        version = fixed[0:8]
        if version == b"\xffBIOSEMI":
            variant, bytes_per_sample = "BDF", 3
        elif version.decode("ascii", "replace").strip() == "0":
            variant, bytes_per_sample = "EDF", 2
        else:
            raise HeaderUnreadable("header.bad_version")
        issues: list[str] = []
        patient, ok_patient = _text(fixed[8:88])
        recording, ok_recording = _text(fixed[88:168])
        startdate, ok_date = _text(fixed[168:176])
        _starttime, ok_time = _text(fixed[176:184])
        header_bytes = _int(fixed[184:192])
        reserved, ok_reserved = _text(fixed[192:236])
        n_records = _int(fixed[236:244])
        record_duration = _fraction(fixed[244:252])
        n_signals = _int(fixed[252:256])
        if not all((ok_patient, ok_recording, ok_date, ok_time, ok_reserved)):
            issues.append("header.non_ascii")
        if n_signals is None or not 0 < n_signals <= MAX_SIGNALS:
            raise HeaderUnreadable("header.bad_signal_count")
        signal_block = handle.read(SIGNAL_HEADER_BYTES * n_signals)
    if len(signal_block) < SIGNAL_HEADER_BYTES * n_signals:
        raise HeaderUnreadable("header.too_short")

    plus = reserved[4:5] if reserved.startswith(("EDF+", "BDF+")) and reserved[4:5] in ("C", "D") else None

    offsets: dict[str, int] = {}
    position = 0
    for name, width in SIGNAL_FIELDS:
        offsets[name] = position
        position += width
    widths = dict(SIGNAL_FIELDS)

    def field(name: str, index: int) -> bytes:
        start = n_signals * offsets[name] + index * widths[name]
        return signal_block[start : start + widths[name]]

    signals: list[EdfSignal] = []
    for index in range(n_signals):
        label, ok_label = _text(field("label", index))
        unit, ok_unit = _text(field("unit", index))
        if not (ok_label and ok_unit):
            issues.append("header.non_ascii")
        pmin, pmax = _float(field("pmin", index)), _float(field("pmax", index))
        dmin, dmax, spr = _int(field("dmin", index)), _int(field("dmax", index)), _int(field("spr", index))
        signals.append(
            EdfSignal(
                label=label,
                unit=unit,
                physical_min=pmin,
                physical_max=pmax,
                digital_min=dmin,
                digital_max=dmax,
                samples_per_record=spr,
            )
        )
        if pmin is None or pmax is None or dmin is None or dmax is None or spr is None:
            issues.append("header.number_field")
            continue
        if dmin >= dmax:
            issues.append("header.digital_range")
        if pmin == pmax:
            issues.append("header.physical_range")
        if spr <= 0:
            issues.append("header.samples_per_record")

    if header_bytes != FIXED_HEADER_BYTES + SIGNAL_HEADER_BYTES * n_signals:
        issues.append("header.size_field")
    has_data_signals = any(s.label.strip().upper() not in ANNOTATION_LABELS for s in signals)
    # A duration of 0 is only allowed for annotation-only EDF+ files (EDF+ specification).
    if record_duration is None or record_duration < 0 or (record_duration == 0 and has_data_signals):
        issues.append("header.record_duration")
    samples = [s.samples_per_record for s in signals]
    if n_records is None or n_records < 0:
        issues.append("header.records_unknown")
    elif header_bytes is not None and all(n is not None for n in samples):
        record_bytes = sum(n for n in samples if n is not None) * bytes_per_sample
        expected = header_bytes + n_records * record_bytes
        if size < expected:
            issues.append("header.file_truncated")
        elif size > expected:
            issues.append("header.file_trailing_data")
    if not _valid_startdate(startdate):
        issues.append("header.startdate")

    return EdfHeader(
        variant=variant,
        plus=plus,
        n_records=n_records,
        record_duration=record_duration,
        header_bytes=header_bytes,
        signals=tuple(signals),
        issues=tuple(dict.fromkeys(issues)),
        identifying_fields=_identifying(patient, recording, startdate, plus),
    )


def to_recording(header: EdfHeader, *, recording_id: str, relative_path: str) -> Recording:
    """The data model view of the header (ARC-01). Rates are exact quotients of the ASCII fields."""
    duration = header.record_duration
    channels = []
    for signal in header.signals:
        kind = classify(signal.label)
        rate = None
        if duration and duration > 0 and signal.samples_per_record and signal.samples_per_record > 0:
            rate = float(Fraction(signal.samples_per_record) / duration)
        physical = None
        resolution = None
        if signal.physical_min is not None and signal.physical_max is not None:
            physical = (signal.physical_min, signal.physical_max)
            if (
                signal.digital_min is not None
                and signal.digital_max is not None
                and signal.digital_max > signal.digital_min
            ):
                resolution = (signal.physical_max - signal.physical_min) / (
                    signal.digital_max - signal.digital_min
                )
        channels.append(
            Channel(
                name=signal.label,
                type=kind,
                unit=signal.unit or None,
                recording_id=recording_id,
                sampling_rate_hz=rate,
                resolution=resolution,
                physical_range=physical,
            )
        )
    eeg_rates = sorted({ch.sampling_rate_hz for ch in channels if ch.type == "EEG" and ch.sampling_rate_hz})
    total = None
    if header.n_records is not None and header.n_records >= 0 and duration is not None and duration >= 0:
        total = float(header.n_records * duration)
    sources = {"channels": "header"}
    if eeg_rates:
        sources["sampling_rate_hz"] = "header"
    if total is not None:
        sources["duration_s"] = "header"
    return Recording(
        id=recording_id,
        format=header.variant,
        path=relative_path,
        sampling_rate_hz=eeg_rates[0] if eeg_rates else None,
        duration_s=total,
        streamable=True,
        discontinuous=header.plus == "D",
        metadata_sources=sources,
        channels=channels,
    )


class EdfAdapter:
    format: str = "EDF"
    extensions: tuple[str, ...] = (".edf",)
    variant: str = "EDF"

    def read(self, path: Path, *, recording_id: str, relative_path: str) -> Recording:
        return to_recording(parse_header(path), recording_id=recording_id, relative_path=relative_path)

    def inspect(self, path: Path) -> HeaderInspection:
        header = parse_header(path)
        issues = list(header.issues)
        if header.variant != self.variant:
            issues.append("header.variant_mismatch")  # e.g. a BDF header in a file named .edf
        issues.extend(self._cross_check(path))
        return HeaderInspection(
            issues=tuple(dict.fromkeys(issues)), identifying_fields=header.identifying_fields
        )

    def _cross_check(self, path: Path) -> tuple[str, ...]:
        return _edfio_issues(path)

    def read_check(self, path: Path) -> str | None:
        import mne  # heavy import, only when data is actually read

        return mne_read_check(mne.io.read_raw_edf, path)


class BdfAdapter(EdfAdapter):
    format: str = "BDF"
    extensions: tuple[str, ...] = (".bdf",)
    variant: str = "BDF"

    def _cross_check(self, path: Path) -> tuple[str, ...]:
        return ()  # edfio reads EDF only; the own parser is the BDF check (A-24)

    def read_check(self, path: Path) -> str | None:
        import mne

        return mne_read_check(mne.io.read_raw_bdf, path)


def _edfio_issues(path: Path) -> tuple[str, ...]:
    """M01 method: 'EDF-Kopfzeile mit edfio prüfen'. Only the outcome is kept, never the message."""
    import edfio

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            edfio.read_edf(path, lazy_load_data=True)
    except Exception:
        return ("header.edfio_rejected",)
    return ()
