"""Dataset discovery: walk the folder, classify files, detect BIDS (A-03, A-12, A-51, A-52, A-66).

Links are never followed, opened or parsed; they are counted, and their relative paths are kept for this run
only (``DatasetScan.skipped_links``, so that the BIDS check can drop what the validator found behind them).
Hidden entries (``.neurogrid`` and other dot files) are skipped. In BIDS
datasets the folders ``derivatives``, ``sourcedata``, ``code`` and ``stimuli`` hold no raw data and are
skipped. Folder formats (EGI MFF, MEF3) count as one unsupported recording and are not entered.
Raw (non-BIDS) folders get pseudonymous recording IDs unless ``show_paths`` is set (D-10 f).
Folders that cannot be listed and data files that cannot be opened are collected as ``unreadable``; they
become M01 findings instead of silently missing (A-12).

Companion files belong to a recording and are not recordings themselves: the data and marker files a
BrainVision header names, the .fdt next to an EEGLAB .set of the same name or named in its header, FIF split
parts. MEG calibration files in BIDS (acq-crosstalk, acq-calibration) are no recordings either. Only regular
files take part: a linked or hidden header claims no companion, so a regular .eeg/.fdt next to it is an
orphan. The .eeg named by an unsupported BrainVision ASCII header (.ahdr) is its companion, not an orphan.
A header never claims a recording or a data file of another format, whatever its references name (A-12).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from neurogrid.io import ADAPTERS, KNOWN_UNSUPPORTED, KNOWN_UNSUPPORTED_DIRS, ORPHAN_SUFFIXES
from neurogrid.io.brainvision import BrainVisionAdapter
from neurogrid.io.eeglab import referenced_fdt
from neurogrid.io.identifying import display_text
from neurogrid.kernel.safety import is_link

BIDS_SKIP_DIRS = frozenset({"derivatives", "sourcedata", "code", "stimuli"})
MAX_DESCRIPTION_BYTES = 1_000_000
DESCRIPTION_LIMITS = {"Name": 200, "License": 80, "BIDSVersion": 40, "DatasetType": 40}
_BIDS_ENTITY = re.compile(r"(?:^|_)(sub|ses|task|run)-([A-Za-z0-9]+)(?=_|$)")
# A-51 hint: names that may identify a person – non-ASCII letters or six or more digits in a row.
_SUSPICIOUS_NAME = re.compile(r"[^\x00-\x7f]|\d{6,}")
_FIF_SPLIT = re.compile(r"^(?P<base>.+)-(?P<part>[1-9]\d*)\.fif$", re.IGNORECASE)
_BIDS_SPLIT = re.compile(r"_split-(?P<part>\d+)_", re.IGNORECASE)
_BIDS_MEG_CALIBRATION = re.compile(r"_acq-(crosstalk|calibration)_meg\.(fif|dat)$", re.IGNORECASE)
_COMPOUND_SUFFIXES = tuple(sorted(s for s in KNOWN_UNSUPPORTED if s.count(".") > 1))  # e.g. .fif.gz
# Extensions NeuroGrid classifies (A-70, A-74): its formats, the ones it knows but cannot read, the orphan
# companions, the text and document files of datasets and of its own outputs, and their gzip parts.
_DOCUMENT_SUFFIXES = frozenset(
    {".tsv", ".json", ".txt", ".yaml", ".toml", ".md", ".pdf", ".html", ".csv", ".zip", ".gz"}
)
_CLASSIFIED = frozenset(
    {*ADAPTERS, *KNOWN_UNSUPPORTED, *ORPHAN_SUFFIXES, *KNOWN_UNSUPPORTED_DIRS, *_DOCUMENT_SUFFIXES}
)
SHOWN_EXTENSIONS = _CLASSIFIED | {s + ".gz" for s in _CLASSIFIED if s.count(".") == 1 and s != ".gz"}
_SHOWN_PART = re.compile(r"[A-Za-z][A-Za-z0-9]{0,9}")


def _suffix(name: str) -> str:
    """Lower-case extension that classifies a file: a two-part one such as ``.fif.gz`` (A-74), or the last."""
    lower = name.lower()
    for compound in _COMPOUND_SUFFIXES:
        if lower.endswith(compound) and len(lower) > len(compound):
            return compound
    return PurePosixPath(lower).suffix


def shown_extension(suffix: str) -> str:
    """The classifying extension ``suffix`` (``_suffix``) as it may appear next to a pseudonym, else '' (A-51,
    A-70): one NeuroGrid classifies (SHOWN_EXTENSIONS), or one whose every dot-part is a short ASCII word
    (a letter, then at most nine letters or digits) that the display rule shows (display_text, C5). Digit
    runs, dates, years and clock times written as an extension ('born.19610312', 'born 12.03.1961', 'lights
    off 22.31') and letters outside ASCII never appear. The one rule of every pseudonymous file name
    (io.provenance.shown_suffix)."""
    if suffix in SHOWN_EXTENSIONS:
        return suffix
    head, *parts = suffix.split(".")
    if head or not parts:
        return ""
    if all(_SHOWN_PART.fullmatch(part) and display_text(part).shown is not None for part in parts):
        return suffix
    return ""


def _claimable(name: str) -> bool:
    """A header may claim a data or marker file as its companion, never a recording or a data file of another
    format: a DataFile/MarkerFile (or EEGLAB data field) naming one must not hide it from the check (A-12)."""
    suffix = _suffix(name)
    return suffix in ORPHAN_SUFFIXES or (suffix not in ADAPTERS and suffix not in KNOWN_UNSUPPORTED)


def pseudonym(relative: PurePosixPath) -> str:
    """``rec-<sha256(relative path)[:8]>`` over the original name bytes (A-51)."""
    return "rec-" + hashlib.sha256(os.fsencode(relative.as_posix())).hexdigest()[:8]


def _printable(text: str) -> str:
    """Names that are not valid Unicode (undecodable bytes) are shown with escapes instead of failing."""
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


@dataclass(frozen=True)
class FoundFile:
    relative: PurePosixPath
    display_id: str
    suffix: str
    size_bytes: int
    entities: tuple[tuple[str, str], ...] = ()

    @property
    def display_file(self) -> str:
        """Pseudonymous IDs get the extension as shown_extension allows it (A-51, A-70); real names are shown
        exactly as stored."""
        if self.display_id == pseudonym(self.relative):
            return f"{self.display_id}{shown_extension(self.suffix)}"
        return self.display_id

    @property
    def identity(self) -> tuple[str, ...]:
        """Stable names for exception matching and finding keys, independent of --show-paths.

        Relative path, pseudonymous ID and pseudonymous file name (ID plus extension, as shown in raw
        folders); A-09, A-14, A-68.
        """
        pseudo = pseudonym(self.relative)
        return (_printable(self.relative.as_posix()), pseudo, f"{pseudo}{shown_extension(self.suffix)}")

    def entity(self, name: str) -> str | None:
        return dict(self.entities).get(name)


@dataclass
class DatasetScan:
    root: Path
    is_bids: bool
    description: dict[str, str] = field(default_factory=dict)
    recordings: list[FoundFile] = field(default_factory=list)
    unsupported: list[FoundFile] = field(default_factory=list)
    other: list[FoundFile] = field(default_factory=list)
    unreadable: list[FoundFile] = field(default_factory=list)
    # Relative paths of the links and junctions that were not followed (A-66). Internal to the run: they are
    # never printed or written to results (A-51); outputs carry only their number.
    skipped_links: list[PurePosixPath] = field(default_factory=list)
    subjects: int | None = None
    suspicious_names: int = 0
    # A single file as target (A-66): its folder was not walked, so the dataset is not validated as a whole.
    single_file: bool = False

    @property
    def links_skipped(self) -> int:
        return len(self.skipped_links)

    @property
    def total_bytes(self) -> int:
        return sum(f.size_bytes for f in (*self.recordings, *self.unsupported, *self.other))


def _description(path: Path) -> dict[str, str]:
    """The few fields NeuroGrid shows, length-limited and without control characters (A-53)."""
    try:
        if is_link(path) or path.stat().st_size > MAX_DESCRIPTION_BYTES:
            return {}
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, RecursionError):
        return {}
    if not isinstance(data, dict):
        return {}
    kept: dict[str, str] = {}
    for key, limit in DESCRIPTION_LIMITS.items():
        value = data.get(key)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            text = "".join(ch for ch in str(value) if ch.isprintable()).strip()
            kept[key] = text[:limit]
    return kept


def _entities(relative: PurePosixPath, is_bids: bool) -> tuple[tuple[str, str], ...]:
    if not is_bids:
        return ()  # raw folders need the mapping from neurogrid.toml (A-05, P2)
    return tuple(_BIDS_ENTITY.findall(relative.name))


def _relative(path: Path, root: Path) -> PurePosixPath:
    return PurePosixPath(path.relative_to(root).as_posix())


def _folder_size(path: Path, root: Path, links: list[PurePosixPath]) -> int:
    """Size of a folder format without following links; the links inside are added to ``links``.

    The BIDS validator does enter such folders, so their links must be known like any other (A-66). Links in
    hidden entries are not counted, as everywhere else (the validator does not look there either).
    """
    total = 0
    for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
        current = Path(dirpath)
        hidden = any(part.startswith(".") for part in current.relative_to(path).parts)
        kept = []
        for name in sorted(dirnames):
            if is_link(current / name):
                if not (hidden or name.startswith(".")):
                    links.append(_relative(current / name, root))
            else:
                kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            child = current / name
            if is_link(child):
                if not (hidden or name.startswith(".")):
                    links.append(_relative(child, root))
                continue
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


class _Collector:
    def __init__(self, result: DatasetScan, show_paths: bool) -> None:
        self.result = result
        self.show_paths = show_paths

    def found(self, relative: PurePosixPath, suffix: str, size: int) -> FoundFile:
        plain = self.result.is_bids or self.show_paths
        display = _printable(relative.as_posix()) if plain else pseudonym(relative)
        return FoundFile(
            relative=relative,
            display_id=display,
            suffix=suffix,
            size_bytes=size,
            entities=_entities(relative, self.result.is_bids),
        )

    def add_file(self, path: Path, relative: PurePosixPath, companions: frozenset[str]) -> None:
        # Windows cannot open names ending in a dot or space; classify them by the name without that end
        suffix = _suffix(path.name.rstrip(" .") or path.name)
        data_file = suffix in ADAPTERS or suffix in KNOWN_UNSUPPORTED
        try:
            size = path.stat().st_size
        except OSError:  # e.g. a name Windows cannot open (trailing dot or space), or a race
            if data_file:
                self.result.unreadable.append(self.found(relative, suffix, 0))
            else:
                self.result.other.append(self.found(relative, suffix, 0))
            return
        item = self.found(relative, suffix, size)
        if path.name.lower() in companions or (
            self.result.is_bids and _BIDS_MEG_CALIBRATION.search(path.name)
        ):
            self.result.other.append(item)
        elif suffix in ADAPTERS:
            self.result.recordings.append(item)
        elif suffix in KNOWN_UNSUPPORTED:
            self.result.unsupported.append(item)
        else:
            self.result.other.append(item)

    def add_folder_format(self, path: Path, relative: PurePosixPath) -> None:
        size = _folder_size(path, self.result.root, self.result.skipped_links)
        self.result.unsupported.append(self.found(relative, path.suffix.lower(), size))

    def add_link(self, path: Path) -> None:
        self.result.skipped_links.append(_relative(path, self.result.root))

    def add_unlistable(self, relative: PurePosixPath) -> None:
        self.result.unreadable.append(self.found(relative, "", 0))


def scan(root: Path, *, show_paths: bool = False, only: PurePosixPath | None = None) -> DatasetScan:
    root = root.resolve(strict=True)
    description_path = root / "dataset_description.json"
    is_bids = os.path.lexists(description_path)
    result = DatasetScan(
        root=root, is_bids=is_bids, description=_description(description_path) if is_bids else {}
    )
    collect = _Collector(result, show_paths)
    if only is not None:
        # A single file given on the command line: no walk through the rest of its folder.
        result.single_file = True
        path = root.joinpath(*only.parts)
        collect.add_file(path, only, frozenset())
        _finish(result)
        return result

    def unlistable(error: OSError) -> None:
        where = Path(error.filename) if error.filename else root
        try:
            relative = PurePosixPath(where.relative_to(root).as_posix())
        except ValueError:
            relative = PurePosixPath()
        collect.add_unlistable(relative)

    for dirpath, dirnames, filenames in os.walk(root, onerror=unlistable, followlinks=False):
        current = Path(dirpath)
        kept_dirs = []
        for name in sorted(dirnames):
            if name.startswith("."):
                continue
            if is_bids and current == root and name in BIDS_SKIP_DIRS:
                continue
            path = current / name
            if is_link(path):
                collect.add_link(path)
                continue
            if Path(name).suffix.lower() in KNOWN_UNSUPPORTED_DIRS:
                collect.add_folder_format(path, _relative(path, root))
                continue
            kept_dirs.append(name)
        dirnames[:] = kept_dirs
        # Links and hidden files are sorted out first: only regular files are opened, also for companions.
        regular = []
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            if is_link(current / name):
                collect.add_link(current / name)
                continue
            regular.append(name)
        companions = _companions(current, regular)
        for name in regular:
            path = current / name
            collect.add_file(path, _relative(path, root), companions)
    result.unreadable.sort(key=lambda f: f.relative.as_posix())
    _finish(result)
    return result


def _finish(result: DatasetScan) -> None:
    data_files = (*result.recordings, *result.unsupported)
    result.suspicious_names = sum(
        1 for f in data_files if any(_SUSPICIOUS_NAME.search(part) for part in f.relative.parts)
    )
    if result.is_bids:
        result.subjects = len({f.entity("sub") for f in data_files if f.entity("sub")})


def _companions(folder: Path, filenames: list[str]) -> frozenset[str]:
    """Lower-case names of the files in ``folder`` that belong to a recording in the same folder.

    ``filenames`` are regular files only (no links, no hidden files): headers among them are opened.
    Compared without regard to case on every platform, so the result does not depend on the file system.
    A name a header refers to is claimed only if it is no recording or other data file (``_claimable``).
    """
    names = {name.lower(): name for name in filenames}
    found: set[str] = set()
    for lower, name in names.items():
        stem, _, extension = lower.rpartition(".")
        if extension in ("vhdr", "ahdr"):  # .ahdr: same header format, unsupported (A-74), data is no orphan
            referenced = BrainVisionAdapter.companions(folder / name)
            plain = (ref.replace("\\", "/").rsplit("/", 1)[-1].lower() for ref in referenced)
            found.update(ref for ref in plain if _claimable(ref))
            found.update({f"{stem}.eeg", f"{stem}.vmrk"})  # also when the header cannot be read
        elif extension == "set":
            found.add(f"{stem}.fdt")
        elif extension == "fif":
            split = _FIF_SPLIT.match(lower)
            if split and f"{split.group('base')}.fif" in names:
                found.add(lower)
            bids = _BIDS_SPLIT.search(lower)
            if bids and int(bids.group("part")) > 1:
                first = _BIDS_SPLIT.sub(f"_split-{'0' * (len(bids.group('part')) - 1)}1_", lower)
                if first in names:
                    found.add(lower)
    if any(lower.endswith(".fdt") and lower not in found for lower in names):
        # a .fdt with another stem: read the .set headers only in this rare case (they may embed data)
        for lower, name in names.items():
            if lower.endswith(".set"):
                fdt_name = referenced_fdt(folder / name)
                if fdt_name and _claimable(fdt_name):
                    found.add(fdt_name)
    return frozenset(found & set(names))
