"""Generate the small synthetic test fixtures (CC BY 4.0) deterministically.

Usage:
    python tools/gen_fixtures.py           # (re)write tests/fixtures/synthetic
    python tools/gen_fixtures.py --check   # fail if the committed fixtures differ from a fresh generation
    python tools/gen_fixtures.py --scale-results OUT.json [--recordings N] [--channels C] [--typical]
                                           # synthetic results.json for the report scaling test (A-59)

All signals are sine waves with noise or, in the signal quality fixtures (edf_quality_*), simulated dipole
sources and artefacts with noise; no fixture contains data of a person. Metadata values in the BIDS
fixtures (authors, positions, head circumference) are synthetic test values and say so in their README.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import tempfile
from collections.abc import Callable
from datetime import date
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
    microvolts: np.ndarray | None = None,
    annotations: tuple[tuple[float, float, str], ...] = (),
    annotation_samples: int = 0,
) -> None:
    """EDF (16 bit) or, with ``bdf=True``, BioSemi BDF (24 bit) with one-second data records.

    ``plus="C"`` or ``"D"`` writes EDF+ with an annotation signal; ``record_onsets`` gives the start of each
    data record in seconds (EDF+D: with gaps). ``microvolts`` (channels x samples) replaces the default
    sine-plus-noise signals; values outside the physical range are clipped to the digital limits.
    ``annotations`` (onset_s, duration_s, text) go into the TAL of the last record that starts at or before
    their onset; ``annotation_samples`` sizes the annotation signal (default ANNOTATION_SAMPLES).
    """
    spr_annotation = annotation_samples or ANNOTATION_SAMPLES
    if bdf and digital == (-32768, 32767):
        digital = (-8388608, 8388607)
    sample_type = "<i4" if bdf else "<i2"
    onsets = record_onsets if record_onsets is not None else tuple(range(seconds))
    if len(onsets) != seconds:
        raise ValueError("one onset per data record")
    if microvolts is not None and microvolts.shape != (len(labels), sfreq * seconds):
        raise ValueError("microvolts must have one row of sfreq * seconds samples per label")
    signals = []
    rows = _microvolts(sfreq, seconds, len(labels), seed) if microvolts is None else list(microvolts)
    for microvolts_row in rows:
        scale = (digital[1] - digital[0]) / (physical[1] - physical[0])
        values = np.clip(
            np.round((microvolts_row - physical[0]) * scale + digital[0]), digital[0], digital[1]
        )
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
        fields.append((annotation, "", "", -1.0, 1.0, digital[0], digital[1], "", spr_annotation))
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
        if plus:  # time-stamped annotation list: the onset of this record, then its annotations
            tal = f"+{onset}\x14\x14\x00".encode("ascii")
            tal += b"".join(_tal(*entry) for entry in annotations if _record_of(entry[0], onsets) == record)
            if len(tal) > spr_annotation * bytes_per_sample:
                raise ValueError(
                    "annotations do not fit into the annotation signal; raise annotation_samples"
                )
            body += tal.ljust(spr_annotation * bytes_per_sample, b"\x00")
    data = bytes(header) + bytes(body)
    if truncate_bytes:
        data = data[:-truncate_bytes]
    _binary(path, data)


def _tal_number(value: float) -> str:
    """A TAL number: plain decimal with a sign (EDF+ specification)."""
    text = f"{abs(value):.6f}".rstrip("0").rstrip(".")
    return ("-" if value < 0 else "+") + text


def _tal(onset: float, duration: float, text: str) -> bytes:
    """One time-stamped annotation list: onset, optional duration, one text."""
    head = _tal_number(onset) + (f"\x15{_tal_number(duration)[1:]}" if duration else "")
    return f"{head}\x14{text}\x14\x00".encode()


def _record_of(onset: float, onsets: tuple[int, ...]) -> int:
    """The last data record that starts at or before ``onset`` (the first one for earlier onsets)."""
    return max([index for index, start in enumerate(onsets) if start <= onset] or [0])


def write_annotation_edf(
    path: Path, annotations: tuple[tuple[float, float, str], ...], *, bdf: bool = False
) -> None:
    """Annotation-only EDF+C (BDF+C with ``bdf=True``), e.g. a hypnogram: one data record of duration 0 with a
    single annotation signal that holds the time-keeping entry and every annotation (onset, duration, text),
    as the scorer files of PSG-IPA have it (A-74, A-80)."""
    tal = b"+0\x14\x14\x00" + b"".join(_tal(*entry) for entry in annotations)
    bytes_per_sample = 3 if bdf else 2
    samples = -(-len(tal) // bytes_per_sample)
    digital = (-8388608, 8388607) if bdf else (-32768, 32767)
    label = "BDF Annotations" if bdf else "EDF Annotations"
    entry: tuple[str | float | int, ...] = (label, "", "", -1.0, 1.0, digital[0], digital[1], "", samples)
    header = bytearray()
    header += b"\xffBIOSEMI" if bdf else _field("0", 8)
    header += _field("X X X X", 80)
    header += _field("Startdate X X X X", 80)
    header += _field("01.01.85", 8)
    header += _field("00.00.00", 8)
    header += _num(512, 8)
    header += _field("BDF+C" if bdf else "EDF+C", 44)
    header += _num(1, 8)
    header += _num(0, 8)
    header += _num(1, 4)
    for index, width in enumerate((16, 80, 8, 8, 8, 8, 8, 80, 8)):
        value = entry[index]
        header += _field(value, width) if isinstance(value, str) else _num(value, width)
    header += _field("", 32)
    _binary(path, bytes(header) + tal.ljust(samples * bytes_per_sample, b"\x00"))


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
    events: tuple[tuple[str | float, float, float | None], ...] = (),
    trials: int = 1,
) -> None:
    """EEGLAB data set: MATLAB v5 .set with a float32 .fdt data file, or with the data embedded.

    ``events`` (type, latency in samples from 1, duration in samples or None for no field) fill EEG.event;
    ``trials`` only sets the header field (the reader of EEG.event looks at nothing else).
    """
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
        "trials": float(trials),
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
        "event": _eeglab_events(events) if events else empty,
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


def write_eeglab_v73(
    path: Path, *, sfreq: int = 512, seconds: int = 4, labels: tuple[str, ...] = EEG_LABELS, seed: int = 1
) -> None:
    """EEGLAB data set in a MATLAB v7.3 (HDF5) container with a float32 .fdt data file, written with h5py
    in MATLAB's layout: a 512-byte user block with the MAT header (version 0x0200), the EEG structure as a
    group, texts as uint16 'char' datasets, empty values marked MATLAB_empty and the chanlocs fields as
    references into '#refs#'. Used by tests at run time (GX-03: an HDF5 container), not committed: HDF5 files
    carry library details that need not be byte-identical across h5py builds."""
    import h5py

    def text(group: Any, name: str, value: str) -> None:
        if value:
            dataset = group.create_dataset(name, data=np.array([[ord(ch)] for ch in value], dtype="<u2"))
        else:
            dataset = group.create_dataset(name, data=np.zeros(2, dtype="<u8"))
            dataset.attrs["MATLAB_empty"] = np.uint8(1)
        dataset.attrs["MATLAB_class"] = np.bytes_(b"char")

    def number(group: Any, name: str, value: float | None) -> None:
        if value is None:
            dataset = group.create_dataset(name, data=np.zeros(2, dtype="<u8"))
            dataset.attrs["MATLAB_empty"] = np.uint8(1)
        else:
            dataset = group.create_dataset(name, data=np.array([[value]], dtype="<f8"))
        dataset.attrs["MATLAB_class"] = np.bytes_(b"double")

    samples = np.stack(_microvolts(sfreq, seconds, len(labels), seed)).astype("<f4")  # channel x time
    points = samples.shape[1]
    fdt = path.with_suffix(".fdt")
    _binary(fdt, samples.T.tobytes())
    with h5py.File(path, "w", userblock_size=512) as handle:
        refs = handle.create_group("#refs#")
        eeg = handle.create_group("EEG")
        eeg.attrs["MATLAB_class"] = np.bytes_(b"struct")
        texts = {"setname": "synthetic", "filename": path.name, "data": fdt.name, "ref": "common"}
        texts.update({key: "" for key in ("filepath", "comments", "history", "subject")})
        for key, value in texts.items():
            text(eeg, key, value)
        counts = {"nbchan": len(labels), "trials": 1, "pnts": points, "srate": sfreq, "xmin": 0.0}
        for key, count in counts.items():
            number(eeg, key, float(count))
        for key in ("times", "event", "epoch", "urevent", "icawinv", "icasphere", "icaweights", "icaact"):
            number(eeg, key, None)
        chanlocs = eeg.create_group("chanlocs")
        chanlocs.attrs["MATLAB_class"] = np.bytes_(b"struct")
        for field in ("labels", "type", "X", "Y", "Z"):
            targets = []
            for index, label in enumerate(labels):
                name = f"{field}{index}"
                if field in ("labels", "type"):
                    text(refs, name, label if field == "labels" else "EEG")
                else:
                    number(refs, name, None)
                targets.append(refs[name].ref)
            chanlocs.create_dataset(field, data=np.array([[ref] for ref in targets], dtype=h5py.ref_dtype))
    with path.open("r+b") as handle:  # the MAT header that tells readers to use HDF5
        handle.write(b"MATLAB 7.3 MAT-file, written by NeuroGrid tools/gen_fixtures.py".ljust(116))
        handle.write(b"\x00" * 8 + b"\x00\x02IM")


def _eeglab_events(events: tuple[tuple[str | float, float, float | None], ...]) -> np.ndarray:
    """EEG.event as a MATLAB struct array (type, latency and, if any event has one, duration)."""
    names = ["type", "latency"] + (["duration"] if any(e[2] is not None for e in events) else [])
    table = np.zeros((1, len(events)), dtype=[(name, "O") for name in names])
    for index, (kind, latency, duration) in enumerate(events):
        values: list[object] = [kind, float(latency)]
        if "duration" in names:
            values.append(np.array([]) if duration is None else float(duration))
        table[0, index] = tuple(values)
    return table


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


# --- AI dataset structure fixtures (M11, M12) -------------------------------------------------------------
#
# Small BIDS datasets (4 channels, 2 s at 128 Hz per recording) for the rules CORE-M11-01 … CORE-M12-02: class
# labels in events.tsv (trial_type), demography in participants.tsv and the splits in .neurogrid/splits.tsv.
# Every recording has its own seed, so signals differ unless a fixture copies one on purpose.

AI_LABELS = ("Fp1", "Fp2", "C3", "C4")


def _ai_edf(path: Path, seed: int, recording: str = "Startdate X X X X") -> None:
    write_edf(path, sfreq=128, seconds=2, labels=AI_LABELS, label_prefix="", seed=seed, recording=recording)


def _ai_events(classes: dict[str, int]) -> str:
    """One event of 0.1 s every 0.2 s, ``count`` events per trial_type in the given order."""
    names = [name for name, count in classes.items() for _ in range(count)]
    rows = "".join(f"{0.2 * index:.1f}\t0.1\t{name}\n" for index, name in enumerate(names))
    return "onset\tduration\ttrial_type\n" + rows


def _ai_dataset(
    name: str,
    participants: str,
    recordings: dict[str, tuple[int, dict[str, int], str]],
    headers: dict[str, str] | None = None,
) -> dict[str, Callable[[Path], None]]:
    """A BIDS dataset: ``recordings`` maps "<sub>/<run>" to (seed, classes, split); the split goes to
    .neurogrid/splits.tsv with the dataset-relative path. ``headers`` gives other EDF recording fields."""
    description = {"Name": name, "BIDSVersion": "1.11.1", "DatasetType": "raw", "License": "CC-BY-4.0"}
    levels = {"A": "Class A (synthetic)", "B": "Class B (synthetic)", "C": "Class C (synthetic)"}
    files: dict[str, Callable[[Path], None]] = {
        "dataset_description.json": lambda p: _json(p, description),
        "README": lambda p: _text(p, README),
        "participants.tsv": lambda p: _text(p, participants),
        "participants.json": lambda p: _json(
            p,
            {
                "participant_id": {"Description": "Participant identifier"},
                "age": {"Description": "Age (synthetic)", "Units": "year"},
                "sex": {"Description": "Sex (synthetic)", "Levels": {"F": "female", "M": "male"}},
            },
        ),
        "task-rest_events.json": lambda p: _json(p, {"trial_type": {"Levels": levels}}),
    }
    splits = ["recording\tsplit\n"]
    for key, (seed, classes, split) in recordings.items():
        sub, run = key.split("/")
        stem = f"sub-{sub}/eeg/sub-{sub}_task-rest_run-{run}"
        header = (headers or {}).get(key, "Startdate X X X X")
        files[f"{stem}_eeg.edf"] = partial(_ai_edf, seed=seed, recording=header)
        files[f"{stem}_events.tsv"] = partial(_text, content=_ai_events(classes))
        splits.append(f"{stem}_eeg.edf\t{split}\n")
    files[".neurogrid/splits.tsv"] = partial(_text, content="".join(splits))
    return files


def _bids_ai_ok() -> dict[str, Callable[[Path], None]]:
    """Positive cases of M11/M12: six subjects (sub-01 with two runs), age and sex documented for all,
    classes A/B/C with shares 0.4/0.3/0.3 in every scope, subject-disjoint splits (train 01-04, val 05,
    test 06), seven different signals. Ages 37.25 and 61.75 are planted for the privacy tests (A-21)."""
    participants = (
        "participant_id\tage\tsex\nsub-01\t23\tF\nsub-02\t37.25\tM\nsub-03\t45\tF\n"
        "sub-04\t61.75\tM\nsub-05\t52\tF\nsub-06\t29\tM\n"
    )
    even = {"A": 4, "B": 3, "C": 3}
    recordings = {
        "01/1": (71, even, "train"),
        "01/2": (72, even, "train"),
        "02/1": (73, even, "train"),
        "03/1": (74, even, "train"),
        "04/1": (75, even, "train"),
        "05/1": (76, even, "val"),
        "06/1": (77, even, "test"),
    }
    return _ai_dataset("NeuroGrid synthetic AI structure dataset", participants, recordings)


def _bids_ai_issues() -> dict[str, Callable[[Path], None]]:
    """Negative cases of M11/M12: sub-02 run-1 in train and run-2 in test; sub-03 age n/a; sub-04 without a
    participants row; class 'rare' with 1 of 40 events (2.5 %); the test split lacks class C; sub-05 run-1
    has the samples of sub-01 run-1 (same seed) under another recording header field and lies in test."""
    participants = "participant_id\tage\tsex\nsub-01\t30\tF\nsub-02\t41\tM\nsub-03\tn/a\tF\nsub-05\t27\tM\n"
    recordings = {
        "01/1": (81, {"A": 4, "B": 2, "C": 2}, "train"),
        "02/1": (82, {"A": 3, "B": 2, "C": 2, "rare": 1}, "train"),
        "02/2": (83, {"A": 4, "B": 3}, "test"),
        "03/1": (84, {"A": 3, "B": 2, "C": 2}, "train"),
        "04/1": (85, {"A": 2, "B": 2, "C": 1}, "val"),
        "05/1": (81, {"A": 3, "B": 2}, "test"),
    }
    return _ai_dataset(
        "NeuroGrid synthetic AI structure dataset with problems",
        participants,
        recordings,
        headers={"05/1": "Startdate X X X copy"},
    )


def _prefixed(folder: str, files: dict[str, Callable[[Path], None]]) -> dict[str, Callable[[Path], None]]:
    return {f"{folder}/{relative}": make for relative, make in files.items()}


# --- signal quality fixtures (M06–M09) ------------------------------------------------------------------
#
# EEG-like signals for the rules CORE-M06-01 … CORE-M09-02: current dipoles under the scalp, each with a
# non-Gaussian time course (bursts), mixed into standard 10-20 channels. Neighbouring channels are therefore
# correlated (pyprep), the epochs are stationary (autoreject) and ICA can separate the sources (ICLabel).
# Artefacts and channel problems are added where a fixture needs them.

QUALITY_SFREQ = 250
QUALITY_SECONDS = 70  # M06/M09 need at least 60 s (A-79); 35 epochs of 2 s for autoreject
QUALITY_SAMPLES = QUALITY_SFREQ * QUALITY_SECONDS
# Positions in m, rounded from the colin27 template that NeuroGrid uses for standard names (A-60). Here they
# only shape the synthetic topographies.
QUALITY_POSITIONS: dict[str, tuple[float, float, float]] = {
    "Fp1": (-0.0294, 0.0839, -0.0070),
    "Fp2": (0.0299, 0.0849, -0.0071),
    "F7": (-0.0703, 0.0425, -0.0114),
    "F3": (-0.0502, 0.0531, 0.0422),
    "Fz": (0.0003, 0.0585, 0.0665),
    "F4": (0.0518, 0.0543, 0.0408),
    "F8": (0.0730, 0.0444, -0.0120),
    "T7": (-0.0842, -0.0160, -0.0093),
    "C3": (-0.0654, -0.0116, 0.0644),
    "Cz": (0.0004, -0.0092, 0.1002),
    "C4": (0.0671, -0.0109, 0.0636),
    "T8": (0.0851, -0.0150, -0.0095),
    "P7": (-0.0724, -0.0735, -0.0025),
    "P3": (-0.0530, -0.0788, 0.0559),
    "Pz": (0.0003, -0.0811, 0.0826),
    "P4": (0.0557, -0.0786, 0.0566),
    "P8": (0.0731, -0.0731, -0.0025),
    "O1": (-0.0294, -0.1124, 0.0088),
    "Oz": (0.0001, -0.1149, 0.0147),
    "O2": (0.0298, -0.1122, 0.0088),
    "FC1": (-0.0341, 0.0260, 0.0800),
    "FC2": (0.0348, 0.0264, 0.0788),
    "CP1": (-0.0355, -0.0473, 0.0913),
    "CP2": (0.0384, -0.0471, 0.0907),
}
HEAD_CENTRE = np.array([0.0011, -0.0161, 0.0049])  # centre of a sphere fitted to the template positions
QUALITY_LABELS = tuple(QUALITY_POSITIONS)[:20]  # 20 channels: M06/M09 need at least 16 EEG channels
ARTEFACT_LABELS = tuple(QUALITY_POSITIONS)  # 24 channels: 16 good ones remain for ICA next to bad ones


def _positions(labels: tuple[str, ...]) -> np.ndarray:
    return np.array([QUALITY_POSITIONS[label] for label in labels])


def _band_noise(rng: np.random.Generator, low: float, high: float) -> np.ndarray:
    """Gaussian noise with power only between ``low`` and ``high`` Hz, unit standard deviation."""
    size = QUALITY_SAMPLES // 2 + 1
    spectrum = rng.normal(size=size) + 1j * rng.normal(size=size)
    freqs = np.fft.rfftfreq(QUALITY_SAMPLES, 1.0 / QUALITY_SFREQ)
    spectrum[(freqs < low) | (freqs > high)] = 0
    noise = np.fft.irfft(spectrum, QUALITY_SAMPLES)
    return np.asarray(noise / noise.std())


def _pink_noise(rng: np.random.Generator) -> np.ndarray:
    """1/f noise without a DC part, unit standard deviation."""
    size = QUALITY_SAMPLES // 2 + 1
    spectrum = rng.normal(size=size) + 1j * rng.normal(size=size)
    freqs = np.fft.rfftfreq(QUALITY_SAMPLES, 1.0 / QUALITY_SFREQ)
    spectrum /= np.sqrt(np.maximum(freqs, 0.5))
    spectrum[0] = 0
    noise = np.fft.irfft(spectrum, QUALITY_SAMPLES)
    return np.asarray(noise / noise.std())


def _bump(start_s: float, length_s: float) -> np.ndarray:
    """A Hann window of ``length_s`` seconds from ``start_s``, zero elsewhere."""
    out = np.zeros(QUALITY_SAMPLES)
    first = round(start_s * QUALITY_SFREQ)
    size = round(length_s * QUALITY_SFREQ)
    out[first : first + size] = np.hanning(size)
    return out


def _dipole(labels: tuple[str, ...], location: np.ndarray, moment: np.ndarray) -> np.ndarray:
    """Scalp topography of a current dipole in an infinite homogeneous medium, scaled to a maximum of 1."""
    diff = _positions(labels) - location
    topography = diff @ moment / np.linalg.norm(diff, axis=1) ** 3
    return np.asarray(topography / np.abs(topography).max())


def _brain(rng: np.random.Generator, labels: tuple[str, ...], sources: int, microvolts: float) -> np.ndarray:
    """``sources`` cortical dipoles 4.5 cm from the head centre (upper half, mostly radial), each with 1/f
    background activity and alpha bursts (8–12 Hz under a slow log-normal envelope); ``microvolts`` is the
    RMS of their sum on an average channel."""
    data = np.zeros((len(labels), QUALITY_SAMPLES))
    for _ in range(sources):
        direction = rng.normal(size=3)
        direction[2] = abs(direction[2]) + 0.3
        direction /= np.linalg.norm(direction)
        topography = _dipole(labels, HEAD_CENTRE + 0.045 * direction, rng.normal(size=3) + 1.5 * direction)
        envelope = np.exp(_band_noise(rng, 0.05, 0.5))
        rhythm = _band_noise(rng, rng.uniform(8.0, 9.5), rng.uniform(10.5, 12.0)) * envelope
        activity = _pink_noise(rng) + 1.5 * rhythm / rhythm.std()
        data += np.outer(topography / np.sqrt(np.mean(topography**2)), activity / activity.std())
    return data * microvolts / np.sqrt(sources)


def _blinks(
    rng: np.random.Generator,
    labels: tuple[str, ...],
    microvolts: tuple[float, float],
    every_s: tuple[float, float],
) -> np.ndarray:
    """Eye blinks: 0.35-s bumps from a dipole near the eyes, one every ``every_s`` seconds."""
    course = np.zeros(QUALITY_SAMPLES)
    onset = 0.7
    while onset < QUALITY_SECONDS - 1:
        course += _bump(onset, 0.35) * rng.uniform(*microvolts)
        onset += rng.uniform(*every_s)
    return np.outer(_dipole(labels, np.array([0.0, 0.10, -0.04]), np.array([0.0, 0.3, 1.0])), course)


def _eye_movements(rng: np.random.Generator, labels: tuple[str, ...]) -> np.ndarray:
    """Horizontal eye movements: a lateral dipole near the eyes, a step of ±40 µV or none every second."""
    steps = np.repeat(rng.choice([-1.0, 0.0, 1.0], size=QUALITY_SECONDS), QUALITY_SFREQ)
    course = np.convolve(steps, np.ones(25) / 25, mode="same") * 40.0
    return np.outer(_dipole(labels, np.array([0.0, 0.10, -0.04]), np.array([1.0, 0.0, 0.0])), course)


def _muscle(rng: np.random.Generator, labels: tuple[str, ...], sources: int, microvolts: float) -> np.ndarray:
    """Muscle activity: 20–110 Hz bursts from dipoles spread around the lower half of the head."""
    data = np.zeros((len(labels), QUALITY_SAMPLES))
    for index in range(sources):
        angle = 2 * np.pi * (index + 0.5) / sources
        direction = np.array([np.cos(angle), np.sin(angle), -0.2])
        direction /= np.linalg.norm(direction)
        course = _band_noise(rng, 20.0, 110.0) * np.exp(1.5 * _band_noise(rng, 0.05, 0.4))
        topography = _dipole(labels, HEAD_CENTRE + 0.06 * direction, direction)
        data += np.outer(topography, course / course.std() * microvolts)
    return data


def _heartbeat(rng: np.random.Generator, labels: tuple[str, ...]) -> np.ndarray:
    """Heartbeat: 40-ms spikes of 25 µV about every 0.85 s from a dipole below the head."""
    course = np.zeros(QUALITY_SAMPLES)
    onset = 0.3
    while onset < QUALITY_SECONDS - 0.2:
        first = round(onset * QUALITY_SFREQ)
        course[first : first + 10] += np.hanning(10) * 25.0
        onset += 0.85 + rng.uniform(-0.03, 0.03)
    return np.outer(_dipole(labels, np.array([0.02, -0.03, -0.12]), np.array([0.3, 0.2, 1.0])), course)


def _movement(rng: np.random.Generator, labels: tuple[str, ...], share: float, kind: str) -> np.ndarray:
    """Movement artefacts in ``share`` of the 2-s epochs (one each, inside the epoch), each with its own
    gradient over the head: a slow deflection of 180–250 µV (``kind="slow"``) or a 15–100 Hz burst of
    40–60 µV (``"burst"``)."""
    data = np.zeros((len(labels), QUALITY_SAMPLES))
    epochs = QUALITY_SECONDS // 2
    for epoch in sorted(rng.choice(epochs, size=round(share * epochs), replace=False).tolist()):
        gradient = rng.normal(size=3)
        topography = (_positions(labels) - HEAD_CENTRE) @ (gradient / np.linalg.norm(gradient))
        shape = _bump(2 * epoch + rng.uniform(0.2, 0.6), rng.uniform(0.8, 1.2))
        if kind == "slow":
            course = shape * rng.uniform(180.0, 250.0)
        else:
            course = shape * _band_noise(rng, 15.0, 100.0) * rng.uniform(40.0, 60.0)
        data += np.outer(topography / np.abs(topography).max(), course)
    return data


def _amplifier(rng: np.random.Generator, data: np.ndarray, noise_uv: float) -> np.ndarray:
    """Every channel at an RMS of 15 µV × 0.85–1.15, plus white noise of ``noise_uv`` × 0.8–1.2 and a weak
    50 Hz line noise of 2.5 µV × 0.8–1.2 (so that the line frequency 50 Hz is plausible, A-47)."""
    channels, samples = data.shape
    t = np.arange(samples) / QUALITY_SFREQ
    data = data * (rng.uniform(0.85, 1.15, size=channels) * 15.0 / data.std(axis=1))[:, None]
    data += rng.uniform(0.8, 1.2, size=(channels, 1)) * noise_uv * rng.normal(size=(channels, samples))
    return np.asarray(data + 2.5 * rng.uniform(0.8, 1.2, size=(channels, 1)) * np.sin(2 * np.pi * 50.0 * t))


def _seconds(start: int, stop: int) -> slice:
    return slice(start * QUALITY_SFREQ, stop * QUALITY_SFREQ)


def quality_ok_signals(seed: int) -> np.ndarray:
    """Clean EEG-like data that passes every M06–M09 rule: twelve cortical sources, a blink every 6–10 s
    and 2 µV amplifier noise. One electrode problem within the M08 limits: P8 is flat from 31 to 33 s and
    saturated from 50 to 52 s (2 of 70 windows each, 2.9 %), so a stricter max_fraction fails it (MET-02)."""
    rng = np.random.default_rng(seed)
    labels = QUALITY_LABELS
    data = _brain(rng, labels, 12, 15.0) + _blinks(rng, labels, (60.0, 100.0), (6.0, 10.0))
    data = _amplifier(rng, data, noise_uv=2.0)
    p8 = labels.index("P8")
    data[p8, _seconds(31, 33)] = 0.0
    data[p8, _seconds(50, 52)] = 600.0  # beyond the physical maximum of 500 µV: the digital maximum
    return data


def quality_issues_signals(seed: int) -> np.ndarray:
    """One problem per rule (negative cases of M06, M07-01, M08-01, M08-02 and M09-01):

    - line noise: 40 µV at 50 Hz on T7, T8, P7 and P8;
    - flat line: O2 from 20 to 30 s (14 % of the duration);
    - clipping: F8 drifts beyond the physical range for about 6 s around 45 s (the digital maximum);
    - bad channels: F3, C4 and P3 without contact (independent 1/f noise), Fz, Pz and Oz with 30 µV of
      amplifier noise, besides O2 and F8 (8 of 20 channels);
    - artefacts: slow movement artefacts in 40 % of the 2-s epochs, a blink every 2.5–5 s.
    """
    rng = np.random.default_rng(seed)
    labels = QUALITY_LABELS
    data = _brain(rng, labels, 6, 15.0) + _blinks(rng, labels, (100.0, 160.0), (2.5, 5.0))
    data = _amplifier(rng, data + _movement(rng, labels, 0.4, "slow"), noise_uv=2.0)
    t = np.arange(QUALITY_SAMPLES) / QUALITY_SFREQ
    for name in ("T7", "T8", "P7", "P8"):
        data[labels.index(name)] += 40.0 * np.sin(2 * np.pi * 50.0 * t + rng.uniform(0.0, 2 * np.pi))
    for name in ("F3", "C4", "P3"):
        data[labels.index(name)] = 15.0 * _pink_noise(rng)
    for name in ("Fz", "Pz", "Oz"):
        data[labels.index(name)] += 30.0 * rng.normal(size=QUALITY_SAMPLES)
    data[labels.index("O2"), _seconds(20, 30)] = 0.0
    data[labels.index("F8")] += 900.0 * _bump(40.0, 10.0)
    return data


def quality_artefact_signals(seed: int) -> np.ndarray:
    """Artefacts dominate (negative case of M09-02, ICLabel): one cortical source next to eye blinks,
    horizontal eye movements, six muscle sources, a heartbeat and muscle-like movement bursts in 30 % of the
    2-s epochs; 24 channels, 3 µV amplifier noise."""
    rng = np.random.default_rng(seed)
    labels = ARTEFACT_LABELS
    data = _brain(rng, labels, 1, 15.0) + _blinks(rng, labels, (50.0, 80.0), (2.5, 5.0))
    data += _muscle(rng, labels, 6, 8.0) + _eye_movements(rng, labels) + _heartbeat(rng, labels)
    return _amplifier(rng, data + _movement(rng, labels, 0.3, "burst"), noise_uv=3.0)


def _quality_edf(path: Path, signals: np.ndarray, labels: tuple[str, ...] = QUALITY_LABELS) -> None:
    write_edf(path, sfreq=QUALITY_SFREQ, seconds=QUALITY_SECONDS, labels=labels, microvolts=signals)


# --- annotation fixtures (M10, A-80) ------------------------------------------------------------------------
#
# A short night (300 s, two channels at 16 Hz, so the files stay small) with three scorers who stage ten 30-s
# epochs each in annotation-only EDF+C files (night_<scorer>.edf, attached to night.edf by their stem).
# annotation_continuous_ok: pairwise kappa 1.0 / 0.5 / 0.5 (mean 0.667 >= 0.6, minimum 0.5), every code in the
# vocabulary, no gaps or overlaps; scorer1 also marks "Lights off" (zero duration: vocabulary only).
# annotation_continuous_issues: scorer1 writes "Stage 2" (not in the vocabulary), scorer2 leaves 180-210 s
# unscored and overlaps 80-90 s, scorer3 disagrees with both (mean kappa below 0.6).
# bids_events_issues: an oddball task in BIDS with two annotators in the events.tsv column "annotator" and the
# vocabulary in task-oddball_events.json Levels; annotator A2 writes "stimx" (not in the vocabulary) and two
# overlapping "standard" events, annotator A1 a "response" during a "standard" (another code: allowed).

ANNOTATION_VOCABULARY = ("W", "N1", "N2", "N3", "R", "Lights off")


def _staged(stages: tuple[str, ...]) -> tuple[tuple[float, float, str], ...]:
    return tuple((30.0 * index, 30.0, stage) for index, stage in enumerate(stages))


HYPNOGRAMS_OK = {
    "scorer1": ((0.0, 0.0, "Lights off"), *_staged(("W", "W", "N1", "N2", "N2", "N3", "N3", "N2", "R", "W"))),
    "scorer2": _staged(("W", "W", "N1", "N2", "N2", "N3", "N3", "N2", "R", "W")),
    "scorer3": _staged(("W", "N1", "N1", "N2", "N3", "N3", "N2", "N2", "R", "R")),
}
HYPNOGRAMS_ISSUES = {
    "scorer1": _staged(("W", "W", "N1", "N2", "Stage 2", "N3", "N3", "N2", "R", "W")),
    "scorer2": (
        (0.0, 30.0, "W"),
        (30.0, 30.0, "N1"),
        (60.0, 30.0, "N2"),
        (80.0, 40.0, "N2"),  # overlaps the previous epoch from 80 to 90 s
        (120.0, 30.0, "N2"),
        (150.0, 30.0, "N3"),
        (210.0, 30.0, "N2"),  # 180-210 s unscored: a gap
        (240.0, 30.0, "R"),
        (270.0, 30.0, "W"),
    ),
    "scorer3": _staged(("N3", "R", "W", "N1", "W", "N2", "R", "N3", "N2", "N1")),
}


def _night(path: Path, seed: int) -> None:
    write_edf(path, sfreq=16, seconds=300, labels=("C3", "C4"), seed=seed)


def _annotated(hypnograms: dict[str, tuple[tuple[float, float, str], ...]], seed: int) -> dict[str, Any]:
    files: dict[str, Callable[[Path], None]] = {"night.edf": partial(_night, seed=seed)}
    for scorer, entries in hypnograms.items():
        files[f"night_{scorer}.edf"] = partial(write_annotation_edf, annotations=entries)
    return files


ODDBALL_EVENTS = (  # (onset, duration, trial_type, annotator)
    (1.2, 0.6, "standard", "A1"),
    (3.2, 0.6, "deviant", "A1"),
    (5.2, 0.6, "standard", "A1"),
    (5.4, 0.4, "response", "A1"),
    (8.2, 0.6, "standard", "A1"),
    (11.2, 0.6, "deviant", "A1"),
    (14.2, 0.6, "standard", "A1"),
    (1.2, 0.6, "standard", "A2"),
    (3.2, 0.6, "deviant", "A2"),
    (5.2, 0.6, "standard", "A2"),
    (5.6, 0.6, "standard", "A2"),
    (8.2, 0.6, "stimx", "A2"),
    (11.2, 0.6, "deviant", "A2"),
    (14.2, 0.6, "standard", "A2"),
)
ODDBALL_LEVELS = {"standard": "Standard tone", "deviant": "Deviant tone", "response": "Button press"}


def _oddball_events() -> str:
    rows = sorted(ODDBALL_EVENTS, key=lambda row: (row[0], row[3]))
    return "onset\tduration\ttrial_type\tannotator\n" + "".join(
        f"{onset}\t{duration}\t{kind}\t{who}\n" for onset, duration, kind, who in rows
    )


def _bids_events_issues() -> dict[str, Callable[[Path], None]]:
    eeg = "sub-01/eeg/sub-01_task-oddball"
    sidecar = _eeg_sidecar(complete=False, TaskName="oddball", SamplingFrequency=256, EEGChannelCount=2)
    return {
        "dataset_description.json": lambda p: _json(p, _description(complete=True)),
        "README": lambda p: _text(p, README),
        "participants.tsv": lambda p: _text(p, "participant_id\nsub-01\n"),
        "task-oddball_events.json": lambda p: _json(
            p,
            {
                "trial_type": {"Description": "Kind of event", "Levels": ODDBALL_LEVELS},
                "annotator": {"Description": "Role code of the person who marked the event"},
            },
        ),
        f"{eeg}_eeg.edf": lambda p: write_edf(
            p, sfreq=256, seconds=20, labels=("Fz", "Cz"), label_prefix="", seed=72
        ),
        f"{eeg}_eeg.json": lambda p: _json(p, sidecar),
        f"{eeg}_channels.tsv": lambda p: _text(p, _channels_tsv(("Fz", "Cz"))),
        f"{eeg}_events.tsv": lambda p: _text(p, _oddball_events()),
    }


IMPEDANCES_OK = {label: "3" for label in EEG_LABELS}

# --- provenance fixtures (M13, CORE-M13-03) ----------------------------------------------------------------
# .neurogrid/provenance.yaml documents processing steps and software versions (A-82); the processing step and
# the software are synthetic examples. Manifests are never committed: tests build them in temporary folders.
PROVENANCE_OK = """# Synthetic provenance documentation for NeuroGrid tests (tools/gen_fixtures.py).
processing_steps:
  - step: export_edf
    tool: ExampleAcq
    version: "2.1.0"
    parameters: {highpass_hz: 0.1, notch: false}
software:
  - name: ExampleAcq
    version: "2.1.0"
"""
PROVENANCE_INCOMPLETE = """# Synthetic provenance documentation, tool version missing (tools/gen_fixtures.py).
processing_steps:
  - step: export_edf
    tool: ExampleAcq
    version: ""
"""

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
    **_prefixed("bids_ai_ok", _bids_ai_ok()),
    **_prefixed("bids_ai_issues", _bids_ai_issues()),
    "edf_quality_ok/rec.edf": lambda p: _quality_edf(p, quality_ok_signals(41)),
    "edf_quality_issues/rec.edf": lambda p: _quality_edf(p, quality_issues_signals(51)),
    "edf_quality_artefacts/rec.edf": lambda p: _quality_edf(p, quality_artefact_signals(63), ARTEFACT_LABELS),
    "provenance_ok/rec.edf": lambda p: write_edf(p, seed=71, seconds=2),
    "provenance_ok/.neurogrid/provenance.yaml": lambda p: _text(p, PROVENANCE_OK),
    "provenance_incomplete/rec.edf": lambda p: write_edf(p, seed=72, seconds=2),
    "provenance_incomplete/.neurogrid/provenance.yaml": lambda p: _text(p, PROVENANCE_INCOMPLETE),
    "provenance_steps_invalid/rec.edf": lambda p: write_edf(p, seed=73, seconds=2),
    "provenance_steps_invalid/.neurogrid/processing_steps.json": lambda p: _text(p, '[{"step": 1}]\n'),
    **_prefixed("annotation_continuous_ok", _annotated(HYPNOGRAMS_OK, seed=70)),
    **_prefixed("annotation_continuous_issues", _annotated(HYPNOGRAMS_ISSUES, seed=71)),
    **_prefixed("bids_events_issues", _bids_events_issues()),
}


# --- synthetic results.json for the report scaling test (A-59, KONZEPT 4 "Skalierung 1000 x 64") ----------

SCALE_SEED = 20261023
SCALE_AS_OF = date(2026, 10, 23)
SCALE_SECONDS = 1200  # each synthetic recording: 20 min, one window per second (A-18)
SCALE_LINE_THRESHOLD = 0.407669  # CORE-M07-01 max_ratio, rulepacks/core.yaml
MAX_SCALE_RANGES = 100  # time ranges kept per channel, as neurogrid/quality/stream.py keeps them


def _scale_ranges(flagged: int, count: int) -> tuple[list[tuple[float, float]], int]:
    """``count`` equal runs of flagged 1-s windows spread over the recording, together ``flagged`` windows
    (at most MAX_SCALE_RANGES listed, the number of runs counted)."""
    count = min(count, flagged)
    if not count:
        return [], 0
    step = SCALE_SECONDS // count
    lengths = [flagged // count + (1 if i < flagged % count else 0) for i in range(count)]
    ranges = [(float(i * step), float(i * step + length)) for i, length in enumerate(lengths)]
    return ranges[:MAX_SCALE_RANGES], count


def scale_results(recordings: int = 1000, channels: int = 64, worst_case: bool = True) -> Any:
    """A results.json (as neurogrid.model.results.Results) for ``recordings`` recordings with ``channels``
    EEG channels each, evaluated by NeuroGrid's own rule engine with the built-in core pack: the M06-M09
    measurements are synthetic, the findings, passed counts, traffic lights and effective thresholds are the
    engine's. Only the quality checks are measured; the other core rules give no finding.

    ``worst_case``: every channel of every recording fails M07 (line-noise ratio above 0.407669) and M08-01
    (flat share above 0.05 in 4 runs of flagged windows, a channel that goes flat a few times), the case A-59
    targets: 2 x recordings x channels channel findings (128 000 for 1000 x 64) plus the M06/M09 findings.
    Otherwise the values are drawn: log-normal line-noise ratios, 2 % flat channels (37 runs, so more than
    the 20 time ranges a report row lists) and 1 % clipped channels (12 runs). All values come from
    random.Random(SCALE_SEED), so the result is the same on every platform apart from the environment
    block."""
    from neurogrid import pipeline
    from neurogrid.checks.registry import REGISTRY
    from neurogrid.kernel import canonical, engine
    from neurogrid.kernel.findings import TimeRange
    from neurogrid.kernel.provenance import ManifestStatus
    from neurogrid.kernel.rules import Measurement
    from neurogrid.model.dataset import Dataset
    from neurogrid.model.results import (
        ConfigInfo,
        ManifestInfo,
        RecordingSummary,
        Results,
        RuleInfo,
        RulepackInfo,
        Summary,
    )

    rng = random.Random(SCALE_SEED)
    core = pipeline.load_rulepack_ref("core")
    names = [f"E{index:03d}" for index in range(1, channels + 1)]
    measurements: dict[str, list[Measurement]] = {}
    summaries = []

    def measure(check: str, rec: str, file: str, **kwargs: Any) -> None:
        measurements.setdefault(check, []).append(
            Measurement(check_id=check, object=rec, file=file, identity=(file, rec), **kwargs)
        )

    for index in range(recordings):
        rec = "rec-" + hashlib.sha256(f"rec_{index:04d}.edf".encode()).hexdigest()[:8]
        file = f"{rec}.edf"
        line_details = {"line_frequency_hz": 50.0, "line_frequency_source": "sidecar"}
        m07: dict[str, Any] = {}
        m08: dict[str, Any] = {}
        for name in names:
            if worst_case:
                ratio = SCALE_LINE_THRESHOLD * (1.5 + rng.random())
                flat = 0.06 + 0.2 * rng.random()
                clipped = 0.0
            else:
                ratio = rng.lognormvariate(-2.3, 0.9)
                flat = 0.0 if rng.random() > 0.02 else 0.3 * rng.random()
                clipped = 0.0 if rng.random() > 0.01 else 0.2 * rng.random()
            ratio = canonical.round_float(ratio)
            m07[name] = {"ratio": ratio, "other_ratio": canonical.round_float(ratio / 5)}
            measure(
                "quality.line_noise", rec, file, subkey=name, channel=name, value=ratio, details=line_details
            )
            windows: dict[str, Any] = {"windows": SCALE_SECONDS}
            for check, share, method, runs, field in (
                ("quality.flatline", flat, "peak_to_peak", 4 if worst_case else 37, "flat_fraction"),
                ("quality.clipping", clipped, "range", 12, "clipped_fraction"),
            ):
                flagged = round(share * SCALE_SECONDS)
                ranges, total = _scale_ranges(flagged, runs)
                measure(
                    check,
                    rec,
                    file,
                    subkey=name,
                    channel=name,
                    value=flagged / SCALE_SECONDS,
                    time_ranges=tuple(TimeRange(start_s=a, end_s=b) for a, b in ranges),
                    time_ranges_total=total,
                    time_ranges_duration_s=float(flagged) if flagged else None,
                    details={
                        "windows": SCALE_SECONDS,
                        "flagged_windows": flagged,
                        "unusable_windows": 0,
                        "method": method,
                    },
                )
                windows[field] = flagged / SCALE_SECONDS
            m08[name] = windows
        values = {}
        for key, check, upper in (
            ("M06", "quality.bad_channels", 0.4),
            ("M09a", "quality.autoreject", 0.4),
            ("M09b", "quality.non_brain_components", 0.8),
        ):
            values[key] = canonical.round_float(upper * rng.random())
            measure(check, rec, file, value=values[key])
        summaries.append(
            RecordingSummary(
                id=rec,
                format="EDF",
                sampling_rate_hz=500.0,
                duration_s=float(SCALE_SECONDS),
                n_channels=channels,
                n_eeg_channels=channels,
                metadata_sources={"channels": "header", "duration_s": "header", "sampling_rate_hz": "header"},
                metrics={
                    "M06": {
                        "state": "measured",
                        "value": values["M06"],
                        "channels": channels,
                        "ransac": True,
                    },
                    "M07": {
                        "line_frequency_hz": 50.0,
                        "line_frequency_source": "sidecar",
                        "other_frequency_hz": 60.0,
                        "channels": m07,
                    },
                    "M08": {"window_s": 1.0, "clipping_method": "range", "channels": m08},
                    "M09a": {"state": "measured", "value": values["M09a"]},
                    "M09b": {"state": "measured", "value": values["M09b"]},
                    "data_seconds": float(SCALE_SECONDS),
                },
                sample={
                    "mode": "sample",
                    # 10 x 60 s in the middle of 10 equal parts (KONZEPT 1.5)
                    "segments": [{"start_s": 120.0 * i + 30.0, "duration_s": 60.0} for i in range(10)],
                    "seed": 20261011,
                    "channels": channels,
                    "positions": "sidecar",
                    "positions_unused": {},
                    "excluded_channels": [],
                    "notch_hz": [50.0, 100.0],
                    "resample_hz": 250.0,
                    "band_hz": [1.0, 100.0],
                    "epoch_s": 2.0,
                },
            )
        )
    result = engine.run(
        engine.EngineInput(packs=[core], registry=REGISTRY, measurements=measurements, as_of=SCALE_AS_OF)
    )
    pack = core.pack
    return Results(
        disclaimer=pipeline.disclaimer_block(),
        tool=pipeline.tool_info(),
        environment=pipeline.environment_info(),
        dataset=Dataset(
            id=f"scale-{recordings}x{channels}",
            name="Synthetic scaling dataset (tools/gen_fixtures.py, no data of a person)",
            version="1",
            license="CC-BY-4.0",
            rulepacks=[pack.rulepack],
        ),
        rulepacks=[
            RulepackInfo(
                name=pack.rulepack,
                version=pack.version,
                source=pack.source,
                source_status=pack.source_status,
                norm=pack.norm,
                sha256=core.sha256,
            )
        ],
        rules=[
            RuleInfo(
                id=rule.id,
                rulepack=pack.rulepack,
                clause=rule.clause,
                title_zh=rule.title_zh,
                title_en=rule.title_en,
                phase=rule.phase,
                check=rule.check,
                severity=rule.effective_severity(False),
                strict_severity=rule.strict_severity,
                verification=rule.verification,
                source_status=pack.source_status,
            )
            for rule in pack.rules
        ],
        config=ConfigInfo(
            canonical_sha256=hashlib.sha256(b"synthetic scaling configuration").hexdigest(),
            as_of=SCALE_AS_OF,
            seed=20261011,
            strict=False,
            sampling={"mode": "sample", "segment_s": 60.0, "segments": 10},
            effective_params=result.effective_params,
            effective_settings={},
        ),
        recordings=summaries,
        findings=result.findings,
        passed=result.passed,
        evidence=result.evidence,
        exceptions=result.exceptions,
        notices=result.notices,
        summary=Summary(
            phases=result.phases,
            coverage=result.coverage,
            errors=sum(p.errors for p in result.phases.values()),
            warnings=sum(p.warnings for p in result.phases.values()),
            exit_code=result.exit_code,
            open_evidence=sum(p.open_evidence for p in result.phases.values()),
        ),
        manifest=ManifestInfo(status=ManifestStatus.MISSING),
    )


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
    parser.add_argument(
        "--scale-results", type=Path, help="write a synthetic results.json (A-59) to this file"
    )
    parser.add_argument("--recordings", type=int, default=1000)
    parser.add_argument("--channels", type=int, default=64)
    parser.add_argument("--typical", action="store_true", help="drawn values instead of the worst case")
    args = parser.parse_args()
    if args.scale_results is not None:
        from neurogrid.kernel import canonical

        results = scale_results(args.recordings, args.channels, worst_case=not args.typical)
        args.scale_results.write_bytes(canonical.dumps(results))
        print(f"wrote {len(results.findings)} findings for {len(results.recordings)} recordings")
        return 0
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
