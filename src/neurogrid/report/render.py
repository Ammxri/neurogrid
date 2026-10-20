"""Build the report context from results.json and render HTML (NG-F13, PRD §14).

The report reads only results.json (A-61). PDF output and charts follow in P5.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neurogrid.kernel.findings import Finding, Phase, Severity, SourceStatus, Status
from neurogrid.kernel.report import render_html
from neurogrid.model.results import Results
from neurogrid.report.texts import translator, validator_text

TEMPLATE_DIR = Path(__file__).parent / "templates"
MAX_TIME_RANGES_SHOWN = 20
MAX_SUB_CODES_SHOWN = 100  # sub-codes are schema fields or table columns; a bound for odd tables


class _Formatter:
    def __init__(self, lang: str) -> None:
        self.lang = lang
        self.tr = translator(lang).t
        self.has = translator(lang).has

    def value(self, value: Any) -> str:
        if value is None:
            return self.tr("report.value.none")
        if isinstance(value, bool):
            return self.tr("report.value.yes" if value else "report.value.no")
        if isinstance(value, float):
            return format(value, ".6g")
        if isinstance(value, list):
            return ", ".join(self.value(item) for item in value)
        if isinstance(value, dict):
            # structured measurements: translated labels, values formatted like scalars
            parts = []
            for key in sorted(value):
                label_key = f"report.measure.{key}"
                label = self.tr(label_key) if self.has(label_key) else key
                parts.append(f"{label}: {self.value(value[key])}")
            return "; ".join(parts)
        return str(value)

    def status(self, finding: Finding) -> str:
        """Placeholder packs carry no verdict (A-41, KONZEPT §3)."""
        if finding.source_status is SourceStatus.PLACEHOLDER:
            return self.tr("report.value.placeholder_status")
        return self.tr(f"status.{finding.status.value}")

    def measured(self, finding: Finding) -> str:
        if finding.measured_value is None and finding.status in (Status.EVIDENCE_OPEN, Status.PASSED):
            return self.tr("report.value.not_applicable_value")
        return self.value(finding.measured_value)

    def clause(self, finding: Finding) -> str:
        if finding.source_status is SourceStatus.PLACEHOLDER:
            return self.tr("report.value.placeholder_clause")
        return finding.clause

    def time_range(self, finding: Finding) -> str:
        if finding.time_ranges:
            shown = ", ".join(
                f"{r.start_s:.3f}–{r.end_s:.3f} s" for r in finding.time_ranges[:MAX_TIME_RANGES_SHOWN]
            )
            extra = finding.time_ranges_total - min(len(finding.time_ranges), MAX_TIME_RANGES_SHOWN)
            return shown + (f" (+{extra})" if extra > 0 else "")
        if finding.file is None:
            return self.tr("report.value.dataset_level")
        return self.tr("report.value.whole_recording")

    def details(self, finding: Finding) -> str:
        parts: list[str] = []
        if finding.reason:
            parts.append(self.tr(f"reason.{finding.reason}"))
        for code in finding.details.get("issues", []):
            parts.append(self.tr(f"issue.{code}"))
        fields = finding.details.get("fields", [])
        if fields:
            parts.append(", ".join(self.tr(f"issue.fields.{name}") for name in fields))
        if "issue" in finding.details:
            parts.append(self.tr(f"issue.{finding.details['issue']}"))
        if "validator_code" in finding.details:  # NeuroGrid's text, never the validator's message (A-06)
            code = str(finding.details["validator_code"])
            parts.append(validator_text(code, self.lang) or self.tr("report.validator.generic", code=code))
            count = finding.details.get("count")
            if isinstance(count, int) and count > 1:
                parts.append(self.tr("report.validator.count", count=count))
            names = self.sub_codes(finding.details.get("sub_codes"))
            if names:
                parts.append(self.tr("report.validator.sub_codes", names=names))
        if "error_type" in finding.details:  # foreign exception: only its type name (A-07)
            parts.append(str(finding.details["error_type"]))
        if "exception_reason" in finding.details:
            parts.append(str(finding.details["exception_reason"]))
        return " ".join(parts) if parts else self.tr("report.value.none")

    @staticmethod
    def sub_codes(value: Any) -> str:
        """What one validator finding covers (A-06, A-77): the sub-codes of the validator code, e.g. the
        sidecar fields, as 'a, b (2), c' (the count only when above 1; at most MAX_SUB_CODES_SHOWN names).

        Plain text: sub-codes are schema identifiers or names from the dataset (TSV columns), and the
        template escapes them (A-53)."""
        if not isinstance(value, dict):
            return ""
        names = [
            f"{name} ({count})" if isinstance(count, int) and count > 1 else str(name)
            for name, count in sorted(value.items())
        ]
        extra = len(names) - MAX_SUB_CODES_SHOWN
        return ", ".join(names[:MAX_SUB_CODES_SHOWN]) + (f" (+{extra})" if extra > 0 else "")


def build_context(results: Results, lang: str) -> dict[str, Any]:
    fmt = _Formatter(lang)
    title_field = "title_zh" if lang == "zh" else "title_en"
    titles = {rule.id: getattr(rule, title_field) for rule in results.rules}
    manual_rules = [rule for rule in results.rules if rule.verification.value == "manual"]
    evaluated = [f for f in results.findings if f.source_status is not SourceStatus.PLACEHOLDER]
    by_severity = [(severity, [f for f in evaluated if f.severity is severity]) for severity in Severity]
    return {
        "t": fmt.tr,
        "fmt": fmt,
        "lang": lang,
        "results": results,
        "titles": titles,
        "by_severity": by_severity,
        "placeholder_findings": [f for f in results.findings if f.source_status is SourceStatus.PLACEHOLDER],
        "phases": [
            (phase, results.summary.phases[phase]) for phase in Phase if phase in results.summary.phases
        ],
        "manual_rules": manual_rules,
        "manual_findings": {
            f.rule_id: f for f in results.findings if f.rule_id in {r.id for r in manual_rules}
        },
        "placeholder": any(p.source_status is SourceStatus.PLACEHOLDER for p in results.rulepacks),
        # checks of placeholder packs are not evaluated, so they are not counted as passed either (A-41)
        "passed_total": sum(
            p.count
            for p in results.passed
            if p.rule_id not in {r.id for r in results.rules if r.source_status is SourceStatus.PLACEHOLDER}
        ),
        "settings_json": json.dumps(
            results.config.effective_settings, ensure_ascii=False, sort_keys=True, indent=2
        ),
    }


def render_report(results: Results, lang: str) -> str:
    return render_html(TEMPLATE_DIR, "report.html.j2", build_context(results, lang))
