"""participants.tsv at the dataset root: demography, a split column and label columns (M11, M12; A-04, A-51,
A-81, DM-02).

The table is dataset data, never a NeuroGrid control file (decision C2): a missing, linked, oversized or
malformed table is a finding of the checks, never exit 2. BIDS datasets and raw folders use the same file;
in raw folders ``participant_id`` is the subject label of the mapping, with or without ``sub-``.

- Columns are matched without surrounding space and without regard to case (A-04; ds004148 has headers with
  spaces, ds004504 capitals). ``participant_id`` is required, else the table is unusable. Demography: ``age``,
  ``sex`` with the fallback ``gender`` (A-04). A ``split`` column assigns subjects to train/val/test.
- Cells are stripped; empty cells and ``n/a`` (any case) count as missing. Several rows of one participant:
  the first row gives the cells, the split values of all rows count (a subject in several splits, A-21).
- Age groups in 10-year steps "0-9" ... "80-89", "90+" (A-21). BIDS top-coding "N+" becomes "90+" from 90 and
  "<decade>+" below; a range "20-25" counts in its lower decade; anything else is unparseable and counts as
  missing (``ai.age_unparseable``). The raw age stays inside :class:`Subject` (``exclude=True``) and is never
  serialised; cell text never leaves this module except through the checks' display rule (A-17, C5).
- Sex is normalised to female | male | other | given (documented, but in none of the three categories).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from neurogrid.io.bids import MAX_TSV_BYTES
from neurogrid.kernel.errors import InputError
from neurogrid.kernel.safety import is_link, read_limited
from neurogrid.model.dataset import Subject

PARTICIPANTS_FILE = "participants.tsv"
PARTICIPANTS_SIDECAR = "participants.json"
MAX_SIDECAR_BYTES = 2_000_000
SplitName = Literal["train", "val", "test"]
SPLIT_NAMES: tuple[SplitName, ...] = ("train", "val", "test")  # DM-06; the fixed order of scopes and outputs
AGE_LIMIT = 150.0  # a decimal age at or above this is no age
_DECIMAL = re.compile(r"^\d{1,3}(?:\.\d+)?$")  # no sign, exponent, nan or inf (A-75)
_TOP_CODED = re.compile(r"^(?P<age>\d{1,3}(?:\.\d+)?)\s*\+$")  # BIDS "89+"
_RANGE = re.compile(r"^(?P<low>\d{1,3}(?:\.\d+)?)\s*-\s*(?P<high>\d{1,3}(?:\.\d+)?)$")
_SEX = {
    "f": "female",
    "female": "female",
    "w": "female",
    "woman": "female",
    "m": "male",
    "male": "male",
    "man": "male",
    "o": "other",
    "other": "other",
    "x": "other",
    "d": "other",
    "diverse": "other",
    "nonbinary": "other",
    "non-binary": "other",
}

ValueState = Literal["documented", "missing", "unparseable", "no_column"]


def canonical(name: str) -> str:
    """Column names are compared without surrounding space and without regard to case (A-04)."""
    return name.strip().casefold()


def missing(value: str) -> bool:
    return value.strip().casefold() in ("", "n/a")


def subject_label(participant_id: str) -> str:
    """The subject label of a participant_id: without surrounding space and without a leading ``sub-``."""
    text = participant_id.strip()
    return text[4:] if text.startswith("sub-") else text


def _decade(age: float) -> str | None:
    if not math.isfinite(age) or age < 0 or age >= AGE_LIMIT:
        return None
    if age >= 90:
        return "90+"
    low = int(age // 10) * 10
    return f"{low}-{low + 9}"


def age_group(text: str) -> str | None:
    """The 10-year group of an age cell, or None if the cell is not an age (A-21, A-81)."""
    value = text.strip()
    if _DECIMAL.fullmatch(value):
        return _decade(float(value))
    top = _TOP_CODED.fullmatch(value)
    if top:
        age = float(top.group("age"))
        if age >= AGE_LIMIT:
            return None
        return "90+" if age >= 90 else f"{int(age // 10) * 10}+"
    span = _RANGE.fullmatch(value)
    if span and float(span.group("low")) <= float(span.group("high")):
        return _decade(float(span.group("low")))
    return None


def _age(text: str) -> float | None:
    """The raw age, only for the internal data model (never serialised)."""
    value = text.strip()
    if _DECIMAL.fullmatch(value) and float(value) < AGE_LIMIT:
        return float(value)
    return None


def sex_category(text: str) -> str:
    return _SEX.get(text.strip().casefold(), "given")


@dataclass(frozen=True)
class Participant:
    """One subject of participants.tsv. ``cells`` holds the first row by canonical column name; ``splits``
    the valid split values of all rows."""

    subject: Subject  # DM-02: pseudo_id, age_group, sex; the raw age is excluded from every dump
    age: ValueState
    sex: ValueState
    splits: frozenset[str] = frozenset()
    invalid_splits: int = 0  # split cells that are neither empty/n/a nor train/val/test
    cells: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ParticipantsTable:
    """The table at the dataset root. ``usable`` is False for a link, a non-regular file, an oversized or
    undecodable file and a table without ``participant_id``; then it holds no participants."""

    usable: bool
    columns: frozenset[str] = frozenset()  # canonical names
    sex_column: str | None = None  # "sex" or "gender" (A-04)
    participants: Mapping[str, Participant] = field(default_factory=dict)  # by subject label
    vocabulary: Mapping[str, frozenset[str]] = field(default_factory=dict)  # participants.json Levels

    @property
    def has_split(self) -> bool:
        return "split" in self.columns


def _levels(root: Path) -> dict[str, frozenset[str]]:
    """The documented values ("Levels") per column of participants.json, by canonical column name."""
    path = root / PARTICIPANTS_SIDECAR
    if is_link(path) or not path.is_file():
        return {}
    try:
        data = json.loads(read_limited(path, MAX_SIDECAR_BYTES).decode("utf-8-sig"))
    except (OSError, InputError, ValueError, RecursionError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, frozenset[str]] = {}
    for name, entry in data.items():
        levels = entry.get("Levels") if isinstance(entry, dict) else None
        if isinstance(name, str) and isinstance(levels, dict):
            out.setdefault(canonical(name), frozenset(str(key) for key in levels))
    return out


def _state(cells: Mapping[str, str], column: str | None, parse: bool = False) -> ValueState:
    if column is None:
        return "no_column"
    value = cells.get(column, "")
    if missing(value):
        return "missing"
    if parse and age_group(value) is None:
        return "unparseable"
    return "documented"


def parse_participants(
    text: str, vocabulary: Mapping[str, frozenset[str]] | None = None
) -> ParticipantsTable:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ParticipantsTable(usable=False)
    header: list[str] = []
    for name in lines[0].split("\t"):
        header.append(canonical(name))
    if "participant_id" not in header:
        return ParticipantsTable(usable=False)
    position = {name: header.index(name) for name in header}  # duplicate columns: the first one counts
    first: dict[str, dict[str, str]] = {}
    splits: dict[str, set[str]] = {}
    invalid: dict[str, int] = {}
    for line in lines[1:]:
        cells = line.split("\t")
        row = {name: cells[index].strip() if index < len(cells) else "" for name, index in position.items()}
        label = subject_label(row["participant_id"])
        if not label:
            continue
        first.setdefault(label, row)
        split = row.get("split", "").casefold()
        if split in SPLIT_NAMES:
            splits.setdefault(label, set()).add(split)
        elif "split" in row and not missing(split):
            invalid[label] = invalid.get(label, 0) + 1
    columns = frozenset(header)
    sex_column = "sex" if "sex" in columns else "gender" if "gender" in columns else None
    age_column = "age" if "age" in columns else None
    participants: dict[str, Participant] = {}
    for label, row in first.items():
        age_text = row.get("age", "")
        sex_text = row.get(sex_column, "") if sex_column else ""
        age = _state(row, age_column, parse=True)
        sex = _state(row, sex_column)
        subject = Subject(
            pseudo_id=f"sub-{label}",
            age_group=age_group(age_text) if age == "documented" else None,
            sex=sex_category(sex_text) if sex == "documented" else None,
            age=_age(age_text) if age == "documented" else None,
        )
        participants[label] = Participant(
            subject=subject,
            age=age,
            sex=sex,
            splits=frozenset(splits.get(label, ())),
            invalid_splits=invalid.get(label, 0),
            cells=row,
        )
    return ParticipantsTable(
        usable=True,
        columns=columns,
        sex_column=sex_column,
        participants=participants,
        vocabulary=dict(vocabulary or {}),
    )


def read_participants(root: Path) -> ParticipantsTable | None:
    """``<root>/participants.tsv``; None if there is none. Links are not followed (A-52), sizes are limited
    (A-53); problems make the table unusable instead of ending the run (C2)."""
    path = root / PARTICIPANTS_FILE
    if not path.exists() and not is_link(path):
        return None
    if is_link(path) or not path.is_file():
        return ParticipantsTable(usable=False)
    try:
        text = read_limited(path, MAX_TSV_BYTES).decode("utf-8-sig")
    except (OSError, InputError, UnicodeDecodeError):
        return ParticipantsTable(usable=False)
    return parse_participants(text, _levels(root))
