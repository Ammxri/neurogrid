"""Every rule of every built-in rule pack has a positive and a negative case (NG-N08).

A case names a fixture folder (and optionally a config) and the expected status of the rule there:
"passed" (positive case) or a non-passing status (negative case).
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import pytest

from neurogrid import pipeline
from neurogrid.kernel.findings import Status
from neurogrid.kernel.rules import load_rulepack

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"


@dataclass(frozen=True)
class Case:
    rule: str
    folder: str
    expected: Status
    config: str | None = None


CASES = [
    Case("CORE-M01-01", "edf_ok", Status.PASSED),
    Case("CORE-M01-01", "empty", Status.FAILED),
    Case("CORE-M01-02", "edf_ok", Status.PASSED),
    Case("CORE-M01-02", "edf_truncated", Status.FAILED),
    Case("CORE-M01-04", "edf_ok", Status.PASSED),
    Case("CORE-M01-04", "unsupported", Status.FAILED),
    Case("CORE-M01-05", "edf_ok", Status.PASSED),
    Case("CORE-M01-05", "edf_identifying", Status.FAILED),
    Case("CORE-M03-01", "edf_ok", Status.PASSED),
    Case("CORE-M03-01", "edf_lowrate", Status.FAILED),
    Case("CORE-M03-02", "edf_ok", Status.PASSED),
    Case("CORE-M03-02", "edf_mixed", Status.FAILED),
    Case(
        "CORE-M03-02",
        "edf_mixed",
        Status.PASSED,
        '[metadata]\nmixed_sampling_rates_reason = "two amplifiers"\n',
    ),
]


def builtin_rule_ids() -> set[str]:
    ids = set()
    for entry in resources.files("neurogrid.rulepacks").iterdir():
        if entry.name.endswith(".yaml"):
            pack = load_rulepack(entry.read_text(encoding="utf-8"), origin="builtin").pack
            ids.update(rule.id for rule in pack.rules)
    return ids


def statuses(case: Case, tmp_path: Path) -> set[Status]:
    config_path = None
    if case.config:
        config_path = tmp_path / "neurogrid.toml"
        config_path.write_text(case.config, encoding="utf-8")
    results = pipeline.run_check(FIX / case.folder, pipeline.CheckOptions(config_path=config_path))
    found = {f.status for f in results.findings if f.rule_id == case.rule}
    if any(p.rule_id == case.rule for p in results.passed):
        found.add(Status.PASSED)
    return found


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c.rule}-{c.folder}-{c.expected.value}")
def test_rule_case(case: Case, tmp_path: Path) -> None:
    found = statuses(case, tmp_path)
    if case.expected is Status.PASSED:
        assert found == {Status.PASSED}
    else:
        assert case.expected in found


def test_every_builtin_rule_has_positive_and_negative_case() -> None:
    positive = {c.rule for c in CASES if c.expected is Status.PASSED}
    negative = {c.rule for c in CASES if c.expected is not Status.PASSED}
    missing = sorted((builtin_rule_ids() - positive) | (builtin_rule_ids() - negative))
    assert not missing, f"rules without positive and negative case: {missing}"
