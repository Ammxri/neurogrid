"""HTML report: six sections (PRD §14), disclaimer, required fields per finding (NG-F13), CSP, escaping."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from markupsafe import escape

from neurogrid import pipeline
from neurogrid.kernel.findings import Phase, SourceStatus
from neurogrid.report.render import EXPLAINED_EMPTY, FINDING_CELLS, render_report
from neurogrid.report.texts import disclaimer, translator
from report_html import finding_rows  # type: ignore[import-not-found]

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"


@pytest.fixture(scope="module")
def results():  # type: ignore[no-untyped-def]
    return pipeline.run_check(FIX / "edf_mixed", pipeline.CheckOptions(as_of=date(2026, 10, 11)))


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_sections_and_disclaimer(results, lang: str) -> None:  # type: ignore[no-untyped-def]
    html = render_report(results, lang)
    for section in ("cover", "summary", "findings", "metrics", "evidence", "appendix"):
        assert f'id="{section}"' in html
    # P5 (REP-07, A-08): cover, appendix, screen footer, the meta description and the @page footer of every
    # printed page (CSS string)
    assert html.count(disclaimer(lang)) >= 5
    assert f'<meta name="description" content="{escape(disclaimer(lang))}">' in html
    assert "Content-Security-Policy" in html and "default-src 'none'" in html
    assert "http://" not in html and "https://" not in html
    assert "2026-10-11" in html


def test_phase_order_follows_prd(results) -> None:  # type: ignore[no-untyped-def]
    html = render_report(results, "en")
    tr = translator("en").t
    positions = [html.index(tr(f"phase.{p.value}")) for p in Phase]
    assert positions == sorted(positions)


def test_each_finding_row_has_required_fields(results) -> None:  # type: ignore[no-untyped-def]
    """NG-F13: every finding row names rule, clause, measured value, threshold, file and time range; P5 adds
    the channel column, data-key and cell classes (B1), and an empty value is '–' with its reason (A-09)."""
    html = render_report(results, "en")
    rows = finding_rows(html)
    assert len(rows) == len(results.findings) >= 2  # no rule has more than 50 findings here (A-59)
    assert {row["key"] for row in rows} == {f.key for f in results.findings}
    explained = {translator("en").t(key) for key in EXPLAINED_EMPTY}
    for row in rows:
        assert set(row) == {"key", *FINDING_CELLS}
        assert all(row[cell].strip() for cell in FINDING_CELLS)
        for cell in FINDING_CELLS:
            if row[cell].startswith("–"):
                assert row[cell] in explained and "(" in row[cell], (cell, row[cell])


def test_untrusted_text_is_escaped(results) -> None:  # type: ignore[no-untyped-def]
    hostile = results.model_copy(deep=True)
    hostile.dataset.name = "<script>alert(1)</script>"
    html = render_report(hostile, "en")
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_placeholder_banner(results) -> None:  # type: ignore[no-untyped-def]
    marked = results.model_copy(deep=True)
    marked.rulepacks[0].source_status = SourceStatus.PLACEHOLDER
    html = render_report(marked, "en")
    assert translator("en").t("report.placeholder_banner") in html


def test_placeholder_findings_are_listed_without_verdict(results) -> None:  # type: ignore[no-untyped-def]
    marked = results.model_copy(deep=True)
    for finding in marked.findings:
        finding.source_status = SourceStatus.PLACEHOLDER
    html = render_report(marked, "en")
    tr = translator("en").t
    assert tr("report.label.placeholder_findings") in html
    assert html.count(tr("report.value.placeholder_clause")) == len(marked.findings)
    findings_html = html[html.index('id="findings"') : html.index('id="metrics"')]
    assert tr("status.failed") not in findings_html


def test_header_issue_keys_are_translated(tmp_path: Path) -> None:
    folder = tmp_path / "bad"
    folder.mkdir()
    data = bytearray((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    data[252:256] = b"0   "
    (folder / "rec.edf").write_bytes(bytes(data))
    broken = pipeline.run_check(folder, pipeline.CheckOptions(as_of=date(2026, 10, 11)))
    html = render_report(broken, "zh")
    assert (
        "header.bad_signal_count" not in html and translator("zh").t("issue.header.bad_signal_count") in html
    )


def test_provided_evidence_wording() -> None:
    from neurogrid.checks.registry import REGISTRY
    from neurogrid.kernel import engine
    from neurogrid.kernel.evidence import EvidenceItem, EvidenceState
    from neurogrid.kernel.rules import load_rulepack

    pack = load_rulepack(
        "rulepack: site\nversion: '1'\nsource: SOP\nsource_status: final\nrules:\n"
        "  - id: SITE-ACC-001\n    clause: '7'\n    title_zh: 访问控制\n"
        "    title_en: Access control documented\n"
        "    phase: access\n    check: evidence.document\n    severity: error\n    verification: manual\n",
        origin="path",
    )
    result = engine.run(
        engine.EngineInput(
            packs=[pack],
            registry=REGISTRY,
            measurements={},
            as_of=date(2026, 10, 11),
            evidence={"SITE-ACC-001": EvidenceItem(status=EvidenceState.PROVIDED, document="sop.pdf")},
        )
    )
    base = pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(as_of=date(2026, 10, 11)))
    rule = base.rules[0].model_copy(
        update={"id": "SITE-ACC-001", "verification": pack.pack.rules[0].verification}
    )
    combined = base.model_copy(update={"rules": [rule], "findings": result.findings})
    html = render_report(combined, "en")
    evidence_html = html[html.index('id="evidence"') : html.index('id="appendix"')]
    assert str(escape(translator("en").t("report.value.evidence_provided"))) in evidence_html
    assert translator("en").t("status.passed") not in evidence_html


def test_passed_count_excludes_placeholder_rules(results) -> None:  # type: ignore[no-untyped-def]
    marked = results.model_copy(deep=True)
    for rule in marked.rules:
        rule.source_status = SourceStatus.PLACEHOLDER
    html = render_report(marked, "en")
    assert f"{translator('en').t('report.label.passed_checks')}: 0" in html
