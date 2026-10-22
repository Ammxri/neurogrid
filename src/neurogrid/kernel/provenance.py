"""Provenance (M13, NG-F10, A-22, A-82): streaming file hashes, the manifest model, the dataset inventory, the
manifest builder and reader, and the comparison of a dataset with its manifest.

manifest.json (format_version "1"; by default <dataset>/.neurogrid/manifest.json, KONZEPT 2.5, A-22, A-82)
holds the sorted file list (path, SHA-256, size), the entries that were not followed or not hashed
(``skipped``: links and junctions, special files such as FIFOs or devices, and names the central path check
refuses, A-52), the excluded paths (``excluded``: the hash-chained vault log, so that ``verify`` needs no
neurogrid.toml), the processing steps (DM-07), the software versions and
``manifest_hash``: SHA-256 over the compact canonical JSON of everything else (kernel/canonical.py, A-61). It
is not the ``sha256sum`` of the file. The manifest holds no time stamp, host or user name and no absolute
path, so the same data give byte-identical manifests (A-11).

What a manifest does not cover, by design: directories (empty folders), mtime and permissions, NTFS alternate
data streams, the targets of links (never followed), the contents of special files and of names the path
check refuses (only their presence is compared), the manifest file itself and the excluded vault log. Names
are not normalised (Unicode, case): a manifest made on Linux with A.txt and a.txt shows one of them missing on
Windows. The manifest hash can be recomputed by anyone; it detects changes relative to the manifest, it does
not protect against deliberate rewriting.

Hashing streams in CHUNK_BYTES pieces over a file descriptor opened without following links (where the system
offers it), checks that the descriptor is the regular file that was listed and that the number of bytes read
equals its size, and runs in up to HASH_THREADS threads (hashlib releases the GIL); results keep input order.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from neurogrid.kernel import canonical
from neurogrid.kernel.errors import InputError, UnsafePathError
from neurogrid.kernel.safety import MAX_PATH_CHARS, check_relative, is_link, read_limited

CHUNK_BYTES = 1024 * 1024
MANIFEST_FORMAT_VERSION = "1"
# The default location of the manifest, relative to the dataset root (KONZEPT 2.5, A-22, A-82): inside
# .neurogrid/, which the BIDS validator does not enter (a manifest.json at a BIDS root is NOT_INCLUDED). It is
# always left out of the inventory; everything else in .neurogrid/ is covered.
DEFAULT_MANIFEST = PurePosixPath(".neurogrid", "manifest.json")
MAX_MANIFEST_BYTES = 256_000_000  # as for results.json (A-53)
MAX_MANIFEST_ENTRIES = 2_000_000
HASH_THREADS = max(1, min(4, os.cpu_count() or 1))
HASH_BATCH = 4096  # files submitted to the thread pool at a time: memory stays bounded for large datasets
VAULT_LOG = "access.jsonl"  # the separately hash-chained access log (A-22, A-30) and its lock file
VAULT_LOCK = "access.jsonl.lock"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
_ESCAPE_SAFE = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._- /")
_ESCAPED_NAME = re.compile(r"^(?:[A-Za-z0-9._\- /]|%[0-9A-F]{2})+$")
_OPEN_FLAGS = (
    os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ManifestError(InputError):
    """An unusable manifest: not found, too large, not JSON, wrong format version, unsafe or duplicate paths.

    ``verify`` and ``manifest`` end with exit 2; ``check`` reports it as CORE-M13-01 failed (A-82, C2).
    Parameters name the field, never a path or a value from the file.
    """


# --- models ---------------------------------------------------------------------------------------------


class ProcessingStep(BaseModel):
    """DM-07 ProcessingStep: schritt→step, werkzeug→tool, version, parameter→parameters,
    eingabe_hash→input_hash, ausgabe_hash→output_hash. ``convert`` writes one per recording (A-77); the
    manifest repeats the steps it found (A-22). Re-exported by neurogrid.model.dataset."""

    model_config = ConfigDict(extra="forbid")

    step: str = Field(max_length=200)
    tool: str = Field(max_length=200)
    version: str = Field(max_length=80)
    parameters: dict[str, Any] = Field(default_factory=dict)
    input_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    output_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)


class ManifestFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=MAX_PATH_CHARS)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size: int = Field(ge=0)


SkippedKind = Literal["link", "special", "unsafe_name"]


class SkippedEntry(BaseModel):
    """An entry that was not hashed: a link or junction (not followed), a special file (FIFO, socket, device;
    reading could block, A-78) or a name the central path check refuses (A-52, critic X8). The path of an
    ``unsafe_name`` is stored percent-encoded (bytes outside ``[A-Za-z0-9._- /]`` as ``%XX``)."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=3 * MAX_PATH_CHARS)
    kind: SkippedKind


class SoftwareEntry(BaseModel):
    """A software version: ``manifest`` (the NeuroGrid that wrote the manifest), ``processing_steps`` (tool of
    a processing step), ``provenance`` (.neurogrid/provenance.yaml) or ``bids`` (dataset_description.json
    GeneratedBy)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    source: Literal["manifest", "processing_steps", "provenance", "bids"]


class Manifest(BaseModel):
    """manifest.json, format version 1 (A-22, A-82, KONZEPT 2.5 plus ``skipped`` and ``excluded``)."""

    model_config = ConfigDict(extra="forbid")

    format_version: Literal["1"]
    files: list[ManifestFile] = Field(max_length=MAX_MANIFEST_ENTRIES)
    skipped: list[SkippedEntry] = Field(max_length=MAX_MANIFEST_ENTRIES)
    excluded: list[str] = Field(max_length=64)
    processing_steps: list[ProcessingStep] = Field(max_length=MAX_MANIFEST_ENTRIES)
    software: list[SoftwareEntry] = Field(max_length=10_000)
    manifest_hash: str = Field(pattern=SHA256_PATTERN)


class ManifestStatus(StrEnum):
    """results.json ``manifest.status`` (A-82): not_verified = read, but no loaded rule compared the files."""

    MISSING = "missing"
    INVALID = "invalid"
    HASH_MISMATCH = "hash_mismatch"
    DIFFERS = "differs"
    MATCHES = "matches"
    NOT_VERIFIED = "not_verified"
    NOT_APPLICABLE = "not_applicable"


def manifest_hash(content: Mapping[str, Any]) -> str:
    """SHA-256 over the compact canonical JSON of the manifest without its ``manifest_hash`` field."""
    return canonical.sha256_of({key: value for key, value in content.items() if key != "manifest_hash"})


def manifest_bytes(manifest: Manifest) -> bytes:
    """manifest.json as written: canonical, indented, sorted keys, LF, UTF-8 without BOM."""
    return canonical.dumps(manifest)


# --- names ----------------------------------------------------------------------------------------------


def safe_relative(relative: str) -> bool:
    """A path the manifest can store as it is: valid Unicode and unchanged by the central path check (A-52).

    Names the check refuses (``aux.txt``, ``a:b``, a trailing dot or space, control characters) and names it
    would change (a backslash on Linux) are stored as ``unsafe_name`` entries instead (critic X8)."""
    if any(0xD800 <= ord(char) <= 0xDFFF for char in relative):
        return False
    try:
        return check_relative(relative).as_posix() == relative
    except UnsafePathError:
        return False


def escape_name(relative: str) -> str:
    """Percent-encoding of the name bytes (os.fsencode); reversible and free of backslashes."""
    return "".join(chr(byte) if byte in _ESCAPE_SAFE else f"%{byte:02X}" for byte in os.fsencode(relative))


def name_bytes(path: str, kind: str | None = None) -> bytes:
    """The original name bytes of a stored path (pseudonyms are taken over them, A-51)."""
    if kind == "unsafe_name":
        out = bytearray()
        index = 0
        while index < len(path):
            if path[index] == "%":
                out.append(int(path[index + 1 : index + 3], 16))
                index += 3
            else:
                out.append(ord(path[index]))
                index += 1
        return bytes(out)
    return os.fsencode(path)


# --- inventory ------------------------------------------------------------------------------------------


def _key(relative: str) -> str:
    return relative.lower() if os.name == "nt" else relative


@dataclass(frozen=True)
class Exclusions:
    """Relative POSIX paths left out of an inventory, compared without case on Windows: files (the manifest,
    the vault log) and folders with everything below them (the run's transient work folder)."""

    files: frozenset[str] = frozenset()
    folders: tuple[str, ...] = ()

    @classmethod
    def of(cls, files: Iterable[str] = (), folders: Iterable[str] = ()) -> Exclusions:
        return cls(frozenset(_key(item) for item in files), tuple(sorted({_key(item) for item in folders})))

    def covers(self, relative: str) -> bool:
        key = _key(relative)
        return key in self.files or any(
            key == folder or key.startswith(folder + "/") for folder in self.folders
        )


@dataclass(frozen=True)
class FileEntry:
    relative: str
    path: Path
    size: int
    device: int
    inode: int


@dataclass
class Inventory:
    """What a walk found: regular files, skipped entries, files that could not be examined and folders that
    could not be listed (all sorted by path)."""

    files: list[FileEntry] = field(default_factory=list)
    skipped: list[SkippedEntry] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)
    unlistable: list[str] = field(default_factory=list)


def _relative_to(location: str | os.PathLike[str] | None, root: Path) -> str:
    try:
        relative = Path(location or root).relative_to(root).as_posix()
    except ValueError:
        return "."
    return relative or "."


def inventory(root: Path, exclusions: Exclusions | None = None) -> Inventory:
    """Walk ``root`` without following links: everything is included (hidden entries, .neurogrid/, BIDS
    derivatives, OS files such as .DS_Store), except the excluded paths (A-22, A-82)."""
    exclusions = exclusions or Exclusions()
    result = Inventory()

    def unlistable(error: OSError) -> None:
        result.unlistable.append(_relative_to(error.filename, root))

    for dirpath, dirnames, filenames in os.walk(root, onerror=unlistable, followlinks=False):
        current = Path(dirpath)
        base = _relative_to(current, root)
        prefix = "" if base == "." else base + "/"
        kept = []
        for name in sorted(dirnames):
            relative = prefix + name
            if exclusions.covers(relative):
                continue
            if not safe_relative(relative):
                result.skipped.append(SkippedEntry(path=escape_name(relative), kind="unsafe_name"))
            elif is_link(current / name):
                result.skipped.append(SkippedEntry(path=relative, kind="link"))
            else:
                kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            relative = prefix + name
            if exclusions.covers(relative):
                continue
            if not safe_relative(relative):
                result.skipped.append(SkippedEntry(path=escape_name(relative), kind="unsafe_name"))
                continue
            path = current / name
            if is_link(path):
                result.skipped.append(SkippedEntry(path=relative, kind="link"))
                continue
            try:
                info = os.lstat(path)
            except OSError:
                result.unreadable.append(relative)
                continue
            if not stat.S_ISREG(info.st_mode):
                result.skipped.append(SkippedEntry(path=relative, kind="special"))
                continue
            result.files.append(FileEntry(relative, path, info.st_size, info.st_dev, info.st_ino))
    result.files.sort(key=lambda entry: entry.relative)
    result.skipped.sort(key=lambda entry: entry.path)
    result.unreadable.sort()
    result.unlistable.sort()
    return result


def hash_file(entry: FileEntry) -> tuple[str, int] | None:
    """SHA-256 and size of a listed regular file, or None if it cannot be read as that file.

    The descriptor must be a regular file with the device and inode that were listed (a swap for a link or a
    FIFO between listing and opening is not read), and the bytes read must equal its size (a file that grows
    or shrinks while it is hashed is not reported with a wrong hash)."""
    try:
        descriptor = os.open(entry.path, _OPEN_FLAGS)
    except OSError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            return None
        if entry.inode and info.st_ino and (info.st_dev, info.st_ino) != (entry.device, entry.inode):
            return None
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(descriptor, CHUNK_BYTES):
            digest.update(chunk)
            total += len(chunk)
        if total != info.st_size:
            return None
        return digest.hexdigest(), total
    except OSError:
        return None
    finally:
        os.close(descriptor)


def hash_files(entries: Sequence[FileEntry], threads: int = HASH_THREADS) -> list[tuple[str, int] | None]:
    """Hashes in input order; the result does not depend on the number of threads."""
    if threads <= 1 or len(entries) <= 1:
        return [hash_file(entry) for entry in entries]
    results: list[tuple[str, int] | None] = []
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for start in range(0, len(entries), HASH_BATCH):
            results.extend(pool.map(hash_file, entries[start : start + HASH_BATCH]))
    return results


# --- build ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildResult:
    """A manifest, or None with the files and folders that could not be read (nothing is written then)."""

    manifest: Manifest | None
    unreadable: tuple[str, ...]
    skipped: tuple[SkippedEntry, ...]
    total_bytes: int


def build_manifest(
    root: Path,
    exclusions: Exclusions,
    *,
    excluded: Sequence[str] = (),
    processing_steps: Sequence[ProcessingStep] = (),
    software: Sequence[SoftwareEntry] = (),
    threads: int = HASH_THREADS,
) -> BuildResult:
    """Inventory and hash ``root``. ``excluded`` lists the paths recorded as left out (the vault log)."""
    found = inventory(root, exclusions)
    hashes = hash_files(found.files, threads)
    failed = {entry.relative for entry, digest in zip(found.files, hashes, strict=True) if digest is None}
    unreadable = tuple(sorted(failed | set(found.unreadable) | set(found.unlistable)))
    if unreadable:
        return BuildResult(None, unreadable, tuple(found.skipped), 0)
    files = [
        ManifestFile(path=entry.relative, sha256=digest[0], size=digest[1])
        for entry, digest in zip(found.files, hashes, strict=True)
        if digest is not None
    ]
    unique = {(item.name, item.version, item.source): item for item in software}
    content: dict[str, Any] = canonical.normalize(
        {
            "format_version": MANIFEST_FORMAT_VERSION,
            "files": [item.model_dump(mode="json") for item in files],
            "skipped": [item.model_dump(mode="json") for item in found.skipped],
            "excluded": sorted(set(excluded)),
            "processing_steps": [step.model_dump(mode="json") for step in processing_steps],
            "software": [unique[key].model_dump(mode="json") for key in sorted(unique)],
        }
    )
    manifest = Manifest.model_validate({**content, "manifest_hash": manifest_hash(content)})
    return BuildResult(manifest, (), tuple(found.skipped), sum(item.size for item in files))


# --- read -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedManifest:
    manifest: Manifest
    hash_ok: bool  # the stored manifest_hash equals the hash of the content


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _no_constant(_name: str) -> Any:
    raise ValueError("NaN or Infinity")


def _finite_float(text: str) -> float:
    value = float(text)
    if value in (float("inf"), float("-inf")):
        raise ValueError("number out of range")
    return value


def strict_json(text: str) -> Any:
    """JSON without duplicate keys, NaN or Infinity (A-53, A-61); raises ValueError."""
    try:
        return json.loads(
            text, object_pairs_hook=_unique_keys, parse_constant=_no_constant, parse_float=_finite_float
        )
    except RecursionError:
        raise ValueError("nested too deeply") from None


def _check_plain(path: str, location: str) -> None:
    if not safe_relative(path):
        raise ManifestError("manifest.unsafe_path", field=location)


def _check_paths(manifest: Manifest) -> None:
    """Every path must be a plain relative path (A-52) and occur once; they are compared, never opened."""
    seen: set[str] = set()

    def once(path: str, location: str) -> None:
        if path in seen:
            raise ManifestError("manifest.duplicate_path", field=location)
        seen.add(path)

    for index, item in enumerate(manifest.files):
        _check_plain(item.path, f"files.{index}.path")
        once(item.path, f"files.{index}.path")
    for index, entry in enumerate(manifest.skipped):
        location = f"skipped.{index}.path"
        if entry.kind == "unsafe_name":
            if not _ESCAPED_NAME.match(entry.path):
                raise ManifestError("manifest.unsafe_path", field=location)
        else:
            _check_plain(entry.path, location)
        once(entry.path, location)
    for index, excluded in enumerate(manifest.excluded):
        _check_plain(excluded, f"excluded.{index}")
        if PurePosixPath(excluded).name not in (VAULT_LOG, VAULT_LOCK):
            raise ManifestError("manifest.excluded_invalid", field=f"excluded.{index}")


def parse_manifest(data: bytes) -> ParsedManifest:
    """Validate manifest.json bytes: UTF-8 (BOM tolerated), strict JSON, format version 1, strict schema,
    plain unique paths. The manifest hash is recomputed over the content as read (key order and indentation
    do not matter, A-61); a mismatch is reported, not refused."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ManifestError("manifest.encoding") from None
    try:
        raw = strict_json(text)
    except ValueError:
        raise ManifestError("manifest.invalid", field="-", problem="json") from None
    if not isinstance(raw, dict):
        raise ManifestError("manifest.invalid", field="-", problem="object")
    if "format_version" in raw and raw["format_version"] != MANIFEST_FORMAT_VERSION:
        raise ManifestError("manifest.unsupported_version")
    try:
        manifest = Manifest.model_validate(raw, strict=True)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or "-"
        raise ManifestError("manifest.invalid", field=location, problem=first["type"]) from None
    _check_paths(manifest)
    try:
        computed = manifest_hash(raw)
    except (TypeError, ValueError):  # defensive: content canonical JSON cannot hold
        raise ManifestError("manifest.invalid", field="-", problem="value") from None
    return ParsedManifest(manifest, computed == manifest.manifest_hash)


def read_manifest(path: Path) -> ParsedManifest:
    """Read and validate a manifest file (size limit before reading, A-53)."""
    try:
        data = read_limited(path, MAX_MANIFEST_BYTES)
    except InputError:
        raise ManifestError("manifest.too_large", limit=MAX_MANIFEST_BYTES) from None
    except OSError:
        raise ManifestError("manifest.unreadable") from None
    return parse_manifest(data)


# --- compare --------------------------------------------------------------------------------------------

DeviationKind = Literal["changed", "new", "missing", "skipped_changed", "unreadable"]
DEVIATION_KINDS: tuple[DeviationKind, ...] = ("changed", "new", "missing", "skipped_changed", "unreadable")


@dataclass(frozen=True)
class Deviation:
    """One path that differs from the manifest.

    ``before`` and ``now`` are "file", a skipped kind (link, special, unsafe_name), "unreadable" or None
    (absent). changed: same path, other content or size; new / missing: absent in the manifest / now;
    skipped_changed: present in both, but a file became a link (or the other way round) or the kind of a
    skipped entry changed; unreadable: listed as a file, but it cannot be read now (A-82)."""

    path: str
    kind: DeviationKind
    before: str | None = None
    now: str | None = None
    size_manifest: int | None = None
    size_now: int | None = None

    @property
    def unsafe(self) -> bool:
        return "unsafe_name" in (self.before, self.now)


@dataclass(frozen=True)
class Comparison:
    deviations: tuple[Deviation, ...]
    files: int  # files listed in the manifest
    checked_bytes: int  # bytes hashed during the comparison

    def count(self, kind: DeviationKind) -> int:
        return sum(1 for deviation in self.deviations if deviation.kind == kind)

    def of(self, kind: DeviationKind) -> list[Deviation]:
        return [deviation for deviation in self.deviations if deviation.kind == kind]


def _below(path: str, folders: Sequence[str]) -> bool:
    return any(folder == "." or path == folder or path.startswith(folder + "/") for folder in folders)


def compare(
    root: Path, manifest: Manifest, exclusions: Exclusions, *, threads: int = HASH_THREADS
) -> Comparison:
    """Compare the dataset with a manifest: sizes first (a different size is a change without hashing), then
    the hashes of the remaining common files. Paths the exclusions cover are not compared."""
    found = inventory(root, exclusions)
    before: dict[str, str] = {entry.path: entry.kind for entry in manifest.skipped}
    before.update({item.path: "file" for item in manifest.files})
    sizes = {item.path: item for item in manifest.files}
    now: dict[str, str] = {entry.path: entry.kind for entry in found.skipped}
    now.update({entry.relative: "file" for entry in found.files})
    now.update({path: "unreadable" for path in found.unreadable})
    current = {entry.relative: entry for entry in found.files}
    deviations: list[Deviation] = []
    to_hash: list[FileEntry] = []
    for path in sorted(set(before) | set(now)):
        if exclusions.covers(path):
            continue
        was, is_now = before.get(path), now.get(path)
        if is_now is None and was is not None and _below(path, found.unlistable):
            is_now = "unreadable"
        if was is None:
            deviations.append(Deviation(path, "new", now=is_now, size_now=_size(current, path)))
        elif is_now is None:
            deviations.append(Deviation(path, "missing", before=was, size_manifest=_listed(sizes, path)))
        elif was == "file" and is_now == "file":
            listed, entry = sizes[path], current[path]
            if listed.size != entry.size:
                deviations.append(Deviation(path, "changed", "file", "file", listed.size, entry.size))
            else:
                to_hash.append(entry)
        elif was == "file" and is_now == "unreadable":
            deviations.append(Deviation(path, "unreadable", "file", "unreadable", sizes[path].size))
        elif was != is_now:
            deviations.append(
                Deviation(path, "skipped_changed", was, is_now, _listed(sizes, path), _size(current, path))
            )
    hashed = hash_files(to_hash, threads)
    checked = 0
    for entry, digest in zip(to_hash, hashed, strict=True):
        listed = sizes[entry.relative]
        if digest is None:
            deviations.append(Deviation(entry.relative, "unreadable", "file", "unreadable", listed.size))
            continue
        checked += digest[1]
        if digest[0] != listed.sha256 or digest[1] != listed.size:
            deviations.append(Deviation(entry.relative, "changed", "file", "file", listed.size, digest[1]))
    deviations.sort(key=lambda deviation: deviation.path)
    return Comparison(tuple(deviations), len(manifest.files), checked)


def _size(current: Mapping[str, FileEntry], path: str) -> int | None:
    entry = current.get(path)
    return entry.size if entry is not None else None


def _listed(sizes: Mapping[str, ManifestFile], path: str) -> int | None:
    item = sizes.get(path)
    return item.size if item is not None else None
