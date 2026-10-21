"""MET-02: every parameter of the check registry can be overridden in neurogrid.toml, and the override works.

Two levels:
- every parameter of every built-in rule takes the toml value (origin "config");
- every parameter of the registry changes the outcome on a fixture when overridden. A registry parameter
  without an entry in EFFECT_CASES fails the meta-test, so new thresholds cannot go untested.
"""

from __future__ import annotations

from datetime import date
from importlib import resources
from pathlib import Path

import pytest

from neurogrid import pipeline
from neurogrid.checks.registry import REGISTRY
from neurogrid.kernel.findings import Status
from neurogrid.kernel.rules import ParamValue, load_rulepack

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = date(2026, 10, 11)
OVERRIDE_VALUES: dict[str, ParamValue] = {
    "number": 123.5,
    "integer": 7,
    "boolean": True,
    "string": "override",
}

# (check, parameter) -> (fixture, override value that turns the default "passed" into "failed")
EFFECT_CASES: dict[tuple[str, str], tuple[str, ParamValue]] = {
    ("signal.sampling_rate_min", "min_hz"): ("edf_ok", 1000),
    ("signal.sampling_rate_consistency", "min_hz"): ("edf_ok", 1000),
    ("impedance.max", "max_kohm"): ("bids_ok", 3),  # bids_ok documents 3.5 kOhm per electrode
    # P3 signal quality: edf_quality_ok passes every M06–M09 rule at the defaults with these measured values
    ("quality.bad_channels", "max_fraction"): ("edf_quality_ok", 0.02),  # P8 and Pz bad: 0.1
    ("quality.line_noise", "max_ratio"): ("edf_quality_ok", 0.001),  # 2.5 µV at 50 Hz: 0.0096–0.028
    ("quality.line_frequency", "min_factor"): ("edf_quality_ok", 0.05),  # 60/50 Hz medians 0.0023/0.0184
    ("quality.flatline", "max_fraction"): ("edf_quality_ok", 0.02),  # P8 flat in 2 of 70 windows: 0.029
    ("quality.clipping", "max_fraction"): ("edf_quality_ok", 0.02),  # P8 saturated in 2 of 70 windows
    ("quality.autoreject", "max_fraction"): ("edf_quality_ok", 0.02),  # 3 of 35 epochs rejected: 0.086
    ("quality.non_brain_components", "max_fraction"): ("edf_quality_ok", 0.1),  # 5 of 17 components: 0.29
    # P4 evidence area: gxdsl008 GX-03; edf_ok is stored as EDF, so allowing only BDF fails it
    ("structure.storage_format", "formats"): ("edf_ok", "BDF"),
    # P4 ai: classes A/B/C at 0.4/0.3/0.3 in every scope of bids_ai_ok (all, train, val, test)
    ("ai.class_balance", "min_share"): ("bids_ai_ok", 0.35),
}
# check -> toml lines both runs need so that the check can be evaluated at all
BASE_CONFIG = {
    "impedance.max": '[metadata.defaults]\nelectrode_type = "wet"\n',
    "ai.class_balance": '[ai]\nlabels = "events:trial_type"\n',
}


def _toml_value(value: ParamValue) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


def _builtin_rule_params() -> list[tuple[str, str, str]]:
    cases = []
    for entry in resources.files("neurogrid.rulepacks").iterdir():
        if not entry.name.endswith(".yaml"):
            continue
        pack = load_rulepack(entry.read_bytes(), origin="builtin").pack
        for rule in pack.rules:
            for name, spec in REGISTRY[rule.check].params.items():
                cases.append((pack.rulepack, rule.id, f"{name}:{spec.kind}"))
    return cases


@pytest.mark.parametrize(("pack", "rule_id", "param"), _builtin_rule_params())
def test_builtin_parameter_override_takes_effect(tmp_path: Path, pack: str, rule_id: str, param: str) -> None:
    name, kind = param.split(":")
    value = OVERRIDE_VALUES[kind]
    packs = "" if pack == "core" else f'[check]\nrulepacks = ["core", "{pack}"]\n'
    config = tmp_path / "neurogrid.toml"
    config.write_text(f'{packs}[rules."{rule_id}".params]\n{name} = {_toml_value(value)}\n', encoding="utf-8")
    results = pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(config_path=config, as_of=AS_OF))
    effective = results.config.effective_params[rule_id][name]
    assert effective.origin == "config" and effective.value == value


def test_every_builtin_rule_with_a_threshold_is_covered() -> None:
    assert _builtin_rule_params(), "no parameterised rules found"


def test_every_registry_parameter_has_an_effect_case() -> None:
    declared = {(check_id, name) for check_id, spec in REGISTRY.items() for name in spec.params}
    assert declared == set(EFFECT_CASES)


def _meta_pack(tmp_path: Path, check_id: str) -> Path:
    pack = tmp_path / "meta.yaml"
    pack.write_text(
        "rulepack: meta\nversion: '1'\nsource: MET-02 meta-test\nsource_status: final\nrules:\n"
        "  - id: META-ACQ-001\n    clause: 'MET-02'\n    title_zh: 参数\n    title_en: Parameter\n"
        f"    phase: acquisition\n    check: {check_id}\n    severity: error\n    verification: automatic\n",
        encoding="utf-8",
    )
    return pack


@pytest.mark.parametrize(("check_id", "param"), sorted(EFFECT_CASES))
def test_parameter_override_changes_the_outcome(tmp_path: Path, check_id: str, param: str) -> None:
    fixture, value = EFFECT_CASES[(check_id, param)]
    options = {"rulepacks": (str(_meta_pack(tmp_path, check_id)),), "as_of": AS_OF}
    base = BASE_CONFIG.get(check_id, "")
    base_config = tmp_path / "base.toml"
    base_config.write_text(base, encoding="utf-8")
    default = pipeline.run_check(
        FIX / fixture,
        pipeline.CheckOptions(config_path=base_config, **options),
    )
    assert not [f for f in default.findings if f.rule_id == "META-ACQ-001"]
    assert any(p.rule_id == "META-ACQ-001" for p in default.passed)
    config = tmp_path / "neurogrid.toml"
    config.write_text(
        f'{base}[rules."META-ACQ-001".params]\n{param} = {_toml_value(value)}\n', encoding="utf-8"
    )
    overridden = pipeline.run_check(
        FIX / fixture,
        pipeline.CheckOptions(config_path=config, **options),
    )
    statuses = {f.status for f in overridden.findings if f.rule_id == "META-ACQ-001"}
    assert statuses == {Status.FAILED}
    assert overridden.config.effective_params["META-ACQ-001"][param].origin == "config"
    assert overridden.summary.exit_code == 1
