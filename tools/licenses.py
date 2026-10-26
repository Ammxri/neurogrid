"""Two-stage license gate (NG-N07, D-05, A-56) plus the static component check (D-08).

Stage 1: pip-licenses --allow-only=<exact allowlist> with version-pinned, reviewed exceptions.
Stage 2: copyleft tripwire (--partial-match --fail-on GPL), also catches dual-classifier loopholes.
Runtime, development and documentation dependencies are checked in separate environments built from uv.lock.
The runtime set is exported with `uv export --frozen --no-default-groups --no-emit-project`: [tool.uv]
default-groups holds dev and docs, so a plain --no-dev export would carry the documentation tools into the
runtime stage (A-86).
Components: every native file and non-Python component of the locked wheels of both targets (win_amd64,
manylinux x86_64) and every pinned part of the offline bundle is covered by a reviewed entry of
license-gate/components.toml - read statically by tools/notices.py, nothing installed, so the Linux check runs
on Windows too. Missing licence texts (license-gate/known_missing.toml) stop the release through
`tools/notices.py --check`.

Usage: python tools/licenses.py [--groups runtime dev docs]
       python tools/licenses.py --components (--wheelhouse DIR ... | --download)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "license-gate"
WORK = ROOT / ".local" / "licenses"
UV = shutil.which("uv") or os.environ.get("UV", "uv")
GROUPS = ("runtime", "dev", "docs")


def _lines(path: Path) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def _python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def export_command(group: str) -> list[str]:
    """`uv export` for one group. Runtime never includes a dependency group (dev, docs)."""
    base = [UV, "export", "--frozen", "--no-hashes", "--no-emit-project", "--format", "requirements-txt"]
    if group == "runtime":
        return [*base, "--no-default-groups"]
    return [*base, "--only-group", group]


def _environment(group: str) -> Path:
    venv = WORK / f"venv-{group}"
    requirements = WORK / f"requirements-{group}.txt"
    WORK.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        subprocess.run(export_command(group), cwd=ROOT, check=True, capture_output=True, text=True).stdout,
        encoding="utf-8",
    )
    if not venv.exists():
        subprocess.run([UV, "venv", "--quiet", str(venv)], cwd=ROOT, check=True)
    subprocess.run(
        [UV, "pip", "sync", "--quiet", "--python", str(_python(venv)), str(requirements)],
        cwd=ROOT,
        check=True,
    )
    return venv


def stage_commands(python: Path) -> list[tuple[str, list[str]]]:
    """The two pip-licenses runs over the distributions installed for the interpreter ``python``."""
    allow = ";".join(_lines(GATE / "allowlist.txt"))
    exceptions = _lines(GATE / "exceptions.txt")
    base = [sys.executable, "-m", "piplicenses", "--python", str(python), "--from=mixed"]
    stage1 = base + [f"--allow-only={allow}"]
    if exceptions:
        stage1 += ["--ignore-packages", *exceptions]
    stage2 = base + ["--partial-match", "--fail-on=GPL;General Public License"]
    return [("allowlist", stage1), ("copyleft", stage2)]


def run_stages(group: str, python: Path) -> bool:
    """Both stages for one environment; prints '<group> / <stage>: ok|FAIL' (and the tail of a failure)."""
    ok = True
    for name, command in stage_commands(python):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        status = "ok" if result.returncode == 0 else "FAIL"
        print(f"{group} / {name}: {status}")
        if result.returncode != 0:
            ok = False
            print(result.stdout[-2000:], result.stderr[-2000:])
    return ok


def check(group: str) -> bool:
    return run_stages(group, _python(_environment(group)))


def components(wheelhouses: list[Path], download: bool) -> int:
    sys.path.insert(0, str(ROOT / "tools"))
    import notices  # the reader of the locked wheels (tools/notices.py)

    try:
        wheels, missing = notices.collect(wheelhouses, fetch=download, cache=notices.DEFAULT_CACHE)
        bundle, missing_parts = notices.collect_bundle(
            wheelhouses, fetch=download, cache=notices.DEFAULT_CACHE
        )
    except notices.NoticeError as exc:
        print(f"components: {exc}")
        return 2
    if missing or missing_parts:
        names = ", ".join(sorted([*missing, *missing_parts]))
        print(f"components: files missing (use --wheelhouse or --download): {names}")
        return 2
    entries, allowed = notices.load_components()
    problems = notices.check_components(wheels, entries, allowed, notices.load_known_missing(), bundle)
    for problem in problems:
        print(f"components: {problem}")
    status = "FAIL" if problems else "ok"
    print(
        f"components ({len(wheels)} wheels, {len(bundle)} bundle parts, {', '.join(notices.TARGETS)}): "
        f"{status}"
    )
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--groups", nargs="+", default=list(GROUPS), choices=GROUPS)
    parser.add_argument("--components", action="store_true")
    parser.add_argument("--wheelhouse", action="append", type=Path, default=[])
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.components:
        return components(args.wheelhouse, args.download)
    results = [check(group) for group in args.groups]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
