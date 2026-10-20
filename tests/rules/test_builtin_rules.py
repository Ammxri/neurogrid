"""Every rule of every built-in rule pack has a positive and a negative case (NG-N08).

A case names a fixture folder (and optionally a config and further rule packs) and the expected status of
the rule there: "passed" (positive case) or a non-passing status (negative case).
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
    rulepacks: tuple[str, ...] = ()


WET = '[metadata.defaults]\nelectrode_type = "wet"\n'
DRY = '[metadata.defaults]\nelectrode_type = "dry"\n'
RAW_DOCUMENTED = (
    '[metadata.defaults]\nreference = "Cz"\nline_frequency_hz = 50\nsoftware_filters = "n/a"\n'
    '[[convert.files]]\npath = "rec.vhdr"\nsubject = "01"\ntask = "rest"\n'
)
BIDS = ("bids",)


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
    # P2: further formats, companions, metadata, channels, impedance and the BIDS validator
    Case("CORE-M01-01", "bdf_ok", Status.PASSED),
    Case("CORE-M01-01", "brainvision_ok", Status.PASSED),
    Case("CORE-M01-01", "eeglab_ok", Status.PASSED),
    Case("CORE-M01-01", "eeglab_embedded", Status.PASSED),
    Case("CORE-M01-01", "brainvision_missing", Status.FAILED),
    Case("CORE-M01-02", "bdf_ok", Status.PASSED),
    Case("CORE-M01-02", "bdf_truncated", Status.FAILED),
    Case("CORE-M01-02", "brainvision_truncated", Status.FAILED),
    Case("CORE-M01-03", "brainvision_ok", Status.PASSED),
    Case("CORE-M01-03", "eeglab_ok", Status.PASSED),
    Case("CORE-M01-03", "brainvision_missing", Status.FAILED),
    Case("CORE-M01-03", "brainvision_unsafe", Status.FAILED),
    Case("CORE-M01-04", "orphan", Status.FAILED),
    Case("CORE-M02-01", "bids_ok", Status.PASSED),
    Case("CORE-M02-01", "brainvision_ok", Status.PASSED, RAW_DOCUMENTED),
    Case("CORE-M02-01", "bids_issues", Status.FAILED),
    Case("CORE-M02-01", "brainvision_ok", Status.FAILED),
    Case("CORE-M02-02", "bids_ok", Status.PASSED),
    Case("CORE-M02-02", "bids_issues", Status.FAILED),
    Case("CORE-M03-03", "bids_ok", Status.PASSED),
    Case("CORE-M03-03", "bids_issues", Status.FAILED),
    Case("CORE-M04-01", "bids_ok", Status.PASSED),
    Case("CORE-M04-01", "bids_issues", Status.FAILED),
    Case("CORE-M04-01", "bids_issues", Status.PASSED, '[metadata.channel_map]\nEXG1 = "Oz"\n'),
    Case("CORE-M04-02", "bids_ok", Status.PASSED),
    Case("CORE-M04-02", "bids_issues", Status.FAILED),
    Case("CORE-M04-03", "bids_ok", Status.PASSED),
    Case("CORE-M04-03", "bids_issues", Status.FAILED),
    Case("CORE-M04-04", "bids_ok", Status.PASSED),
    Case("CORE-M04-04", "bids_issues", Status.FAILED),
    Case("CORE-M04-05", "bids_ok", Status.PASSED),
    Case("CORE-M04-05", "bids_issues", Status.FAILED),
    Case("CORE-M05-01", "bids_ok", Status.PASSED),
    Case("CORE-M05-01", "brainvision_ok", Status.PASSED),
    Case("CORE-M05-01", "bids_issues", Status.FAILED),
    Case("CORE-M05-01", "brainvision_impedance", Status.FAILED),
    Case("CORE-M05-02", "bids_ok", Status.PASSED, WET),
    Case("CORE-M05-02", "brainvision_ok", Status.PASSED, WET),
    Case("CORE-M05-02", "bids_issues", Status.FAILED, WET),
    Case("CORE-M05-02", "brainvision_impedance", Status.FAILED, WET),
    Case("CORE-M05-02", "bids_ok", Status.NOT_CHECKABLE),
    Case("CORE-M05-02", "bids_issues", Status.NOT_APPLICABLE, DRY),
    Case("BIDS-STO-001", "bids_ok", Status.PASSED, rulepacks=BIDS),
    Case("BIDS-STO-001", "bids_issues", Status.FAILED, rulepacks=BIDS),
    Case("BIDS-STO-001", "edf_ok", Status.NOT_APPLICABLE, rulepacks=BIDS),
    Case("BIDS-STO-002", "bids_ok", Status.PASSED, rulepacks=BIDS),
    Case("BIDS-STO-002", "bids_issues", Status.FAILED, rulepacks=BIDS),
    Case("BIDS-STO-003", "bids_ok", Status.PASSED, rulepacks=BIDS),
    Case("BIDS-STO-003", "bids_issues", Status.FAILED, rulepacks=BIDS),
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
    results = pipeline.run_check(
        FIX / case.folder, pipeline.CheckOptions(config_path=config_path, rulepacks=case.rulepacks)
    )
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
