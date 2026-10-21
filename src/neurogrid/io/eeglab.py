"""EEGLAB adapter (.set with embedded data or a .fdt data file; NG-F01, M01, A-24, A-46).

The structure is read the way pymatreader reads it (MATLAB v5 with scipy, v7.3/HDF5 with h5py), at most
MAX_SET_BYTES (A-77). Only the header fields NeuroGrid uses are kept; embedded data are described by their
shape (a v7.3 file never loads them, a v5 file loads them with the structure), so such files are reported as
not streamable (R14).
A v7.3 file is checked as a whole before any reader, NeuroGrid's own or MNE's, opens its content (A-52):
HDF5 external links, external storage and virtual datasets would make HDF5 open other files, so such a file
is never read. Declared sizes (counted as often as a reader loads them, with what it makes of characters and
references) and the expanded size of compressed v5 variables count against MAX_SET_BYTES, and so do header
numbers MNE allocates by before it compares them with the data (epochs, the second the read check reads, the
shape of sparse data; default channel names at most MAX_DEFAULT_CHANNELS), taken as MNE takes them.
Integrity: channel count, sampling rate, size of the .fdt file or shape of the embedded data against the
header. The .fdt reference is a path from a file and goes through the path check (A-52); layouts in which MNE
or MNE-BIDS would read another structure or another EEG.data than the one checked (EEG.EEG, EEG next to a
top-level data variable, v7.3 EEG or EEG.data in a cell) are refused before any reader opens them.
Without channel locations the channels get MNE's default names, so the model matches what MNE reads.
Not taken over (A-51): subject, comments, filepath, history and setname; they are only flagged.
"""

from __future__ import annotations

import math
import struct
import zlib
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

import numpy as np

from neurogrid.io.base import HeaderInspection, HeaderUnreadable, mne_read_check
from neurogrid.io.channels import classify
from neurogrid.io.identifying import looks_identifying, placeholder, real_dates
from neurogrid.kernel.errors import UnsafePathError
from neurogrid.kernel.safety import check_relative, resolve_within
from neurogrid.model.dataset import Channel, Recording

MAX_SET_BYTES = 4_000_000_000
MAX_DEFAULT_CHANNELS = 4096  # channels named by default when chanlocs is missing (as EDF signals, edf.py)
BYTES_PER_SAMPLE = 4  # .fdt holds float32 samples
REFERENCE_BYTES = 512  # what a reader spends on one followed HDF5 object reference (Python objects)
OBJECT_BYTES = (
    128  # what a reader spends on an element it turns into a Python object (a character, a dimension)
)
EPOCH_BYTES = 48  # MNE's event table per declared epoch, built before it looks at the data
SAMPLE_BYTES = 8  # MNE holds samples as float64
_READ_ATTRIBUTES = ("MATLAB_class", "MATLAB_sparse")  # attributes pymatreader reads (MATLAB_fields it skips)
_INFLATE_CHUNK = 1 << 20
_MI_COMPRESSED = 15  # MAT v5 data type of a zlib-compressed variable
_HEADER_FIELDS = (
    "nbchan",
    "pnts",
    "trials",
    "srate",
    "chanlocs",
    "subject",
    "comments",
    "filepath",
    "history",
    "setname",
)
_EVENT_FIELDS = (*_HEADER_FIELDS, "event")  # EEG.event for the annotation reader (M10, A-80)
_TYPES = {
    "EEG": "EEG",
    "EOG": "EOG",
    "ECG": "ECG",
    "EKG": "ECG",
    "EMG": "EMG",
    "MISC": "MISC",
    "TRIG": "TRIG",
}


class _Refused(HeaderUnreadable):
    """The file is refused before any reader opens its content; MNE is not asked either (A-52, A-77).

    ``error_type`` is what the read check reports instead of an MNE exception class.
    """

    def __init__(self, reason: str, error_type: str = "HeaderUnreadable") -> None:
        super().__init__(reason)
        self.error_type = error_type


@dataclass(frozen=True)
class _Samples:
    """Embedded data, described by their shape as pymatreader gives it (singleton axes removed)."""

    shape: tuple[int, ...]


def _load(path: Path, fields: tuple[str, ...] = _HEADER_FIELDS) -> dict[str, Any]:
    """The header fields of the EEGLAB structure, with ``data`` as text (.fdt name), as ``_Samples`` (numeric
    data) or left out (no data, or data that are neither). ``fields`` names the fields kept."""
    if path.stat().st_size > MAX_SET_BYTES:
        raise _Refused("header.too_large")
    try:
        eeg = _read_container(path, fields)
    except HeaderUnreadable:
        raise
    except Exception:  # broken containers raise many exception types; only the outcome counts
        raise HeaderUnreadable("header.unreadable_container") from None
    if not isinstance(eeg, dict) or "nbchan" not in eeg:
        raise HeaderUnreadable("header.unreadable_container")
    _check_declared_reads(eeg)
    return eeg


def _mne_count(value: Any) -> int:
    """A header count as MNE takes it, ``int()`` of the number, also where NeuroGrid reports
    header.number_field; 0 when MNE cannot take it."""
    number = _number(value)
    return int(number) if number is not None else 0


def _check_declared_reads(eeg: Mapping[str, Any]) -> None:
    """Refuse header numbers that make MNE allocate before it compares them with the data (A-77):
    - without chanlocs, a default name for each of nbchan channels: at most MAX_DEFAULT_CHANNELS;
    - an epoched data set: an event table for each epoch (EPOCH_BYTES), at most MAX_SET_BYTES;
    - a continuous data set: the read check reads the first and the last second, one float64 value per
      channel and sample, at most pnts. MNE sizes it by the header, not by the .fdt or the embedded data
      (embedded data saved as top-level variables are read lazily, too): at most MAX_SET_BYTES.
    Real recordings stay far below these limits."""
    locs = _chanlocs(eeg)
    channels = len(locs) or _mne_count(eeg.get("nbchan"))  # as MNE counts them
    if not locs and channels > MAX_DEFAULT_CHANNELS:
        raise _Refused("header.too_large")
    trials = _trials(eeg) or 1  # read_check uses the epochs reader only for a valid count above 1
    if trials > 1:
        declared = trials * EPOCH_BYTES
    else:
        rate = _number(eeg.get("srate"))
        second = min(_mne_count(eeg.get("pnts")), int(rate)) if rate is not None and rate >= 1 else 1
        declared = max(channels, 1) * max(second, 1) * SAMPLE_BYTES
    if declared > MAX_SET_BYTES:
        raise _Refused("header.too_large")


def _check_sparse_data(rows: int, columns: int) -> None:
    """EEG.data as a MATLAB sparse matrix: MNE's raw reader makes a dense float64 array of its declared shape,
    which costs the file nothing (A-77)."""
    if rows * columns * SAMPLE_BYTES > MAX_SET_BYTES:
        raise _Refused("header.too_large")


def _read_container(path: Path, fields: tuple[str, ...] = _HEADER_FIELDS) -> Any:
    """The EEG structure (or the file's variables) like ``pymatreader.read_mat`` gives it, header fields only.

    pymatreader asks scipy first and falls back to HDF5 when scipy refuses (MAT v7.3); this follows the same
    path. Any file HDF5 can open is checked as an HDF5 container first, because MNE's reader may open it so.
    """
    import h5py
    from scipy.io.matlab import matfile_version

    with path.open("rb") as handle:
        major, _ = matfile_version(handle)
    hdf5 = h5py.is_hdf5(str(path))
    if major != 2:
        if hdf5:
            with _checked_hdf5(path):
                pass
        try:
            return _read_mat5(path, major, fields)
        except NotImplementedError:
            if not hdf5:
                raise
    with _checked_hdf5(path) as container:
        return _read_hdf5(container, fields)


@contextmanager
def _checked_hdf5(path: Path) -> Iterator[Any]:
    """The open HDF5 file after ``_check_hdf5``. Any failure of the check refuses the file: MNE's reader
    visits the objects in another order and could reach an external link that the check did not get to."""
    import h5py

    with h5py.File(path, "r") as container:
        try:
            _check_hdf5(container)
        except HeaderUnreadable:
            raise
        except Exception:  # e.g. RecursionError, broken references: the walk did not finish
            raise _Refused("header.unreadable_container") from None
        yield container


def _select(variables: Mapping[str, Any]) -> Any:
    """The EEG structure among the file's variables, or the variables themselves without EEG (A-52, A-77).

    Layouts in which MNE or MNE-BIDS would take another structure than the one NeuroGrid checks are refused,
    so the EEG.data path check and the size checks always apply to what they open (EEGLAB writes neither):
    - EEG next to a top-level ``data`` variable: MNE's raw reader then takes the header from the top-level
      variables, its epochs reader and MNE-BIDS from EEG;
    - EEG.EEG: MNE reads the inner structure, MNE-BIDS copies the .fdt the outer one names.
    """
    if "EEG" not in variables:
        return variables
    if "data" in variables:
        raise _Refused("header.unreadable_container")
    eeg = variables["EEG"]
    if isinstance(eeg, Mapping) and "EEG" in eeg:
        raise _Refused("header.unreadable_container")
    return eeg


def _read_mat5(path: Path, major: int, fields: tuple[str, ...] = _HEADER_FIELDS) -> Any:
    import scipy.io
    import scipy.sparse
    from pymatreader.utils import _parse_scipy_mat_dict

    with path.open("rb") as handle:
        if major == 1:
            _check_inflated_size(handle)
            handle.seek(0)
        variables = scipy.io.loadmat(handle, struct_as_record=True, squeeze_me=True, mat_dtype=False)
    eeg = _select(_parse_scipy_mat_dict(variables))
    if not isinstance(eeg, dict):
        return eeg
    header = {key: eeg[key] for key in fields if key in eeg}
    if "data" in eeg:
        data = eeg["data"]
        if isinstance(data, str):
            header["data"] = data
        elif scipy.sparse.issparse(data):
            _check_sparse_data(*data.shape)
        elif np.asarray(data).dtype.kind in "biufc":  # numbers; one value arrives as a plain number
            header["data"] = _Samples(tuple(np.shape(data)))
    return header


def _check_inflated_size(handle: IO[bytes]) -> None:
    """MAT v5: compressed variables may expand far beyond the file size; count their expanded size first.

    Uncompressed variables hold at most the file size. A broken stream ends the count; scipy reports it.
    """
    end = handle.seek(0, 2)
    handle.seek(124)
    order = "<" if handle.read(4)[2:4] == b"IM" else ">"
    total = 0
    while len(tag := handle.read(8)) == 8:
        kind, size = struct.unpack(order + "II", tag)
        if kind >> 16:  # small element: the data sit in the tag
            continue
        if kind != _MI_COMPRESSED:
            total += min(size, end - handle.tell())  # what the file really holds
            handle.seek(size, 1)
            continue
        inflater = zlib.decompressobj()
        remaining = size
        try:
            while remaining > 0 and not inflater.eof:
                chunk = handle.read(min(remaining, _INFLATE_CHUNK))
                if not chunk:
                    return
                remaining -= len(chunk)
                while chunk and not inflater.eof:
                    total += len(inflater.decompress(chunk, _INFLATE_CHUNK))
                    if total > MAX_SET_BYTES:
                        raise _Refused("header.too_large")
                    chunk = inflater.unconsumed_tail
        except zlib.error:
            return
        handle.seek(remaining, 1)
        if total > MAX_SET_BYTES:
            raise _Refused("header.too_large")


def _check_hdf5(container: Any) -> None:
    """MAT v7.3: refuse what makes a reader leave the file or allocate more than MAX_SET_BYTES (A-52, A-77).

    pymatreader (also inside MNE) reads every object of the file and follows object references, as often as
    they occur. The whole file is walked over its links, resolving hard links only, and over references:
    - external links, external storage and virtual datasets (HDF5 would open other files):
      ``header.external_reference``;
    - soft links, other link kinds, reference cycles, variable-length data (pymatreader takes texts as
      paths; elements may share one stored value, so the file size bounds nothing), the same in the attributes
      pymatreader reads, and objects other than groups and datasets: ``header.unreadable_container`` (MATLAB
      writes none of them);
    - more declared bytes than MAX_SET_BYTES, counted per load, references at REFERENCE_BYTES each and
      elements a reader turns into Python objects (characters: one text per character before they are
      joined; MATLAB_empty dimensions) at OBJECT_BYTES more: ``header.too_large``. Unwritten chunks take no
      space in the file but are allocated when read.
    """
    import h5py

    costs: dict[tuple[int, int], int] = {}
    open_nodes: set[tuple[int, int]] = set()
    spent = 0

    def charge(amount: int) -> None:
        nonlocal spent
        spent += amount
        if spent > MAX_SET_BYTES:
            raise _Refused("header.too_large")

    def cost(node: Any) -> int:
        info = h5py.h5o.get_info(node.id)
        key = (info.fileno, info.addr)
        if key in costs:
            return costs[key]
        if key in open_nodes:  # a cycle: a reader would never end
            raise _Refused("header.unreadable_container")
        open_nodes.add(key)
        for attribute in _READ_ATTRIBUTES:  # checked by type before anyone reads them
            if attribute in node.attrs and h5py.h5a.open(node.id, attribute.encode()).dtype.hasobject:
                raise _Refused("header.unreadable_container")
        if isinstance(node, h5py.Group):
            total = 0
            for name in node:
                link = node.get(name, getlink=True)
                if isinstance(link, h5py.ExternalLink):
                    raise _Refused("header.external_reference", "UnsafePathError")
                if not isinstance(link, h5py.HardLink):
                    raise _Refused("header.unreadable_container")
                total += cost(node[name])
        elif isinstance(node, h5py.Dataset):
            plist = node.id.get_create_plist()
            if plist.get_external_count() > 0 or plist.get_layout() == h5py.h5d.VIRTUAL:
                raise _Refused("header.external_reference", "UnsafePathError")
            reference = h5py.check_dtype(ref=node.dtype)
            if reference is None and node.dtype.hasobject:  # also variable-length fields of a compound
                raise _Refused("header.unreadable_container")
            empty = "MATLAB_empty" in node.attrs
            elements = math.prod(node.shape) if node.shape is not None else 0
            per_element = node.dtype.itemsize
            if empty or _matlab_class(node) == "char":
                per_element += OBJECT_BYTES
            total = elements * per_element
            charge(total)
            if reference is not None and not empty:
                charge(elements * REFERENCE_BYTES)
                addresses = _object_addresses(node) if reference is h5py.Reference else None
                for index, target in enumerate(np.asarray(node[()]).flat):
                    known = None if addresses is None else costs.get((info.fileno, int(addresses[index])))
                    total += REFERENCE_BYTES + (cost(container[target]) if known is None else known)
                    if total > MAX_SET_BYTES:
                        raise _Refused("header.too_large")
        else:
            raise _Refused("header.unreadable_container")
        open_nodes.discard(key)
        if total > MAX_SET_BYTES:
            raise _Refused("header.too_large")
        costs[key] = total
        return total

    cost(container["/"])


def _object_addresses(node: Any) -> Any:
    """The addresses an object reference dataset holds (an object reference is the object's address), so that
    objects checked already are not opened again; None when they cannot be read that way."""
    import h5py

    try:
        addresses = np.empty(node.shape, dtype="<u8")  # STD_REF_OBJ in memory: 8 bytes per reference
        node.id.read(h5py.h5s.ALL, h5py.h5s.ALL, addresses, mtype=h5py.h5t.STD_REF_OBJ)
    except Exception:  # e.g. region references; every reference is then opened
        return None
    return addresses.ravel()


def _read_hdf5(container: Any, fields: tuple[str, ...] = _HEADER_FIELDS) -> Any:
    """Header fields of a checked v7.3 file; embedded data only by their shape (never loaded)."""
    import h5py
    from pymatreader.utils import _handle_hdf5_dataset, _handle_hdf5_group

    group = _select(container)
    if not isinstance(group, h5py.Group):  # e.g. EEG in a cell, which pymatreader unwraps
        raise _Refused("header.unreadable_container")
    header = _handle_hdf5_group(group, variable_names=list(fields), ignore_fields=["#refs#"])
    node = group.get("data")
    if isinstance(node, h5py.Dataset) and h5py.check_dtype(ref=node.dtype) is not None:
        # EEG.data in a cell: pymatreader unwraps a one-element cell, so it could hold a .fdt name that the
        # path check would not see (A-52); MATLAB never writes EEG.data so
        raise _Refused("header.unreadable_container")
    if isinstance(node, h5py.Dataset) and _matlab_class(node) == "char":
        header["data"] = _handle_hdf5_dataset(node)
    elif isinstance(node, h5py.Dataset) and h5py.check_dtype(ref=node.dtype) is None:
        header["data"] = _Samples(_squeezed_shape(node))
    elif isinstance(node, h5py.Group) and "MATLAB_sparse" in node.attrs:  # columns as pymatreader counts them
        columns = node.get("jc")
        _check_sparse_data(int(node.attrs["MATLAB_sparse"]), len(columns) - 1 if columns is not None else 0)
    return header


def _matlab_class(node: Any) -> str:
    value = node.attrs.get("MATLAB_class", b"")
    return value.decode("ascii", "replace") if isinstance(value, bytes) else str(value)


def _squeezed_shape(node: Any) -> tuple[int, ...]:
    """The shape pymatreader gives a numeric dataset: MATLAB order, singleton axes removed."""
    import h5py

    if not isinstance(node, h5py.Dataset) or node.shape is None:
        return ()
    if "MATLAB_empty" in node.attrs:
        return (0,)
    if math.prod(node.shape) == 1:
        return ()  # a single value arrives as a number
    return tuple(reversed([size for size in node.shape if size != 1]))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _count(value: Any) -> int | None:
    """A positive whole number from the header, else None."""
    number = _number(value)
    return int(number) if number is not None and number > 0 and number.is_integer() else None


def _trials(eeg: Mapping[str, Any]) -> int | None:
    """Number of epochs; 1 when the header has none (continuous data), None when it is invalid."""
    value = eeg.get("trials")
    return 1 if value is None else _count(value)


def _as_list(value: Any, count: int) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    if hasattr(value, "tolist"):
        converted = value.tolist()
        return converted if isinstance(converted, list) else [converted] * count
    return [value] * count


def _chanlocs(eeg: Mapping[str, Any]) -> list[dict[str, Any]]:
    locs = eeg.get("chanlocs")
    if isinstance(locs, Mapping):
        labels = _as_list(locs.get("labels", []), 1)  # one channel: the fields are scalars
        columns = {
            key: _as_list(locs.get(key), len(labels)) if locs.get(key) is not None else []
            for key in ("labels", "type", "X", "Y", "Z")
        }
        return [
            {key: values[index] if index < len(values) else None for key, values in columns.items()}
            for index in range(len(labels))
        ]
    if isinstance(locs, Sequence) and not isinstance(locs, str):
        return [dict(item) for item in locs if isinstance(item, Mapping)]
    return []


def _channel_entries(eeg: Mapping[str, Any]) -> list[dict[str, Any]]:
    """chanlocs, completed to nbchan entries with MNE's default names 'EEG 000', 'EEG 001', … and type EEG.

    mne.io.read_raw_eeglab names the channels so when chanlocs is empty (EEGLAB after importing a plain
    matrix). More than MAX_DEFAULT_CHANNELS named this way is refused: the count is only a header number.
    """
    entries = _chanlocs(eeg)
    nbchan = _count(eeg.get("nbchan"))
    if nbchan is None or len(entries) >= nbchan:
        return entries
    if nbchan > MAX_DEFAULT_CHANNELS:
        raise _Refused("header.too_large")
    defaults = [{"labels": f"EEG {index:03d}", "type": "EEG"} for index in range(len(entries), nbchan)]
    return entries + defaults


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "tolist"):  # numpy values; an empty MATLAB text arrives as an empty array
        return _text(value.tolist())
    if isinstance(value, Sequence):
        return " ".join(_text(item) for item in value)
    return str(value)


def _fdt(path: Path, eeg: Mapping[str, Any]) -> tuple[Path | None, str | None]:
    """The data file named in the header (``data`` as text): (path, problem key)."""
    name = eeg.get("data")
    if not isinstance(name, str):
        return None, None  # embedded data
    try:
        relative = check_relative(name)
        if len(relative.parts) != 1:  # only a file next to the .set is followed (A-52, A-77)
            return None, "companion.unsafe_reference"
        target = resolve_within(path.parent, relative, must_exist=False)
    except UnsafePathError:
        return None, "companion.unsafe_reference"
    return (target, None) if target.is_file() else (target, "companion.fdt")


def _shape_matches(shape: tuple[int, ...], nbchan: int, pnts: int, trials: int) -> bool:
    """Embedded data against the header, with singleton axes removed as the reader does: one channel or one
    epoch gives fewer axes. Epochs may be a third axis or follow each other on the second."""
    squeezed = tuple(size for size in shape if size != 1)
    layouts = ((nbchan, pnts, trials), (nbchan, pnts * trials))
    return any(squeezed == tuple(size for size in layout if size != 1) for layout in layouts)


def _position(loc: Mapping[str, Any]) -> str | None:
    coords = [_number(loc.get(axis)) for axis in ("X", "Y", "Z")]
    if any(c is None for c in coords) or all(c == 0 for c in coords):
        return None
    return ",".join(f"{c:.6g}" for c in coords if c is not None)


class EeglabAdapter:
    format: str = "EEGLAB"
    extensions: tuple[str, ...] = (".set",)

    def read(self, path: Path, *, recording_id: str, relative_path: str) -> Recording:
        eeg = _load(path)
        rate = _number(eeg.get("srate"))
        rate = rate if rate and rate > 0 else None
        pnts = _count(eeg.get("pnts"))
        trials = _trials(eeg)
        channels = []
        for loc in _channel_entries(eeg):
            label = _text(loc.get("labels")).strip()
            declared = _text(loc.get("type")).strip().upper()
            channels.append(
                Channel(
                    name=label,
                    type=_TYPES.get(declared, classify(label)),
                    unit="µV",
                    recording_id=recording_id,
                    sampling_rate_hz=rate,
                    position=_position(loc),
                )
            )
        sources = {"channels": "header"}
        duration = pnts * trials / rate if rate and pnts and trials else None
        if rate:
            sources["sampling_rate_hz"] = "header"
        if duration is not None:
            sources["duration_s"] = "header"
        if any(ch.position for ch in channels):
            sources["position"] = "header"
        return Recording(
            id=recording_id,
            format=self.format,
            path=relative_path,
            sampling_rate_hz=rate,  # one rate for all channels (srate), whatever their types
            duration_s=duration,
            streamable=isinstance(eeg.get("data"), str),
            metadata_sources=sources,
            channels=channels,
        )

    def inspect(self, path: Path) -> HeaderInspection:
        eeg = _load(path)
        issues: list[str] = []
        missing: list[str] = []
        nbchan = _count(eeg.get("nbchan"))
        pnts = _count(eeg.get("pnts"))
        trials = _trials(eeg)
        rate = _number(eeg.get("srate"))
        locs = _chanlocs(eeg)
        if nbchan is None:
            issues.append("header.number_field")
        elif locs and len(locs) != nbchan:  # no chanlocs at all: MNE names the channels itself
            issues.append("header.channel_count")
        if rate is None or rate <= 0:
            issues.append("header.sampling_rate")
        if pnts is None or trials is None:
            issues.append("header.number_field")
        fdt, problem = _fdt(path, eeg)
        if problem:
            missing.append(problem)
        elif fdt is not None and nbchan and pnts and trials:  # sizes only from valid counts
            expected = nbchan * pnts * trials * BYTES_PER_SAMPLE
            size = fdt.stat().st_size
            if size < expected:
                issues.append("header.file_truncated")
            elif size > expected:
                issues.append("header.file_trailing_data")
        data = eeg.get("data")
        if not isinstance(data, str) and nbchan and pnts and trials:  # no samples at all is no match either
            if not isinstance(data, _Samples) or not _shape_matches(data.shape, nbchan, pnts, trials):
                issues.append("header.data_shape")
        identifying: list[str] = []
        subject = _text(eeg.get("subject")).strip()
        if subject and not placeholder(subject):
            identifying.append("patient")
        free_text = " ".join(_text(eeg.get(key)) for key in ("comments", "history", "setname"))
        if _text(eeg.get("filepath")).strip() or looks_identifying(free_text):
            identifying.append("recording")
        if real_dates(free_text):
            identifying.append("date")
        return HeaderInspection(
            issues=tuple(dict.fromkeys(issues)),
            identifying_fields=tuple(identifying),
            missing_companions=tuple(dict.fromkeys(missing)),
        )

    def read_check(self, path: Path) -> str | None:
        import mne

        try:
            eeg = _load(path)
            _channel_entries(eeg)  # MNE names a channel for each of nbchan when chanlocs is empty
        except _Refused as refused:
            return refused.error_type  # never handed to MNE: it would leave the file or exhaust memory
        except HeaderUnreadable:
            eeg = None
        if eeg is not None and _fdt(path, eeg)[1] == "companion.unsafe_reference":
            return "UnsafePathError"  # MNE would follow EEG.data itself; it is never opened (A-52)
        trials = (_trials(eeg) or 1) if eeg is not None else 1
        if trials > 1:  # epoched data set
            return mne_read_check(_EpochsAsRaw(mne.read_epochs_eeglab), path)
        return mne_read_check(mne.io.read_raw_eeglab, path)


def epoched(path: Path) -> bool:
    """True for an EEGLAB data set with more than one epoch (convert needs continuous data, A-77)."""
    try:
        trials = _trials(_load(path))
    except HeaderUnreadable:
        return False
    return trials is not None and trials > 1


def load_events(path: Path) -> dict[str, Any]:
    """The header fields plus ``event`` (EEG.event as pymatreader gives it), through the same guarded loaders
    and size limits as the header (A-53, A-77); raises HeaderUnreadable like the adapter."""
    eeg = _load(path, _EVENT_FIELDS)
    _channel_entries(eeg)  # the same refusal as the adapter for unnamed channels beyond the limit
    return eeg


def referenced_fdt(path: Path) -> str | None:
    """Lower-case name of the .fdt file a .set names, if it is a plain file name (for discovery)."""
    try:
        name = _load(path).get("data")
        if not isinstance(name, str):
            return None
        relative = check_relative(name)
    except (HeaderUnreadable, UnsafePathError, OSError):
        return None
    return relative.parts[0].lower() if len(relative.parts) == 1 else None


class _EpochsAsRaw:
    """Read an epoched .set and expose the calls mne_read_check makes on a raw object."""

    def __init__(self, reader: Any) -> None:
        self.reader = reader

    def __call__(self, path: Path, *, preload: bool, verbose: str) -> Any:
        epochs = self.reader(path, verbose=verbose)
        return _EpochsView(epochs)


class _EpochsView:
    def __init__(self, epochs: Any) -> None:
        self.epochs = epochs
        self.ch_names = epochs.ch_names
        self.info = epochs.info
        self.n_times = len(epochs.times)

    def get_data(self, start: int, stop: int, verbose: str) -> Any:
        return self.epochs.get_data(item=[0], verbose=verbose)[:, :, start:stop]
