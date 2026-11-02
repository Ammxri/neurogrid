"""NeuroGrid as a command line of the main project (A-101, F5a A; area B "data and quality").

NeuroArena never imports neurogrid (A-100): it runs the public command line ``neurogrid check`` from the
environment of the main project and reads the public results.json. One call per dataset and condition:

    uv run --project <repo> --locked neurogrid check <folder> --config <toml> --show-paths --jobs N
        --out <file>

``--out`` names the results file in the run folder and ``--locked`` keeps a run from rewriting the main
project's lock: both are added by the scaffold, A-101 names the rest. core is unchanged, with its default
thresholds and sample
(10 x 60 s, seed 20261011). The research configuration sets only ``[quality] min_channels`` (F5d) and
``[metadata.defaults] line_frequency_hz``; findings outside M06-M09 are ignored. Exit codes 0 (no failed
error rule) and 1 (at least one) both give a complete results.json; anything else is an error.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from neuroarena import paths
from neuroarena.datasets import DatasetSpec

UV = shutil.which("uv") or os.environ.get("UV", "uv")  # as tools/licenses.py of the main project
ACCEPTED_EXIT_CODES = (0, 1)


class NeuroGridError(RuntimeError):
    """``neurogrid check`` ended with another exit code than 0 or 1, or wrote no results file."""


def write_config(spec: DatasetSpec, path: Path) -> Path:
    """Write the research configuration of ``spec`` to ``path`` and return it: exactly

        [quality]
        min_channels = <spec.n_eeg_channels>

        [metadata.defaults]
        line_frequency_hz = <spec.line_frequency_hz>

    UTF-8, LF. Nothing else (A-101)."""
    raise NotImplementedError("area B")


def check_command(folder: Path, config: Path, out: Path, jobs: int, repo: Path = paths.REPO) -> list[str]:
    """The argument list of the call above (``UV`` first, absolute paths), for ``subprocess.run`` without a
    shell (as A-53 asks of NeuroGrid itself)."""
    raise NotImplementedError("area B")


def run_check(
    folder: Path, config: Path, out: Path, jobs: int, repo: Path = paths.REPO, timeout_s: float | None = None
) -> Path:
    """Run ``check_command``; return ``out`` after exit code 0 or 1 with the file written. Raise
    ``NeuroGridError`` (exit code and the last lines of stderr, no path of the user's home) otherwise. The
    child gets the environment of this process."""
    raise NotImplementedError("area B")
