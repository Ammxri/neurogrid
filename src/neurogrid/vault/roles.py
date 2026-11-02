"""Roles in access events and the role register roles.yaml (KONZEPT 2.8, NZ-08, NZ-09, NV-F04; A-30, A-90,
A-93).

NeuroGrid has no user accounts: a role is what the user calls the function that accesses the data (a role
name or initials such as ``data_steward`` or ``QA.lead``), never an OS login. The roles are advisory, not
enforced (A-30): the register ``<vault>/roles.yaml`` (model.roles) says which role may perform which action on
which objects, and CORE-NV04-01 compares the access log with it; nothing is refused because of it.

roles.yaml is a control file (C2): a link at its place or anywhere in the vault path is never followed
(errors.vault.link, p6 decisions 2), and a file that is no regular file, cannot be read, is too large, is no
UTF-8 text or holds an invalid register ends the run with exit 2 (errors.roles.*). A missing vault and a
vault without roles.yaml are no error (states no_vault and no_file of LoadedRoles).

The permission rule (A-93): an access is permitted when its role is in the register, the role allows its
action and every object of the event is covered by at least one object pattern of the role (``covers``).
Commands compare their own event with the register at the start of the run and warn
(cli.vault.role_not_permitted, cli.vault.roles_invalid); the event is written anyway and the exit code does
not change (KONZEPT 2.8 "Ein Befehl warnt").
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Literal

from neurogrid.io.identifying import looks_identifying
from neurogrid.kernel.errors import InputError, NeuroGridError
from neurogrid.model.access import role_valid
from neurogrid.model.roles import MAX_FILE_BYTES, RoleRegister, parse_roles
from neurogrid.vault import store
from neurogrid.vault.store import ROLES_FILE, LoadedRegister, VaultLocation

Permission = Literal[
    "permitted", "no_register", "role_missing", "role_unknown", "action_not_allowed", "object_not_allowed"
]
# The permissions a command warns about (cli.vault.role_not_permitted {reason}) and CORE-NV04-01 fails with
NOT_PERMITTED: tuple[Permission, ...] = ("role_unknown", "action_not_allowed", "object_not_allowed")
# What a command found when it compared its event with the register: a Permission, or ROLES_INVALID when
# roles.yaml cannot be read (cli.vault.roles_invalid; only check ends with exit 2 for it, as a control file)
ROLES_INVALID = "roles_invalid"
_WILDCARD = re.compile(r"[*?\[]")


def validate_role(role: str) -> str:
    """The role if it matches model.access.ROLE_PATTERN, else errors.vault.role_invalid (exit 2; the value is
    not shown, A-51)."""
    if not role_valid(role):
        raise InputError("vault.role_invalid")
    return role


def identifying_count(texts: Iterable[str]) -> int:
    """How many of the free texts of the registers (role descriptions and ethics references of roles.yaml,
    risk descriptions of risks.yaml) read like a name, a long number or non-ASCII text (A-51 heuristic of
    io.identifying; notice.registers_look_identifying shows the count, never a text)."""
    return sum(1 for text in texts if looks_identifying(text))


def role_looks_identifying(role: str) -> bool:
    """True for a valid role that still reads like a personal name or an ID (two capitalised words such as
    ``Wang_Wei``, six or more digits in a row): the command warns (cli.vault.role_looks_identifying) and
    records it anyway (p6 decisions 4)."""
    return looks_identifying(role)


# --- the role register roles.yaml (A-93) --------------------------------------------------------------------


class LoadedRoles(LoadedRegister[RoleRegister]):
    """The role register a check run found: ``no_vault``, ``no_file`` or ``loaded`` (``roles: []`` is a
    loaded register without entries)."""


def read_roles(path: Path) -> RoleRegister:
    """roles.yaml at ``path``. Raises FileNotFoundError for a missing file, UnsafePathError errors.vault.link
    for a link and ConfigError errors.roles.not_a_file, .unreadable, .too_large and the errors of
    model.roles.parse_roles."""
    data = store.read_vault_file(path, part=ROLES_FILE, errors="roles", max_bytes=MAX_FILE_BYTES)
    return parse_roles(data)


def _segments(text: str) -> list[str]:
    return [part for part in text.strip("/").split("/") if part]


def _segment_covered(part: str, segment: str) -> bool:
    """Whether the pattern segment ``part`` (not ``**``) covers the object segment ``segment``. A literal
    segment is matched as kernel.glob matches a path; a segment with a wildcard stands for every name it may
    match, so only the same text or ``*`` covers it, and ``**`` (any depth) is covered by no single
    segment."""
    if segment == "**":
        return False
    if _WILDCARD.search(segment):
        return part in (segment, "*")
    return fnmatchcase(segment, part)


def covers(pattern: str, item: str) -> bool:
    """Whether the object pattern ``pattern`` of a role covers the event object ``item`` (A-14, A-93): the
    walk of kernel.glob.match over the object's segments, where an object that is itself a pattern is covered
    only by patterns that cover every path it may name (_segment_covered). So ``**`` (the whole dataset, the
    object of every automatic event) is covered only by a role pattern ``**``, and ``sub-01/*`` by
    ``sub-01/*``, ``sub-01/**`` or ``**``, never by ``*`` (kernel.glob.match alone takes ``*`` for ``**``).
    Bounded like kernel.glob.match: pattern segments x object segments (A-53)."""
    segments = _segments(item)
    reachable = [True] + [False] * len(segments)  # reachable[j]: the pattern so far covers item[:j]
    previous = None
    for part in _segments(pattern):
        if part == "**":
            if previous == "**":
                continue
            seen = False
            for j in range(len(segments) + 1):
                seen = seen or reachable[j]
                reachable[j] = seen
        else:
            reachable = [False] + [
                reachable[j] and _segment_covered(part, segments[j]) for j in range(len(segments))
            ]
        previous = part
    return reachable[len(segments)]


def permission(
    register: RoleRegister | None, role: str | None, action: str, objects: Sequence[str]
) -> Permission:
    """Whether the register permits an access (A-93): ``no_register`` without a register or with an empty
    one (nothing to compare: commands stay silent), ``role_missing`` for an event without a role (scan,
    manifest and verify record none), ``role_unknown``, ``action_not_allowed``, ``object_not_allowed`` (an
    object no pattern of the role covers), else ``permitted``."""
    if register is None or not register.roles:
        return "no_register"
    if role is None:
        return "role_missing"
    entry = register.by_role().get(role)
    if entry is None:
        return "role_unknown"
    if action not in entry.actions:
        return "action_not_allowed"
    if not all(any(covers(pattern, item) for pattern in entry.objects) for item in objects):
        return "object_not_allowed"
    return "permitted"


def role_warning(permission: str | None) -> str | None:
    """The permission a command warns about (cli.vault.role_not_permitted {reason} for NOT_PERMITTED,
    cli.vault.roles_invalid for ROLES_INVALID); None, silent, for every other one and when nothing was
    compared."""
    if permission == ROLES_INVALID or permission in NOT_PERMITTED:
        return permission
    return None


def permission_at(location: VaultLocation, role: str | None, action: str, objects: Sequence[str]) -> str:
    """What a command reports about its own access event at the start of the run: the permission of the
    register of the present vault at ``location``, or ROLES_INVALID when roles.yaml cannot be read (a link,
    no regular file, too large, not UTF-8, an invalid register). Never raises for the register: only check
    ends with exit 2 for an invalid roles.yaml (the control file of CORE-NV04-01)."""
    try:
        loaded = load_for_check(location)
    except NeuroGridError:
        return ROLES_INVALID
    return permission(loaded.file, role, action, objects)


def load_for_check(location: VaultLocation) -> LoadedRoles:
    """The role register for CORE-NV04-01, read before the signal pass (C2, KONZEPT 1.4). Raises
    errors.vault.link {part} (UnsafePathError) and errors.vault.not_folder (InputError) like every command
    that reads the vault (p6 decisions 2), and the errors of read_roles."""
    current = store.located(location)
    if current is None:
        return LoadedRoles("no_vault")
    try:
        return LoadedRoles("loaded", read_roles(current.roles))
    except FileNotFoundError:
        return LoadedRoles("no_file")
