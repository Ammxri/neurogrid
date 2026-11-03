"""The run over datasets x conditions (A-104, A-106, A-109, F3; area C "decoders and evaluation").

For each dataset and condition: the quality step once (``quality.assess``: FIF export, one NeuroGrid call,
levels per recording and session), then both decoders in every session of every subject (``evaluation``).
Parallel worker processes (spawn) with one thread each (``determinism.WORKER_ENVIRONMENT``); resumable: every
unit writes its result atomically and a rerun with the same run id skips finished units, after checking that
run.json holds the same configuration. Aggregates sessions.csv and curve.csv at the end. Layout of the run
folder: ``paths`` module docstring. Budget: at most 48 h wall time per full run (F3 A); the pilot (A-109)
comes first.

Command line::

    python -m neuroarena.runner --run-id ID [--mode full|pilot|smoke] [--datasets ...] [--conditions ...]
                                [--processes N] [--neurogrid-jobs N]

Units, in this order for every dataset of the configuration and every condition in the configured order:
the quality step of the (dataset, condition), then one decoder unit per decoder and subject (all sessions of
the subject). Units are independent of each other; with several processes they run side by side. The main
process alone writes the run folder: after a unit it writes the unit's file atomically,
``units/<dataset>/<condition>/quality.json`` (a marker with the wall time, written after ``quality.assess``
has written its files) or ``units/<dataset>/<condition>/<decoder>/<subject>.json`` (the fold records and the
labels of every session). A unit with such a file is finished and is skipped on a rerun; an interrupted
quality step starts again from an empty folder. ``folds/<dataset>/<condition>/<decoder>.csv`` is written as
soon as every subject of that cell is finished; sessions.csv and curve.csv once every unit is.

Seeds: a session's folds use ``derive_seed(dataset, subject, session)``, independent of the condition and the
decoder, so every condition and both decoders see the same folds and EEGNet the same initial weights (a paired
design: the curve shows the change of the data, not of the split). Fold seeds are
``derive_seed(<session seed>, fold)`` (``evaluation.evaluate_session``).

Modes: ``full`` reads the MOABB loaders (the data must have been fetched with ``datasets.fetch``: MOABB itself
would download missing files); ``pilot`` (A-109) does the same and, on the command line, defaults to the clean
condition; it also fits EEGNet a second time on the first subject of every dataset and records in run.json
whether the folds are identical; ``smoke`` (F11 B) reads ``synthetic.fake_dataset`` and trains EEGNet for
``SMOKE_EEGNET_EPOCHS`` epochs only.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import dataclasses
import datetime
import hashlib
import importlib.metadata
import json
import math
import multiprocessing
import os
import platform
import shutil
import sys
import time
import traceback
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neuroarena import datasets, decoders, determinism, evaluation, paths, quality, records, synthetic
from neuroarena.datasets import DATASETS
from neuroarena.decoders import DECODERS
from neuroarena.keys import CLEAN, CONDITIONS, KINDS, LEVELS, Condition, SessionKey

# full: the approved datasets, every subject (F2 A), all 16 conditions. pilot (A-109): what the pilot
# measures before the full run (clean levels and accuracies, time per fit and per recording, EEGNet twice on
# one subject). smoke (F11 B): synthetic.fake_dataset stand-ins, no download, EEGNet with few epochs.
MODES = ("full", "pilot", "smoke")
# Scaffold choice for the smoke mode (F11 B says "EEGNet with few epochs"); fixed by area C.
SMOKE_EEGNET_EPOCHS = 2

RUN_VERSION = 1
UNITS_FOLDER = "units"
# The libraries whose versions decide the numbers (run.json; a resumed run and a compared run must match).
PACKAGES = (
    "braindecode",
    "mne",
    "moabb",
    "numpy",
    "pandas",
    "pyriemann",
    "scikit-learn",
    "scipy",
    "skorch",
    "torch",
)
# MOABB's default cache configuration, written out: nothing is read from or saved to a disk cache.
NO_CACHE = {"use": False, "save_raw": False, "save_epochs": False, "save_array": False}


@dataclass(frozen=True)
class RunConfig:
    run_id: str
    mode: str = "full"
    datasets: tuple[str, ...] = tuple(DATASETS)
    conditions: tuple[str, ...] = tuple(condition.id for condition in CONDITIONS)
    decoders: tuple[str, ...] = DECODERS
    # dataset -> subjects; None or a missing dataset: all subjects of the loader (F2 A). A subset needs the
    # owner's approval and appears in the report (F2).
    subjects: Mapping[str, tuple[int, ...]] | None = field(default=None)
    processes: int = 1
    neurogrid_jobs: int = 1


@dataclass(frozen=True)
class Unit:
    """One unit of a run: the quality step of (dataset, condition) or one decoder on one subject."""

    dataset: str
    condition: str
    decoder: str | None = None  # None: the quality step
    subject: int | None = None

    @property
    def id(self) -> str:
        if self.decoder is None:
            return f"quality {self.dataset} {self.condition}"
        return f"{self.decoder} {self.dataset} {self.condition} subject {self.subject}"

    def file(self, folder: Path) -> Path:
        """The unit's file in the run folder ``folder``."""
        base = folder / UNITS_FOLDER / self.dataset / self.condition
        if self.decoder is None:
            return base / "quality.json"
        return base / self.decoder / f"{self.subject}.json"


class UnitError(RuntimeError):
    """At least one unit failed; every other unit has been run and kept (exit code 1)."""

    def __init__(self, failed: Sequence[tuple[Unit, str]]) -> None:
        self.failed = tuple(failed)
        super().__init__(f"{len(self.failed)} unit(s) failed: " + "; ".join(u.id for u, _ in self.failed))


def run(config: RunConfig, runs: Path = paths.RUNS, work: Path = paths.WORK) -> Path:
    """Run (or resume) ``config``; return the run folder ``paths.run_dir(config.run_id, runs)``.

    Writes run.json first (configuration, mode, versions of the locked key packages, SHA-256 of
    research/neuroarena/uv.lock and of the main project's uv.lock, ``determinism.BASE_SEED``, CPU and OS
    description, start and end time), then per dataset and condition the files of ``quality.assess`` and
    folds/<dataset>/<condition>/<decoder>.csv, at the end sessions.csv and curve.csv. Raises ValueError if
    run.json exists with another configuration.

    The configuration that must match is everything of run.json except the attempts (times, processes,
    NeuroGrid jobs, failures), the machine description and the pilot block: ``configuration``. Raises
    UnitError after all other units if a unit failed (sessions.csv and curve.csv are then not written).

    Outside the smoke mode ``datasets.configure_storage()`` runs in this process before the first loader and
    in every worker before its unit (MNE_DATA, the MOABB data folders and the upstream download provider)."""
    _validate(config)
    if config.mode != "smoke":
        datasets.configure_storage()
    folder = paths.run_dir(config.run_id, runs)
    subjects = _subjects(config)
    document = _document(config, subjects)
    run_file = folder / paths.RUN_FILE
    if run_file.exists():
        previous = json.loads(run_file.read_text(encoding="utf-8"))
        if configuration(previous) != configuration(document):
            raise ValueError(f"run {config.run_id!r} exists with another configuration ({run_file.name})")
        document["attempts"] = list(previous.get("attempts", []))
        if "pilot" in previous:
            document["pilot"] = previous["pilot"]
    units = plan(config, subjects)
    pending = [unit for unit in units if not _finished(unit, folder, config.run_id, runs)]
    attempt: dict[str, Any] = {
        "started": _now(),
        "finished": None,
        "processes": config.processes,
        "neurogrid_jobs": config.neurogrid_jobs,
        "units": len(units),
        "pending": len(pending),
        "failed": [],
    }
    document["attempts"].append(attempt)
    _write_json(run_file, document)

    failed: list[tuple[Unit, str]] = []
    repeat = config.mode == "pilot" and "pilot" not in document
    if pending or repeat:
        context = _Context(config.mode, config.run_id, runs, work, config.neurogrid_jobs, subjects)
        with _pool(config.processes) as executor:
            failed = _execute(executor, pending, context, folder)
            if repeat and not failed:
                document["pilot"] = _pilot_repeat(executor, config, subjects, context, folder)

    _write_folds(config, subjects, folder, runs)
    if not failed:
        session_rows = _sessions(config, subjects, folder, runs)
        records.write_csv(session_rows, folder / paths.SESSIONS_FILE)
        records.write_csv(curve_points(session_rows), folder / paths.CURVE_FILE)
        shutil.rmtree(work / config.run_id, ignore_errors=True)
    attempt["finished"] = _now()
    attempt["failed"] = [{"unit": unit.id, "error": error} for unit, error in failed]
    _write_json(run_file, document)
    if failed:
        raise UnitError(failed)
    return folder


def plan(config: RunConfig, subjects: Mapping[str, Sequence[int]]) -> list[Unit]:
    """Every unit of ``config`` in the order of submission (module docstring)."""
    units = []
    for dataset in config.datasets:
        for condition in config.conditions:
            units.append(Unit(dataset, condition))
            for decoder in config.decoders:
                units.extend(Unit(dataset, condition, decoder, subject) for subject in subjects[dataset])
    return units


def configuration(document: Mapping[str, Any]) -> dict[str, Any]:
    """The part of a run.json document that decides the numbers: everything but the run id, the attempts,
    the machine, the pilot block and the configuration's ``processes`` and ``neurogrid_jobs`` (they change the
    wall time only). A resumed run must match it; ``compare.compare_runs`` requires it equal as well."""
    result = {
        key: value for key, value in document.items() if key not in ("run_id", "attempts", "machine", "pilot")
    }
    result["config"] = {
        key: value
        for key, value in document.get("config", {}).items()
        if key not in ("run_id", "processes", "neurogrid_jobs")
    }
    return result


def curve_points(sessions: Sequence[records.SessionRecord]) -> list[records.CurvePoint]:
    """The points of both curves from the session records (``records.CurvePoint``).

    Quality axis: per dataset and decoder, the (session, condition) pairs grouped by the session's quality
    level 1-5; ``n_without_level`` is the number of pairs of that dataset and decoder without a level (the
    same on each of its rows). Degradation axis: per dataset, decoder and kind, x = 0 for the clean pairs and
    x = the level for the pairs of that kind. A level without pairs has no row. Means are exact sums over the
    pairs in key order; the interval is ``evaluation.bootstrap_ci`` with the seed
    ``derive_seed("curve", dataset, decoder, axis, kind, x)``."""
    groups: dict[tuple[str, str], list[records.SessionRecord]] = {}
    for row in sorted(sessions, key=lambda r: tuple(getattr(r, c) for c in records.SESSION_KEY)):
        groups.setdefault((row.dataset, row.decoder), []).append(row)
    points = []
    for (dataset, decoder), rows in groups.items():
        without = sum(1 for row in rows if row.quality_level is None)
        for x in LEVELS:
            members = [row for row in rows if row.quality_level == x]
            if members:
                points.append(_point(dataset, decoder, "quality", "all", x, members, without))
        for kind in KINDS:
            for x in (0, *LEVELS):
                members = [
                    row
                    for row in rows
                    if (row.kind == CLEAN.kind if x == 0 else (row.kind == kind and row.level == x))
                ]
                if members:
                    points.append(_point(dataset, decoder, "degradation", kind, x, members, 0))
    return points


def main(argv: Sequence[str] | None = None) -> int:
    """The command line above; exit 0 on success, 1 when a unit failed (the others are kept), 2 on a usage
    error."""
    parser = argparse.ArgumentParser(prog="python -m neuroarena.runner", description=__doc__.split("\n")[0])
    parser.add_argument("--run-id", required=True, help="name of the run folder under .local/arena/runs")
    parser.add_argument("--mode", choices=MODES, default="full")
    parser.add_argument("--datasets", nargs="+", choices=tuple(DATASETS), default=None)
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=None,
        help="condition ids (default: all 16; the pilot mode defaults to clean)",
    )
    parser.add_argument("--processes", type=int, default=1)
    parser.add_argument("--neurogrid-jobs", type=int, default=1)
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        return int(stop.code or 0)
    conditions = args.conditions
    if conditions is None:
        conditions = [CLEAN.id] if args.mode == "pilot" else [c.id for c in CONDITIONS]
    config = RunConfig(
        run_id=args.run_id,
        mode=args.mode,
        datasets=tuple(args.datasets) if args.datasets else tuple(DATASETS),
        conditions=tuple(conditions),
        processes=args.processes,
        neurogrid_jobs=args.neurogrid_jobs,
    )
    try:
        folder = run(config)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except UnitError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"run {config.run_id} complete: {folder.name}")
    return 0


# --- configuration and run.json ------------------------------------------------------------------------


def _validate(config: RunConfig) -> None:
    paths.run_dir(config.run_id)  # ValueError for an unsafe run id
    if config.mode not in MODES:
        raise ValueError(f"unknown mode {config.mode!r}")
    for what, values, known in (
        ("dataset", config.datasets, tuple(DATASETS)),
        ("decoder", config.decoders, DECODERS),
        ("condition", config.conditions, tuple(c.id for c in CONDITIONS)),
    ):
        if not values or len(set(values)) != len(values):
            raise ValueError(f"the {what}s must be given once each: {values!r}")
        unknown = [value for value in values if value not in known]
        if unknown:
            raise ValueError(f"unknown {what}(s): {unknown!r}")
    if config.processes < 1 or config.neurogrid_jobs < 1:
        raise ValueError("processes and neurogrid_jobs must be at least 1")
    for dataset, chosen in (config.subjects or {}).items():
        if dataset not in config.datasets:
            raise ValueError(f"subjects for a dataset outside the run: {dataset!r}")
        if not chosen or len(set(chosen)) != len(chosen) or any(int(s) < 1 for s in chosen):
            raise ValueError(f"invalid subjects for {dataset}: {chosen!r}")


def _base(spec: datasets.DatasetSpec, mode: str) -> Any:
    """The undegraded MOABB dataset of ``spec`` in ``mode`` (B's loader or its synthetic stand-in)."""
    if mode == "smoke":
        return synthetic.fake_dataset(spec)
    return datasets.moabb_dataset(spec)


def _subjects(config: RunConfig) -> dict[str, tuple[int, ...]]:
    chosen = config.subjects or {}
    result = {}
    for dataset in config.datasets:
        if dataset in chosen:
            result[dataset] = tuple(sorted(int(s) for s in chosen[dataset]))
        else:
            result[dataset] = tuple(int(s) for s in _base(DATASETS[dataset], config.mode).subject_list)
        if not result[dataset]:
            raise ValueError(f"no subjects for {dataset}")
    return result


def _document(config: RunConfig, subjects: Mapping[str, tuple[int, ...]]) -> dict[str, Any]:
    chosen = config.subjects
    return {
        "version": RUN_VERSION,
        "run_id": config.run_id,
        "config": {
            "run_id": config.run_id,
            "mode": config.mode,
            "datasets": list(config.datasets),
            "conditions": list(config.conditions),
            "decoders": list(config.decoders),
            "subjects": None if chosen is None else {k: sorted(int(s) for s in v) for k, v in chosen.items()},
            "processes": config.processes,
            "neurogrid_jobs": config.neurogrid_jobs,
        },
        "subjects": {dataset: list(values) for dataset, values in subjects.items()},
        "base_seed": determinism.BASE_SEED,
        "decoders": _decoder_settings(config.mode),
        "evaluation": {
            "n_folds": evaluation.N_FOLDS,
            "confidence": evaluation.CONFIDENCE,
            "bootstrap_resamples": evaluation.BOOTSTRAP_RESAMPLES,
            "session_seed": "derive_seed(dataset, subject, session)",
        },
        "versions": _versions(),
        "locks": _locks(),
        "machine": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
        "attempts": [],
    }


def _decoder_settings(mode: str) -> dict[str, Any]:
    names = (
        "COVARIANCE_ESTIMATOR",
        "CSP_FILTERS",
        "LDA_SOLVER",
        "MI_BAND_CSP_HZ",
        "SSVEP_BAND_HALF_WIDTH_HZ",
        "EEGNET_CLASS",
        "EEGNET_BAND_HZ",
        "EEGNET_SAMPLING_RATE_HZ",
        "EEGNET_MAX_EPOCHS",
        "EEGNET_VALIDATION_SHARE",
        "EEGNET_OPTIMIZER",
        "EEGNET_LEARNING_RATE",
        "EEGNET_BATCH_SIZE",
        "EEGNET_CRITERION",
        "EEGNET_SHUFFLE",
        "EEGNET_DROP_LAST",
        "EEGNET_INPUT_SCALE",
        "EEGNET_EARLY_STOPPING_MONITOR",
        "EEGNET_PATIENCE",
        "EEGNET_LOAD_BEST",
        "DEVICE",
    )
    settings: dict[str, Any] = {name.lower(): _plain(getattr(decoders, name)) for name in names}
    epochs = SMOKE_EEGNET_EPOCHS if mode == "smoke" else decoders.EEGNET_MAX_EPOCHS
    settings["eegnet_epochs_in_this_mode"] = epochs
    return settings


def _plain(value: Any) -> Any:
    return list(value) if isinstance(value, tuple) else value


def _versions() -> dict[str, str | None]:
    result: dict[str, str | None] = {"python": platform.python_version()}
    for name in ("neuroarena", *PACKAGES):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def _locks() -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for lock in (paths.PROJECT / "uv.lock", paths.REPO / "uv.lock"):
        name = lock.relative_to(paths.REPO).as_posix()
        result[name] = hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None
    return result


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def _write_json(path: Path, document: Any) -> Path:
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return records.write_atomic(path, text.encode("utf-8"))


# --- units -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Context:
    """What a worker needs besides the unit (picklable)."""

    mode: str
    run_id: str
    runs: Path
    work: Path
    neurogrid_jobs: int
    subjects: Mapping[str, tuple[int, ...]]


def _finished(unit: Unit, folder: Path, run_id: str, runs: Path) -> bool:
    try:
        document = json.loads(unit.file(folder).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if document.get("version") != RUN_VERSION:
        return False
    if unit.decoder is None:
        out = paths.neurogrid_dir(run_id, unit.dataset, unit.condition, runs)
        return (out / paths.QUALITY_FILE).is_file()
    return True


def _execute(
    executor: concurrent.futures.Executor, units: Sequence[Unit], context: _Context, folder: Path
) -> list[tuple[Unit, str]]:
    """Submit ``units`` in order, write each finished unit's file, return the failed units with their
    error (the others are kept)."""
    futures = {executor.submit(run_unit, unit, context): unit for unit in units}
    failed = []
    done = 0
    for future in concurrent.futures.as_completed(futures):
        unit = futures[future]
        done += 1
        try:
            result = future.result()
        except Exception as error:  # a failed unit must not stop the others (exit code 1)
            text = "".join(traceback.format_exception_only(error)).strip()
            failed.append((unit, text))
            print(f"[{done}/{len(units)}] {unit.id} FAILED: {text}", file=sys.stderr, flush=True)
            continue
        _write_json(unit.file(folder), {"version": RUN_VERSION, **result})
        print(f"[{done}/{len(units)}] {unit.id} ({result['seconds']:.1f} s)", file=sys.stderr, flush=True)
    order = {unit: index for index, unit in enumerate(units)}
    return sorted(failed, key=lambda item: order[item[0]])


def run_unit(unit: Unit, context: _Context) -> dict[str, Any]:
    """Run one unit (in a worker process) and return what its file holds (without the version)."""
    if context.mode != "smoke":
        datasets.configure_storage()
    spec = DATASETS[unit.dataset]
    condition = Condition.from_id(unit.condition)
    view = datasets.degraded_dataset(spec, condition, _base(spec, context.mode))
    start = time.perf_counter()
    if unit.decoder is None:
        out = paths.neurogrid_dir(context.run_id, unit.dataset, unit.condition, context.runs)
        scratch = paths.work_dir(context.run_id, unit.dataset, unit.condition, context.work)
        # An interrupted attempt may have left both: assess refuses a non-empty work folder, and the step
        # starts again from an empty output folder (quality.json, written last, marks a finished step).
        for leftover in (scratch, out):
            if leftover.exists():
                shutil.rmtree(leftover)
        out.mkdir(parents=True)
        assessed = quality.assess(
            view, spec, condition, context.subjects[unit.dataset], scratch, out, context.neurogrid_jobs
        )
        return {
            "unit": dataclasses.asdict(unit),
            "n_recordings": len(assessed.recordings),
            "n_sessions": len(assessed.sessions),
            "seconds": time.perf_counter() - start,
        }
    assert unit.subject is not None
    result = evaluate_subject(view, spec, condition, unit.decoder, unit.subject, context.mode)
    return {"unit": dataclasses.asdict(unit), **result, "seconds": time.perf_counter() - start}


def evaluate_subject(
    dataset: Any, spec: datasets.DatasetSpec, condition: Condition, decoder: str, subject: int, mode: str
) -> dict[str, Any]:
    """Both parts of a decoder unit: the epochs of ``subject`` from ``dataset`` (the degraded view) through
    ``decoders.paradigm(spec, decoder)``, then ``evaluation.evaluate_session`` in every session. Returns
    ``{"sessions": [{"session", "n_trials", "chance", "labels"}], "folds": [FoldRecord as dict]}``."""
    import numpy as np

    X, labels, metadata = decoders.paradigm(spec, decoder).get_data(
        dataset, subjects=[subject], cache_config=dict(NO_CACHE)
    )
    labels = np.asarray(labels)
    if decoder == "eegnet":
        X = np.asarray(X, dtype=np.float32)
    names = metadata["session"].astype(str).to_numpy()
    if len(names) == 0:
        raise ValueError(f"{spec.name} subject {subject}: no epochs")
    sessions, folds = [], []
    for session in sorted(set(names)):
        mask = names == session
        X_session, y_session = X[mask], labels[mask]
        key = SessionKey(spec.name, subject, session)
        seed = determinism.derive_seed(spec.name, subject, session)
        n_outputs = len(np.unique(y_session))

        def make_decoder(fold_seed: int, X_session: Any = X_session, n_outputs: int = n_outputs) -> Any:
            estimator = decoders.make(
                spec, decoder, X_session.shape[1], n_outputs, X_session.shape[2], fold_seed
            )
            if decoder == "eegnet" and mode == "smoke":
                estimator.set_params(max_epochs=SMOKE_EEGNET_EPOCHS)
            return estimator

        session_folds = evaluation.evaluate_session(
            X_session, y_session, make_decoder, key, condition, decoder, seed
        )
        classes, counts = np.unique(y_session, return_counts=True)
        sessions.append(
            {
                "session": session,
                "n_trials": int(len(y_session)),
                "chance": evaluation.chance_level(y_session),
                "labels": {str(c): int(n) for c, n in zip(classes, counts, strict=True)},
            }
        )
        folds.extend(dataclasses.asdict(record) for record in session_folds)
    return {"sessions": sessions, "folds": folds}


def _pilot_repeat(
    executor: concurrent.futures.Executor,
    config: RunConfig,
    subjects: Mapping[str, tuple[int, ...]],
    context: _Context,
    folder: Path,
) -> dict[str, Any]:
    """A-109 item 4: EEGNet once more on the first subject of every dataset (first condition of the run);
    the folds (``fit_seconds`` aside) are compared with the stored unit."""
    if "eegnet" not in config.decoders:
        return {"eegnet_repeat": []}
    units = [Unit(d, config.conditions[0], "eegnet", subjects[d][0]) for d in config.datasets]
    futures = [executor.submit(run_unit, unit, context) for unit in units]
    results = []
    for unit, future in zip(units, futures, strict=True):
        entry: dict[str, Any] = {
            "dataset": unit.dataset,
            "condition": unit.condition,
            "subject": unit.subject,
        }
        try:
            again = future.result()["folds"]
        except Exception as error:  # recorded; the run's own units are complete
            entry.update(identical=None, error="".join(traceback.format_exception_only(error)).strip())
            results.append(entry)
            continue
        stored = json.loads(unit.file(folder).read_text(encoding="utf-8"))["folds"]
        same_folds = len(stored) == len(again)
        entry.update(
            folds=len(again),
            identical=same_folds
            and all(_without_time(a) == _without_time(b) for a, b in zip(stored, again, strict=False)),
            max_trial_difference=max(
                (abs(a["n_correct"] - b["n_correct"]) for a, b in zip(stored, again, strict=False)), default=0
            ),
        )
        results.append(entry)
    return {"eegnet_repeat": results}


def _without_time(fold: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fold.items() if key != "fit_seconds"}


# --- worker processes --------------------------------------------------------------------------------------


@contextlib.contextmanager
def _environment(values: Mapping[str, str]) -> Iterator[None]:
    """Set ``values`` in ``os.environ`` for the duration (spawned children inherit it), then restore."""
    saved = {name: os.environ.get(name) for name in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _worker_start() -> None:
    determinism.check_environment()


def _worker_ready(delay: float = 0.0) -> int:
    time.sleep(delay)
    return os.getpid()


@contextlib.contextmanager
def _pool(processes: int) -> Iterator[concurrent.futures.Executor]:
    """``processes`` spawned worker processes that start with ``determinism.WORKER_ENVIRONMENT`` (inherited
    before the interpreter starts, so before numpy or torch load; PYTHONHASHSEED acts only then). A process
    pool of the spawn context starts its workers on demand, at any submit, so this process keeps the
    environment for the whole life of the pool and restores its own afterwards (this process has loaded its
    libraries already and starts no other program meanwhile). Every worker checks the environment
    (``determinism.check_environment``) before it takes a unit."""
    with _environment(determinism.WORKER_ENVIRONMENT):
        executor = concurrent.futures.ProcessPoolExecutor(
            max_workers=processes, mp_context=multiprocessing.get_context("spawn"), initializer=_worker_start
        )
        try:
            executor.submit(_worker_ready).result()  # fails early if a worker cannot start
            yield executor
        except BaseException:
            executor.shutdown(wait=True, cancel_futures=True)
            raise
        executor.shutdown(wait=True)


# --- aggregation -------------------------------------------------------------------------------------------


def _read_unit(unit: Unit, folder: Path) -> dict[str, Any] | None:
    try:
        return json.loads(unit.file(folder).read_text(encoding="utf-8"))
    except OSError:
        return None


def _write_folds(
    config: RunConfig, subjects: Mapping[str, tuple[int, ...]], folder: Path, runs: Path
) -> None:
    """folds/<dataset>/<condition>/<decoder>.csv for every cell whose subjects are all finished."""
    for dataset in config.datasets:
        for condition in config.conditions:
            for decoder in config.decoders:
                units = [_read_unit(Unit(dataset, condition, decoder, s), folder) for s in subjects[dataset]]
                if any(document is None for document in units):
                    continue
                rows = [records.FoldRecord(**fold) for document in units for fold in document["folds"]]
                if rows:
                    target = paths.folds_file(config.run_id, dataset, condition, decoder, runs)
                    records.write_csv(rows, target)


def _sessions(
    config: RunConfig, subjects: Mapping[str, tuple[int, ...]], folder: Path, runs: Path
) -> list[records.SessionRecord]:
    """One SessionRecord per dataset, condition, decoder and session, with the session's quality level
    from quality.json (``quality.read_quality``)."""
    rows = []
    for dataset in config.datasets:
        spec = DATASETS[dataset]
        for condition_id in config.conditions:
            condition = Condition.from_id(condition_id)
            levels = quality.read_quality(
                paths.neurogrid_dir(config.run_id, dataset, condition_id, runs) / paths.QUALITY_FILE
            )
            for decoder in config.decoders:
                for subject in subjects[dataset]:
                    document = _read_unit(Unit(dataset, condition_id, decoder, subject), folder)
                    assert document is not None
                    for session in document["sessions"]:
                        name = session["session"]
                        own = [f for f in document["folds"] if f["session"] == name]
                        key = SessionKey(dataset, subject, name)
                        level = levels.sessions.get(key)
                        if level is None:
                            raise RuntimeError(f"{key} missing in quality.json of {dataset} {condition_id}")
                        n_test = sum(f["n_test"] for f in own)
                        rows.append(
                            records.SessionRecord(
                                dataset=dataset,
                                paradigm=spec.paradigm,
                                condition=condition_id,
                                kind=condition.kind,
                                level=condition.level,
                                subject=subject,
                                session=name,
                                decoder=decoder,
                                n_trials=n_test,
                                accuracy=sum(f["n_correct"] for f in own) / n_test,
                                chance=session["chance"],
                                quality_level=level.level,
                                runs_without_level=level.runs_without_level,
                            )
                        )
    return rows


def _point(
    dataset: str,
    decoder: str,
    axis: str,
    kind: str,
    x: int,
    members: Sequence[records.SessionRecord],
    without: int,
) -> records.CurvePoint:
    accuracies = [row.accuracy for row in members]
    seed = determinism.derive_seed("curve", dataset, decoder, axis, kind, x)
    low, high = evaluation.bootstrap_ci(accuracies, seed)
    return records.CurvePoint(
        dataset=dataset,
        decoder=decoder,
        axis=axis,
        kind=kind,
        x=x,
        n_sessions=len(members),
        n_without_level=without,
        mean_accuracy=math.fsum(accuracies) / len(accuracies),
        ci_low=low,
        ci_high=high,
        mean_chance=math.fsum(row.chance for row in members) / len(members),
    )


if __name__ == "__main__":
    raise SystemExit(main())
