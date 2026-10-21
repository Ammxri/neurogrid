"""Build the report context from results.json and render HTML (NG-F13, PRD §14).

The report reads only results.json (A-61). PDF output and charts follow in P5.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neurogrid.kernel.evidence import EvidenceRecord, EvidenceState
from neurogrid.kernel.findings import Finding, Phase, Severity, SourceStatus, Status
from neurogrid.kernel.report import render_html
from neurogrid.kernel.rules import EVIDENCE_CHECK
from neurogrid.model.results import Results, RuleInfo
from neurogrid.report.texts import translator, validator_text

TEMPLATE_DIR = Path(__file__).parent / "templates"
MAX_TIME_RANGES_SHOWN = 20
MAX_SUB_CODES_SHOWN = 100  # sub-codes are schema fields or table columns; a bound for odd tables
_SEGMENT_KEYS = ("start_s", "duration_s")
UNKNOWN_CLAUSE = "unknown"  # clause of a pack whose norm text is not accessible (gxdsl008, A-40, A-83)


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
        """Placeholder packs have no clause (A-41); 'unknown' is a pack without accessible norm text, e.g.
        gxdsl008 (A-40, A-83), written in English in the YAML (D-03) and translated here."""
        if finding.source_status is SourceStatus.PLACEHOLDER:
            return self.tr("report.value.placeholder_clause")
        if finding.clause == UNKNOWN_CLAUSE:
            return self.tr("report.value.clause_unknown")
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
        parts.extend(self.ai_details(finding.details))
        chars = finding.details.get("chars")
        if isinstance(chars, int) and not isinstance(chars, bool):  # a code or label not shown (A-17, M10)
            parts.append(self.tr("report.value.free_text", n=chars))
        if "error_type" in finding.details:  # foreign exception: only its type name (A-07)
            parts.append(str(finding.details["error_type"]))
        if "exception_reason" in finding.details:
            parts.append(str(finding.details["exception_reason"]))
        return " ".join(parts) if parts else self.tr("report.value.none")

    def ai_details(self, details: dict[str, Any]) -> list[str]:
        """M11/M12 details (A-81): class counts, free-text labels, split members and duplicate groups. Names
        are displayed recording IDs (pseudonymous in raw folders); signal hashes never reach results.json."""
        parts: list[str] = []
        label_chars = details.get("label_chars")
        if details.get("label") is None and isinstance(label_chars, int):
            parts.append(self.tr("report.ai.free_text", count=label_chars))
        unit = details.get("unit")
        counted = isinstance(details.get("count"), int) and isinstance(details.get("total"), int)
        if unit in ("events", "subjects") and counted:
            parts.append(
                self.tr(
                    "report.ai.share",
                    count=details["count"],
                    total=details["total"],
                    unit=self.tr(f"report.ai.unit_{unit}"),
                )
            )
        recordings = details.get("split_recordings")
        order = ("train", "val", "test")  # DM-06; results.json sorts the keys
        for split, names in (
            sorted(
                recordings.items(),
                key=lambda item: (order.index(item[0]) if item[0] in order else 3, item[0]),
            )
            if isinstance(recordings, dict)
            else []
        ):
            if isinstance(names, list):
                parts.append(self.tr("report.ai.split_recordings", split=split, names=self.names(names)))
        if isinstance(details.get("duplicate_of"), list):
            names = self.names(details["duplicate_of"], details.get("duplicates_total"))
            parts.append(self.tr("report.ai.duplicate_of", names=names))
            if isinstance(details.get("splits"), list):
                parts.append(self.tr("report.ai.duplicate_splits", names=self.names(details["splits"])))
        return parts

    @staticmethod
    def names(items: list[Any], total: Any = None) -> str:
        """'a, b, c' plus '(+n)' when the list was cut (A-59: at most 20 IDs in details)."""
        text = ", ".join(str(item) for item in items)
        extra = total - len(items) if isinstance(total, int) and not isinstance(total, bool) else 0
        return text + (f" (+{extra})" if extra > 0 else "")

    def label(self, prefix: str, key: Any) -> str:
        """The text for a value from results.json, or the value itself if it has none (another version)."""
        dotted = f"{prefix}.{key}"
        return self.tr(dotted) if self.has(dotted) else str(key)

    def segments(self, segments: Any) -> str:
        """Start and end of each sample segment in recording time (KONZEPT 1.5, Ausweis)."""
        parts = [
            f"{float(s['start_s']):.3f}–{float(s['start_s']) + float(s['duration_s']):.3f} s"
            for s in (segments if isinstance(segments, list) else [])
            if isinstance(s, dict)
            and all(
                isinstance(s.get(k), int | float) and not isinstance(s.get(k), bool) for k in _SEGMENT_KEYS
            )
        ]
        return ", ".join(parts) if parts else self.tr("report.value.none")

    def positions(self, sample: Any) -> str:
        """Montage source of the sample, left-out channels and unused sources (A-60, A-79)."""
        sample = sample if isinstance(sample, dict) else {}
        parts = [self.label("report.positions", sample.get("positions", "none"))]
        excluded = sample.get("excluded_channels")
        if isinstance(excluded, list) and excluded:
            parts.append(self.tr("report.text.positions_excluded", names=", ".join(str(n) for n in excluded)))
        unused = sample.get("positions_unused")
        for source, reason in sorted(unused.items()) if isinstance(unused, dict) else []:
            parts.append(
                self.tr(
                    "report.text.positions_unused",
                    source=self.label("report.positions", source),
                    reason=self.label("report.positions_unused", reason),
                )
            )
        return "; ".join(parts)

    def sample_method(self, sample: Any) -> str:
        sample = sample if isinstance(sample, dict) else {}
        band = sample.get("band_hz")
        low, high = band if isinstance(band, list) and len(band) == 2 else (None, None)
        return self.tr(
            "report.text.sample_method",
            resample_hz=self.value(sample.get("resample_hz")),
            low=self.value(low),
            high=self.value(high),
            epoch_s=self.value(sample.get("epoch_s")),
        )

    def sample_row(self, sample: Any) -> dict[str, str]:
        """One row of the sample table; results.json of another version may lack fields or shape them
        differently, so every cell falls back to the 'none' text."""
        sample = sample if isinstance(sample, dict) else {}
        return {
            "mode": self.label("report.sample_mode", sample.get("mode", "none")),
            "segments": self.segments(sample.get("segments")),
            "seed": self.value(sample.get("seed")),
            "channels": self.value(sample.get("channels")),
            "positions": self.positions(sample),
            "notch": self.value(sample.get("notch_hz")),
        }

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

    def evidence_row(
        self, record: EvidenceRecord, rule: RuleInfo | None, finding: Finding | None, title: str
    ) -> dict[str, str]:
        """One row of section 5 (REP-05, A-15, A-83). 'provided' reads as the user's statement, never as
        passed; the document reference, the SHA-256 NeuroGrid computed, reviewer, date and comment follow."""
        none = self.tr("report.value.none")
        placeholder = rule is not None and rule.source_status is SourceStatus.PLACEHOLDER
        if placeholder:
            status = self.tr("report.value.placeholder_status")  # not evaluated (A-41)
        elif record.status is EvidenceState.PROVIDED and record.outcome is Status.PASSED:
            status = self.tr("report.value.evidence_provided")
        else:
            status = self.tr(f"status.{record.outcome.value}")
        check = record.document_check
        texts = [text for text in (record.comment, record.justification) if text]
        return {
            "rule": record.rule_id,
            "rulepack": record.rulepack,
            "title": title,
            "kind": f"{self.label('severity', record.severity.value)} · "
            f"{self.label('verification', record.verification.value)}",
            "status": status,
            "note": self.details(finding) if finding is not None else none,
            "document": record.document or none,
            "document_check": self.label("report.document_check", check.value) if check else none,
            "sha256": record.sha256 or none,
            "reviewer": record.reviewer or none,
            "date": record.date.isoformat() if record.date else none,
            "comment": " / ".join(texts) if texts else none,
        }

    def legacy_evidence_row(self, rule: RuleInfo, finding: Finding | None, title: str) -> dict[str, str]:
        """Section 5 for a results.json without the evidence block (P1-P3): manual rules from the findings."""
        none = self.tr("report.value.none")
        return {
            "rule": rule.id,
            "rulepack": rule.rulepack,
            "title": title,
            "kind": f"{self.label('severity', rule.severity.value)} · "
            f"{self.label('verification', rule.verification.value)}",
            "status": self.status(finding) if finding else self.tr("report.value.evidence_provided"),
            "note": self.details(finding) if finding else none,
            "document": none,
            "document_check": none,
            "sha256": none,
            "reviewer": none,
            "date": none,
            "comment": none,
        }


def _see_also(results: Results) -> dict[str, list[str]]:
    """A-40: packs that share a check and threshold give separate findings on purpose; each finding names the
    findings of the other rules on the same object, subkey and channel (finding key -> other rule IDs).
    Evidence rules are distinct requirements and are never linked."""
    checks = {rule.id: rule.check for rule in results.rules}
    groups: dict[tuple[str | None, str, str | None, str | None], set[str]] = {}
    shown = [
        f
        for f in results.findings
        if f.source_status is not SourceStatus.PLACEHOLDER and checks.get(f.rule_id) != EVIDENCE_CHECK
    ]
    for finding in shown:
        group = (checks.get(finding.rule_id), finding.object, finding.subkey, finding.channel)
        groups.setdefault(group, set()).add(finding.rule_id)
    links: dict[str, list[str]] = {}
    for finding in shown:
        group = (checks.get(finding.rule_id), finding.object, finding.subkey, finding.channel)
        others = sorted(groups[group] - {finding.rule_id})
        if others:
            links[finding.key] = others
    return links


def _evidence_rows(results: Results, fmt: _Formatter, titles: dict[str, str]) -> list[dict[str, str]]:
    rules = {rule.id: rule for rule in results.rules}
    findings = {f.rule_id: f for f in results.findings if f.object == "dataset" and f.subkey is None}
    if results.evidence:
        return [
            fmt.evidence_row(
                record,
                rules.get(record.rule_id),
                findings.get(record.rule_id),
                titles.get(record.rule_id, ""),
            )
            for record in results.evidence
        ]
    manual = [rule for rule in results.rules if rule.verification.value == "manual"]
    return [fmt.legacy_evidence_row(rule, findings.get(rule.id), titles.get(rule.id, "")) for rule in manual]


def build_context(results: Results, lang: str) -> dict[str, Any]:
    fmt = _Formatter(lang)
    title_field = "title_zh" if lang == "zh" else "title_en"
    titles = {rule.id: getattr(rule, title_field) for rule in results.rules}
    evaluated = [f for f in results.findings if f.source_status is not SourceStatus.PLACEHOLDER]
    by_severity = [(severity, [f for f in evaluated if f.severity is severity]) for severity in Severity]
    return {
        "evidence_rows": _evidence_rows(results, fmt, titles),
        "see_also": _see_also(results),
        "secondary_packs": [p for p in results.rulepacks if p.source_status is SourceStatus.SECONDARY],
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
        "sampled": [rec for rec in results.recordings if rec.sample],
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
