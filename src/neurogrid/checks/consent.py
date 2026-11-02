"""M14 consent scope (NV-F02, PRD §12 M14; A-30, A-51, A-91; CORE-M14-01 ``consent.covered``): whether the use
of each signal recording is covered by the effective consent of its subject at the reference date.

A recording needs the uses of its splits (``[consent] split_use``, default train → training, val and test →
validation, each split replaced only by its own key) and every ``[consent] dataset_uses`` use (in a split or
not). Splits, subjects and signal recordings come from checks.ai_dataset.structure, as for M12: subjects are
the BIDS ``sub`` labels or the subject labels of the mapping (A-05); annotation-only files need no consent
(C10). The records come from ``<vault>/consents.yaml`` (vault.consents.load_for_check, read before the signal
pass); M14 never reads the access log, so the run's own access event changes nothing (two runs byte-equal).

Order of the outcomes (p6 decisions 6):
1. a single file as target: one dataset-level not_applicable (``consent.single_file``, A-66);
2. no recording needs a use (no split and no dataset_uses): one dataset-level not_applicable
   (``consent.no_uses``), also without a vault and under --strict: there is nothing to cover;
3. no consent data (no vault, no consents.yaml, or ``consents: []``): one dataset-level measurement without a
   value (``consent.no_vault``, ``consent.no_consents``);
4. a recording with uses whose subject is unknown (a raw folder without mapping): one measurement without a
   value per recording (``consent.subject_unknown``);
5. otherwise one measurement per subject and needed use (ConsentUse order): covered or not, with the reason
   ``consent.missing`` (no record), ``consent.not_yet_valid`` (only records dated after the reference date),
   ``consent.withdrawn`` or ``consent.use_not_permitted``. The object is ``sub-<label>`` and the subkey the
   use, so an exception names ``sub-07`` and ``training``.

The evaluator decides (ARC-02, no kernel change): a measurement without a value is not checkable (grey, not
counted), unless the run requires consent (``details.required``: --strict or [check] strict, or a configured
[consent] section) – then it fails with its reason. Once consent data exist, a missing, withdrawn, not yet
valid or not permitted consent fails (error) with or without [consent] (A-30 read as "consent data present",
A-91). M14 does not use strict_severity: its severity is always error, strict and [consent] change only the
status of a measurement without a value.

Details (A-51, D-17 option B): the use, the splits that need it, whether dataset_uses needs it, the
effective consent version and up to 20 recording IDs; never dates, ethics references or the permitted uses.
These per-subject findings stay in results.json; the report shows M14 only aggregated per use and reason
(report/render.py).

Re-consent (NV-F06; A-30, A-95; CORE-M14-02 ``consent.reconsent``): the risks of ``<vault>/risks.yaml``
(vault.risks.load_for_check, read before the signal pass) dated on or before the reference date, in ID order.
Outcomes in this order:
1. a single file as target: one dataset-level not_applicable (``consent.single_file``);
2. no risk register, or no risk dated on or before the reference date: one dataset-level not_applicable
   (``reconsent.no_risks``);
3. no consent data: one dataset-level not checkable (``consent.no_vault``, ``consent.no_consents``), never
   failed: neither --strict nor [consent] changes it, re-consent is a hint for the ethics committee (A-30);
4. otherwise, per risk, the subjects with a known label whose signal recordings need a use the risk affects
   (the uses of M14-01) and whose effective consent at the reference date is valid: one measurement each
   (object ``sub-<label>``, subkey the risk ID), passed when the consent version reaches the risk's
   ``min_consent_version``, else failed with ``reconsent.version_below``. A subject without a valid consent
   or with an unknown label is left to CORE-M14-01. A risk without such a subject: one dataset-level
   measurement with the risk ID as subkey, passed.
Details: the risk ID, the affected uses the subject's recordings need, the consent version, the risk's
min_consent_version and up to 20 recording IDs; never the risk description (A-51). These findings are the
re-consent list (PRD: the subjects who may need a new consent) and stay in results.json; the report shows
them only as counts per risk (D-17 option B for CORE-M14-02, owner answer 4 of P9).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from neurogrid.checks import ai_dataset
from neurogrid.checks.context import CheckContext, RecordingState
from neurogrid.io.participants import SPLIT_NAMES
from neurogrid.kernel.findings import Notice, Severity
from neurogrid.kernel.rules import CheckSpec, Evaluation, Measurement, ParamValue
from neurogrid.model.consent import ConsentState, ConsentUse, EffectiveConsent, effective, ordered_uses
from neurogrid.model.results import ConsentSummary, ReconsentRisk, ReconsentSummary
from neurogrid.model.risks import Risk
from neurogrid.vault.consents import identifying_refs

COVERED = "consent.covered"
RECONSENT = "consent.reconsent"
CHECKS = frozenset({COVERED, RECONSENT})
MAX_LISTED = ai_dataset.MAX_LISTED  # recording IDs per finding (A-59); the total is given
# The reasons of CORE-M14-02 of its own; it shares consent.single_file, .no_vault and .no_consents of REASONS
RECONSENT_REASONS = ("reconsent.no_risks", "reconsent.version_below")
# Every reason and notice key of this module (some are passed through variables), for the language tables.
REASONS = (
    "consent.single_file",
    "consent.no_uses",
    "consent.no_vault",
    "consent.no_consents",
    "consent.subject_unknown",
    "consent.missing",
    "consent.not_yet_valid",
    "consent.withdrawn",
    "consent.use_not_permitted",
)
NOTICES = (
    "notice.consent_future_versions",
    "notice.consents_without_recording",
    "notice.consent_refs_look_identifying",
    "notice.consents_outside_dataset",
    "notice.risks_future",
)
_NOT_COVERED: dict[ConsentState, str] = {
    "none": "consent.missing",
    "future_only": "consent.not_yet_valid",
    "withdrawn": "consent.withdrawn",
    "valid": "consent.use_not_permitted",
}


def _as_of(ctx: CheckContext) -> date:
    return ctx.as_of or date.today()  # the pipeline always sets the reference date


def needed_uses(ctx: CheckContext, member: ai_dataset.Member) -> tuple[ConsentUse, ...]:
    """The uses a signal recording needs: those of its splits and the dataset_uses, in ConsentUse order."""
    section = ctx.config.consent
    by_split = section.effective_split_use()
    uses = [use for split in member.splits for use in by_split.get(split, ())]
    return ordered_uses([*uses, *section.dataset_uses])


def _dataset(**kwargs: Any) -> Measurement:
    return Measurement(check_id=COVERED, object=ai_dataset.DATASET, **kwargs)


def _on_recording(rec: RecordingState, **kwargs: Any) -> Measurement:
    """A measurement on a recording: displayed ID, file and stable names, as ai_dataset's."""
    return Measurement(check_id=COVERED, object=rec.object_id, file=rec.file, identity=rec.identity, **kwargs)


def _on_subject(label: str, check_id: str = COVERED, **kwargs: Any) -> Measurement:
    """A measurement on a subject ``sub-<label>``, which is also its stable name (A-68), as ai_dataset's."""
    name = f"sub-{label}"
    return Measurement(check_id=check_id, object=name, identity=(name,), **kwargs)


def _no_data_reason(ctx: CheckContext) -> str | None:
    """The reason when there are no consent data (A-30: no vault, no consents.yaml, ``consents: []``), else
    None."""
    consents = ctx.consents
    if consents is not None and consents.has_data:
        return None
    return "consent.no_vault" if consents is None or consents.state == "no_vault" else "consent.no_consents"


def _no_data(ctx: CheckContext) -> Measurement | None:
    """The dataset-level measurement without a value when there are no consent data (A-30), else None."""
    reason = _no_data_reason(ctx)
    if reason is None:
        return None
    return _dataset(value=None, reason=reason, details={"required": ctx.consent_required})


def _needing(ctx: CheckContext) -> list[tuple[ai_dataset.Member, tuple[ConsentUse, ...]]]:
    """The signal recordings that need a use, with their uses, in the order of their stable names."""
    needing = [(member, needed_uses(ctx, member)) for member in ai_dataset.structure(ctx).members]
    return sorted(((m, uses) for m, uses in needing if uses), key=lambda item: item[0].rec.identity[0])


def measure_covered(ctx: CheckContext) -> list[Measurement]:
    if ctx.scan.single_file:
        return [_dataset(state="not_applicable", reason="consent.single_file")]
    needing = _needing(ctx)
    if not needing:
        return [_dataset(state="not_applicable", reason="consent.no_uses")]
    missing = _no_data(ctx)
    if missing is not None:
        return [missing]
    assert ctx.consents is not None and ctx.consents.file is not None
    out = [
        _on_recording(
            member.rec,
            reason="consent.subject_unknown",
            details={"required": ctx.consent_required, "uses": [use.value for use in uses]},
        )
        for member, uses in needing
        if member.subject is None
    ]
    records = ctx.consents.file.by_subject()
    section = ctx.config.consent
    by_split = section.effective_split_use()
    subjects: dict[str, list[tuple[ai_dataset.Member, tuple[ConsentUse, ...]]]] = {}
    for member, uses in needing:
        if member.subject is not None:
            subjects.setdefault(member.subject, []).append((member, uses))
    as_of = _as_of(ctx)
    for label, items in sorted(subjects.items()):
        consent = effective(records.get(f"sub-{label}", ()), as_of)
        splits = {split for member, _uses in items for split in member.splits}
        for use in ordered_uses(use for _member, uses in items for use in uses):
            recordings = [member.rec.object_id for member, uses in items if use in uses]
            details = {
                "use": use.value,
                "splits": [split for split in SPLIT_NAMES if split in splits and use in by_split[split]],
                "dataset_uses": use in section.dataset_uses,
                "consent_version": consent.version,
                "recordings": recordings[:MAX_LISTED],
                "recordings_total": len(recordings),
            }
            covered = consent.covers(use)
            reason = None if covered else _NOT_COVERED[consent.state]
            out.append(_on_subject(label, subkey=use.value, value=covered, reason=reason, details=details))
    return out


def _covered(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
    """No value (no consent data, unknown subject): not checkable, or failed when the run requires consent
    (details.required); otherwise passed exactly when covered."""
    if measurement.value is None:
        if measurement.details.get("required") is True:
            return Evaluation(passed=False)
        return Evaluation(passed=False, not_checkable=measurement.reason or "consent.no_vault")
    return Evaluation(passed=measurement.value is True)


# --- CORE-M14-02 re-consent (NV-F06; A-30, A-95) ---------------------------------------------------------


def _reconsent_dataset(**kwargs: Any) -> Measurement:
    return Measurement(check_id=RECONSENT, object=ai_dataset.DATASET, **kwargs)


def _judged(ctx: CheckContext) -> list[Risk]:
    """The risks judged at the reference date, in ID order (none when risks.yaml was not read)."""
    return ctx.risks.judged(_as_of(ctx)) if ctx.risks is not None else []


@dataclass(frozen=True)
class _Affected:
    """A subject with a known label whose signal recordings need a use the risk affects: those recordings
    with the affected uses each needs, and the subject's effective consent at the reference date."""

    label: str
    items: list[tuple[ai_dataset.Member, tuple[ConsentUse, ...]]]
    consent: EffectiveConsent


def _affected(ctx: CheckContext, risks: list[Risk]) -> list[tuple[Risk, list[_Affected]]]:
    """Per judged risk its affected subjects in label order. Only once there are consent data: without them
    no subject is judged (step 3 of the module docstring). The recordings are grouped by subject and each
    subject's effective consent is taken once, whatever the number of risks."""
    assert ctx.consents is not None and ctx.consents.file is not None
    records = ctx.consents.file.by_subject()
    as_of = _as_of(ctx)
    grouped: dict[str, list[tuple[ai_dataset.Member, tuple[ConsentUse, ...]]]] = {}
    for member, needed in _needing(ctx):
        if member.subject is not None:  # an unknown subject is left to CORE-M14-01
            grouped.setdefault(member.subject, []).append((member, needed))
    subjects = [
        (
            label,
            items,
            {use for _member, needed in items for use in needed},
            effective(records.get(f"sub-{label}", ()), as_of),
        )
        for label, items in sorted(grouped.items())
    ]
    out = []
    for risk in risks:
        uses = set(risk.affected_uses)
        affected = []
        for label, items, needed_uses, consent in subjects:
            if needed_uses & uses:
                hits = [(member, tuple(use for use in needed if use in uses)) for member, needed in items]
                affected.append(_Affected(label, [(member, hit) for member, hit in hits if hit], consent))
        out.append((risk, affected))
    return out


def _judgeable(ctx: CheckContext) -> list[Risk] | Measurement:
    """The judged risks, or the dataset-level measurement of steps 1-3 of the module docstring."""
    if ctx.scan.single_file:
        return _reconsent_dataset(state="not_applicable", reason="consent.single_file")
    risks = _judged(ctx)
    if not risks:
        return _reconsent_dataset(state="not_applicable", reason="reconsent.no_risks")
    reason = _no_data_reason(ctx)
    if reason is not None:  # never failed: no --strict and no [consent] effect (A-95)
        return _reconsent_dataset(state="not_checkable", reason=reason)
    return risks


def measure_reconsent(ctx: CheckContext) -> list[Measurement]:
    judgeable = _judgeable(ctx)
    if isinstance(judgeable, Measurement):
        return [judgeable]
    out = []
    for risk, affected in _affected(ctx, judgeable):
        candidates = [subject for subject in affected if subject.consent.state == "valid"]
        for subject in candidates:  # without a valid consent: left to CORE-M14-01
            version = subject.consent.version
            assert version is not None  # a valid consent has the version of its record
            recordings = [member.rec.object_id for member, _uses in subject.items]
            details = {
                "risk": risk.id,
                "affected_uses": [
                    use.value for use in ordered_uses(u for _m, uses in subject.items for u in uses)
                ],
                "consent_version": version,
                "min_consent_version": risk.min_consent_version,
                "recordings": recordings[:MAX_LISTED],
                "recordings_total": len(recordings),
            }
            reached = version >= risk.min_consent_version
            out.append(
                _on_subject(
                    subject.label,
                    RECONSENT,
                    subkey=risk.id,
                    value=reached,
                    reason=None if reached else "reconsent.version_below",
                    details=details,
                )
            )
        if not candidates:  # no subject to ask: the risk passes for the dataset
            out.append(_reconsent_dataset(subkey=risk.id, value=True, details={"risk": risk.id}))
    return out


def _reconsent(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
    """Passed exactly when the consent version reaches the risk's min_consent_version (the measured value);
    the states of steps 1-3 never reach the evaluator."""
    return Evaluation(passed=measurement.value is True)


SPECS = (CheckSpec(id=COVERED, evaluate=_covered), CheckSpec(id=RECONSENT, evaluate=_reconsent))
MEASURERS = {COVERED: measure_covered, RECONSENT: measure_reconsent}


def summary(ctx: CheckContext, check_ids: Iterable[str]) -> ConsentSummary | None:
    """results.consent (A-81, A-91): per use, how many subjects need it, the sums of the per-use tables the
    report shows. results.passed counts a subject's passed uses without naming them, so without these sums
    the report could not tell the passed subjects of a use, nor withhold a table whose passed cell has 1-4
    subjects. Only when M14 measured per subject (step 5 of the module docstring reached for a subject);
    counts only, in ConsentUse order."""
    if COVERED not in set(check_ids) or ctx.scan.single_file or _no_data(ctx) is not None:
        return None
    subjects: dict[ConsentUse, set[str]] = {}
    for member, uses in _needing(ctx):
        if member.subject is not None:
            for use in uses:
                subjects.setdefault(use, set()).add(member.subject)
    if not subjects:
        return None
    return ConsentSummary(subjects={use.value: len(subjects[use]) for use in ordered_uses(subjects)})


def reconsent_summary(ctx: CheckContext, check_ids: Iterable[str]) -> ReconsentSummary | None:
    """results.reconsent (A-95): per judged risk its ID, date and affected uses, the subjects whose signal
    recordings need an affected use and the candidates among them (valid consent), the sums of the report's
    re-consent tables. Only when CORE-M14-02 judged risks per subject (step 4 of the module docstring);
    counts only, never a description."""
    if RECONSENT not in set(check_ids):
        return None
    judgeable = _judgeable(ctx)
    if isinstance(judgeable, Measurement):
        return None
    risks = [
        ReconsentRisk(
            id=risk.id,
            date=risk.date,
            affected_uses=[use.value for use in risk.affected_uses],
            subjects=len(affected),
            candidates=sum(1 for subject in affected if subject.consent.state == "valid"),
        )
        for risk, affected in _affected(ctx, judgeable)
    ]
    return ReconsentSummary(risks=risks)


def notices(ctx: CheckContext, check_ids: Iterable[str]) -> list[Notice]:
    """The notes of M14 (counts only, A-51): those of the consent records and of the risk register."""
    ids = set(check_ids)
    return _record_notices(ctx, ids) + _risk_notices(ctx, ids)


def _risk_notices(ctx: CheckContext, check_ids: set[str]) -> list[Notice]:
    """Risks dated after the reference date, only when CORE-M14-02 is loaded: they are judged from their date
    on (notice.risks_future, the number only)."""
    if RECONSENT not in check_ids or ctx.risks is None:
        return []
    count = ctx.risks.future(_as_of(ctx))
    if not count:
        return []
    return [Notice(level=Severity.INFO, message_key="notice.risks_future", params={"count": count})]


def _record_notices(ctx: CheckContext, check_ids: set[str]) -> list[Notice]:
    """Notes about the consent records, only when M14 is loaded and records were read (counts only, A-51):
    records of dataset subjects dated after the reference date, subjects of the file without a signal
    recording, ethics references that read like personal data, and a vault outside the dataset (a manifest
    of the dataset does not cover consents.yaml)."""
    consents = ctx.consents
    if COVERED not in check_ids or consents is None or consents.file is None:
        return []
    out: list[Notice] = []
    if consents.outside_dataset:
        out.append(Notice(level=Severity.INFO, message_key="notice.consents_outside_dataset"))
    records = consents.file.consents
    known = {f"sub-{m.subject}" for m in ai_dataset.structure(ctx).members if m.subject is not None}
    as_of = _as_of(ctx)
    future = sum(1 for entry in records if entry.subject in known and entry.date > as_of)
    if future:
        params: dict[str, ParamValue] = {"count": future, "as_of": as_of.isoformat()}
        out.append(Notice(level=Severity.INFO, message_key="notice.consent_future_versions", params=params))
    unmatched = len({entry.subject for entry in records} - known)
    if unmatched:
        out.append(
            Notice(
                level=Severity.INFO,
                message_key="notice.consents_without_recording",
                params={"count": unmatched},
            )
        )
    identifying = identifying_refs(consents.file)
    if identifying:
        out.append(
            Notice(
                level=Severity.INFO,
                message_key="notice.consent_refs_look_identifying",
                params={"count": identifying},
            )
        )
    return out
