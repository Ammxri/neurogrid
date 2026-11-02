"""Controlled degradation in five levels per kind (NA-03; F4, A-103; area B "data and quality").

One ladder per kind (F4a A): line noise, channels, artefacts, each with levels 1-5; level 0 is the clean data.
The level values (F4c) are fixed before the first run and never adapted to results. The degradation acts on
the raw signal (MNE Raw, volts) before filtering and epoching, on the EEG channels only; montage, channel
set, annotations and events stay (F4b A: a removed channel is flat, the montage stays).

Seeds (A-103): one ``numpy.random.SeedSequence`` per (dataset, subject, session, run, kind, level), see
``seed_sequence``. The same key and condition give byte-identical data in every call and process.

Values the drafts leave open are marked OPEN below: area B proposes them with its first commit, the lead
fixes them before the first run (F4c), and they never change after it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from neuroarena.keys import Condition, RecordingKey

if TYPE_CHECKING:
    import mne
    import numpy as np

# --- line noise (F4c row "Netzbrummen") ------------------------------------------------------------------
# Power of the added line-frequency sinusoid relative to the channel's power in LINE_NOISE_REFERENCE_BAND_HZ,
# in dB, for levels 1-5. The threshold of M07 (0.41) lies near -3.9 dB (draft F4c).
LINE_NOISE_DB = (-15.0, -10.0, -5.0, 0.0, 10.0)
LINE_NOISE_REFERENCE_BAND_HZ = (1.0, 40.0)
# The first harmonic (2 x line frequency) with half the amplitude of the fundamental, only below Nyquist.
LINE_NOISE_HARMONIC_AMPLITUDE = 0.5
# The phase of the sinusoid is drawn per channel from the recording's seed (uniform in [0, 2 pi)).

# --- channels (F4c row "Kanäle") -------------------------------------------------------------------------
# k = max(CHANNEL_MINIMUMS[level - 1], round_half_up(CHANNEL_FRACTIONS[level - 1] * n)) EEG channels of a
# recording, drawn per recording from its seed, are set to 0 V (flat, F4b A). 8 channels: 1, 2, 3, 4, 5;
# 14: 1, 2, 3, 5, 7; 64: 3, 6, 13, 22, 32 (F4c). Ties never occur for 8, 14 and 64 channels; the scaffold
# reads the draft's nearest-integer brackets as rounding half up.
CHANNEL_FRACTIONS = (0.05, 0.10, 0.20, 0.35, 0.50)
CHANNEL_MINIMUMS = (1, 2, 3, 4, 5)
FLAT_VALUE_V = 0.0

# --- artefacts (F4c row "Artefakte") ---------------------------------------------------------------------
# A share of the non-overlapping 2-s epochs of a recording (from its first sample; a shorter rest at the end
# is no epoch) receives one additive artefact each, the three types in equal parts: eye blinks (frontal
# emphasis, 100-200 uV), muscle (band 20 Hz to Nyquist - 5 Hz), electrode pops (100-300 uV with decay). The
# threshold of M09a (0.305) lies between levels 3 and 4 (draft F4c).
ARTIFACT_FRACTIONS = (0.05, 0.10, 0.20, 0.35, 0.50)
ARTIFACT_EPOCH_S = 2.0
ARTIFACT_TYPES = ("blink", "muscle", "pop")
BLINK_AMPLITUDE_UV = (100.0, 200.0)
POP_AMPLITUDE_UV = (100.0, 300.0)
MUSCLE_LOW_HZ = 20.0
MUSCLE_NYQUIST_MARGIN_HZ = 5.0
# OPEN (not in F4c): the amplitude of the muscle artefact, the shape and length of a blink and the weight of
# a channel by its frontal position, the decay time of a pop and the channel(s) it hits, and how the epochs
# of a level are split into the three types when their number is not divisible by 3.
MUSCLE_AMPLITUDE_UV: tuple[float, float] | None = None
BLINK_DURATION_S: float | None = None
POP_DECAY_S: float | None = None


def seed_sequence(key: RecordingKey, condition: Condition) -> np.random.SeedSequence:
    """The seed of one recording and condition (A-103), the same in every process and on every machine:
    ``numpy.random.SeedSequence(int.from_bytes(sha256(text).digest(), "big"))`` with ``text`` the UTF-8 of
    ``"neuroarena|{dataset}|{subject}|{session}|{run}|{kind}|{level}"`` (the fields of ``key`` and
    ``condition``; subject and level as decimal integers). Python's ``hash`` is never used."""
    raise NotImplementedError("area B")


def flattened_channel_count(n_eeg_channels: int, level: int) -> int:
    """Number of EEG channels set flat at ``level`` (1-5) for a recording with ``n_eeg_channels``; never more
    than ``n_eeg_channels``."""
    raise NotImplementedError("area B")


def artifact_epoch_count(n_epochs: int, level: int) -> int:
    """Number of 2-s epochs that receive an artefact at ``level`` (1-5): round half up of
    ``ARTIFACT_FRACTIONS[level - 1] * n_epochs``."""
    raise NotImplementedError("area B")


def degrade(
    raw: mne.io.BaseRaw, key: RecordingKey, condition: Condition, line_frequency_hz: float
) -> mne.io.BaseRaw:
    """A degraded copy of ``raw`` (never modified in place).

    Invariants (tests of area B, draft section 4, NA-03):
    - ``condition`` level 0 (clean): the copy equals ``raw`` sample for sample (identity).
    - Deterministic: two calls with equal arguments give byte-identical data (``seed_sequence``).
    - Monotone within a kind: the amount grows with the level (LINE_NOISE_DB, ``flattened_channel_count``,
      ``artifact_epoch_count``). Each level draws from its own seed (A-103), so the channels or epochs of
      level n need not be among those of level n + 1.
    - Only EEG channels change; sampling rate, channel names and types, montage, annotations and the length
      stay. Line noise uses ``line_frequency_hz`` of the dataset (A-101).
    """
    raise NotImplementedError("area B")
