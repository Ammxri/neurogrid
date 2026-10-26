"""Input and output safety: strict YAML loading and bounded file reads (A-53), path checks (A-52),
the output filter for paths (A-51) and per-run work directories (A-54)."""

from __future__ import annotations

import ctypes
import getpass
import ntpath
import os
import re
import shutil
import socket
import sys
import tempfile
from collections.abc import Hashable, Iterable, Iterator, Mapping
from contextlib import contextmanager, suppress
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


_DEVICE_PREFIXES = ("\\\\?\\", "\\\\.\\", "\\??\\")


def operator_path_problem(text: str, *, windows: bool) -> str | None:
    """The message key that refuses a command-line path by its spelling alone, before any file access, or
    None (A-52, A-67); ``windows`` selects the platform's rules.

    Windows: every root made of two separators (slashes and backslashes in any mix) is UNC or a device path;
    colons after the drive (alternate data streams) and reserved device names in any part are refused.
    POSIX: colons, device names and backslashes inside a name are ordinary characters, and '/\\…' is an
    absolute path. A path that starts with '//' or with a backslash followed by another separator (or the
    NT prefix '\\??\\') is a Windows network or device path the operator typed or pasted: refused with the
    same key as on Windows instead of being taken for a relative name (with --out a file of that name).
    """
    if windows:
        native = text.replace("/", "\\")
        if native.startswith(_DEVICE_PREFIXES):
            return "path.device"
        if native.startswith("\\\\"):
            return "path.unc"
        _drive, rest = ntpath.splitdrive(native)
        if ":" in rest:
            return "path.colon"
        for part in rest.split("\\"):
            if part.split(".")[0].strip().upper() in _WINDOWS_RESERVED:
                return "path.reserved"
        return None
    if text.startswith("\\"):
        native = text.replace("/", "\\")
        if native.startswith(_DEVICE_PREFIXES):
            return "path.device"
        if native.startswith("\\\\"):
            return "path.unc"
    return "path.unc" if text.startswith("//") else None


def check_operator_path(raw: str | os.PathLike[str]) -> Path:
    """Validate a path given on the command line: local paths only, no UNC/device paths, no streams
    (operator_path_problem); on Windows the check is repeated on the resolved path so that links to network
    shares and mapped network drives are refused as well."""
    text = os.fspath(raw)
    if not text or len(text) > MAX_PATH_CHARS or any(ord(ch) < 32 for ch in text):
        raise UnsafePathError("path.invalid")
    problem = operator_path_problem(text, windows=os.name == "nt")
    if problem is not None:
        raise UnsafePathError(problem)
    path = Path(text)
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError):
        raise UnsafePathError("path.invalid") from None
    if os.name == "nt" and (str(resolved).startswith("\\\\") or _is_network_drive(resolved)):
        raise UnsafePathError("path.unc")
    return path


MIN_NAME_CHARS = 3  # shorter login or computer names are not searched (the G1 privacy check's limit too)
_NOT_PERSONAL = frozenset({"neurogrid"})  # a service account or computer named after the product
_WORD_EDGE = "A-Za-z0-9"


def home_folder() -> Path | None:
    """The home folder the output filter writes as '~' (A-51), or None: when it cannot be determined (on
    Linux without HOME and without a passwd entry for the user, as in containers with an arbitrary uid,
    Path.home() raises) and when it is the top of the file system (containers often set HOME=/), which
    would stand for every separator."""
    try:
        home = Path.home()
    except (RuntimeError, KeyError, OSError):
        return None
    if not home.is_absolute() or home == Path(home.anchor):
        return None
    return home


def _names(values: Iterable[str]) -> tuple[str, ...]:
    kept: dict[str, str] = {}
    for raw in values:
        value = raw.strip()
        if len(value) >= MIN_NAME_CHARS and value.casefold() not in _NOT_PERSONAL:
            kept.setdefault(value.casefold(), value)
    return tuple(sorted(kept.values(), key=lambda value: (-len(value), value)))


def identity_names() -> dict[str, tuple[str, ...]]:
    """The login name and the computer name, as the output filter replaces them: '<user>' and '<host>'
    (A-51: no user or computer names). They stand in paths outside the home folder, e.g. Linux's
    /tmp/pytest-of-<user> or /media/<user>/<stick>. Every source that answers counts (the login from the
    environment, getpass and on POSIX the passwd entry; the computer from COMPUTERNAME and the host name, also
    without its domain); one that fails is left out, never an error. Names shorter than MIN_NAME_CHARS and
    the product's own name are kept as they are: they would garble paths without naming anyone."""
    users = [os.environ.get("USERNAME", "")]
    with suppress(Exception):
        users.append(getpass.getuser())
    if sys.platform != "win32":
        with suppress(Exception):
            import pwd

            users.append(pwd.getpwuid(os.getuid()).pw_name)
    hosts = [os.environ.get("COMPUTERNAME", "")]
    with suppress(Exception):
        host = socket.gethostname()
        hosts += [host, host.split(".")[0]]
    return {"<user>": _names(users), "<host>": _names(hosts)}


def _root_text(path: Path) -> str:
    """A root as the filter matches it: a drive or file system root without its separator ('' for '/')."""
    text = str(path)
    return text.rstrip("\\/") if text == path.anchor else text


def _inside_label(match: re.Match[str], labels: Iterable[str]) -> bool:
    start, end = match.span()
    for label in labels:
        for found in re.finditer(re.escape(label), match.string):
            if found.start() <= start and end <= found.end():
                return True
    return False


def redact_paths(
    text: str, roots: Mapping[str, Path | None], names: Mapping[str, Iterable[str]] | None = None
) -> str:
    """Output filter (A-51): replace known roots (e.g. the dataset root, the home directory) by a label, then
    the ``names`` (identity_names: the login and the computer name) by theirs.

    Roots: the native, POSIX and repr (doubled backslash) spellings, case-insensitively on Windows, as whole
    path segments. Longer roots are replaced first so that the dataset root wins over the home directory
    around it. A root that ends with a separator (a drive root such as ``E:\\``, a dataset on a stick) is
    matched without it, so that the separator stays after the label; the top of the POSIX file system ('/')
    is no root, it would stand for every separator.
    Names: whole words (no ASCII letter or digit before or after), without case, never inside a label.
    """
    labels = [label for label in (*roots, *(names or {})) if label]
    pairs = sorted(
        ((_root_text(path), label) for label, path in roots.items() if path), key=lambda pair: -len(pair[0])
    )
    flags = re.IGNORECASE if os.name == "nt" else 0
    for root, label in pairs:
        if not root:
            continue
        spellings = {root, root.replace("\\", "/"), root.replace("\\", "\\\\")}
        for spelling in sorted(spellings, key=len, reverse=True):
            pattern = re.escape(spelling) + r"(?=$|[\\/'\"\s:,;)\]])"
            text = re.sub(pattern, lambda _match, replacement=label: replacement, text, flags=flags)
    for label, values in (names or {}).items():

        def replace(match: re.Match[str], replacement: str = label) -> str:
            return match.group(0) if _inside_label(match, labels) else replacement

        for value in sorted(set(values), key=lambda value: (-len(value), value)):
            if value:
                pattern = rf"(?<![{_WORD_EDGE}]){re.escape(value)}(?![{_WORD_EDGE}])"
                text = re.sub(pattern, replace, text, flags=re.IGNORECASE)
    return text


# A-54: a work folder ``<prefix><8 random characters>`` holds a lock file (WORK_LOCK). The run locks it before
# it writes WORK_MARK into it and keeps it locked until the folder is removed; the operating system releases
# the lock when the process ends, also when it is killed or crashes. A later start in the same base removes a
# folder whose lock file holds the mark and is not locked any more: a leftover. The lock file lies inside the
# folder, so whatever leaves the work folder out (manifest comparisons, A-82) leaves it out too, and it is
# removed last, so a folder that could not be removed completely is found again by the next start.
RUN_PREFIX = "run-"
WORK_LOCK = "neurogrid-work.lock"
WORK_MARK = b"NeuroGrid work folder\n"
_RANDOM_PART = "[a-z0-9_]{8}"  # tempfile.mkdtemp's random characters
_OPEN_FLAGS = os.O_RDWR | getattr(os, "O_BINARY", 0)
# the lock files of this process's own folders: never taken for leftovers, also where the file system lets
# a second lock of the same process through (Linux emulates flock on NFS with record locks)
_OWN_LOCKS: set[str] = set()


def _key(path: Path) -> str:
    return os.path.normcase(str(Path(path).absolute()))


def _lock(handle: int, *, wait: bool) -> bool:
    """An exclusive lock on the first byte of the open file ``handle`` (msvcrt on Windows, flock elsewhere),
    held until the handle is closed or the process ends. False when another open file holds it and
    ``wait`` is false; OSError when the file system offers no locks."""
    os.lseek(handle, 0, os.SEEK_SET)
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(handle, msvcrt.LK_LOCK if wait else msvcrt.LK_NBLCK, 1)
        except PermissionError:  # EACCES: the byte is locked through another handle
            if wait:
                raise
            return False
        return True
    import fcntl

    try:
        fcntl.flock(handle, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
    except BlockingIOError:
        return False
    return True


def _empty(folder: Path) -> bool:
    """Remove everything in a work folder but its lock file (links are removed, never followed); True when
    nothing else is left."""
    try:
        with os.scandir(folder) as entries:
            children = [Path(entry.path) for entry in entries if entry.name != WORK_LOCK]
    except FileNotFoundError:
        return True
    except OSError:
        return False
    for child in children:
        with suppress(OSError):
            if not is_link(child) and child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink()  # also a junction on Windows (removed, not followed)
    try:
        with os.scandir(folder) as entries:
            return all(entry.name == WORK_LOCK for entry in entries)
    except FileNotFoundError:
        return True
    except OSError:
        return False


def _drop(folder: Path) -> None:
    with suppress(OSError):
        (folder / WORK_LOCK).unlink(missing_ok=True)
    with suppress(OSError):
        folder.rmdir()


class WorkFolder:
    """A private folder for one run in a base folder, locked by this process while it exists (A-54)."""

    def __init__(self, path: Path, handle: int) -> None:
        self.path = path
        self.lock = path / WORK_LOCK
        self._handle = handle

    @classmethod
    def create(cls, base: Path, prefix: str) -> WorkFolder:
        """A new folder ``<prefix><8 random characters>`` in ``base`` with its lock file, locked by this
        process; OSError when the folder or its lock file cannot be created. On a file system without
        locks the lock file gets no mark: the folder is still removed at the end of the run, only never by
        a later start."""
        path = Path(tempfile.mkdtemp(prefix=prefix, dir=base))
        lock = path / WORK_LOCK
        try:
            handle = os.open(lock, _OPEN_FLAGS | os.O_CREAT | os.O_EXCL, 0o600)
        except BaseException:
            with suppress(OSError):
                path.rmdir()
            raise
        _OWN_LOCKS.add(_key(lock))
        try:
            try:
                locked = _lock(handle, wait=True)
            except OSError:
                locked = False
            if locked:
                os.write(handle, WORK_MARK)
        except BaseException:
            os.close(handle)
            _OWN_LOCKS.discard(_key(lock))
            _drop(path)
            raise
        return cls(path, handle)

    def remove(self) -> None:
        """Remove the folder's content while it is still locked, then release the lock and remove the lock
        file and the folder. If something could not be removed (a file another process holds open), the
        lock file with its mark stays, so that a later start removes the rest."""
        emptied = _empty(self.path)
        os.close(self._handle)
        _OWN_LOCKS.discard(_key(self.lock))
        if emptied:
            _drop(self.path)


def _remove_leftover(folder: Path) -> None:
    lock = folder / WORK_LOCK
    if _key(lock) in _OWN_LOCKS:
        return
    try:
        if is_link(folder) or not folder.is_dir():
            return
        handle = os.open(lock, _OPEN_FLAGS)
    except OSError:  # no lock file: not a work folder NeuroGrid can recognise (or one made without locks)
        return
    try:
        if not _lock(handle, wait=False):  # its run is still going
            return
        os.lseek(handle, 0, os.SEEK_SET)
        if os.read(handle, len(WORK_MARK) + 1) != WORK_MARK:  # not locked yet, or not NeuroGrid's
            return
        opened, current = os.fstat(handle), lock.stat()
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):  # replaced meanwhile
            return
        emptied = _empty(folder)  # still locked: no other start takes the folder meanwhile
    except OSError:
        return
    finally:
        os.close(handle)
    if emptied:
        _drop(folder)


def remove_leftovers(base: Path, prefix: str) -> None:
    """A-54 "deleted at the next start": the work folders ``<prefix>*`` in ``base`` that their run could not
    remove (it was killed, the computer stopped) are removed. Only a folder whose lock file holds WORK_MARK
    and is no longer locked counts; folders of runs still going, other entries with the same prefix (without
    such a lock file), links and anything that cannot be read are left alone. Never fails the run."""
    pattern = re.compile(re.escape(prefix) + _RANDOM_PART)
    try:
        with os.scandir(base) as entries:
            names = sorted(entry.name for entry in entries if pattern.fullmatch(entry.name))
    except OSError:
        return
    for name in names:
        _remove_leftover(base / name)


@contextmanager
def work_directory(base: Path) -> Iterator[Path]:
    """A private directory for one run; removed afterwards, also after errors, and at the next start in the
    same base when the run could not remove it (remove_leftovers).

    The work folder lies next to the output, so a folder that cannot be created there (a file in the way,
    no permission) is reported like an output that cannot be written.
    """
    try:
        base.mkdir(parents=True, exist_ok=True)
        remove_leftovers(base, RUN_PREFIX)
        folder = WorkFolder.create(base, RUN_PREFIX)
    except OSError:
        raise InputError("output.not_writable") from None
    try:
        yield folder.path
    finally:
        folder.remove()
