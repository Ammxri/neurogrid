"""The records of a run and their CSV files (frozen by the P11 scaffold; written by area C, read by area D).

CSV: UTF-8, LF, header row with exactly the columns below in this order, comma separated, no index column;
floats written with ``repr`` (equal runs give equal files); an empty field is a missing value (no level).
Sorted by the key columns in the order given. ``fit_seconds`` is the only field that may differ between two
runs of the same configuration; ``compare.compare_runs`` ignores it.
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FoldRecord:
    """One fold of one decoder in one session and condition (folds/<dataset>/<condition>/<decoder>.csv)."""

    dataset: str
    condition: str  # Condition.id
    kind: str  # "clean" or a degradation kind
    level: int  # 0-5
    subject: int
    session: str
    decoder: str  # decoders.DECODERS
    fold: int  # 0-4
    seed: int
    n_train: int
    n_test: int
    n_correct: int
    accuracy: float  # n_correct / n_test
    fit_seconds: float


@dataclass(frozen=True)
class SessionRecord:
    """One session of one decoder under one condition (sessions.csv)."""

    dataset: str
    paradigm: str  # "imagery" | "ssvep"
    condition: str
    kind: str
    level: int
    subject: int
    session: str
    decoder: str
    n_trials: int
    accuracy: float  # sum of n_correct / sum of n_test over the folds
    chance: float  # evaluation.chance_level of the session's labels
    quality_level: int | None  # session level (quality.SessionQuality.level); None: no level
    runs_without_level: int


@dataclass(frozen=True)
class CurvePoint:
    """One point of a curve (curve.csv). ``axis`` "quality": x is the session's quality level 1-5 over all
    conditions (main figure, F5f A); ``axis`` "degradation": x is the degradation level 0-5 of one kind, the
    clean sessions at x = 0 (second figure, F5f B). A level without sessions has no row: it is reported as
    missing, never invented (DoD 2)."""

    dataset: str
    decoder: str
    axis: str  # "quality" | "degradation"
    kind: str  # "all" on the quality axis; a degradation kind on the degradation axis
    x: int
    n_sessions: int  # (session, condition) pairs in the point
    n_without_level: int  # quality axis: pairs left out for lack of a level (0 on the degradation axis)
    mean_accuracy: float
    ci_low: float  # evaluation.bootstrap_ci over the pairs of the point
    ci_high: float
    mean_chance: float


FOLD_COLUMNS = tuple(FoldRecord.__dataclass_fields__)
SESSION_COLUMNS = tuple(SessionRecord.__dataclass_fields__)
CURVE_COLUMNS = tuple(CurvePoint.__dataclass_fields__)
FOLD_KEY = ("dataset", "condition", "subject", "session", "decoder", "fold")
SESSION_KEY = ("dataset", "condition", "subject", "session", "decoder")
CURVE_KEY = ("dataset", "decoder", "axis", "kind", "x")


_KEYS: dict[type, tuple[str, ...]] = {FoldRecord: FOLD_KEY, SessionRecord: SESSION_KEY, CurvePoint: CURVE_KEY}


def write_csv(records: Iterable[FoldRecord | SessionRecord | CurvePoint], path: Path) -> Path:
    """Write records of one type, sorted by its key, atomically (temporary file in the same folder, then
    replace), as described in the module docstring; return ``path``.

    ValueError for no records (the type, and so the header, would be unknown), mixed types or two records
    with the same key."""
    items = list(records)
    if not items:
        raise ValueError(f"no records for {path.name}")
    kind = type(items[0])
    if kind not in _KEYS or any(type(item) is not kind for item in items):
        raise ValueError(f"records of one type of {sorted(k.__name__ for k in _KEYS)} expected")
    key = _KEYS[kind]
    items.sort(key=lambda item: tuple(getattr(item, column) for column in key))
    for before, after in zip(items, items[1:], strict=False):
        if all(getattr(before, column) == getattr(after, column) for column in key):
            raise ValueError(f"two records with the key {tuple(getattr(after, c) for c in key)!r}")
    columns = tuple(kind.__dataclass_fields__)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for item in items:
        writer.writerow([_text(getattr(item, column)) for column in columns])
    return write_atomic(path, buffer.getvalue().encode("utf-8"))


def read_folds(path: Path) -> list[FoldRecord]:
    return _read(path, FoldRecord)


def read_sessions(path: Path) -> list[SessionRecord]:
    return _read(path, SessionRecord)


def read_curve(path: Path) -> list[CurvePoint]:
    return _read(path, CurvePoint)


def write_atomic(path: Path, data: bytes) -> Path:
    """Write ``data`` to a temporary file next to ``path`` and replace ``path`` with it (atomic on the same
    file system); the folder is created. Retries the replace briefly on Windows, where a scanner may hold
    the target for a moment. Returns ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(10):
            try:
                Path(temporary).replace(path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.1 * (attempt + 1))
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return path


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        raise TypeError("no boolean columns")
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _read[R: (FoldRecord, SessionRecord, CurvePoint)](path: Path, kind: type[R]) -> list[R]:
    fields = kind.__dataclass_fields__
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    if not rows or tuple(rows[0]) != tuple(fields):
        raise ValueError(f"{path.name}: the header is not {','.join(fields)}")
    result = []
    for number, row in enumerate(rows[1:], start=2):
        if len(row) != len(fields):
            raise ValueError(f"{path.name} line {number}: {len(row)} fields instead of {len(fields)}")
        values = {
            name: _value(text, fields[name].type, path.name, number)
            for name, text in zip(fields, row, strict=True)
        }
        result.append(kind(**values))
    return result


def _value(text: str, annotation: object, name: str, line: int) -> object:
    # The annotations are strings (from __future__ import annotations): str, int, float, int | None.
    if annotation == "str":
        return text
    if annotation == "int | None" and text == "":
        return None
    try:
        if annotation in ("int", "int | None"):
            return int(text)
        if annotation == "float":
            return float(text)
    except ValueError:
        raise ValueError(f"{name} line {line}: {text!r} is not a {annotation}") from None
    raise TypeError(f"unsupported column type {annotation!r}")
