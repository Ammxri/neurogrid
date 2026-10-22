"""M10 annotation readers, attachment of annotation-only files and the measurements (NG-F08, A-17, A-80)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from gen_fixtures import (  # type: ignore[import-not-found]
    _field,
    _num,
    write_annotation_edf,
    write_brainvision,
    write_edf,
    write_eeglab,
)
from neurogrid import config as config_module
from neurogrid.checks import annotation as checks
from neurogrid.checks.context import CheckContext
from neurogrid.io import annotations as reader
from neurogrid.io.annotations import AnnotationsUnreadable, build_index
from neurogrid.io.discover import FoundFile, pseudonym, scan
from neurogrid.io.identifying import annotator_pseudonym, display_text, short_hash
from neurogrid.kernel.errors import ConfigError
from neurogrid.model.dataset import Annotation, Recording

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"


def _annotation_file(
    path: Path, tal: bytes, *, bdf: bool = False, plus: str = "C", record_s: int = 0
) -> Path:
    """An annotation-only EDF+C/BDF+C (or +D) with one record of ``record_s`` seconds whose annotation signal
    holds ``tal``."""
    bps = 3 if bdf else 2
    samples = -(-len(tal) // bps)
    header = bytearray(b"\xffBIOSEMI" if bdf else _field("0", 8))
    header += _field("X X X X", 80) + _field("Startdate X X X X", 80) + _field("01.01.85", 8)
    header += _field("00.00.00", 8) + _num(512, 8) + _field(("BDF+" if bdf else "EDF+") + plus, 44)
    header += _num(1, 8) + _num(record_s, 8) + _num(1, 4)
    digital = (-8388608, 8388607) if bdf else (-32768, 32767)
    entry = ("BDF Annotations" if bdf else "EDF Annotations", "", "", -1.0, 1.0, *digital, "", samples)
    for value, width in zip(entry, (16, 80, 8, 8, 8, 8, 8, 80, 8), strict=True):
        header += _field(value, width) if isinstance(value, str) else _num(value, width)
    header += _field("", 32)
    path.write_bytes(bytes(header) + tal.ljust(samples * bps, b"\x00"))
    return path


def _codes(listed: reader.AnnotationList) -> list[tuple[float, float, str]]:
    return [(a.onset_s, a.duration_s, a.code) for a in listed.annotations]


# --- EDF+/BDF+ TAL ------------------------------------------------------------------------------------------


def test_tal_reader_texts_durations_and_time_keeping(tmp_path: Path) -> None:
    tal = (
        b"+0\x14\x14\x00"  # time keeping: no annotation
        b"+10\x155\x14Arousal\x14Snore\x14\x00"  # two texts in one TAL share onset and duration
        b"+12.5\x14Marker\x14\x00"  # no duration: 0
        b"-0.5\x150.25\x14Before start\x14\x00"
        b"+20\x1530\x14Lights off@@EEG Fz\x14\x00"  # channel link (MNE) is not part of the code
        b"+50\x1530\x14Schlaf \xc3\xa4 \xff\x14\x00"  # UTF-8, an undecodable byte replaced
    )
    listed = reader.read_edf_tal(_annotation_file(tmp_path / "hyp.edf", tal))
    assert listed.source == "edf_tal" and listed.data_intervals is None
    assert _codes(listed) == [
        (10.0, 5.0, "Arousal"),
        (10.0, 5.0, "Snore"),
        (12.5, 0.0, "Marker"),
        (-0.5, 0.25, "Before start"),
        (20.0, 30.0, "Lights off"),
        (50.0, 30.0, "Schlaf ä \ufffd"),
    ]


def test_tal_reader_in_a_signal_file_and_bdf(tmp_path: Path) -> None:
    edf = tmp_path / "rec.edf"
    entries = ((0.5, 1.0, "Eyes closed"), (2.0, 0.0, "Blink"))
    write_edf(edf, seconds=3, labels=("Fz",), plus="C", annotations=entries)
    assert _codes(reader.read_edf_tal(edf)) == [(0.5, 1.0, "Eyes closed"), (2.0, 0.0, "Blink")]
    bdf = tmp_path / "rec.bdf"
    write_edf(bdf, seconds=3, labels=("Fz",), plus="C", bdf=True, annotations=entries)
    assert _codes(reader.read_edf_tal(bdf)) == [(0.5, 1.0, "Eyes closed"), (2.0, 0.0, "Blink")]
    hypnogram = tmp_path / "hyp.bdf"
    write_annotation_edf(hypnogram, ((0.0, 30.0, "W"), (30.0, 30.0, "N1")), bdf=True)
    assert _codes(reader.read_edf_tal(hypnogram)) == [(0.0, 30.0, "W"), (30.0, 30.0, "N1")]
    plain = tmp_path / "plain.edf"
    write_edf(plain, seconds=2, labels=("Fz",))
    assert reader.read_edf_tal(plain).annotations == ()


def test_tal_reader_edf_plus_d_record_times() -> None:
    listed = reader.read_edf_tal(FIX / "edf_plus_d" / "rec.edf")
    assert listed.annotations == ()
    assert listed.data_intervals == ((0.0, 5.0), (10.0, 15.0)) and listed.end_s == 15.0


@pytest.mark.parametrize(
    "tal",
    [
        b"+0\x14\x14\x00garbage\x14\x00",  # no onset
        b"+0\x14\x14\x00+1\x15abc\x14x\x14\x00",  # duration not a number
        b"+0\x14\x14\x00+1\x14x\x00",  # text not ended by 0x14
        b"0\x14\x14\x00",  # onset without sign
    ],
)
def test_malformed_tal_makes_the_file_unreadable(tmp_path: Path, tal: bytes) -> None:
    with pytest.raises(AnnotationsUnreadable) as info:
        reader.read_edf_tal(_annotation_file(tmp_path / "bad.edf", tal))
    assert info.value.reason == "annotation.unreadable"


def test_edf_plus_d_without_time_keeping_is_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "d.edf"
    write_edf(path, seconds=2, labels=("Fz",), plus="D")
    raw = bytearray(path.read_bytes())
    start = raw.index(b"+1\x14\x14")
    raw[start : start + 5] = b"+1\x14x\x14"  # record 2 opens with a text, not the time-keeping entry
    path.write_bytes(bytes(raw))
    with pytest.raises(AnnotationsUnreadable):
        reader.read_edf_tal(path)


def test_annotation_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reader, "MAX_ANNOTATIONS", 2)
    path = tmp_path / "hyp.edf"
    write_annotation_edf(path, tuple((30.0 * i, 30.0, "W") for i in range(3)))
    with pytest.raises(AnnotationsUnreadable) as info:
        reader.read_edf_tal(path)
    assert info.value.reason == "annotation.too_many"


def test_long_texts_are_cut(tmp_path: Path) -> None:
    path = _annotation_file(tmp_path / "hyp.edf", b"+0\x14\x14\x00+1\x14" + b"a" * 5000 + b"\x14\x00")
    (annotation,) = reader.read_edf_tal(path).annotations
    assert annotation.code == "a" * reader.MAX_TEXT_BYTES


def test_unreadable_header(tmp_path: Path) -> None:
    path = tmp_path / "x.edf"
    path.write_bytes(b"not an edf")
    with pytest.raises(AnnotationsUnreadable):
        reader.read_edf_tal(path)


# --- BrainVision --------------------------------------------------------------------------------------------


def _vmrk(vhdr: Path, lines: str, encoding: str = "utf-8") -> None:
    vhdr.with_suffix(".vmrk").write_bytes(
        (
            "Brain Vision Data Exchange Marker File, Version 1.0\n\n[Common Infos]\nCodepage=UTF-8\n"
            f"DataFile={vhdr.stem}.eeg\n\n[Marker Infos]\n; comment line\n{lines}"
        ).encode(encoding)
    )


def test_vmrk_reader(tmp_path: Path) -> None:
    vhdr = tmp_path / "rec.vhdr"
    write_brainvision(vhdr, sfreq=500, seconds=2, labels=("Fz",))
    _vmrk(
        vhdr,
        "Mk1=New Segment,,1,1,0,20200101120000000000\n"
        "Mk2=Stimulus,S  1,501,1,0\n"
        "Mk3=Comment,a\\1b,1001,250,0\n"
        "Mk4=Response,R  2,1,x,0\n",
    )
    listed = reader.read_vmrk(vhdr)
    assert listed.source == "vmrk"
    assert _codes(listed) == [
        (1.0, 0.002, "Stimulus/S  1"),
        (2.0, 0.5, "Comment/a,b"),
        (0.0, 0.0, "Response/R  2"),  # a size that is no number is 0, as in MNE
    ]


def test_vmrk_latin1_and_problems(tmp_path: Path) -> None:
    vhdr = tmp_path / "rec.vhdr"
    write_brainvision(vhdr, sfreq=500, seconds=1, labels=("Fz",))
    _vmrk(vhdr, "Mk1=Comment,5 µV,1,1,0\n", encoding="latin-1")
    assert [a.code for a in reader.read_vmrk(vhdr).annotations] == ["Comment/5 µV"]
    _vmrk(vhdr, "Mk1=Stimulus,S 1,abc,1,0\n")
    with pytest.raises(AnnotationsUnreadable):
        reader.read_vmrk(vhdr)
    vhdr.with_suffix(".vmrk").unlink()
    with pytest.raises(AnnotationsUnreadable):  # M01-03 reports the missing marker file
        reader.read_vmrk(vhdr)
    unsafe = tmp_path / "unsafe.vhdr"
    write_brainvision(unsafe, sfreq=500, seconds=1, labels=("Fz",))
    text = unsafe.read_text(encoding="utf-8").replace("MarkerFile=unsafe.vmrk", "MarkerFile=../unsafe.vmrk")
    unsafe.write_text(text, encoding="utf-8")
    with pytest.raises(AnnotationsUnreadable):  # never opened (A-52)
        reader.read_vmrk(unsafe)


# --- EEGLAB -------------------------------------------------------------------------------------------------


def test_eeglab_events_v5(tmp_path: Path) -> None:
    path = tmp_path / "rec.set"
    events = (("stim", 513.0, 256.0), (2.0, 1025.0, None), ("boundary", 1500.0, 0.0), (2.5, 1.0, 0.0))
    write_eeglab(path, sfreq=512, seconds=4, labels=("Fz",), events=events)
    listed = reader.read_eeglab_events(path)
    assert listed.source == "eeglab_event" and not listed.epoched
    assert _codes(listed) == [(1.0, 0.5, "stim"), (2.0, 0.0, "2"), (0.0, 0.0, "2.5")]
    one = tmp_path / "one.set"
    write_eeglab(one, sfreq=512, seconds=4, labels=("Fz",), events=(("x", 1.0, None),), trials=2)
    listed = reader.read_eeglab_events(one)
    assert _codes(listed) == [(0.0, 0.0, "x")] and listed.epoched
    none = tmp_path / "none.set"
    write_eeglab(none, sfreq=512, seconds=4, labels=("Fz",))
    assert reader.read_eeglab_events(none).annotations == ()


def _matlab_number(group: Any, name: str, value: float) -> None:
    dataset = group.create_dataset(name, data=np.array([[value]], dtype="<f8"))
    dataset.attrs["MATLAB_class"] = np.bytes_(b"double")


def test_eeglab_events_v73(tmp_path: Path) -> None:
    """MATLAB v7.3: EEG.event is a struct array whose fields hold object references (MATLAB's layout)."""
    import h5py

    path = tmp_path / "rec.set"
    with h5py.File(path, "w", userblock_size=512) as handle:
        refs = handle.create_group("#refs#")
        eeg = handle.create_group("EEG")
        eeg.attrs["MATLAB_class"] = np.bytes_(b"struct")
        for key, value in (("nbchan", 1.0), ("pnts", 100.0), ("trials", 1.0), ("srate", 100.0)):
            _matlab_number(eeg, key, value)
        empty = eeg.create_dataset("chanlocs", data=np.zeros(2, dtype="<u8"))
        empty.attrs["MATLAB_class"] = np.bytes_(b"struct")
        empty.attrs["MATLAB_empty"] = np.uint8(1)
        samples = eeg.create_dataset("data", data=np.zeros((100, 1), dtype="<f4"))
        samples.attrs["MATLAB_class"] = np.bytes_(b"single")
        event = eeg.create_group("event")
        event.attrs["MATLAB_class"] = np.bytes_(b"struct")
        types, latencies = [], []
        for index, (kind, latency) in enumerate((("stim", 11.0), ("resp", 51.0))):
            text = refs.create_dataset(f"t{index}", data=np.array([[ord(ch)] for ch in kind], dtype="<u2"))
            text.attrs["MATLAB_class"] = np.bytes_(b"char")
            number = refs.create_dataset(f"l{index}", data=np.array([[latency]], dtype="<f8"))
            number.attrs["MATLAB_class"] = np.bytes_(b"double")
            types.append([text.ref])
            latencies.append([number.ref])
        event.create_dataset("type", data=np.array(types, dtype=h5py.ref_dtype))
        event.create_dataset("latency", data=np.array(latencies, dtype=h5py.ref_dtype))
    with path.open("r+b") as raw:
        raw.write(b"MATLAB 7.3 MAT-file, written by NeuroGrid tests".ljust(116) + b"\x00" * 8 + b"\x00\x02IM")
    assert _codes(reader.read_eeglab_events(path)) == [(0.1, 0.0, "stim"), (0.5, 0.0, "resp")]


def test_eeglab_event_rows_shapes() -> None:
    assert reader._event_rows({"type": "a", "latency": 1.0}) == [{"type": "a", "latency": 1.0}]
    assert reader._event_rows({"type": ["a", "b"], "latency": [1.0, 2.0]}) == [
        {"type": "a", "latency": 1.0},
        {"type": "b", "latency": 2.0},
    ]
    assert reader._event_rows([{"type": "a"}, "x"]) == [{"type": "a"}]
    assert reader._event_rows(np.array([])) == []
    assert reader._type_text(np.float64(3.0)) == "3" and reader._type_text(float("nan")) == ""
    assert reader._type_text(True) == "1" and reader._type_text(["a", 2.0]) == "a 2"


def test_unreadable_eeglab(tmp_path: Path) -> None:
    path = tmp_path / "bad.set"
    path.write_bytes(b"no matlab file")
    with pytest.raises(AnnotationsUnreadable):
        reader.read_eeglab_events(path)


# --- FIF ----------------------------------------------------------------------------------------------------


def _fif(path: Path, *, meas_date: bool) -> Path:
    import mne

    info = mne.create_info(["Fz", "Cz"], 100.0, "eeg")
    raw = mne.io.RawArray(np.zeros((2, 1000)), info, first_samp=500, verbose="error")
    if meas_date:
        raw.set_meas_date(1_600_000_000)
    else:
        raw.set_meas_date(None)
    raw.set_annotations(
        mne.Annotations(
            onset=[1.0, 2.0, 3.0, 4.0],
            duration=[0.5, 0.0, 1.0, 0.0],
            description=["stim", "BAD_ACQ_SKIP", "EDGE boundary", "resp"],
        )
    )
    raw.save(path, overwrite=True, verbose="error")
    return path


@pytest.mark.parametrize("meas_date", [True, False])
def test_fif_annotations_relative_to_the_first_sample(tmp_path: Path, meas_date: bool) -> None:
    listed = reader.read_fif_annotations(_fif(tmp_path / "rec_raw.fif", meas_date=meas_date))
    assert listed.source == "fif_annotations"
    assert [(round(a.onset_s, 6), a.duration_s, a.code) for a in listed.annotations] == [
        (1.0, 0.5, "stim"),
        (4.0, 0.0, "resp"),
    ]


def test_fif_with_unsafe_split_is_not_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _fif(tmp_path / "rec_raw.fif", meas_date=True)
    monkeypatch.setattr(reader, "_unsafe_split", lambda _path: True)
    with pytest.raises(AnnotationsUnreadable):
        reader.read_fif_annotations(path)
    with pytest.raises(AnnotationsUnreadable):
        reader.read_fif_annotations(tmp_path / "missing.fif")


# --- BIDS events.tsv ----------------------------------------------------------------------------------------


def _bids(
    root: Path, events: str | None, sidecar: dict[str, Any] | None = None, *, bom: bool = False
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "dataset_description.json").write_text('{"Name": "t", "BIDSVersion": "1.9.0"}', encoding="utf-8")
    eeg = root / "sub-01" / "eeg"
    eeg.mkdir(parents=True, exist_ok=True)
    data = eeg / "sub-01_task-x_eeg.edf"
    write_edf(
        data,
        sfreq=64,
        seconds=20,
        labels=("Fz",),
        label_prefix="",
        plus="C",
        annotations=((1.0, 1.0, "inner"),),
    )
    if events is not None:
        (eeg / "sub-01_task-x_events.tsv").write_bytes(("\ufeff" if bom else "").encode() + events.encode())
    if sidecar is not None:
        (root / "task-x_events.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return root


def test_events_table_header_rule_and_bom(tmp_path: Path) -> None:
    root = _bids(tmp_path / "ds", " Onset \tDURATION\tTrial_Type\n1\t2\ta\n3\n", bom=True)
    table = reader.read_events(root, PurePosixPath("sub-01/eeg/sub-01_task-x_eeg.edf"))
    assert table is not None and table.columns == ("Onset", "DURATION", "Trial_Type")
    assert table.column("onset") == 0 and table.column(" trial_type ") == 2 and table.column("value") is None
    assert table.rows == (("1", "2", "a"), ("3", "", ""))
    assert table.values("trial_type") == ["a"] and table.values("value") is None
    assert reader.read_events(root, PurePosixPath("sub-02/eeg/sub-02_task-x_eeg.edf")) is None


def test_events_annotations_codes_labels_annotators(tmp_path: Path) -> None:
    events = (
        "onset\tduration\ttrial_type\tvalue\tannotator\n"
        "1.0\t0.5\tstim\t1\tA1\n"
        "2.0\tn/a\tstim\t2\tn/a\n"
        "3.0\t0.5\tn/a\t3\tA1\n"  # no code: no annotation
        "x\t0.5\tstim\t1\tA1\n"  # invalid onset
        "4.0\t-1\tstim\t1\tA1\n"  # negative duration
        "5.0\t0.5\tresp\t9\tA2\n"
    )
    sidecar = {"trial_type": {"Levels": {"stim": "Stimulus", "resp": {"Description": "Response"}, "x": 1}}}
    root = _bids(tmp_path / "ds", events, sidecar)
    relative = PurePosixPath("sub-01/eeg/sub-01_task-x_eeg.edf")
    table = reader.read_events(root, relative)
    assert table is not None
    found = reader.events_annotations(root, relative, table)
    assert [(a.onset_s, a.duration_s, a.code, a.label, a.annotator_id) for a in found.annotations] == [
        (1.0, 0.5, "stim", "Stimulus", "A1"),
        (2.0, 0.0, "stim", "Stimulus", "default"),
        (5.0, 0.5, "resp", "Response", "A2"),
    ]
    assert found.vocabulary == ("resp", "stim", "x") and found.invalid_rows == 2
    assert found.labels == (("resp", "Response"), ("stim", "Stimulus"))
    # without trial_type the value column is the code
    plain = _bids(tmp_path / "ds2", "onset\tduration\tvalue\n1\t0\t65536\n")
    table = reader.read_events(plain, relative)
    assert table is not None
    found = reader.events_annotations(plain, relative, table)
    assert [a.code for a in found.annotations] == ["65536"] and found.vocabulary is None
    # without onset every row is invalid
    broken = _bids(tmp_path / "ds3", "begin\tvalue\n1\ta\n")
    table = reader.read_events(broken, relative)
    assert table is not None and reader.events_annotations(broken, relative, table).invalid_rows == 1


def test_events_tsv_problems_are_unreadable_not_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _bids(tmp_path / "ds", None)
    events = root / "sub-01" / "eeg" / "sub-01_task-x_events.tsv"
    events.write_bytes(b"onset\tduration\n\xff\xfe\t1\n")
    relative = PurePosixPath("sub-01/eeg/sub-01_task-x_eeg.edf")
    with pytest.raises(AnnotationsUnreadable):
        reader.read_events(root, relative)
    events.write_text("onset\tduration\n" + "1\t0\n" * 3, encoding="utf-8")
    monkeypatch.setattr(reader, "MAX_ANNOTATIONS", 2)
    with pytest.raises(AnnotationsUnreadable) as info:
        reader.read_events(root, relative)
    assert info.value.reason == "annotation.too_many"
    events.write_text("\n\n", encoding="utf-8")
    assert reader.read_events(root, relative) == reader.EventsTable((), ())


def test_events_tsv_replaces_in_file_annotations_in_bids(tmp_path: Path) -> None:
    root = _bids(tmp_path / "ds", "onset\tduration\ttrial_type\n2\t1\touter\n")
    (obj,) = _index(root).objects
    assert [a.code for a in obj.annotations] == ["outer"] and obj.tracks[0].source == "events_tsv"
    (root / "sub-01" / "eeg" / "sub-01_task-x_events.tsv").unlink()
    (obj,) = _index(root).objects
    assert [a.code for a in obj.annotations] == ["inner"] and obj.tracks[0].source == "edf_tal"


# --- attachment and the index -------------------------------------------------------------------------------


def _index(root: Path, toml: str = "") -> reader.AnnotationIndex:
    return _context(root, toml).annotations()


def _context(root: Path, toml: str = "", *, show_paths: bool = False) -> CheckContext:
    found = scan(root, show_paths=show_paths)
    return CheckContext.build(found, config_module.parse(toml), show_paths=show_paths)


def _night(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    write_edf(path, sfreq=8, seconds=60, labels=("C3",))


def _hypnogram(root: Path, relative: str, stages: tuple[str, ...] = ("W", "N1")) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    write_annotation_edf(path, tuple((30.0 * i, 30.0, s) for i, s in enumerate(stages)))


def _attached(index: reader.AnnotationIndex) -> dict[str, list[tuple[str, str]]]:
    return {
        obj.found.relative.as_posix(): [(t.file.relative.as_posix(), t.annotator) for t in obj.tracks]
        for obj in index.objects
    }


def test_stem_prefix_heuristic_longest_stem_and_signal_files_never_claimed(tmp_path: Path) -> None:
    for name in ("night.edf", "night_long.edf", "night_2.edf"):
        _night(tmp_path, name)
    _hypnogram(tmp_path, "night_long_scorer1.edf")
    _hypnogram(tmp_path, "night_scorer2.edf")
    index = _index(tmp_path)
    assert _attached(index) == {
        "night.edf": [("night_scorer2.edf", "scorer2")],
        "night_2.edf": [],
        "night_long.edf": [("night_long_scorer1.edf", "scorer1")],
    }
    assert (index.unassigned, index.ambiguous, index.unmatched_rows) == (0, 0, 0)


def test_tie_breaks_same_folder_then_nearest_common_folder(tmp_path: Path) -> None:
    for name in ("a/night.edf", "b/night.edf", "x/y/rest.edf", "z/rest.edf"):
        _night(tmp_path, name)
    _hypnogram(tmp_path, "a/night_s1.edf")
    _hypnogram(tmp_path, "x/hyp/rest_s2.edf")
    attached = _attached(_index(tmp_path))
    assert attached["a/night.edf"] == [("a/night_s1.edf", "s1")] and attached["b/night.edf"] == []
    assert attached["x/y/rest.edf"] == [("x/hyp/rest_s2.edf", "s2")] and attached["z/rest.edf"] == []


def test_ambiguous_and_unassigned_files_are_objects_of_their_own(tmp_path: Path) -> None:
    for name in ("a/night.edf", "b/night.edf"):
        _night(tmp_path, name)
    _hypnogram(tmp_path, "c/night_s1.edf")  # both nights equally near: ambiguous
    _hypnogram(tmp_path, "other_s1.edf")  # matches nothing
    index = _index(tmp_path)
    assert (index.ambiguous, index.unassigned) == (1, 1)
    own = {obj.found.relative.as_posix(): obj for obj in index.objects if obj.unassigned}
    assert sorted(own) == ["c/night_s1.edf", "other_s1.edf"]
    assert [t.annotator for t in own["other_s1.edf"].tracks] == ["default"]
    ctx = _context(tmp_path)
    ctx.annotations()
    notices = {n.message_key: n.params["count"] for n in checks.notices(ctx)}
    assert notices == {"notice.annotations_unassigned": 1, "notice.annotations_ambiguous": 1}


def test_files_table_wins_and_unmatched_rows_are_counted(tmp_path: Path) -> None:
    _night(tmp_path, "night.edf")
    _night(tmp_path, "day.edf")
    _hypnogram(tmp_path, "night_s1.edf")
    _hypnogram(tmp_path, "scoring/h2.edf")
    toml = (
        '[[annotation.files]]\npath = "night_s1.edf"\nrecording = "day.edf"\nannotator = "lead"\n'
        '[[annotation.files]]\npath = "scoring\\\\h2.edf"\nrecording = "night.edf"\n'
        '[[annotation.files]]\npath = "missing.edf"\nrecording = "night.edf"\n'
        '[[annotation.files]]\npath = "night.edf"\nrecording = "day.edf"\n'  # a signal file: not attached
    )
    index = _index(tmp_path, toml)
    assert _attached(index) == {
        "day.edf": [("night_s1.edf", "lead")],
        "night.edf": [("scoring/h2.edf", "h2")],
    }
    assert index.unmatched_rows == 2


def test_annotator_patterns_restrict_the_annotators(tmp_path: Path) -> None:
    _night(tmp_path, "night.edf")
    for scorer in ("manual_scorer1", "manual_scorer2", "semiauto_scorer1", "auto"):
        _hypnogram(tmp_path, f"night_{scorer}.edf")
    (obj,) = _index(tmp_path, '[annotation]\nannotators = ["manual_*"]\n').objects
    assert [t.annotator for t in obj.tracks] == ["manual_scorer1", "manual_scorer2"]
    assert obj.excluded_annotators == 2 and len(obj.attached) == 4
    (obj,) = _index(tmp_path).objects
    assert len(obj.tracks) == 4 and obj.excluded_annotators == 0


def test_index_issues_and_by_recording(tmp_path: Path) -> None:
    _night(tmp_path, "night.edf")
    _hypnogram(tmp_path, "night_s1.edf")
    (tmp_path / "night_s2.edf").write_bytes(b"0" * 300)  # not a hypnogram: a broken recording of its own
    index = _index(tmp_path)
    objects = {obj.found.relative.as_posix(): obj for obj in index.objects}
    assert objects["night_s2.edf"].issue == "header.unreadable"
    assert objects["night.edf"].issue is None
    by_recording = index.by_recording()
    assert [a.code for a in by_recording[PurePosixPath("night.edf")]] == ["W", "N1"]
    assert {a.recording_id for a in by_recording[PurePosixPath("night.edf")]} == {
        pseudonym(PurePosixPath("night.edf"))
    }
    bad = tmp_path / "night_s3.edf"
    _annotation_file(bad, b"+0\x14\x14\x00garbage\x00")
    (obj,) = [o for o in _index(tmp_path).objects if o.found.relative.as_posix() == "night.edf"]
    assert obj.issue == "annotation.unreadable" and obj.tracks == ()


# --- κ, gaps, overlaps --------------------------------------------------------------------------------------


def test_cohen_kappa_exact() -> None:
    assert checks.cohen_kappa([1, 1, 2, 2], [1, 2, 2, 2]) == Fraction(1, 2)  # po 3/4, pe 1/2
    assert checks.cohen_kappa(list("aabb"), list("aabb")) == 1
    assert checks.cohen_kappa(list("aaaa"), list("aaaa")) is None  # expected agreement 1
    assert checks.cohen_kappa([], []) is None and checks.cohen_kappa([1], [1, 2]) is None
    assert checks.cohen_kappa(list("ab"), list("ba")) == -1


def _a(onset: float, duration: float, code: str) -> Annotation:
    return Annotation(onset_s=onset, duration_s=duration, code=code)


def _grid(
    duration: float, epoch: float = 30.0, data: tuple[tuple[float, float], ...] | None = None
) -> checks.Grid:
    epochs = int((duration + checks.TIME_TOLERANCE_S) // epoch)
    return checks.Grid(duration_s=duration, epoch_s=epoch, epochs=epochs, data=data or ((0.0, duration),))


def test_epoch_classes_midpoints_combined_classes_and_floor_grid() -> None:
    frame = _grid(100.0)  # three complete epochs; 90-100 s are not scored
    annotations = [
        _a(0.0, 30.0, "W"),
        _a(10.0, 10.0, "Arousal"),  # covers the midpoint 15 together with W
        _a(30.0, 0.0, "Lights off"),  # zero duration: never a class
        _a(45.0, 15.0, "N1"),  # starts at the midpoint 45: covers it (half-open)
        _a(60.0, 15.0, "N2"),  # ends at the midpoint 75: does not cover it
        _a(90.0, 10.0, "N3"),  # partial last epoch
    ]
    assert checks.epoch_classes(annotations, frame) == [("Arousal", "W"), ("N1",), ()]


def test_kappa_of_an_object_with_three_annotators_and_undefined_pairs() -> None:
    found = FoundFile(PurePosixPath("night.edf"), "rec-x", ".edf", 0)

    def track(name: str, stages: str) -> reader.Track:
        return reader.Track(
            name, tuple(_a(30.0 * i, 30.0, s) for i, s in enumerate(stages.split())), "annotation_file", found
        )

    obj = reader.AnnotatedRecording(
        found=found,
        duration_s=120.0,
        tracks=(track("s1", "W W N1 N1"), track("s2", "W N1 N1 N1"), track("s3", "W W N1 N1")),
    )
    result = checks.kappa(obj, _grid(120.0))
    assert result is not None
    assert result.pairs[0][2] == 0.5 and result.minimum == 0.5 and result.mean == pytest.approx(2 / 3)
    assert (result.annotators, result.epochs, result.undefined_pairs) == (3, 4, 0)
    flat = reader.AnnotatedRecording(
        found=found, duration_s=60.0, tracks=(track("s1", "W W"), track("s2", "W W"))
    )
    assert checks.kappa(flat, _grid(60.0)) is None  # the only pair has no kappa


def test_kappa_skips_epochs_in_record_gaps() -> None:
    frame = _grid(150.0, data=((0.0, 60.0), (90.0, 150.0)))
    assert [frame.counted(e) for e in range(frame.epochs)] == [True, True, False, True, True]
    assert frame.counted_mask().tolist() == [True, True, False, True, True]
    assert frame.scored == ((0.0, 60.0), (90.0, 150.0))
    late = _grid(150.0, data=((40.0, 150.0),))
    assert late.counted_mask().tolist() == [False, True, True, True, True] and not late.counted(0)


def test_interval_helpers_are_linear_merges() -> None:
    assert checks._intersect([(0.0, 10.0), (20.0, 30.0)], [(5.0, 25.0), (28.0, 40.0)]) == [
        (5.0, 10.0),
        (20.0, 25.0),
        (28.0, 30.0),
    ]
    frame = _grid(150.0, data=((0.0, 60.0), (90.0, 150.0)))
    missing, coverage = checks.gaps([_a(0.0, 70.0, "W"), _a(100.0, 50.0, "W")], frame)
    assert missing == [(90.0, 100.0)] and coverage == pytest.approx(110.0 / 120.0)


def test_epoch_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _night(tmp_path, "night.edf")
    _hypnogram(tmp_path, "night_s1.edf", ("W", "N1"))
    _hypnogram(tmp_path, "night_s2.edf", ("W", "W"))
    monkeypatch.setattr(checks, "MAX_EPOCHS", 1)
    ctx = _context(tmp_path, '[annotation]\nmode = "continuous"\n')
    (measured,) = checks.measure_kappa(ctx)
    assert (measured.state, measured.reason) == ("not_checkable", "annotation.too_many_epochs")
    (summary,) = checks.summaries(ctx).values()
    assert summary["kappa"] is None and summary["epochs"] is None  # no huge numbers in results.json


def test_gaps_and_coverage() -> None:
    frame = _grid(310.0)  # ten complete epochs, the last 10 s are not scored
    annotations = [_a(30.0 * i, 30.0, "W") for i in range(10) if i not in (0, 4, 5)]
    annotations.append(_a(150.0, 29.9995, "N1"))  # a sub-millisecond rest is no gap
    missing, coverage = checks.gaps(annotations, frame)
    assert missing == [(0.0, 30.0), (120.0, 150.0)]  # a leading and an inner gap
    assert coverage == pytest.approx(240.0 / 310.0)  # of the whole recording; the 0.5-ms rest is joined
    many = [_a(10.0 * i, 5.0, "W") for i in range(30)]
    missing, _ = checks.gaps(many, frame)
    ranges = checks._ranges(missing)
    assert len(ranges["time_ranges"]) == 20 and ranges["time_ranges_total"] == 30
    assert ranges["time_ranges_duration_s"] == pytest.approx(150.0)


def test_overlaps_continuous_and_events_mode() -> None:
    annotations = [
        _a(0.0, 30.0, "W"),
        _a(30.0, 30.0, "W"),  # touches the first: no overlap
        _a(50.0, 20.0, "N1"),  # overlaps 50-60 with another code
        _a(65.0, 0.0, "N1"),  # zero duration: never overlaps
        _a(100.0, 10.0, "N2"),
        _a(105.0, 10.0, "N2"),  # same code: 105-110
        _a(100.0000001, 10.0, "N3"),  # overlaps N2 by 10 s with another code
    ]
    assert checks.overlaps(annotations, same_code=False) == [(50.0, 60.0), (100.0000001, 110.0000001)]
    assert checks.overlaps(annotations, same_code=True) == [(105.0, 110.0)]
    tiny = [_a(0.0, 30.0, "W"), _a(29.9999, 30.0, "W")]
    assert checks.overlaps(tiny, same_code=False) == []


# --- display (A-17, C5) -------------------------------------------------------------------------------------


def test_display_text_rule() -> None:
    assert display_text("Sleep stage W") == ("Sleep stage W", "Sleep stage W")
    assert display_text("Auditory/Left") == ("Auditory/Left", "Auditory/Left")
    for hidden in ("Max Mustermann", "Sleep stage ?", "a" * 33, "张伟", "1234567", "C:/data/x", "a\tb"):
        shown, subkey = display_text(hidden)
        assert shown is None and subkey.startswith("text-") and len(subkey) == 13
        assert display_text(hidden) == (shown, subkey)  # stable
    assert display_text("Max Mustermann", ("Max Mustermann",)).shown == "Max Mustermann"  # vocabulary
    assert display_text("Sleep stage ?", ["Sleep stage ?"]).subkey == "Sleep stage ?"
    assert annotator_pseudonym("scorer1") == annotator_pseudonym("scorer1") != annotator_pseudonym("scorer2")
    assert annotator_pseudonym("\udcff").startswith("ann-")  # names that are not valid Unicode


def test_free_text_codes_and_annotators_never_appear(tmp_path: Path) -> None:
    _night(tmp_path, "night.edf")
    _hypnogram(tmp_path, "night_Max_Mustermann.edf", ("Max Mustermann", "W"))
    _hypnogram(tmp_path, "night_s2.edf", ("W", "W"))
    toml = '[annotation]\nmode = "continuous"\nvocabulary = ["W"]\n'
    for show in (False, True):
        ctx = _context(tmp_path, toml, show_paths=show)
        measured = [m for check in checks.MEASURERS.values() for m in check(ctx)]
        text = repr([(m.object, m.subkey, m.file, m.value, dict(m.details)) for m in measured])
        assert "Max Mustermann" not in text  # the code itself is free text
        assert ("Mustermann" in text) is show  # the file name and the annotator from it: --show-paths only
        code = next(m for m in measured if m.check_id == checks.CODES and m.value is False)
        assert code.subkey == display_text("Max Mustermann").subkey and code.details["chars"] == 14
        subkeys = sorted(m.subkey or "" for m in measured if m.check_id == checks.GAPS)
        assert subkeys == sorted(annotator_pseudonym(n) for n in ("Max_Mustermann", "s2"))
        details = [dict(m.details) for m in measured if m.check_id == checks.GAPS]
        assert any(d.get("annotator") == "Max_Mustermann" for d in details) is show


# --- measurements of the whole dataset ----------------------------------------------------------------------


def _states(measured: list[Any]) -> list[tuple[str, str, str | None]]:
    return sorted((m.object, m.state, m.reason) for m in measured)


def test_dataset_level_measurements_without_annotations(tmp_path: Path) -> None:
    _night(tmp_path, "night.edf")
    ctx = _context(tmp_path)
    for check, reason in (
        (checks.measure_kappa, "annotation.none"),
        (checks.measure_codes, "annotation.none"),
        (checks.measure_gaps, "annotation.event_mode"),
        (checks.measure_overlaps, "annotation.none"),
    ):
        assert _states(check(ctx)) == [("dataset", "not_applicable", reason)]
    continuous = _context(tmp_path, '[annotation]\nmode = "continuous"\n')
    (uncovered,) = checks.measure_gaps(continuous)
    assert uncovered.value == {"gaps": 1, "gap_s": 60.0, "coverage": 0.0}  # A-80: coverage 0
    assert uncovered.time_ranges[0].start_s == 0.0 and uncovered.time_ranges[0].end_s == 60.0


def test_per_object_states(tmp_path: Path) -> None:
    _night(tmp_path, "a.edf")
    _night(tmp_path, "b.edf")
    _night(tmp_path, "c.edf")
    _hypnogram(tmp_path, "a_s1.edf", ("W", "N1"))
    _hypnogram(tmp_path, "a_s2.edf", ("W", "W"))
    _hypnogram(tmp_path, "b_s1.edf", ("W", "N1"))
    ctx = _context(tmp_path, '[annotation]\nmode = "continuous"\n')
    a, b, c = (pseudonym(PurePosixPath(name)) for name in ("a.edf", "b.edf", "c.edf"))
    assert _states(checks.measure_kappa(ctx)) == sorted(
        [
            (a, "measured", None),
            (b, "not_applicable", "annotation.single_annotator"),
            (c, "not_applicable", "annotation.none"),
        ]
    )
    codes = checks.measure_codes(ctx)
    assert _states(codes) == [("dataset", "not_applicable", "annotation.no_vocabulary")]
    overlaps = {(m.object, m.state, m.reason) for m in checks.measure_overlaps(ctx)}
    assert (c, "not_applicable", "annotation.none") in overlaps
    gaps = [m for m in checks.measure_gaps(ctx) if m.object == c]
    assert [m.value["coverage"] for m in gaps] == [0.0]  # signals without annotation (A-80)


def test_kappa_states_too_short_undefined_and_epoched(tmp_path: Path) -> None:
    _night(tmp_path, "night.edf")
    _hypnogram(tmp_path, "night_s1.edf", ("W", "W"))
    _hypnogram(tmp_path, "night_s2.edf", ("W", "W"))
    (undefined,) = checks.measure_kappa(_context(tmp_path, '[annotation]\nmode = "continuous"\n'))
    assert (undefined.state, undefined.reason) == ("not_checkable", "annotation.kappa_undefined")
    (short,) = checks.measure_kappa(_context(tmp_path, '[annotation]\nmode = "continuous"\nepoch_s = 120\n'))
    assert (short.state, short.reason) == ("not_checkable", "annotation.too_short")
    (gaps_short,) = checks.measure_gaps(
        _context(tmp_path, '[annotation]\nmode = "continuous"\nepoch_s = 120\n')
    )
    assert gaps_short.reason == "annotation.too_short"
    epoched = tmp_path / "ep"
    epoched.mkdir()
    write_eeglab(
        epoched / "rec.set", sfreq=64, seconds=4, labels=("Fz",), trials=2, events=(("x", 1.0, 64.0),)
    )
    ctx = _context(epoched, '[annotation]\nmode = "continuous"\n')
    for check in (checks.measure_gaps, checks.measure_overlaps):
        assert [m.reason for m in check(ctx)] == ["annotation.epoched"]


def test_unreadable_objects_are_not_checkable(tmp_path: Path) -> None:
    _night(tmp_path, "night.edf")
    _annotation_file(tmp_path / "night_s1.edf", b"+0\x14\x14\x00garbage\x00")
    ctx = _context(tmp_path, '[annotation]\nmode = "continuous"\n')
    for check in checks.MEASURERS.values():
        reasons = {m.reason for m in check(ctx) if m.state == "not_checkable"}
        assert reasons == {"annotation.unreadable"}
    summary = checks.summaries(ctx)[PurePosixPath("night.edf")]
    assert summary["issue"] == "annotation.unreadable" and summary["kappa"] is None


def test_codes_and_labels(tmp_path: Path) -> None:
    events = (
        "onset\tduration\ttrial_type\n"
        "1\t0.5\tstandard\n2\t0.5\ttarget\n3\t0.5\tdeviant\n4\t0\tMax Mustermann\n"
    )
    sidecar = {"trial_type": {"Levels": {"standard": "Tone", "target": "Tone", "deviant": "Odd tone"}}}
    root = _bids(tmp_path / "ds", events, sidecar)
    measured = checks.measure_codes(_context(root))
    by_subkey = {m.subkey: m for m in measured}
    assert by_subkey["standard"].value is True and by_subkey["target"].value is True
    hidden = by_subkey[display_text("Max Mustermann").subkey]
    assert hidden.value is False and hidden.details == {"count": 1, "chars": 14}
    assert by_subkey["label:Tone"].value is False and by_subkey["label:Tone"].object == "dataset"
    assert by_subkey["label:Tone"].details == {"n_codes": 2, "codes": ["standard", "target"]}
    assert by_subkey["label:Odd tone"].value is True
    # the vocabulary of neurogrid.toml wins over events.json Levels
    toml = '[annotation]\nvocabulary = [" standard ", "Max Mustermann"]\n'
    by_subkey = {m.subkey: m for m in checks.measure_codes(_context(root, toml))}
    assert by_subkey["Max Mustermann"].value is True and by_subkey["deviant"].value is False


def test_summary_values(tmp_path: Path) -> None:
    ctx = _context(FIX / "annotation_continuous_ok", '[annotation]\nmode = "continuous"\n')
    assert checks.summaries(ctx) == {}  # nothing read yet: no summary
    checks.measure_kappa(ctx)
    (entry,) = checks.summaries(ctx).values()
    assert entry["mode"] == "continuous" and entry["epoch_s"] == 30.0 and entry["epochs"] == 10
    assert entry["kappa"]["pairs"] == 3 and entry["kappa"]["min"] == 0.5
    assert entry["coverage"] == {annotator_pseudonym(f"scorer{n}"): 1.0 for n in (1, 2, 3)}
    assert entry["files"] == [pseudonym(PurePosixPath(f"night_scorer{n}.edf")) + ".edf" for n in (1, 2, 3)]
    assert entry["sources"] == ["annotation_file"] and entry["annotations"] == 31


# --- configuration ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("toml", "key", "field"),
    [
        ('[annotation]\nvocabulary = ["' + "x" * 257 + '"]\n', "config.invalid", "annotation.vocabulary.0"),
        ("[annotation]\nvocabulary = []\n", "config.invalid", "annotation.vocabulary"),
        ('[annotation]\nannotators = [""]\n', "config.invalid", "annotation.annotators.0"),
        ("[annotation]\nepoch_s = 0\n", "config.invalid", "annotation.epoch_s"),
        ("[annotation]\nepoch_s = 90000\n", "config.invalid", "annotation.epoch_s"),
        ('[annotation]\nmode = "sleep"\n', "config.invalid", "annotation.mode"),
        ("[annotation]\nunknown = 1\n", "config.invalid", "annotation.unknown"),
        (
            '[[annotation.files]]\npath = "a.edf"\nrecording = "b.edf"\nannotator = "Max Mustermann"\n',
            "config.invalid",
            "annotation.files.0.annotator",
        ),
        ('[[annotation.files]]\npath = "../a.edf"\nrecording = "b.edf"\n', "config.unsafe_path", None),
        ('[[annotation.files]]\npath = "a.edf"\nrecording = "C:/b.edf"\n', "config.unsafe_path", None),
        ('[[annotation.files]]\npath = "a.edf"\n', "config.invalid", "annotation.files.0.recording"),
    ],
)
def test_annotation_config_is_validated_strictly(toml: str, key: str, field: str | None) -> None:
    with pytest.raises(ConfigError) as info:
        config_module.parse(toml)
    assert info.value.message_key == key
    if field is not None:
        assert info.value.params["field"] == field
    else:
        assert info.value.params["field"].startswith("annotation.files.0.")


def test_annotation_config_accepts_the_documented_keys() -> None:
    cfg = config_module.parse(
        '[annotation]\nmode = "continuous"\nepoch_s = 30\nvocabulary = ["W", "N1"]\n'
        'annotators = ["manual_*"]\n'
        '[[annotation.files]]\npath = "hyp/s1.edf"\nrecording = "night.edf"\nannotator = "scorer.1-a"\n'
    )
    assert cfg.annotation.files[0].annotator == "scorer.1-a" and cfg.annotation.annotators == ["manual_*"]


@dataclass
class _Plain:
    found: FoundFile
    path: Path
    recording: Recording | None
    annotations_only: bool


def test_build_index_with_plain_sources(tmp_path: Path) -> None:
    """The index needs only what the SourceRecording protocol names (e.g. for the [ai] labels source)."""
    _night(tmp_path, "night.edf")
    _hypnogram(tmp_path, "night_s1.edf")
    ctx = _context(tmp_path)
    plain = [_Plain(r.found, r.path, r.recording, r.annotations_only) for r in ctx.recordings]
    index = build_index(tmp_path, plain, is_bids=False)
    assert [len(obj.tracks) for obj in index.objects] == [1]


# --- P4 review: bounded times and header sizes (R7: ANN00, CON47, INT40, ANN01) -----------------------------


@pytest.mark.parametrize(
    ("onset", "duration", "valid"),
    [
        (1.0, 0.5, True),
        (-0.5, 0.25, True),  # before the start of the recording (EDF+ allows it)
        (999_999_999.0, 1.0, True),  # ends at the limit
        (-1e9, 0.0, True),
        (1e308, 1e308, False),  # each finite, their end is not (ANN00)
        (2.0, 1.7e308, False),  # a finite end after 10^9 s
        (1e9, 1.0, False),
        (-1e9 - 1.0, 10.0, False),
        (math.nan, 0.0, False),
        (0.0, math.inf, False),
    ],
)
def test_valid_times_are_finite_and_bounded(onset: float, duration: float, valid: bool) -> None:
    assert reader.valid_times(onset, duration) is valid


def test_events_rows_whose_times_are_not_valid_are_counted(tmp_path: Path) -> None:
    """ANN00, CON47, INT40: onset and duration are finite on their own, their end is not or lies after
    10^9 s: invalid rows (notice.events_rows_invalid), never an annotation (A-53)."""
    events = (
        "onset\tduration\ttrial_type\tannotator\n"
        "1\t0.5\tstim\tA1\n"
        "1e308\t1e308\tstim\tA1\n"
        "9e307\t9e307\tstim\tA2\n"
        "2\t1.7e308\tstim\tA2\n"
        "-2e9\t0\tstim\tA1\n"
        "999999999\t1\tstim\tA2\n"  # ends exactly at the limit: an annotation
    )
    root = _bids(tmp_path / "ds", events)
    relative = PurePosixPath("sub-01/eeg/sub-01_task-x_eeg.edf")
    table = reader.read_events(root, relative)
    assert table is not None
    found = reader.events_annotations(root, relative, table)
    assert [(a.onset_s, a.duration_s) for a in found.annotations] == [(1.0, 0.5), (999_999_999.0, 1.0)]
    assert found.invalid_rows == 4


def test_overflowing_rows_never_reach_the_measurements(tmp_path: Path) -> None:
    """The reviewers' crash cases: two annotators (math.ceil(inf) in the epoch classes), one annotator with
    two such rows (an infinite overlap) and an unknown code (an infinite time range) are measured normally."""
    events = (
        "onset\tduration\ttrial_type\tannotator\n"
        "1\t2\tstim\tA1\n1\t2\tstim\tA2\n4\t2\tresp\tA1\n4\t2\tresp\tA2\n"
        "1e308\t1e308\tstim\tA1\n1e308\t1e308\tstim\tA1\n1e308\t1e308\tstimx\tA2\n"
    )
    root = _bids(
        tmp_path / "ds", events, {"trial_type": {"Levels": {"stim": "Stimulus", "resp": "Response"}}}
    )
    ctx = _context(root)
    measured = [m for check in checks.MEASURERS.values() for m in check(ctx)]
    (kappa,) = [m for m in measured if m.check_id == checks.KAPPA]
    assert kappa.value == 1.0
    assert display_text("stimx").subkey not in {m.subkey for m in measured}  # the row was no annotation
    assert all(math.isfinite(m.value["overlap_s"]) for m in measured if m.check_id == checks.OVERLAPS)
    notices = {n.message_key: n.params["count"] for n in checks.notices(ctx)}
    assert notices == {"notice.events_rows_invalid": 3}


@pytest.mark.parametrize(
    "tal",
    [
        b"+0\x14\x14\x00+1000000001\x14late\x14\x00",  # starts after 10^9 s
        b"+0\x14\x14\x00+999999999\x152\x14long\x14\x00",  # ends after 10^9 s
        b"+0\x14\x14\x00-1000000001\x14early\x14\x00",  # starts before -10^9 s
    ],
)
def test_tal_times_beyond_the_limit_make_the_file_unreadable(tmp_path: Path, tal: bytes) -> None:
    with pytest.raises(AnnotationsUnreadable) as info:
        reader.read_edf_tal(_annotation_file(tmp_path / "far.edf", tal))
    assert info.value.reason == "annotation.unreadable"
    ok = _annotation_file(tmp_path / "ok.edf", b"+0\x14\x14\x00+999999999\x151\x14end\x14\x00")
    assert _codes(reader.read_edf_tal(ok)) == [(999_999_999.0, 1.0, "end")]


def test_edf_plus_d_record_onset_beyond_the_limit_is_unreadable(tmp_path: Path) -> None:
    ok = _annotation_file(tmp_path / "ok.edf", b"+5\x14\x14\x00", plus="D", record_s=1)
    assert reader.read_edf_tal(ok).data_intervals == ((5.0, 6.0),)
    far = _annotation_file(tmp_path / "far.edf", b"+2000000000\x14\x14\x00", plus="D", record_s=1)
    with pytest.raises(AnnotationsUnreadable):
        reader.read_edf_tal(far)


def test_vmrk_marker_beyond_the_limit_is_unreadable(tmp_path: Path) -> None:
    vhdr = tmp_path / "rec.vhdr"
    write_brainvision(vhdr, sfreq=500, seconds=1, labels=("Fz",))
    _vmrk(vhdr, "Mk1=Stimulus,S 1,501,1,0\nMk2=Stimulus,S 2,600000000001,1,0\n")  # 1.2 * 10^9 s at 500 Hz
    with pytest.raises(AnnotationsUnreadable):
        reader.read_vmrk(vhdr)


def test_eeglab_event_whose_onset_overflows_is_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sampling rate far below 1 Hz: (latency - 1) / srate overflows to infinity (ANN00)."""
    events: dict[str, Any] = {"srate": 1e-300, "event": {"type": "x", "latency": 1e300}}
    monkeypatch.setattr(reader, "load_events", lambda _path: events)
    with pytest.raises(AnnotationsUnreadable):
        reader.read_eeglab_events(tmp_path / "rec.set")
    events.update(srate=100.0, event={"type": "x", "latency": 11.0, "duration": 5.0})
    assert _codes(reader.read_eeglab_events(tmp_path / "rec.set")) == [(0.1, 0.05, "x")]


@pytest.mark.parametrize(
    ("latency", "duration"), [(math.inf, 5.0), (-math.inf, 5.0), (11.0, math.inf), (11.0, "-Inf")]
)
def test_eeglab_infinite_times_make_the_events_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, latency: float, duration: float | str
) -> None:
    """R7: an infinite latency or duration is damage (formerly read as "no latency" or duration 0 without a
    trace); a NaN latency stays an event EEGLAB ignores and MNE drops, a NaN duration is 0 as before."""
    rows = {"type": ["x", "y"], "latency": [21.0, latency], "duration": [0.0, duration]}
    events: dict[str, Any] = {"srate": 100.0, "event": rows}
    monkeypatch.setattr(reader, "load_events", lambda _path: events)
    with pytest.raises(AnnotationsUnreadable):
        reader.read_eeglab_events(tmp_path / "rec.set")
    rows.update(latency=[21.0, math.nan], duration=[math.nan, 5.0])
    assert _codes(reader.read_eeglab_events(tmp_path / "rec.set")) == [(0.2, 0.0, "x")]
    rows["type"] = ["x", "boundary"]  # a structural marker is no annotation, whatever its times
    rows.update(latency=[21.0, math.inf])
    assert _codes(reader.read_eeglab_events(tmp_path / "rec.set")) == [(0.2, 0.0, "x")]


@pytest.mark.parametrize(
    ("onset", "duration"), [(math.nan, 0.0), (1.0, math.inf), (2e9, 0.0), (1.0, -math.inf)]
)
def test_fif_annotation_times_that_are_not_valid_make_it_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, onset: float, duration: float
) -> None:
    """Formerly dropped without a trace (non-finite) or kept (after 10^9 s): now the source is unreadable."""
    stored = SimpleNamespace(onset=[1.0, onset], duration=[0.5, duration], description=["stim", "far"])
    monkeypatch.setattr(reader, "_unsafe_split", lambda _path: False)
    monkeypatch.setattr(reader, "_raw", lambda _path: SimpleNamespace(annotations=stored, first_time=0.0))
    with pytest.raises(AnnotationsUnreadable):
        reader.read_fif_annotations(tmp_path / "rec_raw.fif")
    stored.onset, stored.duration = [1.0, 2.0], [0.5, -1.0]  # a negative duration is 0 (MNE)
    assert _codes(reader.read_fif_annotations(tmp_path / "rec_raw.fif")) == [
        (1.0, 0.5, "stim"),
        (2.0, 0.0, "far"),
    ]


def test_grid_and_epoch_classes_stay_finite_for_any_time() -> None:
    """R7 defence in depth: values the readers never let through, and an epoch length so small that the
    quotient overflows, end neither in OverflowError nor in an infinite grid."""
    huge = [_a(0.0, 1e308, "W"), _a(1e308, 1e308, "N1"), _a(-1e308, 1e308, "N2"), _a(30.0, math.inf, "R")]
    assert checks.epoch_classes(huge, _grid(90.0)) == [("W",), ("W",), ("W",)]
    tiny = checks.Grid(duration_s=90.0, epoch_s=5e-324, epochs=3, data=((0.0, 90.0),))
    assert checks.epoch_classes([_a(1e10, 1.0, "W"), _a(-1e10, 2e10, "N1")], tiny) == [("N1",)] * 3
    found = FoundFile(PurePosixPath("hyp.edf"), "rec-x", ".edf", 0)
    track = reader.Track("default", (_a(0.0, 30.0, "W"), _a(1e308, 1e308, "N1")), "edf_tal", found)
    own = reader.AnnotatedRecording(found=found, duration_s=None, tracks=(track,), unassigned=True)
    frame = checks.grid(own, 30.0)
    assert (
        frame is not None and frame.duration_s == 30.0 and frame.epochs == 1
    )  # the infinite end is left out
    assert checks.grid(reader.AnnotatedRecording(found=found, duration_s=300.0), 5e-324) is None


@pytest.mark.parametrize("plus", ["C", "D"])
@pytest.mark.parametrize("size", [b"-1      ", b"-768    ", b"256     "])
def test_header_size_below_the_header_makes_the_annotations_unreadable(
    tmp_path: Path, plus: str, size: bytes
) -> None:
    """ANN01: a negative header size made numpy's memory map raise OverflowError (exit 2); a size below the
    fixed and signal headers holds no data offset either. M01 reports the header (header.size_field)."""
    path = tmp_path / "rec.edf"
    write_edf(path, sfreq=8, seconds=3, labels=("Fz",), plus=plus, annotations=((0.5, 1.0, "W"),))
    assert _codes(reader.read_edf_tal(path)) == [(0.5, 1.0, "W")]
    raw = bytearray(path.read_bytes())
    raw[184:192] = size
    path.write_bytes(bytes(raw))
    with pytest.raises(AnnotationsUnreadable) as info:
        reader.read_edf_tal(path)
    assert info.value.reason == "annotation.unreadable"


# --- P4 review: who takes part in kappa, gaps and overlaps (R9: ANN03, ANN04) -------------------------------


def _marker_night(root: Path, relative: str = "night.edf") -> None:
    """A signal EDF+C whose only annotations are the technician's zero-duration markers (a PSG export)."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    markers = ((12.0, 0.0, "Lights off"), (50.0, 0.0, "Lights on"))
    write_edf(path, sfreq=8, seconds=60, labels=("C3",), plus="C", annotations=markers)


def test_a_track_of_markers_only_counts_for_the_codes_alone(tmp_path: Path) -> None:
    """ANN03: the markers in the signal file are no rater: two identical scorers give kappa 1.0 (not 0.33)
    and no gaps failure for 'default'; the markers are still judged as codes and counted as [ai] labels."""
    _marker_night(tmp_path)
    _hypnogram(tmp_path, "night_s1.edf", ("W", "N1"))
    _hypnogram(tmp_path, "night_s2.edf", ("W", "N1"))
    ctx = _context(tmp_path, '[annotation]\nmode = "continuous"\nvocabulary = ["W", "N1", "Lights off"]\n')
    (obj,) = ctx.annotations().objects
    assert [t.annotator for t in obj.tracks] == ["default", "s1", "s2"]
    assert [t.annotator for t in checks.scored_tracks(obj)] == ["s1", "s2"]
    (kappa,) = checks.measure_kappa(ctx)
    assert kappa.value == 1.0 and (kappa.details["annotators"], kappa.details["pairs"]) == (2, 1)
    scorers = sorted(annotator_pseudonym(n) for n in ("s1", "s2"))
    gaps = checks.measure_gaps(ctx)
    assert sorted(m.subkey or "" for m in gaps) == scorers and {m.value["coverage"] for m in gaps} == {1.0}
    assert sorted(m.subkey or "" for m in checks.measure_overlaps(ctx)) == scorers
    codes = {m.subkey: m.value for m in checks.measure_codes(ctx)}
    assert codes == {"Lights off": True, "Lights on": False, "N1": True, "W": True}  # markers count here
    labels = {a.code for a in ctx.annotations().by_recording()[PurePosixPath("night.edf")]}
    assert {"Lights off", "Lights on"} <= labels  # [ai] labels = "annotations" (A-81)
    (summary,) = checks.summaries(ctx).values()
    assert summary["annotators"] == [annotator_pseudonym(n) for n in ("default", "s1", "s2")]
    assert summary["kappa"]["annotators"] == 2 and summary["kappa"]["mean"] == 1.0
    assert sorted(summary["coverage"]) == scorers


def test_a_signal_recording_with_markers_only_is_uncovered(tmp_path: Path) -> None:
    """The same signal file alone: no scored annotation, so coverage 0 for the recording (A-80); kappa and
    overlaps name the reason markers_only, per recording when another recording has scorers."""
    _marker_night(tmp_path)
    ctx = _context(tmp_path, '[annotation]\nmode = "continuous"\n')
    (gap,) = checks.measure_gaps(ctx)
    assert gap.subkey is None and gap.value == {"gaps": 1, "gap_s": 60.0, "coverage": 0.0}
    for check in (checks.measure_kappa, checks.measure_overlaps):
        assert _states(check(ctx)) == [("dataset", "not_applicable", "annotation.markers_only")]
    _night(tmp_path, "day.edf")
    _hypnogram(tmp_path, "day_s1.edf", ("W", "N1"))
    _hypnogram(tmp_path, "day_s2.edf", ("W", "W"))
    states = _states(checks.measure_kappa(_context(tmp_path, '[annotation]\nmode = "continuous"\n')))
    night, day = pseudonym(PurePosixPath("night.edf")), pseudonym(PurePosixPath("day.edf"))
    assert states == sorted([(day, "measured", None), (night, "not_applicable", "annotation.markers_only")])


def test_bids_markers_without_annotator_next_to_two_scorers(tmp_path: Path) -> None:
    """ANN03 in BIDS: stimulus markers (duration 0, no annotator) and two scorers in one events.tsv."""
    events = (
        "onset\tduration\ttrial_type\tannotator\n"
        "1\t0\tbeep\tn/a\n5\t0\tbeep\tn/a\n"
        "0\t10\tW\tA1\n10\t10\tN1\tA1\n0\t10\tW\tA2\n10\t10\tN1\tA2\n"
    )
    ctx = _context(_bids(tmp_path / "ds", events))
    (kappa,) = checks.measure_kappa(ctx)
    assert kappa.value == 1.0 and kappa.details["annotators"] == 2
    overlaps = {m.subkey for m in checks.measure_overlaps(ctx)}
    assert overlaps == {annotator_pseudonym("A1"), annotator_pseudonym("A2")}


def test_an_attached_file_without_annotation_is_an_annotator_with_coverage_0(tmp_path: Path) -> None:
    """ANN04: one file per annotator (A-80); a scorer file without annotations (a failed export) is no longer
    dropped: coverage 0 fails CORE-M10-03, it takes no part in kappa and is listed in the summary."""
    _night(tmp_path, "night.edf")
    _hypnogram(tmp_path, "night_s1.edf", ("W", "N1"))
    _hypnogram(tmp_path, "night_s2.edf", ("W", "W"))
    write_annotation_edf(tmp_path / "night_s3.edf", ())
    toml = '[annotation]\nmode = "continuous"\n'
    ctx = _context(tmp_path, toml)
    (obj,) = ctx.annotations().objects
    assert [(t.annotator, len(t.annotations)) for t in obj.tracks] == [("s1", 2), ("s2", 2), ("s3", 0)]
    (kappa,) = checks.measure_kappa(ctx)
    assert kappa.details["annotators"] == 2
    empty = {m.subkey: m for m in checks.measure_gaps(ctx)}[annotator_pseudonym("s3")]
    assert empty.value == {"gaps": 1, "gap_s": 60.0, "coverage": 0.0}
    assert empty.file == pseudonym(PurePosixPath("night_s3.edf")) + ".edf"
    assert annotator_pseudonym("s3") not in {m.subkey for m in checks.measure_overlaps(ctx)}
    assert [m.state for m in checks.measure_codes(ctx)] == ["not_applicable"]  # no vocabulary, as before
    (summary,) = checks.summaries(ctx).values()
    assert summary["annotators"] == [annotator_pseudonym(n) for n in ("s1", "s2", "s3")]
    assert summary["coverage"][annotator_pseudonym("s3")] == 0.0 and summary["kappa"]["annotators"] == 2
    # left out by the patterns: counted, no finding
    ctx = _context(tmp_path, toml + 'annotators = ["s1", "s2"]\n')
    (obj,) = ctx.annotations().objects
    assert obj.excluded_annotators == 1
    assert annotator_pseudonym("s3") not in {m.subkey for m in checks.measure_gaps(ctx)}
    # alone: the recording is judged through that annotator, coverage 0
    for name in ("night_s1.edf", "night_s2.edf"):
        (tmp_path / name).unlink()
    (alone,) = checks.measure_gaps(_context(tmp_path, toml))
    assert alone.subkey == annotator_pseudonym("s3") and alone.value["coverage"] == 0.0


# --- P4 review: kappa limits and one computation per object (R8: ANN05) -------------------------------------


def test_kappa_annotator_limit_and_one_computation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _night(tmp_path, "night.edf")
    for n, stages in enumerate((("W", "N1"), ("W", "W"), ("N1", "N1")), start=1):
        _hypnogram(tmp_path, f"night_s{n}.edf", stages)
    toml = '[annotation]\nmode = "continuous"\n'
    monkeypatch.setattr(checks, "MAX_KAPPA_ANNOTATORS", 2)
    ctx = _context(tmp_path, toml)
    (measured,) = checks.measure_kappa(ctx)
    assert (measured.state, measured.reason) == ("not_checkable", "annotation.too_many_annotators")
    (summary,) = checks.summaries(ctx).values()
    assert summary["kappa"] is None and len(summary["annotators"]) == 3
    monkeypatch.setattr(checks, "MAX_KAPPA_ANNOTATORS", 3)  # at the limit: measured
    calls: list[str] = []
    original = checks.kappa

    def counted(obj: reader.AnnotatedRecording, frame: checks.Grid) -> checks.KappaResult | None:
        calls.append(obj.found.display_id)
        return original(obj, frame)

    monkeypatch.setattr(checks, "kappa", counted)
    ctx = _context(tmp_path, toml)
    (measured,) = checks.measure_kappa(ctx)
    assert measured.state == "measured" and measured.details["annotators"] == 3
    (summary,) = checks.summaries(ctx).values()
    assert summary["kappa"]["annotators"] == 3 and summary["kappa"]["pairs"] == 3
    assert len(calls) == 1  # the measurement and the summary share one computation (A-53)


def test_kappa_keeps_the_lowest_pairs_only_but_averages_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """Memory does not grow with the number of pairs: only MAX_PAIRS_LISTED pairs are kept (lowest first, as
    the full sort gave them); mean, minimum and the pair count still cover every pair, exactly."""
    monkeypatch.setattr(checks, "MAX_PAIRS_LISTED", 2)
    found = FoundFile(PurePosixPath("night.edf"), "rec-x", ".edf", 0)
    stages = {"s1": "W W N1 N1", "s2": "W N1 N1 N1", "s3": "W W N1 N1", "s4": "N1 N1 W W", "s5": "W W W N1"}
    tracks = tuple(
        reader.Track(
            name, tuple(_a(30.0 * i, 30.0, s) for i, s in enumerate(text.split())), "annotation_file", found
        )
        for name, text in stages.items()
    )
    result = checks.kappa(
        reader.AnnotatedRecording(found=found, duration_s=120.0, tracks=tracks), _grid(120.0)
    )
    assert result is not None
    names = sorted(stages)
    expected = []
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            value = checks.cohen_kappa(stages[first].split(), stages[second].split())
            assert value is not None
            expected.append((value, *sorted((annotator_pseudonym(first), annotator_pseudonym(second)))))
    expected.sort()
    assert (result.pair_count, result.annotators, len(result.pairs)) == (10, 5, 2)
    assert result.mean == float(sum((v for v, _a, _b in expected), Fraction(0)) / 10)
    assert result.minimum == float(expected[0][0])
    assert result.pairs == tuple((a, b, float(v)) for v, a, b in expected[:2])


# --- P4 review: dates in free text (R10: ANN02) -------------------------------------------------------------


def test_display_text_hides_real_dates_and_clock_times() -> None:
    for hidden in ("born 12.03.1961", "recorded 2019-03-12", "Lights off 22.31.07", "DOB 1961-03-12"):
        assert display_text(hidden) == (None, "text-" + short_hash(hidden))
        assert display_text(hidden, (hidden,)).shown == hidden  # vocabulary entries still pass
    for kept in ("Lights off", "Sleep stage W", "N2", "Stage 2", "Auditory/Left", "rest_open", "01.01.85"):
        assert display_text(kept).shown == kept  # no date, or a placeholder date (A-05)


def test_dated_codes_and_annotators_are_free_text(tmp_path: Path) -> None:
    """In-file TAL texts with a birth date, a recording date and a clock time (ANN02) and a BIDS annotator ID
    with a date appear only as text-<sha8> with their length."""
    texts = ("Lights off 22.31.07", "recorded 2019-03-12", "born 12.03.1961", "W")
    write_edf(
        tmp_path / "night.edf",
        sfreq=8,
        seconds=60,
        labels=("C3",),
        plus="C",
        annotations=tuple((10.0 * i, 0.0, text) for i, text in enumerate(texts)),
    )
    measured = checks.measure_codes(_context(tmp_path, '[annotation]\nvocabulary = ["W"]\n'))
    text = repr([(m.subkey, dict(m.details)) for m in measured])
    assert "1961" not in text and "2019" not in text and "22.31" not in text
    hidden = {m.subkey: m.details["chars"] for m in measured if m.value is False}
    assert hidden == {display_text(t).subkey: len(t) for t in texts[:3]}
    events = "onset\tduration\ttrial_type\tannotator\n1\t1\tstim\tAB 12.03.1961\n1\t1\tstim\tA2\n"
    ctx = _context(_bids(tmp_path / "ds", events))
    details = [dict(m.details) for m in checks.measure_overlaps(ctx)]
    assert sorted(d.get("annotator", "") for d in details) == ["", "A2"]  # BIDS: shown only if displayable


# --- P4 review: annotation configuration (R11: ANN06, ANN08) ------------------------------------------------


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("hyp/s1.edf", "hyp/s1.edf"),
        ("hyp\\\\s1.edf", "hyp/s1.edf"),  # the same file with Windows separators
        ("./s1.edf", "s1.edf"),
        ("hyp//s1.edf", "hyp/s1.edf"),
    ],
)
def test_a_file_appears_in_annotation_files_only_once(first: str, second: str) -> None:
    """ANN06: a second row for the same file was ignored without a trace (C2: exit 2 naming the field)."""

    def rows(last: str) -> str:
        return (
            f'[[annotation.files]]\npath = "{first}"\nrecording = "other.edf"\nannotator = "s1"\n'
            '[[annotation.files]]\npath = "x.edf"\nrecording = "night.edf"\n'
            f'[[annotation.files]]\npath = "{last}"\nrecording = "night.edf"\nannotator = "s9"\n'
        )

    with pytest.raises(ConfigError) as info:
        config_module.parse(rows(second))
    assert info.value.message_key == "config.duplicate_path"
    assert info.value.params == {"field": "annotation.files.2.path"}  # the field only, never the path
    assert len(config_module.parse(rows("hyp/s2.edf")).annotation.files) == 3  # several files: fine


def test_patterns_that_leave_out_every_annotator_name_the_reason(tmp_path: Path) -> None:
    """ANN08: the patterns are compared with annotator IDs; a file-name pattern leaves out everyone, and the
    findings say so (annotation.all_excluded) instead of 'no annotations'."""
    _night(tmp_path, "night.edf")
    _hypnogram(tmp_path, "night_scorer1.edf", ("W", "N1"))
    _hypnogram(tmp_path, "night_scorer2.edf", ("W", "W"))
    toml = '[annotation]\nmode = "continuous"\n'
    ctx = _context(tmp_path, toml + 'annotators = ["night_scorer*.edf"]\n')
    for check in (checks.measure_kappa, checks.measure_codes, checks.measure_overlaps):
        assert _states(check(ctx)) == [("dataset", "not_applicable", "annotation.all_excluded")]
    (gap,) = checks.measure_gaps(ctx)
    assert gap.value["coverage"] == 0.0 and gap.details == {"excluded_annotators": 2}
    (kappa,) = checks.measure_kappa(_context(tmp_path, toml + 'annotators = ["scorer*"]\n'))  # IDs
    assert kappa.state == "measured" and kappa.details["annotators"] == 2
    # per recording, when another recording has annotators that take part
    _night(tmp_path, "day.edf")
    _hypnogram(tmp_path, "day_other.edf", ("W", "N1"))  # the annotator ID is "other"
    ctx = _context(tmp_path, toml + 'annotators = ["scorer*"]\n')
    day = next(m for m in checks.measure_kappa(ctx) if m.object == pseudonym(PurePosixPath("day.edf")))
    assert (day.state, day.reason, dict(day.details)) == (
        "not_applicable",
        "annotation.all_excluded",
        {"excluded_annotators": 1},
    )


# --- language tables (C7) -----------------------------------------------------------------------------------


def test_every_m10_text_exists_in_every_language() -> None:
    """Reason and notice keys built at runtime, the check titles and the labels of the measured values."""
    from neurogrid.kernel.i18n import LANGUAGES
    from neurogrid.report.texts import tables

    keys = [f"reason.{key}" for key in checks.REASONS] + list(checks.NOTICES)
    keys += [f"check.{check_id}" for check_id in sorted(checks.CHECKS)]
    keys += [f"report.measure.{key}" for key in ("gaps", "gap_s", "coverage", "overlaps", "overlap_s")]
    keys += ["report.value.free_text"]
    for lang in LANGUAGES:
        missing = [key for key in keys if key not in tables()[lang]]
        assert not missing, (lang, missing)
