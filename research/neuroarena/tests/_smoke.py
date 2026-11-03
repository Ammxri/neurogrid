"""The pair of smoke runs shared by the smoke tests of areas C and D (conftest fixture ``smoke_runs``, one
pair per test session, so the CI smoke step runs it once; F11 B)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from neuroarena import runner

# Two spawned workers, both decoders, Zhou2016 and Kalunga2016, clean and line_noise-5.
SMOKE_CONFIG = runner.RunConfig(
    run_id="smoke-a",
    mode="smoke",
    datasets=("Zhou2016", "Kalunga2016"),
    conditions=("clean", "line_noise-5"),
    processes=2,
    neurogrid_jobs=2,
)


@dataclasses.dataclass(frozen=True)
class SmokeRuns:
    """Two smoke runs of SMOKE_CONFIG (``first`` is the reported run, ``second`` its repetition)."""

    first: Path
    second: Path
    work: Path


def make_smoke_runs(base: Path) -> SmokeRuns:
    """The runner twice in mode smoke with area B's real functions (synthetic.fake_dataset,
    datasets.degraded_dataset, quality.assess with NeuroGrid's command line), runs and work under ``base``."""
    runs, work = base / "runs", base / "work"
    first = runner.run(SMOKE_CONFIG, runs, work)
    second = runner.run(dataclasses.replace(SMOKE_CONFIG, run_id="smoke-b"), runs, work)
    return SmokeRuns(first=first, second=second, work=work)
