"""Metadata of one recording from all sources (NG-F06, A-03, A-04, A-05).

Precedence: neurogrid.toml > BIDS sidecars > format header > undocumented. Every documented value keeps its
source, so that reports can say where a value came from. Raw folders get subject/session/task/run from the
mapping in neurogrid.toml (a regular expression with named groups or a table, A-05); BIDS datasets from the
file names.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from neurogrid.config import Config
from neurogrid.io import bids
from neurogrid.io.discover import FoundFile
from neurogrid.model.dataset import Channel, Recording

REQUIRED_FIELDS = ("EEGReference", "SamplingFrequency", "PowerLineFrequency", "SoftwareFilters", "TaskName")
CHANNEL_COLUMNS = ("name", "type", "units")
NA_IS_MISSING = frozenset(
    {"EEGReference", "PowerLineFrequency"}
)  # A-03: n/a is valid only for SoftwareFilters
ENTITY_FIELDS = (("subject", "sub"), ("session", "ses"), ("task", "task"), ("run", "run"))
# channels.tsv types with a NeuroGrid type of their own; every other declared type is no EEG (see
# declared_type). EKG and STIM are no BIDS types but common spellings.
BIDS_TYPES = {
    "EEG": "EEG",
    "EOG": "EOG",
    "HEOG": "EOG",
    "VEOG": "EOG",
    "ECG": "ECG",
    "EKG": "ECG",
    "EMG": "EMG",
    "TRIG": "TRIG",
    "STIM": "TRIG",
    "MISC": "MISC",
    "RESP": "RESP",
    "REF": "MISC",
}
_LABEL = re.compile(r"[A-Za-z0-9]+")  # BIDS labels are alphanumeric (A-05)


@dataclass(frozen=True)
class Documented:
    value: Any
    source: str  # config | sidecar | header | bids_filename | mapping


@dataclass
class RecordingMetadata:
    fields: dict[str, Documented] = field(default_factory=dict)
    # column -> source: sidecar, header, or sidecar+header when channels.tsv documents the column for some
    # channels and the header for the others (A-77)
    channel_columns: dict[str, str] = field(default_factory=dict)
    sidecar: dict[str, Any] = field(default_factory=dict)
    has_sidecar: bool = False
    channels_tsv: list[dict[str, str]] | None = None
    entities: dict[str, Documented] = field(default_factory=dict)

    @property
    def sidecar_rate(self) -> float | None:
        return _number(self.sidecar.get("SamplingFrequency"))

    @property
    def sidecar_eeg_count(self) -> int | None:
        value = _number(self.sidecar.get("EEGChannelCount"))
        return int(value) if value is not None and value.is_integer() else None


def _number(value: Any) -> float | None:
    """A finite JSON number of a sidecar, else None (A-12, A-75): an integer too large for a float is no
    number NeuroGrid can use, never a crash."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def declared_type(value: str) -> str | None:
    """The channel type a channels.tsv type declares; None for an empty cell or n/a (A-04: the sidecar wins
    over the type from the header label).

    Types without a NeuroGrid type of their own (e.g. GSR, PPG, TEMP, AUDIO, EYEGAZE, PUPIL, SYSCLOCK, SEEG,
    ECOG, DBS) are MISC, MEG types (MEGMAG, MEGGRADPLANAR, ...) are MEG, so that no declared non-EEG channel
    is counted as EEG.
    """
    declared = value.strip().upper()
    if not declared or declared == "N/A":
        return None
    if declared in BIDS_TYPES:
        return BIDS_TYPES[declared]
    if declared.startswith("MEG"):
        return "MEG"
    return "MISC"


def _documented(value: Any, name: str) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        if text.lower() == "n/a":
            return name not in NA_IS_MISSING
    return True


def mapped_entities(found: FoundFile, cfg: Config) -> dict[str, str]:
    """subject/session/task/run of a raw file from the mapping table or the expression (A-05).

    With the expression, a group value that is no alphanumeric label, or a run that is no number, leaves
    the file unmapped (empty result) instead of dropping that entity (A-77).
    """
    relative = found.relative.as_posix()
    for row in cfg.convert.files:
        if PurePosixPath(row.path.replace("\\", "/")).as_posix() == relative:
            values = {"subject": row.subject, "session": row.session, "task": row.task, "run": row.run}
            return {key: value for key, value in values.items() if value}
    if cfg.convert.pattern:
        pattern = re.compile(cfg.convert.pattern)
        match = pattern.fullmatch(relative) or pattern.fullmatch(found.relative.name)
        if match:
            labels: dict[str, str] = {}
            for key, value in match.groupdict().items():
                if not value:
                    continue  # an optional group that did not take part, or matched nothing
                if not _LABEL.fullmatch(value):
                    # a value that is no BIDS label is never dropped silently: the recording would land at
                    # another target; the file counts as not mapped (A-05, A-77)
                    return {}
                labels[key] = value
            if not labels.get("run", "0").isdigit():
                return {}  # a run label is an index; with another run the file counts as not mapped (A-77)
            return labels
    return {}


def entities_for(found: FoundFile, cfg: Config, is_bids: bool) -> dict[str, Documented]:
    if is_bids:
        names = dict(found.entities)
        return {
            name: Documented(names[key], "bids_filename") for name, key in ENTITY_FIELDS if names.get(key)
        }
    return {name: Documented(value, "mapping") for name, value in mapped_entities(found, cfg).items()}


def _with_channel_sidecars(
    root: Path, found: FoundFile, recording: Recording
) -> tuple[Recording, list[dict[str, str]] | None, list[str]]:
    """Types, units and status from channels.tsv; positions and impedances from electrodes.tsv."""
    channels_table = bids.nearest_tsv(root, found.relative, "channels")
    electrodes_table = bids.nearest_tsv(root, found.relative, "electrodes", ignore=("space",))
    header_cols: list[str] = []
    rows: list[dict[str, str]] | None = None
    by_name: dict[str, dict[str, str]] = {}
    if channels_table is not None:
        header_cols, rows = channels_table
        by_name = {row.get("name", ""): row for row in rows}
    positions: dict[str, tuple[str, float | None]] = {}
    if electrodes_table is not None:
        _cols, electrode_rows = electrodes_table
        for row in electrode_rows:
            coords = [_float(row.get(axis)) for axis in ("x", "y", "z")]
            position = ",".join(f"{c:.6g}" for c in coords) if all(c is not None for c in coords) else ""
            positions[row.get("name", "")] = (position, _float(row.get("impedance")))
    sources = dict(recording.metadata_sources)
    channels = []
    for channel in recording.channels:
        update: dict[str, Any] = {}
        channel_row = by_name.get(channel.name)
        if channel_row is not None:
            declared = declared_type(channel_row.get("type", ""))
            # an EDF+/BDF+ annotation channel carries no signal and is no BIDS channel (A-77); a row for it
            # does not turn it into one
            if declared is not None and channel.type != "ANNOT":
                update["type"] = declared
            units = channel_row.get("units", "").strip()
            if units and units.lower() != "n/a":
                update["unit"] = units
            status = channel_row.get("status", "").strip().lower()
            if status in ("good", "bad"):
                update["status"] = status
        if channel.name in positions:
            position, impedance = positions[channel.name]
            if position:
                update["position"] = position
            if impedance is not None:
                update["impedance_kohm"] = impedance
        channels.append(channel.model_copy(update=update) if update else channel)
    if rows:  # a channels.tsv without rows changes no channel
        sources["channels"] = "sidecar"
    if any(position for position, _imp in positions.values()):
        sources["position"] = "sidecar"
    if any(imp is not None for _pos, imp in positions.values()):
        sources["impedance_kohm"] = "sidecar"
    eeg_rates = sorted({ch.sampling_rate_hz for ch in channels if ch.type == "EEG" and ch.sampling_rate_hz})
    updated = recording.model_copy(
        update={
            "channels": channels,
            "metadata_sources": sources,
            "sampling_rate_hz": eeg_rates[0] if eeg_rates else recording.sampling_rate_hz,
        }
    )
    return updated, rows, header_cols


def _float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def collect(
    root: Path, found: FoundFile, recording: Recording | None, cfg: Config, is_bids: bool
) -> tuple[Recording | None, RecordingMetadata]:
    """Merge all sources for one recording. ``recording`` is None if the header could not be read."""
    meta = RecordingMetadata(entities=entities_for(found, cfg, is_bids))
    defaults = cfg.metadata.defaults
    header = recording  # the recording as the format header describes it, before channels.tsv
    channel_rows: list[dict[str, str]] | None = None
    columns: list[str] = []
    if is_bids:
        name = bids.parse_name(found.relative.name)
        suffix = name.suffix if name is not None else "eeg"  # eeg, meg, ieeg: the sidecar has the same suffix
        meta.sidecar, meta.has_sidecar = bids.merged_json(root, found.relative, suffix)
        if recording is not None:
            recording, channel_rows, columns = _with_channel_sidecars(root, found, recording)
        else:
            table = bids.nearest_tsv(root, found.relative, "channels")
            if table is not None:
                columns, channel_rows = table
    meta.channels_tsv = channel_rows

    def pick(name: str, *candidates: tuple[Any, str]) -> None:
        for value, source in candidates:
            if _documented(value, name):
                meta.fields[name] = Documented(value, source)
                return

    side = meta.sidecar
    header_rate = recording.sampling_rate_hz if recording is not None else None
    header_line = recording.line_frequency_hz if recording is not None else None
    task_entity = meta.entities.get("task")
    pick("EEGReference", (defaults.reference, "config"), (side.get("EEGReference"), "sidecar"))
    pick("SamplingFrequency", (side.get("SamplingFrequency"), "sidecar"), (header_rate, "header"))
    pick(
        "PowerLineFrequency",
        (defaults.line_frequency_hz, "config"),
        (side.get("PowerLineFrequency"), "sidecar"),
        (header_line, "header"),
    )
    pick("SoftwareFilters", (defaults.software_filters, "config"), (side.get("SoftwareFilters"), "sidecar"))
    pick(
        "TaskName",
        (side.get("TaskName"), "sidecar"),
        (task_entity.value if task_entity else None, task_entity.source if task_entity else ""),
    )

    meta.channel_columns = _channel_columns(header, channel_rows or [], columns)

    if recording is not None:
        recording = _apply_defaults(recording, meta, defaults)
    return recording, meta


def _channel_columns(
    header: Recording | None, rows: list[dict[str, str]], columns: list[str]
) -> dict[str, str]:
    """Sources of the channels.tsv columns name/type/units (A-77, M02-01).

    channels.tsv documents a column only if every channel of the recording (without annotation channels,
    which carry no signal, type or unit and are no BIDS channels) has a row with a value in it. Otherwise
    each channel needs the value in its row or in the header. A channels.tsv without rows is no source.
    Without a readable header only the table can document a column, if every row has the value.
    """
    out: dict[str, str] = {}
    signals = [ch for ch in header.channels if ch.type != "ANNOT"] if header is not None else []
    if not signals:
        for column in CHANNEL_COLUMNS:
            if rows and column in columns and all(row.get(column, "").strip() for row in rows):
                out[column] = "sidecar"
        return out
    by_name = {row.get("name", ""): row for row in rows}
    for column in CHANNEL_COLUMNS:
        in_table = [
            column in columns and bool(by_name.get(ch.name, {}).get(column, "").strip()) for ch in signals
        ]
        in_header = [_header_column(ch, column) for ch in signals]
        if all(in_table):
            out[column] = "sidecar"
        elif all(in_header):
            out[column] = "header"
        elif all(table or head for table, head in zip(in_table, in_header, strict=True)):
            out[column] = "sidecar+header"
    return out


def _header_column(channel: Channel, column: str) -> bool:
    if column == "name":
        return bool(channel.name.strip())
    if column == "type":
        return bool(channel.type)
    return bool(channel.unit and channel.unit.strip())


def _apply_defaults(recording: Recording, meta: RecordingMetadata, defaults: Any) -> Recording:
    """PRD fields of the recording (DM-03) with their sources; entities from file names or the mapping."""
    update: dict[str, Any] = {}
    sources = dict(recording.metadata_sources)
    for name, documented in meta.entities.items():
        update[name] = documented.value
        sources[name] = documented.source
    reference = meta.fields.get("EEGReference")
    if reference is not None:
        update["reference"] = str(reference.value)
        sources["reference"] = reference.source
    line = meta.fields.get("PowerLineFrequency")
    line_hz = _number(line.value) if line is not None else None
    if line is not None and line_hz is not None:
        update["line_frequency_hz"] = line_hz
        sources["line_frequency_hz"] = line.source
    if defaults.device:
        update["device"] = defaults.device
        sources["device"] = "config"
    elif isinstance(meta.sidecar.get("ManufacturersModelName"), str) and meta.sidecar[
        "ManufacturersModelName"
    ].strip().lower() not in ("", "n/a"):
        update["device"] = meta.sidecar["ManufacturersModelName"].strip()[:120]
        sources["device"] = "sidecar"
    if defaults.electrode_type:
        update["electrode_type"] = defaults.electrode_type
        sources["electrode_type"] = "config"
    update["metadata_sources"] = sources
    return recording.model_copy(update=update)
