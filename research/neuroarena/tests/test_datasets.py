"""NA-01: the three approved datasets with licence, source and DOI, checked against the MOABB loaders as far
as that works without a download; the storage stays under .local/arena; the degraded view keeps the
contract that area C relies on (``datasets.degraded_dataset``)."""

from __future__ import annotations

import importlib
import os
import pickle

import moabb.datasets
import numpy as np
import pytest
from moabb.datasets import gigadb, ssvep_exo
from moabb.paradigms import SSVEP, MotorImagery

from neuroarena import datasets, synthetic
from neuroarena.keys import CLEAN, CONDITIONS, Condition

APPROVED = {
    # name: (licence, source, download, paper DOI, mne sign)
    "Zhou2016": (
        "CC-BY-4.0",
        "doi:10.6084/m9.figshare.2061654",
        importlib.import_module("moabb.datasets.Zhou2016").ZENODO_URL,
        "10.1371/journal.pone.0162657",
        "ZHOU2016",
    ),
    "Cho2017": ("CC0-1.0", "doi:10.5524/100295", gigadb.GIGA_URL, "10.1093/gigascience/gix034", "GIGADB"),
    "Kalunga2016": (
        "CC-BY-4.0",
        "https://zenodo.org/record/2392979",
        ssvep_exo.SSVEPEXO_URL,
        "10.1016/j.neucom.2016.01.007",
        "SSVEPEXO",
    ),
}


def test_datasets_are_the_approved_ones() -> None:
    """F1 B: exactly Zhou2016, Cho2017 and Kalunga2016; licences checked at the download sources by the lead
    (2026-11-02); the numbers are those of the moabb 1.7.2 loaders (draft 2.1, R-P11-9)."""
    assert set(datasets.DATASETS) == set(APPROVED)
    for name, (licence, source, download, paper, sign) in APPROVED.items():
        spec = datasets.DATASETS[name]
        assert spec.name == name and spec.licence == licence and spec.licence_verified, name
        assert (spec.source, spec.download, spec.paper_doi, spec.mne_sign) == (source, download, paper, sign)
        assert spec.licence in spec.licence_note
        loader = getattr(moabb.datasets, name)()
        # attribution (A-36): the reference of the loader's docstring
        assert " ".join(spec.citation.split()) in " ".join(type(loader).__doc__.split())
        meta = type(loader).METADATA.acquisition
        assert loader.code == name and loader.paradigm == spec.paradigm
        assert len(loader.subject_list) == spec.n_subjects
        assert set(loader.event_id) == set(spec.events)
        assert meta.sampling_rate == spec.sampling_rate_hz and meta.line_freq == spec.line_frequency_hz
        assert meta.channel_types["eeg"] == spec.n_eeg_channels
        assert loader.doi in (spec.paper_doi, spec.source.removeprefix("doi:"))
    assert datasets.DATASETS["Cho2017"].events == ("left_hand", "right_hand")
    assert "CC0-1.0" in datasets.DATASETS["Zhou2016"].licence_note  # the original figshare item


def test_configure_storage_writes_no_file_under_home(tmp_path, monkeypatch) -> None:
    """A-100: MNE and MOABB find the data folder in the environment of this process; nothing is written to
    the home folder (no ~/.mne/mne-python.json, no ~/mne_data), and downloads come from the checked
    sources."""
    from moabb.datasets.download import get_dataset_path
    from moabb.utils import get_download_provider

    home = tmp_path / "home"
    home.mkdir()
    for variable in ("HOME", "USERPROFILE", "_MNE_FAKE_HOME_DIR"):
        monkeypatch.setenv(variable, str(home))
    keys = ["MNE_DATA", "MOABB_DOWNLOAD_PROVIDER"]
    keys += [f"MNE_DATASETS_{spec.mne_sign}_PATH" for spec in datasets.DATASETS.values()]
    for variable in keys:  # registered here, so that monkeypatch restores them afterwards
        monkeypatch.setenv(variable, "unset")
    folder = tmp_path / "arena" / "mne_data"
    datasets.configure_storage(folder)
    assert folder.is_dir()
    assert {variable: os.environ[variable] for variable in keys} == {
        **{variable: str(folder) for variable in keys},
        "MOABB_DOWNLOAD_PROVIDER": "upstream",
    }
    for spec in datasets.DATASETS.values():
        assert get_dataset_path(spec.mne_sign, None) == folder
        assert get_dataset_path(spec.name, None) == folder
    assert get_download_provider() == "upstream"
    assert list(home.iterdir()) == []
    assert datasets.paths.MNE_DATA.is_relative_to(datasets.paths.ARENA)


def test_fetch_refuses_an_unverified_licence() -> None:
    unverified = datasets.DatasetSpec(**{**vars(datasets.DATASETS["Cho2017"]), "licence_verified": False})
    with pytest.raises(RuntimeError, match="licence"):
        datasets.fetch(unverified)


def _base(name: str = "Kalunga2016", subjects: int = 1):
    return synthetic.fake_dataset(datasets.DATASETS[name], n_subjects=subjects)


def test_degraded_view_keeps_the_contract() -> None:
    """Same subjects, sessions, runs, channels, montage, annotations and events as the base; only the EEG
    samples differ; CLEAN equals the base sample for sample; every condition has its own code."""
    spec = datasets.DATASETS["Kalunga2016"]
    base = _base()
    reference = base.get_data([1])
    codes = set()
    for condition in (CLEAN, Condition("line_noise", 2), Condition("channels", 5), Condition("artifacts", 1)):
        view = datasets.degraded_dataset(spec, condition, base)
        codes.add(view.code)
        for attribute in ("subject_list", "event_id", "interval", "paradigm", "n_sessions", "unit_factor"):
            assert getattr(view, attribute) == getattr(base, attribute), attribute
        data = view.get_data([1])
        assert data.keys() == reference.keys() and data[1].keys() == reference[1].keys()
        for session, runs in reference[1].items():
            assert data[1][session].keys() == runs.keys()
            for run, raw in runs.items():
                out = data[1][session][run]
                assert out.ch_names == raw.ch_names and out.get_channel_types() == raw.get_channel_types()
                assert out.n_times == raw.n_times and out.info["sfreq"] == raw.info["sfreq"]
                assert list(out.annotations.description) == list(raw.annotations.description)
                np.testing.assert_array_equal(out.annotations.onset, raw.annotations.onset)
                assert out.get_montage().ch_names == raw.get_montage().ch_names
                same = out.get_data(picks=["stim"]).tobytes() == raw.get_data(picks=["stim"]).tobytes()
                assert same
                eeg_equal = out.get_data(picks="eeg").tobytes() == raw.get_data(picks="eeg").tobytes()
                assert eeg_equal == (condition == CLEAN), condition
    assert len(codes) == 4 and base.code not in codes


def test_degraded_view_is_deterministic_and_picklable() -> None:
    spec = datasets.DATASETS["Kalunga2016"]
    view = datasets.degraded_dataset(spec, Condition("artifacts", 3), _base())
    first = view.get_data([1])[1]["0"]["0"].get_data()
    again = pickle.loads(pickle.dumps(view)).get_data([1])[1]["0"]["0"].get_data()
    other = datasets.degraded_dataset(spec, Condition("artifacts", 3), _base()).get_data([1])[1]["0"]["0"]
    assert first.tobytes() == again.tobytes() == other.get_data().tobytes()


@pytest.mark.parametrize("name", sorted(datasets.DATASETS))
def test_moabb_paradigms_accept_the_view(name: str) -> None:
    """Every MOABB paradigm that accepts the base accepts the view (A-103: degraded before filter and
    epoching), with the same trials and labels."""
    spec = datasets.DATASETS[name]
    base = _base(name)
    paradigm = MotorImagery(n_classes=len(spec.events)) if spec.paradigm == "imagery" else SSVEP()
    view = datasets.degraded_dataset(spec, CONDITIONS[-1], base)
    assert paradigm.is_valid(base) and paradigm.is_valid(view)
    x_base, y_base, meta_base = paradigm.get_data(base, [1])
    x_view, y_view, meta_view = paradigm.get_data(view, [1])
    assert x_view.shape == x_base.shape and list(y_view) == list(y_base)
    assert meta_view.equals(meta_base)
    assert not np.array_equal(x_view, x_base)
