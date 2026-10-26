"""Data of the report tables, read from results.json only (A-61): finding groups with the A-59 row limit,
metric values per recording, the rule overview and the dataset-level aggregates.

Nothing here judges a value again (ARC-02): markers and counts come from the findings of the rule engine.
The functions return numbers, keys and findings; render.py turns them into text.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from neurogrid.kernel.findings import Finding, Severity, SourceStatus, Status
from neurogrid.model.results import AILabelScope, RecordingSummary, Results
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
