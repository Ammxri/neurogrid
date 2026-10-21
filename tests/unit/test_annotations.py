"""M10 annotation readers, attachment of annotation-only files and the measurements (NG-F08, A-17, A-80)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path, PurePosixPath
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
from neurogrid.io.identifying import annotator_pseudonym, display_text
from neurogrid.kernel.errors import ConfigError
from neurogrid.model.dataset import Annotation, Recording

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"


def _annotation_file(path: Path, tal: bytes, *, bdf: bool = False) -> Path:
    """An annotation-only EDF+C/BDF+C with one record of duration 0 whose annotation signal holds ``tal``."""
    bps = 3 if bdf else 2
    samples = -(-len(tal) // bps)
    header = bytearray(b"\xffBIOSEMI" if bdf else _field("0", 8))
    header += _field("X X X X", 80) + _field("Startdate X X X X", 80) + _field("01.01.85", 8)
    header += _field("00.00.00", 8) + _num(512, 8) + _field("BDF+C" if bdf else "EDF+C", 44)
    header += _num(1, 8) + _num(0, 8) + _num(1, 4)
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
