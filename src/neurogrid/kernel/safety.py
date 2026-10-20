"""Input and output safety: strict YAML loading and bounded file reads (A-53), path checks (A-52),
the output filter for paths (A-51) and per-run work directories (A-54)."""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import tempfile
from collections.abc import Hashable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node

from neurogrid.kernel.errors import ConfigError, InputError, UnsafePathError

MAX_YAML_BYTES = 2_000_000
MAX_YAML_DEPTH = 32
MAX_PATH_CHARS = 1024

_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CONIN$",
    "CONOUT$",
    *(f"{device}{digit}" for device in ("COM", "LPT") for digit in "123456789\u00b9\u00b2\u00b3"),
}
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader without aliases, with duplicate-key detection and a nesting limit while composing.

    The limit is enforced before PyYAML recurses further, so deeply nested input ends with a clean error
    instead of a RecursionError.
    """

    max_depth = MAX_YAML_DEPTH

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._depth = 0

    def compose_node(self, parent: Node | None, index: int) -> Node | None:
        if self.check_event(yaml.events.AliasEvent):
            # peek_event is untyped in the PyYAML stubs; getattr keeps strict and normal mypy runs clean
            mark = getattr(self, "peek_event")().start_mark  # noqa: B009
            raise ConfigError("yaml.alias", line=mark.line + 1)
        collection = self.check_event(yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent)
        if collection:
            self._depth += 1
            if self._depth > self.max_depth:
                raise ConfigError("yaml.too_deep", limit=self.max_depth)
        try:
            return super().compose_node(parent, index)
        finally:
            if collection:
                self._depth -= 1

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        seen: set[Hashable] = set()
        for key_node, _value in node.value:
            key = self.construct_object(key_node, deep=deep)
            line = key_node.start_mark.line + 1
            if not isinstance(key, Hashable):
                raise ConfigError("yaml.syntax", line=line)
            if key in seen:
                raise ConfigError("yaml.duplicate_key", name=str(key)[:80], line=line)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_yaml(text: str, *, max_bytes: int = MAX_YAML_BYTES, max_depth: int = MAX_YAML_DEPTH) -> Any:
    """Parse untrusted YAML: no aliases, no duplicate keys, bounded size and nesting."""
    if len(text.encode("utf-8", "surrogatepass")) > max_bytes:
        raise ConfigError("yaml.too_large", limit=max_bytes)
    try:
        loader = _StrictLoader(text)  # the reader already rejects control characters here
    except yaml.YAMLError:
        raise ConfigError("yaml.syntax", line="?") from None
    loader.max_depth = max_depth
    try:
        return loader.get_single_data()
    except yaml.YAMLError as exc:
        line = getattr(getattr(exc, "problem_mark", None), "line", None)
        raise ConfigError("yaml.syntax", line=(line + 1) if line is not None else "?") from None
    except RecursionError:
        raise ConfigError("yaml.too_deep", limit=max_depth) from None
    except ValueError:  # e.g. an integer with more digits than Python converts
        raise ConfigError("yaml.syntax", line="?") from None
    finally:
        loader.dispose()


def read_limited(path: Path, max_bytes: int) -> bytes:
    """Read a file only if it is not larger than ``max_bytes``; never loads more than that (A-53)."""
    with path.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise InputError("file.too_large", limit=max_bytes)
    return data


def decode_text(data: bytes, error: type[Exception] = InputError, key: str = "file.encoding") -> str:
    """UTF-8 with or without byte order mark; anything else is a clear error, not an internal one."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise error(key) from None


def check_relative(raw: str) -> PurePosixPath:
    """Validate a path that comes from a data or configuration file.

    Only plain relative paths are allowed: no absolute, drive, UNC or device paths, no ``..``,
    no colon (alternate data streams), no reserved Windows names, no control characters.
    """
    if not raw or len(raw) > MAX_PATH_CHARS or any(ord(ch) < 32 for ch in raw):
        raise UnsafePathError("path.invalid")
    text = raw.replace("\\", "/")
    if text.startswith("/"):
        raise UnsafePathError("path.absolute")
    if ":" in text:
        raise UnsafePathError("path.colon")
    parts: list[str] = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise UnsafePathError("path.parent")
        if part.endswith((" ", ".")):
            raise UnsafePathError("path.trailing")
        if part.split(".")[0].strip().upper() in _WINDOWS_RESERVED:
            raise UnsafePathError("path.reserved")
        parts.append(part)
    if not parts:
        raise UnsafePathError("path.invalid")
    return PurePosixPath(*parts)


def is_link(path: Path) -> bool:
    """True for symlinks and Windows junctions/reparse points."""
    try:
        if path.is_symlink():
            return True
        isjunction = getattr(os.path, "isjunction", None)
        if isjunction is not None and isjunction(path):
            return True
        if os.name == "nt" and path.exists():
            attributes = getattr(os.lstat(path), "st_file_attributes", 0)
            return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return False
    return False


def resolve_within(root: Path, relative: PurePosixPath, *, must_exist: bool = True) -> Path:
    """Join a checked relative path to ``root`` without following links out of it."""
    root_resolved = root.resolve(strict=True)
    current = root_resolved
    for part in relative.parts:
        current = current / part
        if is_link(current):
            raise UnsafePathError("path.link")
    resolved = current.resolve(strict=must_exist)
    if not resolved.is_relative_to(root_resolved):
        raise UnsafePathError("path.outside")
    return resolved


_DRIVE_REMOTE = 4


def _is_network_drive(path: Path) -> bool:
    """Mapped network drives (a drive letter bound to an SMB share) count as network paths on Windows."""
    if os.name != "nt":
        return False
    anchor = path.anchor
    if not re.fullmatch(r"[A-Za-z]:\\", anchor):
        return False
    get_drive_type = ctypes.windll.kernel32.GetDriveTypeW  # type: ignore[attr-defined,unused-ignore]
    return int(get_drive_type(anchor)) == _DRIVE_REMOTE


def check_operator_path(raw: str | os.PathLike[str]) -> Path:
    """Validate a path given on the command line: local paths only, no UNC/device paths, no streams.

    On Windows every root made of two separators (slashes and backslashes in any mix) is UNC or a device
    path; the check is repeated on the resolved path so that links to network shares are refused as well.
    Colons after the drive (alternate data streams) only exist on Windows; on POSIX they are legal.
    """
    text = os.fspath(raw)
    if not text or len(text) > MAX_PATH_CHARS or any(ord(ch) < 32 for ch in text):
        raise UnsafePathError("path.invalid")
    if os.name == "nt":
        native = text.replace("/", "\\")
        if native.startswith(("\\\\?\\", "\\\\.\\", "\\??\\")):
            raise UnsafePathError("path.device")
        if native.startswith("\\\\"):
            raise UnsafePathError("path.unc")
        _drive, rest = os.path.splitdrive(native)
        if ":" in rest:
            raise UnsafePathError("path.colon")
        for part in rest.split("\\"):
            stem = part.split(".")[0].strip().upper()
            if stem in _WINDOWS_RESERVED:
                raise UnsafePathError("path.reserved")
    elif text.startswith("//"):
        raise UnsafePathError("path.unc")
    path = Path(text)
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError):
        raise UnsafePathError("path.invalid") from None
    if os.name == "nt" and (str(resolved).startswith("\\\\") or _is_network_drive(resolved)):
        raise UnsafePathError("path.unc")
    return path


def redact_paths(text: str, roots: Mapping[str, Path | None]) -> str:
    """Output filter (A-51): replace known roots (e.g. the dataset root, the home directory) by a label.

    Covers the native, POSIX and repr (doubled backslash) spellings, case-insensitively on Windows.
    Longer roots are replaced first so that the dataset root wins over the home directory around it.
    """
    pairs = sorted(((str(path), label) for label, path in roots.items() if path), key=lambda p: -len(p[0]))
    flags = re.IGNORECASE if os.name == "nt" else 0
    for root, label in pairs:
        spellings = {root, root.replace("\\", "/"), root.replace("\\", "\\\\")}
        for spelling in sorted(spellings, key=len, reverse=True):
            pattern = re.escape(spelling) + r"(?=$|[\\/'\"\s:,;)\]])"
            text = re.sub(pattern, lambda _match, replacement=label: replacement, text, flags=flags)
    return text


@contextmanager
def work_directory(base: Path) -> Iterator[Path]:
    """A private directory for one run; removed afterwards, also after errors.

    The work folder lies next to the output, so a folder that cannot be created there (a file in the way,
    no permission) is reported like an output that cannot be written.
    """
    try:
        base.mkdir(parents=True, exist_ok=True)
        path = Path(tempfile.mkdtemp(prefix="run-", dir=base))
    except OSError:
        raise InputError("output.not_writable") from None
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
