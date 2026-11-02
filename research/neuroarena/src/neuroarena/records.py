"""The records of a run and their CSV files (frozen by the P11 scaffold; written by area C, read by area D).

CSV: UTF-8, LF, header row with exactly the columns below in this order, comma separated, no index column;
floats written with ``repr`` (equal runs give equal files); an empty field is a missing value (no level).
Sorted by the key columns in the order given. ``fit_seconds`` is the only field that may differ between two
runs of the same configuration; ``compare.compare_runs`` ignores it.
"""

from __future__ import annotations

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


def write_csv(records: Iterable[FoldRecord | SessionRecord | CurvePoint], path: Path) -> Path:
    """Write records of one type, sorted by its key, atomically (temporary file in the same folder, then
    replace), as described in the module docstring; return ``path``."""
    raise NotImplementedError("area C")


def read_folds(path: Path) -> list[FoldRecord]:
    raise NotImplementedError("area C")


def read_sessions(path: Path) -> list[SessionRecord]:
    raise NotImplementedError("area C")


def read_curve(path: Path) -> list[CurvePoint]:
    raise NotImplementedError("area C")
