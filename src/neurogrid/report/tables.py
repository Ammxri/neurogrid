"""Data of the report tables, read from results.json only (A-61): finding groups with the A-59 row limit,
metric values per recording, the rule overview and the dataset-level aggregates.

Nothing here judges a value again (ARC-02): markers and counts come from the findings of the rule engine.
The functions return numbers, keys and findings; render.py turns them into text.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from neurogrid.kernel.findings import Finding, PassedCount, Severity, SourceStatus, Status
from neurogrid.model.consent import CONSENT_USES
from neurogrid.model.results import (
    AILabelScope,
    ReconsentRisk,
    ReconsentSummary,
    RecordingSummary,
    Results,
)
from neurogrid.report.charts import nice_ceiling

MAX_ROWS_PER_RULE = 50  # A-59: the complete list of findings stays in results.json
# Order of the rows inside a rule group: what needs attention first (A-59 keeps the first 50).
STATUS_ORDER: dict[Status, int] = {
    Status.FAILED: 0,
    Status.EVIDENCE_OPEN: 1,
    Status.NOT_CHECKABLE: 2,
    Status.EXCEPTED: 3,
    Status.NOT_APPLICABLE: 4,
    Status.PASSED: 5,
}


@dataclass(frozen=True)
class RuleGroup:
    """The findings of one rule inside a severity group: at most ``MAX_ROWS_PER_RULE`` shown, the counts
    over all of them."""

    rule_id: str
    severity: Severity
    shown: list[Finding]
    total: int
    objects: int
    value_min: float | None
    value_max: float | None
    status_counts: list[tuple[Status, int]]

    @property
    def remainder(self) -> int:
        return self.total - len(self.shown)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def rule_groups(findings: Iterable[Finding], max_rows: int = MAX_ROWS_PER_RULE) -> list[RuleGroup]:
    """One group per rule (rule ID ascending, A-61); rows by status (STATUS_ORDER), object and subkey."""
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_rule[finding.rule_id].append(finding)
    groups = []
    for rule_id in sorted(by_rule):
        items = sorted(
            by_rule[rule_id], key=lambda f: (STATUS_ORDER[f.status], f.object, f.subkey or "", f.key)
        )
        numbers = [n for n in (_number(f.measured_value) for f in items) if n is not None]
        counts = Counter(f.status for f in items)
        groups.append(
            RuleGroup(
                rule_id=rule_id,
                severity=items[0].severity,
                shown=items[:max_rows],
                total=len(items),
                objects=len({f.object for f in items}),
                value_min=min(numbers) if numbers else None,
                value_max=max(numbers) if numbers else None,
                status_counts=sorted(counts.items(), key=lambda item: STATUS_ORDER[item[0]]),
            )
        )
    return groups


# --- M14 consent findings, aggregated (D-17 option B, A-81) ---------------------------------------------

CONSENT_CHECK = "consent.covered"  # checks.consent.COVERED (tests/integration/test_consent_pipeline.py)
RECONSENT_CHECK = (
    "consent.reconsent"  # checks.consent.RECONSENT (tests/integration/test_reconsent_pipeline.py)
)
CONSENT_CHECKS = "consent."  # every check on the consent records: its rules are aggregated (D-17 option B)
DATASET = "dataset"  # the object of a dataset-level result, as checks.ai_dataset.DATASET
SMALL_CELL = 5  # A-51/A-81 table rule, as checks.ai_dataset.SMALL_CELL


@dataclass(frozen=True)
class ConsentRow:
    """One row of the aggregated M14 block: a use (None: the whole dataset, or every use when even the sums
    per use are unknown), a status and reason (both None when the breakdown is withheld) and how many
    subjects, recordings or the dataset."""

    use: str | None
    status: Status | None
    reason: str | None
    count: int
    unit: str  # "subjects", "recordings" or "dataset"


@dataclass(frozen=True)
class ConsentTable:
    """The aggregated M14 block of one rule (D-17 option B, A-81, A-91): its rows, whether the subject table
    is withheld, how many subjects need a use (passed ones included; 0: the rule has no result per subject)
    and how many recordings have no known subject."""

    rows: list[ConsentRow]
    withheld: bool
    subjects: int
    recordings: int


def consent_rules(results: Results) -> frozenset[str]:
    """The rules on a check of the consent records (its ID starts with ``consent.``: M14-01 consent.covered,
    M14-02 consent.reconsent), whatever pack they come from: their per-subject findings stay in results.json,
    the report shows them aggregated only (D-17 option B; for CORE-M14-02 owner answer 4 of P9)."""
    return frozenset(rule.id for rule in results.rules if rule.check.startswith(CONSENT_CHECKS))


def covered_rules(results: Results) -> frozenset[str]:
    """The rules on the M14-01 check: one block of counts per use, status and reason each (consent_table)."""
    return frozenset(rule.id for rule in results.rules if rule.check == CONSENT_CHECK)


def reconsent_rules(results: Results) -> frozenset[str]:
    """The rules on the M14-02 check: counts per risk in the re-consent section (reconsent_table)."""
    return frozenset(rule.id for rule in results.rules if rule.check == RECONSENT_CHECK)


# The rules on the M14 check in the built-in packs (tests/integration/test_consent_pipeline.py compares them
# with the packs): an exception for one of them names a subject also when no loaded pack has the rule.
BUILTIN_CONSENT_RULES = frozenset({"CORE-M14-01"})
# The same for the re-consent check (tests/integration/test_reconsent_pipeline.py).
BUILTIN_RECONSENT_RULES = frozenset({"CORE-M14-02"})


def consent_exception_rules(results: Results) -> frozenset[str]:
    """The rules whose exceptions the report shows only as their number, never with object, use or reason
    (D-17 option B, A-81): the loaded rules on a consent check and the built-in M14 rules, loaded or not. An
    [[exceptions]] entry for CORE-M14-01 or CORE-M14-02 names a subject and gives the user's reason for it
    also in a run with the BIDS pack alone, where it has no effect."""
    return consent_rules(results) | BUILTIN_CONSENT_RULES | BUILTIN_RECONSENT_RULES


def _use_order(use: str) -> tuple[int, str]:
    return (CONSENT_USES.index(use) if use in CONSENT_USES else len(CONSENT_USES), use)


def _status_order(cell: tuple[Status, str | None]) -> tuple[int, str]:
    return (STATUS_ORDER[cell[0]], cell[1] or "")


Cells = Counter[tuple[Status, str | None]]


def _passed_per_use(
    cells: dict[str, Cells], passed: int, sums: Mapping[str, int] | None
) -> dict[str, int] | None:
    """The passed subjects of each use: the sum of the use's table (results.consent) less its other cells,
    checked against the passed results of the rule. Without the sums (results.json written before they
    existed) they are known only when no subject passed a use. None: unknown."""
    if sums is None:
        return dict.fromkeys(cells, 0) if passed == 0 else None
    if not set(cells) <= set(sums):
        return None
    per_use = {use: total - sum(cells.get(use, Counter()).values()) for use, total in sums.items()}
    if any(count < 0 for count in per_use.values()) or sum(per_use.values()) != passed:
        return None
    return per_use


def consent_table(
    findings: Iterable[Finding], passed: Iterable[PassedCount] = (), sums: Mapping[str, int] | None = None
) -> ConsentTable:
    """The results of one M14 rule as counts per use, status and reason, never a subject ID or a consent
    version (D-17 option B). The subjects that need a use form one table per use over its (status, reason)
    cells, the passed ones included: results.passed counts a subject's passed uses without naming them, so the
    passed cell of a use is the use's sum (``sums``, results.consent) less its other cells. By the A-81 rule a
    table is published only if every non-zero cell has at least SMALL_CELL subjects; as the uses of a subject
    are linked (a withdrawal concerns every use), one withheld table withholds all, and then each use shows
    only its sum. When the passed subjects of a use are unknown, the tables are withheld and only the number
    of subjects that need a use is shown. Dataset-level findings and recordings without a known subject (no
    subject, so no consent decision) are counted as they are."""
    passed = list(passed)
    dataset: Cells = Counter()
    recordings: dict[str, Cells] = defaultdict(Counter)
    cells: dict[str, Cells] = defaultdict(Counter)
    subjects = {item.object for item in passed}
    unknown_subject: set[str] = set()
    for finding in findings:
        cell = (finding.status, finding.reason)
        use = finding.details.get("use")
        listed = finding.details.get("uses")
        if isinstance(use, str):
            cells[use][cell] += 1
            subjects.add(finding.object)
        elif isinstance(listed, list):
            unknown_subject.add(finding.object)
            for item in listed:
                recordings[str(item)][cell] += 1
        else:
            dataset[cell] += 1
    rows = [ConsentRow(None, status, reason, n, "dataset") for (status, reason), n in _sorted(dataset)]
    per_use = _passed_per_use(cells, sum(item.count for item in passed), sums) if subjects else {}
    withheld = per_use is None
    if per_use is None:  # the sums per use are unknown too: the number of subjects only
        rows.append(ConsentRow(None, None, None, len(subjects), "subjects"))
    else:
        for use, count in per_use.items():
            if count:
                cells[use][(Status.PASSED, None)] += count
        withheld = any(0 < n < SMALL_CELL for table in cells.values() for n in table.values())
    for use in sorted(set(cells) | set(recordings), key=_use_order):
        table = cells.get(use, Counter())
        if table and per_use is not None and withheld:
            rows.append(ConsentRow(use, None, None, sum(table.values()), "subjects"))
        elif table and per_use is not None:
            rows += [ConsentRow(use, status, reason, n, "subjects") for (status, reason), n in _sorted(table)]
        rows += [
            ConsentRow(use, status, reason, n, "recordings")
            for (status, reason), n in _sorted(recordings.get(use, Counter()))
        ]
    return ConsentTable(rows, withheld, len(subjects), len(unknown_subject))


def consent_rows(
    findings: Iterable[Finding], passed: Iterable[PassedCount] = (), sums: Mapping[str, int] | None = None
) -> tuple[list[ConsentRow], bool]:
    """The rows of consent_table and whether the subject table is withheld."""
    table = consent_table(findings, passed, sums)
    return table.rows, table.withheld


def rule_consent_table(results: Results, rule_id: str) -> ConsentTable:
    """consent_table for one rule of ``results``: its findings, its passed results and results.consent."""
    return consent_table(
        (f for f in results.findings if f.rule_id == rule_id),
        (p for p in results.passed if p.rule_id == rule_id),
        results.consent.subjects if results.consent is not None else None,
    )


def withheld_consent_rules(results: Results) -> frozenset[str]:
    """The loaded rules on a consent check whose subject tables are withheld: no count of theirs that depends
    on the consent decisions may appear elsewhere in the report either (A-81, A-91, A-95)."""
    covered = (rule_id for rule_id in covered_rules(results) if rule_consent_table(results, rule_id).withheld)
    reconsent = (rule_id for rule_id in reconsent_rules(results) if rule_reconsent_withheld(results, rule_id))
    return frozenset((*covered, *reconsent))


# --- M14-02 re-consent findings, aggregated per risk (D-17 option B, A-81, A-95) ------------------------

NO_VALID_CONSENT = "no_valid_consent"  # the reason of the cell of the subjects that M14-01 judges


@dataclass(frozen=True)
class ReconsentCell:
    """One cell of a risk's table: a status and reason of the rule's results per subject, or (status None,
    reason NO_VALID_CONSENT) the subjects without a valid consent at the reference date, whom CORE-M14-01
    judges; and how many subjects."""

    status: Status | None
    reason: str | None
    count: int


@dataclass(frozen=True)
class ReconsentRow:
    """A judged risk of the re-consent section: ID, date and affected uses (results.reconsent), the subjects
    whose signal recordings need an affected use (always shown) and its cells (empty when withheld)."""

    risk: ReconsentRisk
    cells: list[ReconsentCell]


@dataclass(frozen=True)
class ReconsentTable:
    """The re-consent section of one rule: a row per judged risk in ID order, whether the cells are
    withheld."""

    rows: list[ReconsentRow]
    withheld: bool


def reconsent_table(
    findings: Iterable[Finding], passed: Iterable[PassedCount], summary: ReconsentSummary
) -> ReconsentTable:
    """The results of one M14-02 rule as counts per risk, never a subject ID, a consent version or a risk
    description (D-17 option B, A-95). A risk's table distributes the subjects whose signal recordings need
    an affected use (results.reconsent ``subjects``, public like the subjects of a use) over cells: the
    statuses and reasons of the rule's results per subject, the passed ones (the risk's candidates less its
    other results: results.passed counts a subject's passed risks without naming them) and the subjects
    without a valid consent (subjects less candidates), so no cell can be computed from the others and the
    total. By the A-81 rule the tables are published only if every non-zero cell has at least SMALL_CELL
    subjects; the subjects of the risks overlap, so one withheld table withholds all, and each risk then shows
    only its subjects. Results that do not match results.reconsent (a result for a risk it does not name, more
    results than candidates, passed results that do not add up) withhold the tables too. Dataset-level
    results (a risk without candidates) count no subject."""
    cells: dict[str, Cells] = {risk.id: Counter() for risk in summary.risks}
    consistent = True
    for finding in findings:
        if finding.object == DATASET:
            continue
        table = cells.get(finding.subkey or "")
        if table is None:
            consistent = False
        else:
            table[(finding.status, finding.reason)] += 1
    rows = []
    passed_total = 0
    for risk in summary.risks:
        table = cells[risk.id]
        passed_count = risk.candidates - sum(table.values())
        no_valid = risk.subjects - risk.candidates
        consistent = consistent and passed_count >= 0 and no_valid >= 0
        passed_total += passed_count
        shown = [ReconsentCell(status, reason, n) for (status, reason), n in _sorted(table)]
        if passed_count > 0:
            shown.append(ReconsentCell(Status.PASSED, None, passed_count))
        if no_valid > 0:
            shown.append(ReconsentCell(None, NO_VALID_CONSENT, no_valid))
        rows.append(ReconsentRow(risk, shown))
    consistent = consistent and passed_total == sum(p.count for p in passed if p.object != DATASET)
    withheld = not consistent or any(0 < cell.count < SMALL_CELL for row in rows for cell in row.cells)
    if withheld:
        rows = [ReconsentRow(row.risk, []) for row in rows]
    return ReconsentTable(rows, withheld)


def rule_reconsent_table(results: Results, rule_id: str) -> ReconsentTable | None:
    """reconsent_table for one rule of ``results``; None without results.reconsent (no risk judged per
    subject: a single file, no risk, no consent data)."""
    if results.reconsent is None:
        return None
    return reconsent_table(
        (f for f in results.findings if f.rule_id == rule_id),
        (p for p in results.passed if p.rule_id == rule_id),
        results.reconsent,
    )


def rule_reconsent_withheld(results: Results, rule_id: str) -> bool:
    table = rule_reconsent_table(results, rule_id)
    return table is not None and table.withheld


def reconsent_subjects(results: Results) -> int:
    """How many subjects have a failed result of an evaluated rule on the re-consent check: the line of the
    console of check (cli.check.reconsent; the local console is the team's, like results.json). Placeholder
    rules are not evaluated (A-41)."""
    rules = {
        rule.id
        for rule in results.rules
        if rule.check == RECONSENT_CHECK and rule.source_status is not SourceStatus.PLACEHOLDER
    }
    return len(
        {
            f.object
            for f in results.findings
            if f.rule_id in rules and f.status is Status.FAILED and f.object != DATASET
        }
    )


def _sorted(cells: Cells) -> list[tuple[tuple[Status, str | None], int]]:
    return sorted(cells.items(), key=lambda item: _status_order(item[0]))


def evaluated_checks(results: Results) -> dict[str, list[str]]:
    """check id -> IDs of the rules of non-placeholder packs that use it (A-41: placeholders are not
    evaluated)."""
    checks: dict[str, list[str]] = defaultdict(list)
    for rule in results.rules:
        if rule.source_status is not SourceStatus.PLACEHOLDER:
            checks[rule.check].append(rule.id)
    return dict(checks)


def failed_index(results: Results) -> dict[tuple[str, str], set[str]]:
    """(check, object) -> subkeys ('' for none) of the failed findings of non-placeholder rules."""
    check_of = {
        rule.id: rule.check for rule in results.rules if rule.source_status is not SourceStatus.PLACEHOLDER
    }
    index: dict[tuple[str, str], set[str]] = defaultdict(set)
    for finding in results.findings:
        check = check_of.get(finding.rule_id)
        if check is not None and finding.status is Status.FAILED:
            index[(check, finding.object)].add(finding.subkey or "")
    return dict(index)


# --- metric values per recording (REP-04) ---------------------------------------------------------------


@dataclass(frozen=True)
class MetricValue:
    """One metric of one recording: the value, or None with the reason key of the measurement (if any)."""

    value: float | None
    reason: str | None = None


@dataclass(frozen=True)
class Metric:
    """A metric of the metrics table and its chart: where it lives in recordings[].metrics, the check whose
    rules judge it, the threshold parameter of those rules and the chart domain."""

    key: str
    check: str
    param: str | None
    lo: float
    hi: float | None  # None: nice_ceiling of max(2 · threshold, largest value)
    chart: bool = True
    optional: bool = False  # no chart and no 'no values' line when no recording has a value


METRICS: tuple[Metric, ...] = (
    Metric("m06", "quality.bad_channels", "max_fraction", 0.0, 1.0),
    Metric("m07", "quality.line_noise", "max_ratio", 0.0, None),
    Metric("m08_flat", "quality.flatline", "max_fraction", 0.0, 1.0),
    Metric("m08_clip", "quality.clipping", "max_fraction", 0.0, 1.0),
    Metric("m09a", "quality.autoreject", "max_fraction", 0.0, 1.0),
    Metric("m09b", "quality.non_brain_components", "max_fraction", 0.0, 1.0),
    # M10 kappa exists only for datasets with several annotators (A-80): its chart only if a value exists
    Metric("kappa", "annotation.kappa", "min_kappa", -1.0, 1.0, optional=True),
    Metric("coverage_min", "annotation.gaps", None, 0.0, 1.0, chart=False),
)
METRIC_BY_KEY = {metric.key: metric for metric in METRICS}
LINE_FREQUENCY_CHECK = "quality.line_frequency"


def _entry(metrics: dict[str, Any], key: str) -> dict[str, Any]:
    value = metrics.get(key)
    return value if isinstance(value, dict) else {}


def _reason(entry: dict[str, Any]) -> str | None:
    reason = entry.get("reason")
    return reason if isinstance(reason, str) else None


def _channels(metrics: dict[str, Any], key: str) -> list[dict[str, Any]]:
    channels = _entry(metrics, key).get("channels")
    if not isinstance(channels, dict):
        return []
    return [channels[name] for name in sorted(channels) if isinstance(channels[name], dict)]


def _worst(channels: list[dict[str, Any]], field_name: str) -> MetricValue:
    """The largest value over the channels; without any value the reason all channels share (if one)."""
    numbers = [n for n in (_number(ch.get(field_name)) for ch in channels) if n is not None]
    if numbers:
        return MetricValue(max(numbers))
    reasons = {_reason(ch) for ch in channels}
    return MetricValue(None, reasons.pop() if len(reasons) == 1 else None)


def recording_metrics(rec: RecordingSummary) -> dict[str, MetricValue]:
    """The metric values of one recording as the report shows them: one value per recording (worst channel
    for M07/M08), mean κ and the lowest annotator coverage of M10."""
    metrics = rec.metrics
    whole = _reason(metrics) if metrics.get("state") == "not_checkable" else None
    out: dict[str, MetricValue] = {}
    for key, name in (("m06", "M06"), ("m09a", "M09a"), ("m09b", "M09b")):
        entry = _entry(metrics, name)
        value = _number(entry.get("value"))
        out[key] = MetricValue(value) if value is not None else MetricValue(None, _reason(entry) or whole)
    out["m07"] = _worst(_channels(metrics, "M07"), "ratio")
    out["m08_flat"] = _worst(_channels(metrics, "M08"), "flat_fraction")
    out["m08_clip"] = _worst(_channels(metrics, "M08"), "clipped_fraction")
    for key in ("m07", "m08_flat", "m08_clip"):
        if out[key].value is None and out[key].reason is None and whole:
            out[key] = MetricValue(None, whole)
    annotation = _entry(metrics, "annotation")
    kappa = annotation.get("kappa")
    out["kappa"] = MetricValue(_number(kappa.get("mean")) if isinstance(kappa, dict) else None)
    coverage = annotation.get("coverage")
    shares = (
        [n for n in (_number(v) for v in coverage.values()) if n is not None]
        if isinstance(coverage, dict)
        else []
    )
    out["coverage_min"] = MetricValue(min(shares) if shares else None)
    return out


def measured_channels(rec: RecordingSummary) -> int:
    """Channels with an M07 value (the denominator of 'channels not passed')."""
    return sum(1 for ch in _channels(rec.metrics, "M07") if _number(ch.get("ratio")) is not None)


def line_frequency(rec: RecordingSummary) -> tuple[float, str] | None:
    """The line frequency M07 used and its source (config, sidecar, header or default)."""
    entry = _entry(rec.metrics, "M07")
    hz = _number(entry.get("line_frequency_hz"))
    source = entry.get("line_frequency_source")
    return (hz, str(source)) if hz is not None and isinstance(source, str) else None


@dataclass
class ChartData:
    metric: Metric
    values: list[float] = field(default_factory=list)
    missing: int = 0
    failed: int = 0
    thresholds: list[tuple[str, float, str]] = field(default_factory=list)  # rule, value, origin
    lo: float = 0.0
    hi: float = 1.0


def chart_data(results: Results, failed: dict[tuple[str, str], set[str]]) -> list[ChartData]:
    """One entry per chart metric: the values of all recordings, the number without a value, the number of
    recordings with a failed finding of a rule using the check, and the thresholds of those rules. An optional
    metric without any value has no entry."""
    rules = evaluated_checks(results)
    per_recording = [(rec.id, recording_metrics(rec)) for rec in results.recordings]
    charts = []
    for metric in METRICS:
        if not metric.chart:
            continue
        data = ChartData(metric)
        for rec_id, values in per_recording:
            value = values[metric.key].value
            if value is None:
                data.missing += 1
            else:
                data.values.append(value)
            if (metric.check, rec_id) in failed:
                data.failed += 1
        if metric.optional and not data.values:
            continue
        for rule_id in rules.get(metric.check, []):
            param = results.config.effective_params.get(rule_id, {}).get(metric.param or "")
            number = _number(param.value) if param is not None else None
            if param is not None and number is not None:
                data.thresholds.append((rule_id, number, param.origin))
        data.lo = metric.lo
        if metric.hi is not None:
            data.hi = metric.hi
        else:
            # twice each threshold, so its line sits inside the chart; a threshold so large that twice it
            # overflows (a rule 'switched off' by a huge value) does not count, so the domain still covers
            # the measured values
            doubled = [2 * t for _, t, _ in data.thresholds]
            limits = [limit for limit in doubled if math.isfinite(limit)] + data.values
            data.hi = nice_ceiling(max(limits)) if limits else 1.0
        charts.append(data)
    return charts


# --- appendix 6.1: rules checked (REP-06) -------------------------------------------------------------

COUNTED = (
    Status.PASSED,
    Status.FAILED,
    Status.EXCEPTED,
    Status.NOT_APPLICABLE,
    Status.NOT_CHECKABLE,
    Status.EVIDENCE_OPEN,
)


def rule_counts(results: Results) -> dict[str, dict[Status, int]]:
    """rule -> status -> count: passed checks from results.passed (A-59 counts per rule and object) plus
    passed findings, the other statuses from the findings."""
    counts: dict[str, dict[Status, int]] = {rule.id: dict.fromkeys(COUNTED, 0) for rule in results.rules}
    for passed in results.passed:
        if passed.rule_id in counts:
            counts[passed.rule_id][Status.PASSED] += passed.count
    for finding in results.findings:
        if finding.rule_id in counts:
            counts[finding.rule_id][finding.status] += 1
    return counts


# --- dataset-level aggregates (results.ai, results.duplicates; A-81) ----------------------------------

SPLIT_ORDER = ("all", "train", "val", "test")


def scope_order(names: Iterable[str]) -> list[str]:
    return sorted(names, key=lambda name: (SPLIT_ORDER.index(name) if name in SPLIT_ORDER else 4, name))


def label_classes(scopes: dict[str, AILabelScope]) -> list[str]:
    """All class keys over the scopes that are not withheld, sorted."""
    names: set[str] = set()
    for scope in scopes.values():
        if scope.classes is not None:
            names.update(scope.classes)
    return sorted(names)


def has_dataset_level(results: Results) -> bool:
    ai = results.ai
    return results.duplicates is not None or (
        ai is not None and any(part is not None for part in (ai.labels, ai.demographics, ai.splits))
    )
