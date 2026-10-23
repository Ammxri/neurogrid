"""Annotations of a dataset (M10; NG-F08, DM-05, A-04, A-17, A-53, A-80): one reader per format, the one
events.tsv reader, and the attachment of annotation-only files to the signal recordings they belong to.

Sources (``Annotation.source``):

- ``edf_tal``: the time-stamped annotation lists (TAL) of EDF+/BDF+, annotation-only files (hypnograms)
  included. Every annotation signal is read data record by data record (complete records only); empty
  annotation texts, among them the time-keeping entry that opens each record, are skipped; a missing
  duration is 0; onsets are recording time, also in EDF+D, whose record onsets give the data intervals.
  Texts are UTF-8, undecodable bytes replaced; a channel link "text@@channel" (the convention MNE reads;
  PSG-IPA links "Lights off" to channels) is not part of the code. A TAL that does not follow the grammar
  (onset with sign, optional duration after 0x15, texts each ended by 0x14) makes the file unreadable.
  Plain EDF/BDF has no annotations.
- ``vmrk``: the [Marker Infos] of the BrainVision MarkerFile, read only as a plain file name next to the
  header (A-52, A-77; M01-03 reports any other). Every ``Mk<n>=`` line of every [Marker Infos] section
  (whatever the case of its header) is a marker, whatever the number of digits of n (as MNE reads them).
  code = "type/description" (MNE's convention, an escaped comma read as a comma), onset = (position − 1) /
  rate, duration = size / rate.
- ``eeglab_event``: EEG.event through the guarded EEGLAB loaders (A-77): code = type (a number as its
  canonical text, "2"), onset = (latency − 1) / srate, duration = duration / srate. A missing, empty or NaN
  duration is 0 (EEGLAB's convention for an event without duration). An event without a latency (empty,
  NaN or no number, which EEGLAB ignores) is no annotation, as in MNE, but it is counted as invalid like an
  events.tsv row without a valid onset (never a silent drop, A-80); an infinite latency or duration makes
  the source unreadable. Epoched data sets are marked (M10 compares them in events mode only).
- ``fif_annotations``: raw.annotations of a FIF file whose split chain is safe (A-77), onsets relative to the
  first sample (MNE's onset minus ``first_time``, with or without an origin time). read_raw_fif fits the
  stored annotations to the recorded data: one that lies wholly outside it is left out by MNE and counted
  as invalid here (the file's own annotations compared with raw.annotations; never a silent drop, A-80),
  one that reaches beyond it is cut by MNE.
- ``events_tsv``: the nearest BIDS events.tsv (inheritance principle), UTF-8 with or without BOM (ds000248
  starts with one). A cell holds no value when it is empty or n/a in any case (io.bids.no_value, the rule of
  participants.tsv; M10 and M11 alike). code = trial_type if the column exists, else value; a row without
  code is no annotation; a row whose onset or duration is no number, whose duration is negative or whose
  times are not valid (see Limits) is no annotation either and is counted as invalid; duration n/a = 0;
  annotator from the column ``annotator`` (A-04), else "default"; labels are the events.json "Levels"
  descriptions of the code column, whose keys are the vocabulary (A-80, critic X11).

Structural markers are never annotations (fixed list, documented, not configurable, A-80): the EDF+
time-keeping entry, BrainVision "New Segment", EEGLAB "boundary", MNE "BAD_ACQ_SKIP" and "EDGE boundary".

In BIDS datasets events.tsv replaces the annotations inside the data file (MNE-BIDS writes the same markers to
both; no merge). Annotation-only files are no recordings for other checks (A-74, C10): they are attached to a
signal recording by [[annotation.files]] (dataset-relative paths, critic X12) or, as fallback, by their stem:
'<stem of a signal recording>_<annotator>' (the longest such stem wins; on a tie the one in the same folder,
then the one with the nearest common folder). A file that is still ambiguous or matches no recording is an M10
object of its own with the annotator "default"; an attached file without any annotation is still its
annotator (an empty track). ``[annotation] annotators`` (patterns, kernel.glob) restricts which annotators
take part; the patterns are compared with the annotator IDs (events.tsv column,
``[[annotation.files]].annotator`` or the stem rest), not with file names; the others are counted only.

Limits (A-53): at most MAX_ANNOTATIONS per source and per object, texts cut at MAX_TEXT_BYTES. Onset, duration
and end of every annotation must be finite and lie within MAX_ANNOTATION_TIME_S (10^9 s, about 31.7 years)
of the recording start (``valid_times``), EDF+D record onsets as well. An events.tsv row that breaks this is
counted as invalid, and so are an EEGLAB event without a latency and a FIF annotation MNE leaves out
(``AnnotationList.invalid``; one notice for all of them, notice.events_rows_invalid); in the other formats
an annotation with times that are not valid makes the source unreadable, like any other damaged content
(never a silent drop). An EDF header whose size field is smaller than its fixed and signal headers makes the
annotations unreadable. A source that cannot be read gives AnnotationsUnreadable with a reason key; dataset
data never end a run with exit 2 (A-12, C2). Raw annotation texts and annotator IDs never leave the process
unfiltered: outputs use io.identifying.display_text and annotator_pseudonym (A-17, A-51, C5).
"""

from __future__ import annotations

import math
import re
import warnings
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from functools import cached_property
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

import numpy as np

from neurogrid.io.base import HeaderUnreadable
from neurogrid.io.bids import MAX_TSV_BYTES, applicable, merged_json, no_value
from neurogrid.io.brainvision import MAX_MARKER_BYTES, _decode, _reference, _sections, parse_vhdr
from neurogrid.io.channels import ANNOTATION_LABELS
from neurogrid.io.discover import FoundFile
from neurogrid.io.edf import FIXED_HEADER_BYTES, SIGNAL_HEADER_BYTES, parse_header
from neurogrid.io.eeglab import _number, _trials, load_events
from neurogrid.io.fif import _raw, _unsafe_split
from neurogrid.kernel import glob
from neurogrid.kernel.errors import InputError
from neurogrid.kernel.safety import read_limited
from neurogrid.model.dataset import Annotation, Recording

SOURCE_EDF = "edf_tal"
SOURCE_VMRK = "vmrk"
SOURCE_EEGLAB = "eeglab_event"
SOURCE_FIF = "fif_annotations"
SOURCE_EVENTS = "events_tsv"
SOURCE_FILE = "annotation_file"  # an annotation-only file attached to a signal recording
DEFAULT_ANNOTATOR = "default"
MAX_ANNOTATIONS = 1_000_000
MAX_TEXT_BYTES = 1024
MAX_ANNOTATION_TIME_S = 1e9  # A-53: annotation times beyond 10^9 s (about 31.7 years) are no annotation
UNREADABLE = "annotation.unreadable"
TOO_MANY = "annotation.too_many"
NEW_SEGMENT = "New Segment"
EEGLAB_STRUCTURAL = frozenset({"boundary"})
FIF_STRUCTURAL = frozenset({"BAD_ACQ_SKIP", "EDGE boundary"})
# One TAL without its closing NUL: onset, optional duration (bounded digits: always a finite float), texts.
_TAL = re.compile(rb"([+-]\d{1,20}(?:\.\d{0,20})?)(?:\x15(\d{1,20}(?:\.\d{0,20})?))?\x14(.*)\x14", re.DOTALL)
_CHANNEL_LINK = b"@@"  # "text@@channel" links an EDF+ annotation to a channel (MNE); the link is no code
_MARKER = re.compile(r"^Mk\d+=(.*)$")  # every marker number, as MNE reads them
_RECORD_CHUNK = 4096  # data records read at a time from the memory map
_EDF_SUFFIXES = (".edf", ".bdf")


class AnnotationsUnreadable(Exception):
    """An annotation source could not be read; ``reason`` is a stable key (reason.annotation.*)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class AnnotationList:
    """What one reader found in one file. ``data_intervals`` and ``end_s`` describe EDF+D record times;
    ``invalid`` counts the entries that are no annotation because they have no valid time (EEGLAB events
    without a latency, FIF annotations MNE leaves out), reported like invalid events.tsv rows."""

    annotations: tuple[Annotation, ...]
    source: str
    data_intervals: tuple[tuple[float, float], ...] | None = None
    end_s: float | None = None
    epoched: bool = False
    invalid: int = 0


def _text(raw: bytes) -> str:
    return raw[:MAX_TEXT_BYTES].decode("utf-8", "replace").strip()


def _checked(annotations: list[Annotation]) -> None:
    if len(annotations) > MAX_ANNOTATIONS:
        raise AnnotationsUnreadable(TOO_MANY)


def valid_times(onset: float, duration: float) -> bool:
    """A-53: onset, duration and end are finite and the annotation lies within MAX_ANNOTATION_TIME_S of the
    recording start (onset not before -MAX_ANNOTATION_TIME_S, end not after MAX_ANNOTATION_TIME_S). Every
    later computation (epoch grid, interval lengths and their sums) then stays finite."""
    end = onset + duration
    return (
        math.isfinite(onset)
        and math.isfinite(duration)
        and math.isfinite(end)
        and onset >= -MAX_ANNOTATION_TIME_S
        and end <= MAX_ANNOTATION_TIME_S
    )


def _merge(intervals: Iterable[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


# --- EDF+/BDF+ ----------------------------------------------------------------------------------------------


def read_edf_tal(path: Path) -> AnnotationList:
    """The TAL annotations of an EDF+/BDF+ file (see the module text); plain EDF/BDF gives none."""
    try:
        header = parse_header(path)
    except (HeaderUnreadable, OSError):
        raise AnnotationsUnreadable(UNREADABLE) from None
    if header.plus is None:
        return AnnotationList((), SOURCE_EDF)
    signals = [i for i, s in enumerate(header.signals) if s.label.strip().upper() in ANNOTATION_LABELS]
    if not signals:
        return AnnotationList((), SOURCE_EDF)
    bps = 3 if header.variant == "BDF" else 2
    spr = [s.samples_per_record for s in header.signals]
    smallest = FIXED_HEADER_BYTES + SIGNAL_HEADER_BYTES * len(header.signals)
    if header.header_bytes is None or header.header_bytes < smallest or any(n is None or n <= 0 for n in spr):
        raise AnnotationsUnreadable(UNREADABLE)  # also a size field below the header itself, e.g. -1
    counts = [n for n in spr if n is not None]
    record_bytes = sum(counts) * bps
    try:
        size = path.stat().st_size
    except OSError:
        raise AnnotationsUnreadable(UNREADABLE) from None
    available = max(0, (size - header.header_bytes) // record_bytes)
    declared = header.n_records if header.n_records is not None and header.n_records >= 0 else available
    records = min(available, declared)
    offsets = [sum(counts[:i]) * bps for i in range(len(counts))]
    annotations: list[Annotation] = []
    onsets: list[float] = []
    if records:
        try:
            mapped = np.memmap(
                path, dtype=np.uint8, mode="r", offset=header.header_bytes, shape=(records, record_bytes)
            )
        except (OSError, ValueError, OverflowError):
            raise AnnotationsUnreadable(UNREADABLE) from None
        try:
            for first in range(0, records, _RECORD_CHUNK):
                blocks = [  # copies: no view of the map outlives it
                    np.array(mapped[first : first + _RECORD_CHUNK, offsets[i] : offsets[i] + counts[i] * bps])
                    for i in signals
                ]
                for row in range(blocks[0].shape[0]):
                    for number, block in enumerate(blocks):
                        onset = _parse_record(block[row].tobytes(), annotations)
                        if number == 0:
                            onsets.append(math.nan if onset is None else onset)
                    _checked(annotations)
        finally:
            del mapped
    if header.plus != "D":
        return AnnotationList(tuple(annotations), SOURCE_EDF)
    duration = header.record_duration_s
    if not duration or not all(valid_times(onset, duration) for onset in onsets):
        raise AnnotationsUnreadable(UNREADABLE)  # EDF+D needs a valid time-keeping onset for every record
    intervals = _merge((onset, onset + duration) for onset in onsets)
    return AnnotationList(
        tuple(annotations),
        SOURCE_EDF,
        data_intervals=intervals,
        end_s=intervals[-1][1] if intervals else None,
    )


def _parse_record(raw: bytes, out: list[Annotation]) -> float | None:
    """Append the annotations of one record's annotation signal; return the onset of its first TAL if that
    TAL opens with the empty time-keeping entry (EDF+ specification), else None."""
    keeping: float | None = None
    first = True
    for chunk in raw.split(b"\x00"):
        if not chunk:
            continue
        match = _TAL.fullmatch(chunk)
        if match is None:
            raise AnnotationsUnreadable(UNREADABLE)
        onset = float(match.group(1))
        duration = float(match.group(2)) if match.group(2) else 0.0
        texts = match.group(3).split(b"\x14")
        if first and texts[0] == b"":
            keeping = onset
        first = False
        for raw_text in texts:
            text = _text(raw_text.split(_CHANNEL_LINK, 1)[0])
            if text:
                if not valid_times(onset, duration):
                    raise AnnotationsUnreadable(UNREADABLE)
                out.append(Annotation(onset_s=onset, duration_s=duration, code=text, source=SOURCE_EDF))
    return keeping


# --- BrainVision --------------------------------------------------------------------------------------------


def read_vmrk(path: Path) -> AnnotationList:
    """The markers of the MarkerFile a .vhdr names (see the module text)."""
    try:
        header = parse_vhdr(path)
    except (HeaderUnreadable, OSError):
        raise AnnotationsUnreadable(UNREADABLE) from None
    interval = header.interval_us
    marker, problem = _reference(path.parent, header.value("MarkerFile"))
    if interval is None or marker is None or problem is not None:
        raise AnnotationsUnreadable(UNREADABLE)
    rate = Fraction(1_000_000) / interval
    try:
        text = _decode(read_limited(marker, MAX_MARKER_BYTES))
    except (OSError, InputError):
        raise AnnotationsUnreadable(UNREADABLE) from None
    markers = [  # every [Marker Infos] section, whatever its case: none of its markers is left out
        line for name, lines in _sections(text).items() if name.casefold() == "marker infos" for line in lines
    ]
    annotations: list[Annotation] = []
    for line in markers:
        match = _MARKER.match(line.strip())
        if match is None:
            continue  # comments and other lines (MNE reads only Mk<n>= lines as well)
        fields = match.group(1).split(",")
        if len(fields) < 4:
            raise AnnotationsUnreadable(UNREADABLE)
        kind, description = (part.replace("\\1", ",") for part in fields[:2])
        position, size = fields[2].strip(), fields[3].strip()
        if not position.isdecimal() or len(position) > 15:
            raise AnnotationsUnreadable(UNREADABLE)
        if kind.strip() == NEW_SEGMENT:
            continue
        samples = int(size) if size.isdecimal() and len(size) <= 15 else 0  # MNE: anything else is 0
        code = _text(f"{kind}/{description}".encode())
        onset, duration = float((int(position) - 1) / rate), float(samples / rate)
        if not valid_times(onset, duration):
            raise AnnotationsUnreadable(UNREADABLE)
        annotations.append(Annotation(onset_s=onset, duration_s=duration, code=code, source=SOURCE_VMRK))
        _checked(annotations)
    return AnnotationList(tuple(annotations), SOURCE_VMRK)


# --- EEGLAB -------------------------------------------------------------------------------------------------


def _event_rows(event: Any) -> list[Mapping[str, Any]]:
    """EEG.event as pymatreader gives it: a dict of lists, a dict of scalars (one event), a list of dicts, or
    an empty array (no events)."""
    if isinstance(event, Mapping):
        columns = {key: value for key, value in event.items() if isinstance(key, str)}
        lists = [value for value in columns.values() if isinstance(value, (list, tuple))]
        if not lists:
            return [columns]
        count = max(len(value) for value in lists)
        return [
            {
                key: (value[index] if index < len(value) else None)
                if isinstance(value, (list, tuple))
                else value
                for key, value in columns.items()
            }
            for index in range(count)
        ]
    if isinstance(event, (list, tuple)):
        return [row for row in event if isinstance(row, Mapping)]
    return []


def _type_text(value: Any) -> str:
    """The event type as text: a string as it is, a number as its canonical text ("2", "2.5")."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return str(int(value))
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return ""
        return str(int(value)) if float(value).is_integer() else format(value, "g")
    if isinstance(value, (list, tuple)):
        return " ".join(part for part in (_type_text(item) for item in value) if part)
    return ""


def _infinite(value: Any) -> bool:
    """A number that is plus or minus infinity (NaN and empty fields are no value: no latency, duration 0)."""
    try:
        return math.isinf(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def read_eeglab_events(path: Path) -> AnnotationList:
    """EEG.event of an EEGLAB data set (see the module text)."""
    try:
        eeg = load_events(path)
    except (HeaderUnreadable, OSError):
        raise AnnotationsUnreadable(UNREADABLE) from None
    rate = _number(eeg.get("srate"))
    epochs = _trials(eeg)
    if rate is None or rate <= 0:
        raise AnnotationsUnreadable(UNREADABLE)
    rows = _event_rows(eeg.get("event"))
    if len(rows) > MAX_ANNOTATIONS:
        raise AnnotationsUnreadable(TOO_MANY)
    annotations: list[Annotation] = []
    invalid = 0
    for row in rows:
        code = _text(_type_text(row.get("type")).encode("utf-8", "surrogatepass"))
        if not code or code in EEGLAB_STRUCTURAL:
            continue
        if _infinite(row.get("latency")) or _infinite(row.get("duration")):
            raise AnnotationsUnreadable(UNREADABLE)  # A-53: an infinite time is damage, not a missing value
        latency = _number(row.get("latency"))
        if latency is None:  # empty or NaN (EEGLAB ignores the event, MNE drops it): counted, not dropped
            invalid += 1
            continue
        samples = _number(row.get("duration"))  # empty or NaN: no duration, 0 (EEGLAB)
        duration = samples / rate if samples is not None and samples > 0 else 0.0
        onset = (latency - 1) / rate  # overflows for a huge latency and a sampling rate far below 1 Hz
        if not valid_times(onset, duration):
            raise AnnotationsUnreadable(UNREADABLE)
        annotations.append(Annotation(onset_s=onset, duration_s=duration, code=code, source=SOURCE_EEGLAB))
    epoched = epochs is not None and epochs > 1
    return AnnotationList(tuple(annotations), SOURCE_EEGLAB, epoched=epoched, invalid=invalid)


# --- FIF ----------------------------------------------------------------------------------------------------


def _fif_code(description: Any) -> str | None:
    """The code of a FIF annotation; None for an empty description and the structural markers."""
    code = _text(str(description).encode("utf-8", "surrogatepass"))
    return None if not code or code in FIF_STRUCTURAL else code


def _stored_fif_count(path: Path) -> int:
    """The number of annotations with a code that the FIF file itself stores (its first part, the one MNE
    takes them from), before read_raw_fif fits them to the recorded data; 0 if it stores none or they cannot
    be read again (then nothing is compared)."""
    import mne

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            stored = mne.read_annotations(path)  # no annotation block: OSError
        return sum(1 for description in stored.description if _fif_code(description) is not None)
    except Exception:  # only the outcome counts
        return 0


def read_fif_annotations(path: Path) -> AnnotationList:
    """raw.annotations of a FIF file; nothing is read when MNE would follow an unsafe split part (A-52).
    read_raw_fif leaves out every annotation that lies wholly outside the recorded data; these are counted as
    invalid (``AnnotationList.invalid``), never dropped without a trace (A-80)."""
    try:
        if _unsafe_split(path):
            raise AnnotationsUnreadable(UNREADABLE)
        raw = _raw(path)
        stored = raw.annotations
        # MNE keeps onsets with first_time included, with and without orig_time (set_annotations adds it when
        # orig_time is None): relative to the first sample an onset is onset - first_time
        shift = float(raw.first_time)
        entries = list(zip(stored.onset, stored.duration, stored.description, strict=True))
    except AnnotationsUnreadable:
        raise
    except Exception:  # MNE raises many types for damaged files; only the outcome counts
        raise AnnotationsUnreadable(UNREADABLE) from None
    if len(entries) > MAX_ANNOTATIONS:
        raise AnnotationsUnreadable(TOO_MANY)
    annotations: list[Annotation] = []
    for onset, duration, description in entries:
        code = _fif_code(description)
        if code is None:
            continue
        onset_s, duration_s = float(onset) - shift, float(duration)
        if not math.isfinite(duration_s) or not valid_times(onset_s, max(duration_s, 0.0)):
            raise AnnotationsUnreadable(UNREADABLE)
        annotations.append(
            Annotation(onset_s=onset_s, duration_s=max(duration_s, 0.0), code=code, source=SOURCE_FIF)
        )
    outside = max(0, _stored_fif_count(path) - len(annotations))  # MNE's crop to the recorded data
    return AnnotationList(tuple(annotations), SOURCE_FIF, invalid=outside)


# --- BIDS events.tsv ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EventsTable:
    """The nearest events.tsv of a data file: column names and cells with outer whitespace removed, short rows
    padded. One header rule for every reader of events (M10 and M11, critic G10): ``column`` finds a column
    without regard to outer whitespace and case."""

    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def column(self, name: str) -> int | None:
        wanted = name.strip().casefold()
        return next((i for i, column in enumerate(self.columns) if column.casefold() == wanted), None)

    def values(self, name: str) -> list[str] | None:
        """The cells of a column, cells without a value (empty, n/a in any case) left out; None if the column
        does not exist."""
        index = self.column(name)
        if index is None:
            return None
        return [row[index] for row in self.rows if not no_value(row[index])]


def read_events(root: Path, data_file: PurePosixPath) -> EventsTable | None:
    """The events.tsv that applies to ``data_file`` (the nearest one, inheritance principle), or None.

    UTF-8 with or without BOM; larger than MAX_TSV_BYTES, not UTF-8, or more rows than MAX_ANNOTATIONS:
    AnnotationsUnreadable (dataset data: a finding, never exit 2, C2).
    """
    files = applicable(root, data_file, "events", ".tsv")
    if not files:
        return None
    try:
        text = read_limited(files[-1], MAX_TSV_BYTES).decode("utf-8-sig")
    except (OSError, InputError, UnicodeDecodeError):
        raise AnnotationsUnreadable(UNREADABLE) from None
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return EventsTable((), ())
    if len(lines) - 1 > MAX_ANNOTATIONS:
        raise AnnotationsUnreadable(TOO_MANY)
    columns = tuple(cell.strip() for cell in lines[0].split("\t"))
    rows = []
    for line in lines[1:]:
        cells = [cell.strip() for cell in line.split("\t")][: len(columns)]
        rows.append(tuple(cells + [""] * (len(columns) - len(cells))))
    return EventsTable(columns, tuple(rows))


def events_levels(root: Path, data_file: PurePosixPath, column: str) -> dict[str, str] | None:
    """code -> description from the "Levels" of ``column`` in the merged events.json sidecars, or None."""
    merged, _found = merged_json(root, data_file, "events")
    entry = merged.get(column)
    levels = entry.get("Levels") if isinstance(entry, Mapping) else None
    if not isinstance(levels, Mapping):
        return None
    out: dict[str, str] = {}
    for key, description in levels.items():
        if isinstance(description, Mapping):  # newer BIDS: {"Description": ..., "TermURL": ...}
            description = description.get("Description")
        out[str(key).strip()] = description.strip() if isinstance(description, str) else ""
    return out


@dataclass(frozen=True)
class EventsAnnotations:
    annotations: tuple[Annotation, ...]
    vocabulary: tuple[str, ...] | None
    labels: tuple[tuple[str, str], ...]
    invalid_rows: int


def _cell_number(cell: str) -> float | None:
    try:
        value = float(cell)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def events_annotations(root: Path, data_file: PurePosixPath, table: EventsTable) -> EventsAnnotations:
    """Annotations of an events.tsv (see the module text), with the vocabulary and labels of its sidecar."""
    onset = table.column("onset")
    duration = table.column("duration")
    code_name = "trial_type" if table.column("trial_type") is not None else "value"
    code = table.column(code_name)
    annotator = table.column("annotator")
    if onset is None or code is None:
        return EventsAnnotations((), None, (), len(table.rows) if onset is None else 0)
    levels = events_levels(root, data_file, table.columns[code])
    annotations: list[Annotation] = []
    invalid = 0
    for row in table.rows:
        text = _text(row[code].encode("utf-8", "surrogatepass"))
        if no_value(text):
            continue  # a row without code is no annotation (e.g. only a HED string)
        start = _cell_number(row[onset])
        length = 0.0 if duration is None or no_value(row[duration]) else _cell_number(row[duration])
        if start is None or length is None or length < 0 or not valid_times(start, length):
            invalid += 1  # e.g. onset and duration 1e308: each finite, but not their end (A-53)
            continue
        who = row[annotator] if annotator is not None and not no_value(row[annotator]) else DEFAULT_ANNOTATOR
        annotations.append(
            Annotation(
                onset_s=start,
                duration_s=length,
                code=text,
                label=(levels or {}).get(text) or None,
                annotator_id=who,
                source=SOURCE_EVENTS,
            )
        )
    vocabulary = tuple(sorted(levels)) if levels else None
    labels = tuple(sorted((key, value) for key, value in (levels or {}).items() if value))
    return EventsAnnotations(tuple(annotations), vocabulary, labels, invalid)


# --- attachment and the index of a dataset ------------------------------------------------------------------


class SourceRecording(Protocol):
    """What the index needs of a discovered recording (checks.context.RecordingState provides it)."""

    @property
    def found(self) -> FoundFile: ...

    @property
    def path(self) -> Path: ...

    @property
    def recording(self) -> Recording | None: ...

    @property
    def annotations_only(self) -> bool: ...


class FileAssignment(Protocol):
    """One row of [[annotation.files]] (config.AnnotationFile)."""

    @property
    def path(self) -> str: ...

    @property
    def recording(self) -> str: ...

    @property
    def annotator(self) -> str | None: ...


@dataclass(frozen=True)
class Track:
    """The annotations of one annotator for one object; ``annotator`` is the raw ID (never printed as is)."""

    annotator: str
    annotations: tuple[Annotation, ...]
    source: str
    file: FoundFile


@dataclass(frozen=True)
class AnnotatedRecording:
    """One M10 object: a signal recording with every annotation attached to it, or an annotation-only file
    that could not be attached (``unassigned``). ``tracks`` hold the annotators the ``[annotation]
    annotators`` patterns let through, sorted by ID; an attached annotation-only file without any annotation
    is an empty track, and a track may hold zero-duration markers only (checks.annotation decides what each
    track takes part in, A-80). ``issue`` is the reason key when a source could not be read (then the object
    is not checkable)."""

    found: FoundFile
    duration_s: float | None
    tracks: tuple[Track, ...] = ()
    excluded_annotators: int = 0
    attached: tuple[FoundFile, ...] = ()
    issue: str | None = None
    epoched: bool = False
    vocabulary: tuple[str, ...] | None = None  # events.json Levels of the code column
    labels: tuple[tuple[str, str], ...] = ()  # (code, label) from the same Levels
    data_intervals: tuple[tuple[float, float], ...] | None = None  # EDF+D record times
    unassigned: bool = False
    invalid_rows: int = 0  # events.tsv rows, EEGLAB events and FIF annotations without valid times

    @cached_property
    def annotations(self) -> tuple[Annotation, ...]:
        """All annotations of the annotators that take part, in time order (sorted once)."""
        return tuple(sorted((a for t in self.tracks for a in t.annotations), key=_order))


@dataclass(frozen=True)
class AnnotationIndex:
    """The M10 objects of a dataset (sorted by relative path) and what could not be attached."""

    objects: tuple[AnnotatedRecording, ...] = ()
    unassigned: int = 0  # annotation-only files that match no signal recording
    ambiguous: int = 0  # annotation-only files that match several equally well
    unmatched_rows: int = 0  # [[annotation.files]] rows that name no annotation-only file or no recording
    invalid_rows: int = 0  # events.tsv rows, EEGLAB events and FIF annotations without valid times

    def by_recording(self) -> dict[PurePosixPath, tuple[Annotation, ...]]:
        """Relative path of each object -> its annotations (all annotators that take part, time order); the
        source for ``[ai] labels = "annotations"`` (A-81). Unassigned annotation-only files are keyed by
        their own path."""
        return {obj.found.relative: obj.annotations for obj in self.objects}


def _order(annotation: Annotation) -> tuple[float, float, str, str]:
    return (annotation.onset_s, annotation.duration_s, annotation.code, annotation.annotator_id or "")


@dataclass
class _Attachment:
    recording: SourceRecording
    files: list[tuple[SourceRecording, str]] = field(default_factory=list)


def _stem(found: FoundFile) -> str:
    return found.relative.stem


def _common_depth(a: PurePosixPath, b: PurePosixPath) -> int:
    depth = 0
    for left, right in zip(a.parts, b.parts, strict=False):
        if left != right:
            break
        depth += 1
    return depth


def _candidates(
    annotation_file: SourceRecording, signals: Sequence[SourceRecording]
) -> list[SourceRecording]:
    """Signal recordings whose stem plus '_' starts the stem of ``annotation_file``, after the tie-breaks of
    the module text."""
    stem = _stem(annotation_file.found)
    found = [
        s for s in signals if stem.startswith(_stem(s.found) + "_") and len(stem) > len(_stem(s.found)) + 1
    ]
    if len(found) <= 1:
        return found
    longest = max(len(_stem(s.found)) for s in found)
    found = [s for s in found if len(_stem(s.found)) == longest]
    folder = annotation_file.found.relative.parent
    same = [s for s in found if s.found.relative.parent == folder]
    if same:
        found = same
    if len(found) > 1:
        best = max(_common_depth(s.found.relative.parent, folder) for s in found)
        found = [s for s in found if _common_depth(s.found.relative.parent, folder) == best]
    return found


def _annotator_from_stem(annotation_file: SourceRecording, recording: SourceRecording) -> str:
    stem, prefix = _stem(annotation_file.found), _stem(recording.found) + "_"
    return stem[len(prefix) :] if stem.startswith(prefix) and len(stem) > len(prefix) else stem


def _normalised(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).as_posix()


def _in_file(path: Path, suffix: str) -> AnnotationList:
    if suffix in _EDF_SUFFIXES:
        return read_edf_tal(path)
    if suffix == ".vhdr":
        return read_vmrk(path)
    if suffix == ".set":
        return read_eeglab_events(path)
    if suffix == ".fif":
        return read_fif_annotations(path)
    return AnnotationList((), "")


def _tracks(
    annotations: Iterable[Annotation], source: str, file: FoundFile, default: str, recording_id: str
) -> Iterator[Track]:
    groups: dict[str, list[Annotation]] = {}
    for annotation in annotations:
        who = annotation.annotator_id or default
        groups.setdefault(who, []).append(
            annotation.model_copy(update={"annotator_id": who, "recording_id": recording_id})
        )
    for who in sorted(groups):
        yield Track(who, tuple(sorted(groups[who], key=_order)), source, file)


def _included(tracks: Iterable[Track], annotators: Sequence[str] | None) -> tuple[tuple[Track, ...], int]:
    """Tracks merged per annotator ID, and the number of annotators the patterns leave out."""
    merged: dict[str, Track] = {}
    for track in tracks:
        if track.annotator in merged:
            first = merged[track.annotator]
            joined = tuple(sorted((*first.annotations, *track.annotations), key=_order))
            merged[track.annotator] = Track(first.annotator, joined, first.source, first.file)
        else:
            merged[track.annotator] = track
    kept = [
        merged[who]
        for who in sorted(merged)
        if annotators is None or any(glob.match(pattern, who) for pattern in annotators)
    ]
    return tuple(kept), len(merged) - len(kept)


def _duration(recording: Recording | None) -> float | None:
    if recording is None or recording.duration_s is None:
        return None
    value = recording.duration_s
    return value if math.isfinite(value) and value > 0 else None


def _signal_object(
    root: Path,
    signal: SourceRecording,
    attached: Sequence[tuple[SourceRecording, str]],
    *,
    is_bids: bool,
    annotators: Sequence[str] | None,
) -> AnnotatedRecording:
    found = signal.found
    files = tuple(item.found for item, _who in attached)
    if signal.recording is None:  # the header could not be read: nothing reliable to compare (M01 reports it)
        return AnnotatedRecording(found=found, duration_s=None, attached=files, issue="header.unreadable")
    issue: str | None = None
    tracks: list[Track] = []
    vocabulary: tuple[str, ...] | None = None
    labels: tuple[tuple[str, str], ...] = ()
    invalid = 0
    table: EventsTable | None = None
    if is_bids:
        try:
            table = read_events(root, found.relative)
        except AnnotationsUnreadable as exc:
            issue = exc.reason
    in_file: AnnotationList | None = None
    needs_file = table is None and issue is None
    if needs_file or signal.recording.discontinuous or found.suffix == ".set":
        try:
            in_file = _in_file(signal.path, found.suffix)
        except AnnotationsUnreadable as exc:
            if needs_file:
                issue = exc.reason
    if table is not None:
        events = events_annotations(root, found.relative, table)
        tracks.extend(_tracks(events.annotations, SOURCE_EVENTS, found, DEFAULT_ANNOTATOR, found.display_id))
        vocabulary, labels, invalid = events.vocabulary, events.labels, events.invalid_rows
    elif in_file is not None and issue is None:
        tracks.extend(
            _tracks(in_file.annotations, in_file.source, found, DEFAULT_ANNOTATOR, found.display_id)
        )
        invalid = in_file.invalid
    for item, who in attached:
        try:
            extra = read_edf_tal(item.path)
        except AnnotationsUnreadable as exc:
            issue = issue or exc.reason
            continue
        if extra.annotations:
            tracks.extend(_tracks(extra.annotations, SOURCE_FILE, item.found, who, found.display_id))
        else:  # one file per annotator (A-80): a file without annotation is its annotator all the same
            tracks.append(Track(who, (), SOURCE_FILE, item.found))
    kept, excluded = _included(tracks, annotators)
    if issue is None and sum(len(t.annotations) for t in kept) > MAX_ANNOTATIONS:
        issue = TOO_MANY
    duration = _duration(signal.recording)
    if in_file is not None and in_file.end_s is not None:
        duration = in_file.end_s  # EDF+D: the recording time reaches to the end of the last record
    return AnnotatedRecording(
        found=found,
        duration_s=duration,
        tracks=() if issue else kept,
        excluded_annotators=excluded,
        attached=files,
        issue=issue,
        epoched=in_file.epoched if in_file is not None else False,
        vocabulary=vocabulary,
        labels=labels,
        data_intervals=in_file.data_intervals if in_file is not None else None,
        invalid_rows=invalid,
    )


def _own_object(item: SourceRecording, annotators: Sequence[str] | None) -> AnnotatedRecording:
    """An annotation-only file that could not be attached: an object of its own, annotator "default"."""
    found = item.found
    try:
        listed = read_edf_tal(item.path)
    except AnnotationsUnreadable as exc:
        return AnnotatedRecording(found=found, duration_s=None, issue=exc.reason, unassigned=True)
    tracks = _tracks(listed.annotations, SOURCE_EDF, found, DEFAULT_ANNOTATOR, found.display_id)
    kept, excluded = _included(tracks, annotators)
    return AnnotatedRecording(
        found=found, duration_s=None, tracks=kept, excluded_annotators=excluded, unassigned=True
    )


def build_index(
    root: Path,
    recordings: Sequence[SourceRecording],
    *,
    is_bids: bool,
    files: Sequence[FileAssignment] = (),
    annotators: Sequence[str] | None = None,
) -> AnnotationIndex:
    """Read the annotations of every signal recording and attach the annotation-only files (module text)."""
    ordered = sorted(recordings, key=lambda r: r.found.relative.as_posix())
    signals = [r for r in ordered if not r.annotations_only]
    by_path = {r.found.relative.as_posix(): _Attachment(r) for r in signals}
    rows: dict[str, FileAssignment] = {}
    for entry in files:
        rows.setdefault(_normalised(entry.path), entry)
    used_rows: set[str] = set()
    own: list[SourceRecording] = []
    unassigned = ambiguous = 0
    for item in (r for r in ordered if r.annotations_only):
        relative = item.found.relative.as_posix()
        row = rows.get(relative)
        target = by_path.get(_normalised(row.recording)) if row is not None else None
        if row is not None and target is not None:
            used_rows.add(relative)
            who = row.annotator or _annotator_from_stem(item, target.recording)
        else:
            candidates = _candidates(item, signals)
            if len(candidates) != 1:
                own.append(item)
                if candidates:
                    ambiguous += 1
                else:
                    unassigned += 1
                continue
            target = by_path[candidates[0].found.relative.as_posix()]
            who = _annotator_from_stem(item, target.recording)
        target.files.append((item, who))
    objects = [
        _signal_object(root, entry.recording, entry.files, is_bids=is_bids, annotators=annotators)
        for entry in by_path.values()
    ]
    objects += [_own_object(item, annotators) for item in own]
    objects.sort(key=lambda obj: obj.found.relative.as_posix())
    return AnnotationIndex(
        objects=tuple(objects),
        unassigned=unassigned,
        ambiguous=ambiguous,
        unmatched_rows=len(rows) - len(used_rows),
        invalid_rows=sum(obj.invalid_rows for obj in objects),
    )
