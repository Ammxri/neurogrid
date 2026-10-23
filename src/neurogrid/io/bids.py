"""BIDS sidecars for one recording (A-04, A-46, LIB-02): entities, the inheritance principle, JSON and TSV
reading.

A sidecar applies to a data file if it lies in the data file's folder or above it (up to the dataset root),
has the same suffix, and its entities are a subset of the data file's entities. JSON sidecars are merged from
the top level down; for TSV files the nearest one counts. Links are not followed; sizes are limited (A-53).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

from neurogrid.kernel.errors import InputError
from neurogrid.kernel.safety import is_link, read_limited

MAX_JSON_BYTES = 2_000_000
MAX_TSV_BYTES = 10_000_000
_ENTITY = re.compile(r"^(?P<key>[a-z]+)-(?P<value>[A-Za-z0-9]+)$")


@dataclass(frozen=True)
class BidsName:
    entities: dict[str, str]
    suffix: str
    extension: str


@lru_cache(maxsize=65536)
def parse_name(name: str) -> BidsName | None:
    """Entities, suffix and extension of a BIDS file name; None if the name does not follow BIDS.

    MNE-BIDS reads the entities (LIB-02): it knows the entity keys of BIDS and refuses unknown ones.
    NeuroGrid adds the structural check that every part before the suffix is exactly one key-value pair
    with an alphanumeric value, and that MNE-BIDS reads the same pairs.
    """
    stem, dot, extension = name.partition(".")
    parts = stem.split("_")
    if not parts or not dot:
        return None
    suffix = parts[-1]
    entities: dict[str, str] = {}
    for part in parts[:-1]:
        match = _ENTITY.match(part)
        if match is None or match.group("key") in entities:
            return None
        entities[match.group("key")] = match.group("value")
    if not re.fullmatch(r"[A-Za-z0-9]+", suffix):
        return None
    if entities and _mne_bids_entities(name) != entities:
        return None
    return BidsName(entities=entities, suffix=suffix, extension="." + extension.lower())


def _mne_bids_entities(name: str) -> dict[str, str] | None:
    """The entities MNE-BIDS reads from a file name, with short keys; None if MNE-BIDS refuses the name."""
    from mne_bids import get_entities_from_fname  # imported on first use: raw folders never need it
    from mne_bids.config import ALLOWED_PATH_ENTITIES_SHORT

    try:
        found = get_entities_from_fname(name, on_error="raise")
    except (KeyError, ValueError, RuntimeError):
        return None
    return {short: str(found[long]) for short, long in ALLOWED_PATH_ENTITIES_SHORT.items() if found.get(long)}


def applicable(
    root: Path, data_file: PurePosixPath, suffix: str, extension: str, ignore: tuple[str, ...] = ()
) -> list[Path]:
    """Sidecars with ``suffix``/``extension`` that apply to ``data_file``, from the top level down.

    Entities in ``ignore`` are not compared (e.g. ``space`` of electrodes files, which data files lack).
    """
    data = parse_name(data_file.name)
    if data is None:
        return []
    found: list[Path] = []
    levels = [PurePosixPath(*data_file.parts[:depth]) for depth in range(len(data_file.parts))]
    for level in levels:
        folder = root.joinpath(*level.parts)
        if is_link(folder) or not folder.is_dir():
            continue
        try:
            names = sorted(entry.name for entry in folder.iterdir())
        except OSError:
            continue
        for name in names:
            candidate = parse_name(name)
            if candidate is None or candidate.suffix != suffix or candidate.extension != extension:
                continue
            relevant = {key: value for key, value in candidate.entities.items() if key not in ignore}
            if all(data.entities.get(key) == value for key, value in relevant.items()):
                path = folder / name
                if not is_link(path) and path.is_file():
                    found.append(path)
    return found


def read_json(path: Path) -> dict[str, Any] | None:
    """A JSON object, or None if the file is unreadable, too large or not an object."""
    try:
        data = json.loads(read_limited(path, MAX_JSON_BYTES).decode("utf-8-sig"))
    except (OSError, InputError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def no_value(cell: str) -> bool:
    """A TSV cell without a value: empty or n/a, without surrounding space and in any case ("N/A"). One rule
    for every reader of dataset tables: participants.tsv and events.tsv, M10 and M11 (A-80, A-81)."""
    return cell.strip().casefold() in ("", "n/a")


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]] | None:
    """Header and rows of a TSV file (column names exactly as written), or None if unreadable."""
    try:
        text = read_limited(path, MAX_TSV_BYTES).decode("utf-8-sig")
    except (OSError, InputError, UnicodeDecodeError):
        return None
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    header = lines[0].split("\t")
    rows = [dict(zip(header, line.split("\t"), strict=False)) for line in lines[1:]]
    return header, rows


def merged_json(root: Path, data_file: PurePosixPath, suffix: str) -> tuple[dict[str, Any], bool]:
    """All applicable JSON sidecars merged (lower levels win), and whether any sidecar was found."""
    merged: dict[str, Any] = {}
    files = applicable(root, data_file, suffix, ".json")
    for path in files:
        merged.update(read_json(path) or {})
    return merged, bool(files)


def nearest_tsv(
    root: Path, data_file: PurePosixPath, suffix: str, ignore: tuple[str, ...] = ()
) -> tuple[list[str], list[dict[str, str]]] | None:
    files = applicable(root, data_file, suffix, ".tsv", ignore)
    return read_tsv(files[-1]) if files else None
