"""FIF adapter (MNE-Python raw files, incl. split files; NG-F01, M01, A-24).

The measurement info is read by MNE without loading data. Channel types come from the file itself.
Not taken over (A-51): subject_info, experimenter, description and the measurement ID; they are only flagged.
Files anonymized with MNE (experimenter "mne_anonymize", description "Anonymized ...") carry a shifted date
on purpose; that date is not flagged as a real recording date.

A split file names its next part in a FIFF_REF block, and MNE opens that file on its own. Before MNE reads a
file as raw data, the chain of parts is followed here exactly as MNE follows it; every part must be a plain
file name next to the file, without links (A-52, A-77). Otherwise the reference is reported as unsafe
(M01-03), only the measurement info of the file itself is read, and the read check is not run.
"""

from __future__ import annotations

import math
import os
import warnings
from pathlib import Path
from typing import Any

from neurogrid.io.base import HeaderInspection, HeaderUnreadable, mne_read_check
from neurogrid.io.identifying import looks_identifying, placeholder
from neurogrid.kernel.errors import UnsafePathError
from neurogrid.kernel.safety import check_relative, resolve_within
from neurogrid.model.dataset import Channel, Recording

_TYPES = {
    "eeg": "EEG",
    "eog": "EOG",
    "ecg": "ECG",
    "emg": "EMG",
    "stim": "TRIG",
    "misc": "MISC",
    "resp": "RESP",
    "bio": "MISC",
    "mag": "MEG",
    "grad": "MEG",
    "ref_meg": "MEG",
}
_UNITS = {107: "V", 112: "T", 201: "T/m"}  # FIFF unit codes; others stay unnamed
_PERSON_FIELDS = ("his_id", "first_name", "middle_name", "last_name", "birthday")
MAX_SPLIT_PARTS = 1000  # MNE writes at most 100 parts; a longer chain is not followed


def _unsafe_split(path: Path) -> bool:
    """True if MNE, reading ``path`` as raw data, would open a split part that is not a plain file name next
    to ``path`` (absolute, with folders, ``..``, a link, a stream or a reserved name), or would come back to
    a part it has already read, which MNE follows without end (A-52, A-77).

    The parts are found with MNE's own functions (``fiff_open`` and ``_get_next_fname``, as in
    ``mne.io.fiff.raw.Raw``), so the file checked is the file MNE would open. A damaged part makes MNE fail
    before it follows a reference, so it ends the walk without a finding; MNE then reports the damage itself.
    """
    from mne._fiff.open import _get_next_fname, fiff_open

    folder = path.parent
    current = path.expanduser().absolute()  # as MNE's _check_fname makes it
    seen = {os.path.normcase(str(current.resolve()))}
    while True:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                handle, tree, _directory = fiff_open(current, verbose="error")
                with handle as fid:
                    following = _get_next_fname(fid, current, tree)
        except Exception:  # not a FIF file or damaged: MNE stops at the same point
            return False
        if following is None:
            return False
        following = Path(following)
        if following.parent != current.parent:
            return True
        try:
            relative = check_relative(following.name)
            if len(relative.parts) != 1:
                return True
            resolved = resolve_within(folder, relative, must_exist=False)
        except UnsafePathError:
            return True
        if not following.exists():
            return False  # MNE stops with "next file does not exist"; nothing outside is opened
        key = os.path.normcase(str(resolved))
        if key in seen or len(seen) >= MAX_SPLIT_PARTS:
            return True
        seen.add(key)
        current = following


def _raw(path: Path) -> Any:
    import mne

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return mne.io.read_raw_fif(path, preload=False, allow_maxshield=True, verbose="error")
    except Exception:  # not a raw file (e.g. a calibration file) or damaged; only the outcome counts
        raise HeaderUnreadable("header.unreadable_container") from None


def _info_only(path: Path) -> Any:
    """The measurement info of this one file; MNE does not follow split references here."""
    import mne

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return mne.io.read_info(path, verbose="error")
    except Exception:  # damaged or no FIF file; only the outcome counts
        raise HeaderUnreadable("header.unreadable_container") from None


def _open(path: Path) -> tuple[Any, int | None, bool]:
    """(measurement info, number of samples, unsafe split reference). With an unsafe reference only the info
    of the file itself is read and the number of samples is unknown (A-52)."""
    if _unsafe_split(path):
        return _info_only(path), None, True
    raw = _raw(path)
    return raw.info, int(raw.n_times), False


def _position(loc: Any) -> str | None:
    coords = [float(value) for value in loc[:3]]
    if not all(math.isfinite(c) for c in coords) or all(c == 0 for c in coords):
        return None
    return ",".join(f"{c:.6g}" for c in coords)


def _anonymized(info: Any) -> bool:
    experimenter = str(info.get("experimenter") or "")
    description = str(info.get("description") or "")
    return experimenter == "mne_anonymize" or description.startswith("Anonymized")


def _person_value(key: str, value: Any, anonymized: bool) -> bool:
    """True if a subject_info field holds a real value. After raw.anonymize() MNE writes "mne_anonymize"
    and his_id "0" and shifts the birthday like meas_date; those are no identifiers (A-77)."""
    text = str(value or "").strip()
    if not text or placeholder(text):
        return False
    if anonymized and (text == "mne_anonymize" or key == "birthday" or (key == "his_id" and text == "0")):
        return False
    return True


class FifAdapter:
    format: str = "FIF"
    extensions: tuple[str, ...] = (".fif",)

    def read(self, path: Path, *, recording_id: str, relative_path: str) -> Recording:
        info, n_times, _unsafe = _open(path)
        rate = float(info["sfreq"])
        types = info.get_channel_types()
        channels = [
            Channel(
                name=ch["ch_name"],
                type=_TYPES.get(kind, "MISC"),
                unit=_UNITS.get(int(ch["unit"])),
                recording_id=recording_id,
                sampling_rate_hz=rate,
                position=_position(ch["loc"]),
            )
            for ch, kind in zip(info["chs"], types, strict=True)
        ]
        sources = {"channels": "header", "sampling_rate_hz": "header"}
        duration = n_times / rate if rate and n_times is not None else None
        if duration is not None:
            sources["duration_s"] = "header"
        line = info.get("line_freq")
        line = float(line) if line and math.isfinite(float(line)) and float(line) > 0 else None  # A-75
        if line:
            sources["line_frequency_hz"] = "header"
        if any(ch.position for ch in channels):
            sources["position"] = "header"
        return Recording(
            id=recording_id,
            format=self.format,
            path=relative_path,
            sampling_rate_hz=rate if any(ch.type == "EEG" for ch in channels) else None,
            duration_s=duration,
            line_frequency_hz=line,
            streamable=True,
            metadata_sources=sources,
            channels=channels,
        )

    def inspect(self, path: Path) -> HeaderInspection:
        info, _n_times, unsafe = _open(path)
        identifying: list[str] = []
        subject = info.get("subject_info") or {}
        anonymized = _anonymized(info)
        if any(_person_value(key, subject.get(key), anonymized) for key in _PERSON_FIELDS):
            identifying.append("patient")
        if not anonymized:
            free_text = " ".join(
                str(info.get(key) or "") for key in ("experimenter", "description", "proj_name")
            )
            if free_text.strip() and (
                looks_identifying(free_text) or str(info.get("experimenter") or "").strip()
            ):
                identifying.append("recording")
            if info.get("meas_date") is not None:
                identifying.append("date")
        return HeaderInspection(
            identifying_fields=tuple(identifying),
            missing_companions=("companion.unsafe_reference",) if unsafe else (),
        )

    def read_check(self, path: Path) -> str | None:
        """MNE reads the data only when every split part it would open is a plain file next to the file;
        otherwise ``UnsafePathError`` without opening any part (A-52, A-77)."""
        import mne

        if _unsafe_split(path):
            return UnsafePathError.__name__
        return mne_read_check(mne.io.read_raw_fif, path, allow_maxshield=True)
