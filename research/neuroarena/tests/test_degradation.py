"""NA-03 (unit): the degradation ladders are seeded per recording and condition (A-103), byte-identical in
every process, the identity at level 0, monotone within a kind, and touch only the EEG samples (F4)."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from _signals import EEG, small_raw
from neuroarena import degradation
from neuroarena.keys import CLEAN, CONDITIONS, KINDS, LEVELS, Condition, RecordingKey

KEY = RecordingKey("Zhou2016", 1, "0", "1")
TESTS = Path(__file__).resolve().parent


def _eeg(raw) -> np.ndarray:
    return raw.get_data(picks="eeg")


def test_seed_encoding_has_fixed_values() -> None:
    """A-103: SHA-256 of "neuroarena|dataset|subject|session|run|kind|level", big endian, as the entropy of a
    SeedSequence. The values are fixed: a change of the encoding changes every degraded run."""
    seeds = degradation.seed_sequence(KEY, Condition("line_noise", 3))
    assert seeds.entropy == 0xF456D43076BDA980B6CC4B5D5D338041701234D629D94AF22B06406CAAFD6B75
    assert seeds.generate_state(2).tolist() == [3220626876, 1622737878]
    text = b"neuroarena|Zhou2016|1|0|1|line_noise|3"
    assert seeds.entropy == int.from_bytes(hashlib.sha256(text).digest(), "big")
    clean = degradation.seed_sequence(RecordingKey("Cho2017", 52, "0", "0"), CLEAN)
    assert clean.entropy == 0xD32364FC7BE372359337DA4562D482F7B9373D5EFF6AB4302F9B16B9B26522A0
    entropies = {
        degradation.seed_sequence(key, condition).entropy
        for key in (KEY, RecordingKey("Zhou2016", 1, "0", "0"), RecordingKey("Zhou2016", 2, "0", "1"))
        for condition in CONDITIONS
    }
    assert len(entropies) == 3 * len(CONDITIONS)


def test_flattened_channel_count_table() -> None:
    """F4c: k = max(minimum, round half up(fraction * n)), at most n."""
    table = {8: (1, 2, 3, 4, 5), 14: (1, 2, 3, 5, 7), 64: (3, 6, 13, 22, 32), 3: (1, 2, 3, 3, 3), 0: (0,) * 5}
    for channels, expected in table.items():
        assert tuple(degradation.flattened_channel_count(channels, level) for level in LEVELS) == expected
    # ties round up (0.10 * 15 = 1.5 -> 2; 0.50 * 13 = 6.5 -> 7)
    assert degradation.flattened_channel_count(15, 2) == 2
    assert degradation.flattened_channel_count(13, 5) == 7
    for bad in (0, 6, True):
        with pytest.raises(ValueError):
            degradation.flattened_channel_count(14, bad)


def test_artifact_epoch_count_rounds_half_up() -> None:
    assert [degradation.artifact_epoch_count(45, level) for level in LEVELS] == [2, 5, 9, 16, 23]
    assert [degradation.artifact_epoch_count(10, level) for level in LEVELS] == [1, 1, 2, 4, 5]
    assert degradation.artifact_epoch_count(0, 5) == 0
    with pytest.raises(ValueError):
        degradation.artifact_epoch_count(10, 0)
    assert degradation.artifact_type_counts(0) == (0, 0, 0)
    assert degradation.artifact_type_counts(1) == (1, 0, 0)
    assert degradation.artifact_type_counts(5) == (2, 2, 1)
    assert degradation.artifact_type_counts(9) == (3, 3, 3)


def test_level_0_is_identity() -> None:
    raw = small_raw()
    before = raw.get_data().copy()
    out = degradation.degrade(raw, KEY, CLEAN, 50.0)
    assert out is not raw
    assert out.get_data().tobytes() == before.tobytes()
    assert raw.get_data().tobytes() == before.tobytes()


def test_degradation_is_seeded_and_byte_identical() -> None:
    """Two calls give the same bytes; another run (seed) gives other data; the input is never changed."""
    raw = small_raw()
    before = raw.get_data().tobytes()
    for condition in CONDITIONS[1:]:
        first = degradation.degrade(raw, KEY, condition, 50.0).get_data()
        second = degradation.degrade(raw, KEY, condition, 50.0).get_data()
        other = degradation.degrade(raw, RecordingKey("Zhou2016", 1, "0", "0"), condition, 50.0).get_data()
        assert first.tobytes() == second.tobytes(), condition
        assert first.tobytes() != before, condition
        assert first.tobytes() != other.tobytes(), condition
    assert raw.get_data().tobytes() == before


def _digests() -> dict[str, str]:
    raw = small_raw()
    return {
        condition.id: hashlib.sha256(
            degradation.degrade(raw, KEY, condition, 50.0).get_data().tobytes()
        ).hexdigest()
        for condition in CONDITIONS
    }


def test_degradation_is_byte_identical_in_a_fresh_process() -> None:
    """A-103: the same in every process, whatever PYTHONHASHSEED (Python's hash is never used)."""
    probe = (
        "import sys, json\n"
        f"sys.path.insert(0, {str(TESTS)!r})\n"
        "from test_degradation import _digests\n"
        "print(json.dumps(_digests()))\n"
    )
    env = {**os.environ, "PYTHONHASHSEED": "12345"}
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, encoding="utf-8", env=env, check=True
    )
    import json

    assert json.loads(result.stdout.strip().splitlines()[-1]) == _digests()


def test_levels_are_monotone() -> None:
    """The amount grows with the level: line-noise power, number of flat channels, number of artefact
    epochs."""
    raw = small_raw()
    clean = _eeg(raw)
    sfreq = raw.info["sfreq"]
    epoch = round(degradation.ARTIFACT_EPOCH_S * sfreq)
    n_epochs = raw.n_times // epoch
    for kind in KINDS:
        amounts = []
        for level in LEVELS:
            data = _eeg(degradation.degrade(raw, KEY, Condition(kind, level), 50.0))
            if kind == "line_noise":
                added = degradation.band_power(data - clean, sfreq, (49.0, 51.0))
                reference = degradation.band_power(clean, sfreq, degradation.LINE_NOISE_REFERENCE_BAND_HZ)
                ratio = added / reference
                expected = 10 ** (degradation.LINE_NOISE_DB[level - 1] / 10)
                np.testing.assert_allclose(ratio, expected, rtol=0.02)
                amounts.append(float(np.median(ratio)))
            elif kind == "channels":
                flat = np.flatnonzero((data == degradation.FLAT_VALUE_V).all(axis=1))
                assert len(flat) == degradation.flattened_channel_count(len(EEG), level)
                amounts.append(len(flat))
            else:
                changed = (data != clean).reshape(len(EEG), -1)[:, : n_epochs * epoch]
                hit = changed.reshape(len(EEG), n_epochs, epoch).any(axis=(0, 2))
                assert hit.sum() == degradation.artifact_epoch_count(n_epochs, level)
                assert not (data != clean)[:, n_epochs * epoch :].any()  # the rest is no epoch
                amounts.append(int(hit.sum()))
        assert amounts == sorted(amounts) and amounts[0] < amounts[-1], (kind, amounts)


def test_only_eeg_samples_change() -> None:
    """Rate, names, types, montage, annotations, length and the non-EEG channels stay (F4b A)."""
    raw = small_raw()
    eeg = [raw.ch_names.index(name) for name in EEG]
    others = [index for index in range(len(raw.ch_names)) if index not in eeg]
    for condition in CONDITIONS[1:]:
        out = degradation.degrade(raw, KEY, condition, 50.0)
        assert out.info["sfreq"] == raw.info["sfreq"] and out.n_times == raw.n_times
        assert out.ch_names == raw.ch_names and out.get_channel_types() == raw.get_channel_types()
        assert (
            out.get_montage().get_positions()["ch_pos"].keys()
            == raw.get_montage().get_positions()["ch_pos"].keys()
        )
        for name, position in raw.get_montage().get_positions()["ch_pos"].items():
            np.testing.assert_array_equal(out.get_montage().get_positions()["ch_pos"][name], position)
        assert list(out.annotations.description) == list(raw.annotations.description)
        np.testing.assert_array_equal(out.annotations.onset, raw.annotations.onset)
        assert out.get_data(picks=others).tobytes() == raw.get_data(picks=others).tobytes()


def test_line_noise_harmonic_only_below_nyquist() -> None:
    raw = small_raw()
    out = degradation.degrade(raw, KEY, Condition("line_noise", 5), 50.0)
    added = _eeg(out) - _eeg(raw)
    sfreq = raw.info["sfreq"]
    fundamental = degradation.band_power(added, sfreq, (49.0, 51.0))
    harmonic = degradation.band_power(added, sfreq, (99.0, 101.0))
    np.testing.assert_allclose(
        harmonic / fundamental, degradation.LINE_NOISE_HARMONIC_AMPLITUDE**2, rtol=0.02
    )
    slow = small_raw(sfreq=200.0)  # 2 x 60 Hz lies above the Nyquist frequency of 100 Hz
    added = _eeg(degradation.degrade(slow, KEY, Condition("line_noise", 5), 60.0)) - _eeg(slow)
    total = degradation.band_power(added, 200.0, (0.0, 100.0))
    np.testing.assert_allclose(degradation.band_power(added, 200.0, (59.0, 61.0)), total, rtol=1e-6)
    with pytest.raises(ValueError):
        degradation.degrade(slow, KEY, Condition("line_noise", 1), 100.0)


def test_blinks_are_frontal() -> None:
    raw = small_raw()
    positions = np.array([raw.info["chs"][raw.ch_names.index(name)]["loc"][:3] for name in EEG])
    weights = dict(zip(EEG, degradation.blink_weights(positions), strict=True))
    assert weights["Fp1"] > 0.95 and weights["Fp2"] > 0.95
    assert weights["Fp1"] > weights["Fz"] > weights["Cz"] > weights["Pz"] > weights["Oz"] > 0
    assert 0.4 < weights["Fz"] < 0.8 and weights["Oz"] < 0.1
    unknown = degradation.blink_weights(np.array([[np.nan, np.nan, np.nan], [0.0, 0.0, 0.0]]))
    expected = np.exp(
        -(degradation.BLINK_REFERENCE_Y_M - degradation.BLINK_UNKNOWN_Y_M) / degradation.BLINK_FALLOFF_M
    )
    np.testing.assert_allclose(unknown, expected)


def test_muscle_bursts_are_generalised_and_correlated() -> None:
    """Six muscle sources around the head with broad topographies (each peaks at 1): the burst reaches every
    channel, and the channels share six time courses (correlated, unlike independent noise per channel)."""
    raw = small_raw()
    positions = np.array([raw.info["chs"][raw.ch_names.index(name)]["loc"][:3] for name in EEG])
    topographies = degradation.muscle_topographies(positions)
    assert topographies.shape == (len(degradation.MUSCLE_SOURCE_AZIMUTHS_DEG), len(EEG))
    np.testing.assert_allclose(np.abs(topographies).max(axis=1), 1.0)
    load = np.sqrt((topographies**2).sum(axis=0))
    assert (load > 1.0).all() and (load < np.sqrt(len(topographies))).all()
    assert np.linalg.matrix_rank(topographies) == len(degradation.MUSCLE_SOURCE_AZIMUTHS_DEG) < len(EEG)
    unknown = np.vstack([positions[:3], [[np.nan] * 3]])
    weights = degradation.muscle_topographies(unknown)
    np.testing.assert_allclose(weights[:, 3], np.abs(weights[:, :3]).mean(axis=1))
    np.testing.assert_array_equal(degradation.muscle_topographies(np.zeros((2, 3))), 1.0)


def test_open_artefact_values_are_set() -> None:
    """The values F4c leaves open are numbers (proposed by area B, fixed by the lead before the first run)."""
    assert degradation.MUSCLE_AMPLITUDE_UV == (20.0, 50.0)
    assert degradation.BLINK_DURATION_S == 0.4 and degradation.BLINK_FALLOFF_M == 0.06
    assert degradation.POP_DECAY_S == 0.3 and degradation.POP_CHANNELS == 1
