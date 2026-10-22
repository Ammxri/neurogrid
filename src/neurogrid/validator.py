"""BIDS validator 3.0.2 as a sandboxed deno subprocess (NG-F05, LIB-03, A-06, A-49, A-53, A-54).

The bundled validator (bids-validator-deno) runs under the deno binary from PyPI, never fetched at runtime:
- no network (``--deny-net``, ``--no-remote``, ``--no-npm``, ``--cached-only``), no update check;
- read access only to the dataset, write access only to the result file in the run's work folder;
- an environment reduced to what the bundle reads; ``BIDS_SCHEMA`` is never set and ``--schema`` never passed,
  so the bundled schema is used;
- an argument list, no shell.
Exit 0 (no issues) and 16 (issues) are results; any other exit is a tool error (exit 2, A-12).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from neurogrid.kernel.errors import NeuroGridError
from neurogrid.kernel.safety import read_limited

VALIDATOR_VERSION = "3.0.2"
# Top-level folders this validator never lists (its "ignore" defaults, compared without case; measured with
# 3.0.2). Hidden entries are not listed at any level.
VALIDATOR_IGNORED_FOLDERS = frozenset({"sourcedata", "derivatives", "code", "stimuli", "log", "doc"})
MAX_RESULT_BYTES = 500_000_000
TIMEOUT_S = 3600
# Environment variables the bundle reads (determined with a permission probe, KONZEPT 8.1); values come
# only from the sanitized environment below.
ENV_ALLOW = (
    "IGNORE_TEST_WIN32",
    "TF_BUILD",
    "CI",
    "CURSOR_TRACE_ID",
    "FORCE_HYPERLINK",
    "NETLIFY",
    "TEAMCITY_VERSION",
    "TERM_PROGRAM",
    "TERM_PROGRAM_VERSION",
    "VTE_VERSION",
    "TERM",
    "BIDS_SCHEMA",
    "NODE_DEBUG",
    "TMUX",
    "COLORTERM",
    "FORCE_COLOR",
    "NO_COLOR",
)
_PLATFORM_ENV = ("SYSTEMROOT", "WINDIR")  # Windows runtime basics


class ValidatorError(NeuroGridError):
    """The validator is missing, failed or timed out (exit 2)."""


@dataclass(frozen=True)
class ValidatorIssue:
    code: str
    sub_code: str | None
    severity: str  # error | warning | ignore
    location: str | None  # path relative to the dataset root, POSIX, without leading slash


@dataclass(frozen=True)
class ValidatorResult:
    exit_code: int
    schema_version: str | None
    issues: tuple[ValidatorIssue, ...]


def _tools() -> tuple[Path, Path]:
    try:
        import bids_validator_deno
        import deno
    except ImportError:
        raise ValidatorError("validator.missing") from None
    bundle = Path(bids_validator_deno.__file__).with_name("bids-validator.js")
    binary = Path(deno.find_deno_bin())
    if not bundle.is_file() or not binary.is_file():
        raise ValidatorError("validator.missing")
    return bundle, binary


def command(dataset: Path, result: Path, deno_binary: Path, bundle: Path) -> list[str]:
    for path in (dataset, result):
        if "," in str(path):
            raise ValidatorError("validator.comma_path")  # deno splits permission lists at commas
    return [
        str(deno_binary),
        "run",
        "--no-prompt",
        "--no-config",
        "--no-lock",
        "--no-remote",
        "--no-npm",
        "--cached-only",
        "--deny-net",
        f"--allow-read={dataset}",
        f"--allow-write={result}",
        f"--allow-env={','.join(ENV_ALLOW)}",
        "--allow-sys=osRelease",
        str(bundle),
        str(dataset),
        "--format",
        "json",
        "-o",
        str(result),
        "--max-rows",
        "-1",
    ]


def environment(work: Path) -> dict[str, str]:
    env = {
        "DENO_NO_UPDATE_CHECK": "1",
        "DENO_NO_PROMPT": "1",
        "DENO_DIR": str(work / "deno"),
        "NO_COLOR": "1",
        "TMP": str(work),
        "TEMP": str(work),
        "TMPDIR": str(work),
    }
    for name in _PLATFORM_ENV:
        if name in os.environ:
            env[name] = os.environ[name]
    return env


def parse(data: dict[str, object]) -> tuple[str | None, tuple[ValidatorIssue, ...]]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    container = data.get("issues") if isinstance(data.get("issues"), dict) else {}
    raw_issues = container.get("issues", []) if isinstance(container, dict) else []
    issues = []
    for item in raw_issues if isinstance(raw_issues, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("code"), str):
            continue
        location = item.get("location")
        issues.append(
            ValidatorIssue(
                code=item["code"],
                sub_code=item.get("subCode") if isinstance(item.get("subCode"), str) else None,
                severity=str(item.get("severity", "error")),
                location=location.strip("/") if isinstance(location, str) and location.strip("/") else None,
            )
        )
    version = summary.get("schemaVersion") if isinstance(summary, dict) else None
    return (version if isinstance(version, str) else None), tuple(issues)


def run(dataset: Path, work: Path, timeout: float = TIMEOUT_S) -> ValidatorResult:
    """Validate ``dataset``; ``work`` is the private folder of this run (A-54)."""
    bundle, binary = _tools()
    work.mkdir(parents=True, exist_ok=True)
    result = work / "validator.json"
    try:
        process = subprocess.run(
            command(dataset.resolve(), result, binary, bundle),
            capture_output=True,
            env=environment(work),
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ValidatorError("validator.timeout") from None
    except OSError:
        raise ValidatorError("validator.missing") from None
    if process.returncode not in (0, 16) or not result.is_file():
        raise ValidatorError("validator.failed", code=process.returncode)
    try:
        data = json.loads(read_limited(result, MAX_RESULT_BYTES).decode("utf-8"))
    except (OSError, ValueError, NeuroGridError):
        raise ValidatorError("validator.failed", code=process.returncode) from None
    if not isinstance(data, dict):
        raise ValidatorError("validator.failed", code=process.returncode)
    version, issues = parse(data)
    return ValidatorResult(exit_code=process.returncode, schema_version=version, issues=issues)
