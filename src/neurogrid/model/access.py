"""Access events of the NeuroVault access log (DM-09, NV-F03, A-30, A-90). The schema is generated from this
model (tools/gen_schemas.py: schemas/access_event.schema.json).

PRD → English (D-03): zeit→time (UTC), rolle→role, aktion→action, objekte→objects, zweck→purpose,
genehmigung_ref→approval_ref, vorheriger_hash→previous_hash, hash. Added: format_version, seq (position in the
chain, 1..n) and tool_version (the NeuroGrid version that wrote the entry).

An event holds no OS user, host name, process ID or absolute path (A-30, A-51): ``role`` is a role name or
initials chosen by the user (ROLE_PATTERN, KONZEPT 2.8, NZ-09), ``objects`` are relative POSIX paths or
patterns in two namespaces (A-14, A-66): data events name the dataset (``**`` = the whole dataset, manual
entries dataset-relative paths and patterns), events about vault files name the file relative to the project
root (``.neurogrid/vault/consents.yaml``). The hash rule and the chain live in neurogrid.vault.ledger.

Only kernel imports (ARC-01): the vault, the checks and the CLI build on this model, never the reverse.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

from neurogrid.kernel.provenance import SHA256_PATTERN

FORMAT_VERSION = 1
# The action vocabulary of the role register (KONZEPT 2.8); every NeuroGrid command that touches the dataset
# or the vault maps to one of them.
Action = Literal["read", "check", "convert", "report", "export", "consent_manage"]
ACTIONS: tuple[str, ...] = get_args(Action)
# A role name or initials, never a personal name with spaces or an OS login with a domain (NZ-09); the same
# pattern applies to [vault] role in neurogrid.toml and to the keys of the P9 role register.
ROLE_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$"
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"  # UTC, whole seconds
TIME_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"  # ASCII digits only
_TIME_TEXT = re.compile(TIME_PATTERN)
_ROLE = re.compile(ROLE_PATTERN)
MAX_OBJECTS = 1000
MAX_OBJECT_CHARS = 1024
MAX_PURPOSE_CHARS = 200
MAX_APPROVAL_REF_CHARS = 120
MAX_TOOL_VERSION_CHARS = 40


_SURROGATE = re.compile("[\ud800-\udfff]")  # Unicode category Cs
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f]")  # Unicode category Cc


def text_problem(text: str) -> str | None:
    """Why a text cannot stand in the log, or None: a lone surrogate (no valid UTF-8, the hash input is UTF-8)
    or a control character (one entry is one line, the console prints it, A-53)."""
    if _SURROGATE.search(text):
        return "encoding"
    if _CONTROL.search(text):
        return "control"
    return None


def role_valid(role: str) -> bool:
    return _ROLE.fullmatch(role) is not None


def object_problem(item: str) -> str | None:
    """Why ``item`` is no valid object, or None. An object is a relative POSIX path or pattern (A-14 globs
    such as ``**`` or ``sub-01/**`` are allowed): 1..MAX_OBJECT_CHARS characters, no control character, no
    backslash (POSIX separators only), no absolute, drive, UNC or stream path (no leading '/', no colon)
    and no '..' segment (A-52). Objects are recorded, never opened."""
    if not item or len(item) > MAX_OBJECT_CHARS:
        return "length"
    problem = text_problem(item)
    if problem is not None:
        return problem
    if "\\" in item:
        return "separator"
    if item.startswith("/") or ":" in item:
        return "absolute"
    if ".." in item.split("/"):
        return "parent"
    return None


def time_valid(text: str) -> bool:
    """'YYYY-MM-DDTHH:MM:SSZ' with ASCII digits and a real instant (no 2026-02-30, no hour 24, no leap
    second)."""
    if not _TIME_TEXT.fullmatch(text):
        return False
    try:  # not strptime: it asks the locale on every call, too slow for a log of a million lines
        datetime(
            int(text[0:4]),
            int(text[5:7]),
            int(text[8:10]),
            int(text[11:13]),
            int(text[14:16]),
            int(text[17:19]),
        )
    except ValueError:
        return False
    return True


def format_time(moment: datetime) -> str:
    """The event time of an aware datetime: UTC, whole seconds (a naive one counts as local time)."""
    return moment.astimezone(UTC).strftime(TIME_FORMAT)


class AccessEvent(BaseModel):
    """One entry of access.jsonl (DM-09). Every field is required (null where the value is unknown), so the
    hash input is exactly the stored object without ``hash`` (neurogrid.vault.ledger)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    format_version: int = Field(ge=FORMAT_VERSION, le=FORMAT_VERSION)
    seq: int = Field(ge=1)
    time: str = Field(pattern=TIME_PATTERN)
    role: str | None = Field(pattern=ROLE_PATTERN)
    action: Action
    objects: list[Annotated[str, Field(min_length=1, max_length=MAX_OBJECT_CHARS)]] = Field(
        min_length=1, max_length=MAX_OBJECTS
    )
    purpose: str | None = Field(min_length=1, max_length=MAX_PURPOSE_CHARS)
    approval_ref: str | None = Field(min_length=1, max_length=MAX_APPROVAL_REF_CHARS)
    tool_version: str = Field(min_length=1, max_length=MAX_TOOL_VERSION_CHARS)
    previous_hash: str = Field(pattern=SHA256_PATTERN)
    hash: str = Field(pattern=SHA256_PATTERN)

    @field_validator("time")
    @classmethod
    def _time(cls, value: str) -> str:
        if not time_valid(value):
            raise ValueError("expected a UTC time YYYY-MM-DDTHH:MM:SSZ")
        return value

    @field_validator("role")
    @classmethod
    def _role(cls, value: str | None) -> str | None:
        if value is not None and not role_valid(value):
            raise ValueError("expected a role name or initials")
        return value

    @field_validator("objects")
    @classmethod
    def _objects(cls, value: list[str]) -> list[str]:
        for index, item in enumerate(value):
            if object_problem(item) is not None:
                raise ValueError(f"object {index + 1} is no relative POSIX path or pattern")
        return value

    @field_validator("purpose", "approval_ref", "tool_version")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        if value is not None and text_problem(value) is not None:
            raise ValueError("control character or invalid text")
        return value
