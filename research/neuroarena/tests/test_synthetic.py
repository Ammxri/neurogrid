"""The synthetic stand-ins (F11 B): shaped like each approved dataset, without any download, deterministic,
long enough for M06/M09 (A-79) and with enough trials per class for 5-fold stratified CV per session."""

from __future__ import annotations

import pickle
from collections import Counter

import mne
import pytest

from neuroarena import datasets, synthetic


@pytest.mark.parametrize("name", sorted(datasets.DATASETS))
def test_fake_dataset_is_shaped_like_the_spec(name: str) -> None:
    spec = datasets.DATASETS[name]
    fake = synthetic.fake_dataset(spec)
    loader = datasets.moabb_dataset(spec)
    assert fake.subject_list == [1, 2] and fake.paradigm == spec.paradigm
    assert list(fake.event_id) == list(spec.events) and fake.interval == list(map(float, loader.interval))
    data = fake.get_data([1, 2])
    for subject in (1, 2):
        sessions = data[subject]
        assert list(sessions) == [str(index) for index in range(synthetic.SESSIONS)]
        for runs in sessions.values():
            assert list(runs) == [str(index) for index in range(synthetic.RUNS_PER_SESSION)]
            labels: Counter[str] = Counter()
            for raw in runs.values():
                eeg = mne.pick_types(raw.info, eeg=True)
                assert len(eeg) == spec.n_eeg_channels and raw.info["sfreq"] == spec.sampling_rate_hz
                assert raw.info["line_freq"] == spec.line_frequency_hz
                assert raw.n_times / raw.info["sfreq"] >= synthetic.MIN_RUN_SECONDS
                montage = raw.get_montage().get_positions()["ch_pos"]
                assert set(montage) == {raw.ch_names[index] for index in eeg}
                labels.update(raw.annotations.description)
                rms = raw.get_data(picks="eeg").std(axis=1)
                assert ((rms > 5e-6) & (rms < 40e-6)).all()
            assert set(labels) == set(spec.events)
            assert min(labels.values()) >= 2 * 5  # 5-fold stratified CV with two test trials per class
    if name == "Cho2017":
        raw = data[1]["0"]["0"]
        assert raw.get_channel_types().count("emg") == 4 and "EMG1" in raw.ch_names


def test_fake_dataset_is_deterministic_and_picklable() -> None:
    spec = datasets.DATASETS["Zhou2016"]
    first = synthetic.fake_dataset(spec, n_subjects=2, seed=3).get_data([2])[2]["0"]["1"].get_data()
    again = pickle.loads(pickle.dumps(synthetic.fake_dataset(spec, n_subjects=2, seed=3)))
    assert again.get_data([2])[2]["0"]["1"].get_data().tobytes() == first.tobytes()
    other_seed = synthetic.fake_dataset(spec, n_subjects=2, seed=4).get_data([2])[2]["0"]["1"].get_data()
    other_run = synthetic.fake_dataset(spec, n_subjects=2, seed=3).get_data([2])[2]["0"]["0"].get_data()
    assert first.tobytes() != other_seed.tobytes() and first.tobytes() != other_run.tobytes()
    for bad in ({"n_subjects": 0}, {"seed": -1}):
        with pytest.raises(ValueError):
            synthetic.fake_dataset(spec, **bad)
