"""Checks of the rule pack ``gbt47127``: the GB/T 47127—2026 multi-modal data format (NG-F03, RP-11; P7).

The data set folder is read once per run through :mod:`neurogrid.io.gbt47127`. Every measurement concerns one
object (``dataset`` or the relative path of a file or folder, shown as written: GB/T names are structured
names like BIDS names) and one element (``subkey``: a field, a column, a label). ``value`` is True when the
element is as the format requires; otherwise ``reason`` names the problem (``gbt47127.*``).

The field tables below give, per metadata file and modality, the identifiers and data types of the format
(tables 1 to 19), as identifiers only, without norm text (A-55). Fields that are not listed may be present
(the format lists fields with "etc."). Kinds: ``s`` string, ``n`` number, ``b`` boolean, ``S`` list of
strings, ``N`` list of numbers. A required field that is missing or empty fails; an optional field fails only
when present with the wrong type. In tables an empty cell or ``n/a`` counts as missing."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from neurogrid.checks.context import CheckContext
from neurogrid.io import gbt47127 as gbt
from neurogrid.io.discover import pseudonym, shown_extension
from neurogrid.kernel.rules import CheckSpec, Measurement, is_true

PREFIX = "gbt47127"
DESCRIPTION = f"{PREFIX}.description"
DESCRIPTION_NAME = f"{PREFIX}.description_name"
PARTICIPANTS = f"{PREFIX}.participants"
SUBJECT_FOLDERS = f"{PREFIX}.subject_folders"
SESSIONS = f"{PREFIX}.sessions"
ZERO_PADDING = f"{PREFIX}.zero_padding"
MODALITY_FOLDERS = f"{PREFIX}.modality_folders"
FILE_NAMES = f"{PREFIX}.file_names"
METADATA_FORMATS = f"{PREFIX}.metadata_formats"
SIDECAR = f"{PREFIX}.sidecar"
SIDECAR_FIELDS = f"{PREFIX}.sidecar_fields"
CHANNELS = f"{PREFIX}.channels"
POSITIONS = f"{PREFIX}.positions"
EVENTS = f"{PREFIX}.events"
EVENTS_NAME = f"{PREFIX}.events_name"
TIMESTAMP = f"{PREFIX}.timestamp"
IDENTIFYING_IDS = f"{PREFIX}.identifying_ids"
SIGNAL_CONSISTENCY = f"{PREFIX}.signal_consistency"

DATASET = "dataset"
MISSING_TEXT = frozenset({"", "n/a"})
_DIGIT_RUN = re.compile(r"\d{6,}")  # an ID number written as a label (A-51 hint)
_NAME_CHARACTERS = re.compile(r"^[A-Za-z0-9._-]+$")  # AF-2: letters, digits, '.', '_', '-'
# AF-10, IQ-005: the optode types source and detector, in Chinese and in English
OPTODE_TYPES = frozenset({"\u5149\u6e90", "\u5149\u63a2\u6d4b\u5668", "source", "detector"})


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str  # s, n, b, S, N
    required: bool


def _fields(required: str, optional: str = "") -> tuple[FieldSpec, ...]:
    out = []
    for text, flag in ((required, True), (optional, False)):
        for item in text.split():
            name, kind = item.split(":")
            out.append(FieldSpec(name, kind, flag))
    return tuple(out)


DESCRIPTION_FIELDS = _fields("Name:s Version:s", "Author:S")  # table 1
PARTICIPANT_FIELDS = _fields("ParticipantId:s", "Species:s Age:n Sex:s Handedness:s")  # table 2
SESSION_FIELDS = _fields("SessionId:s", "AcquisitionTime:s")  # table 3
EVENT_FIELDS = _fields("Onset:n Duration:n Value:s", "Description:s")  # table 19
SIDECAR_FIELDS_BY_MODALITY: dict[str, tuple[FieldSpec, ...]] = {
    "EEG": _fields(  # table 4
        "TaskName:s EEGReference:s SamplingFrequency:n PowerlineFrequency:n ChannelCount:n",
        "HardwareInfo:s CapInfo:s InstituteName:s PlacementScheme:s SoftwareFilters:s HardwareFilters:s",
    ),
    "fNIRS": _fields(  # table 7
        "TaskName:s SamplingFrequency:n ChannelCount:n SourceOptodeCount:n DetectorOptodeCount:n",
        "HardwareInfo:s CapInfo:s InstituteName:s PlacementScheme:s SourceType:s DetectorType:s",
    ),
    "MEG": _fields(  # table 10
        "TaskName:s SamplingFrequency:n PowerlineFrequency:n DewarPosition:s ChannelCount:n "
        "DigitizedLandmarks:b DigitizedHeadPoints:b",
        "HardwareInfo:s InstituteName:s SoftwareFilters:s HardwareFilters:s",
    ),
    "fMRI": _fields(  # table 12
        "TaskName:s RepetitionTime:n",
        "EchoTime:n FlipAngle:n SliceTiming:N MagneticFieldStrength:n Manufacturer:s ManufacturerModelName:s "
        "InstitutionName:s",
    ),
    "iEEG": _fields(  # table 13
        "TaskName:s iEEGReference:s SamplingFrequency:n PowerlineFrequency:n ChannelCount:n",
        "HardwareInfo:s ElectrodeInfo:s InstitutionName:s PlacementScheme:s SoftwareFilters:s "
        "HardwareFilters:s",
    ),
    "uEphys": _fields(
        "TaskName:s PowerlineFrequency:n ChannelCount:n", "HardwareInfo:s InstitutionName:s"
    ),  # 16
}
_ELECTRICAL_CHANNELS = _fields("Name:s Type:s Unit:s", "Description:s LowCutoff:n HighCutoff:n Notch:n")
CHANNEL_FIELDS_BY_MODALITY: dict[str, tuple[FieldSpec, ...]] = {  # no channel table for fMRI (7.5.4)
    "EEG": _ELECTRICAL_CHANNELS,  # table 6
    "fNIRS": _fields("Name:s Type:s Source:s Detector:s Wavelength:n Unit:s", "Description:s"),  # table 9
    "MEG": _ELECTRICAL_CHANNELS,  # table 11
    "iEEG": _ELECTRICAL_CHANNELS,  # table 15
    "uEphys": _fields(  # table 18
        "Name:s Reference:s Type:s SamplingFrequency:n Unit:s",
        "Description:s SoftwareFilters:s HardwareFilters:s",
    ),
}
# modality -> (table kind, fields, the column whose values must be unique); none for MEG and fMRI
POSITION_TABLES: dict[str, tuple[str, tuple[FieldSpec, ...], str]] = {
    "EEG": ("electrodes", _fields("Name:s X:n Y:n Z:n", "Type:s Material:s"), "Name"),  # table 5
    "fNIRS": ("optodes", _fields("Optode:s X:n Y:n Z:n Type:s", "Description:s"), "Optode"),  # table 8
    "iEEG": (
        "electrodes",
        _fields("Name:s X:n Y:n Z:n Size:n", "Hemisphere:s Material:s"),
        "Name",
    ),  # table 14
    "uEphys": (  # table 17
        "electrodes",
        _fields("ElectrodeID:s", "DeviceInfo:s Hemisphere:s X:n Y:n Z:n Location:s ElectrodeGroup:s"),
        "ElectrodeID",
    ),
}
# subkeys that are identifiers of the format or of this module, never a label taken from the data (A-51)
_SAFE_SUBKEYS = frozenset(
    {
        spec.name
        for group in (
            DESCRIPTION_FIELDS,
            PARTICIPANT_FIELDS,
            SESSION_FIELDS,
            EVENT_FIELDS,
            *SIDECAR_FIELDS_BY_MODALITY.values(),
            *CHANNEL_FIELDS_BY_MODALITY.values(),
            *(fields for _, fields, _ in POSITION_TABLES.values()),
        )
        for spec in group
    }
    | {"name", "data", "levels", "sessions", "label", "spelling", "modality", "labels", "format", "sidecar"}
    | {"channels", "electrodes", "optodes", "events", "matches", "timestamp", "signal", "sub-*"}
    | {gbt.DESCRIPTION_STEM, gbt.PARTICIPANTS_STEM}
)


def _safe_subkey(subkey: str | None) -> bool:
    return subkey is None or subkey.split(":")[0] in _SAFE_SUBKEYS


# modalities whose signal files NeuroGrid can read, for the comparison with the signal (A-113)
READABLE_MODALITIES = frozenset({"EEG", "iEEG"})


# --- values ---------------------------------------------------------------------------------------


def _number(value: Any, from_text: bool) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)) and not from_text:
        return math.isfinite(value)
    if isinstance(value, str) and from_text:
        try:
            return math.isfinite(float(value.strip()))
        except ValueError:
            return False
    return False


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() not in MISSING_TEXT
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def value_ok(value: Any, kind: str, *, from_text: bool) -> bool:
    """Whether a present value has the field's type. ``from_text``: XML or a table cell, where every value is
    text (numbers and booleans are parsed, a single element counts as a list of one)."""
    if kind == "s":
        return isinstance(value, str) and value.strip() != ""
    if kind == "n":
        return _number(value, from_text)
    if kind == "b":
        if from_text:
            return isinstance(value, str) and value.strip().lower() in {"true", "false"}
        return isinstance(value, bool)
    items = value if isinstance(value, list) else ([value] if from_text else None)
    if not items:
        return False
    if kind == "S":
        return all(isinstance(item, str) and item.strip() != "" for item in items)
    return all(_number(item, from_text) for item in items)


# --- measurements ---------------------------------------------------------------------------------


def _measure(
    check_id: str,
    obj: PurePosixPath | str,
    subkey: str | None,
    ok: bool,
    reason: str | None = None,
    **details: Any,
) -> Measurement:
    name = obj.as_posix() if isinstance(obj, PurePosixPath) else obj
    return Measurement(
        check_id=check_id,
        object=name,
        subkey=subkey,
        file=None if name == DATASET else name,
        value=ok,
        reason=None if ok else f"{PREFIX}.{reason}",
        details=details,
        identity=(name,),
    )


def _single(ctx: CheckContext, check_id: str) -> list[Measurement] | None:
    """A single file as target is no data set folder: every check is not applicable."""
    if ctx.scan.single_file:
        return [
            Measurement(
                check_id=check_id, object=DATASET, state="not_applicable", reason=f"{PREFIX}.single_file"
            )
        ]
    return None


def dataset(ctx: CheckContext) -> gbt.GbtDataset:
    if not isinstance(ctx.gbt47127, gbt.GbtDataset):
        ctx.gbt47127 = gbt.read_dataset(ctx.root)
    return ctx.gbt47127


def _fields_of_mapping(
    check_id: str, obj: PurePosixPath, data: Mapping[str, Any], specs: Iterable[FieldSpec], *, from_text: bool
) -> list[Measurement]:
    out = []
    for spec in specs:
        value = data.get(spec.name)
        if not _present(value):
            if spec.required:
                out.append(_measure(check_id, obj, spec.name, False, "field_missing", field=spec.name))
            continue
        ok = value_ok(value, spec.kind, from_text=from_text)
        out.append(_measure(check_id, obj, spec.name, ok, "field_type", field=spec.name, kind=spec.kind))
    return out


def _table_columns(
    check_id: str, table: gbt.TableFile, specs: Iterable[FieldSpec], unique: str | None = None
) -> list[Measurement]:
    """Required columns present and filled in every row, optional columns typed where filled, the unique
    column without repeated values."""
    out = []
    for spec in specs:
        if spec.name not in table.columns:
            if spec.required:
                out.append(
                    _measure(check_id, table.relative, spec.name, False, "column_missing", column=spec.name)
                )
            continue
        cells = [row[spec.name] for row in table.rows]
        empty = sum(1 for cell in cells if cell.strip() in MISSING_TEXT)
        wrong = sum(
            1
            for cell in cells
            if cell.strip() not in MISSING_TEXT and not value_ok(cell, spec.kind, from_text=True)
        )
        if spec.required and empty:
            out.append(
                _measure(
                    check_id, table.relative, spec.name, False, "cells_empty", column=spec.name, rows=empty
                )
            )
        elif wrong:
            out.append(
                _measure(
                    check_id,
                    table.relative,
                    spec.name,
                    False,
                    "cells_type",
                    column=spec.name,
                    rows=wrong,
                    kind=spec.kind,
                )
            )
        else:
            out.append(_measure(check_id, table.relative, spec.name, True))
    if unique and unique in table.columns:
        counts = Counter(row[unique] for row in table.rows if row[unique].strip() not in MISSING_TEXT)
        repeated = sorted(value for value, n in counts.items() if n > 1)
        out.append(
            _measure(
                check_id,
                table.relative,
                f"{unique}:unique",
                not repeated,
                "values_repeated",
                values=repeated[:20],
            )
        )
    return out


def _file_problem(check_id: str, item: gbt.KeyValueFile | gbt.TableFile, subkey: str) -> Measurement | None:
    if item.problem is None:
        return None
    return _measure(check_id, item.relative, subkey, False, "unreadable", problem=item.problem)


def _one(
    check_id: str, found: tuple[Any, ...], where: PurePosixPath | str, subkey: str
) -> tuple[Any | None, list[Measurement]]:
    """The single file of a kind: missing and duplicates are findings."""
    if not found:
        return None, [_measure(check_id, where, subkey, False, "file_missing")]
    if len(found) > 1:
        return None, [_measure(check_id, item.relative, subkey, False, "file_duplicate") for item in found]
    problem = _file_problem(check_id, found[0], subkey)
    return (None, [problem]) if problem else (found[0], [])


# --- data set and subject level -------------------------------------------------------------------


def measure_description(ctx: CheckContext) -> list[Measurement]:
    """7.2, table 1: one data set description with Name and Version (strings); Author a list of strings."""
    if (single := _single(ctx, DESCRIPTION)) is not None:
        return single
    ds = dataset(ctx)
    found, out = _one(DESCRIPTION, ds.descriptions, DATASET, gbt.DESCRIPTION_STEM)
    if found is not None:
        out = _fields_of_mapping(
            DESCRIPTION, found.relative, found.data, DESCRIPTION_FIELDS, from_text=found.suffix == ".xml"
        )
    return out


def measure_description_name(ctx: CheckContext) -> list[Measurement]:
    """Table 1, AF-2: the data set name without spaces or special characters (letters, digits, '.', '_',
    '-')."""
    if (single := _single(ctx, DESCRIPTION_NAME)) is not None:
        return single
    found = dataset(ctx).description
    data = found.data if found is not None else None
    name = data.get("Name") if data is not None else None
    if found is None or not isinstance(name, str) or not name.strip():
        return [
            Measurement(
                check_id=DESCRIPTION_NAME, object=DATASET, state="not_checkable", reason=f"{PREFIX}.no_name"
            )
        ]
    return [
        _measure(
            DESCRIPTION_NAME, found.relative, "Name", bool(_NAME_CHARACTERS.match(name)), "name_characters"
        )
    ]


def _participant_ids(ds: gbt.GbtDataset) -> list[str] | None:
    table = ds.participants
    if table is None or table.problem is not None or "ParticipantId" not in table.columns:
        return None
    return [row["ParticipantId"].strip() for row in table.rows]


def measure_participants(ctx: CheckContext) -> list[Measurement]:
    """7.3, table 2: one subject table; ParticipantId in the form sub-<letters and digits>, unique; the
    optional
    fields typed (Age a number)."""
    if (single := _single(ctx, PARTICIPANTS)) is not None:
        return single
    ds = dataset(ctx)
    table, out = _one(PARTICIPANTS, ds.participants_tables, DATASET, gbt.PARTICIPANTS_STEM)
    if table is None:
        return out
    out = _table_columns(PARTICIPANTS, table, PARTICIPANT_FIELDS, unique="ParticipantId")
    ids = _participant_ids(ds) or []
    bad = [value for value in ids if value and not _label_ok(value, "sub-")]
    if ids:
        out.append(
            _measure(PARTICIPANTS, table.relative, "ParticipantId:form", not bad, "id_form", values=bad[:20])
        )
    return out


def _label_ok(name: str, prefix: str) -> bool:
    return name.startswith(prefix) and bool(gbt.LABEL.match(name[len(prefix) :]))


def measure_subject_folders(ctx: CheckContext) -> list[Measurement]:
    """6.1, 6.2: every subject folder named sub-<letters and digits>, holding data, matched one to one by a
    ParticipantId."""
    if (single := _single(ctx, SUBJECT_FOLDERS)) is not None:
        return single
    ds = dataset(ctx)
    if not ds.subjects:
        return [_measure(SUBJECT_FOLDERS, DATASET, "sub-*", False, "no_subjects")]
    ids = _participant_ids(ds)
    out = []
    for subject in ds.subjects:
        name = subject.relative.name
        out.append(
            _measure(SUBJECT_FOLDERS, subject.relative, "name", _label_ok(name, "sub-"), "folder_name")
        )
        has_data = bool(subject.sessions or subject.modalities)
        out.append(_measure(SUBJECT_FOLDERS, subject.relative, "data", has_data, "folder_empty"))
        if ids is not None:
            out.append(
                _measure(SUBJECT_FOLDERS, subject.relative, "ParticipantId", name in ids, "not_in_table")
            )
    if ids is not None and ds.participants is not None:
        folders = {subject.relative.name for subject in ds.subjects}
        for value in sorted(set(ids) - folders):
            if value:
                out.append(
                    _measure(SUBJECT_FOLDERS, ds.participants.relative, value, False, "folder_missing")
                )
    return out


def measure_sessions(ctx: CheckContext) -> list[Measurement]:
    """6.1, 6.2, 7.4, table 3: session folders ses-<letters and digits>; a session table where a subject has
    several sessions; SessionId in the form ses-<…>, unique, matched one to one with the folders; no modality
    folder beside session folders."""
    if (single := _single(ctx, SESSIONS)) is not None:
        return single
    out = []
    for subject in dataset(ctx).subjects:
        if subject.sessions and subject.modalities:
            out.append(_measure(SESSIONS, subject.relative, "levels", False, "mixed_levels"))
        for session in subject.sessions:
            out.append(
                _measure(
                    SESSIONS,
                    session.relative,
                    "name",
                    _label_ok(session.relative.name, "ses-"),
                    "folder_name",
                )
            )
        if len(subject.sessions) > 1 or subject.sessions_tables:
            table, problems = _one(SESSIONS, subject.sessions_tables, subject.relative, gbt.SESSIONS_STEM)
            out.extend(problems)
            if table is None:
                continue
            out.extend(_table_columns(SESSIONS, table, SESSION_FIELDS, unique="SessionId"))
            if "SessionId" not in table.columns:
                continue
            values = [row["SessionId"].strip() for row in table.rows]
            bad = [value for value in values if value and not _label_ok(value, "ses-")]
            out.append(
                _measure(SESSIONS, table.relative, "SessionId:form", not bad, "id_form", values=bad[:20])
            )
            folders = {session.relative.name for session in subject.sessions}
            for session in subject.sessions:
                ok = session.relative.name in values
                out.append(_measure(SESSIONS, session.relative, "SessionId", ok, "not_in_table"))
            for value in sorted(set(values) - folders):
                if value:
                    out.append(_measure(SESSIONS, table.relative, value, False, "folder_missing"))
        elif not subject.sessions and not subject.modalities:
            continue
        else:
            out.append(_measure(SESSIONS, subject.relative, "sessions", True))
    return out or [_measure(SESSIONS, DATASET, "sessions", True)]


def _labels(ds: gbt.GbtDataset) -> list[tuple[PurePosixPath, str]]:
    out = [(subject.relative, subject.relative.name[4:]) for subject in ds.subjects]
    out += [
        (session.relative, session.relative.name[4:])
        for subject in ds.subjects
        for session in subject.sessions
    ]
    return out


def measure_zero_padding(ctx: CheckContext) -> list[Measurement]:
    """6.2 (should): numeric subject and session labels zero-padded (sub-01, not sub-1)."""
    if (single := _single(ctx, ZERO_PADDING)) is not None:
        return single
    out = [
        _measure(ZERO_PADDING, path, "label", not (label.isdigit() and len(label) == 1), "not_zero_padded")
        for path, label in _labels(dataset(ctx))
    ]
    return out or [_measure(ZERO_PADDING, DATASET, "label", True)]


def measure_identifying_ids(ctx: CheckContext) -> list[Measurement]:
    """Table 2: subject IDs carry no identifying content. Reported: a label with six or more digits in a row,
    which may be an ID number (A-51 hint)."""
    if (single := _single(ctx, IDENTIFYING_IDS)) is not None:
        return single
    ds = dataset(ctx)
    out = [
        _measure(IDENTIFYING_IDS, path, "label", not _DIGIT_RUN.search(label), "id_may_identify")
        for path, label in _labels(ds)
    ]
    table = ds.participants
    for value in _participant_ids(ds) or []:
        if _DIGIT_RUN.search(value) and table is not None:
            out.append(_measure(IDENTIFYING_IDS, table.relative, value, False, "id_may_identify"))
    return out or [_measure(IDENTIFYING_IDS, DATASET, "label", True)]


# --- modality folders and files -------------------------------------------------------------------


def measure_modality_folders(ctx: CheckContext) -> list[Measurement]:
    """6.2, AF-1: modality folders in the spelling of the list (EEG, fNIRS, MEG, fMRI, iEEG, uEphys) or in
    lower
    case; every subject or session holds at least one."""
    if (single := _single(ctx, MODALITY_FOLDERS)) is not None:
        return single
    ds = dataset(ctx)
    out = []
    for _, _, folder in ds.modality_folders():
        ok = folder.spelling in gbt.MODALITIES or folder.spelling == folder.spelling.lower()
        out.append(_measure(MODALITY_FOLDERS, folder.relative, "spelling", ok, "modality_spelling"))
    for subject in ds.subjects:
        for session in subject.sessions:
            out.append(
                _measure(
                    MODALITY_FOLDERS, session.relative, "modality", bool(session.modalities), "no_modality"
                )
            )
    return out or [_measure(MODALITY_FOLDERS, DATASET, "modality", False, "no_modality")]


def _expected(subject: gbt.SubjectFolder, session: gbt.SessionFolder | None) -> tuple[str, str | None]:
    return subject.relative.name[4:], session.relative.name[4:] if session is not None else None


def measure_file_names(ctx: CheckContext) -> list[Measurement]:
    """7.5.7, 7.6: every file of a modality folder follows a naming rule; the subject and session labels in a
    name are those of its folders, the modality suffix that of the folder; a shared event table matches a
    signal file of a modality folder beside it."""
    if (single := _single(ctx, FILE_NAMES)) is not None:
        return single
    ds = dataset(ctx)
    out = []
    for subject, session, folder in ds.modality_folders():
        sub, ses = _expected(subject, session)
        for path in folder.unmatched:
            out.append(_measure(FILE_NAMES, path, "name", False, "file_name"))
        for signal in folder.signals:
            name = signal.name
            if not name.valid:
                out.append(_measure(FILE_NAMES, signal.relative, "name", False, "file_name"))
                continue
            ok = name.subject == sub and name.session == ses
            out.append(_measure(FILE_NAMES, signal.relative, "labels", ok, "name_folder_mismatch"))
            out.append(
                _measure(
                    FILE_NAMES,
                    signal.relative,
                    "modality",
                    signal.modality == folder.modality,
                    "modality_mismatch",
                )
            )
        for kind, name, table in folder.tables:
            ok = name.valid and name.subject == sub and name.session == ses and name.timestamp is None
            out.append(_measure(FILE_NAMES, table.relative, kind, ok, "name_folder_mismatch"))
    for subject in ds.subjects:
        levels: list[tuple[tuple[gbt.TableFile, ...], tuple[gbt.ModalityFolder, ...]]] = [
            (subject.shared_events, subject.modalities)
        ]
        levels += [(session.shared_events, session.modalities) for session in subject.sessions]
        for shared, modalities in levels:
            stems = {signal.stem for folder in modalities for signal in folder.signals}
            for table in shared:
                matches = table.relative.name.rsplit(f"_{gbt.EVENTS_KIND}", 1)[0]
                out.append(
                    _measure(FILE_NAMES, table.relative, "events", matches in stems, "events_unmatched")
                )
    return out or [_measure(FILE_NAMES, DATASET, "name", True)]


_LAYOUT_STEMS = (gbt.DESCRIPTION_STEM, gbt.PARTICIPANTS_STEM, gbt.SESSIONS_STEM)
_LAYOUT_TAILS = (*gbt.TABLE_KINDS, gbt.EVENTS_KIND)


def _metadata_name(path: PurePosixPath) -> tuple[bool, bool]:
    """(names a metadata file of the layout, in a recommended format)."""
    stem, suffix = path.stem, path.suffix.lower()
    if stem in _LAYOUT_STEMS:
        recommended = gbt.KEY_VALUE_SUFFIXES if stem == gbt.DESCRIPTION_STEM else gbt.TABLE_SUFFIXES
        return True, suffix in recommended
    if any(stem.endswith(f"_{tail}") for tail in _LAYOUT_TAILS):
        return True, suffix in gbt.TABLE_SUFFIXES
    return False, True


def measure_metadata_formats(ctx: CheckContext) -> list[Measurement]:
    """7.1 (should): key-value metadata as JSON or XML, tables as TSV or CSV. Reported: a file named as a
    metadata
    file of the layout in another format."""
    if (single := _single(ctx, METADATA_FORMATS)) is not None:
        return single
    ds = dataset(ctx)
    paths = list(ds.other)
    for subject in ds.subjects:
        paths += [*subject.other, *(p for session in subject.sessions for p in session.other)]
    paths += [p for _, _, folder in ds.modality_folders() for p in folder.unmatched]
    out = []
    for path in paths:
        named, recommended = _metadata_name(path)
        if named:
            out.append(_measure(METADATA_FORMATS, path, "format", recommended, "metadata_format"))
    return out or [_measure(METADATA_FORMATS, DATASET, "format", True)]


def _signals(
    ds: gbt.GbtDataset,
) -> list[tuple[gbt.SubjectFolder, gbt.SessionFolder | None, gbt.ModalityFolder, gbt.SignalFile]]:
    return [
        (subject, session, folder, signal)
        for subject, session, folder in ds.modality_folders()
        for signal in folder.signals
    ]


def _no_signal(check_id: str) -> list[Measurement]:
    return [
        Measurement(check_id=check_id, object=DATASET, state="not_applicable", reason=f"{PREFIX}.no_signal")
    ]


def measure_sidecar(ctx: CheckContext) -> list[Measurement]:
    """7.5, 7.5.7.2: every signal file has exactly one readable sidecar (same name, another extension)."""
    if (single := _single(ctx, SIDECAR)) is not None:
        return single
    out = []
    for _, _, _, signal in _signals(dataset(ctx)):
        found, problems = _one(SIDECAR, signal.sidecars, signal.relative, "sidecar")
        if found is None:
            out.extend(problems)
        else:
            out.append(_measure(SIDECAR, found.relative, "sidecar", True))
    return out or _no_signal(SIDECAR)


def measure_sidecar_fields(ctx: CheckContext) -> list[Measurement]:
    """Tables 4, 7, 10, 12, 13, 16: the required fields of the sidecar of each modality, typed."""
    if (single := _single(ctx, SIDECAR_FIELDS)) is not None:
        return single
    out = []
    for _, _, _, signal in _signals(dataset(ctx)):
        sidecar = signal.sidecars[0] if len(signal.sidecars) == 1 else None
        if sidecar is None or sidecar.data is None:
            continue  # reported by gbt47127.sidecar
        specs = SIDECAR_FIELDS_BY_MODALITY[signal.modality]
        out.extend(
            _fields_of_mapping(
                SIDECAR_FIELDS, sidecar.relative, sidecar.data, specs, from_text=sidecar.suffix == ".xml"
            )
        )
    return out or _no_signal(SIDECAR_FIELDS)


def _tables_for(folder: gbt.ModalityFolder, kind: str, signal: gbt.SignalFile) -> tuple[gbt.TableFile, ...]:
    return tuple(
        table
        for table_kind, name, table in folder.tables
        if table_kind == kind
        and (name.subject, name.session, name.task)
        == (signal.name.subject, signal.name.session, signal.name.task)
    )


def _per_task(ds: gbt.GbtDataset) -> list[tuple[gbt.ModalityFolder, gbt.SignalFile]]:
    """One signal per modality folder and task: channel and position tables are named per task (7.5.7.2)."""
    seen: set[tuple[str, str | None]] = set()
    out = []
    for _, _, folder, signal in _signals(ds):
        key = (folder.relative.as_posix(), signal.name.task)
        if key not in seen:
            seen.add(key)
            out.append((folder, signal))
    return out


def _task_object(folder: gbt.ModalityFolder, signal: gbt.SignalFile) -> PurePosixPath:
    return folder.relative / f"task-{signal.name.task}"


def measure_channels(ctx: CheckContext) -> list[Measurement]:
    """Tables 6, 9, 11, 15, 18: one channel table per modality folder and task (none for fMRI) with the
    required columns filled, typed values and unique channel names."""
    if (single := _single(ctx, CHANNELS)) is not None:
        return single
    out = []
    for folder, signal in _per_task(dataset(ctx)):
        specs = CHANNEL_FIELDS_BY_MODALITY.get(signal.modality)
        if specs is None:
            continue
        table, problems = _one(
            CHANNELS, _tables_for(folder, "channels", signal), _task_object(folder, signal), "channels"
        )
        out.extend(problems)
        if table is not None:
            out.extend(_table_columns(CHANNELS, table, specs, unique="Name"))
    return out or _no_signal(CHANNELS)


def measure_positions(ctx: CheckContext) -> list[Measurement]:
    """Tables 5, 8, 14, 17: one electrode table (EEG, iEEG, uEphys) or optode table (fNIRS) per modality
    folder
    and task, with the required columns filled, typed values, unique names and the optode types source or
    detector (AF-10)."""
    if (single := _single(ctx, POSITIONS)) is not None:
        return single
    out = []
    for folder, signal in _per_task(dataset(ctx)):
        spec = POSITION_TABLES.get(signal.modality)
        if spec is None:
            continue
        kind, fields, unique = spec
        table, problems = _one(
            POSITIONS, _tables_for(folder, kind, signal), _task_object(folder, signal), kind
        )
        out.extend(problems)
        if table is None:
            continue
        out.extend(_table_columns(POSITIONS, table, fields, unique=unique))
        if kind == "optodes" and "Type" in table.columns:
            bad = sorted(
                {
                    row["Type"]
                    for row in table.rows
                    if row["Type"].strip() not in MISSING_TEXT
                    and row["Type"].strip().lower() not in OPTODE_TYPES
                }
            )
            out.append(
                _measure(POSITIONS, table.relative, "Type:value", not bad, "optode_type", values=bad[:20])
            )
    return out or _no_signal(POSITIONS)


def _event_tables(ds: gbt.GbtDataset) -> list[gbt.TableFile]:
    tables: dict[str, gbt.TableFile] = {}
    for _, _, _, signal in _signals(ds):
        for table in (*signal.events, *signal.events_with_extension):
            tables[table.relative.as_posix()] = table
    for subject in ds.subjects:
        for table in (*subject.shared_events, *(t for s in subject.sessions for t in s.shared_events)):
            tables[table.relative.as_posix()] = table
    return [tables[key] for key in sorted(tables)]


def measure_events(ctx: CheckContext) -> list[Measurement]:
    """7.6, table 19: event tables readable, with Onset and Duration (numbers) and Value filled in every
    row."""
    if (single := _single(ctx, EVENTS)) is not None:
        return single
    out = []
    for table in _event_tables(dataset(ctx)):
        problem = _file_problem(EVENTS, table, "events")
        out.extend([problem] if problem else _table_columns(EVENTS, table, EVENT_FIELDS))
    if not out:
        return [
            Measurement(check_id=EVENTS, object=DATASET, state="not_applicable", reason=f"{PREFIX}.no_events")
        ]
    return out


def measure_events_name(ctx: CheckContext) -> list[Measurement]:
    """7.6, AF-4: <matches> of an event table is the signal file name without its extension."""
    if (single := _single(ctx, EVENTS_NAME)) is not None:
        return single
    out = []
    for _, _, _, signal in _signals(dataset(ctx)):
        out += [_measure(EVENTS_NAME, t.relative, "matches", True) for t in signal.events]
        out += [
            _measure(EVENTS_NAME, t.relative, "matches", False, "events_name_extension")
            for t in signal.events_with_extension
        ]
    if not out:
        return [
            Measurement(
                check_id=EVENTS_NAME, object=DATASET, state="not_applicable", reason=f"{PREFIX}.no_events"
            )
        ]
    return out


def measure_timestamp(ctx: CheckContext) -> list[Measurement]:
    """7.5.7.1 (should): the optional timestamp of a signal file name as YYYYMMDD-HHMMSS."""
    if (single := _single(ctx, TIMESTAMP)) is not None:
        return single
    out = [
        _measure(
            TIMESTAMP,
            signal.relative,
            "timestamp",
            bool(gbt.TIMESTAMP.match(signal.name.timestamp)),
            "timestamp_form",
        )
        for _, _, _, signal in _signals(dataset(ctx))
        if signal.name.timestamp is not None
    ]
    if not out:
        return [
            Measurement(
                check_id=TIMESTAMP, object=DATASET, state="not_applicable", reason=f"{PREFIX}.no_timestamp"
            )
        ]
    return out


def _as_float(value: Any) -> float | None:
    """A sidecar number: a JSON number, or the text of an XML element (IQ-004); else None."""
    if _number(value, isinstance(value, str)):
        return float(value)
    return None


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9)


def measure_signal_consistency(ctx: CheckContext) -> list[Measurement]:
    """A-113: the sidecar's SamplingFrequency and ChannelCount agree with the signal file (EEG and iEEG files
    in a
    format NeuroGrid reads) and ChannelCount with the rows of the channel table."""
    if (single := _single(ctx, SIGNAL_CONSISTENCY)) is not None:
        return single
    ds = dataset(ctx)
    read = {rec.found.relative.as_posix(): rec.recording for rec in ctx.recordings}
    out = []
    for _, _, folder, signal in _signals(ds):
        data = signal.sidecars[0].data if len(signal.sidecars) == 1 else None
        if data is None:
            continue
        relative = signal.relative
        count = _as_float(data.get("ChannelCount"))
        tables = _tables_for(folder, "channels", signal)
        if count is not None and len(tables) == 1 and tables[0].problem is None:
            rows = len(tables[0].rows)
            out.append(
                _measure(
                    SIGNAL_CONSISTENCY,
                    relative,
                    "ChannelCount:table",
                    _close(count, rows),
                    "count_table",
                    sidecar=count,
                    table=rows,
                )
            )
        if signal.modality not in READABLE_MODALITIES:
            continue
        recording = read.get(relative.as_posix())
        if recording is None:
            out.append(
                Measurement(
                    check_id=SIGNAL_CONSISTENCY,
                    object=relative.as_posix(),
                    subkey="signal",
                    file=relative.as_posix(),
                    state="not_checkable",
                    reason=f"{PREFIX}.signal_not_read",
                    identity=(relative.as_posix(),),
                )
            )
            continue
        rate = _as_float(data.get("SamplingFrequency"))
        if rate is not None and recording.sampling_rate_hz is not None:
            ok = _close(rate, recording.sampling_rate_hz)
            out.append(
                _measure(
                    SIGNAL_CONSISTENCY,
                    relative,
                    "SamplingFrequency",
                    ok,
                    "rate_signal",
                    sidecar=rate,
                    signal=recording.sampling_rate_hz,
                )
            )
        if count is not None:
            channels = len(recording.channels)
            out.append(
                _measure(
                    SIGNAL_CONSISTENCY,
                    relative,
                    "ChannelCount:signal",
                    _close(count, channels),
                    "count_signal",
                    sidecar=count,
                    signal=channels,
                )
            )
    return out or _no_signal(SIGNAL_CONSISTENCY)


def _plain(ctx: CheckContext) -> bool:
    """Names are shown as written in a BIDS or GB/T 47127 data set and with --show-paths; in any other folder
    checked with this pack they are pseudonymous like every raw-folder name (A-51, D-10 f)."""
    return ctx.show_paths or ctx.scan.is_bids or gbt.looks_like_gbt47127(ctx.root)


def _pseudonymous(measurement: Measurement) -> Measurement:
    """The measurement with a pseudonymous object and file and without listed values (A-51)."""
    if measurement.object == DATASET:
        return measurement
    relative = PurePosixPath(measurement.object)
    pseudo = pseudonym(relative)
    suffix = relative.suffix.lower()
    details = {key: value for key, value in measurement.details.items() if key != "values"}
    return Measurement(
        check_id=measurement.check_id,
        object=pseudo,
        subkey=measurement.subkey if _safe_subkey(measurement.subkey) else "value",
        file=f"{pseudo}{shown_extension(suffix)}",
        value=measurement.value,
        state=measurement.state,
        reason=measurement.reason,
        details=details,
        identity=(relative.as_posix(), pseudo, f"{pseudo}{shown_extension(suffix)}"),
    )


def _shown(
    measure: Callable[[CheckContext], list[Measurement]],
) -> Callable[[CheckContext], list[Measurement]]:
    def run(ctx: CheckContext) -> list[Measurement]:
        found = measure(ctx)
        return found if _plain(ctx) else [_pseudonymous(m) for m in found]

    run.__doc__ = measure.__doc__
    return run


Measurer = Callable[[CheckContext], list[Measurement]]
MEASURERS: dict[str, Measurer] = {
    DESCRIPTION: measure_description,
    DESCRIPTION_NAME: measure_description_name,
    PARTICIPANTS: measure_participants,
    SUBJECT_FOLDERS: measure_subject_folders,
    SESSIONS: measure_sessions,
    ZERO_PADDING: measure_zero_padding,
    MODALITY_FOLDERS: measure_modality_folders,
    FILE_NAMES: measure_file_names,
    METADATA_FORMATS: measure_metadata_formats,
    SIDECAR: measure_sidecar,
    SIDECAR_FIELDS: measure_sidecar_fields,
    CHANNELS: measure_channels,
    POSITIONS: measure_positions,
    EVENTS: measure_events,
    EVENTS_NAME: measure_events_name,
    TIMESTAMP: measure_timestamp,
    IDENTIFYING_IDS: measure_identifying_ids,
    SIGNAL_CONSISTENCY: measure_signal_consistency,
}
MEASURERS = {check_id: _shown(measure) for check_id, measure in MEASURERS.items()}
SPECS = tuple(CheckSpec(id=check_id, evaluate=is_true) for check_id in MEASURERS)


def structure_counts(root: Path, severities: Mapping[str, str]) -> tuple[int, int]:
    """Errors and warnings of the pack's checks on a folder ``convert`` has just written, without the
    comparison with the signal (which needs the signal pass of ``check``); ``severities``: check ID -> the
    severity of its rule. The counterpart of the BIDS validator run after ``convert --to bids``."""
    from types import SimpleNamespace

    ctx: Any = SimpleNamespace(
        root=root,
        scan=SimpleNamespace(single_file=False, is_bids=False),
        show_paths=True,
        recordings=[],
        gbt47127=None,
    )
    errors = warnings = 0
    for check_id, measure in MEASURERS.items():
        if check_id == SIGNAL_CONSISTENCY or check_id not in severities:
            continue
        failed = sum(1 for m in measure(ctx) if m.state == "measured" and m.value is False)
        if severities[check_id] == "error":
            errors += failed
        elif severities[check_id] == "warning":
            warnings += failed
    return errors, warnings
