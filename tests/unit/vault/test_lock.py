"""The vault lock (A-30 "Dateisperre um Lesen und Anhängen", A-90, p6 decisions 3): one exclusive, advisory
lock on access.jsonl.lock for every NeuroGrid reader and writer, with real processes."""

from __future__ import annotations

import os
import stat
import sys
import time
from pathlib import Path

import pytest
from vault_processes import appenders, lock_held  # type: ignore[import-not-found]

from conftest import dir_link  # type: ignore[import-not-found]
from neurogrid.kernel.errors import UnsafePathError
from neurogrid.kernel.provenance import VAULT_LOCK
from neurogrid.vault import _os, ledger
from neurogrid.vault.lock import LOCK_TIMEOUT_S, POLL_S, HeldLock, VaultLocked, exclusive
from neurogrid.vault.store import init_vault, locate


def test_constants() -> None:
    assert LOCK_TIMEOUT_S == 10.0  # one timeout for every vault reader and writer
    assert POLL_S == 0.05
    assert VaultLocked().message_key == "vault.locked"


def test_lock_file_name_is_access_jsonl_lock(tmp_path: Path) -> None:
    location = locate(tmp_path, ".neurogrid/vault")
    assert location.lock == location.path / "access.jsonl.lock" and location.lock.name == VAULT_LOCK
    tmp_path.joinpath(".neurogrid", "vault").mkdir(parents=True)
    assert not location.lock.exists()
    with exclusive(location.lock) as held:
        assert held.active and held.covers(location.lock) and isinstance(held, HeldLock)
        assert location.lock.is_file()  # created when missing
    assert not held.active and not held.covers(location.lock)
    assert location.lock.read_bytes() == b""  # never written, never deleted


def test_lock_excludes_second_process(tmp_path: Path) -> None:
    lock = tmp_path / VAULT_LOCK
    with lock_held(lock):
        started = time.monotonic()
        with pytest.raises(VaultLocked), exclusive(lock, timeout_s=0.3):
            pass
        waited = time.monotonic() - started
        assert waited >= 0.3, f"gave up after {waited:.3f} s"
    with exclusive(lock, timeout_s=5) as held:  # free again once the other process let go
        assert held.active


def test_lock_waits_for_the_other_process(tmp_path: Path) -> None:
    """The lock is polled until the other process lets go, within the timeout."""
    lock = tmp_path / VAULT_LOCK
    with lock_held(lock) as child:
        assert child.stdin is not None
        child.stdin.close()  # the child lets go now; exclusive() polls until it is free
        with exclusive(lock, timeout_s=30) as held:
            assert held.active


def test_lock_is_not_reentrant(tmp_path: Path) -> None:
    lock = tmp_path / VAULT_LOCK
    with exclusive(lock):
        started = time.monotonic()
        with pytest.raises(ValueError, match="append_locked"), exclusive(lock):
            pass
        assert time.monotonic() - started < 1  # at once, not after the timeout
    with exclusive(lock):  # released correctly after the refusal
        pass


def test_lock_file_link_refused(tmp_path: Path) -> None:
    (tmp_path / "elsewhere").mkdir()
    lock = tmp_path / VAULT_LOCK
    dir_link(lock, tmp_path / "elsewhere")
    with pytest.raises(UnsafePathError) as info, exclusive(lock):
        pass
    assert info.value.message_key == "vault.link" and info.value.params == {"part": VAULT_LOCK}


def test_lock_needs_a_regular_file(tmp_path: Path) -> None:
    lock = tmp_path / VAULT_LOCK
    lock.mkdir()
    with pytest.raises(OSError), exclusive(lock):
        pass


def test_lock_in_a_folder_that_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(OSError), exclusive(tmp_path / "missing" / VAULT_LOCK):
        pass


@pytest.mark.skipif(sys.platform != "win32" and os.geteuid() == 0, reason="root ignores file modes")
def test_read_only_lock_file_still_locks(tmp_path: Path) -> None:
    """A read-only vault (A-30: warning and finding, never exit 2): the lock is taken through a read
    handle and still excludes other processes."""
    lock = tmp_path / VAULT_LOCK
    lock.write_bytes(b"")
    lock.chmod(stat.S_IREAD)
    try:
        with exclusive(lock) as held:
            assert held.active
        with lock_held(lock), pytest.raises(VaultLocked), exclusive(lock, timeout_s=0.2):
            pass
    finally:
        lock.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_concurrent_appends_8_processes_x_25(tmp_path: Path) -> None:
    """Parallel writers never break the chain: 8 processes append 25 events each at the same time."""
    init_vault(locate(tmp_path, ".neurogrid/vault"))
    statuses = appenders(tmp_path, ".neurogrid/vault", processes=8, events=25)
    assert statuses == ["written"] * 8, statuses
    verification = ledger.verify(locate(tmp_path, ".neurogrid/vault"))
    assert verification.intact and verification.events == 200, verification.deviations[:5]
    entries = list(ledger.iter_entries(locate(tmp_path, ".neurogrid/vault").log))
    assert [entry.event.seq for entry in entries if entry.event] == list(range(1, 201))
    roles = {entry.event.role for entry in entries if entry.event}
    assert roles == {f"writer{number}" for number in range(8)}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX flock branch (D-09: proven in the Linux CI)")
def test_flock_branch(tmp_path: Path) -> None:
    """On POSIX the lock is fcntl.flock on the lock file: a flock of the test process on its own handle fails
    while another process holds the vault lock, and succeeds afterwards."""
    import fcntl

    lock = tmp_path / VAULT_LOCK
    with lock_held(lock):
        fd = os.open(lock, os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)
    fd = os.open(lock, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        mode = stat.S_IMODE(os.fstat(fd).st_mode)
        assert mode == 0o600, f"lock file created with mode {mode:o}"
    finally:
        os.close(fd)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows msvcrt branch")
def test_msvcrt_branch(tmp_path: Path) -> None:
    """On Windows the lock is msvcrt.locking of the first byte: another handle cannot lock it meanwhile."""
    import msvcrt

    lock = tmp_path / VAULT_LOCK
    with exclusive(lock):
        fd = os.open(lock, os.O_RDWR)
        try:
            with pytest.raises(PermissionError):
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        finally:
            os.close(fd)


def test_try_lock_reports_a_held_lock(tmp_path: Path) -> None:
    lock = tmp_path / VAULT_LOCK
    first = _os.open_lock(lock)
    second = _os.open_lock(lock)
    try:
        assert _os.try_lock(first)
        assert not _os.try_lock(second)
        _os.unlock(first)
        assert _os.try_lock(second)
        _os.unlock(second)
    finally:
        os.close(first)
        os.close(second)
