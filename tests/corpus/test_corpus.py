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
