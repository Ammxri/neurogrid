"""The role register of NeuroVault: ``<vault>/roles.yaml`` (NV-F04, KONZEPT 2.8; A-30, A-93). Which role may
perform which action on which objects, with the reference to the ethics approval. The schema is generated from
RoleRegister (tools/gen_schemas.py: schemas/roles.schema.json).

Format (format_version 1)::

    format_version: 1
    roles:
      - role: data_steward                     # model.access.ROLE_PATTERN, unique in the file
        description: Prepares and checks the dataset   # 1..200 printable characters
        actions: [read, check, convert, report]  # 1..6 of model.access.ACTIONS, each once
        objects: ["**", ".neurogrid/vault/consents.yaml"]  # 1..100 relative POSIX paths or patterns
        ethics_approval_ref: "EC-2026-17"        # optional, 1..120 printable characters

Objects are paths and patterns in the two namespaces of access events (A-14, A-66): relative to the dataset
for data events (``**`` = the whole dataset), relative to the project root for the files of the vault; each
follows model.access.object_problem, as an event object does. The register is advisory (A-30, NZ-08):
NeuroGrid never refuses an access because of it; CORE-NV04-01 compares the events of the access log with it.
A role is a role name or initials, never a personal name (NZ-09). Descriptions and ethics references stay in
the file: they never reach results.json, a report or the console (A-51).

The file is a control file (C2): invalid content ends a run with exit 2 and names the place (entry index and
field name), never the text of a value (model._registers). NeuroGrid never rewrites it.

Only kernel and model imports (ARC-01).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from neurogrid.kernel import canonical
from neurogrid.model._registers import (
    FILE_KEY,
    INVALID_TEXT,
    FormatVersion,
    RegisterSpec,
    TupleFromList,
    first_duplicate,
    invalid,
    parse_register,
    text_valid,
)
from neurogrid.model.access import ACTIONS, MAX_OBJECT_CHARS, ROLE_PATTERN, Action, object_problem
from neurogrid.model.consent import MAX_ETHICS_REF_CHARS, ethics_ref_valid

MAX_FILE_BYTES = 1_000_000
MAX_ROLES = 200
MAX_DESCRIPTION_CHARS = 200
MAX_ROLE_OBJECTS = 100
LIST_KEY = "roles"
ENTRY_KEYS = ("role", "description", "actions", "objects", "ethics_approval_ref")
# Problems of the validators below (the ValueError text, a fixed key shown in errors.roles.invalid). An object
# that is no relative POSIX path or pattern is object_<reason of model.access.object_problem>.
DUPLICATE_ROLE = "duplicate_role"
DUPLICATE_ACTION = "duplicate_action"
ETHICS_REF_TEXT = "ethics_ref_text"
OBJECT_PROBLEMS = tuple(
    f"object_{reason}" for reason in ("length", "encoding", "control", "separator", "absolute", "parent")
)
SPEC = RegisterSpec(
    name="roles",
    list_key=LIST_KEY,
    max_bytes=MAX_FILE_BYTES,
    keys=frozenset((FILE_KEY, LIST_KEY, *ENTRY_KEYS)),
    problems=frozenset((INVALID_TEXT, DUPLICATE_ACTION, ETHICS_REF_TEXT, *OBJECT_PROBLEMS)),
)
_ACTION_ORDER = {action: index for index, action in enumerate(ACTIONS)}
# The JSON schema of an object: what model.access.object_problem accepts (no leading '/', no backslash or
# colon, no '..' segment, no control character; the reader also refuses lone surrogates).
OBJECT_SCHEMA_PATTERN = r"^(?!/)(?!.*[\\:])(?!(?:.*/)?\.\.(?:/|$))[^\x00-\x1f\x7f-\x9f]+$"


def _object(value: str) -> str:
    """An object of a role is a relative POSIX path or pattern, as an event object is (A-14, A-52)."""
    problem = object_problem(value)
    if problem is not None:
        raise ValueError(f"object_{problem}")
    return value


RoleObject = Annotated[
    str,
    Field(min_length=1, max_length=MAX_OBJECT_CHARS, json_schema_extra={"pattern": OBJECT_SCHEMA_PATTERN}),
    AfterValidator(_object),
]


class Role(BaseModel):
    """One role of the register (A-93). ``actions`` is kept in the order of model.access.ACTIONS, so equal
    roles are equal objects however the file lists the actions; ``objects`` keeps the order of the file."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    role: str = Field(pattern=ROLE_PATTERN)
    description: str = Field(
        min_length=1, max_length=MAX_DESCRIPTION_CHARS, json_schema_extra={"pattern": r"\S"}
    )
    actions: Annotated[tuple[Action, ...], TupleFromList] = Field(
        min_length=1, max_length=len(ACTIONS), json_schema_extra={"uniqueItems": True}
    )
    objects: Annotated[tuple[RoleObject, ...], TupleFromList] = Field(
        min_length=1, max_length=MAX_ROLE_OBJECTS
    )
    ethics_approval_ref: str | None = Field(
        default=None, min_length=1, max_length=MAX_ETHICS_REF_CHARS, json_schema_extra={"pattern": r"\S"}
    )

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        if not text_valid(value, MAX_DESCRIPTION_CHARS):
            raise ValueError(INVALID_TEXT)
        return value

    @field_validator("actions")
    @classmethod
    def _actions(cls, value: tuple[Action, ...]) -> tuple[Action, ...]:
        if len(set(value)) != len(value):
            raise ValueError(DUPLICATE_ACTION)
        return tuple(sorted(value, key=_ACTION_ORDER.__getitem__))

    @field_validator("ethics_approval_ref")
    @classmethod
    def _ethics_ref(cls, value: str | None) -> str | None:
        if value is not None and not ethics_ref_valid(value):
            raise ValueError(ETHICS_REF_TEXT)
        return value


class RoleRegister(BaseModel):
    """The whole roles.yaml. ``format_version`` and ``roles`` are required in a file (parse_roles, and the
    schema); the defaults only serve NeuroGrid's own construction. Role names are unique (parse_roles)."""

    model_config = ConfigDict(
        strict=True, extra="forbid", json_schema_extra={"required": [FILE_KEY, LIST_KEY]}
    )

    format_version: FormatVersion = 1
    roles: list[Role] = Field(default_factory=list, max_length=MAX_ROLES)

    @property
    def entries(self) -> list[Role]:
        return self.roles

    def canonical_sha256(self) -> str:
        """Hash over the parsed content (results.json config.roles_sha256): the same for every spelling of
        the same register (order of roles, actions and objects, quoting, comments, line ends)."""
        roles = sorted(self.roles, key=lambda entry: entry.role)
        return canonical.sha256_of(
            {
                "format_version": self.format_version,
                "roles": [
                    {**entry.model_dump(mode="json"), "objects": sorted(entry.objects)} for entry in roles
                ],
            }
        )

    def by_role(self) -> dict[str, Role]:
        """role name -> its entry."""
        return {entry.role: entry for entry in self.roles}


def parse_roles(data: bytes) -> RoleRegister:
    """Parse roles.yaml bytes (model._registers.parse_register), then the roles against each other: a role
    name given twice is errors.roles.invalid at the later entry (problem duplicate_role)."""
    parsed = parse_register(data, SPEC, RoleRegister)
    index = first_duplicate([entry.role for entry in parsed.roles])
    if index is not None:
        raise invalid(SPEC, f"{LIST_KEY}.{index}.role", DUPLICATE_ROLE)
    return parsed
