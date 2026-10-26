"""Helpers of the Windows clean room, packaging/ci/cleanroom_windows.ps1 (UF-08, V-01, A-51), each run on
its own under Windows PowerShell 5.1 with the script's ErrorActionPreference Stop. The clean room itself runs
in CI (offline.yml) and with a real bundle (tests/packaging/test_bundle_real.py, marker bundle)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath

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


_HOME_VARIABLES = ("USERPROFILE", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA")
LOCAL = r"C:\Users\x\AppData\Local"


def _hint(prefix: str, environ: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Hint-Commands and Pdf-Hint for `prefix` in a PowerShell whose LOCALAPPDATA, USERPROFILE, HOMEDRIVE and
    HOMEPATH are exactly those of `environ` (missing ones not set at all): three lines, the Command Prompt
    command, the PowerShell command and the hint as the clean room expects it in NeuroGrid's output."""
    assert POWERSHELL is not None
    env = {key: value for key, value in os.environ.items() if key.upper() not in _HOME_VARIABLES}
    env.update(environ)
    quoted = prefix.replace("'", "''")
    script = (
        "$ErrorActionPreference = 'Stop'\n"
        "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false\n"
        f"{_function('Below')}{_function('Hint-Commands')}{_function('Pdf-Hint')}"
        f"$c = Hint-Commands '{quoted}'\n$c[0]\n$c[1]\nPdf-Hint '{quoted}'\n"
    )
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
    ("prefix", "environ"),
    [
        # below LOCALAPPDATA (install.ps1's default; it wins over the user profile), a Chinese name, a space
        (
            r"C:\Users\x\AppData\Local\安装 目录\NeuroGrid",
            {"LOCALAPPDATA": LOCAL, "USERPROFILE": r"C:\Users\x"},
        ),
        (LOCAL, {"LOCALAPPDATA": LOCAL}),  # the folder itself
        (r"C:\Users\x\abc", {"USERPROFILE": "C:\\Users\\x\\"}),  # a trailing separator of the base is ignored
        (r"C:\users\X\a$b`c", {"USERPROFILE": r"C:\Users\x"}),  # Windows paths ignore case; $ and ` escaped
        (r"C:\Users\xy\abc", {"USERPROFILE": r"C:\Users\x"}),  # only the whole folder name
        (r"D:\a\_temp\ngcr1\安装 目录\Neuro'Grid", {"USERPROFILE": r"C:\Users\x"}),  # elsewhere (CI's room)
        (r"C:\Users\x\a b\c", {}),  # no USERPROFILE and no LOCALAPPDATA: as it is, no error
        (
            r"C:\Users\x\a b\c",
            {"HOMEDRIVE": "C:", "HOMEPATH": r"\Users\x"},
        ),  # Path.home() without USERPROFILE
        (r"C:\Users\x\a b\c", {"LOCALAPPDATA": r"AppData\Local"}),  # a relative base is no base
    ],
)
def test_clean_room_expects_the_hint_neurogrid_prints(prefix: str, environ: dict[str, str]) -> None:
    """Review R07 follow-up: since the exit-2 hint for a missing PDF browser is a runnable Command Prompt and
    PowerShell command (kernel/pdf.py install_hint), the clean room has to expect exactly that. It expected
    the old 'Install it with: <~ path> <~ path>' form (Shown), which Windows no longer prints, so the
    cleanroom-windows job would have thrown 'the hint does not name the installation's PDF browser
    installer'. Hint-Commands is compared with kernel/pdf.py's own commands for the same prefix and
    variables, and Pdf-Hint with the start of the English message (errors.pdf.install.command_windows)."""
    from neurogrid.kernel import pdf
    from neurogrid.report.texts import translator

    home = environ.get("USERPROFILE") or (
        environ["HOMEDRIVE"] + environ["HOMEPATH"]
        if "HOMEDRIVE" in environ and "HOMEPATH" in environ
        else None
    )
    cmd, powershell = pdf._windows_commands(PureWindowsPath(prefix), environ, home)
    done = _hint(prefix, environ)
    assert done.returncode == 0, done.stderr
    shown_cmd, shown_powershell, hint = done.stdout.splitlines()
    assert (shown_cmd, shown_powershell) == (cmd, powershell)
    message = translator("en").t("errors.pdf.install.command_windows", cmd=cmd, powershell=powershell)
    assert hint.endswith("   (") and message.startswith(hint), (hint, message)


def test_sha256_matches_hashlib_without_get_filehash(tmp_path: Path) -> None:
    """The clean room records the archive's SHA-256 with .NET (Get-FileHash is unreachable under Windows
    PowerShell 5.1 started from PowerShell 7, see tests/packaging/test_install_ps1.py)."""
    import hashlib

    assert POWERSHELL is not None
    sample = tmp_path / "样本 file.bin"
    sample.write_bytes(bytes(range(256)) * 300)
    script = f"$ErrorActionPreference = 'Stop'\n{_function('Sha256')}Sha256 '{sample}'\n"
    done = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == hashlib.sha256(sample.read_bytes()).hexdigest()
