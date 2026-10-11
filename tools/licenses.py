"""Two-stage license gate (NG-N07, D-05, A-56).

Stage 1: pip-licenses --allow-only=<exact allowlist> with version-pinned, reviewed exceptions.
Stage 2: copyleft tripwire (--partial-match --fail-on GPL), also catches dual-classifier loopholes.
Runtime and development dependencies are checked in separate environments built from uv.lock.

Usage: python tools/licenses.py [--groups runtime dev]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".local" / "licenses"
UV = shutil.which("uv") or os.environ.get("UV", "uv")


def _lines(path: Path) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def _python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _environment(group: str) -> Path:
    venv = WORK / f"venv-{group}"
    requirements = WORK / f"requirements-{group}.txt"
    WORK.mkdir(parents=True, exist_ok=True)
    export = [UV, "export", "--frozen", "--no-hashes", "--no-emit-project", "--format", "requirements-txt"]
    if group == "runtime":
        export.append("--no-dev")
    requirements.write_text(
        subprocess.run(export, cwd=ROOT, check=True, capture_output=True, text=True).stdout, encoding="utf-8"
    )
    if not venv.exists():
        subprocess.run([UV, "venv", "--quiet", str(venv)], cwd=ROOT, check=True)
    subprocess.run(
        [UV, "pip", "install", "--quiet", "--python", str(_python(venv)), "-r", str(requirements)],
        cwd=ROOT,
        check=True,
    )
    return venv


def check(group: str) -> bool:
    venv = _environment(group)
    allow = ";".join(_lines(ROOT / "licenses" / "allowlist.txt"))
    exceptions = _lines(ROOT / "licenses" / "exceptions.txt")
    base = [sys.executable, "-m", "piplicenses", "--python", str(_python(venv)), "--from=mixed"]
    stage1 = base + [f"--allow-only={allow}"]
    if exceptions:
        stage1 += ["--ignore-packages", *exceptions]
    stage2 = base + ["--partial-match", "--fail-on=GPL;General Public License"]
    ok = True
    for name, command in (("allowlist", stage1), ("copyleft", stage2)):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        status = "ok" if result.returncode == 0 else "FAIL"
        print(f"{group} / {name}: {status}")
        if result.returncode != 0:
            ok = False
            print(result.stdout[-2000:], result.stderr[-2000:])
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--groups", nargs="+", default=["runtime", "dev"], choices=["runtime", "dev"])
    args = parser.parse_args()
    results = [check(group) for group in args.groups]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
