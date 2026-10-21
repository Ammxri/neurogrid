"""Public test corpus (LIB-09, E4; KONZEPT §5 "Korpus"): all six data sets (five formats) are read without
M01 errors, real metadata errors are found (golden list), and one recording per format converts to BIDS
without validator errors (NG-F01, NG-F02, NG-F05, M01-M05).

Run with ``python -m pytest -m corpus`` after ``python tools/corpus.py fetch``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import date
from functools import cache
from pathlib import Path

import pytest

from neurogrid import pipeline
from neurogrid.kernel.findings import Status
from neurogrid.model.results import Results

pytestmark = pytest.mark.corpus

ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS = ROOT / ".local" / "corpus"
AS_OF = date(2026, 10, 11)
DATASETS = {  # local folder -> (format, number of recordings in the subset of tools/corpus_spec.json)
    "ds003775-1.2.1": ("EDF", 8),
    "ds002778-1.0.5": ("BDF", 5),
    "ds004148-1.0.1": ("BrainVision", 3),
    "ds004504-1.0.9": ("EEGLAB", 5),
    "ds000248-1.2.4": ("FIF", 1),
    "psg-ipa-1.0.0": ("EDF", 78),  # 3 polysomnographies + 75 annotation-only hypnogram files
}
READ_RULES = ("CORE-M01-01", "CORE-M01-02", "CORE-M01-03", "CORE-M01-04")


@cache
def _check(name: str) -> Results:
    packs = ("bids",) if name.startswith("ds") else ()
    return pipeline.run_check(CORPUS / name, pipeline.CheckOptions(rulepacks=packs, as_of=AS_OF))


def _failed(results: Results, rule: str) -> list[tuple[str, str | None]]:
    return [(f.object, f.subkey) for f in results.findings if f.rule_id == rule and f.status is Status.FAILED]


def test_corpus_is_complete_and_unchanged() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "corpus.py"), "verify", "--root", str(CORPUS)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, f"run python tools/corpus.py fetch first\n{result.stdout}{result.stderr}"


@pytest.mark.parametrize("name", sorted(DATASETS))
def test_every_dataset_is_read_without_m01_errors(name: str) -> None:
    results = _check(name)
    expected_format, count = DATASETS[name]
    assert results.summary.exit_code in (0, 1)
    assert len(results.recordings) == count
    assert {r.format for r in results.recordings} == {expected_format}
    for rule in READ_RULES:
        assert _failed(results, rule) == [], rule


def test_psg_hypnograms_are_annotation_only() -> None:
    results = _check("psg-ipa-1.0.0")
    not_applicable = {
        f.object
        for f in results.findings
        if f.rule_id == "CORE-M04-01" and f.reason == "recording.annotations_only"
    }
    assert len(not_applicable) == 75


def test_golden_list_of_real_metadata_errors() -> None:
    """Errors present in the published data (checked against the files, see FORTSCHRITT.md P2)."""
    ds000248 = _check("ds000248-1.2.4")  # Name is " ", meg.json has no EEGReference, EEG 001-060
    assert ("dataset", "Name") in _failed(ds000248, "CORE-M02-02")
    assert [s for _o, s in _failed(ds000248, "CORE-M02-01")] == ["EEGReference"]
    assert {s for _o, s in _failed(ds000248, "CORE-M04-01")} == {f"EEG {i:03d}" for i in range(1, 61)}

    ds002778 = _check("ds002778-1.0.5")  # EEGReference "n/a"; EXG1-EXG8 have no 10-20 names
    assert {s for _o, s in _failed(ds002778, "CORE-M02-01")} == {"EEGReference"}
    assert len(_failed(ds002778, "CORE-M02-01")) == 5
    assert {s for _o, s in _failed(ds002778, "CORE-M04-01")} == {f"EXG{i}" for i in range(1, 9)}

    ds004148 = _check("ds004148-1.0.1")  # BIDSVersion "1.2"; EEGChannelCount 64 for 61 EEG channels
    assert ("dataset", "BIDSVersion") in _failed(ds004148, "CORE-M02-02")
    count = next(f for f in ds004148.findings if f.rule_id == "CORE-M04-04")
    assert count.measured_value["sidecar_eeg"] == 64 and count.measured_value["channels_tsv_eeg"] == 61

    ds004504 = _check("ds004504-1.0.9")  # BIDSVersion "v1.2.1"
    assert ("dataset", "BIDSVersion") in _failed(ds004504, "CORE-M02-02")

    ds003775 = _check("ds003775-1.2.1")  # no error-level finding
    assert ds003775.summary.exit_code == 0 and ds003775.summary.errors == 0


def test_validator_findings_carry_their_code() -> None:
    results = _check("ds004148-1.0.1")
    codes = {f.subkey for f in results.findings if f.rule_id == "BIDS-STO-002"}
    assert "EEG_CHANNEL_COUNT_MISMATCH" in codes  # agrees with CORE-M04-04 above
    assert all(f.details.get("validator_code") for f in results.findings if f.rule_id.startswith("BIDS-"))


CONVERT = {  # format -> files of one recording (the first is the data file)
    "EDF": ["ds003775-1.2.1/sub-001/ses-t1/eeg/sub-001_ses-t1_task-resteyesc_eeg.edf"],
    "BDF": ["ds002778-1.0.5/sub-hc1/ses-hc/eeg/sub-hc1_ses-hc_task-rest_eeg.bdf"],
    "BrainVision": [
        f"ds004148-1.0.1/sub-01/ses-session1/eeg/sub-01_ses-session1_task-eyesclosed_eeg.{ext}"
        for ext in ("vhdr", "eeg", "vmrk")
    ],
    "EEGLAB": ["ds004504-1.0.9/sub-001/eeg/sub-001_task-eyesclosed_eeg.set"],
    "FIF": ["ds000248-1.2.4/sub-01/meg/sub-01_task-audiovisual_run-01_meg.fif"],
}


@pytest.mark.parametrize("fmt", sorted(CONVERT))
@pytest.mark.parametrize("strip", [False, True], ids=["keep-headers", "strip-headers"])
def test_one_recording_per_format_converts_without_validator_errors(
    fmt: str, strip: bool, tmp_path: Path
) -> None:
    raw = tmp_path / "raw"
    (raw / ".neurogrid").mkdir(parents=True)
    for relative in CONVERT[fmt]:
        shutil.copy2(CORPUS / relative, raw / Path(relative).name)
    main = Path(CONVERT[fmt][0]).name
    (raw / ".neurogrid" / "neurogrid.toml").write_text(
        '[metadata.defaults]\nreference = "Cz"\nline_frequency_hz = 50\nsoftware_filters = "n/a"\n'
        f'[[convert.files]]\npath = "{main}"\nsubject = "01"\ntask = "rest"\n',
        encoding="utf-8",
    )
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, strip_identifying_headers=strip, work_base=tmp_path)
    assert (summary.converted, summary.skipped, summary.validator_errors) == (1, [], 0)
    assert summary.exit_code == 0
    checked = pipeline.run_check(out, pipeline.CheckOptions(rulepacks=("bids",), as_of=AS_OF))
    assert _failed(checked, "BIDS-STO-001") == []
    for rule in READ_RULES:
        assert _failed(checked, rule) == [], rule
    if strip:
        assert _failed(checked, "CORE-M01-05") == []


# --- P3: signal quality (NG-F07, MET-01, A-20, A-79) -------------------------------------------------------

SAMPLE_METRICS = ("M06", "M09a", "M09b")
OPENNEURO = sorted(name for name in DATASETS if name.startswith("ds"))


@pytest.mark.parametrize("name", OPENNEURO)
def test_every_quality_value_is_measured_on_the_openneuro_recordings(name: str) -> None:
    """NG-F07: all values per recording in results.json; every OpenNeuro recording enters the calibration."""
    results = _check(name)
    for rec in results.recordings:
        metrics = rec.metrics
        assert metrics["M07"]["channels"] and metrics["M08"]["channels"], rec.id
        for key in SAMPLE_METRICS:
            assert metrics[key]["state"] == "measured", (rec.id, key, metrics[key])
        assert rec.sample is not None and rec.sample["positions"] != "none", rec.id


def test_montage_sources_follow_a60() -> None:
    """A-60/A-79: FIF positions from the file; ds004148's electrodes.tsv has no coordsystem.json, so the
    template montage is used and the reason is reported; BioSemi EXG1-8 are left out of the sample."""
    (fif,) = _check("ds000248-1.2.4").recordings
    assert fif.sample is not None and fif.sample["positions"] == "header" and fif.sample["channels"] == 60
    for rec in _check("ds004148-1.0.1").recordings:
        assert rec.sample is not None and rec.sample["positions"] == "standard_montage"
        assert rec.sample["positions_unused"] == {"sidecar": "coordsystem_missing"}
    for rec in _check("ds002778-1.0.5").recordings:
        assert rec.sample is not None
        assert rec.sample["excluded_channels"] == [f"EXG{i}" for i in range(1, 9)]


def test_psg_sample_metrics_are_not_checkable_with_three_channels() -> None:
    """A-79: fewer than 16 EEG channels: M06/M09 not_checkable, never exit 2."""
    results = _check("psg-ipa-1.0.0")
    assert results.summary.exit_code in (0, 1)
    psg = [rec for rec in results.recordings if rec.metrics]
    assert len(psg) == 3
    for rec in psg:
        for key in SAMPLE_METRICS:
            assert rec.metrics[key]["state"] == "not_checkable", (rec.id, key)
            assert rec.metrics[key]["reason"] == "quality.too_few_channels", (rec.id, key)


def test_calibration_protocol_is_reproducible_from_the_corpus() -> None:
    """MET-01, A-20: the 95th percentiles over the OpenNeuro corpus, computed again from this run, equal the
    thresholds of the protocol and of the rule pack."""
    import json

    import numpy as np

    protocol = json.loads(
        (ROOT / "src" / "neurogrid" / "rulepacks" / "calibration" / "core.json").read_text(encoding="utf-8")
    )
    values: dict[str, list[float]] = {"M06": [], "M07": [], "M09a": [], "M09b": []}
    for name in OPENNEURO:
        for rec in _check(name).recordings:
            for channel in rec.metrics["M07"]["channels"].values():
                if channel.get("ratio") is not None:
                    values["M07"].append(float(channel["ratio"]))
            for key in SAMPLE_METRICS:
                if rec.metrics[key]["state"] == "measured":
                    values[key].append(float(rec.metrics[key]["value"]))
    for rule, entry in protocol["thresholds"].items():
        data = values[entry["metric"]]
        assert len(data) == entry["n"], rule
        assert float(f"{np.percentile(data, 95.0):.6g}") == entry["value"], rule


# --- P4 evidence area: gxdsl008 on the corpus (GX-00..GX-04, A-40, A-83) ------------------------------------

# GX-03 per data set: EDF passes; BDF, FIF, BrainVision and EEGLAB MAT v5 (ds004504) warn. The 75 PSG-IPA
# hypnograms are annotation-only files, not recordings (not_applicable).
GX03 = {
    "ds000248-1.2.4": {Status.FAILED},
    "ds002778-1.0.5": {Status.FAILED},
    "ds003775-1.2.1": {Status.PASSED},
    "ds004148-1.0.1": {Status.FAILED},
    "ds004504-1.0.9": {Status.FAILED},
    "psg-ipa-1.0.0": {Status.PASSED},
}


@pytest.mark.parametrize("name", sorted(DATASETS))
def test_gxdsl008_runs_on_every_dataset_and_only_warns(name: str, tmp_path: Path) -> None:
    """gxdsl008 alone (no core, so no signal sample): never exit 2, only warnings with the clause 'unknown',
    coverage n/a, GX-04 open without evidence.yaml, and GX-01 never silent (Q16)."""
    config = tmp_path / "neurogrid.toml"
    config.write_text('[check]\nrulepacks = ["gxdsl008"]\n', encoding="utf-8")
    results = pipeline.run_check(CORPUS / name, pipeline.CheckOptions(config_path=config, as_of=AS_OF))
    assert results.summary.exit_code == 0 and results.summary.coverage == {"gxdsl008": "n/a"}
    assert {f.severity.value for f in results.findings} == {"warning"}
    assert {f.clause for f in results.findings} == {"unknown"}
    gx03 = {f.status for f in results.findings if f.rule_id == "GXDSL008-STO-001"}
    gx03 |= {Status.PASSED} if any(p.rule_id == "GXDSL008-STO-001" for p in results.passed) else set()
    assert gx03 - {Status.NOT_APPLICABLE} == GX03[name]
    assert [f.status for f in results.findings if f.rule_id == "GXDSL008-ACC-001"] == [Status.EVIDENCE_OPEN]
    signal = [r for r in results.recordings if r.n_eeg_channels]
    gx01 = [
        f for f in results.findings if f.rule_id == "GXDSL008-ACQ-001" and f.status is Status.NOT_CHECKABLE
    ]
    assert len(gx01) == len(signal)  # no corpus data set documents impedances


# --- P4: AI dataset structure (M11, M12; A-21, A-81) -------------------------------------------------------


def _reasons(results: Results, rule: str) -> dict[tuple[str, str | None, str], str | None]:
    return {(f.object, f.subkey, f.status.value): f.reason for f in results.findings if f.rule_id == rule}


@pytest.mark.parametrize("name", sorted(DATASETS))
def test_ai_structure_without_labels_splits_or_duplicates(name: str) -> None:
    """No corpus dataset configures labels or splits, and none holds two recordings with the same signal."""
    results = _check(name)
    assert _reasons(results, "CORE-M11-01") == {
        ("dataset", None, "not_applicable"): "ai.labels_not_configured"
    }
    assert _reasons(results, "CORE-M12-01") == {("dataset", None, "not_applicable"): "ai.no_splits"}
    assert results.duplicates == []
    assert not [f for f in results.findings if f.rule_id == "CORE-M12-02" and f.status is Status.FAILED]


def test_demography_on_the_corpus() -> None:
    """CORE-M11-02: participants.tsv documents age and sex (ds002778 as 'gender', ds004504 as 'Gender'/'Age',
    ds004148 with spaces in other headers); ds000248 gives n/a for sub-01; PSG-IPA is a raw folder without a
    mapping, so its subjects are unknown. Demography leaves the process only aggregated (A-51)."""
    for name in ("ds002778-1.0.5", "ds003775-1.2.1", "ds004148-1.0.1", "ds004504-1.0.9"):
        assert _reasons(_check(name), "CORE-M11-02") == {}, name
    ds000248 = _check("ds000248-1.2.4")
    assert _reasons(ds000248, "CORE-M11-02") == {
        ("sub-01", "age", "failed"): "ai.value_missing",
        ("sub-01", "sex", "failed"): "ai.value_missing",
    }
    psg = _check("psg-ipa-1.0.0")
    assert _reasons(psg, "CORE-M11-02") == {("dataset", None, "not_checkable"): "ai.subjects_unknown"}
    ds002778 = _check("ds002778-1.0.5").ai
    assert ds002778 is not None and ds002778.demographics is not None
    assert ds002778.demographics.sex == {"female": 5}  # 5 subjects: no small cell
    assert set(ds002778.demographics.age_groups.values()) == {None}  # 1-4 per age group: suppressed


def test_psg_hypnograms_are_no_recordings_for_duplicates() -> None:
    """C10: the 75 annotation-only files are not hashed; the three polysomnographies are."""
    results = _check("psg-ipa-1.0.0")
    reasons = [f.reason for f in results.findings if f.rule_id == "CORE-M12-02"]
    assert reasons == ["recording.annotations_only"] * 75
    assert sum(p.count for p in results.passed if p.rule_id == "CORE-M12-02") == 3
