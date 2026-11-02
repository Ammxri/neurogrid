"""The NeuroVault access log (NV-F03, NV-F04, A-30, A-90, A-93): CORE-NV03-01 its hash chain is intact
(access.log_intact, error), CORE-NV03-02 it can be written (access.log_writable, warning: A-30 "Warnung und
Befund" for a read-only vault, which never ends a run with exit 2) and CORE-NV04-01 its events are permitted
by the role register (roles.permitted, warning; advisory, A-30).

All three are dataset-level checks with ``is_true`` on ctx.vault, the vault of the run ([vault] path relative
to the project root, A-66; built once in pipeline.check_run). A single file as target has no vault: not
applicable (vault.single_file). Without a vault folder they are not checkable (vault.not_found), also under
--strict: a dataset without a vault has no log to judge, and M14 keeps its own rule. A link in the vault path
or a vault path that is no folder never reaches the measurers: check ends with exit 2 before the data are
read (p6 decisions 2).

The log is read with the snapshot rule of neurogrid.vault.ledger: its size taken under the vault lock (not
obtained in LOCK_TIMEOUT_S: not checkable, vault.locked), the bytes before it read without the lock. The run
appends its own event only after results.json is written, and an append never changes the verdict on the
bytes before it. So the details of a broken chain carry only the first deviating line, its kind and the
number of deviations: never an event count, a head hash, a time, and not the likely cause, which an append
after a reorder can change (p6 decisions 6). Two runs on the same dataset stay byte-identical (DoD P6).

CORE-NV04-01 (A-93, p9 decisions 3) compares the events of the log with roles.yaml (read before the signal
pass, ctx.roles; vault.roles.permission). It judges only the well-formed events whose time lies before 00:00
UTC of the day before the reference date (event_cut): the run's own event and the events of every run on
the same local date, for any UTC offset up to 24 hours, never change the result, so two check runs stay
byte-identical (NG-N03). One measurement per role and action (subkey ``<role>/<action>``): passed when every
event of the pair is permitted, else failed with the reason of its first event that is not
(roles.role_unknown, roles.action_not_allowed, roles.object_not_allowed); events without a role (scan,
manifest and verify record none) give one not checkable measurement per action (subkey ``-/<action>``,
roles.role_missing). No event before the cut: not applicable (roles.no_events). Details: role, action, the
number of events not permitted (or without a role) and the first such line; never times, purposes, objects
or texts of the register (A-51).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import PurePosixPath
from typing import Any, Literal

from neurogrid.checks.context import CheckContext
from neurogrid.kernel.errors import InputError, UnsafePathError
from neurogrid.kernel.findings import Notice, Severity
from neurogrid.kernel.provenance import VAULT_LOG
from neurogrid.kernel.rules import CheckSpec, Measurement, is_true
from neurogrid.vault import ledger
from neurogrid.vault import lock as vault_lock
from neurogrid.vault import roles as vault_roles
from neurogrid.vault.lock import VaultLocked
from neurogrid.vault.roles import RoleRegister
from neurogrid.vault.store import DEFAULT_VAULT_PATH, ROLES_FILE, VaultLocation

LOG_INTACT = "access.log_intact"
LOG_WRITABLE = "access.log_writable"
ROLES_PERMITTED = "roles.permitted"
State = Literal["measured", "not_checkable", "not_applicable"]
NO_ROLE = "-"  # the role part of the subkey of events without a role
# Every reason and notice key of CORE-NV04-01 (some are passed through variables), for the language tables
ROLE_REASONS = (
    "roles.no_register",
    "roles.empty",
    "roles.no_events",
    "roles.role_missing",
    "roles.role_unknown",
    "roles.action_not_allowed",
    "roles.object_not_allowed",
)
NOTICES = ("notice.roles_without_ethics_ref", "notice.registers_look_identifying")

SPECS = (
    CheckSpec(id=LOG_INTACT, evaluate=is_true),
    CheckSpec(id=LOG_WRITABLE, evaluate=is_true),
    CheckSpec(id=ROLES_PERMITTED, evaluate=is_true),
)

# The access log as a finding names it: only at the dataset's default vault, a fixed name in .neurogrid/
# (KNOWN_CONTROL_FILES, shown in clear, A-51); a configured vault path can carry any name and lie outside the
# dataset, so its findings name no file.
DEFAULT_LOG = (PurePosixPath(DEFAULT_VAULT_PATH) / VAULT_LOG).as_posix()
# CORE-NV04-01 without a usable register names the register instead (A-93), by the same rule
DEFAULT_ROLES = (PurePosixPath(DEFAULT_VAULT_PATH) / ROLES_FILE).as_posix()


def _file(ctx: CheckContext, location: VaultLocation, name: str = DEFAULT_LOG) -> str | None:
    default = ctx.root.joinpath(*PurePosixPath(DEFAULT_VAULT_PATH).parts)
    return name if location.path == default else None


def present_vault(ctx: CheckContext, check_id: str) -> VaultLocation | list[Measurement]:
    """The vault of the run as it is now, or the measurement when there is none (every check of the vault:
    also checks.retention). A link or a path that is no folder found only now (changed while the run read the
    data) is the tool error check gives at the start (exit 2, p6 decisions 2)."""
    if ctx.scan.single_file:
        return measurement_at(check_id, None, state="not_applicable", reason="vault.single_file")
    current = ctx.vault.refreshed() if ctx.vault is not None else None
    if current is None or current.state == "absent":
        return measurement_at(check_id, None, state="not_checkable", reason="vault.not_found")
    if current.state == "link":
        raise UnsafePathError("vault.link", part=current.link_part)
    if current.state == "not_folder":
        raise InputError("vault.not_folder")
    return current


def measurement_at(
    check_id: str,
    file: str | None,
    *,
    value: bool | None = None,
    state: State = "measured",
    reason: str | None = None,
    details: dict[str, Any] | None = None,
    subkey: str | None = None,
) -> list[Measurement]:
    """One dataset-level measurement of a vault check, as the list a measurer returns."""
    return [
        Measurement(
            check_id=check_id,
            object="dataset",
            subkey=subkey,
            file=file,
            value=value,
            state=state,
            reason=reason,
            details=details or {},
        )
    ]


def measure_log_intact(ctx: CheckContext) -> list[Measurement]:
    found = present_vault(ctx, LOG_INTACT)
    if isinstance(found, list):
        return found
    file = _file(ctx, found)
    try:
        size = ledger.snapshot(found, vault_lock.LOCK_TIMEOUT_S)
        verification = ledger.verify_entries(ledger.iter_entries(found.log, size))
    except VaultLocked:
        return measurement_at(LOG_INTACT, file, state="not_checkable", reason="vault.locked")
    except FileNotFoundError:  # only vault init creates the log; it is never recreated silently
        return measurement_at(LOG_INTACT, file, value=False, reason="vault.log_missing")
    except OSError:
        return measurement_at(LOG_INTACT, file, state="not_checkable", reason="vault.log_unreadable")
    if verification.intact:
        return measurement_at(LOG_INTACT, file, value=True)
    first = verification.deviations[0]
    details = {"first_line": first.line, "kind": first.kind, "deviations": len(verification.deviations)}
    return measurement_at(LOG_INTACT, file, value=False, reason="vault.chain_broken", details=details)


def measure_log_writable(ctx: CheckContext) -> list[Measurement]:
    found = present_vault(ctx, LOG_WRITABLE)
    if isinstance(found, list):
        return found
    file = _file(ctx, found)
    status = ledger.probe_writable(found)
    if status == "writable":
        return measurement_at(LOG_WRITABLE, file, value=True)
    reason = "vault.log_missing" if status == "log_missing" else "vault.not_writable"
    return measurement_at(LOG_WRITABLE, file, value=False, reason=reason)


def event_cut(as_of: date) -> str:
    """The event time before which CORE-NV04-01 judges events: 00:00 UTC of the day before the reference
    date, in the time format of the log (A-93: "Ereignisse vor dem aktuellen Lauf" read as events before the
    day before the reference date)."""
    return f"{(as_of - timedelta(days=1)).isoformat()}T00:00:00Z"


class _Pair:
    """The events of one role and action: how many are not permitted, the first such line and its reason."""

    def __init__(self) -> None:
        self.not_permitted = 0
        self.first_line: int | None = None
        self.reason: str | None = None

    def add(self, line: int, permission: str) -> None:
        if permission == "permitted":
            return
        self.not_permitted += 1
        if self.first_line is None:
            self.first_line, self.reason = line, f"roles.{permission}"


def _pairs(entries: Iterable[ledger.Entry], register: RoleRegister, cut: str) -> dict[tuple[str, str], _Pair]:
    """(role or NO_ROLE, action) -> its events before ``cut``. The permission of an event depends only on
    its role, action and objects, so it is computed once per distinct triple (automatic events repeat one)."""
    pairs: dict[tuple[str, str], _Pair] = {}
    seen: dict[tuple[str | None, str, tuple[str, ...]], str] = {}
    for entry in entries:
        event = entry.event
        if event is None or not event.time < cut:  # well-formed events before the cut only
            continue
        key = (event.role, event.action, tuple(event.objects))
        if key not in seen:
            seen[key] = vault_roles.permission(register, *key)
        pairs.setdefault((event.role or NO_ROLE, event.action), _Pair()).add(entry.line, seen[key])
    return pairs


def measure_roles_permitted(ctx: CheckContext) -> list[Measurement]:
    found = present_vault(ctx, ROLES_PERMITTED)
    if isinstance(found, list):
        return found
    file = _file(ctx, found)
    loaded = ctx.roles if ctx.roles is not None else vault_roles.load_for_check(found)
    register = _file(ctx, found, DEFAULT_ROLES)
    if loaded.file is None:
        return measurement_at(ROLES_PERMITTED, register, state="not_checkable", reason="roles.no_register")
    if not loaded.file.roles:
        return measurement_at(ROLES_PERMITTED, register, state="not_checkable", reason="roles.empty")
    cut = event_cut(ctx.as_of or date.today())  # the pipeline always sets the reference date
    try:
        size = ledger.snapshot(found, vault_lock.LOCK_TIMEOUT_S)
        pairs = _pairs(ledger.iter_entries(found.log, size), loaded.file, cut)
    except VaultLocked:
        return measurement_at(ROLES_PERMITTED, file, state="not_checkable", reason="vault.locked")
    except FileNotFoundError:  # CORE-NV03-01 reports the missing log
        return measurement_at(ROLES_PERMITTED, file, state="not_checkable", reason="vault.log_missing")
    except OSError:
        return measurement_at(ROLES_PERMITTED, file, state="not_checkable", reason="vault.log_unreadable")
    if not pairs:
        return measurement_at(ROLES_PERMITTED, file, state="not_applicable", reason="roles.no_events")
    out: list[Measurement] = []
    for (role, action), pair in sorted(pairs.items()):
        subkey = f"{role}/{action}"
        if role == NO_ROLE:
            details = {"role": None, "action": action, "events_without_role": pair.not_permitted}
            out += measurement_at(
                ROLES_PERMITTED,
                file,
                state="not_checkable",
                reason="roles.role_missing",
                details={**details, "first_line": pair.first_line},
                subkey=subkey,
            )
            continue
        details = {"role": role, "action": action, "events_not_permitted": pair.not_permitted}
        out += measurement_at(
            ROLES_PERMITTED,
            file,
            value=pair.not_permitted == 0,
            reason=pair.reason,
            details={**details, "first_line": pair.first_line},
            subkey=subkey,
        )
    return out


MEASURERS = {
    LOG_INTACT: measure_log_intact,
    LOG_WRITABLE: measure_log_writable,
    ROLES_PERMITTED: measure_roles_permitted,
}


def notices(ctx: CheckContext, check_ids: Iterable[str]) -> list[Notice]:
    """Notes about the registers a run read (counts only, A-51): roles without an ethics approval reference
    (CORE-NV04-01 loaded), and descriptions and ethics references of the registers that read like a name, a
    long number or non-ASCII text (io.identifying; role descriptions and ethics references of roles.yaml,
    descriptions of risks.yaml when CORE-M14-02 read it)."""
    out: list[Notice] = []
    texts: list[str] = []
    register = ctx.roles.file if ctx.roles is not None else None
    if ROLES_PERMITTED in set(check_ids) and register is not None:
        without = sum(1 for role in register.roles if role.ethics_approval_ref is None)
        if without:
            out.append(
                Notice(
                    level=Severity.INFO,
                    message_key="notice.roles_without_ethics_ref",
                    params={"count": without},
                )
            )
    if register is not None:
        texts += [role.description for role in register.roles]
        texts += [role.ethics_approval_ref for role in register.roles if role.ethics_approval_ref is not None]
    if ctx.risks is not None and ctx.risks.file is not None:
        texts += [risk.description for risk in ctx.risks.file.risks]
    identifying = vault_roles.identifying_count(texts)
    if identifying:
        out.append(
            Notice(
                level=Severity.INFO,
                message_key="notice.registers_look_identifying",
                params={"count": identifying},
            )
        )
    return out
