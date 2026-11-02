"""The platform code of the vault (A-90): file locks, new folders and files with their modes, folder fsync,
the open flags and the error kinds of each system. Nothing else in neurogrid.vault branches on the platform.

A block that runs on one platform only starts with a line that carries the marker comment
``# platform-only: windows`` or ``# platform-only: posix``; the marker covers that line's block (the indented
lines below it). tools/coverage_gates.py leaves the other platform's marked blocks out of the "Kern" gate: the
Windows blocks are measured locally, the POSIX blocks in the Linux CI (D-09).

Modes (KONZEPT 2.8, p6 decisions 2): on POSIX new vault folders get 0700 and new vault files 0600, set with
fchmod after creation so that the umask cannot widen or narrow them; on Windows the folder's ACLs are
inherited (os.open's mode only decides the read-only flag, which 0600 leaves off). The operating system
governs access; NeuroGrid has no user accounts.
"""

from __future__ import annotations

import errno
import os
import stat
import sys
from pathlib import Path

NEW_FOLDER_MODE = 0o700
NEW_FILE_MODE = 0o600
# O_NOFOLLOW (POSIX): a link as the last part is refused by the system itself (ELOOP); on Windows the callers
# check for links first (kernel.safety.is_link). O_NOINHERIT/O_CLOEXEC: child processes never get the handle.
FLAGS = (
    getattr(os, "O_BINARY", 0)
    | getattr(os, "O_NOINHERIT", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
# Windows error codes of a file another process has open without sharing, or a byte range it locked: the
# antivirus or the indexer for a moment (ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION).
_SHARING_ERRORS = frozenset({32, 33})


def _set_mode(fd: int, mode: int) -> None:
    if sys.platform != "win32":  # platform-only: posix
        os.fchmod(fd, mode)


_READ_ONLY_ERRORS = frozenset({errno.EACCES, errno.EPERM, errno.EROFS})


def open_lock(path: Path) -> int:
    """A handle on the lock file for locking: created empty (0600 on POSIX) if missing, opened for reading and
    writing, or for reading only if the file or the file system is read-only (a read-only vault: the lock
    still excludes every other NeuroGrid process, both systems lock through a read handle). Raises OSError:
    ELOOP for a link on POSIX (is_link_error), IsADirectoryError if the name is no regular file."""
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | FLAGS, NEW_FILE_MODE)
    except FileExistsError:
        pass
    except OSError:
        if not os.path.lexists(path):  # a read-only folder: the lock cannot be created
            raise
    else:
        _set_mode(fd, NEW_FILE_MODE)
        return fd
    try:
        fd = os.open(path, os.O_RDWR | FLAGS)
    except OSError as exc:
        if exc.errno not in _READ_ONLY_ERRORS:
            raise
        fd = os.open(path, os.O_RDONLY | FLAGS)
    if not stat.S_ISREG(os.fstat(fd).st_mode):  # POSIX opens a folder for reading
        os.close(fd)
        raise IsADirectoryError(errno.EISDIR, "the lock file is no regular file")
    return fd


def try_lock(fd: int) -> bool:
    """Lock the first byte of the lock file without waiting (msvcrt.locking LK_NBLCK on Windows, which may
    lock beyond the end of an empty file; fcntl.flock LOCK_EX|LOCK_NB on POSIX). False when another handle
    holds it, in this or another process."""
    os.lseek(fd, 0, os.SEEK_SET)
    if sys.platform == "win32":  # platform-only: windows
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except PermissionError:  # EACCES: the byte is locked through another handle
            return False
        return True
    else:  # platform-only: posix
        import fcntl

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True


def unlock(fd: int) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    if sys.platform == "win32":  # platform-only: windows
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:  # platform-only: posix
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


def make_folder(path: Path) -> None:
    """Create one folder (FileExistsError if anything of that name exists, a link included: mkdir never
    follows the last part); 0700 on POSIX."""
    Path(path).mkdir(mode=NEW_FOLDER_MODE)
    if sys.platform != "win32":  # platform-only: posix
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | FLAGS)
        try:
            os.fchmod(fd, NEW_FOLDER_MODE)
        finally:
            os.close(fd)


def create_file(path: Path, data: bytes) -> None:
    """Create a new file with ``data`` (FileExistsError if anything of that name exists, a link included),
    0600 on POSIX, written and synced before it is closed."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | FLAGS, NEW_FILE_MODE)
    try:
        _set_mode(fd, NEW_FILE_MODE)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    finally:
        os.close(fd)


def sync_folder(path: Path) -> None:
    """Make new names in a folder durable: fsync of the folder on POSIX; Windows has no such call for folders
    (NTFS journals the names)."""
    if sys.platform != "win32":  # platform-only: posix
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | FLAGS)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def open_log(path: Path) -> int:
    """The access log for appending (every write goes to the end, O_APPEND) and for reading its tail."""
    return os.open(path, os.O_RDWR | os.O_APPEND | FLAGS)


def open_for_reading(path: Path) -> int:
    return os.open(path, os.O_RDONLY | FLAGS)


def is_sharing_violation(exc: OSError) -> bool:
    """A Windows sharing or lock violation (another program has the file open for a moment); never on POSIX,
    where opening a file does not conflict with other handles."""
    return getattr(exc, "winerror", None) in _SHARING_ERRORS


def is_link_error(exc: OSError) -> bool:
    """The error of O_NOFOLLOW on a link (POSIX ELOOP); Windows reports no such error (links are checked
    before)."""
    return exc.errno == errno.ELOOP
