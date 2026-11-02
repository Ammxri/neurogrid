"""The permission rule of the role register (NV-F04, KONZEPT 2.8; A-30, A-93): vault.roles.permission with its
outcomes, the object rule ``covers`` (an object that is itself a pattern, ``**`` above all), the comparison a
command makes at its start (permission_at, role_warning) and the count of identifying register texts."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import dir_link  # type: ignore[import-not-found]
from neurogrid.model.roles import parse_roles
from neurogrid.vault import roles
from neurogrid.vault.roles import (
    NOT_PERMITTED,
    ROLES_INVALID,
    covers,
    permission,
    permission_at,
    role_warning,
)
from neurogrid.vault.store import init_vault, locate

REGISTER = parse_roles(
    b"format_version: 1\nroles:\n"
    b"  - {role: data_steward, description: d, actions: [read, check, export], objects: ['**']}\n"
    b"  - {role: QA.lead, description: d, actions: [read, report],"
    b" objects: ['sub-01/**', 'reports/*.html']}\n"
    b"  - {role: ethics, description: d, actions: [consent_manage],"
    b" objects: ['.neurogrid/vault/consents.yaml']}\n"
)


@pytest.mark.parametrize(
    ("role", "action", "objects", "expected"),
    [
        ("data_steward", "check", ["**"], "permitted"),
        (
            "data_steward",
            "export",
            [".neurogrid/manifest.json", ".neurogrid/vault/access.jsonl"],
            "permitted",
        ),
        ("data_steward", "convert", ["**"], "action_not_allowed"),
        ("QA.lead", "read", ["sub-01/eeg/sub-01_task-rest_eeg.edf"], "permitted"),
        ("QA.lead", "read", ["sub-01/**"], "permitted"),  # the same pattern
        ("QA.lead", "report", ["reports/report.zh.html", "sub-01/x"], "permitted"),
        ("QA.lead", "read", ["**"], "object_not_allowed"),  # the whole dataset needs '**'
        ("QA.lead", "read", ["sub-02/x.edf"], "object_not_allowed"),
        ("QA.lead", "read", ["sub-01/x", "sub-02/x"], "object_not_allowed"),  # every object must be covered
        ("QA.lead", "check", ["sub-01/x"], "action_not_allowed"),
        ("ethics", "consent_manage", [".neurogrid/vault/consents.yaml"], "permitted"),
        ("ethics", "consent_manage", ["secure/vault/consents.yaml"], "object_not_allowed"),
        ("Zhang_San", "read", ["**"], "role_unknown"),
        (None, "read", ["**"], "role_missing"),
    ],
)
def test_the_permission_matrix(role: str | None, action: str, objects: list[str], expected: str) -> None:
    assert permission(REGISTER, role, action, objects) == expected


def test_no_register_and_an_empty_register_are_silent() -> None:
    assert permission(None, "QA", "read", ["**"]) == "no_register"
    assert permission(parse_roles(b"format_version: 1\nroles: []\n"), "QA", "read", ["**"]) == "no_register"
    assert permission(None, None, "read", ["**"]) == "no_register"  # nothing to compare comes first


@pytest.mark.parametrize(
    ("pattern", "item", "covered"),
    [
        ("**", "**", True),
        ("**", "sub-01/eeg/x.edf", True),
        ("**", ".neurogrid/vault/consents.yaml", True),
        ("*", "**", False),  # kernel.glob.match alone would take '*' for '**'
        ("*/**", "**", False),
        ("sub-01/**", "**", False),
        ("**/x.edf", "**", False),
        ("*", "x.edf", True),
        ("*", "sub-01/x.edf", False),
        ("*", "*.edf", True),  # one segment of any name
        ("*.edf", "*", False),
        ("*.edf", "*.edf", True),
        ("sub-01/*", "sub-01/*", True),
        ("sub-01/**", "sub-01/*", True),
        ("sub-01/**", "sub-0?/x", False),
        ("sub-0?/x", "sub-01/x", True),
        ("sub-0?/x", "sub-0?/x", True),
        ("sub-0[12]/x", "sub-01/x", True),
        ("sub-01/x", "sub-01/x", True),
        ("sub-01/x", "Sub-01/x", False),  # case-sensitive on every platform (A-14)
        ("sub-01/**/x.edf", "sub-01/eeg/run/x.edf", True),
    ],
)
def test_covers(pattern: str, item: str, covered: bool) -> None:
    assert covers(pattern, item) is covered


def test_role_warning() -> None:
    assert NOT_PERMITTED == ("role_unknown", "action_not_allowed", "object_not_allowed")
    for warned in (*NOT_PERMITTED, ROLES_INVALID):
        assert role_warning(warned) == warned
    for silent in ("permitted", "no_register", "role_missing", None):
        assert role_warning(silent) is None


def test_permission_at_reads_the_register_of_the_vault(tmp_path: Path) -> None:
    location = locate(tmp_path, ".neurogrid/vault")
    init_vault(location)
    assert permission_at(location, "QA", "check", ["**"]) == "no_register"  # the template: roles: []
    location.roles.write_bytes(
        b"format_version: 1\nroles:\n  - {role: QA, description: d, actions: [read], objects: ['**']}\n"
    )
    assert permission_at(location, "QA", "check", ["**"]) == "action_not_allowed"
    assert permission_at(location, "QA", "read", ["**"]) == "permitted"
    location.roles.write_bytes(b"format_version: 1\nroles: [x]\n")  # invalid: only check ends with exit 2
    assert permission_at(location, "QA", "read", ["**"]) == ROLES_INVALID
    location.roles.unlink()
    assert permission_at(location, "QA", "read", ["**"]) == "no_register"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    dir_link(location.roles, elsewhere)  # a link is never followed: the register cannot be read
    assert permission_at(location, "QA", "read", ["**"]) == ROLES_INVALID


def test_identifying_count() -> None:
    texts = ["Prepares the dataset", "Wang Wei", "EC-2026-17", "Study 123456 subject", "数据管理员"]
    assert roles.identifying_count(texts) == 3
    assert roles.identifying_count([]) == 0
