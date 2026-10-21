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


# --- P4: annotation (NG-F08, M10, A-80) ---------------------------------------------------------------------

PSG_CODES = (
    "Sleep stage W",
    "Sleep stage N1",
    "Sleep stage N2",
    "Sleep stage N3",
    "Sleep stage R",
    "Sleep stage ?",
    "Lights off",
    "Lights on",
)
# A-80: the reproduced 4-decimal values are the reference (KONZEPT 8.5 gives their rounding), +-0.001
PSG_MANUAL = {"SN1": (0.7253, 0.4735), "SN2": (0.6598, 0.3692), "SN4": (0.7656, 0.6460)}  # mean, minimum
PSG_SCORERS_1_2 = {"SN1": 0.7902, "SN2": 0.6905, "SN4": 0.8104}


def _m10_only(folder: Path, annotators: list[str]) -> Path:
    """neurogrid.toml with the DoD settings and a pack of the M10 rules of core alone (no signal metrics, so
    the run takes seconds); written outside the corpus, which stays unchanged."""
    import json

    from neurogrid.kernel.rules import load_rulepack

    core = (ROOT / "src" / "neurogrid" / "rulepacks" / "core.yaml").read_bytes()
    pack = load_rulepack(core, origin="path").pack
    rules = [rule for rule in pack.rules if rule.id.startswith("CORE-M10")]
    m10 = pack.model_copy(update={"rulepack": "core_m10", "rules": rules})
    (folder / "core_m10.yaml").write_text(json.dumps(m10.model_dump(mode="json")), encoding="utf-8")
    config = folder / "neurogrid.toml"
    config.write_text(
        '[check]\nrulepacks = ["core_m10.yaml"]\n[annotation]\nmode = "continuous"\nepoch_s = 30\n'
        f"vocabulary = {json.dumps(list(PSG_CODES))}\nannotators = {json.dumps(annotators)}\n",
        encoding="utf-8",
    )
    return config


def _psg_kappa(tmp_path: Path, annotators: list[str]) -> tuple[Results, dict[str, dict[str, object]]]:
    config = _m10_only(tmp_path, annotators)
    results = pipeline.run_check(
        CORPUS / "psg-ipa-1.0.0", pipeline.CheckOptions(config_path=config, as_of=AS_OF, show_paths=True)
    )
    summaries = {
        Path(rec.id).name.split("_")[0]: rec.metrics["annotation"]
        for rec in results.recordings
        if "annotation" in rec.metrics
    }
    return results, summaries


def test_psg_kappa_of_the_12_manual_scorers(tmp_path: Path) -> None:
    """P4 DoD: kappa on PSG-IPA as measured (+-0.001): 66 pairs of the 12 manual scorers per recording; every
    hypnogram attached by its stem (25 per recording), codes, gaps and overlaps passed."""
    results, summaries = _psg_kappa(tmp_path, ["manual_*"])
    assert sorted(summaries) == ["SN1", "SN2", "SN4"]
    for name, (mean, minimum) in PSG_MANUAL.items():
        kappa = summaries[name]["kappa"]
        assert isinstance(kappa, dict)
        assert abs(kappa["mean"] - mean) <= 0.001 and abs(kappa["min"] - minimum) <= 0.001, name
        assert (kappa["pairs"], kappa["annotators"], kappa["undefined_pairs"]) == (66, 12, 0), name
        files = summaries[name]["files"]
        assert isinstance(files, list) and len(files) == 25 and summaries[name]["excluded_annotators"] == 13
    assert [f for f in results.findings if f.rule_id.startswith("CORE-M10")] == []
    passed = {p.rule_id for p in results.passed}
    assert passed == {"CORE-M10-01", "CORE-M10-02", "CORE-M10-03", "CORE-M10-04"}
    assert not [n for n in results.notices if n.message_key.startswith("notice.annotation")]


def test_psg_kappa_scorer_1_against_2(tmp_path: Path) -> None:
    _results, summaries = _psg_kappa(tmp_path, ["manual_scorer1", "manual_scorer2"])
    for name, value in PSG_SCORERS_1_2.items():
        kappa = summaries[name]["kappa"]
        assert isinstance(kappa, dict) and kappa["pairs"] == 1
        assert abs(kappa["mean"] - value) <= 0.001, name


def test_vmrk_reader_agrees_with_events_tsv() -> None:
    """ds004148: MNE-BIDS wrote the markers of the .vmrk to events.tsv (onset = (position - 1) / rate,
    duration = size / rate, value = the description)."""
    from pathlib import PurePosixPath

    from neurogrid.io.annotations import events_annotations, read_events, read_vmrk

    root = CORPUS / "ds004148-1.0.1"
    headers = sorted(root.rglob("*_eeg.vhdr"))
    assert len(headers) == 3
    for vhdr in headers:
        relative = PurePosixPath(vhdr.relative_to(root).as_posix())
        markers = read_vmrk(vhdr).annotations
        table = read_events(root, relative)
        assert table is not None
        events = events_annotations(root, relative, table).annotations
        assert len(markers) == len(events) > 0
        for marker, event in zip(markers, events, strict=True):
            assert (
                abs(marker.onset_s - event.onset_s) < 1e-6
                and abs(marker.duration_s - event.duration_s) < 1e-6
            )
            assert marker.code.endswith("/" + event.code)


@pytest.mark.parametrize("name", OPENNEURO)
def test_openneuro_annotation_findings_are_not_applicable_or_passed(name: str) -> None:
    """Events mode (the default) on the OpenNeuro sets: nothing fails and nothing is unreadable."""
    results = _check(name)
    statuses = {f.status for f in results.findings if f.rule_id.startswith("CORE-M10")}
    assert statuses == {Status.NOT_APPLICABLE}, name
