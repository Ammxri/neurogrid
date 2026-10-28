"""tools/coverage_gates.py (NG-N08, A-23): the limits per module group, and the values as one annotation that
the public API serves without a login (TECH-05)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
