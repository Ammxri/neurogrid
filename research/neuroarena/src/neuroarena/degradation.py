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

import hashlib
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from neuroarena.keys import CLEAN_KIND, LEVELS, Condition, RecordingKey

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
# OPEN in F4c, proposed by area B (2026-11-02), fixed by the lead before the first run. Every artefact lies
# inside its 2-s epoch; amplitudes are drawn uniformly per artefact from the given ranges.
#
# Blink: a positive Hann pulse of BLINK_DURATION_S (half-amplitude width 0.2 s; blinks last about 0.1-0.4 s,
# lead choice within that range), BLINK_AMPLITUDE_UV at the frontal pole, falling off towards the back of the
# head by exp(-(BLINK_REFERENCE_Y_M - y) / BLINK_FALLOFF_M) on the anterior coordinate y of the channel (head
# frame; at most 1): about 0.6-0.7 at F3/Fz, 0.2 at C3/Cz, 0.07 at Pz and 0.04 at O1, the order of the
# published propagation of blinks from frontal to posterior sites (e.g. Croft & Barry 2000; exact value: lead
# choice).
BLINK_DURATION_S = 0.4
BLINK_FALLOFF_M = 0.06
# Anterior coordinate of Fp1/Fp2 in the head frame of MNE's standard 10-05 montage (0.115 m).
BLINK_REFERENCE_Y_M = 0.115
# A channel without a finite position counts as central (y = 0): a weight of about 0.15 (lead choice).
BLINK_UNKNOWN_Y_M = 0.0
# Muscle: a generalised EMG burst of MUSCLE_DURATION_S with a Tukey taper, as during jaw clenching, frowning
# or a head movement, when the frontalis, both temporales and the neck muscles contaminate most scalp channels
# (e.g. Goncharova et al. 2003). Six sources (MUSCLE_SOURCE_AZIMUTHS_DEG) on a ring MUSCLE_SOURCE_DISTANCE_M
# from MUSCLE_HEAD_CENTRE_M, slightly below its equator (MUSCLE_SOURCE_ELEVATION), each a radial current
# dipole in an infinite homogeneous medium with its own band-limited Gaussian time course (MUSCLE_LOW_HZ to
# Nyquist - MUSCLE_NYQUIST_MARGIN_HZ); each topography is scaled to a maximum magnitude of 1 over the EEG
# channels of the recording. The sources lie deep enough that every topography is broad: on the 14 channels
# of Zhou2016 each channel gets 0.1-1 of a source's maximum, so the burst reaches the whole head.
# MUSCLE_AMPLITUDE_UV is the RMS of a source's time course before the taper, i.e. the RMS it gives its most
# affected channel; surface EMG in scalp EEG reaches tens of microvolts (lead choice of the range).
# Measured on synthetic data (2026-11-02): independent noise per channel makes pyprep flag every channel by
# correlation after a single burst, and a burst of the two temporales alone is interpolated by autoreject on
# 14 channels, so M09a would not see it; this broad burst raises M09a with the artefact share.
MUSCLE_AMPLITUDE_UV = (20.0, 50.0)
MUSCLE_DURATION_S = 1.0
MUSCLE_TAPER = 0.2  # share of the burst in the cosine flanks of the Tukey window
MUSCLE_HEAD_CENTRE_M = (0.0, 0.015, 0.039)  # centre of a sphere fitted to the 10-05 positions (head frame)
MUSCLE_SOURCE_DISTANCE_M = 0.06
# Azimuth from the right (+x) towards the front (+y): right front, front, left front, left back, back, right
# back; the elevation is the z component of the direction before it is normalised.
MUSCLE_SOURCE_AZIMUTHS_DEG = (30.0, 90.0, 150.0, 210.0, 270.0, 330.0)
MUSCLE_SOURCE_ELEVATION = -0.2
# Channels without a finite position get the mean weight of the others; without any position, weight 1.
# Electrode pop: a step of POP_AMPLITUDE_UV (random sign) on POP_CHANNELS EEG channel(s) at a random onset in
# the first half of the epoch, decaying exponentially with the time constant POP_DECAY_S, shifted so that it
# reaches exactly 0 at the end of the epoch (no step at the epoch border). A pop is a single-electrode event
# (sudden impedance change) that recovers within a few hundred milliseconds (lead choice).
POP_DECAY_S = 0.3
POP_CHANNELS = 1
POP_ONSET_SHARE = 0.5
# Split of the k artefact epochs of a level into the three types: k // 3 each, and the k % 3 left over go to
# the first types of ARTIFACT_TYPES (blink, then muscle). The epochs are drawn in a random order and take the
# types in that order, so which epoch gets which type is random as well.


def seed_sequence(key: RecordingKey, condition: Condition) -> np.random.SeedSequence:
    """The seed of one recording and condition (A-103), the same in every process and on every machine:
    ``numpy.random.SeedSequence(int.from_bytes(sha256(text).digest(), "big"))`` with ``text`` the UTF-8 of
    ``"neuroarena|{dataset}|{subject}|{session}|{run}|{kind}|{level}"`` (the fields of ``key`` and
    ``condition``; subject and level as decimal integers). Python's ``hash`` is never used."""
    import numpy as np

    text = (
        f"neuroarena|{key.dataset}|{int(key.subject)}|{key.session}|{key.run}|"
        f"{condition.kind}|{int(condition.level)}"
    )
    return np.random.SeedSequence(int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest(), "big"))


def _round_half_up(fraction: float, count: int) -> int:
    """``fraction * count`` rounded half up, exactly in decimal (0.35 * 10 is 3.5, not 3.4999...)."""
    product = Decimal(repr(fraction)) * count
    return int(product.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _level_index(level: int) -> int:
    if isinstance(level, bool) or level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}, not {level!r}")
    return level - 1


def flattened_channel_count(n_eeg_channels: int, level: int) -> int:
    """Number of EEG channels set flat at ``level`` (1-5) for a recording with ``n_eeg_channels``; never more
    than ``n_eeg_channels``."""
    index = _level_index(level)
    if n_eeg_channels < 0:
        raise ValueError("the number of channels cannot be negative")
    wanted = max(CHANNEL_MINIMUMS[index], _round_half_up(CHANNEL_FRACTIONS[index], n_eeg_channels))
    return min(n_eeg_channels, wanted)


def artifact_epoch_count(n_epochs: int, level: int) -> int:
    """Number of 2-s epochs that receive an artefact at ``level`` (1-5): round half up of
    ``ARTIFACT_FRACTIONS[level - 1] * n_epochs``."""
    index = _level_index(level)
    if n_epochs < 0:
        raise ValueError("the number of epochs cannot be negative")
    return _round_half_up(ARTIFACT_FRACTIONS[index], n_epochs)


def artifact_type_counts(n_artifacts: int) -> tuple[int, ...]:
    """How many of ``n_artifacts`` epochs get each type of ARTIFACT_TYPES (blink, muscle, pop; see the split
    above)."""
    share, rest = divmod(n_artifacts, len(ARTIFACT_TYPES))
    return tuple(share + (index < rest) for index in range(len(ARTIFACT_TYPES)))


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
    import mne
    import numpy as np

    out = raw.copy()
    if condition.kind == CLEAN_KIND:
        return out
    if not out.preload:
        out.load_data(verbose="error")
    picks = mne.pick_types(out.info, eeg=True, exclude=[])
    if len(picks) == 0:
        return out
    rng = np.random.default_rng(seed_sequence(key, condition))
    data = out._data  # float64 in volts, preloaded
    sfreq = float(out.info["sfreq"])
    if condition.kind == "line_noise":
        data[picks] += _line_noise(data[picks], sfreq, line_frequency_hz, condition.level, rng)
    elif condition.kind == "channels":
        count = flattened_channel_count(len(picks), condition.level)
        flat = np.sort(rng.choice(len(picks), size=count, replace=False))
        data[picks[flat]] = FLAT_VALUE_V
    else:
        positions = np.array([out.info["chs"][pick]["loc"][:3] for pick in picks], dtype=float)
        _add_artifacts(data, picks, positions, sfreq, condition.level, rng)
    return out


def band_power(data: np.ndarray, sfreq: float, band: tuple[float, float]) -> np.ndarray:
    """Power (V^2) of every row of ``data`` in ``band`` (inclusive): Welch with 2-s periodic Hann windows
    without overlap and the mean of every window removed, as NeuroGrid's M07; density times bin width."""
    import numpy as np
    from scipy.signal import welch

    size = min(data.shape[-1], round(2.0 * sfreq))
    freqs, psd = welch(
        data,
        fs=sfreq,
        window="hann",
        nperseg=size,
        noverlap=0,
        detrend="constant",
        scaling="density",
        axis=-1,
    )
    mask = (freqs >= band[0]) & (freqs <= band[1])
    return np.asarray(psd[..., mask].sum(axis=-1) * (freqs[1] - freqs[0]))


def _line_noise(
    data: np.ndarray, sfreq: float, line_hz: float, level: int, rng: np.random.Generator
) -> np.ndarray:
    """The sinusoids to add: power LINE_NOISE_DB relative to the 1-40 Hz power of each channel (a sine of
    amplitude A has the power A^2 / 2), a per-channel phase from the seed, the harmonic at 2 f with
    LINE_NOISE_HARMONIC_AMPLITUDE of the amplitude and twice the phase (phase-locked), only below Nyquist."""
    import numpy as np

    nyquist = sfreq / 2
    if not 0 < line_hz < nyquist:
        raise ValueError(f"line frequency {line_hz} Hz is not below the Nyquist frequency {nyquist} Hz")
    gain = 10.0 ** (LINE_NOISE_DB[_level_index(level)] / 10.0)
    amplitude = np.sqrt(2.0 * gain * band_power(data, sfreq, LINE_NOISE_REFERENCE_BAND_HZ))
    phase = rng.uniform(0.0, 2 * np.pi, size=len(data))
    t = np.arange(data.shape[1]) / sfreq
    added = amplitude[:, None] * np.sin(2 * np.pi * line_hz * t[None, :] + phase[:, None])
    if 2 * line_hz < nyquist:
        added += (LINE_NOISE_HARMONIC_AMPLITUDE * amplitude)[:, None] * np.sin(
            2 * np.pi * 2 * line_hz * t[None, :] + 2 * phase[:, None]
        )
    return np.asarray(added)


def blink_weights(positions: np.ndarray) -> np.ndarray:
    """Frontal emphasis of a blink per channel (``positions``: head frame, m; see BLINK_FALLOFF_M)."""
    import numpy as np

    y = np.where(_known(positions), positions[:, 1], BLINK_UNKNOWN_Y_M)
    return np.asarray(np.minimum(1.0, np.exp(-(BLINK_REFERENCE_Y_M - y) / BLINK_FALLOFF_M)))


def _known(positions: np.ndarray) -> np.ndarray:
    """Rows with a finite position that is not the origin (MNE's ``loc`` of a channel without a position)."""
    import numpy as np

    return np.asarray(np.isfinite(positions).all(axis=1) & (np.abs(positions).sum(axis=1) > 0))


def muscle_topographies(positions: np.ndarray) -> np.ndarray:
    """(sources, channels): the weights of the muscle sources (see MUSCLE_SOURCE_AZIMUTHS_DEG), each with a
    maximum magnitude of 1 over the channels (the sign is that of the dipole's potential)."""
    import numpy as np

    known = _known(positions)
    out = np.ones((len(MUSCLE_SOURCE_AZIMUTHS_DEG), len(positions)))
    if not known.any():
        return out
    centre = np.asarray(MUSCLE_HEAD_CENTRE_M)
    for row, azimuth in enumerate(np.radians(MUSCLE_SOURCE_AZIMUTHS_DEG)):
        direction = np.array([np.cos(azimuth), np.sin(azimuth), MUSCLE_SOURCE_ELEVATION])
        unit = direction / np.linalg.norm(direction)
        diff = positions[known] - (centre + MUSCLE_SOURCE_DISTANCE_M * unit)
        weights = diff @ unit / np.linalg.norm(diff, axis=1) ** 3
        weights /= np.abs(weights).max()
        out[row, known] = weights
        out[row, ~known] = np.abs(weights).mean()
    return out


def _add_artifacts(
    data: np.ndarray,
    picks: np.ndarray,
    positions: np.ndarray,
    sfreq: float,
    level: int,
    rng: np.random.Generator,
) -> None:
    """Add one artefact to each of ``artifact_epoch_count`` drawn 2-s epochs (rows ``picks`` of ``data``)."""
    import numpy as np
    from scipy.signal.windows import tukey

    epoch = round(ARTIFACT_EPOCH_S * sfreq)
    n_epochs = data.shape[1] // epoch
    chosen = rng.choice(n_epochs, size=artifact_epoch_count(n_epochs, level), replace=False)
    counts = artifact_type_counts(len(chosen))
    kinds = [kind for kind, count in zip(ARTIFACT_TYPES, counts, strict=True) for _ in range(count)]
    weights = blink_weights(positions)
    topographies = muscle_topographies(positions)
    blink = np.hanning(round(BLINK_DURATION_S * sfreq))
    muscle_size = round(MUSCLE_DURATION_S * sfreq)
    taper = tukey(muscle_size, MUSCLE_TAPER)
    freqs = np.fft.rfftfreq(muscle_size, 1.0 / sfreq)
    outside = (freqs < MUSCLE_LOW_HZ) | (freqs > sfreq / 2 - MUSCLE_NYQUIST_MARGIN_HZ)
    for index, kind in zip(chosen.tolist(), kinds, strict=True):
        start = index * epoch
        if kind == "blink":
            onset = start + int(rng.integers(0, epoch - len(blink) + 1))
            amplitude = rng.uniform(*BLINK_AMPLITUDE_UV) * 1e-6
            data[picks, onset : onset + len(blink)] += np.outer(weights * amplitude, blink)
        elif kind == "muscle":
            onset = start + int(rng.integers(0, epoch - muscle_size + 1))
            amplitude = rng.uniform(*MUSCLE_AMPLITUDE_UV) * 1e-6
            spectrum = np.fft.rfft(rng.standard_normal((len(topographies), muscle_size)), axis=1)
            spectrum[:, outside] = 0
            courses = np.fft.irfft(spectrum, muscle_size, axis=1)
            courses /= courses.std(axis=1, keepdims=True)
            data[picks, onset : onset + muscle_size] += amplitude * (topographies.T @ courses) * taper
        else:
            onset = int(rng.integers(0, round(POP_ONSET_SHARE * epoch)))
            channels = rng.choice(len(picks), size=min(POP_CHANNELS, len(picks)), replace=False)
            amplitude = rng.uniform(*POP_AMPLITUDE_UV) * 1e-6 * rng.choice((-1.0, 1.0))
            u = np.arange(epoch - onset) / sfreq
            end = (epoch - onset) / sfreq
            shape = (np.exp(-u / POP_DECAY_S) - np.exp(-end / POP_DECAY_S)) / (1 - np.exp(-end / POP_DECAY_S))
            data[picks[np.sort(channels)], start + onset : start + epoch] += amplitude * shape
