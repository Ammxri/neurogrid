"""Rule engine, P4: evidence records and notices (A-15, A-83), exceptions completed (A-14), counting and the
traffic light (A-16, C6), coverage of semi-automatic rules (RP-07)."""

from __future__ import annotations

from datetime import date

import pytest

from neurogrid.config import ConfigExceptionEntry, parse
from neurogrid.kernel import engine
from neurogrid.kernel.errors import ConfigError
from neurogrid.kernel.evidence import DocumentCheck, DocumentResult, EvidenceItem, EvidenceState
from neurogrid.kernel.findings import Light, Phase, Severity, Status
from neurogrid.kernel.rules import (
    CheckSpec,
    Measurement,
    ParamSpec,
    at_most,
    evidence_spec,
    is_true,
    load_rulepack,
)

AS_OF = date(2026, 10, 11)
REGISTRY = {
    "test.max": CheckSpec("test.max", at_most("limit"), {"limit": ParamSpec("number", 10)}),
    "test.flag": CheckSpec("test.flag", is_true),
    "evidence.document": evidence_spec(),
}


def pack(
    body: str, *, name: str = "demo", status: str = "final", norm: bool = False
) -> engine.LoadedRulepack:
    header = (
        f"rulepack: {name}\nversion: '1.0'\nsource: Test\n"
        f"source_status: {status}\nnorm: {str(norm).lower()}\n"
    )
    return load_rulepack(header + "rules:\n" + body, origin="path")


def rule(rule_id: str, check: str, *, phase: str, severity: str, verification: str, clause: str = "4") -> str:
    return (
        f"  - id: {rule_id}\n    clause: '{clause}'\n    title_zh: 规则\n    title_en: Rule\n"
        f"    phase: {phase}\n"
        f"    check: {check}\n    severity: {severity}\n    verification: {verification}\n"
    )


MANUAL_WARNING = rule(
    "DEMO-ACC-001", "evidence.document", phase="access", severity="warning", verification="manual"
)
MANUAL_ERROR = rule(
    "DEMO-ACC-002", "evidence.document", phase="access", severity="error", verification="manual"
)
SEMI_ERROR = rule(
    "DEMO-STO-009", "evidence.document", phase="storage", severity="error", verification="semi_automatic"
)
FLAG = rule("DEMO-STO-001", "test.flag", phase="storage", severity="warning", verification="automatic")
MAX = rule("DEMO-ACQ-001", "test.max", phase="acquisition", severity="error", verification="automatic")


def run(packs, measurements=None, **kwargs) -> engine.EngineResult:  # type: ignore[no-untyped-def]
    return engine.run(
        engine.EngineInput(
            packs=packs, registry=REGISTRY, measurements=measurements or {}, as_of=AS_OF, **kwargs
        )
    )


def provided(document: str = "sop.pdf", **kwargs: object) -> EvidenceItem:
    return EvidenceItem(status=EvidenceState.PROVIDED, document=document, **kwargs)  # type: ignore[arg-type]


def checker(result: DocumentCheck, sha256: str | None = "a" * 64):  # type: ignore[no-untyped-def]
    return lambda _item: DocumentResult(result, sha256 if result is not DocumentCheck.NO_DOCUMENT else None)


# --- semi-automatic and manual evidence (A-15) -----------------------------------------------------------


@pytest.mark.parametrize(
    ("check", "status", "reason", "exit_code"),
    [
        (DocumentCheck.OK, Status.PASSED, None, 0),
        (DocumentCheck.DOCUMENT_MISSING, Status.FAILED, "evidence.document_missing", 1),
        (DocumentCheck.HASH_MISMATCH, Status.FAILED, "evidence.hash_mismatch", 1),
        (DocumentCheck.DOCUMENT_LINK, Status.FAILED, "evidence.document_link", 1),
    ],
)
def test_semi_automatic_rule_needs_the_document_and_its_hash(
    check: DocumentCheck, status: Status, reason: str | None, exit_code: int
) -> None:
    result = run([pack(SEMI_ERROR)], evidence={"DEMO-STO-009": provided()}, document_check=checker(check))
    found = [(f.status, f.reason) for f in result.findings] or [(Status.PASSED, None)]
    assert found == [(status, reason)] and result.exit_code == exit_code
    (record,) = result.evidence
    assert record.outcome is status and record.document_check is check and record.sha256 == "a" * 64
    assert not [n for n in result.notices if n.message_key.startswith("notice.evidence_document")]
    if status is Status.FAILED:
        assert result.phases[Phase.STORAGE].open_evidence == 0  # a failed document check is no open evidence


@pytest.mark.parametrize(
    "check", [DocumentCheck.DOCUMENT_MISSING, DocumentCheck.DOCUMENT_LINK, DocumentCheck.HASH_MISMATCH]
)
def test_manual_provided_stays_passed_with_a_warning(check: DocumentCheck) -> None:
    """A-83: the user's statement is kept ('nicht von NeuroGrid bewertet'); the document problem becomes a
    notice."""
    result = run([pack(MANUAL_ERROR)], evidence={"DEMO-ACC-002": provided()}, document_check=checker(check))
    assert result.findings == [] and result.exit_code == 0
    assert [p.rule_id for p in result.passed] == ["DEMO-ACC-002"]
    (record,) = result.evidence
    assert record.outcome is Status.PASSED and record.document_check is check
    notices = [(n.level, n.message_key, n.params) for n in result.notices]
    assert notices == [
        (Severity.WARNING, f"notice.evidence_document.{check.value}", {"rule": "DEMO-ACC-002"})
    ]


def test_record_per_evidence_rule_also_without_entry() -> None:
    item = EvidenceItem(
        status=EvidenceState.PARTIAL,
        document="draft.pdf",
        sha256="b" * 64,
        reviewer="QA",
        date=date(2026, 9, 1),
        comment="draft",
    )
    result = run(
        [pack(MANUAL_WARNING + MANUAL_ERROR + FLAG)],
        {"test.flag": [Measurement(check_id="test.flag", object="a", value=True)]},
        evidence={"DEMO-ACC-001": item},
        document_check=checker(DocumentCheck.OK, "c" * 64),
    )
    first, second = result.evidence
    assert [r.rule_id for r in result.evidence] == ["DEMO-ACC-001", "DEMO-ACC-002"]  # pack and rule order
    assert first.status is EvidenceState.PARTIAL and first.outcome is Status.EVIDENCE_OPEN
    assert (first.document, first.sha256, first.sha256_recorded) == ("draft.pdf", "c" * 64, "b" * 64)
    assert (first.reviewer, first.date, first.comment, first.document_check) == (
        "QA",
        date(2026, 9, 1),
        "draft",
        DocumentCheck.OK,
    )
    assert second.status is None and second.outcome is Status.EVIDENCE_OPEN and second.document is None
    finding = next(f for f in result.findings if f.rule_id == "DEMO-ACC-001")
    assert finding.reason == "evidence.partial" and finding.details["document_check"] == "ok"


@pytest.mark.parametrize(("strict", "severity"), [(False, Severity.WARNING), (True, Severity.ERROR)])
def test_record_carries_the_effective_severity(strict: bool, severity: Severity) -> None:
    """strict_severity (A-82) applies to the evidence record as to the rule's findings and results rules[]:
    a manual warning with strict_severity error is an error record in strict mode."""
    stricter = "    severity: warning\n    strict_severity: error\n"
    strict_rule = MANUAL_WARNING.replace("    severity: warning\n", stricter)
    result = run(
        [pack(strict_rule + SEMI_ERROR)],
        evidence={"DEMO-STO-009": provided()},
        document_check=checker(DocumentCheck.OK),
        strict=strict,
    )
    records = {record.rule_id: (record.outcome, record.severity) for record in result.evidence}
    assert records == {
        "DEMO-ACC-001": (Status.EVIDENCE_OPEN, severity),
        "DEMO-STO-009": (Status.PASSED, Severity.ERROR),  # no strict_severity: the base severity
    }
    (finding,) = result.findings
    assert (finding.rule_id, finding.severity) == ("DEMO-ACC-001", severity)
    assert result.exit_code == (1 if strict else 0)


def test_excepted_evidence_is_recorded_as_excepted() -> None:
    exception = engine.ExceptionEntry(rule="DEMO-ACC-002", reason="covered by the hospital SOP")
    result = run([pack(MANUAL_ERROR)], exceptions=[exception])
    assert result.evidence[0].outcome is Status.EXCEPTED and result.exit_code == 0
    assert result.phases[Phase.ACCESS].light is Light.GREEN


def test_entries_for_unknown_and_measured_rules() -> None:
    result = run(
        [pack(FLAG + MANUAL_WARNING)],
        {"test.flag": [Measurement(check_id="test.flag", object="a", value=False)]},
        evidence={
            "DEMO-STO-001": EvidenceItem(status=EvidenceState.OPEN),
            "OTHER-ACC-001": EvidenceItem(status=EvidenceState.OPEN),
            "DEMO-ACC-001": provided(),
        },
        document_check=checker(DocumentCheck.OK),
    )
    flag = next(f for f in result.findings if f.rule_id == "DEMO-STO-001")
    assert flag.status is Status.FAILED  # the entry changes nothing for a measured rule
    notices = {(n.level, n.message_key, n.params["rule"]) for n in result.notices}
    assert notices == {
        (Severity.WARNING, "notice.evidence_ignored", "DEMO-STO-001"),
        (Severity.INFO, "notice.evidence_unused", "OTHER-ACC-001"),
    }
    assert [r.rule_id for r in result.evidence] == ["DEMO-ACC-001"]


def test_review_date_after_the_reference_date_gives_a_note() -> None:
    late = provided(date=date(2026, 12, 1))
    result = run(
        [pack(MANUAL_WARNING)], evidence={"DEMO-ACC-001": late}, document_check=checker(DocumentCheck.OK)
    )
    (notice,) = result.notices
    assert notice.level is Severity.INFO and notice.message_key == "notice.evidence_date_after_as_of"
    assert notice.params == {"rule": "DEMO-ACC-001", "date": "2026-12-01", "as_of": "2026-10-11"}
    same_day = provided(date=AS_OF)
    assert not run(
        [pack(MANUAL_WARNING)], evidence={"DEMO-ACC-001": same_day}, document_check=checker(DocumentCheck.OK)
    ).notices


# --- counting and traffic light (A-16, C6) -----------------------------------------------------------------


def test_open_manual_warning_is_yellow_and_exit_zero() -> None:
    result = run([pack(MANUAL_WARNING)])
    access = result.phases[Phase.ACCESS]
    assert (access.light, access.warnings, access.errors, access.open_evidence) == (Light.YELLOW, 1, 0, 1)
    assert result.exit_code == 0


def test_open_manual_error_is_red_and_exit_one() -> None:
    result = run([pack(MANUAL_ERROR)], evidence={"DEMO-ACC-002": EvidenceItem(status=EvidenceState.PARTIAL)})
    access = result.phases[Phase.ACCESS]
    assert (access.light, access.errors, access.open_evidence, result.exit_code) == (Light.RED, 1, 1, 1)


def test_not_applicable_evidence_is_green_and_not_counted() -> None:
    item = EvidenceItem(status=EvidenceState.NOT_APPLICABLE, justification="no data at rest")
    result = run([pack(MANUAL_ERROR)], evidence={"DEMO-ACC-002": item})
    access = result.phases[Phase.ACCESS]
    assert (access.light, access.errors, access.open_evidence, result.exit_code) == (Light.GREEN, 0, 0, 0)


def test_provided_manual_rule_alone_makes_the_phase_green() -> None:
    result = run(
        [pack(MANUAL_WARNING)],
        evidence={"DEMO-ACC-001": provided()},
        document_check=checker(DocumentCheck.OK),
    )
    assert result.phases[Phase.ACCESS].light is Light.GREEN


def test_manual_rule_in_placeholder_pack_is_not_counted() -> None:
    result = run([pack(MANUAL_ERROR, status="placeholder")])
    access = result.phases[Phase.ACCESS]
    assert (access.light, access.errors, access.open_evidence, result.exit_code) == (Light.GREY, 0, 0, 0)
    assert result.evidence[0].outcome is Status.EVIDENCE_OPEN  # listed, but not evaluated (A-41)


def test_phase_with_only_not_applicable_results_is_grey() -> None:
    """C6: a phase is grey when no rule of it gave a passed or failed result."""
    measurements = {
        "test.flag": [Measurement(check_id="test.flag", object="a", state="not_applicable", reason="r")]
    }
    result = run([pack(FLAG)], measurements)
    assert result.phases[Phase.STORAGE].light is Light.GREY
    checkable = {
        "test.flag": [Measurement(check_id="test.flag", object="a", state="not_checkable", reason="r")]
    }
    assert run([pack(FLAG)], checkable).phases[Phase.STORAGE].light is Light.GREY
    assert run([pack(FLAG)], {}).phases[Phase.STORAGE].light is Light.GREY  # a rule without any measurement
    passed = {"test.flag": [Measurement(check_id="test.flag", object="a", value=True)]}
    assert run([pack(FLAG)], passed).phases[Phase.STORAGE].light is Light.GREEN
    excepted = run(
        [pack(FLAG)],
        {"test.flag": [Measurement(check_id="test.flag", object="a", value=False)]},
        exceptions=[engine.ExceptionEntry(rule="DEMO-STO-001", reason="documented")],
    )
    assert excepted.phases[Phase.STORAGE].light is Light.GREEN


def test_summary_counts_are_the_sum_over_the_phases() -> None:
    measurements = {
        "test.max": [Measurement(check_id="test.max", object="a", value=11.0)],
        "test.flag": [Measurement(check_id="test.flag", object="a", value=False)],
    }
    result = run([pack(MAX + FLAG + MANUAL_WARNING + MANUAL_ERROR)], measurements)
    assert sum(p.errors for p in result.phases.values()) == 2  # DEMO-ACQ-001 failed, DEMO-ACC-002 open
    assert sum(p.warnings for p in result.phases.values()) == 2  # DEMO-STO-001 failed, DEMO-ACC-001 open
    assert sum(p.open_evidence for p in result.phases.values()) == 2


MANUAL_INFO = rule(
    "DEMO-ANN-001", "evidence.document", phase="annotation", severity="info", verification="manual"
)


def test_open_evidence_of_an_info_rule_is_listed_but_not_counted() -> None:
    """A-16: errors and warnings contain the open evidence, open_evidence is only a breakdown of them; the
    open evidence of an info rule (a 可 clause, PRD §11) is a finding but no count (review P4, EVI33)."""
    result = run([pack(MANUAL_INFO + MANUAL_WARNING)])
    annotation = result.phases[Phase.ANNOTATION]
    assert (annotation.light, annotation.errors, annotation.warnings, annotation.open_evidence) == (
        Light.GREEN,
        0,
        0,
        0,
    )
    info = next(f for f in result.findings if f.rule_id == "DEMO-ANN-001")
    assert (info.status, info.severity) == (Status.EVIDENCE_OPEN, Severity.INFO)
    assert result.phases[Phase.ACCESS].open_evidence == 1 and result.exit_code == 0
    for summary in result.phases.values():
        assert summary.open_evidence <= summary.errors + summary.warnings


def test_open_evidence_counts_with_the_effective_severity() -> None:
    """strict_severity (A-82) decides whether open evidence is counted, as for errors and warnings."""
    raised = MANUAL_INFO.replace("    severity: info\n", "    severity: info\n    strict_severity: warning\n")
    normal = run([pack(raised)]).phases[Phase.ANNOTATION]
    strict = run([pack(raised)], strict=True).phases[Phase.ANNOTATION]
    assert (normal.light, normal.warnings, normal.open_evidence) == (Light.GREEN, 0, 0)
    assert (strict.light, strict.warnings, strict.open_evidence) == (Light.YELLOW, 1, 1)


# --- exceptions completed (A-14) ----------------------------------------------------------------------------


def _failing() -> dict[str, list[Measurement]]:
    return {
        "test.max": [Measurement(check_id="test.max", object="sub-01/eeg/r.edf", value=11.0, subkey="Fp1")]
    }


@pytest.mark.parametrize(("valid_until", "expired"), [(AS_OF, False), (date(2026, 10, 10), True)])
def test_expiry_boundary(valid_until: date, expired: bool) -> None:
    entry = engine.ExceptionEntry(rule="DEMO-ACQ-001", reason="sensor", valid_until=valid_until)
    result = run([pack(MAX)], _failing(), exceptions=[entry])
    assert (result.findings[0].status is Status.EXCEPTED) is not expired
    assert result.exceptions[0].expired is expired and result.exceptions[0].used is not expired
    assert ("notice.exception_expired" in {n.message_key for n in result.notices}) is expired


def test_every_matching_entry_counts_as_used() -> None:
    first = engine.ExceptionEntry(rule="DEMO-ACQ-001", object="sub-01/**", reason="first")
    second = engine.ExceptionEntry(rule="DEMO-ACQ-001", subkey="Fp1", reason="second")
    other = engine.ExceptionEntry(rule="DEMO-ACQ-001", subkey="Fp2", reason="other channel")
    result = run([pack(MAX)], _failing(), exceptions=[first, second, other])
    assert result.findings[0].details["exception_reason"] == "first"
    assert [use.used for use in result.exceptions] == [True, True, False]
    assert [n.message_key for n in result.notices] == ["notice.exception_unused"]


def test_exception_for_a_rule_that_is_not_loaded_is_a_warning() -> None:
    typo = engine.ExceptionEntry(rule="DEMO-ACQ-010", reason="typo in the rule ID")
    result = run([pack(MAX)], _failing(), exceptions=[typo])
    (notice,) = result.notices
    assert notice.level is Severity.WARNING and notice.message_key == "notice.exception_unknown_rule"
    assert notice.params == {"rule": "DEMO-ACQ-010"} and result.exceptions[0].used is False


def test_exception_rule_id_must_be_a_rule_id_in_neurogrid_toml() -> None:
    """The form of a rule ID is checked where neurogrid.toml is read (A-83); the entry stored in results.json
    takes any rule text, as results of P1-P3 hold it (C1, review P4 INT41)."""
    assert engine.ExceptionEntry(rule="core-m05-02", reason="lower case").rule == "core-m05-02"
    with pytest.raises(ValueError):
        ConfigExceptionEntry(rule="core-m05-02", reason="lower case")
    for rule_text in ("M05 impedance", "core-m05-02"):
        with pytest.raises(ConfigError) as info:
            parse(f'[[exceptions]]\nrule = "{rule_text}"\nreason = "x"\n')
        assert info.value.message_key == "config.invalid"
        assert info.value.params["field"] == "exceptions.0.rule"
    assert isinstance(
        parse('[[exceptions]]\nrule = "CORE-M05-02"\nreason = "x"\n').exceptions[0], ConfigExceptionEntry
    )


def test_subkey_matches_exactly() -> None:
    entry = engine.ExceptionEntry(rule="DEMO-ACQ-001", subkey="fp1", reason="case differs")
    assert run([pack(MAX)], _failing(), exceptions=[entry]).findings[0].status is Status.FAILED


# --- coverage (RP-07 contribution) -------------------------------------------------------------------------


def test_semi_automatic_must_clause_counts_as_covered_manual_does_not() -> None:
    semi = rule(
        "NORM-STO-001",
        "evidence.document",
        phase="storage",
        severity="error",
        verification="semi_automatic",
        clause="5.1",
    )
    manual = rule(
        "NORM-ACC-001",
        "evidence.document",
        phase="access",
        severity="error",
        verification="manual",
        clause="5.2",
    )
    automatic = rule(
        "NORM-ACQ-001",
        "test.flag",
        phase="acquisition",
        severity="error",
        verification="automatic",
        clause="5.3",
    )
    norm = pack(semi + manual + automatic, name="norm", status="inventory", norm=True)
    assert run([norm]).coverage["norm"] == round(2 / 3, 4)
    assert run([pack(manual, name="norm", status="inventory", norm=True)]).coverage["norm"] == 0.0
    assert run([pack(semi + manual, name="norm", status="secondary", norm=True)]).coverage["norm"] == "n/a"
