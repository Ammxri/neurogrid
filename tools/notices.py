"""Third-party notices (D-08, A-56, TECH-10): THIRD_PARTY_NOTICES.txt from the locked wheels, read statically.

The runtime packages of uv.lock are resolved for both delivery targets (CPython 3.12 on win_amd64 and on
manylinux_2_28 x86_64, A-48, A-58) and their wheels are read with zipfile only - nothing is installed, no code
of a wheel runs. Per wheel: the licence fields of METADATA, every licence file (dist-info/licenses/** after
PEP 639 and dist-info/LICENSE*, COPYING*, NOTICE*, AUTHORS*) and the extra notices that
license-gate/components.toml names. Native components (ELF or PE files that are no Python extension module,
D-08) must each be covered by a reviewed entry of components.toml, so are the non-Python components inside
wheels (deno, the BIDS validator bundle and its schemas). The parts of the offline bundle outside the wheels -
python-build-standalone and uv, pinned by the bundle data packaging/bundle_lock.json - are read the same way
(tarfile, zipfile) when that file exists. This own reader replaces pip-licenses for the notices (deviation
from A-56, recorded in A-86): pip-licenses only sees the installed packages of one platform.

Usage:
    python tools/notices.py --list                                    # runtime packages per target (offline)
    python tools/notices.py --wheelhouse DIR [--wheelhouse DIR] --out THIRD_PARTY_NOTICES.txt
    python tools/notices.py --download [--cache DIR] --out THIRD_PARTY_NOTICES.txt
    python tools/notices.py --wheelhouse DIR --check                  # the committed file is current and
    complete python tools/notices.py --wheelhouse DIR --components             # static component check only

Files come from --wheelhouse folders (file name as in uv.lock or the bundle data, SHA-256 checked), from the
bundle cache of tools/bundle.py (NEUROGRID_BUNDLE_CACHE or .local/bundle-cache, files named by their SHA-256)
or, with --download, from their pinned URLs (PyPI and the python-build-standalone releases, D-06) into a cache
(default .local/notices-wheels), size and SHA-256 checked. The network is used only with --download; this tool
is not part of the NeuroGrid package.

--check fails while license-gate/known_missing.toml lists a gap: the notices are then incomplete, and the
release workflow, which runs `--download --check`, stops (STOPP G1).

Exit codes: 0 fine, 1 outdated or incomplete notices or a component problem, 2 usage, a missing file or a
download error.
"""

from __future__ import annotations

import argparse
import email.parser
import fnmatch
import hashlib
import json
import os
import re
import sys
import tarfile
import tomllib
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from packaging.markers import Marker
from packaging.tags import Tag, compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "uv.lock"
COMPONENTS = ROOT / "license-gate" / "components.toml"
KNOWN_MISSING = ROOT / "license-gate" / "known_missing.toml"
BUNDLE_LOCK = ROOT / "packaging" / "bundle_lock.json"
NOTICES = ROOT / "THIRD_PARTY_NOTICES.txt"
DEFAULT_CACHE = ROOT / ".local" / "notices-wheels"
DEFAULT_BUNDLE_CACHE = ROOT / ".local" / "bundle-cache"
PROJECT = "neurogrid"
TIMEOUT_S = 120
DOWNLOAD_PREFIXES = (
    "https://files.pythonhosted.org/",
    "https://github.com/astral-sh/python-build-standalone/releases/download/",
)

MANYLINUX = [f"manylinux_2_{minor}_x86_64" for minor in range(28, 4, -1)]
TARGETS: dict[str, dict[str, Any]] = {
    "win_amd64": {
        "platforms": ["win_amd64"],
        "markers": {
            "sys_platform": "win32",
            "platform_system": "Windows",
            "platform_machine": "AMD64",
            "os_name": "nt",
        },
    },
    "linux_x86_64": {
        "platforms": [*MANYLINUX, "manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64"],
        "markers": {
            "sys_platform": "linux",
            "platform_system": "Linux",
            "platform_machine": "x86_64",
            "os_name": "posix",
        },
    },
}
PYTHON = {
    "python_version": "3.12",
    "python_full_version": "3.12.15",
    "implementation_name": "cpython",
    "platform_python_implementation": "CPython",
    "platform_release": "",
    "platform_version": "",
}

LICENSE_FILE = re.compile(r"^[^/]+\.dist-info/(licenses/.+|(LICEN[CS]E|COPYING|NOTICE|AUTHORS)[^/]*)$", re.I)
EXTENSION_MODULE = re.compile(r"(\.pyd|\.cpython-[^/]*\.so|\.abi3\.so)$", re.I)
NPM_SOURCE = re.compile(r"node_modules/\.deno/((?:@[^/@]+/)?[^/@]+)@([^/]+)/node_modules/")
JSR_SOURCE = re.compile(r"jsr\.io/(@[^/]+/[^/]+)/([^/]+)/")
LICENSE_HINT = re.compile(
    r"(?:SPDX-License-Identifier:\s*|@license\s+)([A-Za-z0-9.+()\- ]{2,60}?)\s*(?:\*/|\n|$)"
)
VALIDATOR = "bids-validator-deno"
VALIDATOR_MAP = "bids_validator_deno/bids-validator.js.map"
# python-build-standalone: its own licence file and the licence files of the packages it carries (pip).
PBS = "python-build-standalone"
PBS_LICENSE = re.compile(r"^python/(?:lib/python3\.\d+/)?LICENSE\.txt$")
PBS_PACKAGE_LICENSE = re.compile(
    r"^python/(?:Lib|lib/python3\.\d+)/site-packages/[^/]+\.dist-info/"
    r"(licenses/.+|(LICEN[CS]E|COPYING|NOTICE|AUTHORS)[^/]*)$",
    re.I,
)
UV = "uv"
PENDING = "Text pending owner approval (G1)"


class NoticeError(Exception):
    """A usage, file or download problem (exit 2)."""


# --- lock and targets ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LockedWheel:
    filename: str
    url: str
    sha256: str
    size: int


@dataclass(frozen=True)
class Locked:
    name: str
    version: str
    wheels: tuple[LockedWheel, ...]
    dependencies: tuple[Mapping[str, Any], ...]
    optional: Mapping[str, tuple[Mapping[str, Any], ...]]


def load_lock(path: Path = LOCK) -> tuple[dict[tuple[str, str], Locked], Mapping[str, Any]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    packages: dict[tuple[str, str], Locked] = {}
    project: Mapping[str, Any] = {}
    for entry in data["package"]:
        if entry.get("source", {}).get("editable") == "." or entry["name"] == PROJECT:
            project = entry
            continue
        wheels = tuple(
            LockedWheel(
                filename=PurePosixPath(w["url"]).name,
                url=w["url"],
                sha256=w["hash"].removeprefix("sha256:"),
                size=int(w.get("size", 0)),
            )
            for w in entry.get("wheels", [])
        )
        optional = {k: tuple(v) for k, v in entry.get("optional-dependencies", {}).items()}
        locked = Locked(
            entry["name"], entry["version"], wheels, tuple(entry.get("dependencies", [])), optional
        )
        packages[(canonicalize_name(entry["name"]), entry["version"])] = locked
    if not project:
        raise NoticeError(f"{path.name}: the project entry '{PROJECT}' is missing")
    return packages, project


def environment(target: str) -> dict[str, str]:
    return {**PYTHON, **TARGETS[target]["markers"]}


def _applies(dependency: Mapping[str, Any], env: Mapping[str, str]) -> bool:
    marker = dependency.get("marker")
    return marker is None or Marker(marker).evaluate(dict(env))


def runtime_packages(target: str, lock: Path = LOCK) -> list[Locked]:
    """The runtime closure of the project for one target: [project] dependencies only, never a dependency
    group (dev, docs), with extras and markers resolved like `uv export --no-default-groups` does."""
    packages, project = load_lock(lock)
    by_name: dict[str, list[Locked]] = {}
    for (name, _version), locked in packages.items():
        by_name.setdefault(name, []).append(locked)
    env = environment(target)
    seen: dict[str, Locked] = {}
    pending: list[tuple[Mapping[str, Any], tuple[str, ...]]] = [
        (dep, tuple(dep.get("extra", ()))) for dep in project.get("dependencies", []) if _applies(dep, env)
    ]
    expanded: set[tuple[str, str, tuple[str, ...]]] = set()
    while pending:
        dependency, extras = pending.pop()
        name = canonicalize_name(dependency["name"])
        candidates = by_name.get(name, [])
        version = dependency.get("version")
        chosen = [c for c in candidates if version is None or c.version == version]
        if len(chosen) != 1:
            raise NoticeError(f"uv.lock: dependency {name} {version or ''} is not unique")
        locked = chosen[0]
        key = (name, locked.version, tuple(sorted(extras)))
        if key in expanded:
            continue
        expanded.add(key)
        seen[name] = locked
        nested = list(locked.dependencies)
        for extra in extras:
            nested += list(locked.optional.get(extra, ()))
        for dep in nested:
            if _applies(dep, env):
                pending.append((dep, tuple(dep.get("extra", ()))))
    return sorted(seen.values(), key=lambda p: (p.name.casefold(), p.version))


def supported_tags(target: str) -> list[Tag]:
    platforms = TARGETS[target]["platforms"]
    tags = list(cpython_tags(python_version=(3, 12), abis=["cp312"], platforms=platforms))
    tags += list(compatible_tags(python_version=(3, 12), interpreter="cp312", platforms=platforms))
    return tags


def select_wheel(package: Locked, target: str) -> LockedWheel:
    """The wheel pip/uv would install on the target: the best ranked compatible tag (no-build, A-48)."""
    rank = {tag: index for index, tag in enumerate(supported_tags(target))}
    best: tuple[int, LockedWheel] | None = None
    for wheel in package.wheels:
        _name, _version, _build, tags = parse_wheel_filename(wheel.filename)
        score = min((rank[t] for t in tags if t in rank), default=None)
        if score is not None and (best is None or score < best[0]):
            best = (score, wheel)
    if best is None:
        raise NoticeError(f"{package.name} {package.version}: no wheel for {target} in uv.lock (no-build)")
    return best[1]


# --- file sources -------------------------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def find_file(filename: str, sha256: str, folders: Sequence[Path]) -> Path | None:
    """A pinned file in one of the folders, by its file name or (bundle cache) by its SHA-256."""
    for folder in folders:
        for candidate in (folder / filename, folder / sha256):
            if candidate.is_file():
                if _sha256(candidate) != sha256:
                    raise NoticeError(f"{candidate.name}: SHA-256 differs from the pinned value")
                return candidate
    return None


def find_wheel(wheel: LockedWheel, folders: Sequence[Path]) -> Path | None:
    return find_file(wheel.filename, wheel.sha256, folders)


def download_file(url: str, filename: str, sha256: str, size: int, cache: Path) -> Path:
    """Fetch one pinned file (PyPI or python-build-standalone, D-06) into the cache; size and SHA-256 are
    checked, a mismatch leaves nothing behind."""
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / filename
    if target.is_file() and _sha256(target) == sha256:
        return target
    if not url.startswith(DOWNLOAD_PREFIXES):
        raise NoticeError(f"{filename}: only pinned PyPI and python-build-standalone URLs are downloaded")
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as response, partial.open("wb") as out:  # noqa: S310
        for block in iter(lambda: response.read(1 << 20), b""):
            digest.update(block)
            out.write(block)
    if digest.hexdigest() != sha256 or (size and partial.stat().st_size != size):
        partial.unlink(missing_ok=True)
        raise NoticeError(f"{filename}: download does not match the pinned size or SHA-256")
    partial.replace(target)
    return target


def download(wheel: LockedWheel, cache: Path) -> Path:
    return download_file(wheel.url, wheel.filename, wheel.sha256, wheel.size, cache)


# --- reading a wheel ----------------------------------------------------------------------------------------


@dataclass
class WheelInfo:
    name: str
    version: str
    target: str
    filename: str
    sha256: str
    license_expression: str
    license_texts: dict[str, str]  # path inside the wheel -> LF-normalized text
    native: list[str]  # ELF/PE files that are no extension module
    paths: list[str]
    sources: list[tuple[str, str, str]] = field(default_factory=list)  # validator bundle: kind, name, version
    source_licenses: dict[tuple[str, str], str] = field(default_factory=dict)


def _text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"


def license_expression(metadata: str) -> str:
    """License-Expression (PEP 639) > License (if short) > the licence classifiers."""
    message = email.parser.Parser().parsestr(metadata, headersonly=True)
    expression = (message.get("License-Expression") or "").strip()
    if expression:
        return expression
    plain = (message.get("License") or "").strip()
    if plain and "\n" not in plain and len(plain) <= 80:
        return plain
    classifiers = [
        c.split("::")[-1].strip() for c in message.get_all("Classifier") or [] if "License ::" in c
    ]
    if classifiers:
        return "; ".join(classifiers)
    return "NOASSERTION" if not plain else "see licence text"


def _is_native(archive: zipfile.ZipFile, name: str) -> bool:
    if name.endswith("/") or EXTENSION_MODULE.search(name):
        return False
    with archive.open(name) as stream:
        head = stream.read(4)
    return head == b"\x7fELF" or head[:2] == b"MZ"


def validator_sources(
    archive: zipfile.ZipFile,
) -> tuple[list[tuple[str, str, str]], dict[tuple[str, str], str]]:
    """npm and jsr packages compiled into the BIDS validator bundle, from its source map (names, versions and
    the licence a bundled source file states, if any). The packages' own licence files are not in the
    wheel."""
    if VALIDATOR_MAP not in archive.namelist():
        return [], {}
    data = json.loads(archive.read(VALIDATOR_MAP))
    found: set[tuple[str, str, str]] = set()
    stated: dict[tuple[str, str], set[str]] = {}
    contents = data.get("sourcesContent") or []
    for index, source in enumerate(data.get("sources", [])):
        match = NPM_SOURCE.search(source)
        kind = "npm"
        if match is None:
            match = JSR_SOURCE.search(source)
            kind = "jsr"
        if match is None:
            continue
        name, version = match.group(1), match.group(2)
        found.add((kind, name, version))
        content = (contents[index] if index < len(contents) else None) or ""
        for hint in LICENSE_HINT.findall(content[:4000]):
            stated.setdefault((name, version), set()).add(hint.strip())
    licences = {key: " / ".join(sorted(values)) for key, values in stated.items()}
    return sorted(found, key=lambda x: (x[1].casefold(), x[2], x[0])), licences


def read_wheel(path: Path, package: Locked, target: str, extra_notices: Iterable[str]) -> WheelInfo:
    with zipfile.ZipFile(path) as archive:
        names = sorted(n for n in archive.namelist() if not n.endswith("/"))
        metadata_name = next((n for n in names if n.endswith(".dist-info/METADATA")), None)
        if metadata_name is None:
            raise NoticeError(f"{path.name}: no METADATA")
        expression = license_expression(archive.read(metadata_name).decode("utf-8", errors="replace"))
        texts: dict[str, str] = {}
        patterns = list(extra_notices)
        for name in names:
            if LICENSE_FILE.match(name) or any(fnmatch.fnmatchcase(name, p) for p in patterns):
                texts[name] = _text(archive.read(name))
        native = [name for name in names if _is_native(archive, name)]
        sources, source_licenses = (
            validator_sources(archive) if canonicalize_name(package.name) == VALIDATOR else ([], {})
        )
    return WheelInfo(
        name=package.name,
        version=package.version,
        target=target,
        filename=path.name,
        sha256=_sha256(path),
        license_expression=expression,
        license_texts=texts,
        native=native,
        paths=names,
        sources=sources,
        source_licenses=source_licenses,
    )


# --- parts of the offline bundle outside the wheels (packaging/bundle_lock.json) ----------------------------


@dataclass(frozen=True)
class Pinned:
    """A file of the offline bundle that tools/bundle.py takes from its pinned URL."""

    name: str  # PBS or UV
    version: str
    target: str
    url: str
    sha256: str
    size: int

    @property
    def filename(self) -> str:
        return urllib.parse.unquote(PurePosixPath(urllib.parse.urlparse(self.url).path).name)


@dataclass
class BundleInfo:
    name: str
    version: str
    target: str
    filename: str
    license_expression: str  # the wheel's metadata (uv); for python-build-standalone the reviewed entry
    license_texts: dict[str, str]
    removed: list[tuple[str, str]]  # files tools/bundle.py leaves out, with the reason


def bundle_pins(path: Path = BUNDLE_LOCK) -> tuple[list[Pinned], dict[str, list[tuple[str, str]]]]:
    """The pinned python-build-standalone archives and uv wheels per target, and the recorded removals. No
    bundle data in the checkout means no bundle parts (the bundle area provides the file)."""
    if not path.is_file():
        return [], {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format_version") != 1:
        raise NoticeError(f"{path.name}: unsupported format_version")
    python, uv = data["python"], data["uv"]
    pins = []
    for target in TARGETS:
        for name, version, entry in (
            (PBS, f"{python['version']}+{python['build']}", python["platforms"][target]),
            (UV, str(uv["version"]), uv["platforms"][target]),
        ):
            pins.append(Pinned(name, version, target, entry["url"], entry["sha256"], int(entry["size"])))
    removed = {
        target: [(str(item["path"]), str(item["reason"])) for item in data.get("remove", {}).get(target, [])]
        for target in TARGETS
    }
    return pins, removed


def read_pbs(path: Path, pin: Pinned, licence: str, removed: list[tuple[str, str]]) -> BundleInfo:
    """Licence texts of a python-build-standalone archive (tarfile, read in memory, nothing extracted)."""
    texts: dict[str, str] = {}
    with tarfile.open(path, "r:*") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            if PBS_LICENSE.match(member.name) or PBS_PACKAGE_LICENSE.match(member.name):
                stream = archive.extractfile(member)
                if stream is not None:
                    texts[member.name] = _text(stream.read())
    if not any(PBS_LICENSE.match(name) for name in texts):
        raise NoticeError(f"{path.name}: no python/LICENSE.txt in the archive")
    return BundleInfo(pin.name, pin.version, pin.target, pin.filename, licence, texts, removed)


def read_uv_wheel(path: Path, pin: Pinned) -> BundleInfo:
    with zipfile.ZipFile(path) as archive:
        names = sorted(n for n in archive.namelist() if not n.endswith("/"))
        metadata_name = next((n for n in names if n.endswith(".dist-info/METADATA")), None)
        if metadata_name is None:
            raise NoticeError(f"{path.name}: no METADATA")
        expression = license_expression(archive.read(metadata_name).decode("utf-8", errors="replace"))
        texts = {name: _text(archive.read(name)) for name in names if LICENSE_FILE.match(name)}
    return BundleInfo(pin.name, pin.version, pin.target, pin.filename, expression, texts, [])


# --- components (license-gate/components.toml) --------------------------------------------------------------


@dataclass(frozen=True)
class Component:
    dist: str
    pattern: str
    platform: str
    spdx: str
    kind: str
    notice: str
    note: str

    def applies(self, target: str) -> bool:
        return self.platform in ("any", target)


def load_components(path: Path = COMPONENTS) -> tuple[list[Component], set[str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    components = [
        Component(
            dist=str(item["dist"]),
            pattern=str(item["pattern"]),
            platform=str(item["platform"]),
            spdx=str(item["spdx"]),
            kind=str(item["kind"]),
            notice=str(item.get("notice", "")),
            note=str(item.get("note", "")),
        )
        for item in data.get("component", [])
    ]
    return components, set(data.get("native_allowed", []))


def load_known_missing(path: Path = KNOWN_MISSING) -> list[dict[str, str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return [{str(k): str(v) for k, v in item.items()} for item in data.get("missing", [])]


def spdx_units(expression: str) -> set[str]:
    """The licences of an SPDX expression; 'X WITH Y' stays one unit, so an exception is never dropped."""
    units = set()
    for part in re.split(r"\s+(?:AND|OR)\s+", re.sub(r"[()]", " ", expression).strip()):
        unit = " ".join(part.split())
        if unit:
            units.add(unit)
    return units


def bundle_component(components: Sequence[Component], name: str, version: str) -> Component | None:
    """The reviewed entry of a bundle part: dist = its name, pattern = its pinned version."""
    return next(
        (c for c in components if c.kind == "bundle" and c.dist == name and c.pattern == version), None
    )


def check_components(
    wheels: Sequence[WheelInfo],
    components: Sequence[Component],
    allowed: set[str],
    known_missing: Sequence[Mapping[str, str]],
    bundle: Sequence[BundleInfo] = (),
) -> list[str]:
    """Every native file and every non-Python component of the locked wheels is covered by a reviewed entry;
    its licence is on the native allowlist (D-08) or the entry is listed in known_missing.toml (text or
    licence pending at G1); no entry of a delivered package matches nothing (stale review); every pinned part
    of the offline bundle has a reviewed entry for exactly its version."""
    problems: list[str] = []
    pending = {item["component"] for item in known_missing}
    for wheel in wheels:
        dist = canonicalize_name(wheel.name)
        mine = [c for c in components if canonicalize_name(c.dist) == dist and c.applies(wheel.target)]
        for path in wheel.native:
            covering = [
                c for c in mine if c.kind in ("native", "bundled") and fnmatch.fnmatchcase(path, c.pattern)
            ]
            if not covering:
                problems.append(
                    f"{wheel.target}: {wheel.name} {wheel.version}: native file without review: {path}"
                )
        for component in mine:
            if not any(fnmatch.fnmatchcase(path, component.pattern) for path in wheel.paths):
                problems.append(
                    f"{wheel.target}: {wheel.name}: components.toml entry matches nothing: "
                    f"{component.pattern}"
                )
                continue
            if component.notice and not any(fnmatch.fnmatchcase(p, component.notice) for p in wheel.paths):
                problems.append(f"{wheel.target}: {wheel.name}: notice not in the wheel: {component.notice}")
            if component.kind in ("native", "bundled"):
                ids = spdx_units(component.spdx)
                key = f"{component.dist}:{component.pattern}"
                if (component.spdx == "NOASSERTION" or not ids <= allowed) and key not in pending:
                    problems.append(
                        f"{wheel.target}: {wheel.name}: licence {component.spdx} of {component.pattern} is "
                        "not on the native allowlist and not in known_missing.toml"
                    )
    for part in bundle:
        if bundle_component(components, part.name, part.version) is None:
            problems.append(
                f"{part.target}: bundle part {part.name} {part.version} has no reviewed entry in "
                "components.toml"
            )
    return problems


# --- assembling ---------------------------------------------------------------------------------------------


def collect(
    folders: Sequence[Path], *, fetch: bool, cache: Path, lock: Path = LOCK
) -> tuple[list[WheelInfo], list[str]]:
    components, _allowed = load_components()
    wheels: list[WheelInfo] = []
    missing: list[str] = []
    for target in TARGETS:
        for package in runtime_packages(target, lock):
            wheel = select_wheel(package, target)
            path = find_wheel(wheel, folders)
            if path is None and fetch:
                path = download(wheel, cache)
            if path is None:
                missing.append(wheel.filename)
                continue
            extra = [
                c.notice or c.pattern
                for c in components
                if canonicalize_name(c.dist) == canonicalize_name(package.name)
                and c.applies(target)
                and c.kind == "notice"
            ]
            wheels.append(read_wheel(path, package, target, extra))
    return wheels, missing


def bundle_cache() -> Path:
    return Path(os.environ.get("NEUROGRID_BUNDLE_CACHE") or DEFAULT_BUNDLE_CACHE)


def collect_bundle(
    folders: Sequence[Path], *, fetch: bool, cache: Path, bundle_lock: Path = BUNDLE_LOCK
) -> tuple[list[BundleInfo], list[str]]:
    """python-build-standalone and uv of the offline bundle, per target, as the bundle data pins them."""
    pins, removed = bundle_pins(bundle_lock)
    components, _allowed = load_components()
    parts: list[BundleInfo] = []
    missing: list[str] = []
    for pin in pins:
        path = find_file(pin.filename, pin.sha256, [*folders, bundle_cache()])
        if path is None and fetch:
            path = download_file(pin.url, pin.filename, pin.sha256, pin.size, cache)
        if path is None:
            missing.append(pin.filename)
            continue
        if pin.name == PBS:
            entry = bundle_component(components, PBS, pin.version)
            parts.append(
                read_pbs(path, pin, entry.spdx if entry else "NOASSERTION", removed.get(pin.target, []))
            )
        else:
            parts.append(read_uv_wheel(path, pin))
    return parts, missing


def _lock_digest(lock: Path = LOCK) -> str:
    return hashlib.sha256(lock.read_bytes()).hexdigest()


def _table(rows: Iterable[Sequence[str]], header: Sequence[str]) -> list[str]:
    rows = [list(header), *[list(r) for r in rows]]
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    lines = ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(r)).rstrip() for r in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return lines


def _repository_text(name: str) -> str | None:
    """A licence text kept in this repository (for example the report font's OFL.txt)."""
    path = ROOT / name
    return _text(path.read_bytes()) if name and path.is_file() else None


def render(
    wheels: Sequence[WheelInfo],
    components: Sequence[Component],
    known: Sequence[Mapping[str, str]],
    bundle: Sequence[BundleInfo] = (),
    lock: Path = LOCK,
) -> str:
    """Deterministic text: no date, sorted by name (casefold) and version, texts deduplicated by SHA-256."""
    out: list[str] = [
        "NeuroGrid - third-party notices",
        "",
        "Generated by tools/notices.py from the locked wheels (read statically, nothing installed).",
        f"uv.lock SHA-256: {_lock_digest(lock)}",
        f"Targets: {', '.join(TARGETS)} (CPython 3.12)",
        "",
        "NeuroGrid itself is licensed under Apache-2.0 (LICENSE, NOTICE). Its documentation and sample data",
        "are licensed under CC BY 4.0; the bundled report fonts under the SIL Open Font License 1.1",
        "(REUSE.toml).",
        "Every text below keeps its own terms.",
        "",
    ]
    by_package: dict[tuple[str, str], dict[str, WheelInfo]] = {}
    for wheel in wheels:
        by_package.setdefault((wheel.name, wheel.version), {})[wheel.target] = wheel
    ordered = sorted(by_package.items(), key=lambda item: (item[0][0].casefold(), item[0][1]))
    out += ["1. Python packages (runtime dependencies)", ""]
    rows: list[tuple[str, ...]] = []
    for (name, version), per_target in ordered:
        expressions = sorted({w.license_expression for w in per_target.values()})
        targets = ", ".join(t for t in TARGETS if t in per_target)
        rows.append((name, version, " | ".join(expressions), targets))
    out += _table(rows, ("Package", "Version", "Licence (metadata)", "Targets"))
    out += ["", "2. Native and non-Python components inside the wheels (D-08)", ""]
    rows = []
    for wheel in sorted(wheels, key=lambda w: (w.name.casefold(), w.version, w.target)):
        dist = canonicalize_name(wheel.name)
        for component in components:
            if canonicalize_name(component.dist) != dist or not component.applies(wheel.target):
                continue
            if component.kind not in ("native", "bundled"):
                continue
            matches = [p for p in wheel.paths if fnmatch.fnmatchcase(p, component.pattern)]
            for path in matches:
                rows.append((wheel.target, f"{wheel.name} {wheel.version}", path, component.spdx))
    out += _table(sorted(rows), ("Target", "Package", "File", "Licence"))
    notes = sorted(
        {(c.dist, c.pattern, c.note) for c in components if c.note and c.kind in ("native", "bundled")}
    )
    if notes:
        out += ["", "Review notes:"]
        out += [f"- {dist} {pattern}: {note}" for dist, pattern, note in notes]
    validator = [w for w in wheels if w.sources]
    if validator:
        wheel = validator[0]
        out += [
            "",
            f"3. Packages compiled into the BIDS validator bundle ({wheel.name} {wheel.version})",
            "",
            "Taken from bids-validator.js.map. The wheel carries only the validator's own MIT licence; the",
            f"licence files of these packages are not in the wheel. {PENDING}.",
            "",
        ]
        rows = [
            (kind, name, version, wheel.source_licenses.get((name, version), "not stated in the bundle"))
            for kind, name, version in wheel.sources
        ]
        out += _table(rows, ("Registry", "Package", "Version", "Licence stated in the bundled source"))
    other = [c for c in components if c.kind in ("external", "bundle", "not_distributed")]
    if other or bundle:
        out += ["", "4. Components outside the wheels", ""]
        rows = [(c.kind, c.dist, c.pattern, c.platform, c.spdx, c.notice or "-") for c in other]
        out += _table(sorted(rows), ("Kind", "Component", "Part", "Platform", "Licence", "Text"))
        out += [""] + [
            f"- {c.dist} {c.pattern}: {c.note}" for c in sorted(other, key=lambda c: (c.dist, c.pattern))
        ]
    if bundle:
        out += ["", "Offline bundle parts as pinned in packaging/bundle_lock.json:", ""]
        rows = [(p.target, p.name, p.version, p.filename, p.license_expression) for p in bundle]
        out += _table(sorted(rows), ("Target", "Component", "Version", "File", "Licence"))
        removals = sorted({(p.target, path, reason) for p in bundle for path, reason in p.removed})
        out += [
            f"- removed from the bundle ({target}): {path} - {reason}" for target, path, reason in removals
        ]
    if known:
        out += ["", "5. Known gaps (the release workflow fails while this list is not empty)", ""]
        out += [f"- {item['component']}: {item['what']} {PENDING}." for item in known]
    out += [
        "",
        "6. Licence texts",
        "",
        "Each text once (SHA-256 of the LF-normalized text), with the files that carry it.",
    ]
    texts: dict[str, tuple[str, set[str]]] = {}

    def add(text: str, user: str) -> None:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        texts.setdefault(digest, (text, set()))[1].add(user)

    for wheel in wheels:
        for path, text in wheel.license_texts.items():
            add(text, f"{wheel.name} {wheel.version} ({wheel.target}): {path}")
    for part in bundle:
        for path, text in part.license_texts.items():
            add(text, f"{part.name} {part.version} ({part.target}): {path}")
    for component in other:
        repository_text = _repository_text(component.notice) if component.kind == "external" else None
        if repository_text is not None:
            add(repository_text, f"{component.dist} ({component.platform}): {component.notice}")
    for _digest, (text, users) in sorted(texts.items(), key=lambda item: sorted(item[1][1])[0].casefold()):
        out += ["", "=" * 78]
        out += [f"Used by: {user}" for user in sorted(users, key=str.casefold)]
        out += ["-" * 78, text.rstrip()]
    return "\n".join(out).rstrip() + "\n"


def listing(lock: Path = LOCK) -> str:
    lines = []
    for target in TARGETS:
        lines.append(f"[{target}]")
        for package in runtime_packages(target, lock):
            lines.append(f"{package.name}=={package.version}  {select_wheel(package, target).filename}")
    return "\n".join(lines) + "\n"


def notice_packages(text: str) -> set[tuple[str, str]]:
    """(name, version) of section 1 of a notices text: the offline check against uv.lock."""
    section = text.split("1. Python packages (runtime dependencies)", 1)[-1].split("\n2. ", 1)[0]
    lines = [line for line in section.splitlines() if line.strip()]
    rows = [line.split() for line in lines[2:]]  # after the column header and its rule
    return {(row[0], row[1]) for row in rows if len(row) >= 2}


def locked_packages(lock: Path = LOCK) -> set[tuple[str, str]]:
    return {(p.name, p.version) for target in TARGETS for p in runtime_packages(target, lock)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--wheelhouse", action="append", type=Path, default=[])
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--bundle-lock", type=Path, default=BUNDLE_LOCK)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--components", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.list:
            sys.stdout.write(listing())
            return 0
        if not (args.out or args.check or args.components):
            parser.error("one of --list, --out, --check or --components is needed")
        wheels, missing = collect(args.wheelhouse, fetch=args.download, cache=args.cache)
        bundle, missing_parts = collect_bundle(
            args.wheelhouse, fetch=args.download, cache=args.cache, bundle_lock=args.bundle_lock
        )
        if missing or missing_parts:
            names = ", ".join(sorted([*missing, *missing_parts]))
            raise NoticeError(f"files missing (use --wheelhouse or --download): {names}")
    except NoticeError as exc:
        print(f"notices: {exc}", file=sys.stderr)
        return 2
    components, allowed = load_components()
    known = load_known_missing()
    problems = check_components(wheels, components, allowed, known, bundle)
    for problem in problems:
        print(f"component: {problem}", file=sys.stderr)
    if args.components:
        print(
            f"components: {len(problems)} problem(s) in {len(wheels)} wheels and {len(bundle)} bundle parts"
        )
        return 1 if problems else 0
    text = render(wheels, components, known, bundle)
    if args.check:
        current = NOTICES.read_text(encoding="utf-8") if NOTICES.is_file() else ""
        if current != text:
            print(f"{NOTICES.name} is outdated - run python tools/notices.py --out {NOTICES.name} ...")
            return 1
        print(f"{NOTICES.name} up to date")
        for item in known:
            print(f"incomplete: {item['component']} - {PENDING}")
        return 1 if problems or known else 0
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.out} ({len(wheels)} wheels, {len(bundle)} bundle parts)")
    return 1 if problems else 0


def iter_texts(text: str) -> Iterator[str]:
    """The licence texts of a notices file (section 6), for tests."""
    for block in text.split("\n" + "=" * 78 + "\n")[1:]:
        yield block.split("-" * 78 + "\n", 1)[-1]


if __name__ == "__main__":
    sys.exit(main())
