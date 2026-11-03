"""The FIF export and its index (A-101, F5a A): one flat FIF file per recording of the degraded view, float32,
with all channels, montage and annotations of the loader; the index maps the file back to the key."""

from __future__ import annotations

import json

import mne
import numpy as np
import pytest

from neuroarena import datasets, export, synthetic
from neuroarena.keys import Condition, RecordingKey

SPEC = datasets.DATASETS["Kalunga2016"]


def test_recording_filename_is_flat_and_never_a_split_name() -> None:
    assert export.recording_filename(RecordingKey("Cho2017", 7, "0", "12")) == "sub-007_ses-0_run-12_eeg.fif"
    assert export.recording_filename(RecordingKey("Zhou2016", 123, "2", "1")) == "sub-123_ses-2_run-1_eeg.fif"


def test_index_round_trip_is_sorted_utf8_lf(tmp_path) -> None:
    index = {
        "sub-002_ses-0_run-0_eeg.fif": RecordingKey("Zhou2016", 2, "0", "0"),
        "sub-001_ses-1_run-1_eeg.fif": RecordingKey("Zhou2016", 1, "1", "1"),
    }
    path = export.write_index(index, tmp_path)
    raw = path.read_bytes()
    assert path.name == "recordings.json" and b"\r" not in raw and raw.endswith(b"}\n")
    document = json.loads(raw)
    assert document["version"] == 1
    assert [entry["file"] for entry in document["recordings"]] == sorted(index)
    assert list(document["recordings"][0]) == ["dataset", "file", "run", "session", "subject"]
    assert raw.startswith(b'{\n  "recordings": [\n    {\n      "dataset"')
    assert export.read_index(tmp_path) == index == export.read_index(path)
    for bad in ("../x.fif", "a\\b.fif", "/abs.fif", "C:x.fif", ""):
        with pytest.raises(ValueError):
            export.write_index({bad: RecordingKey("Zhou2016", 1, "0", "0")}, tmp_path)
    path.write_bytes(raw.replace(b'"version": 1', b'"version": 2'))
    with pytest.raises(ValueError):
        export.read_index(path)


def test_write_fifs_writes_the_degraded_view(tmp_path) -> None:
    """Every run of the view as float32 FIF with the loader's channels, montage and annotations."""
    base = synthetic.fake_dataset(SPEC, n_subjects=2)
    view = datasets.degraded_dataset(SPEC, Condition("artifacts", 5), base)
    folder = tmp_path / "work"
    index = export.write_fifs(view, SPEC, [2, 1], folder)
    expected = [
        f"sub-{subject:03d}_ses-0_run-{run}_eeg.fif"
        for subject in (1, 2)
        for run in range(synthetic.RUNS_PER_SESSION)
    ]
    assert list(index) == expected
    assert sorted(path.name for path in folder.iterdir()) == sorted([*expected, "recordings.json"])
    assert export.read_index(folder) == index
    reference = view.get_data([1])[1]["0"]["1"]
    raw = mne.io.read_raw_fif(folder / "sub-001_ses-0_run-1_eeg.fif", preload=True, verbose="error")
    assert raw.ch_names == reference.ch_names and raw.get_channel_types() == reference.get_channel_types()
    assert raw.info["sfreq"] == reference.info["sfreq"] and raw.n_times == reference.n_times
    eeg = reference.get_data(picks="eeg")
    np.testing.assert_array_equal(raw.get_data(picks="eeg"), eeg.astype(np.float32).astype(np.float64))
    assert list(raw.annotations.description) == list(reference.annotations.description)
    assert len(raw.annotations) == synthetic.TRIALS_PER_CLASS_PER_RUN * len(SPEC.events)
    positions = raw.get_montage().get_positions()["ch_pos"]
    for name, position in reference.get_montage().get_positions()["ch_pos"].items():
        np.testing.assert_allclose(positions[name], position, atol=1e-7)
    with pytest.raises(ValueError, match="new or empty"):
        export.write_fifs(view, SPEC, [1], folder)
