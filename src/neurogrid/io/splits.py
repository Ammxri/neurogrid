"""The split control file ``splits.tsv`` (KONZEPT 2.5, A-04, A-21, A-52, A-53, A-81; decision C2).

Location: ``[ai] splits`` (relative to the project root, A-66; a configured file that does not exist ends the
run with exit 2), else ``<dataset>/.neurogrid/splits.tsv`` if it exists. Links are never followed (A-52).

Format: UTF-8 (with or without byte order mark), tab-separated, a header with the columns ``recording`` and
``split`` (matched without surrounding space and without regard to case), one row per recording and split.
``split`` is train, val or test (DM-06; no synonyms). ``recording`` is the dataset-relative path of the data
file or its pseudonymous ID ``rec-<sha8>``, with or without the extension (A-51, A-70). A recording may
appear with several splits; split integrity (CORE-M12-01) reports that.

splits.tsv is a file the user writes as configuration (C2): a missing column, an unknown split value, an
empty cell, an unsafe path, a file that is too large, has too many rows or is no UTF-8 text end the run with
exit 2. Messages name the line, never the cell text (A-51). Rows that match no recording are counted, never
shown.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from neurogrid.io.discover import FoundFile
from neurogrid.io.participants import SPLIT_NAMES, canonical
from neurogrid.kernel.errors import ConfigError, InputError, UnsafePathError
from neurogrid.kernel.safety import check_relative, is_link, read_limited, resolve_within

CONTROL_DIR = ".neurogrid"
SPLITS_FILE = "splits.tsv"
MAX_SPLITS_BYTES = 10_000_000
MAX_SPLITS_ROWS = 100_000
_PSEUDONYM = re.compile(r"^rec-[0-9a-f]{8}(?:\.[A-Za-z0-9]{1,16})?$")


@dataclass(frozen=True)
class SplitRow:
    line: int  # line number in the file (1 = header)
    recording: str  # a relative POSIX path, or a pseudonymous ID with a lower-case extension if any
    split: str


@dataclass(frozen=True)
class SplitFile:
    path: Path
    outside_dataset: bool  # [ai] splits may name a file outside the dataset (A-81: info notice)


def locate(dataset_root: Path, project_root: Path | None, configured: str | None) -> SplitFile | None:
    """The splits file of the run, or None if there is none."""
    root = dataset_root.resolve()
    if configured is not None:
        relative = check_relative(configured)  # already checked when the configuration was read (A-66)
        try:
            path = resolve_within(project_root or root, relative)
        except FileNotFoundError:
            raise ConfigError("config.splits_not_found", field="ai.splits") from None
        except UnsafePathError:
            raise UnsafePathError("splits.link") from None
        return SplitFile(path=path, outside_dataset=not path.is_relative_to(root))
    if not os.path.lexists(root / CONTROL_DIR / SPLITS_FILE) and not is_link(root / CONTROL_DIR):
        return None
    try:
        path = resolve_within(root, PurePosixPath(CONTROL_DIR, SPLITS_FILE), must_exist=False)
    except UnsafePathError:
        raise UnsafePathError("splits.link") from None
    if not os.path.lexists(path):
        return None
    return SplitFile(path=path, outside_dataset=False)


def _recording(raw: str, line: int) -> str:
    if _PSEUDONYM.fullmatch(raw):
        stem, dot, extension = raw.partition(".")
        return f"{stem}{dot}{extension.lower()}"
    try:
        return check_relative(raw).as_posix()
    except UnsafePathError:
        raise InputError("splits.unsafe_path", line=line) from None


def parse_splits(data: bytes) -> list[SplitRow]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputError("splits.encoding") from None
    lines = text.splitlines()
    header_line = next((index for index, line in enumerate(lines) if line.strip()), None)
    if header_line is None:
        raise InputError("splits.columns")
    header = [canonical(name) for name in lines[header_line].split("\t")]
    if header.count("recording") != 1 or header.count("split") != 1:
        raise InputError("splits.columns")
    recording_at, split_at = header.index("recording"), header.index("split")
    rows: list[SplitRow] = []
    for index in range(header_line + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        number = index + 1
        if len(rows) >= MAX_SPLITS_ROWS:
            raise InputError("splits.too_many_rows", limit=MAX_SPLITS_ROWS)
        cells = line.split("\t")
        if max(recording_at, split_at) >= len(cells):
            raise InputError("splits.invalid_row", line=number)
        raw_recording, raw_split = cells[recording_at].strip(), cells[split_at].strip()
        if not raw_recording or not raw_split:
            raise InputError("splits.invalid_row", line=number)
        split = raw_split.casefold()
        if split not in SPLIT_NAMES:
            raise InputError("splits.invalid_split", line=number)
        rows.append(SplitRow(line=number, recording=_recording(raw_recording, number), split=split))
    return rows


def read_splits(path: Path) -> list[SplitRow]:
    if is_link(path):
        raise UnsafePathError("splits.link")
    if not path.is_file():
        raise InputError("splits.not_a_file")
    try:
        data = read_limited(path, MAX_SPLITS_BYTES)
    except InputError:
        raise InputError("splits.too_large", limit=MAX_SPLITS_BYTES) from None
    except OSError:
        raise InputError("splits.unreadable") from None
    return parse_splits(data)


def assign(rows: Iterable[SplitRow], found: Iterable[FoundFile]) -> tuple[dict[str, set[str]], int]:
    """Splits per recording (by relative POSIX path) and the number of rows that match no recording.

    A row matches a recording by its relative path or by its pseudonymous ID with or without the extension
    (the names of A-68). Paths are compared exactly, as stored (A-14 matcher: case matters).
    """
    names: dict[str, str] = {}
    for item in found:
        relative = item.relative.as_posix()
        # the pseudonymous ID and file name as findings show them (FoundFile.identity: one suffix rule, A-70)
        for name in (relative, *item.identity[1:]):
            names.setdefault(name, relative)
    assigned: dict[str, set[str]] = {}
    unknown = 0
    for row in rows:
        target = names.get(row.recording)
        if target is None:
            unknown += 1
            continue
        assigned.setdefault(target, set()).add(row.split)
    return assigned, unknown
