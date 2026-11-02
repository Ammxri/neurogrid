"""FIF export of the (degraded) recordings for NeuroGrid (A-101, F5a A; area B "data and quality").

One folder per dataset and condition (``paths.work_dir``) holds one FIF file per recording, exactly the raw
that the decoders see (``datasets.degraded_dataset``), with the channels and montage of the MOABB loader, and
the index ``recordings.json``. NeuroGrid checks the folder as a raw folder; with ``--show-paths`` the id of a
recording in results.json is its file path relative to the folder (A-51), which the index maps back to the
recording key.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from neuroarena import paths
from neuroarena.datasets import DatasetSpec
from neuroarena.keys import RecordingKey

if TYPE_CHECKING:
    from moabb.datasets.base import BaseDataset

# Relative POSIX path of a FIF file inside the checked folder -> its recording.
RecordingIndex = Mapping[str, RecordingKey]

# FIF samples as float32 (draft 2.6: working files "FIF, float32"; raw.save(fmt="single")).
FIF_FORMAT = "single"
INDEX_VERSION = 1


def recording_filename(key: RecordingKey) -> str:
    """``sub-{subject:03d}_ses-{session}_run-{run}_eeg.fif``: one flat folder, an ending MNE reads without a
    naming warning, never a split-file name ``<base>-<n>.fif``. Session and run are the loader's names
    (keys.NAME)."""
    return f"sub-{key.subject:03d}_ses-{key.session}_run-{key.run}_eeg.fif"


def folder_is_free(folder: Path) -> bool:
    """True when ``folder`` does not exist or is an empty folder."""
    folder = Path(folder)
    return not folder.exists() or (folder.is_dir() and not any(folder.iterdir()))


def write_fifs(
    dataset: BaseDataset, spec: DatasetSpec, subjects: Sequence[int], folder: Path
) -> dict[str, RecordingKey]:
    """Write one FIF file per recording of ``subjects`` (in this order, one subject in memory at a time) of
    ``dataset`` into ``folder`` (which must not exist yet or be empty) and the index (``write_index``).
    Returns the index. Keys use ``spec.name`` as dataset. The files hold all channels of the loader.

    The raws are those of ``dataset.get_data([subject])`` (MOABB's raw stage: the loader's channels and
    montage, events as annotations), saved as float32 (``FIF_FORMAT``). ValueError if ``folder`` is not free
    or a subject appears twice; the index is sorted by file name."""
    folder = Path(folder)
    if not folder_is_free(folder):
        raise ValueError(f"the export folder must be new or empty: {folder.name}")
    if len(set(subjects)) != len(subjects):
        raise ValueError("a subject appears twice")
    folder.mkdir(parents=True, exist_ok=True)
    index: dict[str, RecordingKey] = {}
    for subject in subjects:
        data = dataset.get_data(subjects=[subject])
        for session, runs in data[subject].items():
            for run in list(runs):
                key = RecordingKey(spec.name, subject, str(session), str(run))
                name = recording_filename(key)
                runs.pop(run).save(folder / name, fmt=FIF_FORMAT, overwrite=False, verbose="error")
                index[name] = key
        del data
    index = dict(sorted(index.items()))
    write_index(index, folder)
    return index


def _checked_file(name: str) -> str:
    if not name or "\\" in name or name.startswith("/") or ".." in name.split("/") or ":" in name:
        raise ValueError(f"not a relative POSIX path: {name!r}")
    return name


def write_index(index: RecordingIndex, folder: Path) -> Path:
    """``folder/recordings.json``: ``{"version": 1, "recordings": [{"file", "dataset", "subject", "session",
    "run"}, ...]}`` sorted by file, UTF-8, LF, two-space indent, ``sort_keys``; returns its path."""
    entries = [
        {
            "file": _checked_file(name),
            "dataset": key.dataset,
            "subject": key.subject,
            "session": key.session,
            "run": key.run,
        }
        for name, key in sorted(index.items())
    ]
    text = json.dumps({"version": INDEX_VERSION, "recordings": entries}, indent=2, sort_keys=True)
    path = Path(folder) / paths.INDEX_FILE
    path.write_bytes((text + "\n").encode("utf-8"))
    return path


def read_index(path: Path) -> dict[str, RecordingKey]:
    """The index written by ``write_index`` (a folder or the file itself)."""
    path = Path(path)
    if path.is_dir():
        path = path / paths.INDEX_FILE
    document = json.loads(path.read_bytes().decode("utf-8"))
    if not isinstance(document, dict) or document.get("version") != INDEX_VERSION:
        raise ValueError(f"{paths.INDEX_FILE}: unknown version")
    index: dict[str, RecordingKey] = {}
    for entry in document["recordings"]:
        name = _checked_file(entry["file"])
        if name in index:
            raise ValueError(f"{paths.INDEX_FILE}: {name!r} appears twice")
        index[name] = RecordingKey(entry["dataset"], int(entry["subject"]), entry["session"], entry["run"])
    return index
