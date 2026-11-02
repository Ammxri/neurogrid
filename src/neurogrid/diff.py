"""Comparison of two check runs: ``neurogrid diff OLD NEW`` (NG-F15, CLI-07, UF-02; A-33, A-97).

Findings are compared by their stable key (A-09). A key only in the new run is **new**; a key only in the old
run is **fixed** when its rule counts a passed result for the same object in the new run, else **removed**
(rule not loaded, object gone); a key in both runs is **changed** when its status, its effective severity or
its measured value differs, floats rounded to 6 significant digits as results.json and the report show them
(A-61). Severity is part of the comparison so that --strict never raises exit 1 without a listed change.
Findings of placeholder packs are not compared, only counted (A-41).

Exit code 1 iff a key is a counted error finding of the new run (severity error, status failed or
evidence_open) and none of the old run; findings of consent rules count as well, although they are listed only
as numbers per rule and category (D-17 option B). The comparison reads only the two results files: no dataset,
no vault and no access event (A-30).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any, Literal

from neurogrid import __version__
from neurogrid.kernel import canonical
from neurogrid.kernel.errors import NeuroGridError
from neurogrid.kernel.findings import SEVERITY_ORDER, Finding, Severity, SourceStatus, Status
from neurogrid.kernel.safety import check_operator_path, read_limited
from neurogrid.model.diff import (
    CATEGORIES,
    Category,
    DiffChange,
    DiffCount,
    DiffDataset,
    DiffFinding,
    DiffFindings,
    DiffResult,
    DiffRulepack,
    DiffRules,
    DiffRun,
    DiffState,
    DiffSummary,
)
from neurogrid.model.results import Disclaimer, Results, ToolInfo
from neurogrid.report.texts import disclaimer, translator

MAX_RESULTS_BYTES = 256_000_000  # as `report` reads results.json (A-53)
MAX_LISTED = 200  # lines per category in the text; the JSON lists every finding (A-59 style)
MAX_TEXT_CHARS = 200  # a text from a results file on the console: cleaned and shortened (A-53)
FORMATS = ("text", "json")
COUNTED = (Status.FAILED, Status.EVIDENCE_OPEN)  # as kernel.engine counts errors and warnings
CONSENT_CHECK_PREFIX = "consent."


def load(raw: str, label: Literal["OLD", "NEW"]) -> Results:
    """A results.json given on the command line, read like `report` reads it (<= 256 MB, the Results model;
    older files of P1-P6 load, C1). Every problem is one error naming the argument, never the path (A-51)."""
    path = check_operator_path(raw)
    try:
        return Results.model_validate_json(read_limited(path, MAX_RESULTS_BYTES))
    except (OSError, ValueError, NeuroGridError):
        raise NeuroGridError("errors.diff.results_invalid", file=label) from None


def _value(value: Any) -> Any:
    """A measured value as results.json and the report show it: floats rounded to 6 significant digits,
    recursively (A-61); a non-finite number of a hand-made file is null (A-75)."""
    if isinstance(value, float):
        return canonical.round_float(value) if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_value(item) for item in value]
    return value


def _same_value(old: Any, new: Any) -> bool:
    return canonical.compact(_value(old)) == canonical.compact(_value(new))


def _counted_error(finding: Finding) -> bool:
    return finding.severity is Severity.ERROR and finding.status in COUNTED


def _by_key(findings: Iterable[Finding]) -> dict[str, Finding]:
    """The compared findings of a run by key; a key twice in a hand-made file keeps its first finding."""
    found: dict[str, Finding] = {}
    for finding in findings:
        if finding.source_status is not SourceStatus.PLACEHOLDER:
            found.setdefault(finding.key, finding)
    return found


def _order(finding: Finding) -> tuple[Any, ...]:
    """The order of results.json (A-61): severity, rule, object, sub-key; the key decides between equals. A
    changed finding is ordered by its state in the new run."""
    return (
        SEVERITY_ORDER[finding.severity],
        finding.rule_id,
        finding.object,
        finding.subkey or "",
        finding.key,
    )


def _listed(finding: Finding) -> DiffFinding:
    return DiffFinding(
        key=finding.key,
        rule_id=finding.rule_id,
        rulepack=finding.rulepack,
        severity=finding.severity,
        status=finding.status,
        object=finding.object,
        subkey=finding.subkey,
        file=finding.file,
        channel=finding.channel,
        measured_value=_value(finding.measured_value),
        reason=finding.reason,
    )


def _state(finding: Finding) -> DiffState:
    return DiffState(
        status=finding.status, severity=finding.severity, measured_value=_value(finding.measured_value)
    )


def _run(results: Results) -> DiffRun:
    dataset = results.dataset
    return DiffRun(
        tool_version=results.tool.version,
        dataset=DiffDataset(id=dataset.id, name=dataset.name, version=dataset.version),
        as_of=results.config.as_of,
        config_sha256=results.config.canonical_sha256,
        rulepacks=[DiffRulepack(name=p.name, version=p.version, sha256=p.sha256) for p in results.rulepacks],
    )


def compare(old: Results, new: Results) -> DiffResult:
    """The comparison of two runs; the same inputs give a byte-identical result (canonical JSON, NG-N03)."""
    before, after = _by_key(old.findings), _by_key(new.findings)
    placeholder = {
        f.key for f in (*old.findings, *new.findings) if f.source_status is SourceStatus.PLACEHOLDER
    }
    consent_rules = {
        rule.id for rule in (*old.rules, *new.rules) if rule.check.startswith(CONSENT_CHECK_PREFIX)
    }
    passed_now = {(item.rule_id, item.object) for item in new.passed if item.count > 0}

    # (category, the finding whose state the entry shows, the entry) per changed key
    compared: list[tuple[Category, Finding, DiffFinding | DiffChange]] = []
    for key in after.keys() - before.keys():
        compared.append(("new", after[key], _listed(after[key])))
    for key in before.keys() - after.keys():
        then = before[key]
        category: Category = "fixed" if (then.rule_id, then.object) in passed_now else "removed"
        compared.append((category, then, _listed(then)))
    unchanged = 0
    for key in before.keys() & after.keys():
        then, now = before[key], after[key]
        if (
            now.status is then.status
            and now.severity is then.severity
            and _same_value(then.measured_value, now.measured_value)
        ):
            unchanged += 1
            continue
        change = DiffChange(
            key=key,
            rule_id=now.rule_id,
            object=now.object,
            subkey=now.subkey,
            old=_state(then),
            new=_state(now),
        )
        compared.append(("changed", now, change))
    new_errors = sum(
        1
        for key, now in after.items()
        if _counted_error(now) and (key not in before or not _counted_error(before[key]))
    )

    counts: Counter[Category] = Counter(category for category, _finding, _entry in compared)
    aggregated: Counter[tuple[str, Category]] = Counter()
    listed: dict[Category, list[tuple[tuple[Any, ...], Any]]] = {category: [] for category in CATEGORIES}
    for category, finding, entry in compared:
        if finding.rule_id in consent_rules:  # never per subject (D-17 option B): counted per rule
            aggregated[(finding.rule_id, category)] += 1
        else:
            listed[category].append((_order(finding), entry))

    def entries(category: Category) -> list[Any]:
        return [entry for _order_key, entry in sorted(listed[category], key=lambda item: item[0])]

    old_rules, new_rules = {rule.id for rule in old.rules}, {rule.id for rule in new.rules}
    return DiffResult(
        disclaimer=Disclaimer(zh=disclaimer("zh"), en=disclaimer("en")),
        tool=ToolInfo(version=__version__),
        old=_run(old),
        new=_run(new),
        rules=DiffRules(added=sorted(new_rules - old_rules), removed=sorted(old_rules - new_rules)),
        summary=DiffSummary(
            new=counts["new"],
            fixed=counts["fixed"],
            removed=counts["removed"],
            changed=counts["changed"],
            unchanged=unchanged,
            new_errors=new_errors,
            placeholder_skipped=len(placeholder),
            exit_code=1 if new_errors else 0,
        ),
        findings=DiffFindings(
            new=entries("new"), fixed=entries("fixed"), removed=entries("removed"), changed=entries("changed")
        ),
        aggregated=[
            DiffCount(rule_id=rule_id, category=category, count=aggregated[(rule_id, category)])
            for rule_id in sorted({rule_id for rule_id, _category in aggregated})
            for category in CATEGORIES
            if aggregated[(rule_id, category)]
        ],
    )


# --- text (the console; NeuroGrid's own words from the language tables, NG-N06) -----------------------------


def _clean(text: object) -> str:
    """A text from a results file: printable characters only, shortened (A-53)."""
    cleaned = "".join(ch for ch in str(text) if ch.isprintable())
    return cleaned if len(cleaned) <= MAX_TEXT_CHARS else cleaned[: MAX_TEXT_CHARS - 1] + "…"


def _shown_value(value: Any, none: str) -> str:
    """A measured value in the report's number format (.6g, A-61), a text as it is, anything else as its
    JSON (true, 8, {"documented": 0}); '–' without one."""
    if value is None:
        return none
    if isinstance(value, float):
        return format(value, ".6g")
    return _clean(value if isinstance(value, str) else canonical.compact(value).decode("utf-8"))


def _shown_object(obj: str, subkey: str | None) -> str:
    """Objects as results.json names them: pseudonymous in raw folders unless the run used --show-paths."""
    return _clean(obj if subkey is None else f"{obj} / {subkey}")


def _packs(run: DiffRun, none: str) -> str:
    return _clean(", ".join(f"{pack.name} {pack.version}" for pack in run.rulepacks)) or none


def text_lines(result: DiffResult, lang: str) -> list[str]:
    """The comparison for the console: both runs, one section per category with at most MAX_LISTED lines,
    the consent rules as counts, the summary and the reason of the exit code. The disclaimer follows from the
    command (A-08)."""
    tr = translator(lang).t
    none = tr("report.value.none")

    def status(state: DiffFinding | DiffState) -> str:
        shown = tr(f"status.{state.status.value}")
        reason = getattr(state, "reason", None)
        return f"{shown} ({_clean(tr(f'reason.{reason}'))})" if reason else shown

    def pair(old: str, new: str) -> str:
        return old if old == new else f"{old} → {new}"

    lines = [tr("cli.diff.title")]
    for which, run in (("old", result.old), ("new", result.new)):
        lines.append(
            tr(
                f"cli.diff.run.{which}",
                version=_clean(run.tool_version),
                as_of=run.as_of.isoformat(),
                packs=_packs(run, none),
            )
        )
    same_config = result.old.config_sha256 == result.new.config_sha256
    lines.append(tr("cli.diff.config_unchanged" if same_config else "cli.diff.config_changed"))
    old_set, new_set = result.old.dataset, result.new.dataset
    if (old_set.id, old_set.name) != (new_set.id, new_set.name):
        lines.append(tr("cli.diff.dataset_differs"))
    if result.rules.added or result.rules.removed:
        lines.append(
            tr(
                "cli.diff.rules",
                added=_clean(", ".join(result.rules.added)) or none,
                removed=_clean(", ".join(result.rules.removed)) or none,
            )
        )
    sections: tuple[tuple[Category, Sequence[DiffFinding | DiffChange]], ...] = (
        ("new", result.findings.new),
        ("fixed", result.findings.fixed),
        ("removed", result.findings.removed),
        ("changed", result.findings.changed),
    )
    for category, items in sections:
        lines.append(tr(f"cli.diff.section.{category}", count=len(items)))
        for item in items[:MAX_LISTED]:
            if isinstance(item, DiffChange):
                lines.append(
                    tr(
                        "cli.diff.changed_line",
                        rule=_clean(item.rule_id),
                        object=_shown_object(item.object, item.subkey),
                        status=pair(status(item.old), status(item.new)),
                        severity=pair(
                            tr(f"severity.{item.old.severity.value}"),
                            tr(f"severity.{item.new.severity.value}"),
                        ),
                        value=pair(
                            _shown_value(item.old.measured_value, none),
                            _shown_value(item.new.measured_value, none),
                        ),
                    )
                )
            else:
                lines.append(
                    tr(
                        "cli.diff.line",
                        rule=_clean(item.rule_id),
                        severity=tr(f"severity.{item.severity.value}"),
                        object=_shown_object(item.object, item.subkey),
                        status=status(item),
                        value=_shown_value(item.measured_value, none),
                    )
                )
        if len(items) > MAX_LISTED:
            lines.append(tr("cli.diff.more", count=len(items) - MAX_LISTED))
    if result.aggregated:
        lines.append(tr("cli.diff.section.aggregated"))
        for count in result.aggregated:
            lines.append(
                tr(
                    "cli.diff.aggregated",
                    rule=_clean(count.rule_id),
                    category=tr(f"terms.diff_category.{count.category}"),
                    count=count.count,
                )
            )
    summary = result.summary
    lines.append(
        tr(
            "cli.diff.summary",
            new=summary.new,
            fixed=summary.fixed,
            removed=summary.removed,
            changed=summary.changed,
            unchanged=summary.unchanged,
            placeholder=summary.placeholder_skipped,
        )
    )
    if summary.exit_code:
        lines.append(tr("cli.diff.exit_new_errors", count=summary.new_errors))
    else:
        lines.append(tr("cli.diff.exit_no_new_errors"))
    return lines
