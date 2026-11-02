"""The NeuroVault access log (NV-F03, A-30, A-90): CORE-NV03-01 its hash chain is intact (access.log_intact,
error) and CORE-NV03-02 it can be written (access.log_writable, warning: A-30 "Warnung und Befund" for a
read-only vault, which never ends a run with exit 2).

Both are dataset-level checks with ``is_true`` on ctx.vault, the vault of the run ([vault] path relative to
the project root, A-66; built once in pipeline.check_run). A single file as target has no vault: not
applicable (vault.single_file). Without a vault folder both are not checkable (vault.not_found), also under
--strict: a dataset without a vault has no log to judge, and M14 keeps its own rule. A link in the vault path
or a vault path that is no folder never reaches the measurers: check ends with exit 2 before the data are
read (p6 decisions 2).

The log is read with the snapshot rule of neurogrid.vault.ledger: its size taken under the vault lock (not
obtained in LOCK_TIMEOUT_S: not checkable, vault.locked), the bytes before it read without the lock. The run
appends its own event only after results.json is written, and an append never changes the verdict on the
bytes before it. So the details of a broken chain carry only the first deviating line, its kind and the
number of deviations: never an event count, a head hash, a time, and not the likely cause, which an append
after a reorder can change (p6 decisions 6). Two runs on the same dataset stay byte-identical (DoD P6).
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Literal

from neurogrid.checks.context import CheckContext
from neurogrid.kernel.errors import InputError, UnsafePathError
from neurogrid.kernel.provenance import VAULT_LOG
from neurogrid.kernel.rules import CheckSpec, Measurement, is_true
from neurogrid.vault import ledger
from neurogrid.vault import lock as vault_lock
from neurogrid.vault.lock import VaultLocked
from neurogrid.vault.store import DEFAULT_VAULT_PATH, VaultLocation

LOG_INTACT = "access.log_intact"
LOG_WRITABLE = "access.log_writable"
State = Literal["measured", "not_checkable", "not_applicable"]

SPECS = (
    CheckSpec(id=LOG_INTACT, evaluate=is_true),
    CheckSpec(id=LOG_WRITABLE, evaluate=is_true),
)

# The access log as a finding names it: only at the dataset's default vault, a fixed name in .neurogrid/
# (KNOWN_CONTROL_FILES, shown in clear, A-51); a configured vault path can carry any name and lie outside the
# dataset, so its findings name no file.
DEFAULT_LOG = (PurePosixPath(DEFAULT_VAULT_PATH) / VAULT_LOG).as_posix()


def _file(ctx: CheckContext, location: VaultLocation) -> str | None:
    default = ctx.root.joinpath(*PurePosixPath(DEFAULT_VAULT_PATH).parts)
    return DEFAULT_LOG if location.path == default else None


def _present(ctx: CheckContext, check_id: str) -> VaultLocation | list[Measurement]:
    """The vault of the run as it is now, or the measurement when there is none. A link or a path that is no
    folder found only now (changed while the run read the data) is the tool error check gives at the start
    (exit 2, p6 decisions 2)."""
    if ctx.scan.single_file:
        return _measurement(check_id, None, state="not_applicable", reason="vault.single_file")
    current = ctx.vault.refreshed() if ctx.vault is not None else None
    if current is None or current.state == "absent":
        return _measurement(check_id, None, state="not_checkable", reason="vault.not_found")
    if current.state == "link":
        raise UnsafePathError("vault.link", part=current.link_part)
    if current.state == "not_folder":
        raise InputError("vault.not_folder")
    return current


def _measurement(
    check_id: str,
    file: str | None,
    *,
    value: bool | None = None,
    state: State = "measured",
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> list[Measurement]:
    return [
        Measurement(
            check_id=check_id,
            object="dataset",
            file=file,
            value=value,
            state=state,
            reason=reason,
            details=details or {},
        )
    ]


def measure_log_intact(ctx: CheckContext) -> list[Measurement]:
    found = _present(ctx, LOG_INTACT)
    if isinstance(found, list):
        return found
    file = _file(ctx, found)
    try:
        size = ledger.snapshot(found, vault_lock.LOCK_TIMEOUT_S)
        verification = ledger.verify_entries(ledger.iter_entries(found.log, size))
    except VaultLocked:
        return _measurement(LOG_INTACT, file, state="not_checkable", reason="vault.locked")
    except FileNotFoundError:  # only vault init creates the log; it is never recreated silently
        return _measurement(LOG_INTACT, file, value=False, reason="vault.log_missing")
    except OSError:
        return _measurement(LOG_INTACT, file, state="not_checkable", reason="vault.log_unreadable")
    if verification.intact:
        return _measurement(LOG_INTACT, file, value=True)
    first = verification.deviations[0]
    details = {"first_line": first.line, "kind": first.kind, "deviations": len(verification.deviations)}
    return _measurement(LOG_INTACT, file, value=False, reason="vault.chain_broken", details=details)


def measure_log_writable(ctx: CheckContext) -> list[Measurement]:
    found = _present(ctx, LOG_WRITABLE)
    if isinstance(found, list):
        return found
    file = _file(ctx, found)
    status = ledger.probe_writable(found)
    if status == "writable":
        return _measurement(LOG_WRITABLE, file, value=True)
    reason = "vault.log_missing" if status == "log_missing" else "vault.not_writable"
    return _measurement(LOG_WRITABLE, file, value=False, reason=reason)


MEASURERS = {
    LOG_INTACT: measure_log_intact,
    LOG_WRITABLE: measure_log_writable,
}
