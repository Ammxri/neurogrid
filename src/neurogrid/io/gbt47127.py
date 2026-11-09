"""Data sets in the GB/T 47127—2026 multi-modal data format: reading (NG-F03, RP-11, ARC-04; A-112 ff.).

Own description of the layout, no norm text (A-55); clause numbers in brackets:

- The data set folder holds the data set description ``dataset_description.<ext>`` (key-value), the subject
  table ``participants.<ext>`` and one folder ``sub-<label>`` per subject (6.1, 7.2, 7.3).
- A subject folder holds ``ses-<label>`` folders and the session table ``sessions.<ext>``; with a single
  session the session level may be left out and the subject folder holds the modality folders itself
  (6.1, 7.4).
- Modality folders are named EEG, fNIRS, MEG, fMRI, iEEG or uEphys (6.2). They hold the signal files
  ``sub-<l>[_ses-<l>]_task-<l>[_<timestamp>]_<modality>.<ext>``, a key-value sidecar with the same name and
  another extension, the tables ``sub-<l>[_ses-<l>]_task-<l>_channels.<ext>``, ``..._electrodes.<ext>`` (EEG,
  iEEG, uEphys) or ``..._optodes.<ext>`` (fNIRS), and event tables ``<matches>_events.<ext>`` (7.5, 7.6).
  An event table may also lie one level above the modality folders when several modalities share it (7.6).
- Key-value files are JSON or XML, tables TSV or CSV (7.1).

Reading never follows links and skips hidden entries, like discovery (A-52, A-66). Nothing raises for a
malformed file: every file carries its reading problem as a stable key, so that the checks report it.

Interpretations of the lead (A-112 ff., ENTSCHEIDUNGEN): modality folder names and file suffixes are matched
without regard to case and keep their spelling for the checks (AF-1); an XML key-value file is a root element
whose children are the fields (a repeated child is a list, a child with children a mapping), and documents
with a DOCTYPE or entity declaration are refused (AF-9); ``<matches>`` of an event table is the signal file
name without its extension, with the extension it is recognised as well (AF-4).
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from neurogrid.kernel.errors import InputError
from neurogrid.kernel.safety import decode_text, is_link, read_limited

FORMAT = "gbt47127"
MODALITIES = ("EEG", "fNIRS", "MEG", "fMRI", "iEEG", "uEphys")  # 6.2, 7.5.7.1
KEY_VALUE_SUFFIXES = (".json", ".xml")  # 7.1
TABLE_SUFFIXES = (".tsv", ".csv")  # 7.1
DESCRIPTION_STEM = "dataset_description"  # 7.2
PARTICIPANTS_STEM = "participants"  # 7.3
SESSIONS_STEM = "sessions"  # 7.4
TABLE_KINDS = ("channels", "electrodes", "optodes")  # 7.5.7.2
EVENTS_KIND = "events"  # 7.6
MAX_METADATA_BYTES = 2_000_000
MAX_XML_DEPTH = 32
LABEL = re.compile(r"^[A-Za-z0-9]+$")  # participant and session labels: letters and digits only (6.2)
TIMESTAMP = re.compile(r"^\d{8}-\d{6}$")  # the recommended form YYYYMMDD-HHMMSS (7.5.7.1)
_MODALITY_BY_LOWER = {name.lower(): name for name in MODALITIES}
_XML_DECLARATIONS = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


def modality_of(name: str) -> str | None:
    """The modality a folder name or file suffix stands for (case-insensitive, AF-1), else None."""
    return _MODALITY_BY_LOWER.get(name.lower())


@dataclass(frozen=True)
class KeyValueFile:
    """A key-value metadata file (7.1): ``data`` is None when ``problem`` names why it could not be read."""

    relative: PurePosixPath
    data: dict[str, Any] | None
    problem: str | None = None

    @property
    def suffix(self) -> str:
        return self.relative.suffix.lower()


@dataclass(frozen=True)
class TableFile:
    """An instance metadata table (7.1): one row per instance; cells as text, header order kept."""

    relative: PurePosixPath
    columns: tuple[str, ...] = ()
    rows: tuple[dict[str, str], ...] = ()
    problem: str | None = None

    @property
    def suffix(self) -> str:
        return self.relative.suffix.lower()


@dataclass(frozen=True)
class FileName:
    """The parts of a file name in a modality folder (7.5.7); ``valid``: it follows the pattern."""

    subject: str | None = None
    session: str | None = None
    task: str | None = None
    timestamp: str | None = None
    tail: str | None = None  # the last part: a modality suffix, channels, electrodes, optodes or events
    valid: bool = False


@dataclass(frozen=True)
class SignalFile:
    """A signal recording data file with its sidecar and event tables (7.5, 7.6)."""

    relative: PurePosixPath
    name: FileName
    modality: str  # canonical spelling (MODALITIES)
    sidecars: tuple[KeyValueFile, ...] = ()  # same name, another extension; more than one is a finding
    events: tuple[TableFile, ...] = ()
    events_with_extension: tuple[TableFile, ...] = ()  # <matches> written with the signal's extension (AF-4)

    @property
    def stem(self) -> str:
        return (
            self.relative.name[: -len(self.relative.suffix)] if self.relative.suffix else self.relative.name
        )


@dataclass(frozen=True)
class ModalityFolder:
    relative: PurePosixPath
    modality: str  # canonical spelling
    spelling: str  # as found (AF-1)
    signals: tuple[SignalFile, ...] = ()
    tables: tuple[
        tuple[str, FileName, TableFile], ...
    ] = ()  # (kind, name parts, table) for channels/electrodes/optodes
    unmatched: tuple[PurePosixPath, ...] = ()  # files that follow no naming rule of 7.5.7 or 7.6


@dataclass(frozen=True)
class SessionFolder:
    relative: PurePosixPath
    label: str
    modalities: tuple[ModalityFolder, ...] = ()
    shared_events: tuple[TableFile, ...] = ()  # event tables beside the modality folders (7.6)
    other: tuple[PurePosixPath, ...] = ()


@dataclass(frozen=True)
class SubjectFolder:
    relative: PurePosixPath
    label: str
    sessions_tables: tuple[TableFile, ...] = ()
    sessions: tuple[SessionFolder, ...] = ()
    modalities: tuple[ModalityFolder, ...] = ()  # without a session level (6.1)
    shared_events: tuple[TableFile, ...] = ()
    other: tuple[PurePosixPath, ...] = ()


@dataclass(frozen=True)
class GbtDataset:
    root: Path
    descriptions: tuple[KeyValueFile, ...] = ()  # dataset_description.<ext>; more than one is a finding
    participants_tables: tuple[TableFile, ...] = ()
    subjects: tuple[SubjectFolder, ...] = ()
    other: tuple[PurePosixPath, ...] = ()  # entries of the data set folder outside the layout
    skipped_links: tuple[PurePosixPath, ...] = ()
    unreadable: tuple[PurePosixPath, ...] = ()  # folders that could not be listed

    @property
    def description(self) -> KeyValueFile | None:
        return self.descriptions[0] if len(self.descriptions) == 1 else None

    @property
    def participants(self) -> TableFile | None:
        return self.participants_tables[0] if len(self.participants_tables) == 1 else None

    def modality_folders(self) -> list[tuple[SubjectFolder, SessionFolder | None, ModalityFolder]]:
        out: list[tuple[SubjectFolder, SessionFolder | None, ModalityFolder]] = []
        for subject in self.subjects:
            out.extend((subject, None, folder) for folder in subject.modalities)
            for session in subject.sessions:
                out.extend((subject, session, folder) for folder in session.modalities)
        return out


# --- metadata files -------------------------------------------------------------------------------


def _xml_value(element: ElementTree.Element, depth: int) -> Any:
    if depth > MAX_XML_DEPTH:
        raise ValueError("depth")
    children = list(element)
    if not children:
        return (element.text or "").strip()
    out: dict[str, Any] = {}
    for child in children:
        value = _xml_value(child, depth + 1)
        if child.tag in out:
            existing = out[child.tag]
            out[child.tag] = [*existing, value] if isinstance(existing, list) else [existing, value]
        else:
            out[child.tag] = value
    return out


def parse_key_value(data: bytes, suffix: str) -> dict[str, Any]:
    """The fields of a JSON object or an XML document (AF-9); ValueError with a reason key otherwise."""
    if suffix == ".json":
        try:
            parsed = json.loads(decode_text(data, ValueError, "gbt47127.encoding"))
        except (json.JSONDecodeError, RecursionError):
            raise ValueError("gbt47127.json_invalid") from None
        if not isinstance(parsed, dict):
            raise ValueError("gbt47127.not_object")
        return parsed
    if _XML_DECLARATIONS.search(data):
        raise ValueError("gbt47127.xml_declaration")
    try:
        root = ElementTree.fromstring(data)
        value = _xml_value(root, 0)
    except (ElementTree.ParseError, ValueError):
        raise ValueError("gbt47127.xml_invalid") from None
    return value if isinstance(value, dict) else {}


def read_key_value(root: Path, relative: PurePosixPath) -> KeyValueFile:
    try:
        data = read_limited(root / relative, MAX_METADATA_BYTES)
        return KeyValueFile(relative, parse_key_value(data, relative.suffix.lower()))
    except InputError as exc:
        return KeyValueFile(
            relative,
            None,
            "gbt47127.too_large" if exc.message_key == "file.too_large" else "gbt47127.unreadable",
        )
    except ValueError as exc:
        return KeyValueFile(relative, None, str(exc))
    except OSError:
        return KeyValueFile(relative, None, "gbt47127.unreadable")


def parse_table(data: bytes, suffix: str) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    """Header and rows of a TSV or CSV table; ValueError with a reason key for a malformed table."""
    text = decode_text(data, ValueError, "gbt47127.encoding")
    delimiter = "\t" if suffix == ".tsv" else ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        lines = [line for line in reader if line != []]
    except csv.Error:
        raise ValueError("gbt47127.table_invalid") from None
    if not lines:
        raise ValueError("gbt47127.table_empty")
    header = tuple(cell.strip() for cell in lines[0])
    if len(set(header)) != len(header) or any(not name for name in header):
        raise ValueError("gbt47127.table_header")
    rows = []
    for line in lines[1:]:
        if len(line) != len(header):
            raise ValueError("gbt47127.table_row_length")
        rows.append({name: cell.strip() for name, cell in zip(header, line, strict=True)})
    return header, tuple(rows)


def read_table(root: Path, relative: PurePosixPath) -> TableFile:
    try:
        columns, rows = parse_table(
            read_limited(root / relative, MAX_METADATA_BYTES), relative.suffix.lower()
        )
        return TableFile(relative, columns, rows)
    except InputError as exc:
        return TableFile(
            relative,
            problem="gbt47127.too_large" if exc.message_key == "file.too_large" else "gbt47127.unreadable",
        )
    except ValueError as exc:
        return TableFile(relative, problem=str(exc))
    except OSError:
        return TableFile(relative, problem="gbt47127.unreadable")


# --- names ----------------------------------------------------------------------------------------


def parse_name(stem: str) -> FileName:
    """Split a file stem of a modality folder into its parts (7.5.7): ``sub-<l>[_ses-<l>]_task-<l>`` then
    optionally a timestamp, then the last part. Labels of subject and session must be letters and digits."""
    parts = stem.split("_")
    if len(parts) < 3 or not parts[0].startswith("sub-"):
        return FileName()
    subject = parts[0][4:]
    index = 1
    session = None
    if parts[index].startswith("ses-"):
        session = parts[index][4:]
        index += 1
    if index >= len(parts) or not parts[index].startswith("task-"):
        return FileName(subject=subject, session=session)
    task = parts[index][5:]
    rest = parts[index + 1 :]
    if not rest or len(rest) > 2:
        return FileName(subject=subject, session=session, task=task)
    timestamp = rest[0] if len(rest) == 2 else None
    valid = bool(
        LABEL.match(subject) and (session is None or LABEL.match(session)) and task and "-" not in rest[-1]
    )
    return FileName(subject, session, task, timestamp, rest[-1], valid)


# --- walking --------------------------------------------------------------------------------------


def _names(folder: Path) -> list[str]:
    """The sorted entry names of a folder; OSError when it cannot be listed."""
    return sorted(entry.name for entry in folder.iterdir())


@dataclass
class _Walk:
    root: Path
    links: list[PurePosixPath] = field(default_factory=list)
    unreadable: list[PurePosixPath] = field(default_factory=list)

    def entries(self, relative: PurePosixPath) -> list[tuple[str, bool]]:
        """(name, is folder) of the visible entries of a folder, links counted and skipped (A-52, A-66)."""
        folder = self.root / relative if relative.parts else self.root
        try:
            names = _names(folder)
        except OSError:
            self.unreadable.append(relative)
            return []
        out = []
        for name in names:
            if name.startswith("."):
                continue
            path = folder / name
            if is_link(path):
                self.links.append(relative / name)
                continue
            out.append((name, path.is_dir()))
        return out


def _stem_and_suffix(name: str) -> tuple[str, str]:
    path = PurePosixPath(name)
    return (name[: -len(path.suffix)] if path.suffix else name), path.suffix.lower()


def _events_for(
    stem: str, signal_name: str, tables: dict[str, TableFile]
) -> tuple[list[TableFile], list[TableFile]]:
    plain = [table for key, table in tables.items() if key == f"{stem}_{EVENTS_KIND}"]
    with_extension = [table for key, table in tables.items() if key == f"{signal_name}_{EVENTS_KIND}"]
    return plain, with_extension


def _modality_folder(walk: _Walk, relative: PurePosixPath, spelling: str) -> ModalityFolder:
    modality = modality_of(spelling) or spelling
    files = [name for name, is_dir in walk.entries(relative) if not is_dir]
    key_values: dict[str, list[KeyValueFile]] = {}
    events: dict[str, TableFile] = {}
    tables: list[tuple[str, FileName, TableFile]] = []
    signal_names: list[tuple[str, str, FileName]] = []
    unmatched: list[PurePosixPath] = []
    for name in files:
        stem, suffix = _stem_and_suffix(name)
        if stem.endswith(f"_{EVENTS_KIND}") and suffix in TABLE_SUFFIXES:
            events[stem] = read_table(walk.root, relative / name)
            continue
        parsed = parse_name(stem)
        tail = (parsed.tail or "").lower()
        if parsed.task is not None and tail in TABLE_KINDS and suffix in TABLE_SUFFIXES:
            tables.append((tail, parsed, read_table(walk.root, relative / name)))
        elif parsed.task is not None and modality_of(parsed.tail or "") is not None:
            if suffix in KEY_VALUE_SUFFIXES:
                key_values.setdefault(stem, []).append(read_key_value(walk.root, relative / name))
            else:
                signal_names.append((name, stem, parsed))
        else:
            unmatched.append(relative / name)
    # the data and marker file of a BrainVision header and the .fdt of an EEGLAB set are part of that signal
    # file, not signal files of their own (A-12)
    headers = {(stem, PurePosixPath(name).suffix.lower()) for name, stem, _ in signal_names}
    companions = {".eeg": ".vhdr", ".vmrk": ".vhdr", ".fdt": ".set"}
    signal_names = [
        (name, stem, parsed)
        for name, stem, parsed in signal_names
        if (stem, companions.get(PurePosixPath(name).suffix.lower(), "")) not in headers
    ]
    signals = []
    claimed_events: set[str] = set()
    claimed_sidecars: set[str] = set()
    for name, stem, parsed in signal_names:
        plain, with_extension = _events_for(stem, name, events)
        claimed_events.update(t.relative.name for t in (*plain, *with_extension))
        claimed_sidecars.add(stem)
        signals.append(
            SignalFile(
                relative=relative / name,
                name=parsed,
                modality=modality_of(parsed.tail or "") or modality,
                sidecars=tuple(key_values.get(stem, ())),
                events=tuple(plain),
                events_with_extension=tuple(with_extension),
            )
        )
    # a sidecar without a signal file and an event table that matches no signal follow no rule of 7.5.7/7.6
    unmatched.extend(
        kv.relative for stem, items in key_values.items() if stem not in claimed_sidecars for kv in items
    )
    unmatched.extend(t.relative for t in events.values() if t.relative.name not in claimed_events)
    return ModalityFolder(
        relative=relative,
        modality=modality,
        spelling=spelling,
        signals=tuple(signals),
        tables=tuple(tables),
        unmatched=tuple(sorted(unmatched)),
    )


def _level(
    walk: _Walk, relative: PurePosixPath
) -> tuple[list[ModalityFolder], list[TableFile], list[PurePosixPath], list[tuple[str, bool]]]:
    """Modality folders, shared event tables and other entries of a subject or session folder."""
    modalities: list[ModalityFolder] = []
    shared: list[TableFile] = []
    other: list[PurePosixPath] = []
    rest: list[tuple[str, bool]] = []
    for name, is_dir in walk.entries(relative):
        stem, suffix = _stem_and_suffix(name)
        if is_dir and modality_of(name) is not None:
            modalities.append(_modality_folder(walk, relative / name, name))
        elif not is_dir and stem.endswith(f"_{EVENTS_KIND}") and suffix in TABLE_SUFFIXES:
            shared.append(read_table(walk.root, relative / name))
        else:
            rest.append((name, is_dir))
            other.append(relative / name)
    return modalities, shared, other, rest


def _session(walk: _Walk, relative: PurePosixPath) -> SessionFolder:
    modalities, shared, other, _ = _level(walk, relative)
    return SessionFolder(
        relative=relative,
        label=relative.name[4:],
        modalities=tuple(modalities),
        shared_events=tuple(shared),
        other=tuple(other),
    )


def _subject(walk: _Walk, relative: PurePosixPath) -> SubjectFolder:
    modalities, shared, _, rest = _level(walk, relative)
    sessions: list[SessionFolder] = []
    tables: list[TableFile] = []
    other: list[PurePosixPath] = []
    for name, is_dir in rest:
        stem, suffix = _stem_and_suffix(name)
        if is_dir and name.startswith("ses-"):
            sessions.append(_session(walk, relative / name))
        elif not is_dir and stem == SESSIONS_STEM and suffix in TABLE_SUFFIXES:
            tables.append(read_table(walk.root, relative / name))
        else:
            other.append(relative / name)
    return SubjectFolder(
        relative=relative,
        label=relative.name[4:],
        sessions_tables=tuple(tables),
        sessions=tuple(sessions),
        modalities=tuple(modalities),
        shared_events=tuple(shared),
        other=tuple(other),
    )


def read_dataset(root: Path) -> GbtDataset:
    """The GB/T 47127 view of a data set folder. Never raises for content; a folder that cannot be listed is
    listed in ``unreadable``."""
    walk = _Walk(root)
    descriptions: list[KeyValueFile] = []
    participants: list[TableFile] = []
    subjects: list[SubjectFolder] = []
    other: list[PurePosixPath] = []
    top = PurePosixPath()
    for name, is_dir in walk.entries(top):
        stem, suffix = _stem_and_suffix(name)
        if not is_dir and stem == DESCRIPTION_STEM and suffix in KEY_VALUE_SUFFIXES:
            descriptions.append(read_key_value(root, top / name))
        elif not is_dir and stem == PARTICIPANTS_STEM and suffix in TABLE_SUFFIXES:
            participants.append(read_table(root, top / name))
        elif is_dir and name.startswith("sub-"):
            subjects.append(_subject(walk, top / name))
        else:
            other.append(top / name)
    return GbtDataset(
        root=root,
        descriptions=tuple(descriptions),
        participants_tables=tuple(participants),
        subjects=tuple(subjects),
        other=tuple(other),
        skipped_links=tuple(walk.links),
        unreadable=tuple(walk.unreadable),
    )


def _modality_folder_names(root: Path) -> list[str]:
    """Names of the modality folders (6.2) below ``sub-`` folders, with or without a session level; links are
    not entered."""
    found: list[str] = []
    try:
        names = _names(root)
    except OSError:
        return found
    for name in names:
        subject = root / name
        if not name.startswith("sub-") or is_link(subject) or not subject.is_dir():
            continue
        try:
            entries = _names(subject)
        except OSError:
            continue
        for entry in entries:
            path = subject / entry
            if is_link(path) or not path.is_dir():
                continue
            if modality_of(entry) is not None:
                found.append(entry)
            elif entry.startswith("ses-"):
                try:
                    inner = _names(path)
                except OSError:
                    continue
                found.extend(
                    n
                    for n in inner
                    if modality_of(n) is not None and not is_link(path / n) and (path / n).is_dir()
                )
    return found


def looks_like_gbt47127(root: Path) -> bool:
    """Layout recognition (A-112). A data set is taken as GB/T 47127 when its folder holds a data set
    description, no JSON description names a ``BIDSVersion``, and a modality folder (6.2) lies below a
    ``sub-`` folder that is either written in the spelling of the list of 6.2 (``EEG``, ``fNIRS`` …, which
    BIDS never uses) or comes with an XML description (BIDS has none). A lower-case ``eeg`` folder with a
    JSON description stays a BIDS candidate as before; ``check --rulepack gbt47127`` reads such a folder as
    GB/T all the same."""
    try:
        names = _names(root)
    except OSError:
        return False
    descriptions = [
        n for n in names if _stem_and_suffix(n) in {(DESCRIPTION_STEM, s) for s in KEY_VALUE_SUFFIXES}
    ]
    if not descriptions:
        return False
    for name in descriptions:
        if is_link(root / name):
            continue  # never read through a link (A-52)
        if _stem_and_suffix(name)[1] == ".json":
            try:
                data = parse_key_value(read_limited(root / name, MAX_METADATA_BYTES), ".json")
            except (InputError, ValueError, OSError):
                continue
            if "BIDSVersion" in data:
                return False
    folders = _modality_folder_names(root)
    xml = any(_stem_and_suffix(n)[1] == ".xml" for n in descriptions)
    return any(xml or name != name.lower() for name in folders)


# --- writing: a BIDS data set in the GB/T 47127 layout (convert --to gbt47127, A-114 ff.) -----------------

FORMAT_VERSION = "GB/T 47127-2026"  # table 1: Version is the version of the format the data set follows
_BIDS_DATA_SUFFIXES = (".edf", ".bdf", ".vhdr")
_BIDS_ENTITY = re.compile(r"(?:^|_)(sub|ses|task|acq|run)-([A-Za-z0-9]+)")
# GB/T EEG sidecar field <- BIDS eeg.json key; values n/a or missing are left out, never invented
_SIDECAR_FROM_BIDS = (
    ("TaskName", "TaskName"),
    ("EEGReference", "EEGReference"),
    ("SamplingFrequency", "SamplingFrequency"),
    ("PowerlineFrequency", "PowerLineFrequency"),
    ("InstituteName", "InstitutionName"),
    ("PlacementScheme", "EEGPlacementScheme"),
    ("SoftwareFilters", "SoftwareFilters"),
    ("HardwareFilters", "HardwareFilters"),
)
_JOINED_FROM_BIDS = (
    ("HardwareInfo", ("Manufacturer", "ManufacturersModelName")),
    ("CapInfo", ("CapManufacturer", "CapManufacturersModelName")),
)
_COUNT_KEYS = ("EEGChannelCount", "EOGChannelCount", "ECGChannelCount", "EMGChannelCount", "MiscChannelCount")
_CHANNELS_FROM_BIDS = (
    ("Name", "name"),
    ("Type", "type"),
    ("Unit", "units"),
    ("Description", "description"),
    ("LowCutoff", "low_cutoff"),
    ("HighCutoff", "high_cutoff"),
    ("Notch", "notch"),
)
_ELECTRODES_FROM_BIDS = (
    ("Name", "name"),
    ("X", "x"),
    ("Y", "y"),
    ("Z", "z"),
    ("Type", "type"),
    ("Material", "material"),
)
_PARTICIPANTS_FROM_BIDS = (
    ("ParticipantId", "participant_id"),
    ("Species", "species"),
    ("Age", "age"),
    ("Sex", "sex"),
    ("Handedness", "handedness"),
)
REQUIRED_COLUMNS = {"channels": ("Name", "Type", "Unit"), "electrodes": ("Name", "X", "Y", "Z")}
REQUIRED_SIDECAR = ("TaskName", "EEGReference", "SamplingFrequency", "PowerlineFrequency", "ChannelCount")


@dataclass(frozen=True)
class WrittenRecording:
    """One signal file written: its BIDS source and GB/T target (relative POSIX paths) and the files that make
    them up, for the processing step (DM-07)."""

    source: str
    target: str
    input_files: tuple[Path, ...]
    output_files: tuple[Path, ...]


@dataclass
class GbtWriteResult:
    written: list[WrittenRecording] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (BIDS relative path, reason key)
    gaps: dict[str, int] = field(default_factory=dict)  # required element -> files written without it

    def gap(self, name: str) -> None:
        self.gaps[name] = self.gaps.get(name, 0) + 1


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() in ("", "n/a")) or value == []


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = parse_key_value(read_limited(path, MAX_METADATA_BYTES), ".json")
    except (InputError, ValueError, OSError):
        return {}
    return data


def _read_rows(path: Path) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    try:
        return parse_table(read_limited(path, MAX_METADATA_BYTES), ".tsv")
    except (InputError, ValueError, OSError):
        return (), ()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_bytes((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _write_table(path: Path, header: list[str], rows: list[list[str]]) -> None:
    def cell(text: str) -> str:
        return " ".join(str(text).replace("\t", " ").split())

    lines = ["\t".join(header), *("\t".join(cell(value) for value in row) for row in rows)]
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _mapped_table(
    source: Path, mapping: tuple[tuple[str, str], ...], required: tuple[str, ...]
) -> tuple[list[str], list[list[str]]]:
    """The BIDS table as a GB/T table: renamed columns, n/a as an empty cell; optional columns only when the
    source has them, required columns always."""
    columns, rows = _read_rows(source)
    pairs = [
        (gbt_name, bids_name)
        for gbt_name, bids_name in mapping
        if bids_name in columns or gbt_name in required
    ]
    header = [gbt_name for gbt_name, _ in pairs]
    out = [["" if _missing(row.get(bids_name)) else row[bids_name] for _, bids_name in pairs] for row in rows]
    return header, out


def _inherited(root: Path, folder: Path, entities: dict[str, str], suffix: str) -> dict[str, Any]:
    """The BIDS sidecar of a recording with the inheritance principle: data set, subject and session level
    files for its task, then its own (later ones win)."""
    task = entities.get("task", "")
    names = [
        root / f"task-{task}_{suffix}.json",
        root / f"sub-{entities['sub']}" / f"sub-{entities['sub']}_task-{task}_{suffix}.json",
    ]
    if "ses" in entities:
        ses = root / f"sub-{entities['sub']}" / f"ses-{entities['ses']}"
        names.append(ses / f"sub-{entities['sub']}_ses-{entities['ses']}_task-{task}_{suffix}.json")
    merged: dict[str, Any] = {}
    for path in names:
        if path.is_file() and not is_link(path):
            merged.update(_read_json(path))
    return merged


def _gbt_sidecar(bids: dict[str, Any], channel_rows: int | None, result: GbtWriteResult) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for gbt_name, bids_name in _SIDECAR_FROM_BIDS:
        value = bids.get(bids_name)
        if gbt_name == "SoftwareFilters" and value == "n/a":
            out[gbt_name] = value  # documents that no software filter was applied (BIDS, A-03), not a gap
            continue
        if _missing(value):
            continue
        out[gbt_name] = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
    for gbt_name, bids_names in _JOINED_FROM_BIDS:
        parts = [str(bids[name]) for name in bids_names if not _missing(bids.get(name))]
        if parts:
            out[gbt_name] = " ".join(parts)
    if channel_rows is not None:
        out["ChannelCount"] = channel_rows
    else:
        counts = [
            bids[key]
            for key in _COUNT_KEYS
            if isinstance(bids.get(key), int) and not isinstance(bids.get(key), bool)
        ]
        if counts:
            out["ChannelCount"] = sum(counts)
    for name in REQUIRED_SIDECAR:
        if name not in out:
            result.gap(name)
    return {key: out[key] for key in sorted(out, key=lambda k: (k not in REQUIRED_SIDECAR, k))}


_REFERENCE = re.compile(rb"^(DataFile|MarkerFile)=(.*?)\s*$", re.MULTILINE)


def _copy_brainvision(
    header: Path, target_stem: str, folder: Path
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """The header, data and marker file under the GB/T name, the references in the header and the marker
    file pointing to the new names (plain file names next to the header, A-52)."""
    text = header.read_bytes()
    found = {match.group(1).decode(): match.group(2).decode("latin-1") for match in _REFERENCE.finditer(text)}
    new = {"DataFile": f"{target_stem}.eeg", "MarkerFile": f"{target_stem}.vmrk"}
    sources = {key: header.parent / name for key, name in found.items() if name}
    inputs = (header, *sources.values())
    out_header = folder / f"{target_stem}.vhdr"
    out_header.write_bytes(
        _REFERENCE.sub(lambda m: m.group(1) + b"=" + new[m.group(1).decode()].encode(), text)
    )
    outputs = [out_header]
    if "DataFile" in sources:
        shutil.copyfile(sources["DataFile"], folder / new["DataFile"])
        outputs.append(folder / new["DataFile"])
    if "MarkerFile" in sources:
        marker = sources["MarkerFile"].read_bytes()
        marker = re.sub(
            rb"^DataFile=.*?$", b"DataFile=" + new["DataFile"].encode(), marker, flags=re.MULTILINE
        )
        (folder / new["MarkerFile"]).write_bytes(marker)
        outputs.append(folder / new["MarkerFile"])
    return inputs, tuple(outputs)


def _entities(name: str) -> dict[str, str]:
    return {key: value for key, value in _BIDS_ENTITY.findall(name)}


def _timestamp(scans: Path, relative: str) -> str | None:
    """YYYYMMDD-HHMMSS from the acq_time of scans.tsv (7.5.7.1), else None."""
    columns, rows = _read_rows(scans) if scans.is_file() else ((), ())
    if "filename" not in columns or "acq_time" not in columns:
        return None
    for row in rows:
        if row["filename"].replace("\\", "/") == relative:
            match = re.match(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})", row["acq_time"])
            return "{}{}{}-{}{}{}".format(*match.groups()) if match else None
    return None


def from_bids(bids_root: Path, output: Path, name: str | None = None) -> GbtWriteResult:
    """Write the EEG recordings of a BIDS data set in the GB/T 47127 layout into ``output`` (A-114 ff.).

    Each BIDS recording becomes ``sub-<l>[/ses-<l>]/EEG/sub-<l>[_ses-<l>]_task-<l>[_<timestamp>]_EEG.<ext>``
    with its sidecar (JSON), and per modality folder and task one channel table and one electrode table
    (TSV); event tables keep the signal file name. GB/T has no run or acquisition label: several recordings
    of one task in one session are told apart by the timestamp from scans.tsv; without distinct timestamps
    they are not written (``convert.gbt_runs``). EEGLAB files of a BIDS input are not written
    (``convert.gbt_eeglab``). Nothing is invented: a required value that BIDS does not document is left out
    and counted in ``gaps``.
    """
    result = GbtWriteResult()
    description = _read_json(bids_root / "dataset_description.json")
    candidates: list[tuple[dict[str, str], Path]] = []
    for path in sorted(bids_root.rglob("*")):
        relative = path.relative_to(bids_root)
        if not relative.parts or not relative.parts[0].startswith("sub-") or "eeg" not in relative.parts[:-1]:
            continue
        if is_link(path) or not path.is_file():
            continue
        stem, suffix = _stem_and_suffix(path.name)
        if suffix == ".set" and stem.endswith("_eeg"):
            result.skipped.append((relative.as_posix(), "convert.gbt_eeglab"))
        elif suffix in _BIDS_DATA_SUFFIXES and stem.endswith("_eeg"):
            candidates.append((_entities(stem), path))
    groups: dict[tuple[str, str | None, str], list[tuple[dict[str, str], Path]]] = {}
    for entities, path in candidates:
        groups.setdefault((entities["sub"], entities.get("ses"), entities.get("task", "")), []).append(
            (entities, path)
        )
    subjects: dict[str, set[str | None]] = {}
    tables_done: set[tuple[str, str | None, str]] = set()
    for (sub, ses, task), items in sorted(
        groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "", kv[0][2])
    ):
        stamps: list[str | None] = [None]
        if len(items) > 1:
            level = bids_root / f"sub-{sub}" / (f"ses-{ses}" if ses else "")
            scans = level / (f"sub-{sub}_ses-{ses}_scans.tsv" if ses else f"sub-{sub}_scans.tsv")
            stamps = [_timestamp(scans, path.relative_to(level).as_posix()) for _, path in items]
            if None in stamps or len(set(stamps)) != len(stamps):
                result.skipped += [
                    (path.relative_to(bids_root).as_posix(), "convert.gbt_runs") for _, path in items
                ]
                continue
        folder = output / f"sub-{sub}" / (f"ses-{ses}" if ses else "") / "EEG"
        folder.mkdir(parents=True, exist_ok=True)
        subjects.setdefault(sub, set()).add(ses)
        prefix = f"sub-{sub}" + (f"_ses-{ses}" if ses else "") + f"_task-{task}"
        for (entities, path), stamp in zip(
            items, stamps * len(items) if stamps == [None] else stamps, strict=True
        ):
            stem = path.name[: -len(path.suffix)]
            target_stem = prefix + (f"_{stamp}" if stamp else "") + "_EEG"
            if path.suffix.lower() == ".vhdr":
                inputs, outputs = _copy_brainvision(path, target_stem, folder)
            else:
                target = folder / f"{target_stem}{path.suffix.lower()}"
                shutil.copyfile(path, target)
                inputs, outputs = (path,), (target,)
            channels_source = path.with_name(stem[: -len("_eeg")] + "_channels.tsv")
            channel_rows = len(_read_rows(channels_source)[1]) if channels_source.is_file() else None
            bids_sidecar = _inherited(bids_root, path.parent, entities, "eeg")
            bids_sidecar.update(_read_json(path.with_name(f"{stem}.json")))
            sidecar = _gbt_sidecar(bids_sidecar, channel_rows, result)
            _write_json(folder / f"{target_stem}.json", sidecar)
            outputs += (folder / f"{target_stem}.json",)
            events_source = path.with_name(stem[: -len("_eeg")] + "_events.tsv")
            if events_source.is_file():
                columns, _ = _read_rows(events_source)
                value = "value" if "value" in columns else "trial_type"
                header, rows = _mapped_table(
                    events_source,
                    (("Onset", "onset"), ("Duration", "duration"), ("Value", value)),
                    ("Onset", "Duration", "Value"),
                )
                if any(not row[2] for row in rows) or value not in columns:
                    result.gap("Value")
                _write_table(folder / f"{target_stem}_events.tsv", header, rows)
                outputs += (folder / f"{target_stem}_events.tsv",)
            key = (sub, ses, task)
            if key not in tables_done:
                tables_done.add(key)
                if channels_source.is_file():
                    header, rows = _mapped_table(
                        channels_source, _CHANNELS_FROM_BIDS, REQUIRED_COLUMNS["channels"]
                    )
                    _write_table(folder / f"{prefix}_channels.tsv", header, rows)
                else:
                    result.gap("channels")
                electrodes = sorted(path.parent.glob(f"sub-{sub}*_electrodes.tsv"))
                if electrodes:
                    header, rows = _mapped_table(
                        electrodes[0], _ELECTRODES_FROM_BIDS, REQUIRED_COLUMNS["electrodes"]
                    )
                    if any(not all(row[:4]) for row in rows):
                        result.gap("electrodes")
                    _write_table(folder / f"{prefix}_electrodes.tsv", header, rows)
                else:
                    result.gap("electrodes")
            result.written.append(
                WrittenRecording(
                    source=path.relative_to(bids_root).as_posix(),
                    target=(folder / f"{target_stem}{outputs[0].suffix}").relative_to(output).as_posix(),
                    input_files=inputs,
                    output_files=outputs,
                )
            )
    if result.written:
        title = description.get("Name") if not _missing(description.get("Name")) else name
        out_description: dict[str, Any] = {"Version": FORMAT_VERSION}
        if title:
            out_description = {"Name": title, **out_description}
        else:
            result.gap("Name")
        authors = description.get("Authors")
        if isinstance(authors, list) and authors and all(isinstance(a, str) for a in authors):
            out_description["Author"] = authors
        _write_json(output / "dataset_description.json", out_description)
        _write_participants(bids_root, output, sorted(subjects))
        for sub, sessions in subjects.items():
            if any(sessions):
                _write_sessions(bids_root, output, sub, sorted(s for s in sessions if s))
    return result


def _write_participants(bids_root: Path, output: Path, subjects: list[str]) -> None:
    source = bids_root / "participants.tsv"
    columns, rows = _read_rows(source) if source.is_file() else ((), ())
    by_id = {row.get("participant_id", ""): row for row in rows}
    pairs = [(g, b) for g, b in _PARTICIPANTS_FROM_BIDS if b in columns or g == "ParticipantId"]
    out = []
    for sub in subjects:
        row = by_id.get(f"sub-{sub}", {})
        out.append(
            [
                f"sub-{sub}" if g == "ParticipantId" else ("" if _missing(row.get(b)) else row[b])
                for g, b in pairs
            ]
        )
    _write_table(output / "participants.tsv", [g for g, _ in pairs], out)


def _write_sessions(bids_root: Path, output: Path, sub: str, sessions: list[str]) -> None:
    source = bids_root / f"sub-{sub}" / f"sub-{sub}_sessions.tsv"
    columns, rows = _read_rows(source) if source.is_file() else ((), ())
    times = {row.get("session_id", ""): row.get("acq_time", "") for row in rows}
    header = ["SessionId", *(["AcquisitionTime"] if "acq_time" in columns else [])]
    out = [
        [f"ses-{ses}", *([times.get(f"ses-{ses}", "").replace("n/a", "")] if "acq_time" in columns else [])]
        for ses in sessions
    ]
    _write_table(output / f"sub-{sub}" / "sessions.tsv", header, out)
