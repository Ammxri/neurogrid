"""Small deterministic MNE raws for the unit tests of area B (no download, no NeuroGrid). Also imported by
a fresh process in ``test_degradation`` (cross-process byte identity), so it depends on nothing but numpy and
mne."""

from __future__ import annotations

import warnings

import mne
import numpy as np

EEG = ("Fp1", "Fp2", "F3", "Fz", "F4", "C3", "Cz", "C4", "P3", "Pz", "P4", "O1", "Oz", "O2")


def small_raw(sfreq: float = 250.0, seconds: float = 21.0, seed: int = 7) -> mne.io.RawArray:
    """14 EEG channels (10-20 names with the standard montage), one EOG and one stim channel, two
    annotations; EEG of about 15 uV, volts. ``seconds`` = 21 gives ten 2-s epochs and a rest of 1 s."""
    rng = np.random.default_rng(seed)
    n = round(seconds * sfreq)
    mixing = rng.standard_normal((len(EEG), 6))
    eeg = mixing @ rng.standard_normal((6, n)) * 6e-6 + rng.standard_normal((len(EEG), n)) * 2e-6
    eog = rng.standard_normal((1, n)) * 30e-6
    stim = np.zeros((1, n))
    stim[0, [round(2 * sfreq), round(9 * sfreq)]] = (1, 2)
    names = [*EEG, "EOG1", "STI"]
    info = mne.create_info(names, sfreq, ["eeg"] * len(EEG) + ["eog", "stim"])
    raw = mne.io.RawArray(np.vstack([eeg, eog, stim]), info, verbose="error")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        raw.set_montage(mne.channels.make_standard_montage("standard_1005"), verbose="error")
    raw.set_annotations(mne.Annotations([2.0, 9.0], [3.0, 3.0], ["left_hand", "right_hand"]))
    return raw
