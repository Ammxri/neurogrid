"""Rule engine: measurements × rules → findings (ARC-02, A-09, A-12–A-16, A-41).

Checks only measure; this module alone decides passed/failed, applies thresholds, exceptions and
evidence, and derives the per-phase traffic light, the coverage measure and the exit code.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from neurogrid.kernel import glob
from neurogrid.kernel.errors import ConfigError
from neurogrid.kernel.evidence import (
    DocumentCheck,
    DocumentChecker,
    EvidenceItem,
    EvidenceState,
    no_document_checker,
)
from neurogrid.kernel.findings import (
    SEVERITY_ORDER,
    EffectiveParam,
    Finding,
    Light,
    Notice,
    ParamValue,
    PassedCount,
    Phase,
    PhaseSummary,
    Severity,
    SourceStatus,
    Status,
    Verification,
    finding_key,
)
from neurogrid.kernel.rules import (
    EVIDENCE_CHECK,
    CheckSpec,
    LoadedRulepack,
    Measurement,
    Rule,
    check_param_value,
    validate_against_registry,
)

COUNTED = (Status.FAILED, Status.EVIDENCE_OPEN)


class ExceptionEntry(BaseModel):
    """A justified exception from neurogrid.toml (NG-F18, A-14).

    ``object`` is a pattern over relative POSIX paths; pseudonymous recording IDs match as well.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    rule: str = Field(min_length=1, max_length=64)
    object: str | None = Field(default=None, max_length=512)
    subkey: str | None = Field(default=None, max_length=128)
    reason: str = Field(max_length=1000)
    approved_by: str | None = Field(default=None, max_length=80)
    valid_until: date | None = None

    @field_validator("reason")
    @classmethod
    def _reason_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("an exception needs a reason")
        return value


class ExceptionUse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry: ExceptionEntry
    used: bool
    expired: bool


@dataclass
class EngineInput:
    packs: Sequence[LoadedRulepack]
    registry: Mapping[str, CheckSpec]
    measurements: Mapping[str, Sequence[Measurement]]
    as_of: date
    overrides: Mapping[str, Mapping[str, ParamValue]] = field(default_factory=dict)
    exceptions: Sequence[ExceptionEntry] = ()
    evidence: Mapping[str, EvidenceItem] = field(default_factory=dict)
    document_check: DocumentChecker = no_document_checker
    strict: bool = False  # --strict / [check] strict: rules with strict_severity use it (CLI-04, A-82)


@dataclass
class EngineResult:
    findings: list[Finding]
    passed: list[PassedCount]
    phases: dict[Phase, PhaseSummary]
    coverage: dict[str, float | str]
    exit_code: int
    effective_params: dict[str, dict[str, EffectiveParam]]
    exceptions: list[ExceptionUse]
    notices: list[Notice]


@dataclass(frozen=True)
class _Outcome:
    measurement: Measurement
    status: Status
    threshold: Any = None
    reason: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


def resolve_params(
    spec: CheckSpec, rule: Rule, override: Mapping[str, ParamValue]
) -> dict[str, EffectiveParam]:
    """Precedence: neurogrid.toml > rule pack > check default (A-13)."""
    values = {name: EffectiveParam(value=p.default, origin="check") for name, p in spec.params.items()}
    for name, value in rule.params.items():
        values[name] = EffectiveParam(value=value, origin="rulepack")
    for name, value in override.items():
        param = spec.params.get(name)
        if param is None:
            raise ConfigError("config.unknown_param", rule=rule.id, param=name)
        if not check_param_value(param, value):
            raise ConfigError("config.param_type", rule=rule.id, param=name)
        values[name] = EffectiveParam(value=value, origin="config")
    return values


def _finite(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Mapping):
        return all(_finite(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite(v) for v in value)
    return True


def _measurement_outcome(
    spec: CheckSpec, measurement: Measurement, params: Mapping[str, ParamValue]
) -> _Outcome:
    if measurement.state == "not_checkable":
        return _Outcome(measurement, Status.NOT_CHECKABLE, reason=measurement.reason)
    if measurement.state == "not_applicable":
        return _Outcome(measurement, Status.NOT_APPLICABLE, reason=measurement.reason)
    if not _finite(measurement.value):
        # A-61: a non-finite value is never compared; the finding is not_checkable and the value null
        return _Outcome(replace(measurement, value=None), Status.NOT_CHECKABLE, reason="value.non_finite")
    evaluation = spec.evaluate(measurement, params)
    status = Status.PASSED if evaluation.passed else Status.FAILED
    return _Outcome(measurement, status, threshold=evaluation.threshold, reason=measurement.reason)


def _evidence_outcome(rule: Rule, item: EvidenceItem | None, check: DocumentChecker) -> _Outcome:
    measurement = Measurement(check_id=EVIDENCE_CHECK, object="dataset")
    if item is None:
        return _Outcome(measurement, Status.EVIDENCE_OPEN, reason="evidence.missing")
    details = {"evidence": item.status.value}
    if item.status is EvidenceState.NOT_APPLICABLE:
        return _Outcome(measurement, Status.NOT_APPLICABLE, reason="evidence.not_applicable", details=details)
    if item.status in (EvidenceState.OPEN, EvidenceState.PARTIAL):
        return _Outcome(
            measurement, Status.EVIDENCE_OPEN, reason=f"evidence.{item.status.value}", details=details
        )
    if rule.verification is Verification.SEMI_AUTOMATIC:
        result = check(item)
        if result is not DocumentCheck.OK:
            return _Outcome(measurement, Status.FAILED, reason=f"evidence.{result.value}", details=details)
    return _Outcome(measurement, Status.PASSED, details=details)


def _active_exceptions(
    entries: Sequence[ExceptionEntry], as_of: date
) -> tuple[list[ExceptionEntry], list[Notice]]:
    active: list[ExceptionEntry] = []
    notices: list[Notice] = []
    for entry in entries:
        if entry.valid_until is not None and entry.valid_until < as_of:
            notices.append(
                Notice(
                    level=Severity.WARNING,
                    message_key="notice.exception_expired",
                    params={"rule": entry.rule, "valid_until": entry.valid_until.isoformat()},
                )
            )
        else:
            active.append(entry)
    return active, notices


def _matching_exception(
    entries: Sequence[ExceptionEntry], rule_id: str, measurement: Measurement
) -> int | None:
    names = (measurement.object, *measurement.identity)
    for index, entry in enumerate(entries):
        if entry.rule != rule_id:
            continue
        pattern = entry.object
        if pattern is not None and not any(glob.match(pattern, name) for name in names):
            continue
        if entry.subkey is not None and entry.subkey != measurement.subkey:
            continue
        return index
    return None


def run(inp: EngineInput) -> EngineResult:
    validate_against_registry(inp.packs, inp.registry)
    effective: dict[str, dict[str, EffectiveParam]] = {}
    for loaded in inp.packs:
        for rule in loaded.pack.rules:
            effective[rule.id] = resolve_params(
                inp.registry[rule.check], rule, inp.overrides.get(rule.id, {})
            )

    notices: list[Notice] = [
        Notice(level=Severity.INFO, message_key="notice.override_unused", params={"rule": rule_id})
        for rule_id in sorted(set(inp.overrides) - set(effective))
    ]
    active, expired_notices = _active_exceptions(inp.exceptions, inp.as_of)
    notices.extend(expired_notices)
    used = [False] * len(active)

    findings: list[Finding] = []
    stable_object: dict[
        int, str
    ] = {}  # id(finding) -> identity[0]: the order must not depend on --show-paths
    passed: Counter[tuple[str, str]] = Counter()
    for loaded in inp.packs:
        pack = loaded.pack
        for rule in pack.rules:
            spec = inp.registry[rule.check]
            params = {name: p.value for name, p in effective[rule.id].items()}
            if rule.check == EVIDENCE_CHECK:
                outcomes = [_evidence_outcome(rule, inp.evidence.get(rule.id), inp.document_check)]
            else:
                outcomes = [
                    _measurement_outcome(spec, m, params) for m in inp.measurements.get(rule.check, ())
                ]
            for outcome in outcomes:
                m = outcome.measurement
                status = outcome.status
                details = {**m.details, **outcome.details}
                if status in COUNTED:
                    hit = _matching_exception(active, rule.id, m)
                    if hit is not None:
                        used[hit] = True
                        status = Status.EXCEPTED
                        details["exception_reason"] = active[hit].reason
                if status is Status.PASSED:
                    passed[(rule.id, m.object)] += 1
                    continue
                stable = m.identity[0] if m.identity else m.object
                findings.append(
                    Finding(
                        key=finding_key(rule.id, stable, m.subkey),
                        rule_id=rule.id,
                        rulepack=pack.rulepack,
                        rulepack_version=pack.version,
                        source_status=pack.source_status,
                        clause=rule.clause,
                        phase=rule.phase,
                        severity=rule.effective_severity(inp.strict),
                        status=status,
                        object=m.object,
                        subkey=m.subkey,
                        file=m.file,
                        channel=m.channel,
                        measured_value=m.value,
                        threshold=outcome.threshold,
                        params=dict(effective[rule.id]),
                        time_ranges=list(m.time_ranges),
                        time_ranges_total=m.time_ranges_total,
                        time_ranges_duration_s=m.time_ranges_duration_s,
                        details=details,
                        message_key=f"check.{rule.check}",
                        reason=outcome.reason,
                    )
                )
                stable_object[id(findings[-1])] = stable

    for index, entry in enumerate(active):
        if not used[index]:
            notices.append(
                Notice(
                    level=Severity.INFO, message_key="notice.exception_unused", params={"rule": entry.rule}
                )
            )
    uses = [
        ExceptionUse(entry=entry, used=False, expired=True)
        for entry in inp.exceptions
        if entry.valid_until is not None and entry.valid_until < inp.as_of
    ] + [ExceptionUse(entry=entry, used=used[i], expired=False) for i, entry in enumerate(active)]

    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.rule_id, stable_object[id(f)], f.subkey or ""))
    passed_list = [PassedCount(rule_id=r, object=o, count=c) for (r, o), c in sorted(passed.items())]
    phases = _phase_summary(inp.packs, findings)
    exit_code = 1 if any(summary.errors for summary in phases.values()) else 0
    return EngineResult(
        findings=findings,
        passed=passed_list,
        phases=phases,
        coverage=_coverage(inp.packs),
        exit_code=exit_code,
        effective_params=effective,
        exceptions=uses,
        notices=notices,
    )


def _counts(finding: Finding) -> bool:
    return finding.source_status is not SourceStatus.PLACEHOLDER and finding.status in COUNTED


def _phase_summary(packs: Sequence[LoadedRulepack], findings: Sequence[Finding]) -> dict[Phase, PhaseSummary]:
    phases_with_rules = {
        rule.phase
        for loaded in packs
        if loaded.pack.source_status is not SourceStatus.PLACEHOLDER
        for rule in loaded.pack.rules
    }
    result: dict[Phase, PhaseSummary] = {}
    for phase in Phase:
        relevant = [f for f in findings if f.phase is phase and _counts(f)]
        errors = sum(1 for f in relevant if f.severity is Severity.ERROR)
        warnings = sum(1 for f in relevant if f.severity is Severity.WARNING)
        open_evidence = sum(1 for f in relevant if f.status is Status.EVIDENCE_OPEN)
        if phase not in phases_with_rules:
            light = Light.GREY
        elif errors:
            light = Light.RED
        elif warnings:
            light = Light.YELLOW
        else:
            light = Light.GREEN
        result[phase] = PhaseSummary(
            light=light, errors=errors, warnings=warnings, open_evidence=open_evidence
        )
    return result


def _coverage(packs: Sequence[LoadedRulepack]) -> dict[str, float | str]:
    """Share of must-clauses (clauses with an error rule) checked automatically or semi-automatically."""
    coverage: dict[str, float | str] = {}
    for loaded in packs:
        pack = loaded.pack
        if not pack.norm or pack.source_status not in (SourceStatus.INVENTORY, SourceStatus.FINAL):
            coverage[pack.rulepack] = "n/a"
            continue
        must = {r.clause for r in pack.rules if r.severity is Severity.ERROR}
        covered = {
            r.clause
            for r in pack.rules
            if r.severity is Severity.ERROR and r.verification is not Verification.MANUAL
        }
        coverage[pack.rulepack] = round(len(covered) / len(must), 4) if must else "n/a"
    return coverage
