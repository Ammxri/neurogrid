"""Locations of NeuroArena (A-100, F1; frozen by the P11 scaffold).

Data, working files and runs live under ``.local/arena/`` of the NeuroGrid repository: never in the
repository, never in a CI cache. The repository keeps code, lock, notebook, report, figures and aggregated CSV
only (``notebooks/``, ``report/en/``, ``report/zh/``, ``results/``; area D). The paths assume the project is
installed editable, as ``uv sync`` does. Every builder takes its base folder as an argument, so tests pass a
temporary one.

Run folder ``.local/arena/runs/<run-id>/`` (written by the runner, area C, and ``quality.assess``, area B)::

    run.json                                   the run's configuration, versions and lock hash (runner)
    neurogrid/<dataset>/<condition>/neurogrid.toml   the research configuration of the check (A-101)
    neurogrid/<dataset>/<condition>/recordings.json  FIF file -> recording key (export)
    neurogrid/<dataset>/<condition>/results.json     NeuroGrid's results (A-101)
    neurogrid/<dataset>/<condition>/quality.json     quality levels per recording and session (A-102)
    folds/<dataset>/<condition>/<decoder>.csv  one row per fold (records.FOLD_COLUMNS)
    sessions.csv                               one row per dataset, condition, decoder and session
    curve.csv                                  accuracy over the quality level (records.CURVE_COLUMNS)

Working folder ``.local/arena/work/<run-id>/<dataset>/<condition>/``: the exported FIF files of one check,
deleted after the check of that condition (F1).
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]  # research/neuroarena
REPO = PROJECT.parents[1]  # the NeuroGrid repository; its uv project runs the command line (A-101)
ARENA = REPO / ".local" / "arena"
MNE_DATA = ARENA / "mne_data"  # MNE_DATA and the download folder of MOABB
WORK = ARENA / "work"
RUNS = ARENA / "runs"

# Reserved for area D (committed): the notebook, the report in en and zh, aggregated CSV, figures and
# results/run_compare.json (DoD 1).
NOTEBOOKS = PROJECT / "notebooks"
REPORT_EN = PROJECT / "report" / "en"
REPORT_ZH = PROJECT / "report" / "zh"
RESULTS = PROJECT / "results"

RUN_FILE = "run.json"
CONFIG_FILE = "neurogrid.toml"
INDEX_FILE = "recordings.json"
RESULTS_FILE = "results.json"
QUALITY_FILE = "quality.json"
SESSIONS_FILE = "sessions.csv"
CURVE_FILE = "curve.csv"
RUN_COMPARE_FILE = "run_compare.json"

# A run id is a single safe folder name.
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def _checked(value: str, pattern: re.Pattern[str], what: str) -> str:
    if not pattern.fullmatch(value) or value.endswith("."):
        raise ValueError(f"invalid {what}: {value!r}")
    return value


def run_dir(run_id: str, runs: Path = RUNS) -> Path:
    """``<runs>/<run-id>``."""
    return runs / _checked(run_id, RUN_ID, "run id")


def neurogrid_dir(run_id: str, dataset: str, condition: str, runs: Path = RUNS) -> Path:
    """``<runs>/<run-id>/neurogrid/<dataset>/<condition>`` (condition: ``Condition.id``)."""
    return (
        run_dir(run_id, runs)
        / "neurogrid"
        / _checked(dataset, _NAME, "dataset")
        / _checked(condition, _NAME, "condition")
    )


def folds_file(run_id: str, dataset: str, condition: str, decoder: str, runs: Path = RUNS) -> Path:
    """``<runs>/<run-id>/folds/<dataset>/<condition>/<decoder>.csv``."""
    folder = run_dir(run_id, runs) / "folds" / _checked(dataset, _NAME, "dataset")
    return folder / _checked(condition, _NAME, "condition") / f"{_checked(decoder, _NAME, 'decoder')}.csv"


def work_dir(run_id: str, dataset: str, condition: str, work: Path = WORK) -> Path:
    """``<work>/<run-id>/<dataset>/<condition>``: the FIF files of one check (deleted afterwards)."""
    return (
        work
        / _checked(run_id, RUN_ID, "run id")
        / _checked(dataset, _NAME, "dataset")
        / _checked(condition, _NAME, "condition")
    )
