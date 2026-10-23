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
- Age groups in 10-year steps "0-9" ... "80-89", "90+" (A-21, :data:`AGE_GROUPS`). BIDS top-coding "N+"
  counts in the group of N ("89+" -> "80-89", "95+" -> "90+", A-81); a range "20-25" counts in its lower
  decade; anything else is unparseable and counts as missing (``ai.age_unparseable``). The raw age stays
  inside :class:`Subject` (``exclude=True``) and is never serialised; cell text never leaves this module
  except through the checks' display rule (A-17, C5). Besides ``age``, a column whose name says age
  (``age_years``, ``Age at scan``, ``AgeYears``, ``SubjectAge``, ``AgeInMonths``; :func:`is_age_column`)
  holds ages as well: as a label source it counts in the same groups (A-21). Its ages are in years unless
  its name gives a unit (:func:`age_unit`: months, weeks or days, as in ``age_months``, ``AgeDays``,
  ``age_in_weeks``, ``GestationalAgeWeeks``); they are converted to years before they are grouped
  (months / 12, weeks · 7 / 365.25, days / 365.25; A-81). The setting and the header may differ in case, so
  both spellings count (:func:`age_column`).
- Sex is normalised to female | male | other | given (documented, but in none of the three categories). A
  placeholder of :data:`SEX_PLACEHOLDERS` ("unknown", "U", "nan", "?", ...) documents no sex: it counts as
  missing like an empty cell (A-81), also in a sex column used as label source.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from neurogrid.io.bids import MAX_TSV_BYTES, no_value
from neurogrid.kernel.errors import InputError
from neurogrid.kernel.safety import is_link, read_limited
from neurogrid.model.dataset import Subject

PARTICIPANTS_FILE = "participants.tsv"
PARTICIPANTS_SIDECAR = "participants.json"
MAX_SIDECAR_BYTES = 2_000_000
SplitName = Literal["train", "val", "test"]
SPLIT_NAMES: tuple[SplitName, ...] = ("train", "val", "test")  # DM-06; the fixed order of scopes and outputs
AGE_LIMIT = 150.0  # a decimal age at or above this is no age (in years)


@dataclass(frozen=True)
class _AgeForms:
    """The three forms of an age cell for one number of integer digits: no sign, exponent, nan or inf
    (A-75), so every number converts to a finite float."""

    decimal: re.Pattern[str]
    top_coded: re.Pattern[str]  # BIDS "89+"
    span: re.Pattern[str]  # "20-25"

    @classmethod
    def of(cls, digits: int) -> _AgeForms:
        number = rf"\d{{1,{digits}}}(?:\.\d+)?"
        return cls(
            re.compile(rf"^{number}$"),
            re.compile(rf"^(?P<age>{number})\s*\+$"),
            re.compile(rf"^(?P<low>{number})\s*-\s*(?P<high>{number})$"),
        )


_YEAR_FORMS = _AgeForms.of(3)
_UNIT_FORMS = _AgeForms.of(5)  # an age below AGE_LIMIT has at most 5 integer digits in days (54787)
AGE_GROUPS: tuple[str, ...] = (*(f"{low}-{low + 9}" for low in range(0, 90, 10)), "90+")  # A-21
# The unit a column name gives its ages in: years per unit as (numerator, denominator), so the conversion is
# one multiplication and one division (months / 12, weeks * 7 / 365.25, days / 365.25; A-81)
YEARS: tuple[float, float] = (1.0, 1.0)
_UNIT_WORDS: dict[str, tuple[float, float]] = {
    **dict.fromkeys(("years", "year", "yrs", "yr"), YEARS),
    **dict.fromkeys(("months", "month", "mos", "mo"), (1.0, 12.0)),
    **dict.fromkeys(("weeks", "week", "wks", "wk"), (7.0, 365.25)),
    **dict.fromkeys(("days", "day"), (1.0, 365.25)),
}
_UNITS = "|".join(sorted(_UNIT_WORDS, key=len, reverse=True))  # the longest first: "months" before "mo"
# Words that qualify an age in a compact name without capitals or separators ("subjectage",
# "gestationalageweeks"). The list is closed because many words end in "age" ("stage", "voltage", "postage",
# "parentage", "percentage"); with capitals or separators any word in front counts ("DonorAge", "donor_age").
_AGE_QUALIFIERS = (
    "subject",
    "participant",
    "patient",
    "child",
    "infant",
    "mother",
    "father",
    "maternal",
    "paternal",
    "gestational",
    "chronological",
    "corrected",
    "postmenstrual",
    "postconceptional",
    "conceptional",
    "postnatal",
    "biological",
    "developmental",
    "mental",
    "brain",
    "bone",
    "onset",
    "scan",
    "visit",
    "baseline",
    "current",
)
_QUALIFIERS = "|".join(sorted(_AGE_QUALIFIERS, key=len, reverse=True))
# A word of a column name that says the column holds ages: "age", "ages" or a compact form ("ageyears",
# "ageatscan", "agemonths", "ageinmonths", "ageatscandays", "subjectage"); the group "unit" is the unit the
# compact form names
_AGE_WORD = re.compile(rf"(?:{_QUALIFIERS})?ages?(?:at[a-z]*?)?(?:(?:in)?(?P<unit>{_UNITS})|group|grp)?")
_NAME_WORDS = re.compile(r"[^0-9a-z]+")
# Where camel case starts a new word: a capital after a small letter ("Subject|Age", "Age|In|Months"), the
# last capital of an acronym before a small letter ("EEG|Age"), and letters next to digits ("Age|2")
_CAMEL_WORDS = re.compile(
    r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])"
)
SEX_COLUMNS = ("sex", "gender")  # in this order (A-04)
# Sex cells that say the sex is not known, compared after strip and casefold: no documentation (A-81)
SEX_PLACEHOLDERS = frozenset(
    {
        "unknown",
        "unk",
        "u",
        "nan",
        "na",
        "n/a",
        "none",
        "null",
        "missing",
        "not reported",
        "not available",
        "?",
        "-",
    }
)
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
    return no_value(value)


def _name_words(name: str) -> tuple[list[str], list[str]]:
    """The words of a column name in two readings, without regard to case: split at every character that is
    neither a letter nor a digit (``age_years``, ``Age at scan``; compact forms stay whole: ``ageinmonths``),
    and also where camel case or digits start a new word (``SubjectAge``, ``AgeInMonths``, ``EEGAge``,
    ``Age2``)."""
    camel = [word for part in _CAMEL_WORDS.split(name.strip()) for word in _NAME_WORDS.split(canonical(part))]
    return _NAME_WORDS.split(canonical(name)), camel


def is_age_column(name: str) -> bool:
    """Whether a column holds ages by its name: a word "age" (``age``, ``age_years``, ``Age at scan``,
    ``subject_age``, ``SubjectAge``, ``AgeInMonths``) or a compact form (``AgeYears``, ``ageatscan``,
    ``agemonths``, ``ageinmonths``, ``patientage``), but not a word that only contains the letters
    (``language``, ``stage``, ``PageCount``). Raw ages never leave the process (A-21, A-81)."""
    return any(_AGE_WORD.fullmatch(word) for words in _name_words(name) for word in words)


def age_unit(name: str) -> tuple[float, float]:
    """Years per unit, as (numerator, denominator), of the ages in a column that holds ages: the first unit
    its name gives, in a compact age word (``agemonths``, ``ageatscandays``, ``ageinweeks``) or as a word of
    its own (``age_in_weeks``, ``Age (days)``, ``AgeInMonths``, ``GestationalAgeWeeks``): months, weeks or
    days (A-81); a name without a unit gives years."""
    for words in _name_words(name):
        for word in words:
            compact = _AGE_WORD.fullmatch(word)
            unit = compact.group("unit") if compact is not None else word
            if unit in _UNIT_WORDS:
                return _UNIT_WORDS[unit]
    return YEARS


def age_column(*names: str) -> tuple[float, float] | None:
    """Years per unit of a column that holds ages by one of its spellings, or None if no spelling says age.
    The name in the settings and the header in participants.tsv match without regard to case, but only the
    capitals show the words of ``SubjectAge`` or ``DonorAgeDays``: a column holds ages if one spelling says
    so, and its unit is the first unit a spelling gives (:func:`age_unit`), else years (A-81)."""
    if not any(is_age_column(name) for name in names):
        return None
    return next((unit for unit in map(age_unit, names) if unit != YEARS), YEARS)


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


def age_group(text: str, unit: tuple[float, float] = YEARS) -> str | None:
    """The 10-year group of an age cell, or None if the cell is not an age (A-21, A-81). ``unit`` gives the
    years per unit of the cell (:func:`age_unit`): an age in months, weeks or days is converted to years
    first, so it counts in the same groups as the demography."""
    value = text.strip()
    forms = _YEAR_FORMS if unit == YEARS else _UNIT_FORMS
    numerator, denominator = unit

    def years(number: str) -> float:
        return float(number) * numerator / denominator

    if forms.decimal.fullmatch(value):
        return _decade(years(value))
    top = forms.top_coded.fullmatch(value)
    if top:  # "N+" counts in the group of N (A-81)
        return _decade(years(top.group("age")))
    span = forms.span.fullmatch(value)
    if span and float(span.group("low")) <= float(span.group("high")):
        return _decade(years(span.group("low")))
    return None


def _age(text: str) -> float | None:
    """The raw age, only for the internal data model (never serialised)."""
    value = text.strip()
    if _YEAR_FORMS.decimal.fullmatch(value) and float(value) < AGE_LIMIT:
        return float(value)
    return None


def sex_category(text: str) -> str | None:
    """female | male | other | given; None when the cell documents no sex (empty, n/a or a placeholder)."""
    value = text.strip().casefold()
    if not value or value in SEX_PLACEHOLDERS:
        return None
    return _SEX.get(value, "given")


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
    headers: Mapping[str, str] = field(default_factory=dict)  # the header text by canonical name (the first)
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


def _state(cells: Mapping[str, str], column: str | None, kind: Literal["age", "sex"]) -> ValueState:
    if column is None:
        return "no_column"
    value = cells.get(column, "")
    if missing(value) or (kind == "sex" and sex_category(value) is None):
        return "missing"
    if kind == "age" and age_group(value) is None:
        return "unparseable"
    return "documented"


def parse_participants(
    text: str, vocabulary: Mapping[str, frozenset[str]] | None = None
) -> ParticipantsTable:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ParticipantsTable(usable=False)
    header: list[str] = []
    headers: dict[str, str] = {}
    for name in lines[0].split("\t"):
        header.append(canonical(name))
        headers.setdefault(canonical(name), name.strip())  # duplicate columns: the first one counts
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
    sex_column = next((name for name in SEX_COLUMNS if name in columns), None)
    age_column = "age" if "age" in columns else None
    participants: dict[str, Participant] = {}
    for label, row in first.items():
        age_text = row.get("age", "")
        sex_text = row.get(sex_column, "") if sex_column else ""
        age = _state(row, age_column, "age")
        sex = _state(row, sex_column, "sex")
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
        headers=headers,
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
