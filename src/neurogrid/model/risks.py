"""The risk register of NeuroVault: ``<vault>/risks.yaml`` (NV-F06; A-30, A-95). Risks found after consents
were given, with the uses they affect and the consent version from which a consent covers them. The schema
is generated from RiskRegister (tools/gen_schemas.py: schemas/risks.schema.json).

Format (format_version 1)::

    format_version: 1
    risks:
      - id: R-2026-01                  # a letter, then letters, digits, '_', '.' or '-'; 1..40, unique
        date: 2026-09-01               # a YAML date or the text "2026-09-01"
        description: Second model trained on the recordings   # 1..500 printable characters
        affected_uses: [training, sharing]                     # 1..5 consent uses, each once
        min_consent_version: 2         # integer 1..model.consent.MAX_VERSION

CORE-M14-02 (consent.reconsent) judges the risks dated on or before the reference date: a subject whose
recordings need an affected use and whose valid consent has a lower version than ``min_consent_version`` may
need a new consent; the ethics committee decides (A-30). The description stays in the file: it never reaches
results.json, a report, an export or the console (A-51); the ID, the date, the uses and the version may.

The file is a control file (C2): invalid content ends a run with exit 2 and names the place (entry index and
field name), never the text of a value (model._registers). NeuroGrid never rewrites it.

Only kernel and model imports (ARC-01).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from neurogrid.kernel import canonical
from neurogrid.model._registers import (
    FILE_KEY,
    INVALID_TEXT,
    FormatVersion,
    RegisterDate,
    RegisterSpec,
    TupleFromList,
    first_duplicate,
    invalid,
    parse_register,
    text_valid,
)
from neurogrid.model.consent import MAX_VERSION, ConsentUse, Use, ordered_uses

MAX_FILE_BYTES = 1_000_000
MAX_RISKS = 1_000
MAX_ID_CHARS = 40
MAX_DESCRIPTION_CHARS = 500
RISK_ID_PATTERN = rf"^[A-Za-z][A-Za-z0-9_.-]{{0,{MAX_ID_CHARS - 1}}}$"
LIST_KEY = "risks"
ENTRY_KEYS = ("id", "date", "description", "affected_uses", "min_consent_version")
# Problems of the validators below (the ValueError text, a fixed key shown in errors.risks.invalid).
DUPLICATE_ID = "duplicate_id"
DUPLICATE_USE = "duplicate_use"
SPEC = RegisterSpec(
    name="risks",
    list_key=LIST_KEY,
    max_bytes=MAX_FILE_BYTES,
    keys=frozenset((FILE_KEY, LIST_KEY, *ENTRY_KEYS)),
    problems=frozenset((INVALID_TEXT, DUPLICATE_USE)),
)


class Risk(BaseModel):
    """One risk of the register (A-95). ``affected_uses`` is kept in ConsentUse order, so equal risks are
    equal objects however the file lists the uses."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    id: str = Field(pattern=RISK_ID_PATTERN)
    date: RegisterDate
    description: str = Field(
        min_length=1, max_length=MAX_DESCRIPTION_CHARS, json_schema_extra={"pattern": r"\S"}
    )
    affected_uses: Annotated[tuple[Use, ...], TupleFromList] = Field(
        min_length=1, max_length=len(ConsentUse), json_schema_extra={"uniqueItems": True}
    )
    min_consent_version: int = Field(ge=1, le=MAX_VERSION)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        if not text_valid(value, MAX_DESCRIPTION_CHARS):
            raise ValueError(INVALID_TEXT)
        return value

    @field_validator("affected_uses")
    @classmethod
    def _uses(cls, value: tuple[ConsentUse, ...]) -> tuple[ConsentUse, ...]:
        if len(set(value)) != len(value):
            raise ValueError(DUPLICATE_USE)
        return ordered_uses(value)


class RiskRegister(BaseModel):
    """The whole risks.yaml. ``format_version`` and ``risks`` are required in a file (parse_risks, and the
    schema); the defaults only serve NeuroGrid's own construction. Risk IDs are unique (parse_risks)."""

    model_config = ConfigDict(
        strict=True, extra="forbid", json_schema_extra={"required": [FILE_KEY, LIST_KEY]}
    )

    format_version: FormatVersion = 1
    risks: list[Risk] = Field(default_factory=list, max_length=MAX_RISKS)

    @property
    def entries(self) -> list[Risk]:
        return self.risks

    def canonical_sha256(self) -> str:
        """Hash over the parsed content (results.json config.risks_sha256): the same for every spelling of
        the same register (order of risks and uses, quoting, comments, line ends)."""
        risks = sorted(self.risks, key=lambda entry: entry.id)
        return canonical.sha256_of(
            {
                "format_version": self.format_version,
                "risks": [entry.model_dump(mode="json") for entry in risks],
            }
        )


def parse_risks(data: bytes) -> RiskRegister:
    """Parse risks.yaml bytes (model._registers.parse_register), then the risks against each other: an ID
    given twice is errors.risks.invalid at the later entry (problem duplicate_id)."""
    parsed = parse_register(data, SPEC, RiskRegister)
    index = first_duplicate([entry.id for entry in parsed.risks])
    if index is not None:
        raise invalid(SPEC, f"{LIST_KEY}.{index}.id", DUPLICATE_ID)
    return parsed
