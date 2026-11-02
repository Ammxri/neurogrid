"""Role names in access events (KONZEPT 2.8, NZ-08, NZ-09, A-30, A-90; p6 decisions 4): a role name or
initials, never a personal name or an OS login; names that still look identifying give a warning."""

from __future__ import annotations

import pytest

from neurogrid.kernel.errors import InputError
from neurogrid.vault.roles import role_looks_identifying, validate_role


@pytest.mark.parametrize("role", ["data_steward", "QA.lead", "AB", "pi-1", "R" + "x" * 79])
def test_role_pattern_accepts_role_names(role: str) -> None:
    assert validate_role(role) == role


@pytest.mark.parametrize(
    "role",
    [
        "QA lead",
        "data steward",
        "role\n",
        "a\tb",
        "",
        "_x",
        "1st",
        "R" + "x" * 80,
        "王伟",
        "DOMAIN\\user",
        "x@host",
    ],
)
def test_role_pattern_rejects_spaces_control_chars_and_names(role: str) -> None:
    with pytest.raises(InputError) as info:
        validate_role(role)
    # the message never repeats the value (A-51)
    assert info.value.message_key == "vault.role_invalid" and info.value.params == {}


@pytest.mark.parametrize(
    ("role", "warned"),
    [
        ("Wang_Wei", True),
        ("Max_Mustermann", True),
        ("emp1234567", True),
        ("data_steward", False),
        ("QA_lead", False),
        ("AB", False),
    ],
)
def test_role_looks_identifying_warning(role: str, warned: bool) -> None:
    assert role_looks_identifying(validate_role(role)) is warned
