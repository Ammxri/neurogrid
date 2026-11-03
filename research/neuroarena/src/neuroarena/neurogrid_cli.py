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
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from neuroarena import paths
from neuroarena.datasets import DatasetSpec

UV = shutil.which("uv") or os.environ.get("UV", "uv")  # as tools/licenses.py of the main project
ACCEPTED_EXIT_CODES = (0, 1)
MAX_JOBS = 64  # the range of `neurogrid check --jobs`
STDERR_LINES = 20  # lines of stderr in a NeuroGridError


class NeuroGridError(RuntimeError):
    """``neurogrid check`` ended with another exit code than 0 or 1, or wrote no results file."""


def write_config(spec: DatasetSpec, path: Path) -> Path:
    """Write the research configuration of ``spec`` to ``path`` and return it: exactly

        [quality]
        min_channels = <spec.n_eeg_channels>

        [metadata.defaults]
        line_frequency_hz = <spec.line_frequency_hz>

    UTF-8, LF. Nothing else (A-101)."""
    text = (
        "[quality]\n"
        f"min_channels = {int(spec.n_eeg_channels)}\n"
        "\n"
        "[metadata.defaults]\n"
        f"line_frequency_hz = {float(spec.line_frequency_hz)!r}\n"
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def check_command(folder: Path, config: Path, out: Path, jobs: int, repo: Path = paths.REPO) -> list[str]:
    """The argument list of the call above (``UV`` first, absolute paths), for ``subprocess.run`` without a
    shell (as A-53 asks of NeuroGrid itself)."""
    if isinstance(jobs, bool) or not 1 <= jobs <= MAX_JOBS:
        raise ValueError(f"jobs must be 1-{MAX_JOBS}")
    return [
        UV,
        "run",
        "--project",
        str(Path(repo).absolute()),
        "--locked",
        "neurogrid",
        "check",
        str(Path(folder).absolute()),
        "--config",
        str(Path(config).absolute()),
        "--show-paths",
        "--jobs",
        str(jobs),
        "--out",
        str(Path(out).absolute()),
    ]


def _without_home(text: str) -> str:
    """``text`` with every spelling of the home folder replaced by ``~`` (A-51: no user path in messages)."""
    home = Path.home()
    for spelling in sorted({str(home), home.as_posix()}, key=len, reverse=True):
        text = re.sub(re.escape(spelling), "~", text, flags=re.IGNORECASE)
    return text


def _kill_tree(process: subprocess.Popen[str]) -> None:
    """End ``process`` and its children (uv starts NeuroGrid as a child; killing uv alone leaves it)."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False, timeout=60
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.kill()
    process.communicate()


def run_check(
    folder: Path, config: Path, out: Path, jobs: int, repo: Path = paths.REPO, timeout_s: float | None = None
) -> Path:
    """Run ``check_command``; return ``out`` after exit code 0 or 1 with the file written. Raise
    ``NeuroGridError`` (exit code and the last lines of stderr, no path of the user's home) otherwise. The
    child gets the environment of this process.

    A results file left from an earlier call is removed first, so only a file of this call counts. On
    ``timeout_s`` the whole process tree ends (uv and NeuroGrid) and ``NeuroGridError`` follows."""
    out = Path(out)
    command = check_command(folder, config, out, jobs, repo)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=sys.platform != "win32",
    )
    try:
        _stdout, stderr = process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        raise NeuroGridError(f"neurogrid check did not end within {timeout_s} s") from None
    code = process.returncode
    if code in ACCEPTED_EXIT_CODES and out.is_file():
        return out
    tail = "\n".join(stderr.strip().splitlines()[-STDERR_LINES:])
    what = "wrote no results file" if code in ACCEPTED_EXIT_CODES else f"ended with exit code {code}"
    raise NeuroGridError(_without_home(f"neurogrid check {what}:\n{tail}"))
