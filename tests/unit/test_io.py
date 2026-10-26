"""EDF header parser, data model view, channel types and dataset discovery (M01, A-12, A-51, A-64)."""

from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath

import pytest

from conftest import dir_link
from neurogrid.io.base import HeaderUnreadable
from neurogrid.io.channels import classify
from neurogrid.io.discover import pseudonym, scan
from neurogrid.io.edf import SIGNAL_FIELDS, EdfAdapter, parse_header, to_recording

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
SRC = FIX / "edf_ok" / "rec_a.edf"
N_SIGNALS = 8


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def _patch(source: Path, target: Path, offset: int, value: bytes) -> Path:
    data = bytearray(source.read_bytes())
    data[offset : offset + len(value)] = value
    return _write(target, bytes(data))


def _signal_offset(name: str) -> int:
    """Start of a per-signal field block in a header with N_SIGNALS signals."""
    offset = 0
    for field, width in SIGNAL_FIELDS:
        if field == name:
            return 256 + N_SIGNALS * offset
        offset += width
    raise KeyError(name)


def test_valid_header_and_data_model() -> None:
    header = parse_header(SRC)
    assert header.variant == "EDF" and header.plus is None and header.issues == ()
    assert header.identifying_fields == ()
    recording = to_recording(header, recording_id="rec-1", relative_path="rec_a.edf")
    assert len(recording.eeg_channels) == 8 and recording.sampling_rate_hz == 512.0
    assert recording.duration_s == 10.0 and recording.path == "rec_a.edf" and recording.id == "rec-1"
    channel = recording.eeg_channels[0]
    assert channel.sampling_rate_hz == 512.0 and channel.recording_id == "rec-1"
    assert channel.physical_range == (-500.0, 500.0)
    assert channel.resolution == pytest.approx(1000.0 / 65535)
    assert recording.metadata_sources == {
        "channels": "header",
        "sampling_rate_hz": "header",
        "duration_s": "header",
    }
    assert "path" not in recording.model_dump(mode="json")


def test_signal_layout_matches_the_specification() -> None:
    assert sum(width for _name, width in SIGNAL_FIELDS) == 256
    assert _signal_offset("spr") == 256 + N_SIGNALS * 216
    assert _signal_offset("reserved") == 256 + N_SIGNALS * 224


def test_exact_sampling_rate_from_ascii_fields(tmp_path: Path) -> None:
    """550 samples per 1.1-s record is exactly 500 Hz; binary floating point would give 499.99999999999994."""
    data = bytearray(SRC.read_bytes())
    data[244:252] = b"1.1     "
    spr = _signal_offset("spr")
    for index in range(N_SIGNALS):
        data[spr + 8 * index : spr + 8 * index + 8] = b"550     "
    recording = to_recording(
        parse_header(_write(tmp_path / "r.edf", bytes(data))), recording_id="r", relative_path="r.edf"
    )
    assert recording.sampling_rate_hz == 500.0
    assert {ch.sampling_rate_hz for ch in recording.channels} == {500.0}


@pytest.mark.parametrize("value", [b"nan     ", b"inf     ", b"1e400   ", b"-inf    ", b"0       "])
def test_non_finite_or_zero_record_duration_is_a_header_issue(tmp_path: Path, value: bytes) -> None:
    header = parse_header(_patch(SRC, tmp_path / "d.edf", 244, value))
    assert "header.record_duration" in header.issues
    recording = to_recording(header, recording_id="r", relative_path="d.edf")
    assert recording.sampling_rate_hz is None
    assert all(ch.sampling_rate_hz is None for ch in recording.channels)


def test_truncated_and_bad_ranges() -> None:
    assert "header.file_truncated" in parse_header(FIX / "edf_truncated" / "rec_trunc.edf").issues
    assert "header.digital_range" in parse_header(FIX / "edf_badheader" / "rec_bad.edf").issues


def test_identifying_fields_never_keep_values() -> None:
    header = parse_header(FIX / "edf_identifying" / "rec_named.edf")
    assert header.identifying_fields == ("patient", "date")
    assert "Zhang" not in repr(header)


def test_unreadable_headers(tmp_path: Path) -> None:
    with pytest.raises(HeaderUnreadable) as info:
        parse_header(_write(tmp_path / "short.edf", b"0" * 100))
    assert info.value.reason == "header.too_short"
    with pytest.raises(HeaderUnreadable) as info:
        parse_header(_patch(SRC, tmp_path / "v.edf", 0, b"9       "))
    assert info.value.reason == "header.bad_version"
    with pytest.raises(HeaderUnreadable) as info:
        parse_header(_patch(SRC, tmp_path / "n.edf", 252, b"0   "))
    assert info.value.reason == "header.bad_signal_count"
    with pytest.raises(HeaderUnreadable):
        parse_header(_write(tmp_path / "cut.edf", SRC.read_bytes()[:400]))


def test_malformed_fields(tmp_path: Path) -> None:
    issues = parse_header(_patch(SRC, tmp_path / "a.edf", 184, b"abc     ")).issues
    assert "header.size_field" in issues
    issues = parse_header(_patch(SRC, tmp_path / "b.edf", 236, b"-1      ")).issues
    assert "header.records_unknown" in issues
    issues = parse_header(_patch(SRC, tmp_path / "c.edf", 168, b"2026-1-1")).issues
    assert "header.startdate" in issues
    issues = parse_header(_patch(SRC, tmp_path / "d.edf", 8, "Zé".encode("latin-1"))).issues
    assert "header.non_ascii" in issues
    data = bytearray(SRC.read_bytes())
    data.extend(b"\x00" * 10)
    assert "header.file_trailing_data" in parse_header(_write(tmp_path / "e.edf", bytes(data))).issues
    issues = parse_header(_patch(SRC, tmp_path / "f.edf", _signal_offset("spr"), b"0       ")).issues
    assert "header.samples_per_record" in issues
    issues = parse_header(_patch(SRC, tmp_path / "g.edf", _signal_offset("pmin"), b"xx      ")).issues
    assert "header.number_field" in issues
    issues = parse_header(_patch(SRC, tmp_path / "h.edf", _signal_offset("pmin"), b"500     ")).issues
    assert "header.physical_range" in issues


def _with_fields(
    tmp_path: Path, name: str, *, patient: bytes, recording: bytes, plus: bool, start: bytes
) -> Path:
    data = bytearray(SRC.read_bytes())
    data[8:88] = patient.ljust(80)
    data[88:168] = recording.ljust(80)
    data[168:176] = start
    data[192:236] = (b"EDF+C" if plus else b"").ljust(44)
    return _write(tmp_path / name, bytes(data))


@pytest.mark.parametrize(
    ("patient", "recording", "plus", "start", "expected"),
    [
        # EDF+: every patient subfield except the sex counts, the recording field's date, code and technician
        (
            b"MCH-0234567 F 02-MAY-1951 Haagse_Harry",
            b"Startdate 02-MAR-2002 EMG561 BK/JOP Sony",
            True,
            b"01.01.85",
            ("patient", "recording", "date"),
        ),
        (b"MCH-0234567 X X X", b"Startdate X X X X", True, b"01.01.85", ("patient",)),
        (b"X F X X", b"Startdate X X Dr_Wang_Li X", True, b"01.01.85", ("recording",)),
        (b"X X X X", b"Startdate 01-JAN-1985 X X EEG-64", True, b"01.01.85", ()),
        (b"X X X X", b"Startdate X X X X", True, b"24.08.21", ("date",)),
        # plain EDF: any patient text other than a placeholder counts
        (b"ZHANG SAN", b"Startdate X X X X", False, b"01.01.85", ("patient",)),
        (b"KV-Nr 4711234567", b"", False, b"01.01.85", ("patient",)),
        (b"anonymous", b"Sleep study 4711234", False, b"01.01.85", ("recording",)),
        (b"X", b"Startdate 02-MAR-2002 X X X", False, b"01.01.85", ("date",)),
        # an empty or malformed start date is a header issue, not a real date
        (b"X X X X", b"", False, b"        ", ()),
    ],
)
def test_identifying_heuristics(
    tmp_path: Path, patient: bytes, recording: bytes, plus: bool, start: bytes, expected: tuple[str, ...]
) -> None:
    path = _with_fields(tmp_path, "i.edf", patient=patient, recording=recording, plus=plus, start=start)
    assert parse_header(path).identifying_fields == expected


def test_identifying_non_ascii_name(tmp_path: Path) -> None:
    path = _with_fields(
        tmp_path, "n.edf", patient="张三".encode("gbk"), recording=b"", plus=False, start=b"01.01.85"
    )
    header = parse_header(path)
    assert header.identifying_fields == ("patient",) and "header.non_ascii" in header.issues


def test_adapter_read_inspect_and_read_check(tmp_path: Path) -> None:
    adapter = EdfAdapter()
    assert adapter.read_check(SRC) is None
    assert adapter.read_check(_write(tmp_path / "junk.edf", b"0" * 300)) is not None
    assert adapter.inspect(FIX / "edf_badheader" / "rec_bad.edf").issues
    recording = adapter.read(SRC, recording_id="rec-x", relative_path="rec_a.edf")
    assert recording.format == "EDF" and len(recording.channels) == 8


@pytest.mark.parametrize(
    ("label", "kind"),
    [
        ("EEG Fp1", "EEG"),
        ("Cz", "EEG"),
        ("EOG E1-M2", "EOG"),
        ("EMG chin", "EMG"),
        ("ECG", "ECG"),
        ("EKG II", "ECG"),
        ("Resp nasal", "RESP"),
        ("SaO2", "MISC"),
        ("Status", "TRIG"),
        ("EDF Annotations", "ANNOT"),
    ],
)
def test_channel_types(label: str, kind: str) -> None:
    assert classify(label) == kind


def test_scan_raw_folder_pseudonymises() -> None:
    result = scan(FIX / "unsupported")
    assert not result.is_bids and result.subjects is None
    assert [f.display_id for f in result.recordings] == [pseudonym(PurePosixPath("rec_ok.edf"))]
    assert result.recordings[0].display_id.startswith("rec-")
    pseudo = pseudonym(PurePosixPath("rec_ok.edf"))
    assert result.recordings[0].identity == ("rec_ok.edf", pseudo, f"{pseudo}.edf")
    assert [f.suffix for f in result.unsupported] == [".cnt"]
    assert len(result.other) == 1
    shown = scan(FIX / "unsupported", show_paths=True)
    assert shown.recordings[0].display_id == "rec_ok.edf"
    assert shown.recordings[0].identity == result.recordings[0].identity


def _bids(tmp_path: Path) -> Path:
    (tmp_path / "dataset_description.json").write_text(
        json.dumps({"Name": "Demo", "License": "CC0", "BIDSVersion": "1.11.1", "Nested": {"x": 1}}),
        encoding="utf-8",
    )
    eeg = tmp_path / "sub-01" / "eeg"
    eeg.mkdir(parents=True)
    (eeg / "sub-01_ses-a_task-rest_run-1_eeg.edf").write_bytes(SRC.read_bytes())
    return eeg


def test_scan_bids_and_hidden(tmp_path: Path) -> None:
    eeg = _bids(tmp_path)
    (tmp_path / "derivatives").mkdir()
    (tmp_path / "derivatives" / "x.edf").write_bytes(b"x")
    (tmp_path / ".neurogrid").mkdir()
    (tmp_path / ".neurogrid" / "manifest.json").write_text("{}", encoding="utf-8")
    eeg.joinpath("sub-01_task-rest_events.tsv").write_text("onset\n", encoding="utf-8")
    eeg.joinpath("sub-02_task-rest_eeg.vhdr").write_text("", encoding="utf-8")
    eeg.joinpath("sub-02_task-rest_eeg.eeg").write_bytes(b"")
    result = scan(tmp_path)
    assert result.is_bids and result.description == {
        "Name": "Demo",
        "License": "CC0",
        "BIDSVersion": "1.11.1",
    }
    assert [f.display_id for f in result.recordings] == [
        "sub-01/eeg/sub-01_ses-a_task-rest_run-1_eeg.edf",
        "sub-01/eeg/sub-02_task-rest_eeg.vhdr",  # BrainVision is read since P2; .eeg is its companion
    ]
    assert dict(result.recordings[0].entities) == {"sub": "01", "ses": "a", "task": "rest", "run": "1"}
    assert "sub-01/eeg/sub-02_task-rest_eeg.eeg" in [f.relative.as_posix() for f in result.other]
    assert result.unsupported == []
    assert result.subjects == 2 and result.total_bytes > 0


def test_display_file_keeps_upper_case_extension(tmp_path: Path) -> None:
    eeg = _bids(tmp_path)
    eeg.joinpath("sub-01_ses-a_task-rest_run-1_eeg.edf").rename(eeg / "sub-01_task-rest_eeg.EDF")
    found = scan(tmp_path).recordings[0]
    assert found.display_file == "sub-01/eeg/sub-01_task-rest_eeg.EDF"


def test_folder_formats_are_unsupported_recordings(tmp_path: Path) -> None:
    (tmp_path / "rec.edf").write_bytes(SRC.read_bytes())
    mff = tmp_path / "sub01_rest.mff"
    mff.mkdir()
    (mff / "signal1.bin").write_bytes(b"\x00" * 100)
    (mff / "info.xml").write_text("<x/>", encoding="utf-8")
    mef = tmp_path / "sub02.mefd" / "Fp1.timd"
    mef.mkdir(parents=True)
    (mef / "Fp1.tdat").write_bytes(b"\x00" * 10)
    result = scan(tmp_path)
    assert sorted(f.suffix for f in result.unsupported) == [".mefd", ".mff"]
    assert {f.size_bytes for f in result.unsupported} == {104, 10}
    assert result.other == []  # the folder contents are not listed separately


def test_scan_skips_directory_links(tmp_path: Path) -> None:
    target = tmp_path / "real"
    target.mkdir()
    (target / "a.edf").write_bytes(b"x")
    root = tmp_path / "root"
    root.mkdir()
    dir_link(root / "linked", target)
    result = scan(root)
    assert result.links_skipped == 1 and result.recordings == []


def test_scan_skips_file_links(tmp_path: Path) -> None:
    target = tmp_path / "real.edf"
    target.write_bytes(b"x")
    root = tmp_path / "root"
    root.mkdir()
    try:
        Path(root / "b.edf").symlink_to(target)
    except OSError:
        pytest.skip("file symlinks not permitted on this system")
    result = scan(root)
    assert result.links_skipped == 1 and result.recordings == []


def test_linked_dataset_description_is_not_read(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "dataset_description.json").write_text('{"Name": "foreign"}', encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / "dataset_description.json").symlink_to(outside / "dataset_description.json")
    except OSError:
        pytest.skip("file symlinks not permitted on this system")
    result = scan(root)
    assert result.is_bids and result.description == {}


def test_scan_single_file_does_not_walk_the_folder(tmp_path: Path) -> None:
    (tmp_path / "dataset_description.json").write_text("not json", encoding="utf-8")
    (tmp_path / "a.edf").write_bytes(b"x")
    (tmp_path / "b.edf").write_bytes(b"x")
    sub = tmp_path / "deep"
    sub.mkdir()
    dir_link(sub / "link", tmp_path / "deep")
    result = scan(tmp_path, only=PurePosixPath("b.edf"))
    assert [f.relative.name for f in result.recordings] == ["b.edf"] and result.description == {}
    assert result.links_skipped == 0


def test_suspicious_names_are_counted_not_shown(tmp_path: Path) -> None:
    (tmp_path / "Müller").mkdir()
    (tmp_path / "Müller" / "rest.edf").write_bytes(b"x")
    (tmp_path / "id_4711234.edf").write_bytes(b"x")
    (tmp_path / "rec_01.edf").write_bytes(b"x")
    result = scan(tmp_path)
    assert result.suspicious_names == 2
    assert all(f.display_id.startswith("rec-") for f in result.recordings)


def test_undecodable_file_name_does_not_stop_the_scan(tmp_path: Path) -> None:
    """Windows: a lone surrogate in the name; Linux: the byte 0x80 (not valid UTF-8), listed by Python as
    the same surrogate escape. A file system that refuses the name skips the test (macOS)."""
    (tmp_path / "rec.edf").write_bytes(SRC.read_bytes())
    try:
        (tmp_path / "notiz_\udc80.txt").write_bytes(b"x")
        (tmp_path / "rec_\udc80.edf").write_bytes(b"x")
    except (OSError, UnicodeError):
        pytest.skip("file system refuses the name")
    raw = scan(tmp_path)
    shown = scan(tmp_path, show_paths=True)
    assert len(raw.recordings) == 2 and all(f.display_id.startswith("rec-") for f in raw.recordings)
    assert any("\\udc80" in f.display_id for f in shown.recordings)
    for f in shown.recordings:
        f.display_id.encode("utf-8")


def _annotation_only_edf(path: Path, duration: bytes = b"0") -> Path:
    """An EDF+C file with only the 'EDF Annotations' signal, like a hypnogram."""
    spr = 60
    tal = b"+0\x14\x14\x00+0\x1530\x14Sleep stage W\x14\x00"
    record = tal.ljust(2 * spr, b"\x00")
    header = bytearray()
    header += b"0".ljust(8)
    header += b"X X X X".ljust(80)
    header += b"Startdate X X X X".ljust(80)
    header += b"01.01.85" + b"00.00.00"
    header += str(512).encode().ljust(8)
    header += b"EDF+C".ljust(44)
    header += b"1".ljust(8) + duration.ljust(8) + b"1".ljust(4)
    header += b"EDF Annotations".ljust(16) + b"".ljust(80) + b"".ljust(8)
    header += b"-1".ljust(8) + b"1".ljust(8) + b"-32768".ljust(8) + b"32767".ljust(8)
    header += b"".ljust(80) + str(spr).encode().ljust(8) + b"".ljust(32)
    path.write_bytes(bytes(header) + record)
    return path


def _mixed_rate_edf(path: Path) -> Path:
    """Plain EDF, 2 records of 1 s: 'EEG Fz' at 512 Hz and 'ECG' at 256 Hz (rates differ per signal)."""
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
    path.write_bytes(bytes(header) + record * 2)
    return path


def test_read_check_keeps_library_warnings_inside(tmp_path: Path) -> None:
    import warnings

    path = _mixed_rate_edf(tmp_path / "psg.edf")
    assert parse_header(path).issues == ()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert EdfAdapter().read_check(path) is None
    assert caught == []


def test_annotation_only_edf_is_readable(tmp_path: Path) -> None:
    path = _annotation_only_edf(tmp_path / "hypnogram.edf")
    assert parse_header(path).issues == ()
    assert EdfAdapter().read_check(path) is None


@pytest.mark.parametrize(
    "value",
    [b"1e-320  ", b"1E-999  ", b"1e308   ", b"0e999999", b"1_000   ", b"0x10    "],
)
def test_extreme_or_malformed_numbers_are_header_issues(tmp_path: Path, value: bytes) -> None:
    data = bytearray(SRC.read_bytes())
    data[236:244] = b"2       "
    data[244:252] = value
    header = parse_header(_write(tmp_path / "x.edf", bytes(data)))
    assert "header.record_duration" in header.issues
    recording = to_recording(header, recording_id="r", relative_path="x.edf")
    assert recording.sampling_rate_hz is None and recording.duration_s is None


def test_exponent_within_limits_is_accepted(tmp_path: Path) -> None:
    data = bytearray(SRC.read_bytes())
    data[244:252] = b"1E+01   "
    header = parse_header(_write(tmp_path / "e.edf", bytes(data)))
    assert "header.record_duration" not in header.issues and header.record_duration_s == 10.0


@pytest.mark.parametrize("start", [b"00.00.00", b"31.02.21", b"99.99.99", b"32.13.21"])
def test_impossible_start_date_is_a_header_issue_not_a_date(tmp_path: Path, start: bytes) -> None:
    header = parse_header(_patch(SRC, tmp_path / "s.edf", 168, start))
    assert "header.startdate" in header.issues and "date" not in header.identifying_fields


@pytest.mark.parametrize(
    ("patient", "recording", "plus", "expected"),
    [
        (b"X Mueller X X", b"Startdate X X X X", True, ("patient",)),  # sex field holds a name
        (b"X M X X", b"Startdate X X X EEG-64 Dr_Wang_Li", True, ("recording",)),  # extra subfield
        (b"X X X X", b"Recorded 2002-03-02 at site A", True, ("date",)),  # no Startdate keyword
        (b"X", b"Session 2002-03-02", False, ("date",)),  # ISO date in a plain EDF field
        (b"X", b"Session 2002/01/01", False, ()),  # ISO placeholder
    ],
)
def test_identifying_edge_cases(
    tmp_path: Path, patient: bytes, recording: bytes, plus: bool, expected: tuple[str, ...]
) -> None:
    path = _with_fields(tmp_path, "e.edf", patient=patient, recording=recording, plus=plus, start=b"01.01.85")
    assert parse_header(path).identifying_fields == expected


def test_brainvision_companion_is_case_insensitive(tmp_path: Path) -> None:
    (tmp_path / "rec.VHDR").write_text("", encoding="utf-8")
    (tmp_path / "rec.eeg").write_bytes(b"")
    result = scan(tmp_path)
    assert [f.suffix for f in result.recordings] == [".vhdr"]
    assert [f.relative.name for f in result.other] == ["rec.eeg"] and result.unsupported == []


def test_long_and_hostile_description_fields(tmp_path: Path) -> None:
    (tmp_path / "dataset_description.json").write_text(
        json.dumps({"Name": "A\x1b[31m" + "x" * 500, "License": True}), encoding="utf-8"
    )
    result = scan(tmp_path)
    assert result.description == {"Name": "A[31m" + "x" * 195}
    (tmp_path / "dataset_description.json").write_text("[" * 200_000, encoding="utf-8")
    assert scan(tmp_path).description == {}


def test_unlistable_folder_is_collected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    (tmp_path / "good.edf").write_bytes(SRC.read_bytes())
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "bad.edf").write_bytes(b"x")
    real_scandir = os.scandir

    def scandir(path: object = ".") -> object:
        if Path(str(path)).resolve() == locked.resolve():
            raise PermissionError(13, "denied", str(path))
        return real_scandir(path)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "scandir", scandir)
    result = scan(tmp_path)
    assert [f.relative.as_posix() for f in result.unreadable] == ["locked"]
    assert result.unreadable[0].display_id.startswith("rec-") and len(result.recordings) == 1


@pytest.mark.skipif(sys.platform != "win32", reason="names with a trailing dot are a Windows case")
def test_unreachable_file_name_is_collected(tmp_path: Path) -> None:
    (tmp_path / "good.edf").write_bytes(SRC.read_bytes())
    try:
        with Path("\\\\?\\" + str(tmp_path / "bad.edf.")).open("wb") as handle:
            handle.write(b"x")
    except OSError:
        pytest.skip("file system refuses the name")
    result = scan(tmp_path)
    assert [f.suffix for f in result.unreadable] == [".edf"] and len(result.recordings) == 1


@pytest.mark.parametrize(
    ("recording", "expected"),
    [
        (b"Startdate X X X EEG-64 seen_2002-03-02", ("date",)),  # date in an extra subfield, next to "_"
        (b"Startdate X X X EEG-64 Wang Li", ("recording",)),  # name spread over two subfields
    ],
)
def test_edfplus_extra_subfields_as_free_text(
    tmp_path: Path, recording: bytes, expected: tuple[str, ...]
) -> None:
    path = _with_fields(
        tmp_path, "x.edf", patient=b"X X X X", recording=recording, plus=True, start=b"01.01.85"
    )
    assert parse_header(path).identifying_fields == expected


@pytest.mark.skipif(sys.platform != "win32", reason="names with a trailing dot are a Windows case")
def test_display_file_of_unreachable_names_is_the_stored_name(tmp_path: Path) -> None:
    (tmp_path / "dataset_description.json").write_text('{"Name": "D"}', encoding="utf-8")
    try:
        with Path("\\\\?\\" + str(tmp_path / "trail.edf.")).open("wb") as handle:
            handle.write(b"x")
    except OSError:
        pytest.skip("file system refuses the name")
    entry = scan(tmp_path).unreadable[0]
    assert entry.display_file == "trail.edf."
