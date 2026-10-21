"""MET-01, A-20: the calibrated thresholds of M06, M07 and M09 come from the documented calibration run.

The protocol (src/neurogrid/rulepacks/calibration/core.json) names the data sets and the 95th percentile; the
rule pack ``core`` and the check defaults carry the same values. That the protocol is reproducible from the
corpus is checked in tests/corpus (``-m corpus``).
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

import calibrate
from neurogrid.checks import quality
from neurogrid.checks.registry import REGISTRY
from neurogrid.kernel.rules import load_rulepack

# rule -> the check default that must carry the same start value
DEFAULTS = {
    "CORE-M06-01": quality.BAD_CHANNELS,
    "CORE-M07-01": quality.LINE_NOISE,
    "CORE-M09-01": quality.AUTOREJECT,
    "CORE-M09-02": quality.NON_BRAIN,
}


def _protocol() -> dict[str, Any]:
    path = resources.files("neurogrid.rulepacks").joinpath("calibration/core.json")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def test_protocol_covers_the_calibrated_rules_with_at_least_three_public_datasets() -> None:
    protocol = _protocol()
    assert set(protocol["thresholds"]) == set(DEFAULTS)
    datasets = protocol["datasets"]
    assert len(datasets) >= 3  # MET-01: at least three public data sets
    assert all(entry["doi"].startswith("10.18112/openneuro.") for entry in datasets)  # A-20: OpenNeuro
    for rule, entry in protocol["thresholds"].items():
        assert entry["percentile"] == 95.0, rule
        assert entry["n"] >= 3 and entry["value"] is not None, rule
        metric = entry["metric"] if entry["metric"] != "M07" else "M07_channels"
        assert entry["n"] == sum(d[metric] for d in datasets), rule


def test_rule_pack_and_check_defaults_carry_the_protocol_values() -> None:
    pack = load_rulepack(
        resources.files("neurogrid.rulepacks").joinpath("core.yaml").read_bytes(), origin="builtin"
    ).pack
    rules = {rule.id: rule for rule in pack.rules}
    for rule_id, entry in _protocol()["thresholds"].items():
        rule = rules[rule_id]
        assert rule.check == DEFAULTS[rule_id]
        assert rule.params[entry["param"]] == entry["value"], rule_id
        assert REGISTRY[rule.check].params[entry["param"]].default == entry["value"], rule_id


def test_calibrate_check_agrees() -> None:
    assert calibrate.check() == 0
