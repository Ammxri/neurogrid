"""Role names in access events (KONZEPT 2.8, NZ-08, NZ-09, A-30, A-90; P6 part: the name check only, the role
register roles.yaml and CORE-NV04-01 follow in P9).

NeuroGrid has no user accounts: a role is what the user calls the function that accesses the data (a role
name or initials such as ``data_steward`` or ``QA.lead``), never an OS login. The roles are advisory, not
enforced (A-30).
"""

from __future__ import annotations

from neurogrid.io.identifying import looks_identifying
from neurogrid.kernel.errors import InputError
from neurogrid.model.access import role_valid


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
