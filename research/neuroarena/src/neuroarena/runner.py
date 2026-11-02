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
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from neuroarena import paths
from neuroarena.datasets import DATASETS
from neuroarena.decoders import DECODERS
from neuroarena.keys import CONDITIONS

# full: the approved datasets, every subject (F2 A), all 16 conditions. pilot (A-109): what the pilot
# measures before the full run (clean levels and accuracies, time per fit and per recording, EEGNet twice on
# one subject). smoke (F11 B): synthetic.fake_dataset stand-ins, no download, EEGNet with few epochs.
MODES = ("full", "pilot", "smoke")
# Scaffold choice for the smoke mode (F11 B says "EEGNet with few epochs"); fixed by area C.
SMOKE_EEGNET_EPOCHS = 2


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


def run(config: RunConfig, runs: Path = paths.RUNS, work: Path = paths.WORK) -> Path:
    """Run (or resume) ``config``; return the run folder ``paths.run_dir(config.run_id, runs)``.

    Writes run.json first (configuration, mode, versions of the locked key packages, SHA-256 of
    research/neuroarena/uv.lock and of the main project's uv.lock, ``determinism.BASE_SEED``, CPU and OS
    description, start and end time), then per dataset and condition the files of ``quality.assess`` and
    folds/<dataset>/<condition>/<decoder>.csv, at the end sessions.csv and curve.csv. Raises ValueError if
    run.json exists with another configuration."""
    raise NotImplementedError("area C")


def main(argv: Sequence[str] | None = None) -> int:
    """The command line above; exit 0 on success, 1 when a unit failed (the others are kept), 2 on a usage
    error."""
    raise NotImplementedError("area C")


if __name__ == "__main__":
    raise SystemExit(main())
