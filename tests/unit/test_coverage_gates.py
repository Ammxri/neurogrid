"""tools/coverage_gates.py (NG-N08, A-23): the limits per module group, and the values as one annotation that
the public API serves without a login (TECH-05)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "coverage_gates.py"


def _run(tmp_path: Path, kernel: int, checks: int) -> subprocess.CompletedProcess[str]:
    report = {
        "files": {
            "src/neurogrid/kernel/a.py": {"summary": {"covered_lines": kernel, "num_statements": 100}},
            "src/neurogrid/checks/b.py": {"summary": {"covered_lines": checks, "num_statements": 100}},
        }
    }
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(TOOL), str(path)], capture_output=True, text=True, encoding="utf-8", check=False
    )


KERN_OK = "Kern: 95.0 % (limit 90 %) ok"
CHECKS_OK = "Prüfer: 85.0 % (limit 80 %) ok"
CHECKS_LOW = "Prüfer: 70.0 % (limit 80 %) FAIL"


@pytest.mark.parametrize(
    ("checks", "code", "lines"),
    [
        (85, 0, [KERN_OK, CHECKS_OK, f"::notice title=coverage::{KERN_OK}; {CHECKS_OK}"]),
        (70, 1, [KERN_OK, CHECKS_LOW, f"::error title=coverage::{KERN_OK}; {CHECKS_LOW}"]),
    ],
)
def test_the_gates_print_their_values_as_one_annotation(
    tmp_path: Path, checks: int, code: int, lines: list[str]
) -> None:
    run = _run(tmp_path, 95, checks)
    assert run.returncode == code, run.stderr
    assert run.stdout.splitlines() == lines


# A synthetic platform module (p6 decisions 12): lines 2-3 are one if-block marked windows, 4-6 its else-block
# marked posix, 7-8 run everywhere.
OS_MODULE = """def lock(fd):
    if sys.platform == "win32":  # platform-only: windows
        return msvcrt_lock(fd)
    else:  # platform-only: posix
        flock(fd)
        return True
def other():
    return 1
"""
OS_PATH = "src/neurogrid/vault/_os.py"


def _platform_run(
    tmp_path: Path, files: dict[str, tuple[str, dict[str, Any]]], platform: str
) -> subprocess.CompletedProcess[str]:
    """The gate in ``tmp_path`` (where the synthetic sources lie, as in the folder coverage ran in)."""
    report: dict[str, Any] = {"files": {}}
    for name, (source, data) in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(source, encoding="utf-8")
        report["files"][name] = data
    (tmp_path / "coverage.json").write_text(json.dumps(report), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(TOOL), "coverage.json", "--platform", platform],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        cwd=tmp_path,
    )


def _measured(
    executed: list[int],
    missing: list[int],
    executed_branches: list[list[int]],
    missing_branches: list[list[int]],
) -> dict[str, Any]:
    return {
        "executed_lines": executed,
        "missing_lines": missing,
        "executed_branches": executed_branches,
        "missing_branches": missing_branches,
        "summary": {
            "covered_lines": len(executed),
            "num_statements": len(executed) + len(missing),
            "covered_branches": len(executed_branches),
            "num_branches": len(executed_branches) + len(missing_branches),
        },
    }


def test_marked_blocks_cover_the_marker_line_and_the_lines_below() -> None:
    sys.path.insert(0, str(TOOL.parent))
    try:
        from coverage_gates import marked_blocks  # type: ignore[import-not-found]
    finally:
        sys.path.remove(str(TOOL.parent))
    blocks, unknown = marked_blocks(OS_MODULE)
    assert blocks == {"windows": {2, 3}, "posix": {4, 5, 6}} and unknown == []
    assert marked_blocks("x = 1  # platform-only: macos\n")[1] == [1]


def test_the_other_platforms_blocks_are_left_out(tmp_path: Path) -> None:
    """A Windows run never executes the POSIX block: without the markers the Kern gate would count it as
    missing (6 of 9 lines and branches covered); with them only the Windows lines count. The same report
    read as a POSIX run keeps the POSIX block and drops the Windows one, so its missing lines count (3 of 5;
    D-09: the Linux CI measures them)."""
    windows_run = _measured([1, 2, 3, 7, 8], [5, 6], [[2, 3]], [[2, 5]])
    run = _platform_run(tmp_path, {OS_PATH: (OS_MODULE, windows_run)}, "windows")
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.splitlines()[0] == "Kern: 100.0 % (limit 90 %) ok"
    assert "note: 3 line(s) of posix-only blocks left out (windows run)" in run.stdout
    run = _platform_run(tmp_path, {OS_PATH: (OS_MODULE, windows_run)}, "posix")
    assert run.returncode == 1 and run.stdout.splitlines()[0] == "Kern: 60.0 % (limit 90 %) FAIL"


def test_a_marker_outside_the_platform_module_fails_the_gate(tmp_path: Path) -> None:
    covered = _measured([1, 2], [], [], [])
    files = {
        OS_PATH: (OS_MODULE, _measured([1, 2, 3, 7, 8], [5, 6], [[2, 3]], [[2, 5]])),
        "src/neurogrid/vault/ledger.py": ("x = 1\ny = 2  # platform-only: posix\n", covered),
    }
    run = _platform_run(tmp_path, files, "windows")
    assert run.returncode == 1
    assert "error: platform-only marker outside neurogrid/vault/_os.py" in run.stdout
    assert "src/neurogrid/vault/ledger.py:2" in run.stdout
    files[OS_PATH] = (OS_MODULE + "z = 3  # platform-only: macos\n", files[OS_PATH][1])
    files.pop("src/neurogrid/vault/ledger.py")
    run = _platform_run(tmp_path, files, "windows")
    assert run.returncode == 1 and "_os.py:9 (unknown platform)" in run.stdout
