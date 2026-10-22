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
check refuses (only their presence is compared; a folder the check refuses is walked, and every name below it
is refused as well), the manifest file itself and the excluded vault log. Names are not normalised (Unicode,
case): a manifest made on Linux with A.txt and a.txt shows one of them missing on Windows. The manifest hash
can be recomputed by anyone; it detects changes relative to the manifest, it does not protect against
deliberate rewriting.

A refused name is stored percent-encoded and can read like a plain name ('a:b.edf' as 'a%3Ab.edf'); the
reader and the comparison keep the two apart by the original name bytes. On Windows the walk uses the
extended-length form of the root (the \\\\?\\ prefix), so names Windows would otherwise change (a trailing
dot or space, reserved names) are listed and opened as they are.

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

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from neurogrid.kernel import canonical
from neurogrid.kernel.errors import InputError, UnsafePathError
from neurogrid.kernel.safety import MAX_PATH_CHARS, MAX_YAML_DEPTH, check_relative, is_link, read_limited

CHUNK_BYTES = 1024 * 1024
MANIFEST_FORMAT_VERSION = "1"
# The default location of the manifest, relative to the dataset root (KONZEPT 2.5, A-22, A-82): inside
# .neurogrid/, which the BIDS validator does not enter (a manifest.json at a BIDS root is NOT_INCLUDED). It is
# always left out of the inventory; everything else in .neurogrid/ is covered.
DEFAULT_MANIFEST = PurePosixPath(".neurogrid", "manifest.json")
MAX_MANIFEST_BYTES = 256_000_000  # as for results.json (A-53)
MAX_MANIFEST_ENTRIES = 2_000_000
# The longest relative path a walk can return, in UTF-8 bytes: Windows extended-length paths hold at most
# 32,767 UTF-16 units, each at most 3 UTF-8 bytes (a surrogate pair is 2 units and 4 bytes); POSIX PATH_MAX is
# far smaller. Percent-encoding turns a byte into at most 3 characters, so every refused name a walk finds,
# also deep below a refused folder, fits MAX_ESCAPED_CHARS; writer and reader use the same bound.
MAX_NAME_BYTES = 3 * 32_767
MAX_ESCAPED_CHARS = 3 * MAX_NAME_BYTES
# Nesting of JSON arrays and objects (A-53), checked before the schema, canonical JSON or the hash recurse
# into a document. The parameters of a processing step nest at most MAX_PARAMETER_DEPTH levels (the
# parameters object is level 1; provenance.yaml cannot nest deeper anyway). They sit at level 4 of a manifest
# and at level 3 of processing_steps.json, so neither file the builder or ``convert`` writes ever nests deeper
# than its reader's limit: the reader accepts every manifest the builder writes.
MAX_JSON_DEPTH = 64
MAX_PARAMETER_DEPTH = MAX_YAML_DEPTH
MAX_MANIFEST_DEPTH = MAX_PARAMETER_DEPTH + 3
MAX_STEPS_DEPTH = MAX_PARAMETER_DEPTH + 2
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


class NestingError(ValueError):
    """JSON nested deeper than MAX_JSON_DEPTH (A-53)."""


def nesting_within(value: Any, limit: int) -> bool:
    """True if lists and mappings in ``value`` nest at most ``limit`` levels (a scalar is level 0).

    Iterative, level by level, so any depth is measured without recursion."""
    level = [value] if isinstance(value, (dict, list, tuple)) else []
    depth = 0
    while level:
        depth += 1
        if depth > limit:
            return False
        nested = []
        for item in level:
            for child in item.values() if isinstance(item, dict) else item:
                if isinstance(child, (dict, list, tuple)):
                    nested.append(child)
        level = nested
    return True


# --- models ---------------------------------------------------------------------------------------------

# The models hold names from the dataset: a validation error never shows its input (--debug tracebacks, A-51).


class ProcessingStep(BaseModel):
    """DM-07 ProcessingStep: schritt→step, werkzeug→tool, version, parameter→parameters,
    eingabe_hash→input_hash, ausgabe_hash→output_hash. ``convert`` writes one per recording (A-77); the
    manifest repeats the steps it found (A-22). Re-exported by neurogrid.model.dataset."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    step: str = Field(max_length=200)
    tool: str = Field(max_length=200)
    version: str = Field(max_length=80)
    parameters: dict[str, Any] = Field(default_factory=dict)
    input_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    output_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @field_validator("parameters")
    @classmethod
    def _bounded_nesting(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Parameters nested deeper than MAX_PARAMETER_DEPTH would give a manifest its reader refuses."""
        if not nesting_within(value, MAX_PARAMETER_DEPTH):
            raise ValueError("parameters nested too deeply")
        return value


class ManifestFile(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    path: str = Field(min_length=1, max_length=MAX_PATH_CHARS)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size: int = Field(ge=0)


SkippedKind = Literal["link", "special", "unsafe_name"]


class SkippedEntry(BaseModel):
    """An entry that was not hashed: a link or junction (not followed), a special file (FIFO, socket, device;
    reading could block, A-78) or a name the central path check refuses (A-52, critic X8). The path of an
    ``unsafe_name`` is stored percent-encoded (bytes outside ``[A-Za-z0-9._- /]`` as ``%XX``)."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    path: str = Field(min_length=1, max_length=MAX_ESCAPED_CHARS)
    kind: SkippedKind


class SoftwareEntry(BaseModel):
    """A software version: ``manifest`` (the NeuroGrid that wrote the manifest), ``processing_steps`` (tool of
    a processing step), ``provenance`` (.neurogrid/provenance.yaml) or ``bids`` (dataset_description.json
    GeneratedBy)."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    source: Literal["manifest", "processing_steps", "provenance", "bids"]


class Manifest(BaseModel):
    """manifest.json, format version 1 (A-22, A-82, KONZEPT 2.5 plus ``skipped`` and ``excluded``)."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

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


def _walk_root(root: Path) -> Path:
    """The root a walk starts from: on Windows its extended-length form (``\\\\?\\``), so that names Windows
    would otherwise change (a trailing dot or space, reserved names such as aux) and long paths are listed and
    opened as they are."""
    if os.name != "nt":
        return root
    text = os.path.normpath(root.absolute())  # the extended form is taken literally: no "..", backslashes
    if text.startswith("\\\\?\\"):
        return Path(text)
    if text.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + text[2:])
    return Path("\\\\?\\" + text)


def inventory(root: Path, exclusions: Exclusions | None = None) -> Inventory:
    """Walk ``root`` without following links: everything is included (hidden entries, .neurogrid/, BIDS
    derivatives, OS files such as .DS_Store), except the excluded paths (A-22, A-82).

    A folder whose name the path check refuses is recorded and walked (unless it is a link): every name below
    it is refused as well and recorded, so that new and missing entries there are noticed (presence only,
    never hashed, critic X8). A folder that cannot be listed is reported in ``unlistable``."""
    exclusions = exclusions or Exclusions()
    result = Inventory()
    top = _walk_root(root)

    def unlistable(error: OSError) -> None:
        result.unlistable.append(_relative_to(error.filename, top))

    def refused(relative: str) -> None:
        escaped = escape_name(relative)
        if len(escaped) > MAX_ESCAPED_CHARS:  # longer than any path a system returns: cannot be recorded
            result.unreadable.append(relative)
        else:
            result.skipped.append(SkippedEntry(path=escaped, kind="unsafe_name"))

    for dirpath, dirnames, filenames in os.walk(top, onerror=unlistable, followlinks=False):
        current = Path(dirpath)
        base = _relative_to(current, top)
        prefix = "" if base == "." else base + "/"
        kept = []
        for name in sorted(dirnames):
            relative = prefix + name
            if exclusions.covers(relative):
                continue
            linked = is_link(current / name)
            if not safe_relative(relative):
                refused(relative)
                if not linked:
                    kept.append(name)
            elif linked:
                result.skipped.append(SkippedEntry(path=relative, kind="link"))
            else:
                kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            relative = prefix + name
            if exclusions.covers(relative):
                continue
            if not safe_relative(relative):
                refused(relative)
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
    """A manifest, or None with the files and folders that could not be read, or with ``too_many`` (the
    limit) when the dataset holds more entries than a manifest lists (nothing is written then)."""

    manifest: Manifest | None
    unreadable: tuple[str, ...]
    skipped: tuple[SkippedEntry, ...]
    total_bytes: int
    too_many: int | None = None


def build_manifest(
    root: Path,
    exclusions: Exclusions,
    *,
    excluded: Sequence[str] = (),
    processing_steps: Sequence[ProcessingStep] = (),
    software: Sequence[SoftwareEntry] = (),
    threads: int = HASH_THREADS,
) -> BuildResult:
    """Inventory and hash ``root``. ``excluded`` lists the paths recorded as left out (the vault log).

    More than MAX_MANIFEST_ENTRIES files or skipped entries cannot be written: that is dataset data, so it is
    a result without a manifest (``too_many``, nothing hashed; exit 1, C2), not an error. Steps whose
    parameters canonical JSON cannot hold are an error (``manifest.steps_invalid``)."""
    found = inventory(root, exclusions)
    if max(len(found.files), len(found.skipped)) > MAX_MANIFEST_ENTRIES:
        return BuildResult(None, (), (), 0, too_many=MAX_MANIFEST_ENTRIES)
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
    try:
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
    except (TypeError, ValueError, RecursionError):  # defensive: the readers of the step sources refuse these
        raise ManifestError("manifest.steps_invalid", problem="value") from None
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


def strict_json(text: str, *, max_depth: int = MAX_JSON_DEPTH) -> Any:
    """JSON without duplicate keys, NaN or Infinity, nested at most ``max_depth`` levels (A-53, A-61); raises
    ValueError, NestingError for too deep nesting. Nothing deeper reaches a schema, canonical JSON or a hash,
    which recurse."""
    try:
        value = json.loads(
            text, object_pairs_hook=_unique_keys, parse_constant=_no_constant, parse_float=_finite_float
        )
    except RecursionError:
        raise NestingError("nested too deeply") from None
    if not nesting_within(value, max_depth):
        raise NestingError("nested too deeply")
    return value


def _check_plain(path: str, location: str) -> None:
    if not safe_relative(path):
        raise ManifestError("manifest.unsafe_path", field=location)


def _check_paths(manifest: Manifest) -> None:
    """Every path must be a plain relative path (A-52) and occur once; they are compared, never opened.

    "Once" is decided on the original name bytes: a refused name stored as 'a%3Ab.edf' and a plain file named
    'a%3Ab.edf' are two entries, the same name listed twice (in any spelling) is refused."""
    seen: set[bytes] = set()

    def once(name: bytes, location: str) -> None:
        if name in seen:
            raise ManifestError("manifest.duplicate_path", field=location)
        seen.add(name)

    for index, item in enumerate(manifest.files):
        _check_plain(item.path, f"files.{index}.path")
        once(name_bytes(item.path), f"files.{index}.path")
    for index, entry in enumerate(manifest.skipped):
        location = f"skipped.{index}.path"
        if entry.kind == "unsafe_name":
            if not _ESCAPED_NAME.match(entry.path):
                raise ManifestError("manifest.unsafe_path", field=location)
        else:
            _check_plain(entry.path, location)
        once(name_bytes(entry.path, entry.kind), location)
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
        raw = strict_json(text, max_depth=MAX_MANIFEST_DEPTH)
    except NestingError:
        raise ManifestError("manifest.invalid", field="-", problem="too_deep") from None
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
    except (TypeError, ValueError, RecursionError):  # defensive: content canonical JSON cannot hold
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
    skipped entry changed; unreadable: listed in the manifest, but it cannot be examined now (a file that
    cannot be read, or any entry below a folder that cannot be listed, A-82)."""

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


def _below(name: bytes, folders: Sequence[bytes]) -> bool:
    return any(folder == b"." or name == folder or name.startswith(folder + b"/") for folder in folders)


def compare(
    root: Path, manifest: Manifest, exclusions: Exclusions, *, threads: int = HASH_THREADS
) -> Comparison:
    """Compare the dataset with a manifest: sizes first (a different size is a change without hashing), then
    the hashes of the remaining common files. Paths the exclusions cover are not compared.

    Entries are matched by their original name bytes, so a refused name (stored percent-encoded) and a plain
    name that reads the same stay two entries; a deviation carries the path as the manifest stores it."""
    found = inventory(root, exclusions)
    before: dict[bytes, tuple[str, str]] = {}  # name bytes -> (stored path, kind)
    listed: dict[bytes, ManifestFile] = {}
    for entry in manifest.skipped:
        before[name_bytes(entry.path, entry.kind)] = (entry.path, entry.kind)
    for item in manifest.files:
        before[name_bytes(item.path)] = (item.path, "file")
        listed[name_bytes(item.path)] = item
    now: dict[bytes, tuple[str, str]] = {}
    current: dict[bytes, FileEntry] = {}
    for entry in found.skipped:
        now[name_bytes(entry.path, entry.kind)] = (entry.path, entry.kind)
    for file in found.files:
        now[name_bytes(file.relative)] = (file.relative, "file")
        current[name_bytes(file.relative)] = file
    for path in found.unreadable:
        now[name_bytes(path)] = (path, "unreadable")
    unlistable = [os.fsencode(folder) for folder in found.unlistable]
    deviations: list[Deviation] = []
    to_hash: list[tuple[FileEntry, ManifestFile]] = []
    for name in sorted(set(before) | set(now)):
        if exclusions.covers(name.decode("utf-8", "surrogateescape")):
            continue
        stored_path, was = before.get(name, ("", None))
        present_path, is_now = now.get(name, ("", None))
        path = stored_path or present_path
        size_manifest = listed[name].size if name in listed else None
        size_now = current[name].size if name in current else None
        if is_now is None and was is not None and _below(name, unlistable):
            is_now = "unreadable"
        if was is None:
            deviations.append(Deviation(path, "new", now=is_now, size_now=size_now))
        elif is_now is None:
            deviations.append(Deviation(path, "missing", before=was, size_manifest=size_manifest))
        elif was == "file" and is_now == "file":
            if listed[name].size != current[name].size:
                deviations.append(Deviation(path, "changed", "file", "file", size_manifest, size_now))
            else:
                to_hash.append((current[name], listed[name]))
        elif is_now == "unreadable":
            deviations.append(Deviation(path, "unreadable", was, "unreadable", size_manifest))
        elif was != is_now:
            deviations.append(Deviation(path, "skipped_changed", was, is_now, size_manifest, size_now))
    hashed = hash_files([entry for entry, _item in to_hash], threads)
    checked = 0
    for (_entry, item), digest in zip(to_hash, hashed, strict=True):
        if digest is None:
            deviations.append(Deviation(item.path, "unreadable", "file", "unreadable", item.size))
            continue
        checked += digest[1]
        if digest[0] != item.sha256 or digest[1] != item.size:
            deviations.append(Deviation(item.path, "changed", "file", "file", item.size, digest[1]))
    deviations.sort(key=lambda deviation: (deviation.path, deviation.unsafe))
    return Comparison(tuple(deviations), len(manifest.files), checked)
