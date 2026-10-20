"""Conversion of raw folders to EEG-BIDS (NG-F02, CLI-02, A-04, A-05, A-06, A-52, A-54, A-77; E3 e).

- Raw folders need a mapping of every data file to subject/session/task/run (neurogrid.toml, A-05). Files with
  annotation channels only (hypnograms) are no recordings (A-77): they need no mapping, take no part in the
  duplicate check and are listed as not converted. Without a mapping the run ends with exit 2 and writes a
  template to ``.neurogrid/mapping-template.toml`` in the input folder: never through a link (A-52, A-66),
  via a temporary file that replaces the old one, with every name as a TOML string that parses (A-74).
- Two recordings with the same target (sub/ses/task/run) end with exit 2. Targets are compared without regard
  to case, because sub-A and sub-a are the same folder on Windows and macOS; for the same reason subject or
  session labels that differ only in case end with exit 2 as well, also when the targets differ.
- How a recording is written:
  - MNE-BIDS copies EDF, BDF, BrainVision and EEGLAB files; EDF+D keeps its time structure. MNE-BIDS finds the
    files to copy by editing the data file path as text (".eeg", ".fdt" and ".dat" anywhere in the path,
    ".ds" in a folder name, the name split at its first dot) and reads a BrainVision header with its declared
    code page. Where that would fail, an EDF/BDF file is first linked or copied under a plain name into the
    run's work folder (A-54); BrainVision and EEGLAB recordings (also EEGLAB MAT v7.3, which MNE-BIDS cannot
    copy) are written as BrainVision from the loaded data, like FIF, EEGLAB with embedded data and EEGLAB with
    ``--strip-identifying-headers``.
  - FIF keeps its EEG and auxiliary channels only (MEG has no place in EEG-BIDS). A recording without an EEG
    channel is not converted.
  - Electrode positions of EEGLAB (``chanlocs``) and BrainVision (``[Coordinates]`` of a cap file) may be
    template positions, so they are not written as measured (CapTrak) positions (A-05).
  - ``channels.tsv`` of an EDF/BDF recording takes sampling rate, unit and filter cutoffs per channel from the
    header instead of MNE's values for the whole file (A-04); a value the header does not give is n/a.
- Each recording is converted on its own. If writing it fails, what it wrote is taken back (its files and its
  rows in participants.tsv and scans.tsv), it is listed as not converted, and the run goes on (A-77).
- Required sidecar fields come from the documented metadata (A-04). Fields nobody documented are written as
  "n/a" where BIDS allows it and are listed on the console (M02). MNE-BIDS placeholders are replaced or left
  out; typed recommended fields never get "n/a"; BIDSVersion is the version of the bundled validator schema.
- Identifying header fields stay unchanged unless ``--strip-identifying-headers`` is given (A-05).
- Every converted recording is recorded as a processing step (DM-07). ``input_hash`` and ``output_hash`` cover
  all files of the recording (header, data and marker file, .fdt, FIF split parts): SHA-256 over the sorted
  lines ``<file name>\\t<SHA-256 of the file>\\n`` (the file name as stored, UTF-8). The output is checked
  with the BIDS validator afterwards.
"""

from __future__ import annotations

import codecs
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import warnings
from collections.abc import Callable, Iterable
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import neurogrid
from neurogrid.config import Config
from neurogrid.io import ADAPTERS, ORPHAN_SUFFIXES
from neurogrid.io.base import FormatAdapter
from neurogrid.io.discover import FoundFile, scan
from neurogrid.io.eeglab import epoched as eeglab_epoched
from neurogrid.kernel import canonical
from neurogrid.kernel.errors import InputError, NeuroGridError, UnsafePathError
from neurogrid.kernel.provenance import sha256_file
from neurogrid.kernel.safety import read_limited, resolve_within, work_directory
from neurogrid.metadata import RecordingMetadata, collect, mapped_entities
from neurogrid.model.dataset import ProcessingStep, Recording

BIDS_VERSION = "1.11.1"  # BIDS version of schema 1.2.7 bundled with bids-validator-deno 3.0.2
NA_ALLOWED = frozenset({"EEGReference", "PowerLineFrequency", "SoftwareFilters"})
MNE_TYPES = {
    "EEG": "eeg",
    "EOG": "eog",
    "ECG": "ecg",
    "EMG": "emg",
    "TRIG": "stim",
    "MISC": "misc",
    "RESP": "resp",
}
EEG_BIDS_TYPES = frozenset(MNE_TYPES.values())
TEMPLATE = PurePosixPath(".neurogrid", "mapping-template.toml")
_PLACEHOLDER_NAMES = ("[Unspecified]", "")
# Header issues that concern only text fields; every other issue means the data may be damaged (A-77)
_TEXT_ONLY_ISSUES = frozenset({"header.non_ascii", "header.startdate", "header.edfio_rejected"})
_COPIED = "auto"  # MNE-BIDS copies the files
_BRAINVISION = "BrainVision"  # MNE-BIDS writes the loaded data with pybv
_COMPANIONS = {".vhdr": (".eeg", ".vmrk"), ".set": (".fdt",)}  # further files next to a written data file
_EDF_SUFFIXES = (".edf", ".bdf")
_CUTOFFS = (("low_cutoff", "HP"), ("high_cutoff", "LP"))  # channels.tsv column, EDF prefilter token
# The date field of a 'New Segment' marker: its leading digits are zeroed, whatever follows them (spaces) and
# whatever separates the lines (the adapter splits lines like str.splitlines and strips them, A-77).
_SEGMENT_DATE = re.compile(
    rb"(?<![0-9A-Za-z])(Mk\d+=New Segment,[^,\r\n]*,[^,\r\n]*,[^,\r\n]*,[^,\r\n]*,[ \t]*)(\d+)"
)
_HEADER_CODECS = ("utf-8", "gbk", "latin-1")  # the codecs brainvision._decode chooses from (A-77)


@dataclass
class ConvertedRecording:
    source: FoundFile
    target: str
    missing_fields: list[str]


@dataclass
class ConvertResult:
    output: Path
    converted: list[ConvertedRecording] = field(default_factory=list)
    skipped: list[tuple[FoundFile, str]] = field(default_factory=list)
    steps: list[ProcessingStep] = field(default_factory=list)


class _NotConverted(Exception):
    """A recording that is not converted, with the reason key; raised before anything is written."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _reader(suffix: str) -> Any:
    import mne

    return {
        ".edf": mne.io.read_raw_edf,
        ".bdf": mne.io.read_raw_bdf,
        ".vhdr": mne.io.read_raw_brainvision,
        ".set": mne.io.read_raw_eeglab,
        ".fif": mne.io.read_raw_fif,
    }[suffix]


def annotations_only(recording: Recording | None) -> bool:
    """A file with annotation channels only (e.g. a hypnogram): readable, but no recording (A-74, A-77)."""
    return (
        recording is not None
        and bool(recording.channels)
        and all(ch.type == "ANNOT" for ch in recording.channels)
    )


def read_header(root: Path, item: FoundFile) -> Recording | None:
    """The data model of a raw data file from its header; None if the header cannot be read."""
    try:
        return ADAPTERS[item.suffix].read(
            root.joinpath(*item.relative.parts),
            recording_id=item.display_id,
            relative_path=item.relative.as_posix(),
        )
    except Exception:  # an unreadable header is listed as not converted later
        return None


# --- mapping template --------------------------------------------------------------------------------------


def _toml_string(text: str) -> str:
    """``text`` as a TOML basic string that always parses (A-74).

    Quotes and backslashes are escaped, control characters and DEL as \\uXXXX. A lone surrogate (part of a
    file name that is not valid Unicode) has no TOML form; it appears as the visible text \\uXXXX.
    """
    parts = []
    for char in text:
        code = ord(char)
        if char in '"\\':
            parts.append("\\" + char)
        elif code < 0x20 or code == 0x7F:
            parts.append(f"\\u{code:04X}")
        elif 0xD800 <= code <= 0xDFFF:
            parts.append(f"\\\\u{code:04X}")
        else:
            parts.append(char)
    return '"' + "".join(parts) + '"'


def mapping_template(unmapped: list[FoundFile]) -> bytes:
    """A neurogrid.toml fragment listing the files that still need subject and task (A-05), UTF-8."""
    lines = [
        "# NeuroGrid mapping template (A-05): copy into .neurogrid/neurogrid.toml and fill in the labels.",
        "# Labels are letters and digits only; session and run are optional.",
        "",
    ]
    for item in unmapped:
        name = item.relative.as_posix()
        if any(0xD800 <= ord(char) <= 0xDFFF for char in name):
            lines.append(
                "# This file name is not valid Unicode and cannot be given here; "
                "rename the file or map it with [convert] pattern."
            )
        lines += ["[[convert.files]]", f"path = {_toml_string(name)}", 'subject = ""', 'task = ""', ""]
    return "\n".join(lines).encode("utf-8")


def _replace_file(target: Path, data: bytes) -> None:
    """Write via a temporary file in the same folder that then replaces ``target``: an existing link or
    hard link at ``target`` is replaced, not written through; nothing is left behind on failure (A-54)."""
    handle, name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        temporary.replace(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_mapping_template(root: Path, unmapped: list[FoundFile]) -> Path:
    """Write the mapping template into the input folder (A-05, A-77).

    ``.neurogrid`` and the template are never followed as links or junctions (A-52, A-66). If the template
    cannot be written (no permission, a file or a link in the way), the run still ends with a message that
    the mapping is missing (exit 2), not with an internal error (A-12).
    """
    data = mapping_template(unmapped)
    try:
        target = resolve_within(root, TEMPLATE, must_exist=False)
        target.parent.mkdir(exist_ok=True)
        _replace_file(target, data)
    except (UnsafePathError, OSError):
        raise InputError(
            "convert.mapping_missing_unwritable", count=len(unmapped), template=TEMPLATE.name
        ) from None
    return target


# --- dataset level -----------------------------------------------------------------------------------------


def _refuse_case_collisions(mappings: Iterable[dict[str, str]]) -> None:
    """Subject or session labels that differ only in case (sub-A and sub-a; ses-X and ses-x of one subject)
    are one folder on Windows and macOS, so the output would mix two subjects (A-77). Refused before anything
    is written (exit 2), on every platform, so that the outcome does not depend on the file system."""
    seen: dict[str, str] = {}
    for labels in mappings:
        folders = [f"sub-{labels['subject']}"]
        if labels.get("session"):
            folders.append(f"{folders[0]}/ses-{labels['session']}")
        for folder in folders:
            first = seen.setdefault(folder.casefold(), folder)
            if first != folder:
                raise InputError("convert.label_case", first=first, second=folder)


def _bids_path(output: Path, entities: dict[str, str]) -> Any:
    from mne_bids import BIDSPath

    return BIDSPath(
        subject=entities["subject"],
        session=entities.get("session"),
        task=entities["task"],
        run=entities.get("run"),
        datatype="eeg",
        root=output,
    )


def _clean_sidecar(path: Path, documented: dict[str, Any], missing: list[str]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in list(data):
        if data[key] == "n/a" and key not in NA_ALLOWED:
            del data[key]  # typed recommended fields never get n/a (A-05)
    data.pop("Manufacturer", None)  # MNE-BIDS infers it from the file format, which documents nothing (A-77)
    data.update(documented)
    for key in missing:
        data[key] = "n/a"
    path.write_bytes((json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _description(output: Path, cfg: Config) -> None:
    path = output / "dataset_description.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    data["Name"] = (
        cfg.dataset.name
        or (data.get("Name") if data.get("Name") not in _PLACEHOLDER_NAMES else None)
        or "n/a"  # not documented: reported by convert and by check (M02-02, A-77)
    )
    data["BIDSVersion"] = BIDS_VERSION
    data["DatasetType"] = "raw"
    data.pop("Authors", None)  # MNE-BIDS placeholder; authors are not invented (A-05)
    if cfg.dataset.license:
        data["License"] = cfg.dataset.license
    else:
        data.pop("License", None)
    data["GeneratedBy"] = [{"Name": "NeuroGrid", "Version": neurogrid.__version__}]
    path.write_bytes((json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _readme(output: Path, cfg: Config) -> None:
    heading = f"# {cfg.dataset.name}\n\n" if cfg.dataset.name else ""
    text = f"{heading}EEG data converted to BIDS {BIDS_VERSION} with NeuroGrid {neurogrid.__version__}.\n"
    (output / "README.md").write_bytes(text.encode("utf-8"))
    for candidate in ("README", "README.txt", "README.rst"):
        (output / candidate).unlink(missing_ok=True)


def convert_to_bids(
    root: Path,
    output: Path,
    cfg: Config,
    *,
    only: PurePosixPath | None = None,
    strip_identifying_headers: bool = False,
    work: Callable[[], Path] | None = None,
) -> ConvertResult:
    """Convert the raw folder ``root`` into the BIDS folder ``output``.

    ``work`` gives the run's private work folder (A-54); it is asked for only after the input and the output
    were accepted, so a refused run creates nothing. Without it a temporary folder is used.
    """
    if output.exists() and not output.is_dir():
        raise InputError("output.not_writable")
    found = scan(root, only=only)
    if found.is_bids:
        raise InputError("convert.already_bids")
    if output.exists() and any(output.iterdir()):
        raise InputError("convert.output_not_empty")
    if output.resolve().is_relative_to(root.resolve()):
        raise InputError("convert.output_inside_input")
    headers = {item.relative: read_header(root, item) for item in found.recordings}
    recordings = [item for item in found.recordings if not annotations_only(headers[item.relative])]
    entities = {item.relative: mapped_entities(item, cfg) for item in recordings}
    unmapped = [item for item in recordings if not {"subject", "task"} <= set(entities[item.relative])]
    if unmapped:
        template = write_mapping_template(root, unmapped)
        raise InputError("convert.mapping_missing", count=len(unmapped), template=template.name)
    targets: set[tuple[str, ...]] = set()
    for item in recordings:
        labels = entities[item.relative]
        key = tuple((labels.get(name) or "").casefold() for name in ("subject", "session", "task", "run"))
        if key in targets:
            raise InputError("convert.duplicate_target", subject=labels["subject"], task=labels["task"])
        targets.add(key)
    _refuse_case_collisions(entities[item.relative] for item in recordings)

    with ExitStack() as stack:
        if work is not None:
            folder = work()
        else:
            folder = stack.enter_context(work_directory(Path(tempfile.gettempdir()) / "neurogrid"))
        output.mkdir(parents=True, exist_ok=True)
        result = ConvertResult(output=output)
        for item in found.unsupported:
            orphan = item.suffix in ORPHAN_SUFFIXES  # a .eeg/.fdt no header refers to (A-77)
            result.skipped.append((item, "format.orphan_companion" if orphan else "format.unsupported"))
        for item in found.unreadable:
            result.skipped.append((item, "read.failed"))
        for item in found.recordings:
            header = headers[item.relative]
            if annotations_only(header):
                result.skipped.append((item, "recording.annotations_only"))
                continue
            _convert_one(
                root,
                output,
                item,
                entities[item.relative],
                cfg,
                strip_identifying_headers,
                result,
                header,
                folder,
            )
    if result.converted:
        _description(output, cfg)
        _readme(output, cfg)
    steps_path = output / ".neurogrid" / "processing_steps.json"
    steps_path.parent.mkdir(parents=True, exist_ok=True)
    steps_path.write_bytes(canonical.dumps(result.steps))
    return result


# --- one recording -----------------------------------------------------------------------------------------


class _OutputState:
    """What writing one recording may change in the output, captured before it is written (A-77).

    MNE-BIDS writes dataset-level files (dataset_description.json, participants.tsv/.json) and everything else
    below sub-<label>. A failed recording is taken back: what is new there is removed, and the text files that
    changed (e.g. its rows in participants.tsv and scans.tsv) get their content back, so the output stays as
    valid as it was before.
    """

    def __init__(self, output: Path, subject: str) -> None:
        self.output = output
        self.subject = output / f"sub-{subject}"
        self.top = {child.name for child in output.iterdir()}
        self.below = set(self.subject.rglob("*")) if self.subject.is_dir() else set()
        texts = [child for child in output.iterdir() if child.is_file()]
        texts += [path for path in self.below if path.suffix in (".tsv", ".json") and path.is_file()]
        self.contents = {path: path.read_bytes() for path in texts}

    def restore(self) -> None:
        for child in self.output.iterdir():
            if child.name not in self.top:
                _remove(child)
        if self.subject.is_dir():
            for path in sorted(self.subject.rglob("*"), key=lambda p: len(p.parts)):
                if path not in self.below:
                    _remove(path)
        for path, data in self.contents.items():
            try:
                if not path.is_file() or path.read_bytes() != data:
                    path.write_bytes(data)
            except OSError:
                continue  # best effort; the run goes on and the validator sees the output


def _remove(path: Path) -> None:
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    except OSError:
        return


def _convert_one(
    root: Path,
    output: Path,
    item: FoundFile,
    entities: dict[str, str],
    cfg: Config,
    strip: bool,
    result: ConvertResult,
    header: Recording | None,
    work: Path,
) -> None:
    source = root.joinpath(*item.relative.parts)
    adapter = ADAPTERS[item.suffix]
    if header is None:  # unreadable header: listed, not converted
        result.skipped.append((item, "read.failed"))
        return
    try:
        recording, meta, reason = _prepare(root, item, header, cfg, source, adapter)
    except Exception:  # an input the adapter cannot inspect: listed, not converted
        result.skipped.append((item, "read.failed"))
        return
    if reason is not None:
        result.skipped.append((item, reason))
        return
    state = _OutputState(output, entities["subject"])
    try:
        converted, step = _write(root, output, item, entities, recording, meta, source, strip, work)
    except _NotConverted as exc:
        state.restore()
        result.skipped.append((item, exc.reason))
        return
    except NeuroGridError:
        state.restore()
        raise  # a tool error (e.g. the work folder cannot be written) ends the run with exit 2
    except Exception:  # MNE or MNE-BIDS refused this recording; the others are still converted (A-77)
        state.restore()
        result.skipped.append((item, "convert.failed"))
        return
    result.converted.append(converted)
    result.steps.append(step)


def _prepare(
    root: Path, item: FoundFile, header: Recording, cfg: Config, source: Path, adapter: FormatAdapter
) -> tuple[Recording, RecordingMetadata, str | None]:
    """The merged metadata and the reason not to convert, if any (nothing is written yet)."""
    inspection = adapter.inspect(source)
    recording, meta = collect(root, item, header, cfg, is_bids=False)
    assert recording is not None
    # only recordings without M01-02/M01-03 problems are converted; damaged data are never taken over (A-77)
    if inspection.missing_companions:
        return recording, meta, "convert.companion"
    if set(inspection.issues) - _TEXT_ONLY_ISSUES:
        return recording, meta, "convert.damaged"
    if item.suffix == ".set" and eeglab_epoched(source):
        return recording, meta, "convert.epoched"
    if adapter.read_check(source) is not None:
        return recording, meta, "read.failed"
    return recording, meta, None


def _open_raw(path: Path, item: FoundFile, recording: Recording, meta: RecordingMetadata) -> Any:
    """The recording as an MNE raw object with NeuroGrid's channel types, ready for MNE-BIDS."""
    try:
        raw = _reader(item.suffix)(path, preload=False, verbose="error")
    except Exception:  # MNE refuses the file: listed, not converted
        raise _NotConverted("read.failed") from None
    types = {ch.name: MNE_TYPES[ch.type] for ch in recording.channels if ch.type in MNE_TYPES}
    types = {name: kind for name, kind in types.items() if name in raw.ch_names}
    if types and item.suffix != ".fif":
        raw.set_channel_types(types, verbose="error")
    line = meta.fields.get("PowerLineFrequency")
    raw.info["line_freq"] = float(line.value) if line is not None else None
    if "eeg" not in raw.get_channel_types():
        raise _NotConverted("convert.no_eeg_channels")  # EEG-BIDS (and MNE-BIDS) need an EEG channel
    if item.suffix == ".fif":
        # EEG-BIDS holds EEG and its auxiliary channels; MEG channels of a combined FIF stay out (A-77)
        kinds = zip(raw.ch_names, raw.get_channel_types(), strict=True)
        raw.pick([name for name, kind in kinds if kind in EEG_BIDS_TYPES], verbose="error")
    return raw


def _write(
    root: Path,
    output: Path,
    item: FoundFile,
    entities: dict[str, str],
    recording: Recording,
    meta: RecordingMetadata,
    source: Path,
    strip: bool,
    work: Path,
) -> tuple[ConvertedRecording, ProcessingStep]:
    from mne_bids import write_raw_bids

    with ExitStack() as stack:
        stack.enter_context(warnings.catch_warnings())
        warnings.simplefilter("ignore")
        raw = _open_raw(source, item, recording, meta)
        if item.suffix == ".fif" or (item.suffix == ".set" and (strip or not recording.streamable)):
            write_format = _BRAINVISION  # FIF, and EEGLAB that is stripped or holds its data inside the .set
        elif _copyable(raw, source, item.suffix):
            write_format = _COPIED
        elif item.suffix in _EDF_SUFFIXES:
            staged = _stage(source, item.suffix, work, stack)
            raw = _open_raw(staged, item, recording, meta)
            if _copyable(raw, staged, item.suffix):
                write_format = _COPIED
            elif recording.discontinuous:
                raise _NotConverted("convert.failed")  # EDF+D written as BrainVision would lose its gaps
            else:
                write_format = _BRAINVISION
        else:
            write_format = _BRAINVISION
        if write_format == _BRAINVISION:
            raw.load_data(verbose="error")
        if item.suffix in (".set", ".vhdr"):
            raw.set_montage(None)  # may be template positions; never written as measured CapTrak (A-05)
        if strip:
            raw.set_meas_date(None)
            raw.info["subject_info"] = None
            raw.info["experimenter"] = None
            raw.info["description"] = None
        inputs = _input_files(root, source, item, raw)
        written = write_raw_bids(
            raw,
            _bids_path(output, entities),
            format=write_format,
            allow_preload=write_format == _BRAINVISION,
            overwrite=False,
            readme=False,
            verbose="error",
        )
    sidecar = Path(str(written.copy().update(suffix="eeg", extension=".json").fpath))
    documented: dict[str, Any] = {"TaskName": entities["task"]}
    missing: list[str] = []
    for name in ("EEGReference", "PowerLineFrequency", "SoftwareFilters"):
        value = meta.fields.get(name)
        if value is None:
            missing.append(name)
        else:
            documented[name] = value.value
    _clean_sidecar(sidecar, documented, missing)
    data_file = Path(str(written.fpath))
    if item.suffix in _EDF_SUFFIXES:
        channels = Path(str(written.copy().update(suffix="channels", extension=".tsv").fpath))
        _edf_channels(channels, source, recording, copied=data_file.suffix.lower() in _EDF_SUFFIXES)
    if strip:
        _strip(data_file)
    target = data_file.relative_to(output).as_posix()
    step = ProcessingStep(
        step="convert_to_bids",
        tool="neurogrid",
        version=neurogrid.__version__,
        parameters={
            "input_format": ADAPTERS[item.suffix].format,
            "output_format": data_file.suffix.lstrip(".").upper(),
            "strip_identifying_headers": strip,
            "bids_version": BIDS_VERSION,
            "target": target,
        },
        input_hash=files_hash(inputs),
        output_hash=files_hash(_output_files(data_file)),
    )
    return ConvertedRecording(source=item, target=target, missing_fields=missing), step


# --- can MNE-BIDS copy the files? --------------------------------------------------------------------------


def _copyable(raw: Any, header: Path, suffix: str) -> bool:
    """True if MNE-BIDS 0.20 can copy the recording as it is (write_raw_bids and mne_bids.copyfiles).

    MNE-BIDS finds the header from ``raw.filenames[0]`` (the data file) by replacing ".eeg", ".fdt" and ".dat"
    anywhere in the path and treats a path with ".ds" in a folder name as CTF; it splits the name at the first
    dot and accepts lower-case extensions only. A BrainVision header must name ``<stem>.eeg`` and
    ``<stem>.vmrk`` on lines of their own and decode with its declared code page; an EEGLAB file must be
    MAT v5 (scipy cannot load v7.3).
    """
    name = str(raw.filenames[0])
    if ".ds" in str(Path(name).parent):
        return False
    derived = name.replace(".eeg", ".vhdr").replace(".fdt", ".set").replace(".dat", ".lay")
    stem, _dot, extension = header.name.partition(".")
    if derived != str(Path(name).with_name(header.name)) or not stem or "c,rf" in stem:
        return False
    if f".{extension}" != suffix:
        return False
    if suffix == ".vhdr":
        return _brainvision_copyable(header, stem)
    if suffix == ".set":
        return _mat_v5(header)
    return True


def _brainvision_copyable(vhdr: Path, stem: str) -> bool:
    """MNE-BIDS reads the header with the code page it declares (UTF-8 without one), takes the first
    ``DataFile=``/``MarkerFile=`` entry and rewrites only lines that are exactly ``DataFile=<stem>.eeg`` and
    ``MarkerFile=<stem>.vmrk`` (mne_bids.copyfiles.copyfile_brainvision)."""
    from neurogrid.io.brainvision import MAX_HEADER_BYTES, MAX_MARKER_BYTES

    try:
        data = read_limited(vhdr, MAX_HEADER_BYTES)
        start = data.find(b"Codepage=")
        codec = data[start + 9 :].split()[0].decode() if start != -1 else "UTF-8"
        codecs.lookup(codec)
        lines = io.StringIO(data.decode(codec), newline=None).readlines()
        read_limited(vhdr.with_name(f"{stem}.vmrk"), MAX_MARKER_BYTES).decode(codec)
    except (OSError, LookupError, ValueError, IndexError, InputError):
        return False
    joined = " ".join(lines)
    data_file = re.search(r"DataFile=(.*\.(eeg|dat))", joined)
    marker_file = re.search(r"MarkerFile=(.*\.vmrk)", joined)
    exact = {line.strip() for line in lines}
    return (
        data_file is not None
        and data_file.group(1) == f"{stem}.eeg"
        and marker_file is not None
        and marker_file.group(1) == f"{stem}.vmrk"
        and f"DataFile={stem}.eeg" in exact
        and f"MarkerFile={stem}.vmrk" in exact
    )


def _mat_v5(path: Path) -> bool:
    from scipy.io.matlab import matfile_version

    try:
        major, _minor = matfile_version(str(path), appendmat=False)
    except Exception:  # not a MATLAB file scipy recognises
        return False
    return int(major) in (0, 1)  # 2 is MAT v7.3 (HDF5)


def _stage(source: Path, suffix: str, work: Path, stack: ExitStack) -> Path:
    """A link to (or copy of) an EDF/BDF file under a plain name in the work folder (A-54), so that
    MNE-BIDS reads its path correctly; removed when the recording is written."""
    folder = Path(tempfile.mkdtemp(prefix="stage-", dir=work))
    stack.callback(shutil.rmtree, folder, ignore_errors=True)
    staged = folder / f"recording{suffix}"
    try:
        staged.hardlink_to(source)
    except OSError:  # another volume or a file system without hard links
        shutil.copyfile(source, staged)
    return staged


# --- hashes (DM-07) ----------------------------------------------------------------------------------------


def files_hash(paths: Iterable[Path]) -> str:
    """SHA-256 over the sorted lines "<file name>\\t<SHA-256 of the file>\\n" of all files of a recording."""
    lines = sorted(
        os.fsencode(path.name) + b"\t" + sha256_file(path).encode("ascii") + b"\n" for path in paths
    )
    return hashlib.sha256(b"".join(lines)).hexdigest()


def _input_files(root: Path, source: Path, item: FoundFile, raw: Any) -> list[Path]:
    """The header and every file it uses: BrainVision data and marker file, the .fdt of an EEGLAB data set,
    the parts of a split FIF file (only files inside the dataset)."""
    files = [source]
    if item.suffix == ".vhdr":
        from neurogrid.io.brainvision import BrainVisionAdapter, _reference

        for name in BrainVisionAdapter.companions(source):  # DataFile and MarkerFile as the header names them
            path, problem = _reference(source.parent, name)
            if path is not None and problem is None:
                files.append(path)
    elif item.suffix in (".set", ".fif"):
        inside = root.resolve()
        files += [Path(name) for name in raw.filenames if Path(name).resolve().is_relative_to(inside)]
    return list({path.resolve(): path for path in files}.values())


def _output_files(data_file: Path) -> list[Path]:
    files = [data_file]
    for extension in _COMPANIONS.get(data_file.suffix.lower(), ()):
        companion = data_file.with_suffix(extension)
        if companion.is_file():
            files.append(companion)
    return files


# --- channels.tsv of EDF/BDF (A-04) ------------------------------------------------------------------------


def _edf_texts(path: Path, name: str) -> list[str]:
    """One text field (e.g. "unit", "prefilter") of every signal in an EDF/BDF header (layout of the EDF
    specification). The specification allows ASCII only, but files write "µV" or "°C" in UTF-8 or Latin-1;
    a field is read as UTF-8 if it is valid UTF-8, else as Latin-1 (as MNE reads it), up to a NUL byte."""
    from neurogrid.io.edf import FIXED_HEADER_BYTES, SIGNAL_FIELDS, SIGNAL_HEADER_BYTES

    with path.open("rb") as handle:
        fixed = handle.read(FIXED_HEADER_BYTES)
        count = int(fixed[252:256].decode("ascii").strip())
        block = handle.read(SIGNAL_HEADER_BYTES * count)
    offset = 0
    for field_name, width in SIGNAL_FIELDS:
        if field_name == name:
            break
        offset += width
    width = dict(SIGNAL_FIELDS)[name]
    texts = []
    for index in range(count):
        raw = block[count * offset + index * width :][:width].split(b"\x00")[0]
        try:
            texts.append(raw.decode("utf-8").strip())
        except UnicodeDecodeError:
            texts.append(raw.decode("latin-1").strip())
    return texts


def _cutoff(prefilter: str, token: str) -> str:
    """The high-pass ("HP") or low-pass ("LP") frequency of one signal, read like MNE reads it ("HP:0.1Hz",
    "HP:DC"); n/a if the text gives none."""
    value = ""
    for match in re.findall(rf"{token}:\s*([a-zA-Z0-9,.]+)(Hz)?", prefilter):
        if match[0]:
            value = match[0].replace("Hz", "").replace(",", ".")
    if value == "DC":
        return "0.0" if token == "HP" else "n/a"
    if not value.replace(".", "", 1).isdigit():
        return "n/a"
    number = float(value)
    return "n/a" if token == "LP" and number <= 0 else str(number)


def _unit(text: str) -> str:
    unit = text.strip()
    return {"uV": "µV"}.get(unit, unit) or "n/a"


def _edf_channels(path: Path, source: Path, recording: Recording, *, copied: bool) -> None:
    """channels.tsv of an EDF/BDF recording from its header (A-04).

    MNE gives every channel the highest sampling rate of the file, the highest high-pass and the lowest
    low-pass of all channels, and no unit to non-voltage signals. Each row gets the cutoffs of its own signal
    (n/a if its prefilter text gives none); a copied file also keeps the rate and unit of each signal. Data
    written as BrainVision were resampled by MNE to one rate, so their rates stay as MNE-BIDS wrote them.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    columns = lines[0].split("\t")
    rows = [dict(zip(columns, line.split("\t"), strict=False)) for line in lines[1:] if line]
    prefilters, units = _edf_texts(source, "prefilter"), _edf_texts(source, "unit")
    signals = [
        (channel, prefilters[index], units[index])
        for index, channel in enumerate(recording.channels)
        if channel.type != "ANNOT" and index < min(len(prefilters), len(units))
    ]
    matched = len(signals) == len(rows)  # MNE drops only the annotation signals
    for index, row in enumerate(rows):
        if not matched:
            values = dict.fromkeys(("low_cutoff", "high_cutoff"), "n/a")
            if copied:
                values.update(sampling_frequency="n/a", units="n/a")
        else:
            channel, prefilter, unit = signals[index]
            values = {column: _cutoff(prefilter, token) for column, token in _CUTOFFS}
            if copied:
                rate = channel.sampling_rate_hz
                values["sampling_frequency"] = str(float(rate)) if rate else "n/a"
                values["units"] = _unit(unit)
        row.update({column: value for column, value in values.items() if column in row})
    text = "\n".join(["\t".join(columns), *("\t".join(row.get(c, "n/a") for c in columns) for row in rows)])
    path.write_bytes((text + "\n").encode("utf-8"))


# --- --strip-identifying-headers (E3 e, A-05, A-77) --------------------------------------------------------


def _strip(data_file: Path) -> None:
    """Replace identifying header fields of the written file by placeholders (E3 e, A-05)."""
    suffix = data_file.suffix.lower()
    if suffix in _EDF_SUFFIXES:
        _strip_edf(data_file)
    elif suffix == ".vhdr":
        _strip_brainvision(data_file)


def _strip_edf(path: Path) -> None:
    with path.open("r+b") as handle:
        fixed = bytearray(handle.read(256))
        plus = fixed[192:197] in (b"EDF+C", b"EDF+D", b"BDF+C", b"BDF+D")
        fixed[8:88] = b"X X X X".ljust(80)
        fixed[88:168] = (b"Startdate X X X X" if plus else b"X").ljust(80)
        fixed[168:176] = b"01.01.85"
        handle.seek(0)
        handle.write(bytes(fixed))


def _strip_brainvision(vhdr: Path) -> None:
    """Keep only the impedance block of the header comment and zero the date of the 'New Segment' marker.

    The written files are changed as bytes: lines are dropped and date digits replaced by zeros; nothing else
    is decoded and encoded again, so the Codepage line stays true (A-77).
    """
    from neurogrid.io.brainvision import parse_vhdr

    keep = parse_vhdr(vhdr).impedance_lines
    vhdr.write_bytes(_without_comment(vhdr.read_bytes(), keep))
    marker = vhdr.with_suffix(".vmrk")
    if marker.is_file():
        data = marker.read_bytes()
        marker.write_bytes(_SEGMENT_DATE.sub(lambda match: match.group(1) + b"0" * len(match.group(2)), data))


def _header_codec(data: bytes) -> str:
    """The codec the BrainVision adapter reads this header with (brainvision._decode, A-77)."""
    from neurogrid.io.brainvision import _decode

    text = _decode(data)
    for codec in _HEADER_CODECS:
        try:
            if data.decode(codec) == text:
                return codec
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _without_comment(data: bytes, keep: set[int]) -> bytes:
    """The header without the lines of its [Comment] section, except the lines ``keep``, counted the way
    brainvision.parse_vhdr counts them. The lines are cut out of the bytes. If the decoded text does not map
    back to the bytes, no comment line is kept."""
    codec = _header_codec(data)
    pieces = data.decode(codec).splitlines(keepends=True)
    chunks = [piece.encode(codec) for piece in pieces]
    if b"".join(chunks) != data:
        chunks = data.splitlines(keepends=True)
        pieces = [chunk.decode("latin-1") for chunk in chunks]
        keep = set()
    out: list[bytes] = []
    in_comment = False
    index = 0
    for piece, chunk in zip(pieces, chunks, strict=True):
        stripped = piece.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_comment = stripped[1:-1] == "Comment"
            out.append(chunk)
        elif in_comment:
            if index in keep:
                out.append(chunk)
            index += 1
        else:
            out.append(chunk)
    return b"".join(out)


def remove_output(output: Path, *, keep_folder: bool = False) -> None:
    """Remove a partly written output after a failure (A-54).

    With ``keep_folder`` the folder stays and only its contents go: it existed and was empty before the run.
    """
    if not keep_folder:
        shutil.rmtree(output, ignore_errors=True)
        return
    for child in output.iterdir() if output.is_dir() else ():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
