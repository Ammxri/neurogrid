"""Comparison of two runs with the documented tolerance (DoD P11 "the notebook runs twice with equal numbers",
F3, A-106; area C "decoders and evaluation").

Exactly equal: the quality levels (quality.json), NeuroGrid's values (``recordings[].metrics`` of every
results.json, without the run-specific blocks such as ``environment`` and ``config.as_of``) and every CSP+LDA
fold. EEGNet: every fold exactly equal on the same machine; only if the pilot shows deviations does the
relaxed tolerance apply, at most 1 test trial per fold and at most 0.5 percentage points in the mean of a cell
(dataset x condition x decoder) - the report states which one was used (F3). No equality across machines is
claimed. ``fit_seconds`` and the times in run.json are never compared.

Command line (DoD 1; its output is committed as results/run_compare.json by area D)::

    python -m neuroarena.compare RUN_A RUN_B [--eegnet-tolerance] [--out FILE]

Exit 0: equal within the tolerance; 1: not; 2: usage error or a run folder that is incomplete.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EegnetTolerance:
    """The relaxed tolerance of F3 for EEGNet."""

    max_trials_per_fold: int = 1
    max_mean_points_per_cell: float = 0.5  # percentage points


@dataclass(frozen=True)
class Difference:
    what: str  # "quality" | "neurogrid" | "fold" | "cell" | "missing"
    where: str  # file and key, e.g. "folds/Zhou2016/clean/eegnet.csv subject=1 session=0 fold=3"
    a: str
    b: str


@dataclass(frozen=True)
class Comparison:
    ok: bool  # equal within the applied tolerance
    exact: bool  # everything exactly equal
    tolerance: EegnetTolerance | None  # None: exact for EEGNet as well
    compared: Mapping[str, int]  # what -> number of items compared
    differences: tuple[Difference, ...]  # sorted by (what, where)


def compare_runs(a: Path, b: Path, eegnet_tolerance: EegnetTolerance | None = None) -> Comparison:
    """Compare the run folders ``a`` and ``b`` (same configuration in run.json, else ValueError)."""
    raise NotImplementedError("area C")


def write_comparison(comparison: Comparison, path: Path) -> Path:
    """JSON (UTF-8, LF, sort_keys, two-space indent) without absolute paths or machine names (the run ids
    only); return ``path``."""
    raise NotImplementedError("area C")


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError("area C")


if __name__ == "__main__":
    raise SystemExit(main())
