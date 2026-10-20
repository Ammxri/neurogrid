"""Review P2, EEGLAB adapter: a MAT v7.3 (HDF5) data set never makes a reader leave the file, declared and
expanded sizes count against the 4 GB limit, data sets without channel locations keep their channels under
MNE's default names, and one-channel or one-epoch embedded data match the header (A-52, A-77, NG-F01, M01).

Covers neurogrid.io.eeglab: the whole-file HDF5 check before pymatreader or MNE (external links, external
storage, virtual datasets, soft links, cycles, references, variable-length data), header-only loading of
embedded data, characters and empty-array dimensions at what a reader spends on them, the expanded size of
compressed MAT v5 variables, default channels and the recording rate, and the embedded data shape.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from neurogrid import pipeline
from neurogrid.io import eeglab
from neurogrid.io.base import HeaderUnreadable
from neurogrid.io.discover import scan
from neurogrid.io.eeglab import EeglabAdapter, _load, epoched, referenced_fdt
from neurogrid.kernel.findings import Status

AS_OF = date(2026, 10, 11)
MAT73_HEADER = b"MATLAB 7.3 MAT-file, written by NeuroGrid tests".ljust(116) + b"\x00" * 8 + b"\x00\x02IM"


# --- writers ----------------------------------------------------------------------------------------------


def _write_v5(
    path: Path,
    *,
    nbchan: int = 4,
    pnts: int = 256,
    srate: float = 128.0,
    trials: int = 1,
    labels: tuple[str, ...] | None = None,
    types: tuple[str, ...] | None = None,
    data: Any = None,
    compress: bool = False,
    header: dict[str, Any] | None = None,
) -> Path:
    """A MATLAB v5 EEGLAB data set with embedded data; ``labels`` None means EEG.chanlocs = [] (as EEGLAB has
    it after importing a plain matrix). ``header`` overrides EEG fields after the data were made."""
    import scipy.io

    empty = np.array([])
    samples = np.random.default_rng(0).normal(0.0, 5.0, (nbchan, pnts * trials)).astype("<f4")
    if trials > 1:
        samples = samples.reshape(nbchan, pnts, trials, order="F")
    chanlocs: Any = empty
    if labels is not None:
        chanlocs = np.zeros((1, len(labels)), dtype=[(key, "O") for key in ("labels", "type", "X", "Y", "Z")])
        for index, label in enumerate(labels):
            chanlocs[0, index] = (label, types[index] if types else "EEG", empty, empty, empty)
    eeg: dict[str, Any] = {
        "setname": "",
        "filename": path.name,
        "filepath": "",
        "subject": "",
        "comments": "",
        "history": "",
        "nbchan": float(nbchan),
        "trials": float(trials),
        "pnts": float(pnts),
        "srate": srate,
        "xmin": 0.0,
        "xmax": (pnts - 1) / srate,
        "times": empty,
        "data": samples if data is None else data,
        "chanlocs": chanlocs,
        "event": empty,
        "epoch": empty,
        "ref": "common",
        "chaninfo": {"plotrad": empty, "shrink": empty, "nosedir": "+X"},
    }
    eeg.update(header or {})
    path.parent.mkdir(parents=True, exist_ok=True)
    scipy.io.savemat(path, {"EEG": eeg}, appendmat=False, format="5", oned_as="row", do_compression=compress)
    return path


def _number(group: Any, name: str, value: float) -> Any:
    dataset = group.create_dataset(name, data=np.array([[value]], dtype="<f8"))
    dataset.attrs["MATLAB_class"] = np.bytes_(b"double")
    return dataset


def _write_v73(
    path: Path,
    *,
    nbchan: int = 2,
    pnts: int = 100,
    srate: float | None = 512.0,
    data: str | None = None,
    declared: tuple[int, ...] | None = None,
    build: Callable[[Any, Any, Any], None] | None = None,
    header: bytes = MAT73_HEADER,
) -> Path:
    """A MATLAB v7.3 EEGLAB data set without channel locations, written with h5py in MATLAB's layout.

    Embedded float32 samples (HDF5 order pnts x nbchan) unless ``data`` names a .fdt; ``declared`` gives the
    embedded dataset a declared HDF5 shape whose chunks are never written (a few kB on disk). ``srate`` None
    leaves the field to ``build(file, EEG group, #refs# group)``, which adds whatever the test needs.
    """
    import h5py

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w", userblock_size=512) as handle:
        refs = handle.create_group("#refs#")
        eeg = handle.create_group("EEG")
        eeg.attrs["MATLAB_class"] = np.bytes_(b"struct")
        for key, value in (("nbchan", nbchan), ("pnts", pnts), ("trials", 1)):
            _number(eeg, key, float(value))
        if srate is not None:
            _number(eeg, "srate", srate)
        empty = eeg.create_dataset("chanlocs", data=np.zeros(2, dtype="<u8"))
        empty.attrs["MATLAB_class"] = np.bytes_(b"struct")
        empty.attrs["MATLAB_empty"] = np.uint8(1)
        if data is not None:
            text = eeg.create_dataset("data", data=np.array([[ord(ch)] for ch in data], dtype="<u2"))
            text.attrs["MATLAB_class"] = np.bytes_(b"char")
        elif declared is not None:
            samples = eeg.create_dataset(
                "data", shape=declared, dtype="<f4", chunks=(min(declared[0], 65536), *declared[1:])
            )
            samples.attrs["MATLAB_class"] = np.bytes_(b"single")
        else:
            values = np.random.default_rng(1).normal(0.0, 5.0, (pnts, nbchan)).astype("<f4")
            samples = eeg.create_dataset("data", data=values)
            samples.attrs["MATLAB_class"] = np.bytes_(b"single")
        if build is not None:
            build(handle, eeg, refs)
    with path.open("r+b") as raw:
        raw.write(header)
    return path


def _outside_h5(folder: Path, value: float = 512.0) -> Path:
    import h5py

    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "secret.h5"
    with h5py.File(target, "w") as handle:
        _number(handle, "srate", value)
    return target


@pytest.fixture
def mne_calls(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Records every MNE EEGLAB reader call; a refused file must never reach MNE (A-52, A-77)."""
    import mne

    calls: list[Path] = []

    def fake(path: Path, **kwargs: Any) -> Any:
        calls.append(Path(path))
        raise AssertionError("MNE must not open this file")

    monkeypatch.setattr(mne.io, "read_raw_eeglab", fake)
    monkeypatch.setattr(mne, "read_epochs_eeglab", fake)
    return calls


def _assert_refused(path: Path, reason: str, error_type: str, mne_calls: list[Path]) -> None:
    adapter = EeglabAdapter()
    for call in (adapter.inspect, lambda p: adapter.read(p, recording_id="r", relative_path=p.name)):
        with pytest.raises(HeaderUnreadable) as info:
            call(path)
        assert info.value.reason == reason
    assert adapter.read_check(path) == error_type
    assert referenced_fdt(path) is None and epoched(path) is False
    assert mne_calls == []


# --- 1. HDF5 references to other files ----------------------------------------------------------------------


def test_v73_external_link_is_refused_and_never_followed(tmp_path: Path, mne_calls: list[Path]) -> None:
    """Reviewer case (sk/h5_make.py): EEG/srate is an external link to an absolute outside path."""
    import h5py

    secret = _outside_h5(tmp_path / "OUTSIDE_Z")
    path = _write_v73(
        tmp_path / "ds" / "rec.set",
        srate=None,
        build=lambda f, eeg, refs: eeg.__setitem__("srate", h5py.ExternalLink(str(secret), "/srate")),
    )
    _assert_refused(path, "header.external_reference", "UnsafePathError", mne_calls)
    # the link is classified, not resolved: a dangling target gives the same answer
    secret.unlink()
    _assert_refused(path, "header.external_reference", "UnsafePathError", mne_calls)


@pytest.mark.parametrize("target", ["relative.h5", "../OUTSIDE/x.h5", "\\\\server\\share\\x.h5"])
def test_v73_external_link_anywhere_in_the_file(tmp_path: Path, target: str, mne_calls: list[Path]) -> None:
    """MNE's pymatreader reads every variable, so a link outside EEG counts as well."""
    import h5py

    def build(handle: Any, eeg: Any, refs: Any) -> None:
        etc = handle.create_group("etc")
        etc.attrs["MATLAB_class"] = np.bytes_(b"struct")
        etc["x"] = h5py.ExternalLink(target, "/x")

    path = _write_v73(tmp_path / "rec.set", build=build)
    _assert_refused(path, "header.external_reference", "UnsafePathError", mne_calls)


def test_v73_external_link_reached_through_a_reference(tmp_path: Path, mne_calls: list[Path]) -> None:
    """pymatreader skips '#refs#' as a field but follows object references into it (MATLAB cells, structs)."""
    import h5py

    secret = _outside_h5(tmp_path / "outside")

    def build(handle: Any, eeg: Any, refs: Any) -> None:
        hidden = refs.create_group("hidden")
        hidden.attrs["MATLAB_class"] = np.bytes_(b"struct")
        hidden["x"] = h5py.ExternalLink(str(secret), "/srate")
        cell = eeg.create_dataset("etc", data=np.array([[hidden.ref]], dtype=h5py.ref_dtype))
        cell.attrs["MATLAB_class"] = np.bytes_(b"cell")

    path = _write_v73(tmp_path / "ds" / "rec.set", build=build)
    _assert_refused(path, "header.external_reference", "UnsafePathError", mne_calls)


def test_v73_external_storage_and_virtual_datasets_are_refused(tmp_path: Path, mne_calls: list[Path]) -> None:
    import h5py

    outside = tmp_path / "outside"
    secret = _outside_h5(outside)
    raw = outside / "raw.bin"
    raw.write_bytes(np.array([512.0], dtype="<f8").tobytes())

    def external(handle: Any, eeg: Any, refs: Any) -> None:
        dataset = eeg.create_dataset("srate", shape=(1, 1), dtype="<f8", external=[(str(raw), 0, 8)])
        dataset.attrs["MATLAB_class"] = np.bytes_(b"double")

    def virtual(handle: Any, eeg: Any, refs: Any) -> None:
        layout = h5py.VirtualLayout(shape=(1, 1), dtype="<f8")
        layout[:] = h5py.VirtualSource(str(secret), "srate", shape=(1, 1))
        dataset = eeg.create_virtual_dataset("srate", layout, fillvalue=0.0)
        dataset.attrs["MATLAB_class"] = np.bytes_(b"double")

    for name, build in (("external", external), ("virtual", virtual)):
        path = _write_v73(tmp_path / name / "rec.set", srate=None, build=build)
        _assert_refused(path, "header.external_reference", "UnsafePathError", mne_calls)


def test_v73_file_that_also_looks_like_mat_v5_is_checked_as_hdf5(
    tmp_path: Path, mne_calls: list[Path]
) -> None:
    """A v5 header in front of an HDF5 file: pymatreader falls back to HDF5 when scipy gives up."""
    import h5py

    secret = _outside_h5(tmp_path / "outside")
    v5_header = b"MATLAB 5.0 MAT-file".ljust(116) + b"\x00" * 8 + b"\x00\x01IM"
    path = _write_v73(
        tmp_path / "ds" / "rec.set",
        srate=None,
        header=v5_header,
        build=lambda f, eeg, refs: eeg.__setitem__("srate", h5py.ExternalLink(str(secret), "/srate")),
    )
    _assert_refused(path, "header.external_reference", "UnsafePathError", mne_calls)


@pytest.mark.parametrize("case", ["soft_link", "cycle", "variable_length_text"])
def test_v73_structures_matlab_never_writes_are_refused(
    tmp_path: Path, case: str, mne_calls: list[Path]
) -> None:
    """Soft links may lead through external links, cycles never end, and variable-length texts are taken as
    paths by pymatreader; none of them is followed and MNE is not asked either."""
    import h5py

    def build(handle: Any, eeg: Any, refs: Any) -> None:
        if case == "soft_link":
            _number(refs, "s", 512.0)
            eeg["srate"] = h5py.SoftLink("/#refs#/s")
            return
        _number(eeg, "srate", 512.0)
        if case == "cycle":
            loop = refs.create_group("loop")
            loop.create_dataset("self", data=np.array([[loop.ref]], dtype=h5py.ref_dtype))
        else:
            eeg.create_dataset("setname", data="/EEG/data", dtype=h5py.string_dtype())

    path = _write_v73(tmp_path / "rec.set", srate=None, build=build)
    _assert_refused(path, "header.unreadable_container", "HeaderUnreadable", mne_calls)


def test_v73_regular_file_still_reads(tmp_path: Path) -> None:
    """The check does not refuse what MATLAB writes (struct fields, #refs#, references, a .fdt name)."""
    import h5py

    def build(handle: Any, eeg: Any, refs: Any) -> None:
        _number(refs, "a", 1.0)
        cell = eeg.create_dataset(
            "etc", data=np.array([[refs["a"].ref], [refs["a"].ref]], dtype=h5py.ref_dtype)
        )
        cell.attrs["MATLAB_class"] = np.bytes_(b"cell")

    path = _write_v73(tmp_path / "rec.set", data="rec.fdt", build=build)
    (tmp_path / "rec.fdt").write_bytes(np.zeros((100, 2), dtype="<f4").tobytes())
    adapter = EeglabAdapter()
    recording = adapter.read(path, recording_id="r", relative_path="rec.set")
    assert recording.streamable and recording.sampling_rate_hz == 512.0
    assert adapter.inspect(path).issues == ()
    assert referenced_fdt(path) == "rec.fdt"
    assert adapter.read_check(path) is None


# --- 2. sizes ---------------------------------------------------------------------------------------------


def test_v73_declared_size_counts_against_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mne_calls: list[Path]
) -> None:
    """Reviewer case (sk/h5_fill.py): a 6 kB file declaring 2,000,000 x 64 float32 samples (512 MB)."""
    path = _write_v73(tmp_path / "rec.set", nbchan=64, pnts=2_000_000, declared=(2_000_000, 64))
    assert path.stat().st_size < 50_000
    monkeypatch.setattr(eeglab, "MAX_SET_BYTES", 100_000_000)
    _assert_refused(path, "header.too_large", "HeaderUnreadable", mne_calls)


def test_v73_embedded_samples_are_never_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Within the limit, the header-only paths describe embedded data by their shape and never read them."""
    import pymatreader.utils

    path = _write_v73(tmp_path / "rec.set", nbchan=64, pnts=2_000_000, declared=(2_000_000, 64))
    read: list[str] = []
    original = pymatreader.utils._handle_hdf5_dataset

    def recording(node: Any) -> Any:
        read.append(node.name)
        return original(node)

    monkeypatch.setattr(pymatreader.utils, "_handle_hdf5_dataset", recording)
    adapter = EeglabAdapter()
    eeg = _load(path)
    assert eeg["data"].shape == (64, 2_000_000)
    assert adapter.inspect(path).issues == ()
    recording_model = adapter.read(path, recording_id="r", relative_path="rec.set")
    assert recording_model.streamable is False and recording_model.duration_s == 2_000_000 / 512
    assert epoched(path) is False and referenced_fdt(path) is None
    assert "/EEG/data" not in read and "/EEG/nbchan" in read


def test_v73_repeated_references_count_each_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mne_calls: list[Path]
) -> None:
    """One declared 4 MB dataset referenced 50 times is loaded 50 times by pymatreader."""
    import h5py

    def build(handle: Any, eeg: Any, refs: Any) -> None:
        big = refs.create_dataset("big", shape=(1_000_000,), dtype="<f4", chunks=(65536,))
        big.attrs["MATLAB_class"] = np.bytes_(b"single")
        cell = eeg.create_dataset("etc", data=np.array([[big.ref]] * 50, dtype=h5py.ref_dtype))
        cell.attrs["MATLAB_class"] = np.bytes_(b"cell")

    path = _write_v73(tmp_path / "rec.set", build=build)
    monkeypatch.setattr(eeglab, "MAX_SET_BYTES", 40_000_000)  # holds one copy, not fifty
    _assert_refused(path, "header.too_large", "HeaderUnreadable", mne_calls)


def test_v73_characters_count_as_python_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mne_calls: list[Path]
) -> None:
    """pymatreader joins a text from one Python string per character: a declared 2-byte character costs
    about 80 bytes when read, also in NeuroGrid's own header load (EEG.history here, never written)."""

    def build(handle: Any, eeg: Any, refs: Any) -> None:
        history = eeg.create_dataset(
            "history", shape=(1_000_000, 1), dtype="<u2", chunks=(65536, 1), fillvalue=0x4E00
        )
        history.attrs["MATLAB_class"] = np.bytes_(b"char")

    path = _write_v73(tmp_path / "rec.set", build=build)
    assert path.stat().st_size < 50_000
    monkeypatch.setattr(eeglab, "MAX_SET_BYTES", 20_000_000)  # holds the declared 2 MB, not 1,000,000 texts
    _assert_refused(path, "header.too_large", "HeaderUnreadable", mne_calls)


def test_v73_matlab_empty_dimensions_count_as_python_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mne_calls: list[Path]
) -> None:
    """pymatreader.whosmat (called by MNE) turns the dimensions of an empty top-level variable into Python
    numbers; MATLAB writes two of them, this file declares a million."""

    def build(handle: Any, eeg: Any, refs: Any) -> None:
        empty = handle.create_dataset("icaact", shape=(1_000_000,), dtype="<u8", chunks=(65536,), fillvalue=7)
        empty.attrs["MATLAB_class"] = np.bytes_(b"double")
        empty.attrs["MATLAB_empty"] = np.uint8(1)

    path = _write_v73(tmp_path / "rec.set", build=build)
    monkeypatch.setattr(eeglab, "MAX_SET_BYTES", 50_000_000)  # holds the declared 8 MB
    _assert_refused(path, "header.too_large", "HeaderUnreadable", mne_calls)


@pytest.mark.parametrize("case", ["compound_vlen", "vlen_matlab_class"])
def test_v73_variable_length_data_anywhere_are_refused(
    tmp_path: Path, case: str, mne_calls: list[Path]
) -> None:
    """Variable-length elements may all point at one stored value, so the file size bounds nothing: a field
    of a compound type and the MATLAB_class attribute pymatreader reads count like variable-length texts."""
    import h5py

    def build(handle: Any, eeg: Any, refs: Any) -> None:
        if case == "compound_vlen":
            kind = np.dtype([("a", "<f8"), ("b", h5py.vlen_dtype(np.dtype("<f4")))])
            etc = eeg.create_dataset("etc", shape=(3,), dtype=kind)
            etc.attrs["MATLAB_class"] = np.bytes_(b"double")
        else:
            etc = eeg.create_dataset("etc", data=np.zeros((2, 2)))
            etc.attrs["MATLAB_class"] = "double"  # h5py stores a str as a variable-length text

    path = _write_v73(tmp_path / "rec.set", build=build)
    _assert_refused(path, "header.unreadable_container", "HeaderUnreadable", mne_calls)


def test_v5_compressed_variables_count_with_their_expanded_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mne_calls: list[Path]
) -> None:
    zeros = np.zeros((64, 200_000), dtype="<f4")
    path = _write_v5(tmp_path / "rec.set", compress=True, header={"icaact": zeros})
    assert path.stat().st_size < 1_000_000  # 51 MB of zeros, compressed
    assert EeglabAdapter().inspect(path).issues == ()  # within the default limit
    monkeypatch.setattr(eeglab, "MAX_SET_BYTES", 10_000_000)
    _assert_refused(path, "header.too_large", "HeaderUnreadable", mne_calls)


def test_epoch_count_counts_against_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mne_calls: list[Path]
) -> None:
    """MNE's epochs reader builds an event table for each declared epoch (48 bytes) before it compares the
    count with the data: a 2 kB file declaring 20,000,000 epochs made it allocate about 1 GB."""
    path = _write_v5(tmp_path / "rec.set", nbchan=1, pnts=4, labels=("Cz",), header={"trials": 1e6})
    assert EeglabAdapter().inspect(path).issues == ("header.data_shape",)  # 48 MB: within the default limit
    monkeypatch.setattr(eeglab, "MAX_SET_BYTES", 10_000_000)
    _assert_refused(path, "header.too_large", "HeaderUnreadable", mne_calls)
    fdt = _write_v5(
        tmp_path / "fdt" / "rec.set", nbchan=1, labels=("Cz",), data="rec.fdt", header={"trials": 1e6}
    )
    _assert_refused(fdt, "header.too_large", "HeaderUnreadable", mne_calls)
    few = _write_v5(tmp_path / "few.set", nbchan=1, pnts=4, labels=("Cz",), trials=3)
    assert epoched(few) is True and EeglabAdapter().inspect(few).issues == ()


def test_read_check_second_counts_against_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mne_calls: list[Path]
) -> None:
    """The read check reads the first and the last second through MNE, sized by srate and pnts from the header
    and not by the data: a 16-byte .fdt under pnts = srate = 1e8 made MNE allocate 800 MB per channel, and so
    did 4 embedded samples saved as top-level variables (MNE reads those lazily, too)."""
    import scipy.io

    labels = ("Fz", "Cz", "Pz", "Oz")
    header = {"pnts": 1e6, "srate": 1e6}
    fdt = _write_v5(tmp_path / "rec.set", nbchan=4, labels=labels, data="rec.fdt", header=header)
    (tmp_path / "rec.fdt").write_bytes(np.zeros(4, dtype="<f4").tobytes())
    content = scipy.io.loadmat(fdt, squeeze_me=False, struct_as_record=True)["EEG"]
    variables = {name: content[name][0, 0] for name in content.dtype.names}
    variables["data"] = np.zeros((4, 1), dtype="<f4")
    top_level = tmp_path / "top" / "rec.set"
    top_level.parent.mkdir()
    scipy.io.savemat(top_level, variables, format="5")
    assert _load(top_level)["data"].shape == (4,)
    fraction = _write_v5(
        tmp_path / "fraction.set",
        nbchan=4,
        labels=labels,
        data="rec.fdt",
        header={**header, "pnts": 1e6 + 0.5},
    )
    for path in (fdt, top_level, fraction):  # within the default limit
        assert EeglabAdapter().inspect(path).issues  # truncated, wrong shape, or pnts not a whole number
    monkeypatch.setattr(eeglab, "MAX_SET_BYTES", 10_000_000)  # 4 channels x 1e6 samples x 8 bytes = 32 MB
    for path in (fdt, top_level, fraction):  # MNE takes int(pnts) where NeuroGrid reports header.number_field
        _assert_refused(path, "header.too_large", "HeaderUnreadable", mne_calls)
    # a short recording at that rate is read for its length only
    short = _write_v5(tmp_path / "short.set", nbchan=4, labels=labels, data="rec.fdt", header={"srate": 1e6})
    assert EeglabAdapter().inspect(short).issues == ("header.file_truncated",)


def test_default_channel_count_is_taken_as_mne_takes_it(tmp_path: Path, mne_calls: list[Path]) -> None:
    """nbchan 300000.5 is header.number_field for NeuroGrid, but MNE names int(nbchan) = 300,000 channels
    (14 s, 300 MB); the limit on default channels counts what MNE makes of it."""
    path = _write_v5(tmp_path / "rec.set", nbchan=4, data="rec.fdt", header={"nbchan": 300_000.5})
    _assert_refused(path, "header.too_large", "HeaderUnreadable", mne_calls)
    within = _write_v5(tmp_path / "within.set", nbchan=4, data="within.fdt", header={"nbchan": 3.5})
    assert EeglabAdapter().inspect(within).issues == ("header.number_field",)


def test_sparse_data_count_with_their_dense_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mne_calls: list[Path]
) -> None:
    """EEG.data as a sparse matrix: MNE's raw reader allocates a dense float64 array of the declared shape,
    which costs the file a few bytes (v5) or one index per column (v7.3)."""
    import scipy.sparse

    v5 = _write_v5(tmp_path / "v5.set", data=scipy.sparse.csc_matrix((1000, 2000)), compress=True)
    assert v5.stat().st_size < 5_000

    def sparse(handle: Any, eeg: Any, refs: Any) -> None:
        del eeg["data"]
        group = eeg.create_group("data")
        group.attrs["MATLAB_class"] = np.bytes_(b"double")
        group.attrs["MATLAB_sparse"] = np.uint64(1000)
        group.create_dataset("jc", data=np.zeros(2001, dtype="<u8"))

    v73 = _write_v73(tmp_path / "v73.set", build=sparse)
    for path in (v5, v73):
        assert EeglabAdapter().inspect(path).issues == ("header.data_shape",)  # 16 MB: within the limit
    monkeypatch.setattr(eeglab, "MAX_SET_BYTES", 10_000_000)
    for path in (v5, v73):
        _assert_refused(path, "header.too_large", "HeaderUnreadable", mne_calls)


def test_file_size_limit_is_refused_before_mne(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mne_calls: list[Path]
) -> None:
    path = _write_v5(tmp_path / "rec.set")
    monkeypatch.setattr(eeglab, "MAX_SET_BYTES", 1000)
    _assert_refused(path, "header.too_large", "HeaderUnreadable", mne_calls)


def test_v5_header_load_keeps_only_header_fields(tmp_path: Path) -> None:
    path = _write_v5(tmp_path / "rec.set", compress=True)
    eeg = _load(path)
    assert "event" not in eeg and "chaninfo" not in eeg
    assert not isinstance(eeg["data"], np.ndarray) and eeg["data"].shape == (4, 256)


# --- 3. no channel locations ------------------------------------------------------------------------------


def test_data_set_without_chanlocs_has_mne_default_channels(tmp_path: Path) -> None:
    """Reviewer case (probe_eeglab2.py): nbchan 4, srate 512, chanlocs [] -> MNE reads 'EEG 000'.."""
    import mne

    path = _write_v5(tmp_path / "rec.set", nbchan=4, pnts=1024, srate=512.0)
    adapter = EeglabAdapter()
    recording = adapter.read(path, recording_id="r", relative_path="rec.set")
    raw = mne.io.read_raw_eeglab(path, preload=False, verbose="error")
    assert (
        [ch.name for ch in recording.channels] == raw.ch_names == ["EEG 000", "EEG 001", "EEG 002", "EEG 003"]
    )
    assert {(ch.type, ch.sampling_rate_hz, ch.position) for ch in recording.channels} == {
        ("EEG", 512.0, None)
    }
    assert set(raw.get_channel_types()) == {"eeg"}
    assert recording.sampling_rate_hz == 512.0 and recording.duration_s == 2.0
    assert recording.metadata_sources == {
        "channels": "header",
        "sampling_rate_hz": "header",
        "duration_s": "header",
    }
    assert adapter.inspect(path).issues == () and adapter.read_check(path) is None


def test_v73_data_set_without_chanlocs_has_default_channels(tmp_path: Path) -> None:
    path = _write_v73(tmp_path / "rec.set", nbchan=2, pnts=100)
    adapter = EeglabAdapter()
    recording = adapter.read(path, recording_id="r", relative_path="rec.set")
    assert [(ch.name, ch.type) for ch in recording.channels] == [("EEG 000", "EEG"), ("EEG 001", "EEG")]
    assert recording.sampling_rate_hz == 512.0 and recording.streamable is False
    assert adapter.inspect(path).issues == () and adapter.read_check(path) is None


def test_short_chanlocs_are_completed_and_reported(tmp_path: Path) -> None:
    """chanlocs with fewer entries than nbchan: the header issue stays, the model keeps nbchan channels."""
    path = _write_v5(tmp_path / "rec.set", nbchan=4, labels=("Fz", "Cz"))
    adapter = EeglabAdapter()
    recording = adapter.read(path, recording_id="r", relative_path="rec.set")
    assert [ch.name for ch in recording.channels] == ["Fz", "Cz", "EEG 002", "EEG 003"]
    assert adapter.inspect(path).issues == ("header.channel_count",)


def test_too_many_default_channels_are_refused(tmp_path: Path, mne_calls: list[Path]) -> None:
    """nbchan is only a header number: a few bytes must not create millions of channels (here or in MNE)."""
    path = _write_v5(tmp_path / "big.set", nbchan=4, data="big.fdt", header={"nbchan": 1e9})
    adapter = EeglabAdapter()
    with pytest.raises(HeaderUnreadable) as info:
        adapter.read(path, recording_id="r", relative_path="big.set")
    assert info.value.reason == "header.too_large"
    assert adapter.read_check(path) == "HeaderUnreadable" and mne_calls == []
    limit = eeglab.MAX_DEFAULT_CHANNELS
    path = _write_v5(tmp_path / "limit.set", nbchan=4, data="limit.fdt", header={"nbchan": float(limit)})
    recording = adapter.read(path, recording_id="r", relative_path="limit.set")
    assert len(recording.channels) == limit and recording.channels[-1].name == f"EEG {limit - 1:03d}"


def test_recording_rate_does_not_depend_on_channel_types(tmp_path: Path) -> None:
    path = _write_v5(tmp_path / "rec.set", nbchan=2, labels=("HEOG", "VEOG"), types=("EOG", "EOG"))
    recording = EeglabAdapter().read(path, recording_id="r", relative_path="rec.set")
    assert [ch.type for ch in recording.channels] == ["EOG", "EOG"]
    assert recording.sampling_rate_hz == 128.0


def test_check_counts_a_data_set_without_chanlocs_as_a_readable_recording(tmp_path: Path) -> None:
    """Reviewer case (repro_eeglab_nochanlocs.py): a readable recording, SamplingFrequency documented."""
    _write_v5(tmp_path / "data" / "rec.set", nbchan=8, pnts=2048, srate=512.0)
    results = pipeline.run_check(tmp_path / "data", pipeline.CheckOptions(as_of=AS_OF, work_base=tmp_path))
    (record,) = results.recordings
    assert (record.n_channels, record.n_eeg_channels, record.sampling_rate_hz) == (8, 8, 512.0)
    failed = {(f.rule_id, f.object, f.subkey) for f in results.findings if f.status is Status.FAILED}
    assert ("CORE-M01-01", "dataset", "readable_recordings") not in failed
    assert not any(rule == "CORE-M02-01" and subkey == "SamplingFrequency" for rule, _, subkey in failed)
    assert not any(
        subkey and subkey.startswith("channels.") for rule, _, subkey in failed if rule == "CORE-M02-01"
    )
    assert not any(rule in ("CORE-M01-01", "CORE-M01-02") for rule, _, _ in failed)


# --- 4. one channel or one epoch with embedded data -------------------------------------------------------


@pytest.mark.parametrize(
    ("nbchan", "pnts", "trials"),
    [(1, 2048, 1), (1, 256, 3), (3, 1, 1), (1, 1, 1), (2, 256, 1), (2, 128, 4)],
)
def test_embedded_data_with_singleton_axes_match_the_header(
    tmp_path: Path, nbchan: int, pnts: int, trials: int
) -> None:
    """Reviewer case (probe_eeglab.py, one_embedded): the reader removes singleton axes of the data."""
    path = _write_v5(
        tmp_path / "rec.set",
        nbchan=nbchan,
        pnts=pnts,
        trials=trials,
        labels=tuple(f"E{index}" for index in range(nbchan)),
    )
    assert EeglabAdapter().inspect(path).issues == ()


def test_one_channel_embedded_matches_mne_and_wrong_sizes_still_fail(tmp_path: Path) -> None:
    import gen_fixtures  # type: ignore[import-not-found,unused-ignore]

    one = tmp_path / "one" / "rec.set"
    one.parent.mkdir()
    gen_fixtures.write_eeglab(one, labels=("Cz",), embedded=True)
    adapter = EeglabAdapter()
    assert adapter.inspect(one).issues == () and adapter.read_check(one) is None
    for field, value in (("pnts", 255.0), ("trials", 2.0), ("nbchan", 2.0)):
        wrong = _write_v5(tmp_path / f"{field}.set", nbchan=1, labels=("Cz",), header={field: value})
        assert "header.data_shape" in adapter.inspect(wrong).issues
    swapped = _write_v5(
        tmp_path / "swapped.set", nbchan=2, pnts=3, labels=("Cz", "Pz"), data=np.zeros((3, 2))
    )
    assert adapter.inspect(swapped).issues == ("header.data_shape",)


@pytest.mark.parametrize(
    ("data", "issues"),
    [(None, ("header.data_shape",)), ({"x": 1.0}, ("header.data_shape",)), (np.float32(3.0), ())],
)
def test_one_sample_header_still_needs_numeric_data(
    tmp_path: Path, data: Any, issues: tuple[str, ...]
) -> None:
    """With nbchan = pnts = trials = 1 every axis is a singleton: missing or non-numeric data must still
    differ from the header, one number matches it."""
    path = tmp_path / "rec.set"
    _write_v5(path, nbchan=1, pnts=1, labels=("Cz",), data=data if data is not None else np.zeros((1, 1)))
    if data is None:  # the field left out entirely
        import scipy.io

        content = scipy.io.loadmat(path, squeeze_me=False, struct_as_record=True)["EEG"]
        fields = {name: content[name][0, 0] for name in content.dtype.names if name != "data"}
        scipy.io.savemat(path, {"EEG": fields}, format="5")
        assert "data" not in _load(path)
    assert EeglabAdapter().inspect(path).issues == issues


def test_v73_one_channel_embedded_matches_the_header(tmp_path: Path) -> None:
    path = _write_v73(tmp_path / "rec.set", nbchan=1, pnts=300)
    eeg = _load(path)
    assert eeg["data"].shape == (300,)
    assert EeglabAdapter().inspect(path).issues == ()


def test_one_channel_and_unlocated_data_sets_are_converted(tmp_path: Path) -> None:
    """Reviewer cases: both were skipped by convert before (data_shape issue, no channels)."""
    import gen_fixtures  # type: ignore[import-not-found,unused-ignore]
    from conftest import DOCUMENTED_TOML  # type: ignore[import-not-found,unused-ignore]

    raw = tmp_path / "raw"
    (raw / ".neurogrid").mkdir(parents=True)
    gen_fixtures.write_eeglab(raw / "one.set", labels=("Cz",), embedded=True)
    _write_v5(raw / "nolocs.set", nbchan=4, pnts=1024, srate=512.0)
    rows = "".join(
        f'\n[[convert.files]]\npath = "{name}"\nsubject = "{subject}"\ntask = "rest"\n'
        for name, subject in (("one.set", "01"), ("nolocs.set", "02"))
    )
    (raw / ".neurogrid" / "neurogrid.toml").write_text(DOCUMENTED_TOML + rows, encoding="utf-8")
    summary = pipeline.run_convert(raw, tmp_path / "bids", work_base=tmp_path)
    assert (summary.converted, summary.skipped) == (2, [])
    channels = tmp_path / "bids" / "sub-02" / "eeg" / "sub-02_task-rest_channels.tsv"
    names = [line.split("\t")[0] for line in channels.read_text(encoding="utf-8").splitlines()[1:]]
    assert names == ["EEG 000", "EEG 001", "EEG 002", "EEG 003"]


# --- 5. NeuroGrid checks the structure MNE reads ----------------------------------------------------------


def _outside_fdt(folder: Path) -> str:
    """A .fdt outside the data set; returns the relative name a header would use for it."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "x.fdt").write_bytes(np.ones((256, 2), dtype="<f4").tobytes())
    return f"../{folder.name}/x.fdt"


def _opens_under(folder: Path) -> Callable[[], list[str]]:
    """Records the Python-level opens of files under ``folder`` from now on (the audit hook stays installed,
    so it filters by folder; MNE opens a .fdt with open())."""
    import sys

    seen: list[str] = []
    marker = str(folder)

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event == "open" and args and isinstance(args[0], (str, Path)) and marker in str(args[0]):
            seen.append(str(args[0]))

    sys.addaudithook(hook)
    return lambda: list(seen)


def _assert_never_read_outside(path: Path, outside: Path, mne_calls: list[Path]) -> None:
    opened = _opens_under(outside)
    _assert_refused(path, "header.unreadable_container", "HeaderUnreadable", mne_calls)
    results = pipeline.run_check(
        path.parent, pipeline.CheckOptions(as_of=AS_OF, work_base=path.parent.parent)
    )
    failed = {(f.rule_id, f.object) for f in results.findings if f.status is Status.FAILED}
    assert ("CORE-M01-01", "dataset") in failed
    assert opened() == [] and mne_calls == []


def test_nested_eeg_structure_is_refused(tmp_path: Path, mne_calls: list[Path]) -> None:
    """EEG.EEG: MNE 1.13 reads the inner structure (whose EEG.data here names a .fdt outside the data set),
    MNE-BIDS copies by the outer one; NeuroGrid checked only the outer one before."""
    import scipy.io

    outside = tmp_path / "OUTSIDE"
    name = _outside_fdt(outside)
    v5 = _write_v5(tmp_path / "v5" / "rec.set", nbchan=2, labels=("Fz", "Cz"), data="rec.fdt")
    (v5.parent / "rec.fdt").write_bytes(np.zeros((256, 2), dtype="<f4").tobytes())
    content = scipy.io.loadmat(v5, squeeze_me=False, struct_as_record=True)["EEG"]
    outer = {key: content[key][0, 0] for key in content.dtype.names}
    outer["EEG"] = {**outer, "data": name}
    scipy.io.savemat(v5, {"EEG": outer}, appendmat=False, format="5", oned_as="row")
    _assert_never_read_outside(v5, outside, mne_calls)

    def nested(handle: Any, eeg: Any, refs: Any) -> None:
        inner = eeg.create_group("EEG")
        inner.attrs["MATLAB_class"] = np.bytes_(b"struct")
        for key, value in (("nbchan", 2.0), ("pnts", 256.0), ("trials", 1.0), ("srate", 128.0)):
            _number(inner, key, value)
        text = inner.create_dataset("data", data=np.array([[ord(ch)] for ch in name], dtype="<u2"))
        text.attrs["MATLAB_class"] = np.bytes_(b"char")

    v73 = _write_v73(tmp_path / "v73" / "rec.set", pnts=256, data="rec.fdt", build=nested)
    (v73.parent / "rec.fdt").write_bytes(np.zeros((256, 2), dtype="<f4").tobytes())
    _assert_never_read_outside(v73, outside, mne_calls)


def test_v73_data_or_eeg_in_a_cell_is_refused(tmp_path: Path, mne_calls: list[Path]) -> None:
    """pymatreader unwraps a one-element cell: EEG.data {'../x.fdt'} reached MNE as a .fdt name that the
    header-only load did not see (the earlier full load did), and EEG in a cell reached MNE unchecked."""
    import h5py

    outside = tmp_path / "OUTSIDE"
    name = _outside_fdt(outside)

    def text(group: Any, key: str) -> Any:
        node = group.create_dataset(key, data=np.array([[ord(ch)] for ch in name], dtype="<u2"))
        node.attrs["MATLAB_class"] = np.bytes_(b"char")
        return node

    def cell_data(handle: Any, eeg: Any, refs: Any) -> None:
        del eeg["data"]
        cell = eeg.create_dataset("data", data=np.array([[text(refs, "a").ref]], dtype=h5py.ref_dtype))
        cell.attrs["MATLAB_class"] = np.bytes_(b"cell")

    def cell_eeg(handle: Any, eeg: Any, refs: Any) -> None:
        del eeg["data"]
        text(eeg, "data")
        handle.move("EEG", "#refs#/e")
        cell = handle.create_dataset("EEG", data=np.array([[refs["e"].ref]], dtype=h5py.ref_dtype))
        cell.attrs["MATLAB_class"] = np.bytes_(b"cell")

    for case, build in (("data", cell_data), ("eeg", cell_eeg)):
        path = _write_v73(tmp_path / case / "rec.set", pnts=256, build=build)
        _assert_never_read_outside(path, outside, mne_calls)


def test_eeg_next_to_top_level_data_is_refused(tmp_path: Path, mne_calls: list[Path]) -> None:
    """With a numeric top-level 'data' variable MNE's raw reader takes the header from the top-level
    variables, while NeuroGrid (like MNE's epochs reader and MNE-BIDS) took EEG: the checks would not see
    MNE's header."""
    import scipy.io

    path = _write_v5(tmp_path / "ds" / "rec.set", nbchan=2, labels=("Fz", "Cz"))
    content = scipy.io.loadmat(path, squeeze_me=False, struct_as_record=True)["EEG"]
    eeg = {key: content[key][0, 0] for key in content.dtype.names}
    scipy.io.savemat(path, {"EEG": eeg, "data": np.zeros((2, 4), dtype="<f4")}, appendmat=False, format="5")
    _assert_refused(path, "header.unreadable_container", "HeaderUnreadable", mne_calls)


def test_v5_data_name_in_a_cell_still_goes_through_the_path_check(
    tmp_path: Path, mne_calls: list[Path]
) -> None:
    """MATLAB v5: scipy and pymatreader unwrap the cell the same way for NeuroGrid and MNE."""
    cell = np.empty((1, 1), dtype=object)
    cell[0, 0] = _outside_fdt(tmp_path / "OUTSIDE")
    path = _write_v5(tmp_path / "ds" / "rec.set", nbchan=2, labels=("Fz", "Cz"), data=cell)
    adapter = EeglabAdapter()
    assert adapter.inspect(path).missing_companions == ("companion.unsafe_reference",)
    assert adapter.read_check(path) == "UnsafePathError" and mne_calls == []


# --- earlier rules stay (A-77) ----------------------------------------------------------------------------


def test_earlier_rules_stay(tmp_path: Path, mne_calls: list[Path]) -> None:
    adapter = EeglabAdapter()
    labels = ("Fz", "Cz", "Pz", "Oz")
    bad_counts = _write_v5(tmp_path / "counts.set", nbchan=4, labels=labels, header={"nbchan": 2.5})
    assert adapter.inspect(bad_counts).issues == ("header.number_field",)
    unsafe = _write_v5(tmp_path / "unsafe.set", nbchan=2, labels=("Fz", "Cz"), data="../outside.fdt")
    inspection = adapter.inspect(unsafe)
    assert inspection.missing_companions == ("companion.unsafe_reference",)
    assert adapter.read_check(unsafe) == "UnsafePathError" and mne_calls == []
    epochs = _write_v5(tmp_path / "ep.set", nbchan=2, labels=("Fz", "Cz"), trials=3)
    assert epoched(epochs) is True and epoched(unsafe) is False
    other = _write_v5(tmp_path / "x" / "rec.set", nbchan=2, labels=("Fz", "Cz"), data="Other.FDT")
    assert referenced_fdt(other) == "other.fdt"
    (other.parent / "Other.FDT").write_bytes(np.zeros((256, 2), dtype="<f4").tobytes())
    assert [entry.relative.as_posix() for entry in scan(other.parent).recordings] == ["rec.set"]
