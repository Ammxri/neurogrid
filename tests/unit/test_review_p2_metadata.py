"""Review P2, metadata and channel types: non-EEG channels are no EEG channels, channels.tsv types and columns
follow A-04/A-77, sidecar numbers never crash, and the mapping of raw folders neither drops labels nor hangs
(A-04, A-05, A-12, A-18, A-46, A-53, A-75, A-77).

Covers neurogrid.io.channels.classify, neurogrid.metadata (declared_type, _number, mapped_entities, the
channels.tsv column sources), neurogrid.checks.metadata.measure_count and the mapping expression check in
neurogrid.config.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from datetime import date
from pathlib import Path, PurePosixPath

import numpy as np
import pytest

import gen_fixtures  # type: ignore[import-not-found,unused-ignore]
from conftest import DOCUMENTED_TOML, documented_config  # type: ignore[import-not-found,unused-ignore]
from neurogrid import config as config_module
from neurogrid import pipeline
from neurogrid.checks import metadata as metadata_checks
from neurogrid.checks.context import CheckContext, RecordingState
from neurogrid.config import Config, ConvertSection, backtracking_risk, parse
from neurogrid.convert import convert_to_bids
from neurogrid.io.channels import classify
from neurogrid.io.discover import FoundFile, pseudonym, scan
from neurogrid.io.montage_names import ONLY_1005, SYSTEM_1020
from neurogrid.kernel.errors import ConfigError, InputError
from neurogrid.kernel.findings import Status
from neurogrid.kernel.rules import Measurement
from neurogrid.metadata import RecordingMetadata, declared_type, mapped_entities
from neurogrid.model.dataset import Recording

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = date(2026, 10, 11)
LABELS = gen_fixtures.EEG_LABELS
DATA = "sub-01/eeg/sub-01_task-rest_eeg.edf"
TSV = "sub-01/eeg/sub-01_task-rest_channels.tsv"
SIDECAR = "sub-01/eeg/sub-01_task-rest_eeg.json"


# --- helpers ----------------------------------------------------------------------------------------------


def _bids_ok(root: Path) -> Path:
    shutil.copytree(FIX / "bids_ok", root)
    return root


def _state(root: Path, cfg: Config | None = None) -> RecordingState:
    ctx = CheckContext.build(scan(root), cfg or Config())
    return next(s for s in ctx.recordings if s.found.relative.as_posix() in (DATA, "rec.vhdr", "rec.edf"))


def _context(root: Path, cfg: Config | None = None) -> CheckContext:
    return CheckContext.build(scan(root), cfg or Config())


def _recording(state: RecordingState) -> Recording:
    assert state.recording is not None, state.header_error
    return state.recording


def _types(state: RecordingState) -> dict[str, str]:
    return {ch.name: ch.type for ch in _recording(state).channels}


def _found(relative: str) -> FoundFile:
    path = PurePosixPath(relative)
    return FoundFile(relative=path, display_id=pseudonym(path), suffix=path.suffix.lower(), size_bytes=0)


def _count(root: Path) -> Measurement:
    measurements = metadata_checks.measure_count(_context(root))
    return next(
        m for m in measurements if m.object != "dataset" and m.file is not None and "sub-01" in m.file
    )


def _count_passes(measurement: Measurement) -> bool:
    spec = next(s for s in metadata_checks.SPECS if s.id == metadata_checks.COUNT)
    return spec.evaluate(measurement, {}).passed


def _field(text: str, width: int) -> bytes:
    return text.encode("ascii").ljust(width, b" ")


# label, unit, samples per 30 s record: the channel set of PhysioNet Sleep-EDF Expanded (EEG/EOG 100 Hz,
# everything else 1 Hz), with synthetic data
SLEEP_EDF = (
    ("EEG Fpz-Cz", "uV", 3000),
    ("EEG Pz-Oz", "uV", 3000),
    ("EOG horizontal", "uV", 3000),
    ("Resp oro-nasal", "", 30),
    ("EMG submental", "uV", 30),
    ("Temp rectal", "DegC", 30),
    ("Event marker", "", 30),
)


# an SHHS/AASM-like polysomnography set: EEG at 125 Hz, EOG E1-M2/E2-M1 at 50 Hz, the rest at 1 or 10 Hz
PSG_AASM = (
    ("C3-M2", "uV", 3750),
    ("C4-M1", "uV", 3750),
    ("E1-M2", "uV", 1500),
    ("E2-M1", "uV", 1500),
    ("H.R.", "bpm", 30),
    ("SaO2", "%", 30),
    ("OX stat", "-", 30),
    ("SOUND", "-", 300),
    ("Effort THO", "-", 300),
    ("Therm", "-", 300),
)


def _sleep_edf(path: Path, signals: tuple[tuple[str, str, int], ...] = SLEEP_EDF) -> Path:
    records, duration, ns = 4, 30, len(signals)
    header = _field("0", 8) + _field("X X X X", 80) + _field("Startdate X X X X", 80) + _field("01.01.85", 8)
    header += _field("00.00.00", 8) + _field(str(256 * (ns + 1)), 8) + _field("", 44)
    header += _field(str(records), 8) + _field(str(duration), 8) + _field(str(ns), 4)
    columns = [
        [s[0] for s in signals],
        ["" for _ in signals],
        [s[1] for s in signals],
        ["-500" for _ in signals],
        ["500" for _ in signals],
        ["-32768" for _ in signals],
        ["32767" for _ in signals],
        ["" for _ in signals],
        [str(s[2]) for s in signals],
        ["" for _ in signals],
    ]
    for values, width in zip(columns, (16, 80, 8, 8, 8, 8, 8, 80, 8, 32), strict=True):
        for value in values:
            header += _field(value, width)
    rng = np.random.default_rng(0)
    body = b"".join(
        rng.integers(-1000, 1000, n, dtype="<i2").tobytes() for _ in range(records) for _l, _u, n in signals
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + body)
    return path


# --- classify: common non-EEG channels (finding: VEOG/HEOG, Event marker, GSR/Plet, TUH EKG) ---------------


@pytest.mark.parametrize(
    ("label", "kind"),
    [
        ("VEOG", "EOG"),
        ("HEOG", "EOG"),
        ("heog-l", "EOG"),
        ("VEOGU", "EOG"),
        ("EOG horizontal", "EOG"),
        ("EEG LOC-REF", "EOG"),  # outer canthus EOG as a whole word
        ("ROC-A1", "EOG"),
        ("HEO", "EOG"),  # Neuroscan spellings (verifier: missed by the first fix)
        ("VEO", "EOG"),
        ("HEOL", "EOG"),
        ("VEOU", "EOG"),
        ("EEG LUC-REF", "EOG"),  # TUH canthus electrodes
        ("EEG RLC-REF", "EOG"),
        ("E1-M2", "EOG"),  # AASM sleep montage
        ("E2-M1", "EOG"),
        ("E1 - A2", "EOG"),
        ("LO1", "EOG"),  # orbital EOG electrodes of Neuroscan/BESA caps (verifier: missed by the fix)
        ("LO2", "EOG"),
        ("IO1", "EOG"),
        ("IO2-REF", "EOG"),
        ("SO1", "EOG"),
        ("EEG SO2-REF", "EOG"),
        ("Photo", "MISC"),  # photodiode of ERP setups
        ("Photodiode", "MISC"),
        ("ACC_X", "MISC"),  # motion sensors of mobile devices
        ("AccZ", "MISC"),
        ("GYROX", "MISC"),
        ("H.R.", "MISC"),  # SHHS
        ("OX stat", "MISC"),
        ("SOUND", "MISC"),
        ("Effort THO", "RESP"),
        ("Therm", "RESP"),
        ("Nasal Pressure", "RESP"),
        ("EEG EKG1-REF", "ECG"),  # TUH: the type word "EEG" comes first
        ("EEG ECG-REF", "ECG"),
        ("EEG EMG-REF", "EMG"),
        ("Event marker", "MISC"),  # Sleep-EDF
        ("Marker", "MISC"),
        ("Annotations", "MISC"),  # a signal named like annotations, but no EDF+ annotation channel
        ("EDF Annotations", "ANNOT"),
        ("PHOTIC-REF", "MISC"),
        ("EEG PHOTIC-REF", "MISC"),
        ("PHOTIC PH", "MISC"),
        ("GSR1", "MISC"),  # BioSemi
        ("GSR2", "MISC"),
        ("Plet", "MISC"),
        ("Pleth", "MISC"),
        ("PPG", "MISC"),
        ("EDA", "MISC"),
        ("Erg1", "MISC"),
        ("ERG", "MISC"),
        ("SpO2", "MISC"),
        ("SaO2", "MISC"),
        ("OSat", "MISC"),
        ("HR", "MISC"),
        ("IBI", "MISC"),
        ("BURSTS", "MISC"),
        ("SUPPR", "MISC"),
        ("Thor", "RESP"),
        ("Abdo", "RESP"),
        ("Airflow", "RESP"),
        ("Flow Patient", "RESP"),
        ("Resp oro-nasal", "RESP"),
        ("Temp rectal", "MISC"),
        ("Status", "TRIG"),
        ("STI 014", "TRIG"),
        # genuine EEG labels stay EEG
        ("EEG Fp1-REF", "EEG"),
        ("EEG FP1-REF", "EEG"),
        ("Fpz-Cz", "EEG"),
        ("EEG Fpz-Cz", "EEG"),
        ("EEG Pz-Oz", "EEG"),
        ("C3-A2", "EEG"),
        ("EEG C4-M1", "EEG"),
        ("EEG T1-REF", "EEG"),
        ("EEG SP1-REF", "EEG"),
        ("EEG 001", "EEG"),
        ("EEG", "EEG"),
        ("EEG1", "EEG"),
        ("EXG1", "EEG"),
        ("PO3", "EEG"),
        ("POz", "EEG"),
        ("A1", "EEG"),
        ("I1", "EEG"),  # 10-05 names next to the orbital EOG words
        ("Iz", "EEG"),
        ("O1", "EEG"),
        ("AF3", "EEG"),
        ("E1", "EEG"),  # an EGI net electrode, not the AASM EOG
        ("E2", "EEG"),
        ("E129", "EEG"),
        ("E1-E2", "EEG"),
        ("O1-M2", "EEG"),
        ("Oz", "EEG"),
        ("Ch17", "EEG"),
    ],
)
def test_channel_type_of_common_labels(label: str, kind: str) -> None:
    assert classify(label) == kind


def test_no_standard_name_is_typed_as_non_eeg() -> None:
    """Every 10-20/10-10/10-05 name stays EEG, alone, with a type word, a reference or as a derivation."""
    wrong = []
    for name in sorted(SYSTEM_1020 | ONLY_1005):
        for label in (name, f"EEG {name}", f"EEG {name}-REF", f"{name}-REF", f"{name}-A2", f"EEG {name}-M1"):
            if classify(label) != "EEG":
                wrong.append(label)
    assert wrong == []


@pytest.mark.parametrize("eog", [("VEOG", "HEOG"), ("VEO", "HEO")])  # BrainProducts, Neuroscan
def test_veog_and_heog_in_a_raw_brainvision_folder_are_no_eeg_channels(
    tmp_path: Path, eog: tuple[str, str]
) -> None:
    """Reviewer case bv_eog: VEOG/HEOG gave CORE-M04-01 errors (unknown EEG names) and exit 1."""
    root = tmp_path / "raw"
    labels = ("Fp1", "Fp2", "Cz", "Pz", *eog)
    gen_fixtures.write_brainvision(root / "rec.vhdr", labels=labels, impedances=dict.fromkeys(labels, "3"))
    types = _types(_state(root))
    assert types == {"Fp1": "EEG", "Fp2": "EEG", "Cz": "EEG", "Pz": "EEG", eog[0]: "EOG", eog[1]: "EOG"}
    config = documented_config(
        tmp_path, '[[convert.files]]\npath = "rec.vhdr"\nsubject = "01"\ntask = "rest"\n'
    )
    results = pipeline.run_check(
        root, pipeline.CheckOptions(as_of=AS_OF, config_path=config, work_base=tmp_path)
    )
    names = [f for f in results.findings if f.rule_id == "CORE-M04-01" and f.status is Status.FAILED]
    assert names == []
    positions = next(f for f in results.findings if f.rule_id == "CORE-M04-02")
    assert positions.measured_value == {"documented": 0, "eeg_channels": 4}  # a warning
    assert results.summary.exit_code == 0


def test_sleep_edf_channel_set_keeps_the_eeg_rate(tmp_path: Path) -> None:
    """Reviewer case sleepedf_like: 'Event marker' at 1 Hz was EEG, so the recording rate was 1 Hz,
    M03-02 saw mixed rates and M04-01 failed for it."""
    root = tmp_path / "raw"
    _sleep_edf(root / "rec.edf")
    state = _state(root)
    assert _types(state) == {
        "EEG Fpz-Cz": "EEG",
        "EEG Pz-Oz": "EEG",
        "EOG horizontal": "EOG",
        "Resp oro-nasal": "RESP",
        "EMG submental": "EMG",
        "Temp rectal": "MISC",
        "Event marker": "MISC",
    }
    assert _recording(state).sampling_rate_hz == 100.0
    results = pipeline.run_check(
        root, pipeline.CheckOptions(as_of=AS_OF, config_path=documented_config(tmp_path), work_base=tmp_path)
    )
    assert results.recordings[0].sampling_rate_hz == 100.0
    failed = {f.rule_id: f.measured_value for f in results.findings if f.status is Status.FAILED}
    assert failed["CORE-M03-01"] == 100.0  # below the minimum rate, measured on the EEG channels (was 1.0)
    assert "CORE-M03-02" not in failed and "CORE-M04-01" not in failed  # no mixed rates, no unknown names
    assert failed["CORE-M04-02"] == {"documented": 0, "eeg_channels": 2}


def test_aasm_polysomnography_keeps_the_eeg_rate(tmp_path: Path) -> None:
    """Verifier variant of the Sleep-EDF case: E1-M2/E2-M1 (50 Hz) and the SHHS-style signals H.R., OX stat
    (1 Hz), SOUND, Effort THO and Therm (10 Hz) were EEG, so the recording rate was 1 Hz."""
    root = tmp_path / "raw"
    _sleep_edf(root / "rec.edf", PSG_AASM)
    state = _state(root)
    types = _types(state)
    assert [name for name, kind in types.items() if kind == "EEG"] == ["C3-M2", "C4-M1"]
    assert (types["E1-M2"], types["E2-M1"], types["H.R."], types["OX stat"]) == ("EOG", "EOG", "MISC", "MISC")
    assert (types["SOUND"], types["Effort THO"], types["Therm"]) == ("MISC", "RESP", "RESP")
    assert _recording(state).sampling_rate_hz == 125.0
    names = metadata_checks.measure_standard_names(_context(root))
    assert [(m.subkey, m.value) for m in names] == [("C3-M2", True), ("C4-M1", True)]


# --- channels.tsv: every declared type wins over the header (A-04) ----------------------------------------


@pytest.mark.parametrize(
    ("declared", "kind"),
    [
        ("EEG", "EEG"),
        ("eeg", "EEG"),
        ("EOG", "EOG"),
        ("HEOG", "EOG"),
        ("VEOG", "EOG"),
        ("ECG", "ECG"),
        ("EKG", "ECG"),
        ("EMG", "EMG"),
        ("TRIG", "TRIG"),
        ("STIM", "TRIG"),
        ("RESP", "RESP"),
        ("REF", "MISC"),
        ("MISC", "MISC"),
        ("GSR", "MISC"),
        ("PPG", "MISC"),
        ("TEMP", "MISC"),
        ("AUDIO", "MISC"),
        ("EYEGAZE", "MISC"),
        ("PUPIL", "MISC"),
        ("SYSCLOCK", "MISC"),
        ("SEEG", "MISC"),
        ("ECOG", "MISC"),
        ("DBS", "MISC"),
        ("anything", "MISC"),
        ("MEGMAG", "MEG"),
        ("MEGGRADPLANAR", "MEG"),
        ("MEGREFMAG", "MEG"),
        (" ", None),
        ("", None),
        ("n/a", None),
    ],
)
def test_declared_channels_tsv_types(declared: str, kind: str | None) -> None:
    assert declared_type(declared) == kind


def _bids_types(root: Path) -> Path:
    """Reviewer case bids_types: GSR1 (type GSR) and Plet (type PPG) next to the 8 EEG channels of bids_ok."""
    _bids_ok(root)
    labels = (*LABELS, "GSR1", "Plet")
    gen_fixtures.write_edf(root / DATA, seed=21, label_prefix="", labels=labels)
    rows = "".join(f"{label}\tEEG\tuV\n" for label in LABELS) + "GSR1\tGSR\tuS\nPlet\tPPG\tn/a\n"
    (root / TSV).write_text("name\ttype\tunits\n" + rows, encoding="utf-8")
    return root


def test_bids_types_without_neurogrid_type_are_no_eeg_channels(tmp_path: Path) -> None:
    root = _bids_types(tmp_path / "ds")
    state = _state(root)
    types = _types(state)
    assert (types["GSR1"], types["Plet"]) == ("MISC", "MISC")
    assert [name for name, kind in types.items() if kind == "EEG"] == list(LABELS)
    measurement = _count(root)
    assert measurement.value == {
        "sidecar_eeg": 8,
        "channels_tsv_eeg": 8,
        "file_eeg": 8,
        "channels_tsv_total": 10,
        "file_total": 10,
    }
    assert _count_passes(measurement)
    names = metadata_checks.measure_standard_names(_context(root))
    checked = sorted(m.subkey for m in names if m.subkey and m.file and "sub-01" in m.file)
    assert checked == sorted(LABELS)  # GSR1 and Plet are no EEG channels and get no M04-01 error


def test_declared_type_overrides_the_label_in_both_directions(tmp_path: Path) -> None:
    root = _bids_ok(tmp_path / "ds")
    gen_fixtures.write_edf(root / DATA, seed=21, label_prefix="", labels=(*LABELS, "VEOG", "Ch9"))
    rows = "".join(f"{label}\tEEG\tuV\n" for label in LABELS) + "VEOG\tEEG\tuV\nCh9\tSYSCLOCK\tn/a\n"
    (root / TSV).write_text("name\ttype\tunits\n" + rows, encoding="utf-8")
    types = _types(_state(root))
    assert (types["VEOG"], types["Ch9"]) == ("EEG", "MISC")


def test_channels_tsv_row_never_turns_an_annotation_channel_into_a_signal(tmp_path: Path) -> None:
    root = _bids_ok(tmp_path / "ds")
    gen_fixtures.write_edf(root / DATA, seed=21, label_prefix="", plus="C")
    rows = "".join(f"{label}\tEEG\tuV\n" for label in LABELS) + "EDF Annotations\tMISC\tn/a\n"
    (root / TSV).write_text("name\ttype\tunits\n" + rows, encoding="utf-8")
    state = _state(root)
    assert _types(state)["EDF Annotations"] == "ANNOT"
    assert _count(root).value["file_total"] == 8


# --- channels.tsv columns: every channel needs the value (A-77) -------------------------------------------


def _blank_units(edf: Path, keep: int) -> None:
    """Remove the unit of every signal after the first ``keep`` signals in an EDF header."""
    data = bytearray(edf.read_bytes())
    ns = int(data[252:256].decode().strip())
    base = 256 + ns * (16 + 80)
    for index in range(keep, ns):
        data[base + index * 8 : base + index * 8 + 8] = b" " * 8
    edf.write_bytes(bytes(data))


def _units_source(root: Path) -> str | None:
    return _state(root).metadata.channel_columns.get("units")


def test_partial_channels_tsv_documents_no_column_for_the_unlisted_channels(tmp_path: Path) -> None:
    """Reviewer case channels_partial_units: the header has no unit for channels 3-8, channels.tsv lists only
    Fp1 and Fp2; units were documented ("sidecar"), now they are not."""
    root = _bids_ok(tmp_path / "ds")
    _blank_units(root / DATA, keep=2)
    (root / TSV).write_text("name\ttype\tunits\nFp1\tEEG\tuV\nFp2\tEEG\tuV\n", encoding="utf-8")
    state = _state(root)
    assert state.metadata.channel_columns == {"name": "header", "type": "header"}
    required = metadata_checks.measure_required(_context(root))
    units = next(m for m in required if m.subkey == "channels.units" and m.file and "sub-01" in m.file)
    assert units.value is False
    # without the table the outcome is the same: an incomplete table hides nothing
    (root / TSV).unlink()
    assert _state(root).metadata.channel_columns == {"name": "header", "type": "header"}


def test_channels_tsv_and_header_together_document_a_column(tmp_path: Path) -> None:
    root = _bids_ok(tmp_path / "ds")
    _blank_units(root / DATA, keep=2)
    # the table has the units the header lacks (channels 3-8), the header has those of Fp1 and Fp2
    rows = "".join(f"{label}\tEEG\tuV\n" for label in LABELS[2:])
    (root / TSV).write_text("name\ttype\tunits\n" + rows, encoding="utf-8")
    assert _state(root).metadata.channel_columns == {
        "name": "header",
        "type": "header",
        "units": "sidecar+header",
    }
    # one channel without a unit in both: not documented
    rows = "".join(f"{label}\tEEG\tuV\n" for label in LABELS[3:])
    (root / TSV).write_text("name\ttype\tunits\n" + rows, encoding="utf-8")
    assert _units_source(root) is None
    # the full table documents every column, also where the header has no unit
    (root / TSV).write_text(gen_fixtures._channels_tsv(LABELS), encoding="utf-8")
    assert _state(root).metadata.channel_columns == {"name": "sidecar", "type": "sidecar", "units": "sidecar"}


def test_channels_tsv_rows_must_match_the_channel_names(tmp_path: Path) -> None:
    root = _bids_ok(tmp_path / "ds")
    _blank_units(root / DATA, keep=0)
    # as many rows as channels, but one name differs: that channel has no unit anywhere
    names = (*LABELS[:-1], "Oz")
    (root / TSV).write_text(gen_fixtures._channels_tsv(names), encoding="utf-8")
    assert _units_source(root) is None
    # an empty unit cell is no value; n/a is one (BIDS writes n/a for channels without a unit)
    rows = "".join(f"{label}\tEEG\t{'' if label == 'O2' else 'n/a'}\n" for label in LABELS)
    (root / TSV).write_text("name\ttype\tunits\n" + rows, encoding="utf-8")
    assert _units_source(root) is None
    rows = "".join(f"{label}\tEEG\tn/a\n" for label in LABELS)
    (root / TSV).write_text("name\ttype\tunits\n" + rows, encoding="utf-8")
    assert _units_source(root) == "sidecar"


def test_annotation_channel_needs_no_channels_tsv_row(tmp_path: Path) -> None:
    root = _bids_ok(tmp_path / "ds")
    gen_fixtures.write_edf(root / DATA, seed=21, label_prefix="", plus="C")
    (root / TSV).write_text(gen_fixtures._channels_tsv(LABELS), encoding="utf-8")
    assert _state(root).metadata.channel_columns == {"name": "sidecar", "type": "sidecar", "units": "sidecar"}


# --- M04-04: a channels.tsv without rows is no source (A-77) ----------------------------------------------


def test_header_only_channels_tsv_is_no_count_source(tmp_path: Path) -> None:
    """Reviewer case bids_empty_tsv: M04-04 failed with channels_tsv_eeg 0 / channels_tsv_total 0."""
    root = _bids_ok(tmp_path / "ds")
    (root / TSV).write_text("name\ttype\tunits\n", encoding="utf-8")
    measurement = _count(root)
    assert measurement.value == {
        "sidecar_eeg": 8,
        "channels_tsv_eeg": None,
        "file_eeg": 8,
        "channels_tsv_total": None,
        "file_total": 8,
    }
    assert _count_passes(measurement)
    # without EEGChannelCount in the sidecar nothing is left to compare
    sidecar = json.loads((root / SIDECAR).read_text(encoding="utf-8"))
    del sidecar["EEGChannelCount"]
    (root / SIDECAR).write_text(json.dumps(sidecar), encoding="utf-8")
    measurement = _count(root)
    assert (measurement.state, measurement.reason) == ("not_applicable", "metadata.no_sidecar")


# --- sidecar numbers too large for a float (A-12, A-75) ---------------------------------------------------


def test_sidecar_integer_too_large_for_a_float_is_no_number() -> None:
    huge = 5 * 10**400
    meta = RecordingMetadata(sidecar={"SamplingFrequency": huge, "EEGChannelCount": huge})
    assert meta.sidecar_rate is None and meta.sidecar_eeg_count is None
    meta = RecordingMetadata(sidecar={"SamplingFrequency": -huge, "EEGChannelCount": 2**1100})
    assert meta.sidecar_rate is None and meta.sidecar_eeg_count is None


def test_power_line_frequency_too_large_for_a_float_does_not_crash(tmp_path: Path) -> None:
    """Reviewer case bids_bigint: 'Internal error (OverflowError)', exit 2."""
    root = _bids_ok(tmp_path / "ds")
    text = (root / SIDECAR).read_text(encoding="utf-8")
    data = json.loads(text)
    data["PowerLineFrequency"] = 5 * 10**400
    data["SamplingFrequency"] = 10**400
    (root / SIDECAR).write_text(json.dumps(data), encoding="utf-8")
    state = _state(root)
    rec = _recording(state)
    assert rec.line_frequency_hz is None and "line_frequency_hz" not in rec.metadata_sources
    assert state.metadata.sidecar_rate is None
    assert "PowerLineFrequency" in state.metadata.fields  # documented, but no number NeuroGrid can use


# --- mapping expression: a value that is no label leaves the file unmapped (A-05, A-77) -------------------

REVIEW_PATTERN = r"(?P<subject>[^_]+)_(?P<session>[^_]+)_run(?P<run>[^_]+)_(?P<task>[a-z]+)\.edf"


def _pattern_config(pattern: str) -> Config:
    return parse("[convert]\npattern = '" + pattern + "'\n")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("s01_pre-op_run1-2_rest.edf", {}),  # was: sub-s01 without session and run
        ("s01_pre_run1-2_rest.edf", {}),  # was: ses-pre without run
        ("s01_pre_run1b_rest.edf", {}),  # a run that is no number
        ("s-01_pre_run1_rest.edf", {}),  # a subject that is no label
        ("s01_pre_run1_rest.edf", {"subject": "s01", "session": "pre", "run": "1", "task": "rest"}),
    ],
)
def test_mapping_value_that_is_no_label_is_not_dropped(name: str, expected: dict[str, str]) -> None:
    assert mapped_entities(_found(name), _pattern_config(REVIEW_PATTERN)) == expected


def test_optional_group_without_value_is_no_label_problem() -> None:
    cfg = _pattern_config(r"(?P<subject>[a-z0-9]+)_(?P<task>[a-z]+)(?:_(?P<run>[0-9]*))?\.edf")
    assert mapped_entities(_found("s1_rest.edf"), cfg) == {"subject": "s1", "task": "rest"}
    assert mapped_entities(_found("s1_rest_.edf"), cfg) == {"subject": "s1", "task": "rest"}
    assert mapped_entities(_found("s1_rest_2.edf"), cfg) == {"subject": "s1", "task": "rest", "run": "2"}


def test_convert_lists_a_file_with_a_non_label_value_as_unmapped(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir()
    shutil.copyfile(FIX / "edf_ok" / "rec_a.edf", root / "s01_pre-op_run1-2_rest.edf")
    with pytest.raises(InputError) as info:
        convert_to_bids(root, tmp_path / "out", _pattern_config(REVIEW_PATTERN))
    assert info.value.message_key == "convert.mapping_missing" and info.value.params["count"] == 1
    assert (root / ".neurogrid" / "mapping-template.toml").is_file()
    assert not (tmp_path / "out").exists()


# --- mapping expression: no catastrophic backtracking (A-53) ----------------------------------------------

UNSAFE_PATTERNS = [
    r"(?P<subject>(a|aa)+)+(?P<task>b)",  # reviewer case sk/redos.py
    r"(?P<subject>(a|aa)+)(?P<task>b)",  # alternatives inside a repetition
    r"(?P<subject>(?:a?a?)+)(?P<task>b)",  # optional parts inside a repetition
    r"(?P<subject>(?:\w+_)+)(?P<task>[a-z]+)\.edf",
    r"(?P<subject>(?:[a-z]+)*)_(?P<task>[a-z]+)\.edf",
    r"(?P<subject>(?:a{1,3}){2,})(?P<task>b)",
    r"(?P<subject>a+)_(?P<task>b)_(?P=subject)\.edf",  # back-reference
    r"(?P<subject>a)?(?P<task>b)(?(subject)c|d)\.edf",  # conditional on a group
    # verifier: no nesting, but many neighbouring parts that can match the same characters; each of these
    # ran for more than 15 s on a name of about 30 characters, the six .* for 6 s on 100 characters
    "(?P<subject>" + "a?" * 32 + "a" * 32 + ")(?P<task>b)",  # 2**32 ways
    "(?P<subject>" + "(?:a|a)" * 30 + ")(?P<task>b)",  # alternatives that start alike
    "(?P<subject>" + "a*" * 12 + ")(?P<task>b)",
    "(?P<subject>" + "a{0,9}" * 12 + ")(?P<task>b)",
    r"(?P<subject>.*)(?P<task>.*).*.*.*.*x",  # the case the fix left open
    r"(?P<subject>\w*\w*\w*\w*\w*)_(?P<task>b)",
    r"(?P<subject>.+)_(?P<session>.+)_(?P<task>.+)_(?P<run>.+)_.+\.edf",  # five such parts
    r"(?=.*_.*_.*_.*_.*_x)(?P<subject>\w+)_(?P<task>b)",  # in a look-ahead (7 s on 140 characters)
]
SAFE_PATTERNS = [
    r"(?P<task>[A-Za-z0-9]+)(?:_(?P<subject>[A-Za-z0-9]+))?\.(?:edf|bdf)",
    r"(?P<subject>[A-Za-z0-9]+)_(?P<task>[a-z]+)(?:_(?P<run>[0-9]+))?\.edf",
    r"(?P<subject>\w+)_(?P<session>\w+)_(?P<task>\w+)_(?P<run>\d+)\.edf",
    r"(?P<subject>[^_]+)_(?P<session>[^_]+)_run(?P<run>[^_]+)_(?P<task>[a-z]+)\.edf",
    r"(?P<subject>[A-Za-z0-9]+)/(?P<session>[A-Za-z0-9]+)/(?P<task>[a-z]+)\.vhdr",
    r"(?:.*/)?(?P<subject>s\d{2})_(?P<task>rest|task)\.edf",
    r"(?P<task>rec)_(?P<subject>[ab])\.edf",
    r"(?P<subject>(?:ab){2})(?P<task>b)",
    r"(?:.*/)?(?P<subject>[A-Za-z0-9]+)(?:_(?P<session>[A-Za-z0-9]+))?_(?P<task>[a-z]+)"
    r"(?:_run(?P<run>\d+))?(?:_.*)?\.(?:edf|bdf|vhdr|set)",
    r"(?i)(?P<subject>sub[0-9]+)_(?P<task>[a-z]+)\.(?:edf|bdf)",
    r"(?P<subject>.+?)_(?P<session>.+?)_(?P<task>.+?)\.set",
    r"data/(?P<subject>[^/]+)/(?P<session>[^/]+)/eeg/(?P<task>[^/_]+)(?:_(?P<run>\d+))?\.vhdr",
    "(?P<subject>[^_]+)_" + "[^_]+_" * 8 + "(?P<task>[^_]+)",  # every choice decided by the next character
]
# four parts that can match the same characters: the most that is allowed (about 3-5 s on a hostile name
# of 255 characters, MAX_SPLITS)
BOUNDARY_PATTERN = r"(?P<subject>.+)_(?P<session>.+)_(?P<task>.+)_(?P<run>.+)\.edf"
HOSTILE_NAMES = ["_" * 254 + "!", "a_" * 127 + "!", "a" * 254 + "!", "a/" * 127 + "!", "s1_" * 85, "a." * 127]


@pytest.mark.parametrize("pattern", UNSAFE_PATTERNS)
def test_mapping_expression_that_may_backtrack_is_refused(pattern: str) -> None:
    assert backtracking_risk(pattern)
    started = time.perf_counter()
    with pytest.raises(ConfigError) as info:
        _pattern_config(pattern)
    assert time.perf_counter() - started < 5
    assert info.value.message_key == "config.unsafe_pattern"
    assert info.value.params == {"field": "convert.pattern"}
    with pytest.raises(ConfigError):
        ConvertSection(pattern=pattern)


@pytest.mark.parametrize("pattern", SAFE_PATTERNS)
def test_usual_mapping_expressions_stay_valid(pattern: str) -> None:
    assert not backtracking_risk(pattern)
    assert _pattern_config(pattern).convert.pattern == pattern


def test_documented_toml_pattern_stays_valid() -> None:
    assert parse(DOCUMENTED_TOML).convert.pattern is not None


def test_four_parts_that_match_the_same_characters_stay_valid() -> None:
    assert not backtracking_risk(BOUNDARY_PATTERN)
    assert _pattern_config(BOUNDARY_PATTERN).convert.pattern == BOUNDARY_PATTERN


@pytest.mark.parametrize("pattern", SAFE_PATTERNS)
def test_accepted_expressions_finish_quickly_on_hostile_names(pattern: str) -> None:
    compiled = re.compile(pattern)
    started = time.perf_counter()
    for name in HOSTILE_NAMES:
        compiled.fullmatch(name)
    assert time.perf_counter() - started < 3


def test_choices_decided_by_the_next_character_cost_nothing() -> None:
    """[^_]+ before '_' can only stop at the separator, while \\w+ (which matches '_') may stop anywhere:
    ten such parts in a row are refused only with \\w."""
    decided = "(?P<subject>[^_]+)_" + "[^_]+_" * 8 + "(?P<task>[^_]+)\\.edf"
    assert not backtracking_risk(decided)
    assert backtracking_risk(decided.replace("[^_]", "\\w"))


def test_character_sets_beyond_the_probed_characters_count_as_overlapping() -> None:
    # Hebrew letters belong to both sets, but to none of the characters the check probes (ASCII, a few
    # others, the characters the expression names and their neighbours)
    hebrew = "[֐-ࣿ]"
    ends = ("֏", "֐", "֑", "ࣾ", "ࣿ", "ऀ")
    assert not any(re.fullmatch(hebrew, c) and re.fullmatch(r"\w", c) for c in ends)
    assert backtracking_risk("(?P<subject>" + (hebrew + "*\\w*") * 3 + ")(?P<task>b)")
    # a separator outside the range still decides
    assert not backtracking_risk("(?P<subject>" + (hebrew + "+_") * 8 + ")(?P<task>b)")


def test_deeply_nested_expression_does_not_crash_the_check() -> None:
    deep = "(?P<subject>" + "(?:" * 90 + "a" + ")" * 90 + ")(?P<task>b)"
    assert backtracking_risk(deep) is False
    assert backtracking_risk("(?P<subject>" + "(?:" * 90 + "a+" + ")+" * 90 + ")(?P<task>b)") is True


def test_unsafe_pattern_in_the_dataset_configuration_ends_scan_with_a_config_error(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    (root / ".neurogrid").mkdir(parents=True)
    shutil.copyfile(FIX / "edf_ok" / "rec_a.edf", root / ("a" * 37 + "c.edf"))
    (root / ".neurogrid" / "neurogrid.toml").write_text(
        "[convert]\npattern = '" + UNSAFE_PATTERNS[0] + "'\n", encoding="utf-8"
    )
    started = time.perf_counter()
    with pytest.raises(ConfigError) as info:
        config_module.load(None, root)
    assert info.value.message_key == "config.unsafe_pattern"
    with pytest.raises(ConfigError):
        pipeline.run_scan(root)
    assert time.perf_counter() - started < 5
