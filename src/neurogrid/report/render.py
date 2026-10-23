"""Build the report context from results.json and render HTML (NG-F13, PRD §14).

The report reads only results.json (A-61). The HTML is print-ready (REP-00, A-84): A4, the cover and the
summary in portrait, sections 3-6 on landscape pages, the fixed sentence, a running head and the page counter
on every page (CSS @page margin boxes), one font family ('NG Sans') whose @font-face rules the caller passes
as ``font_css`` (the PDF pipeline subsets the report fonts for the text of the page, B1). Every value goes
through glyph_safe, so no character falls back to a system font and the rendered document needs no second
glyph pass. The fonts are texts.FONT_FILES, the one font-path constant of the product. The PDF is a print of
exactly this HTML.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from markupsafe import Markup

from neurogrid.kernel.evidence import EvidenceRecord, EvidenceState
from neurogrid.kernel.findings import Finding, Phase, Severity, SourceStatus, Status
from neurogrid.kernel.report import render_html
from neurogrid.kernel.rules import EVIDENCE_CHECK
from neurogrid.model.results import Results, RuleInfo, Summary
from neurogrid.report import tables, texts
from neurogrid.report.charts import histogram_svg
from neurogrid.report.glyphs import font_coverage, glyph_safe
from neurogrid.report.texts import tables as language_tables
from neurogrid.report.texts import translator, validator_text

TEMPLATE_DIR = Path(__file__).parent / "templates"
FONT_FAMILY = "NG Sans"
MAX_TIME_RANGES_SHOWN = 20
MAX_SUB_CODES_SHOWN = 100  # sub-codes are schema fields or table columns; a bound for odd tables
MAX_ROWS_PER_RULE = tables.MAX_ROWS_PER_RULE
_SEGMENT_KEYS = ("start_s", "duration_s")
UNKNOWN_CLAUSE = "unknown"  # clause of a pack whose norm text is not accessible (gxdsl008, A-40, A-83)
# The texts a finding row shows instead of an empty value (A-09: '–' only with a reason). Imported by the
# tests and by the acceptance checks: a cell of a finding row that starts with '–' is one of these texts.
EXPLAINED_EMPTY: tuple[str, ...] = (
    "report.value.not_applicable_value",
    "report.value.measured_see_reason",
    "report.value.measured_presence",
    "report.value.no_threshold",
    "report.value.dataset_level",
    "report.value.no_channel",
    "report.value.whole_recording",
    "report.value.whole_file",
    "report.value.time_dataset",
    "report.value.no_details",
    "report.value.clause_missing",
    "report.value.title_missing",
)
# Cell classes of a finding row, in column order (B1); every row has data-key = Finding.key.
FINDING_CELLS: tuple[str, ...] = (
    "rule",
    "clause",
    "title",
    "status",
    "file",
    "channel",
    "measured",
    "threshold",
    "time",
    "reason",
)
_COUNTER = re.compile(r"(\{page\}|\{pages\})")


def report_coverage() -> frozenset[int] | None:
    """The code points the report fonts (texts.FONT_FILES, the static cuts of A-27 whose subsets the HTML
    embeds) can draw; None without the font files (no font is embedded then)."""
    fonts = texts.FONT_FILES
    return font_coverage(fonts[weight] for weight in sorted(fonts))


def has_value(value: Any) -> bool:
    """Whether a measured value holds anything to show: None, blank text and lists or mappings whose elements
    all hold nothing count as no value (A-09: such a cell is '–' with its reason, never a bare '–')."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(has_value(item) for item in value)
    if isinstance(value, dict):
        return any(has_value(item) for item in value.values())
    return True


def _finalize(value: Any) -> Any:
    """Applied by Jinja2 to every template expression: text is made glyph-safe, Markup passes."""
    if isinstance(value, Markup) or not isinstance(value, str):
        return value
    return glyph_safe(value, report_coverage())


class _Formatter:
    def __init__(
        self,
        lang: str,
        recordings: frozenset[str] = frozenset(),
        evidence_rules: frozenset[str] = frozenset(),
    ) -> None:
        """``recordings`` are the IDs of results.json's recordings: a finding on one of them without a time
        range covers the whole recording; one on another file (a control file, a new file in the manifest
        comparison, an unsupported or orphan data file) covers the whole file (A-10). ``evidence_rules`` are
        the rules evaluated from evidence.yaml: they measure no value (A-15)."""
        self.lang = lang
        self.tr = translator(lang).t
        self.has = translator(lang).has
        self.recordings = recordings
        self.evidence_rules = evidence_rules

    def value(self, value: Any, *, empty: str | None = None) -> str:
        """A value from results.json as text. ``empty`` is the text key for an element without a value (None,
        blank text, an empty list) inside a list or mapping; without it such an element is '–'."""
        if empty is not None and not has_value(value):
            return self.tr(empty)
        if value is None:
            return self.tr("report.value.none")
        if isinstance(value, bool):
            return self.tr("report.value.yes" if value else "report.value.no")
        if isinstance(value, float):
            return format(value, ".6g")
        if isinstance(value, list):
            return ", ".join(self.value(item, empty=empty) for item in value)
        if isinstance(value, dict):
            # structured measurements: translated labels, values formatted like scalars
            parts = []
            for key in sorted(value):
                label_key = f"report.measure.{key}"
                label = self.tr(label_key) if self.has(label_key) else key
                parts.append(f"{label}: {self.value(value[key], empty=empty)}")
            return "; ".join(parts)
        return str(value)

    def status(self, finding: Finding) -> str:
        """Placeholder packs carry no verdict (A-41, KONZEPT §3)."""
        if finding.source_status is SourceStatus.PLACEHOLDER:
            return self.tr("report.value.placeholder_status")
        return self.tr(f"status.{finding.status.value}")

    def measured(self, finding: Finding) -> str:
        """The measured value, or '–' with the reason why there is none (A-09). A value without any element
        that holds something (empty text, an empty list, a list of None) counts as none; an element without a
        value inside a measured list or mapping is named as such, so the cell never shows a bare '–'."""
        if has_value(finding.measured_value):
            return self.value(finding.measured_value, empty="report.value.element_missing")
        if finding.rule_id in self.evidence_rules or finding.status in (Status.EVIDENCE_OPEN, Status.PASSED):
            return self.tr("report.value.not_applicable_value")
        if finding.status in (Status.NOT_CHECKABLE, Status.NOT_APPLICABLE):
            return self.tr("report.value.measured_see_reason")
        return self.tr("report.value.measured_presence")

    def threshold(self, finding: Finding) -> str:
        """The effective parameters with their origin (A-13), also when no value was measured; '–' with
        reason only for a rule without parameters and threshold."""
        params = finding.params
        parts = []
        if finding.threshold is not None and not any(finding.threshold == p.value for p in params.values()):
            parts.append(self.value(finding.threshold))
        for name in sorted(params):
            param = params[name]
            origin = self.tr(f"report.text.origin_{param.origin}")
            parts.append(f"{name} = {self.value(param.value)} ({origin})")
        return "; ".join(parts) if parts else self.tr("report.value.no_threshold")

    def file(self, finding: Finding) -> str:
        return finding.file or self.tr("report.value.dataset_level")

    def channel(self, finding: Finding) -> str:
        return finding.channel or self.tr("report.value.no_channel")

    def clause_text(self, clause: str, source_status: SourceStatus) -> str:
        """Placeholder packs have no clause (A-41); 'unknown' is a pack without accessible norm text, e.g.
        gxdsl008 (A-40, A-83), written in English in the YAML (D-03) and translated here."""
        if source_status is SourceStatus.PLACEHOLDER:
            return self.tr("report.value.placeholder_clause")
        if clause == UNKNOWN_CLAUSE:
            return self.tr("report.value.clause_unknown")
        return clause or self.tr("report.value.clause_missing")

    def clause(self, finding: Finding) -> str:
        return self.clause_text(finding.clause, finding.source_status)

    def time_range(self, finding: Finding) -> str:
        """At most 20 ranges, then their number and total duration (A-10)."""
        if finding.time_ranges:
            shown = finding.time_ranges[:MAX_TIME_RANGES_SHOWN]
            text = ", ".join(f"{r.start_s:.3f}–{r.end_s:.3f} s" for r in shown)
            total = max(finding.time_ranges_total, len(finding.time_ranges))
            seconds = finding.time_ranges_duration_s
            if total > len(shown):
                if seconds is None:
                    return (
                        text
                        + " "
                        + self.tr("report.value.time_ranges_more_count", shown=len(shown), total=total)
                    )
                return (
                    text
                    + " "
                    + self.tr(
                        "report.value.time_ranges_more",
                        shown=len(shown),
                        total=total,
                        seconds=self.value(seconds),
                    )
                )
            if total > 1 and seconds is not None:
                return text + " " + self.tr("report.value.time_ranges_total", seconds=self.value(seconds))
            return text
        if finding.file is None:
            return self.tr("report.value.time_dataset")
        if finding.object in self.recordings:
            return self.tr("report.value.whole_recording")
        return self.tr("report.value.whole_file")

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

    def reason_cell(self, finding: Finding) -> str:
        """The reason column of a finding row: the details, or '–' with the note that there are none."""
        text = self.details(finding)
        return text if text != self.tr("report.value.none") else self.tr("report.value.no_details")

    def ai_details(self, details: dict[str, Any]) -> list[str]:
        """M11/M12 details (A-81): class counts or a withheld subject-level scope (A-51), free-text labels,
        split members and duplicate groups. Names are displayed recording IDs (pseudonymous in raw folders);
        signal hashes never reach results.json."""
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
        if unit == "subjects" and details.get("withheld") is True and isinstance(details.get("total"), int):
            parts.append(self.tr("report.ai.withheld", total=details["total"]))  # A-51 table rule
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

    def overall(self, summary: Summary) -> str:
        """The overall sentence (POS-01): 'passes the checks of the loaded rule packs', never 'conforms'."""
        if summary.errors:
            return self.tr("report.text.overall_fails", errors=summary.errors, warnings=summary.warnings)
        if summary.warnings:
            return self.tr("report.text.overall_passes_warnings", warnings=summary.warnings)
        return self.tr("report.text.overall_passes")

    def share(self, value: float | None, failed: bool = False) -> str:
        """A share, ratio or κ of the metrics table: three decimals, ' *' when a rule on it is not passed."""
        if value is None:
            return self.tr("report.value.none")
        return format(value, ".3f") + (" *" if failed else "")


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


# --- section 1: cover (REP-01) -------------------------------------------------------------------------


def _cover_rows(results: Results, fmt: _Formatter) -> list[tuple[str, str, bool]]:
    """(label, value, monospace) of the cover table; every empty value names its reason (A-09)."""
    tr = fmt.tr
    dataset = results.dataset
    if dataset.manifest_hash:
        manifest_hash = dataset.manifest_hash
    elif results.manifest is not None:
        status = fmt.label("report.manifest_status", results.manifest.status.value)
        manifest_hash = tr("report.value.manifest_hash_missing", status=status)
    else:
        manifest_hash = tr("report.value.manifest_block_missing")
    manifest_status = (
        fmt.label("report.manifest_status", results.manifest.status.value)
        if results.manifest
        else tr("report.value.manifest_block_missing")
    )
    return [
        (tr("report.label.dataset"), dataset.name or tr("report.value.name_missing"), False),
        (tr("report.label.dataset_id"), dataset.id, True),
        (tr("report.label.version"), dataset.version or tr("report.value.version_missing"), False),
        (tr("report.label.license"), dataset.license or tr("report.value.license_missing"), False),
        (tr("report.label.date"), results.config.as_of.isoformat(), False),
        (tr("report.label.tool_version"), f"NeuroGrid {results.tool.version}", False),
        (tr("report.label.manifest_hash"), manifest_hash, bool(dataset.manifest_hash)),
        (tr("report.label.manifest_status"), manifest_status, False),
    ]


# --- section 3: findings (REP-03, NG-F13) --------------------------------------------------------------


def _finding_row(f: Finding, fmt: _Formatter, title: str, see_also: list[str] | None) -> dict[str, str]:
    """The ten cells of one finding row (B1); no cell is empty: a missing value is '–' with its reason."""
    title_text = (title or fmt.tr("report.value.title_missing")) + (f" – {f.subkey}" if f.subkey else "")
    if see_also:
        title_text += " · " + fmt.tr("report.text.see_also", rules=", ".join(see_also))
    return {
        "key": f.key,
        "rule": f.rule_id,
        "clause": fmt.clause(f),
        "title": title_text,
        "status": fmt.status(f),
        "file": fmt.file(f),
        "channel": fmt.channel(f),
        "measured": fmt.measured(f),
        "threshold": fmt.threshold(f),
        "time": fmt.time_range(f),
        "reason": fmt.reason_cell(f),
    }


def _group_view(
    group: tables.RuleGroup,
    fmt: _Formatter,
    titles: dict[str, str],
    see_also: dict[str, list[str]],
    *,
    placeholder: bool,
) -> dict[str, Any]:
    tr = fmt.tr
    parts = [tr("report.text.rule_aggregate", findings=group.total, objects=group.objects)]
    if group.value_min is not None and group.value_max is not None:
        parts.append(
            tr(
                "report.text.rule_aggregate_range",
                min=fmt.value(group.value_min),
                max=fmt.value(group.value_max),
            )
        )
    if not placeholder:  # placeholder rules carry no verdict (A-41)
        parts.extend(
            tr("report.text.status_count", status=tr(f"status.{status.value}"), count=count)
            for status, count in group.status_counts
        )
    aggregate = tr("report.text.separator").join(parts)
    title = titles.get(group.rule_id, "")
    return {
        "rule": group.rule_id,
        "heading": f"{group.rule_id} – {title}" if title else group.rule_id,
        "aggregate": aggregate,
        "rows": [_finding_row(f, fmt, title, see_also.get(f.key)) for f in group.shown],
        "more": tr("report.text.rule_more", count=group.remainder, rule=group.rule_id)
        if group.remainder
        else "",
    }


def _findings(
    results: Results, fmt: _Formatter, titles: dict[str, str], see_also: dict[str, list[str]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    evaluated = [f for f in results.findings if f.source_status is not SourceStatus.PLACEHOLDER]
    placeholder = [f for f in results.findings if f.source_status is SourceStatus.PLACEHOLDER]
    sections = []
    for severity in Severity:
        items = [f for f in evaluated if f.severity is severity]
        sections.append(
            {
                "severity": severity.value,
                "count": len(items),
                "groups": [
                    _group_view(g, fmt, titles, see_also, placeholder=False)
                    for g in tables.rule_groups(items)
                ],
            }
        )
    placeholder_groups = [
        _group_view(g, fmt, titles, see_also, placeholder=True) for g in tables.rule_groups(placeholder)
    ]
    return sections, placeholder_groups, len(placeholder)


# --- section 4: metrics (REP-04) -----------------------------------------------------------------------


def _missing(fmt: _Formatter, value: tables.MetricValue) -> str:
    if value.reason:
        return fmt.tr("report.value.missing_reason", reason=fmt.tr(f"reason.{value.reason}"))
    return fmt.tr("report.value.none")


def _metric_cell(
    fmt: _Formatter,
    value: tables.MetricValue,
    check: str,
    rec_id: str,
    failed: dict[tuple[str, str], set[str]],
) -> str:
    if value.value is None:
        return _missing(fmt, value)
    return fmt.share(value.value, (check, rec_id) in failed)


def _metric_rows(
    results: Results, fmt: _Formatter, failed: dict[tuple[str, str], set[str]]
) -> list[dict[str, str]]:
    rows = []
    by_key = tables.METRIC_BY_KEY
    for rec in results.recordings:
        values = tables.recording_metrics(rec)

        def cell(key: str, rec_id: str = rec.id, values: dict[str, tables.MetricValue] = values) -> str:
            return _metric_cell(fmt, values[key], by_key[key].check, rec_id, failed)

        line = tables.line_frequency(rec)
        if line is None:
            line_text = fmt.tr("report.value.none")
        else:
            marker = " *" if (tables.LINE_FREQUENCY_CHECK, rec.id) in failed else ""
            line_text = f"{fmt.value(line[0])} ({fmt.label('report.line_source', line[1])}){marker}"
        measured = tables.measured_channels(rec)
        if measured:
            failed_channels = len(failed.get((by_key["m07"].check, rec.id), set()))
            m07_failed = f"{failed_channels} / {measured}"
        else:
            m07_failed = _missing(fmt, values["m07"])
        if values["m08_flat"].value is None and values["m08_clip"].value is None:
            m08 = _missing(fmt, values["m08_flat"])
        else:
            m08 = f"{cell('m08_flat')} / {cell('m08_clip')}"
        format_text = rec.format + ("" if rec.streamable else " – " + fmt.tr("report.value.not_streamable"))
        rows.append(
            {
                "id": rec.id,
                "format": format_text,
                "rate": fmt.value(rec.sampling_rate_hz),
                "duration": fmt.value(rec.duration_s),
                "channels": f"{fmt.value(rec.n_channels)} ({fmt.value(rec.n_eeg_channels)})",
                "line": line_text,
                "m06": cell("m06"),
                "m07": cell("m07"),
                "m07_failed": m07_failed,
                "m08": m08,
                "m09a": cell("m09a"),
                "m09b": cell("m09b"),
                "kappa": cell("kappa"),
                "coverage_min": cell("coverage_min"),
            }
        )
    return rows


def _charts(
    results: Results, fmt: _Formatter, failed: dict[tuple[str, str], set[str]]
) -> list[dict[str, Any]]:
    tr = fmt.tr
    rules = tables.evaluated_checks(results)
    charts = []
    for data in tables.chart_data(results, failed):
        key = data.metric.key
        title = tr(f"report.chart.{key}")
        caption = tr(
            "report.chart.caption",
            n=len(data.values),
            unit=tr("report.chart.unit_recordings"),
            missing=data.missing,
        )
        notes = []
        if rules.get(data.metric.check):
            notes.append(tr("report.chart.failed", failed=data.failed))
        for rule_id, value, origin in data.thresholds:
            notes.append(
                tr(
                    "report.chart.threshold",
                    rule=rule_id,
                    value=fmt.value(value),
                    origin=tr(f"report.text.origin_{origin}"),
                )
            )
        svg = (
            Markup(
                histogram_svg(
                    data.values,
                    lo=data.lo,
                    hi=data.hi,
                    label=glyph_safe(title, report_coverage()),
                    thresholds=[value for _, value, _ in data.thresholds],
                )
            )
            if data.values
            else None
        )
        charts.append(
            {
                "key": key,
                "title": title,
                "svg": svg,
                "caption": tr("report.text.separator").join([caption, *notes]),
                "empty": "" if data.values else tr("report.text.chart_no_values", title=title),
            }
        )
    return charts


def _ai_view(results: Results, fmt: _Formatter) -> dict[str, Any] | None:
    """The dataset-level aggregates of M11/M12 (A-81): class counts per scope, demographics, splits and the
    number of duplicate groups. A scope that is withheld by the A-51 table rule shows no class and no count
    (one withheld scope withholds all, as results.json does)."""
    if not tables.has_dataset_level(results):
        return None
    tr = fmt.tr
    view: dict[str, Any] = {"labels": None, "demographics": None, "splits": None, "duplicates": None}
    ai = results.ai
    labels = ai.labels if ai else None
    if labels is not None:
        scopes = tables.scope_order(labels.scopes)
        withheld = any(labels.scopes[name].classes is None for name in scopes)
        source = labels.source + (f": {labels.column}" if labels.column else "")
        view["labels"] = {
            "source": tr("report.text.label_source", source=source, unit=tr(f"report.ai.unit_{labels.unit}")),
            "scopes": scopes,
            "withheld": withheld,
            "rows": []
            if withheld
            else [
                [name, *(str((labels.scopes[s].classes or {}).get(name, 0)) for s in scopes)]
                for name in tables.label_classes(labels.scopes)
            ],
            "totals": [str(labels.scopes[s].total) for s in scopes],
            "withheld_text": [tr("report.ai.withheld", total=labels.scopes[s].total) for s in scopes],
        }
    demographics = ai.demographics if ai else None
    if demographics is not None:
        withheld_text = tr("report.ai.withheld", total=demographics.subjects)
        view["demographics"] = {
            "subjects": str(demographics.subjects),
            "age_documented": str(demographics.age_documented),
            "sex_documented": str(demographics.sex_documented),
            "age_groups": None
            if demographics.age_groups is None
            else [(name, str(count)) for name, count in sorted(demographics.age_groups.items())],
            "sex": None
            if demographics.sex is None
            else [(name, str(count)) for name, count in sorted(demographics.sex.items())],
            "withheld": withheld_text,
        }
    splits = ai.splits if ai else None
    if splits is not None:
        names = tables.scope_order(set(splits.recordings) | set(splits.subjects))
        view["splits"] = {
            "source": splits.source,
            "rows": [
                (name, str(splits.recordings.get(name, 0)), str(splits.subjects.get(name, 0)))
                for name in names
            ],
            "unassigned": str(splits.unassigned),
        }
    if results.duplicates is not None:
        view["duplicates"] = str(len(results.duplicates))
    return view


# --- section 6: appendix (REP-06) ----------------------------------------------------------------------


def _rule_overview(results: Results, fmt: _Formatter, titles: dict[str, str]) -> list[dict[str, Any]]:
    counts = tables.rule_counts(results)
    rows = []
    for rule in results.rules:
        severity = fmt.label("severity", rule.severity.value)
        if rule.strict_severity is not None and not results.config.strict:
            severity += " " + fmt.tr(
                "report.text.strict_severity", severity=fmt.label("severity", rule.strict_severity.value)
            )
        placeholder = rule.source_status is SourceStatus.PLACEHOLDER
        rows.append(
            {
                "id": rule.id,
                "pack": rule.rulepack,
                "clause": fmt.clause_text(rule.clause, rule.source_status),
                "title": titles.get(rule.id, ""),
                "phase": fmt.label("phase", rule.phase.value),
                "severity": severity,
                "verification": fmt.label("verification", rule.verification.value),
                "placeholder": fmt.tr("report.value.placeholder_status") if placeholder else "",
                "counts": [str(counts[rule.id][status]) for status in tables.COUNTED],
            }
        )
    return rows


def _configuration_rows(results: Results, fmt: _Formatter) -> list[tuple[str, str]]:
    tr = fmt.tr
    config = results.config
    return [
        (tr("report.label.date"), config.as_of.isoformat()),
        (tr("report.label.seed"), str(config.seed)),
        (tr("report.label.strict"), fmt.value(config.strict)),
        (
            tr("report.label.sampling"),
            json.dumps(config.sampling, ensure_ascii=False, sort_keys=True, separators=(", ", ": ")),
        ),
        (tr("report.label.evidence_sha256"), config.evidence_sha256 or tr("report.value.no_evidence_file")),
        (tr("report.label.configuration_sha256"), config.canonical_sha256),
    ]


def _environment_rows(results: Results, fmt: _Formatter) -> list[tuple[str, str]]:
    tr = fmt.tr
    env = results.environment
    libraries = ", ".join(f"{name} {version}" for name, version in sorted(env.libraries.items()))
    return [
        (tr("report.label.python"), env.python),
        (tr("report.label.platform"), env.platform),
        (tr("report.label.libraries"), libraries or tr("report.value.none")),
        (
            tr("report.label.blas_threads"),
            str(env.blas_threads) if env.blas_threads is not None else tr("report.value.not_recorded"),
        ),
    ]


# --- print CSS (REP-00, REP-07) ------------------------------------------------------------------------


def css_string(text: str) -> str:
    """``text`` as a CSS string literal; '<' is escaped too, so the style element cannot be closed."""
    out = []
    for char in text:
        if char in '"\\':
            out.append("\\" + char)
        elif char == "<" or ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\{ord(char):X} ")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def _counter_content(template: str) -> str:
    """'Page {page} / {pages}' as CSS content: strings and the page counters."""
    parts = []
    for part in _COUNTER.split(template):
        if part == "{page}":
            parts.append("counter(page)")
        elif part == "{pages}":
            parts.append("counter(pages)")
        elif part:
            parts.append(css_string(part))
    return " ".join(parts)


def page_css(lang: str, as_of: str) -> str:
    """The @page rules: A4 portrait with margin boxes (running head, fixed sentence, page counter) and the
    landscape page 'wide' for sections 3-6. Every margin box names the report font itself."""
    tr = translator(lang).t
    family = f"font-family: '{FONT_FAMILY}';"
    raw_counter = language_tables()[lang]["report.page.page_of"]  # placeholders become counters
    box = f"{family} font-weight: 400; font-style: normal; font-size: 7.5pt; color: #333;"
    return (
        "@page { size: A4 portrait; margin: 16mm 13mm 20mm 13mm; "
        f"@top-left {{ content: {css_string(tr('report.page.running_head', as_of=as_of))}; {box} }} "
        f"@bottom-left {{ content: {css_string(tr('disclaimer'))}; {box} width: 80%; vertical-align: top; }} "
        f"@bottom-right {{ content: {_counter_content(raw_counter)}; {box} vertical-align: top; }} }}\n"
        "@page wide { size: A4 landscape; }\n"
    )


def page_text(lang: str) -> str:
    """Every text that appears only in CSS (the content of the @page margin boxes): the fixed sentence, the
    running head and the words of the page counter, with all digits and the date separator, so the font
    subset covers them (B1)."""
    tr = translator(lang).t
    digits = "0123456789"
    return "\n".join(
        (
            tr("disclaimer"),
            tr("report.page.running_head", as_of=digits + "-"),
            tr("report.page.page_of", page=digits, pages=digits),
            digits + " /",
        )
    )


@lru_cache(maxsize=1)
def _static_css() -> str:
    return (TEMPLATE_DIR / "report.css").read_text(encoding="utf-8")


def build_context(results: Results, lang: str, *, font_css: str = "") -> dict[str, Any]:
    evidence_rules = frozenset(rule.id for rule in results.rules if rule.check == EVIDENCE_CHECK)
    fmt = _Formatter(
        lang, recordings=frozenset(rec.id for rec in results.recordings), evidence_rules=evidence_rules
    )
    title_field = "title_zh" if lang == "zh" else "title_en"
    titles = {rule.id: getattr(rule, title_field) for rule in results.rules}
    see_also = _see_also(results)
    severity_sections, placeholder_groups, placeholder_count = _findings(results, fmt, titles, see_also)
    failed = tables.failed_index(results)
    placeholder_rules = {r.id for r in results.rules if r.source_status is SourceStatus.PLACEHOLDER}
    css = Markup(font_css) + Markup(_static_css()) + Markup(page_css(lang, results.config.as_of.isoformat()))
    return {
        "css": css,
        "evidence_rows": _evidence_rows(results, fmt, titles),
        "secondary_packs": [p for p in results.rulepacks if p.source_status is SourceStatus.SECONDARY],
        "core_loaded": any(p.name == "core" for p in results.rulepacks),
        "t": fmt.tr,
        "fmt": fmt,
        "lang": lang,
        "results": results,
        "titles": titles,
        "cover_rows": _cover_rows(results, fmt),
        "overall": fmt.overall(results.summary),
        "severity_sections": severity_sections,
        "placeholder_groups": placeholder_groups,
        "placeholder_count": placeholder_count,
        "finding_cells": FINDING_CELLS,
        "phases": [
            (phase, results.summary.phases[phase]) for phase in Phase if phase in results.summary.phases
        ],
        "charts": _charts(results, fmt, failed) if results.recordings else [],
        "metric_rows": _metric_rows(results, fmt, failed),
        "dataset_level": _ai_view(results, fmt),
        "sampled": [rec for rec in results.recordings if rec.sample],
        "placeholder": any(p.source_status is SourceStatus.PLACEHOLDER for p in results.rulepacks),
        # checks of placeholder packs are not evaluated, so they are not counted as passed either (A-41)
        "passed_total": sum(p.count for p in results.passed if p.rule_id not in placeholder_rules),
        "rule_overview": _rule_overview(results, fmt, titles),
        "counted_statuses": [status.value for status in tables.COUNTED],
        "configuration_rows": _configuration_rows(results, fmt),
        "environment_rows": _environment_rows(results, fmt),
        "settings_json": json.dumps(
            results.config.effective_settings, ensure_ascii=False, sort_keys=True, indent=2
        ),
    }


def render_report(results: Results, lang: str, *, font_css: str = "") -> str:
    """The report as one self-contained HTML document (B1). ``font_css`` are the @font-face rules of the
    embedded font subsets (family 'NG Sans', data: URIs); the style element starts with them."""
    return render_html(
        TEMPLATE_DIR, "report.html.j2", build_context(results, lang, font_css=font_css), finalize=_finalize
    )
