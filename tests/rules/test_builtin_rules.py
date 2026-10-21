"""Every rule of every built-in rule pack has a positive and a negative case (NG-N08).

A case names a fixture folder (and optionally a config and further rule packs) and the expected status of
the rule there: "passed" (positive case) or a non-passing status (negative case). A case may name a setup
(SETUPS) that prepares the run in a temporary folder, e.g. a copy of the fixture with a manifest or an
evidence file, and further CheckOptions fields such as ``strict``.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
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
    setup: str | None = None  # name in SETUPS
    options: tuple[tuple[str, object], ...] = ()  # further CheckOptions fields, e.g. (("strict", True),)


# name -> function(fixture folder, temporary folder) -> (folder to check, further CheckOptions fields)
SETUPS: dict[str, Callable[[Path, Path], tuple[Path, dict[str, object]]]] = {}


WET = '[metadata.defaults]\nelectrode_type = "wet"\n'
DRY = '[metadata.defaults]\nelectrode_type = "dry"\n'
RAW_DOCUMENTED = (
    '[metadata.defaults]\nreference = "Cz"\nline_frequency_hz = 50\nsoftware_filters = "n/a"\n'
    '[[convert.files]]\npath = "rec.vhdr"\nsubject = "01"\ntask = "rest"\n'
)
BIDS = ("bids",)
# documents 60 Hz for data with 50 Hz line noise (A-47)
LINE_60_HZ = "[metadata.defaults]\nline_frequency_hz = 60\n"
# P4 annotation (M10, A-80): continuous sleep staging with the vocabulary of tools/gen_fixtures.py
CONTINUOUS = (
    '[annotation]\nmode = "continuous"\nepoch_s = 30\n'
    'vocabulary = ["W", "N1", "N2", "N3", "R", "Lights off"]\n'
)
# the hypnograms of annotation_continuous_ok under names the stem heuristic cannot attach (see SETUPS)
FILES_TABLE = CONTINUOUS + "".join(
    f'[[annotation.files]]\npath = "scoring/hyp_{n}.edf"\nrecording = "night.edf"\nannotator = "s{n}"\n'
    for n in (1, 2, 3)
)


def _renamed_hypnograms(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    """A copy of the fixture whose hypnograms only [[annotation.files]] can attach (A-80)."""
    target = tmp / "renamed"
    (target / "scoring").mkdir(parents=True)
    shutil.copy2(fixture / "night.edf", target / "night.edf")
    for n in (1, 2, 3):
        shutil.copy2(fixture / f"night_scorer{n}.edf", target / "scoring" / f"hyp_{n}.edf")
    return target, {}


SETUPS["annotation_files_table"] = _renamed_hypnograms


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
    # P3: signal quality M06–M09 at the calibrated thresholds, all from the measured values of the synthetic
    # recordings (tools/gen_fixtures.py): edf_quality_ok passes every rule, edf_quality_issues has one problem
    # per rule, edf_quality_artefacts is dominated by artefacts (ICLabel).
    Case("CORE-M06-01", "edf_quality_ok", Status.PASSED),  # 2 of 20 channels bad (0.1)
    Case("CORE-M06-01", "edf_quality_issues", Status.FAILED),  # 10 of 20 channels bad (0.5)
    Case("CORE-M06-01", "edf_ok", Status.NOT_CHECKABLE),  # 10 s of data: quality.too_short (A-79)
    Case("CORE-M07-01", "edf_quality_ok", Status.PASSED),  # ratios 0.0096–0.028
    Case("CORE-M07-01", "edf_quality_issues", Status.FAILED),  # 40 µV hum on T7, T8, P7, P8 (ratio ≥ 5)
    Case("CORE-M07-02", "edf_quality_ok", Status.PASSED),  # documented 50 Hz fits the 50 Hz hum
    Case("CORE-M07-02", "edf_quality_ok", Status.FAILED, LINE_60_HZ),  # 50 Hz median 8 × the 60 Hz one
    Case("CORE-M08-01", "edf_quality_ok", Status.PASSED),  # P8 flat in 2 of 70 windows (2.9 %)
    Case("CORE-M08-01", "edf_quality_issues", Status.FAILED),  # O2 flat for 10 s (14 %)
    Case("CORE-M08-02", "edf_quality_ok", Status.PASSED),  # P8 at the digital maximum in 2 of 70 windows
    Case("CORE-M08-02", "edf_quality_issues", Status.FAILED),  # F8 at the digital maximum for 6 s (8.6 %)
    Case("CORE-M09-01", "edf_quality_ok", Status.PASSED),  # 3 of 35 epochs rejected (0.086)
    Case("CORE-M09-01", "edf_quality_issues", Status.FAILED),  # 22 of 35 epochs rejected (0.63)
    Case("CORE-M09-02", "edf_quality_ok", Status.PASSED),  # 5 of 17 components not brain (0.29)
    Case("CORE-M09-02", "edf_quality_artefacts", Status.FAILED),  # 17 of 19 components not brain (0.89)
    Case("CORE-M09-02", "edf_quality_issues", Status.NOT_CHECKABLE),  # 10 good channels, ICA needs 16
    # --- P4 annotation (M10, A-80): fixtures of tools/gen_fixtures.py ---
    Case("CORE-M10-01", "annotation_continuous_ok", Status.PASSED, CONTINUOUS),  # mean kappa 0.667
    Case("CORE-M10-01", "annotation_continuous_issues", Status.FAILED, CONTINUOUS),  # mean kappa 0.024
    Case("CORE-M10-01", "edf_ok", Status.NOT_APPLICABLE),  # no annotations: one dataset-level finding
    Case(
        "CORE-M10-01",
        "annotation_continuous_ok",
        Status.PASSED,
        FILES_TABLE,
        setup="annotation_files_table",
    ),
    Case("CORE-M10-02", "annotation_continuous_ok", Status.PASSED, CONTINUOUS),
    Case("CORE-M10-02", "annotation_continuous_issues", Status.FAILED, CONTINUOUS),  # "Stage 2"
    Case("CORE-M10-02", "bids_events_issues", Status.FAILED),  # "stimx" not in events.json Levels
    Case("CORE-M10-03", "annotation_continuous_ok", Status.PASSED, CONTINUOUS),
    Case("CORE-M10-03", "annotation_continuous_issues", Status.FAILED, CONTINUOUS),  # 180-210 s unscored
    Case("CORE-M10-03", "annotation_continuous_ok", Status.NOT_APPLICABLE),  # events mode
    Case("CORE-M10-04", "annotation_continuous_ok", Status.PASSED, CONTINUOUS),
    Case("CORE-M10-04", "annotation_continuous_issues", Status.FAILED, CONTINUOUS),  # 80-90 s
    Case("CORE-M10-04", "bids_events_issues", Status.FAILED),  # two "standard" events overlap
]


def builtin_rule_ids() -> set[str]:
    ids: set[str] = set()
    for entry in resources.files("neurogrid.rulepacks").iterdir():
        if entry.name.endswith(".yaml"):
            pack = load_rulepack(entry.read_text(encoding="utf-8"), origin="builtin").pack
            ids.update(rule.id for rule in pack.rules)
    return ids


# Statuses per rule of one run, keyed by fixture, configuration and rule packs. A run is deterministic, so
# the cases of the same run share it: the signal quality sample (M06/M09) costs seconds per recording.
_RUNS: dict[tuple[object, ...], dict[str, set[Status]]] = {}


def statuses(case: Case, tmp_path: Path) -> set[Status]:
    key = (case.folder, case.config, case.rulepacks, case.setup, case.options)
    if key not in _RUNS:
        config_path = None
        if case.config:
            config_path = tmp_path / "neurogrid.toml"
            config_path.write_text(case.config, encoding="utf-8")
        target, extra = FIX / case.folder, {}
        if case.setup:
            target, extra = SETUPS[case.setup](FIX / case.folder, tmp_path / "setup")
        options = {**dict(case.options), **extra}
        results = pipeline.run_check(
            target,
            pipeline.CheckOptions(config_path=config_path, rulepacks=case.rulepacks, **options),  # type: ignore[arg-type]
        )
        by_rule: dict[str, set[Status]] = {}
        for finding in results.findings:
            by_rule.setdefault(finding.rule_id, set()).add(finding.status)
        for passed in results.passed:
            by_rule.setdefault(passed.rule_id, set()).add(Status.PASSED)
        _RUNS[key] = by_rule
    return set(_RUNS[key].get(case.rule, set()))


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
