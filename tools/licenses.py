"""Two-stage license gate (NG-N07, D-05, A-56) plus the static component check (D-08), for the package and,
with --target research, for the research project research/neuroarena (A-36, A-108).

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

Research (--target research; A-108 after F10 B): its own gate with the same two stages over the runtime and
dev groups of research/neuroarena/uv.lock and its own allowlist (license-gate/research/allowlist.txt).
Exceptions are version-bound entries of license-gate/research/exceptions.toml: a package outside the
allowlist passes stage 1 only as such an entry and stage 2 only as an LGPL entry; GPL and AGPL are never
accepted, also not as an exception. The research environments are built from a pylock.toml export, which
keeps the wheel URLs of the PyTorch CPU index (A-36). The component check reads the locked research wheels of
both targets (Linux: the ubuntu-24.04 runner of research.yml, glibc 2.39) against
license-gate/research/components.toml; a native file outside its native allowlist (LGPL among them) passes
only as a version-bound exception. An exception with status "pending" passes and is printed: it waits for
the owner's decision.

Usage: python tools/licenses.py [--groups runtime dev docs]
       python tools/licenses.py --components (--wheelhouse DIR ... | --download)
       python tools/licenses.py --target research [--groups runtime dev]
       python tools/licenses.py --target research --components (--wheelhouse DIR ... | --download)
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "license-gate"
WORK = ROOT / ".local" / "licenses"
UV = shutil.which("uv") or os.environ.get("UV", "uv")
GROUPS = ("runtime", "dev", "docs")

RESEARCH = ROOT / "research" / "neuroarena"
RESEARCH_GATE = GATE / "research"
RESEARCH_GROUPS = ("runtime", "dev")
RESEARCH_WHEELS = ROOT / ".local" / "research-wheels"
# torch comes from the PyTorch CPU index (A-36, D-06); the locked wheel URLs of that index use download-r2.
RESEARCH_PREFIXES = (
    "https://files.pythonhosted.org/",
    "https://download-r2.pytorch.org/whl/cpu/",
    "https://download.pytorch.org/whl/cpu/",
)
# The Linux target of the research project is the ubuntu-24.04 runner of research.yml (glibc 2.39), where uv
# takes for example debugpy's manylinux_2_34 wheel; the package's limit (2.28, A-48) does not apply here.
RESEARCH_PLATFORMS = {
    "win_amd64": ["win_amd64"],
    "linux_x86_64": [
        *(f"manylinux_2_{minor}_x86_64" for minor in range(39, 4, -1)),
        "manylinux2014_x86_64",
        "manylinux2010_x86_64",
        "manylinux1_x86_64",
    ],
}
# The only copyleft a research exception may have (F10 B); GPL and AGPL stay forbidden.
LGPL = re.compile(r"^LGPL-(?:2\.0|2\.1|3\.0)-(?:only|or-later)$")
STATUSES = ("accepted", "pending")


def _lines(path: Path) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def _python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def export_command(group: str, research: bool = False) -> list[str]:
    """`uv export` for one group. Runtime never includes a dependency group (dev, docs). The research project
    is exported as pylock.toml with hashes: a requirements file carries no index URL for torch."""
    if research:
        base = [UV, "export", "--frozen", "--no-emit-project", "--format", "pylock.toml"]
    else:
        base = [UV, "export", "--frozen", "--no-hashes", "--no-emit-project", "--format", "requirements-txt"]
    if group == "runtime":
        return [*base, "--no-default-groups"]
    return [*base, "--only-group", group]


def _environment(group: str, research: bool = False) -> Path:
    name = f"research-{group}" if research else group
    project = RESEARCH if research else ROOT
    venv = WORK / f"venv-{name}"
    requirements = WORK / (f"pylock.{name}.toml" if research else f"requirements-{name}.txt")
    WORK.mkdir(parents=True, exist_ok=True)
    requirements.write_text(
        subprocess.run(
            export_command(group, research), cwd=project, check=True, capture_output=True, text=True
        ).stdout,
        encoding="utf-8",
    )
    if not venv.exists():
        python = ["--python", "3.12"] if research else []
        subprocess.run([UV, "venv", "--quiet", *python, str(venv)], cwd=project, check=True)
    subprocess.run(
        [UV, "pip", "sync", "--quiet", "--python", str(_python(venv)), str(requirements)],
        cwd=project,
        check=True,
    )
    return venv


# --- research exceptions (license-gate/research/exceptions.toml) -------------------------------------------


class GateError(Exception):
    """A reviewed list breaks the rules of the research gate (exit 2)."""


@dataclass(frozen=True)
class ResearchException:
    """A version-bound, reviewed exception of the research gate (A-108)."""

    kind: str  # package (the pip-licenses stages) | component (a native or bundled part of a wheel)
    name: str  # distribution name as uv.lock writes it
    version: str
    licence: str  # SPDX expression of what the exception lets pass
    status: str  # accepted | pending (waits for the owner's decision; passes and is printed)
    decision: str
    reason: str
    pattern: str = ""  # component: the pattern of its entry in license-gate/research/components.toml
    platform: str = ""  # component: win_amd64 | linux_x86_64 | any

    @property
    def lgpl(self) -> bool:
        return any(LGPL.match(unit) for unit in spdx_units(self.licence))


def spdx_units(expression: str) -> list[str]:
    """The licences of an SPDX expression; 'X WITH Y' stays one unit."""
    parts = re.split(r"\s+(?:AND|OR)\s+", re.sub(r"[()]", " ", expression).strip())
    return [" ".join(part.split()) for part in parts if part.strip()]


def load_research_exceptions(path: Path | None = None) -> list[ResearchException]:
    """The entries of license-gate/research/exceptions.toml, checked: an exact version, a known status, a
    pattern and platform for a component, and no licence with GPL in it other than LGPL (F10 B)."""
    text = (path or RESEARCH_GATE / "exceptions.toml").read_text(encoding="utf-8")
    data: dict[str, Any] = tomllib.loads(text)
    found = []
    for kind in ("package", "component"):
        for item in data.get(kind, []):
            entry = ResearchException(
                kind=kind,
                name=str(item["name"]),
                version=str(item["version"]),
                licence=str(item["licence"]),
                status=str(item["status"]),
                decision=str(item["decision"]),
                reason=str(item["reason"]),
                pattern=str(item.get("pattern", "")),
                platform=str(item.get("platform", "")),
            )
            label = f"{kind} {entry.name} {entry.version}"
            if not re.fullmatch(r"\d[\w.+!-]*", entry.version):
                raise GateError(f"{label}: the version must be exact")
            if entry.status not in STATUSES:
                raise GateError(f"{label}: status {entry.status!r} is not one of {list(STATUSES)}")
            for unit in spdx_units(entry.licence):
                if "GPL" in unit and not LGPL.match(unit):
                    raise GateError(f"{label}: {unit} is forbidden, also as an exception (F10 B)")
            if kind == "component" and not (entry.pattern and entry.platform):
                raise GateError(f"{label}: a component exception names its pattern and platform")
            found.append(entry)
    return found


def stage_commands(python: Path, research: bool = False) -> list[tuple[str, list[str]]]:
    """The two pip-licenses runs over the distributions installed for the interpreter ``python``."""
    allow = ";".join(_lines((RESEARCH_GATE if research else GATE) / "allowlist.txt"))
    base = [sys.executable, "-m", "piplicenses", "--python", str(python), "--from=mixed"]
    stage1 = base + [f"--allow-only={allow}"]
    stage2 = base + ["--partial-match", "--fail-on=GPL;General Public License"]
    if research:
        packages = [e for e in load_research_exceptions() if e.kind == "package"]
        ignored = [f"{e.name}:{e.version}" for e in packages]
        lgpl = [f"{e.name}:{e.version}" for e in packages if e.lgpl]
        if ignored:
            stage1 += ["--ignore-packages", *ignored]
        if lgpl:
            stage2 += ["--ignore-packages", *lgpl]
    else:
        exceptions = _lines(GATE / "exceptions.txt")
        if exceptions:
            stage1 += ["--ignore-packages", *exceptions]
    return [("allowlist", stage1), ("copyleft", stage2)]


def run_stages(group: str, python: Path, research: bool = False) -> bool:
    """Both stages for one environment; prints '<group> / <stage>: ok|FAIL' (and the tail of a failure)."""
    ok = True
    for name, command in stage_commands(python, research):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        status = "ok" if result.returncode == 0 else "FAIL"
        print(f"{group} / {name}: {status}")
        if result.returncode != 0:
            ok = False
            print(result.stdout[-2000:], result.stderr[-2000:])
    return ok


def check(group: str, research: bool = False) -> bool:
    label = f"research {group}" if research else group
    return run_stages(label, _python(_environment(group, research)), research)


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


# --- research components ----------------------------------------------------------------------------------


def research_wheel(package: Any, target: str) -> Any:
    """The wheel uv installs on the research target: the best ranked compatible tag (no-build)."""
    from packaging.tags import compatible_tags, cpython_tags
    from packaging.utils import parse_wheel_filename

    platforms = RESEARCH_PLATFORMS[target]
    tags = list(cpython_tags(python_version=(3, 12), abis=["cp312"], platforms=platforms))
    tags += list(compatible_tags(python_version=(3, 12), interpreter="cp312", platforms=platforms))
    rank = {tag: index for index, tag in enumerate(tags)}
    best: tuple[int, Any] | None = None
    for wheel in package.wheels:
        _name, _version, _build, wheel_tags = parse_wheel_filename(wheel.filename)
        score = min((rank[t] for t in wheel_tags if t in rank), default=None)
        if score is not None and (best is None or score < best[0]):
            best = (score, wheel)
    if best is None:
        raise GateError(f"{package.name} {package.version}: no wheel for {target} in the research lock")
    return best[1]


def research_wheels(wheelhouses: Sequence[Path], download: bool) -> tuple[list[Any], list[str]]:
    """The runtime wheels of research/neuroarena/uv.lock for both targets, read statically (nothing
    installed); downloads go to .local/research-wheels."""
    sys.path.insert(0, str(ROOT / "tools"))
    import notices

    found, missing = [], []
    for target in notices.TARGETS:
        for package in notices.runtime_packages(target, RESEARCH / "uv.lock"):
            wheel = research_wheel(package, target)
            path = notices.find_wheel(wheel, [*wheelhouses, RESEARCH_WHEELS])
            if path is None and download:
                path = notices.download(wheel, RESEARCH_WHEELS, RESEARCH_PREFIXES)
            if path is None:
                missing.append(wheel.filename)
                continue
            found.append(notices.read_wheel(path, package, target, []))
    return found, missing


def accepted_components(
    wheels: Sequence[Any], entries: Sequence[Any], exceptions: Sequence[ResearchException]
) -> tuple[list[str], list[str]]:
    """("<dist>:<pattern>" of the entries a version-bound exception accepts, problems). An exception holds
    only for exactly its version of the locked wheel, its pattern and its platform, and names the licence of
    its entry; one that matches no file of the locked wheel is stale."""
    from packaging.utils import canonicalize_name

    keys: list[str] = []
    problems: list[str] = []
    for exception in (e for e in exceptions if e.kind == "component"):
        label = f"exception {exception.name} {exception.version} {exception.pattern} ({exception.platform})"
        name = canonicalize_name(exception.name)
        entry = next(
            (
                c
                for c in entries
                if canonicalize_name(c.dist) == name
                and c.pattern == exception.pattern
                and c.platform == exception.platform
            ),
            None,
        )
        if entry is None:
            problems.append(f"{label}: no entry with this pattern and platform in components.toml")
            continue
        if entry.spdx != exception.licence:
            problems.append(f"{label}: licence {exception.licence} differs from its entry ({entry.spdx})")
            continue
        targets = RESEARCH_PLATFORMS if exception.platform == "any" else (exception.platform,)
        locked = [w for w in wheels if canonicalize_name(w.name) == name and w.target in targets]
        if not locked or any(w.version != exception.version for w in locked):
            versions = ", ".join(sorted({w.version for w in locked})) or "nothing"
            problems.append(f"{label}: the lock has {versions}; the part needs a new review")
            continue
        if not any(fnmatch.fnmatchcase(path, exception.pattern) for w in locked for path in w.paths):
            problems.append(f"{label}: matches no file of the locked wheel")
            continue
        keys.append(f"{entry.dist}:{entry.pattern}")
    return keys, problems


def research_components(wheelhouses: list[Path], download: bool) -> int:
    sys.path.insert(0, str(ROOT / "tools"))
    import notices

    try:
        exceptions = load_research_exceptions()
        wheels, missing = research_wheels(wheelhouses, download)
    except (notices.NoticeError, GateError) as exc:
        print(f"research components: {exc}")
        return 2
    if missing:
        print(f"research components: files missing (use --wheelhouse or --download): {', '.join(missing)}")
        return 2
    entries, allowed = notices.load_components(RESEARCH_GATE / "components.toml")
    keys, problems = accepted_components(wheels, entries, exceptions)
    problems += notices.check_components(
        wheels,
        entries,
        allowed,
        [],
        (),
        third_party=RESEARCH_GATE / "third_party",
        exceptions=[],
        accepted=keys,
    )
    for problem in problems:
        print(f"research components: {problem}")
    status = "FAIL" if problems else "ok"
    print(f"research components ({len(wheels)} wheels, {', '.join(notices.TARGETS)}): {status}")
    return 1 if problems else 0


def print_exceptions() -> None:
    """Every research exception with its status, so that a pending one is never silent."""
    for exception in load_research_exceptions():
        where = f" {exception.pattern} ({exception.platform})" if exception.kind == "component" else ""
        print(
            f"research exception ({exception.status}): {exception.name} {exception.version}{where}: "
            f"{exception.licence}; {exception.decision}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--groups", nargs="+", default=None, choices=GROUPS)
    parser.add_argument("--target", choices=("package", "research"), default="package")
    parser.add_argument("--components", action="store_true")
    parser.add_argument("--wheelhouse", action="append", type=Path, default=[])
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    research = args.target == "research"
    groups = args.groups or list(RESEARCH_GROUPS if research else GROUPS)
    if research and not set(groups) <= set(RESEARCH_GROUPS):
        parser.error(f"--target research has the groups {', '.join(RESEARCH_GROUPS)}")
    if not research:
        if args.components:
            return components(args.wheelhouse, args.download)
        return 0 if all([check(group) for group in groups]) else 1
    try:
        print_exceptions()
        if args.components:
            return research_components(args.wheelhouse, args.download)
        results = [check(group, research=True) for group in groups]
    except GateError as exc:
        print(f"research gate: {exc}")
        return 2
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
