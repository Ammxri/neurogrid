"""Synthetic stand-ins of the approved datasets, without any download (F11 B smoke runs and the tests;
draft section 4: "the synthetic data are a generator as in KONZEPT 4"; area B "data and quality").

The runner's smoke mode (area C) and the integration tests of areas B and C use these instead of the MOABB
loaders. They never touch ``paths.MNE_DATA``.

The signal model follows the quality fixtures of the main project (``tools/gen_fixtures.py``): current dipoles
under the scalp with 1/f activity and alpha bursts, mixed into the channels by their positions in the standard
10-05 montage, every channel rescaled to an EEG-like amplitude, plus white amplifier noise. Neighbouring
channels are therefore correlated (pyprep, M06), the 2-s epochs are stationary (autoreject, M09a) and ICA
finds brain-like components (ICLabel, M09b), so the clean data lie below NeuroGrid's thresholds and the
degradation ladders have room to act. The signal does not depend on the class of a trial: decoders score
near chance.

Shape per subject: ``SESSIONS`` session(s) of ``RUNS_PER_SESSION`` runs, each with
``TRIALS_PER_CLASS_PER_RUN`` trials per class (classes in a shuffled order per block), one trial every
``ceil(interval end) + 1`` s from 1 s, at least ``MIN_RUN_SECONDS`` long. Channel names, sampling rate, line
frequency (``raw.info``) and the epoch interval are those of the MOABB loader of ``spec`` (its METADATA and
its ``interval``, no download); sensors that are not in the montage (Cho2017's EMG1-EMG4) are EMG channels.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

from neuroarena.datasets import DatasetSpec

if TYPE_CHECKING:
    import mne
    import numpy as np
    from moabb.datasets.base import BaseDataset

SMOKE_SUBJECTS = 2
# NeuroGrid measures M06 and M09 only on >= 60 s of usable data (A-79); a smoke run must reach that.
MIN_RUN_SECONDS = 60.0

SESSIONS = 1
RUNS_PER_SESSION = 2  # two runs: the session level is the worst of its runs (F5e)
TRIALS_PER_CLASS_PER_RUN = 5  # 10 per class and session: 5-fold stratified CV has 2 test trials per class
FIRST_TRIAL_S = 1.0
TRIAL_GAP_S = 1.0  # rest after the end of the epoch interval before the next cue
MONTAGE = "standard_1005"  # the montage of the MOABB loaders (Cho2017, Kalunga2016)
SOURCES = 20  # cortical dipoles; as many as NeuroGrid's ICA components (M09b)
SOURCE_DEPTH_M = 0.045  # distance of a dipole from the head centre
HEAD_CENTRE_M = (0.0, 0.015, 0.039)  # centre of a sphere fitted to the 10-05 positions (head frame)
BRAIN_RMS_UV = 15.0  # RMS of a channel, times 0.85-1.15 per channel
AMPLIFIER_NOISE_UV = 2.0  # white noise per channel, times 0.8-1.2
AUXILIARY_RMS_UV = 10.0  # white noise on the non-EEG channels (EMG)
STIM_CHANNEL = "STI"


def fake_dataset(spec: DatasetSpec, n_subjects: int = SMOKE_SUBJECTS, seed: int = 0) -> BaseDataset:
    """A MOABB dataset shaped like ``spec`` without any download: ``spec.paradigm``, ``spec.events``,
    ``spec.n_eeg_channels`` EEG channels with names of the MOABB standard montage, ``spec.sampling_rate_hz``,
    runs of at least ``MIN_RUN_SECONDS`` and enough trials per class for 5-fold stratified CV in every
    session; deterministic for ``seed``. Built on ``moabb.datasets.fake.FakeDataset`` or an equivalent
    ``BaseDataset``. Not separable by design: decoders score near chance on it (area C builds its own
    separable data for its tests)."""
    from neuroarena import _views

    if n_subjects < 1 or seed < 0:
        raise ValueError("n_subjects must be at least 1 and seed not negative")
    return _views.Synthetic(spec, n_subjects, seed)


def loader_layout(spec: DatasetSpec) -> tuple[tuple[str, ...], tuple[str, ...], tuple[float, float]]:
    """(EEG channel names, other sensor names, epoch interval) of the MOABB loader of ``spec``, read from the
    class (METADATA and ``interval``) without any download. ValueError if the number of EEG names is not
    ``spec.n_eeg_channels``."""
    import moabb.datasets

    loader = getattr(moabb.datasets, spec.name)
    montage = set(_montage().ch_names)
    sensors = tuple(loader.METADATA.acquisition.sensors)
    eeg = tuple(name for name in sensors if name in montage)
    other = tuple(name for name in sensors if name not in montage)
    if len(eeg) != spec.n_eeg_channels:
        raise ValueError(f"{spec.name}: {len(eeg)} EEG sensors in the loader, {spec.n_eeg_channels} expected")
    interval = loader().interval
    return eeg, other, (float(interval[0]), float(interval[1]))


def run_layout(spec: DatasetSpec, interval: Sequence[float]) -> tuple[float, float, int]:
    """(run length in s, trial period in s, trials per run) of every synthetic run of ``spec``."""
    period = math.ceil(interval[1]) + TRIAL_GAP_S
    trials = TRIALS_PER_CLASS_PER_RUN * len(spec.events)
    seconds = max(MIN_RUN_SECONDS, math.ceil(FIRST_TRIAL_S + trials * period))
    return float(seconds), float(period), trials


def raw_seed(spec: DatasetSpec, seed: int, subject: int, session: str, run: str) -> np.random.SeedSequence:
    """The seed of one synthetic run (SHA-256 of its fields, as ``degradation.seed_sequence``)."""
    import numpy as np

    text = f"neuroarena-synthetic|{spec.name}|{seed}|{subject}|{session}|{run}"
    return np.random.SeedSequence(int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest(), "big"))


def synthetic_raw(
    spec: DatasetSpec,
    eeg_names: Sequence[str],
    other_names: Sequence[str],
    interval: Sequence[float],
    seeds: np.random.SeedSequence,
) -> mne.io.RawArray:
    """One synthetic run of ``spec`` (volts, MNE): EEG, the other sensors as EMG and a stim channel with one
    event per trial (codes 1..k in the order of ``spec.events``)."""
    import mne
    import numpy as np

    rng = np.random.default_rng(seeds)
    sfreq = float(spec.sampling_rate_hz)
    seconds, period, trials = run_layout(spec, interval)
    n = round(seconds * sfreq)
    positions = _positions(eeg_names, sfreq)
    eeg = _brain(rng, positions, n, sfreq)
    eeg *= (rng.uniform(0.85, 1.15, size=len(eeg_names)) * BRAIN_RMS_UV / eeg.std(axis=1))[:, None]
    eeg += (
        rng.uniform(0.8, 1.2, size=(len(eeg_names), 1)) * AMPLIFIER_NOISE_UV * rng.standard_normal(eeg.shape)
    )
    other = AUXILIARY_RMS_UV * rng.standard_normal((len(other_names), n))
    stim = np.zeros((1, n))
    codes = np.concatenate(
        [rng.permutation(len(spec.events)) + 1 for _ in range(TRIALS_PER_CLASS_PER_RUN)]
    ).astype(float)
    onsets = np.round((FIRST_TRIAL_S + period * np.arange(trials)) * sfreq).astype(int)
    stim[0, onsets] = codes
    names = [*eeg_names, *other_names, STIM_CHANNEL]
    types = ["eeg"] * len(eeg_names) + ["emg"] * len(other_names) + ["stim"]
    info = mne.create_info(names, sfreq, types)
    raw = mne.io.RawArray(np.vstack([eeg * 1e-6, other * 1e-6, stim]), info, verbose="error")
    raw.set_montage(_montage(), on_missing="ignore", verbose="error")
    with raw.info._unlock():
        raw.info["line_freq"] = float(spec.line_frequency_hz)
    return raw


def _montage() -> mne.channels.DigMontage:
    import warnings

    import mne

    with warnings.catch_warnings():  # mne 1.13 renames standard_1005 (colin27_1005); MOABB still uses it
        warnings.simplefilter("ignore", FutureWarning)
        return mne.channels.make_standard_montage(MONTAGE)


def _positions(names: Sequence[str], sfreq: float) -> np.ndarray:
    """Head-frame positions (m) of ``names`` in the montage, as ``set_montage`` puts them into ``info``."""
    import mne
    import numpy as np

    info = mne.create_info(list(names), sfreq, "eeg")
    info.set_montage(_montage(), verbose="error")
    return np.array([channel["loc"][:3] for channel in info["chs"]])


def _band_noise(rng: np.random.Generator, n: int, sfreq: float, low: float, high: float) -> np.ndarray:
    """Gaussian noise with power only between ``low`` and ``high`` Hz, unit standard deviation."""
    import numpy as np

    size = n // 2 + 1
    spectrum = rng.standard_normal(size) + 1j * rng.standard_normal(size)
    freqs = np.fft.rfftfreq(n, 1.0 / sfreq)
    spectrum[(freqs < low) | (freqs > high)] = 0
    noise = np.fft.irfft(spectrum, n)
    return np.asarray(noise / noise.std())


def _pink_noise(rng: np.random.Generator, n: int, sfreq: float) -> np.ndarray:
    """1/f noise without a DC part, unit standard deviation."""
    import numpy as np

    size = n // 2 + 1
    spectrum = rng.standard_normal(size) + 1j * rng.standard_normal(size)
    freqs = np.fft.rfftfreq(n, 1.0 / sfreq)
    spectrum /= np.sqrt(np.maximum(freqs, 0.5))
    spectrum[0] = 0
    noise = np.fft.irfft(spectrum, n)
    return np.asarray(noise / noise.std())


def _brain(rng: np.random.Generator, positions: np.ndarray, n: int, sfreq: float) -> np.ndarray:
    """``SOURCES`` dipoles ``SOURCE_DEPTH_M`` from the head centre (upper half, mostly radial), each with 1/f
    activity and alpha bursts (8-12 Hz under a slow log-normal envelope), mixed into the channels by the
    potential of a current dipole in an infinite homogeneous medium."""
    import numpy as np

    centre = np.asarray(HEAD_CENTRE_M)
    data = np.zeros((len(positions), n))
    for _ in range(SOURCES):
        direction = rng.standard_normal(3)
        direction[2] = abs(direction[2]) + 0.3
        direction /= np.linalg.norm(direction)
        moment = rng.standard_normal(3) + 1.5 * direction
        diff = positions - (centre + SOURCE_DEPTH_M * direction)
        topography = diff @ moment / np.linalg.norm(diff, axis=1) ** 3
        envelope = np.exp(_band_noise(rng, n, sfreq, 0.05, 0.5))
        rhythm = _band_noise(rng, n, sfreq, rng.uniform(8.0, 9.5), rng.uniform(10.5, 12.0)) * envelope
        activity = _pink_noise(rng, n, sfreq) + 1.5 * rhythm / rhythm.std()
        data += np.outer(topography / np.sqrt(np.mean(topography**2)), activity / activity.std())
    return data
