"""The vault lock (A-30 "Dateisperre um Lesen und Anhängen", A-90): one exclusive lock on
``<vault>/access.jsonl.lock`` for every NeuroGrid reader and writer of the vault.

The lock is advisory: it excludes NeuroGrid processes from each other, not other programs (an editor can
still change access.jsonl; the hash chain shows that). It is a byte lock of the lock file (msvcrt on Windows,
flock on POSIX, neurogrid.vault._os), polled every POLL_S seconds up to a timeout; it ends with the handle,
also when the process dies, so a crash never leaves the vault locked. The lock file is never deleted
(deleting it would let two processes lock two different files) and a link at its place is refused.

The lock is not reentrant: a second ``exclusive`` on the same file in the same process would wait for itself,
so it raises ValueError at once. Code that holds the lock and appends an event uses
ledger.append_locked with its HeldLock (``vault consent add``).
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from neurogrid.kernel.errors import NeuroGridError, UnsafePathError
from neurogrid.kernel.provenance import VAULT_LOCK
from neurogrid.kernel.safety import is_link
from neurogrid.vault import _os

# ONE timeout for every vault reader and writer (p6 decisions 3). Two check runs stay byte-identical as long
# as no other process holds the lock longer than this (p6 decisions 7).
LOCK_TIMEOUT_S = 10.0
POLL_S = 0.05

_HELD: set[str] = set()  # lock files this process holds (the lock is not reentrant)


class VaultLocked(NeuroGridError):
    """The vault lock was not obtained within the timeout (errors.vault.locked, exit 2 where a command needs
    the vault; a warning where it only appends its own event)."""

    def __init__(self) -> None:
        super().__init__("vault.locked")


class HeldLock:
    """Proof that this process holds the vault lock of ``path`` while the ``exclusive`` block runs; ``active``
    turns False when the block ends."""

    __slots__ = ("_active", "path")

    def __init__(self, path: Path) -> None:
        self.path = path
        self._active = True

    @property
    def active(self) -> bool:
        return self._active

    def covers(self, lock_path: Path) -> bool:
        """True while held and for the same lock file."""
        return self._active and _key(self.path) == _key(lock_path)

    def _release(self) -> None:
        self._active = False


def _key(path: Path) -> str:
    return os.path.normcase(str(Path(path).absolute()))


@contextmanager
def exclusive(lock_path: Path, timeout_s: float = LOCK_TIMEOUT_S) -> Iterator[HeldLock]:
    """Hold the vault lock for the block. Raises VaultLocked after ``timeout_s`` seconds, UnsafePathError
    errors.vault.link {part} for a link at the lock file, ValueError if this process holds it already, and
    OSError if the lock file cannot be opened or created (a read-only folder without one, a full disk)."""
    key = _key(lock_path)
    if key in _HELD:
        raise ValueError("the vault lock is held by this process already; use ledger.append_locked")
    if is_link(lock_path):
        raise UnsafePathError("vault.link", part=VAULT_LOCK)
    try:
        fd = _os.open_lock(lock_path)
    except OSError as exc:
        if _os.is_link_error(exc):
            raise UnsafePathError("vault.link", part=VAULT_LOCK) from None
        raise
    try:
        deadline = time.monotonic() + max(timeout_s, 0.0)
        while not _os.try_lock(fd):
            if time.monotonic() >= deadline:
                raise VaultLocked()
            time.sleep(POLL_S)
        _HELD.add(key)
        held = HeldLock(Path(lock_path))
        try:
            yield held
        finally:
            held._release()
            _HELD.discard(key)
            with suppress(OSError):  # closing the handle below releases the lock anyway
                _os.unlock(fd)
    finally:
        os.close(fd)
