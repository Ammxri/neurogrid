"""results.json (NG-F14). The schema is generated from these models (tools/gen_schemas.py).

results.json never contains wall-clock times, host or user names, absolute paths, vault head hashes,
signal hashes, raw ages or diagnosis codes (A-11, A-51).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from neurogrid.kernel.engine import ExceptionUse
from neurogrid.kernel.evidence import EvidenceRecord
from neurogrid.kernel.findings import (
    EffectiveParam,
    Finding,
    Notice,
    PassedCount,
    Phase,
    PhaseSummary,
    Severity,
    SourceStatus,
    Verification,
)
from neurogrid.model.dataset import Dataset

SCHEMA_VERSION = "1.0"


class Disclaimer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zh: str
    en: str


class ToolInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "neurogrid"
    version: str


class EnvironmentInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    python: str
    platform: str
    libraries: dict[str, str]
    blas_threads: int | None = None


class RulepackInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    source: str
    source_status: SourceStatus
    norm: bool
    sha256: str


class RuleInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    rulepack: str
    clause: str
    title_zh: str
    title_en: str
    phase: Phase
    check: str
    severity: Severity
    verification: Verification
    source_status: SourceStatus


class ConfigInfo(BaseModel):
    """KONZEPT 2.3: hash, reference date, seed, sampling, effective parameters and settings (cleaned)."""

    model_config = ConfigDict(extra="forbid")

    canonical_sha256: str
    as_of: date
    seed: int
    strict: bool
    sampling: dict[str, Any]
    effective_params: dict[str, dict[str, EffectiveParam]]
    effective_settings: dict[str, Any]
    # canonical SHA-256 of the parsed evidence.yaml (A-83); None without one. Never its path (A-11, A-51).
    evidence_sha256: str | None = None


class RecordingSummary(BaseModel):
    """One recording as seen by the checks (no path; ``id`` is pseudonymous in raw folders)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    format: str
    subject: str | None = None
    session: str | None = None
    task: str | None = None
    run: str | None = None
    sampling_rate_hz: float | None = None
    duration_s: float | None = None
    n_channels: int | None = None
    n_eeg_channels: int | None = None
    streamable: bool = True
    metadata_sources: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)  # M06–M09 values per recording (NG-F07)
    sample: dict[str, Any] | None = None  # the sample of M06/M09: segments, seed, parameters (KONZEPT 1.5)


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phases: dict[Phase, PhaseSummary]
    coverage: dict[str, float | str]
    errors: int
    warnings: int
    exit_code: int
    open_evidence: int = 0  # breakdown: open evidence is counted in errors/warnings already (A-16)


class AILabelScope(BaseModel):
    """Class counts of one scope (all, train, val, test). None: a suppressed small cell (A-51)."""

    model_config = ConfigDict(extra="forbid")

    total: int | None = None
    classes: dict[str, int | None] = Field(default_factory=dict)


class AILabels(BaseModel):
    """M11 class shares per split and overall (A-21, A-81). Class keys are the displayed labels or
    ``text-<sha8>`` for free text (A-17, C5)."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["events", "participants"]
    column: str
    unit: Literal["events", "subjects"]
    scopes: dict[str, AILabelScope] = Field(default_factory=dict)


class AIDemographics(BaseModel):
    """M11 demography of the subjects with recordings, aggregated only, small cells suppressed (A-51)."""

    model_config = ConfigDict(extra="forbid")

    subjects: int
    age_documented: int | None = None
    sex_documented: int | None = None
    age_groups: dict[str, int | None] = Field(default_factory=dict)
    sex: dict[str, int | None] = Field(default_factory=dict)


class AISplits(BaseModel):
    """M12 split assignment: recordings and subjects per split (DM-06) and unassigned recordings."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["splits.tsv", "participants.tsv"]
    recordings: dict[str, int] = Field(default_factory=dict)
    subjects: dict[str, int] = Field(default_factory=dict)
    unassigned: int = 0


class AISummary(BaseModel):
    """Aggregates of the AI dataset structure (M11, M12; decision C1: optional block)."""

    model_config = ConfigDict(extra="forbid")

    labels: AILabels | None = None
    demographics: AIDemographics | None = None
    splits: AISplits | None = None


class Results(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    disclaimer: Disclaimer
    tool: ToolInfo
    environment: EnvironmentInfo
    dataset: Dataset
    rulepacks: list[RulepackInfo]
    rules: list[RuleInfo]
    config: ConfigInfo
    recordings: list[RecordingSummary]
    findings: list[Finding]
    passed: list[PassedCount]
    # rules evaluated from evidence.yaml, in pack and rule order (KONZEPT 2.3, A-83); empty in P1-P3 results
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    exceptions: list[ExceptionUse]
    notices: list[Notice]
    summary: Summary
    # M12 duplicate groups (KONZEPT 2.3): displayed recording IDs per group, never signal hashes (A-21).
    # None when no duplicate check ran; optional like every P4 field (decision C1).
    duplicates: list[list[str]] | None = None
    ai: AISummary | None = None  # M11/M12 aggregates (A-81)


class ScanFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    format: str | None = None
    size_bytes: int


class ScanResult(BaseModel):
    """The inventory of ``scan``. ``unsupported`` lists data files in a format NeuroGrid cannot read;
    ``orphans`` lists .eeg/.fdt data files that no header refers to, so they cannot be assigned to a
    recording (A-74, A-77; CORE-M01-04 reports both)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    disclaimer: Disclaimer
    tool: ToolInfo
    is_bids: bool
    formats: dict[str, int]
    recordings: list[ScanFile]
    unsupported: list[ScanFile]
    orphans: list[ScanFile] = Field(default_factory=list)
    unreadable: list[ScanFile] = Field(
        default_factory=list
    )  # folders that cannot be listed, files not opened
    other_files: int
    links_skipped: int
    subjects: int | None = None  # BIDS only; raw folders need the mapping (A-05)
    suspicious_names: int = 0  # A-51 hint: data file paths with non-ASCII letters or 6+ digits
    total_bytes: int
