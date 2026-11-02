"""Synthetic stand-ins of the approved datasets, without any download (F11 B smoke runs and the tests;
draft section 4: "the synthetic data are a generator as in KONZEPT 4"; area B "data and quality").

The runner's smoke mode (area C) and the integration tests of areas B and C use these instead of the MOABB
loaders. They never touch ``paths.MNE_DATA``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from neuroarena.datasets import DatasetSpec

if TYPE_CHECKING:
    from moabb.datasets.base import BaseDataset

SMOKE_SUBJECTS = 2
# NeuroGrid measures M06 and M09 only on >= 60 s of usable data (A-79); a smoke run must reach that.
MIN_RUN_SECONDS = 60.0


def fake_dataset(spec: DatasetSpec, n_subjects: int = SMOKE_SUBJECTS, seed: int = 0) -> BaseDataset:
    """A MOABB dataset shaped like ``spec`` without any download: ``spec.paradigm``, ``spec.events``,
    ``spec.n_eeg_channels`` EEG channels with names of the MOABB standard montage, ``spec.sampling_rate_hz``,
    runs of at least ``MIN_RUN_SECONDS`` and enough trials per class for 5-fold stratified CV in every
    session; deterministic for ``seed``. Built on ``moabb.datasets.fake.FakeDataset`` or an equivalent
    ``BaseDataset``. Not separable by design: decoders score near chance on it (area C builds its own
    separable data for its tests)."""
    raise NotImplementedError("area B")
