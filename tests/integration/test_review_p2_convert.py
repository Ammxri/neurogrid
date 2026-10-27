"""Reproductions of the P2 review findings on ``convert`` and ``scan`` (A-03, A-05, A-12, A-52, A-54, A-66,
A-74, A-77, DM-07; .local/review_p2/CONFIRMED_FINDINGS.txt).

- One recording never aborts the run: names and paths MNE-BIDS misreads, BrainVision/EEGLAB data files with
  another name, EEGLAB MAT v7.3, FIF without EEG channels, any other failure (taken back, listed).
- Labels that differ only in case are one target.
- Annotation-only files (hypnograms) need no mapping, in convert and in scan.
- The mapping template is never written through a link, and a folder that cannot take it gives a message.
- An aborted run (comma path, validator failure, Ctrl+C) leaves no new output.
- --strip-identifying-headers changes bytes only; the Codepage stays true.
- BrainVision template positions are not written; channels.tsv of EDF follows the header; hashes cover every
  file; orphan companions keep their reason.
"""

from __future__ import annotations

import codecs
import contextlib
import hashlib
import os
import shutil
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import pytest
from test_convert import (  # type: ignore[import-not-found]
    FIX,
    METADATA,
    _annotation_only_edf,
    _copy,
    _copy_folder,
    _json,
    _row,
    _run,
    _tsv,
    _write_config,
)

import gen_fixtures  # type: ignore[import-not-found]
from conftest import (  # type: ignore[import-not-found]
    LOCALE_ENCODINGS,
    dir_link,
    leave_out_of_order,
    linux_text_system,
    locale_encoding,
)
from neurogrid import pipeline
from neurogrid.convert import _strip_brainvision, write_mapping_template
from neurogrid.io.brainvision import mne_read_raw_brainvision
from neurogrid.io.discover import FoundFile, pseudonym
from neurogrid.kernel.errors import InputError, NeuroGridError
from neurogrid.validator import ValidatorError


def _pseudo(name: str) -> str:
    return pseudonym(PurePosixPath(name))


def _files_hash(paths: list[Path]) -> str:
    """SHA-256 over the sorted lines "<file name>\\t<SHA-256 of the file>\\n" (DM-07)."""
    lines = sorted(
        f"{path.name}\t{hashlib.sha256(path.read_bytes()).hexdigest()}\n".encode() for path in paths
    )
    return hashlib.sha256(b"".join(lines)).hexdigest()


def _mapped_pair(raw: Path) -> None:
    for name in ("rec_a.edf", "rec_b.edf"):
        _copy(FIX / "edf_ok" / name, raw / name)
    _write_config(raw, METADATA + _row("rec_a.edf", "01") + _row("rec_b.edf", "02"))


def _data(vhdr_or_file: Path) -> Any:
    """The samples as MNE reads them; BrainVision as NeuroGrid has MNE read it: plain MNE decodes the marker
    file with the locale's encoding and cannot read a Latin-1 marker file on Linux (A-77, TECH-05)."""
    import mne

    reader = {".vhdr": mne_read_raw_brainvision, ".set": mne.io.read_raw_eeglab}[vhdr_or_file.suffix]
    return reader(vhdr_or_file, preload=True, verbose="error").get_data()


def _tree(folder: Path) -> dict[str, bytes]:
    """Every file below ``folder`` with its bytes, by relative path."""
    return {
        path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob("*") if path.is_file()
    }


# --- one recording never aborts the run (A-77) --------------------------------------------------------------


def test_names_and_paths_that_mne_bids_misreads_are_still_copied(tmp_path: Path) -> None:
    """MNE-BIDS edits the data path as text and splits the name at its first dot; such files are linked under
    a plain name into the work folder first, so EDF stays a file copy (A-77)."""
    raw = tmp_path / "lab.data" / "raw"  # '.dat' outside the dataset as well
    names = {
        "2021.08.24 rec.edf": "01",
        "rec.Edf": "02",
        "study.data/rec_a.edf": "03",
        "x.eeg.edf": "04",
        "old.dsets/rec.edf": "05",
        "normal.edf": "06",
    }
    for name in names:
        _copy(FIX / "edf_ok" / "rec_a.edf", raw / name)
    _write_config(raw, METADATA + "".join(_row(name, subject) for name, subject in names.items()))
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, work_base=tmp_path)
    assert (summary.converted, summary.skipped, summary.validator_errors, summary.exit_code) == (6, [], 0, 0)
    for name, subject in names.items():
        written = out / f"sub-{subject}" / "eeg" / f"sub-{subject}_task-rest_eeg.edf"
        assert written.read_bytes() == (raw / name).read_bytes(), name  # a file copy, not a conversion
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bids", "lab.data"]  # staged links are gone (A-54)


def _renamed_data_files(raw: Path) -> None:
    """A BrainVision header naming data.eeg/marks.vmrk and an EEGLAB set naming other.fdt (allowed, A-77)."""
    import scipy.io

    header = (FIX / "brainvision_ok" / "rec.vhdr").read_text(encoding="utf-8")
    header = header.replace("DataFile=rec.eeg", "DataFile=data.eeg").replace(
        "MarkerFile=rec.vmrk", "MarkerFile=marks.vmrk"
    )
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "rec.vhdr").write_bytes(header.encode("utf-8"))
    marker = (FIX / "brainvision_ok" / "rec.vmrk").read_text(encoding="utf-8")
    (raw / "marks.vmrk").write_bytes(marker.replace("DataFile=rec.eeg", "DataFile=data.eeg").encode("utf-8"))
    shutil.copyfile(FIX / "brainvision_ok" / "rec.eeg", raw / "data.eeg")
    eeg = scipy.io.loadmat(FIX / "eeglab_ok" / "rec.set", appendmat=False)["EEG"]
    eeg["data"][0, 0] = "other.fdt"
    if "datfile" in eeg.dtype.names:
        eeg["datfile"][0, 0] = "other.fdt"
    scipy.io.savemat(raw / "ab.set", {"EEG": eeg}, appendmat=False, format="5", oned_as="row")
    shutil.copyfile(FIX / "eeglab_ok" / "rec.fdt", raw / "other.fdt")


def test_data_files_with_another_name_are_written_as_brainvision(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _renamed_data_files(raw)
    _copy(FIX / "edf_ok" / "rec_a.edf", raw / "rec_a.edf")
    _write_config(raw, METADATA + _row("rec.vhdr", "01") + _row("ab.set", "02") + _row("rec_a.edf", "03"))
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, work_base=tmp_path)
    assert (summary.converted, summary.skipped, summary.validator_errors, summary.exit_code) == (3, [], 0, 0)
    for subject, source in (("01", raw / "rec.vhdr"), ("02", raw / "ab.set")):
        vhdr = out / f"sub-{subject}" / "eeg" / f"sub-{subject}_task-rest_eeg.vhdr"
        np.testing.assert_allclose(_data(vhdr), _data(source), rtol=1e-6, atol=1e-12)
    steps = {
        step["parameters"]["target"]: step for step in _json(out / ".neurogrid" / "processing_steps.json")
    }
    step = steps["sub-01/eeg/sub-01_task-rest_eeg.vhdr"]
    assert step["input_hash"] == _files_hash([raw / "rec.vhdr", raw / "data.eeg", raw / "marks.vmrk"])
    assert steps["sub-02/eeg/sub-02_task-rest_eeg.vhdr"]["input_hash"] == _files_hash(
        [raw / "ab.set", raw / "other.fdt"]
    )


def _fif(path: Path, names: list[str], kinds: list[str]) -> None:
    import mne

    info = mne.create_info(names, 500.0, kinds, verbose="error")
    data = np.random.default_rng(1).normal(0.0, 1e-12, (len(names), 1000))
    path.parent.mkdir(parents=True, exist_ok=True)
    mne.io.RawArray(data, info, verbose="error").save(path, verbose="error")


def test_fif_without_eeg_channels_is_listed_and_the_rest_converted(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _fif(raw / "eeg_raw.fif", ["Fz", "Cz"], ["eeg", "eeg"])
    _fif(raw / "megonly_raw.fif", ["MEG 0111", "MEG 0112"], ["mag", "grad"])
    _fif(raw / "megstim_raw.fif", ["MEG 0111", "EOG 061", "STI 014"], ["mag", "eog", "stim"])
    _write_config(
        raw,
        METADATA + _row("eeg_raw.fif", "01") + _row("megonly_raw.fif", "02") + _row("megstim_raw.fif", "03"),
    )
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, work_base=tmp_path)
    assert summary.converted == 1 and summary.validator_errors == 0 and summary.exit_code == 1
    assert summary.skipped == [
        (_pseudo("megonly_raw.fif"), "convert.no_eeg_channels"),
        (_pseudo("megstim_raw.fif"), "convert.no_eeg_channels"),
    ]
    assert sorted(p.name for p in out.iterdir() if p.name.startswith("sub-")) == ["sub-01"]


def _eeglab_v73(path: Path) -> None:
    """An EEGLAB data set saved as MATLAB v7.3 (HDF5) with a .fdt file (EEGLAB with 'version' 7.3)."""
    import h5py

    nbchan, pnts, srate, labels = 4, 5000, 500.0, ["Fz", "Cz", "Pz", "Oz"]

    def char(group: Any, name: str, text: str) -> None:
        data = (
            np.array([[ord(c)] for c in text], dtype=np.uint16) if text else np.zeros((2,), dtype=np.uint64)
        )
        dataset = group.create_dataset(name, data=data)
        dataset.attrs["MATLAB_class"] = np.bytes_("char")
        if not text:
            dataset.attrs["MATLAB_empty"] = np.uint8(1)

    def number(group: Any, name: str, value: float) -> None:
        dataset = group.create_dataset(name, data=np.array([[value]], dtype=np.float64))
        dataset.attrs["MATLAB_class"] = np.bytes_("double")

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w", userblock_size=512) as handle:
        eeg = handle.create_group("EEG")
        eeg.attrs["MATLAB_class"] = np.bytes_("struct")
        for name, value in (("nbchan", nbchan), ("pnts", pnts), ("trials", 1), ("srate", srate)):
            number(eeg, name, value)
        number(eeg, "xmin", 0.0)
        number(eeg, "xmax", (pnts - 1) / srate)
        char(eeg, "data", path.with_suffix(".fdt").name)
        char(eeg, "datfile", path.with_suffix(".fdt").name)
        char(eeg, "setname", "")
        char(eeg, "ref", "common")
        refs = handle.create_group("#refs#")
        locs = eeg.create_group("chanlocs")
        locs.attrs["MATLAB_class"] = np.bytes_("struct")
        ref_dtype = h5py.special_dtype(ref=h5py.Reference)
        for field in ("labels", "type"):
            column = np.empty((nbchan, 1), dtype=ref_dtype)
            for index, label in enumerate(labels):
                char(refs, f"{field}{index}", label if field == "labels" else "EEG")
                column[index, 0] = refs[f"{field}{index}"].ref
            locs.create_dataset(field, data=column, dtype=ref_dtype)
        for field in ("X", "Y", "Z", "theta", "radius", "sph_theta", "sph_phi", "sph_radius"):
            column = np.empty((nbchan, 1), dtype=ref_dtype)
            for index in range(nbchan):
                dataset = refs.create_dataset(f"{field}{index}", data=np.zeros((2,), dtype=np.uint64))
                dataset.attrs["MATLAB_class"] = np.bytes_("double")
                dataset.attrs["MATLAB_empty"] = np.uint8(1)
                column[index, 0] = dataset.ref
            locs.create_dataset(field, data=column, dtype=ref_dtype)
    header = (
        b"MATLAB 7.3 MAT-file, Platform: PCWIN64, Created on: Mon Jan  1 00:00:00 2024 HDF5 schema 1.00 ."
    )
    with path.open("r+b") as handle:
        handle.write(header.ljust(116, b" ") + b"\x00" * 8 + b"\x00\x02" + b"IM")
    samples = np.random.default_rng(3).normal(0, 10, (pnts, nbchan)).astype("<f4")
    path.with_suffix(".fdt").write_bytes(samples.tobytes())


def test_eeglab_v73_with_fdt_is_written_as_brainvision(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _eeglab_v73(raw / "v73.set")
    _write_config(raw, METADATA + _row("v73.set", "01"))
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, work_base=tmp_path)
    assert (summary.converted, summary.skipped, summary.validator_errors, summary.exit_code) == (1, [], 0, 0)
    vhdr = out / "sub-01" / "eeg" / "sub-01_task-rest_eeg.vhdr"
    np.testing.assert_allclose(_data(vhdr), _data(raw / "v73.set"), rtol=1e-6, atol=1e-12)


@pytest.mark.parametrize(
    ("first", "second"),
    [(("A", "rest"), ("a", "rest")), (("01", "Rest"), ("01", "rest"))],
    ids=["subject", "task"],
)
def test_labels_that_differ_only_in_case_are_one_target(
    tmp_path: Path, first: tuple[str, str], second: tuple[str, str]
) -> None:
    """sub-A and sub-a are one folder on Windows and macOS (A-77)."""
    raw = tmp_path / "raw"
    for name in ("rec_a.edf", "rec_b.edf"):
        _copy(FIX / "edf_ok" / name, raw / name)
    _write_config(raw, METADATA + _row("rec_a.edf", *first) + _row("rec_b.edf", *second))
    out = tmp_path / "bids"
    with pytest.raises(InputError) as info:
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert info.value.message_key == "convert.duplicate_target"
    assert info.value.params == {"subject": second[0], "task": second[1]}
    assert not out.exists()


@pytest.mark.parametrize(
    ("rows", "first", "second"),
    [
        (
            _row("rec_a.edf", "A", "rest") + _row("rec_b.edf", "a", "sleep"),
            "sub-A",
            "sub-a",
        ),
        (
            _row("rec_a.edf", "01", "rest", session="X") + _row("rec_b.edf", "01", "sleep", session="x"),
            "sub-01/ses-X",
            "sub-01/ses-x",
        ),
    ],
    ids=["subject", "session"],
)
def test_labels_that_differ_only_in_case_are_refused_also_for_different_targets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], rows: str, first: str, second: str
) -> None:
    """sub-A/task-rest and sub-a/task-sleep are two targets, but one folder on Windows and macOS: the output
    would mix two subjects there, so the run is refused before anything is written, on every platform."""
    raw = tmp_path / "raw"
    for name in ("rec_a.edf", "rec_b.edf"):
        _copy(FIX / "edf_ok" / name, raw / name)
    _write_config(raw, METADATA + rows)
    out = tmp_path / "bids"
    with pytest.raises(InputError) as info:
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert info.value.message_key == "convert.label_case"
    assert info.value.params == {"first": first, "second": second}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["raw"]
    code, stdout, stderr = _run(["convert", str(raw), "--to", "bids", "--out", str(out)], capsys)
    assert code == 2 and stdout == ""
    assert stderr.strip() == (
        f"Error: The labels {first} and {second} differ only in case; they would share one folder on "
        "Windows and macOS. Please make them distinct."
    )
    assert not out.exists()


def _brainvision_triple(raw: Path, stem: str, *, data: str | None = None, marker_extra: bytes = b"") -> Path:
    """The brainvision_ok recording under the header name ``<stem>.vhdr``, its data file named ``data``."""
    data = data or f"{stem}.eeg"
    vhdr = raw / f"{stem}.vhdr"
    vhdr.parent.mkdir(parents=True, exist_ok=True)
    header = (FIX / "brainvision_ok" / "rec.vhdr").read_text(encoding="utf-8")
    header = header.replace("DataFile=rec.eeg", f"DataFile={data}")
    vhdr.write_bytes(header.replace("MarkerFile=rec.vmrk", f"MarkerFile={stem}.vmrk").encode("utf-8"))
    marker = (FIX / "brainvision_ok" / "rec.vmrk").read_text(encoding="utf-8")
    marker = marker.replace("DataFile=rec.eeg", f"DataFile={data}")
    vhdr.with_name(f"{stem}.vmrk").write_bytes(marker.encode("utf-8") + marker_extra)
    shutil.copyfile(FIX / "brainvision_ok" / "rec.eeg", vhdr.with_name(data))
    return vhdr


def _dotted_eeglab(raw: Path) -> Path:
    import scipy.io

    raw.mkdir(parents=True, exist_ok=True)
    eeg = scipy.io.loadmat(FIX / "eeglab_ok" / "rec.set", appendmat=False)["EEG"]
    eeg["data"][0, 0] = "a.b.fdt"
    if "datfile" in eeg.dtype.names:
        eeg["datfile"][0, 0] = "a.b.fdt"
    scipy.io.savemat(raw / "a.b.set", {"EEG": eeg}, appendmat=False, format="5", oned_as="row")
    shutil.copyfile(FIX / "eeglab_ok" / "rec.fdt", raw / "a.b.fdt")
    return raw / "a.b.set"


@pytest.mark.parametrize(
    "case",
    ["dotted-name", "eeg-folder", "dat-data-file", "marker-not-in-codepage", "dotted-eeglab"],
)
def test_brainvision_and_eeglab_that_mne_bids_cannot_copy_are_written_as_brainvision(
    tmp_path: Path, case: str
) -> None:
    """MNE-BIDS cannot copy these (name split at the first dot, '.eeg' replaced anywhere in the path, a '.dat'
    data file taken for Persyst, a marker file that does not decode with the declared code page); they are
    written from the loaded data instead, and the run does not end (A-77)."""
    raw = tmp_path / "raw"
    if case == "dotted-name":
        source = _brainvision_triple(raw, "2021.08.24 rec")
    elif case == "eeg-folder":
        source = _brainvision_triple(raw / "study.eeg", "rec")
    elif case == "dat-data-file":
        source = _brainvision_triple(raw, "rec", data="rec.dat")
    elif case == "marker-not-in-codepage":  # Codepage=UTF-8, but a Latin-1 marker text
        source = _brainvision_triple(raw, "rec", marker_extra="Mk2=Comment,Größe,100,1,0\n".encode("latin-1"))
    else:
        source = _dotted_eeglab(raw)
    name = source.relative_to(raw).as_posix()
    _write_config(raw, METADATA + _row(name, "01"))
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, work_base=tmp_path)
    outcome = (summary.converted, summary.skipped, summary.validator_errors, summary.exit_code)
    assert outcome == (1, [], 0, 0), _why_not_converted(source)
    vhdr = out / "sub-01" / "eeg" / "sub-01_task-rest_eeg.vhdr"
    np.testing.assert_allclose(_data(vhdr), _data(source), rtol=1e-6, atol=1e-12)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bids", "raw"]


def _why_not_converted(source: Path) -> str:
    """For the CI annotation: the read check of the source, the locale's encoding and whether Python knows
    the codec ANSI on this system."""
    import locale

    from neurogrid.io import ADAPTERS

    try:
        ansi = codecs.lookup("ANSI").name
    except LookupError:
        ansi = "unknown"
    check = ADAPTERS[source.suffix].read_check(source)
    return f"read_check={check}, locale encoding={locale.getpreferredencoding(False)}, codec ANSI={ansi}"


@pytest.mark.parametrize(
    ("marker_extra", "copied"),
    [
        ("Mk2=Comment,Größe,100,1,0\n".encode("latin-1"), False),  # Codepage=UTF-8 claimed: rewritten
        ("Mk2=Comment,睁眼,100,1,0\n".encode(), True),  # UTF-8: copied; 睁 holds 0x9D and 0x81 (no cp1252)
    ],
    ids=["latin-1-marker", "utf-8-chinese-marker"],
)
def test_brainvision_marker_text_is_converted_the_same_under_every_locale(
    tmp_path: Path, marker_extra: bytes, copied: bool
) -> None:
    """CI ubuntu-24.04, [marker-not-in-codepage]: (0, [(rec, 'read.failed')], 0, 1) instead of (1, [], 0, 0).
    MNE read the Latin-1 marker file with the locale's encoding, UTF-8 there, and failed; on a Western Windows
    the same happened to a UTF-8 marker file with Chinese text, also when MNE-BIDS reads the recording it
    copies once more. Simulated here with the locale encodings of Linux and of a Western and a Chinese
    Windows: converted, to the same files."""
    trees = {}
    for system, codec in LOCALE_ENCODINGS.items():
        base = tmp_path / codec
        raw = base / "raw"
        _brainvision_triple(raw, "rec", marker_extra=marker_extra)
        _write_config(raw, METADATA + _row("rec.vhdr", "01"))
        with locale_encoding(codec):
            summary = pipeline.run_convert(raw, base / "bids", work_base=base)
        outcome = (summary.converted, summary.skipped, summary.validator_errors, summary.exit_code)
        assert outcome == (1, [], 0, 0), system
        trees[system] = _tree(base / "bids")
        written = base / "bids" / "sub-01" / "eeg" / "sub-01_task-rest_eeg.eeg"
        assert (written.read_bytes() == (raw / "rec.eeg").read_bytes()) is copied
    assert trees["Linux"] == trees["Western Windows"] == trees["Chinese Windows"]


def test_upper_case_extensions_and_names_mne_bids_misreads_stay_file_copies(tmp_path: Path) -> None:
    """Upper-case extensions, a name MNE-BIDS takes for BTi ('c,rf') and a dotted EDF+D name: staged under a
    plain name, then copied byte for byte, so EDF+D keeps its gaps (A-77)."""
    raw = tmp_path / "raw"
    sources = {
        "A.EDF": (FIX / "edf_ok" / "rec_a.edf", "01", ".edf"),
        "b.BDF": (FIX / "bdf_ok" / "rec.bdf", "02", ".bdf"),
        "c,rf.edf": (FIX / "edf_ok" / "rec_b.edf", "03", ".edf"),
        "2021.08.24 d.edf": (FIX / "edf_plus_d" / "rec.edf", "04", ".edf"),
    }
    for name, (source, _subject, _extension) in sources.items():
        _copy(source, raw / name)
    _write_config(raw, METADATA + "".join(_row(name, subject) for name, (_s, subject, _e) in sources.items()))
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, work_base=tmp_path)
    assert (summary.converted, summary.skipped, summary.validator_errors, summary.exit_code) == (4, [], 0, 0)
    for name, (_source, subject, extension) in sources.items():
        written = out / f"sub-{subject}" / "eeg" / f"sub-{subject}_task-rest_eeg{extension}"
        assert written.read_bytes() == (raw / name).read_bytes(), name
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bids", "raw"]


def test_edf_plus_d_that_would_still_be_misread_is_listed_and_the_rest_converted(tmp_path: Path) -> None:
    """Input and work folder below 'study.data': even the staged path holds '.dat'. EDF+D is then not
    converted (written as BrainVision it would lose its gaps); a continuous EDF is written as BrainVision."""
    import mne

    folder = tmp_path / "study.data"
    raw = folder / "raw"
    _copy(FIX / "edf_plus_d" / "rec.edf", raw / "d.edf")
    _copy(FIX / "edf_ok" / "rec_a.edf", raw / "c.edf")
    _write_config(raw, METADATA + _row("d.edf", "01") + _row("c.edf", "02"))
    out = folder / "bids"
    summary = pipeline.run_convert(raw, out, work_base=folder)
    assert (summary.converted, summary.validator_errors, summary.exit_code) == (1, 0, 1)
    assert summary.skipped == [(_pseudo("d.edf"), "convert.failed")]
    assert sorted(p.name for p in out.iterdir() if p.name.startswith("sub-")) == ["sub-02"]
    vhdr = out / "sub-02" / "eeg" / "sub-02_task-rest_eeg.vhdr"
    source = mne.io.read_raw_edf(raw / "c.edf", preload=True, verbose="error").get_data()
    np.testing.assert_allclose(_data(vhdr), source, rtol=1e-6, atol=1e-12)
    assert sorted(p.name for p in folder.iterdir()) == ["bids", "raw"]


def test_edf_without_eeg_channels_is_listed_and_the_rest_converted(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _edf(raw / "heart.edf", (("ECG", "mV", "", 256), ("EMG chin", "uV", "", 256)))
    _copy(FIX / "edf_ok" / "rec_a.edf", raw / "ok.edf")
    _write_config(raw, METADATA + _row("heart.edf", "01") + _row("ok.edf", "02"))
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, work_base=tmp_path)
    assert (summary.converted, summary.validator_errors, summary.exit_code) == (1, 0, 1)
    assert summary.skipped == [(_pseudo("heart.edf"), "convert.no_eeg_channels")]
    assert sorted(p.name for p in out.iterdir() if p.name.startswith("sub-")) == ["sub-02"]


def test_a_failing_recording_is_taken_back_and_the_run_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mne_bids

    raw = tmp_path / "raw"
    for index, name in enumerate(("rec_a.edf", "rec_b.edf", "rec_c.edf", "rec_d.edf")):
        _copy(FIX / "edf_ok" / ("rec_a.edf", "rec_b.edf")[index % 2], raw / name)
    _write_config(
        raw,
        METADATA
        + _row("rec_a.edf", "03")  # fails, the first recording of the run and the only one of sub-03
        + _row("rec_b.edf", "01", session="1")
        + _row("rec_c.edf", "01", session="2")  # fails; sub-01 keeps its other session
        + _row("rec_d.edf", "02"),
    )
    original = mne_bids.write_raw_bids

    def write_then_fail(raw_object: Any, bids_path: Any, **kwargs: Any) -> Any:
        written = original(raw_object, bids_path, **kwargs)
        if bids_path.subject == "03" or bids_path.session == "2":
            raise RuntimeError("disk full")  # after MNE-BIDS wrote data, sidecars and table rows
        return written

    monkeypatch.setattr(mne_bids, "write_raw_bids", write_then_fail)
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, work_base=tmp_path)
    assert summary.converted == 2 and summary.validator_errors == 0 and summary.exit_code == 1
    assert summary.skipped == [
        (_pseudo("rec_a.edf"), "convert.failed"),
        (_pseudo("rec_c.edf"), "convert.failed"),
    ]
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert not [name for name in files if "sub-03" in name or "ses-2" in name]
    assert sorted(row["participant_id"] for row in _tsv(out / "participants.tsv")) == ["sub-01", "sub-02"]
    assert [row["filename"] for row in _tsv(out / "sub-01" / "ses-1" / "sub-01_ses-1_scans.tsv")] == [
        "eeg/sub-01_ses-1_task-rest_eeg.edf"
    ]
    steps = _json(out / ".neurogrid" / "processing_steps.json")
    assert sorted(step["parameters"]["target"] for step in steps) == [
        "sub-01/ses-1/eeg/sub-01_ses-1_task-rest_eeg.edf",
        "sub-02/eeg/sub-02_task-rest_eeg.edf",
    ]


# --- annotation-only files (A-74, A-77) ---------------------------------------------------------------------


def _psg_with_hypnogram(raw: Path) -> None:
    _copy(FIX / "edf_ok" / "rec_a.edf", raw / "SN1_psg.edf")
    _annotation_only_edf(raw / "SN1_hypnogram.edf")


def test_hypnograms_need_no_mapping_and_are_listed(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _psg_with_hypnogram(raw)
    _write_config(raw, METADATA + _row("SN1_psg.edf", "SN1", "sleep"))
    summary = pipeline.run_convert(raw, tmp_path / "bids", work_base=tmp_path)
    assert summary.converted == 1 and summary.validator_errors == 0
    assert summary.skipped == [(_pseudo("SN1_hypnogram.edf"), "recording.annotations_only")]
    assert summary.exit_code == 1  # its annotations are not in the output: a file that was not converted
    assert not (raw / ".neurogrid" / "mapping-template.toml").exists()


def test_a_hypnogram_mapped_like_its_recording_is_no_duplicate(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _psg_with_hypnogram(raw)
    # the natural mapping gives the hypnogram the target of the recording it scores
    _write_config(
        raw, METADATA + _row("SN1_psg.edf", "SN1", "sleep") + _row("SN1_hypnogram.edf", "SN1", "sleep")
    )
    summary = pipeline.run_convert(raw, tmp_path / "bids", work_base=tmp_path)
    assert summary.converted == 1
    assert summary.skipped == [(_pseudo("SN1_hypnogram.edf"), "recording.annotations_only")]


def test_scan_counts_subjects_without_mapping_the_hypnogram(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _psg_with_hypnogram(raw)
    _write_config(raw, METADATA + _row("SN1_psg.edf", "SN1", "sleep"))
    assert pipeline.run_scan(raw).subjects == 1
    _write_config(raw, METADATA)  # the recording itself is not mapped: unknown
    assert pipeline.run_scan(raw).subjects is None


# --- mapping template (A-52, A-66, A-74) --------------------------------------------------------------------


def test_template_is_not_written_through_a_linked_neurogrid_folder(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _copy(FIX / "edf_ok" / "rec_a.edf", raw / "rec_a.edf")
    outside = tmp_path / "operator_folder"
    outside.mkdir()
    dir_link(raw / ".neurogrid", outside)
    config = tmp_path / "operator.toml"  # an operator configuration: the linked folder is not read for it
    config.write_text(METADATA, encoding="utf-8")
    out = tmp_path / "bids"
    with pytest.raises(InputError) as info:
        pipeline.run_convert(raw, out, config_path=config, work_base=tmp_path)
    assert info.value.message_key == "convert.mapping_missing_unwritable"
    assert info.value.params == {"count": 1, "template": "mapping-template.toml"}
    assert list(outside.iterdir()) == [] and not out.exists()


def test_template_replaces_a_hard_link_instead_of_writing_through_it(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _copy(FIX / "edf_ok" / "rec_a.edf", raw / "rec_a.edf")
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"a file outside the dataset")
    (raw / ".neurogrid").mkdir()
    try:
        os.link(victim, raw / ".neurogrid" / "mapping-template.toml")
    except OSError:
        pytest.skip("hard links not supported here")
    with pytest.raises(InputError) as info:
        pipeline.run_convert(raw, tmp_path / "bids", work_base=tmp_path)
    assert info.value.message_key == "convert.mapping_missing"
    assert victim.read_bytes() == b"a file outside the dataset"
    template = (raw / ".neurogrid" / "mapping-template.toml").read_bytes()
    assert template.startswith(b"# NeuroGrid mapping template")
    assert sorted(p.name for p in (raw / ".neurogrid").iterdir()) == ["mapping-template.toml"]  # no temp file


def test_template_is_not_written_through_a_linked_template_file(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _copy(FIX / "edf_ok" / "rec_a.edf", raw / "rec_a.edf")
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"a file outside the dataset")
    (raw / ".neurogrid").mkdir()
    try:
        (raw / ".neurogrid" / "mapping-template.toml").symlink_to(victim)
    except OSError:
        pytest.skip("symbolic links not permitted here")
    config = tmp_path / "operator.toml"
    config.write_text(METADATA, encoding="utf-8")
    with pytest.raises(InputError) as info:
        pipeline.run_convert(raw, tmp_path / "bids", config_path=config, work_base=tmp_path)
    assert info.value.message_key == "convert.mapping_missing_unwritable"
    assert victim.read_bytes() == b"a file outside the dataset"


def test_input_folder_that_cannot_take_the_template_is_no_internal_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    _copy(FIX / "edf_ok" / "rec_a.edf", raw / "rec_a.edf")
    (raw / ".neurogrid").write_bytes(b"a file where the folder would be")
    out = tmp_path / "bids"
    with pytest.raises(InputError) as info:
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert info.value.message_key == "convert.mapping_missing_unwritable"
    assert info.value.params == {"count": 1, "template": "mapping-template.toml"}
    code, stdout, stderr = _run(["convert", str(raw), "--to", "bids", "--out", str(out)], capsys)
    assert code == 2 and stdout == "" and "Internal error" not in stderr and "Traceback" not in stderr
    assert not out.exists()


def test_template_parses_for_names_with_del_and_names_that_are_not_unicode(tmp_path: Path) -> None:
    names = ["rec\x7f.edf", "M\udcfcller_rest.edf", "tab\tand\x01control.edf"]
    items = [
        FoundFile(relative=PurePosixPath(name), display_id=_pseudo(name), suffix=".edf", size_bytes=1)
        for name in names
    ]
    template = write_mapping_template(tmp_path, items)
    text = template.read_text(encoding="utf-8")
    rows = tomllib.loads(text)["convert"]["files"]
    assert [row["path"] for row in rows] == [
        "rec\x7f.edf",
        "M\\uDCFCller_rest.edf",
        "tab\tand\x01control.edf",
    ]
    assert (
        "# This file name is not valid Unicode" in text
    )  # it cannot be mapped by name; the template says so


def test_names_that_are_not_unicode_get_a_template_instead_of_an_internal_error(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    try:
        shutil.copyfile(FIX / "edf_ok" / "rec_a.edf", raw / "M\udcfcller_rest.edf")
    except (OSError, UnicodeError):
        pytest.skip("the file system does not store names that are not valid Unicode")
    with pytest.raises(InputError) as info:
        pipeline.run_convert(raw, tmp_path / "bids", work_base=tmp_path)
    assert info.value.message_key == "convert.mapping_missing"
    rows = tomllib.loads((raw / ".neurogrid" / "mapping-template.toml").read_text(encoding="utf-8"))
    assert len(rows["convert"]["files"]) == 1


# --- an aborted run leaves no output (A-06, A-54, A-77) -----------------------------------------------------


@pytest.mark.parametrize("existing", [False, True], ids=["new", "empty-folder"])
def test_comma_in_the_output_is_refused_before_anything_is_written(tmp_path: Path, existing: bool) -> None:
    raw = tmp_path / "raw"
    _mapped_pair(raw)
    out = tmp_path / "a,b"
    if existing:
        out.mkdir()
    with pytest.raises(NeuroGridError) as info:
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert info.value.message_key == "validator.comma_path"
    assert (list(out.iterdir()) == []) if existing else not out.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(["raw", *(["a,b"] if existing else [])])


def test_comma_in_the_work_folder_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _mapped_pair(raw)
    out = tmp_path / "bids"
    with pytest.raises(NeuroGridError) as info:
        pipeline.run_convert(raw, out, work_base=tmp_path / "w,x")
    assert info.value.message_key == "validator.comma_path"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["raw"]


@pytest.mark.parametrize("existing", [False, True], ids=["new", "empty-folder"])
def test_validator_failure_removes_the_new_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    import neurogrid.validator

    raw = tmp_path / "raw"
    _mapped_pair(raw)
    out = tmp_path / "bids"
    if existing:
        out.mkdir()

    def broken(dataset: Path, work: Path, timeout: float = 0) -> Any:
        raise ValidatorError("validator.failed", code=3)

    monkeypatch.setattr(neurogrid.validator, "run", broken)
    with pytest.raises(ValidatorError):
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert (list(out.iterdir()) == []) if existing else not out.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(["raw", *(["bids"] if existing else [])])


def _interrupt_second_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    import mne_bids

    original = mne_bids.write_raw_bids
    calls: list[int] = []

    def write(raw_object: Any, bids_path: Any, **kwargs: Any) -> Any:
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return original(raw_object, bids_path, **kwargs)

    monkeypatch.setattr(mne_bids, "write_raw_bids", write)


def test_ctrl_c_removes_the_new_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = tmp_path / "raw"
    _mapped_pair(raw)
    _interrupt_second_recording(monkeypatch)
    out = tmp_path / "bids"
    with pytest.raises(KeyboardInterrupt):
        pipeline.run_convert(raw, out, work_base=tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["raw"]


def test_ctrl_c_on_the_command_line_leaves_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    _mapped_pair(raw)
    _interrupt_second_recording(monkeypatch)
    out = tmp_path / "bids"
    out.mkdir()  # an empty folder of the operator: kept, and empty again
    code, stdout, _stderr = _run(["convert", str(raw), "--to", "bids", "--out", str(out)], capsys)
    assert code == 130 and stdout == ""  # Typer's code for an interrupt (128 + SIGINT), no data verdict
    assert list(out.iterdir()) == [] and sorted(p.name for p in tmp_path.iterdir()) == ["bids", "raw"]


# --- --strip-identifying-headers keeps the bytes (A-77) -----------------------------------------------------


def _ansi_brainvision(raw: Path) -> None:
    """A Western BrainVision Recorder triple: Codepage=ANSI (cp1252), "µV", umlauts in a marker, a name in the
    comment and a recording date in the New Segment marker."""
    header = (
        (FIX / "brainvision_ok" / "rec.vhdr")
        .read_text(encoding="utf-8")
        .replace("Codepage=UTF-8", "Codepage=ANSI")
    )
    header = header.replace("[Comment]\n", "[Comment]\nPatient: Müller, born 01.02.1980\n")
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "rec.vhdr").write_bytes(header.encode("cp1252"))
    marker = (
        (FIX / "brainvision_ok" / "rec.vmrk")
        .read_text(encoding="utf-8")
        .replace("Codepage=UTF-8", "Codepage=ANSI")
    )
    marker = marker.replace("Mk1=New Segment,,1,1,0\n", "Mk1=New Segment,,1,1,0,20210824101500000000\n")
    marker += "Mk2=Comment,Größe ändern,100,1,0\n"
    (raw / "rec.vmrk").write_bytes(marker.encode("cp1252"))
    shutil.copyfile(FIX / "brainvision_ok" / "rec.eeg", raw / "rec.eeg")


def test_strip_keeps_the_codepage_true_and_the_marker_text(tmp_path: Path) -> None:
    """The ANSI recording is copied on every system (TECH-05): Codepage=ANSI and the cp1252 bytes stay."""
    raw = tmp_path / "raw"
    _ansi_brainvision(raw)
    _write_config(raw, METADATA + _row("rec.vhdr", "01"))
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, strip_identifying_headers=True, work_base=tmp_path)
    outcome = (summary.converted, summary.validator_errors, summary.exit_code)
    assert outcome == (1, 0, 0), _why_not_converted(raw / "rec.vhdr")
    vhdr = out / "sub-01" / "eeg" / "sub-01_task-rest_eeg.vhdr"
    header, marker = vhdr.read_bytes(), vhdr.with_suffix(".vmrk").read_bytes()
    assert header.split(b"Codepage=", 1)[1].split()[0] == b"ANSI", _why_not_converted(raw / "rec.vhdr")
    text, marks = header.decode("cp1252"), marker.decode("cp1252")
    assert "Ch1=Fp1,,0.1,µV" in text.splitlines()
    assert b"\xc2\xb5" not in header and "Codepage=ANSI" in marks
    assert "Müller" not in text and "1980" not in text
    assert "Impedance [kOhm] at 00:00:00 :" in text
    assert "Größe ändern" in marks and "20210824" not in marks
    annotations = mne_read_raw_brainvision(vhdr, verbose="error").annotations.description
    assert "Comment/Größe ändern" in list(annotations)


@pytest.mark.parametrize("strip", [False, True], ids=["as-is", "strip"])
def test_ansi_recording_is_copied_the_same_with_the_codecs_of_linux(tmp_path: Path, strip: bool) -> None:
    """CI ubuntu-24.04: Python knows no codec "ANSI" there (on Windows it is mbcs, the system's ANSI code
    page), so MNE-BIDS could not copy a Codepage=ANSI recording and NeuroGrid wrote it from the loaded data
    (float32, Codepage=UTF-8), while Windows copied it. Simulated: the codec registry and the locale encoding
    of the Linux runner. The recording is copied with its bytes there too, to the same files (TECH-05)."""
    with linux_text_system(), pytest.raises(LookupError):
        codecs.lookup("ANSI")  # as on the runner: "LookupError: unknown encoding: ANSI"
    trees = {}
    for system, simulated in (("native", contextlib.nullcontext), ("Linux", linux_text_system)):
        base = tmp_path / system
        _ansi_brainvision(base / "raw")
        _write_config(base / "raw", METADATA + _row("rec.vhdr", "01"))
        with simulated():
            summary = pipeline.run_convert(
                base / "raw", base / "bids", strip_identifying_headers=strip, work_base=base
            )
        assert (summary.converted, summary.validator_errors, summary.exit_code) == (1, 0, 0), system
        trees[system] = _tree(base / "bids")
        eeg = base / "bids" / "sub-01" / "eeg"
        assert (eeg / "sub-01_task-rest_eeg.eeg").read_bytes() == (base / "raw" / "rec.eeg").read_bytes()
        # MNE-BIDS writes the copy in text mode, with the line ends of the system
        written = (eeg / "sub-01_task-rest_eeg.vhdr").read_bytes().replace(b"\r\n", b"\n")
        assert b"\nCodepage=ANSI\n" in written and b"\nCh1=Fp1,,0.1,\xb5V\n" in written, system
        if not strip:  # the copy changes the references only
            lines = zip(
                (base / "raw" / "rec.vhdr").read_bytes().split(b"\n"), written.split(b"\n"), strict=True
            )
            assert [(old, new) for old, new in lines if old != new] == [
                (b"DataFile=rec.eeg", b"DataFile=sub-01_task-rest_eeg.eeg"),
                (b"MarkerFile=rec.vmrk", b"MarkerFile=sub-01_task-rest_eeg.vmrk"),
            ], system
    assert trees["Linux"] == trees["native"]


def test_copy_codec_of_mne_bids_holds_for_threads_that_leave_out_of_order(tmp_path: Path) -> None:
    """The patch of MNE-BIDS's module is one for the whole process. Thread A enters, then B; A leaves first.
    Before, A's exit took the patch away while B still wrote (B's copy would read ANSI as the system's code
    page again, LookupError on Linux), and B's exit put A's replacement back for good."""
    from mne_bids import copyfiles

    from neurogrid.convert import _copy_codec_for_mne_bids

    _ansi_brainvision(tmp_path / "raw")
    vhdr = tmp_path / "raw" / "rec.vhdr"
    original = copyfiles._get_brainvision_encoding
    assert original(vhdr) == "ANSI"
    inside = leave_out_of_order(_copy_codec_for_mne_bids, lambda: copyfiles._get_brainvision_encoding(vhdr))
    assert inside == "latin-1", "B copies without the patch"
    assert copyfiles._get_brainvision_encoding is original, "the patch outlived the last block"


def test_strip_cuts_comment_lines_as_the_header_parser_counts_them(tmp_path: Path) -> None:
    """A Latin-1 header whose comment holds U+0085 (a line break for Python's str.splitlines) after an
    impedance value: the name behind it is not part of the impedance block and is removed."""
    head = (
        b"Brain Vision Data Exchange Header File Version 1.0\r\n\r\n[Common Infos]\r\nCodepage=ANSI\r\n"
        b"DataFile=x.eeg\r\nMarkerFile=x.vmrk\r\nDataFormat=BINARY\r\nNumberOfChannels=2\r\n"
        b"SamplingInterval=2000\r\n\r\n[Binary Infos]\r\nBinaryFormat=INT_16\r\n\r\n[Channel Infos]\r\n"
        b"Ch1=Fp1,,0.1,\xb5V\r\nCh2=Fp2,,0.1,\xb5V\r\n\r\n"
    )
    comment = b"[Comment]\r\nImpedance [kOhm] at 10:00:00 :\r\nFp1: 5\x85Zhang San\r\nFp2: 4\r\nRoom 12\r\n"
    vhdr = tmp_path / "x.vhdr"
    vhdr.write_bytes(head + comment)
    _strip_brainvision(vhdr)
    stripped = vhdr.read_bytes()
    assert stripped.startswith(head)  # everything outside the comment is byte for byte the same
    assert stripped[len(head) :] == b"[Comment]\r\nImpedance [kOhm] at 10:00:00 :\r\nFp1: 5\x85"
    assert b"Zhang" not in stripped and b"Room" not in stripped


def test_strip_keeps_a_chinese_ansi_header_in_its_encoding(tmp_path: Path) -> None:
    """A GBK header (Chinese Windows, Codepage=ANSI) is not re-encoded: only the comment lines go."""
    head = (
        "Brain Vision Data Exchange Header File Version 1.0\n; 脑电记录 中文说明\n\n[Common Infos]\n"
        "Codepage=ANSI\nDataFile=x.eeg\nMarkerFile=x.vmrk\nDataFormat=BINARY\nNumberOfChannels=1\n"
        "SamplingInterval=2000\n\n[Binary Infos]\nBinaryFormat=INT_16\n\n[Channel Infos]\nCh1=C3,,0.1,uV\n\n"
    ).encode("gbk")
    comment = "[Comment]\n患者：张三\nImpedance [kOhm] at 10:00:00 :\nC3: 5\n".encode("gbk")
    vhdr = tmp_path / "x.vhdr"
    vhdr.write_bytes(head + comment)
    _strip_brainvision(vhdr)
    assert vhdr.read_bytes() == head + b"[Comment]\nImpedance [kOhm] at 10:00:00 :\nC3: 5\n"


# --- positions, channels.tsv, hashes, reasons --------------------------------------------------------------


def test_brainvision_template_coordinates_are_not_written(tmp_path: Path) -> None:
    """[Coordinates] with radius 1 are an idealized cap; they are no measured CapTrak positions (A-05)."""
    raw = tmp_path / "raw"
    _copy_folder(FIX / "brainvision_ok", raw)
    coordinates = {"Fp1": (-90, -72), "Fp2": (90, 72), "F3": (-60, -51), "F4": (60, 51)}
    coordinates |= {"C3": (-45, 0), "C4": (45, 0), "O1": (-90, 72), "O2": (90, -72)}
    section = "[Coordinates]\n" + "".join(
        f"Ch{index}=1,{theta},{phi}\n" for index, (theta, phi) in enumerate(coordinates.values(), start=1)
    )
    header = (raw / "rec.vhdr").read_text(encoding="utf-8").replace("[Comment]", section + "\n[Comment]")
    (raw / "rec.vhdr").write_bytes(header.encode("utf-8"))
    _write_config(raw, METADATA + _row("rec.vhdr", "01"))
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, work_base=tmp_path)
    assert (summary.converted, summary.validator_errors) == (1, 0)
    assert list(out.rglob("*_electrodes.tsv")) == [] and list(out.rglob("*_coordsystem.json")) == []


def _edf(path: Path, signals: tuple[tuple[str, str, str, int], ...], records: int = 4) -> None:
    """A plain EDF file with one record per second and its own unit, prefilter text and rate per signal."""
    count = len(signals)
    header = bytearray()
    header += b"0".ljust(8) + b"X".ljust(80) + b"X".ljust(80) + b"01.01.85" + b"00.00.00"
    header += str(256 * (count + 1)).encode().ljust(8) + b"".ljust(44)
    header += str(records).encode().ljust(8) + b"1".ljust(8) + str(count).encode().ljust(4)
    header += b"".join(label.encode().ljust(16) for label, _unit, _filter, _rate in signals)
    header += b"".ljust(80) * count
    header += b"".join(unit.encode().ljust(8) for _label, unit, _filter, _rate in signals)
    header += b"-500".ljust(8) * count + b"500".ljust(8) * count
    header += b"-32768".ljust(8) * count + b"32767".ljust(8) * count
    header += b"".join(prefilter.encode().ljust(80) for _label, _unit, prefilter, _rate in signals)
    header += b"".join(str(rate).encode().ljust(8) for _label, _unit, _filter, rate in signals)
    header += b"".ljust(32) * count
    rng = np.random.default_rng(5)
    body = b"".join(
        rng.integers(-1000, 1000, rate).astype("<i2").tobytes()
        for _record in range(records)
        for _label, _unit, _filter, rate in signals
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(header) + body)


def test_edf_channels_tsv_takes_rate_unit_and_filters_per_channel(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _edf(
        raw / "psg.edf",
        (
            ("EEG Fz", "uV", "HP:0.2Hz LP:35.0Hz", 256),
            ("EMG chin", "uV", "HP:10Hz LP:100Hz", 128),
            ("SaO2", "%", "", 4),
            ("Resp chest", "mV", "HP:DC LP:5Hz", 32),
        ),
    )
    _write_config(raw, METADATA + _row("psg.edf", "01", "sleep"))
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, work_base=tmp_path)
    assert (summary.converted, summary.skipped, summary.validator_errors) == (1, [], 0)
    rows = _tsv(out / "sub-01" / "eeg" / "sub-01_task-sleep_channels.tsv")
    columns = ("name", "units", "sampling_frequency", "low_cutoff", "high_cutoff")
    assert [tuple(row[column] for column in columns) for row in rows] == [
        ("EEG Fz", "µV", "256.0", "0.2", "35.0"),
        ("EMG chin", "µV", "128.0", "10.0", "100.0"),
        ("SaO2", "%", "4.0", "n/a", "n/a"),
        ("Resp chest", "mV", "32.0", "0.0", "5.0"),
    ]


def test_edf_channels_tsv_reads_units_as_real_files_write_them(tmp_path: Path) -> None:
    """EDF allows ASCII only, but files write "µV" in Latin-1 (b"\\xb5V") or UTF-8 and pad with NUL bytes;
    the unit is read as such files mean it, never as replacement characters or with NULs (A-04)."""
    raw = tmp_path / "raw"
    units = (b"\xb5V", b"\xc2\xb5V", b"\xb0C", b"mV\x00\x00\x00\x00\x00\x00")
    signals = tuple((f"EEG E{index}", "uV", "", 256) for index in range(len(units)))
    _edf(raw / "u.edf", signals)
    data = bytearray((raw / "u.edf").read_bytes())
    start = 256 + len(units) * (16 + 80)  # the unit fields follow the labels and the transducer fields
    for index, unit in enumerate(units):
        data[start + 8 * index : start + 8 * (index + 1)] = unit.ljust(8)
    (raw / "u.edf").write_bytes(bytes(data))
    _write_config(raw, METADATA + _row("u.edf", "01"))
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, work_base=tmp_path)
    assert (summary.converted, summary.skipped, summary.validator_errors) == (1, [], 0)
    rows = _tsv(out / "sub-01" / "eeg" / "sub-01_task-rest_channels.tsv")
    assert [row["units"] for row in rows] == ["µV", "µV", "°C", "mV"]


def test_hashes_cover_the_data_files(tmp_path: Path) -> None:
    """Two BrainVision recordings that differ only in their .eeg samples get different hashes (DM-07)."""
    steps = []
    for name, flip in (("a", False), ("b", True)):
        raw = tmp_path / name / "raw"
        _copy_folder(FIX / "brainvision_ok", raw)
        if flip:
            data = bytearray((raw / "rec.eeg").read_bytes())
            (raw / "rec.eeg").write_bytes(bytes(byte ^ 0x55 for byte in data))
        _write_config(raw, METADATA + _row("rec.vhdr", "01"))
        out = tmp_path / name / "bids"
        assert pipeline.run_convert(raw, out, work_base=tmp_path / name).converted == 1
        [step] = _json(out / ".neurogrid" / "processing_steps.json")
        written = out / "sub-01" / "eeg" / "sub-01_task-rest_eeg.vhdr"
        assert step["input_hash"] == _files_hash([raw / f"rec.{ext}" for ext in ("vhdr", "eeg", "vmrk")])
        assert step["output_hash"] == _files_hash(
            [written.with_suffix(f".{ext}") for ext in ("vhdr", "eeg", "vmrk")]
        )
        steps.append(step)
    assert steps[0]["input_hash"] != steps[1]["input_hash"]
    assert steps[0]["output_hash"] != steps[1]["output_hash"]


def test_hash_of_a_split_fif_covers_every_part(tmp_path: Path) -> None:
    import mne

    raw = tmp_path / "raw"
    raw.mkdir()
    info = mne.create_info([f"E{index}" for index in range(8)], 1000.0, "eeg", verbose="error")
    data = np.random.default_rng(7).normal(0.0, 1e-5, (8, 200_000))
    mne.io.RawArray(data, info, verbose="error").save(raw / "rec_raw.fif", split_size="5MB", verbose="error")
    parts = sorted(raw.glob("*.fif"))
    assert [p.name for p in parts] == ["rec_raw-1.fif", "rec_raw.fif"]  # precondition: a split file
    _write_config(raw, METADATA + _row("rec_raw.fif", "01"))
    out = tmp_path / "bids"
    assert pipeline.run_convert(raw, out, work_base=tmp_path).converted == 1
    [step] = _json(out / ".neurogrid" / "processing_steps.json")
    assert step["input_hash"] == _files_hash(parts)


def test_orphan_companions_keep_their_reason(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    raw = tmp_path / "raw"
    _copy_folder(FIX / "orphan", raw)
    _write_config(raw, METADATA + _row("rec_ok.edf", "01"))
    summary = pipeline.run_convert(raw, tmp_path / "bids", work_base=tmp_path)
    assert summary.converted == 1
    assert summary.skipped == [(_pseudo("lonely.fdt"), "format.orphan_companion")]
    code, stdout, _stderr = _run(["scan", str(raw)], capsys)
    assert code == 0
    assert f"    - {_pseudo('lonely.fdt')} (FDT) – Data file without a header that refers to it" in stdout


def test_software_filters_written_as_na_promise_no_m02_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """n/a documents SoftwareFilters in BIDS (A-03); the console does not send the reader to M02 for it."""
    out = tmp_path / "bids"
    summary = pipeline.ConvertSummary(
        converted=2,
        skipped=[],
        missing_fields={"EEGReference": 1, "SoftwareFilters": 2},
        name_missing=False,
        validator_errors=0,
        validator_warnings=0,
        steps_file=out / ".neurogrid" / "processing_steps.json",
    )
    monkeypatch.setattr(pipeline, "run_convert", lambda *args, **kwargs: summary)
    (tmp_path / "raw").mkdir()
    code, stdout, _stderr = _run(
        ["convert", str(tmp_path / "raw"), "--to", "bids", "--out", str(out)], capsys
    )
    assert code == 0
    lines = stdout.splitlines()
    assert lines[1] == "Not documented, written as n/a: EEGReference (1 recording(s)); see M02 in 'check'."
    assert lines[2] == (
        "Not documented, written as n/a: SoftwareFilters (2 recording(s)); BIDS accepts n/a for this field, "
        "so 'check' does not report it."
    )


def test_identifying_strip_works_on_a_gen_fixtures_header(tmp_path: Path) -> None:
    """The written header of a UTF-8 recording keeps every line outside the comment unchanged."""
    raw = tmp_path / "raw"
    gen_fixtures.write_brainvision(raw / "bv.vhdr", seed=12, impedances=gen_fixtures.IMPEDANCES_OK)
    _write_config(raw, METADATA + _row("bv.vhdr", "01"))
    out = tmp_path / "bids"
    pipeline.run_convert(raw, out, strip_identifying_headers=True, work_base=tmp_path)
    written = (out / "sub-01" / "eeg" / "sub-01_task-rest_eeg.vhdr").read_text(encoding="utf-8")
    source = (raw / "bv.vhdr").read_text(encoding="utf-8")
    before = [
        line
        for line in source.split("[Comment]")[0].splitlines()
        if not line.startswith(("DataFile", "MarkerFile"))
    ]
    after = [
        line
        for line in written.split("[Comment]")[0].splitlines()
        if not line.startswith(("DataFile", "MarkerFile"))
    ]
    assert after == before
