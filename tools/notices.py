"""Third-party notices (D-08, A-56, TECH-10): THIRD_PARTY_NOTICES.txt from the locked wheels, read statically.

The runtime packages of uv.lock are resolved for both delivery targets (CPython 3.12 on win_amd64 and on
manylinux_2_28 x86_64, A-48, A-58) and their wheels are read with zipfile only - nothing is installed, no code
of a wheel runs. Per wheel: the licence fields of METADATA, every licence file (dist-info/licenses/** after
PEP 639 and dist-info/LICENSE*, COPYING*, NOTICE*, AUTHORS*) and the extra notices that
license-gate/components.toml names. Native components (ELF or PE files that are no Python extension module,
D-08) must each be covered by a reviewed entry of components.toml, so are the non-Python components inside
wheels (deno, the BIDS validator bundle and its schemas). The licence texts of the npm and jsr packages
compiled into the validator bundle are not in its wheel; they were downloaded once at the versions of its
source map (D-15) and are kept with a manifest in license-gate/third_party/, which --check verifies (SHA-256,
the package set covers every entry of the source map, permissive licences, every SPDX-License-Identifier and
@license that a bundled source states anywhere is part of the reviewed licence; a licence outside the
permissive ones needs a known_missing.toml entry with the owner's decision or a version-bound exception of
components.toml, D-16). The parts of the offline
bundle outside the wheels - python-build-standalone and uv, pinned by the bundle data
packaging/bundle_lock.json - are read the same way (tarfile, zipfile) when that file exists. The documentation
site (docs/ of the bundle and of the release) is listed from its review of the locked mkdocs-material
version (license-gate/third_party/mkdocs-material-<version>/manifest.toml), which tools/build_docs.py checks
against every file of the built site. This own reader
replaces pip-licenses for the notices (deviation from A-56, recorded in A-86): pip-licenses only sees the
installed packages of one platform.

Usage:
    python tools/notices.py --list                                    # runtime packages per target (offline)
    python tools/notices.py --wheelhouse DIR [--wheelhouse DIR] --out THIRD_PARTY_NOTICES.txt
    python tools/notices.py --download [--cache DIR] --out THIRD_PARTY_NOTICES.txt
    python tools/notices.py --wheelhouse DIR --check         # the committed file is current and complete
    python tools/notices.py --wheelhouse DIR --components    # static component check only

Files come from --wheelhouse folders (file name as in uv.lock or the bundle data, SHA-256 checked), from the
bundle cache of tools/bundle.py (NEUROGRID_BUNDLE_CACHE or .local/bundle-cache, files named by their SHA-256)
or, with --download, from their pinned URLs (PyPI and the python-build-standalone releases, D-06) into a cache
(default .local/notices-wheels), size and SHA-256 checked. The network is used only with --download; this tool
is not part of the NeuroGrid package.

--check fails while license-gate/known_missing.toml lists a gap: the notices are then incomplete, and the
release workflow, which runs `--download --check`, stops (STOPP G1). The prose of the file is wrapped here
(WIDTH), so how a source string is broken never changes the output.

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
import textwrap
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
# A package that the prebuilt dist of a bundled npm package carries in its own node_modules (no version).
NESTED_SOURCE = re.compile(
    r"node_modules/\.deno/((?:@[^/@]+/)?[^/@]+)@([^/]+)/node_modules/(?:@[^/]+/)?[^/]+/"
    r"node_modules/((?:@[^/]+/)?[^/]+)/"
)
JSR_SOURCE = re.compile(r"jsr\.io/(@[^/]+/[^/]+)/([^/]+)/")
LICENSE_HINT = re.compile(
    r"(?:SPDX-License-Identifier:\s*|@license\s+)([A-Za-z0-9.+()\- ]{2,60}?)\s*(?:\*/|\n|$)"
)
# Every SPDX-License-Identifier line of a bundled source, whatever follows it: a value LICENSE_HINT cannot
# read is kept as it stands, so that it fails the review instead of going unnoticed.
SPDX_LINE = re.compile(r"SPDX-License-Identifier:[ \t]*([^\r\n]*)")
# A Node built-in polyfill that esbuild inlined ("node-modules-polyfills:node:fs/promises"): the package it
# comes from is named only by esbuild's "// node_modules/<package>/..." markers in the content (no version).
POLYFILL_SOURCE = re.compile(r"^node-modules-polyfills:")
POLYFILL_PACKAGE = re.compile(r"^// node_modules/((?:@[^/\s]+/)?[^/\s]+)/", re.M)
POLYFILL_FOUND = "in node-modules-polyfills"
# The validator's own sources (its src/ and deno.json, relative to its build folder): its wheel's licence.
OWN_SOURCE = re.compile(r"^(?:\.\./)+(?:src/\S+|deno\.json)$")
OWN = ("", "own sources")  # key of the licences that the validator's own sources state
VALIDATOR = "bids-validator-deno"
VALIDATOR_MAP = "bids_validator_deno/bids-validator.js.map"
# Licence texts of the packages compiled into the validator bundle (D-15): <folder>/bids-validator-<version>/
THIRD_PARTY = ROOT / "license-gate" / "third_party"
# Licences a package compiled into the validator bundle may have: permissive ones only. A public-domain
# dedication counts as permissive, and so does a choice of licences with at least one permissive option, of
# which the manifest names the one NeuroGrid uses (D-16, licence_policy).
BUNDLED_ALLOWED = frozenset(
    {
        "0BSD",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "CC-BY-4.0",
        "CC0-1.0",
        "ISC",
        "LicenseRef-Public-Domain",
        "MIT",
        "Zlib",
    }
)
# A components.toml notice that starts with one of these is a text kept in this repository, not in the wheel.
REPOSITORY_NOTICE = ("LICENSES/", "license-gate/")
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
WIDTH = 110  # line width of the generated prose (tables and licence texts keep their own lines)
INTRO = (
    "NeuroGrid itself is licensed under Apache-2.0 (LICENSE, NOTICE). Its documentation and sample data are "
    "licensed under CC BY 4.0; the bundled report fonts under the SIL Open Font License 1.1 (REUSE.toml)."
)
TERMS = (
    "Every text below keeps its own terms. Only NeuroGrid's own prose in this file is licensed under "
    "CC BY 4.0; the licence texts, notices and headers it reproduces word for word keep their terms and "
    "authors (LicenseRef-NeuroGrid-Reproduced-Notices in REUSE.toml and LICENSES/)."
)
VALIDATOR_INTRO = (
    "Taken from bids-validator.js.map; 'in <package>' marks a package that the prebuilt dist of that package "
    "carries, for which the map names no version. The wheel carries only the validator's own MIT licence. "
    "The licence files of these packages were taken at exactly these versions from registry.npmjs.org and "
    "jsr.io (D-15) and are kept with URL and SHA-256 in license-gate/third_party/bids-validator-{version}/"
    "manifest.toml; their texts are in section 6. Texts still missing, and licences outside the permissive "
    "ones that wait for the owner's decision ('decision: section 5'), are listed in section 5."
)
POLICY_INTRO = (
    "Permissive means: {allowed}. A public-domain dedication (LicenseRef-Public-Domain) counts as "
    "permissive, and so does a choice of licences with at least one permissive option; NeuroGrid uses the "
    "option named under 'Licence choices' (D-16)."
)
CHOICES_HEADING = "Licence choices (D-16): the permissive option NeuroGrid uses of each choice of licences."
TEXTS_INTRO = "Each text once (SHA-256 of the LF-normalized text), with the files that carry it."
EXCEPTIONS_HEADING = "Version-bound exceptions to the permissive-only policy (D-05):"
EXCEPTIONS_INTRO = (
    "Each exception holds for exactly the named package version inside exactly the named validator "
    "version; any other version fails tools/notices.py --check until it is reviewed again. NeuroGrid passes "
    "the part on unchanged, inside the unchanged bundle, which runs as a separate process (deno run). The "
    "licence texts are in section 6, and the source code stays readable in the wheel and in the offline "
    "bundle. Whoever passes the offline bundle on takes on the same obligations: keep these notices, the "
    "licence texts and the source code with it."
)


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
    unattributed: list[str] = field(default_factory=list)  # source-map entries of no package, not own code
    # validator bundle: source-map entry -> the licences it states (stated_licences), entries with any only
    source_statements: dict[str, tuple[str, ...]] = field(default_factory=dict)


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


def stated_licences(content: str) -> set[str]:
    """Every licence a bundled source states anywhere in its text, not only in its head: the @license tags
    and SPDX-License-Identifier lines that LICENSE_HINT reads, and the rest of every other
    SPDX-License-Identifier line up to a closing comment, so that no identifier is dropped."""
    found = {hint.strip() for hint in LICENSE_HINT.findall(content)}
    for value in SPDX_LINE.findall(content):
        found.add(value.split("*/", 1)[0].strip() or "(empty SPDX-License-Identifier)")
    return {hint for hint in found if hint}


def validator_sources(
    archive: zipfile.ZipFile,
) -> tuple[list[tuple[str, str, str]], dict[tuple[str, str], str], list[str]]:
    """The packages, their stated licences and the unattributed entries of read_validator_map."""
    found, licences, unattributed, _statements = read_validator_map(archive)
    return found, licences, unattributed


def read_validator_map(
    archive: zipfile.ZipFile,
) -> tuple[list[tuple[str, str, str]], dict[tuple[str, str], str], list[str], dict[str, tuple[str, ...]]]:
    """npm and jsr packages compiled into the BIDS validator bundle, from its source map (names, versions and
    the licences their bundled sources state, stated_licences), and the entries of the map that belong to no
    package and are not the validator's own code. A package inside the prebuilt dist of a bundled npm
    package has no version in the map; its version reads 'in <package>@<version>'. A Node polyfill that
    esbuild inlined belongs to the packages its markers name, as 'in node-modules-polyfills'. What the
    validator's own sources state is kept under OWN. The packages' own licence files are not in the wheel
    (license-gate/third_party keeps them, D-15). Last: each entry of the map that states a licence, with
    what it states (the location a version-bound exception names, D-16)."""
    if VALIDATOR_MAP not in archive.namelist():
        return [], {}, [], {}
    data = json.loads(archive.read(VALIDATOR_MAP))
    found: set[tuple[str, str, str]] = set()
    stated: dict[tuple[str, str], set[str]] = {}
    unattributed: list[str] = []
    statements: dict[str, tuple[str, ...]] = {}
    contents = data.get("sourcesContent") or []
    for index, source in enumerate(data.get("sources", [])):
        content = (contents[index] if index < len(contents) else None) or ""
        owners: list[tuple[str, str, str]] = []
        nested = NESTED_SOURCE.search(source)
        match = NPM_SOURCE.search(source)
        kind = "npm"
        if match is None:
            match = JSR_SOURCE.search(source)
            kind = "jsr"
        if match is not None:
            name, version = match.group(1), match.group(2)
            if nested is not None:
                name, version = nested.group(3), f"in {nested.group(1)}@{nested.group(2)}"
            owners.append((kind, name, version))
        elif POLYFILL_SOURCE.match(source):
            names = sorted(set(POLYFILL_PACKAGE.findall(content)))
            owners += [("npm", name, POLYFILL_FOUND) for name in names]
        hints = stated_licences(content)
        if hints:
            statements[source] = tuple(sorted(hints))
        if not owners:
            if OWN_SOURCE.match(source):
                stated.setdefault(OWN, set()).update(hints)
            else:
                unattributed.append(source)
            continue
        for owner in owners:
            found.add(owner)
            stated.setdefault((owner[1], owner[2]), set()).update(hints)
    licences = {key: " / ".join(sorted(values)) for key, values in stated.items() if values}
    packages = sorted(found, key=lambda x: (x[1].casefold(), x[2], x[0]))
    return packages, licences, unattributed, statements


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
        sources, source_licenses, unattributed, statements = (
            read_validator_map(archive) if canonicalize_name(package.name) == VALIDATOR else ([], {}, [], {})
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
        unattributed=unattributed,
        source_statements=statements,
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


@dataclass(frozen=True)
class BundledException:
    """A reviewed, version-bound exception to the permissive-only policy (D-05) for one part of a package
    compiled into the validator bundle (D-16): valid only for exactly this validator version, this package
    version and this source-map entry; any other version fails the check until it is reviewed again."""

    decision: str
    dist: str  # the wheel that carries the bundle
    dist_version: str
    registry: str
    package: str
    version: str
    source: str  # the source-map entry that holds the part and states its licence
    spdx: str
    component: str  # what the part is
    copyright: str
    location: str  # where the part is in the distributed files
    source_code: str  # where its source code is
    texts: tuple[str, ...]  # licence texts in this repository, attached to the package in manifest.toml
    note: str

    @property
    def label(self) -> str:
        return f"{self.registry} {self.package} {self.version} in {self.dist} {self.dist_version}"


def load_bundled_exceptions(path: Path = COMPONENTS) -> list[BundledException]:
    """The [[bundled_exception]] tables of license-gate/components.toml."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return [
        BundledException(
            decision=str(item["decision"]),
            dist=str(item["dist"]),
            dist_version=str(item["dist_version"]),
            registry=str(item["registry"]),
            package=str(item["package"]),
            version=str(item["version"]),
            source=str(item["source"]),
            spdx=str(item["spdx"]),
            component=str(item["component"]),
            copyright=str(item["copyright"]),
            location=str(item["location"]),
            source_code=str(item["source_code"]),
            texts=tuple(str(text) for text in item["texts"]),
            note=str(item.get("note", "")),
        )
        for item in data.get("bundled_exception", [])
    ]


def gap_status(item: Mapping[str, str]) -> str:
    """What a known_missing.toml entry waits for: the owner's decision it names, else the texts (PENDING)."""
    decision = item.get("decision", "").strip().rstrip(".")
    return f"{decision[:1].upper()}{decision[1:]} (G1)" if decision else PENDING


# --- licence texts of the packages inside the validator bundle (license-gate/third_party, D-15) -------------


@dataclass(frozen=True)
class BundledText:
    """One stored licence text: a file of the package folder or a text of this repository (LICENSES/)."""

    path: Path
    label: str  # the file as the manifest names it
    origin: str  # where the text comes from inside the package
    kind: str  # licence file | source header | standard text
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class LicenceChoice:
    """The option NeuroGrid uses of a choice of licences ('A OR B') in a bundled package (D-16)."""

    expression: str  # the choice as the reviewed licence states it
    chosen: str  # the permissive option NeuroGrid uses
    parts: str  # the parts of the package under that choice


@dataclass(frozen=True)
class BundledPackage:
    registry: str
    name: str
    version: str  # the exact version the texts were taken at ("" while unknown)
    found: str  # the version as the source map names it (validator_sources)
    declared: str  # the licence of the registry metadata (npm), "" if none
    spdx: str  # the reviewed licence of the texts, "" while pending
    note: str
    pending: str  # the known_missing.toml entry for missing texts, "" if none
    texts: tuple[BundledText, ...]
    # the known_missing.toml entry (with a decision) for a licence outside BUNDLED_ALLOWED, "" if none
    owner_decision: str = ""
    choices: tuple[LicenceChoice, ...] = ()
    # licences of parts whose texts are still missing (the gap 'pending'); reviewed once the texts are there
    pending_licences: tuple[str, ...] = ()

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.registry, self.name, self.found)


def validator_texts_folder(version: str, folder: Path = THIRD_PARTY) -> Path:
    return folder / f"bids-validator-{version}"


def load_validator_texts(version: str, folder: Path = THIRD_PARTY) -> list[BundledPackage] | None:
    """The reviewed packages of the validator bundle of one version, or None without a manifest."""
    base = validator_texts_folder(version, folder)
    manifest = base / "manifest.toml"
    if not manifest.is_file():
        return None
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    if data.get("version") != 1 or str(data.get("validator_version")) != version:
        raise NoticeError(f"{manifest}: unsupported version or another validator version")
    return _bundled_packages(data, base)


def _bundled_packages(data: Mapping[str, Any], base: Path) -> list[BundledPackage]:
    """The [[package]] tables of a review manifest; a text is a file below ``base`` or a repository_file."""
    packages = []
    for item in data.get("package", []):
        texts = []
        for text in item.get("text", []):
            if "repository_file" in text:
                label = str(text["repository_file"])
                path = ROOT / label
            else:
                label = str(text["file"])
                path = base / label
            texts.append(
                BundledText(
                    path=path,
                    label=label,
                    origin=str(text["origin"]),
                    kind=str(text["kind"]),
                    url=str(text.get("url", "")),
                    size=int(text["size"]),
                    sha256=str(text["sha256"]),
                )
            )
        packages.append(
            BundledPackage(
                registry=str(item["registry"]),
                name=str(item["name"]),
                version=str(item.get("version", "")),
                found=str(item.get("found") or item.get("version", "")),
                declared=str(item.get("declared", "")),
                spdx=str(item.get("spdx", "")),
                note=str(item.get("note", "")),
                pending=str(item.get("pending", "")),
                texts=tuple(texts),
                owner_decision=str(item.get("owner_decision", "")),
                choices=tuple(
                    LicenceChoice(str(c["expression"]), str(c["chosen"]), str(c.get("parts", "")))
                    for c in item.get("choice", [])
                ),
                pending_licences=tuple(str(unit) for unit in item.get("pending_licences", [])),
            )
        )
    return packages


# --- the documentation site (docs/ of the offline bundle and of the release, TECH-06) --------------------

SITE_THEME = "mkdocs-material"
# Licences a part of the documentation site may have: the permissive ones of the validator bundle and the
# font licence of the report fonts; MPL-2.0 only for a package passed on unmodified (D-05).
SITE_ALLOWED = BUNDLED_ALLOWED | frozenset({"OFL-1.1"})
SITE_MPL = "MPL-2.0"
SITE_INTRO = (
    "Built by tools/build_docs.py with {theme} {version} and reviewed in license-gate/third_party/"
    "{theme}-{version}/manifest.toml; the build fails for a file of the site that neither NeuroGrid writes "
    "itself nor this review covers, and for a licence outside the permissive ones. NeuroGrid's own parts of "
    "the site are the text of the pages (CC BY 4.0) and its style sheet, script and generated index, "
    "sitemap and schemas (Apache-2.0)."
)


@dataclass(frozen=True)
class SiteFile:
    """A glob of paths of the built site and the reviewed packages such a file contains."""

    pattern: str
    packages: tuple[str, ...]


@dataclass(frozen=True)
class SiteReview:
    """The licence review of the documentation site for one theme version (manifest.toml)."""

    theme: str
    version: str
    folder: Path
    packages: tuple[BundledPackage, ...]
    files: tuple[SiteFile, ...]
    pruned: tuple[str, ...]
    unmodified: frozenset[str]  # packages under MPL-2.0 that the site passes on unchanged (D-05)
    installed: Mapping[str, str]  # stored text -> the file of the installed theme it was copied from


def site_glob(pattern: str) -> re.Pattern[str]:
    """A glob of a site path: '**/' any number of folders, '**' anything, '*' anything but '/'."""
    out, index = "", 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out, index = out + "(?:.*/)?", index + 3
        elif pattern.startswith("**", index):
            out, index = out + ".*", index + 2
        elif pattern[index] == "*":
            out, index = out + "[^/]*", index + 1
        else:
            out, index = out + re.escape(pattern[index]), index + 1
    return re.compile(out)


def locked_version(name: str, lock: Path = LOCK) -> str | None:
    """The version of ``name`` in uv.lock (any group), None if it is not locked or not unique."""
    packages, _project = load_lock(lock)
    versions = {version for (locked, version) in packages if locked == canonicalize_name(name)}
    return versions.pop() if len(versions) == 1 else None


def site_review_folder(version: str, folder: Path = THIRD_PARTY) -> Path:
    return folder / f"{SITE_THEME}-{version}"


def load_site_review(version: str | None, folder: Path = THIRD_PARTY) -> SiteReview | None:
    """The licence review of the documentation site built with ``SITE_THEME`` ``version``, or None."""
    if not version:
        return None
    base = site_review_folder(version, folder)
    manifest = base / "manifest.toml"
    if not manifest.is_file():
        return None
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    if data.get("version") != 1 or data.get("theme") != SITE_THEME or data.get("theme_version") != version:
        raise NoticeError(f"{manifest}: unsupported version or another theme version")
    installed = {
        str(text["file"]): str(text["installed"])
        for item in data.get("package", [])
        for text in item.get("text", [])
        if "installed" in text and "file" in text
    }
    return SiteReview(
        theme=SITE_THEME,
        version=version,
        folder=base,
        packages=tuple(_bundled_packages(data, base)),
        files=tuple(
            SiteFile(str(item["pattern"]), tuple(str(name) for name in item["packages"]))
            for item in data.get("site_file", [])
        ),
        pruned=tuple(str(pattern) for pattern in data.get("pruned", [])),
        unmodified=frozenset(str(item["name"]) for item in data.get("package", []) if item.get("unmodified")),
        installed=installed,
    )


def site_licence_problems(package: BundledPackage, review: SiteReview) -> list[str]:
    """A licence of a site package outside SITE_ALLOWED (MPL-2.0 only unmodified, D-05)."""
    outside = spdx_units(package.spdx) - SITE_ALLOWED
    if package.name in review.unmodified:
        outside -= {SITE_MPL}
    return (
        [
            f"licence {package.spdx} is not permissive"
            + (" (MPL-2.0 needs unmodified = true)" if SITE_MPL in outside else "")
        ]
        if outside
        else []
    )


# A file of this repository that the own prose of the notices names (notes of the manifests and of
# components.toml): only the two top-level folders that hold no third-party sources, so the paths quoted from
# the bundled sources (src/..., tools/...) are not taken for files of NeuroGrid.
REPOSITORY_PATH = re.compile(r"(?<![\w./@-])(?:LICENSES|license-gate)/[\w@.+\-/]*\w")


def missing_repository_paths(text: str, root: Path = ROOT) -> list[str]:
    """The repository paths named in ``text`` (REPOSITORY_PATH) that do not exist under ``root``, sorted:
    a note still naming a text after it was moved (R27)."""
    named = set(REPOSITORY_PATH.findall(text))
    return sorted(path for path in named if not (root / path).exists())


def check_site_review(review: SiteReview | None, known_missing: Sequence[Mapping[str, str]]) -> list[str]:
    """The review of the documentation site: every package has its texts (recorded SHA-256 and size) or a
    known_missing.toml entry, a reviewed licence that is permissive (site_licence_problems) unless that entry
    waits for it, and is part of a site file; every site file names reviewed packages only."""
    if review is None:
        return [f"documentation site: no licence review of {SITE_THEME} (license-gate/third_party)"]
    where = f"documentation site ({review.theme} {review.version})"
    pending = {item["component"] for item in known_missing}
    problems: list[str] = []
    names = {package.name for package in review.packages}
    used = {name for item in review.files for name in item.packages}
    for item in review.files:
        for name in sorted(set(item.packages) - names):
            problems.append(f"{where}: {item.pattern} names {name}, which the review does not list")
    for package in review.packages:
        label = f"{where}: {package.registry} {package.name} {package.version or package.found}"
        if package.name not in used:
            problems.append(f"{label}: part of no site file (stale review)")
        if package.pending and package.pending not in pending:
            problems.append(f"{label}: '{package.pending}' is not listed in known_missing.toml")
        if not package.texts and not package.pending:
            problems.append(f"{label}: no licence text and no known_missing.toml entry")
        if not package.spdx and not package.pending:
            problems.append(f"{label}: no reviewed licence and no known_missing.toml entry")
        problems += [f"{label}: {problem}" for problem in site_licence_problems(package, review)]
        for text in package.texts:
            if not text.path.is_file():
                problems.append(f"{label}: licence text missing: {text.label}")
                continue
            data = text.path.read_bytes()
            if hashlib.sha256(data).hexdigest() != text.sha256 or len(data) != text.size:
                problems.append(f"{label}: SHA-256 or size of {text.label} differs from manifest.toml")
    return problems


def _site_lines(review: SiteReview) -> list[str]:
    """The documentation site in section 4: its packages with licence, texts and site files."""
    out = [
        "",
        f"Documentation site (docs/ of the offline bundle and of the release, {review.theme} "
        f"{review.version}):",
        "",
        *paragraph(SITE_INTRO.format(theme=review.theme, version=review.version)),
        "",
    ]
    rows = [
        (p.registry, p.name, p.version or p.found, p.spdx or "pending (section 5)", _text_kinds(p))
        for p in review.packages
    ]
    out += _table(rows, ("Kind", "Part", "Version", "Licence", "Licence texts"))
    out += ["", "Files of the site and the parts they contain:"]
    out += [f"- {item.pattern}: {', '.join(item.packages)}" for item in review.files]
    out += ["", "Review notes (manifest.toml):"]
    out += [f"- {p.registry} {p.name} {p.version or p.found}: {p.note}" for p in review.packages if p.note]
    if review.pruned:
        out += [
            f"- not shipped: {', '.join(review.pruned)} - removed by tools/build_docs.py after the build "
            "(the lunr language files of lunr-languages, tinyseg and wordcut, which the English-only search "
            "never loads, and the source maps)"
        ]
    return out


def check_validator_texts(
    wheel: WheelInfo,
    packages: Sequence[BundledPackage] | None,
    known_missing: Sequence[Mapping[str, str]],
    allowed: Iterable[str] = BUNDLED_ALLOWED,
    exceptions: Sequence[BundledException] = (),
) -> list[str]:
    """The reviewed licence texts cover exactly the packages of the validator's source map: every entry of the
    map belongs to a package or to the validator's own code (or is a listed gap), every stored text has its
    recorded SHA-256 and size, every licence is permissive (BUNDLED_ALLOWED) or waits for the owner's
    decision in known_missing.toml, every licence a bundled source states is part of the reviewed one (of a
    package still without texts: permissive; of the validator's own code: its wheel's licence), and a package
    without texts names its known_missing.toml entry. A licence outside the permissive ones may also be
    covered by a version-bound exception (check_exceptions, D-16)."""
    where = f"{wheel.target}: {wheel.name} {wheel.version}"
    if packages is None:
        return [
            f"{where}: no reviewed licence texts (license-gate/third_party/bids-validator-{wheel.version})"
        ]
    problems, excused = check_exceptions(wheel, packages, exceptions)
    pending = {item["component"] for item in known_missing}
    decisions = {item["component"] for item in known_missing if item.get("decision", "").strip()}
    permitted = set(allowed)
    reviewed = {package.key: package for package in packages}
    sources = set(wheel.sources)
    for source in wheel.unattributed:
        if f"{wheel.name}:{source}" not in pending:
            problems.append(f"{where}: source-map entry of no package and not the validator's own: {source}")
    own = spdx_units(wheel.license_expression)
    for hint in (h.strip() for h in wheel.source_licenses.get(OWN, "").split(" / ") if h.strip()):
        if not spdx_units(hint) <= own:
            problems.append(
                f"{where}: an own source states {hint}, the wheel says {wheel.license_expression}"
            )
    for kind, name, version in sorted(sources - set(reviewed)):
        problems.append(f"{where}: bundled package without review: {kind} {name} {version}")
    for kind, name, version in sorted(set(reviewed) - sources):
        problems.append(
            f"{where}: reviewed package not in the bundle (stale review): {kind} {name} {version}"
        )
    for package in packages:
        label = f"{where}: {package.registry} {package.name} {package.version or package.found}"
        if not package.texts and not package.pending:
            problems.append(f"{label}: no licence text and no known_missing.toml entry")
        if package.pending and package.pending not in pending:
            problems.append(f"{label}: '{package.pending}' is not listed in known_missing.toml")
        if package.texts and not package.spdx:
            problems.append(f"{label}: licence texts without a reviewed licence")
        units = spdx_units(package.spdx)
        outside, policy = licence_policy(package, permitted)
        outside -= excused.get(package.key, set())
        problems += [f"{label}: {problem}" for problem in policy]
        if outside and not package.owner_decision:
            problems.append(f"{label}: licence {package.spdx} is not permissive (not in BUNDLED_ALLOWED)")
        if package.owner_decision and package.owner_decision not in decisions:
            problems.append(
                f"{label}: licence {package.spdx}: '{package.owner_decision}' is not listed with a decision "
                "in known_missing.toml"
            )
        stated = wheel.source_licenses.get((package.name, package.found), "")
        for hint in (h.strip() for h in stated.split(" / ") if h.strip()):
            if package.spdx and not spdx_units(hint) <= units:
                problems.append(f"{label}: a bundled source states {hint}, the review says {package.spdx}")
            elif not package.spdx and not (package.pending and spdx_units(hint) <= permitted):
                problems.append(f"{label}: a bundled source states {hint}, there is no reviewed licence")
        for text in package.texts:
            if not text.path.is_file():
                problems.append(f"{label}: licence text missing: {text.label}")
                continue
            data = text.path.read_bytes()
            if hashlib.sha256(data).hexdigest() != text.sha256 or len(data) != text.size:
                problems.append(f"{label}: SHA-256 or size of {text.label} differs from manifest.toml")
    return problems


def check_exceptions(
    wheel: WheelInfo, packages: Sequence[BundledPackage], exceptions: Sequence[BundledException]
) -> tuple[list[str], dict[tuple[str, str, str], set[str]]]:
    """The version-bound exceptions of the validator wheel (D-16) and the licences each one excuses, by
    package key. An exception holds only while the wheel has its version, the bundle carries the package
    at its version, the licence is stated in exactly its source-map entry and nowhere else, the review of
    the package names the licence and the package carries the licence texts it names; otherwise it is a
    problem (an upgrade needs a new review) and excuses nothing."""
    where = f"{wheel.target}: {wheel.name} {wheel.version}"
    problems: list[str] = []
    excused: dict[tuple[str, str, str], set[str]] = {}
    reviewed = {(p.registry, p.name, p.version): p for p in packages if p.version}
    sources = set(wheel.sources)
    for exception in exceptions:
        if canonicalize_name(exception.dist) != canonicalize_name(wheel.name):
            continue
        tag = f"{where}: exception {exception.decision} for {exception.label} ({exception.spdx})"
        if exception.dist_version != wheel.version:
            problems.append(f"{tag} does not hold for {wheel.name} {wheel.version}: review it again")
            continue
        package = reviewed.get((exception.registry, exception.package, exception.version))
        if package is None or package.key not in sources:
            problems.append(f"{tag}: the bundle carries no {exception.package} {exception.version}")
            continue
        before = len(problems)
        units = spdx_units(exception.spdx)
        if not units or not units <= spdx_units(package.spdx):
            problems.append(f"{tag}: the review of the package says {package.spdx}")
        stating = sorted(
            source
            for source, hints in wheel.source_statements.items()
            if any(units & spdx_units(hint) for hint in hints)
        )
        if stating != [exception.source]:
            problems.append(
                f"{tag}: the licence is stated in {', '.join(stating) or 'no source'}, "
                f"the exception names {exception.source}"
            )
        attached = {text.label for text in package.texts} | {_repository_path(t.path) for t in package.texts}
        if not exception.texts:
            problems.append(f"{tag}: names no licence text")
        for name in exception.texts:
            if name not in attached or not (ROOT / name).is_file():
                problems.append(f"{tag}: licence text {name} is not attached to the package in manifest.toml")
        if len(problems) == before:
            excused.setdefault(package.key, set()).update(units)
    return problems, excused


def _repository_path(path: Path) -> str:
    """``path`` relative to the repository (POSIX), or as it is when it lies outside."""
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def licence_policy(package: BundledPackage, permitted: Iterable[str]) -> tuple[set[str], list[str]]:
    """The licences of a bundled package outside the permissive policy, and what is wrong with its choices
    and pending licences. D-16: a choice of licences ('A OR B') with at least one permissive option counts
    as permissive, and the manifest names the permissive option NeuroGrid uses; a licence of parts whose
    texts are still missing (pending_licences) waits with the package's text gap instead."""
    allowed = set(permitted)
    try:
        clauses = spdx_clauses(package.spdx)
    except ValueError as exc:
        return spdx_units(package.spdx) - allowed, [f"licence {package.spdx} is no SPDX expression ({exc})"]
    problems: list[str] = []
    outside: set[str] = set()
    recorded: dict[frozenset[str], LicenceChoice] = {}
    for choice in package.choices:
        try:
            (options,) = spdx_clauses(choice.expression)
        except ValueError:
            options = frozenset()
        if len(options) < 2:
            problems.append(f"recorded choice {choice.expression} is no choice of licences")
            continue
        recorded[options] = choice
    single = {unit for clause in clauses if len(clause) == 1 for unit in clause}
    for clause in clauses:
        if len(clause) == 1:
            outside |= clause - allowed
            continue
        if not clause & allowed:
            outside |= clause  # a choice without a permissive option is not permissive
            continue
        named = recorded.get(clause)
        expression = " OR ".join(sorted(clause))
        if named is None:
            problems.append(f"the choice {expression} names no chosen permissive option (D-16)")
        elif named.chosen not in clause & allowed:
            problems.append(f"{named.chosen} is no permissive option of the choice {expression}")
    for key, named in recorded.items():
        if key not in clauses:
            problems.append(f"recorded choice {named.expression} is not part of the licence {package.spdx}")
    pending = set(package.pending_licences)
    if pending and not package.pending:
        problems.append("pending_licences without a gap for the missing texts (pending)")
    for unit in sorted(pending - single):
        problems.append(f"pending licence {unit} is not part of the licence {package.spdx}")
    if package.pending:
        outside -= pending
    return outside, problems


def spdx_clauses(expression: str) -> list[frozenset[str]]:
    """An SPDX expression as the clauses that must all hold (AND), each the set of licences it may be
    chosen from (OR; one licence for a plain term); 'X WITH Y' stays one licence. '' has no clause. A
    malformed expression raises ValueError."""
    tokens = re.findall(r"[()]|[^\s()]+", expression)
    position = 0

    def peek() -> str:
        return tokens[position] if position < len(tokens) else ""

    def take() -> str:
        nonlocal position
        token = peek()
        position += 1
        return token

    def any_of() -> list[frozenset[str]]:
        clauses = all_of()
        while peek() == "OR":
            take()
            right = all_of()
            clauses = [left | other for left in clauses for other in right]
        return clauses

    def all_of() -> list[frozenset[str]]:
        clauses = term()
        while peek() == "AND":
            take()
            clauses = clauses + term()
        return clauses

    def term() -> list[frozenset[str]]:
        token = take()
        if token == "(":
            clauses = any_of()
            if take() != ")":
                raise ValueError("unbalanced parentheses")
            return clauses
        if token in ("", ")", "AND", "OR", "WITH"):
            raise ValueError(f"licence expected, found {token or 'the end'}")
        if peek() == "WITH":
            take()
            exception = take()
            if exception in ("", "(", ")", "AND", "OR", "WITH"):
                raise ValueError("exception expected after WITH")
            token = f"{token} WITH {exception}"
        return [frozenset({token})]

    if not tokens:
        return []
    found = any_of()
    if position != len(tokens):
        raise ValueError(f"unexpected {tokens[position]}")
    unique: list[frozenset[str]] = []
    for clause in found:
        if clause not in unique:
            unique.append(clause)
    return unique


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
    third_party: Path = THIRD_PARTY,
    exceptions: Sequence[BundledException] | None = None,
) -> list[str]:
    """Every native file and every non-Python component of the locked wheels is covered by a reviewed entry;
    its licence is on the native allowlist (D-08) or the entry is listed in known_missing.toml (text or
    licence pending at G1); no entry of a delivered package matches nothing (stale review); every pinned part
    of the offline bundle has a reviewed entry for exactly its version; the packages compiled into the
    validator bundle have their reviewed licence texts (check_validator_texts, with the version-bound
    exceptions of components.toml unless others are given)."""
    problems: list[str] = []
    pending = {item["component"] for item in known_missing}
    if exceptions is None:
        exceptions = load_bundled_exceptions()
    checked: set[tuple[str, str]] = set()
    for wheel in wheels:
        if wheel.sources and (wheel.name, wheel.version) not in checked:
            checked.add((wheel.name, wheel.version))  # the same pure-Python wheel serves both targets
            texts = load_validator_texts(wheel.version, third_party)
            problems += check_validator_texts(wheel, texts, known_missing, exceptions=exceptions)
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
            if component.notice.startswith(REPOSITORY_NOTICE):
                if not (ROOT / component.notice).is_file():
                    problems.append(
                        f"{wheel.target}: {wheel.name}: notice not in the repository: {component.notice}"
                    )
            elif component.notice and not any(fnmatch.fnmatchcase(p, component.notice) for p in wheel.paths):
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


def paragraph(text: str) -> list[str]:
    """One paragraph of the notices, wrapped at WIDTH; runs of white space count as one space."""
    return textwrap.wrap(" ".join(text.split()), width=WIDTH, break_long_words=False, break_on_hyphens=False)


def _lock_digest(lock: Path = LOCK) -> str:
    return hashlib.sha256(lock.read_bytes()).hexdigest()


def _table(rows: Iterable[Sequence[str]], header: Sequence[str]) -> list[str]:
    rows = [list(header), *[list(r) for r in rows]]
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    lines = ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(r)).rstrip() for r in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return lines


def _text_kinds(package: BundledPackage) -> str:
    """The stored texts of a bundled package in a few words, for the table of section 3."""
    if not package.texts:
        return "missing (section 5)"
    counts: dict[str, int] = {}
    for item in package.texts:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    parts = []
    for kind, count in counts.items():
        parts.append(kind if count == 1 else f"{count} {kind}s")
    return ", ".join(parts)


def _repository_text(name: str) -> str | None:
    """A licence text kept in this repository (for example the report font's OFL.txt)."""
    path = ROOT / name
    return _text(path.read_bytes()) if name and path.is_file() else None


def _exception_lines(exception: BundledException) -> list[str]:
    """One version-bound exception for the notices: component, licence, copyright, location, source code
    and the licence texts."""
    head = (
        f"- {exception.label}, licence {exception.spdx}, decision {exception.decision} "
        f"(source-map entry {exception.source})"
    )
    fields = [
        ("Component", exception.component),
        ("Copyright", exception.copyright),
        ("Location", exception.location),
        ("Source code", exception.source_code),
        ("Licence texts", f"{', '.join(exception.texts)} (section 6)"),
    ]
    if exception.note:
        fields.append(("Note", exception.note))
    lines = textwrap.wrap(head, width=WIDTH, subsequent_indent="  ", break_long_words=False)
    for name, value in fields:
        lines += textwrap.wrap(
            " ".join(f"{name}: {value}".split()),
            width=WIDTH,
            initial_indent="  ",
            subsequent_indent="    ",
            break_long_words=False,
            break_on_hyphens=False,
        )
    return lines


def render(
    wheels: Sequence[WheelInfo],
    components: Sequence[Component],
    known: Sequence[Mapping[str, str]],
    bundle: Sequence[BundleInfo] = (),
    lock: Path = LOCK,
    third_party: Path = THIRD_PARTY,
    exceptions: Sequence[BundledException] | None = None,
    site: SiteReview | None = None,
) -> str:
    """Deterministic text: no date, sorted by name (casefold) and version, texts deduplicated by SHA-256.
    The version-bound exceptions are those of components.toml unless others are given; the documentation
    site is the review of the locked theme version in ``third_party`` unless one is given."""
    if exceptions is None:
        exceptions = load_bundled_exceptions()
    if site is None:
        site = load_site_review(locked_version(SITE_THEME, lock), third_party)
    out: list[str] = [
        "NeuroGrid - third-party notices",
        "",
        "Generated by tools/notices.py from the locked wheels (read statically, nothing installed).",
        f"uv.lock SHA-256: {_lock_digest(lock)}",
        f"Targets: {', '.join(TARGETS)} (CPython 3.12)",
        "",
        *paragraph(INTRO),
        *paragraph(TERMS),
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
    bundled: list[BundledPackage] = []
    if validator:
        wheel = validator[0]
        bundled = load_validator_texts(wheel.version, third_party) or []
        reviewed = {package.key: package for package in bundled}
        valid = [
            e
            for e in exceptions
            if canonicalize_name(e.dist) == canonicalize_name(wheel.name) and e.dist_version == wheel.version
        ]
        excepted = {(e.registry, e.package, e.version): e for e in valid}
        out += [
            "",
            f"3. Packages compiled into the BIDS validator bundle ({wheel.name} {wheel.version})",
            "",
            *paragraph(VALIDATOR_INTRO.format(version=wheel.version)),
            *paragraph(POLICY_INTRO.format(allowed=", ".join(sorted(BUNDLED_ALLOWED, key=str.casefold)))),
            "",
        ]
        rows = []
        for kind, name, version in wheel.sources:
            package = reviewed.get((kind, name, version))
            if package is None:
                rows.append((kind, name, version, "not reviewed", "-"))
            else:
                licence = package.spdx or "pending"
                if package.owner_decision:
                    licence += " (decision: section 5)"
                exception = excepted.get((package.registry, package.name, package.version))
                if exception is not None:
                    licence += f" (exception {exception.decision}: below)"
                if package.choices:
                    licence += " (choice: below)"
                if package.pending_licences:
                    licence += " (pending: section 5)"
                rows.append((kind, name, package.version or version, licence, _text_kinds(package)))
        out += _table(rows, ("Registry", "Package", "Version", "Licence", "Licence texts"))
        noted = [p for p in bundled if p.note]
        if noted:
            out += ["", "Review notes (manifest.toml):"]
            out += [f"- {p.registry} {p.name} {p.version or p.found}: {p.note}" for p in noted]
        chosen = [(p, c) for p in bundled for c in p.choices]
        if chosen:
            out += ["", CHOICES_HEADING]
            out += [
                f"- {p.registry} {p.name} {p.version or p.found}: {c.expression}"
                + (f" ({c.parts})" if c.parts else "")
                + f" - chosen: {c.chosen}"
                for p, c in chosen
            ]
        if valid:
            out += ["", EXCEPTIONS_HEADING, *paragraph(EXCEPTIONS_INTRO)]
            for exception in sorted(valid, key=lambda e: (e.package.casefold(), e.version, e.source)):
                out += _exception_lines(exception)
    other = [c for c in components if c.kind in ("external", "bundle", "not_distributed")]
    if other or bundle or site:
        out += ["", "4. Components outside the wheels", ""]
        rows = [(c.kind, c.dist, c.pattern, c.platform, c.spdx, c.notice or "-") for c in other]
        out += _table(sorted(rows), ("Kind", "Component", "Part", "Platform", "Licence", "Text"))
        out += [""] + [
            f"- {c.dist} {c.pattern}: {c.note}" for c in sorted(other, key=lambda c: (c.dist, c.pattern))
        ]
    if site is not None:
        out += _site_lines(site)
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
        out += [f"- {item['component']}: {item['what']} {gap_status(item)}." for item in known]
    out += [
        "",
        "6. Licence texts",
        "",
        *paragraph(TEXTS_INTRO),
    ]
    texts: dict[str, tuple[str, set[str]]] = {}

    def add(text: str, user: str) -> None:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        texts.setdefault(digest, (text, set()))[1].add(user)

    for wheel in wheels:
        for path, text in wheel.license_texts.items():
            add(text, f"{wheel.name} {wheel.version} ({wheel.target}): {path}")
        for component in components:
            if (
                canonicalize_name(component.dist) == canonicalize_name(wheel.name)
                and component.applies(wheel.target)
                and component.kind in ("native", "bundled")
                and component.notice.startswith(REPOSITORY_NOTICE)
            ):
                kept = _repository_text(component.notice)
                if kept is not None:
                    add(kept, f"{wheel.name} {wheel.version}: {component.pattern} ({component.spdx})")
    if validator:
        wheel = validator[0]
        sources = set(wheel.sources)
        for package in bundled:
            if package.key not in sources:
                continue
            for item in package.texts:
                if item.path.is_file():
                    user = f"{package.registry} {package.name} {package.version or package.found}"
                    add(
                        _text(item.path.read_bytes()),
                        f"{wheel.name} {wheel.version} bundle: {user}: {item.origin}",
                    )
    for part in bundle:
        for path, text in part.license_texts.items():
            add(text, f"{part.name} {part.version} ({part.target}): {path}")
    if site is not None:
        for package in site.packages:
            for item in package.texts:
                if item.path.is_file():
                    user = f"{package.registry} {package.name} {package.version or package.found}"
                    add(
                        _text(item.path.read_bytes()),
                        f"documentation site ({site.theme} {site.version}): {user}: {item.origin}",
                    )
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
        components, allowed = load_components()
        known = load_known_missing()
        exceptions = load_bundled_exceptions()
        problems = check_components(wheels, components, allowed, known, bundle, exceptions=exceptions)
        site = load_site_review(locked_version(SITE_THEME))
        problems += check_site_review(site, known)
        text = render(wheels, components, known, bundle, exceptions=exceptions, site=site)
        gone = missing_repository_paths(text)
        problems += [f"the notices name a file not in the repository: {p}" for p in gone]
    except NoticeError as exc:
        print(f"notices: {exc}", file=sys.stderr)
        return 2
    for problem in problems:
        print(f"component: {problem}", file=sys.stderr)
    if args.components:
        print(
            f"components: {len(problems)} problem(s) in {len(wheels)} wheels and {len(bundle)} bundle parts"
        )
        return 1 if problems else 0
    if args.check:
        current = NOTICES.read_text(encoding="utf-8") if NOTICES.is_file() else ""
        if current != text:
            line = first_difference(current, text)
            print(
                f"{NOTICES.name} is outdated (first difference in line {line}) - run "
                f"python tools/notices.py --out {NOTICES.name} ..."
            )
            return 1
        print(f"{NOTICES.name} up to date")
        for item in known:
            print(f"incomplete: {item['component']} - {gap_status(item)}")
        return 1 if problems or known else 0
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.out} ({len(wheels)} wheels, {len(bundle)} bundle parts)")
    return 1 if problems else 0


def first_difference(old: str, new: str) -> int:
    """The 1-based number of the first line in which two texts differ (one past the shorter if one ends)."""
    old_lines, new_lines = old.splitlines(), new.splitlines()
    for number, (a, b) in enumerate(zip(old_lines, new_lines, strict=False), start=1):
        if a != b:
            return number
    return min(len(old_lines), len(new_lines)) + 1


def iter_texts(text: str) -> Iterator[str]:
    """The licence texts of a notices file (section 6), for tests."""
    for block in text.split("\n" + "=" * 78 + "\n")[1:]:
        yield block.split("-" * 78 + "\n", 1)[-1]


if __name__ == "__main__":
    sys.exit(main())
