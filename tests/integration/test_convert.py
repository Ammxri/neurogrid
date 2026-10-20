"""Conversion of raw folders to EEG-BIDS: pipeline, convert module and CLI (NG-F02, CLI-02, NG-F14, M01, M02,
M04, A-03, A-04, A-05, A-12, A-46, A-51, A-53, A-54, A-77).

One conversion per format is shared by several tests (module-scoped fixtures); conversions run MNE-BIDS and
the bundled BIDS validator and take a few seconds each. Tests of the command line that only concern its
options and printed lines replace ``pipeline.run_convert`` by a stand-in.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import shutil
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import pytest

import gen_fixtures  # type: ignore[import-not-found]
import neurogrid
from conftest import AS_OF  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.cli import main
from neurogrid.config import parse as parse_config
from neurogrid.convert import BIDS_VERSION, NA_ALLOWED, _strip_edf, write_mapping_template
from neurogrid.io import ADAPTERS
from neurogrid.io.discover import FoundFile, pseudonym
from neurogrid.kernel.errors import ConfigError, InputError, NeuroGridError
from neurogrid.kernel.findings import Finding, Status
from neurogrid.model.results import Results

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
# Documented values differ from what MNE-BIDS would write by itself, so that the sidecars show their origin.
METADATA = '[metadata.defaults]\nreference = "FCz"\nline_frequency_hz = 60\nsoftware_filters = "n/a"\n'
DISCLAIMER = "Pre-check with NeuroGrid. Not a conformity assessment within the meaning of NMPA regulations."
NAME = "Mustermann_Max_1957"  # a raw folder name that identifies a person; it must never be printed (A-51)
EEG_NAMES = gen_fixtures.EEG_LABELS
FIF_CHANNELS = (  # name, MNE type, BIDS type in the output (None: not written)
    ("Fp1", "eeg", "EEG"),
    ("Fp2", "eeg", "EEG"),
    ("C3", "eeg", "EEG"),
    ("C4", "eeg", "EEG"),
    ("MEG 0111", "mag", None),
    ("MEG 0112", "grad", None),
    ("EOG 061", "eog", "EOG"),
    ("ECG 063", "ecg", "ECG"),
    ("EMG 001", "emg", "EMG"),
    ("STI 014", "stim", "TRIG"),
    ("MISC 001", "misc", "MISC"),
    ("RESP 001", "resp", "RESP"),
)
# A polysomnography-like EDF: the types come from NeuroGrid's label list (io/channels.py), not from MNE.
PSG_CHANNELS = (
    ("EEG Fp1", "EEG"),
    ("EEG C3", "EEG"),
    ("EOG L", "EOG"),
    ("ECG", "ECG"),
    ("EMG chin", "EMG"),
    ("Resp", "RESP"),
    ("SaO2", "MISC"),
    ("Status", "TRIG"),
)
IDENTIFYING = (b"Zhang", b"24.08.21", b"2021-08-24", b"20210824")  # name and dates in the identifying inputs
MEAS_DATE = datetime.datetime(2021, 8, 24, 10, 15, tzinfo=datetime.UTC)


def _row(
    path: str, subject: str, task: str = "rest", *, session: str | None = None, run: str | None = None
) -> str:
    text = f'[[convert.files]]\npath = "{path}"\nsubject = "{subject}"\ntask = "{task}"\n'
    if session is not None:
        text += f'session = "{session}"\n'
    if run is not None:
        text += f'run = "{run}"\n'
    return text


def _copy(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def _copy_folder(source: Path, target: Path) -> None:
    for path in source.iterdir():
        _copy(path, target / path.name)


def _write_config(raw: Path, text: str) -> Path:
    path = raw / ".neurogrid" / "neurogrid.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files_hash(paths: list[Path]) -> str:
    """Hash of a processing step: SHA-256 over the sorted lines "<file name>\\t<SHA-256>\\n" of all files of
    the recording (DM-07)."""
    lines = sorted(f"{path.name}\t{_sha256(path)}\n".encode() for path in paths)
    return hashlib.sha256(b"".join(lines)).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _tsv(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    return [dict(zip(header, line.split("\t"), strict=True)) for line in lines[1:] if line]


def _check(out: Path, work: Path) -> Results:
    """``check`` of a converted output with the core and the bids rule packs."""
    return pipeline.run_check(out, pipeline.CheckOptions(rulepacks=("bids",), as_of=AS_OF, work_base=work))


def _failed(results: Results, rule: str) -> list[Finding]:
    return [f for f in results.findings if f.rule_id == rule and f.status is Status.FAILED]


def _passed(results: Results, rule: str) -> list[str]:
    return [p.object for p in results.passed if p.rule_id == rule]


def _run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def _edf_pair(raw: Path) -> None:
    for name in ("rec_a.edf", "rec_b.edf"):
        _copy(FIX / "edf_ok" / name, raw / name)


def _mapped_edf_pair(raw: Path, first: str = "01", second: str = "02") -> None:
    _edf_pair(raw)
    _write_config(raw, METADATA + _row("rec_a.edf", first) + _row("rec_b.edf", second))


def _bdf(raw: Path) -> None:
    _copy(FIX / "bdf_ok" / "rec.bdf", raw / "rec.bdf")


def _brainvision(raw: Path) -> None:
    _copy_folder(FIX / "brainvision_ok", raw)


def _eeglab_with_positions(raw: Path) -> None:
    """eeglab_ok with electrode positions in ``chanlocs``, so that leaving them out is observable (A-77)."""
    import mne
    import scipy.io

    path = raw / "rec.set"
    _copy_folder(FIX / "eeglab_ok", raw)
    eeg = scipy.io.loadmat(path, appendmat=False)["EEG"]
    chanlocs = eeg["chanlocs"][0, 0]
    for index, label in enumerate(EEG_NAMES):
        for axis, value in zip("XYZ", gen_fixtures.POSITIONS[label], strict=True):
            chanlocs[0, index][axis] = np.array([[value * 1000.0]])  # EEGLAB stores millimetres
    scipy.io.savemat(path, {"EEG": eeg}, appendmat=False, format="5", oned_as="row")
    montage = mne.io.read_raw_eeglab(path, preload=False, verbose="error").get_montage()
    assert montage is not None and len(montage.ch_names) == len(EEG_NAMES)  # precondition of the test


def _fif(raw: Path) -> None:
    """A combined EEG/MEG FIF file with auxiliary channels, written with MNE at test time."""
    import mne

    names = [name for name, _kind, _bids in FIF_CHANNELS]
    info = mne.create_info(names, 500.0, [kind for _name, kind, _bids in FIF_CHANNELS], verbose="error")
    data = np.random.default_rng(20).normal(0.0, 1e-5, (len(names), 1000))
    data[[4, 5]] *= 1e-8  # magnetometer and gradiometer in T and T/m
    data[9] = 0.0  # trigger channel without events
    raw.mkdir(parents=True, exist_ok=True)
    mne.io.RawArray(data, info, verbose="error").save(raw / "rec_raw.fif", verbose="error")


def _fif_with_subject(path: Path) -> None:
    """A FIF file with measurement date, subject information and experimenter (identifying, A-51, A-77)."""
    import mne

    info = mne.create_info(list(EEG_NAMES[:4]), 500.0, "eeg", verbose="error")
    raw = mne.io.RawArray(np.random.default_rng(21).normal(0.0, 1e-5, (4, 1000)), info, verbose="error")
    raw.set_meas_date(MEAS_DATE)
    raw.info["subject_info"] = {
        "last_name": "Zhang",
        "first_name": "San",
        "birthday": datetime.date(1980, 1, 1),
        "sex": 1,
        "hand": 1,
    }
    raw.info["experimenter"] = "Li Wei"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw.save(path, verbose="error")


def _edf_plus_d(path: Path, onsets: tuple[int, ...] = (0, 5, 6)) -> None:
    """An EDF+D file: two EEG signals and 'EDF Annotations', three 1-s records with a gap after the first."""
    sfreq, annotation_samples, labels = 256, 30, ("EEG Fz", "EEG Cz")
    ns = len(labels) + 1
    header = bytearray()
    header += b"0".ljust(8) + b"X X X X".ljust(80) + b"Startdate X X X X".ljust(80)
    header += b"01.01.85" + b"00.00.00" + str(256 * (ns + 1)).encode().ljust(8) + b"EDF+D".ljust(44)
    header += str(len(onsets)).encode().ljust(8) + b"1".ljust(8) + str(ns).encode().ljust(4)
    for label in (*labels, "EDF Annotations"):
        header += label.encode().ljust(16)
    header += b"".ljust(80) * ns
    header += b"uV".ljust(8) * len(labels) + b"".ljust(8)
    header += b"-500".ljust(8) * len(labels) + b"-1".ljust(8)
    header += b"500".ljust(8) * len(labels) + b"1".ljust(8)
    header += b"-32768".ljust(8) * ns + b"32767".ljust(8) * ns + b"".ljust(80) * ns
    header += str(sfreq).encode().ljust(8) * len(labels) + str(annotation_samples).encode().ljust(8)
    header += b"".ljust(32) * ns
    rng = np.random.default_rng(23)
    body = bytearray()
    for onset in onsets:
        for _label in labels:
            body += rng.integers(-1000, 1000, sfreq).astype("<i2").tobytes()
        body += f"+{onset}\x14\x14\x00".encode().ljust(2 * annotation_samples, b"\x00")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(header) + bytes(body))


def _epoched_eeglab(path: Path) -> None:
    """An EEGLAB data set with two epochs (trials = 2), which ``check`` reads as epochs (A-77)."""
    import scipy.io

    gen_fixtures.write_eeglab(path, seed=22)
    eeg = scipy.io.loadmat(path, appendmat=False)["EEG"]
    points = int(eeg["pnts"][0, 0][0, 0])
    eeg["trials"][0, 0] = np.array([[2.0]])
    eeg["pnts"][0, 0] = np.array([[points / 2]])
    eeg["xmax"][0, 0] = np.array([[(points / 2 - 1) / 512]])
    scipy.io.savemat(path, {"EEG": eeg}, appendmat=False, format="5", oned_as="row")
    assert ADAPTERS[".set"].read_check(path) is None  # precondition: readable for check (as epochs)


# --- one conversion per format -----------------------------------------------------------------------------


@dataclass(frozen=True)
class FormatCase:
    build: Callable[[Path], None]  # writes the data files into the raw folder
    config: str  # neurogrid.toml besides METADATA and [dataset]
    targets: dict[str, tuple[str, str]]  # data file in the output -> (source file, task label)
    channels: tuple[tuple[str, str], ...]  # (name, BIDS type) of every recording, in file order
    input_format: str
    sfreq: float
    companions: tuple[str, ...] = ()  # extensions of further files next to each data file
    name: str | None = None  # [dataset] name
    license: str | None = None  # [dataset] license


FORMATS = {
    # A table row (with session and run) for rec_a.edf and the expression for the rest: table rows win, even
    # though rec_a.edf matches the expression as well (A-05, A-77).
    "EDF": FormatCase(
        build=_edf_pair,
        config="[convert]\npattern = '(?P<task>rec)_(?P<subject>[ab])\\.edf'\n"
        + _row("rec_a.edf", "01", session="pre", run="1"),
        targets={
            "sub-01/ses-pre/eeg/sub-01_ses-pre_task-rest_run-1_eeg.edf": ("rec_a.edf", "rest"),
            "sub-b/eeg/sub-b_task-rec_eeg.edf": ("rec_b.edf", "rec"),
        },
        channels=tuple((f"EEG {label}", "EEG") for label in EEG_NAMES),
        input_format="EDF",
        sfreq=512.0,
        name="Synthetic EDF conversion",
        license="CC0",
    ),
    "BDF": FormatCase(  # no [dataset] section
        build=_bdf,
        config=_row("rec.bdf", "01"),
        targets={"sub-01/eeg/sub-01_task-rest_eeg.bdf": ("rec.bdf", "rest")},
        channels=tuple((f"EEG {label}", "EEG") for label in EEG_NAMES),
        input_format="BDF",
        sfreq=512.0,
    ),
    "BrainVision": FormatCase(
        build=_brainvision,
        config=_row("rec.vhdr", "01"),
        targets={"sub-01/eeg/sub-01_task-rest_eeg.vhdr": ("rec.vhdr", "rest")},
        channels=tuple((label, "EEG") for label in EEG_NAMES),
        input_format="BrainVision",
        sfreq=500.0,
        companions=(".eeg", ".vmrk"),
        name="Synthetic BrainVision conversion",
    ),
    "EEGLAB": FormatCase(
        build=_eeglab_with_positions,
        config=_row("rec.set", "01"),
        targets={"sub-01/eeg/sub-01_task-rest_eeg.set": ("rec.set", "rest")},
        channels=tuple((label, "EEG") for label in EEG_NAMES),
        input_format="EEGLAB",
        sfreq=512.0,
        companions=(".fdt",),
        name="Synthetic EEGLAB conversion",
    ),
    "FIF": FormatCase(  # written as BrainVision, EEG and auxiliary channels only (A-05, A-77)
        build=_fif,
        config=_row("rec_raw.fif", "01"),
        targets={"sub-01/eeg/sub-01_task-rest_eeg.vhdr": ("rec_raw.fif", "rest")},
        channels=tuple((name, bids) for name, _kind, bids in FIF_CHANNELS if bids is not None),
        input_format="FIF",
        sfreq=500.0,
        companions=(".eeg", ".vmrk"),
        name="Synthetic FIF conversion",
    ),
}


@dataclass(frozen=True)
class Converted:
    case: FormatCase
    raw: Path
    out: Path
    summary: pipeline.ConvertSummary
    results: Results  # check of the output with the core and the bids rule packs


@pytest.fixture(scope="module")
def conversions(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], Converted]:
    """Converts each format once per module, on first use."""
    done: dict[str, Converted] = {}

    def get(name: str) -> Converted:
        if name not in done:
            case = FORMATS[name]
            base = tmp_path_factory.mktemp(f"convert-{name}")
            raw = base / "raw"
            raw.mkdir()
            case.build(raw)
            dataset = "".join(
                f'{key} = "{value}"\n'
                for key, value in (("name", case.name), ("license", case.license))
                if value
            )
            _write_config(raw, METADATA + (f"[dataset]\n{dataset}" if dataset else "") + case.config)
            out = base / "bids"
            summary = pipeline.run_convert(raw, out, work_base=base)
            done[name] = Converted(case, raw, out, summary, _check(out, base))
        return done[name]

    return get


@pytest.fixture(params=sorted(FORMATS))
def converted(request: pytest.FixtureRequest, conversions: Callable[[str], Converted]) -> Converted:
    return conversions(request.param)


def test_conversion_summary_and_validator(converted: Converted) -> None:
    summary = converted.summary
    assert summary.converted == len(converted.case.targets)
    assert summary.skipped == [] and summary.missing_fields == {}
    assert summary.validator_errors == 0 and summary.exit_code == 0
    assert summary.steps_file == converted.out / ".neurogrid" / "processing_steps.json"
    assert summary.steps_file.is_file()


def test_dataset_level_files(converted: Converted) -> None:
    out, case = converted.out, converted.case
    description = _json(out / "dataset_description.json")
    assert description["BIDSVersion"] == BIDS_VERSION == "1.11.1"
    assert description["DatasetType"] == "raw"
    assert description["GeneratedBy"] == [{"Name": "NeuroGrid", "Version": neurogrid.__version__}]
    assert "Authors" not in description  # the MNE-BIDS placeholder is not kept, authors are not invented
    assert description["Name"] not in ("", "[Unspecified]")  # no MNE-BIDS placeholder
    if case.license:
        assert description["License"] == case.license
    else:
        assert "License" not in description
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert f"converted to BIDS {BIDS_VERSION} with NeuroGrid {neurogrid.__version__}" in readme
    if case.name:  # without [dataset] name see test_name_is_na_without_dataset_name
        assert description["Name"] == case.name
        assert readme.startswith(f"# {case.name}\n")
    assert not any((out / name).exists() for name in ("README", "README.txt", "README.rst"))
    subjects = sorted(row["participant_id"] for row in _tsv(out / "participants.tsv"))
    assert subjects == sorted({target.split("/")[0] for target in case.targets})


def test_recording_files_sidecars_and_channels(converted: Converted) -> None:
    out, case = converted.out, converted.case
    data_files = sorted(
        p.relative_to(out).as_posix()
        for p in out.rglob("*_eeg.*")
        if p.suffix in (".edf", ".bdf", ".vhdr", ".set")
    )
    assert data_files == sorted(case.targets)
    for target, (_source, task) in case.targets.items():
        data = out / target
        for extension in case.companions:
            assert data.with_suffix(extension).is_file(), extension
        sidecar = _json(data.with_suffix(".json"))
        assert sidecar["TaskName"] == task
        assert sidecar["EEGReference"] == "FCz"
        assert sidecar["PowerLineFrequency"] == 60
        assert sidecar["SoftwareFilters"] == "n/a"
        assert sidecar["SamplingFrequency"] == case.sfreq
        typed_na = [key for key, value in sidecar.items() if value == "n/a" and key not in NA_ALLOWED]
        assert typed_na == []  # typed recommended fields never get n/a (A-05)
        channels = _tsv(data.with_name(data.name.replace("_eeg" + data.suffix, "_channels.tsv")))
        assert [(row["name"], row["type"]) for row in channels] == list(case.channels)
        assert sidecar["EEGChannelCount"] == sum(1 for _name, kind in case.channels if kind == "EEG")
    # Positions are never written as measured CapTrak positions (EEGLAB: possibly template positions).
    assert list(out.rglob("*_electrodes.tsv")) == [] and list(out.rglob("*_coordsystem.json")) == []


def test_processing_steps_record_every_conversion(converted: Converted) -> None:
    out, case = converted.out, converted.case
    steps = _json(out / ".neurogrid" / "processing_steps.json")
    assert sorted(step["parameters"]["target"] for step in steps) == sorted(case.targets)
    for step in steps:
        target = step["parameters"]["target"]
        source, _task = case.targets[target]
        assert step["step"] == "convert_to_bids" and step["tool"] == "neurogrid"
        assert step["version"] == neurogrid.__version__
        assert step["parameters"] == {
            "input_format": case.input_format,
            "output_format": PurePosixPath(target).suffix.lstrip(".").upper(),
            "strip_identifying_headers": False,
            "bids_version": BIDS_VERSION,
            "target": target,
        }
        # Both hashes cover every file of the recording: header, data and marker file, .fdt (DM-07).
        stem = PurePosixPath(source).stem
        inputs = [p for p in converted.raw.iterdir() if p.is_file() and p.stem == stem]
        assert sorted(p.suffix for p in inputs) == sorted(
            {"BrainVision": [".eeg", ".vhdr", ".vmrk"], "EEGLAB": [".fdt", ".set"]}.get(
                case.input_format, [PurePosixPath(source).suffix]
            )
        )
        outputs = [out / target, *((out / target).with_suffix(ext) for ext in case.companions)]
        assert step["input_hash"] == _files_hash(inputs)
        assert step["output_hash"] == _files_hash(outputs)


def test_check_of_the_output_finds_no_validator_error(converted: Converted) -> None:
    results = converted.results
    assert results.dataset.is_bids
    assert _failed(results, "BIDS-STO-001") == [] and _passed(results, "BIDS-STO-001") != []
    assert _failed(results, "CORE-M02-01") == []  # every required field is documented in the output
    assert sorted(_passed(results, "CORE-M02-01")) == sorted(converted.case.targets)
    assert _failed(results, "CORE-M01-02") == [] and _failed(results, "CORE-M04-04") == []
    consistency = [(f.object, f.subkey) for f in _failed(results, "CORE-M02-02")]
    if converted.case.name:
        assert consistency == []
    else:
        # TaskName and BIDSVersion are consistent; the missing Name must be reported (A-77), which is
        # test_check_reports_the_missing_dataset_name, so it is not asserted either way here.
        assert [item for item in consistency if item != ("dataset", "Name")] == []


def test_fif_output_keeps_eeg_and_auxiliary_channels_only(conversions: Callable[[str], Converted]) -> None:
    converted = conversions("FIF")
    names = [row["name"] for row in _tsv(converted.out / "sub-01" / "eeg" / "sub-01_task-rest_channels.tsv")]
    assert "MEG 0111" not in names and "MEG 0112" not in names
    assert names == [name for name, _kind, bids in FIF_CHANNELS if bids is not None]
    header = (converted.out / "sub-01" / "eeg" / "sub-01_task-rest_eeg.vhdr").read_text(encoding="utf-8")
    assert "NumberOfChannels=10" in header.splitlines()


def test_fif_sidecar_does_not_name_the_vendor_of_the_output_format(
    conversions: Callable[[str], Converted],
) -> None:
    sidecar = _json(conversions("FIF").out / "sub-01" / "eeg" / "sub-01_task-rest_eeg.json")
    assert sidecar.get("Manufacturer") != "Brain Products"


def test_name_is_na_without_dataset_name(conversions: Callable[[str], Converted]) -> None:
    converted = conversions("BDF")  # converted without [dataset] section
    assert converted.case.name is None
    assert _json(converted.out / "dataset_description.json")["Name"] == "n/a"


def test_check_reports_the_missing_dataset_name(conversions: Callable[[str], Converted]) -> None:
    results = conversions("BDF").results
    assert ("dataset", "Name") in [(f.object, f.subkey) for f in _failed(results, "CORE-M02-02")]


# --- channel types and EDF variants (A-05, A-77, M04) ------------------------------------------------------


@pytest.fixture(scope="module")
def edf_variants(tmp_path_factory: pytest.TempPathFactory) -> Converted:
    """A polysomnography-like EDF with auxiliary channels and an EDF+D file, converted together."""
    base = tmp_path_factory.mktemp("edf-variants")
    raw = base / "raw"
    gen_fixtures.write_edf(
        raw / "psg.edf", labels=tuple(name for name, _kind in PSG_CHANNELS), label_prefix=""
    )
    _edf_plus_d(raw / "rec_d.edf")
    _write_config(raw, METADATA + _row("psg.edf", "01", "sleep") + _row("rec_d.edf", "02"))
    out = base / "bids"
    summary = pipeline.run_convert(raw, out, work_base=base)
    case = FormatCase(
        build=lambda _raw: None,
        config="",
        targets={
            "sub-01/eeg/sub-01_task-sleep_eeg.edf": ("psg.edf", "sleep"),
            "sub-02/eeg/sub-02_task-rest_eeg.edf": ("rec_d.edf", "rest"),
        },
        channels=PSG_CHANNELS,
        input_format="EDF",
        sfreq=512.0,
    )
    return Converted(case, raw, out, summary, _check(out, base))


def test_channel_types_from_the_labels_are_written(edf_variants: Converted) -> None:
    out, summary, results = edf_variants.out, edf_variants.summary, edf_variants.results
    assert (summary.converted, summary.skipped, summary.validator_errors, summary.exit_code) == (2, [], 0, 0)
    channels = _tsv(out / "sub-01" / "eeg" / "sub-01_task-sleep_channels.tsv")
    assert [(row["name"], row["type"]) for row in channels] == list(PSG_CHANNELS)
    sidecar = _json(out / "sub-01" / "eeg" / "sub-01_task-sleep_eeg.json")
    counts = ("EEG", "EOG", "ECG", "EMG", "Misc", "Trigger")
    assert [sidecar[f"{kind}ChannelCount"] for kind in counts] == [2, 1, 1, 1, 1, 1]
    # The EEG channel count agrees in sidecar, channels.tsv and file (M04-04, A-46).
    assert "sub-01/eeg/sub-01_task-sleep_eeg.edf" in _passed(results, "CORE-M04-04")
    assert _failed(results, "CORE-M04-04") == [] and _failed(results, "BIDS-STO-001") == []


def test_edf_plus_d_is_copied_with_its_time_structure(edf_variants: Converted) -> None:
    raw, out, results = edf_variants.raw, edf_variants.out, edf_variants.results
    written = out / "sub-02" / "eeg" / "sub-02_task-rest_eeg.edf"
    assert written.read_bytes() == (raw / "rec_d.edf").read_bytes()  # EDF+D is not rejected or rewritten
    assert written.read_bytes()[192:197] == b"EDF+D"
    assert "sub-02/eeg/sub-02_task-rest_eeg.edf" in _passed(results, "CORE-M01-02")


# --- identifying header fields (A-05, A-77, E3 e) ----------------------------------------------------------


@dataclass(frozen=True)
class Identifying:
    strip: bool
    raw: Path
    out: Path
    summary: pipeline.ConvertSummary
    results: Results


@pytest.fixture(scope="module", params=[False, True], ids=["keep-headers", "strip-headers"])
def identifying(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Identifying:
    """edf_identifying (name and dates in the header), an EEGLAB recording and a FIF file with subject
    information and measurement date, converted with and without --strip-identifying-headers."""
    strip = bool(request.param)
    base = tmp_path_factory.mktemp("identifying")
    raw = base / "raw"
    _copy(FIX / "edf_identifying" / "rec_named.edf", raw / "rec_named.edf")
    _copy_folder(FIX / "eeglab_ok", raw)
    _fif_with_subject(raw / "rec_id_raw.fif")
    _write_config(
        raw, METADATA + _row("rec_named.edf", "01") + _row("rec.set", "02") + _row("rec_id_raw.fif", "03")
    )
    out = base / "bids"
    summary = pipeline.run_convert(raw, out, strip_identifying_headers=strip, work_base=base)
    return Identifying(strip, raw, out, summary, _check(out, base))


def test_identifying_headers_are_kept_unless_stripped(identifying: Identifying) -> None:
    raw, out, summary = identifying.raw, identifying.out, identifying.summary
    assert (summary.converted, summary.skipped, summary.validator_errors, summary.exit_code) == (3, [], 0, 0)
    source = (raw / "rec_named.edf").read_bytes()
    written = (out / "sub-01" / "eeg" / "sub-01_task-rest_eeg.edf").read_bytes()
    assert written[256:] == source[256:]  # signal headers and data are untouched
    acq_time = _tsv(out / "sub-01" / "sub-01_scans.tsv")[0]["acq_time"]
    fif_acq_time = _tsv(out / "sub-03" / "sub-03_scans.tsv")[0]["acq_time"]
    if identifying.strip:
        assert written[8:88] == b"X X X X".ljust(80)
        assert written[88:168] == b"X".ljust(80)  # plain EDF: no EDF+ start date subfield
        assert written[168:176] == b"01.01.85"
        assert acq_time == "n/a" and fif_acq_time == "n/a"
        # MNE drops subject_info before writing, so nothing is derived from it (A-77).
        participant = {row["participant_id"]: row for row in _tsv(out / "participants.tsv")}["sub-03"]
        assert [participant[key] for key in ("age", "sex", "hand")] == ["n/a", "n/a", "n/a"]
        found = {
            (needle, p.relative_to(out).as_posix())
            for p in out.rglob("*")
            if p.is_file()
            for needle in IDENTIFYING
            if needle in p.read_bytes()
        }
        assert found == set()
    else:
        assert written == source  # EDF is copied unchanged
        assert written[8:88].startswith(b"Zhang San 01-JAN-1980") and written[168:176] == b"24.08.21"
        assert acq_time.startswith("2021-08-24")
        assert fif_acq_time.startswith("2021-08-24T10:15:00")


def test_processing_steps_record_the_strip_option(identifying: Identifying) -> None:
    strip, raw, out = identifying.strip, identifying.raw, identifying.out
    steps = {
        step["parameters"]["target"]: step for step in _json(out / ".neurogrid" / "processing_steps.json")
    }
    edf_target = "sub-01/eeg/sub-01_task-rest_eeg.edf"
    eeglab_target = "sub-02/eeg/sub-02_task-rest_eeg." + ("vhdr" if strip else "set")  # A-77
    fif_target = "sub-03/eeg/sub-03_task-rest_eeg.vhdr"
    assert sorted(steps) == sorted([edf_target, eeglab_target, fif_target])
    assert steps[eeglab_target]["parameters"]["input_format"] == "EEGLAB"
    assert steps[eeglab_target]["parameters"]["output_format"] == ("VHDR" if strip else "SET")
    assert steps[fif_target]["parameters"]["input_format"] == "FIF"
    assert all(step["parameters"]["strip_identifying_headers"] is strip for step in steps.values())
    assert steps[edf_target]["input_hash"] == _files_hash([raw / "rec_named.edf"])
    assert steps[edf_target]["output_hash"] == _files_hash([out / edf_target])
    # The hashes include the file names, so the copied content is compared directly: changed only by strip.
    assert ((out / edf_target).read_bytes() == (raw / "rec_named.edf").read_bytes()) is not strip


def test_check_reports_identifying_headers_only_when_kept(identifying: Identifying) -> None:
    results = identifying.results
    failed = [f.object for f in _failed(results, "CORE-M01-05")]
    if identifying.strip:
        assert failed == []
        assert "sub-01/eeg/sub-01_task-rest_eeg.edf" in _passed(results, "CORE-M01-05")
    else:
        assert failed == ["sub-01/eeg/sub-01_task-rest_eeg.edf"]
    assert _failed(results, "BIDS-STO-001") == []


@pytest.mark.parametrize(
    ("bdf", "reserved", "recording"),
    [(False, b"", b"X"), (False, b"EDF+C", b"Startdate X X X X"), (True, b"BDF+D", b"Startdate X X X X")],
    ids=["edf", "edf-plus", "bdf-plus"],
)
def test_strip_edf_header_uses_the_edf_plus_placeholders(
    tmp_path: Path, bdf: bool, reserved: bytes, recording: bytes
) -> None:
    path = tmp_path / ("rec.bdf" if bdf else "rec.edf")
    gen_fixtures.write_edf(
        path,
        seconds=1,
        patient="MCH-0234567 F 02-MAY-1951 Haagse_Harry",
        recording="Startdate 02-MAR-2002 PSG-1234/2002 NN Telemetry03",
        startdate="02.03.02",
        bdf=bdf,
    )
    data = bytearray(path.read_bytes())
    data[192:236] = reserved.ljust(44)
    path.write_bytes(bytes(data))
    _strip_edf(path)
    stripped = path.read_bytes()
    assert stripped[8:88] == b"X X X X".ljust(80)
    assert stripped[88:168] == recording.ljust(80)
    assert stripped[168:176] == b"01.01.85"
    assert stripped[:8] == bytes(data[:8]) and stripped[176:] == bytes(data[176:])


@pytest.fixture(scope="module")
def stripped_brainvision(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, pipeline.ConvertSummary]:
    """A BrainVision recording with a name in the comment and a recording date in the marker file."""
    base = tmp_path_factory.mktemp("bv-strip")
    raw = base / "raw"
    gen_fixtures.write_brainvision(raw / "bv.vhdr", seed=12, impedances=gen_fixtures.IMPEDANCES_OK)
    header = (raw / "bv.vhdr").read_text(encoding="utf-8")
    header = header.replace("[Comment]\n", "[Comment]\nPatient: Zhang San, born 01.02.1980\n")
    (raw / "bv.vhdr").write_bytes((header + "\nRecorded at Example Hospital, room 12\n").encode("utf-8"))
    markers = (raw / "bv.vmrk").read_text(encoding="utf-8")
    assert "Mk1=New Segment,,1,1,0\n" in markers  # precondition of the replacement below
    markers = markers.replace("Mk1=New Segment,,1,1,0\n", "Mk1=New Segment,,1,1,0,20210824101500000000\n")
    (raw / "bv.vmrk").write_bytes(markers.encode("utf-8"))
    _write_config(raw, METADATA + _row("bv.vhdr", "01"))
    out = base / "bids"
    return out, pipeline.run_convert(raw, out, strip_identifying_headers=True, work_base=base)


def test_strip_keeps_only_the_impedance_block_of_the_brainvision_comment(
    stripped_brainvision: tuple[Path, pipeline.ConvertSummary],
) -> None:
    out, summary = stripped_brainvision
    assert (summary.converted, summary.validator_errors, summary.exit_code) == (1, 0, 0)
    header = (out / "sub-01" / "eeg" / "sub-01_task-rest_eeg.vhdr").read_text(encoding="utf-8")
    comment = header.split("[Comment]\n", 1)[1].splitlines()
    assert comment == ["Impedance [kOhm] at 00:00:00 :", *(f"{label}: 3" for label in EEG_NAMES)]
    assert "Zhang" not in header and "1980" not in header and "Hospital" not in header
    assert "DataFile=sub-01_task-rest_eeg.eeg" in header.splitlines()
    assert _tsv(out / "sub-01" / "sub-01_scans.tsv")[0]["acq_time"] == "n/a"
    step = _json(out / ".neurogrid" / "processing_steps.json")[0]
    assert step["parameters"]["strip_identifying_headers"] is True


def test_strip_zeroes_the_brainvision_segment_date(
    stripped_brainvision: tuple[Path, pipeline.ConvertSummary], tmp_path: Path
) -> None:
    out, _summary = stripped_brainvision
    markers = (out / "sub-01" / "eeg" / "sub-01_task-rest_eeg.vmrk").read_text(encoding="utf-8")
    assert "Mk1=New Segment,,1,1,0,00000000000000000000" in markers.splitlines()
    assert "20210824" not in markers
    assert _failed(_check(out, tmp_path), "CORE-M01-05") == []


# --- skipped recordings, undocumented fields, exit 1 -------------------------------------------------------


def _annotation_only_edf(path: Path) -> Path:
    """An EDF+C file with only the 'EDF Annotations' signal, like a hypnogram."""
    spr = 60
    tal = b"+0\x14\x14\x00+0\x1530\x14Sleep stage W\x14\x00"
    header = bytearray()
    header += b"0".ljust(8) + b"X X X X".ljust(80) + b"Startdate X X X X".ljust(80)
    header += b"01.01.85" + b"00.00.00" + b"512".ljust(8) + b"EDF+C".ljust(44)
    header += b"1".ljust(8) + b"0".ljust(8) + b"1".ljust(4)
    header += b"EDF Annotations".ljust(16) + b"".ljust(80) + b"".ljust(8)
    header += b"-1".ljust(8) + b"1".ljust(8) + b"-32768".ljust(8) + b"32767".ljust(8)
    header += b"".ljust(80) + str(spr).encode().ljust(8) + b"".ljust(32)
    path.write_bytes(bytes(header) + tal.ljust(2 * spr, b"\x00"))
    return path


def test_cli_skipped_recordings_and_undocumented_fields_end_with_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / NAME
    _edf_pair(raw)
    for name in ("rec.vhdr", "rec.vmrk"):  # a header without its .eeg data file
        _copy(FIX / "brainvision_missing" / name, raw / name)
    _copy(FIX / "unsupported" / "legacy.cnt", raw / "legacy.cnt")
    (raw / "broken.edf").write_bytes(b"not an EDF header")
    _annotation_only_edf(raw / "qx_scoring.edf")
    config = tmp_path / "convert.toml"  # nothing under [metadata.defaults] is documented
    config.write_text(
        _row("rec_a.edf", "01")
        + _row("rec_b.edf", "05")
        + _row("rec.vhdr", "02")
        + _row("broken.edf", "03")
        + _row("qx_scoring.edf", "04", "sleep"),
        encoding="utf-8",
    )
    out = tmp_path / "bids"
    seen: list[tuple[pipeline.ConvertSummary, dict[str, Any]]] = []
    original = pipeline.run_convert

    def spy(*args: Any, **kwargs: Any) -> pipeline.ConvertSummary:
        summary = original(*args, **kwargs)
        seen.append((summary, kwargs))
        return summary

    monkeypatch.setattr(pipeline, "run_convert", spy)
    code, stdout, stderr = _run(
        ["convert", str(raw), "--to", "bids", "--out", str(out), "--config", str(config)], capsys
    )

    assert code == 1, stderr
    [(summary, kwargs)] = seen
    assert kwargs["work_base"] == out.absolute().parent  # the work folder lies next to the output (A-54)
    ids = {
        name: pseudonym(PurePosixPath(name))
        for name in ("legacy.cnt", "broken.edf", "qx_scoring.edf", "rec.vhdr")
    }
    assert summary.converted == 2
    assert summary.skipped == [
        (ids["legacy.cnt"], "format.unsupported"),
        (ids["broken.edf"], "read.failed"),
        (ids["qx_scoring.edf"], "recording.annotations_only"),
        (ids["rec.vhdr"], "convert.companion"),  # the .eeg named in the header is missing (M01-03, A-77)
    ]
    assert summary.name_missing  # no [dataset] name: written as n/a and listed
    # Counted per recording, over both converted recordings.
    assert summary.missing_fields == {"EEGReference": 2, "PowerLineFrequency": 2, "SoftwareFilters": 2}
    assert summary.validator_errors == 0 and summary.exit_code == 1

    lines = stdout.splitlines()
    assert lines[:10] == [
        "Converted recordings: 2",
        f"Not converted: {ids['legacy.cnt']} – Data file in a format NeuroGrid cannot read.",
        f"Not converted: {ids['broken.edf']} – The data could not be read.",
        f"Not converted: {ids['qx_scoring.edf']} – Annotations only (e.g. a hypnogram); no signal channels.",
        f"Not converted: {ids['rec.vhdr']} – A companion file is missing or its reference is not usable "
        "(CORE-M01-03); not converted.",
        "Not documented, written as n/a: EEGReference (2 recording(s)); see M02 in 'check'.",
        "Not documented, written as n/a: PowerLineFrequency (2 recording(s)); see M02 in 'check'.",
        # n/a documents SoftwareFilters in BIDS (A-03): no M02 finding is promised for it
        "Not documented, written as n/a: SoftwareFilters (2 recording(s)); BIDS accepts n/a for this field, "
        "so 'check' does not report it.",
        "Not documented, written as n/a: Name in dataset_description.json; set [dataset] name in "
        "neurogrid.toml.",
        f"BIDS validator on the output: 0 error(s), {summary.validator_warnings} warning(s)",
    ]
    assert summary.validator_warnings > 0  # the validator really ran (recommended fields are missing)
    assert lines[10].startswith("BIDS dataset written to ") and lines[10].endswith("bids")
    assert lines[11:] == [DISCLAIMER]
    printed = stdout + stderr
    for secret in (NAME, str(raw), "rec_a", "rec_b", "broken", "qx_scoring", "legacy", str(Path.home())):
        assert secret not in printed, secret

    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [NAME, "bids", "convert.toml"]
    )  # no work folder
    for subject in ("01", "05"):
        sidecar = _json(out / f"sub-{subject}" / "eeg" / f"sub-{subject}_task-rest_eeg.json")
        values = [sidecar[key] for key in ("EEGReference", "PowerLineFrequency", "SoftwareFilters")]
        assert values == ["n/a"] * 3
    results = _check(out, tmp_path)
    # n/a is valid documentation only for SoftwareFilters (A-03); the other two are reported by M02.
    assert sorted((f.object, f.subkey) for f in _failed(results, "CORE-M02-01")) == [
        (f"sub-{subject}/eeg/sub-{subject}_task-rest_eeg.edf", key)
        for subject in ("01", "05")
        for key in ("EEGReference", "PowerLineFrequency")
    ]
    assert _failed(results, "BIDS-STO-001") == []


def test_only_unreadable_recordings_write_no_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    raw = tmp_path / "raw"
    for name in ("rec.vhdr", "rec.vmrk"):
        _copy(FIX / "brainvision_missing" / name, raw / name)
    locked = raw / "Zhang_San"  # a folder that cannot be listed: its contents are not converted (A-12)
    _copy(FIX / "edf_ok" / "rec_a.edf", locked / "rec_a.edf")
    _write_config(raw, METADATA + _row("rec.vhdr", "01"))
    real_scandir = os.scandir

    def scandir(path: Any = ".") -> Any:
        if Path(str(path)).resolve() == locked.resolve():
            raise PermissionError(13, "denied", str(path))
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", scandir)
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, work_base=tmp_path)
    assert summary.converted == 0
    assert summary.skipped == [
        (pseudonym(PurePosixPath("Zhang_San")), "read.failed"),
        (pseudonym(PurePosixPath("rec.vhdr")), "convert.companion"),
    ]
    assert (summary.validator_errors, summary.validator_warnings, summary.exit_code) == (0, 0, 1)
    assert not summary.name_missing
    assert not out.exists()  # nothing converted: no output that could pass for a BIDS dataset (A-77)


def test_validator_errors_end_with_exit_1(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _bdf(raw)
    # A documented value that is not valid BIDS (SoftwareFilters must be an object or n/a).
    _write_config(
        raw,
        '[metadata.defaults]\nreference = "Cz"\nline_frequency_hz = 50\nsoftware_filters = "none"\n'
        + _row("rec.bdf", "01"),
    )
    summary = pipeline.run_convert(raw, tmp_path / "bids", work_base=tmp_path)
    assert summary.converted == 1 and summary.skipped == []
    assert summary.validator_errors > 0 and summary.exit_code == 1
    sidecar = _json(tmp_path / "bids" / "sub-01" / "eeg" / "sub-01_task-rest_eeg.json")
    assert sidecar["SoftwareFilters"] == "none"


def test_convert_summary_exit_code() -> None:
    def summary(skipped: list[tuple[str, str]], errors: int, converted: int = 1) -> pipeline.ConvertSummary:
        return pipeline.ConvertSummary(
            converted=converted,
            skipped=skipped,
            missing_fields={},
            name_missing=True,  # a missing name is reported, but does not change the exit code
            validator_errors=errors,
            validator_warnings=7,
            steps_file=Path("steps.json"),
        )

    assert summary([], 0).exit_code == 0
    assert summary([("rec-00000000", "read.failed")], 0).exit_code == 1
    assert summary([], 1).exit_code == 1
    assert summary([], 0, converted=0).exit_code == 1  # nothing converted is no success (A-77)


@pytest.mark.parametrize("folder", ["edf_truncated", "bdf_truncated", "brainvision_truncated"])
def test_truncated_input_is_not_converted(folder: str, tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _copy_folder(FIX / folder, raw)
    main_file = next(p.name for p in sorted(raw.iterdir()) if p.suffix in (".edf", ".bdf", ".vhdr"))
    _write_config(raw, METADATA + _row(main_file, "01"))
    summary = pipeline.run_convert(raw, tmp_path / "bids", work_base=tmp_path)
    assert summary.converted == 0 and len(summary.skipped) == 1 and summary.exit_code == 1


def test_eeglab_with_embedded_data_is_converted(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _copy_folder(FIX / "eeglab_embedded", raw)
    _write_config(raw, METADATA + _row("rec.set", "01"))
    summary = pipeline.run_convert(raw, tmp_path / "bids", work_base=tmp_path)
    assert (summary.converted, summary.skipped, summary.validator_errors, summary.exit_code) == (1, [], 0, 0)


def test_epoched_eeglab_does_not_abort_the_conversion(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _copy(FIX / "edf_ok" / "rec_a.edf", raw / "rec_a.edf")
    _epoched_eeglab(raw / "epochs.set")
    _write_config(raw, METADATA + _row("rec_a.edf", "01") + _row("epochs.set", "02"))
    summary = pipeline.run_convert(raw, tmp_path / "bids", work_base=tmp_path)
    assert summary.converted + len(summary.skipped) == 2
    assert (tmp_path / "bids" / "sub-01" / "eeg" / "sub-01_task-rest_eeg.edf").is_file()
    assert summary.exit_code == (1 if summary.skipped else 0)


def test_folder_without_recordings_is_not_a_successful_conversion(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _copy(FIX / "empty" / "README.txt", raw / "README.txt")
    summary = pipeline.run_convert(raw, tmp_path / "bids", work_base=tmp_path)
    assert summary.converted == 0
    assert summary.exit_code != 0


# --- mapping (A-05) ----------------------------------------------------------------------------------------


def test_missing_mapping_writes_a_template_and_no_output(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _edf_pair(raw)
    _copy(FIX / "edf_ok" / "rec_a.edf", raw / "session1" / "rec_c.edf")
    _write_config(raw, METADATA + _row("rec_a.edf", "01"))  # rec_b.edf and session1/rec_c.edf unmapped
    out = tmp_path / "bids"
    with pytest.raises(InputError) as info:
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert info.value.message_key == "convert.mapping_missing"
    assert info.value.params == {"count": 2, "template": "mapping-template.toml"}
    assert not out.exists()
    data = (raw / ".neurogrid" / "mapping-template.toml").read_bytes()
    assert b"\r\n" not in data and data.startswith(b"# NeuroGrid mapping template")
    text = data.decode("utf-8")
    assert tomllib.loads(text)["convert"]["files"] == [
        {"path": "rec_b.edf", "subject": "", "task": ""},
        {"path": "session1/rec_c.edf", "subject": "", "task": ""},
    ]
    with pytest.raises(ConfigError):  # an unfilled template is no silent mapping
        parse_config(text)
    filled = text.replace('subject = ""', 'subject = "02"', 1).replace('subject = ""', 'subject = "03"', 1)
    cfg = parse_config(filled.replace('task = ""', 'task = "rest"'))
    assert [(row.path, row.subject, row.task) for row in cfg.convert.files] == [
        ("rec_b.edf", "02", "rest"),
        ("session1/rec_c.edf", "03", "rest"),
    ]


def test_missing_mapping_of_a_single_file_lists_only_that_file(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _edf_pair(raw)
    with pytest.raises(InputError) as info:
        pipeline.run_convert(raw / "rec_b.edf", tmp_path / "bids", work_base=tmp_path)
    assert info.value.message_key == "convert.mapping_missing" and info.value.params["count"] == 1
    rows = tomllib.loads((raw / ".neurogrid" / "mapping-template.toml").read_text(encoding="utf-8"))
    assert [row["path"] for row in rows["convert"]["files"]] == ["rec_b.edf"]


def test_mapping_template_quotes_every_name(tmp_path: Path) -> None:
    names = ['a "quoted" name.edf', "back\\slash.edf", "张三 rest.edf", "tab\there.edf", "sub/Ö.vhdr"]
    items = [
        FoundFile(
            relative=PurePosixPath(name),
            display_id=pseudonym(PurePosixPath(name)),
            suffix=".edf",
            size_bytes=1,
        )
        for name in names
    ]
    template = write_mapping_template(tmp_path, items)
    assert template == tmp_path / ".neurogrid" / "mapping-template.toml"
    rows = tomllib.loads(template.read_text(encoding="utf-8"))["convert"]["files"]
    assert [row["path"] for row in rows] == names


def _record_targets(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, str]]]:
    """Replaces the conversion of each recording by a stand-in that only records its BIDS entities."""
    import neurogrid.convert as convert_module

    seen: list[tuple[str, dict[str, str]]] = []

    def record(root: Path, output: Path, item: FoundFile, entities: dict[str, str], *args: Any) -> None:
        seen.append((item.relative.as_posix(), entities))

    monkeypatch.setattr(convert_module, "_convert_one", record)
    return seen


def test_recordings_that_differ_in_session_or_run_are_distinct_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "raw"
    _edf_pair(raw)
    _copy(FIX / "edf_ok" / "rec_a.edf", raw / "s2" / "rec_c.edf")
    _write_config(
        raw,
        METADATA
        + _row("rec_a.edf", "01", run="1")
        + _row("rec_b.edf", "01", run="2")
        + _row("s2/rec_c.edf", "01", session="2", run="1"),
    )
    seen = _record_targets(monkeypatch)
    summary = pipeline.run_convert(raw, tmp_path / "bids", work_base=tmp_path)
    assert sorted(seen) == [
        ("rec_a.edf", {"subject": "01", "task": "rest", "run": "1"}),
        ("rec_b.edf", {"subject": "01", "task": "rest", "run": "2"}),
        ("s2/rec_c.edf", {"subject": "01", "session": "2", "task": "rest", "run": "1"}),
    ]
    assert summary.converted == 0  # the stand-in converts nothing, so the validator does not run
    assert not (raw / ".neurogrid" / "mapping-template.toml").exists()


def test_same_session_task_and_run_is_a_duplicate_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "raw"
    _edf_pair(raw)
    _write_config(
        raw,
        METADATA
        + _row("rec_a.edf", "07", session="2", run="3")
        + _row("rec_b.edf", "07", session="2", run="3"),
    )
    seen = _record_targets(monkeypatch)
    out = tmp_path / "bids"
    with pytest.raises(InputError) as info:
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert info.value.message_key == "convert.duplicate_target"
    assert info.value.params == {"subject": "07", "task": "rest"}
    assert seen == [] and not out.exists()


# --- tool errors (exit 2) -----------------------------------------------------------------------------------


def test_input_that_is_already_bids_is_refused(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    shutil.copytree(FIX / "bids_ok", raw)
    out = tmp_path / "bids"
    with pytest.raises(InputError) as info:
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert info.value.message_key == "convert.already_bids"
    assert not out.exists() and not (raw / ".neurogrid").exists()


def test_output_that_is_not_empty_is_refused_and_kept(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _mapped_edf_pair(raw)
    out = tmp_path / "bids"
    out.mkdir()
    (out / "keep.txt").write_text("results of somebody else", encoding="utf-8")
    with pytest.raises(InputError) as info:
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert info.value.message_key == "convert.output_not_empty"
    assert [p.name for p in out.iterdir()] == ["keep.txt"]
    assert (out / "keep.txt").read_text(encoding="utf-8") == "results of somebody else"


@pytest.mark.parametrize("inside", ["bids", ".neurogrid/bids"])
def test_output_inside_the_input_is_refused(tmp_path: Path, inside: str) -> None:
    raw = tmp_path / "raw"
    _mapped_edf_pair(raw)
    out = raw / inside
    with pytest.raises(InputError) as info:
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert info.value.message_key == "convert.output_inside_input"
    assert not out.exists()


def test_two_files_with_the_same_target_are_refused(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _mapped_edf_pair(raw, "01", "01")
    out = tmp_path / "bids"
    with pytest.raises(InputError) as info:
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert info.value.message_key == "convert.duplicate_target"
    assert info.value.params == {"subject": "01", "task": "rest"}
    assert not out.exists() and not (raw / ".neurogrid" / "mapping-template.toml").exists()


def _failing_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    """The first recording fails after it has written part of the output."""
    import neurogrid.convert as convert_module

    def fail(root: Path, output: Path, *args: Any) -> None:
        (output / "sub-01").mkdir()
        (output / "sub-01" / "partial.edf").write_bytes(b"partly written")
        raise RuntimeError("disk full")

    monkeypatch.setattr(convert_module, "_convert_one", fail)


def test_failure_removes_a_newly_created_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = tmp_path / "raw"
    _mapped_edf_pair(raw)
    _failing_conversion(monkeypatch)
    out = tmp_path / "bids"
    with pytest.raises(RuntimeError):
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert not out.exists()


def test_failure_keeps_an_existing_output_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = tmp_path / "raw"
    _mapped_edf_pair(raw)
    _failing_conversion(monkeypatch)
    out = tmp_path / "bids"
    out.mkdir()
    with pytest.raises(RuntimeError):
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert out.is_dir()  # the operator's folder is not deleted


def test_failure_leaves_an_existing_output_folder_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "raw"
    _mapped_edf_pair(raw)
    _failing_conversion(monkeypatch)
    out = tmp_path / "bids"
    out.mkdir()
    with pytest.raises(RuntimeError):
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert list(out.iterdir()) == []


def test_output_path_that_is_a_file_is_a_tool_error_and_the_file_is_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    _mapped_edf_pair(raw)
    blocker = tmp_path / "bids"
    blocker.write_text("not a folder", encoding="utf-8")
    code, stdout, _stderr = _run(["convert", str(raw), "--to", "bids", "--out", str(blocker)], capsys)
    assert code == 2 and stdout == ""
    assert blocker.read_text(encoding="utf-8") == "not a folder"


def test_output_path_that_is_a_file_has_a_clear_message(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _mapped_edf_pair(raw)
    blocker = tmp_path / "bids"
    blocker.write_text("not a folder", encoding="utf-8")
    with pytest.raises(NeuroGridError):
        pipeline.run_convert(raw, blocker, work_base=tmp_path)


# --- command line (CLI-02, NG-F14) -------------------------------------------------------------------------


def test_cli_converts_a_single_file_with_exit_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    raw = tmp_path / NAME
    _brainvision(raw)
    _copy(FIX / "edf_ok" / "rec_a.edf", raw / "rec_a.edf")  # not mapped: ignored when one file is given
    config = tmp_path / "convert.toml"
    config.write_text(METADATA + _row("rec.vhdr", "01"), encoding="utf-8")
    out = tmp_path / "bids"
    code, stdout, stderr = _run(
        ["convert", str(raw / "rec.vhdr"), "--to", " BIDS ", "--out", str(out), "--config", str(config)],
        capsys,
    )
    assert code == 0, stderr
    lines = stdout.splitlines()
    assert lines[0] == "Converted recordings: 1"
    assert lines[1] == (
        "Not documented, written as n/a: Name in dataset_description.json; "
        "set [dataset] name in neurogrid.toml."
    )
    assert re.fullmatch(r"BIDS validator on the output: 0 error\(s\), \d+ warning\(s\)", lines[2])
    assert lines[3].startswith("BIDS dataset written to ") and lines[3].endswith("bids")
    assert lines[4:] == [DISCLAIMER]
    assert NAME not in stdout + stderr and str(Path.home()) not in stdout + stderr
    data_files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*_eeg.*") if p.suffix != ".json")
    assert data_files == [f"sub-01/eeg/sub-01_task-rest_eeg.{ext}" for ext in ("eeg", "vhdr", "vmrk")]
    assert not (raw / ".neurogrid").exists()  # no mapping template for the file that was not given
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([NAME, "bids", "convert.toml"])


def _stand_in(
    monkeypatch: pytest.MonkeyPatch, summary: pipeline.ConvertSummary
) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
    """Replaces pipeline.run_convert by a stand-in that records its arguments and returns ``summary``."""
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def fake(*args: Any, **kwargs: Any) -> pipeline.ConvertSummary:
        calls.append((args, kwargs))
        return summary

    monkeypatch.setattr(pipeline, "run_convert", fake)
    return calls


def test_cli_passes_strip_and_config_to_the_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    config = tmp_path / "convert.toml"
    config.write_text(METADATA, encoding="utf-8")
    out = tmp_path / "bids"
    done = pipeline.ConvertSummary(
        converted=1,
        skipped=[],
        missing_fields={},
        name_missing=False,
        validator_errors=0,
        validator_warnings=0,
        steps_file=out / ".neurogrid" / "processing_steps.json",
    )
    calls = _stand_in(monkeypatch, done)
    base = ["convert", str(raw), "--to", "bids", "--out", str(out)]
    assert _run([*base, "--strip-identifying-headers", "--config", str(config)], capsys)[0] == 0
    assert _run(base, capsys)[0] == 0
    [(args_strip, kwargs_strip), (args_keep, kwargs_keep)] = calls
    assert args_strip == (str(raw), out) and args_keep == (str(raw), out)
    assert kwargs_strip == {
        "config_path": config,
        "strip_identifying_headers": True,
        "work_base": out.absolute().parent,
    }
    assert kwargs_keep == {
        "config_path": None,
        "strip_identifying_headers": False,
        "work_base": out.absolute().parent,
    }


def test_cli_convert_lines_in_chinese_without_control_characters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    out = tmp_path / "bids"
    summary = pipeline.ConvertSummary(
        converted=2,
        skipped=[
            ("rec-0a1b2c3d\x1b[2J\x07", "format.unsupported"),  # control characters are dropped (A-53)
            ("rec-00000001", "read.failed"),
            ("rec-00000002", "recording.annotations_only"),
        ],
        missing_fields={"EEGReference": 2, "PowerLineFrequency": 1},
        name_missing=True,
        validator_errors=0,
        validator_warnings=3,
        steps_file=out / ".neurogrid" / "processing_steps.json",
    )
    _stand_in(monkeypatch, summary)
    code, stdout, stderr = _run(
        ["--lang", "zh", "convert", str(raw), "--to", "bids", "--out", str(out)], capsys
    )
    assert code == 1 and stderr == ""
    lines = stdout.splitlines()
    assert lines[:8] == [
        "已转换的记录：2",
        "未转换：rec-0a1b2c3d[2J – NeuroGrid 无法读取该格式的数据文件。",
        "未转换：rec-00000001 – 无法读取数据。",
        "未转换：rec-00000002 – 仅含标注（如睡眠分期图），无信号通道。",
        "未记录，已写为 n/a：EEGReference（2 条记录）；见 'check' 中的 M02。",
        "未记录，已写为 n/a：PowerLineFrequency（1 条记录）；见 'check' 中的 M02。",
        "未记录，已写为 n/a：dataset_description.json 中的 Name；"
        "请在 neurogrid.toml 的 [dataset] 中设置 name。",
        "对输出运行 BIDS 验证器：0 个错误，3 个警告",
    ]
    assert lines[8].startswith("BIDS 数据集已写入 ") and lines[8].endswith("bids")
    assert lines[9:] == [
        "使用 NeuroGrid 进行的预检。不构成国家药品监督管理局（NMPA）法规意义上的符合性评价。"
    ]
    assert "\x1b" not in stdout and "\x07" not in stdout


def _cli_case(tmp_path: Path, case: str) -> tuple[list[str], str]:
    """Arguments and the expected error text of one tool error."""
    raw = tmp_path / NAME
    out = tmp_path / "bids"
    if case == "already_bids":
        shutil.copytree(FIX / "bids_ok", raw)
        return [str(raw), "--to", "bids", "--out", str(out)], "Error: The input is already a BIDS dataset."
    _edf_pair(raw)
    if case == "mapping_missing":
        return [str(raw), "--to", "bids", "--out", str(out)], (
            "Error: 2 data file(s) have no subject/task mapping; a template was written to "
            ".neurogrid/mapping-template.toml."
        )
    if case == "target_unavailable":
        return [str(raw), "--to", "gbt47127", "--out", str(out)], (
            "Error: Conversion target 'gbt47127' is not available in this version (bids)."
        )
    if case == "duplicate_target":
        _write_config(raw, METADATA + _row("rec_a.edf", "07") + _row("rec_b.edf", "07"))
        return [str(raw), "--to", "bids", "--out", str(out)], (
            "Error: Two files map to the same BIDS recording (subject 07, task rest)."
        )
    _write_config(raw, METADATA + _row("rec_a.edf", "01") + _row("rec_b.edf", "02"))
    if case == "output_not_empty":
        out.mkdir()
        (out / "keep.txt").write_text("x", encoding="utf-8")
        return [str(raw), "--to", "bids", "--out", str(out)], "Error: The output folder is not empty."
    assert case == "output_inside_input"
    return [str(raw), "--to", "bids", "--out", str(raw / "bids")], (
        "Error: The output folder must not lie inside the input folder."
    )


@pytest.mark.parametrize(
    "case",
    [
        "mapping_missing",
        "target_unavailable",
        "already_bids",
        "output_not_empty",
        "output_inside_input",
        "duplicate_target",
    ],
)
def test_cli_tool_errors_end_with_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    args, message = _cli_case(tmp_path, case)
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    code, stdout, stderr = _run(["convert", *args], capsys)
    assert code == 2 and stdout == ""
    assert stderr.strip() == message
    assert NAME not in stderr and "Traceback" not in stderr
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    if case == "mapping_missing":  # the template is the only thing written, inside the input folder
        assert after == sorted([*before, f"{NAME}/.neurogrid", f"{NAME}/.neurogrid/mapping-template.toml"])
    else:
        assert after == before  # nothing is written, nothing is removed


def test_cli_validator_path_with_comma_is_a_tool_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    _bdf(raw)
    _write_config(raw, METADATA + _row("rec.bdf", "01"))
    code, stdout, stderr = _run(["convert", str(raw), "--to", "bids", "--out", str(tmp_path / "a,b")], capsys)
    assert code == 2 and stdout == ""
    assert (
        stderr.strip()
        == "Error: Paths with a comma cannot be validated (deno permission lists); please rename."
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["raw"]  # refused before anything is written


def test_edf_plus_d_keeps_its_time_structure(tmp_path: Path) -> None:
    """MNE-BIDS takes EDF over as a file copy, so the record onsets of EDF+D stay (A-05, A-77)."""
    raw = tmp_path / "raw"
    source = _copy(FIX / "edf_plus_d" / "rec.edf", raw / "rec.edf")
    _write_config(raw, METADATA + _row("rec.edf", "01"))
    summary = pipeline.run_convert(raw, tmp_path / "bids", work_base=tmp_path)
    assert (summary.converted, summary.skipped, summary.validator_errors) == (1, [], 0)
    written = (tmp_path / "bids" / "sub-01" / "eeg" / "sub-01_task-rest_eeg.edf").read_bytes()
    original = source.read_bytes()
    assert written[192:197] == b"EDF+D"
    header_bytes = int(original[184:192])
    assert written[header_bytes:] == original[header_bytes:]  # data records with their onsets unchanged
    results = _check(tmp_path / "bids", tmp_path)
    for rule in ("CORE-M01-01", "CORE-M01-02", "CORE-M01-03", "BIDS-STO-001"):
        assert _failed(results, rule) == [], rule
