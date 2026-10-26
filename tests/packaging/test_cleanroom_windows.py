"""Helpers of the Windows clean room, packaging/ci/cleanroom_windows.ps1 (UF-08, V-01, A-51), each run on
its own under Windows PowerShell 5.1 with the script's ErrorActionPreference Stop. The clean room itself runs
in CI (offline.yml) and with a real bundle (tests/packaging/test_bundle_real.py, marker bundle)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "packaging" / "ci" / "cleanroom_windows.ps1"
POWERSHELL = shutil.which("powershell") if sys.platform == "win32" else None
pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell 5.1 exists only on Windows")


def _function(name: str) -> str:
    """The text of one function of the script: from `function <name>(` to the closing brace in column 0."""
    text = SCRIPT.read_text(encoding="utf-8-sig")
    (found,) = re.findall(rf"^function {name}\(.*?^}}\n", text, re.M | re.S)
    return found


def _shown(path: str, home: str | None) -> subprocess.CompletedProcess[str]:
    """Shown <path> in a PowerShell whose USERPROFILE is `home` (None: not set at all)."""
    assert POWERSHELL is not None
    env = {key: value for key, value in os.environ.items() if key.upper() != "USERPROFILE"}
    if home is not None:
        env["USERPROFILE"] = home
    script = f"$ErrorActionPreference = 'Stop'\n{_function('Shown')}Shown '{path}'\n"
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


@pytest.mark.parametrize(
    ("path", "home", "expected"),
    [
        ("C:\\Users\\x\\a b\\c", "C:\\Users\\x", '"~\\a b\\c"'),  # quoted (a space), then the home as ~
        ("C:\\Users\\x\\abc", "C:\\Users\\x\\", "~\\abc"),  # a trailing separator of the home is ignored
        ("C:\\users\\X\\abc", "C:\\Users\\x", "~\\abc"),  # Windows paths ignore case
        ("C:\\Users\\xy\\abc", "C:\\Users\\x", "C:\\Users\\xy\\abc"),  # only the whole folder name
        ("C:\\Users\\x\\a b\\c", None, '"C:\\Users\\x\\a b\\c"'),  # no USERPROFILE: no ~, no error
    ],
)
def test_shown_writes_paths_as_neurogrid_shows_them(path: str, home: str | None, expected: str) -> None:
    """The clean room compares NeuroGrid's install hint with Shown(...) of the expected paths. Without
    USERPROFILE the function used to call a method on $null, a terminating error under ErrorActionPreference
    Stop, so its own guard for a missing home folder was never reached."""
    done = _shown(path, home)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == expected
