"""CORE-M14-02 re-consent in the check pipeline, the console and the report (NV-F06; A-30, A-81, A-95; D-17
option B for CORE-M14-02, owner answer 4 of P9): the re-consent list as findings per subject in results.json,
the counts per risk of the report's re-consent section under the A-81 small-cell rule, privacy of subjects,
consent versions and risk descriptions in every output, the notice of later risks, the states without consent
data, determinism and risks.yaml as a control file.

bids_ai_ok has six subjects: sub-01..04 in train (training), sub-05 in val and sub-06 in test (validation by
default)."""

from __future__ import annotations

import datetime as dt
import html as html_lib
import io
import json
import os
import re
import shutil
from pathlib import Path

import jsonschema
import pypdf
import pytest

from neurogrid import pipeline
from neurogrid.checks import ai_dataset
from neurogrid.checks import consent as consent_checks
from neurogrid.checks.context import CheckContext
from neurogrid.cli import main
from neurogrid.kernel import canonical
from neurogrid.kernel.errors import ConfigError
from neurogrid.kernel.findings import PassedCount, Severity, Status
from neurogrid.model.consent import ConsentFile, ConsentScope, dump_consents
from neurogrid.model.results import ReconsentRisk, ReconsentSummary, Results
from neurogrid.report import tables
from neurogrid.report.output import write_reports
from neurogrid.report.render import render_report
from neurogrid.report.texts import tables as language_tables
from neurogrid.report.texts import translator
from neurogrid.vault import store
from report_html import finding_rows, section, visible_text  # type: ignore[import-not-found]

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
SCHEMAS = Path(__file__).parents[2] / "src" / "neurogrid" / "schemas"
AS_OF = dt.date(2026, 11, 20)
RULE = "CORE-M14-02"
VERSION = 7777  # a consent version that must never reach the report or the console
MINIMUM = 8888  # a min_consent_version that must never reach the report or the console
DESCRIPTION = "ZhangSanRiskText"  # a risk description that must never reach any output
ENTRY = (
    "  - {{id: {id}, date: {date}, description: {text}, affected_uses: [{uses}], min_consent_version: {v}}}\n"
)


def record(subject: str, version: int = 1, **fields: object) -> ConsentScope:
    values: dict[str, object] = {"subject": subject, "version": version, "date": dt.date(2026, 1, 1)}
    values.update(fields)
    values.setdefault("permitted_uses", ("training", "validation"))
    return ConsentScope(**values)  # type: ignore[arg-type]


def risks(*entries: str) -> bytes:
    return ("format_version: 1\nrisks:\n" + "".join(entries)).encode("utf-8")


def risk(
    id: str = "R-all",
    uses: str = "training, validation",
    v: int = 2,
    date: str = "2026-09-01",
    text: str = DESCRIPTION,
) -> str:
    return ENTRY.format(id=id, date=date, text=text, uses=uses, v=v)


ALL_V1 = [record(f"sub-0{n}") for n in range(1, 7)]
ALL_V2 = [record(f"sub-0{n}", 2) for n in range(1, 7)]


def dataset(
    tmp_path: Path, records: list[ConsentScope], register: bytes | None, toml: str | None = None
) -> Path:
    """A copy of bids_ai_ok with a vault (what ``vault init`` creates), these consent records and this risk
    register (None: the empty template)."""
    folder = tmp_path / "ds"
    shutil.copytree(FIX / "bids_ai_ok", folder)
    location = store.locate(folder, store.DEFAULT_VAULT_PATH)
    store.init_vault(location)
    location.consents.write_bytes(dump_consents(ConsentFile(consents=records)))
    if register is not None:
        location.risks.write_bytes(register)
    if toml is not None:
        (folder / ".neurogrid" / "neurogrid.toml").write_text(toml, encoding="utf-8")
    return folder


def check(folder: Path, tmp_path: Path, **options: object) -> Results:
    values: dict[str, object] = {"as_of": AS_OF, "work_base": tmp_path / "work"}
    values.update(options)
    return pipeline.run_check(folder, pipeline.CheckOptions(**values))  # type: ignore[arg-type]


def m14_02(results: Results) -> list[tuple[str, str | None, str, str | None]]:
    return sorted(
        (f.object, f.subkey, f.status.value, f.reason) for f in results.findings if f.rule_id == RULE
    )


def views(results: Results, lang: str) -> dict[str, str]:
    """The visible text of every part of the report that shows CORE-M14-02: its line in section 3, its part
    of the re-consent section, its row in appendix 6.1 and the passed checks of section 2."""
    html = render_report(results, lang)
    findings = section(html, "findings")
    line = re.search(rf'<div class="rule-group" data-rule="{RULE}">.*?</div>', findings, re.S)
    part = re.search(r'<div class="reconsent" id="reconsent">.*', findings, re.S)
    overview = re.search(rf'<tr data-rule="{RULE}">.*?</tr>', section(html, "appendix"), re.S)
    passed = re.search(
        r'<p class="passed">.*?</p>\s*(?:<p class="passed-note">.*?</p>)?', section(html, "summary"), re.S
    )
    assert line and part and overview and passed
    return {
        "line": visible_text(line.group(0)),
        "section": visible_text(part.group(0)),
        "section_html": part.group(0),
        "overview": visible_text(overview.group(0)),
        "overview_cells": overview.group(0),
        "passed": visible_text(passed.group(0)),
    }


# --- the re-consent list as findings and the report section (DoD of P9 for NV-F06) --------------------------


def test_reconsent_list_as_findings_and_report_section(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """KONZEPT 6 P9 DoD 'Neueinwilligungsliste als Befunde + Berichtsabschnitt': every subject whose valid
    consent is below the version of a risk that affects a use of its recordings is a finding of CORE-M14-02 in
    results.json (warning, subkey the risk ID, details without description); the report counts them per risk
    in its own section with the fixed text of A-30, and the console gives their number."""
    folder = dataset(tmp_path, ALL_V1, risks(risk()))
    out = tmp_path / "results.json"
    with pytest.raises(SystemExit) as info:
        main(["--lang", "en", "check", str(folder), "--as-of", AS_OF.isoformat(), "--out", str(out)])
    console = capsys.readouterr()
    results = Results.model_validate_json(out.read_bytes())
    without = check(dataset(tmp_path / "template", ALL_V1, None), tmp_path)  # the empty register
    assert info.value.code == results.summary.exit_code == without.summary.exit_code  # warnings only
    assert results.summary.errors == without.summary.errors
    assert results.summary.warnings == without.summary.warnings + 6
    assert m14_02(results) == [
        (f"sub-0{n}", "R-all", "failed", "reconsent.version_below") for n in range(1, 7)
    ]
    first = next(f for f in results.findings if f.rule_id == RULE)
    assert first.severity is Severity.WARNING and first.measured_value is False
    assert first.details == {
        "risk": "R-all",
        "affected_uses": ["training"],
        "consent_version": 1,
        "min_consent_version": 2,
        "recordings": [
            "sub-01/eeg/sub-01_task-rest_run-1_eeg.edf",
            "sub-01/eeg/sub-01_task-rest_run-2_eeg.edf",
        ],
        "recordings_total": 2,
    }
    assert results.reconsent == ReconsentSummary(
        risks=[
            ReconsentRisk(
                id="R-all",
                date=dt.date(2026, 9, 1),
                affected_uses=["training", "validation"],
                subjects=6,
                candidates=6,
            )
        ]
    )
    assert translator("en").t("cli.check.reconsent", count=6) in console.out
    assert "sub-0" not in console.out + console.err
    for lang in ("zh", "en"):
        tr = translator(lang).t
        shown = views(results, lang)
        assert tr("report.reconsent.pointer", heading=tr("report.reconsent.heading")) in shown["line"]
        assert shown["section"].startswith(tr("report.reconsent.heading"))
        assert tr("report.reconsent.text") in shown["section"]  # A-30
        cell = tr(
            "report.reconsent.cell",
            result=tr(
                "report.reconsent.with_reason",
                status=tr("status.failed"),
                reason=tr("report.reconsent.version_below"),
            ),
            count=tr("report.consent.subjects", count=6),
        )
        assert cell in shown["section"]  # 6 subjects: the table is published
        assert "R-all" in shown["section"] and "2026-09-01" in shown["section"]
        assert tr("terms.consent_use.training") in shown["section"]
        assert tr("report.reconsent.note") in shown["section"]
        assert "sub-0" not in shown["section"] + shown["line"]
        assert not any(row["rule"] == RULE for row in finding_rows(render_report(results, lang)))  # no rows


def test_every_version_reached_and_a_risk_without_candidates_pass(tmp_path: Path) -> None:
    """Passed results are counted (A-59): per subject whose version reaches the risk's, and once for the
    dataset for a risk whose uses no recording needs; the section still shows the published counts."""
    register = risks(risk(), risk("R-com", "commercial", 1))
    results = check(dataset(tmp_path, ALL_V2, register), tmp_path)
    assert m14_02(results) == []
    passed = {p.object: p.count for p in results.passed if p.rule_id == RULE}
    assert passed == {"dataset": 1, **{f"sub-0{n}": 1 for n in range(1, 7)}}
    assert results.reconsent is not None and [
        (r.id, r.subjects, r.candidates) for r in results.reconsent.risks
    ] == [
        ("R-all", 6, 6),
        ("R-com", 0, 0),
    ]
    tr = translator("en").t
    shown = views(results, "en")
    assert (
        tr("report.reconsent.cell", result=tr("status.passed"), count=tr("report.consent.subjects", count=6))
        in (shown["section"])
    )
    assert tr("report.reconsent.no_subjects") in shown["section"]
    assert '<td class="num">' in shown["overview_cells"]  # published: 6.1 counts the rule as any other


def test_subjects_without_a_valid_consent_are_left_to_m14_01(tmp_path: Path) -> None:
    """A withdrawn, missing or not yet valid consent: no CORE-M14-02 result for the subject (CORE-M14-01
    judges it); the section counts such subjects in a cell of their own, so no cell follows from the
    others."""
    records = [
        *ALL_V1[:3],
        record("sub-04", 2, permitted_uses=(), withdrawn=True, date=dt.date(2026, 6, 1)),
        record("sub-05", date=dt.date(2027, 1, 1)),
    ]
    results = check(dataset(tmp_path, records, risks(risk())), tmp_path)
    assert m14_02(results) == [
        (f"sub-0{n}", "R-all", "failed", "reconsent.version_below") for n in range(1, 4)
    ]
    assert results.reconsent is not None
    assert [(r.subjects, r.candidates) for r in results.reconsent.risks] == [(6, 3)]
    table = tables.rule_reconsent_table(results, RULE)
    assert table is not None and table.withheld and table.rows[0].cells == []  # 3 and 3: below 5
    unwithheld = tables.reconsent_table(
        [f for f in results.findings if f.rule_id == RULE], [], results.reconsent
    )
    assert unwithheld.withheld  # every cell below 5


# --- the small-cell rule (A-81 as accepted in D-15, D-17 option B; A-95) ------------------------------------


def _finding(results: Results, subject: str, risk_id: str, status: Status = Status.FAILED) -> object:
    template = next(f for f in results.findings if f.rule_id == RULE)
    return template.model_copy(update={"object": subject, "subkey": risk_id, "status": status})


def test_reconsent_small_cells_withheld(tmp_path: Path) -> None:
    """A risk's table distributes the subjects whose recordings need an affected use over the results per
    subject, the passed ones and those without a valid consent; it is published only if every non-zero cell
    has at least 5 subjects, and one withheld table withholds every risk (they share subjects). Results that
    do not match results.reconsent withhold the tables too."""
    base = check(dataset(tmp_path, ALL_V1, risks(risk())), tmp_path)
    assert tables.SMALL_CELL == 5 and tables.RECONSENT_CHECK == consent_checks.RECONSENT
    assert tables.DATASET == ai_dataset.DATASET
    summary = ReconsentSummary(
        risks=[
            ReconsentRisk(id="R1", date=AS_OF, affected_uses=["training"], subjects=20, candidates=15),
            ReconsentRisk(id="R2", date=AS_OF, affected_uses=["sharing"], subjects=10, candidates=10),
        ]
    )
    failed = [_finding(base, f"sub-f{n}", "R1") for n in range(5)]
    passed = [PassedCount(rule_id=RULE, object=f"sub-p{n}", count=1) for n in range(20)]
    table = tables.reconsent_table(failed, passed, summary)  # type: ignore[arg-type]
    assert not table.withheld
    assert [(c.status, c.reason, c.count) for c in table.rows[0].cells] == [
        (Status.FAILED, "reconsent.version_below", 5),
        (Status.PASSED, None, 10),
        (None, tables.NO_VALID_CONSENT, 5),
    ]
    assert [(c.status, c.count) for c in table.rows[1].cells] == [(Status.PASSED, 10)]
    one_more = [*failed, _finding(base, "sub-f5", "R2")]  # R2: 1 not passed, 9 passed
    small = tables.reconsent_table(one_more, passed[:19], summary)  # type: ignore[arg-type]
    assert small.withheld and all(row.cells == [] for row in small.rows)  # R1 is withheld with R2
    assert [row.risk.subjects for row in small.rows] == [20, 10]
    excepted = [*failed[:4], _finding(base, "sub-f4", "R1", Status.EXCEPTED)]  # an exception of 1
    assert tables.reconsent_table(excepted, passed, summary).withheld  # type: ignore[arg-type]
    for broken in (
        (failed, passed[:19]),  # passed results that do not add up
        ([*failed, _finding(base, "sub-x", "R9")], passed),  # a risk results.reconsent does not name
    ):
        assert tables.reconsent_table(*broken, summary).withheld  # type: ignore[arg-type]
    no_valid = summary.model_copy(  # R1: 2 subjects without a valid consent
        update={"risks": [summary.risks[0].model_copy(update={"candidates": 18}), summary.risks[1]]}
    )
    passed_23 = [PassedCount(rule_id=RULE, object=f"sub-p{n}", count=1) for n in range(23)]
    assert tables.reconsent_table(failed, passed_23, no_valid).withheld  # type: ignore[arg-type]


def _withheld_views(tmp_path: Path) -> dict[str, Results]:
    """Four runs whose re-consent cells differ only below 5 subjects: R-train (training, version 2) with
    sub-01..04 all at version 2, sub-02 at version 1, sub-03 withdrawn, or sub-02 at version 1 and
    excepted."""
    register = risks(risk("R-train", "training"))
    exception = (
        '[[exceptions]]\nrule = "CORE-M14-02"\nobject = "sub-02"\nsubkey = "R-train"\n'
        'reason = "asked again ZhangSan"\n'
    )
    below = [r if r.subject != "sub-02" else record("sub-02", 1) for r in ALL_V2]
    withdrawn = [*ALL_V2, record("sub-03", 3, permitted_uses=(), withdrawn=True, date=dt.date(2026, 6, 1))]
    runs = {}
    for name, records, toml in (
        ("reached", ALL_V2, None),
        ("below", below, None),
        ("withdrawn", withdrawn, None),
        ("excepted", below, exception),
    ):
        (tmp_path / name).mkdir()
        runs[name] = check(dataset(tmp_path / name, records, register, toml), tmp_path / name)
    return runs


def test_no_reconsent_cell_of_one_to_four_subjects_can_be_read_from_the_report(tmp_path: Path) -> None:
    """A-81 for CORE-M14-02 (A-95): whether all four subjects reach the version, one is below it, one has no
    valid consent or one is excepted, the line in section 3, the re-consent section, the rule's row in 6.1 (no
    count at all: its results are the candidates, which beside the subjects of the section would tell how
    many have no valid consent) and the passed checks of section 2 read the same. As for CORE-M14-01, the
    warning counts of the summary and the light count the not passed results (P6 review)."""
    runs = _withheld_views(tmp_path)
    assert m14_02(runs["reached"]) == []
    assert m14_02(runs["below"]) == [("sub-02", "R-train", "failed", "reconsent.version_below")]
    assert m14_02(runs["withdrawn"]) == []
    assert m14_02(runs["excepted"]) == [("sub-02", "R-train", "excepted", "reconsent.version_below")]
    for lang in ("zh", "en"):
        tr = translator(lang).t
        shown = {name: views(results, lang) for name, results in runs.items()}
        for part in ("line", "section", "overview", "passed"):
            assert len({shown[name][part] for name in runs}) == 1, (lang, part)
        reached = shown["reached"]
        assert tr("report.reconsent.withheld") in reached["section"]
        assert tr("report.consent.subjects", count=4) in reached["section"]  # the subjects of the risk
        assert tr("report.reconsent.overview_withheld") in reached["overview"]
        assert '<td class="num">' not in reached["overview_cells"]
        assert tr("report.consent.passed_note") in reached["passed"]
        for count in (1, 3):
            assert tr("report.consent.subjects", count=count) not in reached["section"]
    excepted = render_report(runs["excepted"], "en")
    appendix = section(excepted, "appendix")
    assert "ZhangSan" not in visible_text(appendix) and "R-train" not in visible_text(appendix)  # 6.3, 6.5
    assert translator("en").t("report.consent.exceptions_total", count=1) in visible_text(appendix)
    assert runs["excepted"].exceptions[0].entry.object == "sub-02"  # results.json keeps the exception


def test_exceptions_of_an_unloaded_reconsent_rule_are_withheld(tmp_path: Path) -> None:
    """D-17 option B: an exception for CORE-M14-02 names a subject, a risk and the user's reason; the report
    withholds them also in a run without the rule (tables.BUILTIN_RECONSENT_RULES)."""
    toml = (
        '[check]\nrulepacks = ["bids"]\n[[exceptions]]\nrule = "CORE-M14-02"\nobject = "sub-02"\n'
        'subkey = "R-train"\nreason = "asked again ZhangSan"\n'
    )
    results = check(dataset(tmp_path, ALL_V1, risks(risk("R-train")), toml), tmp_path)
    assert RULE not in {rule.id for rule in results.rules} and results.reconsent is None
    for lang in ("zh", "en"):
        text = visible_text(section(render_report(results, lang), "appendix"))
        assert "ZhangSan" not in text and "sub-02" not in text and "R-train" not in text
        assert translator(lang).t("report.consent.exceptions_total", count=1) in text


def test_the_built_in_reconsent_rules_are_known() -> None:
    """tables.BUILTIN_RECONSENT_RULES names every rule on consent.reconsent of the built-in packs."""
    from importlib import resources

    found = {
        rule.id
        for entry in resources.files("neurogrid.rulepacks").iterdir()
        if entry.name.endswith(".yaml")
        for rule in pipeline.load_rulepack_ref(entry.name.removesuffix(".yaml")).pack.rules
        if rule.check == tables.RECONSENT_CHECK
    }
    assert found == tables.BUILTIN_RECONSENT_RULES == {RULE}
    assert tables.RECONSENT_CHECK.startswith(tables.CONSENT_CHECKS) and tables.CONSENT_CHECK.startswith(
        tables.CONSENT_CHECKS
    )


# --- privacy (A-51, D-17 option B): subjects, versions and descriptions -----------------------------------


LAB_PACK = """rulepack: lab
version: "1"
source: "Lab re-consent rule"
source_status: final
rules:
  - id: LAB-ACC-002
    clause: "LAB-9"
    title_zh: 可能需要重新取得知情同意
    title_en: Re-consent possibly needed
    phase: access
    check: consent.reconsent
    severity: warning
    verification: automatic
"""
LAB_RULE = "LAB-ACC-002"


def _private_run(tmp_path: Path) -> Path:
    """A raw folder whose recordings map to sub-07 (train) and sub-08 (val), both consented with VERSION, R-hi
    asks for MINIMUM, checked with a pack that has only the re-consent rule: subject IDs and versions can then
    reach outputs only through its findings (two subjects: the table is withheld)."""
    folder = tmp_path / "raw"
    shutil.copytree(FIX / "edf_ok", folder)
    location = store.locate(folder, store.DEFAULT_VAULT_PATH)
    store.init_vault(location)
    records = [record("sub-07", VERSION), record("sub-08", VERSION)]
    location.consents.write_bytes(dump_consents(ConsentFile(consents=records)))
    location.risks.write_bytes(risks(risk("R-hi", v=MINIMUM)))
    (folder / ".neurogrid" / "splits.tsv").write_text(
        "recording\tsplit\nrec_a.edf\ttrain\nrec_b.edf\tval\n", encoding="utf-8"
    )
    (folder / "lab.yaml").write_text(LAB_PACK, encoding="utf-8")
    (folder / ".neurogrid" / "neurogrid.toml").write_text(
        '[check]\nrulepacks = ["lab.yaml"]\n'
        '[[convert.files]]\npath = "rec_a.edf"\nsubject = "07"\ntask = "rest"\n'
        '[[convert.files]]\npath = "rec_b.edf"\nsubject = "08"\ntask = "rest"\n',
        encoding="utf-8",
    )
    return folder


def _texts(data: bytes) -> str:
    return "".join(page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(data)).pages)


def _outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str], formats: str) -> dict[str, str]:
    folder = _private_run(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    results_file = out / "results.json"
    texts: dict[str, str] = {}
    for args in (
        ["--lang", "en", "check", str(folder), "--as-of", AS_OF.isoformat(), "--out", str(results_file)],
        [
            "--lang",
            "en",
            "report",
            str(results_file),
            "--lang",
            "zh,en",
            "--format",
            formats,
            "--out",
            str(out),
        ],
    ):
        with pytest.raises(SystemExit) as info:
            main(args)
        captured = capsys.readouterr()
        assert info.value.code in (0, 1), captured.err
        texts[f"console {args[2]}"] = captured.out + captured.err
    texts["results.json"] = results_file.read_text(encoding="utf-8")
    for lang in ("zh", "en"):
        document = (out / f"report.{lang}.html").read_text(encoding="utf-8")
        texts[f"html {lang}"] = document
        texts[f"visible {lang}"] = visible_text(document)
        if "pdf" in formats:
            texts[f"pdf {lang}"] = _texts((out / f"report.{lang}.pdf").read_bytes())
    return texts


def _assert_private(texts: dict[str, str]) -> None:
    for name, text in texts.items():
        assert DESCRIPTION not in text, name  # the description stays in risks.yaml (A-51)
    results = json.loads(texts["results.json"])
    listed = [f for f in results["findings"] if f["rule_id"] == LAB_RULE]
    # results.json keeps the re-consent list with the consent versions (D-17 option B) ...
    assert {(f["object"], f["subkey"]) for f in listed} == {("sub-07", "R-hi"), ("sub-08", "R-hi")}
    assert {(f["details"]["consent_version"], f["details"]["min_consent_version"]) for f in listed} == {
        (VERSION, MINIMUM)
    }
    # ... the report (HTML visible text, PDF text) and the console show neither the subjects nor a version
    # (the markup embeds font data, whose base64 text may hold any digits)
    for name, text in texts.items():
        if name != "results.json" and not name.startswith("html"):
            flat = re.sub(r"\s+", "", text)
            assert "sub-07" not in flat and "sub-08" not in flat, name
            assert str(VERSION) not in flat and str(MINIMUM) not in flat, name


def test_report_never_names_reconsent_subjects_or_versions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The HTML reports (visible text) and the console of check and report: no subject ID, no
    consent version, no min_consent_version, no risk description; the two subjects are counted, withheld."""
    texts = _outputs(tmp_path, capsys, "html")
    _assert_private(texts)
    assert translator("en").t("cli.check.reconsent", count=2) in texts["console check"]
    for lang in ("zh", "en"):
        tr = translator(lang).t
        assert tr("report.consent.subjects", count=2) in texts[f"visible {lang}"]
        assert tr("report.reconsent.withheld") in texts[f"visible {lang}"]
        assert "R-hi" in texts[f"visible {lang}"]  # the risk ID and its date may appear (A-95)


@pytest.mark.pdf
def test_reconsent_never_reaches_the_pdf_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The same in the printed reports, with the section's heading, the fixed text of A-30, the withheld
    sentence, the note and appendix 6.1 without a count."""
    texts = _outputs(tmp_path, capsys, "html,pdf")
    assert {"pdf zh", "pdf en"} <= set(texts)
    _assert_private(texts)
    for lang in ("zh", "en"):
        tr = translator(lang).t
        flat = re.sub(r"\s+", "", texts[f"pdf {lang}"])
        for shown in (
            tr("report.reconsent.heading"),
            tr("report.reconsent.text"),
            tr("report.reconsent.withheld"),
            tr("report.reconsent.note"),
            tr("report.reconsent.overview_withheld"),
        ):
            assert re.sub(r"\s+", "", shown) in flat, shown


@pytest.mark.pdf
def test_the_withheld_reconsent_counts_print(tmp_path: Path) -> None:
    """The printed re-consent section of a withheld BIDS run: the withheld sentence and the subjects of the
    risk, never the one subject below the version (other rules name the BIDS subjects by their files)."""
    runs = _withheld_views(tmp_path)
    for path in write_reports(runs["below"], ["zh", "en"], ["pdf"], tmp_path / "reports", environ=os.environ):
        tr = translator(path.name.split(".")[1]).t
        text = re.sub(r"\s+", "", _texts(path.read_bytes()))
        heading = re.sub(r"\s+", "", tr("report.reconsent.heading"))
        part = text.rsplit(heading, 1)[1].split(re.sub(r"\s+", "", tr("report.section.metrics")), 1)[0]
        assert re.sub(r"\s+", "", tr("report.reconsent.withheld")) in part
        assert re.sub(r"\s+", "", tr("report.consent.subjects", count=4)) in part
        assert "sub-0" not in part and re.sub(r"\s+", "", tr("report.consent.subjects", count=1)) not in part


def test_risk_description_in_no_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The risk description never reaches results.json, the report (markup included) or the console; nor do
    the descriptions of later risks (A-51, A-95)."""
    folder = _private_run(tmp_path)
    store.locate(folder, store.DEFAULT_VAULT_PATH).risks.write_bytes(
        risks(risk("R-hi", v=MINIMUM), risk("R-later", date="2027-01-01", text="LaterRiskText"))
    )
    results_file = tmp_path / "results.json"
    with pytest.raises(SystemExit):
        main(["check", str(folder), "--as-of", AS_OF.isoformat(), "--out", str(results_file)])
    with pytest.raises(SystemExit):
        main(["report", str(results_file), "--lang", "zh,en", "--out", str(tmp_path)])
    captured = capsys.readouterr()
    outputs = [results_file.read_text(encoding="utf-8"), captured.out, captured.err]
    outputs += [(tmp_path / f"report.{lang}.html").read_text(encoding="utf-8") for lang in ("zh", "en")]
    for text in outputs:
        assert DESCRIPTION not in text and "LaterRiskText" not in text
    assert "R-later" not in outputs[0]  # a later risk is only counted (notice.risks_future)


# --- notices, states without consent data, configuration ----------------------------------------------------


def test_future_risks_notice(tmp_path: Path) -> None:
    """A risk dated after the reference date is not judged; a notice counts it (info). A risk dated on the
    reference date is judged."""
    register = risks(risk("R-on", date=AS_OF.isoformat()), risk("R-later", date="2026-11-21"))
    results = check(dataset(tmp_path, ALL_V1, register), tmp_path)
    assert {subkey for _o, subkey, _s, _r in m14_02(results)} == {"R-on"}
    notices = [n for n in results.notices if n.message_key == "notice.risks_future"]
    assert [(n.level, n.params) for n in notices] == [(Severity.INFO, {"count": 1})]
    only_later = check(dataset(tmp_path / "later", ALL_V1, risks(risk(date="2027-01-01"))), tmp_path)
    assert m14_02(only_later) == [("dataset", None, "not_applicable", "reconsent.no_risks")]
    assert only_later.reconsent is None
    assert {n.message_key for n in only_later.notices} >= {"notice.risks_future"}


def test_reconsent_without_consent_data_not_checkable(tmp_path: Path) -> None:
    """No consent data (consents: [], no consents.yaml): one dataset-level result, not checkable; never
    failed, neither with --strict nor with a configured [consent]; no results.reconsent, and the report
    section says why there is no table. Without a vault or risk register: not applicable."""
    folder = dataset(tmp_path, [], risks(risk()))
    expected = [("dataset", None, "not_checkable", "consent.no_consents")]
    plain = check(folder, tmp_path)
    assert m14_02(plain) == expected and plain.reconsent is None
    assert m14_02(check(folder, tmp_path, strict=True)) == expected
    (folder / ".neurogrid" / "neurogrid.toml").write_text('[consent]\ndataset_uses = ["sharing"]\n', "utf-8")
    assert m14_02(check(folder, tmp_path)) == expected
    store.locate(folder, store.DEFAULT_VAULT_PATH).consents.unlink()
    assert m14_02(check(folder, tmp_path)) == expected
    for lang in ("zh", "en"):
        shown = views(plain, lang)
        assert translator(lang).t("report.reconsent.no_consents") in shown["section"]
        assert translator(lang).t("report.reconsent.text") not in shown["section"]  # no list, no claim
    no_vault = pipeline.run_check(FIX / "bids_ai_ok", pipeline.CheckOptions(as_of=AS_OF, work_base=tmp_path))
    assert m14_02(no_vault) == [("dataset", None, "not_applicable", "reconsent.no_risks")]
    assert translator("en").t("report.reconsent.no_risks") in views(no_vault, "en")["section"]


def test_the_needed_uses_of_m14_decide_which_subjects_a_risk_affects(tmp_path: Path) -> None:
    """[consent] dataset_uses = sharing: every recording needs sharing, so a risk on sharing affects all six
    subjects; a risk on publication none (passed for the dataset)."""
    toml = '[consent]\ndataset_uses = ["sharing"]\n'
    records = [record(f"sub-0{n}", permitted_uses=("training", "validation", "sharing")) for n in range(1, 7)]
    register = risks(risk("R-share", "sharing"), risk("R-pub", "publication", 1))
    results = check(dataset(tmp_path, records, register, toml), tmp_path)
    assert {(o, s) for o, s, _st, _r in m14_02(results)} == {(f"sub-0{n}", "R-share") for n in range(1, 7)}
    assert {f.details["affected_uses"][0] for f in results.findings if f.rule_id == RULE} == {"sharing"}
    assert {p.object for p in results.passed if p.rule_id == RULE} == {"dataset"}


# --- determinism and the control file (NG-N03, C2) ----------------------------------------------------------


def test_two_checks_with_a_risk_register_are_byte_identical(tmp_path: Path) -> None:
    """Two runs give the same results.json; so does risks.yaml spelled another way (order, comments, CRLF,
    quoting), with the same config.risks_sha256 (A-91 rule for the registers)."""
    folder = dataset(tmp_path, ALL_V1, risks(risk(), risk("R-com", "commercial", 1)))
    first = check(folder, tmp_path)
    second = check(folder, tmp_path)
    assert canonical.dumps(first) == canonical.dumps(second)
    assert first.config.risks_sha256 is not None
    respelled = (
        "# hand-written\r\nformat_version: 1\r\nrisks:\r\n"
        + risk("R-com", "commercial", 1).replace("\n", "\r\n")
        + risk(uses="validation, training", date="'2026-09-01'").replace("\n", "\r\n")
    )
    store.locate(folder, store.DEFAULT_VAULT_PATH).risks.write_bytes(respelled.encode("utf-8"))
    assert canonical.dumps(check(folder, tmp_path)) == canonical.dumps(first)
    data = json.loads(canonical.dumps(first))
    jsonschema.validate(data, json.loads((SCHEMAS / "results.schema.json").read_text(encoding="utf-8")))


def test_an_invalid_risk_register_ends_the_run_before_the_signal_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """C2: with the core pack (CORE-M14-02 loaded) an invalid risks.yaml is exit 2 before the data are read,
    naming the field, never the value."""
    folder = dataset(tmp_path, ALL_V1, risks(risk(), risk()))  # the same ID twice

    def never(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the signal pass ran")

    monkeypatch.setattr(CheckContext, "compute_quality", never)
    with pytest.raises(ConfigError) as info:
        check(folder, tmp_path)
    assert info.value.message_key == "risks.invalid" and info.value.params == {
        "field": "risks.1.id",
        "problem": "duplicate_id",
    }
    out = tmp_path / "results.json"
    with pytest.raises(SystemExit) as exit_info:
        main(["--lang", "en", "check", str(folder), "--out", str(out)])
    assert exit_info.value.code == 2 and not out.exists()
    assert DESCRIPTION not in capsys.readouterr().err


# --- the evaluator, the oracle helpers and the language keys of the area ----------------------------------


def test_the_evaluator_and_the_console_count() -> None:
    from neurogrid.kernel.rules import Measurement

    evaluate = consent_checks.SPECS[1].evaluate
    assert consent_checks.SPECS[1].id == consent_checks.RECONSENT == pipeline.RISKS_CHECK
    reached = Measurement(check_id=consent_checks.RECONSENT, object="sub-01", value=True, subkey="R1")
    below = Measurement(check_id=consent_checks.RECONSENT, object="sub-01", value=False, subkey="R1")
    assert evaluate(reached, {}).passed is True and evaluate(below, {}).passed is False
    assert consent_checks.CHECKS == {consent_checks.COVERED, consent_checks.RECONSENT}


def test_language_keys_of_the_area() -> None:
    """Keys built at run time: zh, en, de (NG-N06, C7)."""
    keys = [f"reason.{key}" for key in consent_checks.RECONSENT_REASONS]
    keys += ["notice.risks_future", "check.consent.reconsent", "cli.check.reconsent"]
    keys += [
        f"report.reconsent.{name}"
        for name in (
            "heading",
            "text",
            "legend",
            "pointer",
            "risk",
            "date",
            "uses",
            "subjects",
            "results",
            "cell",
            "with_reason",
            "version_below",
            "no_valid_consent",
            "no_subjects",
            "withheld",
            "note",
            "no_risks",
            "no_consents",
            "more",
            "overview_withheld",
        )
    ]
    for lang in ("zh", "en", "de"):
        missing = [key for key in keys if key not in language_tables()[lang]]
        assert not missing, (lang, missing)
    source = Path(consent_checks.__file__).read_text(encoding="utf-8")
    assert set(re.findall(r'"(reconsent\.[a-z_]+)"', source)) == set(consent_checks.RECONSENT_REASONS)


def test_the_g1_oracle_checks_the_reconsent_display(tmp_path: Path) -> None:
    """tools/acceptance_g1.py (the NG-F13 oracle of G1): CORE-M14-02 needs its line in section 3 without a
    table and its part of the re-consent section; a subject named in them is a problem."""
    import acceptance_g1 as g1  # type: ignore[import-not-found]

    results = check(dataset(tmp_path, ALL_V1, risks(risk())), tmp_path)
    document = render_report(results, "en")

    def problems(text: str) -> list[str]:
        return [p for p in g1.check_finding_rows(text, results, "en").problems if p.startswith(RULE)]

    assert problems(document) == []
    missing = f"{RULE}: the re-consent line or section is missing"
    assert problems(document.replace('<div class="reconsent-rule"', '<div class="other"', 1)) == [missing]
    line = f'<div class="rule-group" data-rule="{RULE}">'
    assert problems(document.replace(line, line + "<table></table>", 1)) == [missing]
    named = document.replace('<table class="reconsent">', 'sub-03 <table class="reconsent">', 1)
    assert problems(named) == [f"{RULE}: the aggregated block names 1 object(s) of its findings"]


def test_many_risks_are_cut_with_a_sentence(tmp_path: Path) -> None:
    """A-59 bound: at most MAX_ROWS_PER_RULE risks per rule in the section, then a sentence with the number of
    further risks (all of them are in results.json)."""
    from neurogrid.report.render import MAX_RISKS_SHOWN

    entries = [risk(f"R{n:03d}", "commercial", 1) for n in range(MAX_RISKS_SHOWN + 3)]
    results = check(dataset(tmp_path, ALL_V1, risks(*entries)), tmp_path)
    assert results.reconsent is not None and len(results.reconsent.risks) == MAX_RISKS_SHOWN + 3
    tr = translator("en").t
    shown = views(results, "en")
    assert tr("report.reconsent.more", count=3) in shown["section"]
    assert shown["section_html"].count("<tr>") == MAX_RISKS_SHOWN + 1  # header and the shown risks
    assert html_lib.escape(f"R{MAX_RISKS_SHOWN - 1:03d}") in shown["section_html"]
    assert f"R{MAX_RISKS_SHOWN:03d}" not in shown["section"]
