"""Report, P4 evidence area: section 5 with the evidence block (REP-05 contribution, A-15, A-83), links
between packs that share a threshold (A-40), the translated clause and source status of gxdsl008, the
exceptions appendix and the traffic-light legend (A-14, A-16), and reports of P3 results without the new
blocks."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

import pytest
from markupsafe import escape

from conftest import documented_config  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.kernel import canonical
from neurogrid.kernel.findings import Notice, Severity
from neurogrid.model.results import Results
from neurogrid.report import render
from neurogrid.report.render import render_report
from neurogrid.report.texts import translator
from report_html import inline_text  # type: ignore[import-not-found]

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = date(2026, 10, 11)
SOP = b"IT security SOP 12 (synthetic test document)\n"
LANGUAGES = ("zh", "en", "de")


def _section(html: str, name: str, following: str) -> str:
    return html[html.index(f'id="{name}"') : html.index(f'id="{following}"')]


@pytest.fixture(scope="module")
def provided(tmp_path_factory: pytest.TempPathFactory) -> Results:
    """bids_issues with wet electrodes, gxdsl008, GX-04 provided with a document and an expired exception."""
    tmp = tmp_path_factory.mktemp("report_evidence")
    (tmp / "docs").mkdir()
    (tmp / "docs" / "it-security-sop.pdf").write_bytes(SOP)
    evidence = tmp / "evidence.yaml"
    evidence.write_text(
        "format_version: 1\nevidence:\n  GXDSL008-ACC-001:\n    status: provided\n"
        "    document: docs/it-security-sop.pdf\n    reviewer: QA lead\n    date: 2026-10-01\n"
        "    comment: AES-256 at rest, role concept v2\n",
        encoding="utf-8",
    )
    config = tmp / "neurogrid.toml"
    config.write_text(
        '[metadata.defaults]\nelectrode_type = "wet"\n'
        '[[exceptions]]\nrule = "CORE-M05-01"\nreason = "Impedance sheet archived"\n'
        "valid_until = 2026-01-01\n",
        encoding="utf-8",
    )
    return pipeline.run_check(
        FIX / "bids_issues",
        pipeline.CheckOptions(
            rulepacks=("gxdsl008",), config_path=config, evidence_path=evidence, as_of=AS_OF
        ),
    )


@pytest.mark.parametrize("lang", LANGUAGES)
def test_provided_evidence_uses_the_a15_wording_in_every_language(provided: Results, lang: str) -> None:
    tr = translator(lang).t
    evidence = _section(render_report(provided, lang), "evidence", "appendix")
    assert str(escape(tr("report.value.evidence_provided"))) in evidence
    for verdict in (tr("status.passed"), "erfüllt", "通过"):
        assert verdict not in evidence  # never 'passed' for the user's statement (A-15)
    assert "docs/it-security-sop.pdf" in evidence and hashlib.sha256(SOP).hexdigest() in evidence
    assert "QA lead" in evidence and "2026-10-01" in evidence and "AES-256 at rest" in evidence
    assert str(escape(tr("report.document_check.ok"))) in evidence
    assert '<span class="nowrap">GXDSL008-ACC-001</span> (gxdsl008)' in evidence  # the ID never breaks (P5)


def test_open_and_missing_evidence_name_their_reason(tmp_path: Path) -> None:
    tr = translator("en").t
    options = {"rulepacks": ("gxdsl008",), "as_of": AS_OF, "config_path": documented_config(tmp_path)}
    missing = pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(**options))  # type: ignore[arg-type]
    section = _section(render_report(missing, "en"), "evidence", "appendix")
    assert tr("status.evidence_open") in section and tr("reason.evidence.missing") in section
    evidence = tmp_path / "evidence.yaml"
    evidence.write_text(
        "format_version: 1\nevidence:\n  GXDSL008-ACC-001:\n    status: open\n", encoding="utf-8"
    )
    open_run = pipeline.run_check(
        FIX / "edf_ok",
        pipeline.CheckOptions(evidence_path=evidence, **options),  # type: ignore[arg-type]
    )
    section = _section(render_report(open_run, "en"), "evidence", "appendix")
    assert tr("reason.evidence.open") in section and tr("report.value.evidence_provided") not in section


def test_semi_automatic_rules_are_listed_with_their_document_check(tmp_path: Path) -> None:
    pack = tmp_path / "semi.yaml"
    pack.write_text(
        "rulepack: site\nversion: '1'\nsource: SOP\nsource_status: final\nrules:\n"
        "  - id: SITE-STO-001\n    clause: '7'\n    title_zh: 备份程序\n"
        "    title_en: Backup procedure filed\n    phase: storage\n    check: evidence.document\n"
        "    severity: error\n    verification: semi_automatic\n",
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence.yaml"
    evidence.write_text(
        "format_version: 1\nevidence:\n  SITE-STO-001:\n    status: provided\n    document: backup.pdf\n",
        encoding="utf-8",
    )
    results = pipeline.run_check(
        FIX / "edf_ok",
        pipeline.CheckOptions(rulepacks=(str(pack),), evidence_path=evidence, as_of=AS_OF),
    )
    tr = translator("en").t
    section = _section(render_report(results, "en"), "evidence", "appendix")
    # the rule ID in a span that never wraps, the pack after it (P5, the rule ID never breaks inside)
    row = re.search(
        r"<tr><td class=\"mono\"><span class=\"nowrap\">SITE-STO-001</span> \(site\)</td>(.*?)</tr>",
        section,
        flags=re.S,
    )
    assert row is not None
    assert tr("status.failed") in row.group(1) and tr("reason.evidence.document_missing") in row.group(1)
    assert tr("verification.semi_automatic") in row.group(1)
    assert tr("report.document_check.document_missing") in row.group(1)


def test_findings_of_packs_sharing_a_threshold_are_linked(provided: Results) -> None:
    findings = _section(render_report(provided, "en"), "findings", "metrics")
    # P5: the title is the cell of class c-title after the rule and clause cells; the rule ID it names
    # stands in a span that never wraps (the ID never breaks inside)
    title = r'<td class="c-clause">[^<]*</td><td class="c-title">(.*?)</td>'
    core = re.findall(r'<td class="c-rule mono">CORE-M05-02</td>' + title, findings)
    gx = re.findall(r'<td class="c-rule mono">GXDSL008-ACQ-001</td>' + title, findings)
    assert core and gx
    assert all('also reported as <span class="nowrap">GXDSL008-ACQ-001</span>' in title for title in core)
    assert all('also reported as <span class="nowrap">CORE-M05-02</span>' in title for title in gx)


def test_text_next_to_a_rule_id_never_takes_its_slot(provided: Results) -> None:
    """P5: a rule ID goes into its sentence through a slot (render.RULE_SLOT) and stands in a span that never
    wraps. The dataset and user text around it is glyph-safe before the sentence is formatted: the slot
    character in a finding's subkey next to a cross reference, or in a notice's value next to a loaded rule,
    is written as its code point; it moves no rule ID and never ends the report with an error (dataset data
    never exit 2)."""
    slot = render.RULE_SLOT
    written = f"[U+{ord(slot):04X}]"
    changed = provided.model_copy(deep=True)
    changed.findings = [f.model_copy(update={"subkey": f"x{slot}y"}) for f in changed.findings]
    params = {"rule": "CORE-M05-01", "valid_until": f"2026{slot}01"}
    notice = Notice(level=Severity.WARNING, message_key="notice.exception_expired", params=params)
    changed.notices.append(notice)
    for lang in LANGUAGES:
        html = render_report(changed, lang)
        assert slot not in html
        findings = _section(html, "findings", "metrics")
        cross = re.escape(f"x{written}y") + r' · [^<]*<span class="nowrap">GXDSL008-ACQ-001</span>'
        assert re.search(cross, findings), lang
        # the notice as the reader sees it, the loaded rule's ID in a span of its own
        notices = re.findall(r"<li>(.*?)</li>", html[html.index("<h3>6.4 ") :], re.S)
        expected = translator(lang).t(notice.message_key, **{**params, "valid_until": f"2026{written}01"})
        shown = [item for item in notices if inline_text(item).endswith(expected)]
        assert len(shown) == 1 and '<span class="nowrap">CORE-M05-01</span>' in shown[0], (lang, notices)


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_gxdsl008_clause_and_source_status_are_translated(provided: Results, lang: str) -> None:
    tr = translator(lang).t
    html = render_report(provided, lang)
    findings = _section(html, "findings", "metrics")
    assert str(escape(tr("report.value.clause_unknown"))) in findings
    assert "<td>unknown</td>" not in findings  # the YAML value never appears raw (A-40, D-03)
    cover = _section(html, "cover", "summary")
    assert str(escape(tr("source_status.secondary"))) in cover and "<td>secondary</td>" not in cover
    assert str(escape(tr("report.text.secondary_note", pack="gxdsl008"))) in cover


def test_appendix_marks_expired_exceptions_and_legend_follows_a16(provided: Results) -> None:
    tr = translator("en").t
    html = render_report(provided, "en")
    appendix = html[html.index('id="appendix"') :]
    # the ID of a loaded rule in a span that never wraps (P5)
    row = re.search(
        r'<tr><td class="mono"><span class="nowrap">CORE-M05-01</span></td>(.*?)</tr>', appendix, flags=re.S
    )
    assert row is not None and tr("report.label.expired") in appendix
    cells = re.findall(r"<td[^>]*>(.*?)</td>", row.group(1))
    assert cells[-2:] == [tr("report.value.no"), tr("report.value.yes")]  # not applied, expired
    legend = tr("light.legend")
    assert str(escape(legend)) in html and "open evidence" in legend and "Grey" in legend


def test_p3_results_without_the_new_blocks_still_render(provided: Results) -> None:
    """C1/G8: results.json from P1-P3 has no evidence block, no evidence_sha256 and no open_evidence."""
    data = json.loads(canonical.dumps(provided))
    for key in ("evidence",):
        data.pop(key)
    data["config"].pop("evidence_sha256")
    data["summary"].pop("open_evidence")
    old = Results.model_validate_json(json.dumps(data))  # as 'neurogrid report' reads it
    assert old.evidence == [] and old.summary.open_evidence == 0 and old.config.evidence_sha256 is None
    for lang in ("zh", "en"):
        section = _section(render_report(old, lang), "evidence", "appendix")
        # manual rules from the rules block, as in P3 (the rule ID in a span that never wraps, P5)
        assert '<span class="nowrap">GXDSL008-ACC-001</span> (gxdsl008)' in section
    assert render_report(Results.model_validate_json(canonical.dumps(old)), "en")
