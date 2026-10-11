"""Dataset discovery: walk the folder, classify files, detect BIDS (A-03, A-12, A-51, A-52).

Links are never followed. Hidden entries (``.neurogrid`` and other dot files) are skipped. In BIDS
datasets the folders ``derivatives``, ``sourcedata``, ``code`` and ``stimuli`` hold no raw data and are
skipped. Folder formats (EGI MFF, MEF3) count as one unsupported recording and are not entered.
Raw (non-BIDS) folders get pseudonymous recording IDs unless ``show_paths`` is set (D-10 f).
Folders that cannot be listed and data files that cannot be opened are collected as ``unreadable``; they
become M01 findings instead of silently missing (A-12).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from neurogrid.io import ADAPTERS, KNOWN_UNSUPPORTED, KNOWN_UNSUPPORTED_DIRS
from neurogrid.kernel.safety import is_link

BIDS_SKIP_DIRS = frozenset({"derivatives", "sourcedata", "code", "stimuli"})
MAX_DESCRIPTION_BYTES = 1_000_000
DESCRIPTION_LIMITS = {"Name": 200, "License": 80, "BIDSVersion": 40, "DatasetType": 40}
_BIDS_ENTITY = re.compile(r"(?:^|_)(sub|ses|task|run)-([A-Za-z0-9]+)(?=_|$)")
# A-51 hint: names that may identify a person – non-ASCII letters or six or more digits in a row.
_SUSPICIOUS_NAME = re.compile(r"[^\x00-\x7f]|\d{6,}")


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
        """Pseudonymous IDs get the extension (A-70); real names are shown exactly as stored."""
        if self.display_id == pseudonym(self.relative):
            return f"{self.display_id}{self.suffix}"
        return self.display_id

    @property
    def identity(self) -> tuple[str, ...]:
        """Stable names for exception matching and finding keys, independent of --show-paths.

        Relative path, pseudonymous ID and pseudonymous file name (ID plus extension, as shown in raw
        folders); A-09, A-14, A-68.
        """
        pseudo = pseudonym(self.relative)
        return (_printable(self.relative.as_posix()), pseudo, f"{pseudo}{self.suffix}")

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
    links_skipped: int = 0
    subjects: int | None = None
    suspicious_names: int = 0

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


def _folder_size(path: Path) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not is_link(current / d)]
        for name in filenames:
            child = current / name
            if not is_link(child):
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

    def add_file(self, path: Path, relative: PurePosixPath, siblings: frozenset[str]) -> None:
        # Windows cannot open names ending in a dot or space; classify them by the name without that end
        suffix = PurePosixPath(path.name.rstrip(" .") or path.name).suffix.lower()
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
        if suffix in ADAPTERS:
            self.result.recordings.append(item)
        elif suffix in KNOWN_UNSUPPORTED and not _is_brainvision_companion(path, siblings):
            self.result.unsupported.append(item)
        else:
            self.result.other.append(item)

    def add_folder_format(self, path: Path, relative: PurePosixPath) -> None:
        self.result.unsupported.append(self.found(relative, path.suffix.lower(), _folder_size(path)))

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
                result.links_skipped += 1
                continue
            if Path(name).suffix.lower() in KNOWN_UNSUPPORTED_DIRS:
                collect.add_folder_format(path, PurePosixPath(path.relative_to(root).as_posix()))
                continue
            kept_dirs.append(name)
        dirnames[:] = kept_dirs
        siblings = frozenset(name.lower() for name in filenames)
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            path = current / name
            if is_link(path):
                result.links_skipped += 1
                continue
            collect.add_file(path, PurePosixPath(path.relative_to(root).as_posix()), siblings)
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


def _is_brainvision_companion(path: Path, siblings: frozenset[str]) -> bool:
    """A ``.eeg`` next to a ``.vhdr`` of the same stem belongs to BrainVision, not to an unknown format.

    Compared without regard to case on every platform, so the result does not depend on the file system.
    """
    return path.suffix.lower() == ".eeg" and f"{path.stem.lower()}.vhdr" in siblings
