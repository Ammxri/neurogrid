"""M02 Metadaten, M04 Kanalsatz und Montage, M05 Impedanz (PRD §12; A-03, A-04, A-18, A-46).

Values come from the merged metadata of each recording (neurogrid.toml > BIDS sidecars > header).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from neurogrid.checks.context import CheckContext, RecordingState
from neurogrid.io.channels import standard_name
from neurogrid.kernel.rules import (
    CheckSpec,
    Evaluation,
    Measurement,
    ParamSpec,
    ParamValue,
    at_most,
    is_true,
)
from neurogrid.metadata import CHANNEL_COLUMNS, REQUIRED_FIELDS

REQUIRED = "metadata.required_fields"
CONSISTENT = "metadata.consistent"
STANDARD_NAMES = "channels.standard_names"
POSITIONS = "channels.positions"
SAME_SET = "channels.same_set_per_task"
COUNT = "channels.count_consistent"
ONLY_1005 = "channels.only_1005"
IMPEDANCE_DOCUMENTED = "impedance.documented"
IMPEDANCE_MAX = "impedance.max"
BIDS_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def _counts_consistent(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
    value = measurement.value
    eeg = [
        value[key] for key in ("sidecar_eeg", "channels_tsv_eeg", "file_eeg") if value.get(key) is not None
    ]
    totals = [value[key] for key in ("channels_tsv_total", "file_total") if value.get(key) is not None]
    return Evaluation(passed=len(set(eeg)) <= 1 and len(set(totals)) <= 1)


def _complete(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
    value = measurement.value
    return Evaluation(passed=value["documented"] == value["eeg_channels"])


SPECS = (
    CheckSpec(id=REQUIRED, evaluate=is_true),
    CheckSpec(id=CONSISTENT, evaluate=is_true),
    CheckSpec(id=STANDARD_NAMES, evaluate=is_true),
    CheckSpec(id=POSITIONS, evaluate=_complete),
    CheckSpec(id=SAME_SET, evaluate=is_true),
    CheckSpec(id=COUNT, evaluate=_counts_consistent),
    CheckSpec(id=ONLY_1005, evaluate=is_true),
    CheckSpec(id=IMPEDANCE_DOCUMENTED, evaluate=_complete),
    CheckSpec(id=IMPEDANCE_MAX, evaluate=at_most("max_kohm"), params={"max_kohm": ParamSpec("number", 5)}),
)


def _annotations_only(rec: RecordingState, check_id: str) -> Measurement:
    return _base(rec, check_id, state="not_applicable", reason="recording.annotations_only")


def _base(rec: RecordingState, check_id: str, **kwargs: Any) -> Measurement:
    return Measurement(
        check_id=check_id, object=rec.object_id, file=rec.file, identity=rec.identity, **kwargs
    )


def measure_required(ctx: CheckContext) -> list[Measurement]:
    """M02-01: one measurement per recording and required field (subkey = field, A-03)."""
    out: list[Measurement] = []
    for rec in ctx.recordings:
        if rec.annotations_only:
            out.append(_annotations_only(rec, REQUIRED))
            continue
        meta = rec.metadata
        for name in REQUIRED_FIELDS:
            documented = meta.fields.get(name)
            out.append(
                _base(
                    rec,
                    REQUIRED,
                    subkey=name,
                    value=documented is not None,
                    details={"source": documented.source} if documented else {},
                )
            )
        for column in CHANNEL_COLUMNS:
            source = meta.channel_columns.get(column)
            out.append(
                _base(
                    rec,
                    REQUIRED,
                    subkey=f"channels.{column}",
                    value=source is not None,
                    details={"source": source} if source else {},
                )
            )
    return out


def _alnum(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", text).lower()


def measure_consistent(ctx: CheckContext) -> list[Measurement]:
    """M02-02 (A-46, A-77): TaskName matches the task label; BIDSVersion format; Name not empty or n/a."""
    out: list[Measurement] = []
    for rec in ctx.recordings:
        if rec.annotations_only:
            out.append(_annotations_only(rec, CONSISTENT))
            continue
        task_name = rec.metadata.sidecar.get("TaskName")
        label = rec.metadata.entities.get("task")
        if not isinstance(task_name, str) or label is None:
            out.append(
                _base(
                    rec, CONSISTENT, subkey="TaskName", state="not_applicable", reason="metadata.no_task_name"
                )
            )
            continue
        out.append(
            _base(rec, CONSISTENT, subkey="TaskName", value=_alnum(task_name) == _alnum(str(label.value)))
        )
    if not ctx.scan.is_bids:
        for subkey in ("BIDSVersion", "Name"):
            out.append(
                Measurement(
                    check_id=CONSISTENT,
                    object="dataset",
                    subkey=subkey,
                    state="not_applicable",
                    reason="metadata.not_bids",
                )
            )
        return out
    description = ctx.scan.description
    out.append(
        Measurement(
            check_id=CONSISTENT,
            object="dataset",
            subkey="BIDSVersion",
            value=bool(BIDS_VERSION.match(description.get("BIDSVersion", ""))),
        )
    )
    out.append(
        Measurement(
            check_id=CONSISTENT,
            object="dataset",
            subkey="Name",
            value=description.get("Name", "").strip().lower() not in ("", "n/a"),
        )
    )
    return out


def _eeg_channels(rec: RecordingState) -> list[tuple[str, object]]:
    if rec.recording is None:
        return []
    return [(ch.name, ch) for ch in rec.recording.channels if ch.type == "EEG"]


def _unreadable(rec: RecordingState, check_id: str) -> Measurement:
    return _base(rec, check_id, state="not_checkable", reason="header.unreadable")


def measure_standard_names(ctx: CheckContext) -> list[Measurement]:
    """M04-01: every EEG channel has a 10-20/10-10/10-05 name or a mapping in neurogrid.toml."""
    channel_map = ctx.config.metadata.channel_map
    out: list[Measurement] = []
    for rec in ctx.recordings:
        if rec.annotations_only:
            out.append(_annotations_only(rec, STANDARD_NAMES))
            continue
        if rec.recording is None:
            out.append(_unreadable(rec, STANDARD_NAMES))
            continue
        for name, _channel in _eeg_channels(rec):
            known = standard_name(name, channel_map)
            out.append(_base(rec, STANDARD_NAMES, subkey=name, channel=name, value=known is not None))
    return out


def measure_only_1005(ctx: CheckContext) -> list[Measurement]:
    """M04-05 (A-18): note for names that exist only in the 10-05 system."""
    channel_map = ctx.config.metadata.channel_map
    out: list[Measurement] = []
    for rec in ctx.recordings:
        if rec.annotations_only:
            out.append(_annotations_only(rec, ONLY_1005))
            continue
        if rec.recording is None:
            out.append(_unreadable(rec, ONLY_1005))
            continue
        for name, _channel in _eeg_channels(rec):
            known = standard_name(name, channel_map)
            if known is not None:
                out.append(_base(rec, ONLY_1005, subkey=name, channel=name, value=known[1] != "1005"))
    return out


def measure_positions(ctx: CheckContext) -> list[Measurement]:
    """M04-02 (A-18): positions of the EEG channels documented (electrodes.tsv or the file)."""
    out: list[Measurement] = []
    for rec in ctx.recordings:
        if rec.annotations_only:
            out.append(_annotations_only(rec, POSITIONS))
            continue
        eeg = [ch for _name, ch in _eeg_channels(rec)]
        if rec.recording is None:
            out.append(_unreadable(rec, POSITIONS))
        elif not eeg:
            out.append(_base(rec, POSITIONS, state="not_checkable", reason="signal.no_eeg_channels"))
        else:
            documented = sum(1 for ch in eeg if getattr(ch, "position", None))
            out.append(_base(rec, POSITIONS, value={"documented": documented, "eeg_channels": len(eeg)}))
    return out


def measure_same_set(ctx: CheckContext) -> list[Measurement]:
    """M04-03 (A-18): all recordings of one task have the same EEG channel set (subkey = task)."""
    groups: dict[str, set[frozenset[str]]] = defaultdict(set)
    for rec in ctx.recordings:
        if rec.recording is None or rec.annotations_only:
            continue
        task = rec.metadata.entities.get("task")
        names = frozenset(name.strip().upper() for name, _ch in _eeg_channels(rec))
        groups[str(task.value) if task else "-"].add(names)
    return [
        Measurement(
            check_id=SAME_SET,
            object="dataset",
            subkey=task,
            value=len(sets) <= 1,
            details={"channel_sets": len(sets)},
        )
        for task, sets in sorted(groups.items())
    ]


def measure_count(ctx: CheckContext) -> list[Measurement]:
    """M04-04 (A-46, A-77): EEG channel count in the sidecar, channels.tsv and the file agree.

    A channels.tsv without rows is no source (A-77); it neither counts 0 channels nor makes the check
    applicable.
    """
    out: list[Measurement] = []
    for rec in ctx.recordings:
        if rec.annotations_only:
            out.append(_annotations_only(rec, COUNT))
            continue
        if rec.recording is None:
            out.append(_unreadable(rec, COUNT))
            continue
        meta = rec.metadata
        rows = meta.channels_tsv
        value = {
            "sidecar_eeg": meta.sidecar_eeg_count,
            "channels_tsv_eeg": sum(1 for row in rows if row.get("type", "").strip().upper() == "EEG")
            if rows
            else None,
            "file_eeg": len(_eeg_channels(rec)),
            "channels_tsv_total": len(rows) if rows else None,
            "file_total": len([ch for ch in rec.recording.channels if ch.type != "ANNOT"]),
        }
        sources = sum(1 for key in ("sidecar_eeg", "channels_tsv_eeg") if value[key] is not None)
        if sources == 0:
            out.append(_base(rec, COUNT, state="not_applicable", reason="metadata.no_sidecar"))
            continue
        out.append(_base(rec, COUNT, value=value))
    return out


def measure_impedance_documented(ctx: CheckContext) -> list[Measurement]:
    """M05-01: impedances of the EEG channels documented (electrodes.tsv or the file)."""
    out: list[Measurement] = []
    for rec in ctx.recordings:
        if rec.annotations_only:
            out.append(_annotations_only(rec, IMPEDANCE_DOCUMENTED))
            continue
        eeg = [ch for _name, ch in _eeg_channels(rec)]
        if rec.recording is None:
            out.append(_unreadable(rec, IMPEDANCE_DOCUMENTED))
        elif not eeg:
            out.append(
                _base(rec, IMPEDANCE_DOCUMENTED, state="not_checkable", reason="signal.no_eeg_channels")
            )
        else:
            documented = sum(1 for ch in eeg if getattr(ch, "impedance_kohm", None) is not None)
            out.append(
                _base(rec, IMPEDANCE_DOCUMENTED, value={"documented": documented, "eeg_channels": len(eeg)})
            )
    return out


def measure_impedance_max(ctx: CheckContext) -> list[Measurement]:
    """M05-02 and GX-01: each documented impedance below the limit, for wet electrodes only (PRD: 5 kOhm
    nass).

    A recording without any documented impedance is not_checkable (impedance.not_documented, Q16/A-83), so
    that a rule on this check is never silent, e.g. gxdsl008 loaded without core (M05-01 is in core).
    """
    out: list[Measurement] = []
    for rec in ctx.recordings:
        if rec.annotations_only:
            out.append(_annotations_only(rec, IMPEDANCE_MAX))
            continue
        if rec.recording is None:
            out.append(_unreadable(rec, IMPEDANCE_MAX))
            continue
        eeg = _eeg_channels(rec)
        values = [(name, getattr(ch, "impedance_kohm", None)) for name, ch in eeg]
        values = [(name, value) for name, value in values if value is not None]
        electrode = rec.recording.electrode_type
        if electrode == "dry":
            out.append(_base(rec, IMPEDANCE_MAX, state="not_applicable", reason="impedance.dry_electrodes"))
        elif not eeg:
            out.append(_base(rec, IMPEDANCE_MAX, state="not_checkable", reason="signal.no_eeg_channels"))
        elif not values:
            out.append(_base(rec, IMPEDANCE_MAX, state="not_checkable", reason="impedance.not_documented"))
        elif electrode is None:
            out.append(
                _base(rec, IMPEDANCE_MAX, state="not_checkable", reason="metadata.electrode_type_unknown")
            )
        else:
            out.extend(
                _base(rec, IMPEDANCE_MAX, subkey=name, channel=name, value=value) for name, value in values
            )
    return out


MEASURERS = {
    REQUIRED: measure_required,
    CONSISTENT: measure_consistent,
    STANDARD_NAMES: measure_standard_names,
    POSITIONS: measure_positions,
    SAME_SET: measure_same_set,
    COUNT: measure_count,
    ONLY_1005: measure_only_1005,
    IMPEDANCE_DOCUMENTED: measure_impedance_documented,
    IMPEDANCE_MAX: measure_impedance_max,
}
