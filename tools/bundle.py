"""Offline bundle per platform for machines without network (KONZEPT 1.6; UF-08, NG-N01, CON-04, A-26, D-08).

A bundle holds everything a customer machine needs to install and run NeuroGrid without network and without a
preinstalled Python: python-build-standalone 3.12 (pinned in packaging/bundle_lock.json), the uv binary taken
from its PyPI wheel (with its licence files and SBOM), the cp312 wheelhouse of every runtime package of
uv.lock that applies to the target plus the NeuroGrid wheel, the sdist (CON-05), the built documentation, the
third-party notices, tools/install_pdf_browser.py (D-08: the Chrome Headless Shell itself is never inside),
the install scripts, BUNDLE.json and SHA256SUMS - signed keyless with Sigstore only in the owner-started
release workflow (D-10 g). On Linux the interpreter's _dbm module is left out (Berkeley DB, Sleepycat
licence); every removal is recorded in BUNDLE.json.

Usage:
    python tools/bundle.py build --platform win_amd64|linux_x86_64 --wheel dist/neurogrid-<v>-py3-none-any.whl
        --docs site --notices THIRD_PARTY_NOTICES.txt [--sdist dist/neurogrid-<v>.tar.gz] [--out dist]
        [--cache DIR] [--sign none|sigstore] [--pdf-installer tools/install_pdf_browser.py]
    python tools/bundle.py verify <archive or extracted folder>     # offline
    python tools/bundle.py sizes [--platform win_amd64|linux_x86_64]  # offline: wheels per platform
    python tools/bundle.py lock --python 3.12.15 --pbs-build 20261009 --uv 0.13.0  # maintainers, network

The network is used only by `build` (downloads of the pinned interpreter, uv and the locked wheels into the
cache, each checked against size and SHA-256; D-06) and by `lock`. Builds are reproducible: SOURCE_DATE_EPOCH
(default: commit time of HEAD) fixes every timestamp, entries are sorted, owners and modes are normalised.
The cache defaults to NEUROGRID_BUNDLE_CACHE or .local/bundle-cache. The runtime package set comes from
`uv export --frozen --no-default-groups --no-emit-project` (uv from the environment variable UV or PATH).

Exit codes: 0 fine, 1 verify found problems, 2 usage, input, network or source error.
This tool is not part of the NeuroGrid package, which never uses the network.
"""

from __future__ import annotations

import argparse
import dataclasses
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from packaging.markers import Marker
from packaging.tags import Tag, compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
LOCK_FILE = PACKAGING / "bundle_lock.json"
DEFAULT_CACHE = ROOT / ".local" / "bundle-cache"
PLATFORMS = ("win_amd64", "linux_x86_64")
FORMAT_VERSION = 1
USER_AGENT = "neurogrid-bundle-tool/1 (offline bundle of the NeuroGrid project)"
CHUNK = 1 << 20
MAX_ARCHIVE_BYTES = 2 * 1024**3  # GitHub release assets (A-26)
MAX_MANYLINUX = (2, 28)  # A-58: glibc >= 2.28
PATH_PATTERN = re.compile(r"[A-Za-z0-9._+/-]+")
SUMS = "SHA256SUMS"
SIGNATURE = "SHA256SUMS.sigstore.json"
SYMLINKS = "SYMLINKS"
OIDC_ISSUER = "https://token.actions.githubusercontent.com"
NOTICES = "THIRD_PARTY_NOTICES.txt"
PDF_INSTALLER = "tools/install_pdf_browser.py"
# Names that would mean a browser build or a Playwright browser folder slipped into the bundle (D-08).
BROWSER_NAMES = re.compile(r"(?i)^(chrome|chromium|headless[-_]shell|ms-playwright)")
UV_FILES = {"win_amd64": ("uv.exe",), "linux_x86_64": ("uv",)}
UV_EXTRA = ("LICENSE-APACHE", "LICENSE-MIT", "uv.cyclonedx.json")
INSTALL_SCRIPTS = {"win_amd64": ("install.cmd", "install.ps1"), "linux_x86_64": ("install.sh",)}
COMMON_TOP = (
    "BUNDLE.json",
    "LICENSE",
    "NOTICE",
    "README.txt",
    SUMS,
    NOTICES,
    "docs/",
    "python/",
    "requirements.lock.txt",
    "src/",
    "tools/",
    "uv/",
    "wheels/",
)
STORED_SUFFIXES = (".whl", ".zip", ".gz", ".tgz", ".xz", ".bz2", ".png", ".jpg", ".woff", ".woff2")


class BundleError(Exception):
    """Wrong input, a failed download or an inconsistent source (exit 2)."""


# --- small helpers -----------------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def check_relative(path: str) -> None:
    """A bundle path: relative POSIX, only [A-Za-z0-9._+/-], no empty, '.' or '..' segment."""
    if not PATH_PATTERN.fullmatch(path):
        raise BundleError(f"path with characters outside [A-Za-z0-9._+/-]: {path!r}")
    if path.startswith("/") or any(part in ("", ".", "..") for part in path.split("/")):
        raise BundleError(f"path is not a plain relative path: {path!r}")


def is_executable(data: bytes) -> bool:
    """ELF, PE or script with a shebang: these keep an executable mode in the archive."""
    return data[:4] == b"\x7fELF" or data[:2] in (b"MZ", b"#!")


def find_uv() -> str:
    """uv from the environment variable UV (set by `uv run`) or from PATH."""
    candidate = os.environ.get("UV") or shutil.which("uv")
    if not candidate:
        raise BundleError("uv not found: put uv on PATH or set UV (uv run sets it)")
    return candidate


def bundle_name(version: str, platform: str) -> str:
    return f"neurogrid-{version}-offline-{platform}"


def archive_name(version: str, platform: str) -> str:
    return bundle_name(version, platform) + (".zip" if platform == "win_amd64" else ".tar.gz")


# --- pins: bundle_lock.json, uv.lock and the runtime export ----------------------------------------------


def load_bundle_lock(path: Path = LOCK_FILE) -> dict[str, Any]:
    """The pinned interpreter, uv and the removals; shape checked so that a hand edit cannot slip through."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format_version") != FORMAT_VERSION:
        raise BundleError(f"{path.name}: unsupported format_version")
    for part in ("python", "uv"):
        section = data.get(part)
        if not isinstance(section, dict) or not isinstance(section.get("platforms"), dict):
            raise BundleError(f"{path.name}: section {part!r} missing")
        for platform in PLATFORMS:
            pin = section["platforms"].get(platform)
            if not isinstance(pin, dict):
                raise BundleError(f"{path.name}: {part} has no pin for {platform}")
            if not str(pin.get("url", "")).startswith(("https://", "file:")):
                raise BundleError(f"{path.name}: {part}/{platform}: url must be https")
            if not re.fullmatch(r"[0-9a-f]{64}", str(pin.get("sha256", ""))):
                raise BundleError(f"{path.name}: {part}/{platform}: sha256 must be 64 lowercase hex digits")
            if not isinstance(pin.get("size"), int) or pin["size"] <= 0:
                raise BundleError(f"{path.name}: {part}/{platform}: size must be a positive integer")
    if not re.fullmatch(r"3\.12\.\d+", str(data["python"].get("version", ""))):
        raise BundleError(f"{path.name}: the bundle interpreter must be CPython 3.12.x (KONZEPT 1.6)")
    for platform, removals in data.get("remove", {}).items():
        if platform not in PLATFORMS:
            raise BundleError(f"{path.name}: removal for unknown platform {platform!r}")
        for item in removals:
            check_relative(item["path"])
            if not item.get("reason"):
                raise BundleError(f"{path.name}: removal {item['path']} needs a reason")
    return data


@dataclasses.dataclass(frozen=True)
class Pin:
    """One line of the runtime export: name==version, optional marker, accepted hashes."""

    name: str
    version: str
    marker: str | None
    hashes: frozenset[str]


@dataclasses.dataclass(frozen=True)
class WheelRef:
    name: str
    version: str
    filename: str
    url: str
    sha256: str
    size: int


REQUIREMENT_LINE = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)\s*(?:;\s*(.+?))?")


def export_requirements(root: Path = ROOT) -> str:
    """`uv export` of the runtime set: no dev or docs group, no project, with hashes (A-48)."""
    command = [find_uv(), "export", "--frozen", "--no-default-groups", "--no-emit-project"]
    command += ["--format", "requirements-txt", "--no-header"]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode != 0:
        raise BundleError(f"uv export failed: {result.stderr.strip()[-500:]}")
    return result.stdout


def parse_requirements(text: str) -> list[Pin]:
    """Pins of a requirements file as written by `uv export` (continuation lines, --hash, comments)."""
    pins: list[Pin] = []
    current = ""
    for raw in [*text.splitlines(), ""]:
        line = raw.strip()
        if line.startswith("#"):
            line = ""
        continued = line.endswith("\\")
        part = line[:-1].strip() if continued else line
        current = f"{current} {part}".strip()
        if continued or not current:
            continue
        spec, *options = re.split(r"\s+(?=--)", current)
        current = ""
        match = REQUIREMENT_LINE.fullmatch(spec)
        if match is None:
            raise BundleError(f"unexpected requirement line: {spec!r}")
        hashes = set()
        for option in options:
            if not option.startswith("--hash=sha256:"):
                raise BundleError(f"unexpected option in requirements: {option!r}")
            hashes.add(option.removeprefix("--hash=sha256:"))
        if not hashes:
            raise BundleError(f"{spec}: no hash (the export must carry hashes, A-48)")
        name, version, marker = match.groups()
        pins.append(Pin(canonicalize_name(name), version, marker, frozenset(hashes)))
    return pins


def target_environment(platform: str, python_full: str) -> dict[str, str]:
    """Marker environment of the bundle interpreter on the target, independent of the build machine."""
    windows = platform == "win_amd64"
    return {
        "implementation_name": "cpython",
        "implementation_version": python_full,
        "os_name": "nt" if windows else "posix",
        "platform_machine": "AMD64" if windows else "x86_64",
        "platform_python_implementation": "CPython",
        "platform_release": "",
        "platform_system": "Windows" if windows else "Linux",
        "platform_version": "",
        "python_full_version": python_full,
        "python_version": ".".join(python_full.split(".")[:2]),
        "sys_platform": "win32" if windows else "linux",
        "extra": "",
    }


def platform_tags(platform: str) -> list[str]:
    if platform == "win_amd64":
        return ["win_amd64"]
    if platform != "linux_x86_64":
        raise BundleError(f"unknown platform {platform!r}")
    manylinux = [f"manylinux_2_{minor}_x86_64" for minor in range(MAX_MANYLINUX[1], 4, -1)]
    return [*manylinux, "manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64"]


def supported_tags(platform: str) -> dict[Tag, int]:
    """cp312 tags the bundle interpreter accepts on the target, best first (manylinux at most 2_28)."""
    plats = platform_tags(platform)
    ranks: dict[Tag, int] = {}
    tags = [
        *cpython_tags(python_version=(3, 12), abis=["cp312"], platforms=plats),
        *compatible_tags(python_version=(3, 12), interpreter="cp312", platforms=plats),
    ]
    for tag in tags:
        ranks.setdefault(tag, len(ranks))
    return ranks


def select_wheels(
    uv_lock: Mapping[str, Any], pins: Sequence[Pin], platform: str, python_full: str
) -> list[WheelRef]:
    """The best cp312 wheel of every pin that applies to the target; a pin without one is an error (A-48)."""
    environment = target_environment(platform, python_full)
    ranks = supported_tags(platform)
    packages: dict[tuple[str, str], Mapping[str, Any]] = {
        (str(canonicalize_name(str(pkg["name"]))), str(pkg.get("version", ""))): pkg
        for pkg in uv_lock.get("package", [])
    }
    selected: list[WheelRef] = []
    missing: list[str] = []
    for pin in pins:
        if pin.marker and not Marker(pin.marker).evaluate(environment):
            continue
        package = packages.get((pin.name, pin.version))
        if package is None:
            raise BundleError(f"{pin.name}=={pin.version} is exported but not in uv.lock")
        best: tuple[int, str, Mapping[str, Any]] | None = None
        for wheel in package.get("wheels", []):
            filename = urllib.parse.unquote(str(wheel["url"]).rsplit("/", 1)[-1])
            rank = min(
                (ranks[tag] for tag in parse_wheel_filename(filename)[3] if tag in ranks), default=None
            )
            if rank is not None and (best is None or rank < best[0]):
                best = (rank, filename, wheel)
        if best is None:
            missing.append(f"{pin.name}=={pin.version}")
            continue
        _, filename, wheel = best
        digest = str(wheel["hash"]).removeprefix("sha256:")
        if digest not in pin.hashes:
            raise BundleError(f"{filename}: its uv.lock hash is not among the exported hashes")
        selected.append(
            WheelRef(pin.name, pin.version, filename, str(wheel["url"]), digest, int(wheel["size"]))
        )
    if missing:
        raise BundleError(
            f"no cp312 wheel for {platform}: {', '.join(missing)} (source builds are not allowed, A-48)"
        )
    return sorted(selected, key=lambda ref: ref.name)


def highest_manylinux(filenames: Sequence[str]) -> tuple[int, int] | None:
    """The glibc version the selected Linux wheels need (manylinux2014 = 2.17, 2010 = 2.12, 1 = 2.5)."""
    legacy = {"manylinux2014": (2, 17), "manylinux2010": (2, 12), "manylinux1": (2, 5)}
    found: list[tuple[int, int]] = []
    for filename in filenames:
        needs: list[tuple[int, int]] = []
        for tag in parse_wheel_filename(filename)[3]:
            match = re.fullmatch(r"manylinux_(\d+)_(\d+)_x86_64", tag.platform)
            if match:
                needs.append((int(match.group(1)), int(match.group(2))))
            elif tag.platform.removesuffix("_x86_64") in legacy:
                needs.append(legacy[tag.platform.removesuffix("_x86_64")])
        if needs:
            found.append(min(needs))  # a wheel with several tags runs on the oldest it names
    return max(found) if found else None


# --- downloads ---------------------------------------------------------------------------------------


def fetch(url: str, sha256: str, size: int, cache: Path) -> Path:
    """The file behind ``url`` in the cache (keyed by SHA-256), downloaded once, checked by size and hash."""
    target = cache / sha256
    if target.is_file():
        if target.stat().st_size == size and sha256_file(target) == sha256:
            return target
        target.unlink()
    cache.mkdir(parents=True, exist_ok=True)
    part = cache / f"{sha256}.part"
    for attempt in range(4):
        digest, received = hashlib.sha256(), 0
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=120) as response, part.open("wb") as handle:
                while chunk := response.read(CHUNK):
                    received += len(chunk)
                    if received > size:
                        raise BundleError(f"{url}: larger than the pinned {size} bytes")
                    digest.update(chunk)
                    handle.write(chunk)
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            part.unlink(missing_ok=True)
            if attempt == 3:
                raise BundleError(f"download failed: {url}: {exc}") from None
            time.sleep(2**attempt)
        except BundleError:
            part.unlink(missing_ok=True)
            raise
    if received != size or digest.hexdigest() != sha256:
        part.unlink(missing_ok=True)
        raise BundleError(
            f"{url}: got {received} bytes with SHA-256 {digest.hexdigest()}, pinned {size} / {sha256}"
        )
    Path(part).replace(target)
    return target


# --- staging -------------------------------------------------------------------------------------------


@dataclasses.dataclass
class Entry:
    """One bundle member. Regular files come from bytes or a file; symbolic links (Linux) only from a target.

    Nothing is extracted to disk: the Linux interpreter holds names that differ only in case
    (share/terminfo), which a Windows build machine could not keep apart.
    """

    path: str
    data: bytes | None = None
    source: Path | None = None
    link: str | None = None
    executable: bool = False
    _digest: str | None = None

    def read(self) -> bytes:
        if self.data is not None:
            return self.data
        if self.source is None:
            raise BundleError(f"{self.path}: no content")
        return self.source.read_bytes()

    @property
    def sha256(self) -> str:
        if self._digest is None:
            self._digest = sha256_bytes(self.data) if self.data is not None else sha256_file(self._source())
        return self._digest

    @property
    def size(self) -> int:
        return len(self.data) if self.data is not None else self._source().stat().st_size

    def _source(self) -> Path:
        if self.source is None:
            raise BundleError(f"{self.path}: no content")
        return self.source

    @property
    def mode(self) -> int:
        if self.link is not None:
            return 0o777
        if self.executable:
            return 0o755
        head = self.data[:4] if self.data is not None else self._head()
        return 0o755 if is_executable(head) else 0o644

    def _head(self) -> bytes:
        with self._source().open("rb") as handle:
            return handle.read(4)


class Stage:
    """The members of one bundle, keyed by their relative path."""

    def __init__(self, platform: str) -> None:
        self.platform = platform
        self.entries: dict[str, Entry] = {}

    def add(self, entry: Entry) -> None:
        check_relative(entry.path)
        if entry.path in self.entries:
            raise BundleError(f"two members with the path {entry.path}")
        self.entries[entry.path] = entry

    def file(self, path: str, data: bytes, *, executable: bool = False) -> None:
        self.add(Entry(path, data=data, executable=executable))

    def copy(self, path: str, source: Path) -> None:
        if not source.is_file():
            raise BundleError(f"input file missing: {source}")
        self.add(Entry(path, source=source))

    def regular(self) -> list[Entry]:
        return [self.entries[p] for p in sorted(self.entries) if self.entries[p].link is None]

    def links(self) -> list[Entry]:
        return [self.entries[p] for p in sorted(self.entries) if self.entries[p].link is not None]


def stage_python(stage: Stage, archive: Path, removals: Sequence[str]) -> list[str]:
    """python-build-standalone as it is, minus the recorded removals (returns what was removed)."""
    removed: list[str] = []
    wanted = set(removals)
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            name = member.name.removeprefix("./")
            if member.isdir():
                continue
            if not name.startswith("python/"):
                raise BundleError(f"{archive.name}: member outside python/: {name}")
            if name in wanted:
                removed.append(name)
                continue
            if member.issym():
                if stage.platform == "win_amd64":
                    raise BundleError(f"{archive.name}: symbolic link in a Windows interpreter: {name}")
                target = member.linkname
                resolved = PurePosixPath(name).parent.joinpath(target).as_posix()
                if target.startswith("/") or not _inside(resolved):
                    raise BundleError(f"{archive.name}: link {name} points outside the bundle: {target}")
                stage.add(Entry(name, link=target))
            elif member.isfile():
                handle = tar.extractfile(member)
                if handle is None:
                    raise BundleError(f"{archive.name}: cannot read {name}")
                data = handle.read()
                stage.add(Entry(name, data=data, executable=bool(member.mode & 0o111) or is_executable(data)))
            else:
                raise BundleError(f"{archive.name}: unsupported member type for {name}")
    missing = sorted(wanted - set(removed))
    if missing:
        raise BundleError(
            f"{archive.name}: removal not found (bundle_lock.json outdated?): {', '.join(missing)}"
        )
    return sorted(removed)


def _inside(path: str) -> bool:
    depth = 0
    for part in path.split("/"):
        if part == "..":
            depth -= 1
        elif part not in ("", "."):
            depth += 1
        if depth < 0:
            return False
    return True


def stage_uv(stage: Stage, wheel: Path, version: str) -> None:
    """The uv binary, its two licence texts and its CycloneDX SBOM, all taken from the PyPI wheel."""
    binary = UV_FILES[stage.platform][0]
    wanted = {
        f"uv-{version}.data/scripts/{binary}": f"uv/{binary}",
        f"uv-{version}.dist-info/licenses/LICENSE-APACHE": "uv/LICENSE-APACHE",
        f"uv-{version}.dist-info/licenses/LICENSE-MIT": "uv/LICENSE-MIT",
        f"uv-{version}.dist-info/sboms/uv.cyclonedx.json": "uv/uv.cyclonedx.json",
    }
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        for inner, target in wanted.items():
            if inner not in names:
                raise BundleError(f"{wheel.name}: {inner} missing")
            data = archive.read(inner)
            stage.file(target, data, executable=target == f"uv/{binary}")


def stage_tree(stage: Stage, prefix: str, folder: Path) -> int:
    """Every regular file below ``folder`` (no links) under ``prefix``/."""
    if not folder.is_dir():
        raise BundleError(f"folder missing: {folder}")
    count = 0
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise BundleError(f"symbolic link in {folder}: {path.relative_to(folder).as_posix()}")
        if path.is_file():
            stage.copy(f"{prefix}/{path.relative_to(folder).as_posix()}", path)
            count += 1
    if count == 0:
        raise BundleError(f"folder is empty: {folder}")
    return count


def requirements_lock(wheels: Sequence[WheelRef], neurogrid_version: str, neurogrid_sha256: str) -> bytes:
    """One exact pin with the hash of the bundled wheel per package; installed with --require-hashes."""
    lines = [f"{ref.name}=={ref.version} \\\n    --hash=sha256:{ref.sha256}\n" for ref in wheels]
    lines.append(f"neurogrid=={neurogrid_version} \\\n    --hash=sha256:{neurogrid_sha256}\n")
    return "".join(sorted(lines)).encode("utf-8")


def installed_paths(wheel_name: str, names: Sequence[str], platform: str) -> Iterator[str]:
    """Paths below the install prefix that a wheel produces in the venv, including compiled bytecode."""
    windows = platform == "win_amd64"
    site = "venv/Lib/site-packages" if windows else "venv/lib/python3.12/site-packages"
    scripts = "venv/Scripts" if windows else "venv/bin"
    include = "venv/Include/site/python3.12" if windows else "venv/include/site/python3.12"
    dist = parse_wheel_filename(wheel_name)[0]
    for name in names:
        if name.endswith("/"):
            continue
        head, _, rest = name.partition("/")
        if head.endswith(".data") and rest:
            kind, _, inner = rest.partition("/")
            base = {"scripts": scripts, "purelib": site, "platlib": site, "headers": f"{include}/{dist}"}
            path = f"{base.get(kind, 'venv')}/{inner}"
            if kind in ("purelib", "platlib"):
                yield from _with_bytecode(path)
            else:
                yield path
        else:
            yield from _with_bytecode(f"{site}/{name}")


def _with_bytecode(path: str) -> Iterator[str]:
    yield path
    if path.endswith(".py"):
        folder, _, name = path.rpartition("/")
        yield f"{folder}/__pycache__/{name[:-3]}.cpython-312.pyc"


def console_scripts(archive: zipfile.ZipFile) -> list[str]:
    for name in archive.namelist():
        if name.endswith(".dist-info/entry_points.txt"):
            text = archive.read(name).decode("utf-8")
            section, found = "", []
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("["):
                    section = line.strip("[]")
                elif "=" in line and section in ("console_scripts", "gui_scripts"):
                    found.append(line.split("=", 1)[0].strip())
            return found
    return []


def max_install_path(stage: Stage) -> int:
    """Longest relative path below the prefix after installation (Windows MAX_PATH guard of install.ps1)."""
    longest = max((len(path) for path in stage.entries if path.startswith("python/")), default=0)
    windows = stage.platform == "win_amd64"
    for path, entry in stage.entries.items():
        if not (path.startswith("wheels/") and path.endswith(".whl")):
            continue
        with zipfile.ZipFile(
            entry.source if entry.source is not None else io.BytesIO(entry.read())
        ) as archive:
            names = archive.namelist()
            launchers = [
                f"venv/Scripts/{name}.exe" if windows else f"venv/bin/{name}"
                for name in console_scripts(archive)
            ]
        name = path.removeprefix("wheels/")
        longest = max(
            [longest, *(len(p) for p in installed_paths(name, names, stage.platform)), *map(len, launchers)]
        )
    return longest


# --- writing ------------------------------------------------------------------------------------------


def sha256sums(stage: Stage) -> bytes:
    """GNU coreutils text format, sorted bytewise; neither SHA256SUMS nor its signature is listed."""
    lines = [
        f"{entry.sha256}  {entry.path}\n" for entry in stage.regular() if entry.path not in (SUMS, SIGNATURE)
    ]
    return "".join(lines).encode("utf-8")


def symlinks_file(stage: Stage) -> bytes:
    return "".join(f"{entry.path} -> {entry.link}\n" for entry in stage.links()).encode("utf-8")


def _zip_time(epoch: int) -> tuple[int, int, int, int, int, int]:
    moment = datetime.fromtimestamp(max(epoch, 315532800), tz=UTC)  # zip cannot store dates before 1980
    return (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second)


def pack_zip(stage: Stage, root: str, target: Path, epoch: int) -> None:
    if stage.links():
        raise BundleError("symbolic links cannot go into a Windows bundle")
    when = _zip_time(epoch)
    with zipfile.ZipFile(target, "w") as archive:
        for entry in stage.regular():
            info = zipfile.ZipInfo(f"{root}/{entry.path}", when)
            info.create_system = 3  # Unix attributes, the same on every build machine
            info.external_attr = (stat.S_IFREG | entry.mode) << 16
            stored = entry.path.endswith(STORED_SUFFIXES)
            method = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            archive.writestr(info, entry.read(), compress_type=method, compresslevel=None if stored else 6)


def pack_tar_gz(stage: Stage, root: str, target: Path, epoch: int) -> None:
    folders = {root}
    for path in stage.entries:
        parts = path.split("/")[:-1]
        folders.update(f"{root}/{'/'.join(parts[: i + 1])}" for i in range(len(parts)))
    members: list[tuple[str, Entry | None]] = [(name, None) for name in folders]
    members += [(f"{root}/{path}", entry) for path, entry in stage.entries.items()]
    with target.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as packed:
        with tarfile.open(fileobj=packed, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for name, entry in sorted(members, key=lambda item: item[0]):
                info = tarfile.TarInfo(name)
                info.mtime, info.uid, info.gid, info.uname, info.gname = epoch, 0, 0, "", ""
                if entry is None:
                    info.type, info.mode = tarfile.DIRTYPE, 0o755
                    tar.addfile(info)
                elif entry.link is not None:
                    info.type, info.mode, info.linkname = tarfile.SYMTYPE, 0o777, entry.link
                    tar.addfile(info)
                else:
                    data = entry.read()
                    info.size, info.mode = len(data), entry.mode
                    tar.addfile(info, io.BytesIO(data))


def sign_sigstore(sums: bytes, identity: str) -> bytes:
    """Keyless Sigstore signature of SHA256SUMS (D-10 g), only inside a GitHub Actions run with OIDC."""
    if os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"):
        raise BundleError("--sign sigstore needs the OIDC token of a GitHub Actions run (release.yml)")
    cosign = shutil.which("cosign")
    if cosign is None:
        raise BundleError("cosign not found (release.yml installs it with sigstore/cosign-installer)")
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        (work / SUMS).write_bytes(sums)
        for command in (
            [cosign, "sign-blob", "--yes", "--bundle", SIGNATURE, SUMS],
            [cosign, "verify-blob", SUMS, "--bundle", SIGNATURE, "--certificate-identity", identity]
            + ["--certificate-oidc-issuer", OIDC_ISSUER],
        ):
            result = subprocess.run(command, cwd=work, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise BundleError(f"cosign failed ({command[1]}): {result.stderr.strip()[-500:]}")
        return (work / SIGNATURE).read_bytes()


def release_identity(version: str, environ: Mapping[str, str]) -> str:
    repository = environ.get("GITHUB_REPOSITORY") or environ.get("NEUROGRID_RELEASE_REPOSITORY")
    if not repository or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise BundleError(
            "a signed bundle needs GITHUB_REPOSITORY or NEUROGRID_RELEASE_REPOSITORY (owner/repo)"
        )
    return f"https://github.com/{repository}/.github/workflows/release.yml@refs/tags/v{version}"


def render_readme(template: str, version: str, platform: str, identity: str | None) -> bytes:
    text = template.replace("{{version}}", version).replace("{{platform}}", platform)
    text = text.replace("{{identity}}", identity or "-")
    if "{{" in text:
        raise BundleError("README.bundle.txt has an unknown placeholder")
    return text.encode("utf-8")


def crlf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


@dataclasses.dataclass
class BuildInputs:
    platform: str
    wheel: Path
    sdist: Path
    docs: Path
    notices: Path
    pdf_installer: Path
    out: Path
    cache: Path
    sign: str
    lock: dict[str, Any]
    uv_lock_text: str
    requirements: str
    source_date_epoch: int
    git_commit: str | None
    packaging_dir: Path = PACKAGING
    license_file: Path = ROOT / "LICENSE"
    notice_file: Path = ROOT / "NOTICE"
    environ: Mapping[str, str] = dataclasses.field(default_factory=lambda: dict(os.environ))


def build(inputs: BuildInputs) -> Path:
    """Stage, check and pack one bundle; returns the archive path."""
    platform = inputs.platform
    if platform not in PLATFORMS:
        raise BundleError(f"unknown platform {platform!r}")
    name, version, _, tags = parse_wheel_filename(inputs.wheel.name)
    if name != "neurogrid" or {str(t) for t in tags} != {"py3-none-any"}:
        raise BundleError(f"not the NeuroGrid wheel: {inputs.wheel.name}")
    version_text = str(version)
    if inputs.sdist.name != f"neurogrid-{version_text}.tar.gz":
        raise BundleError(f"sdist name does not match the wheel version {version_text}: {inputs.sdist.name}")
    for path in (inputs.wheel, inputs.sdist, inputs.notices, inputs.pdf_installer):
        if not path.is_file():
            raise BundleError(f"input file missing: {path}")
    if not (inputs.docs / "index.html").is_file():
        raise BundleError(f"not a built documentation site (index.html missing): {inputs.docs}")
    with zipfile.ZipFile(inputs.wheel) as archive:
        if any(n.endswith(".pyc") for n in archive.namelist()):
            raise BundleError(f"{inputs.wheel.name} contains bytecode (it is compiled at install, A-48)")
    signed = inputs.sign == "sigstore"
    identity = release_identity(version_text, inputs.environ) if signed else None

    lock = inputs.lock
    python_pin = lock["python"]["platforms"][platform]
    uv_pin = lock["uv"]["platforms"][platform]
    python_full = str(lock["python"]["version"])
    pins = parse_requirements(inputs.requirements)
    uv_lock = tomllib.loads(inputs.uv_lock_text)
    wheels = select_wheels(uv_lock, pins, platform, python_full)

    stage = Stage(platform)
    pbs = fetch(python_pin["url"], python_pin["sha256"], python_pin["size"], inputs.cache)
    removals = [item["path"] for item in lock.get("remove", {}).get(platform, [])]
    removed = stage_python(stage, pbs, removals)
    uv_wheel = fetch(uv_pin["url"], uv_pin["sha256"], uv_pin["size"], inputs.cache)
    stage_uv(stage, uv_wheel, str(lock["uv"]["version"]))
    for ref in wheels:
        stage.copy(f"wheels/{ref.filename}", fetch(ref.url, ref.sha256, ref.size, inputs.cache))
    stage.copy(f"wheels/{inputs.wheel.name}", inputs.wheel)
    stage.file("requirements.lock.txt", requirements_lock(wheels, version_text, sha256_file(inputs.wheel)))
    stage.copy(f"src/{inputs.sdist.name}", inputs.sdist)
    stage.copy(PDF_INSTALLER, inputs.pdf_installer)
    stage_tree(stage, "docs", inputs.docs)
    stage.copy("LICENSE", inputs.license_file)
    stage.copy("NOTICE", inputs.notice_file)
    stage.copy(NOTICES, inputs.notices)
    template = (inputs.packaging_dir / "README.bundle.txt").read_text(encoding="utf-8")
    stage.file("README.txt", render_readme(template, version_text, platform, identity))
    if platform == "win_amd64":
        script = (inputs.packaging_dir / "install.ps1").read_bytes()
        if not script.startswith(b"\xef\xbb\xbf"):
            raise BundleError(
                "install.ps1 must be UTF-8 with BOM (Windows PowerShell 5.1 reads it otherwise as ANSI)"
            )
        stage.file("install.ps1", script.replace(b"\r\n", b"\n"))
        stage.file("install.cmd", crlf((inputs.packaging_dir / "install.cmd").read_bytes()))
    else:
        stage.file("install.sh", (inputs.packaging_dir / "install.sh").read_bytes().replace(b"\r\n", b"\n"))
        stage.file(SYMLINKS, symlinks_file(stage))
    if platform == "win_amd64":
        folded: dict[str, str] = {}
        for member in stage.entries:
            other = folded.setdefault(member.lower(), member)
            if other != member:
                raise BundleError(f"paths differ only in case (Windows cannot keep both): {other}, {member}")

    info = {
        "format_version": FORMAT_VERSION,
        "name": "neurogrid",
        "version": version_text,
        "platform": platform,
        "git_commit": inputs.git_commit,
        "source_date_epoch": inputs.source_date_epoch,
        "uv_lock_sha256": sha256_bytes(inputs.uv_lock_text.encode("utf-8")),
        "python": {
            "version": python_full,
            "build": lock["python"]["build"],
            "url": python_pin["url"],
            "sha256": python_pin["sha256"],
            "removed": removed,
        },
        "uv": {
            "version": lock["uv"]["version"],
            "wheel": uv_pin["url"].rsplit("/", 1)[-1],
            "sha256": uv_pin["sha256"],
        },
        "wheels": sorted(
            (
                {"file": e.path.removeprefix("wheels/"), "sha256": e.sha256, "size": e.size}
                for e in stage.regular()
                if e.path.startswith("wheels/")
            ),
            key=lambda item: str(item["file"]),
        ),
        "sdist": {"file": inputs.sdist.name, "sha256": sha256_file(inputs.sdist)},
        "max_relative_install_path": max_install_path(stage),
        "release_identity": identity,
    }
    stage.file("BUNDLE.json", (json.dumps(info, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    sums = sha256sums(stage)
    stage.file(SUMS, sums)
    if signed and identity is not None:
        stage.file(SIGNATURE, sign_sigstore(sums, identity))

    root = bundle_name(version_text, platform)
    inputs.out.mkdir(parents=True, exist_ok=True)
    target = inputs.out / archive_name(version_text, platform)
    part = target.with_name(target.name + ".part")
    try:
        if platform == "win_amd64":
            pack_zip(stage, root, part, inputs.source_date_epoch)
        else:
            pack_tar_gz(stage, root, part, inputs.source_date_epoch)
        if part.stat().st_size >= MAX_ARCHIVE_BYTES:
            raise BundleError(f"{target.name} is larger than 2 GiB (GitHub release limit)")
        Path(part).replace(target)
    finally:
        part.unlink(missing_ok=True)
    return target


# --- verify -------------------------------------------------------------------------------------------


@dataclasses.dataclass
class Item:
    kind: str  # "file" or "link"
    sha256: str = ""
    size: int = 0
    link: str = ""
    data: bytes | None = None  # small text members only
    wheel_names: list[str] | None = None


KEEP = ("BUNDLE.json", SUMS, SYMLINKS, "README.txt", "requirements.lock.txt")


def _record(items: dict[str, Item], path: str, data: bytes) -> None:
    item = Item("file", sha256_bytes(data), len(data))
    if path in KEEP:
        item.data = data
    if path.startswith("wheels/") and path.endswith(".whl"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                item.wheel_names = archive.namelist()
        except zipfile.BadZipFile:
            item.wheel_names = []
    items[path] = item


def inventory(path: Path) -> tuple[str, dict[str, Item], list[str]]:
    """Root folder name, members and structural problems of an archive or an extracted bundle folder."""
    items: dict[str, Item] = {}
    problems: list[str] = []
    roots: set[str] = set()

    def place(name: str) -> str | None:
        head, _, rest = name.strip("/").partition("/")
        roots.add(head)
        return rest or None

    if path.is_dir():
        roots.add(path.name)
        for entry in sorted(path.rglob("*")):
            relative = entry.relative_to(path).as_posix()
            if entry.is_symlink():
                items[relative] = Item("link", link=str(entry.readlink()))
            elif entry.is_file():
                _record(items, relative, entry.read_bytes())
            elif not entry.is_dir():
                problems.append(f"special file: {relative}")
    elif path.name.endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                inner = place(info.filename)
                if inner is None or info.is_dir():
                    continue
                if stat.S_ISLNK(info.external_attr >> 16):
                    items[inner] = Item("link", link=archive.read(info).decode("utf-8", "replace"))
                else:
                    _record(items, inner, archive.read(info))
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as tar:
            for member in tar:
                inner = place(member.name)
                if inner is None or member.isdir():
                    continue
                if member.issym():
                    items[inner] = Item("link", link=member.linkname)
                elif member.isfile():
                    handle = tar.extractfile(member)
                    _record(items, inner, handle.read() if handle else b"")
                else:
                    problems.append(f"unsupported member type: {inner}")
    else:
        raise BundleError(f"not a bundle archive or folder: {path}")
    if len(roots) != 1:
        problems.append(f"the archive must hold exactly one root folder, found: {sorted(roots)}")
    return (next(iter(roots)) if len(roots) == 1 else ""), items, problems


def verify(path: Path) -> list[str]:
    """Every problem of a bundle; empty means the bundle is complete, consistent and allowed."""
    root, items, problems = inventory(path)
    match = re.fullmatch(r"neurogrid-(.+)-offline-(win_amd64|linux_x86_64)", root)
    if match is None:
        return [*problems, f"unexpected root folder name: {root!r}"]
    version, platform = match.groups()
    if path.is_file() and path.stat().st_size >= MAX_ARCHIVE_BYTES:
        problems.append("archive is larger than 2 GiB")

    for rel in items:
        try:
            check_relative(rel)
        except BundleError as exc:
            problems.append(str(exc))
        if any(BROWSER_NAMES.match(part) for part in rel.split("/")):
            problems.append(f"browser files must not be in the bundle (D-08): {rel}")
        if rel.endswith(".pyc") and not rel.startswith("python/"):
            problems.append(f"bytecode outside the interpreter (compiled at install, A-48): {rel}")
    problems += _check_layout(items, version, platform)
    problems += _check_sums(items)
    problems += _check_links(items, platform)
    problems += _check_wheels(items, platform)
    problems += _check_info(items, version, platform)
    problems += _check_readme(items)
    return problems


def _check_layout(items: Mapping[str, Item], version: str, platform: str) -> list[str]:
    allowed = {*COMMON_TOP, *INSTALL_SCRIPTS[platform], SIGNATURE} | (
        {SYMLINKS} if platform != "win_amd64" else set()
    )
    problems = []
    present = set()
    for rel in items:
        head, slash, _ = rel.partition("/")
        top = head + "/" if slash else head
        present.add(top)
        if top not in allowed:
            problems.append(f"not allowed at the top level: {top}")
    required = allowed - {SIGNATURE}
    problems += [f"missing: {name}" for name in sorted(required - present)]
    expected_dirs = {
        "src/": {f"src/neurogrid-{version}.tar.gz"},
        "tools/": {PDF_INSTALLER},
        "uv/": {f"uv/{name}" for name in (*UV_FILES[platform], *UV_EXTRA)},
    }
    for prefix, names in expected_dirs.items():
        found = {rel for rel in items if rel.startswith(prefix)}
        problems += [f"not allowed in {prefix}: {rel}" for rel in sorted(found - names)]
        problems += [f"missing: {rel}" for rel in sorted(names - found)]
    problems += [
        f"not a wheel: {rel}" for rel in items if rel.startswith("wheels/") and not rel.endswith(".whl")
    ]
    if "docs/index.html" not in items:
        problems.append("missing: docs/index.html")
    if platform == "linux_x86_64":
        problems += [
            f"Berkeley DB module must be removed (licence): {rel}" for rel in items if "/_dbm." in rel
        ]
    if platform == "win_amd64":
        folded: dict[str, str] = {}
        for rel in items:
            other = folded.setdefault(rel.lower(), rel)
            if other != rel:
                problems.append(f"paths differ only in case: {other}, {rel}")
    return problems


def _check_sums(items: Mapping[str, Item]) -> list[str]:
    sums = items.get(SUMS)
    if sums is None or sums.data is None:
        return []  # reported as missing by the layout check
    listed: dict[str, str] = {}
    problems = []
    lines = sums.data.decode("utf-8", "replace").split("\n")
    if lines[-1] != "":
        problems.append("SHA256SUMS does not end with a newline")
    for line in lines[:-1]:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._+/-]+)", line)
        if match is None:
            problems.append(f"malformed SHA256SUMS line: {line!r}")
            continue
        digest, rel = match.groups()
        if rel in listed:
            problems.append(f"listed twice in SHA256SUMS: {rel}")
        listed[rel] = digest
    if list(listed) != sorted(listed):
        problems.append("SHA256SUMS is not sorted")
    regular = {
        rel: item for rel, item in items.items() if item.kind == "file" and rel not in (SUMS, SIGNATURE)
    }
    for rel, digest in listed.items():
        if rel not in regular:
            problems.append(f"listed but missing: {rel}")
        elif regular[rel].sha256 != digest:
            problems.append(f"changed (SHA-256 differs): {rel}")
    problems += [f"not listed in SHA256SUMS: {rel}" for rel in sorted(set(regular) - set(listed))]
    return problems


def _check_links(items: Mapping[str, Item], platform: str) -> list[str]:
    links = {rel: item.link for rel, item in items.items() if item.kind == "link"}
    if platform == "win_amd64":
        return [f"symbolic link in a Windows bundle: {rel}" for rel in sorted(links)]
    problems = []
    for rel, target in sorted(links.items()):
        resolved = PurePosixPath(rel).parent.joinpath(target).as_posix()
        if target.startswith("/") or not _inside(resolved):
            problems.append(f"link points outside the bundle: {rel} -> {target}")
    recorded = items.get(SYMLINKS)
    if recorded is not None and recorded.data is not None:
        expected = "".join(f"{rel} -> {target}\n" for rel, target in sorted(links.items()))
        if recorded.data.decode("utf-8", "replace") != expected:
            problems.append("SYMLINKS does not match the symbolic links of the bundle")
    return problems


def _check_wheels(items: Mapping[str, Item], platform: str) -> list[str]:
    ranks = supported_tags(platform)
    problems = []
    names = []
    for rel, item in sorted(items.items()):
        if not (rel.startswith("wheels/") and rel.endswith(".whl")):
            continue
        filename = rel.removeprefix("wheels/")
        names.append(filename)
        try:
            tags = parse_wheel_filename(filename)[3]
        except ValueError:
            problems.append(f"not a valid wheel name: {filename}")
            continue
        if not any(tag in ranks for tag in tags):
            problems.append(
                f"wheel does not fit {platform} with CPython 3.12 (manylinux <= 2_28): {filename}"
            )
        if item.wheel_names is not None and any(n.endswith(".pyc") for n in item.wheel_names):
            problems.append(f"wheel contains bytecode (A-48): {filename}")
        if item.wheel_names == []:
            problems.append(f"wheel is not a readable zip file: {filename}")
    requirements = items.get("requirements.lock.txt")
    if requirements is not None and requirements.data is not None:
        try:
            pins = parse_requirements(requirements.data.decode("utf-8"))
        except BundleError as exc:
            return [*problems, f"requirements.lock.txt: {exc}"]
        hashes = {h for pin in pins for h in pin.hashes}
        wheel_hashes = {items[f"wheels/{n}"].sha256: n for n in names}
        problems += [
            f"wheel not pinned in requirements.lock.txt: {n}"
            for h, n in wheel_hashes.items()
            if h not in hashes
        ]
        problems += [f"pinned hash without a bundled wheel: {h}" for h in sorted(hashes - set(wheel_hashes))]
    return problems


def _check_info(items: Mapping[str, Item], version: str, platform: str) -> list[str]:
    info_item = items.get("BUNDLE.json")
    if info_item is None or info_item.data is None:
        return []
    try:
        info = json.loads(info_item.data.decode("utf-8"))
    except ValueError:
        return ["BUNDLE.json is not valid JSON"]
    problems = []
    if info.get("format_version") != FORMAT_VERSION:
        problems.append("BUNDLE.json: unsupported format_version")
    if info.get("version") != version or info.get("platform") != platform:
        problems.append("BUNDLE.json: version or platform differ from the root folder name")
    listed = {str(w.get("file")): (w.get("sha256"), w.get("size")) for w in info.get("wheels", [])}
    actual = {
        rel.removeprefix("wheels/"): (item.sha256, item.size)
        for rel, item in items.items()
        if rel.startswith("wheels/")
    }
    if listed != actual:
        problems.append("BUNDLE.json: wheel list differs from wheels/")
    for removed in info.get("python", {}).get("removed", []):
        if removed in items:
            problems.append(f"BUNDLE.json records {removed} as removed, but it is present")
    signed = SIGNATURE in items
    if signed != bool(info.get("release_identity")):
        problems.append("BUNDLE.json: release_identity and SHA256SUMS.sigstore.json must come together")
    if not isinstance(info.get("max_relative_install_path"), int):
        problems.append("BUNDLE.json: max_relative_install_path missing")
    return problems


def _check_readme(items: Mapping[str, Item]) -> list[str]:
    readme = items.get("README.txt")
    if readme is None or readme.data is None:
        return []
    from neurogrid.report.texts import disclaimer  # the fixed sentence of the language tables (A-08)

    text = readme.data.decode("utf-8", "replace")
    return [
        f"README.txt lacks the fixed sentence ({lang})"
        for lang in ("zh", "en")
        if disclaimer(lang) not in text
    ]


# --- lock (maintainers, network) ------------------------------------------------------------------------


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data: bytes = response.read()
            return data
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise BundleError(f"download failed: {url}: {exc}") from None


def cmd_lock(python: str, build_id: str, uv_version: str, lock_path: Path, cache: Path) -> int:
    """Rewrite bundle_lock.json from the release checksums of the interpreter and the PyPI data of uv."""
    base = f"https://github.com/astral-sh/python-build-standalone/releases/download/{build_id}"
    sums = {}
    for line in _get(f"{base}/SHA256SUMS").decode("utf-8").splitlines():
        digest, _, name = line.partition("  ")
        sums[name.strip()] = digest.strip()
    triples = {"win_amd64": "x86_64-pc-windows-msvc", "linux_x86_64": "x86_64-unknown-linux-gnu"}
    python_pins = {}
    for platform, triple in triples.items():
        filename = f"cpython-{python}+{build_id}-{triple}-install_only_stripped.tar.gz"
        if filename not in sums:
            raise BundleError(f"{filename} is not in the release SHA256SUMS")
        url = f"{base}/{urllib.parse.quote(filename)}"
        data = _get(url)
        if sha256_bytes(data) != sums[filename]:
            raise BundleError(f"{filename}: SHA-256 differs from the release SHA256SUMS")
        cache.mkdir(parents=True, exist_ok=True)
        (cache / sums[filename]).write_bytes(data)
        python_pins[platform] = {"url": url, "size": len(data), "sha256": sums[filename]}
    release = json.loads(_get(f"https://pypi.org/pypi/uv/{uv_version}/json"))
    files = {item["filename"]: item for item in release["urls"] if item["packagetype"] == "bdist_wheel"}
    wanted = {
        "win_amd64": f"uv-{uv_version}-py3-none-win_amd64.whl",
        "linux_x86_64": f"uv-{uv_version}-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
    }
    uv_pins = {}
    for platform, filename in wanted.items():
        if filename not in files:
            raise BundleError(f"{filename} is not on PyPI")
        item = files[filename]
        uv_pins[platform] = {
            "url": item["url"],
            "size": int(item["size"]),
            "sha256": item["digests"]["sha256"],
        }
    previous = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.is_file() else {}
    lock = {
        "format_version": FORMAT_VERSION,
        "python": {
            "version": python,
            "build": build_id,
            "flavor": "install_only_stripped",
            "platforms": python_pins,
        },
        "uv": {"version": uv_version, "source": "PyPI wheel", "platforms": uv_pins},
        "remove": previous.get("remove", {}),
    }
    lock_path.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"written {lock_path.relative_to(ROOT) if lock_path.is_relative_to(ROOT) else lock_path}")
    return 0


# --- command line ---------------------------------------------------------------------------------------


def source_date_epoch(root: Path, environ: Mapping[str, str]) -> int:
    value = environ.get("SOURCE_DATE_EPOCH")
    if value is not None:
        if not value.isdigit():
            raise BundleError("SOURCE_DATE_EPOCH must be a whole number of seconds")
        return int(value)
    result = subprocess.run(
        ["git", "log", "-1", "--format=%ct"], cwd=root, capture_output=True, text=True, check=False
    )
    if result.returncode != 0 or not result.stdout.strip().isdigit():
        raise BundleError("set SOURCE_DATE_EPOCH (no git commit to take the time from)")
    return int(result.stdout.strip())


def git_commit(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def cmd_build(args: argparse.Namespace) -> int:
    wheel = Path(args.wheel)
    sdist = (
        Path(args.sdist) if args.sdist else wheel.with_name(f"neurogrid-{wheel.name.split('-')[1]}.tar.gz")
    )
    cache = Path(args.cache or os.environ.get("NEUROGRID_BUNDLE_CACHE") or DEFAULT_CACHE)
    inputs = BuildInputs(
        platform=args.platform,
        wheel=wheel,
        sdist=sdist,
        docs=Path(args.docs),
        notices=Path(args.notices),
        pdf_installer=Path(args.pdf_installer),
        out=Path(args.out),
        cache=cache,
        sign=args.sign,
        lock=load_bundle_lock(),
        uv_lock_text=(ROOT / "uv.lock").read_text(encoding="utf-8"),
        requirements=export_requirements(),
        source_date_epoch=source_date_epoch(ROOT, os.environ),
        git_commit=git_commit(ROOT),
    )
    started = time.monotonic()
    target = build(inputs)
    problems = verify(target)
    if problems:
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        raise BundleError(f"{target.name}: the new bundle does not pass verify")
    size = target.stat().st_size
    print(
        f"{target.name}: {size / 2**20:.1f} MiB, sha256 {sha256_file(target)}, "
        f"{time.monotonic() - started:.0f} s"
    )
    return 0


def cmd_verify(path: Path) -> int:
    if not path.exists():
        raise BundleError(f"not found: {path}")
    problems = verify(path)
    for problem in problems:
        print(problem)
    print(f"{path.name}: {'ok' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


def cmd_sizes(platforms: Sequence[str]) -> int:
    lock = load_bundle_lock()
    pins = parse_requirements(export_requirements())
    uv_lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    for platform in platforms:
        wheels = select_wheels(uv_lock, pins, platform, str(lock["python"]["version"]))
        total = sum(ref.size for ref in wheels)
        line = f"{platform}: {len(wheels)} wheels, {total / 2**20:.1f} MiB"
        glibc = highest_manylinux([ref.filename for ref in wheels]) if platform != "win_amd64" else None
        print(line + (f", highest manylinux glibc {glibc[0]}.{glibc[1]}" if glibc else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--platform", required=True, choices=PLATFORMS)
    b.add_argument("--wheel", required=True)
    b.add_argument("--sdist")
    b.add_argument("--docs", required=True)
    b.add_argument("--notices", required=True)
    b.add_argument("--pdf-installer", default=str(ROOT / PDF_INSTALLER))
    b.add_argument("--out", default="dist")
    b.add_argument("--cache")
    b.add_argument("--sign", choices=("none", "sigstore"), default="none")
    v = sub.add_parser("verify")
    v.add_argument("path")
    s = sub.add_parser("sizes")
    s.add_argument("--platform", choices=PLATFORMS, action="append")
    lock = sub.add_parser("lock")
    lock.add_argument("--python", required=True)
    lock.add_argument("--pbs-build", required=True)
    lock.add_argument("--uv", required=True)
    lock.add_argument("--cache")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    try:
        if args.command == "build":
            return cmd_build(args)
        if args.command == "verify":
            return cmd_verify(Path(args.path))
        if args.command == "sizes":
            return cmd_sizes(args.platform or list(PLATFORMS))
        cache = Path(args.cache or os.environ.get("NEUROGRID_BUNDLE_CACHE") or DEFAULT_CACHE)
        return cmd_lock(args.python, args.pbs_build, args.uv, LOCK_FILE, cache)
    except BundleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
