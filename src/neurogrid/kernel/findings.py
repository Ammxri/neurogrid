"""Findings and their vocabulary (PRD §10 Finding, A-09).

PRD names (German) map to these English fields: regel_id→rule_id, klausel→clause,
schweregrad→severity, status, messwert→measured_value, schwelle→threshold, objekt→object,
belege→details.

Severity levels follow the model of NWB Inspector (LIB-10): its importance levels CRITICAL,
BEST_PRACTICE_VIOLATION and BEST_PRACTICE_SUGGESTION correspond to error, warning and info, and checks
are registered functions that report what they found while a separate layer decides on severity.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ParamValue = str | int | float | bool


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


SEVERITY_ORDER: dict[Severity, int] = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


class Phase(StrEnum):
    ACQUISITION = "acquisition"
    PROCESSING = "processing"
    ANNOTATION = "annotation"
    STORAGE = "storage"
    ACCESS = "access"


class Verification(StrEnum):
    AUTOMATIC = "automatic"
    SEMI_AUTOMATIC = "semi_automatic"
    MANUAL = "manual"


class SourceStatus(StrEnum):
    """Where the rules of a pack come from (A-41)."""

    PLACEHOLDER = "placeholder"
    SECONDARY = "secondary"
    INVENTORY = "inventory"
    FINAL = "final"


class Status(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    EXCEPTED = "excepted"
    NOT_APPLICABLE = "not_applicable"
    NOT_CHECKABLE = "not_checkable"
    EVIDENCE_OPEN = "evidence_open"


class Light(StrEnum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    GREY = "grey"


class TimeRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_s: float
    end_s: float


class EffectiveParam(BaseModel):
    """A threshold as applied, with its origin (A-13: toml > rule pack > check default)."""

    model_config = ConfigDict(extra="forbid")

    value: ParamValue
    origin: Literal["check", "rulepack", "config"]


class Finding(BaseModel):
    """One finding per rule × object × subkey.

    ``params`` holds the effective thresholds of the rule with their origin (A-13). ``key`` is stable across
    runs and independent of the display option ``--show-paths`` (A-09).
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    rule_id: str
    rulepack: str
    rulepack_version: str
    source_status: SourceStatus
    clause: str
    phase: Phase
    severity: Severity
    status: Status
    object: str
    subkey: str | None = None
    file: str | None = None
    channel: str | None = None
    measured_value: Any = None
    threshold: Any = None
    params: dict[str, EffectiveParam] = Field(default_factory=dict)
    time_ranges: list[TimeRange] = Field(default_factory=list)
    time_ranges_total: int = 0
    time_ranges_duration_s: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    message_key: str
    reason: str | None = None


class PassedCount(BaseModel):
    """Passed checks are counted per rule and object instead of being listed (A-59)."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    object: str
    count: int


class Notice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Severity
    message_key: str
    params: dict[str, Any] = Field(default_factory=dict)


class PhaseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    light: Light
    errors: int = 0
    warnings: int = 0
    open_evidence: int = 0


def finding_key(rule_id: str, obj: str, subkey: str | None) -> str:
    raw = "\x1f".join((rule_id, obj, subkey or ""))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
