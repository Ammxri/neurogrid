"""The comparison of two check runs, ``neurogrid diff`` (NG-F15, CLI-07, A-33, A-97). The schema
diff.schema.json is generated from these models (tools/gen_schemas.py).

A finding of the comparison carries only what results.json shows of it in both runs (key, rule, pack,
severity, status, object, sub-key, file, channel, measured value, reason), never its details, thresholds or
time ranges. Findings of rules on a consent check (``consent.*``) are only counted per rule and category
(D-17 option B, owner answer 4 of P9): no subject of the consent records is listed (A-51)."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from neurogrid.kernel.findings import Severity, Status
from neurogrid.model.results import Disclaimer, ToolInfo

DIFF_SCHEMA_VERSION = "1.0"
Category = Literal["new", "fixed", "removed", "changed"]
CATEGORIES: tuple[Category, ...] = ("new", "fixed", "removed", "changed")


class DiffDataset(BaseModel):
    """The dataset fields that tell whether both runs looked at the same dataset."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str | None = None
    version: str | None = None


class DiffRulepack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    sha256: str


class DiffRun(BaseModel):
    """One of the two results.json files: the NeuroGrid version, dataset, reference date, configuration hash
    and rule packs of its run. No path of the file (A-51)."""

    model_config = ConfigDict(extra="forbid")

    tool_version: str
    dataset: DiffDataset
    as_of: date
    config_sha256: str
    rulepacks: list[DiffRulepack]


class DiffRules(BaseModel):
    """Rule IDs loaded in only one of the runs, sorted."""

    model_config = ConfigDict(extra="forbid")

    added: list[str] = Field(default_factory=list)  # only in the new run
    removed: list[str] = Field(default_factory=list)  # only in the old run


class DiffSummary(BaseModel):
    """Counts of every compared key, the aggregated consent rules included. ``new_errors`` counts the keys
    that are a counted error finding of the new run and none of the old run; it alone sets the exit code."""

    model_config = ConfigDict(extra="forbid")

    new: int = 0
    fixed: int = 0
    removed: int = 0
    changed: int = 0
    unchanged: int = 0
    new_errors: int = 0
    placeholder_skipped: int = 0  # keys of placeholder packs in either run, not compared (A-41)
    exit_code: int = 0


class DiffFinding(BaseModel):
    """A finding that is new (its state in the new run), fixed or removed (its state in the old run)."""

    model_config = ConfigDict(extra="forbid")

    key: str
    rule_id: str
    rulepack: str
    severity: Severity
    status: Status
    object: str
    subkey: str | None = None
    file: str | None = None
    channel: str | None = None
    measured_value: Any = None  # floats rounded to 6 significant digits, non-finite numbers null (A-61)
    reason: str | None = None


class DiffState(BaseModel):
    """What can change of a finding whose key is in both runs."""

    model_config = ConfigDict(extra="forbid")

    status: Status
    severity: Severity
    measured_value: Any = None


class DiffChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    rule_id: str
    object: str
    subkey: str | None = None
    old: DiffState
    new: DiffState


class DiffFindings(BaseModel):
    """The listed findings per category, in the order of results.json (A-61): severity, rule, object,
    sub-key, then the key. Findings of consent rules are only counted (DiffResult.aggregated)."""

    model_config = ConfigDict(extra="forbid")

    new: list[DiffFinding] = Field(default_factory=list)
    fixed: list[DiffFinding] = Field(default_factory=list)
    removed: list[DiffFinding] = Field(default_factory=list)
    changed: list[DiffChange] = Field(default_factory=list)


class DiffCount(BaseModel):
    """The number of findings of one consent rule in one category (D-17 option B)."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    category: Category
    count: int


class DiffResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = DIFF_SCHEMA_VERSION
    disclaimer: Disclaimer
    tool: ToolInfo
    old: DiffRun
    new: DiffRun
    rules: DiffRules
    summary: DiffSummary
    findings: DiffFindings
    aggregated: list[DiffCount] = Field(default_factory=list)  # by rule, then category (new, fixed, ...)
