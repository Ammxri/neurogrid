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
"""

from __future__ import annotations

from pathlib import Path

from neurogrid.io.identifying import looks_identifying
from neurogrid.kernel.errors import InputError
from neurogrid.model.access import role_valid
from neurogrid.model.roles import MAX_FILE_BYTES, RoleRegister, parse_roles
from neurogrid.vault import store
from neurogrid.vault.store import ROLES_FILE, LoadedRegister, VaultLocation


def validate_role(role: str) -> str:
    """The role if it matches model.access.ROLE_PATTERN, else errors.vault.role_invalid (exit 2; the value is
    not shown, A-51)."""
    if not role_valid(role):
        raise InputError("vault.role_invalid")
    return role


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
