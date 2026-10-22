"""Rule engine: thresholds, exceptions, evidence, placeholder packs, traffic light, coverage, exit code."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pytest

from neurogrid.kernel import engine
from neurogrid.kernel.errors import ConfigError, RulepackError
from neurogrid.kernel.evidence import DocumentCheck, DocumentResult, EvidenceItem, EvidenceState
from neurogrid.kernel.findings import Light, ParamValue, Phase, Status
from neurogrid.kernel.rules import (
    CheckSpec,
    Evaluation,
    Measurement,
    ParamSpec,
    at_least,
    at_most,
    evidence_spec,
    is_true,
    load_rulepack,
)

AS_OF = date(2026, 10, 11)
REGISTRY = {
    "test.max": CheckSpec("test.max", at_most("limit"), {"limit": ParamSpec("number", 10)}),
    "test.min": CheckSpec("test.min", at_least("limit"), {"limit": ParamSpec("integer", 3)}),
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


RULE_MAX = """  - id: DEMO-ACQ-001
    clause: "4.1"
    title_zh: 上限
    title_en: Upper limit
    phase: acquisition
    check: test.max
    params: {limit: 5}
    severity: error
    verification: automatic
"""
RULE_FLAG = """  - id: DEMO-STO-001
    clause: "4.2"
    title_zh: 标志
    title_en: Flag
    phase: storage
    check: test.flag
    severity: warning
    verification: automatic
"""
RULE_MANUAL = """  - id: DEMO-ACC-001
    clause: "4.3"
    title_zh: 人工
    title_en: Manual
    phase: access
    check: evidence.document
    severity: error
    verification: manual
"""


def run(packs, measurements, **kwargs) -> engine.EngineResult:  # type: ignore[no-untyped-def]
    return engine.run(
        engine.EngineInput(packs=packs, registry=REGISTRY, measurements=measurements, as_of=AS_OF, **kwargs)
    )


def m(check: str, obj: str, value: object, **kw: object) -> Measurement:
    return Measurement(check_id=check, object=obj, value=value, **kw)  # type: ignore[arg-type]


def test_pass_fail_and_exit_code() -> None:
    result = run([pack(RULE_MAX)], {"test.max": [m("test.max", "a", 4.0), m("test.max", "b", 6.0)]})
    assert [f.object for f in result.findings] == ["b"]
    assert result.findings[0].status is Status.FAILED and result.findings[0].threshold == 5
    assert result.passed[0].object == "a" and result.passed[0].count == 1
    assert result.exit_code == 1
    assert result.phases[Phase.ACQUISITION].light is Light.RED
    assert result.phases[Phase.ANNOTATION].light is Light.GREY


def test_threshold_precedence() -> None:
    result = run(
        [pack(RULE_MAX)], {"test.max": [m("test.max", "b", 6.0)]}, overrides={"DEMO-ACQ-001": {"limit": 7}}
    )
    assert result.exit_code == 0
    assert result.effective_params["DEMO-ACQ-001"]["limit"].origin == "config"
    default = run([pack(RULE_MAX.replace("    params: {limit: 5}\n", ""))], {"test.max": []})
    assert default.effective_params["DEMO-ACQ-001"]["limit"].value == 10
    assert default.effective_params["DEMO-ACQ-001"]["limit"].origin == "check"


def test_override_validation() -> None:
    with pytest.raises(ConfigError):
        run([pack(RULE_MAX)], {}, overrides={"DEMO-ACQ-001": {"nope": 1}})
    with pytest.raises(ConfigError):
        run([pack(RULE_MAX)], {}, overrides={"DEMO-ACQ-001": {"limit": "5"}})
    result = run([pack(RULE_MAX)], {}, overrides={"OTHER-1": {"x": 1}})
    assert result.notices[0].message_key == "notice.override_unused"


def test_warning_gives_yellow_and_exit_zero() -> None:
    result = run([pack(RULE_FLAG)], {"test.flag": [m("test.flag", "a", False)]})
    assert result.exit_code == 0
    assert result.phases[Phase.STORAGE].light is Light.YELLOW
    assert result.phases[Phase.STORAGE].warnings == 1


def test_exception_applies_with_object_and_subkey() -> None:
    entry = engine.ExceptionEntry(
        rule="DEMO-ACQ-001", object="sub-07/**", subkey="X1", reason="documented sensor"
    )
    measurements = {
        "test.max": [
            m("test.max", "sub-07/eeg/r.edf", 9.0, subkey="X1"),
            m("test.max", "sub-07/eeg/r.edf", 9.0, subkey="X2"),
        ]
    }
    result = run([pack(RULE_MAX)], measurements, exceptions=[entry])
    statuses = {f.subkey: f.status for f in result.findings}
    assert statuses == {"X1": Status.EXCEPTED, "X2": Status.FAILED}
    assert result.exceptions[0].used is True
    assert result.exit_code == 1


def test_expired_and_unused_exceptions() -> None:
    expired = engine.ExceptionEntry(rule="DEMO-ACQ-001", reason="old", valid_until=date(2026, 1, 1))
    unused = engine.ExceptionEntry(rule="DEMO-STO-001", reason="nothing to except")
    result = run(
        [pack(RULE_MAX + RULE_FLAG)], {"test.max": [m("test.max", "a", 9.0)]}, exceptions=[expired, unused]
    )
    assert result.findings[0].status is Status.FAILED
    keys = sorted(n.message_key for n in result.notices)
    assert keys == ["notice.exception_expired", "notice.exception_unused"]
    assert [u.expired for u in result.exceptions] == [True, False]


def test_exception_needs_reason() -> None:
    with pytest.raises(ValueError):
        engine.ExceptionEntry(rule="X-1", reason="   ")


def test_not_checkable_does_not_count() -> None:
    result = run(
        [pack(RULE_MAX)], {"test.max": [m("test.max", "a", None, state="not_checkable", reason="r")]}
    )
    assert result.findings[0].status is Status.NOT_CHECKABLE and result.exit_code == 0
    na = run([pack(RULE_MAX)], {"test.max": [m("test.max", "a", None, state="not_applicable", reason="r")]})
    assert na.findings[0].status is Status.NOT_APPLICABLE


def test_evaluator_can_find_a_measurement_not_checkable() -> None:
    """An evaluator may decide under the rule's parameters that a measurement cannot be judged (A-51: the
    verdict would reveal a withheld small cell): not_checkable with its reason, never counted, the threshold
    kept; the other measurements keep passed/failed."""

    def bounded(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
        limit = params["limit"]
        if measurement.value is None:
            return Evaluation(passed=True, threshold=limit, not_checkable="test.withheld")
        return Evaluation(passed=measurement.value <= limit, threshold=limit)

    registry = {**REGISTRY, "test.max": CheckSpec("test.max", bounded, {"limit": ParamSpec("number", 10)})}
    result = engine.run(
        engine.EngineInput(
            packs=[pack(RULE_MAX)],
            registry=registry,
            measurements={"test.max": [m("test.max", "a", None), m("test.max", "b", 4.0)]},
            as_of=AS_OF,
        )
    )
    assert [(f.object, f.status, f.reason, f.threshold) for f in result.findings] == [
        ("a", Status.NOT_CHECKABLE, "test.withheld", 5)
    ]
    assert [(p.object, p.count) for p in result.passed] == [("b", 1)] and result.exit_code == 0


@pytest.mark.parametrize(
    ("item", "status", "exit_code"),
    [
        (None, Status.EVIDENCE_OPEN, 1),
        (EvidenceItem(status=EvidenceState.OPEN), Status.EVIDENCE_OPEN, 1),
        (EvidenceItem(status=EvidenceState.PARTIAL), Status.EVIDENCE_OPEN, 1),
        (EvidenceItem(status=EvidenceState.PROVIDED, document="sop.pdf"), Status.PASSED, 0),
        (
            EvidenceItem(status=EvidenceState.NOT_APPLICABLE, justification="no storage"),
            Status.NOT_APPLICABLE,
            0,
        ),
    ],
)
def test_manual_evidence(item: EvidenceItem | None, status: Status, exit_code: int) -> None:
    evidence = {} if item is None else {"DEMO-ACC-001": item}
    result = run([pack(RULE_MANUAL)], {}, evidence=evidence)
    found = [f.status for f in result.findings] or [Status.PASSED]
    assert found == [status]
    assert result.exit_code == exit_code
    if status is Status.EVIDENCE_OPEN:
        assert result.phases[Phase.ACCESS].errors == 1 and result.phases[Phase.ACCESS].open_evidence == 1


def test_semi_automatic_document_check() -> None:
    body = RULE_MANUAL.replace("verification: manual", "verification: semi_automatic")
    item = EvidenceItem(status=EvidenceState.PROVIDED, document="sop.pdf")
    failed = run([pack(body)], {}, evidence={"DEMO-ACC-001": item})
    assert (
        failed.findings[0].status is Status.FAILED
        and failed.findings[0].reason == "evidence.document_missing"
    )
    ok = run(
        [pack(body)],
        {},
        evidence={"DEMO-ACC-001": item},
        document_check=lambda _: DocumentResult(DocumentCheck.OK, "0" * 64),
    )
    assert ok.findings == []


def test_evidence_not_applicable_needs_justification() -> None:
    with pytest.raises(ValueError):
        EvidenceItem(status=EvidenceState.NOT_APPLICABLE)


def test_placeholder_findings_do_not_count() -> None:
    result = run([pack(RULE_MAX, status="placeholder", norm=True)], {"test.max": [m("test.max", "a", 9.0)]})
    assert result.findings[0].status is Status.FAILED
    assert result.exit_code == 0
    assert result.phases[Phase.ACQUISITION].light is Light.GREY
    assert result.coverage["demo"] == "n/a"


def test_coverage_for_norm_packs() -> None:
    norm = pack(RULE_MAX + RULE_MANUAL, status="inventory", norm=True)
    assert run([norm], {}).coverage["demo"] == 0.5
    assert run([pack(RULE_FLAG, status="final", norm=True)], {}).coverage["demo"] == "n/a"
    assert run([pack(RULE_MAX, status="final", norm=False)], {}).coverage["demo"] == "n/a"
    assert run([pack(RULE_MAX, status="secondary", norm=True)], {}).coverage["demo"] == "n/a"


def test_registry_validation() -> None:
    unknown = RULE_MAX.replace("check: test.max", "check: test.unknown")
    with pytest.raises(RulepackError) as info:
        run([pack(unknown)], {})
    assert info.value.message_key == "rulepack.unknown_check"
    bad_param = RULE_MAX.replace("params: {limit: 5}", "params: {other: 5}")
    with pytest.raises(RulepackError):
        run([pack(bad_param)], {})
    bad_type = RULE_MAX.replace("params: {limit: 5}", "params: {limit: 'five'}")
    with pytest.raises(RulepackError):
        run([pack(bad_type)], {})
    manual_wrong = RULE_FLAG.replace("verification: automatic", "verification: manual")
    with pytest.raises(RulepackError):
        run([pack(manual_wrong)], {})
    with pytest.raises(RulepackError):
        run([pack(RULE_MAX), pack(RULE_MAX, name="other")], {})


def test_findings_sorted_and_keys_stable() -> None:
    result = run(
        [pack(RULE_MAX + RULE_FLAG)],
        {
            "test.max": [m("test.max", "z", 9.0), m("test.max", "a", 9.0)],
            "test.flag": [m("test.flag", "a", False)],
        },
    )
    assert [(f.rule_id, f.object) for f in result.findings] == [
        ("DEMO-ACQ-001", "a"),
        ("DEMO-ACQ-001", "z"),
        ("DEMO-STO-001", "a"),
    ]
    assert len({f.key for f in result.findings}) == 3


def test_exception_matches_identity_and_key_uses_it() -> None:
    loaded = pack(RULE_FLAG)
    measurement = Measurement(
        check_id="test.flag",
        object="rec-1234abcd",
        value=False,
        identity=("site-A/rec.edf", "rec-1234abcd"),
    )
    shown = Measurement(
        check_id="test.flag",
        object="site-A/rec.edf",
        value=False,
        identity=("site-A/rec.edf", "rec-1234abcd"),
    )
    entries = [engine.ExceptionEntry(rule="DEMO-STO-001", object="site-A/**", reason="SOP")]
    keys = []
    for m in (measurement, shown):
        for pattern_entries in (entries, [entries[0].model_copy(update={"object": "rec-1234abcd"})]):
            result = engine.run(
                engine.EngineInput(
                    packs=[loaded],
                    registry=REGISTRY,
                    measurements={"test.flag": [m]},
                    as_of=AS_OF,
                    exceptions=pattern_entries,
                )
            )
            assert result.findings[0].status is Status.EXCEPTED
            keys.append(result.findings[0].key)
    assert len(set(keys)) == 1


def test_exception_entry_is_strict() -> None:
    with pytest.raises(ValueError):
        engine.ExceptionEntry.model_validate({"rule": "X-1", "reason": "r", "valid_until": "2027-01-01"})


def test_findings_carry_params_with_origin() -> None:
    result = engine.run(
        engine.EngineInput(
            packs=[pack(RULE_MAX)],
            registry=REGISTRY,
            measurements={"test.max": [Measurement(check_id="test.max", object="r", value=7)]},
            as_of=AS_OF,
            overrides={"DEMO-ACQ-001": {"limit": 6}},
        )
    )
    finding = result.findings[0]
    assert finding.params["limit"].value == 6 and finding.params["limit"].origin == "config"
