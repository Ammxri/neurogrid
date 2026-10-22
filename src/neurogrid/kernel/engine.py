"""Rule engine: measurements × rules → findings (ARC-02, A-09, A-12–A-16, A-41, A-83).

Checks only measure; this module alone decides passed/failed, applies thresholds, exceptions and
evidence, and derives the per-phase traffic light, the coverage measure and the exit code.

Evidence (A-15): a rule with the check ``evidence.document`` is evaluated from its evidence.yaml entry. No
entry, ``open`` and ``partial`` give evidence_open, counted with the rule's severity; ``not_applicable``
(justified) gives not_applicable; ``provided`` passes. A semi-automatic rule passes only if its document
exists, is no link and its recorded hash matches; otherwise it fails with the reason
``evidence.<document check>``. A manual rule that is ``provided`` stays passed whatever the document check
finds (the user's statement, not assessed by NeuroGrid) and gets a warning notice instead. Every referenced
document is checked and its SHA-256 reported.

Traffic light (A-16, C6): red/yellow for a counted error/warning (failed or evidence_open), else green; grey
when no rule of a non-placeholder pack produced an evaluated outcome in the phase (passed, failed, excepted,
evidence_open, or any outcome of an evidence rule).
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
    DocumentResult,
    EvidenceItem,
    EvidenceRecord,
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
# Outcomes that show a phase was evaluated (C6); not_applicable and not_checkable alone leave it grey.
EVALUATED = (Status.PASSED, Status.FAILED, Status.EXCEPTED, Status.EVIDENCE_OPEN)


class ExceptionEntry(BaseModel):
    """A justified exception from neurogrid.toml (NG-F18, A-14).

    ``object`` is a pattern over relative POSIX paths; pseudonymous recording IDs match as well. ``subkey``
    must equal the finding's subkey (e.g. a validator code, a field or a channel). Exceptions are per rule ID:
    the same defect reported by two packs (A-40) needs one entry per rule. In results.json ``rule`` may be any
    text, as results of earlier versions hold it (C1); neurogrid.toml must name a rule ID (A-83, checked when
    the file is read).
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
    evidence: list[EvidenceRecord] = field(default_factory=list)  # one per rule with check evidence.document


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


def _evidence_outcome(
    rule: Rule, item: EvidenceItem | None, check: DocumentChecker
) -> tuple[_Outcome, DocumentResult | None]:
    """The outcome of an evidence rule and the check of its document (None without a document)."""
    measurement = Measurement(check_id=EVIDENCE_CHECK, object="dataset")
    if item is None:
        return _Outcome(measurement, Status.EVIDENCE_OPEN, reason="evidence.missing"), None
    document = check(item) if item.document is not None else None
    details: dict[str, Any] = {"evidence": item.status.value}
    if document is not None:
        details["document_check"] = document.check.value
    if item.status is EvidenceState.NOT_APPLICABLE:
        outcome = _Outcome(
            measurement, Status.NOT_APPLICABLE, reason="evidence.not_applicable", details=details
        )
        return outcome, document
    if item.status in (EvidenceState.OPEN, EvidenceState.PARTIAL):
        outcome = _Outcome(
            measurement, Status.EVIDENCE_OPEN, reason=f"evidence.{item.status.value}", details=details
        )
        return outcome, document
    if rule.verification is Verification.SEMI_AUTOMATIC:
        result = document.check if document is not None else DocumentCheck.NO_DOCUMENT
        if result is not DocumentCheck.OK:
            outcome = _Outcome(measurement, Status.FAILED, reason=f"evidence.{result.value}", details=details)
            return outcome, document
    return _Outcome(measurement, Status.PASSED, details=details), document


def _evidence_notices(
    rule: Rule, item: EvidenceItem | None, document: DocumentResult | None, as_of: date
) -> list[Notice]:
    """A manual rule 'provided' whose document is missing, a link or changed stays passed and gets a warning;
    a review date after the reference date gets a note (A-83)."""
    notices: list[Notice] = []
    if item is None:
        return notices
    if (
        item.status is EvidenceState.PROVIDED
        and rule.verification is not Verification.SEMI_AUTOMATIC
        and document is not None
        and document.check is not DocumentCheck.OK
    ):
        notices.append(
            Notice(
                level=Severity.WARNING,
                message_key=f"notice.evidence_document.{document.check.value}",
                params={"rule": rule.id},
            )
        )
    if item.date is not None and item.date > as_of:
        notices.append(
            Notice(
                level=Severity.INFO,
                message_key="notice.evidence_date_after_as_of",
                params={"rule": rule.id, "date": item.date.isoformat(), "as_of": as_of.isoformat()},
            )
        )
    return notices


def _evidence_record(
    pack_name: str,
    rule: Rule,
    item: EvidenceItem | None,
    document: DocumentResult | None,
    outcome: Status,
    severity: Severity,
) -> EvidenceRecord:
    """``severity`` is the effective severity of the run (strict_severity under --strict), as in the rule's
    findings and results rules[] (A-82)."""
    return EvidenceRecord(
        rule_id=rule.id,
        rulepack=pack_name,
        phase=rule.phase,
        severity=severity,
        verification=rule.verification,
        status=item.status if item is not None else None,
        outcome=outcome,
        document=item.document if item is not None else None,
        document_check=document.check if document is not None else None,
        sha256=document.sha256 if document is not None else None,
        sha256_recorded=item.sha256 if item is not None else None,
        reviewer=item.reviewer if item is not None else None,
        date=item.date if item is not None else None,
        comment=item.comment if item is not None else None,
        justification=item.justification if item is not None else None,
    )


def _unmatched_evidence(inp: EngineInput) -> list[Notice]:
    """Entries for rules that are not loaded (info) or that NeuroGrid measures itself (warning, ignored)."""
    checks = {rule.id: rule.check for loaded in inp.packs for rule in loaded.pack.rules}
    notices: list[Notice] = []
    for rule_id in sorted(inp.evidence):
        if rule_id not in checks:
            notices.append(
                Notice(level=Severity.INFO, message_key="notice.evidence_unused", params={"rule": rule_id})
            )
        elif checks[rule_id] != EVIDENCE_CHECK:
            notices.append(
                Notice(
                    level=Severity.WARNING, message_key="notice.evidence_ignored", params={"rule": rule_id}
                )
            )
    return notices


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


def _matching_exceptions(
    entries: Sequence[ExceptionEntry], candidates: Sequence[int], measurement: Measurement
) -> list[int]:
    """Indices of every entry (among the rule's ``candidates``) that matches: the object pattern against the
    displayed ID and every stable name (A-68), the subkey exactly. All of them count as used; the first one's
    reason is recorded."""
    names = (measurement.object, *measurement.identity)
    hits = []
    for index in candidates:
        entry = entries[index]
        pattern = entry.object
        if pattern is not None and not any(glob.match(pattern, name) for name in names):
            continue
        if entry.subkey is not None and entry.subkey != measurement.subkey:
            continue
        hits.append(index)
    return hits


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
    by_rule: dict[str, list[int]] = {}
    for index, entry in enumerate(active):
        by_rule.setdefault(entry.rule, []).append(index)
    evaluated: set[Phase] = set()
    records: list[EvidenceRecord] = []
    evidence_notices: list[Notice] = []

    findings: list[Finding] = []
    stable_object: dict[
        int, str
    ] = {}  # id(finding) -> identity[0]: the order must not depend on --show-paths
    passed: Counter[tuple[str, str]] = Counter()
    for loaded in inp.packs:
        pack = loaded.pack
        for rule in pack.rules:
            spec = inp.registry[rule.check]
            severity = rule.effective_severity(inp.strict)
            params = {name: p.value for name, p in effective[rule.id].items()}
            is_evidence = rule.check == EVIDENCE_CHECK
            item = inp.evidence.get(rule.id) if is_evidence else None
            document: DocumentResult | None = None
            if is_evidence:
                evidence_outcome, document = _evidence_outcome(rule, item, inp.document_check)
                outcomes = [evidence_outcome]
                evidence_notices.extend(_evidence_notices(rule, item, document, inp.as_of))
            else:
                outcomes = [
                    _measurement_outcome(spec, m, params) for m in inp.measurements.get(rule.check, ())
                ]
            for outcome in outcomes:
                m = outcome.measurement
                status = outcome.status
                details = {**m.details, **outcome.details}
                if status in COUNTED:
                    hits = _matching_exceptions(active, by_rule.get(rule.id, ()), m)
                    if hits:
                        for hit in hits:
                            used[hit] = True
                        status = Status.EXCEPTED
                        details["exception_reason"] = active[hits[0]].reason
                if pack.source_status is not SourceStatus.PLACEHOLDER and (
                    status in EVALUATED or is_evidence
                ):
                    evaluated.add(rule.phase)
                if is_evidence:
                    records.append(_evidence_record(pack.rulepack, rule, item, document, status, severity))
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
                        severity=severity,
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

    notices.extend(evidence_notices)
    notices.extend(_unmatched_evidence(inp))
    for index, entry in enumerate(active):
        if used[index]:
            continue
        if entry.rule not in effective:  # not a rule of any loaded pack: probably a typo (A-14)
            notices.append(
                Notice(
                    level=Severity.WARNING,
                    message_key="notice.exception_unknown_rule",
                    params={"rule": entry.rule},
                )
            )
        else:
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
    phases = _phase_summary(findings, evaluated)
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
        evidence=records,
    )


def _counts(finding: Finding) -> bool:
    return finding.source_status is not SourceStatus.PLACEHOLDER and finding.status in COUNTED


def _phase_summary(findings: Sequence[Finding], evaluated: set[Phase]) -> dict[Phase, PhaseSummary]:
    """Per phase: counted errors and warnings (open evidence included, A-16), the open evidence of error and
    warning rules as a breakdown of them (an info rule's open evidence is listed as a finding, never counted),
    and the light. Severities are the effective ones of the run (strict_severity, A-82). ``evaluated`` holds
    the phases in which a non-placeholder rule had an evaluated outcome."""
    result: dict[Phase, PhaseSummary] = {}
    for phase in Phase:
        relevant = [f for f in findings if f.phase is phase and _counts(f)]
        errors = sum(1 for f in relevant if f.severity is Severity.ERROR)
        warnings = sum(1 for f in relevant if f.severity is Severity.WARNING)
        open_evidence = sum(
            1
            for f in relevant
            if f.status is Status.EVIDENCE_OPEN and f.severity in (Severity.ERROR, Severity.WARNING)
        )
        if phase not in evaluated:
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
