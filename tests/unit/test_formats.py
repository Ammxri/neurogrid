"""Format adapters BDF, BrainVision, EEGLAB and FIF, the shared identifying-content heuristics, channel types
and standard electrode names (NG-F01, M01, M04, M05, A-18, A-24, A-46, A-51, A-52, A-53, A-64, A-77)."""

from __future__ import annotations

import datetime
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import gen_fixtures
from neurogrid.io import ADAPTERS, brainvision, eeglab
from neurogrid.io.base import HeaderInspection, HeaderUnreadable, mne_read_check
from neurogrid.io.brainvision import BrainVisionAdapter, _decode, _segment_date, parse_vhdr
from neurogrid.io.channels import classify, standard_name
from neurogrid.io.edf import SIGNAL_FIELDS, BdfAdapter, EdfAdapter, parse_header
from neurogrid.io.eeglab import EeglabAdapter, _chanlocs, _EpochsAsRaw, _load, _text
from neurogrid.io.fif import FifAdapter, _position
from neurogrid.io.identifying import dates_or_times, looks_identifying, placeholder, real_dates
from neurogrid.io.montage_names import ONLY_1005, SYSTEM_1020

ROOT = Path(__file__).resolve().parent.parent.parent
FIX = ROOT / "tests" / "fixtures" / "synthetic"
EEG_LABELS = gen_fixtures.EEG_LABELS
HEADER_SOURCES = {"channels": "header", "sampling_rate_hz": "header", "duration_s": "header"}
VHDR_MAGIC = "Brain Vision Data Exchange Header File Version 1.0\n"
VMRK_MAGIC = "Brain Vision Data Exchange Marker File, Version 1.0\n"


def _copy_folder(name: str, target: Path) -> Path:
    destination = target / name
    shutil.copytree(FIX / name, destination)
    return destination


def _edit(path: Path, old: str, new: str) -> Path:
    text = path.read_bytes().decode("utf-8")
    assert old in text, old
    path.write_bytes(text.replace(old, new).encode("utf-8"))
    return path


def _append(path: Path, extra: bytes) -> Path:
    path.write_bytes(path.read_bytes() + extra)
    return path


# --- BDF and the EDF/BDF variant check -------------------------------------------------------------------

BDF = FIX / "bdf_ok" / "rec.bdf"
EDF = FIX / "edf_ok" / "rec_a.edf"


def test_adapter_registry_covers_the_p2_formats() -> None:
    expected = {
        ".edf": (EdfAdapter, "EDF"),
        ".bdf": (BdfAdapter, "BDF"),
        ".vhdr": (BrainVisionAdapter, "BrainVision"),
        ".set": (EeglabAdapter, "EEGLAB"),
        ".fif": (FifAdapter, "FIF"),
    }
    assert set(ADAPTERS) == set(expected)
    for suffix, (kind, name) in expected.items():
        adapter = ADAPTERS[suffix]
        assert type(adapter) is kind and adapter.format == name and adapter.extensions == (suffix,)


def test_bdf_read_gives_the_data_model() -> None:
    recording = BdfAdapter().read(BDF, recording_id="rec-b", relative_path="rec.bdf")
    assert recording.format == "BDF" and recording.id == "rec-b" and recording.path == "rec.bdf"
    assert [ch.name for ch in recording.channels] == [f"EEG {label}" for label in EEG_LABELS]
    assert {ch.type for ch in recording.channels} == {"EEG"}
    assert {ch.unit for ch in recording.channels} == {"uV"}
    assert {ch.sampling_rate_hz for ch in recording.channels} == {512.0}
    assert {ch.physical_range for ch in recording.channels} == {(-500.0, 500.0)}
    # 24-bit digital range: 1000 µV over 2**24 - 1 steps
    assert recording.channels[0].resolution == pytest.approx(1000.0 / (2**24 - 1))
    assert recording.sampling_rate_hz == 512.0 and recording.duration_s == 10.0
    assert recording.streamable and not recording.discontinuous
    assert recording.metadata_sources == HEADER_SOURCES


def test_bdf_inspect_and_read_check_of_a_clean_file() -> None:
    adapter = BdfAdapter()
    inspection = adapter.inspect(BDF)
    assert inspection.issues == () and inspection.identifying_fields == ()
    assert inspection.missing_companions == ()
    assert adapter.read_check(BDF) is None


def test_truncated_bdf_is_a_header_issue() -> None:
    path = FIX / "bdf_truncated" / "rec_trunc.bdf"
    assert BdfAdapter().inspect(path).issues == ("header.file_truncated",)
    assert BdfAdapter().read_check(path) is None  # MNE reads it; only the header check finds the cut (A-65)


def test_bdf_size_is_computed_with_three_bytes_per_sample(tmp_path: Path) -> None:
    header = parse_header(BDF)
    assert header.variant == "BDF" and header.header_bytes == 256 * 9
    assert BDF.stat().st_size == 256 * 9 + 10 * 8 * 512 * 3
    longer = _append(Path(shutil.copy(BDF, tmp_path / "long.bdf")), b"\x00" * 3)
    assert BdfAdapter().inspect(longer).issues == ("header.file_trailing_data",)


@pytest.mark.parametrize(("reserved", "discontinuous"), [(b"BDF+C", False), (b"BDF+D", True)])
def test_bdf_plus_variants(tmp_path: Path, reserved: bytes, discontinuous: bool) -> None:
    data = bytearray(BDF.read_bytes())
    data[192:236] = reserved.ljust(44)
    path = tmp_path / "plus.bdf"
    path.write_bytes(bytes(data))
    header = parse_header(path)
    assert header.plus == reserved.decode()[-1] and header.issues == ()
    recording = BdfAdapter().read(path, recording_id="r", relative_path="plus.bdf")
    assert recording.discontinuous is discontinuous


@pytest.mark.parametrize(
    ("patient", "recording", "startdate", "plus", "expected"),
    [
        # plain BDF: the patient field is free text
        ("Zhang San", "Startdate X X X X", "24.08.21", False, ("patient", "date")),
        ("X", "Session 2002-03-02", "01.01.85", False, ("date",)),
        ("X", "Study 4711234", "01.01.85", False, ("recording",)),
        # BDF+ uses the EDF+ subfields (A-64)
        (
            "MCH-0234567 F 02-MAY-1951 Haagse_Harry",
            "Startdate 02-MAR-2002 EMG561 BK/JOP Biosemi",
            "01.01.85",
            True,
            ("patient", "recording", "date"),
        ),
        ("X Q X X", "Startdate X X X Biosemi", "01.01.85", True, ("patient",)),  # sex field is no sex
        ("X X X X", "Startdate X X X Biosemi Dr_Wang_Li", "01.01.85", True, ("recording",)),
        ("X X X X", "Startdate X X X Biosemi seen_2002-03-02", "01.01.85", True, ("date",)),
        ("X X X X", "Recorded 2002-03-02 by Jane Doe", "01.01.85", True, ("recording", "date")),
        ("X M X X", "Startdate 01-JAN-2002 X X Biosemi", "01.01.85", True, ()),
        ("X X X X", "Recorded at site a", "01.01.85", True, ()),  # free text without identifiers
    ],
)
def test_bdf_identifying_header_fields(
    tmp_path: Path, patient: str, recording: str, startdate: str, plus: bool, expected: tuple[str, ...]
) -> None:
    path = tmp_path / "named.bdf"
    gen_fixtures.write_edf(
        path, seconds=1, bdf=True, patient=patient, recording=recording, startdate=startdate
    )
    if plus:
        data = bytearray(path.read_bytes())
        data[192:236] = b"BDF+C".ljust(44)
        path.write_bytes(bytes(data))
    inspection = BdfAdapter().inspect(path)
    assert inspection.identifying_fields == expected and inspection.issues == ()


def test_edf_bytes_named_bdf_are_a_variant_mismatch(tmp_path: Path) -> None:
    path = Path(shutil.copy(EDF, tmp_path / "rec.bdf"))
    assert BdfAdapter().inspect(path).issues == ("header.variant_mismatch",)
    # the data model names what the header says, not what the file name says
    assert BdfAdapter().read(path, recording_id="r", relative_path="rec.bdf").format == "EDF"


def test_bdf_bytes_named_edf_are_a_variant_mismatch(tmp_path: Path) -> None:
    path = Path(shutil.copy(BDF, tmp_path / "rec.edf"))
    assert parse_header(path).issues == ()
    assert EdfAdapter().inspect(path).issues == ("header.variant_mismatch",)
    assert EdfAdapter().read_check(path) is None  # MNE detects the variant itself; the data are readable


def test_bdf_is_not_cross_checked_with_edfio(monkeypatch: pytest.MonkeyPatch) -> None:
    """edfio reads EDF only; the own parser is the BDF header check (A-24)."""

    def edfio_called(path: Path) -> tuple[str, ...]:
        raise AssertionError("edfio must not be used for BDF")

    monkeypatch.setattr("neurogrid.io.edf._edfio_issues", edfio_called)
    assert BdfAdapter().inspect(BDF).issues == ()
    with pytest.raises(AssertionError):
        EdfAdapter().inspect(EDF)


def test_bdf_read_check_reports_unreadable_data(tmp_path: Path) -> None:
    junk = tmp_path / "junk.bdf"
    junk.write_bytes(b"\xffBIOSEMI" + b"\x00" * 300)
    # only the class name of MNE's exception is kept, never its message (A-51; MNE is pinned, A-48)
    assert BdfAdapter().read_check(junk) == "ValueError"


def test_only_edf_headers_are_cross_checked_with_edfio(tmp_path: Path) -> None:
    """The same broken record duration: edfio rejects the EDF file, the BDF file has only the own check."""
    for source, adapter in ((EDF, EdfAdapter()), (BDF, BdfAdapter())):
        data = bytearray(source.read_bytes())
        data[244:252] = b"abc     "
        path = tmp_path / f"broken{source.suffix}"
        path.write_bytes(bytes(data))
        expected = ("header.record_duration",)
        if adapter.variant == "EDF":
            expected += ("header.edfio_rejected",)
        assert adapter.inspect(path).issues == expected


def _bdf_signal_field(name: str) -> int:
    """Byte offset of a per-signal header field (first signal) in the 8-signal BDF fixture."""
    offset = 0
    for field, width in SIGNAL_FIELDS:
        if field == name:
            return 256 + 8 * offset
        offset += width
    raise KeyError(name)


def _patched_bdf(tmp_path: Path, offset: int, value: bytes) -> Path:
    data = bytearray(BDF.read_bytes())
    data[offset : offset + len(value)] = value
    path = tmp_path / "patched.bdf"
    path.write_bytes(bytes(data))
    return path


@pytest.mark.parametrize(
    ("offset", "value", "issues"),
    [
        (8, "Zé".encode("latin-1"), ("header.non_ascii",)),
        (184, b"abc     ", ("header.size_field",)),
        (236, b"-1      ", ("header.records_unknown",)),
        (236, b"1.5     ", ("header.records_unknown",)),
        (244, b"0       ", ("header.record_duration",)),
        (168, b"2026-1-1", ("header.startdate",)),
        (168, b"31.02.21", ("header.startdate",)),
        (_bdf_signal_field("label"), "Fp1é".encode("latin-1"), ("header.non_ascii",)),
        (_bdf_signal_field("unit"), b"\xb5V      ", ("header.non_ascii",)),
        (_bdf_signal_field("pmin"), b"xx      ", ("header.number_field",)),
        (_bdf_signal_field("dmin"), b"8388607 ", ("header.digital_range",)),
        (_bdf_signal_field("pmin"), b"500     ", ("header.physical_range",)),
        # the header now declares 512 fewer samples per record than the file holds
        (_bdf_signal_field("spr"), b"0       ", ("header.samples_per_record", "header.file_trailing_data")),
    ],
)
def test_bdf_header_issues(tmp_path: Path, offset: int, value: bytes, issues: tuple[str, ...]) -> None:
    assert BdfAdapter().inspect(_patched_bdf(tmp_path, offset, value)).issues == issues


@pytest.mark.parametrize(
    ("damage", "reason"),
    [
        (lambda data: data[:100], "header.too_short"),
        (lambda data: b"\xffBIOSEMX" + data[8:], "header.bad_version"),
        (lambda data: data[:252] + b"0   " + data[256:], "header.bad_signal_count"),
        (lambda data: data[:252] + b"9999" + data[256:], "header.bad_signal_count"),
        (lambda data: data[:1000], "header.too_short"),  # the signal block is cut
    ],
)
def test_unreadable_bdf_headers(tmp_path: Path, damage: Callable[[bytes], bytes], reason: str) -> None:
    path = tmp_path / "bad.bdf"
    path.write_bytes(damage(BDF.read_bytes()))
    with pytest.raises(HeaderUnreadable) as info:
        BdfAdapter().inspect(path)
    assert info.value.reason == reason


def test_bdf_data_model_of_invalid_fields(tmp_path: Path) -> None:
    adapter = BdfAdapter()
    first, second = adapter.read(
        _patched_bdf(tmp_path, _bdf_signal_field("pmin"), b"xx      "),
        recording_id="r",
        relative_path="p.bdf",
    ).channels[:2]
    assert first.physical_range is None and first.resolution is None
    assert second.physical_range == (-500.0, 500.0)
    assert second.resolution == pytest.approx(
        1000.0 / (2**24 - 1)
    )  # one broken field affects its signal only
    channel = adapter.read(
        _patched_bdf(tmp_path, _bdf_signal_field("dmin"), b"8388607 "),
        recording_id="r",
        relative_path="p.bdf",
    ).channels[0]
    assert channel.physical_range == (-500.0, 500.0) and channel.resolution is None
    path = _patched_bdf(tmp_path, 244, b"abc     ")
    assert parse_header(path).record_duration_s is None
    recording = adapter.read(path, recording_id="r", relative_path="p.bdf")
    assert recording.sampling_rate_hz is None and recording.duration_s is None
    assert {ch.sampling_rate_hz for ch in recording.channels} == {None}
    assert recording.metadata_sources == {"channels": "header"}


# --- BrainVision -----------------------------------------------------------------------------------------


def _vhdr(
    path: Path,
    *,
    common: dict[str, str | None] | None = None,
    binary: str | None = "INT_16",
    channels: tuple[str, ...] = ("Fp1,,0.1,µV", "Fp2,,0.1,µV"),
    comment: str | None = None,
    magic: str = VHDR_MAGIC,
    encoding: str = "utf-8",
) -> Path:
    """A BrainVision header; ``None`` in ``common`` leaves a key out."""
    values: dict[str, str | None] = {
        "Codepage": "UTF-8",
        "DataFile": "rec.eeg",
        "MarkerFile": "rec.vmrk",
        "DataFormat": "BINARY",
        "DataOrientation": "MULTIPLEXED",
        "NumberOfChannels": str(len(channels)),
        "SamplingInterval": "2000",
    }
    values.update(common or {})
    text = magic + "\n[Common Infos]\n"
    text += "".join(f"{key}={value}\n" for key, value in values.items() if value is not None)
    if binary is not None:
        text += f"\n[Binary Infos]\nBinaryFormat={binary}\n"
    text += "\n[Channel Infos]\n" + "".join(f"Ch{i}={info}\n" for i, info in enumerate(channels, start=1))
    if comment is not None:
        text += "\n[Comment]\n" + comment
    path.write_bytes(text.encode(encoding))
    return path


def _brainvision(folder: Path, **options: Any) -> Path:
    """A complete BrainVision triple of 8 channels, 500 Hz, 1 s (8000 bytes of INT_16 data)."""
    vhdr = folder / "rec.vhdr"
    gen_fixtures.write_brainvision(vhdr, seconds=1, **options)
    return vhdr


def test_brainvision_read_gives_the_data_model() -> None:
    recording = BrainVisionAdapter().read(
        FIX / "brainvision_ok" / "rec.vhdr", recording_id="rec-v", relative_path="rec.vhdr"
    )
    assert recording.format == "BrainVision" and recording.id == "rec-v"
    assert [ch.name for ch in recording.channels] == list(EEG_LABELS)
    assert {(ch.type, ch.unit, ch.resolution) for ch in recording.channels} == {("EEG", "µV", 0.1)}
    assert {ch.sampling_rate_hz for ch in recording.channels} == {500.0}
    assert {ch.impedance_kohm for ch in recording.channels} == {3.0}
    # 80000 bytes = 5000 frames of 8 channels x 2 bytes, 2000 µs apart
    assert recording.sampling_rate_hz == 500.0 and recording.duration_s == 10.0
    assert recording.streamable
    assert recording.metadata_sources == HEADER_SOURCES | {"impedance_kohm": "header"}


def test_brainvision_impedances_from_the_comment_section() -> None:
    path = FIX / "brainvision_impedance" / "rec.vhdr"
    recording = BrainVisionAdapter().read(path, recording_id="r", relative_path="rec.vhdr")
    impedances = {ch.name: ch.impedance_kohm for ch in recording.channels}
    assert impedances == {
        "Fp1": 3.0,
        "Fp2": 3.0,
        "F3": 3.0,
        "F4": 3.0,
        "C3": 25.0,
        "C4": 3.0,
        "O1": 3.0,
        "O2": None,
    }
    # the impedance block is measurement data, not identifying free text (A-51)
    inspection = BrainVisionAdapter().inspect(path)
    assert (
        inspection.issues == ()
        and inspection.identifying_fields == ()
        and inspection.missing_companions == ()
    )


def test_brainvision_impedance_block_details(tmp_path: Path) -> None:
    comment = (
        "Impedance [kOhm] at 09:00:00 :\nFp1: 50\nFp2: 60\n"
        "Impedance [Ohm] at 10:00:00 :\nFp1: 5000\nFp2: Out of Range!\nGnd: 1500\n"
        "Recorded by the night shift\n"
    )
    header = parse_vhdr(_vhdr(tmp_path / "rec.vhdr", comment=comment))
    assert header.impedances == {"Fp1": 5.0, "Fp2": None, "Gnd": 1.5}  # last block wins, Ohm -> kOhm
    assert header.impedance_lines == set(range(7))  # both blocks; the free text line after them is not part
    assert header.comment[7] == "Recorded by the night shift"


def test_brainvision_without_impedances_has_no_impedance_source(tmp_path: Path) -> None:
    vhdr = _brainvision(tmp_path)
    recording = BrainVisionAdapter().read(vhdr, recording_id="r", relative_path="rec.vhdr")
    assert {ch.impedance_kohm for ch in recording.channels} == {None}
    assert recording.metadata_sources == HEADER_SOURCES and recording.duration_s == 1.0


def test_vhdr_without_magic_is_unreadable(tmp_path: Path) -> None:
    path = _vhdr(tmp_path / "x.vhdr", magic="[Common Infos]\n")
    adapter = BrainVisionAdapter()
    for call in (parse_vhdr, adapter.inspect, lambda p: adapter.read(p, recording_id="r", relative_path="x")):
        with pytest.raises(HeaderUnreadable) as info:
            call(path)
        assert info.value.reason == "header.bad_version"


@pytest.mark.parametrize(
    "magic",
    [
        "\ufeff" + VHDR_MAGIC,  # byte order mark
        "\n\n  " + VHDR_MAGIC,  # leading blank lines
        "BrainVision Data Exchange Header File Version 2.0\n",  # newer spelling without the space
        "brain vision data exchange header file version 1.0\n",  # case does not matter
    ],
)
def test_vhdr_magic_variants_are_accepted(tmp_path: Path, magic: str) -> None:
    header = parse_vhdr(_vhdr(tmp_path / "x.vhdr", magic=magic))
    assert header.issues == [] and header.n_channels == 2 and header.interval_us == 2000


def test_vhdr_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _vhdr(tmp_path / "x.vhdr")
    monkeypatch.setattr(brainvision, "MAX_HEADER_BYTES", 100)
    with pytest.raises(HeaderUnreadable) as info:
        parse_vhdr(path)
    assert info.value.reason == "header.too_large"


def test_vhdr_missing_required_keys_are_one_issue(tmp_path: Path) -> None:
    path = _vhdr(
        tmp_path / "x.vhdr", common={"DataFile": None, "SamplingInterval": None, "NumberOfChannels": ""}
    )
    header = parse_vhdr(path)
    assert header.issues == ["header.missing_key"]
    assert header.n_channels is None and header.interval_us is None


def test_vhdr_channel_infos(tmp_path: Path) -> None:
    channels = ("Fp1,Ref,0.5,nV", "Fp2", "A\\1B,,,", "O1,,abc,µV", "O2,, 2 ,mV")
    header = parse_vhdr(_vhdr(tmp_path / "x.vhdr", channels=channels))
    assert header.channels == [
        ("Fp1", "Ref", 0.5, "nV"),
        ("Fp2", None, 1.0, "µV"),  # defaults of the specification: resolution 1, unit µV
        ("A,B", None, 1.0, "µV"),  # "\1" stands for a comma in a name
        ("O1", None, None, "µV"),
        ("O2", None, 2.0, "mV"),
    ]
    assert header.issues == ["header.number_field"]


def test_vhdr_channels_are_ordered_by_number(tmp_path: Path) -> None:
    text = (
        VHDR_MAGIC + "[Common Infos]\nDataFile=rec.eeg\nMarkerFile=rec.vmrk\nDataFormat=BINARY\n"
        "NumberOfChannels=11\nSamplingInterval=1000\n[Binary Infos]\nBinaryFormat=IEEE_FLOAT_32\n"
        "[Channel Infos]\n; a comment line\nCh10=C10\nCh2=C2\nCh11=C11\n"
        + "".join(f"Ch{i}=C{i}\n" for i in (1, 3, 4, 5, 6, 7, 8, 9))
        + "Note=ignored\n"
    )
    path = tmp_path / "x.vhdr"
    path.write_bytes(text.encode("utf-8"))
    header = parse_vhdr(path)
    assert [name for name, *_rest in header.channels] == [f"C{i}" for i in range(1, 12)]
    assert header.issues == [] and header.bytes_per_sample == 4 and header.interval_us == 1000


@pytest.mark.parametrize(
    ("common", "binary", "issue"),
    [
        ({"NumberOfChannels": "eight"}, "INT_16", "header.number_field"),
        ({"NumberOfChannels": "0"}, "INT_16", "header.number_field"),
        ({"NumberOfChannels": "²"}, "INT_16", "header.number_field"),  # a digit int() refuses
        ({"NumberOfChannels": "1" * 5000}, "INT_16", "header.number_field"),  # over int()'s digit limit
        ({"NumberOfChannels": "3"}, "INT_16", "header.channel_count"),
        ({"SamplingInterval": "abc"}, "INT_16", "header.sampling_interval"),
        ({"SamplingInterval": "0"}, "INT_16", "header.sampling_interval"),
        ({"SamplingInterval": "1" * 5000}, "INT_16", "header.sampling_interval"),
        ({"DataFormat": "XML"}, "INT_16", "header.data_format"),
        ({"DataOrientation": "DIAGONAL"}, "INT_16", "header.data_format"),
        ({}, "INT_8", "header.data_format"),
        ({}, None, "header.data_format"),
    ],
)
def test_vhdr_invalid_fields(
    tmp_path: Path, common: dict[str, str | None], binary: str | None, issue: str
) -> None:
    header = parse_vhdr(_vhdr(tmp_path / "x.vhdr", common=common, binary=binary))
    assert header.issues == [issue]


@pytest.mark.parametrize(
    ("binary", "size"), [("INT_16", 2), ("uint_16", 2), ("INT_32", 4), ("IEEE_FLOAT_32", 4)]
)
def test_brainvision_sample_size_sets_the_frame_size(tmp_path: Path, binary: str, size: int) -> None:
    """Duration and the whole-frame check use NumberOfChannels x bytes per value of BinaryFormat (A-46)."""
    vhdr = _vhdr(tmp_path / "rec.vhdr", binary=binary)
    (tmp_path / "rec.eeg").write_bytes(b"\x00" * (2 * size * 250))  # 250 frames of 2 channels
    (tmp_path / "rec.vmrk").write_bytes(VMRK_MAGIC.encode("ascii"))
    assert parse_vhdr(vhdr).bytes_per_sample == size
    recording = BrainVisionAdapter().read(vhdr, recording_id="r", relative_path="rec.vhdr")
    assert recording.duration_s == 0.5  # 250 frames, 2000 µs apart
    assert BrainVisionAdapter().inspect(vhdr).issues == ()
    _append(tmp_path / "rec.eeg", b"\x00" * size)  # one value more: the last frame is incomplete
    assert BrainVisionAdapter().inspect(vhdr).issues == ("header.file_truncated",)


def test_brainvision_invalid_sampling_interval_gives_no_rate(tmp_path: Path) -> None:
    vhdr = _edit(_brainvision(tmp_path), "SamplingInterval=2000", "SamplingInterval=-2000")
    recording = BrainVisionAdapter().read(vhdr, recording_id="r", relative_path="rec.vhdr")
    assert recording.sampling_rate_hz is None and recording.duration_s is None
    assert {ch.sampling_rate_hz for ch in recording.channels} == {None}
    assert recording.metadata_sources == {"channels": "header"}
    assert BrainVisionAdapter().inspect(vhdr).issues == ("header.sampling_interval",)


def test_vhdr_ascii_data_is_not_streamable_and_not_size_checked(tmp_path: Path) -> None:
    vhdr = _vhdr(tmp_path / "rec.vhdr", common={"DataFormat": "ASCII"}, binary=None)
    (tmp_path / "rec.eeg").write_bytes(b"1 2\n3 4\n5")
    (tmp_path / "rec.vmrk").write_bytes(VMRK_MAGIC.encode("ascii"))
    header = parse_vhdr(vhdr)
    assert header.issues == [] and header.bytes_per_sample is None
    recording = BrainVisionAdapter().read(vhdr, recording_id="r", relative_path="rec.vhdr")
    assert not recording.streamable and recording.duration_s is None and recording.sampling_rate_hz == 500.0
    assert BrainVisionAdapter().inspect(vhdr).issues == ()


def test_brainvision_only_eeg_channels_set_the_recording_rate(tmp_path: Path) -> None:
    vhdr = _vhdr(tmp_path / "rec.vhdr", channels=("EOG1,,0.1,µV", "ECG,,0.1,µV"))
    recording = BrainVisionAdapter().read(vhdr, recording_id="r", relative_path="rec.vhdr")
    assert [ch.type for ch in recording.channels] == ["EOG", "ECG"]
    assert {ch.sampling_rate_hz for ch in recording.channels} == {500.0}
    assert recording.sampling_rate_hz is None


@pytest.mark.parametrize(
    ("raw", "text"),
    [
        ("Fp1,,0.1,µV".encode(), "Fp1,,0.1,µV"),  # UTF-8
        ("左额,,0.1,uV".encode("gbk"), "左额,,0.1,uV"),  # GBK (Chinese recorders)
        ("Café au lait".encode("latin-1"), "Café au lait"),  # neither UTF-8 nor GBK
        (b"plain", "plain"),
    ],
)
def test_vhdr_decoding(raw: bytes, text: str) -> None:
    assert _decode(raw) == text


def test_gbk_header_keeps_chinese_channel_names(tmp_path: Path) -> None:
    path = _vhdr(
        tmp_path / "x.vhdr",
        common={"Codepage": "ANSI"},
        channels=("左额,,0.1,uV", "右额,,0.1,uV"),
        encoding="gbk",
    )
    header = parse_vhdr(path)
    assert [name for name, *_rest in header.channels] == ["左额", "右额"]
    assert {unit for *_rest, unit in header.channels} == {"uV"} and header.issues == []


def test_latin1_header_falls_back_to_latin1(tmp_path: Path) -> None:
    path = _vhdr(
        tmp_path / "x.vhdr",
        common={"Codepage": "ANSI"},
        channels=("Fp1,,0.1,µV", "Fp2,,0.1,µV"),
        comment="Caf\u00e9 \n",  # 0xE9 followed by a space is invalid GBK
        encoding="latin-1",
    )
    header = parse_vhdr(path)
    assert {unit for *_rest, unit in header.channels} == {"µV"} and header.comment == ["Café "]


def test_latin1_micro_volt_unit_of_an_ansi_header(tmp_path: Path) -> None:
    path = _vhdr(tmp_path / "x.vhdr", common={"Codepage": "ANSI"}, encoding="latin-1")
    assert {unit for *_rest, unit in parse_vhdr(path).channels} == {"µV"}


def test_brainvision_missing_data_file() -> None:
    path = FIX / "brainvision_missing" / "rec.vhdr"
    adapter = BrainVisionAdapter()
    inspection = adapter.inspect(path)
    assert inspection.missing_companions == ("companion.data_file",) and inspection.issues == ()
    recording = adapter.read(path, recording_id="r", relative_path="rec.vhdr")
    assert recording.duration_s is None and recording.sampling_rate_hz == 500.0
    assert "duration_s" not in recording.metadata_sources
    assert adapter.read_check(path) == "FileNotFoundError"


def test_brainvision_unsafe_reference_is_not_followed(tmp_path: Path) -> None:
    folder = _copy_folder("brainvision_unsafe", tmp_path)
    (tmp_path / "outside.eeg").write_bytes(b"\x00" * 16 * 500)  # exists, but outside the recording folder
    adapter = BrainVisionAdapter()
    inspection = adapter.inspect(folder / "rec.vhdr")
    assert inspection.missing_companions == ("companion.unsafe_reference",) and inspection.issues == ()
    assert adapter.read(folder / "rec.vhdr", recording_id="r", relative_path="rec.vhdr").duration_s is None


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("DataFile", "C:/data/rec.eeg", ("companion.unsafe_reference",)),
        ("DataFile", "\\\\server\\share\\rec.eeg", ("companion.unsafe_reference",)),
        ("DataFile", "other.eeg", ("companion.data_file",)),
        ("MarkerFile", "../rec.vmrk", ("companion.unsafe_reference",)),
        ("MarkerFile", "other.vmrk", ("companion.marker_file",)),
    ],
)
def test_brainvision_references_are_path_checked(
    tmp_path: Path, key: str, value: str, expected: tuple[str, ...]
) -> None:
    current = {"DataFile": "rec.eeg", "MarkerFile": "rec.vmrk"}[key]
    vhdr = _edit(_brainvision(tmp_path), f"{key}={current}\n", f"{key}={value}\n")
    assert BrainVisionAdapter().inspect(vhdr).missing_companions == expected


@pytest.mark.parametrize(
    ("key", "name", "problem"),
    [("DataFile", "rec.eeg", "companion.data_file"), ("MarkerFile", "rec.vmrk", "companion.marker_file")],
)
def test_brainvision_reference_into_a_subfolder_is_not_followed(
    tmp_path: Path, key: str, name: str, problem: str
) -> None:
    vhdr = _brainvision(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / name).rename(tmp_path / "data" / name)
    _edit(vhdr, f"{key}={name}", f"{key}=data\\{name}")
    inspection = BrainVisionAdapter().inspect(vhdr)
    assert inspection.missing_companions in ((problem,), ("companion.unsafe_reference",))
    if key == "DataFile":
        assert BrainVisionAdapter().read(vhdr, recording_id="r", relative_path="rec.vhdr").duration_s is None


def test_brainvision_without_data_file_key_reports_the_key_only(tmp_path: Path) -> None:
    vhdr = _edit(_brainvision(tmp_path), "DataFile=rec.eeg\n", "")
    inspection = BrainVisionAdapter().inspect(vhdr)
    assert inspection.issues == ("header.missing_key",) and inspection.missing_companions == ()


def test_brainvision_missing_marker_file(tmp_path: Path) -> None:
    vhdr = _brainvision(tmp_path)
    (tmp_path / "rec.vmrk").unlink()
    inspection = BrainVisionAdapter().inspect(vhdr)
    assert inspection.missing_companions == ("companion.marker_file",) and inspection.issues == ()
    assert BrainVisionAdapter.companions(vhdr) == ("rec.eeg", "rec.vmrk")
    # without a MarkerFile key the marker file is missing as well; MarkerFile is no required key
    _edit(vhdr, "MarkerFile=rec.vmrk\n", "")
    inspection = BrainVisionAdapter().inspect(vhdr)
    assert inspection.missing_companions == ("companion.marker_file",) and inspection.issues == ()


def test_brainvision_truncated_data_file() -> None:
    path = FIX / "brainvision_truncated" / "rec.vhdr"
    assert BrainVisionAdapter().inspect(path).issues == ("header.file_truncated",)
    # 79000 bytes hold 4937 whole frames of 16 bytes
    recording = BrainVisionAdapter().read(path, recording_id="r", relative_path="rec.vhdr")
    assert recording.duration_s == pytest.approx(4937 * 0.002)


def test_brainvision_trailing_partial_frame_and_whole_extra_frame(tmp_path: Path) -> None:
    vhdr = _brainvision(tmp_path)
    _append(tmp_path / "rec.eeg", b"\x00" * 16)  # one more complete frame: just a longer recording
    assert BrainVisionAdapter().inspect(vhdr).issues == ()
    assert BrainVisionAdapter().read(vhdr, recording_id="r", relative_path="rec.vhdr").duration_s == 1.002
    _append(tmp_path / "rec.eeg", b"\x00" * 3)  # the last frame is incomplete
    assert BrainVisionAdapter().inspect(vhdr).issues == ("header.file_truncated",)


IMPEDANCE_BLOCK = "Impedance [kOhm] at 12:00:00 :\n" + "".join(f"{label}: 3\n" for label in EEG_LABELS)


@pytest.mark.parametrize(
    "comment",
    [
        "Patient John Smith, left handed\n",  # a name
        "Hospital ID 4711234\n",  # six or more digits
        "Notiz: Müller\n",  # non-ASCII letters
        "Exported from C:\\Users\\lab\\eeg\n",  # an absolute path of the original system
        "Recorded 2021-08-24\n",  # a real date
    ],
)
def test_brainvision_identifying_comment(tmp_path: Path, comment: str) -> None:
    vhdr = _brainvision(tmp_path)
    _append(vhdr, ("\n[Comment]\n" + comment + IMPEDANCE_BLOCK).encode("utf-8"))
    inspection = BrainVisionAdapter().inspect(vhdr)
    assert inspection.identifying_fields == ("recording",)
    recording = BrainVisionAdapter().read(vhdr, recording_id="r", relative_path="rec.vhdr")
    assert {ch.impedance_kohm for ch in recording.channels} == {3.0}
    assert comment.strip() not in recording.model_dump_json()  # the comment is never taken over


def test_brainvision_free_text_after_the_impedance_block_is_checked(tmp_path: Path) -> None:
    vhdr = _brainvision(tmp_path)
    _append(vhdr, ("\n[Comment]\n" + IMPEDANCE_BLOCK + "Recorded 2021-08-24 by John Smith\n").encode("utf-8"))
    assert BrainVisionAdapter().inspect(vhdr).identifying_fields == ("recording",)


def test_brainvision_key_value_note_after_the_impedance_block_is_checked(tmp_path: Path) -> None:
    vhdr = _brainvision(tmp_path)
    _append(vhdr, ("\n[Comment]\n" + IMPEDANCE_BLOCK + "Patient: John Smith\n").encode("utf-8"))
    assert BrainVisionAdapter().inspect(vhdr).identifying_fields == ("recording",)


def test_brainvision_harmless_comment_is_not_identifying(tmp_path: Path) -> None:
    vhdr = _brainvision(tmp_path)
    _append(vhdr, b"\n[Comment]\nresting state, eyes closed\n")
    assert BrainVisionAdapter().inspect(vhdr).identifying_fields == ()


@pytest.mark.parametrize(
    ("marker", "expected"),
    [
        ("Mk1=New Segment,,1,1,0,20210824101500123456", ("date",)),
        ("Mk1=New Segment,,1,1,0,00000000000000000000", ()),  # zero date written by anonymising tools
        ("Mk1=New Segment,,1,1,0", ()),
        ("Mk1=Stimulus,S  1,1,1,0,20210824101500123456", ()),  # only the segment start carries the date
    ],
)
def test_brainvision_segment_date_in_the_marker_file(
    tmp_path: Path, marker: str, expected: tuple[str, ...]
) -> None:
    vhdr = _brainvision(tmp_path)
    (tmp_path / "rec.vmrk").write_bytes(
        (VMRK_MAGIC + "\n[Common Infos]\nDataFile=rec.eeg\n\n[Marker Infos]\n" + marker + "\n").encode()
    )
    inspection = BrainVisionAdapter().inspect(vhdr)
    assert inspection.identifying_fields == expected and inspection.issues == ()


def test_segment_date_reads_are_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    marker = tmp_path / "rec.vmrk"
    marker.write_bytes(b"[Marker Infos]\nMk1=New Segment,,1,1,0,20210824101500123456\n")
    assert _segment_date(marker)
    assert not _segment_date(tmp_path)  # a folder cannot be read
    monkeypatch.setattr(brainvision, "MAX_MARKER_BYTES", 10)
    assert not _segment_date(marker)  # never loads more than the limit (A-53)


def test_brainvision_read_check() -> None:
    adapter = BrainVisionAdapter()
    assert adapter.read_check(FIX / "brainvision_ok" / "rec.vhdr") is None
    # MNE reads the whole frames of a cut data file; the cut is found by the size check of inspect (A-65)
    assert adapter.read_check(FIX / "brainvision_truncated" / "rec.vhdr") is None


@pytest.mark.parametrize("outside", ["parent", "absolute"])
def test_brainvision_read_check_does_not_follow_unsafe_references(tmp_path: Path, outside: str) -> None:
    folder = tmp_path / "dataset"
    folder.mkdir()
    vhdr = _brainvision(folder)
    target = tmp_path / "outside.eeg"
    (folder / "rec.eeg").rename(target)  # valid data, but outside the recording folder
    reference = "../outside.eeg" if outside == "parent" else str(target)
    _edit(vhdr, "DataFile=rec.eeg", f"DataFile={reference}")
    adapter = BrainVisionAdapter()
    assert adapter.inspect(vhdr).missing_companions == ("companion.unsafe_reference",)
    # the outside file is not read as this recording; MNE is not called at all (A-77)
    assert adapter.read_check(vhdr) == "UnsafePathError"


def test_brainvision_companions(tmp_path: Path) -> None:
    assert BrainVisionAdapter.companions(FIX / "brainvision_ok" / "rec.vhdr") == ("rec.eeg", "rec.vmrk")
    assert BrainVisionAdapter.companions(FIX / "brainvision_unsafe" / "rec.vhdr") == (
        "../outside.eeg",
        "rec.vmrk",
    )
    no_marker = _vhdr(tmp_path / "a.vhdr", common={"MarkerFile": None})
    assert BrainVisionAdapter.companions(no_marker) == ("rec.eeg",)
    assert BrainVisionAdapter.companions(_vhdr(tmp_path / "b.vhdr", magic="garbage\n")) == ()
    assert BrainVisionAdapter.companions(tmp_path / "missing.vhdr") == ()


# --- EEGLAB ----------------------------------------------------------------------------------------------

SET_OK = FIX / "eeglab_ok" / "rec.set"
SET_EMBEDDED = FIX / "eeglab_embedded" / "rec.set"


def _write_set(
    path: Path,
    *,
    labels: tuple[str, ...] = ("Fp1", "Fp2", "Cz"),
    sfreq: int = 128,
    points: int = 256,
    trials: int = 1,
    embedded: bool = False,
    chantypes: tuple[str, ...] | None = None,
    positions: tuple[tuple[float, float, float] | None, ...] | None = None,
    top_level: bool = False,
    **fields: Any,
) -> Path:
    """A MATLAB v5 EEGLAB data set like tools/gen_fixtures.py writes; ``fields`` override EEG entries.

    ``top_level`` stores the fields as variables of the file instead of inside an ``EEG`` structure (newer
    EEGLAB versions can save data sets that way).
    """
    import scipy.io

    samples = np.random.default_rng(0).normal(0.0, 5.0, (len(labels), points * trials)).astype("<f4")
    empty = np.array([])
    chanlocs = np.zeros((1, len(labels)), dtype=[(key, "O") for key in ("labels", "type", "X", "Y", "Z")])
    for index, label in enumerate(labels):
        kind = chantypes[index] if chantypes else "EEG"
        position = positions[index] if positions else None
        coords = position if position is not None else (empty, empty, empty)
        chanlocs[0, index] = (label, kind, *coords)
    fdt = path.with_suffix(".fdt")
    data: Any = fdt.name
    if embedded:
        data = samples if trials == 1 else samples.reshape(len(labels), points, trials, order="F")
    eeg: dict[str, Any] = {
        "setname": "synthetic",
        "filename": path.name,
        "filepath": "",
        "subject": "",
        "comments": "",
        "history": "",
        "nbchan": float(len(labels)),
        "trials": float(trials),
        "pnts": float(points),
        "srate": float(sfreq),
        "xmin": 0.0,
        "xmax": (points - 1) / sfreq,
        "times": empty,
        "data": data,
        "chanlocs": chanlocs,
        "event": empty,
        "epoch": empty,
        "urevent": empty,
        "ref": "common",
        "icawinv": empty,
        "icasphere": empty,
        "icaweights": empty,
        "icaact": empty,
        "chaninfo": {"plotrad": empty, "shrink": empty, "nosedir": "+X"},
    }
    if trials > 1:  # one 'stim' event at the start of every epoch
        event = np.zeros((1, trials), dtype=[(key, "O") for key in ("type", "latency", "epoch")])
        epoch = np.zeros((1, trials), dtype=[(key, "O") for key in ("event", "eventtype", "eventlatency")])
        for trial in range(trials):
            event[0, trial] = ("stim", float(trial * points + 1), float(trial + 1))
            epoch[0, trial] = (float(trial + 1), "stim", 0.0)
        eeg["event"], eeg["epoch"] = event, epoch
    eeg.update(fields)
    if not embedded:
        fdt.write_bytes(samples.T.tobytes())
    scipy.io.savemat(path, eeg if top_level else {"EEG": eeg}, appendmat=False, format="5", oned_as="row")
    return path


def _write_set_v73(path: Path, *, labels: tuple[str, ...] = ("Fp1", "Fp2", "Cz"), subject: str = "") -> Path:
    """A MATLAB v7.3 (HDF5) EEGLAB data set of 2 s at 128 Hz with a .fdt data file, written with h5py.

    Layout as MATLAB writes it: a 512-byte user block with the MAT header (version 0x0200), the EEG
    structure as a group, texts as uint16 'char' datasets, empty values marked MATLAB_empty, and the
    fields of the chanlocs structure array as references into '#refs#'.
    """
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

    points, sfreq = 256, 128.0
    samples = np.random.default_rng(0).normal(0.0, 5.0, (len(labels), points)).astype("<f4")
    fdt = path.with_suffix(".fdt")
    fdt.write_bytes(samples.T.tobytes())
    with h5py.File(path, "w", userblock_size=512) as handle:
        refs = handle.create_group("#refs#")
        eeg = handle.create_group("EEG")
        eeg.attrs["MATLAB_class"] = np.bytes_(b"struct")
        texts = {"setname": "synthetic", "filename": path.name, "data": fdt.name, "ref": "common"}
        for key in ("filepath", "comments", "history"):
            texts[key] = ""
        texts["subject"] = subject
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
        handle.write(
            b"MATLAB 7.3 MAT-file, written by NeuroGrid tests".ljust(116) + b"\x00" * 8 + b"\x00\x02IM"
        )
    return path


@pytest.mark.parametrize(("path", "streamable"), [(SET_OK, True), (SET_EMBEDDED, False)])
def test_eeglab_read_gives_the_data_model(path: Path, streamable: bool) -> None:
    recording = EeglabAdapter().read(path, recording_id="rec-s", relative_path="rec.set")
    assert recording.format == "EEGLAB" and recording.id == "rec-s"
    assert [ch.name for ch in recording.channels] == list(EEG_LABELS)
    assert {(ch.type, ch.unit, ch.sampling_rate_hz, ch.position) for ch in recording.channels} == {
        ("EEG", "µV", 512.0, None)
    }
    assert recording.sampling_rate_hz == 512.0 and recording.duration_s == 4.0
    assert recording.streamable is streamable  # embedded data are loaded with the header (R14)
    assert recording.metadata_sources == HEADER_SOURCES


@pytest.mark.parametrize("path", [SET_OK, SET_EMBEDDED])
def test_eeglab_fixtures_are_clean_and_readable(path: Path) -> None:
    adapter = EeglabAdapter()
    inspection = adapter.inspect(path)
    assert inspection.issues == () and inspection.missing_companions == ()
    assert inspection.identifying_fields == ()
    assert adapter.read_check(path) is None


def test_empty_matlab_texts_are_not_identifying() -> None:
    """Regression: scipy writes empty MATLAB texts as empty arrays; they must not count as content."""
    eeg = _load(SET_OK)
    for key in ("subject", "filepath", "comments", "history"):
        assert isinstance(eeg[key], np.ndarray) and eeg[key].size == 0
        assert _text(eeg[key]) == ""
    assert EeglabAdapter().inspect(SET_OK).identifying_fields == ()


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (None, ""),
        (np.array([]), ""),
        ("Cz", "Cz"),
        (["first line", "second line"], "first line second line"),
        (np.array(["a", "b"]), "a b"),
        (3.0, "3.0"),
    ],
)
def test_eeglab_text_values(value: Any, text: str) -> None:
    assert _text(value) == text


@pytest.mark.parametrize(
    ("delta", "issue"), [(-4, "header.file_truncated"), (4, "header.file_trailing_data")]
)
def test_eeglab_fdt_size_against_the_header(tmp_path: Path, delta: int, issue: str) -> None:
    folder = _copy_folder("eeglab_ok", tmp_path)
    fdt = folder / "rec.fdt"
    data = fdt.read_bytes()
    fdt.write_bytes(data[:delta] if delta < 0 else data + b"\x00" * delta)
    inspection = EeglabAdapter().inspect(folder / "rec.set")
    assert inspection.issues == (issue,) and inspection.missing_companions == ()


def test_eeglab_missing_fdt(tmp_path: Path) -> None:
    folder = _copy_folder("eeglab_ok", tmp_path)
    (folder / "rec.fdt").unlink()
    adapter = EeglabAdapter()
    inspection = adapter.inspect(folder / "rec.set")
    assert inspection.missing_companions == ("companion.fdt",) and inspection.issues == ()
    assert adapter.read(folder / "rec.set", recording_id="r", relative_path="rec.set").streamable
    assert adapter.read_check(folder / "rec.set") == "FileNotFoundError"


def test_eeglab_fdt_reference_with_a_folder_is_not_followed(tmp_path: Path) -> None:
    """Like the BrainVision references (A-52, A-77), only a plain file name next to the .set is followed. MNE
    would follow "sub/rec.fdt" itself, so such a reference is reported and the data are never opened."""
    path = _write_set(tmp_path / "rec.set", data="sub/rec.fdt")
    (tmp_path / "sub").mkdir()
    (tmp_path / "rec.fdt").rename(tmp_path / "sub" / "rec.fdt")
    adapter = EeglabAdapter()
    inspection = adapter.inspect(path)
    assert inspection.missing_companions == ("companion.unsafe_reference",) and inspection.issues == ()
    assert adapter.read_check(path) == "UnsafePathError"


def test_eeglab_read_check_does_not_follow_unsafe_references(tmp_path: Path) -> None:
    folder = tmp_path / "dataset"
    folder.mkdir()
    path = _write_set(folder / "rec.set", data="../outside.fdt")
    (folder / "rec.fdt").rename(tmp_path / "outside.fdt")  # valid data, but outside the recording folder
    adapter = EeglabAdapter()
    assert adapter.inspect(path).missing_companions == ("companion.unsafe_reference",)
    # no concrete class name is specified; the point is that the outside file is not read as this recording
    assert adapter.read_check(path) is not None


@pytest.mark.parametrize("reference", ["../outside.fdt", "C:\\data\\rec.fdt", "\\\\server\\share\\rec.fdt"])
def test_eeglab_unsafe_fdt_reference(tmp_path: Path, reference: str) -> None:
    folder = tmp_path / "set"
    folder.mkdir()
    path = _write_set(folder / "rec.set", data=reference)
    (tmp_path / "outside.fdt").write_bytes((folder / "rec.fdt").read_bytes())
    inspection = EeglabAdapter().inspect(path)
    assert inspection.missing_companions == ("companion.unsafe_reference",) and inspection.issues == ()


def test_eeglab_channel_count_mismatch(tmp_path: Path) -> None:
    path = _write_set(tmp_path / "rec.set", nbchan=4.0)
    # the .fdt holds 3 channels, so it is also shorter than 4 channels need
    assert EeglabAdapter().inspect(path).issues == ("header.channel_count", "header.file_truncated")


@pytest.mark.parametrize(
    ("fields", "issues"),
    [
        ({"srate": 0.0}, ("header.sampling_rate",)),
        ({"srate": float("nan")}, ("header.sampling_rate",)),
        ({"srate": "fast"}, ("header.sampling_rate",)),
        ({"pnts": 0.0}, ("header.number_field",)),
        ({"pnts": "many"}, ("header.number_field",)),
        ({"nbchan": 0.0}, ("header.number_field",)),
    ],
)
def test_eeglab_invalid_header_numbers(
    tmp_path: Path, fields: dict[str, Any], issues: tuple[str, ...]
) -> None:
    path = _write_set(tmp_path / "rec.set", **fields)
    assert EeglabAdapter().inspect(path).issues == issues


@pytest.mark.parametrize("fields", [{"nbchan": 2.5}, {"nbchan": -3.0}, {"pnts": -5.0}])
def test_eeglab_invalid_counts_are_number_fields(tmp_path: Path, fields: dict[str, Any]) -> None:
    path = _write_set(tmp_path / "rec.set", **fields)
    # the invalid count is reported first; the exact (complete) issue list is the strict xfail below
    assert EeglabAdapter().inspect(path).issues[:1] == ("header.number_field",)


@pytest.mark.parametrize(
    "fields",
    [
        {"nbchan": 2.5},  # actual: number_field + file_trailing_data
        {"nbchan": 4.5},  # actual: number_field + file_truncated
        {"nbchan": -3.0},  # actual: number_field + file_trailing_data
        {"pnts": -5.0},  # actual: number_field + file_trailing_data
        {"pnts": 255.5},  # actual: file_trailing_data only
        {"nbchan": -3.0, "embedded": True},  # actual: number_field + data_shape
    ],
)
def test_eeglab_invalid_counts_give_only_the_number_field_issue(
    tmp_path: Path, fields: dict[str, Any]
) -> None:
    path = _write_set(tmp_path / "rec.set", **fields)
    assert EeglabAdapter().inspect(path).issues == ("header.number_field",)


def test_eeglab_negative_sample_count_gives_no_duration(tmp_path: Path) -> None:
    path = _write_set(tmp_path / "rec.set", pnts=-5.0)
    recording = EeglabAdapter().read(path, recording_id="r", relative_path="rec.set")
    assert recording.duration_s is None and "duration_s" not in recording.metadata_sources


def test_eeglab_invalid_rate_gives_no_rate_and_no_duration(tmp_path: Path) -> None:
    path = _write_set(tmp_path / "rec.set", srate=0.0)
    recording = EeglabAdapter().read(path, recording_id="r", relative_path="rec.set")
    assert recording.sampling_rate_hz is None and recording.duration_s is None
    assert {ch.sampling_rate_hz for ch in recording.channels} == {None}
    assert recording.metadata_sources == {"channels": "header"}


def test_eeglab_embedded_data_shape_against_the_header(tmp_path: Path) -> None:
    path = _write_set(tmp_path / "rec.set", embedded=True, pnts=300.0)
    assert EeglabAdapter().inspect(path).issues == ("header.data_shape",)
    good = _write_set(tmp_path / "good.set", embedded=True)
    assert EeglabAdapter().inspect(good).issues == ()


def test_eeglab_not_a_mat_file_is_unreadable(tmp_path: Path) -> None:
    junk = tmp_path / "junk.set"
    junk.write_bytes(b"this is not a MATLAB file" * 10)
    adapter = EeglabAdapter()
    for call in (adapter.inspect, lambda p: adapter.read(p, recording_id="r", relative_path="junk.set")):
        with pytest.raises(HeaderUnreadable) as info:
            call(junk)
        assert info.value.reason == "header.unreadable_container"
    assert adapter.read_check(junk) == "ValueError"  # the class name only (A-51)


@pytest.mark.parametrize("content", [{"x": 1.0}, {"EEG": 5.0}, {"EEG": {"srate": 128.0}}])
def test_mat_file_without_eeglab_structure_is_unreadable(tmp_path: Path, content: dict[str, Any]) -> None:
    import scipy.io

    path = tmp_path / "other.set"
    scipy.io.savemat(path, content, appendmat=False, format="5")
    with pytest.raises(HeaderUnreadable) as info:
        EeglabAdapter().inspect(path)
    assert info.value.reason == "header.unreadable_container"


def test_eeglab_fields_without_an_eeg_structure(tmp_path: Path) -> None:
    """Data sets whose fields are variables of the file (no EEG structure) are read the same way."""
    path = _write_set(tmp_path / "rec.set", top_level=True, subject="Max Mustermann")
    adapter = EeglabAdapter()
    recording = adapter.read(path, recording_id="r", relative_path="rec.set")
    assert [ch.name for ch in recording.channels] == ["Fp1", "Fp2", "Cz"]
    assert recording.sampling_rate_hz == 128.0 and recording.duration_s == 2.0
    inspection = adapter.inspect(path)
    assert inspection.issues == () and inspection.identifying_fields == ("patient",)
    assert adapter.read_check(path) is None


def test_eeglab_matlab_v73_data_set(tmp_path: Path) -> None:
    """A-77: EEGLAB is read with pymatreader from MAT v5 and v7.3 (HDF5)."""
    path = _write_set_v73(tmp_path / "rec.set")
    adapter = EeglabAdapter()
    recording = adapter.read(path, recording_id="r", relative_path="rec.set")
    assert [(ch.name, ch.type, ch.position) for ch in recording.channels] == [
        ("Fp1", "EEG", None),
        ("Fp2", "EEG", None),
        ("Cz", "EEG", None),
    ]
    assert recording.sampling_rate_hz == 128.0 and recording.duration_s == 2.0 and recording.streamable
    inspection = adapter.inspect(path)
    # empty HDF5 texts (MATLAB_empty) count as empty, as in MAT v5
    assert inspection == HeaderInspection()
    assert adapter.read_check(path) is None
    (tmp_path / "rec.fdt").write_bytes(b"\x00" * 16)
    assert adapter.inspect(path).issues == ("header.file_truncated",)
    named = _write_set_v73(tmp_path / "named.set", subject="Max Mustermann")
    assert adapter.inspect(named).identifying_fields == ("patient",)


def test_eeglab_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eeglab, "MAX_SET_BYTES", 1000)
    with pytest.raises(HeaderUnreadable) as info:
        EeglabAdapter().inspect(SET_OK)
    assert info.value.reason == "header.too_large"


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"subject": "Max Mustermann"}, ("patient",)),
        ({"subject": "sub-01"}, ("patient",)),  # pseudonymous codes count as well (A-64)
        ({"subject": "anonymous"}, ()),
        ({"subject": "n/a"}, ()),
        ({"filepath": "data"}, ("recording",)),  # any original folder
        ({"comments": "Recorded by Jane Doe"}, ("recording",)),
        ({"history": "EEG = pop_loadset('filepath', 'D:\\study\\');"}, ("recording",)),
        ({"setname": "rest 4711234"}, ("recording",)),
        ({"comments": "Session on 2021-08-24"}, ("date",)),
        ({"comments": "Session on 01-JAN-2000"}, ()),  # a date placeholder
        (
            {"subject": "Max Mustermann", "setname": "Max Mustermann 24.08.21"},
            ("patient", "recording", "date"),
        ),
        ({"comments": "resting state, eyes closed"}, ()),
    ],
)
def test_eeglab_identifying_fields(tmp_path: Path, fields: dict[str, Any], expected: tuple[str, ...]) -> None:
    path = _write_set(tmp_path / "rec.set", **fields)
    inspection = EeglabAdapter().inspect(path)
    assert inspection.identifying_fields == expected and inspection.issues == ()


def test_eeglab_identifying_values_are_never_taken_over(tmp_path: Path) -> None:
    path = _write_set(
        tmp_path / "rec.set",
        subject="Max Mustermann",
        comments="Recorded by Jane Doe",
        filepath="C:\\Users\\jdoe\\study",
        setname="rest 4711234",
    )
    assert EeglabAdapter().inspect(path).identifying_fields == ("patient", "recording")
    dumped = EeglabAdapter().read(path, recording_id="r", relative_path="rec.set").model_dump_json()
    assert not any(value in dumped for value in ("Mustermann", "Jane", "jdoe", "4711234"))  # A-51


def test_eeglab_channel_types_and_positions(tmp_path: Path) -> None:
    path = _write_set(
        tmp_path / "rec.set",
        labels=("Cz", "HEOG", "ECG", "Pz"),
        chantypes=("EEG", "EOG", "", "misc"),
        positions=((0.0, 0.0, 0.1), (0.0123456789, -0.05, 0.02), None, (0.0, 0.0, 0.0)),
    )
    recording = EeglabAdapter().read(path, recording_id="r", relative_path="rec.set")
    assert [(ch.name, ch.type, ch.position) for ch in recording.channels] == [
        ("Cz", "EEG", "0,0,0.1"),
        ("HEOG", "EOG", "0.0123457,-0.05,0.02"),
        ("ECG", "ECG", None),  # no declared type: the label decides
        ("Pz", "MISC", None),  # all-zero coordinates are no position
    ]
    assert recording.metadata_sources["position"] == "header"
    assert recording.sampling_rate_hz == 128.0


def test_chanlocs_as_a_list_of_structures() -> None:
    eeg = {"chanlocs": [{"labels": "Cz", "type": "EEG"}, "not a structure", {"labels": "Pz"}]}
    assert _chanlocs(eeg) == [{"labels": "Cz", "type": "EEG"}, {"labels": "Pz"}]
    assert _chanlocs({"chanlocs": np.array([])}) == []
    assert _chanlocs({}) == []


def test_chanlocs_as_a_structure_of_arrays() -> None:
    """pymatreader returns a struct array as one mapping of per-field values (numpy arrays or lists)."""
    locs = {"labels": np.array(["Cz", "Pz"]), "type": np.str_("EEG"), "X": np.array([0.1, 0.2]), "Y": None}
    assert _chanlocs({"chanlocs": locs}) == [
        {"labels": "Cz", "type": "EEG", "X": 0.1, "Y": None, "Z": None},
        {"labels": "Pz", "type": "EEG", "X": 0.2, "Y": None, "Z": None},
    ]


def test_eeglab_single_channel_data_set(tmp_path: Path) -> None:
    path = _write_set(tmp_path / "one.set", labels=("Cz",))
    recording = EeglabAdapter().read(path, recording_id="r", relative_path="one.set")
    assert [(ch.name, ch.type) for ch in recording.channels] == [("Cz", "EEG")]
    assert recording.sampling_rate_hz == 128.0


def test_eeglab_epoched_data_set(tmp_path: Path) -> None:
    import mne

    path = _write_set(tmp_path / "ep.set", trials=3)
    adapter = EeglabAdapter()
    recording = adapter.read(path, recording_id="r", relative_path="ep.set")
    assert recording.duration_s == 3 * 256 / 128 and recording.streamable
    assert adapter.inspect(path).issues == ()  # the .fdt holds all three epochs
    # the raw reader refuses epoched files, so a successful check shows the epochs path is taken
    with pytest.raises(TypeError):
        mne.io.read_raw_eeglab(path, preload=False, verbose="error")
    assert adapter.read_check(path) is None
    embedded = _write_set(tmp_path / "epe.set", trials=3, embedded=True)
    assert adapter.inspect(embedded).issues == () and adapter.read_check(embedded) is None


class _FakeEpochs:
    """Three epochs of two channels with 50 samples at 100 Hz."""

    def __init__(self) -> None:
        self.ch_names = ["Cz", "Pz"]
        self.info = {"sfreq": 100.0}
        self.times = np.arange(50) / 100.0
        self.data = np.arange(3 * 2 * 50, dtype=float).reshape(3, 2, 50)
        self.items: list[Any] = []

    def get_data(self, *, item: Any, verbose: str) -> np.ndarray:
        self.items.append(item)
        return self.data[item]


def test_epochs_view_exposes_what_the_read_check_needs(tmp_path: Path) -> None:
    epochs = _FakeEpochs()
    opened: list[tuple[Path, str]] = []

    def reader(path: Path, *, verbose: str) -> _FakeEpochs:
        opened.append((path, verbose))
        return epochs

    view = _EpochsAsRaw(reader)(tmp_path / "x.set", preload=False, verbose="error")
    assert opened == [(tmp_path / "x.set", "error")]
    assert view.ch_names == ["Cz", "Pz"] and view.n_times == 50 and view.info["sfreq"] == 100.0
    window = view.get_data(start=10, stop=20, verbose="error")
    assert window.shape == (1, 2, 10) and np.array_equal(window, epochs.data[[0], :, 10:20])
    assert mne_read_check(_EpochsAsRaw(reader), tmp_path / "x.set") is None
    assert epochs.items == [[0], [0], [0]]  # only the first epoch is read


def test_epochs_reader_failure_is_reported_by_class_name(tmp_path: Path) -> None:
    def reader(path: Path, *, verbose: str) -> Any:
        raise KeyError("epoch")

    assert mne_read_check(_EpochsAsRaw(reader), tmp_path / "x.set") == "KeyError"


# --- FIF -------------------------------------------------------------------------------------------------

FIF_NAMES = ("Fp1", "Fp2", "Cz", "EOG 061", "MEG 0111", "MEG 0112", "STI 014")
FIF_TYPES = ("eeg", "eeg", "eeg", "eog", "mag", "grad", "stim")
FIF_POSITIONS = {"Fp1": (-0.03, 0.08, 0.02), "Fp2": (0.03, 0.08, 0.02), "Cz": (0.0, 0.0, 0.1)}
MEAS_DATE = datetime.datetime(2021, 8, 24, 10, 0, tzinfo=datetime.UTC)
PERSON = {
    "his_id": "P-4711",
    "first_name": "Max",
    "last_name": "Mustermann",
    "birthday": datetime.date(1980, 5, 1),
}


def _write_fif(
    path: Path,
    *,
    names: tuple[str, ...] = FIF_NAMES,
    types: tuple[str, ...] = FIF_TYPES,
    montage: str | None = "explicit",
    line_freq: float | None = 50.0,
    subject_info: dict[str, Any] | None = None,
    meas_date: datetime.datetime | None = None,
    experimenter: str | None = None,
    description: str | None = None,
    proj_name: str | None = None,
    anonymize: bool = False,
) -> Path:
    import mne

    info = mne.create_info(list(names), 256.0, list(types))
    raw = mne.io.RawArray(np.zeros((len(names), 512)), info, verbose="error")
    if montage == "explicit":
        dig = mne.channels.make_dig_montage(ch_pos=dict(FIF_POSITIONS), coord_frame="head")
        raw.set_montage(dig, on_missing="ignore", verbose="error")
    elif montage is not None:
        raw.set_montage(mne.channels.make_standard_montage(montage), on_missing="ignore", verbose="error")
    raw.info["line_freq"] = line_freq
    if subject_info is not None:
        raw.info["subject_info"] = dict(subject_info)
    if experimenter is not None:
        raw.info["experimenter"] = experimenter
    if description is not None:
        raw.info["description"] = description
    if proj_name is not None:
        raw.info["proj_name"] = proj_name
    if meas_date is not None:
        raw.set_meas_date(meas_date)
    if anonymize:
        raw.anonymize(verbose="error")
    raw.save(path, overwrite=True, verbose="error")
    return path


def test_fif_read_gives_the_data_model(tmp_path: Path) -> None:
    path = _write_fif(tmp_path / "rec_raw.fif")
    recording = FifAdapter().read(path, recording_id="rec-f", relative_path="rec_raw.fif")
    assert recording.format == "FIF" and recording.id == "rec-f"
    assert [(ch.name, ch.type, ch.unit, ch.position) for ch in recording.channels] == [
        ("Fp1", "EEG", "V", "-0.03,0.08,0.02"),
        ("Fp2", "EEG", "V", "0.03,0.08,0.02"),
        ("Cz", "EEG", "V", "0,0,0.1"),
        ("EOG 061", "EOG", "V", None),
        ("MEG 0111", "MEG", "T", None),
        ("MEG 0112", "MEG", "T/m", None),
        ("STI 014", "TRIG", "V", None),
    ]
    assert {ch.sampling_rate_hz for ch in recording.channels} == {256.0}
    assert recording.sampling_rate_hz == 256.0 and recording.duration_s == 2.0
    assert recording.line_frequency_hz == 50.0 and recording.streamable
    assert recording.metadata_sources == HEADER_SOURCES | {
        "line_frequency_hz": "header",
        "position": "header",
    }


def test_fif_standard_montage_gives_eeg_positions(tmp_path: Path) -> None:
    path = _write_fif(tmp_path / "rec_raw.fif", montage="colin27_1020", line_freq=60.0)
    recording = FifAdapter().read(path, recording_id="r", relative_path="rec_raw.fif")
    positions = {ch.name: ch.position for ch in recording.channels}
    assert [name for name, position in positions.items() if position is not None] == ["Fp1", "Fp2", "Cz"]
    coords = {
        name: [float(value) for value in position.split(",")]
        for name, position in positions.items()
        if position is not None
    }
    assert all(
        len(xyz) == 3 and 0.05 < float(np.linalg.norm(xyz)) < 0.15 for xyz in coords.values()
    )  # metres
    # head coordinates: +x right, +y front, +z up
    assert coords["Fp1"][0] < 0 < coords["Fp2"][0]
    assert min(coords["Fp1"][1], coords["Fp2"][1]) > coords["Cz"][1]
    assert coords["Cz"][2] > max(coords["Fp1"][2], coords["Fp2"][2])
    assert recording.line_frequency_hz == 60.0
    assert recording.metadata_sources["position"] == "header"


def test_fif_without_eeg_line_frequency_or_positions(tmp_path: Path) -> None:
    path = _write_fif(
        tmp_path / "meg_raw.fif",
        names=("MEG 0111", "T1"),
        types=("mag", "temperature"),
        montage=None,
        line_freq=None,
    )
    recording = FifAdapter().read(path, recording_id="r", relative_path="meg_raw.fif")
    assert [(ch.type, ch.unit) for ch in recording.channels] == [("MEG", "T"), ("MISC", None)]
    assert recording.sampling_rate_hz is None and recording.line_frequency_hz is None
    assert recording.duration_s == 2.0 and recording.metadata_sources == HEADER_SOURCES


def test_fif_identifying_fields(tmp_path: Path) -> None:
    path = _write_fif(
        tmp_path / "rec_raw.fif", subject_info=PERSON, meas_date=MEAS_DATE, experimenter="Dr. Jane Doe"
    )
    inspection = FifAdapter().inspect(path)
    assert inspection.identifying_fields == ("patient", "recording", "date")
    assert inspection.issues == () and inspection.missing_companions == ()
    dumped = FifAdapter().read(path, recording_id="r", relative_path="rec_raw.fif").model_dump_json()
    assert "Mustermann" not in dumped and "Jane" not in dumped and "P-4711" not in dumped


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({}, ()),
        ({"subject_info": {"his_id": "0"}}, ()),  # a placeholder
        ({"subject_info": {"his_id": "sub-01"}}, ("patient",)),
        ({"subject_info": {"birthday": datetime.date(1980, 5, 1)}}, ("patient",)),
        ({"experimenter": "lab"}, ("recording",)),  # any experimenter
        ({"experimenter": "   "}, ()),  # blank
        ({"description": "resting state"}, ()),
        ({"description": "copied from C:\\Users\\jane\\meg"}, ("recording",)),
        ({"proj_name": "Study of John Smith"}, ("recording",)),
        ({"proj_name": "rest"}, ()),
        ({"meas_date": MEAS_DATE}, ("date",)),
        # each marker that MNE writes when anonymising is enough to treat the date as shifted
        ({"meas_date": MEAS_DATE, "experimenter": "mne_anonymize"}, ()),
        ({"meas_date": MEAS_DATE, "description": "Anonymized using a time shift"}, ()),
    ],
)
def test_fif_identifying_cases(tmp_path: Path, options: dict[str, Any], expected: tuple[str, ...]) -> None:
    path = _write_fif(tmp_path / "rec_raw.fif", **options)
    assert FifAdapter().inspect(path).identifying_fields == expected


def test_fif_anonymized_file_has_no_identifying_fields(tmp_path: Path) -> None:
    path = _write_fif(
        tmp_path / "anon_raw.fif",
        subject_info={"his_id": "P-4711"},
        meas_date=MEAS_DATE,
        experimenter="Dr. Jane Doe",
        anonymize=True,
    )
    # the shifted measurement date of an MNE-anonymised file is not a real date
    assert FifAdapter().inspect(path).identifying_fields == ()


@pytest.mark.parametrize(
    "person",
    [
        {key: PERSON[key] for key in ("his_id", "first_name", "last_name")},  # names become 'mne_anonymize'
        PERSON,  # plus the birthday, shifted by the same time as the date
    ],
)
def test_fif_anonymized_file_with_person_fields_has_no_identifying_fields(
    tmp_path: Path, person: dict[str, Any]
) -> None:
    path = _write_fif(
        tmp_path / "anon_raw.fif",
        subject_info=person,
        meas_date=MEAS_DATE,
        experimenter="Dr. Jane Doe",
        anonymize=True,
    )
    assert FifAdapter().inspect(path).identifying_fields == ()


def test_broken_fif_is_unreadable(tmp_path: Path) -> None:
    good = _write_fif(tmp_path / "good_raw.fif")
    broken = tmp_path / "broken_raw.fif"
    broken.write_bytes(good.read_bytes()[:300])
    junk = tmp_path / "junk_raw.fif"
    junk.write_bytes(b"\x00" * 200)
    adapter = FifAdapter()
    for path in (broken, junk):
        for call in (adapter.inspect, lambda p: adapter.read(p, recording_id="r", relative_path="x.fif")):
            with pytest.raises(HeaderUnreadable) as info:
                call(path)
            assert info.value.reason == "header.unreadable_container"
        assert adapter.read_check(path) == "ValueError"  # the class name only (A-51)
    assert adapter.read_check(good) is None


@pytest.mark.parametrize(
    ("loc", "expected"),
    [
        (np.array([0.01, -0.02, 0.03, 1.0]), "0.01,-0.02,0.03"),
        (np.zeros(12), None),
        (np.array([np.nan, 0.0, 0.1]), None),
        (np.array([np.inf, 0.0, 0.1]), None),
    ],
)
def test_fif_position_from_loc(loc: np.ndarray, expected: str | None) -> None:
    assert _position(loc) == expected


# --- identifying-content heuristics (A-51, A-64) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", True),
        ("X X X X", True),
        ("Anonymous", True),
        ("n/a", True),
        ("- _ 0 none unknown", True),
        ("X Mueller", False),
        ("sub-01", False),
    ],
)
def test_placeholder(text: str, expected: bool) -> None:
    assert placeholder(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Recorded 2021-08-24", True),
        ("02-MAR-2002", True),
        ("24.08.21", True),
        ("on 24/08/2021", True),
        ("seen_2002-03-02", True),  # underscores stand for spaces in EDF+
        ("01-JAN-1985", False),
        ("01.01.85", False),
        ("2002/01/01", False),
        ("1970-1-1", False),
        ("at 14:03:22", False),
        ("version 1.13.2", False),
        ("20210824", False),
    ],
)
def test_real_dates(text: str, expected: bool) -> None:
    assert real_dates(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Recorded 2021-08-24", True),  # everything real_dates finds
        ("born_12_03_1961", True),  # underscores as date separators
        ("born_12_03_61", True),
        ("born 12 Mar 1961", True),
        ("born March 1961", True),
        ("seen 3rd of", False),
        ("seen 3rd Sept", True),
        ("born 1961", True),
        ("01-JAN-1985", True),  # the year stays hidden in the display rule
        ("2002/01/01", True),
        ("Lights off 22.31", True),
        ("Lights off at 23.05", True),
        ("22h31", True),
        ("10.30 pm", True),
        ("8 PM", True),
        ("01.01.85", False),  # the A-05 placeholder date
        ("at 14:03:22", False),  # not displayable anyway (colon, A-17)
        ("version 1.13.2", False),
        ("v1.2.10", False),
        ("R1.10.2", False),
        ("Stim 1.50", False),
        ("contrast_0.25", False),
        ("EEG 10-20", False),
        ("S1999", False),  # glued to letters: a code, not a year
        ("Marker 12", False),
        ("Decimal 10", False),
        ("lights off 2231", False),  # four digits that are no year: indistinguishable from a code
    ],
)
def test_dates_or_times(text: str, expected: bool) -> None:
    """The display rule's view (C5, A-51); the A-05 header heuristic real_dates stays narrow."""
    assert dates_or_times(text) is expected
    assert not real_dates("born 1961") and not real_dates("Lights off 22.31")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("John Smith", True),
        ("Wang_Li", True),  # underscores stand for spaces
        ("Smith, John", True),
        ("KV 4711234", True),
        ("Müller", True),
        ("bad \ufffd byte", True),
        ("C:\\Users\\lab", True),
        ("d:/data", True),
        ("\\\\server\\share", True),
        ("stored in /home/lab/eeg", True),
        ("resting state eyes closed", False),
        ("EEG-64 amplifier", False),
        ("12345", False),
        ("data/rec.eeg", False),
    ],
)
def test_looks_identifying(text: str, expected: bool) -> None:
    assert looks_identifying(text) is expected


# --- channel types and standard names (A-18, M04) --------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "kind"),
    [
        ("  bdf annotations ", "ANNOT"),
        ("EOG left", "EOG"),
        ("EKG", "ECG"),
        ("SpO2", "MISC"),
        ("Pleth", "MISC"),
        ("Pulse", "MISC"),
        ("Temp rectal", "MISC"),
        ("Snore", "MISC"),
        ("Light", "MISC"),
        ("Position", "MISC"),
        ("Leg/L", "EMG"),
        ("Chin1-Chin2", "EMG"),
        ("Trigger", "TRIG"),
        ("STI 014", "TRIG"),
        ("PO3", "EEG"),  # not the body position channel
        ("POz", "EEG"),
        ("EXG1", "EEG"),
        ("AFF1h", "EEG"),
    ],
)
def test_channel_type_by_label(label: str, kind: str) -> None:
    assert classify(label) == kind


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Fp1", ("Fp1", "1020")),
        ("fp1", ("Fp1", "1020")),  # case does not matter
        ("FPZ", ("Fpz", "1020")),
        ("EEG Fp1", ("Fp1", "1020")),  # leading type word
        ("eeg:Cz", ("Cz", "1020")),
        ("EEG_O2", ("O2", "1020")),
        ("EEG FP1-REF", ("Fp1", "1020")),  # trailing reference
        ("C3-AVG", ("C3", "1020")),
        ("T3_LE", ("T3", "1020")),  # old 10-20 alias
        ("O1 AR", ("O1", "1020")),
        ("Pz-Cz", ("Pz", "1020")),
        ("Cz", ("Cz", "1020")),  # the reference name itself stays
        ("C3-A2", ("C3-A2", "1020")),  # referential derivation to a mastoid site
        ("Fp1-F7", ("Fp1-F7", "1020")),  # bipolar
        ("Fp1 - F7", ("Fp1-F7", "1020")),
        ("EEG Fp1-F7-REF", ("Fp1-F7", "1020")),
        ("AFF1h", ("AFF1h", "1005")),  # 10-05 only
        ("EEG aff1h-REF", ("AFF1h", "1005")),
        ("Fp1-AFF1h", ("Fp1-AFF1h", "1005")),  # the wider system wins
        ("EXG1", None),
        ("Fp1-EXG1", None),
        ("Fp1-F7-O1", None),
        ("EEGFp1", None),
        ("", None),
    ],
)
def test_standard_name(label: str, expected: tuple[str, str] | None) -> None:
    assert standard_name(label) == expected


def test_standard_name_with_channel_map() -> None:
    mapping = {"EXG1": "Cz", "E7": "aff1h", "Fp1": "Bogus"}
    assert standard_name("EXG1", mapping) == ("Cz", "1020")
    assert standard_name("E7", mapping) == ("AFF1h", "1005")
    assert standard_name("Fp1", mapping) is None  # the mapping wins, also when its target is no standard name
    assert standard_name("F3", mapping) == ("F3", "1020")  # labels without an entry are matched as usual
    assert standard_name("EXG1", {}) is None


def test_montage_name_lists() -> None:
    assert not SYSTEM_1020 & ONLY_1005
    assert {"Fp1", "Fpz", "T3", "T4", "T5", "T6", "T7", "P8", "A1", "A2", "M1", "M2", "Iz"} <= SYSTEM_1020
    assert {"AFF1h", "AFp1", "I1", "PPO9"} <= ONLY_1005
    assert not {"Nz", "LPA", "RPA", "EXG1"} & (SYSTEM_1020 | ONLY_1005)


def test_montage_names_are_up_to_date() -> None:
    result = subprocess.run(
        [sys.executable, "tools/gen_montage_names.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout


# --- EDF+D (A-12, A-77) ------------------------------------------------------------------------------------


def test_edf_plus_d_is_read_as_one_discontinuous_recording() -> None:
    """Ten one-second records with a five-second gap: read like a continuous file, marked discontinuous."""
    path = FIX / "edf_plus_d" / "rec.edf"
    adapter = EdfAdapter()
    recording = adapter.read(path, recording_id="r", relative_path="rec.edf")
    assert recording.discontinuous is True
    assert [ch.type for ch in recording.channels] == ["EEG"] * 8 + ["ANNOT"]
    assert recording.duration_s == 10.0  # the data records; the gap holds no data
    assert adapter.inspect(path) == HeaderInspection()
    assert adapter.read_check(path) is None
    continuous = adapter.read(FIX / "edf_ok" / "rec_a.edf", recording_id="r", relative_path="rec_a.edf")
    assert continuous.discontinuous is False


def test_edf_plus_d_record_onsets_are_in_the_file() -> None:
    """The fixture really is discontinuous: the annotation signal of record 6 starts at +10 s."""
    data = (FIX / "edf_plus_d" / "rec.edf").read_bytes()
    assert data[192:197] == b"EDF+D"
    header_bytes = int(data[184:192])
    record_bytes = 8 * 512 * 2 + gen_fixtures.ANNOTATION_SAMPLES * 2
    sixth = data[header_bytes + 5 * record_bytes : header_bytes + 6 * record_bytes]
    assert sixth[-gen_fixtures.ANNOTATION_SAMPLES * 2 :].startswith(b"+10\x14\x14\x00")


@pytest.mark.parametrize("unit", ["A-", "A'", "Ab "])
def test_name_heuristic_is_linear_on_long_comment_text(unit: str) -> None:
    """A-53: a 2 MB BrainVision comment of repeated name-like pieces must not take hours (the unbounded
    name pattern backtracked quadratically); the bounded pattern still finds real names."""
    import time

    text = unit * (2_000_000 // len(unit))
    start = time.perf_counter()
    looks_identifying(text)
    assert time.perf_counter() - start < 20
    assert looks_identifying("x-John Smith") and looks_identifying("Recorded by Wang Li")
    assert not looks_identifying("Fp1 Fp2 Cz") and not looks_identifying("A" + "b" * 60 + " Cd")
