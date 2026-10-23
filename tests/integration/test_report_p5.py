"""Report content of P5 (NG-F13, NG-F18, REP-00..REP-07, POS-01, ARC-05, UF-01, UF-07, NG-N05; B1, A-84):
cover with reasons for missing values, summary with totals and coverage note, findings grouped by severity and
rule with the A-59 limit, the empty-cell contract, metrics table and charts, dataset-level aggregates,
appendix (rules checked, configuration, environment), print CSS, glyph safety, wording and privacy."""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import pytest
from markupsafe import escape

from conftest import documented_config  # type: ignore[import-not-found]
from gen_fixtures import scale_results  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.kernel import canonical
from neurogrid.kernel.findings import Phase, Severity, SourceStatus, Status, TimeRange
from neurogrid.kernel.i18n import LANGUAGES
from neurogrid.kernel.safety import load_yaml
from neurogrid.model.results import AILabelScope, Results
from neurogrid.report import charts, render
from neurogrid.report.render import (
    EXPLAINED_EMPTY,
    FINDING_CELLS,
    MAX_ROWS_PER_RULE,
    css_string,
    page_css,
    page_text,
    render_report,
)
from neurogrid.report.texts import disclaimer, translator
from report_html import finding_rows, section, visible_text  # type: ignore[import-not-found]

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
SRC = Path(__file__).parent.parent.parent / "src" / "neurogrid"
AS_OF = date(2026, 10, 11)
REPORT_LANGS = ("zh", "en")
SOP = b"IT security SOP 12 (synthetic test document)\n"
EXCEPTION_REASON = "Reference documented in the lab SOP 7 (synthetic)"
EXPIRED_REASON = "Impedance sheet archived"
DATASET_TOML = (
    '[dataset]\nid = "p5-report"\nname = "P5 report fixture"\nversion = "2.1"\nlicense = "CC-BY-4.0"\n'
    '[metadata.defaults]\nelectrode_type = "wet"\n'
    f'[[exceptions]]\nrule = "CORE-M02-01"\nreason = "{EXCEPTION_REASON}"\napproved_by = "QA"\n'
    f'[[exceptions]]\nrule = "CORE-M05-01"\nreason = "{EXPIRED_REASON}"\nvalid_until = 2026-01-01\n'
    '[rules."CORE-M03-01".params]\nmin_hz = 1000\n'
)


def _tr(lang: str):  # type: ignore[no-untyped-def]
    return translator(lang).t


@pytest.fixture(scope="module")
def rich(tmp_path_factory: pytest.TempPathFactory) -> Results:
    """bids_issues with a manifest, core + bids + gxdsl008, GX-04 provided with a document, one applied and
    one expired exception, a threshold from neurogrid.toml and the [dataset] section (UF-01, UF-07)."""
    tmp = tmp_path_factory.mktemp("report_p5")
    dataset = tmp / "ds"
    shutil.copytree(FIX / "bids_issues", dataset)
    built = pipeline.run_manifest(dataset)
    assert built.data is not None
    built.target.parent.mkdir(parents=True, exist_ok=True)
    built.target.write_bytes(built.data)
    (tmp / "docs").mkdir()
    (tmp / "docs" / "it-security-sop.pdf").write_bytes(SOP)
    evidence = tmp / "evidence.yaml"
    evidence.write_text(
        "format_version: 1\nevidence:\n  GXDSL008-ACC-001:\n    status: provided\n"
        "    document: docs/it-security-sop.pdf\n    reviewer: QA lead\n    date: 2026-10-01\n",
        encoding="utf-8",
    )
    config = tmp / "neurogrid.toml"
    config.write_text(DATASET_TOML, encoding="utf-8")
    return pipeline.run_check(
        dataset,
        pipeline.CheckOptions(
            rulepacks=("bids", "gxdsl008"),
            config_path=config,
            evidence_path=evidence,
            as_of=AS_OF,
            work_base=tmp,
        ),
    )


@pytest.fixture(scope="module")
def quality(tmp_path_factory: pytest.TempPathFactory) -> Results:
    """Measured M06-M09 values with failed quality rules (edf_quality_issues)."""
    tmp = tmp_path_factory.mktemp("report_p5_quality")
    return pipeline.run_check(
        FIX / "edf_quality_issues",
        pipeline.CheckOptions(config_path=documented_config(tmp), as_of=AS_OF),
    )


@pytest.fixture(scope="module")
def annotated(tmp_path_factory: pytest.TempPathFactory) -> Results:
    """M10 in continuous mode: kappa and coverage per recording, hypnogram files without signal values."""
    tmp = tmp_path_factory.mktemp("report_p5_annotation")
    config = tmp / "neurogrid.toml"
    config.write_text(
        '[annotation]\nmode = "continuous"\nepoch_s = 30\n'
        'vocabulary = ["W", "N1", "N2", "N3", "R", "Lights off"]\n',
        encoding="utf-8",
    )
    return pipeline.run_check(
        FIX / "annotation_continuous_issues", pipeline.CheckOptions(config_path=config, as_of=AS_OF)
    )


@pytest.fixture(scope="module")
def ai(tmp_path_factory: pytest.TempPathFactory) -> Results:
    """M11/M12 aggregates: event labels per split, withheld demographics, splits and one duplicate group;
    gxdsl008 without evidence.yaml, so GX-04 is an open evidence finding."""
    tmp = tmp_path_factory.mktemp("report_p5_ai")
    config = tmp / "neurogrid.toml"
    config.write_text('[ai]\nlabels = "events:trial_type"\n', encoding="utf-8")
    return pipeline.run_check(
        FIX / "bids_ai_issues",
        pipeline.CheckOptions(rulepacks=("gxdsl008",), config_path=config, as_of=AS_OF, work_base=tmp),
    )


@pytest.fixture(scope="module")
def scaled() -> Results:
    """The worst case of the scaling generator, small: every channel fails M07 and M08-01 (A-59)."""
    return scale_results(recordings=30, channels=8, worst_case=True)


def _explained(lang: str) -> set[str]:
    return {_tr(lang)(key) for key in EXPLAINED_EMPTY}


# --- REP-01 cover ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_cover_lists_rep01_fields(rich: Results, lang: str) -> None:
    cover = visible_text(section(render_report(rich, lang), "cover"))
    assert rich.dataset.name == "P5 report fixture" and rich.dataset.version == "2.1"
    assert rich.dataset.manifest_hash is not None
    for text in (
        rich.dataset.name,
        rich.dataset.id,
        rich.dataset.version,
        rich.config.as_of.isoformat(),
        f"NeuroGrid {rich.tool.version}",
        rich.dataset.manifest_hash,
        _tr(lang)("report.label.date"),
        _tr(lang)("report.text.scope_note"),
        _tr(lang)("report.text.core_clause_note"),
        disclaimer(lang),
    ):
        assert text in cover, text
    for pack in rich.rulepacks:
        assert f"{pack.name} ({pack.source})" in cover and pack.version in cover and pack.sha256 in cover


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_cover_names_reason_for_missing_manifest_hash(quality: Results, lang: str) -> None:
    tr = _tr(lang)
    assert quality.manifest is not None and quality.dataset.manifest_hash is None
    cover = visible_text(section(render_report(quality, lang), "cover"))
    status = tr("report.manifest_status.missing")
    assert tr("report.value.manifest_hash_missing", status=status) in cover
    for key in ("report.value.version_missing", "report.value.name_missing", "report.value.license_missing"):
        assert tr(key) in cover
    older = quality.model_copy(update={"manifest": None})  # results.json of P1-P3 (C1)
    assert tr("report.value.manifest_block_missing") in visible_text(
        section(render_report(older, lang), "cover")
    )


# --- REP-02 summary ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_summary_rows_match_results(rich: Results, lang: str) -> None:
    tr = _tr(lang)
    summary = section(render_report(rich, lang), "summary")
    rows = re.findall(r'<tr data-phase="(\w+)">(.*?)</tr>', summary, flags=re.S)
    assert [phase for phase, _ in rows] == [p.value for p in Phase]  # PRD order, five rows
    for phase, row in rows:
        expected = rich.summary.phases[Phase(phase)]
        cells = [visible_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)]
        assert cells[1] == tr(f"light.{expected.light.value}")  # never colour only
        assert cells[2:] == [str(expected.errors), str(expected.warnings), str(expected.open_evidence)]
    total = re.search(r'<tr class="total">(.*?)</tr>', summary, flags=re.S)
    assert total is not None
    cells = [visible_text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", total.group(1), flags=re.S)]
    totals = [str(rich.summary.errors), str(rich.summary.warnings), str(rich.summary.open_evidence)]
    assert cells == [tr("report.label.total"), *totals]
    assert rich.summary.errors == sum(p.errors for p in rich.summary.phases.values())


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_coverage_note_when_na(rich: Results, lang: str) -> None:
    tr = _tr(lang)
    summary = visible_text(section(render_report(rich, lang), "summary"))
    assert set(rich.summary.coverage.values()) == {"n/a"}  # core, bids and secondary gxdsl008 (A-16)
    assert summary.count(tr("report.value.na")) >= len(rich.summary.coverage)
    assert tr("report.text.coverage_note") in summary


def test_access_phase_is_grey_without_rules(quality: Results) -> None:
    """core has no access rule: the light is grey, shown with its text (A-16)."""
    assert not any(rule.phase is Phase.ACCESS for rule in quality.rules)
    summary = section(render_report(quality, "en"), "summary")
    row = re.search(r'<tr data-phase="access">(.*?)</tr>', summary, flags=re.S)
    assert row is not None and 'class="light light-grey">grey<' in row.group(1)


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_overall_sentence_variants(quality: Results, lang: str) -> None:
    """POS-01: 'passes the checks of the loaded rule packs', with the warnings named; never 'conforms'."""
    tr = _tr(lang)
    cases = {
        (0, 0): tr("report.text.overall_passes"),
        (0, 3): tr("report.text.overall_passes_warnings", warnings=3),
        (2, 3): tr("report.text.overall_fails", errors=2, warnings=3),
    }
    for (errors, warnings), sentence in cases.items():
        summary = quality.summary.model_copy(update={"errors": errors, "warnings": warnings})
        html = render_report(quality.model_copy(update={"summary": summary}), lang)
        overall = re.search(r'<p class="overall">(.*?)</p>', html, flags=re.S)
        assert overall is not None and html_lib.unescape(overall.group(1)) == sentence
    assert "3" in cases[(0, 3)] and "2" in cases[(2, 3)]


# --- REP-03 / NG-F13 findings -----------------------------------------------------------------------------


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_findings_grouped_by_severity_then_rule(rich: Results, lang: str) -> None:
    findings = section(render_report(rich, lang), "findings")
    headings = re.findall(r'<h3 class="sev-(\w+)">', findings)
    assert headings == [s.value for s in Severity]  # error > warning > info (A-61)
    severity_of = {f.rule_id: f.severity.value for f in rich.findings}
    parts = re.split(r'<h3 class="sev-(\w+)">', findings)[1:]
    for severity, part in zip(parts[0::2], parts[1::2], strict=True):
        rules = re.findall(r'<div class="rule-group" data-rule="([^"]+)">', part)
        assert rules == sorted(rules) and all(severity_of[rule] == severity for rule in rules)
        for rule in rules:
            group = part[part.index(f'data-rule="{rule}"') :]
            group = group[: group.index("</table>")]
            assert {row["rule"] for row in finding_rows(group)} == {rule}


def test_rows_inside_a_rule_follow_status_then_object(rich: Results) -> None:
    order = [
        Status.FAILED,
        Status.EVIDENCE_OPEN,
        Status.NOT_CHECKABLE,
        Status.EXCEPTED,
        Status.NOT_APPLICABLE,
    ]
    by_key = {f.key: f for f in rich.findings}
    rows = finding_rows(render_report(rich, "en"))
    for rule in {row["rule"] for row in rows}:
        shown = [by_key[row["key"]] for row in rows if row["rule"] == rule]
        keys = [(order.index(f.status) if f.status in order else 9, f.object, f.subkey or "") for f in shown]
        assert keys == sorted(keys), rule


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_rows_per_rule_capped_at_50_with_total(scaled: Results, lang: str) -> None:
    """A-59: at most 50 rows per rule; the exact remainder is named and lives in results.json."""
    tr = _tr(lang)
    html = render_report(scaled, lang)
    rows = finding_rows(html)
    totals: dict[str, int] = {}
    for finding in scaled.findings:
        totals[finding.rule_id] = totals.get(finding.rule_id, 0) + 1
    assert max(totals.values()) > MAX_ROWS_PER_RULE  # the limit is reached
    findings_text = visible_text(section(html, "findings"))
    for rule, total in totals.items():
        shown = sum(1 for row in rows if row["rule"] == rule)
        assert shown == min(total, MAX_ROWS_PER_RULE)
        more = tr("report.text.rule_more", count=total - shown, rule=rule)
        assert (more in findings_text) is (total > shown)
    assert len(rows) + sum(t - min(t, MAX_ROWS_PER_RULE) for t in totals.values()) == len(scaled.findings)
    assert {row["key"] for row in rows} <= {f.key for f in scaled.findings}


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_rule_aggregate_counts_match_results(scaled: Results, lang: str) -> None:
    tr = _tr(lang)
    findings = section(render_report(scaled, lang), "findings")
    for rule in sorted({f.rule_id for f in scaled.findings}):
        items = [f for f in scaled.findings if f.rule_id == rule]
        group = findings[findings.index(f'data-rule="{rule}"') :]
        aggregate = re.search(r'<p class="aggregate">(.*?)</p>', group, flags=re.S)
        assert aggregate is not None
        text = html_lib.unescape(aggregate.group(1))
        assert (
            tr("report.text.rule_aggregate", findings=len(items), objects=len({f.object for f in items}))
            in text
        )
        values = [float(f.measured_value) for f in items]
        fmt = render._Formatter(lang)
        assert (
            tr("report.text.rule_aggregate_range", min=fmt.value(min(values)), max=fmt.value(max(values)))
            in text
        )
        failed = tr("report.text.status_count", status=tr("status.failed"), count=len(items))
        assert failed in text


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_empty_cells_name_their_reason(rich: Results, ai: Results, lang: str) -> None:
    """A-09/NG-F13: no bare '–'; every cell that starts with '–' is one of the explained texts (B1)."""
    tr = _tr(lang)
    explained = _explained(lang)
    seen: set[str] = set()
    for results in (rich, ai):
        rows = finding_rows(render_report(results, lang))
        assert len(rows) == len(results.findings)
        by_key = {f.key: f for f in results.findings}
        for row in rows:
            assert all(row[cell].strip() for cell in FINDING_CELLS)
            for cell in FINDING_CELLS:
                if row[cell].startswith("–"):
                    assert row[cell] in explained, (cell, row[cell])
                    seen.add(row[cell])
            finding = by_key[row["key"]]
            if finding.file is None:
                assert row["file"] == tr("report.value.dataset_level")
                assert row["time"] == tr("report.value.time_dataset")
            if finding.channel is None:
                assert row["channel"] == tr("report.value.no_channel")
            if finding.measured_value is None and finding.status in (
                Status.NOT_CHECKABLE,
                Status.NOT_APPLICABLE,
            ):
                assert row["measured"] == tr("report.value.measured_see_reason")
            if (
                finding.status is Status.EVIDENCE_OPEN
            ):  # evaluated from evidence.yaml: nothing measured (A-15)
                assert row["measured"] == tr("report.value.not_applicable_value")
            if not finding.params and finding.threshold is None:
                assert row["threshold"] == tr("report.value.no_threshold")
    assert any(f.status is Status.EVIDENCE_OPEN for f in ai.findings)
    for key in (
        "report.value.no_channel",
        "report.value.no_threshold",
        "report.value.time_dataset",
        "report.value.measured_see_reason",
        "report.value.not_applicable_value",
    ):
        assert tr(key) in seen, key


def test_failed_without_value_and_without_details_explain_themselves(quality: Results) -> None:
    """A failed finding without a numeric value (a presence check such as a missing manifest) and without
    details; a rule pack without a clause."""
    tr = _tr("en")
    finding = next(f for f in quality.findings if f.status is Status.FAILED)
    plain = finding.model_copy(update={"measured_value": None, "reason": None, "details": {}})
    results = quality.model_copy(update={"findings": [plain]})
    (row,) = finding_rows(render_report(results, "en"))
    assert row["measured"] == tr("report.value.measured_presence")
    assert row["reason"] == tr("report.value.no_details")
    nameless = quality.model_copy(update={"findings": [plain.model_copy(update={"clause": ""})]})
    (row,) = finding_rows(render_report(nameless, "en"))
    assert row["clause"] == tr("report.value.clause_missing")
    # an empty measured value counts as none; a rule missing from the rules block keeps a titled row
    empty = plain.model_copy(update={"measured_value": [], "status": Status.NOT_CHECKABLE})
    unlisted = quality.model_copy(update={"findings": [empty], "rules": []})
    (row,) = finding_rows(render_report(unlisted, "en"))
    assert row["measured"] == tr("report.value.measured_see_reason")
    assert row["title"].startswith(tr("report.value.title_missing"))
    assert all(row[cell].strip() for cell in FINDING_CELLS)


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_threshold_shows_origin(rich: Results, quality: Results, lang: str) -> None:
    """A-13: the effective parameters with their origin, also when the value is missing."""
    tr = _tr(lang)
    rows = {row["key"]: row for row in finding_rows(render_report(rich, lang))}
    m03 = [f for f in rich.findings if f.rule_id == "CORE-M03-01"]
    assert m03 and all(f.measured_value == 512.0 for f in m03)  # 512 Hz < min_hz 1000 from neurogrid.toml
    for finding in m03:
        assert rows[finding.key]["threshold"] == f"min_hz = 1000 ({tr('report.text.origin_config')})"
    m05 = [f for f in rich.findings if f.rule_id == "CORE-M05-02"]
    assert m05
    for finding in m05:
        assert rows[finding.key]["threshold"] == f"max_kohm = 5 ({tr('report.text.origin_rulepack')})"
    rows = {row["key"]: row for row in finding_rows(render_report(quality, lang))}
    missing = next(f for f in quality.findings if f.params and f.measured_value is None)
    name, param = next(iter(sorted(missing.params.items())))
    assert rows[missing.key]["threshold"].startswith(f"{name} = ")
    assert tr(f"report.text.origin_{param.origin}") in rows[missing.key]["threshold"]


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_time_ranges_show_count_and_total(quality: Results, lang: str) -> None:
    """A-10: at most 20 ranges, then their number and the total duration."""
    tr = _tr(lang)
    finding = next(f for f in quality.findings if f.rule_id == "CORE-M08-01")
    ranges = [TimeRange(start_s=float(i), end_s=i + 0.5) for i in range(30)]
    many = finding.model_copy(
        update={"time_ranges": ranges, "time_ranges_total": 34, "time_ranges_duration_s": 17.0}
    )
    (row,) = finding_rows(render_report(quality.model_copy(update={"findings": [many]}), lang))
    assert row["time"].count(" s,") == 19 and "19.000–19.500 s" in row["time"] and "20.000" not in row["time"]
    assert row["time"].endswith(tr("report.value.time_ranges_more", shown=20, total=34, seconds="17"))


# --- NG-F18 / UF-07 exceptions and evidence ---------------------------------------------------------------


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_every_exception_and_its_reason_is_shown(rich: Results, lang: str) -> None:
    tr = _tr(lang)
    html = render_report(rich, lang)
    appendix = visible_text(section(html, "appendix"))
    assert {use.entry.reason for use in rich.exceptions} == {EXCEPTION_REASON, EXPIRED_REASON}
    for use in rich.exceptions:
        assert use.entry.reason in appendix
    excepted = [f for f in rich.findings if f.status is Status.EXCEPTED]
    assert excepted
    rows = {row["key"]: row for row in finding_rows(html)}
    for finding in excepted:
        assert rows[finding.key]["status"] == tr("status.excepted")
        assert EXCEPTION_REASON in rows[finding.key]["reason"]


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_evidence_document_and_wording(rich: Results, lang: str) -> None:
    evidence = visible_text(section(render_report(rich, lang), "evidence"))
    assert "docs/it-security-sop.pdf" in evidence
    assert _tr(lang)("report.value.evidence_provided") in evidence


# --- REP-04 metrics and charts -----------------------------------------------------------------------------


def _metric_rows(html: str) -> list[tuple[str, dict[str, str]]]:
    metrics = section(html, "metrics")
    out = []
    for rec, row in re.findall(r'<tr data-recording="([^"]+)">(.*?)</tr>', metrics, flags=re.S):
        cells = dict(re.findall(r'<td class="num ([\w-]+)">(.*?)</td>', row, flags=re.S))
        out.append((html_lib.unescape(rec), {k: html_lib.unescape(v) for k, v in cells.items()}))
    return out


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_metrics_table_has_one_row_per_recording(quality: Results, scaled: Results, lang: str) -> None:
    for results in (quality, scaled):
        rows = _metric_rows(render_report(results, lang))
        assert [rec for rec, _ in rows] == [rec.id for rec in results.recordings]
    (rec, cells), *_ = _metric_rows(render_report(quality, lang))
    metrics = quality.recordings[0].metrics
    assert cells["m06"].startswith(format(metrics["M06"]["value"], ".3f"))
    ratios = [ch["ratio"] for ch in metrics["M07"]["channels"].values() if "ratio" in ch]
    assert cells["m07"].startswith(format(max(ratios), ".3f"))
    assert cells["m07-failed"].endswith(f" / {len(ratios)}")


def test_markers_follow_failed_findings(quality: Results, scaled: Results) -> None:
    """' *' exactly where a non-placeholder rule using the metric's check has a failed finding (no second
    judgement in the report, ARC-02)."""
    checks = {"m06": "quality.bad_channels", "m07": "quality.line_noise", "m09a": "quality.autoreject"}
    for results in (quality, scaled):
        check_of = {r.id: r.check for r in results.rules if r.source_status is not SourceStatus.PLACEHOLDER}
        failed = {(check_of.get(f.rule_id), f.object) for f in results.findings if f.status is Status.FAILED}
        for rec, cells in _metric_rows(render_report(results, "en")):
            for column, check in checks.items():
                if not cells[column].startswith("–"):
                    assert cells[column].endswith(" *") is ((check, rec) in failed), (rec, column)
            if not cells["m07-failed"].startswith("–"):
                count = len(
                    {
                        f.subkey
                        for f in results.findings
                        if f.object == rec and f.rule_id == "CORE-M07-01" and f.status is Status.FAILED
                    }
                )
                assert cells["m07-failed"].startswith(f"{count} / ")


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_missing_metrics_render_dash_with_reason(annotated: Results, lang: str) -> None:
    tr = _tr(lang)
    rows = dict(_metric_rows(render_report(annotated, lang)))
    low = next(
        rec
        for rec in annotated.recordings
        if rec.metrics.get("M06", {}).get("reason") == "quality.rate_too_low"
    )
    reason = tr("report.value.missing_reason", reason=tr("reason.quality.rate_too_low"))
    assert rows[low.id]["m06"] == reason and rows[low.id]["m09a"] == reason
    kappa = low.metrics["annotation"]["kappa"]["mean"]
    assert rows[low.id]["kappa"].startswith(format(kappa, ".3f"))
    coverage = min(low.metrics["annotation"]["coverage"].values())
    assert rows[low.id]["coverage"].startswith(format(coverage, ".3f"))
    hypnogram = next(rec for rec in annotated.recordings if not rec.metrics)
    assert rows[hypnogram.id]["m06"] == "–"  # nothing measured: explained by the legend
    assert tr("report.text.metrics_legend") in visible_text(
        section(render_report(annotated, lang), "metrics")
    )


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_charts_one_value_per_recording_with_thresholds(quality: Results, scaled: Results, lang: str) -> None:
    tr = _tr(lang)
    metrics = section(render_report(scaled, lang), "metrics")
    figures = re.findall(r'<figure class="chart" data-metric="(\w+)">(.*?)</figure>', metrics, flags=re.S)
    assert [key for key, _ in figures] == ["m06", "m07", "m08_flat", "m08_clip", "m09a", "m09b"]
    params = scaled.config.effective_params
    rule_of = {
        "m06": "CORE-M06-01",
        "m07": "CORE-M07-01",
        "m08_flat": "CORE-M08-01",
        "m08_clip": "CORE-M08-02",
    }
    rule_of |= {"m09a": "CORE-M09-01", "m09b": "CORE-M09-02"}
    for key, figure in figures:
        rects = re.findall(
            r'<rect class="bar" x="[\d.]+" y="[\d.]+" width="[\d.]+" height="([\d.]+)"/>', figure
        )
        assert 1 <= len(rects) <= 20
        caption = visible_text(figure.split("<figcaption>")[1])
        assert tr("report.chart.caption", n=30, unit=tr("report.chart.unit_recordings"), missing=0) in caption
        (param,) = params[rule_of[key]].values()
        threshold = tr(
            "report.chart.threshold",
            rule=rule_of[key],
            value=render._Formatter(lang).value(param.value),
            origin=tr("report.text.origin_rulepack"),
        )
        assert threshold in caption
    m07 = dict(figures)["m07"]
    assert tr("report.chart.failed", failed=30) in visible_text(m07)  # every recording fails M07
    assert "0.407669" in visible_text(m07) and 'class="thr"' in m07
    # M10 kappa only when a recording has a value (several annotators, A-80): no chart and no 'no values' line
    assert 'data-metric="kappa"' not in metrics


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_kappa_chart_when_kappa_was_measured(annotated: Results, lang: str) -> None:
    """REP-04: the M10 chart on the domain [-1, 1] with the threshold of CORE-M10-01, one mean kappa per
    recording that has one."""
    tr = _tr(lang)
    metrics = section(render_report(annotated, lang), "metrics")
    figure = re.search(r'<figure class="chart" data-metric="kappa">(.*?)</figure>', metrics, flags=re.S)
    assert figure is not None
    means = [
        rec.metrics["annotation"]["kappa"]["mean"]
        for rec in annotated.recordings
        if isinstance(rec.metrics.get("annotation", {}).get("kappa"), dict)
        and rec.metrics["annotation"]["kappa"].get("mean") is not None
    ]
    assert means
    caption = visible_text(figure.group(1).split("<figcaption>")[1])
    missing = len(annotated.recordings) - len(means)
    unit = tr("report.chart.unit_recordings")
    assert tr("report.chart.caption", n=len(means), unit=unit, missing=missing) in caption
    origin = tr("report.text.origin_rulepack")
    assert tr("report.chart.threshold", rule="CORE-M10-01", value="0.6", origin=origin) in caption
    ticks = re.findall(
        r'<text class="tk" x="[\d.]+" y="\d+" text-anchor="middle">([^<]+)</text>', figure.group(1)
    )
    assert ticks == ["-1", "0", "1"]
    line = re.search(r'<line class="thr" x1="([\d.]+)"', figure.group(1))
    assert line is not None and float(line.group(1)) == round(charts.threshold_x(0.6, -1.0, 1.0), 2)


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_dataset_level_tables_show_aggregates(ai: Results, lang: str) -> None:
    tr = _tr(lang)
    assert ai.ai is not None and ai.ai.labels is not None and ai.ai.splits is not None
    block = section(render_report(ai, lang), "metrics")
    block = visible_text(block[block.index('class="dataset-level"') :])
    for name, count in (ai.ai.labels.scopes["all"].classes or {}).items():
        assert f"{name} {count}" in block
    assert tr("report.label.duplicate_groups") + f": {len(ai.duplicates or [])}" in block
    assert ai.ai.demographics is not None and ai.ai.demographics.age_groups is None  # withheld (A-51)
    assert tr("report.ai.withheld", total=ai.ai.demographics.subjects) in block


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_withheld_ai_tables_show_no_counts(ai: Results, lang: str) -> None:
    """A-51/A-81: a withheld scope shows neither class names nor counts, in every scope."""
    assert ai.ai is not None and ai.ai.labels is not None
    scopes = dict(ai.ai.labels.scopes)
    scopes["train"] = AILabelScope(total=scopes["train"].total, classes=None)
    labels = ai.ai.labels.model_copy(update={"scopes": scopes})
    hidden = ai.model_copy(update={"ai": ai.ai.model_copy(update={"labels": labels})})
    block = section(render_report(hidden, lang), "metrics")
    block = block[block.index('class="dataset-level"') :]
    table = block[block.index('<table class="labels">') : block.index("</table>")]
    for name in ai.ai.labels.scopes["all"].classes or {}:
        assert f"<td>{name}</td>" not in table
    assert _tr(lang)("report.ai.withheld", total=scopes["train"].total) in html_lib.unescape(table)


def test_metric_contract_keys(quality: Results, annotated: Results) -> None:
    """The keys of recordings[].metrics the report reads (check area contract, R8)."""
    metrics = quality.recordings[0].metrics
    assert {"M06", "M07", "M08", "M09a", "M09b", "data_seconds"} <= set(metrics)
    assert {"state", "value"} <= set(metrics["M06"]) and {"state"} <= set(metrics["M09b"])
    assert {"line_frequency_hz", "line_frequency_source", "channels"} <= set(metrics["M07"])
    assert all(
        {"ratio"} <= set(ch) or {"state", "reason"} <= set(ch) for ch in metrics["M07"]["channels"].values()
    )
    assert all({"flat_fraction", "clipped_fraction"} <= set(ch) for ch in metrics["M08"]["channels"].values())
    entry = next(rec.metrics["annotation"] for rec in annotated.recordings if rec.metrics.get("annotation"))
    assert {"mean"} <= set(entry["kappa"]) and isinstance(entry["coverage"], dict)


# --- REP-06 appendix ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_appendix_lists_every_rule_with_counts(rich: Results, lang: str) -> None:
    appendix = section(render_report(rich, lang), "appendix")
    rows = re.findall(r'<tr data-rule="([^"]+)">(.*?)</tr>', appendix, flags=re.S)
    assert [rule for rule, _ in rows] == [rule.id for rule in rich.rules]
    for rule, row in rows:
        counts = [visible_text(c) for c in re.findall(r'<td class="num">(.*?)</td>', row, flags=re.S)]
        passed = sum(p.count for p in rich.passed if p.rule_id == rule)
        findings = [f for f in rich.findings if f.rule_id == rule]
        expected = [passed + sum(1 for f in findings if f.status is Status.PASSED)] + [
            sum(1 for f in findings if f.status is status)
            for status in (
                Status.FAILED,
                Status.EXCEPTED,
                Status.NOT_APPLICABLE,
                Status.NOT_CHECKABLE,
                Status.EVIDENCE_OPEN,
            )
        ]
        assert counts == [str(n) for n in expected], rule


def test_appendix_marks_placeholder_rules_not_evaluated(quality: Results) -> None:
    marked = quality.model_copy(deep=True)
    marked.rules[0].source_status = SourceStatus.PLACEHOLDER
    appendix = section(render_report(marked, "en"), "appendix")
    row = re.search(rf'<tr data-rule="{marked.rules[0].id}">(.*?)</tr>', appendix, flags=re.S)
    assert row is not None and _tr("en")("report.value.placeholder_status") in html_lib.unescape(row.group(1))
    assert '<td class="num">' not in row.group(1)


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_appendix_settings_equal_results_config(rich: Results, lang: str) -> None:
    tr = _tr(lang)
    appendix = section(render_report(rich, lang), "appendix")
    config = rich.config
    text = visible_text(appendix)
    for value in (config.as_of.isoformat(), str(config.seed), config.canonical_sha256, tr("report.value.no")):
        assert value in text
    assert config.evidence_sha256 is not None and config.evidence_sha256 in text
    pre = re.search(r'<pre class="settings">(.*?)</pre>', appendix, flags=re.S)
    assert pre is not None
    assert json.loads(html_lib.unescape(pre.group(1))) == json.loads(
        canonical.dumps(config.effective_settings)
    )
    params = re.findall(r'<table class="params">(.*?)</table>', appendix, flags=re.S)[0]
    for rule_id, entries in config.effective_params.items():
        for name in entries:
            assert f'<td class="mono">{rule_id}</td><td>{name}</td>' in params


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_appendix_environment_block(rich: Results, lang: str) -> None:
    text = visible_text(section(render_report(rich, lang), "appendix"))
    env = rich.environment
    assert env.python in text and env.platform in text and str(env.blas_threads) in text
    for name, version in env.libraries.items():
        assert f"{name} {version}" in text
    older = rich.model_copy(update={"environment": env.model_copy(update={"blas_threads": None})})
    assert _tr(lang)("report.value.not_recorded") in visible_text(
        section(render_report(older, lang), "appendix")
    )


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_scope_note_on_cover_and_appendix(rich: Results, lang: str) -> None:
    """ARC-05: the report says it describes the dataset and makes no statement about patients."""
    html = render_report(rich, lang)
    note = _tr(lang)("report.text.scope_note")
    assert note in visible_text(section(html, "cover")) and note in visible_text(section(html, "appendix"))


# --- POS-01, ARC-05, NG-N05: wording and content of the rendered reports ----------------------------------


def test_rendered_reports_make_no_conformity_claims(
    rich: Results, quality: Results, annotated: Results, ai: Results, scaled: Results
) -> None:
    """POS-01 (A-57) and ARC-05 over the visible text of every rendered report in zh and en: only the fixed
    sentence and the allowed negations are exempt."""
    wording = load_yaml((SRC / "report" / "wording" / "forbidden.yaml").read_text(encoding="utf-8"))
    statements = load_yaml((SRC / "report" / "wording" / "statements.yaml").read_text(encoding="utf-8"))
    assert isinstance(wording, dict) and isinstance(statements, dict)
    patterns = [re.compile(p) for lang in LANGUAGES for p in wording[lang]]
    patterns += [re.compile(p) for lang in LANGUAGES for p in statements["patient"][lang]]
    allowed = [*wording["allowed"], *statements["allowed"], *(disclaimer(lang) for lang in REPORT_LANGS)]
    for results in (rich, quality, annotated, ai, scaled):
        for lang in REPORT_LANGS:
            text = visible_text(render_report(results, lang))
            for phrase in allowed:
                text = re.sub(re.escape(phrase), "", text, flags=re.IGNORECASE)
            assert not [p.pattern for p in patterns if p.search(text)], lang


def test_report_contains_no_raw_signals(quality: Results, scaled: Results) -> None:
    """NG-N05: charts are histograms of one value per recording (at most 20 bars), never waveforms: only
    rect, line and text inside the SVG; no images, canvases, paths or long number lists."""
    for results in (quality, scaled):
        html = render_report(results, "en")
        for tag in (
            "<img",
            "<canvas",
            "<path",
            "<polyline",
            "<polygon",
            "<script",
            "<object",
            "<iframe",
            "<embed",
        ):
            assert tag not in html
        for svg in re.findall(r"<svg[^>]*>(.*?)</svg>", html, flags=re.S):
            assert set(re.findall(r"<(\w+)", svg)) <= {"rect", "line", "text"}
            assert len(re.findall(r"<rect ", svg)) <= 20
        assert not re.search(r"(-?\d+(\.\d+)?\s*,\s*){20,}-?\d", visible_text(html))


def test_planted_identifiers_absent_from_report(tmp_path: Path) -> None:
    """NG-N05/A-51: names and dates in file names and EDF headers never reach the report (raw folder, no
    --show-paths)."""
    folder = tmp_path / "raw"
    folder.mkdir()
    shutil.copy(FIX / "edf_identifying" / "rec_named.edf", folder / "rec_named.edf")
    edf = (FIX / "edf_ok" / "rec_a.edf").read_bytes()
    (folder / "ZhangSan_19800101.edf").write_bytes(edf)
    (folder / "张三.edf").write_bytes(edf)
    results = pipeline.run_check(
        folder, pipeline.CheckOptions(config_path=documented_config(tmp_path), as_of=AS_OF)
    )
    planted = ("Zhang", "24.08.21", "rec_named", "ZhangSan", "19800101", "张三")
    for lang in REPORT_LANGS:
        html = render_report(results, lang)
        assert not [name for name in planted if name in html], lang


def test_planted_annotation_names_absent_from_report(tmp_path: Path) -> None:
    """NG-N05/A-51: the planted fixtures of the annotation pipeline (a name in a hypnogram file name, in an
    annotation text, in the mapping table and in the annotator column of a BIDS events file) reach no part of
    the P5 report: findings, metrics table, charts, dataset-level tables, appendix with the configuration."""
    from test_annotation_pipeline import _check, _planted  # type: ignore[import-not-found]

    raw, bids, config = _planted(tmp_path)
    for results in (_check(raw, config), _check(bids)):
        for lang in REPORT_LANGS:
            html = render_report(results, lang)
            assert "Mustermann" not in html and "Zhang" not in html, lang
            assert 'id="metrics"' in html and 'id="appendix"' in html


# --- A-59 scaling generator (B1: one generator, tools/gen_fixtures.py) ------------------------------------


def test_scale_generator_worst_case(scaled: Results) -> None:
    """The worst case of the scaling test: every channel of every recording fails M07 and M08-01 (2 x
    recordings x channels findings), evaluated by the rule engine; the same arguments give the same bytes."""
    by_rule = Counter(f.rule_id for f in scaled.findings)
    assert by_rule["CORE-M07-01"] == 30 * 8 and by_rule["CORE-M08-01"] == 30 * 8
    worst = [f for f in scaled.findings if f.rule_id in ("CORE-M07-01", "CORE-M08-01")]
    assert all(f.status is Status.FAILED and f.channel for f in worst)
    assert len(scaled.recordings) == 30 and all(rec.n_eeg_channels == 8 for rec in scaled.recordings)
    assert canonical.dumps(scale_results(recordings=30, channels=8, worst_case=True)) == canonical.dumps(
        scaled
    )
    typical = scale_results(recordings=30, channels=8, worst_case=False)
    assert len(typical.findings) < len(scaled.findings)


def test_scale_generator_command_line(tmp_path: Path) -> None:
    out = tmp_path / "scale.json"
    tool = Path(__file__).parent.parent.parent / "tools" / "gen_fixtures.py"
    command = [sys.executable, str(tool), "--scale-results", str(out), "--recordings", "3", "--channels", "2"]
    run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
    assert run.returncode == 0, run.stderr
    results = Results.model_validate_json(out.read_bytes())
    assert len(results.recordings) == 3
    assert sum(1 for f in results.findings if f.rule_id == "CORE-M07-01") == 3 * 2


# --- REP-00 print layout, B1 contract, glyph safety, determinism, compatibility --------------------------


def test_print_css_contract() -> None:
    """B1: the style element starts with the font CSS; one family everywhere, also in the margin boxes; no
    synthetic styles; portrait cover/summary, landscape sections 3-6; headers repeat, rows never split."""
    results = pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(as_of=AS_OF))
    font_css = '@font-face { font-family: "NG Sans"; font-weight: 400; src: url(data:font/ttf;base64,AAAA); }'
    html = render_report(results, "en", font_css=font_css)
    style = html[html.index("<style>") + len("<style>") : html.index("</style>")]
    assert style.lstrip().startswith(font_css)
    assert "*, *::before, *::after { font-family: 'NG Sans' !important; font-synthesis: none;" in style
    families = re.findall(r"font-family:\s*([^;}]+)", style)
    assert families and all(f.strip() in ("'NG Sans' !important", "'NG Sans'", '"NG Sans"') for f in families)
    page = style[style.index("@page {") :]
    for box in ("@top-left", "@bottom-left", "@bottom-right"):
        block = page[page.index(box) : page.index("}", page.index(box))]
        assert "font-family: 'NG Sans';" in block
    assert "size: A4 portrait" in page and "@page wide { size: A4 landscape; }" in page
    assert "section#findings, section#metrics, section#evidence, section#appendix { page: wide; }" in style
    assert "section#cover { break-after: page; }" in style
    assert "thead { display: table-header-group; }" in style and "tr { break-inside: avoid; }" in style
    rules = re.sub(r"/\*.*?\*/", "", style, flags=re.S)  # the comments explain, the rules count
    assert "italic" not in rules and "monospace" not in rules and "oblique" not in rules
    assert "counter(page)" in page and "counter(pages)" in page


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_fixed_sentence_and_counter_in_the_page_margin(lang: str) -> None:
    """REP-07: the fixed sentence in the footer of every printed page (@bottom-left) and 'page x / y'."""
    css = page_css(lang, "2026-10-11")
    assert f"@bottom-left {{ content: {css_string(disclaimer(lang))};" in css
    assert css_string(_tr(lang)("report.page.running_head", as_of="2026-10-11")) in css
    words = re.split(r"\{page\}|\{pages\}", _tr(lang)("report.page.page_of"))
    assert all(css_string(word) in css for word in words if word)


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_page_text_covers_css_only_strings(lang: str) -> None:
    """B1: every character that appears only in CSS content strings is in page_text, so the font subset
    covers it."""
    css = page_css(lang, "2026-10-11")
    contents = re.findall(r'"((?:[^"\\]|\\.)*)"', css)
    text = page_text(lang)
    assert disclaimer(lang) in text
    assert set("".join(contents)) <= set(text)
    assert set("0123456789-/ ") <= set(text)


def test_css_string_escapes_quotes_backslashes_and_markup() -> None:
    assert css_string('a"b') == '"a\\"b"' and css_string("a\\b") == '"a\\\\b"'
    assert css_string("</style>") == '"\\3C /style>"' and css_string("a\nb") == '"a\\A b"'


def _font(path: Path, chars: str) -> Path:
    """A minimal TrueType font that maps exactly ``chars`` (each glyph a square)."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    names = [".notdef", *(f"g{ord(c):05X}" for c in sorted(set(chars)))]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({ord(c): f"g{ord(c):05X}" for c in set(chars)})
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((0, 500))
        pen.lineTo((500, 500))
        pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 0) for name in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    builder.save(str(path))
    return path


def test_glyph_safe_replaces_uncovered_and_control_characters(
    rich: Results, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REP-00/A-27: a character the report fonts cannot draw (emoji, CJK Ext-B) or a control character in a
    dataset name, an exception reason or an evidence comment becomes '[U+XXXX]'; nothing falls back to a
    system font."""
    hostile = rich.model_copy(deep=True)
    hostile.dataset.name = "Data\x07set 😀 𠀀"
    hostile.exceptions[0].entry.reason = "Reason\x1b[31m"
    hostile.evidence[0].comment = "ok ✗"
    absent = {400: tmp_path / "absent-regular.ttf", 700: tmp_path / "absent-bold.ttf"}
    monkeypatch.setattr(render, "REPORT_FONTS", absent)
    plain = render_report(hostile, "en")  # without the report fonts: only controls are replaced
    assert "[U+0007]" in plain and "[U+001B]" in plain and "\x07" not in plain and "\x1b" not in plain
    assert "😀" in plain
    covered = set(render_report(rich, "en") + page_text("en")) - set("😀𠀀✗")
    regular = _font(tmp_path / "Regular.ttf", "".join(sorted(covered)))
    bold = _font(tmp_path / "Bold.ttf", "".join(sorted(covered)))
    monkeypatch.setattr(render, "REPORT_FONTS", {400: regular, 700: bold})
    html = render_report(hostile, "en")
    for code in ("[U+0007]", "[U+1F600]", "[U+20000]", "[U+001B]", "[U+2717]"):
        assert code in html, code
    assert not {"😀", "𠀀", "✗", "\x07", "\x1b"} & set(html)


def test_html_is_byte_identical_over_two_renders(rich: Results, scaled: Results) -> None:
    for results in (rich, scaled):
        for lang in REPORT_LANGS:
            assert render_report(results, lang) == render_report(results, lang)
            assert render_report(results, lang, font_css="/*x*/") == render_report(
                results, lang, font_css="/*x*/"
            )


@pytest.mark.parametrize("lang", REPORT_LANGS)
def test_results_from_p1_p3_p4_render(rich: Results, quality: Results, lang: str) -> None:
    """R8: results.json of every earlier phase renders (optional blocks absent; unknown keys stay keys)."""
    tr = _tr(lang)
    for results in (rich, quality):
        data = json.loads(canonical.dumps(results))
        for key in ("evidence", "manifest", "ai", "duplicates"):
            data.pop(key, None)
        data["config"].pop("evidence_sha256", None)
        data["summary"].pop("open_evidence", None)
        data["environment"].pop("blas_threads", None)
        for rec in data["recordings"]:
            rec["metrics"] = {}
            rec.pop("sample", None)
        old = Results.model_validate_json(json.dumps(data))
        html = render_report(old, lang)
        assert tr("report.value.manifest_block_missing") in visible_text(section(html, "cover"))
        assert tr("report.text.chart_no_values", title=tr("report.chart.m06")) in visible_text(html)
        for row in finding_rows(html):
            assert all(row[cell].strip() for cell in FINDING_CELLS)
    foreign = quality.model_copy(deep=True)
    foreign.findings[0].reason = "made.up_{reason}"
    assert "reason.made.up_{reason}" in html_lib.unescape(render_report(foreign, lang))


# --- UF-01 / UF-07: check with three packs, then report, in real processes ---------------------------------


def test_uf01_uf07_check_then_report(tmp_path: Path) -> None:
    """UF-01: check (core+bids+gxdsl008) then report zh/en as real subprocesses; the report names every
    shown finding's rule and clause, the evidence document and the exception reason (UF-07). The PDF of the
    same HTML is printed by the PDF pipeline (pdf area, B1)."""
    dataset = tmp_path / "ds"
    shutil.copytree(FIX / "bids_issues", dataset)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "it-security-sop.pdf").write_bytes(SOP)
    evidence = tmp_path / "evidence.yaml"
    evidence.write_text(
        "format_version: 1\nevidence:\n  GXDSL008-ACC-001:\n    status: provided\n"
        "    document: docs/it-security-sop.pdf\n",
        encoding="utf-8",
    )
    config = tmp_path / "neurogrid.toml"
    config.write_text(DATASET_TOML, encoding="utf-8")
    out = tmp_path / "out"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    check = subprocess.run(
        [
            sys.executable,
            "-m",
            "neurogrid",
            "check",
            str(dataset),
            "--rulepack",
            "bids",
            "--rulepack",
            "gxdsl008",
            "--config",
            str(config),
            "--evidence",
            str(evidence),
            "--as-of",
            "2026-10-11",
            "--out",
            str(out / "results.json"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert check.returncode in (0, 1), check.stderr
    report = subprocess.run(
        [
            sys.executable,
            "-m",
            "neurogrid",
            "report",
            str(out / "results.json"),
            "--lang",
            "zh,en",
            "--format",
            "html",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert report.returncode == 0, report.stderr
    assert sorted(p.name for p in out.iterdir()) == ["report.en.html", "report.zh.html", "results.json"]
    results = Results.model_validate_json((out / "results.json").read_bytes())
    assert {p.name for p in results.rulepacks} == {"core", "bids", "gxdsl008"}
    for lang in REPORT_LANGS:
        html = (out / f"report.{lang}.html").read_text(encoding="utf-8")
        rows = finding_rows(html)
        assert {row["key"] for row in rows} == {f.key for f in results.findings}  # below 50 per rule
        fmt = render._Formatter(lang)
        for finding in results.findings:
            row = next(r for r in rows if r["key"] == finding.key)
            assert row["rule"] == finding.rule_id and row["clause"] == fmt.clause(finding)
        text = visible_text(html)
        assert "docs/it-security-sop.pdf" in text and EXCEPTION_REASON in text and EXPIRED_REASON in text
        assert str(escape(disclaimer(lang))) in html
