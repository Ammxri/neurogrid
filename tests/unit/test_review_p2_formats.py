"""Review P2, BrainVision and FIF references: MNE never opens a data, marker or split file that is not a plain
file name next to the file NeuroGrid checks (A-52, A-77).

Covers neurogrid.io.brainvision (the key/value sections read with MNE's grammar: keys without case, ``=`` and
``:``, the ``[Common infos]`` fallback, only the text before ``[Comment]``; MNE's own reading of DataFile and
MarkerFile with its Codepage decoding; read_check calling MNE only for present and safe references) and
neurogrid.io.fif (split references followed as MNE follows them, before MNE reads the file).
"""

from __future__ import annotations

import configparser
import json
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import time
import warnings
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import pytest

from conftest import (  # type: ignore[import-not-found,unused-ignore]
    LOCALE_ENCODINGS,
    dir_link,
    leave_out_of_order,
    locale_encoding,
)
from neurogrid import pipeline
from neurogrid.io import brainvision, fif
from neurogrid.io.base import HeaderUnreadable
from neurogrid.io.brainvision import BrainVisionAdapter, parse_vhdr
from neurogrid.io.discover import pseudonym
from neurogrid.io.fif import FifAdapter
from neurogrid.kernel import safety
from neurogrid.kernel.errors import UnsafePathError

VHDR_MAGIC = "Brain Vision Data Exchange Header File Version 1.0\n"
VMRK = (
    "Brain Vision Data Exchange Marker File, Version 1.0\n\n"
    "[Common Infos]\nCodepage=UTF-8\nDataFile=rec.eeg\n\n[Marker Infos]\nMk1=New Segment,,1,1,0\n"
)
REST = "DataFormat=BINARY\nDataOrientation=MULTIPLEXED\nNumberOfChannels=2\nSamplingInterval=1000\n"
TAIL = "\n[Binary Infos]\nBinaryFormat=INT_16\n\n[Channel Infos]\nCh1=Fp1,,1,µV\nCh2=Fp2,,1,µV\n"
INSIDE_VALUE, OUTSIDE_VALUE = 3, 7  # INT_16 values of the data files, 1 µV each


def _eeg(path: Path, value: int) -> None:
    path.write_bytes(struct.pack("<4000h", *([value] * 4000)))  # 2000 frames of 2 channels: 2 s at 1000 Hz


def _dataset(tmp_path: Path) -> tuple[Path, Path]:
    """``ds`` with rec.eeg/rec.vmrk and a folder OUTSIDE the dataset with other valid data and markers."""
    ds, outside = tmp_path / "ds", tmp_path / "OUTSIDE"
    for folder, value in ((ds, INSIDE_VALUE), (outside, OUTSIDE_VALUE)):
        folder.mkdir(parents=True)
        _eeg(folder / "rec.eeg", value)
        (folder / "rec.vmrk").write_bytes(VMRK.encode("utf-8"))
    return ds, outside


def _header(
    ds: Path, common: str, *, section: str = "Common Infos", before: str = "", after: str = ""
) -> Path:
    vhdr = ds / "rec.vhdr"
    text = VHDR_MAGIC + before + f"\n[{section}]\nCodepage=UTF-8\n" + common + REST + TAIL + after
    vhdr.write_bytes(text.encode("utf-8"))
    return vhdr


@pytest.fixture
def no_mne(monkeypatch: pytest.MonkeyPatch) -> None:
    """MNE must not be asked to read the data (it would follow the references itself)."""

    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("MNE was called")

    monkeypatch.setattr(brainvision, "mne_read_check", fail)
    monkeypatch.setattr(fif, "mne_read_check", fail)
    monkeypatch.setattr(fif, "_raw", fail)


def _mne_header_view(vhdr: Path) -> tuple[str | None, str | None]:
    """DataFile and MarkerFile from MNE's own header reader (it opens neither of them)."""
    import configparser

    from mne.io.brainvision.brainvision import _aux_hdr_info

    _settings, cfg, section, _info, _sfreq = _aux_hdr_info(str(vhdr))

    def get(key: str) -> str | None:
        try:
            return str(cfg.get(section, key))
        except (configparser.NoOptionError, configparser.NoSectionError):
            return None

    return get("DataFile"), get("MarkerFile")


# --- BrainVision: the header is read with MNE's grammar ----------------------------------------------------

# Spellings that MNE (configparser) accepts and the former parser of NeuroGrid did not see; {outside} is the
# absolute path of the folder outside the dataset.
VARIANTS = {
    "lowercase key, absolute path": ("datafile={outside}/rec.eeg\nmarkerfile=rec.vmrk\n", "Common Infos", ""),
    "colon as separator": ("DataFile: ../OUTSIDE/rec.eeg\nMarkerFile: rec.vmrk\n", "Common Infos", ""),
    "NeurOne section spelling": ("DataFile=../OUTSIDE/rec.eeg\nMarkerFile=rec.vmrk\n", "Common infos", ""),
    "upper-case marker key with spaces": (
        "DataFile=rec.eeg\nMARKERFILE = ../OUTSIDE/rec.vmrk\n",
        "Common Infos",
        "",
    ),
    "value continued on an indented line": (
        "DataFile=rec.eeg\n  ../OUTSIDE/rec.eeg\nMarkerFile=rec.vmrk\n",
        "Common Infos",
        "",
    ),
    "inherited from the DEFAULT section": (
        "MarkerFile=rec.vmrk\n",
        "Common Infos",
        "\n[DEFAULT]\nDataFile=../OUTSIDE/rec.eeg\n",
    ),
}


@pytest.mark.parametrize("variant", list(VARIANTS))
def test_brainvision_references_are_found_as_mne_finds_them(
    tmp_path: Path, variant: str, no_mne: None
) -> None:
    ds, outside = _dataset(tmp_path)
    common, section, before = VARIANTS[variant]
    vhdr = _header(ds, common.format(outside=outside.as_posix()), section=section, before=before)
    header = parse_vhdr(vhdr)
    assert header.issues == []  # every required key is found, whatever its spelling
    mne_view = _mne_header_view(vhdr)
    assert (header.value("DataFile"), header.value("MarkerFile")) == mne_view  # NeuroGrid sees what MNE sees
    assert header.mne_references == mne_view
    adapter = BrainVisionAdapter()
    assert adapter.inspect(vhdr).missing_companions == ("companion.unsafe_reference",)
    assert adapter.read_check(vhdr) == "UnsafePathError"  # MNE is not called (fixture no_mne)
    # the duration comes only from a data file next to the header (2000 frames at 1000 Hz)
    expected = 2.0 if mne_view[0] == "rec.eeg" else None
    assert adapter.read(vhdr, recording_id="r", relative_path="rec.vhdr").duration_s == expected


def test_mne_alone_reads_the_outside_data_of_such_a_header(tmp_path: Path) -> None:
    """What the check prevents: MNE follows 'DataFile: ../OUTSIDE/rec.eeg' and returns foreign data."""
    import mne

    ds, _outside = _dataset(tmp_path)
    vhdr = _header(ds, "DataFile: ../OUTSIDE/rec.eeg\nMarkerFile=rec.vmrk\n")
    data = mne.io.read_raw_brainvision(vhdr, preload=True, verbose="error").get_data()
    assert np.allclose(data, OUTSIDE_VALUE * 1e-6)


def test_brainvision_mne_grammar_on_a_harmless_header(tmp_path: Path) -> None:
    """Lower-case keys, ':' and the NeurOne section name are a valid header for MNE and for NeuroGrid."""
    ds, _outside = _dataset(tmp_path)
    vhdr = ds / "rec.vhdr"
    vhdr.write_bytes(
        (
            VHDR_MAGIC
            + "; exported\n\n[Common infos]\ncodepage: UTF-8\ndatafile: rec.eeg\nMARKERFILE=rec.vmrk\n"
            "dataformat=BINARY\nDataOrientation : MULTIPLEXED\nnumberofchannels=2\nsamplinginterval=1000\n"
            "\n[Binary Infos]\nbinaryformat=INT_16\n\n"
            "[Channel Infos]\n# a comment line\nch2=Fp2,,1,µV\nCH1: Fp1,,1,µV\n"
        ).encode("utf-8")
    )
    header = parse_vhdr(vhdr)
    assert header.issues == [] and header.bytes_per_sample == 2 and header.interval_us == 1000
    assert [name for name, *_rest in header.channels] == ["Fp1", "Fp2"]
    assert header.mne_references == ("rec.eeg", "rec.vmrk") == _mne_header_view(vhdr)
    adapter = BrainVisionAdapter()
    assert adapter.inspect(vhdr).missing_companions == ()
    assert adapter.read(vhdr, recording_id="r", relative_path="rec.vhdr").duration_s == 2.0
    assert adapter.read_check(vhdr) is None  # MNE reads it
    assert BrainVisionAdapter.companions(vhdr) == ("rec.eeg", "rec.vmrk")


def test_brainvision_keys_after_the_comment_are_not_header_keys(tmp_path: Path) -> None:
    """MNE reads the key/value sections only up to [Comment]; a later section changes nothing (A-77)."""
    ds, _outside = _dataset(tmp_path)
    vhdr = _header(
        ds,
        "DataFile=rec.eeg\nMarkerFile=rec.vmrk\n",
        after="\n[Comment]\nresting state\n\n"
        "[Common Infos]\nDataFile=../OUTSIDE/rec.eeg\nNumberOfChannels=9\n",
    )
    header = parse_vhdr(vhdr)
    assert header.value("DataFile") == "rec.eeg" and header.n_channels == 2 and header.issues == []
    assert header.mne_references == ("rec.eeg", "rec.vmrk") == _mne_header_view(vhdr)
    adapter = BrainVisionAdapter()
    assert adapter.inspect(vhdr).missing_companions == ()
    assert adapter.read_check(vhdr) is None


@pytest.mark.parametrize(
    ("common", "unlink", "missing", "issues"),
    [
        ("DataFile=rec.eeg\n", None, ("companion.marker_file",), ()),  # no MarkerFile key
        ("DataFile=rec.eeg\nMarkerFile=rec.vmrk\n", "rec.vmrk", ("companion.marker_file",), ()),
        ("DataFile=rec.eeg\nMarkerFile=rec.vmrk\n", "rec.eeg", ("companion.data_file",), ()),
        ("MarkerFile=rec.vmrk\n", None, (), ("header.missing_key",)),  # no DataFile key
    ],
)
def test_brainvision_read_check_needs_both_references(
    tmp_path: Path,
    common: str,
    unlink: str | None,
    missing: tuple[str, ...],
    issues: tuple[str, ...],
    no_mne: None,
) -> None:
    """Without a present DataFile and MarkerFile, MNE is not asked to read the data at all (A-52, A-77)."""
    ds, _outside = _dataset(tmp_path)
    vhdr = _header(ds, common)
    if unlink is not None:
        (ds / unlink).unlink()
    inspection = BrainVisionAdapter().inspect(vhdr)
    assert inspection.missing_companions == missing and inspection.issues == issues
    assert BrainVisionAdapter().read_check(vhdr) == "FileNotFoundError"


def test_brainvision_read_check_of_an_unparseable_header_does_not_call_mne(
    tmp_path: Path, no_mne: None
) -> None:
    ds, _outside = _dataset(tmp_path)
    vhdr = ds / "rec.vhdr"
    vhdr.write_bytes(
        b"Brain Vision Core Data Exchange Header File Version 1.0\n[Common Infos]\nDataFile=../x.eeg\n"
    )
    with pytest.raises(HeaderUnreadable):
        parse_vhdr(vhdr)
    assert BrainVisionAdapter().read_check(vhdr) == "HeaderUnreadable"


def _gbk_header(ds: Path, data_file: bytes, marker_file: bytes) -> Path:
    """A header in GBK (a Chinese channel name) that claims Codepage=UTF-8: NeuroGrid decodes it as GBK
    (A-77), MNE falls back to Latin-1, so a lead byte before a backslash or letter reads differently."""
    vhdr = ds / "rec.vhdr"
    vhdr.write_bytes(
        (VHDR_MAGIC + "\n[Common Infos]\nCodepage=UTF-8\nDataFile=").encode("ascii")
        + data_file
        + b"\nMarkerFile="
        + marker_file
        + ("\n" + REST + "\n[Binary Infos]\nBinaryFormat=INT_16\n\n[Channel Infos]\nCh1=").encode("ascii")
        + "左额".encode("gbk")
        + b",,1,uV\nCh2=Fp2,,1,uV\n"
    )
    return vhdr


def test_brainvision_reference_as_mne_decodes_it_is_checked(tmp_path: Path, no_mne: None) -> None:
    """GBK reads 0x81 0x5C as one character, Latin-1 as '\\x81' and a backslash: MNE on Windows would open
    '<ds>/\\x81/x.eeg', here a directory link to the outside data (A-52). A backslash in a reference separates
    folders for NeuroGrid on every system (BrainVision files are written on Windows), so the reference is
    refused on Linux as well, where MNE would take it for one file name (the two tests below)."""
    ds, outside = _dataset(tmp_path)
    shutil.copy(ds / "rec.eeg", ds / "乗x.eeg")  # the file NeuroGrid's reading names, next to the header
    (outside / "rec.eeg").rename(outside / "x.eeg")
    dir_link(ds / "\x81", outside)
    vhdr = _gbk_header(ds, b"\x81\x5cx.eeg", b"rec.vmrk")
    header = parse_vhdr(vhdr)
    assert header.value("DataFile") == "乗x.eeg" and header.channels[0][0] == "左额"
    assert header.mne_references == ("\x81\\x.eeg", "rec.vmrk") == _mne_header_view(vhdr)
    adapter = BrainVisionAdapter()
    assert adapter.inspect(vhdr).missing_companions == ("companion.unsafe_reference",)
    assert adapter.read_check(vhdr) == "UnsafePathError"


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows only: the backslash of '\\x81\\\\x.eeg' is a path separator only there; on POSIX MNE "
    "opens one file of that name inside the dataset "
    "(test_mne_on_posix_opens_the_backslash_name_inside_the_dataset)",
)
def test_mne_alone_follows_the_differently_decoded_reference(tmp_path: Path) -> None:
    import mne

    ds, outside = _dataset(tmp_path)
    (outside / "rec.eeg").rename(outside / "x.eeg")
    dir_link(ds / "\x81", outside)
    vhdr = _gbk_header(ds, b"\x81\x5cx.eeg", b"rec.vmrk")
    data = mne.io.read_raw_brainvision(vhdr, preload=True, verbose="error").get_data()
    assert np.allclose(data, OUTSIDE_VALUE * 1e-6)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX only: Windows cannot store a file name with a backslash (there it is a path separator)",
)
def test_mne_on_posix_opens_the_backslash_name_inside_the_dataset(tmp_path: Path) -> None:
    """CI ubuntu-24.04: MNE opened '<ds>/\\x81\\\\x.eeg' as one name (FileNotFoundError), not the folder link.
    NeuroGrid refuses the reference all the same, so the outcome is that of Windows (A-52, TECH-05)."""
    import mne

    ds, outside = _dataset(tmp_path)
    (outside / "rec.eeg").rename(outside / "x.eeg")
    dir_link(ds / "\x81", outside)
    shutil.copy(ds / "rec.eeg", ds / "乗x.eeg")  # the file NeuroGrid's reading names, next to the header
    shutil.copy(ds / "rec.eeg", ds / "\x81\\x.eeg")  # one file name with a backslash, inside the dataset
    vhdr = _gbk_header(ds, b"\x81\x5cx.eeg", b"rec.vmrk")
    data = mne.io.read_raw_brainvision(vhdr, preload=True, verbose="error").get_data()
    # the file inside, not the outside data behind the link
    assert np.allclose(data, INSIDE_VALUE * 1e-6), f"MNE read {data.flat[0]:g} V, sep={os.sep!r}"
    adapter = BrainVisionAdapter()
    assert adapter.inspect(vhdr).missing_companions == ("companion.unsafe_reference",)
    assert adapter.read_check(vhdr) == "UnsafePathError"


@pytest.mark.parametrize(
    ("reference", "parts"),
    [
        ("\x81\\x.eeg", ("\x81", "x.eeg")),
        ("sub\\rec.eeg", ("sub", "rec.eeg")),
        ("..\\OUTSIDE\\rec.eeg", None),
    ],
)
def test_backslash_in_a_reference_is_a_separator_on_every_system(
    tmp_path: Path, reference: str, parts: tuple[str, ...] | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MNE joins DataFile with os.path.join: on POSIX the backslash stays in one file name inside the dataset,
    on Windows it separates folders (the posixpath and ntpath asserts; MNE's own POSIX reading is
    test_mne_on_posix_opens_the_backslash_name_inside_the_dataset). NeuroGrid's decision does not ask the
    system: check_relative splits at every backslash in the string alone, and _reference refuses a reference
    with folders before it calls anything that looks at the system (resolve_within and is_link fail here if
    called), so a dataset gets the same outcome on Linux and Windows (A-52, TECH-05)."""
    import ntpath
    import posixpath

    assert posixpath.dirname(posixpath.join("/ds", reference)) == "/ds"  # POSIX: one name in the folder
    assert ntpath.dirname(ntpath.join("C:\\ds", reference)) != "C:\\ds"  # Windows: folders
    if parts is None:
        with pytest.raises(UnsafePathError, match="path.parent"):
            safety.check_relative(reference)
    else:
        assert safety.check_relative(reference).parts == parts
    ds, _outside = _dataset(tmp_path)

    def system_dependent(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("_reference looked at the file system for a reference with folders")

    monkeypatch.setattr(brainvision, "resolve_within", system_dependent)
    monkeypatch.setattr(brainvision, "is_link", system_dependent)
    assert brainvision._reference(ds, reference) == (None, "unsafe")


def test_brainvision_marker_fallback_of_mne_must_not_be_a_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MNE's MarkerFile '\\x81Arec.vmrk' does not exist, so MNE opens <stem>.vmrk instead; that file must not
    be a link. NeuroGrid's reading names '\\u4e04rec.vmrk', which exists."""
    ds, _outside = _dataset(tmp_path)
    shutil.copy(ds / "rec.vmrk", ds / "丄rec.vmrk")
    vhdr = _gbk_header(ds, b"rec.eeg", b"\x81Arec.vmrk")
    header = parse_vhdr(vhdr)
    assert header.value("MarkerFile") == "丄rec.vmrk"
    assert header.mne_references == ("rec.eeg", "\x81Arec.vmrk")
    adapter = BrainVisionAdapter()
    assert adapter.inspect(vhdr).missing_companions == ()
    assert adapter.read_check(vhdr) is None  # a regular rec.vmrk: MNE reads the recording
    monkeypatch.setattr(brainvision, "is_link", lambda path: Path(path).name == "rec.vmrk")
    assert adapter.inspect(vhdr).missing_companions == ("companion.unsafe_reference",)
    assert adapter.read_check(vhdr) == "UnsafePathError"


def test_brainvision_header_mne_cannot_parse_keeps_the_last_value(tmp_path: Path) -> None:
    """A duplicate key makes MNE fail before it opens anything; NeuroGrid keeps the last value and MNE's
    error is the read result."""
    ds, _outside = _dataset(tmp_path)
    vhdr = _header(ds, "DataFile=../OUTSIDE/rec.eeg\ndatafile=rec.eeg\nMarkerFile=rec.vmrk\n")
    header = parse_vhdr(vhdr)
    assert header.value("DataFile") == "rec.eeg" and header.mne_references is None
    assert BrainVisionAdapter().inspect(vhdr).missing_companions == ()
    assert BrainVisionAdapter().read_check(vhdr) == "DuplicateOptionError"


def test_brainvision_stray_lines_do_not_hide_the_sections(tmp_path: Path) -> None:
    """Lines without a key, also before the first section, are skipped as before; the sections stay read."""
    ds, _outside = _dataset(tmp_path)
    vhdr = _header(
        ds, "DataFile=rec.eeg\nMarkerFile=rec.vmrk\nno key on this line\n", before="stray text before\n"
    )
    header = parse_vhdr(vhdr)
    assert header.issues == [] and header.value("DataFile") == "rec.eeg" and len(header.channels) == 2
    assert BrainVisionAdapter().inspect(vhdr).missing_companions == ()


# Verifier, review P2: headers whose bytes MNE decodes by their Codepage entry into other names than
# NeuroGrid's decoding rule (A-77) gives; the mirror of MNE's reading must give exactly what MNE reads.
MIRROR_CASES = {
    "UTF-7": b"Codepage=UTF-7\nDataFile=+AC4ALgAv-x.eeg\nMarkerFile=rec.vmrk\n",
    "Codepage in a comment line": b"; Codepage=UTF-7\nDataFile=+AC4ALgAv-x.eeg\nMarkerFile=rec.vmrk\n",
    "unicode_escape": b"Codepage=unicode_escape\nDataFile=rec.eeg\nMarkerFile=\\u002e\\u002e/x.vmrk\n",
    "ANSI": b"Codepage=ANSI\nDataFile=r\x85c.eeg\nMarkerFile=rec.vmrk\n",
    "invalid UTF-8": b"Codepage=UTF-8\nDataFile=r\xe9c.eeg\nMarkerFile=rec.vmrk\n",
    "CRLF without Codepage": b"DataFile=rec.eeg\r\nMarkerFile = ../x.vmrk\r\n",
}


@pytest.mark.parametrize("case", list(MIRROR_CASES))
def test_brainvision_mne_reading_of_the_references_is_mnes_own(tmp_path: Path, case: str) -> None:
    vhdr = tmp_path / "rec.vhdr"
    vhdr.write_bytes(
        VHDR_MAGIC.encode("ascii") + b"[Common Infos]\n" + MIRROR_CASES[case] + REST.encode("ascii")
    )
    assert parse_vhdr(vhdr).mne_references == _mne_header_view(vhdr)


UTF7_NAME = "+AC4ALgAv-OUTSIDE+AC8-rec.eeg"  # '../OUTSIDE/rec.eeg' when decoded as UTF-7


def test_brainvision_ascii_header_that_mne_decodes_by_its_codepage(tmp_path: Path, no_mne: None) -> None:
    """Verifier, review P2: a pure ASCII header with Codepage=UTF-7 names a plain file that exists next to the
    header for NeuroGrid, but '../OUTSIDE/rec.eeg' for MNE. MNE's reading is checked as well (A-52, A-77)."""
    import mne

    ds, _outside = _dataset(tmp_path)
    shutil.copy(ds / "rec.eeg", ds / UTF7_NAME)
    vhdr = ds / "rec.vhdr"
    vhdr.write_bytes(
        (
            VHDR_MAGIC
            + f"\n[Common Infos]\nCodepage=UTF-7\nDataFile={UTF7_NAME}\nMarkerFile=rec.vmrk\n"
            + REST
        ).encode("ascii")
        + TAIL.replace("µV", "uV").encode("ascii")
    )
    header = parse_vhdr(vhdr)
    assert header.issues == [] and header.value("DataFile") == UTF7_NAME
    assert header.mne_references == ("../OUTSIDE/rec.eeg", "rec.vmrk") == _mne_header_view(vhdr)
    adapter = BrainVisionAdapter()
    assert adapter.inspect(vhdr).missing_companions == ("companion.unsafe_reference",)
    assert adapter.read_check(vhdr) == "UnsafePathError"  # MNE is not called (fixture no_mne)
    # what the check prevents: MNE on its own returns the data of the outside file
    data = mne.io.read_raw_brainvision(vhdr, preload=True, verbose="error").get_data()
    assert np.allclose(data, OUTSIDE_VALUE * 1e-6)


def test_brainvision_number_fields_beyond_int_do_not_stop_the_scan(tmp_path: Path) -> None:
    """Verifier, review P2: 'NumberOfChannels=²' (isdigit, but no int) and a channel key with 5000 digits
    (over int()'s digit limit) made parse_vhdr raise ValueError. Discovery asks every header for its
    companions, so scan and check ended with an internal error (exit 2). They are header issues now (A-75)."""
    from neurogrid.io.discover import scan

    ds, _outside = _dataset(tmp_path)
    vhdr = _header(ds, "DataFile=rec.eeg\nMarkerFile=rec.vmrk\n", after="Ch" + "1" * 5000 + "=X,,1,µV\n")
    vhdr.write_bytes(vhdr.read_bytes().replace(b"NumberOfChannels=2", "NumberOfChannels=²".encode()))
    header = parse_vhdr(vhdr)
    assert header.issues == ["header.number_field"] and len(header.channels) == 2
    assert BrainVisionAdapter.companions(vhdr) == ("rec.eeg", "rec.vmrk")
    assert [found.relative.as_posix() for found in scan(ds).recordings] == ["rec.vhdr"]
    assert BrainVisionAdapter().inspect(vhdr).issues == ("header.number_field",)


# --- BrainVision: MNE's reading does not depend on the locale (A-77, TECH-05) -----------------------------
# CI ubuntu-24.04: a recording whose marker file is not UTF-8 was unreadable on Linux and readable on Windows.
# MNE 1.13 reads the marker file once more in text mode without an encoding, to find the recording date, so
# Python decodes it with the locale's encoding (UTF-8 on Linux, the ANSI code page on Windows).

SEGMENT_WITH_DATE = "Mk1=New Segment,,1,1,0,20210824101500000000\n"
MARKER_TEXTS = {  # Codepage of the marker file, the comment text in the bytes the recorder wrote
    "Latin-1 text, Codepage=UTF-8": ("UTF-8", "Café".encode("latin-1")),
    "Western ANSI (cp1252)": ("ANSI", "Größe ändern".encode("cp1252")),
    "Chinese ANSI (GBK)": ("ANSI", "丄睁眼".encode("gbk")),  # 0x81 0x41 is '丄': 0x81 is no cp1252 byte
    "UTF-8": ("UTF-8", "睁眼 Größe".encode()),
}


def _mne_marker_text(codepage: str, comment: bytes) -> str:
    """The comment as MNE decodes the marker file itself: by its Codepage (ANSI as cp1252), else Latin-1."""
    try:
        return comment.decode("cp1252" if codepage == "ANSI" else codepage)
    except UnicodeDecodeError:
        return comment.decode("latin-1")


@pytest.mark.parametrize("marker", list(MARKER_TEXTS))
def test_brainvision_reading_is_the_same_whatever_the_locale(tmp_path: Path, marker: str) -> None:
    """Simulated: the locale encodings of Linux, a Western and a Chinese Windows. The read check, the
    recording date and the marker texts are the same under each; every marker file here is readable (A-77,
    TECH-05)."""
    import datetime

    vhdr = _marker_case(tmp_path, marker)
    outcomes = {}
    for system, codec in LOCALE_ENCODINGS.items():
        with locale_encoding(codec):
            check = BrainVisionAdapter().read_check(vhdr)
            raw = brainvision.mne_read_raw_brainvision(vhdr, preload=False, verbose="error")
        outcomes[system] = (check, raw.info["meas_date"], tuple(raw.annotations.description))
    date = datetime.datetime(2021, 8, 24, 10, 15, tzinfo=datetime.UTC)
    description = f"Comment/{_mne_marker_text(*MARKER_TEXTS[marker])}"
    assert set(outcomes.values()) == {(None, date, (description,))}, outcomes


def _marker_case(tmp_path: Path, marker: str) -> Path:
    """The dataset with a marker file of MARKER_TEXTS: its Codepage, a dated New Segment and the comment."""
    ds, _outside = _dataset(tmp_path)
    codepage, comment = MARKER_TEXTS[marker]
    text = VMRK.replace("Codepage=UTF-8", f"Codepage={codepage}").replace("Mk1=New Segment,,1,1,0\n", "")
    marker_line = b"Mk2=Comment," + comment + b",100,1,0\n"
    (ds / "rec.vmrk").write_bytes((text + SEGMENT_WITH_DATE).encode("ascii") + marker_line)
    return _header(ds, "DataFile=rec.eeg\nMarkerFile=rec.vmrk\n")


def test_mne_alone_reads_the_marker_date_with_the_locale_encoding(tmp_path: Path) -> None:
    """What mne_read_raw_brainvision prevents: plain MNE fails on a Latin-1 marker file under the locale of
    Linux (UTF-8) and reads it under that of a Western Windows. If MNE stops doing this, the workaround in
    brainvision.mne_reading_without_locale can go."""
    import mne

    vhdr = _marker_case(tmp_path, "Latin-1 text, Codepage=UTF-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", EncodingWarning)  # MNE's own open without an encoding
        with locale_encoding("cp1252"):
            mne.io.read_raw_brainvision(vhdr, verbose="error")
        with locale_encoding("utf-8"), pytest.raises(UnicodeDecodeError):
            mne.io.read_raw_brainvision(vhdr, verbose="error")


def _mne_reader_globals() -> dict[str, Any]:
    from mne.io.brainvision import brainvision as reader_module

    return vars(reader_module)


def test_mne_reading_without_locale_holds_for_threads_that_leave_out_of_order(tmp_path: Path) -> None:
    """The patch of MNE's module is one for the whole process. Thread A enters, then B; A leaves first.
    Before, A's exit took the patch away while B still read (B saw the built-in open and failed on the
    Latin-1 marker file under the locale of Linux), and B's exit put A's patch back for good."""
    import mne

    vhdr = _marker_case(tmp_path, "Latin-1 text, Codepage=UTF-8")

    def read_in_b() -> tuple[object, ...]:
        assert _mne_reader_globals().get("open") is brainvision._open_for_mne, "B reads without the patch"
        with locale_encoding(LOCALE_ENCODINGS["Linux"]):
            raw = mne.io.read_raw_brainvision(vhdr, verbose="error")
        return tuple(raw.annotations.description)

    assert leave_out_of_order(brainvision.mne_reading_without_locale, read_in_b) == ("Comment/Café",)
    assert "open" not in _mne_reader_globals(), "the patch outlived the last block"


def test_mne_reading_without_locale_in_many_threads_at_once(tmp_path: Path) -> None:
    """Eight threads read the Latin-1 marker recording at the same time under the locale of Linux, each
    through mne_read_raw_brainvision: every read succeeds, and the module is unpatched afterwards."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    vhdr = _marker_case(tmp_path, "Latin-1 text, Codepage=UTF-8")
    start = threading.Barrier(8)

    def reads(_index: int) -> set[tuple[str, ...]]:
        start.wait(30)
        return {
            tuple(brainvision.mne_read_raw_brainvision(vhdr, verbose="error").annotations.description)
            for _ in range(5)
        }

    with locale_encoding(LOCALE_ENCODINGS["Linux"]), ThreadPoolExecutor(8) as pool:
        results = list(pool.map(reads, range(8)))
    assert set().union(*results) == {("Comment/Café",)}
    assert "open" not in _mne_reader_globals() and brainvision._MNE_READER_PATCH.holders == 0


def test_module_patch_refuses_a_module_that_changed() -> None:
    """A wrapped function that is gone, or a built-in the module now defines itself: the patch would not do
    what NeuroGrid relies on, so holding it fails instead (a library update is reviewed)."""
    from neurogrid.io.base import ModulePatch

    with pytest.raises(RuntimeError, match="has no function _no_such_function"):
        with ModulePatch("mne.io.brainvision.brainvision", wrapped={"_no_such_function": lambda f: f}).held():
            pass
    with pytest.raises(RuntimeError, match="defines re"):
        with ModulePatch("mne.io.brainvision.brainvision", added={"re": None}).held():
            pass
    assert "re" in _mne_reader_globals() and "_no_such_function" not in _mne_reader_globals()


def test_neurogrid_calls_mne_for_brainvision_only_through_the_locale_free_reader() -> None:
    """Every use of mne.io.read_raw_brainvision in NeuroGrid is the one inside mne_read_raw_brainvision."""
    import ast

    class Uses(ast.NodeVisitor):
        def __init__(self, name: str) -> None:
            self.name, self.functions, self.found = name, [""], list[tuple[str, str]]()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.functions.append(node.name)
            self.generic_visit(node)
            self.functions.pop()

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if node.attr == "read_raw_brainvision":
                self.found.append((self.name, self.functions[-1]))
            self.generic_visit(node)

    root = Path(brainvision.__file__).parents[1]
    found = []
    for path in sorted(root.rglob("*.py")):
        visitor = Uses(path.relative_to(root).as_posix())
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        found += visitor.found
    assert found == [("io/brainvision.py", "mne_read_raw_brainvision")]


def test_read_check_of_a_vanished_file_reports_the_error_class(tmp_path: Path) -> None:
    """Verifier, review P2: read_check reports an outcome and never raises, also when the header is gone
    between the scan and the read check (parse_vhdr runs before MNE now)."""
    assert BrainVisionAdapter().read_check(tmp_path / "gone.vhdr") == "FileNotFoundError"
    assert FifAdapter().read_check(tmp_path / "gone_raw.fif") == "FileNotFoundError"


# --- BrainVision: reading takes bounded time (A-53) ---------------------------------------------------------
# Verifier, review P2 (second pass): parse_vhdr runs for every header in scan, check and convert, up to five
# times per header. configparser builds the message of every line it rejects with += (80,000 such lines took
# 30 s per parse, a 2 MB header hours), its key pattern in older CPython releases (3.13.7 here) backtracks
# over whitespace runs in a key (hours for one 2 MB run), Codepage=punycode decodes in quadratic time, and the
# former impedance pattern backtracked quadratically on a long line of spaces (hours for one 2 MB line).

TIME_LIMIT_S = 20.0  # generous for slow CI machines; the former code needed hours for each of these headers


def _bounded_header(ds: Path, extra: str, *, codepage: str = "UTF-8", after: str = "") -> Path:
    """An ASCII header (``uV``, so that any codepage reads the same characters) with ``extra`` after the
    channel infos and ``after`` after a [Comment] line."""
    vhdr = ds / "rec.vhdr"
    vhdr.write_bytes(
        (
            VHDR_MAGIC
            + f"\n[Common Infos]\nCodepage={codepage}\nDataFile=rec.eeg\nMarkerFile=rec.vmrk\n"
            + REST
            + TAIL.replace("µV", "uV")
            + extra
            + (f"\n[Comment]\n{after}" if after else "")
        ).encode("ascii")
    )
    assert vhdr.stat().st_size <= brainvision.MAX_HEADER_BYTES
    return vhdr


def _configparser_runs(*_args: Any, **_kwargs: Any) -> None:
    raise AssertionError("configparser was run")


@pytest.fixture
def no_configparser(monkeypatch: pytest.MonkeyPatch) -> None:
    """configparser must not be run on the header at all."""
    monkeypatch.setattr(configparser.ConfigParser, "read_string", _configparser_runs)


@pytest.mark.parametrize(
    "extra",
    [
        "x\n" * 900_000,  # lines without a key: 1.8 MB
        "=x\n:y\n" * 300_000,  # a separator without a key
        "[Extra]\n" + " x\n" * 600_000,  # indented, but no value to continue after a section line
        "stray\n" * (brainvision.MAX_LOOSE_LINES + 1),  # just over the limit
        "[Extra]\na" + " " * 1_900_000 + "b=1\n",  # one key with a whitespace run of 1.9 MB
        "[Extra]\na" + " " * 1_900_000 + "b\n",  # the same without a separator
        "[Extra]\nA" + " " * (brainvision.MAX_KEY_SPACES + 1) + "B=1\n",  # just over the limit
    ],
    ids=["no key", "empty key", "indented", "limit + 1", "long run in a key", "long run", "run limit + 1"],
)
def test_brainvision_header_configparser_cannot_read_in_bounded_time_is_unreadable(
    tmp_path: Path, extra: str, no_mne: None, no_configparser: None
) -> None:
    """configparser is never run on such a header, neither by NeuroGrid nor by MNE (A-53)."""
    ds, _outside = _dataset(tmp_path)
    vhdr = _bounded_header(ds, extra)
    start = time.perf_counter()
    with pytest.raises(HeaderUnreadable) as info:
        parse_vhdr(vhdr)
    assert info.value.reason == "header.unreadable"
    adapter = BrainVisionAdapter()
    with pytest.raises(HeaderUnreadable):
        adapter.inspect(vhdr)
    assert adapter.read_check(vhdr) == "HeaderUnreadable"  # fixture no_mne: MNE is not called either
    assert BrainVisionAdapter.companions(vhdr) == ()
    assert time.perf_counter() - start < TIME_LIMIT_S


def test_brainvision_stray_lines_up_to_the_limit_are_still_skipped(tmp_path: Path) -> None:
    """Up to MAX_LOOSE_LINES lines without a key are skipped as before; MNE refuses them itself."""
    ds, _outside = _dataset(tmp_path)
    vhdr = _bounded_header(ds, "stray\n" * brainvision.MAX_LOOSE_LINES)
    header = parse_vhdr(vhdr)
    assert header.issues == [] and len(header.channels) == 2 and header.mne_references is None
    assert BrainVisionAdapter().inspect(vhdr).missing_companions == ()
    assert BrainVisionAdapter().read_check(vhdr) == "ParsingError"


def test_brainvision_key_with_whitespace_up_to_the_limit_is_read(tmp_path: Path) -> None:
    ds, _outside = _dataset(tmp_path)
    key = "Aligned" + " " * brainvision.MAX_KEY_SPACES + "Key"
    vhdr = _bounded_header(ds, f"[User Infos]\n{key} = 1\n")
    header = parse_vhdr(vhdr)
    assert header.issues == [] and header.mne_references == ("rec.eeg", "rec.vmrk")
    assert BrainVisionAdapter().inspect(vhdr).missing_companions == ()
    assert BrainVisionAdapter().read_check(vhdr) is None  # MNE reads it


def test_brainvision_lines_without_a_key_in_mnes_reading_count_as_well(
    tmp_path: Path, no_mne: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With Codepage=UTF-7, '+AAo-' is a line break for MNE only: NeuroGrid's reading has one key, MNE's
    reading has a line without a key per '+AAo-x'. The limit applies to MNE's reading as well."""
    ds, _outside = _dataset(tmp_path)
    vhdr = _bounded_header(
        ds, "Note=a" + "+AAo-x" * (brainvision.MAX_LOOSE_LINES + 1) + "\n", codepage="UTF-7"
    )
    body = brainvision._decode(vhdr.read_bytes()).partition("\n")[2]
    assert brainvision._key_lines(body) == (0, 0)  # NeuroGrid's reading
    with pytest.raises(HeaderUnreadable) as info:
        parse_vhdr(vhdr)
    assert info.value.reason == "header.unreadable"
    assert BrainVisionAdapter().read_check(vhdr) == "HeaderUnreadable"  # fixture no_mne: MNE is not called
    monkeypatch.setattr(configparser.ConfigParser, "read_string", _configparser_runs)
    with pytest.raises(HeaderUnreadable):
        brainvision._mne_references(vhdr.read_bytes())  # before configparser runs on MNE's reading


@pytest.mark.parametrize("codepage", ["punycode", "PUNYCODE", "Punycode "])
def test_brainvision_codepage_punycode_makes_the_header_unreadable(
    tmp_path: Path, codepage: str, no_mne: None
) -> None:
    """MNE decodes the header by its Codepage; decoding punycode takes time that grows with the square of the
    length (450 kB: 5 s, 2 MB: minutes), so such a header is unreadable and is never decoded with it, neither
    by NeuroGrid nor by MNE (A-53)."""
    ds, _outside = _dataset(tmp_path)
    vhdr = _bounded_header(ds, "", codepage=codepage)
    with pytest.raises(HeaderUnreadable) as info:
        parse_vhdr(vhdr)
    assert info.value.reason == "header.unreadable"
    assert BrainVisionAdapter().read_check(vhdr) == "HeaderUnreadable"
    assert BrainVisionAdapter.companions(vhdr) == ()


def test_brainvision_unknown_codepage_is_left_to_mne(tmp_path: Path) -> None:
    """A codepage Python does not know: MNE fails on it before it opens a reference, as before."""
    ds, _outside = _dataset(tmp_path)
    vhdr = _bounded_header(ds, "", codepage="no-such-codepage")
    header = parse_vhdr(vhdr)
    assert header.issues == [] and header.mne_references is None
    assert BrainVisionAdapter().read_check(vhdr) == "LookupError"


# The former impedance pattern; its matches are the expected results of the new parsing of a line.
FORMER_IMPEDANCE_LINE = re.compile(r"^\s*(?P<name>[ A-Za-z0-9_+-]+?)\s*:\s*(?P<value>\S+)")
IMPEDANCE_CHANNELS = ("Fp1", "Fp2", "F p1", "Fp1 \t x")
IMPEDANCE_LINES = [
    "Fp1: 5",
    "Fp1 :5",
    "Fp1\t: 5",
    "F p1: 6",
    "Fp1:",
    "Fp1: Out of Range!",
    "Fp1:5:6",
    ":5",
    "Fp1 : 7",
    "F p1: 7",
    "Fp1 \t x: 5",
    "Fp2:\t-3.5",
    "REF: 1",
    "Gnd : 2",
    "Fp1: 5 kOhm",
    "Fp1= 5",
    "fp1: 9",
    "Fp1: ٣",
    "Cz: 4",
    "Fp1: 5",
]


@pytest.mark.parametrize("line", IMPEDANCE_LINES)
def test_brainvision_impedance_lines_are_read_as_before(line: str) -> None:
    known = {name.upper() for name in IMPEDANCE_CHANNELS} | {"REF", "GND"}
    match = FORMER_IMPEDANCE_LINE.match(line.strip())
    expected: dict[str, float | None] = {}
    if match and match.group("name").strip().upper() in known:
        value = match.group("value")
        number = re.fullmatch(r"[-+]?\d+(\.\d+)?", value)
        expected = {match.group("name").strip(): float(value) if number else None}
    found, used = brainvision._impedance_block(["Impedance [kOhm] at 10:00:00 :", line], IMPEDANCE_CHANNELS)
    assert found == expected and used == ({0, 1} if expected else {0})


def test_brainvision_long_impedance_line_of_spaces_is_read_in_linear_time(tmp_path: Path) -> None:
    ds, _outside = _dataset(tmp_path)
    block = "Impedance [kOhm] at 10:00:00 :\nFp1" + " " * 1_900_000 + "x\nFp2: 4\n"
    vhdr = _bounded_header(ds, "", after=block)
    start = time.perf_counter()
    header = parse_vhdr(vhdr)
    assert time.perf_counter() - start < TIME_LIMIT_S
    assert header.impedances == {} and header.impedance_lines == {0} and header.issues == []


LINE_POOL = [
    "[S]",
    "[DEFAULT]",
    "[Common Infos]",
    "key=1",
    "key: 2",
    "k = v = w",
    "=x",
    ": y",
    " = z",
    "junk",
    "  junk",
    "\tjunk",
    "# c",
    "; c",
    "  ; c",
    "",
    "   ",
    "[]",
    "[x",
    "a]b",
    "[s] trailing",
    "x\r",
    "﻿junk",
    "  cont: x",
    "  continued",
]


def test_loose_line_count_is_an_upper_bound_of_the_lines_configparser_rejects() -> None:
    """The limit must count every line configparser collects into its error message, in NeuroGrid's lenient
    reading and in MNE's strict one (otherwise the quadratic message comes back)."""
    rng = random.Random(77)
    for _ in range(2000):
        text = "\n".join(rng.choice(LINE_POOL) for _line in range(rng.randint(1, 25))) + "\n"
        bound = brainvision._key_lines(text)[0]
        for strict, prefix in ((False, brainvision._PREAMBLE), (True, "")):
            parser = configparser.ConfigParser(interpolation=None, strict=strict)
            try:
                parser.read_string(prefix + text)
            except configparser.MissingSectionHeaderError:
                pass  # raised at once (a subclass of ParsingError): no message is built up
            except configparser.ParsingError as exc:
                assert len(exc.errors) <= bound, text
            except configparser.Error:
                pass  # raised at once (duplicate section or key): no message is built up


# --- FIF: split references ---------------------------------------------------------------------------------

FIFF_REF_FILE_NAME, FIFFT_STRING = 118, 10  # tag kind and data type of a split reference
N_TIMES = 200_000  # 2 channels at 100 Hz: two parts with split_size 2 MB


def _write_split(folder: Path, name: str, **options: Any) -> list[Path]:
    import mne

    folder.mkdir(parents=True, exist_ok=True)
    data = np.zeros((2, N_TIMES))
    data[:, 150_000:] = 1e-3  # the second part holds samples of 1 mV
    raw = mne.io.RawArray(data, mne.create_info(["Fp1", "Fp2"], 100.0, "eeg"), verbose="error")
    raw.save(folder / name, split_size="2MB", fmt="single", overwrite=True, verbose="error", **options)
    parts = sorted(folder.glob("*.fif"))
    assert len(parts) == 2
    return parts


@pytest.fixture(scope="module")
def split_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("split")
    _write_split(folder, "rec_raw.fif")
    return folder


def _rewrite_reference(path: Path, old: str, new: str) -> None:
    """Replace the file name of a split reference; MNE writes no tag directory, so the length may change."""
    blob = path.read_bytes()
    tag = struct.pack(">iiii", FIFF_REF_FILE_NAME, FIFFT_STRING, len(old.encode()), 0) + old.encode()
    assert blob.count(tag) == 1
    new_tag = struct.pack(">iiii", FIFF_REF_FILE_NAME, FIFFT_STRING, len(new.encode()), 0) + new.encode()
    path.write_bytes(blob.replace(tag, new_tag))


def _split_dataset(tmp_path: Path, source: Path) -> tuple[Path, Path, Path]:
    """(rec_raw.fif in ds, its second part, the folder OUTSIDE the dataset)."""
    ds, outside = tmp_path / "ds", tmp_path / "OUTSIDE"
    ds.mkdir(parents=True)
    outside.mkdir()
    for part in source.glob("*.fif"):
        shutil.copy(part, ds / part.name)
    return ds / "rec_raw.fif", ds / "rec_raw-1.fif", outside


def _assert_not_followed(path: Path) -> None:
    adapter = FifAdapter()
    recording = adapter.read(path, recording_id="r", relative_path=path.name)
    assert [(ch.name, ch.type) for ch in recording.channels] == [("Fp1", "EEG"), ("Fp2", "EEG")]
    assert recording.sampling_rate_hz == 100.0
    assert recording.duration_s is None and "duration_s" not in recording.metadata_sources
    inspection = adapter.inspect(path)
    assert inspection.missing_companions == ("companion.unsafe_reference",) and inspection.issues == ()
    assert adapter.read_check(path) == "UnsafePathError"


@pytest.mark.parametrize(
    ("reference", "place"),
    [
        ("../OUTSIDE/rec_raw-1.fif", "outside"),  # the reviewer's case
        ("{outside}/rec_raw-1.fif", "outside"),  # absolute
        ("sub/rec_raw-1.fif", "sub"),  # a folder inside the dataset is not followed either
        ("sub\\rec_raw-1.fif", "sub"),
        ("\\\\server\\share\\rec_raw-1.fif", None),  # UNC
        ("rec_raw-1.fif:stream", None),  # alternate data stream
    ],
)
def test_fif_split_reference_out_of_the_folder_is_not_followed(
    tmp_path: Path, split_source: Path, reference: str, place: str | None, no_mne: None
) -> None:
    path, second, outside = _split_dataset(tmp_path, split_source)
    if place is not None:
        target = outside if place == "outside" else path.parent / place
        target.mkdir(exist_ok=True)
        second.rename(target / second.name)
    _rewrite_reference(path, "rec_raw-1.fif", reference.format(outside=outside.as_posix()))
    assert fif._unsafe_split(path)
    _assert_not_followed(path)  # fixture no_mne: MNE's raw reader is never used


def test_mne_alone_follows_the_rewritten_split_reference(tmp_path: Path, split_source: Path) -> None:
    """What the check prevents: MNE reads the second part from outside the dataset."""
    import mne

    path, second, outside = _split_dataset(tmp_path, split_source)
    second.rename(outside / second.name)
    _rewrite_reference(path, "rec_raw-1.fif", "../OUTSIDE/rec_raw-1.fif")
    raw = mne.io.read_raw_fif(path, verbose="error")
    assert raw.n_times == N_TIMES and len(raw.filenames) == 2


def test_fif_reference_in_a_later_part_is_checked(tmp_path: Path, no_mne: None) -> None:
    """MNE follows the chain from part to part; the reference in the second part counts as well. The
    absolute name of the previous part that MNE writes into each later part is no reference MNE follows."""
    import mne

    ds, outside = tmp_path / "ds", tmp_path / "OUTSIDE"
    outside.mkdir()
    raw = mne.io.RawArray(
        np.zeros((2, 300_000)), mne.create_info(["Fp1", "Fp2"], 100.0, "eeg"), verbose="error"
    )
    ds.mkdir()
    raw.save(ds / "rec_raw.fif", split_size="2MB", fmt="single", verbose="error")
    assert sorted(p.name for p in ds.iterdir()) == ["rec_raw-1.fif", "rec_raw-2.fif", "rec_raw.fif"]
    assert not fif._unsafe_split(ds / "rec_raw.fif")
    (ds / "rec_raw-2.fif").rename(outside / "rec_raw-2.fif")
    _rewrite_reference(ds / "rec_raw-1.fif", "rec_raw-2.fif", "../OUTSIDE/rec_raw-2.fif")
    _assert_not_followed(ds / "rec_raw.fif")


@pytest.mark.parametrize("target", ["rec_raw.fif", "rec_raw-1.fif"])
def test_fif_cycle_through_a_later_part_is_not_followed(tmp_path: Path, target: str, no_mne: None) -> None:
    """Verifier, review P2: the second of three parts names the first part or itself as its next part; MNE
    would read the parts again and again without end. The cycle is found from a later part as well (A-52)."""
    import mne

    ds = tmp_path / "ds"
    ds.mkdir()
    raw = mne.io.RawArray(
        np.zeros((2, 300_000)), mne.create_info(["Fp1", "Fp2"], 100.0, "eeg"), verbose="error"
    )
    raw.save(ds / "rec_raw.fif", split_size="2MB", fmt="single", verbose="error")
    (ds / "rec_raw-2.fif").unlink()
    _rewrite_reference(ds / "rec_raw-1.fif", "rec_raw-2.fif", target)
    _assert_not_followed(ds / "rec_raw.fif")


def test_fif_split_part_that_is_a_link_is_not_followed(
    tmp_path: Path, split_source: Path, monkeypatch: pytest.MonkeyPatch, no_mne: None
) -> None:
    path, _second, _outside = _split_dataset(tmp_path, split_source)
    monkeypatch.setattr(safety, "is_link", lambda candidate: Path(candidate).name == "rec_raw-1.fif")
    _assert_not_followed(path)


def test_fif_split_reference_to_itself_is_not_followed(
    tmp_path: Path, split_source: Path, no_mne: None
) -> None:
    """MNE would read the file again and again without end; the chain is cut and reported (A-52)."""
    path, second, _outside = _split_dataset(tmp_path, split_source)
    second.unlink()
    _rewrite_reference(path, "rec_raw-1.fif", "rec_raw.fif")
    _assert_not_followed(path)


@pytest.mark.parametrize("naming", ["neuromag", "bids"])
def test_fif_regular_split_files_are_read_whole(tmp_path: Path, naming: str) -> None:
    name = "rec_raw.fif" if naming == "neuromag" else "sub-01_task-rest_eeg.fif"
    parts = _write_split(tmp_path / "ds", name, split_naming=naming)
    first = parts[0] if naming == "bids" else tmp_path / "ds" / name
    assert [p.name for p in parts] == (
        ["sub-01_task-rest_split-01_eeg.fif", "sub-01_task-rest_split-02_eeg.fif"]
        if naming == "bids"
        else ["rec_raw-1.fif", "rec_raw.fif"]
    )
    assert not fif._unsafe_split(first)
    adapter = FifAdapter()
    recording = adapter.read(first, recording_id="r", relative_path=first.name)
    assert recording.duration_s == N_TIMES / 100.0 and recording.metadata_sources["duration_s"] == "header"
    assert adapter.inspect(first).missing_companions == ()
    assert adapter.read_check(first) is None


def test_fif_missing_split_part_is_a_read_failure(tmp_path: Path, split_source: Path) -> None:
    """A plain name next to the file that does not exist: MNE stops on its own (no unsafe reference)."""
    path, second, _outside = _split_dataset(tmp_path, split_source)
    second.unlink()
    assert not fif._unsafe_split(path)
    with pytest.raises(HeaderUnreadable):
        FifAdapter().read(path, recording_id="r", relative_path=path.name)
    assert FifAdapter().read_check(path) == "ValueError"


def test_fif_damaged_file_is_left_to_mne(tmp_path: Path) -> None:
    junk = tmp_path / "junk_raw.fif"
    junk.write_bytes(b"\x00" * 200)
    assert not fif._unsafe_split(junk)
    assert FifAdapter().read_check(junk) == "ValueError"


# --- nothing outside is opened: audit hook and conversion ---------------------------------------------------

AUDIT_SCRIPT = """
import json
import os
import sys
from pathlib import Path

opened = []


def hook(event, args):
    if event == "open" and args:
        try:
            name = os.fsdecode(os.fspath(args[0]))
        except TypeError:
            return
        if "OUTSIDE" in name:
            opened.append(name)


sys.addaudithook(hook)
from neurogrid.io.brainvision import BrainVisionAdapter
from neurogrid.io.fif import FifAdapter

result = {}
for adapter, path in ((BrainVisionAdapter(), Path(sys.argv[1])), (FifAdapter(), Path(sys.argv[2]))):
    adapter.read(path, recording_id="r", relative_path=path.name)
    adapter.inspect(path)
    result[adapter.format] = adapter.read_check(path)
result["opened"] = opened
print(json.dumps(result))
"""


def _outside_cases(tmp_path: Path, split_source: Path) -> tuple[Path, Path]:
    """The two reviewer reproductions: a BrainVision header with 'DataFile: ../OUTSIDE/rec.eeg' and a split
    FIF whose second part lies in ../OUTSIDE; each in its own dataset folder ``ds``."""
    ds, _outside = _dataset(tmp_path / "bv")
    vhdr = _header(ds, "DataFile: ../OUTSIDE/rec.eeg\nMarkerFile=rec.vmrk\n")
    path, second, outside = _split_dataset(tmp_path / "fif", split_source)
    second.rename(outside / second.name)
    _rewrite_reference(path, "rec_raw-1.fif", "../OUTSIDE/rec_raw-1.fif")
    return vhdr, path


def test_no_file_outside_the_dataset_is_opened(tmp_path: Path, split_source: Path) -> None:
    """An audit hook sees every open() of the process: read, inspect and read_check stay inside (A-52)."""
    vhdr, fif_path = _outside_cases(tmp_path, split_source)
    script = tmp_path / "audit.py"
    script.write_text(AUDIT_SCRIPT, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(script), str(vhdr), str(fif_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {
        "BrainVision": "UnsafePathError",
        "FIF": "UnsafePathError",
        "opened": [],
    }


def test_convert_takes_over_no_outside_data(tmp_path: Path, split_source: Path) -> None:
    """Both recordings are skipped as M01-03 problems; no BIDS output is written (A-05, A-77)."""
    vhdr, fif_path = _outside_cases(tmp_path, split_source)
    results = {}
    for path in (vhdr, fif_path):
        config = path.parent / ".neurogrid" / "neurogrid.toml"
        config.parent.mkdir()
        config.write_text(
            f'[[convert.files]]\npath = "{path.name}"\nsubject = "01"\ntask = "rest"\n', encoding="utf-8"
        )
        out = path.parent.parent / "bids"
        summary = pipeline.run_convert(path.parent, out, work_base=path.parent.parent)
        results[path.suffix] = (summary.converted, summary.skipped, summary.exit_code, out.exists())
    assert results == {
        suffix: (0, [(pseudonym(PurePosixPath(name)), "convert.companion")], 1, False)
        for suffix, name in ((".vhdr", "rec.vhdr"), (".fif", "rec_raw.fif"))
    }
