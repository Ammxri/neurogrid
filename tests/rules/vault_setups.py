"""Setups for the rule cases of the NeuroVault access log (CORE-NV03-01/02; NV-F03, A-30, A-90). Each makes a
copy of the fixture with a vault at its default location (.neurogrid/vault, made by ``vault init``) and two
access events with fixed times:

- ``vault_intact``: the log as NeuroGrid wrote it;
- ``vault_broken``: the role of the second entry edited by hand, its stored hash kept (hash_mismatch);
- ``vault_log_missing``: a vault folder without access.jsonl (only ``vault init`` creates it);
- ``vault_read_only``: access.jsonl read-only (the read-only attribute on Windows, mode 0400 on POSIX; as
  root, who writes read-only files, a folder in its place);
- ``vault_unreadable``: a folder where the lock file belongs, so the log cannot be read under the lock;
- ``vault_locked``: another process holds the vault lock while the check runs (the measurement waits
  LOCK_TIMEOUT_S and gives up); the process lets go when the test session ends.
"""

from __future__ import annotations

import atexit
import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from neurogrid.vault import ledger
from neurogrid.vault.store import VaultLocation, init_vault, locate

FIXED = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)
HOLD = """
import sys
from pathlib import Path
from neurogrid.vault.lock import exclusive
with exclusive(Path(sys.argv[1])):
    sys.stdout.write("held\\n")
    sys.stdout.flush()
    sys.stdin.readline()
"""
_HOLDERS: list[subprocess.Popen[bytes]] = []


def _release_all() -> None:
    for child in _HOLDERS:
        if child.stdin is not None:
            child.stdin.close()
        child.wait(timeout=60)


atexit.register(_release_all)


def vault_copy(fixture: Path, tmp: Path, events: int = 2) -> tuple[Path, VaultLocation]:
    """A copy of the fixture with an initialised vault and ``events`` check events."""
    folder = tmp / fixture.name
    shutil.copytree(fixture, folder)
    location = locate(folder, ".neurogrid/vault")
    init_vault(location)
    for _ in range(events):
        outcome = ledger.append(
            location,
            role="data_steward",
            action="check",
            objects=["**"],
            purpose=None,
            approval_ref=None,
            now=lambda: FIXED,
        )
        assert outcome.status == "written", outcome
    return folder, location.refreshed()


def vault_intact(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    return vault_copy(fixture, tmp)[0], {}


def vault_broken(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    folder, location = vault_copy(fixture, tmp)
    lines = location.log.read_bytes().splitlines(keepends=True)
    lines[1] = lines[1].replace(b'"role":"data_steward"', b'"role":"someone_else"')
    location.log.write_bytes(b"".join(lines))
    return folder, {}


def vault_log_missing(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    folder, location = vault_copy(fixture, tmp)
    location.log.unlink()
    return folder, {}


def vault_read_only(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    folder, location = vault_copy(fixture, tmp)
    if sys.platform != "win32" and os.geteuid() == 0:
        location.log.unlink()
        location.log.mkdir()
    else:
        location.log.chmod(stat.S_IREAD)
    return folder, {}


def vault_unreadable(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    folder, location = vault_copy(fixture, tmp)
    location.lock.unlink()
    location.lock.mkdir()
    return folder, {}


def vault_locked(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    folder, location = vault_copy(fixture, tmp)
    child = subprocess.Popen(
        [sys.executable, "-c", HOLD, str(location.lock)], stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )
    _HOLDERS.append(child)
    assert child.stdout is not None and child.stdout.readline().strip() == b"held", "no lock in the child"
    return folder, {}


VAULT_SETUPS: dict[str, Callable[[Path, Path], tuple[Path, dict[str, object]]]] = {
    "vault_intact": vault_intact,
    "vault_broken": vault_broken,
    "vault_log_missing": vault_log_missing,
    "vault_read_only": vault_read_only,
    "vault_unreadable": vault_unreadable,
    "vault_locked": vault_locked,
}
