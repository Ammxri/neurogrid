"""BIDS sidecars, metadata from all sources and the mapping of raw folders (NG-F06, CLI-01, M01, M02, A-03,
A-04, A-05, A-46, A-52, A-66, A-67, A-72, A-74, A-75, A-76, A-77).

Covers the inheritance principle of BIDS sidecars (io/bids.py), the precedence neurogrid.toml > sidecar >
header with the recorded source per field (metadata.py), the validation of ``[convert]`` and ``[metadata]``
in neurogrid.toml (config.py), companion, split and calibration files in discovery (io/discover.py) and the
metadata attached to each recording of a check run (checks/context.py).
"""

from __future__ import annotations

import json
import shutil
import warnings
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

import gen_fixtures  # type: ignore[import-not-found]
from conftest import DOCUMENTED_TOML, dir_link  # type: ignore[import-not-found]
from neurogrid import config as config_module
from neurogrid import pipeline
from neurogrid.checks import context as context_module
from neurogrid.checks.context import CheckContext, RecordingState
from neurogrid.config import Config, parse, parse_bytes
from neurogrid.io import ADAPTERS, bids
from neurogrid.io.base import HeaderInspection, HeaderUnreadable
from neurogrid.io.discover import FoundFile, pseudonym, scan
from neurogrid.io.edf import EdfAdapter
from neurogrid.kernel.errors import ConfigError
from neurogrid.kernel.findings import Status
from neurogrid.metadata import Documented, RecordingMetadata, entities_for, mapped_entities
from neurogrid.model.dataset import Recording

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
BIDS_EDF = FIX / "bids_ok" / "sub-01" / "eeg" / "sub-01_task-rest_eeg.edf"  # 8 EEG channels, 512 Hz, uV
DATA = "sub-01/eeg/sub-01_task-rest_eeg.edf"
LABELS = gen_fixtures.EEG_LABELS
ALL_SIDECAR = {"name": "sidecar", "type": "sidecar", "units": "sidecar"}
ALL_HEADER = {"name": "header", "type": "header", "units": "header"}
RAW_TOML = (
    '[metadata.defaults]\nreference = "Cz"\nline_frequency_hz = 50\nsoftware_filters = "n/a"\n'
    'electrode_type = "wet"\n'
)
# subject and task from the file name, run optional; the expression is matched against the relative path
# first and then against the file name (A-05)
PATTERN = "[convert]\npattern = '(?P<subject>[A-Za-z0-9]+)_(?P<task>[a-z]+)(?:_(?P<run>[0-9]+))?\\.edf'\n"


# --- helpers ----------------------------------------------------------------------------------------------


def _write(path: Path, content: str | bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return path


def _write_json(path: Path, data: object) -> Path:
    return _write(path, json.dumps(data))


def _bids_root(root: Path, sidecar: dict[str, Any] | None = None, data: str = DATA) -> Path:
    """A minimal BIDS dataset with the EDF of bids_ok at ``data`` and an optional sidecar next to it."""
    _write_json(root / "dataset_description.json", {"Name": "test", "BIDSVersion": "1.11.1"})
    target = root / data
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BIDS_EDF, target)
    if sidecar is not None:
        _write_json(target.with_suffix(".json"), sidecar)
    return root


def _state(root: Path, cfg: Config | None = None, relative: str | None = None) -> RecordingState:
    ctx = CheckContext.build(scan(root), cfg or Config())
    if relative is None:
        assert len(ctx.recordings) == 1
        return ctx.recordings[0]
    return next(s for s in ctx.recordings if s.found.relative.as_posix() == relative)


def _recording(state: RecordingState) -> Recording:
    assert state.recording is not None, state.header_error
    return state.recording


def _fields(meta: RecordingMetadata) -> dict[str, tuple[Any, str]]:
    return {name: (doc.value, doc.source) for name, doc in meta.fields.items()}


def _entities(meta: RecordingMetadata) -> dict[str, tuple[Any, str]]:
    return {name: (doc.value, doc.source) for name, doc in meta.entities.items()}


def _found(relative: str, entities: tuple[tuple[str, str], ...] = ()) -> FoundFile:
    path = PurePosixPath(relative)
    return FoundFile(
        relative=path, display_id=pseudonym(path), suffix=path.suffix.lower(), size_bytes=0, entities=entities
    )


def _names(files: list[FoundFile]) -> list[str]:
    return sorted(f.relative.as_posix() for f in files)


def _write_fif(path: Path, line_freq: float | None) -> Path:
    """A small FIF raw file with two EEG channels at 256 Hz and the given power line frequency."""
    import mne
    import numpy as np

    info = mne.create_info(["Fz", "Cz"], 256.0, "eeg")
    info["line_freq"] = line_freq
    raw = mne.io.RawArray(np.zeros((2, 512)), info, verbose="error")
    path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw.save(path, overwrite=True, verbose="error")
    return path


def _mixed_rate_edf(path: Path) -> Path:
    """Plain EDF, 2 records of 1 s: 'EEG Fz' at 512 Hz and 'ECG' at 256 Hz."""
    rates = (512, 256)
    header = bytearray()
    header += b"0".ljust(8) + b"X X X X".ljust(80) + b"Startdate X X X X".ljust(80)
    header += b"01.01.85" + b"00.00.00" + str(256 * 3).encode().ljust(8) + b"".ljust(44)
    header += b"2".ljust(8) + b"1".ljust(8) + b"2".ljust(4)
    header += b"EEG Fz".ljust(16) + b"ECG".ljust(16)
    header += b"".ljust(80) * 2 + b"uV".ljust(8) * 2
    header += b"-500".ljust(8) * 2 + b"500".ljust(8) * 2 + b"-32768".ljust(8) * 2 + b"32767".ljust(8) * 2
    header += b"".ljust(80) * 2 + b"".join(str(r).encode().ljust(8) for r in rates) + b"".ljust(32) * 2
    record = b"".join(b"\x00\x00" * r for r in rates)
    return _write(path, bytes(header) + record * 2)


# --- io/bids.py: names, inheritance principle, JSON and TSV -----------------------------------------------


@pytest.mark.parametrize(
    ("name", "entities", "suffix", "extension"),
    [
        (
            "sub-01_ses-a_task-rest_run-1_eeg.edf",
            {"sub": "01", "ses": "a", "task": "rest", "run": "1"},
            "eeg",
            ".edf",
        ),
        ("task-rest_eeg.JSON", {"task": "rest"}, "eeg", ".json"),
        ("participants.tsv", {}, "participants", ".tsv"),
        ("sub-01_T1w.nii.gz", {"sub": "01"}, "T1w", ".nii.gz"),
    ],
)
def test_parse_name(name: str, entities: dict[str, str], suffix: str, extension: str) -> None:
    assert bids.parse_name(name) == bids.BidsName(entities=entities, suffix=suffix, extension=extension)


@pytest.mark.parametrize(
    "name",
    [
        "README",  # no extension
        "sub-01_task-rest_eeg",  # no extension
        "sub-01_rest_eeg.json",  # a part that is no key-value pair
        "Sub-01_eeg.json",  # keys are lower case
        "sub-_eeg.json",  # empty label
        "sub-01_task-re-st_eeg.json",  # label not alphanumeric
        "sub-01_task-rest_e-eg.json",  # suffix not alphanumeric
        "_eeg.json",
    ],
)
def test_parse_name_rejects_non_bids_names(name: str) -> None:
    assert bids.parse_name(name) is None


SESSION_DATA = PurePosixPath("sub-01/ses-a/eeg/sub-01_ses-a_task-rest_run-1_eeg.edf")
APPLICABLE = [
    "task-rest_eeg.json",
    "sub-01/sub-01_task-rest_eeg.json",
    "sub-01/ses-a/sub-01_ses-a_task-rest_eeg.json",
    "sub-01/ses-a/eeg/sub-01_ses-a_task-rest_run-1_eeg.json",
]


def _inheritance_tree(root: Path) -> Path:
    """Sidecars on the dataset, subject, session and data level, plus sidecars that do not apply."""
    _write_json(root / "dataset_description.json", {"Name": "test", "BIDSVersion": "1.11.1"})
    _write_json(
        root / "task-rest_eeg.json", {"TaskName": "rest", "EEGReference": "dataset", "PowerLineFrequency": 50}
    )
    _write_json(root / "sub-01/sub-01_task-rest_eeg.json", {"EEGReference": "subject", "Manufacturer": "S"})
    _write_json(
        root / "sub-01/ses-a/sub-01_ses-a_task-rest_eeg.json",
        {"EEGReference": "session", "SoftwareFilters": "n/a"},
    )
    _write_json(root / "sub-01/ses-a/eeg/sub-01_ses-a_task-rest_run-1_eeg.json", {"SamplingFrequency": 512})
    # Not applicable: an extra entity, another task, another run, another suffix, another extension, a folder
    # that is no ancestor, a name that does not follow BIDS, and a folder with a sidecar name.
    _write_json(root / "task-rest_acq-high_eeg.json", {"EEGReference": "extra entity"})
    _write_json(root / "task-other_eeg.json", {"EEGReference": "other task"})
    _write_json(root / "sub-01/ses-a/eeg/sub-01_ses-a_task-rest_run-2_eeg.json", {"EEGReference": "run 2"})
    _write_json(root / "task-rest_ieeg.json", {"EEGReference": "other suffix"})
    _write(root / "task-rest_eeg.tsv", "EEGReference\nother extension\n")
    _write_json(root / "sub-02/task-rest_eeg.json", {"EEGReference": "other subject"})
    _write_json(root / "notes_eeg.json", {"EEGReference": "not a BIDS name"})
    (root / "sub-01" / "task-rest_eeg.json").mkdir()
    shutil.copyfile(BIDS_EDF, root / SESSION_DATA)
    return root


def test_applicable_follows_the_inheritance_principle(tmp_path: Path) -> None:
    root = _inheritance_tree(tmp_path)
    found = bids.applicable(root, SESSION_DATA, "eeg", ".json")
    assert [path.relative_to(root).as_posix() for path in found] == APPLICABLE


def test_merged_json_lets_the_nearest_sidecar_win(tmp_path: Path) -> None:
    merged, has_sidecar = bids.merged_json(_inheritance_tree(tmp_path), SESSION_DATA, "eeg")
    assert has_sidecar is True
    assert merged == {
        "TaskName": "rest",  # dataset level
        "EEGReference": "session",  # set on three levels; the session level is the nearest
        "PowerLineFrequency": 50,
        "Manufacturer": "S",  # subject level
        "SoftwareFilters": "n/a",
        "SamplingFrequency": 512,  # data level
    }


def test_inherited_sidecars_reach_the_recording(tmp_path: Path) -> None:
    """The merged sidecars and the entities of the BIDS name end up in the metadata and the data model."""
    state = _state(_inheritance_tree(tmp_path))
    assert state.found.relative == SESSION_DATA
    assert _fields(state.metadata) == {
        "EEGReference": ("session", "sidecar"),
        "SamplingFrequency": (512, "sidecar"),
        "PowerLineFrequency": (50, "sidecar"),
        "SoftwareFilters": ("n/a", "sidecar"),
        "TaskName": ("rest", "sidecar"),
    }
    assert _entities(state.metadata) == {
        "subject": ("01", "bids_filename"),
        "session": ("a", "bids_filename"),
        "task": ("rest", "bids_filename"),
        "run": ("1", "bids_filename"),
    }
    rec = _recording(state)
    assert (rec.subject, rec.session, rec.task, rec.run, rec.reference) == ("01", "a", "rest", "1", "session")
    assert (
        rec.metadata_sources["session"] == "bids_filename" and rec.metadata_sources["run"] == "bids_filename"
    )


def test_sidecar_suffix_follows_the_data_file(tmp_path: Path) -> None:
    """A-77: a MEG data file reads *_meg.json sidecars; *_eeg.json files do not apply to it."""
    _write_json(tmp_path / "dataset_description.json", {"Name": "test", "BIDSVersion": "1.11.1"})
    _write_json(tmp_path / "task-rest_eeg.json", {"TaskName": "eeg sidecar", "EEGReference": "Cz"})
    _write_fif(tmp_path / "sub-01/meg/sub-01_task-rest_meg.fif", line_freq=None)
    _write_json(
        tmp_path / "sub-01/meg/sub-01_task-rest_meg.json", {"TaskName": "rest", "PowerLineFrequency": 60}
    )
    state = _state(tmp_path)
    assert state.metadata.has_sidecar
    assert state.metadata.sidecar == {"TaskName": "rest", "PowerLineFrequency": 60}
    assert _fields(state.metadata) == {
        "SamplingFrequency": (256.0, "header"),
        "PowerLineFrequency": (60, "sidecar"),
        "TaskName": ("rest", "sidecar"),
    }
    assert _recording(state).line_frequency_hz == 60.0


def test_merged_json_counts_an_unreadable_sidecar_as_present(tmp_path: Path) -> None:
    root = _bids_root(tmp_path)
    _write(root / "sub-01/eeg/sub-01_task-rest_eeg.json", "{broken")
    assert bids.merged_json(root, PurePosixPath(DATA), "eeg") == ({}, True)
    assert bids.merged_json(root, PurePosixPath(DATA), "meg") == ({}, False)


def test_no_sidecar_applies_to_a_data_file_without_bids_name(tmp_path: Path) -> None:
    root = _inheritance_tree(tmp_path)
    _write_json(root / "eeg.json", {"EEGReference": "applies to every eeg data file with a BIDS name"})
    shutil.copyfile(BIDS_EDF, root / "sub-01/ses-a/eeg/rec_01.edf")
    data = PurePosixPath("sub-01/ses-a/eeg/rec_01.edf")
    assert bids.parse_name(data.name) is None
    assert bids.applicable(root, data, "eeg", ".json") == []
    assert bids.merged_json(root, data, "eeg") == ({}, False)
    state = _state(root, relative=data.as_posix())
    assert not state.metadata.has_sidecar and state.metadata.entities == {}
    assert _fields(state.metadata) == {"SamplingFrequency": (512.0, "header")}


def test_sidecars_behind_links_are_not_read(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    _write_json(outside / "task-rest_eeg.json", {"EEGReference": "foreign"})
    root = _bids_root(tmp_path / "ds")
    dir_link(root / "linked", outside)
    found = bids.applicable(root, PurePosixPath("linked/sub-01_task-rest_eeg.edf"), "eeg", ".json")
    assert found == []


def test_linked_sidecar_file_is_not_read(tmp_path: Path) -> None:
    outside = _write_json(tmp_path / "outside" / "task-rest_eeg.json", {"EEGReference": "foreign"})
    root = _bids_root(tmp_path / "ds", {"TaskName": "rest"})
    try:
        (root / "task-rest_eeg.json").symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks not permitted on this system")
    found = bids.applicable(root, PurePosixPath(DATA), "eeg", ".json")
    assert [path.relative_to(root).as_posix() for path in found] == ["sub-01/eeg/sub-01_task-rest_eeg.json"]


def test_unlistable_level_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _inheritance_tree(tmp_path)
    blocked = root / "sub-01"
    real_iterdir = Path.iterdir

    def iterdir(self: Path) -> Any:
        if self == blocked:
            raise PermissionError(13, "denied", str(self))
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    found = bids.applicable(root, SESSION_DATA, "eeg", ".json")
    assert [path.relative_to(root).as_posix() for path in found] == [APPLICABLE[0], *APPLICABLE[2:]]


@pytest.mark.parametrize(
    "content",
    [
        b"{broken",
        b"[1, 2]",  # valid JSON, but no object
        b'"text"',
        b"",
        b"\xff\xfe{}",  # not UTF-8
        b"[" * 100_000,  # nested too deep
    ],
    ids=["syntax", "array", "string", "empty", "not-utf8", "too-deep"],
)
def test_read_json_returns_none_for_broken_input(tmp_path: Path, content: bytes) -> None:
    assert bids.read_json(_write(tmp_path / "x_eeg.json", content)) is None


def test_read_json_accepts_bom_and_enforces_the_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path / "x_eeg.json", b'\xef\xbb\xbf{"TaskName": "rest"}')
    assert bids.read_json(path) == {"TaskName": "rest"}
    assert bids.read_json(tmp_path / "missing_eeg.json") is None
    monkeypatch.setattr(bids, "MAX_JSON_BYTES", 10)
    assert bids.read_json(path) is None


def test_read_tsv_keeps_header_and_rows(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "x_channels.tsv", b"\xef\xbb\xbfname\ttype\tunits\r\nFp1\tEEG\tuV\r\n\r\n  \nFp2\tEEG\n"
    )
    assert bids.read_tsv(path) == (
        ["name", "type", "units"],
        [{"name": "Fp1", "type": "EEG", "units": "uV"}, {"name": "Fp2", "type": "EEG"}],
    )
    assert bids.read_tsv(_write(tmp_path / "h_channels.tsv", "name\ttype\n")) == (["name", "type"], [])


@pytest.mark.parametrize("content", [b"", b"\n \n\t\n", b"name\nF\xffp1\n"])
def test_read_tsv_returns_none_for_unusable_input(tmp_path: Path, content: bytes) -> None:
    assert bids.read_tsv(_write(tmp_path / "x_channels.tsv", content)) is None


def test_read_tsv_missing_or_too_large(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write(tmp_path / "x_channels.tsv", "name\ttype\nFp1\tEEG\n")
    assert bids.read_tsv(tmp_path / "missing_channels.tsv") is None
    monkeypatch.setattr(bids, "MAX_TSV_BYTES", 5)
    assert bids.read_tsv(path) is None


def test_nearest_tsv_and_the_ignored_space_entity(tmp_path: Path) -> None:
    root = _bids_root(tmp_path)
    data = PurePosixPath(DATA)
    _write(root / "sub-01/sub-01_channels.tsv", "name\ttype\tunits\nFp1\tEEG\tmV\n")
    _write(root / "sub-01/eeg/sub-01_task-rest_channels.tsv", "name\ttype\tunits\nFp1\tEOG\tuV\n")
    assert bids.nearest_tsv(root, data, "channels") == (
        ["name", "type", "units"],
        [{"name": "Fp1", "type": "EOG", "units": "uV"}],
    )
    _write(root / "sub-01/eeg/sub-01_space-CapTrak_electrodes.tsv", "name\tx\ty\tz\nFp1\t1\t2\t3\n")
    assert bids.nearest_tsv(root, data, "electrodes") is None  # data files have no space entity
    assert bids.nearest_tsv(root, data, "electrodes", ignore=("space",)) == (
        ["name", "x", "y", "z"],
        [{"name": "Fp1", "x": "1", "y": "2", "z": "3"}],
    )
    assert bids.nearest_tsv(root, data, "events") is None


# --- metadata.collect: precedence and sources (A-03, A-04) ------------------------------------------------


def test_bids_ok_documents_everything_from_sidecars() -> None:
    ctx = CheckContext.build(scan(FIX / "bids_ok"), Config())
    assert [s.found.relative.as_posix() for s in ctx.recordings] == [
        "sub-01/eeg/sub-01_task-rest_eeg.edf",
        "sub-02/eeg/sub-02_task-rest_eeg.edf",
    ]
    for state, subject in zip(ctx.recordings, ("01", "02"), strict=True):
        meta = state.metadata
        assert _fields(meta) == {
            "EEGReference": ("Cz", "sidecar"),
            "SamplingFrequency": (512, "sidecar"),
            "PowerLineFrequency": (50, "sidecar"),
            "SoftwareFilters": ("n/a", "sidecar"),
            "TaskName": ("rest", "sidecar"),
        }
        assert meta.channel_columns == ALL_SIDECAR
        assert meta.has_sidecar and meta.sidecar_rate == 512.0 and meta.sidecar_eeg_count == 8
        assert meta.channels_tsv is not None and [row["name"] for row in meta.channels_tsv] == list(LABELS)
        assert _entities(meta) == {"subject": (subject, "bids_filename"), "task": ("rest", "bids_filename")}
        rec = _recording(state)
        assert (rec.subject, rec.session, rec.task, rec.run) == (subject, None, "rest", None)
        assert (rec.reference, rec.line_frequency_hz, rec.electrode_type) == ("Cz", 50.0, None)
        assert rec.channels[0].position == "-0.0294,0.0839,-0.007" and rec.channels[0].impedance_kohm == 3.5
        # every source is named exactly; "device" is left out here (see test_device_na_documents_no_device)
        sources = {key: value for key, value in rec.metadata_sources.items() if key != "device"}
        assert sources == {
            "subject": "bids_filename",
            "task": "bids_filename",
            "reference": "sidecar",
            "line_frequency_hz": "sidecar",
            "channels": "sidecar",
            "position": "sidecar",
            "impedance_kohm": "sidecar",
            "sampling_rate_hz": "header",
            "duration_s": "header",
        }


def test_neurogrid_toml_wins_over_sidecar() -> None:
    cfg = parse(
        '[metadata.defaults]\nreference = "FCz"\nline_frequency_hz = 60\nsoftware_filters = "HP 0.1 Hz"\n'
        'device = "ExampleAmp 64"\nelectrode_type = "dry"\n'
    )
    state = CheckContext.build(scan(FIX / "bids_ok"), cfg).recordings[0]
    assert _fields(state.metadata) == {
        "EEGReference": ("FCz", "config"),
        "SamplingFrequency": (512, "sidecar"),  # the toml has no value for it
        "PowerLineFrequency": (60.0, "config"),
        "SoftwareFilters": ("HP 0.1 Hz", "config"),
        "TaskName": ("rest", "sidecar"),
    }
    rec = _recording(state)
    assert (rec.reference, rec.line_frequency_hz, rec.device, rec.electrode_type) == (
        "FCz",
        60.0,
        "ExampleAmp 64",
        "dry",
    )
    keys = ("reference", "line_frequency_hz", "device", "electrode_type")
    assert {key: rec.metadata_sources[key] for key in keys} == dict.fromkeys(keys, "config")


def test_header_rate_when_the_sidecar_lacks_it(tmp_path: Path) -> None:
    state = _state(_bids_root(tmp_path, {"TaskName": "rest"}))
    assert _fields(state.metadata) == {
        "SamplingFrequency": (512.0, "header"),
        "TaskName": ("rest", "sidecar"),
    }
    assert state.metadata.has_sidecar and state.metadata.sidecar_rate is None


@pytest.mark.parametrize(
    ("sidecar", "toml", "expected"),
    [
        ({}, "", (50.0, "header")),
        ({"PowerLineFrequency": 60}, "", (60, "sidecar")),
        ({"PowerLineFrequency": "n/a"}, "", (50.0, "header")),  # A-03: n/a is missing, the header follows
        ({"PowerLineFrequency": 60}, "[metadata.defaults]\nline_frequency_hz = 55\n", (55.0, "config")),
    ],
)
def test_power_line_frequency_toml_then_sidecar_then_header(
    tmp_path: Path, sidecar: dict[str, Any], toml: str, expected: tuple[Any, str]
) -> None:
    _write_json(tmp_path / "dataset_description.json", {"Name": "test", "BIDSVersion": "1.11.1"})
    _write_fif(tmp_path / "sub-01/eeg/sub-01_task-rest_eeg.fif", line_freq=50.0)
    _write_json(tmp_path / "sub-01/eeg/sub-01_task-rest_eeg.json", sidecar)
    state = _state(tmp_path, parse(toml))
    assert _fields(state.metadata)["PowerLineFrequency"] == expected
    rec = _recording(state)
    assert rec.line_frequency_hz == float(expected[0])
    assert rec.metadata_sources["line_frequency_hz"] == expected[1]


def test_power_line_frequency_undocumented_everywhere(tmp_path: Path) -> None:
    _write_json(tmp_path / "dataset_description.json", {"Name": "test", "BIDSVersion": "1.11.1"})
    _write_fif(tmp_path / "sub-01/eeg/sub-01_task-rest_eeg.fif", line_freq=None)
    state = _state(tmp_path)
    assert "PowerLineFrequency" not in state.metadata.fields
    rec = _recording(state)
    assert rec.line_frequency_hz is None and "line_frequency_hz" not in rec.metadata_sources


@pytest.mark.parametrize("value", ["50 Hz", "60", True])
def test_power_line_frequency_that_is_no_number_sets_no_frequency(tmp_path: Path, value: object) -> None:
    """A sidecar value that is no JSON number never becomes Recording.line_frequency_hz, and never crashes."""
    state = _state(_bids_root(tmp_path, {"TaskName": "rest", "PowerLineFrequency": value}))
    assert state.metadata.sidecar["PowerLineFrequency"] == value  # the sidecar was read
    rec = _recording(state)
    assert rec.line_frequency_hz is None and "line_frequency_hz" not in rec.metadata_sources


@pytest.mark.parametrize("na", ["n/a", " N/A "])
def test_na_is_missing_for_reference_and_line_frequency_but_documents_filters(
    tmp_path: Path, na: str
) -> None:
    """A-03: n/a counts as missing for EEGReference and PowerLineFrequency, as valid for SoftwareFilters."""
    sidecar = {"TaskName": "rest", "EEGReference": na, "PowerLineFrequency": na, "SoftwareFilters": na}
    state = _state(_bids_root(tmp_path, sidecar))
    assert _fields(state.metadata) == {
        "SamplingFrequency": (512.0, "header"),
        "SoftwareFilters": (na, "sidecar"),
        "TaskName": ("rest", "sidecar"),
    }
    rec = _recording(state)
    assert rec.reference is None and rec.line_frequency_hz is None
    assert "reference" not in rec.metadata_sources and "line_frequency_hz" not in rec.metadata_sources


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_empty_values_are_missing_for_every_field(tmp_path: Path, empty: str | None) -> None:
    sidecar = {
        "TaskName": empty,
        "EEGReference": empty,
        "PowerLineFrequency": empty,
        "SoftwareFilters": empty,
    }
    state = _state(_bids_root(tmp_path, sidecar))
    # the task entity of the file name documents TaskName when the sidecar does not
    assert _fields(state.metadata) == {
        "SamplingFrequency": (512.0, "header"),
        "TaskName": ("rest", "bids_filename"),
    }


def test_na_in_neurogrid_toml(tmp_path: Path) -> None:
    sidecar = {"TaskName": "rest", "EEGReference": "Cz", "SoftwareFilters": {"HighPass": {"cutoff": 0.1}}}
    cfg = parse('[metadata.defaults]\nreference = "n/a"\nsoftware_filters = "n/a"\n')
    fields = _fields(_state(_bids_root(tmp_path, sidecar), cfg).metadata)
    assert fields["EEGReference"] == ("Cz", "sidecar")  # n/a in the toml documents no reference either
    assert fields["SoftwareFilters"] == ("n/a", "config")


def test_task_name_from_sidecar_wins_over_the_task_entity() -> None:
    states = CheckContext.build(scan(FIX / "bids_issues"), Config()).recordings
    meta = states[0].metadata
    assert meta.fields["TaskName"] == Documented("resting", "sidecar")
    assert meta.entities["task"] == Documented("rest", "bids_filename")
    assert "EEGReference" not in meta.fields and meta.sidecar_eeg_count == 9 and meta.sidecar_rate == 500.0


def test_no_task_name_without_sidecar_value_or_task_entity(tmp_path: Path) -> None:
    state = _state(_bids_root(tmp_path, {}, data="sub-01/eeg/sub-01_eeg.edf"))
    assert "TaskName" not in state.metadata.fields
    assert _entities(state.metadata) == {"subject": ("01", "bids_filename")}


def test_channel_columns_from_channels_tsv_or_header(tmp_path: Path) -> None:
    root = _bids_root(tmp_path, {"TaskName": "rest"})
    channels = root / "sub-01/eeg/sub-01_task-rest_channels.tsv"
    # one empty units cell: the column is not documented by the sidecar, the header documents it
    rows = "".join(f"{label}\tEEG\t{'uV' if index else ''}\n" for index, label in enumerate(LABELS))
    _write(channels, "name\ttype\tunits\n" + rows)
    assert _state(root).metadata.channel_columns == {"name": "sidecar", "type": "sidecar", "units": "header"}
    _write(channels, "name\tunits\n" + "".join(f"{label}\tuV\n" for label in LABELS))
    assert _state(root).metadata.channel_columns == {"name": "sidecar", "type": "header", "units": "sidecar"}
    _write(channels, "name\ttype\tunits\n")
    meta = _state(root).metadata
    assert meta.channel_columns == ALL_HEADER and meta.channels_tsv == []
    channels.unlink()
    meta = _state(root).metadata
    assert meta.channel_columns == ALL_HEADER and meta.channels_tsv is None


def test_units_missing_in_header_and_sidecar_stay_undocumented(tmp_path: Path) -> None:
    data = bytearray(BIDS_EDF.read_bytes())
    data[1024:1032] = b" " * 8  # units field of the first of 8 signals
    raw = tmp_path / "raw"
    _write(raw / "rec.edf", bytes(data))
    assert _state(raw).metadata.channel_columns == {"name": "header", "type": "header"}
    root = _bids_root(tmp_path / "bids", {"TaskName": "rest"})
    _write(root / DATA, bytes(data))
    assert _state(root).metadata.channel_columns == {"name": "header", "type": "header"}
    _write(root / "sub-01/eeg/sub-01_task-rest_channels.tsv", gen_fixtures._channels_tsv(LABELS))
    assert _state(root).metadata.channel_columns == ALL_SIDECAR


def _edf_plus_with_annotations(path: Path) -> Path:
    """EDF+C, 1 record of 1 s: 'EEG Fz' at 256 Hz in uV and an 'EDF Annotations' signal (blank unit)."""
    spr = (256, 60)
    header = bytearray()
    header += b"0".ljust(8) + b"X X X X".ljust(80) + b"Startdate X X X X".ljust(80)
    header += b"01.01.85" + b"00.00.00" + str(256 * 3).encode().ljust(8) + b"EDF+C".ljust(44)
    header += b"1".ljust(8) + b"1".ljust(8) + b"2".ljust(4)
    header += b"EEG Fz".ljust(16) + b"EDF Annotations".ljust(16)
    header += b"".ljust(80) * 2 + b"uV".ljust(8) + b"".ljust(8)
    header += b"-500".ljust(8) + b"-1".ljust(8) + b"500".ljust(8) + b"1".ljust(8)
    header += b"-32768".ljust(8) * 2 + b"32767".ljust(8) * 2
    header += b"".ljust(80) * 2 + b"".join(str(r).encode().ljust(8) for r in spr) + b"".ljust(32) * 2
    tal = b"+0\x14\x14\x00".ljust(2 * spr[1], b"\x00")
    return _write(path, bytes(header) + b"\x00\x00" * spr[0] + tal)


def test_annotation_channels_do_not_count_for_header_columns(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    _edf_plus_with_annotations(root / "rec.edf")
    state = _state(root)
    assert [(ch.name, ch.type, ch.unit) for ch in _recording(state).channels] == [
        ("EEG Fz", "EEG", "uV"),
        ("EDF Annotations", "ANNOT", None),
    ]
    assert state.metadata.channel_columns == ALL_HEADER


def test_channels_tsv_without_rows_is_no_channel_source(tmp_path: Path) -> None:
    root = _bids_root(tmp_path, {"TaskName": "rest"})
    _write(root / "sub-01/eeg/sub-01_task-rest_channels.tsv", "name\ttype\tunits\n")
    state = _state(root)
    assert state.metadata.channels_tsv == [] and state.metadata.channel_columns == ALL_HEADER
    assert _recording(state).metadata_sources["channels"] == "header"


def test_types_units_and_status_from_channels_tsv(tmp_path: Path) -> None:
    root = _bids_root(tmp_path, {"TaskName": "rest"})
    _write(
        root / "sub-01/eeg/sub-01_task-rest_channels.tsv",
        "name\ttype\tunits\tstatus\n"
        "Fp1\tHEOG\tµV\tbad\n"
        "Fp2\tveog\tn/a\tGOOD\n"
        "F3\tREF\tuV\tn/a\n"
        "F4\tTRIG\t\t\n"
        "C3\tMEGMAG\tmV\tunknown\n"
        "C4\tEEG\tuV\tgood\n",  # O1 and O2 are not listed
    )
    rec = _recording(_state(root))
    by_name = {ch.name: ch for ch in rec.channels}
    assert [(by_name[name].type, by_name[name].unit, by_name[name].status) for name in LABELS] == [
        ("EOG", "µV", "bad"),
        ("EOG", "uV", "good"),  # units n/a keep the header unit
        ("MISC", "uV", None),
        ("TRIG", "uV", None),
        ("MEG", "mV", None),  # every declared type wins over the header (A-04); MEG types are MEG
        ("EEG", "uV", "good"),
        ("EEG", "uV", None),
        ("EEG", "uV", None),
    ]
    assert rec.metadata_sources["channels"] == "sidecar"


def test_recording_rate_follows_the_types_of_channels_tsv(tmp_path: Path) -> None:
    root = _bids_root(tmp_path, {"TaskName": "rest"})
    _mixed_rate_edf(root / DATA)
    assert _recording(_state(root)).sampling_rate_hz == 512.0  # ECG at 256 Hz is no EEG channel
    _write(
        root / "sub-01/eeg/sub-01_task-rest_channels.tsv",
        "name\ttype\tunits\nEEG Fz\tEEG\tuV\nECG\tEEG\tuV\n",
    )
    assert _recording(_state(root)).sampling_rate_hz == 256.0  # the lowest EEG rate (A-76)


def test_positions_and_impedances_from_electrodes_tsv(tmp_path: Path) -> None:
    root = _bids_root(tmp_path, {"TaskName": "rest"})
    _write(
        root / "sub-01/eeg/sub-01_space-CapTrak_electrodes.tsv",
        "name\tx\ty\tz\timpedance\n"
        "Fp1\t-0.0294\t0.0839\t-0.007\t4.5\n"
        "Fp2\tn/a\tn/a\tn/a\tn/a\n"
        "F3\t0.1\tinf\t0.2\t7\n"
        "F4\t1e-3\t2\t3\tnan\n"
        "Cz\t0\t0\t0.1\t1\n",  # not a channel of the recording
    )
    rec = _recording(_state(root))
    by_name = {ch.name: (ch.position, ch.impedance_kohm) for ch in rec.channels}
    assert by_name["Fp1"] == ("-0.0294,0.0839,-0.007", 4.5)
    assert by_name["Fp2"] == (None, None)
    assert by_name["F3"] == (None, 7.0)  # one coordinate not finite: no position
    assert by_name["F4"] == ("0.001,2,3", None)
    assert by_name["C3"] == (None, None)
    assert (
        rec.metadata_sources["position"] == "sidecar" and rec.metadata_sources["impedance_kohm"] == "sidecar"
    )


def test_electrodes_tsv_without_values_documents_nothing(tmp_path: Path) -> None:
    root = _bids_root(tmp_path, {"TaskName": "rest"})
    rows = "".join(f"{label}\tn/a\tn/a\tn/a\tn/a\n" for label in LABELS)
    _write(root / "sub-01/eeg/sub-01_electrodes.tsv", "name\tx\ty\tz\timpedance\n" + rows)
    rec = _recording(_state(root))
    assert all(ch.position is None and ch.impedance_kohm is None for ch in rec.channels)
    assert "position" not in rec.metadata_sources and "impedance_kohm" not in rec.metadata_sources


def test_electrodes_tsv_without_impedance_column(tmp_path: Path) -> None:
    root = _bids_root(tmp_path, {"TaskName": "rest"})
    rows = "".join(f"{label}\t{x}\t{y}\t{z}\n" for label, (x, y, z) in gen_fixtures.POSITIONS.items())
    _write(root / "sub-01/eeg/sub-01_electrodes.tsv", "name\tx\ty\tz\n" + rows)
    rec = _recording(_state(root))
    assert [ch.position for ch in rec.channels][:2] == ["-0.0294,0.0839,-0.007", "0.0298,0.0849,-0.0071"]
    assert all(ch.position and ch.impedance_kohm is None for ch in rec.channels)
    assert rec.metadata_sources["position"] == "sidecar" and "impedance_kohm" not in rec.metadata_sources


@pytest.mark.parametrize(
    ("electrodes", "fp1", "fp2", "source"),
    [
        (None, 3.0, 3.0, "header"),
        ("n/a", 3.0, 3.0, "header"),  # nothing documented in the sidecar: the header values stay
        ("12", 12.0, 12.0, "sidecar"),
    ],
)
def test_electrodes_tsv_impedance_wins_over_the_header(
    tmp_path: Path, electrodes: str | None, fp1: float, fp2: float, source: str
) -> None:
    _write_json(tmp_path / "dataset_description.json", {"Name": "test", "BIDSVersion": "1.11.1"})
    eeg = tmp_path / "sub-01" / "eeg"
    gen_fixtures.write_brainvision(eeg / "sub-01_task-rest_eeg.vhdr", impedances=gen_fixtures.IMPEDANCES_OK)
    if electrodes is not None:
        rows = "".join(f"{label}\tn/a\tn/a\tn/a\t{electrodes}\n" for label in LABELS)
        _write(eeg / "sub-01_electrodes.tsv", "name\tx\ty\tz\timpedance\n" + rows)
    rec = _recording(_state(tmp_path))
    by_name = {ch.name: ch.impedance_kohm for ch in rec.channels}
    assert (by_name["Fp1"], by_name["Fp2"]) == (fp1, fp2)
    assert rec.metadata_sources["impedance_kohm"] == source


@pytest.mark.parametrize(("model", "expected"), [("  AmpX 32  ", "AmpX 32"), ("A" * 200, "A" * 120)])
def test_device_from_manufacturers_model_name(tmp_path: Path, model: str, expected: str) -> None:
    rec = _recording(_state(_bids_root(tmp_path, {"TaskName": "rest", "ManufacturersModelName": model})))
    assert rec.device == expected and rec.metadata_sources["device"] == "sidecar"


@pytest.mark.parametrize("model", [42, "", "   ", ["AmpX"]])
def test_device_needs_a_text(tmp_path: Path, model: object) -> None:
    rec = _recording(_state(_bids_root(tmp_path, {"TaskName": "rest", "ManufacturersModelName": model})))
    assert rec.device is None and "device" not in rec.metadata_sources


def test_device_na_documents_no_device(tmp_path: Path) -> None:
    rec = _recording(_state(_bids_root(tmp_path, {"TaskName": "rest", "ManufacturersModelName": "n/a"})))
    assert rec.device is None and "device" not in rec.metadata_sources


def test_device_from_neurogrid_toml_wins(tmp_path: Path) -> None:
    root = _bids_root(tmp_path, {"TaskName": "rest", "ManufacturersModelName": "AmpX"})
    rec = _recording(_state(root, parse('[metadata.defaults]\ndevice = "ExampleAmp 64"\n')))
    assert rec.device == "ExampleAmp 64" and rec.metadata_sources["device"] == "config"


@pytest.mark.parametrize(
    ("sidecar", "rate", "count"),
    [
        ({"SamplingFrequency": 512, "EEGChannelCount": 8}, 512.0, 8),
        ({"SamplingFrequency": 512.5, "EEGChannelCount": 8.0}, 512.5, 8),
        ({"SamplingFrequency": "512", "EEGChannelCount": "8"}, None, None),
        ({"SamplingFrequency": True, "EEGChannelCount": 8.5}, None, None),
        ({"SamplingFrequency": float("nan"), "EEGChannelCount": float("inf")}, None, None),
        ({}, None, None),
    ],
)
def test_sidecar_numbers(sidecar: dict[str, Any], rate: float | None, count: int | None) -> None:
    meta = RecordingMetadata(sidecar=sidecar)
    assert meta.sidecar_rate == rate and meta.sidecar_eeg_count == count


# --- raw folders: mapping table and expression (A-05) -----------------------------------------------------


def test_raw_folder_table_documents_metadata(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    shutil.copytree(FIX / "brainvision_ok", root)
    _write_json(root / "rec_eeg.json", {"EEGReference": "ignored", "TaskName": "ignored"})  # no BIDS dataset
    cfg = parse(
        RAW_TOML
        + '[[convert.files]]\npath = "rec.vhdr"\nsubject = "01"\nsession = "a"\ntask = "rest"\nrun = "2"\n'
    )
    state = _state(root, cfg)
    meta = state.metadata
    assert not meta.has_sidecar and meta.sidecar == {} and meta.channels_tsv is None
    assert _fields(meta) == {
        "EEGReference": ("Cz", "config"),
        "SamplingFrequency": (500.0, "header"),
        "PowerLineFrequency": (50.0, "config"),
        "SoftwareFilters": ("n/a", "config"),
        "TaskName": ("rest", "mapping"),
    }
    assert meta.channel_columns == ALL_HEADER
    rec = _recording(state)
    assert (rec.subject, rec.session, rec.task, rec.run, rec.electrode_type) == (
        "01",
        "a",
        "rest",
        "2",
        "wet",
    )
    keys = ("subject", "session", "task", "run", "reference", "electrode_type", "impedance_kohm")
    assert {key: rec.metadata_sources[key] for key in keys} == {
        "subject": "mapping",
        "session": "mapping",
        "task": "mapping",
        "run": "mapping",
        "reference": "config",
        "electrode_type": "config",
        "impedance_kohm": "header",
    }


def test_raw_folder_without_mapping_documents_only_the_header() -> None:
    state = _state(FIX / "brainvision_ok")
    assert _fields(state.metadata) == {"SamplingFrequency": (500.0, "header")}
    assert state.metadata.entities == {}
    rec = _recording(state)
    assert (rec.subject, rec.task, rec.electrode_type, rec.device) == (None, None, None, None)


def test_mapping_expression_on_relative_path_or_file_name() -> None:
    cfg = parse(PATTERN)
    assert mapped_entities(_found("a01_rest_3.edf"), cfg) == {"subject": "a01", "task": "rest", "run": "3"}
    # the relative path does not match (it contains a folder), the file name does; run is optional
    assert mapped_entities(_found("site/a01_rest.edf"), cfg) == {"subject": "a01", "task": "rest"}
    assert mapped_entities(_found("notes.edf"), cfg) == {}
    assert mapped_entities(_found("a01_rest.edf"), Config()) == {}
    by_path = parse(
        "[convert]\npattern = '(?P<subject>[A-Za-z0-9]+)/(?P<session>[A-Za-z0-9]+)/(?P<task>[a-z]+)\\.vhdr'\n"
    )
    assert mapped_entities(_found("s01/v2/rest.vhdr"), by_path) == {
        "subject": "s01",
        "session": "v2",
        "task": "rest",
    }


def test_mapping_expression_value_that_is_no_label_leaves_the_file_unmapped() -> None:
    """A-05/A-77: a non-alphanumeric value is never dropped silently (the file would land elsewhere)."""
    cfg = parse("[convert]\npattern = '(?P<subject>[^_]+)_(?P<task>[^.]+)\\.edf'\n")
    assert mapped_entities(_found("a-1_rest.edf"), cfg) == {}
    assert mapped_entities(_found("a1_rest.edf"), cfg) == {"subject": "a1", "task": "rest"}


def test_mapping_expression_run_must_be_an_index() -> None:
    text = "[convert]\npattern = '(?P<subject>[a-z0-9]+)_(?P<task>[a-z]+)_(?P<run>[a-z0-9]+)\\.edf'\n"
    cfg = parse(text)
    assert mapped_entities(_found("s1_rest_3.edf"), cfg)["run"] == "3"
    # A-77: a file with another run is not mapped (the run is never dropped, the file gets a template row)
    assert mapped_entities(_found("s1_rest_b.edf"), cfg) == {}


def test_mapping_table_wins_over_the_expression() -> None:
    table = (
        '[[convert.files]]\npath = \'site\\a01_rest.edf\'\nsubject = "T01"\ntask = "table"\n'
        '[[convert.files]]\npath = "./b02_rest.edf"\nsubject = "T02"\nsession = "s"\n'
        'task = "table"\nrun = "07"\n'
    )
    cfg = parse(PATTERN + table)
    assert mapped_entities(_found("site/a01_rest.edf"), cfg) == {"subject": "T01", "task": "table"}
    assert mapped_entities(_found("b02_rest.edf"), cfg) == {
        "subject": "T02",
        "session": "s",
        "task": "table",
        "run": "07",
    }
    assert mapped_entities(_found("c03_rest.edf"), cfg) == {"subject": "c03", "task": "rest"}


def test_entities_from_bids_names_or_from_the_mapping() -> None:
    cfg = parse(PATTERN)
    found = _found(
        "sub-01_ses-a_task-rest_run-1_eeg.edf",
        entities=(("sub", "01"), ("ses", "a"), ("task", "rest"), ("run", "1")),
    )
    assert entities_for(found, cfg, is_bids=True) == {
        "subject": Documented("01", "bids_filename"),
        "session": Documented("a", "bids_filename"),
        "task": Documented("rest", "bids_filename"),
        "run": Documented("1", "bids_filename"),
    }
    # in a raw folder BIDS-like names mean nothing; only the mapping counts
    assert entities_for(found, Config(), is_bids=False) == {}
    raw = _found("a01_rest_3.edf")
    assert entities_for(raw, cfg, is_bids=False) == {
        "subject": Documented("a01", "mapping"),
        "task": Documented("rest", "mapping"),
        "run": Documented("3", "mapping"),
    }
    assert entities_for(raw, cfg, is_bids=True) == {}  # BIDS datasets ignore the mapping


# --- config.py: [convert] and [metadata] ------------------------------------------------------------------


def test_valid_mapping_and_metadata_sections() -> None:
    cfg = parse(
        RAW_TOML
        + "[convert]\npattern = '(?P<subject>\\w+)_(?P<session>\\w+)_(?P<task>\\w+)_(?P<run>\\d+)\\.edf'\n"
        + '[[convert.files]]\npath = "sub/rec.vhdr"\nsubject = "01"\nsession = "a"\n'
        + 'task = "rest"\nrun = "02"\n'
        + '[metadata.channel_map]\nEXG1 = "Oz"\n"T3 " = "T7"\n'
    )
    row = cfg.convert.files[0]
    assert (row.path, row.subject, row.session, row.task, row.run) == (
        "sub/rec.vhdr",
        "01",
        "a",
        "rest",
        "02",
    )
    assert cfg.convert.pattern == r"(?P<subject>\w+)_(?P<session>\w+)_(?P<task>\w+)_(?P<run>\d+)\.edf"
    assert cfg.metadata.channel_map == {"EXG1": "Oz", "T3 ": "T7"}
    defaults = cfg.metadata.defaults
    assert (defaults.software_filters, defaults.electrode_type, defaults.line_frequency_hz) == (
        "n/a",
        "wet",
        50.0,
    )
    assert Config.model_validate({"convert": {"pattern": None}}).convert.pattern is None
    assert Config().convert.files == [] and Config().metadata.channel_map == {}


ROW = '[[convert.files]]\npath = "rec.vhdr"\n'


CONFIG_ERRORS = [
    (ROW + 'subject = "sub-01"\ntask = "rest"\n', "convert.files.0.subject", "string_pattern_mismatch"),
    (ROW + 'subject = "01"\ntask = "rest task"\n', "convert.files.0.task", "string_pattern_mismatch"),
    (
        ROW + 'subject = "01"\nsession = "a_b"\ntask = "rest"\n',
        "convert.files.0.session",
        "string_pattern_mismatch",
    ),
    (
        ROW + 'subject = "01"\ntask = "rest"\nrun = "1a"\n',
        "convert.files.0.run",
        "string_pattern_mismatch",
    ),
    (
        ROW + 'subject = "01"\ntask = "rest"\nrun = "123456789"\n',
        "convert.files.0.run",
        "string_too_long",
    ),
    (ROW + 'subject = "01"\ntask = "rest"\nrun = 1\n', "convert.files.0.run", "string_type"),
    (ROW + 'subject = "01"\n', "convert.files.0.task", "missing"),
    (ROW + 'subject = "01"\ntask = "rest"\nacq = "x"\n', "convert.files.0.acq", "extra_forbidden"),
    ("[convert]\nfiles = {}\n", "convert.files", "list_type"),
    ("[convert]\npattern = '('\n", "convert.pattern", "value_error"),
    ("[convert]\npattern = '(?P<subject>\\w+)'\n", "convert.pattern", "value_error"),
    ("[convert]\npattern = '(?P<task>\\w+)'\n", "convert.pattern", "value_error"),
    (
        "[convert]\npattern = '(?P<subject>\\w+)_(?P<task>\\w+)_(?P<acq>\\w+)'\n",
        "convert.pattern",
        "value_error",
    ),
    ("[convert]\npattern = '" + "a" * 513 + "'\n", "convert.pattern", "string_too_long"),
    ("[metadata.channel_map]\nEXG1 = 1\n", "metadata.channel_map.EXG1", "string_type"),
    (
        "[metadata.channel_map]\n" + "".join(f'C{index} = "Cz"\n' for index in range(4097)),
        "metadata.channel_map",
        "too_long",
    ),
    (
        '[metadata.defaults]\nelectrode_type = "gel"\n',
        "metadata.defaults.electrode_type",
        "literal_error",
    ),
    (
        "[metadata.defaults]\nline_frequency_hz = 0\n",
        "metadata.defaults.line_frequency_hz",
        "greater_than",
    ),
    (
        "[metadata.defaults]\nline_frequency_hz = nan\n",
        "metadata.defaults.line_frequency_hz",
        "finite_number",
    ),
    (
        '[metadata.defaults]\nsoftware_filters = "' + "x" * 501 + '"\n',
        "metadata.defaults.software_filters",
        "string_too_long",
    ),
    (
        '[metadata.defaults]\ndevice = "' + "x" * 121 + '"\n',
        "metadata.defaults.device",
        "string_too_long",
    ),
    ("[metadata.defaults]\nreference = 1\n", "metadata.defaults.reference", "string_type"),
]


@pytest.mark.parametrize(
    ("toml", "field", "problem"),
    CONFIG_ERRORS,
    ids=[f"{field}-{problem}" for _toml, field, problem in CONFIG_ERRORS],
)
def test_invalid_mapping_or_metadata_is_a_config_error(toml: str, field: str, problem: str) -> None:
    with pytest.raises(ConfigError) as info:
        parse(toml)
    assert info.value.message_key == "config.invalid"
    assert info.value.params == {"field": field, "problem": problem}


@pytest.mark.parametrize(
    "path",
    [
        "/data/rec.vhdr",  # absolute
        "../rec.vhdr",  # leaves the project root
        "sub/../../rec.vhdr",
        "C:/data/rec.vhdr",  # drive
        "C:rec.vhdr",
        "\\\\\\\\server\\\\share\\\\rec.vhdr",  # UNC (TOML escapes)
        "rec.vhdr:stream",  # alternate data stream
        "sub/CON.vhdr",  # reserved Windows name (A-67)
        "sub./rec.vhdr",  # trailing dot, which Windows drops
        "",
    ],
)
def test_mapping_table_paths_must_be_plain_relative_paths(path: str) -> None:
    """A-52: absolute, drive, UNC and '..' paths in [[convert.files]] are refused with the field name."""
    good = '[[convert.files]]\npath = "ok.vhdr"\nsubject = "01"\ntask = "rest"\n'
    bad = f'[[convert.files]]\npath = "{path}"\nsubject = "02"\ntask = "rest"\n'
    with pytest.raises(ConfigError) as info:
        parse(good + bad)
    assert info.value.message_key == "config.unsafe_path"
    assert info.value.params == {"field": "convert.files.1.path"}


def test_mapping_table_accepts_backslashes_and_dot_segments() -> None:
    cfg = parse('[[convert.files]]\npath = \'sub\\.\\rec.vhdr\'\nsubject = "01"\ntask = "rest"\n')
    assert mapped_entities(_found("sub/rec.vhdr"), cfg) == {"subject": "01", "task": "rest"}


def test_default_config_location_feeds_the_metadata(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    shutil.copytree(FIX / "brainvision_ok", root)
    toml = RAW_TOML + '[[convert.files]]\npath = "rec.vhdr"\nsubject = "07"\ntask = "rest"\n'
    _write(root / ".neurogrid" / "neurogrid.toml", toml)
    loaded = config_module.load(None, root)
    assert loaded.path == root.resolve() / ".neurogrid" / "neurogrid.toml"
    assert loaded.project_root == root.resolve()
    state = _state(root, loaded.config)  # the hidden .neurogrid folder is no part of the dataset
    assert _recording(state).subject == "07" and state.metadata.fields["TaskName"] == Documented(
        "rest", "mapping"
    )


def test_config_locations_and_project_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ds"
    root.mkdir()
    assert config_module.load(None, root) == (Config(), None, root.resolve())
    (root / ".neurogrid").mkdir()
    assert config_module.load(None, root).path is None  # the folder alone holds no configuration
    inside = _write(root / "conf" / "mine.toml", RAW_TOML)
    assert config_module.load(inside, root).project_root == root.resolve()
    outside = _write(tmp_path / "elsewhere" / "mine.toml", RAW_TOML)
    assert config_module.load(outside, root).project_root == outside.parent.resolve()
    # A-66: a toml in a .neurogrid folder has the folder above as project root, also with --config
    other = _write(tmp_path / "other" / ".neurogrid" / "neurogrid.toml", RAW_TOML)
    assert config_module.load(other, root).project_root == (tmp_path / "other").resolve()
    with pytest.raises(ConfigError) as info:
        config_module.load(tmp_path / "missing.toml", root)
    assert info.value.message_key == "config.not_found"
    monkeypatch.setattr(config_module, "MAX_CONFIG_BYTES", 10)
    with pytest.raises(ConfigError) as info:
        config_module.load(inside, root)
    assert info.value.message_key == "config.too_large"
    with pytest.raises(ConfigError) as info:
        parse(RAW_TOML)
    assert info.value.message_key == "config.too_large"


@pytest.mark.parametrize(
    ("data", "key"),
    [
        (b"[convert\n", "config.syntax"),
        (b"a = 1" + b"0" * 5000 + b"\n", "config.syntax"),
        (b"a = " + b"[" * 5000 + b"]" * 5000 + b"\n", "config.too_deep"),
        ('[metadata.defaults]\nreference = "Ä"\n'.encode("latin-1"), "config.encoding"),
    ],
)
def test_unreadable_configuration(data: bytes, key: str) -> None:
    with pytest.raises(ConfigError) as info:
        parse_bytes(data)
    assert info.value.message_key == key


def test_configuration_with_bom_and_its_hash() -> None:
    plain = parse_bytes(RAW_TOML.encode("utf-8"))
    with_bom = parse_bytes(b"\xef\xbb\xbf" + RAW_TOML.replace("\n", "\r\n").encode("utf-8"))
    assert plain == with_bom and plain.canonical_sha256() == with_bom.canonical_sha256()
    assert plain.canonical_sha256() != Config().canonical_sha256()
    overrides = parse('[rules."CORE-M05-02".params]\nmax_kohm = 10\n').overrides()
    assert overrides == {"CORE-M05-02": {"max_kohm": 10}}


# --- discover: companions, orphans, splits, calibration and folder formats (M01, A-74) --------------------


def test_brainvision_companions_follow_the_header(tmp_path: Path) -> None:
    gen_fixtures.write_brainvision(tmp_path / "rec.vhdr", data_file="Data_Other.EEG", seed=12)
    _write(tmp_path / "stray.eeg", b"\x00" * 32)  # named by no header
    _write(tmp_path / "broken.vhdr", "")  # unreadable header: its own stem still claims .eeg and .vmrk
    _write(tmp_path / "broken.eeg", b"")
    _write(tmp_path / "broken.vmrk", b"")
    result = scan(tmp_path)
    assert _names(result.recordings) == ["broken.vhdr", "rec.vhdr"]
    assert _names(result.other) == ["Data_Other.EEG", "broken.eeg", "broken.vmrk", "rec.vmrk"]
    assert _names(result.unsupported) == ["stray.eeg"]


def test_brainvision_data_file_counts_by_name_only_and_without_case(tmp_path: Path) -> None:
    """A-74, A-77: DataFile counts only as a file name in the same folder, compared without case."""
    gen_fixtures.write_brainvision(tmp_path / "rec.vhdr", data_file="Data_Other.EEG", seed=12)
    header = tmp_path / "rec.vhdr"
    text = header.read_text(encoding="utf-8")
    assert "DataFile=Data_Other.EEG\n" in text
    header.write_text(text.replace("DataFile=Data_Other.EEG", "DataFile=export\\DATA_OTHER.eeg"), "utf-8")
    result = scan(tmp_path)
    assert _names(result.recordings) == ["rec.vhdr"]
    assert _names(result.other) == ["Data_Other.EEG", "rec.vmrk"] and result.unsupported == []


def test_eeglab_fdt_next_to_the_set_is_a_companion(tmp_path: Path) -> None:
    result = scan(FIX / "eeglab_ok")
    assert _names(result.recordings) == ["rec.set"] and _names(result.other) == ["rec.fdt"]
    assert result.unsupported == []
    shutil.copyfile(FIX / "eeglab_ok" / "rec.set", tmp_path / "Rec.SET")
    shutil.copyfile(FIX / "eeglab_ok" / "rec.fdt", tmp_path / "rec.fdt")
    mixed_case = scan(tmp_path)  # companions are matched without regard to case (A-74)
    assert _names(mixed_case.recordings) == ["Rec.SET"] and _names(mixed_case.other) == ["rec.fdt"]


def test_fdt_named_by_the_set_header_is_a_companion(tmp_path: Path) -> None:
    gen_fixtures.write_eeglab(tmp_path / "rec.set", seed=17)
    (tmp_path / "rec.set").rename(tmp_path / "renamed.set")  # EEG.data still names rec.fdt
    assert ADAPTERS[".set"].inspect(tmp_path / "renamed.set").missing_companions == ()
    result = scan(tmp_path)
    assert _names(result.recordings) == ["renamed.set"]
    assert result.unsupported == [] and _names(result.other) == ["rec.fdt"]


def test_orphan_companions_are_unsupported_and_reported(tmp_path: Path) -> None:
    orphan = scan(FIX / "orphan")
    assert _names(orphan.recordings) == ["rec_ok.edf"]
    assert [(f.relative.as_posix(), f.suffix) for f in orphan.unsupported] == [("lonely.fdt", ".fdt")]
    root = tmp_path / "raw"
    root.mkdir()
    shutil.copyfile(FIX / "orphan" / "rec_ok.edf", root / "rec_ok.edf")
    for name in ("lonely.eeg", "lonely.fdt", "legacy.cnt"):
        _write(root / name, b"\x00" * 64)
    results = pipeline.run_check(root, pipeline.CheckOptions(as_of=date(2026, 10, 11)))
    reported = {f.file: (f.status, f.reason) for f in results.findings if f.rule_id == "CORE-M01-04"}

    def shown(name: str) -> str:  # raw folders show pseudonymous IDs plus extension (A-70)
        return pseudonym(PurePosixPath(name)) + PurePosixPath(name).suffix

    assert reported == {
        shown("lonely.eeg"): (Status.FAILED, "format.orphan_companion"),
        shown("lonely.fdt"): (Status.FAILED, "format.orphan_companion"),
        shown("legacy.cnt"): (Status.FAILED, "format.unsupported"),
    }


def test_fif_split_parts_are_companions(tmp_path: Path) -> None:
    for name in ("rec.fif", "rec-1.fif", "REC-2.FIF", "other-1.fif", "rec-01.fif"):
        _write(tmp_path / name, b"x")
    result = scan(tmp_path)
    # other-1.fif has no first part; rec-01.fif is no split name (parts start at 1 without zero padding)
    assert _names(result.recordings) == ["other-1.fif", "rec-01.fif", "rec.fif"]
    assert _names(result.other) == ["REC-2.FIF", "rec-1.fif"]


def test_bids_split_parts_are_companions(tmp_path: Path) -> None:
    _write_json(tmp_path / "dataset_description.json", {"Name": "test", "BIDSVersion": "1.11.1"})
    meg = tmp_path / "sub-01" / "meg"
    names = (
        "sub-01_task-rest_split-01_meg.fif",
        "sub-01_task-rest_split-02_meg.fif",
        "sub-01_task-rest_split-10_meg.fif",
        "sub-01_task-other_split-02_meg.fif",  # its first part is missing
        "sub-01_task-x_split-1_meg.fif",
        "sub-01_task-x_split-2_meg.fif",
    )
    for name in names:
        _write(meg / name, b"x")
    result = scan(tmp_path)
    assert _names(result.recordings) == [
        "sub-01/meg/sub-01_task-other_split-02_meg.fif",
        "sub-01/meg/sub-01_task-rest_split-01_meg.fif",
        "sub-01/meg/sub-01_task-x_split-1_meg.fif",
    ]
    assert [name for name in _names(result.other) if name.endswith(".fif")] == [
        "sub-01/meg/sub-01_task-rest_split-02_meg.fif",
        "sub-01/meg/sub-01_task-rest_split-10_meg.fif",
        "sub-01/meg/sub-01_task-x_split-2_meg.fif",
    ]


def test_bids_meg_calibration_files_are_no_recordings(tmp_path: Path) -> None:
    bids_root = tmp_path / "bids"
    _write_json(bids_root / "dataset_description.json", {"Name": "test", "BIDSVersion": "1.11.1"})
    meg = bids_root / "sub-01" / "meg"
    for name in (
        "sub-01_acq-crosstalk_meg.fif",
        "sub-01_ses-a_acq-calibration_meg.dat",
        "sub-01_task-rest_meg.fif",
    ):
        _write(meg / name, b"x")
    result = scan(bids_root)
    assert _names(result.recordings) == ["sub-01/meg/sub-01_task-rest_meg.fif"]
    assert _names(result.other) == [
        "dataset_description.json",
        "sub-01/meg/sub-01_acq-crosstalk_meg.fif",
        "sub-01/meg/sub-01_ses-a_acq-calibration_meg.dat",
    ]
    assert result.unsupported == [] and result.subjects == 1
    raw = tmp_path / "raw"
    _write(raw / "x_acq-crosstalk_meg.fif", b"x")  # outside BIDS the name means nothing
    assert _names(scan(raw).recordings) == ["x_acq-crosstalk_meg.fif"]


def test_mff_folder_in_bids_is_one_unsupported_recording(tmp_path: Path) -> None:
    root = _bids_root(tmp_path, {"TaskName": "rest"})
    mff = root / "sub-02" / "eeg" / "sub-02_task-rest_eeg.mff"
    _write(mff / "signal1.bin", b"\x00" * 100)
    _write(mff / "info.xml", "<x/>")
    result = scan(root)
    assert [(f.relative.as_posix(), f.suffix, f.size_bytes) for f in result.unsupported] == [
        ("sub-02/eeg/sub-02_task-rest_eeg.mff", ".mff", 104)
    ]
    assert dict(result.unsupported[0].entities) == {"sub": "02", "task": "rest"}
    listed = _names([*result.recordings, *result.other])
    assert not any(".mff/" in name for name in listed)  # the folder is not entered
    assert result.subjects == 2  # A-72: sub labels of all data files, readable or not


def test_mef3_folder_in_a_raw_folder_is_one_unsupported_recording(tmp_path: Path) -> None:
    """A-74: a .mefd folder is one unsupported recording and is not entered; raw folders get pseudonyms."""
    mefd = tmp_path / "Night.MEFD"
    _write(mefd / "chan.timd" / "seg.tdat", b"\x00" * 40)
    _write(mefd / "info.rdat", b"\x00" * 2)
    shutil.copyfile(BIDS_EDF, tmp_path / "rec.edf")
    result = scan(tmp_path)
    assert [(f.relative.as_posix(), f.suffix, f.size_bytes) for f in result.unsupported] == [
        ("Night.MEFD", ".mefd", 42)
    ]
    assert result.unsupported[0].display_file == pseudonym(PurePosixPath("Night.MEFD")) + ".mefd"
    assert _names(result.recordings) == ["rec.edf"] and result.other == []
    assert result.subjects is None  # raw folder without mapping: unknown (A-72)


def test_scan_counts_raw_subjects_from_the_mapping(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    for name in ("rest_a01.edf", "task_a01.edf", "rest_b02.edf"):
        _write(root / name, BIDS_EDF.read_bytes())
    _write(root / ".neurogrid" / "neurogrid.toml", DOCUMENTED_TOML)
    assert pipeline.run_scan(root).subjects == 2
    _write(root / "notes.edf", BIDS_EDF.read_bytes())  # mapped without subject: the count is unknown again
    assert pipeline.run_scan(root).subjects is None


def test_found_file_entities_and_display(tmp_path: Path) -> None:
    root = _bids_root(tmp_path, {"TaskName": "rest"})
    found = scan(root).recordings[0]
    assert found.entity("sub") == "01" and found.entity("ses") is None
    assert found.display_id == DATA and found.display_file == DATA


def test_single_bids_file_keeps_its_entities_and_sidecars(tmp_path: Path) -> None:
    root = _bids_root(tmp_path, {"TaskName": "rest", "EEGReference": "Cz"})
    shutil.copyfile(BIDS_EDF, root / "sub-01/eeg/sub-01_task-other_eeg.edf")
    result = scan(root, only=PurePosixPath(DATA))
    assert _names(result.recordings) == [DATA] and result.subjects == 1
    state = CheckContext.build(result, Config()).recordings[0]
    assert _fields(state.metadata)["EEGReference"] == ("Cz", "sidecar")
    assert _entities(state.metadata) == {
        "subject": ("01", "bids_filename"),
        "task": ("rest", "bids_filename"),
    }


def test_bids_scan_skips_derived_hidden_and_linked_entries(tmp_path: Path) -> None:
    root = _bids_root(tmp_path / "ds", {"TaskName": "rest"})
    kept = ("dataset_description.json", DATA, "sub-01/eeg/sub-01_task-rest_eeg.json")
    for folder in ("derivatives", "sourcedata", "code", "stimuli"):
        (root / folder).mkdir()
        shutil.copyfile(BIDS_EDF, root / folder / "sub-09_task-rest_eeg.edf")
    _write(root / "sub-01/eeg/.sub-01_task-rest_eeg.edf", b"hidden")
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.copyfile(BIDS_EDF, outside / "sub-08_task-rest_eeg.edf")
    dir_link(root / "sub-08", outside)
    result = scan(root)
    assert _names(result.recordings) == [DATA] and result.subjects == 1
    assert _names(result.other) == sorted(name for name in kept if name != DATA)
    assert result.links_skipped == 1 and result.unsupported == [] and result.unreadable == []
    assert result.total_bytes == sum((root / name).stat().st_size for name in kept)


@pytest.mark.parametrize(
    ("content", "description"),
    [(b"[1, 2]", {}), (b"{broken", {}), (b'{"Name": ["x"], "License": 1.5}', {"License": "1.5"})],
)
def test_unusable_dataset_description_still_marks_bids(
    tmp_path: Path, content: bytes, description: dict[str, str]
) -> None:
    root = _bids_root(tmp_path, {"TaskName": "rest"})
    _write(root / "dataset_description.json", content)
    result = scan(root)
    assert result.is_bids and result.subjects == 1 and result.description == description


# --- checks/context.py: metadata per recording ------------------------------------------------------------


def test_build_attaches_metadata_to_each_recording() -> None:
    ctx = CheckContext.build(scan(FIX / "bids_issues"), Config())
    first, second = ctx.recordings
    assert first.object_id == first.found.display_id == "sub-01/eeg/sub-01_task-rest_eeg.edf"
    assert first.file == first.found.display_file and first.identity == first.found.identity
    assert _fields(first.metadata) == {
        "SamplingFrequency": (500, "sidecar"),
        "PowerLineFrequency": (50, "sidecar"),
        "SoftwareFilters": ("n/a", "sidecar"),
        "TaskName": ("resting", "sidecar"),
    }
    first_rec = _recording(first)
    assert first_rec.reference is None and all(ch.position is None for ch in first_rec.channels)
    assert "position" not in first_rec.metadata_sources  # sub-01 has no electrodes.tsv
    assert (
        first.inspection == HeaderInspection() and first.header_error is None and not first.annotations_only
    )
    assert (first.adapter, first.path) == (ADAPTERS[".edf"], ctx.root / first.found.relative)
    assert second.metadata.fields["EEGReference"] == Documented("Cz", "sidecar")
    by_name = {ch.name: ch for ch in _recording(second).channels}
    assert (by_name["EXG1"].position, by_name["EXG1"].impedance_kohm) == ("0,0,-0.05", 12.0)
    assert ctx.root == ctx.scan.root and ctx.work is None


class _FailingAdapter:
    """EDF adapter whose ``read`` (or only ``inspect``) raises ``error``."""

    format = "EDF"
    extensions = (".edf",)

    def __init__(self, error: Exception, *, in_inspect: bool = False) -> None:
        self.error = error
        self.in_inspect = in_inspect

    def read(self, path: Path, *, recording_id: str, relative_path: str) -> Recording:
        if not self.in_inspect:
            raise self.error
        return EdfAdapter().read(path, recording_id=recording_id, relative_path=relative_path)

    def inspect(self, path: Path) -> HeaderInspection:
        raise self.error

    def read_check(self, path: Path) -> str | None:
        return None


@pytest.mark.parametrize(
    ("error", "in_inspect", "reason"),
    [
        (OverflowError("value too large"), False, "header.number_field"),
        (ZeroDivisionError("rate"), False, "header.number_field"),
        (ValueError("not a number"), False, "header.number_field"),
        (ValueError("not a number"), True, "header.number_field"),
        (HeaderUnreadable("header.too_short"), False, "header.too_short"),
        (PermissionError(13, "denied"), False, "header.io_error"),
    ],
)
def test_unreadable_header_keeps_the_sidecar_metadata(
    monkeypatch: pytest.MonkeyPatch, error: Exception, in_inspect: bool, reason: str
) -> None:
    """A-75: a header value no model can hold is a finding (header.number_field), never a crash."""
    monkeypatch.setitem(ADAPTERS, ".edf", _FailingAdapter(error, in_inspect=in_inspect))
    ctx = CheckContext.build(scan(FIX / "bids_ok"), Config())
    assert len(ctx.recordings) == 2
    for state in ctx.recordings:
        assert (state.recording, state.inspection, state.header_error) == (None, None, reason)
        meta = state.metadata
        assert _fields(meta) == {
            "EEGReference": ("Cz", "sidecar"),
            "SamplingFrequency": (512, "sidecar"),
            "PowerLineFrequency": (50, "sidecar"),
            "SoftwareFilters": ("n/a", "sidecar"),
            "TaskName": ("rest", "sidecar"),
        }
        assert meta.channel_columns == ALL_SIDECAR  # from channels.tsv, without a header
        assert meta.channels_tsv is not None and [row["name"] for row in meta.channels_tsv] == list(LABELS)
        assert not state.annotations_only


def test_truncated_bids_header_without_sidecar_rate(tmp_path: Path) -> None:
    root = _bids_root(tmp_path, {"TaskName": "rest", "EEGReference": "Cz"})
    _write(root / DATA, b"0" * 100)
    state = _state(root)
    assert state.recording is None and state.header_error == "header.too_short"
    assert _fields(state.metadata) == {"EEGReference": ("Cz", "sidecar"), "TaskName": ("rest", "sidecar")}
    assert state.metadata.channel_columns == {} and state.metadata.channels_tsv is None


def test_unreadable_raw_header_keeps_the_mapping(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    _write(root / "rest_a01.edf", b"0" * 100)
    state = _state(root, parse(DOCUMENTED_TOML))
    assert state.recording is None and state.header_error == "header.too_short"
    assert _fields(state.metadata) == {
        "EEGReference": ("Cz", "config"),
        "PowerLineFrequency": (50.0, "config"),
        "SoftwareFilters": ("n/a", "config"),
        "TaskName": ("rest", "mapping"),
    }
    assert _entities(state.metadata) == {"subject": ("a01", "mapping"), "task": ("rest", "mapping")}
    assert state.metadata.channel_columns == {}


def test_read_error_is_computed_once_and_the_validator_needs_a_work_folder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Path] = []

    class _Counting(EdfAdapter):
        def read_check(self, path: Path) -> str | None:
            calls.append(path)
            return "OSError"

    monkeypatch.setitem(ADAPTERS, ".edf", _Counting())
    ctx = CheckContext.build(scan(FIX / "edf_ok"), Config())
    state = ctx.recordings[0]
    assert state.read_error() == "OSError" and state.read_error() == "OSError"
    assert calls == [state.path]
    with pytest.raises(RuntimeError):
        ctx.validator_result()


def test_validator_runs_once_in_the_work_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, Path]] = []
    sentinel = object()

    def run_validator(root: Path, out: Path) -> object:
        calls.append((root, out))
        return sentinel

    monkeypatch.setattr(context_module, "run_validator", run_validator)
    found = scan(FIX / "bids_ok")
    ctx = CheckContext.build(found, Config(), work=tmp_path)
    assert ctx.validator_result() is sentinel and ctx.validator_result() is sentinel
    assert calls == [(found.root, tmp_path / "validator")]


# --- LIB-02: MNE-BIDS reads the entities of BIDS file names ---------------------------------------------


def test_entities_are_read_with_mne_bids() -> None:
    name = bids.parse_name("sub-01_ses-a_task-rest_acq-x_run-1_eeg.edf")
    assert name is not None
    assert name.entities == {"sub": "01", "ses": "a", "task": "rest", "acq": "x", "run": "1"}
    assert (name.suffix, name.extension) == ("eeg", ".edf")
    space = bids.parse_name("sub-01_space-CapTrak_electrodes.tsv")
    assert space is not None and space.entities == {"sub": "01", "space": "CapTrak"}


@pytest.mark.parametrize(
    "name",
    [
        "sub-01_foo-bar_eeg.edf",  # an entity BIDS does not define (MNE-BIDS refuses it)
        "sub-01_sub-02_eeg.edf",  # the same entity twice
        "sub-01_task-re-st_eeg.edf",  # a value that is not alphanumeric
    ],
)
def test_names_mne_bids_refuses_are_not_bids(name: str) -> None:
    assert bids.parse_name(name) is None


def test_sidecar_with_an_unknown_entity_does_not_apply(tmp_path: Path) -> None:
    eeg = tmp_path / "sub-01" / "eeg"
    eeg.mkdir(parents=True)
    data = eeg / "sub-01_task-rest_eeg.edf"
    data.write_bytes(b"")
    (eeg / "sub-01_task-rest_eeg.json").write_text('{"EEGReference": "Cz"}', encoding="utf-8")
    (eeg / "sub-01_foo-x_task-rest_eeg.json").write_text('{"EEGReference": "Fz"}', encoding="utf-8")
    found = bids.applicable(tmp_path, PurePosixPath("sub-01/eeg/sub-01_task-rest_eeg.edf"), "eeg", ".json")
    assert [p.name for p in found] == ["sub-01_task-rest_eeg.json"]
