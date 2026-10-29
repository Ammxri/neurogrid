"""The access event model of the vault log (DM-09, NV-F03, A-30, A-90): the PRD fields in English plus
format_version, seq and tool_version, no OS user or host, strict validation of every field."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from neurogrid.model.access import (
    ACTIONS,
    MAX_OBJECTS,
    ROLE_PATTERN,
    AccessEvent,
    format_time,
    object_problem,
    role_valid,
    text_problem,
    time_valid,
)

ROOT = Path(__file__).resolve().parents[2]
GENESIS = "0" * 64
# DM-09 (PRD §10, D-03): zeit, rolle, aktion, objekte, zweck, genehmigung_ref, vorheriger_hash, hash
PRD_FIELDS = {"time", "role", "action", "objects", "purpose", "approval_ref", "previous_hash", "hash"}


def event(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "format_version": 1,
        "seq": 1,
        "time": "2026-10-29T12:00:00Z",
        "role": "data_steward",
        "action": "check",
        "objects": ["**"],
        "purpose": "pre-check before registration",
        "approval_ref": "EC-2026-17",
        "tool_version": "0.2.0",
        "previous_hash": GENESIS,
        "hash": "a" * 64,
    }
    data.update(changes)
    return data


def test_access_event_fields_dm09_no_user_host() -> None:
    fields = set(AccessEvent.model_fields)
    assert PRD_FIELDS <= fields
    assert fields - PRD_FIELDS == {"format_version", "seq", "tool_version"}
    for forbidden in ("user", "host", "pid", "path", "machine", "login", "computer"):
        assert not [name for name in fields if forbidden in name], forbidden
    assert all(field.is_required() for field in AccessEvent.model_fields.values())  # the hash input is fixed


def test_actions_are_the_vocabulary_of_the_role_register() -> None:
    assert ACTIONS == ("read", "check", "convert", "report", "export", "consent_manage")  # KONZEPT 2.8


def test_valid_event_is_accepted_and_frozen() -> None:
    parsed = AccessEvent.model_validate(event(role=None, purpose=None, approval_ref=None), strict=True)
    assert parsed.role is None and parsed.objects == ["**"]
    with pytest.raises(ValidationError):
        parsed.seq = 2  # type: ignore[misc]
    for action in ACTIONS:
        assert AccessEvent.model_validate(event(action=action), strict=True).action == action
    assert AccessEvent.model_validate(event(objects=["x"] * MAX_OBJECTS), strict=True)


REJECTED: list[tuple[str, Any]] = [
    ("format_version", 2),
    ("format_version", True),
    ("format_version", 1.0),
    ("format_version", "1"),
    ("seq", 0),
    ("seq", True),
    ("seq", "1"),
    ("seq", 1.0),
    ("time", "2026-10-29T12:00:00"),
    ("time", "2026-10-29T12:00:00+00:00"),
    ("time", "2026-10-29T12:00:00.5Z"),
    ("time", "2026-10-29 12:00:00Z"),
    ("time", "2026-02-30T12:00:00Z"),
    ("time", "2026-10-29T24:00:00Z"),
    ("time", "2026-10-29T12:00:60Z"),
    ("time", "٢٠٢٦-10-29T12:00:00Z"),
    ("time", "2026-10-29T12:00:00Z\n"),
    ("role", "QA lead"),
    ("role", "7am"),
    ("role", "a" * 81),
    ("role", "Wáng"),
    ("role", "DOMAIN\\user"),
    ("role", ""),
    ("role", "data_steward\n"),
    ("action", "delete"),
    ("action", "Check"),
    ("objects", []),
    ("objects", ["**"] * (MAX_OBJECTS + 1)),
    ("objects", [""]),
    ("objects", ["x" * 1025]),
    ("objects", ["/abs/file.edf"]),
    ("objects", ["C:/data/file.edf"]),
    ("objects", ["file.edf:stream"]),
    ("objects", ["\\\\server\\share\\x.edf"]),
    ("objects", ["sub-01\\x.edf"]),
    ("objects", ["../outside.edf"]),
    ("objects", ["sub-01/../../x"]),
    ("objects", ["a\nb"]),
    ("objects", ["a\x00b"]),
    ("objects", ["\ud800"]),
    ("objects", [1]),
    ("objects", "**"),
    ("purpose", ""),
    ("purpose", "p" * 201),
    ("purpose", "two\nlines"),
    ("purpose", "x\ud800"),
    ("approval_ref", "r" * 121),
    ("approval_ref", "a\tb"),
    ("tool_version", ""),
    ("tool_version", "v" * 41),
    ("previous_hash", "A" * 64),
    ("previous_hash", "0" * 63),
    ("hash", "g" * 64),
    ("hash", None),
    ("user", "someone"),
    ("host", "machine"),
]


@pytest.mark.parametrize(("field", "value"), REJECTED, ids=[f"{f}-{i}" for i, (f, _) in enumerate(REJECTED)])
def test_strict_rejections(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        AccessEvent.model_validate(event(**{field: value}), strict=True)


@pytest.mark.parametrize("missing", sorted(AccessEvent.model_fields))
def test_every_field_is_required(missing: str) -> None:
    data = event()
    del data[missing]
    with pytest.raises(ValidationError):
        AccessEvent.model_validate(data, strict=True)


@pytest.mark.parametrize(
    "item",
    [
        "**",
        "sub-01/**",
        "sub-01/eeg/sub-01_task-rest_eeg.edf",
        "rec-1a2b3c4d.edf",
        "*.edf",
        ".neurogrid/vault/consents.yaml",
        "a b/c,d.edf",
        "数据/记录.edf",
    ],
)
def test_objects_accept_relative_paths_and_patterns(item: str) -> None:
    assert object_problem(item) is None
    assert AccessEvent.model_validate(event(objects=[item]), strict=True).objects == [item]


def test_object_problems_are_named() -> None:
    assert object_problem("") == "length"
    assert object_problem("x" * 1025) == "length"
    assert object_problem("a\x7fb") == "control"
    assert object_problem("a\x85b") == "control"  # C1 control (NEL)
    assert object_problem("\udc00") == "encoding"
    assert object_problem("a\\b") == "separator"
    assert object_problem("/x") == "absolute"
    assert object_problem("x:y") == "absolute"
    assert object_problem("a/../b") == "parent"
    assert object_problem("a/..b/c..") is None  # '..' only as a whole segment


def test_text_problem() -> None:
    assert text_problem("pre-check before registration") is None
    assert text_problem("预检查") is None
    assert text_problem("tab\there") == "control"
    assert text_problem("lone \ud83d") == "encoding"


@pytest.mark.parametrize(
    ("role", "valid"),
    [
        ("data_steward", True),
        ("QA.lead", True),
        ("AB", True),
        ("x-1", True),
        ("a" * 80, True),
        ("a" * 81, False),
        ("QA lead", False),
        ("_x", False),
        ("1st", False),
        ("角色", False),
        ("", False),
    ],
)
def test_role_pattern(role: str, valid: bool) -> None:
    assert role_valid(role) is valid
    assert ROLE_PATTERN.startswith("^") and ROLE_PATTERN.endswith("$")


def test_time_format_and_conversion() -> None:
    assert time_valid("2024-02-29T23:59:59Z")
    assert not time_valid("2023-02-29T00:00:00Z")
    beijing = timezone(timedelta(hours=8))
    assert format_time(datetime(2026, 10, 29, 20, 0, 5, 999_999, tzinfo=beijing)) == "2026-10-29T12:00:05Z"
    assert format_time(datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)) == "2026-10-29T12:00:00Z"


def test_schema_is_generated_and_checked_in() -> None:
    """DM-09: the published schema of an access.jsonl line (tools/gen_schemas.py --check runs in
    test_architecture.py)."""
    import gen_schemas  # type: ignore[import-not-found]

    assert gen_schemas.MODELS["access_event"] is AccessEvent
    path = ROOT / "src" / "neurogrid" / "schemas" / "access_event.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert set(schema["required"]) == set(AccessEvent.model_fields)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["action"]["enum"] == list(ACTIONS)
    assert path.read_text(encoding="utf-8") == gen_schemas.render(AccessEvent)
