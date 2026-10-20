"""Generate the small synthetic test fixtures (CC BY 4.0) deterministically.

Usage:
    python tools/gen_fixtures.py           # (re)write tests/fixtures/synthetic
    python tools/gen_fixtures.py --check   # fail if the committed fixtures differ from a fresh generation

All signals are sine waves with noise; no fixture contains data of a person. Metadata values in the BIDS
fixtures (authors, positions, head circumference) are synthetic test values and say so in their README.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "tests" / "fixtures" / "synthetic"
EEG_LABELS = ("Fp1", "Fp2", "F3", "F4", "C3", "C4", "O1", "O2")
MAT_HEADER = b"MATLAB 5.0 MAT-file, written by NeuroGrid tools/gen_fixtures.py (synthetic test data)"


def _field(text: str, width: int) -> bytes:
    raw = text.encode("ascii")
    if len(raw) > width:
        raise ValueError(f"field too long: {text!r}")
    return raw.ljust(width, b" ")


def _num(value: float | int, width: int) -> bytes:
    text = str(value)
    if isinstance(value, float):
        text = f"{value:.6f}".rstrip("0").rstrip(".")
    return _field(text[:width], width)


def _microvolts(sfreq: int, seconds: int, channels: int, seed: int) -> list[np.ndarray]:
    """One synthetic signal per channel: a sine of 8 Hz + channel index plus Gaussian noise, in µV."""
    rng = np.random.default_rng(seed)
    n = sfreq * seconds
    t = np.arange(n) / sfreq
    return [20.0 * np.sin(2 * np.pi * (8 + index) * t) + rng.normal(0.0, 5.0, n) for index in range(channels)]


ANNOTATION_SAMPLES = 30  # samples (2 bytes each) of the EDF+ annotation signal per data record


def write_edf(
    path: Path,
    *,
    sfreq: int = 512,
    seconds: int = 10,
    labels: tuple[str, ...] = EEG_LABELS,
    label_prefix: str = "EEG ",
    patient: str = "X X X X",
    recording: str = "Startdate X X X X",
    startdate: str = "01.01.85",
    seed: int = 1,
    digital: tuple[int, int] = (-32768, 32767),
    physical: tuple[float, float] = (-500.0, 500.0),
    bad_digital_channel: int | None = None,
    truncate_bytes: int = 0,
    bdf: bool = False,
    plus: str = "",
    record_onsets: tuple[int, ...] | None = None,
) -> None:
    """EDF (16 bit) or, with ``bdf=True``, BioSemi BDF (24 bit) with one-second data records.

    ``plus="C"`` or ``"D"`` writes EDF+ with an annotation signal; ``record_onsets`` gives the start of each
    data record in seconds (EDF+D: with gaps).
    """
    if bdf and digital == (-32768, 32767):
        digital = (-8388608, 8388607)
    sample_type = "<i4" if bdf else "<i2"
    onsets = record_onsets if record_onsets is not None else tuple(range(seconds))
    if len(onsets) != seconds:
        raise ValueError("one onset per data record")
    signals = []
    for microvolts in _microvolts(sfreq, seconds, len(labels), seed):
        scale = (digital[1] - digital[0]) / (physical[1] - physical[0])
        values = np.clip(np.round((microvolts - physical[0]) * scale + digital[0]), digital[0], digital[1])
        signals.append(values.astype(sample_type))

    ns = len(labels) + (1 if plus else 0)
    dmins = [digital[0]] * len(labels)
    dmaxs = [digital[1]] * len(labels)
    if bad_digital_channel is not None:
        dmins[bad_digital_channel] = digital[1]
        dmaxs[bad_digital_channel] = digital[1]
    # one entry per signal: label, transducer, unit, physical min/max, digital min/max, prefilter, samples
    fields: list[tuple[str, str, str, float, float, int, int, str, int]] = [
        (
            f"{label_prefix}{label}",
            "AgAgCl electrode",
            "uV",
            *physical,
            dmin,
            dmax,
            "HP:0.1Hz LP:100Hz",
            sfreq,
        )
        for label, dmin, dmax in zip(labels, dmins, dmaxs, strict=True)
    ]
    if plus:
        annotation = "BDF Annotations" if bdf else "EDF Annotations"
        fields.append((annotation, "", "", -1.0, 1.0, digital[0], digital[1], "", ANNOTATION_SAMPLES))
    header = bytearray()
    header += b"\xffBIOSEMI" if bdf else _field("0", 8)
    header += _field(patient, 80)
    header += _field(recording, 80)
    header += _field(startdate, 8)
    header += _field("00.00.00", 8)
    header += _num(256 * (ns + 1), 8)
    reserved = f"{'BDF' if bdf else 'EDF'}+{plus}" if plus else ("24BIT" if bdf else "")
    header += _field(reserved, 44)
    header += _num(seconds, 8)
    header += _num(1, 8)
    header += _num(ns, 4)
    for index, width in enumerate((16, 80, 8, 8, 8, 8, 8, 80, 8)):
        for entry in fields:
            value = entry[index]
            header += _field(value, width) if isinstance(value, str) else _num(value, width)
    for _ in fields:
        header += _field("", 32)
    assert len(header) == 256 * (ns + 1)

    bytes_per_sample = 3 if bdf else 2
    body = bytearray()
    for record, onset in enumerate(onsets):
        for values in signals:
            chunk = values[record * sfreq : (record + 1) * sfreq]
            if bdf:  # 3 bytes per sample, little endian
                body += chunk.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
            else:
                body += chunk.tobytes()
        if plus:  # time-stamped annotation list: the onset of this record, no annotation text
            tal = f"+{onset}\x14\x14\x00".encode("ascii")
            body += tal.ljust(ANNOTATION_SAMPLES * bytes_per_sample, b"\x00")
    data = bytes(header) + bytes(body)
    if truncate_bytes:
        data = data[:-truncate_bytes]
    _binary(path, data)


def write_brainvision(
    vhdr: Path,
    *,
    sfreq: int = 500,
    seconds: int = 10,
    labels: tuple[str, ...] = EEG_LABELS,
    seed: int = 1,
    impedances: dict[str, str] | None = None,
    data_file: str | None = None,
    write_data: bool = True,
    truncate_bytes: int = 0,
) -> None:
    """BrainVision triple (.vhdr, .vmrk, .eeg; INT_16, multiplexed, 0.1 µV resolution)."""
    stem = vhdr.stem
    data_name = data_file if data_file is not None else f"{stem}.eeg"
    channel_lines = "".join(f"Ch{i}={label},,0.1,µV\n" for i, label in enumerate(labels, start=1))
    comment = ""
    if impedances is not None:
        comment = "\n[Comment]\nImpedance [kOhm] at 00:00:00 :\n" + "".join(
            f"{label}: {value}\n" for label, value in impedances.items()
        )
    _text(
        vhdr,
        "Brain Vision Data Exchange Header File Version 1.0\n"
        "; Synthetic test data written by NeuroGrid tools/gen_fixtures.py\n\n"
        "[Common Infos]\nCodepage=UTF-8\n"
        f"DataFile={data_name}\nMarkerFile={stem}.vmrk\n"
        "DataFormat=BINARY\nDataOrientation=MULTIPLEXED\n"
        f"NumberOfChannels={len(labels)}\nSamplingInterval={1_000_000 // sfreq}\n\n"
        "[Binary Infos]\nBinaryFormat=INT_16\n\n"
        "[Channel Infos]\n" + channel_lines + comment,
    )
    _text(
        vhdr.with_suffix(".vmrk"),
        "Brain Vision Data Exchange Marker File, Version 1.0\n\n"
        f"[Common Infos]\nCodepage=UTF-8\nDataFile={data_name}\n\n"
        "[Marker Infos]\nMk1=New Segment,,1,1,0\n",
    )
    if write_data:
        samples = np.stack(_microvolts(sfreq, seconds, len(labels), seed), axis=1)  # time x channel
        data = np.clip(np.round(samples / 0.1), -32768, 32767).astype("<i2").tobytes()
        if truncate_bytes:
            data = data[:-truncate_bytes]
        _binary(vhdr.with_name(data_name), data)


def write_eeglab(
    path: Path,
    *,
    sfreq: int = 512,
    seconds: int = 4,
    labels: tuple[str, ...] = EEG_LABELS,
    seed: int = 1,
    embedded: bool = False,
) -> None:
    """EEGLAB data set: MATLAB v5 .set with a float32 .fdt data file, or with the data embedded."""
    import scipy.io

    samples = np.stack(_microvolts(sfreq, seconds, len(labels), seed)).astype("<f4")  # channel x time
    points = samples.shape[1]
    empty = np.array([])
    chanlocs = np.zeros(
        (1, len(labels)), dtype=[(key, "O") for key in ("labels", "type", "X", "Y", "Z", "theta", "radius")]
    )
    for index, label in enumerate(labels):
        chanlocs[0, index] = (label, "EEG", empty, empty, empty, empty, empty)
    fdt = path.with_suffix(".fdt")
    eeg: dict[str, Any] = {
        "setname": "synthetic",
        "filename": path.name,
        "filepath": "",
        "subject": "",
        "group": "",
        "condition": "",
        "session": empty,
        "comments": "",
        "nbchan": float(len(labels)),
        "trials": 1.0,
        "pnts": float(points),
        "srate": float(sfreq),
        "xmin": 0.0,
        "xmax": (points - 1) / sfreq,
        "times": empty,
        "data": samples if embedded else fdt.name,
        "icaact": empty,
        "icawinv": empty,
        "icasphere": empty,
        "icaweights": empty,
        "icachansind": empty,
        "chanlocs": chanlocs,
        "urchanlocs": empty,
        "chaninfo": {"plotrad": empty, "shrink": empty, "nosedir": "+X"},
        "ref": "common",
        "event": empty,
        "urevent": empty,
        "eventdescription": empty,
        "epoch": empty,
        "epochdescription": empty,
        "reject": empty,
        "stats": empty,
        "specdata": empty,
        "specicaact": empty,
        "splinefile": "",
        "icasplinefile": "",
        "dipfit": empty,
        "history": "",
        "saved": "justloaded",
        "etc": empty,
        "run": empty,
    }
    if not embedded:
        eeg["datfile"] = fdt.name
        _binary(fdt, samples.T.tobytes())  # .fdt: float32, all channels of one time point after another
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / "set.mat"
        scipy.io.savemat(scratch, {"EEG": eeg}, appendmat=False, format="5", oned_as="row")
        content = bytearray(scratch.read_bytes())
    content[:116] = MAT_HEADER.ljust(116, b" ")  # scipy puts the creation time here
    _binary(path, bytes(content))


def _binary(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


def _json(path: Path, content: dict[str, Any]) -> None:
    _text(path, json.dumps(content, indent=2, ensure_ascii=False) + "\n")


# --- BIDS fixtures --------------------------------------------------------------------------------

POSITIONS = {  # synthetic positions in metres, roughly on a sphere
    "Fp1": (-0.0294, 0.0839, -0.007),
    "Fp2": (0.0298, 0.0849, -0.0071),
    "F3": (-0.0502, 0.0531, 0.0421),
    "F4": (0.0517, 0.0543, 0.0402),
    "C3": (-0.0653, -0.0114, 0.0644),
    "C4": (0.0671, -0.0109, 0.0636),
    "O1": (-0.0295, -0.1125, 0.0088),
    "O2": (0.0298, -0.1123, 0.0088),
    "AFF1h": (-0.0101, 0.0727, 0.0581),
    "EXG1": (0.0, 0.0, -0.05),
}
LANDMARKS = {"NAS": [0.0, 0.085, 0.0], "LPA": [-0.07, 0.0, 0.0], "RPA": [0.07, 0.0, 0.0]}
README = (
    "Synthetic EEG test data for NeuroGrid, generated by tools/gen_fixtures.py.\n\n"
    "The signals are sine waves with noise; they are not recordings of any person. All metadata values,\n"
    "including authors, positions and the head circumference, are synthetic test values.\n"
)


def _description(complete: bool) -> dict[str, Any]:
    if not complete:
        return {"Name": "NeuroGrid synthetic test dataset with problems", "BIDSVersion": "v1.2.1"}
    return {
        "Name": "NeuroGrid synthetic test dataset",
        "BIDSVersion": "1.11.1",
        "HEDVersion": "8.3.0",
        "DatasetType": "raw",
        "License": "CC-BY-4.0",
        "Authors": ["NeuroGrid fixture author A (synthetic)", "NeuroGrid fixture author B (synthetic)"],
        "GeneratedBy": [{"Name": "NeuroGrid tools/gen_fixtures.py"}],
        "SourceDatasets": [{"URL": "urn:x-neurogrid:synthetic"}],
    }


def _eeg_sidecar(complete: bool, **override: Any) -> dict[str, Any]:
    sidecar: dict[str, Any] = {
        "TaskName": "rest",
        "SamplingFrequency": 512,
        "EEGReference": "Cz",
        "PowerLineFrequency": 50,
        "SoftwareFilters": "n/a",
        "EEGChannelCount": 8,
    }
    if complete:
        sidecar |= {
            "EOGChannelCount": 0,
            "ECGChannelCount": 0,
            "EMGChannelCount": 0,
            "MISCChannelCount": 0,
            "TriggerChannelCount": 0,
            "RecordingDuration": 10,
            "RecordingType": "continuous",
            "EEGGround": "Fpz",
            "EEGPlacementScheme": "10-20",
            "Manufacturer": "n/a",
            "ManufacturersModelName": "n/a",
            "SoftwareVersions": "n/a",
            "DeviceSerialNumber": "n/a",
            "CapManufacturer": "n/a",
            "CapManufacturersModelName": "n/a",
            "TaskDescription": "Synthetic signal without a task.",
            "Instructions": "n/a",
            "CogAtlasID": "urn:x-neurogrid:synthetic",
            "CogPOID": "urn:x-neurogrid:synthetic",
            "InstitutionName": "n/a",
            "InstitutionAddress": "n/a",
            "InstitutionalDepartmentName": "n/a",
            "HeadCircumference": 56,
            "HardwareFilters": "n/a",
            "SubjectArtefactDescription": "n/a",
        }
    for key, value in override.items():
        if value is None:
            sidecar.pop(key, None)
        else:
            sidecar[key] = value
    return sidecar


def _coordsystem() -> dict[str, Any]:
    return {
        "EEGCoordinateSystem": "CTF",
        "EEGCoordinateUnits": "m",
        "EEGCoordinateSystemDescription": "Synthetic positions.",
        "FiducialsCoordinates": LANDMARKS,
        "FiducialsCoordinateSystem": "CTF",
        "FiducialsCoordinateUnits": "m",
        "FiducialsCoordinateSystemDescription": "Synthetic positions.",
        "AnatomicalLandmarkCoordinates": LANDMARKS,
        "AnatomicalLandmarkCoordinateSystem": "CTF",
        "AnatomicalLandmarkCoordinateUnits": "m",
        "AnatomicalLandmarkCoordinateSystemDescription": "Synthetic positions.",
    }


def _channels_tsv(labels: tuple[str, ...]) -> str:
    return "name\ttype\tunits\n" + "".join(f"{label}\tEEG\tuV\n" for label in labels)


def _electrodes_tsv(labels: tuple[str, ...], impedance: str) -> str:
    rows = []
    for label in labels:
        x, y, z = POSITIONS[label]
        rows.append(f"{label}\t{x}\t{y}\t{z}\t{impedance}\n")
    return "name\tx\ty\tz\timpedance\n" + "".join(rows)


def _events_tsv() -> str:
    return "onset\tduration\ttrial_type\tHED\n1.0\t0.5\tstim\tSensory-event, Visual-presentation\n"


def _bids_ok() -> dict[str, Callable[[Path], None]]:
    """Complete EEG-BIDS 1.11.1 data set with HED annotations: the bundled validator reports nothing."""
    files: dict[str, Callable[[Path], None]] = {
        "dataset_description.json": lambda p: _json(p, _description(complete=True)),
        "README": lambda p: _text(p, README),
        "participants.tsv": lambda p: _text(p, "participant_id\nsub-01\nsub-02\n"),
        "participants.json": lambda p: _json(
            p, {"participant_id": {"Description": "Participant identifier"}}
        ),
        "task-rest_events.json": lambda p: _json(
            p, {"StimulusPresentation": {"OperatingSystem": "n/a", "SoftwareName": "n/a"}}
        ),
    }
    for number, sub in enumerate(("01", "02")):
        eeg = f"sub-{sub}/eeg/sub-{sub}"
        files |= {
            f"{eeg}_task-rest_eeg.edf": partial(write_edf, seed=21 + number, label_prefix=""),
            f"{eeg}_task-rest_eeg.json": lambda p: _json(p, _eeg_sidecar(complete=True)),
            f"{eeg}_task-rest_channels.tsv": lambda p: _text(p, _channels_tsv(EEG_LABELS)),
            f"{eeg}_electrodes.tsv": lambda p: _text(p, _electrodes_tsv(EEG_LABELS, "3.5")),
            f"{eeg}_coordsystem.json": lambda p: _json(p, _coordsystem()),
            f"{eeg}_task-rest_events.tsv": lambda p: _text(p, _events_tsv()),
        }
    return files


def _bids_issues() -> dict[str, Callable[[Path], None]]:
    """EEG-BIDS data set with one problem per check (negative cases of M02-M05 and BIDS-STO-001..003).

    sub-01: EEGReference missing, TaskName "resting" for task-rest, SamplingFrequency 500 for 512 Hz data,
    EEGChannelCount 9 for 8 channels, no electrodes.tsv. sub-02: channels AFF1h (10-05 only) and EXG1
    (no standard name), impedance 12 kOhm. Data set: BIDSVersion "v1.2.1", HED annotations with schema 8.99.0
    (not available offline), no README.
    """
    labels_02 = ("Fp1", "Fp2", "F3", "F4", "C3", "C4", "AFF1h", "EXG1")
    description = _description(complete=False) | {"HEDVersion": "8.99.0"}
    sidecar_01 = _eeg_sidecar(
        complete=False, EEGReference=None, TaskName="resting", SamplingFrequency=500, EEGChannelCount=9
    )
    return {
        "dataset_description.json": lambda p: _json(p, description),
        "participants.tsv": lambda p: _text(p, "participant_id\nsub-01\nsub-02\n"),
        "sub-01/eeg/sub-01_task-rest_eeg.edf": lambda p: write_edf(p, seed=31, label_prefix=""),
        "sub-01/eeg/sub-01_task-rest_eeg.json": lambda p: _json(p, sidecar_01),
        "sub-01/eeg/sub-01_task-rest_channels.tsv": lambda p: _text(p, _channels_tsv(EEG_LABELS)),
        "sub-01/eeg/sub-01_task-rest_events.tsv": lambda p: _text(p, _events_tsv()),
        "sub-02/eeg/sub-02_task-rest_eeg.edf": lambda p: write_edf(
            p, seed=32, labels=labels_02, label_prefix=""
        ),
        "sub-02/eeg/sub-02_task-rest_eeg.json": lambda p: _json(p, _eeg_sidecar(complete=False)),
        "sub-02/eeg/sub-02_task-rest_channels.tsv": lambda p: _text(p, _channels_tsv(labels_02)),
        "sub-02/eeg/sub-02_electrodes.tsv": lambda p: _text(p, _electrodes_tsv(labels_02, "12")),
        "sub-02/eeg/sub-02_coordsystem.json": lambda p: _json(p, _coordsystem()),
    }


def _prefixed(folder: str, files: dict[str, Callable[[Path], None]]) -> dict[str, Callable[[Path], None]]:
    return {f"{folder}/{relative}": make for relative, make in files.items()}


IMPEDANCES_OK = {label: "3" for label in EEG_LABELS}

FIXTURES: dict[str, Callable[[Path], None]] = {
    "edf_ok/rec_a.edf": lambda p: write_edf(p, seed=1),
    "edf_ok/rec_b.edf": lambda p: write_edf(p, seed=2),
    "edf_lowrate/rec_low.edf": lambda p: write_edf(p, sfreq=256, seed=3),
    "edf_mixed/rec_512.edf": lambda p: write_edf(p, sfreq=512, seed=4),
    "edf_mixed/rec_256.edf": lambda p: write_edf(p, sfreq=256, seed=5),
    "edf_truncated/rec_trunc.edf": lambda p: write_edf(p, seed=6, truncate_bytes=4096),
    "edf_badheader/rec_bad.edf": lambda p: write_edf(p, seed=7, bad_digital_channel=2),
    "edf_identifying/rec_named.edf": lambda p: write_edf(
        p, seed=8, patient="Zhang San 01-JAN-1980", startdate="24.08.21"
    ),
    "unsupported/rec_ok.edf": lambda p: write_edf(p, seed=9),
    "unsupported/legacy.cnt": lambda p: _binary(p, b"\x00" * 64),
    "unsupported/notes.txt": lambda p: _text(p, "Notes that are not EEG data.\n"),
    "empty/README.txt": lambda p: _text(p, "A folder without EEG recordings.\n"),
    "bdf_ok/rec.bdf": lambda p: write_edf(p, seed=10, bdf=True),
    "bdf_truncated/rec_trunc.bdf": lambda p: write_edf(p, seed=11, bdf=True, truncate_bytes=3000),
    "brainvision_ok/rec.vhdr": lambda p: write_brainvision(p, seed=12, impedances=IMPEDANCES_OK),
    "brainvision_missing/rec.vhdr": lambda p: write_brainvision(p, seed=13, write_data=False),
    "brainvision_truncated/rec.vhdr": lambda p: write_brainvision(p, seed=14, truncate_bytes=1000),
    "brainvision_unsafe/rec.vhdr": lambda p: write_brainvision(
        p, seed=15, data_file="../outside.eeg", write_data=False
    ),
    "brainvision_impedance/rec.vhdr": lambda p: write_brainvision(
        p, seed=16, impedances={**IMPEDANCES_OK, "C3": "25", "O2": "Out of Range!"}
    ),
    "eeglab_ok/rec.set": lambda p: write_eeglab(p, seed=17),
    "eeglab_embedded/rec.set": lambda p: write_eeglab(p, seed=18, embedded=True),
    "orphan/rec_ok.edf": lambda p: write_edf(p, seed=19),
    "edf_plus_d/rec.edf": lambda p: write_edf(
        p, seed=20, plus="D", record_onsets=(0, 1, 2, 3, 4, 10, 11, 12, 13, 14)
    ),
    "orphan/lonely.fdt": lambda p: _binary(p, b"\x00" * 64),
    **_prefixed("bids_ok", _bids_ok()),
    **_prefixed("bids_issues", _bids_issues()),
}


def generate(target: Path) -> None:
    for relative, make in FIXTURES.items():
        make(target / relative)


def _files(folder: Path) -> dict[str, bytes]:
    return {
        path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob("*") if path.is_file()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        generate(TARGET)
        print(f"wrote fixtures to {TARGET.relative_to(ROOT)} ({len(_files(TARGET))} files)")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        generate(Path(tmp))
        fresh = _files(Path(tmp))
    committed = _files(TARGET)
    differing = sorted(rel for rel in fresh.keys() | committed.keys() if fresh.get(rel) != committed.get(rel))
    if differing:
        print("fixtures differ from a fresh generation:", ", ".join(differing))
        return 1
    print("fixtures up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
