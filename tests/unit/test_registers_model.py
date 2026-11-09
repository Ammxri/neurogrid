"""The registers of NeuroVault (NV-F04, NV-F05, NV-F06; A-93, A-94, A-95): roles.yaml, retention.yaml and
risks.yaml, read by model.roles, model.retention and model.risks through model._registers. Valid files, every
format rule and limit refused with the field and never the value (C2, A-51), the templates of vault init and
their commented examples, the retention rules (three years, 29 February, review order), the canonical hashes,
the schemas and the error texts."""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

from neurogrid.kernel import canonical
from neurogrid.kernel.errors import ConfigError
from neurogrid.kernel.i18n import LANGUAGES
from neurogrid.model import _registers
from neurogrid.model import retention as retention_model
from neurogrid.model import risks as risks_model
from neurogrid.model import roles as roles_model
from neurogrid.model.access import ACTIONS
from neurogrid.model.consent import CONSENT_USES, MAX_VERSION, ConsentUse
from neurogrid.model.retention import (
    REQUIRED,
    RETENTION_OBJECTS,
    RetentionItem,
    RetentionRegister,
    parse_retention,
    plus_three_years,
)
from neurogrid.model.risks import RiskRegister, parse_risks
from neurogrid.model.roles import Role, RoleRegister, parse_roles
from neurogrid.report.texts import tables
from neurogrid.vault.store import (
    PIA_FILES,
    RETENTION_TEMPLATE,
    RISKS_TEMPLATE,
    ROLES_TEMPLATE,
    pia_template,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "src" / "neurogrid" / "schemas"
Parser = Callable[[bytes], Any]
TOKEN = "Zhang San"  # planted in refused values: an error never shows it (A-51)

ROLES_HEAD = "format_version: 1\nroles:\n"
ROLE = (
    "  - role: QA.lead\n"
    "    description: Reviews the reports\n"
    "    actions: [report, read]\n"
    "    objects: ['**', '.neurogrid/vault/consents.yaml']\n"
)
RISKS_HEAD = "format_version: 1\nrisks:\n"
RISK = (
    "  - id: R-2026-01\n"
    "    date: 2026-09-01\n"
    "    description: Second model\n"
    "    affected_uses: [sharing, training]\n"
    "    min_consent_version: 2\n"
)
RETENTION_HEAD = "format_version: 1\nobjects:\n"
ITEM = "  - object: pia\n    created: 2026-11-02\n    min_until: 2029-11-02\n"


def roles_doc(entry: str = ROLE, extra: str = "") -> str:
    return ROLES_HEAD + entry + extra


def risks_doc(entry: str = RISK, extra: str = "") -> str:
    return RISKS_HEAD + entry + extra


def retention_doc(entry: str = ITEM, extra: str = "") -> str:
    return RETENTION_HEAD + entry + extra


def _refusal(parse: Parser, text: str | bytes) -> ConfigError:
    data = text.encode("utf-8") if isinstance(text, str) else text
    with pytest.raises(ConfigError) as info:
        parse(data)
    return info.value


# --- valid files --------------------------------------------------------------------------------------------


def test_a_valid_role_register() -> None:
    extra = (
        "  - role: data_steward\n    description: 数据管理\n    actions: [consent_manage, read]\n"
        "    objects: [sub-01/**]\n    ethics_approval_ref: EC-2026-17\n"
    )
    first, second = parse_roles(roles_doc(extra=extra).encode("utf-8")).roles
    assert first == Role(
        role="QA.lead",
        description="Reviews the reports",
        actions=("read", "report"),  # model.access.ACTIONS order
        objects=("**", ".neurogrid/vault/consents.yaml"),  # the order of the file
    )
    assert second.actions == ("read", "consent_manage") and second.ethics_approval_ref == "EC-2026-17"
    assert second.description == "数据管理" and second.objects == ("sub-01/**",)


def test_a_valid_risk_register_with_a_yaml_date_and_date_text() -> None:
    second = RISK.replace("R-2026-01", "R2").replace("2026-09-01", "'2026-10-01'")
    first, other = parse_risks(risks_doc(extra=second).encode("utf-8")).risks
    assert first.id == "R-2026-01" and first.date == dt.date(2026, 9, 1)
    assert first.affected_uses == (ConsentUse.TRAINING, ConsentUse.SHARING)  # ConsentUse order
    assert first.min_consent_version == 2 and other.date == dt.date(2026, 10, 1)


def test_a_valid_retention_register_with_every_object() -> None:
    items = "".join(
        f"  - object: {name}\n    created: '2026-01-01'\n    min_until: 2029-01-01\n"
        for name in RETENTION_OBJECTS
    )
    parsed = parse_retention((RETENTION_HEAD + items).encode("utf-8"))
    assert [item.object for item in parsed.objects] == list(RETENTION_OBJECTS)
    assert parsed.by_object()["pia"] == RetentionItem(
        object="pia", created=dt.date(2026, 1, 1), min_until=dt.date(2029, 1, 1)
    )
    assert RETENTION_OBJECTS == ("pia", "access_log", "roles", "risks", "consents")
    assert REQUIRED == ("pia", "access_log")


@pytest.mark.parametrize(
    ("parse", "text"),
    [(parse_roles, roles_doc()), (parse_risks, risks_doc()), (parse_retention, retention_doc())],
    ids=["roles", "risks", "retention"],
)
def test_a_bom_and_crlf_line_ends_are_accepted(parse: Parser, text: str) -> None:
    plain = parse(text.encode("utf-8"))
    assert parse(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")) == plain


# --- refusals: the field, never the value (C2, A-51) --------------------------------------------------------

ROLE_REFUSALS: dict[str, tuple[str, str, str]] = {
    "role with a space": (
        roles_doc(ROLE.replace("QA.lead", f"'{TOKEN}'")),
        "roles.0.role",
        "string_pattern_mismatch",
    ),
    "role starting with a digit": (
        roles_doc(ROLE.replace("QA.lead", "1QA")),
        "roles.0.role",
        "string_pattern_mismatch",
    ),
    "role of 81 characters": (
        roles_doc(ROLE.replace("QA.lead", "a" * 81)),
        "roles.0.role",
        "string_pattern_mismatch",
    ),
    "non-ASCII role": (roles_doc(ROLE.replace("QA.lead", "张三")), "roles.0.role", "string_pattern_mismatch"),
    "role as a number": (roles_doc(ROLE.replace("QA.lead", "17")), "roles.0.role", "string_type"),
    "role twice": (roles_doc(extra=ROLE), "roles.1.role", "duplicate_role"),
    "empty description": (
        roles_doc(ROLE.replace("Reviews the reports", "''")),
        "roles.0.description",
        "string_too_short",
    ),
    "blank description": (
        roles_doc(ROLE.replace("Reviews the reports", "'   '")),
        "roles.0.description",
        "invalid_text",
    ),
    "description of 201 characters": (
        roles_doc(ROLE.replace("Reviews the reports", "x" * 201)),
        "roles.0.description",
        "string_too_long",
    ),
    "description with a control character": (
        roles_doc(ROLE.replace("Reviews the reports", '"Zhang\\u0007San"')),
        "roles.0.description",
        "invalid_text",
    ),
    "description with a line break": (
        roles_doc(ROLE.replace("Reviews the reports", '"Zhang\\nSan"')),
        "roles.0.description",
        "invalid_text",
    ),
    "no action": (roles_doc(ROLE.replace("[report, read]", "[]")), "roles.0.actions", "too_short"),
    "unknown action": (
        roles_doc(ROLE.replace("[report, read]", "[delete]")),
        "roles.0.actions.0",
        "literal_error",
    ),
    "action twice": (
        roles_doc(ROLE.replace("[report, read]", "[read, read]")),
        "roles.0.actions",
        "duplicate_action",
    ),
    "actions as text": (roles_doc(ROLE.replace("[report, read]", "read")), "roles.0.actions", "tuple_type"),
    "no object": (
        roles_doc(ROLE.replace("['**', '.neurogrid/vault/consents.yaml']", "[]")),
        "roles.0.objects",
        "too_short",
    ),
    "absolute object": (
        roles_doc(ROLE.replace("'**'", f"'/{TOKEN}'")),
        "roles.0.objects.0",
        "object_absolute",
    ),
    "drive object": (
        roles_doc(ROLE.replace("'**'", f"'C:/{TOKEN}'")),
        "roles.0.objects.0",
        "object_absolute",
    ),
    "object with a backslash": (
        roles_doc(ROLE.replace("'**'", f"'{TOKEN}\\x'")),
        "roles.0.objects.0",
        "object_separator",
    ),
    "object with '..'": (
        roles_doc(ROLE.replace("'**'", f"'a/../{TOKEN}'")),
        "roles.0.objects.0",
        "object_parent",
    ),
    "object with a control character": (
        roles_doc(ROLE.replace("'**'", '"a\\u0001b"')),
        "roles.0.objects.0",
        "object_control",
    ),
    "object of 1025 characters": (
        roles_doc(ROLE.replace("'**'", "x" * 1025)),
        "roles.0.objects.0",
        "string_too_long",
    ),
    "empty object": (roles_doc(ROLE.replace("'**'", "''")), "roles.0.objects.0", "string_too_short"),
    "blank ethics ref": (
        roles_doc(extra="    ethics_approval_ref: '  '\n"),
        "roles.0.ethics_approval_ref",
        "ethics_ref_text",
    ),
    "ethics ref of 121 characters": (
        roles_doc(extra=f"    ethics_approval_ref: {'E' * 121}\n"),
        "roles.0.ethics_approval_ref",
        "string_too_long",
    ),
    "unknown key": (roles_doc(extra=f"    {TOKEN}: 1\n"), "roles.0.?", "extra_forbidden"),
    "unknown top-level key": (roles_doc(extra=f"{TOKEN}: x\n"), "?", "extra_forbidden"),
    "a field missing": (
        roles_doc(ROLE.replace("    description: Reviews the reports\n", "")),
        "roles.0.description",
        "missing",
    ),
    "format_version missing": ("roles: []\n", "format_version", "missing"),
    "format_version 2": ("format_version: 2\nroles: []\n", "format_version", "literal_error"),
    "format_version true": ("format_version: true\nroles: []\n", "format_version", "literal_error"),
    "roles missing": ("format_version: 1\n", "roles", "missing"),
    "roles as a mapping": ("format_version: 1\nroles: {}\n", "roles", "list_type"),
    "an entry that is no mapping": ("format_version: 1\nroles: [x]\n", "roles.0", "model_type"),
    "a list instead of a mapping": ("- 1\n", "roles.yaml", "not_mapping"),
}
RISK_REFUSALS: dict[str, tuple[str, str, str]] = {
    "ID starting with a digit": (
        risks_doc(RISK.replace("R-2026-01", "1R")),
        "risks.0.id",
        "string_pattern_mismatch",
    ),
    "ID with a space": (
        risks_doc(RISK.replace("R-2026-01", f"'{TOKEN}'")),
        "risks.0.id",
        "string_pattern_mismatch",
    ),
    "ID of 41 characters": (
        risks_doc(RISK.replace("R-2026-01", "R" * 41)),
        "risks.0.id",
        "string_pattern_mismatch",
    ),
    "ID twice": (risks_doc(extra=RISK), "risks.1.id", "duplicate_id"),
    "timestamp": (risks_doc(RISK.replace("2026-09-01", "2026-09-01 10:00:00")), "risks.0.date", "date_type"),
    "impossible date as text": (
        risks_doc(RISK.replace("2026-09-01", "'2026-02-30'")),
        "risks.0.date",
        "date_type",
    ),
    "basic date format": (risks_doc(RISK.replace("2026-09-01", "'20260901'")), "risks.0.date", "date_type"),
    "empty description": (
        risks_doc(RISK.replace("Second model", "''")),
        "risks.0.description",
        "string_too_short",
    ),
    "blank description": (
        risks_doc(RISK.replace("Second model", "' '")),
        "risks.0.description",
        "invalid_text",
    ),
    "description of 501 characters": (
        risks_doc(RISK.replace("Second model", "x" * 501)),
        "risks.0.description",
        "string_too_long",
    ),
    "description with a control character": (
        risks_doc(RISK.replace("Second model", '"Zhang\\u0007San"')),
        "risks.0.description",
        "invalid_text",
    ),
    "no use": (risks_doc(RISK.replace("[sharing, training]", "[]")), "risks.0.affected_uses", "too_short"),
    "unknown use": (
        risks_doc(RISK.replace("[sharing, training]", "[research]")),
        "risks.0.affected_uses.0",
        "enum",
    ),
    "use twice": (
        risks_doc(RISK.replace("[sharing, training]", "[training, training]")),
        "risks.0.affected_uses",
        "duplicate_use",
    ),
    "version 0": (
        risks_doc(RISK.replace("min_consent_version: 2", "min_consent_version: 0")),
        "risks.0.min_consent_version",
        "greater_than_equal",
    ),
    "version too high": (
        risks_doc(RISK.replace("min_consent_version: 2", f"min_consent_version: {MAX_VERSION + 1}")),
        "risks.0.min_consent_version",
        "less_than_equal",
    ),
    "version true": (
        risks_doc(RISK.replace("min_consent_version: 2", "min_consent_version: true")),
        "risks.0.min_consent_version",
        "int_type",
    ),
    "version as text": (
        risks_doc(RISK.replace("min_consent_version: 2", "min_consent_version: '2'")),
        "risks.0.min_consent_version",
        "int_type",
    ),
    "a field missing": (
        risks_doc(RISK.replace("    min_consent_version: 2\n", "")),
        "risks.0.min_consent_version",
        "missing",
    ),
    "unknown key": (risks_doc(extra=f"    {TOKEN}: 1\n"), "risks.0.?", "extra_forbidden"),
    "format_version 2": ("format_version: 2\nrisks: []\n", "format_version", "literal_error"),
    "risks missing": ("format_version: 1\n", "risks", "missing"),
    "a list instead of a mapping": ("[]\n", "risks.yaml", "not_mapping"),
}
RETENTION_REFUSALS: dict[str, tuple[str, str, str]] = {
    "unknown object": (
        retention_doc(ITEM.replace("object: pia", f"object: '{TOKEN}'")),
        "objects.0.object",
        "literal_error",
    ),
    "object twice": (retention_doc(extra=ITEM), "objects.1.object", "duplicate_object"),
    "created missing": (
        retention_doc(ITEM.replace("    created: 2026-11-02\n", "")),
        "objects.0.created",
        "missing",
    ),
    "min_until missing": (
        retention_doc(ITEM.replace("    min_until: 2029-11-02\n", "")),
        "objects.0.min_until",
        "missing",
    ),
    "timestamp": (
        retention_doc(ITEM.replace("created: 2026-11-02", "created: 2026-11-02 10:00:00")),
        "objects.0.created",
        "date_type",
    ),
    "impossible date as text": (
        retention_doc(ITEM.replace("2029-11-02", "'2029-13-02'")),
        "objects.0.min_until",
        "date_type",
    ),
    "review date as text that is no date": (
        retention_doc(extra="    review_at: soon\n"),
        "objects.0.review_at",
        "date_type",
    ),
    "unknown key": (retention_doc(extra=f"    {TOKEN}: 1\n"), "objects.0.?", "extra_forbidden"),
    "six entries": (retention_doc(ITEM * 6), "objects", "too_long"),
    "format_version true": ("format_version: true\nobjects: []\n", "format_version", "literal_error"),
    "objects missing": ("format_version: 1\n", "objects", "missing"),
    "a list instead of a mapping": ("- 1\n", "retention.yaml", "not_mapping"),
}
REFUSALS = [
    *((parse_roles, "roles", *case) for case in ROLE_REFUSALS.values()),
    *((parse_risks, "risks", *case) for case in RISK_REFUSALS.values()),
    *((parse_retention, "retention", *case) for case in RETENTION_REFUSALS.values()),
]
REFUSAL_IDS = [
    *(f"roles: {name}" for name in ROLE_REFUSALS),
    *(f"risks: {name}" for name in RISK_REFUSALS),
    *(f"retention: {name}" for name in RETENTION_REFUSALS),
]


@pytest.mark.parametrize(("parse", "name", "text", "field", "problem"), REFUSALS, ids=REFUSAL_IDS)
def test_invalid_content_names_the_field_never_the_value(
    parse: Parser, name: str, text: str, field: str, problem: str
) -> None:
    error = _refusal(parse, text)
    assert error.message_key == f"{name}.invalid"
    assert error.params == {"field": field, "problem": problem}
    assert "Zhang" not in str(error.params) and "张三" not in str(error.params)


@pytest.mark.parametrize(
    ("parse", "name", "head", "known"),
    [
        (parse_roles, "roles", ROLES_HEAD + ROLE, "description"),
        (parse_risks, "risks", RISKS_HEAD + RISK, "description"),
        (parse_retention, "retention", RETENTION_HEAD + ITEM, "created"),
    ],
    ids=["roles", "risks", "retention"],
)
def test_yaml_aliases_duplicate_keys_size_and_encoding(
    parse: Parser, name: str, head: str, known: str
) -> None:
    list_key = {"roles": "roles", "risks": "risks", "retention": "objects"}[name]
    assert (
        _refusal(parse, f"format_version: 1\n{list_key}:\n  - &a {{x: 1}}\n  - *a\n").message_key
        == "yaml.alias"
    )
    duplicate = _refusal(parse, head + f"    {known}: 2026-01-01\n")
    assert duplicate.message_key == "yaml.duplicate_key" and duplicate.params["name"] == known
    unknown = _refusal(parse, head + f"    {TOKEN}: 1\n    {TOKEN}: 2\n")
    assert unknown.message_key == "yaml.duplicate_key" and unknown.params["name"] == "?"
    limit = {"roles": roles_model, "risks": risks_model, "retention": retention_model}[name].MAX_FILE_BYTES
    too_large = _refusal(parse, b"#" * (limit + 1))
    assert too_large.message_key == f"{name}.too_large" and too_large.params == {"limit": limit}
    latin = (head + "# é\n").encode("latin-1")
    assert _refusal(parse, latin).message_key == f"{name}.encoding"


def test_the_byte_limits() -> None:
    assert (roles_model.MAX_FILE_BYTES, risks_model.MAX_FILE_BYTES) == (1_000_000, 1_000_000)
    assert retention_model.MAX_FILE_BYTES == 100_000
    text = retention_doc()
    padded = text + "#" * (retention_model.MAX_FILE_BYTES - len(text) - 1) + "\n"
    assert len(padded.encode("utf-8")) == retention_model.MAX_FILE_BYTES
    assert parse_retention(padded.encode("utf-8")).objects  # a file of exactly the limit is read


def _many(monkeypatch: pytest.MonkeyPatch, document: dict[str, Any]) -> None:
    """The parsed document given directly: thousands of entries take PyYAML seconds (the consent tests do
    the same)."""
    monkeypatch.setattr(_registers, "_yaml", lambda _text, _spec: document)


def test_entry_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    role = {"role": "r", "description": "d", "actions": ["read"], "objects": ["**"]}
    roles = [{**role, "role": f"r{n}"} for n in range(roles_model.MAX_ROLES + 1)]
    _many(monkeypatch, {"format_version": 1, "roles": roles[:-1]})
    assert len(parse_roles(b"").roles) == roles_model.MAX_ROLES == 200
    _many(monkeypatch, {"format_version": 1, "roles": roles})
    assert _refusal(parse_roles, b"").params == {"field": "roles", "problem": "too_long"}
    objects = [f"sub-{n}/**" for n in range(roles_model.MAX_ROLE_OBJECTS + 1)]
    _many(monkeypatch, {"format_version": 1, "roles": [{**role, "objects": objects[:-1]}]})
    assert len(parse_roles(b"").roles[0].objects) == roles_model.MAX_ROLE_OBJECTS == 100
    _many(monkeypatch, {"format_version": 1, "roles": [{**role, "objects": objects}]})
    assert _refusal(parse_roles, b"").params == {"field": "roles.0.objects", "problem": "too_long"}
    _many(monkeypatch, {"format_version": 1, "roles": [{**role, "actions": list(ACTIONS)}]})
    assert parse_roles(b"").roles[0].actions == ACTIONS  # all six actions
    risk = {
        "id": "R",
        "date": dt.date(2026, 1, 1),
        "description": "d",
        "affected_uses": list(CONSENT_USES),
        "min_consent_version": MAX_VERSION,
    }
    risks = [{**risk, "id": f"R{n}"} for n in range(risks_model.MAX_RISKS + 1)]
    _many(monkeypatch, {"format_version": 1, "risks": risks[:-1]})
    assert len(parse_risks(b"").risks) == risks_model.MAX_RISKS == 1000
    _many(monkeypatch, {"format_version": 1, "risks": risks})
    assert _refusal(parse_risks, b"").params == {"field": "risks", "problem": "too_long"}


def test_lengths_at_the_limits_are_accepted() -> None:
    longest = ROLE.replace("QA.lead", "a" * 80).replace("Reviews the reports", "x" * 200)
    entry = parse_roles(roles_doc(longest, f"    ethics_approval_ref: {'E' * 120}\n").encode("utf-8")).roles[
        0
    ]
    assert (len(entry.role), len(entry.description), len(entry.ethics_approval_ref or "")) == (80, 200, 120)
    risk = RISK.replace("R-2026-01", "R" * 40).replace("Second model", "x" * 500)
    parsed = parse_risks(risks_doc(risk).encode("utf-8")).risks[0]
    assert (len(parsed.id), len(parsed.description)) == (40, 500)
    one = parse_risks(risks_doc(RISK.replace("min_consent_version: 2", "min_consent_version: 1")).encode())
    assert one.risks[0].min_consent_version == 1


# --- retention: three years, 29 February, review order (A-94) -----------------------------------------------


@pytest.mark.parametrize(
    ("created", "earliest"),
    [
        (dt.date(2026, 11, 2), dt.date(2029, 11, 2)),
        (dt.date(2024, 2, 29), dt.date(2027, 3, 1)),  # no 29 February in 2027: the stricter reading
        (dt.date(2025, 2, 28), dt.date(2028, 2, 28)),
        (dt.date(2025, 3, 1), dt.date(2028, 3, 1)),
        (dt.date(9996, 12, 31), dt.date(9999, 12, 31)),
        (dt.date(9997, 1, 1), None),  # beyond the calendar: no min_until is late enough
    ],
)
def test_plus_three_years(created: dt.date, earliest: dt.date | None) -> None:
    assert plus_three_years(created) == earliest


@pytest.mark.parametrize(
    ("created", "min_until", "too_short"),
    [
        ("2026-11-02", "2029-11-02", False),
        ("2026-11-02", "2029-11-01", True),
        ("2026-11-02", "2026-11-02", True),
        ("2026-11-02", "2026-11-01", True),  # before the creation date
        ("2024-02-29", "2027-03-01", False),
        ("2024-02-29", "2027-02-28", True),
        ("9997-01-01", "9999-12-31", True),
    ],
)
def test_a_minimum_retention_below_three_years_is_exit_2(
    created: str, min_until: str, too_short: bool
) -> None:
    text = RETENTION_HEAD + f"  - object: access_log\n    created: {created}\n    min_until: {min_until}\n"
    if not too_short:
        assert parse_retention(text.encode("utf-8")).objects[0].too_short is False
        return
    error = _refusal(parse_retention, text)
    assert (error.message_key, error.params) == ("retention.too_short", {"object": "access_log"})


@pytest.mark.parametrize(
    ("review_at", "valid"),
    [
        ("2026-11-02", True),
        ("2029-11-02", True),
        ("2028-01-01", True),
        ("2026-11-01", False),
        ("2029-11-03", False),
    ],
)
def test_the_review_date_lies_between_created_and_min_until(review_at: str, valid: bool) -> None:
    text = retention_doc(extra=f"    review_at: {review_at}\n")
    if valid:
        assert parse_retention(text.encode("utf-8")).objects[0].review_at == dt.date.fromisoformat(review_at)
        return
    error = _refusal(parse_retention, text)
    assert error.params == {"field": "objects.0.review_at", "problem": "review_order"}


def test_retention_problems_are_reported_in_file_order() -> None:
    short = "  - object: roles\n    created: 2026-11-02\n    min_until: 2027-01-01\n"
    assert _refusal(parse_retention, retention_doc(extra=short + ITEM)).message_key == "retention.too_short"
    error = _refusal(parse_retention, retention_doc(extra=ITEM + short))  # the repeated pia comes first
    assert error.params == {"field": "objects.1.object", "problem": "duplicate_object"}


# --- the templates of vault init (A-93 to A-95) -------------------------------------------------------------

TEMPLATES = {
    "roles": (ROLES_TEMPLATE, parse_roles, "roles", RoleRegister(roles=[])),
    "risks": (RISKS_TEMPLATE, parse_risks, "risks", RiskRegister(risks=[])),
    "retention": (RETENTION_TEMPLATE, parse_retention, "objects", RetentionRegister(objects=[])),
}


def uncommented(template: bytes, list_key: str) -> bytes:
    """The template as its header says to use the example: the line '<list_key>: []' deleted and '# '
    removed at the start of every example line (from '# <list_key>:' on)."""
    lines: list[str] = []
    example = False
    for line in template.decode("utf-8").splitlines():
        example = example or line == f"# {list_key}:"
        if line == f"{list_key}: []":
            continue
        lines.append(line[2:] if example and line.startswith("# ") else line)
    return ("\n".join(lines) + "\n").encode("utf-8")


@pytest.mark.parametrize("name", TEMPLATES)
def test_each_template_parses_to_an_empty_register(name: str) -> None:
    template, parse, list_key, empty = TEMPLATES[name]
    assert parse(template) == empty and not parse(template).entries
    assert b"\r" not in template and not template.startswith(b"\xef\xbb\xbf")
    text = template.decode("ascii")
    assert text.endswith(f"format_version: 1\n{list_key}: []\n")
    assert all(line.startswith("#") for line in text.splitlines()[:-2])  # an English comment header
    assert f"docs/<lang>/vault.md#{name}" in text and f"delete the line '{list_key}: []'" in text


def test_the_commented_examples_parse_when_used_as_the_headers_say() -> None:
    roles = parse_roles(uncommented(ROLES_TEMPLATE, "roles"))
    assert [role.role for role in roles.roles] == ["data_steward", "QA.lead"]
    assert roles.roles[0].actions == ACTIONS and roles.roles[0].ethics_approval_ref == "EC-2026-17"
    assert all(role.objects[0] == "**" for role in roles.roles)  # quoted: '**' unquoted is a YAML alias
    risks = parse_risks(uncommented(RISKS_TEMPLATE, "risks"))
    assert [(risk.id, risk.min_consent_version) for risk in risks.risks] == [("R-2026-01", 2)]
    retention = parse_retention(uncommented(RETENTION_TEMPLATE, "objects"))
    assert [item.object for item in retention.objects] == list(REQUIRED)


PIA_HEADERS = {
    "pia.zh.md": "草稿/占位文本——不构成法律意见——使用前须经在中华人民共和国获准执业的法律顾问审核",
    "pia.en.md": (
        "DRAFT/PLACEHOLDER – not legal advice – to be reviewed before use by a legal adviser admitted in the "
        "People's Republic of China"
    ),
}
PIA_MARKERS = {"pia.zh.md": "【待填写】", "pia.en.md": "[to be completed]"}


@pytest.mark.parametrize("name", PIA_FILES)
def test_the_pia_templates(name: str) -> None:
    """A-30, A-94 and owner answer 3 of P9: the draft header as the first line in the file's language, the
    PIPL triggers as an unticked checklist and the assessment points as headings, both with article numbers,
    a placeholder marker in every field and no prefilled assessment, the review by a PRC-admitted adviser
    before the first real use; UTF-8 without BOM, LF."""
    data = pia_template(name)
    assert b"\r" not in data and not data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8")
    lines = text.splitlines()
    assert lines[0] == PIA_HEADERS[name] and text.endswith("\n")
    marker = PIA_MARKERS[name]
    # every field ends with the marker, and the text names it nowhere else: a filled-in file holds none
    marked = [line for line in lines if marker in line]
    assert len(marked) == 16 and all(line.endswith(marker) and line.count(marker) == 1 for line in marked)
    fields = [line for line in lines if line.startswith("- ") and not line.startswith("- [")]
    assert len(fields) == 15 and all(line.endswith(marker) for line in fields)  # nothing prefilled
    assert sum(line.startswith("- [ ] ") for line in lines) == 5 and "- [x]" not in text.lower()
    if name == "pia.en.md":
        assert "(PIPL Art. 55)" in text and all(f"(PIPL Art. 56, item {n})" in text for n in (1, 2, 3))
        assert "reviews this template before its first real use" in text
    else:
        assert "（第五十五条）" in text and all(f"（第五十六条第{n}项）" in text for n in "一二三")
        assert "本模板在首次实际使用前，由在中华人民共和国获准执业的法律顾问审核。" in text


# --- the canonical hashes (results.json config.<file>_sha256) -----------------------------------------------


def test_the_hashes_are_the_same_for_every_spelling_of_the_same_register() -> None:
    other_role = "  - role: data_steward\n    description: d\n    actions: [read]\n    objects: [a, b]\n"
    one = parse_roles(roles_doc(extra=other_role).encode("utf-8"))
    respelled = parse_roles(
        b"# notes\r\nroles:\r\n  - {objects: [b, a], actions: [read], description: d, role: data_steward}\r\n"
        b"  - role: QA.lead\r\n    objects: ['.neurogrid/vault/consents.yaml', '**']\r\n"
        b'    actions: [read, report]\r\n    description: "Reviews the reports"\r\nformat_version: 1\r\n'
    )
    assert one.canonical_sha256() == respelled.canonical_sha256()
    assert parse_roles(roles_doc().encode()).canonical_sha256() != one.canonical_sha256()
    risks = parse_risks(risks_doc(extra=RISK.replace("R-2026-01", "R0")).encode("utf-8"))
    respelled_risks = parse_risks(
        risks_doc(
            RISK.replace("R-2026-01", "R0").replace("[sharing, training]", "[training, sharing]"),
            RISK.replace("2026-09-01", "'2026-09-01'"),
        ).encode("utf-8")
    )
    assert risks.canonical_sha256() == respelled_risks.canonical_sha256()
    changed = risks_doc(extra=RISK.replace("R-2026-01", "R0").replace("Second model", "Third model"))
    assert parse_risks(changed.encode("utf-8")).canonical_sha256() != risks.canonical_sha256()
    access = "  - object: access_log\n    created: 2026-11-02\n    min_until: 2030-01-01\n"
    retention = parse_retention(retention_doc(extra=access).encode("utf-8"))
    assert (
        retention.canonical_sha256()
        == parse_retention(retention_doc(access, ITEM).encode()).canonical_sha256()
    )
    later = retention_doc(extra=access.replace("2030-01-01", "2030-01-02"))
    assert parse_retention(later.encode("utf-8")).canonical_sha256() != retention.canonical_sha256()


def test_the_hashes_are_canonical_json_of_the_parsed_content() -> None:
    """The hash rule, pinned: canonical JSON (kernel.canonical) of format_version and the entries sorted by
    their key (roles also with sorted objects), as consents_sha256 (A-91)."""
    roles = parse_roles(uncommented(ROLES_TEMPLATE, "roles"))
    entries = sorted(roles.roles, key=lambda role: role.role)
    expected = [{**role.model_dump(mode="json"), "objects": sorted(role.objects)} for role in entries]
    assert roles.canonical_sha256() == canonical.sha256_of({"format_version": 1, "roles": expected})
    empty = {
        name: parse(template).canonical_sha256() for name, (template, parse, _k, _e) in TEMPLATES.items()
    }
    assert empty == {
        "roles": canonical.sha256_of({"format_version": 1, "roles": []}),
        "risks": canonical.sha256_of({"format_version": 1, "risks": []}),
        "retention": canonical.sha256_of({"format_version": 1, "objects": []}),
    }
    risks = parse_risks(uncommented(RISKS_TEMPLATE, "risks"))
    assert json.loads(canonical.dumps({"risks": [risks.risks[0]]}))["risks"][0] == {
        "id": "R-2026-01",
        "date": "2026-09-01",
        "description": "The recordings are also used to train a second model",
        "affected_uses": ["training", "sharing"],
        "min_consent_version": 2,
    }


# --- the schemas accept what the readers accept (apart from rules across entries and fields) ---------------

AGREEMENT: dict[str, tuple[str, str, bool]] = {
    "roles: valid": ("roles", roles_doc(), True),
    "roles: empty": ("roles", "format_version: 1\nroles: []\n", True),
    "roles: with ethics ref": ("roles", roles_doc(extra="    ethics_approval_ref: EC-1\n"), True),
    "roles: bad role": ("roles", roles_doc(ROLE.replace("QA.lead", "'a b'")), False),
    "roles: blank description": ("roles", roles_doc(ROLE.replace("Reviews the reports", "' '")), False),
    "roles: unknown action": ("roles", roles_doc(ROLE.replace("[report, read]", "[delete]")), False),
    "roles: action twice": ("roles", roles_doc(ROLE.replace("[report, read]", "[read, read]")), False),
    "roles: absolute object": ("roles", roles_doc(ROLE.replace("'**'", "'/x'")), False),
    "roles: object with '..'": ("roles", roles_doc(ROLE.replace("'**'", "'a/../b'")), False),
    "roles: object '..'": ("roles", roles_doc(ROLE.replace("'**'", "'..'")), False),
    "roles: object with a colon": ("roles", roles_doc(ROLE.replace("'**'", "'a:b'")), False),
    "roles: object with a backslash": ("roles", roles_doc(ROLE.replace("'**'", "'a\\b'")), False),
    "roles: object with dots in a name": ("roles", roles_doc(ROLE.replace("'**'", "'a..b/c.'")), True),
    "roles: no objects": (
        "roles",
        roles_doc(ROLE.replace("['**', '.neurogrid/vault/consents.yaml']", "[]")),
        False,
    ),
    "roles: unknown key": ("roles", roles_doc(extra="    note: x\n"), False),
    "roles: no format_version": ("roles", "roles: []\n", False),
    "risks: valid": ("risks", risks_doc(), True),
    "risks: date as text": ("risks", risks_doc(RISK.replace("2026-09-01", "'2026-09-01'")), True),
    "risks: bad ID": ("risks", risks_doc(RISK.replace("R-2026-01", "1R")), False),
    "risks: impossible date": ("risks", risks_doc(RISK.replace("2026-09-01", "'2026-02-30'")), False),
    "risks: no use": ("risks", risks_doc(RISK.replace("[sharing, training]", "[]")), False),
    "risks: use twice": (
        "risks",
        risks_doc(RISK.replace("[sharing, training]", "[sharing, sharing]")),
        False,
    ),
    "risks: version 0": (
        "risks",
        risks_doc(RISK.replace("min_consent_version: 2", "min_consent_version: 0")),
        False,
    ),
    "risks: no risks": ("risks", "format_version: 1\n", False),
    "retention: valid": ("retention", retention_doc(extra="    review_at: 2028-01-01\n"), True),
    "retention: unknown object": ("retention", retention_doc(ITEM.replace("pia", "data")), False),
    "retention: no created": (
        "retention",
        retention_doc(ITEM.replace("    created: 2026-11-02\n", "")),
        False,
    ),
    "retention: format_version 2": ("retention", "format_version: 2\nobjects: []\n", False),
}
PARSERS: dict[str, Parser] = {"roles": parse_roles, "risks": parse_risks, "retention": parse_retention}


class _Yaml12Loader(yaml.SafeLoader):
    """Dates stay text, as a YAML 1.2 tool reads them; the schema's format "date" checks them."""


_Yaml12Loader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _reader_accepts(name: str, text: str) -> bool:
    try:
        PARSERS[name](text.encode("utf-8"))
    except ConfigError:
        return False
    return True


def _schema_accepts(name: str, text: str) -> bool:
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    data = json.loads(json.dumps(yaml.load(text, Loader=_Yaml12Loader)))  # noqa: S506 - the strict SafeLoader
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    return validator.is_valid(data)


@pytest.mark.parametrize(("name", "text", "valid"), AGREEMENT.values(), ids=list(AGREEMENT))
def test_schema_and_reader_accept_the_same_documents(name: str, text: str, valid: bool) -> None:
    """The schema cannot compare entries or fields: unique role names and risk IDs, the retention rules and
    the printable-text rule are the reader's alone (tests above)."""
    assert (_reader_accepts(name, text), _schema_accepts(name, text)) == (valid, valid)


# --- error texts (zh, en, de) -------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["roles", "risks", "retention"])
def test_every_error_of_a_register_has_a_text_in_every_language(name: str) -> None:
    """The keys are built from the register's name (model._registers), so the code scan of
    test_language_and_wording cannot see them."""
    kinds = ["invalid", "too_large", "encoding", "not_a_file", "unreadable"]
    kinds += ["too_short"] if name == "retention" else []
    params = {"invalid": {"field", "problem"}, "too_large": {"limit"}, "too_short": {"object"}}
    for lang in LANGUAGES:
        for kind in kinds:
            text = tables()[lang][f"errors.{name}.{kind}"]
            assert set(re.findall(r"\{(\w+)\}", text)) == params.get(kind, set()), (lang, kind)
            assert f"{name}.yaml" in text, (lang, kind)
