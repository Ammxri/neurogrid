"""M11 classes and demography, M12 split integrity and duplicates (NG-F09, PRD §12 M11/M12; A-04, A-21, A-51,
A-81; decisions C1, C2, C5, C10, C11). TECH-01 names this module checks/ai_dataset.py.

Dataset-wide checks over the signal recordings; annotation-only files (hypnograms) are no recordings here
(C10). Subjects are the BIDS ``sub`` labels of the file names, in raw folders the subject labels of the
mapping (A-05); without them a subject is unknown. A subject is shown as ``sub-<label>`` in both kinds of
dataset and that is also its identity, so keys and exceptions do not depend on --show-paths (A-68).

- CORE-M11-01 ``ai.class_balance``: class shares per scope (all recordings, then train, val, test as far as
  present) and class; ``min_share`` 0.05 (PRD, not calibrated, A-20). Label source ``[ai] labels``:
  ``events:<column>`` counts the event rows of the BIDS events.tsv files, ``participants:<column>`` counts
  subjects. Unset: one dataset-level not_applicable (A-81). A class missing from a split has share 0.
- CORE-M11-02 ``ai.demographics_complete``: age and sex of every subject in participants.tsv at the dataset
  root (also for raw folders); one measurement per subject and value. Format headers are no source (A-51,
  A-64: the EDF patient field is never read).
- CORE-M12-01 ``ai.split_integrity``: a subject in more than one split is an error in every combination
  (A-21). Splits come from splits.tsv (control file, C2) or a ``split`` column in participants.tsv; splits.tsv
  wins (info notice). Without splits: one dataset-level not_applicable (C11).
- CORE-M12-02 ``ai.duplicate_recordings``: recordings with the same signal hash NG-SIGHASH-v1 from the
  streaming pass (A-79) are duplicates; every member of a group fails (subkey = group number). Identical flat
  recordings are duplicates as well. Hashes never leave the process; results.json lists the groups as
  displayed recording IDs (KONZEPT 2.3).

Outputs (A-51): subject-level counts (participants label source, demography) of 1-4 are suppressed in
results.json, also as measured values of CORE-M11-01 (null with reason ``ai.small_cell``, applied after the
engine by :func:`suppress_small_cells`), with complementary suppression; event-level counts are shown. Free
text labels are shown only by the A-17 rule (C5). Raw ages and participants cell text are never output.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from neurogrid.checks.context import CheckContext, RecordingState
from neurogrid.config import AI_LABELS
from neurogrid.io.events import event_labels
from neurogrid.io.identifying import display_text
from neurogrid.io.participants import SPLIT_NAMES, ParticipantsTable, canonical, missing, read_participants
from neurogrid.io.splits import assign, locate, read_splits
from neurogrid.kernel.findings import Finding, Notice, Severity
from neurogrid.kernel.rules import (
    CheckSpec,
    Evaluation,
    Measurement,
    ParamSpec,
    ParamValue,
    at_least,
    is_true,
)
from neurogrid.model.dataset import Split
from neurogrid.model.results import AIDemographics, AILabels, AILabelScope, AISplits, AISummary

CLASS_BALANCE = "ai.class_balance"
DEMOGRAPHICS = "ai.demographics_complete"
SPLIT_INTEGRITY = "ai.split_integrity"
DUPLICATES = "ai.duplicate_recordings"
STRUCTURE_CHECKS = frozenset({CLASS_BALANCE, DEMOGRAPHICS, SPLIT_INTEGRITY})  # participants.tsv, splits
STREAM_CHECKS = frozenset({DUPLICATES})  # needs the signal hash of the streaming pass (KONZEPT 1.4)
CHECKS = STRUCTURE_CHECKS | STREAM_CHECKS
SCOPE_ALL = "all"
SMALL_CELL = 5  # A-51: subject-level counts below this are not output
MAX_LISTED = 20  # recording IDs per detail list (A-59); the total is given
DATASET = "dataset"
DEMOGRAPHIC_ITEMS = ("age", "sex")
# Every reason and notice key of this module (some are passed through variables), for the language tables.
REASONS = (
    "ai.labels_not_configured",
    "ai.labels_need_bids",
    "ai.label_column_missing",
    "ai.no_label_values",
    "ai.subjects_unknown",
    "ai.subject_unknown",
    "ai.no_participants_table",
    "ai.participants_unusable",
    "ai.not_in_participants",
    "ai.column_missing",
    "ai.value_missing",
    "ai.age_unparseable",
    "ai.no_splits",
    "ai.hash_unavailable",
    "ai.small_cell",
)
NOTICES = (
    "notice.splits_both_sources",
    "notice.splits_unknown_rows",
    "notice.splits_unassigned",
    "notice.splits_outside_dataset",
    "notice.participants_split_invalid",
)
LabelSource = Literal["events", "participants"]
Unit = Literal["events", "subjects"]
SplitSource = Literal["splits.tsv", "participants.tsv"]
_VALUE_REASONS = {
    "no_column": "ai.column_missing",
    "missing": "ai.value_missing",
    "unparseable": "ai.age_unparseable",
}


@dataclass(frozen=True)
class Member:
    """A signal recording with its subject label (None: unknown) and its splits."""

    rec: RecordingState
    subject: str | None
    splits: frozenset[str]

    @property
    def key(self) -> str:
        return self.rec.found.relative.as_posix()


@dataclass(frozen=True)
class Labels:
    """Class counts of the configured label source. ``reason`` is set when nothing can be counted."""

    source: LabelSource
    column: str
    unit: Unit
    reason: str | None = None
    counts: Mapping[str, Counter[str]] = field(default_factory=dict)  # scope -> class key -> count
    shown: Mapping[str, str | None] = field(default_factory=dict)  # class key -> label (None: free text)
    chars: Mapping[str, int] = field(default_factory=dict)  # class key -> length of a free text label

    @property
    def classes(self) -> list[str]:
        return sorted(self.counts.get(SCOPE_ALL, {}))


@dataclass
class Structure:
    members: tuple[Member, ...]
    participants: ParticipantsTable | None
    split_source: SplitSource | None
    splits: tuple[Split, ...]  # DM-06, recording IDs as displayed
    labels: Labels | None  # None: [ai] labels not configured
    notices: list[Notice] = field(default_factory=list)

    @property
    def subjects_known(self) -> bool:
        return all(member.subject is not None for member in self.members)


# --- structure: participants, splits, labels (computed once per run) -------------------------------------


def structure(ctx: CheckContext) -> Structure:
    """The AI dataset structure of the run, built once. Reads the split control file: an invalid splits.tsv
    ends the run with exit 2 (C2), so the pipeline builds this before the signal pass."""
    cached = ctx.ai_structure
    if isinstance(cached, Structure):
        return cached
    built = _build(ctx)
    ctx.ai_structure = built
    return built


def _subject(rec: RecordingState) -> str | None:
    documented = rec.metadata.entities.get("subject")
    return str(documented.value) if documented is not None else None


def _scopes(members: Iterable[Member]) -> list[str]:
    present = {split for member in members for split in member.splits}
    return [SCOPE_ALL, *(split for split in SPLIT_NAMES if split in present)]


def _build(ctx: CheckContext) -> Structure:
    participants = read_participants(ctx.root)
    signal = [rec for rec in ctx.recordings if not rec.annotations_only]  # C10
    notices: list[Notice] = []
    table_splits = participants is not None and participants.usable and participants.has_split
    split_source: SplitSource | None = None
    by_recording: dict[str, set[str]] = {}
    split_file = locate(ctx.root, ctx.project_root, ctx.config.ai.splits)
    if split_file is not None:
        assigned, unknown = assign(read_splits(split_file.path), ctx.scan.recordings)
        by_recording, split_source = assigned, "splits.tsv"
        if split_file.outside_dataset:
            notices.append(Notice(level=Severity.INFO, message_key="notice.splits_outside_dataset"))
        if unknown:
            notices.append(
                Notice(
                    level=Severity.WARNING,
                    message_key="notice.splits_unknown_rows",
                    params={"count": unknown},
                )
            )
        if table_splits:
            notices.append(Notice(level=Severity.INFO, message_key="notice.splits_both_sources"))
    elif participants is not None and table_splits:
        split_source = "participants.tsv"
        invalid = sum(p.invalid_splits for p in participants.participants.values())
        if invalid:
            notices.append(
                Notice(
                    level=Severity.INFO,
                    message_key="notice.participants_split_invalid",
                    params={"count": invalid},
                )
            )
        for rec in signal:
            label = _subject(rec)
            participant = participants.participants.get(label) if label is not None else None
            if participant is not None and participant.splits:
                by_recording[rec.found.relative.as_posix()] = set(participant.splits)
    members = tuple(
        Member(rec, _subject(rec), frozenset(by_recording.get(rec.found.relative.as_posix(), ())))
        for rec in signal
    )
    splits: tuple[Split, ...] = ()
    if split_source is not None:
        unassigned = sum(1 for member in members if not member.splits)
        if unassigned:
            notices.append(
                Notice(
                    level=Severity.INFO, message_key="notice.splits_unassigned", params={"count": unassigned}
                )
            )
        ordered = sorted(members, key=lambda m: m.rec.identity[0])
        splits = tuple(
            Split(name=name, recording_ids=[m.rec.object_id for m in ordered if name in m.splits])
            for name in SPLIT_NAMES
            if any(name in m.splits for m in members)
        )
    return Structure(
        members=members,
        participants=participants,
        split_source=split_source,
        splits=splits,
        labels=_labels(ctx, members, participants),
        notices=notices,
    )


def _labels(
    ctx: CheckContext, members: Sequence[Member], participants: ParticipantsTable | None
) -> Labels | None:
    configured = ctx.config.ai.labels
    if configured is None:
        return None
    match = AI_LABELS.fullmatch(configured)  # validated when the configuration was read
    assert match is not None
    column = match.group("column")
    if match.group("source") == "events":
        return _event_labels(ctx, members, column)
    return _participant_labels(members, participants, column)


def _counted(
    source: LabelSource,
    column: str,
    unit: Unit,
    members: Sequence[Member],
    units: Sequence[tuple[str, frozenset[str]]],
    vocabulary: frozenset[str],
) -> Labels:
    """Count ``units`` (label, splits) per scope and class; labels are keyed by the A-17 display rule."""
    counts: dict[str, Counter[str]] = {scope: Counter() for scope in _scopes(members)}
    shown: dict[str, str | None] = {}
    chars: dict[str, int] = {}
    for value, splits in units:
        label, key = display_text(value, vocabulary)
        shown[key] = label
        if label is None:
            chars[key] = len(value)
        counts[SCOPE_ALL][key] += 1
        for split in splits:
            counts[split][key] += 1
    reason = None if counts[SCOPE_ALL] else "ai.no_label_values"
    return Labels(source, column, unit, reason=reason, counts=counts, shown=shown, chars=chars)


def _event_labels(ctx: CheckContext, members: Sequence[Member], column: str) -> Labels:
    if not ctx.scan.is_bids:
        return Labels("events", column, "events", reason="ai.labels_need_bids")
    if not members:
        return Labels("events", column, "events", reason="ai.no_label_values")
    found = [(member, event_labels(ctx.root, member.rec.found.relative, column)) for member in members]
    if not any(labels.column for _member, labels in found):
        return Labels("events", column, "events", reason="ai.label_column_missing")
    vocabulary = frozenset().union(*(labels.vocabulary for _member, labels in found))
    units = [(value, member.splits) for member, labels in found for value in labels.values]
    return _counted("events", column, "events", members, units, vocabulary)


def _participant_labels(members: Sequence[Member], table: ParticipantsTable | None, column: str) -> Labels:
    reason = _table_reason(table)
    wanted = canonical(column)
    if reason is None and table is not None and wanted not in table.columns:
        reason = "ai.label_column_missing"
    if reason is None and any(member.subject is None for member in members):
        reason = "ai.subjects_unknown"
    if reason is not None or table is None:
        return Labels("participants", column, "subjects", reason=reason or "ai.no_participants_table")
    subject_splits: dict[str, set[str]] = {}
    for member in members:
        assert member.subject is not None
        subject_splits.setdefault(member.subject, set()).update(member.splits)
    units = []
    for label, splits in sorted(subject_splits.items()):
        participant = table.participants.get(label)
        value = participant.cells.get(wanted, "") if participant is not None else ""
        if not missing(value):
            units.append((value, frozenset(splits)))
    vocabulary = table.vocabulary.get(wanted, frozenset())
    return _counted("participants", column, "subjects", members, units, vocabulary)


def _table_reason(table: ParticipantsTable | None) -> str | None:
    if table is None:
        return "ai.no_participants_table"
    if not table.usable:
        return "ai.participants_unusable"
    return None


# --- small cells (A-51) ----------------------------------------------------------------------------------


def suppressed(cells: Mapping[str, int], total: int) -> tuple[dict[str, int | None], int | None]:
    """Counts of 1-4 become None. If that hides exactly one cell, the next smallest non-zero cell is hidden
    as well (complementary suppression), so that it cannot be derived from the total. The total is hidden
    when it is small itself or when fewer than two cells could be hidden."""
    hidden = {key for key, count in cells.items() if 0 < count < SMALL_CELL}
    if len(hidden) == 1:
        rest = sorted((count, key) for key, count in cells.items() if count > 0 and key not in hidden)
        if rest:
            hidden.add(rest[0][1])
    hide_total = 0 < total < SMALL_CELL or 0 < len(hidden) < 2
    return {key: None if key in hidden else count for key, count in sorted(cells.items())}, (
        None if hide_total else total
    )


def suppress_small_cells(findings: Sequence[Finding]) -> list[Finding]:
    """Output filter after the engine (A-51): a class share at subject level that would reveal a small
    count is output without its value; status and exit code come from the engine's exact comparison."""
    out = []
    for finding in findings:
        if finding.message_key == f"check.{CLASS_BALANCE}" and finding.details.get("small_cell") is True:
            finding = finding.model_copy(update={"measured_value": None, "reason": "ai.small_cell"})
        out.append(finding)
    return out


# --- measurements ----------------------------------------------------------------------------------------


def _dataset(check_id: str, **kwargs: Any) -> Measurement:
    return Measurement(check_id=check_id, object=DATASET, **kwargs)


def _on_recording(rec: RecordingState, check_id: str, **kwargs: Any) -> Measurement:
    return Measurement(
        check_id=check_id, object=rec.object_id, file=rec.file, identity=rec.identity, **kwargs
    )


def _on_subject(label: str, check_id: str, **kwargs: Any) -> Measurement:
    name = f"sub-{label}"
    return Measurement(check_id=check_id, object=name, identity=(name,), **kwargs)


def measure_class_balance(ctx: CheckContext) -> list[Measurement]:
    labels = structure(ctx).labels
    if labels is None:
        return [_dataset(CLASS_BALANCE, state="not_applicable", reason="ai.labels_not_configured")]
    if labels.reason is not None:
        return [_dataset(CLASS_BALANCE, state="not_checkable", reason=labels.reason)]
    classes = labels.classes
    out: list[Measurement] = []
    for scope, counter in labels.counts.items():
        total = sum(counter.values())
        if not total:
            out.append(
                _dataset(
                    CLASS_BALANCE,
                    subkey=scope,
                    state="not_checkable",
                    reason="ai.no_label_values",
                    details={"scope": scope},
                )
            )
            continue
        cells = {key: counter.get(key, 0) for key in classes}
        shown_cells, shown_total = (
            suppressed(cells, total) if labels.unit == "subjects" else (dict(cells), total)
        )
        for key in classes:
            details: dict[str, Any] = {"scope": scope, "label": labels.shown[key], "unit": labels.unit}
            if labels.shown[key] is None:
                details["label_chars"] = labels.chars[key]
            if shown_cells[key] is None:
                details["small_cell"] = True
            else:
                details["count"] = cells[key]
            if shown_total is not None:
                details["total"] = total
            out.append(
                _dataset(CLASS_BALANCE, subkey=f"{scope}:{key}", value=cells[key] / total, details=details)
            )
    return out


def measure_demographics(ctx: CheckContext) -> list[Measurement]:
    data = structure(ctx)
    if not data.members:
        return []
    if not data.subjects_known:
        return [_dataset(DEMOGRAPHICS, state="not_checkable", reason="ai.subjects_unknown")]
    table = data.participants
    out: list[Measurement] = []
    for label in sorted({member.subject for member in data.members if member.subject is not None}):
        for item in DEMOGRAPHIC_ITEMS:
            reason = _table_reason(table)
            details: dict[str, Any] = {}
            if reason is None and table is not None:
                participant = table.participants.get(label)
                if participant is None:
                    reason = "ai.not_in_participants"
                else:
                    state = participant.age if item == "age" else participant.sex
                    reason = _VALUE_REASONS.get(state)
                    column = "age" if item == "age" else table.sex_column
                    if column is not None and state != "no_column":
                        details["column"] = column
            out.append(
                _on_subject(
                    label, DEMOGRAPHICS, subkey=item, value=reason is None, reason=reason, details=details
                )
            )
    return out


def measure_split_integrity(ctx: CheckContext) -> list[Measurement]:
    data = structure(ctx)
    if data.split_source is None:
        return [_dataset(SPLIT_INTEGRITY, state="not_applicable", reason="ai.no_splits")]
    out: list[Measurement] = []
    by_subject: dict[str, list[Member]] = {}
    for member in data.members:
        if not member.splits:
            continue
        if member.subject is not None:
            by_subject.setdefault(member.subject, []).append(member)
        elif len(member.splits) > 1:  # the recording itself lies in several splits: no subject needed
            out.append(_on_recording(member.rec, SPLIT_INTEGRITY, value=_ordered(member.splits)))
        else:
            out.append(
                _on_recording(member.rec, SPLIT_INTEGRITY, state="not_checkable", reason="ai.subject_unknown")
            )
    for label, members in sorted(by_subject.items()):
        splits = _ordered(split for member in members for split in member.splits)
        ordered = sorted(members, key=lambda m: m.rec.identity[0])
        listed = {
            split: [m.rec.object_id for m in ordered if split in m.splits][:MAX_LISTED] for split in splits
        }
        out.append(
            _on_subject(
                label,
                SPLIT_INTEGRITY,
                value=splits,
                details={"split_recordings": listed, "recordings_total": len(members)},
            )
        )
    return out


def _ordered(splits: Iterable[str]) -> list[str]:
    distinct = set(splits)
    return [split for split in SPLIT_NAMES if split in distinct]


def _signal_hash(rec: RecordingState) -> str | None:
    result = rec.quality
    if rec.annotations_only or result is None or result.reason or result.stream is None:
        return None
    return result.stream.signal_hash


def _hash_unavailable(rec: RecordingState) -> Measurement | None:
    """Why a recording has no signal hash, if it has none (the reasons of the quality checks)."""
    if rec.annotations_only:
        return _on_recording(rec, DUPLICATES, state="not_applicable", reason="recording.annotations_only")
    if rec.recording is None:
        return _on_recording(rec, DUPLICATES, state="not_checkable", reason="header.unreadable")
    result = rec.quality
    if result is None or (result.stream is None and not result.reason):
        return _on_recording(rec, DUPLICATES, state="not_checkable", reason="quality.not_computed")
    if result.reason:
        details = {"error_type": result.error_type} if result.error_type else {}
        return _on_recording(rec, DUPLICATES, state="not_checkable", reason=result.reason, details=details)
    if _signal_hash(rec) is None:
        return _on_recording(rec, DUPLICATES, state="not_checkable", reason="ai.hash_unavailable")
    return None


def duplicate_groups(ctx: CheckContext) -> list[list[RecordingState]]:
    """Recordings with the same signal hash, members and groups ordered by relative path (A-68: independent
    of --show-paths). The hash itself is only compared here."""
    by_hash: dict[str, list[RecordingState]] = {}
    for rec in ctx.recordings:
        digest = _signal_hash(rec)
        if digest is not None:
            by_hash.setdefault(digest, []).append(rec)
    groups = [sorted(recs, key=lambda r: r.identity[0]) for recs in by_hash.values() if len(recs) > 1]
    return sorted(groups, key=lambda group: group[0].identity[0])


def measure_duplicates(ctx: CheckContext) -> list[Measurement]:
    splits = {member.key: member.splits for member in structure(ctx).members}
    membership: dict[str, tuple[int, list[RecordingState]]] = {}
    for number, group in enumerate(duplicate_groups(ctx), start=1):
        for rec in group:
            membership[rec.found.relative.as_posix()] = (number, group)
    out: list[Measurement] = []
    for rec in ctx.recordings:
        unavailable = _hash_unavailable(rec)
        if unavailable is not None:
            out.append(unavailable)
            continue
        entry = membership.get(rec.found.relative.as_posix())
        if entry is None:
            out.append(_on_recording(rec, DUPLICATES, value=0))
            continue
        number, group = entry
        others = [other for other in group if other is not rec]
        details: dict[str, Any] = {
            "group": number,
            "duplicate_of": [other.object_id for other in others][:MAX_LISTED],
            "duplicates_total": len(others),
        }
        group_splits = _ordered(
            split for member in group for split in splits.get(member.found.relative.as_posix(), ())
        )
        if group_splits:
            details["splits"] = group_splits
        out.append(_on_recording(rec, DUPLICATES, subkey=str(number), value=len(others), details=details))
    return out


def _single_split(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
    return Evaluation(passed=len(measurement.value) <= 1)


def _no_duplicate(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
    return Evaluation(passed=measurement.value == 0, threshold=0)


SPECS = (
    CheckSpec(
        id=CLASS_BALANCE, evaluate=at_least("min_share"), params={"min_share": ParamSpec("number", 0.05)}
    ),
    CheckSpec(id=DEMOGRAPHICS, evaluate=is_true),
    CheckSpec(id=SPLIT_INTEGRITY, evaluate=_single_split),
    CheckSpec(id=DUPLICATES, evaluate=_no_duplicate),
)

MEASURERS = {
    CLASS_BALANCE: measure_class_balance,
    DEMOGRAPHICS: measure_demographics,
    SPLIT_INTEGRITY: measure_split_integrity,
    DUPLICATES: measure_duplicates,
}


# --- results.json blocks ---------------------------------------------------------------------------------


def _labels_block(labels: Labels | None) -> AILabels | None:
    if labels is None or labels.reason is not None:
        return None
    scopes: dict[str, AILabelScope] = {}
    for scope, counter in labels.counts.items():
        cells = {key: counter.get(key, 0) for key in labels.classes}
        total = sum(cells.values())
        shown_cells, shown_total = (
            suppressed(cells, total) if labels.unit == "subjects" else (dict(sorted(cells.items())), total)
        )
        scopes[scope] = AILabelScope(total=shown_total, classes=shown_cells)
    return AILabels(
        source=labels.source,
        column=labels.column,
        unit=labels.unit,
        scopes=scopes,
    )


def _demographics_block(data: Structure) -> AIDemographics | None:
    table = data.participants
    if table is None or not table.usable or not data.members or not data.subjects_known:
        return None
    labels = sorted({member.subject for member in data.members if member.subject is not None})
    participants = [table.participants[label] for label in labels if label in table.participants]
    ages = Counter(p.subject.age_group for p in participants if p.age == "documented" and p.subject.age_group)
    sexes = Counter(p.subject.sex for p in participants if p.sex == "documented" and p.subject.sex)
    age_groups, age_total = suppressed(dict(ages), sum(ages.values()))
    sex, sex_total = suppressed(dict(sexes), sum(sexes.values()))
    return AIDemographics(
        subjects=len(labels),
        age_documented=age_total,
        sex_documented=sex_total,
        age_groups=age_groups,
        sex=sex,
    )


def _splits_block(data: Structure) -> AISplits | None:
    if data.split_source is None:
        return None
    subjects: dict[str, set[str]] = {name: set() for name in SPLIT_NAMES}
    for member in data.members:
        for split in member.splits:
            if member.subject is not None:
                subjects[split].add(member.subject)
    recordings = {split.name: len(split.recording_ids) for split in data.splits}  # DM-06
    return AISplits(
        source=data.split_source,
        recordings={name: recordings.get(name, 0) for name in SPLIT_NAMES},
        subjects={name: len(subjects[name]) for name in SPLIT_NAMES},
        unassigned=sum(1 for member in data.members if not member.splits),
    )


@dataclass(frozen=True)
class Outputs:
    duplicates: list[list[str]] | None  # None: no duplicate check ran
    summary: AISummary | None  # None: no M11/M12 structure check ran
    notices: list[Notice]


def outputs(ctx: CheckContext, check_ids: Iterable[str]) -> Outputs:
    """The results.json blocks of M11/M12 (decision C1: optional) and the notices about the splits."""
    loaded = set(check_ids)
    duplicates = (
        [[rec.object_id for rec in group] for group in duplicate_groups(ctx)]
        if DUPLICATES in loaded
        else None
    )
    if not loaded & CHECKS:
        return Outputs(duplicates=duplicates, summary=None, notices=[])
    data = structure(ctx)
    summary = None
    if loaded & STRUCTURE_CHECKS:
        summary = AISummary(
            labels=_labels_block(data.labels),
            demographics=_demographics_block(data),
            splits=_splits_block(data),
        )
    return Outputs(duplicates=duplicates, summary=summary, notices=list(data.notices))
