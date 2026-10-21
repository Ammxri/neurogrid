"""Rule-pack field ``strict_severity`` (RP-01 extension like A-62, A-82): applied by the engine in strict mode
(--strict or [check] strict), never by a check (ARC-02); CORE-M13-01 is a warning, in strict mode an error."""

from __future__ import annotations

import json
from datetime import date
from importlib import resources
from pathlib import Path

import jsonschema
import pytest

from neurogrid.kernel import engine
from neurogrid.kernel.errors import RulepackError
from neurogrid.kernel.findings import Light, Phase, Severity, Status
from neurogrid.kernel.rules import CheckSpec, Measurement, is_true, load_rulepack

AS_OF = date(2026, 10, 11)
SCHEMA = Path(__file__).parent.parent.parent / "src" / "neurogrid" / "schemas" / "rulepack.schema.json"
PACK = """rulepack: demo
version: '1.0'
source: Test
source_status: final
rules:
  - id: DEMO-STO-001
    clause: "1"
    title_zh: 清单
    title_en: Manifest
    phase: storage
    check: test.flag
    severity: warning
    strict_severity: {strict}
    verification: automatic
"""
REGISTRY = {"test.flag": CheckSpec("test.flag", is_true)}


def _run(strict: bool, value: bool = False, severity: str = "error") -> engine.EngineResult:
    pack = load_rulepack(PACK.format(strict=severity), origin="path")
    return engine.run(
        engine.EngineInput(
            packs=[pack],
            registry=REGISTRY,
            measurements={"test.flag": [Measurement(check_id="test.flag", object="dataset", value=value)]},
            as_of=AS_OF,
            strict=strict,
        )
    )


def test_strict_mode_turns_the_warning_into_an_error() -> None:
    normal = _run(strict=False)
    assert [(f.severity, f.status) for f in normal.findings] == [(Severity.WARNING, Status.FAILED)]
    assert normal.phases[Phase.STORAGE].light is Light.YELLOW and normal.exit_code == 0
    strict = _run(strict=True)
    assert [(f.severity, f.status) for f in strict.findings] == [(Severity.ERROR, Status.FAILED)]
    assert strict.phases[Phase.STORAGE].light is Light.RED and strict.exit_code == 1
    assert strict.phases[Phase.STORAGE].errors == 1 and strict.phases[Phase.STORAGE].warnings == 0


def test_strict_severity_only_matters_for_findings() -> None:
    passed = _run(strict=True, value=True)
    assert passed.findings == [] and passed.exit_code == 0
    assert passed.phases[Phase.STORAGE].light is Light.GREEN
    milder = _run(strict=True, severity="info")  # the field may also lower a severity in strict mode
    assert [f.severity for f in milder.findings] == [Severity.INFO] and milder.exit_code == 0


def test_rule_without_strict_severity_keeps_its_severity() -> None:
    pack = load_rulepack(PACK.replace("    strict_severity: {strict}\n", ""), origin="path")
    rule = pack.pack.rules[0]
    assert rule.strict_severity is None
    assert rule.effective_severity(True) is Severity.WARNING is rule.effective_severity(False)


def test_invalid_strict_severity_is_refused() -> None:
    with pytest.raises(RulepackError) as info:
        load_rulepack(PACK.format(strict="fatal"), origin="path")
    assert info.value.params["field"] == "strict_severity"


def test_rule_pack_schema_lists_strict_severity() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    data = {
        "rulepack": "demo",
        "version": "1.0",
        "source": "Test",
        "source_status": "final",
        "rules": [
            {
                "id": "DEMO-STO-001",
                "clause": "1",
                "title_zh": "清单",
                "title_en": "Manifest",
                "phase": "storage",
                "check": "test.flag",
                "severity": "warning",
                "strict_severity": "error",
                "verification": "automatic",
            }
        ],
    }
    jsonschema.validate(data, schema)
    data["rules"][0]["strict_severity"] = "fatal"  # type: ignore[index]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_core_m13_01_uses_strict_severity() -> None:
    text = resources.files("neurogrid.rulepacks").joinpath("core.yaml").read_bytes()
    rules = {rule.id: rule for rule in load_rulepack(text, origin="builtin").pack.rules}
    assert (rules["CORE-M13-01"].severity, rules["CORE-M13-01"].strict_severity) == (
        Severity.WARNING,
        Severity.ERROR,
    )
    assert rules["CORE-M13-02"].severity is Severity.ERROR and rules["CORE-M13-02"].strict_severity is None
    assert rules["CORE-M13-03"].severity is Severity.WARNING
    others = [rule.id for rule in rules.values() if rule.strict_severity is not None]
    assert others == ["CORE-M13-01"]
