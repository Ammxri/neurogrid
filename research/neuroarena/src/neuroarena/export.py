"""FIF export of the (degraded) recordings for NeuroGrid (A-101, F5a A; area B "data and quality").

One folder per dataset and condition (``paths.work_dir``) holds one FIF file per recording, exactly the raw
that the decoders see (``datasets.degraded_dataset``), with the channels and montage of the MOABB loader, and
the index ``recordings.json``. NeuroGrid checks the folder as a raw folder; with ``--show-paths`` the id of a
recording in results.json is its file path relative to the folder (A-51), which the index maps back to the
recording key.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

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
    raise NotImplementedError("area B")


def write_fifs(
    dataset: BaseDataset, spec: DatasetSpec, subjects: Sequence[int], folder: Path
) -> dict[str, RecordingKey]:
    """Write one FIF file per recording of ``subjects`` (in this order, one subject in memory at a time) of
    ``dataset`` into ``folder`` (which must not exist yet or be empty) and the index (``write_index``).
    Returns the index. Keys use ``spec.name`` as dataset. The files hold all channels of the loader."""
    raise NotImplementedError("area B")


def write_index(index: RecordingIndex, folder: Path) -> Path:
    """``folder/recordings.json``: ``{"version": 1, "recordings": [{"file", "dataset", "subject", "session",
    "run"}, ...]}`` sorted by file, UTF-8, LF, two-space indent, ``sort_keys``; returns its path."""
    raise NotImplementedError("area B")


def read_index(path: Path) -> dict[str, RecordingKey]:
    """The index written by ``write_index`` (a folder or the file itself)."""
    raise NotImplementedError("area B")
