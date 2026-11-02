"""Evaluation within the session (A-104, F6 A; area C "decoders and evaluation").

Training and test in the same condition (NeuroGrid checks training data: a dataset of level Qx allows a model
of accuracy y). 5 folds within each session (StratifiedKFold, shuffled, seeded), as the MOABB standard, for
all three datasets. Metric: accuracy (PRD), with the chance level per dataset; averaged over the sessions with
a 95 % bootstrap interval (seeded). MOABB supplies data and paradigms; the cross-validation is NeuroArena's
own so that seeds and caches stay under control (A-104).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from neuroarena.keys import Condition, SessionKey
from neuroarena.records import FoldRecord

if TYPE_CHECKING:
    import numpy as np

N_FOLDS = 5
CONFIDENCE = 0.95
# Scaffold choice (A-104 names no number): percentile bootstrap with this many resamples; fixed before the
# first run.
BOOTSTRAP_RESAMPLES = 10_000


def folds(y: np.ndarray, seed: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """(train indices, test indices) of ``StratifiedKFold(n_splits=N_FOLDS, shuffle=True,
    random_state=seed)``; ValueError if a class has fewer than N_FOLDS trials."""
    raise NotImplementedError("area C")


def accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Share of correctly predicted test trials."""
    raise NotImplementedError("area C")


def chance_level(y: np.ndarray) -> float:
    """The chance level of a session's labels. OPEN (the drafts name "chance level per dataset" without a
    definition): the scaffold proposes the share of the most frequent class (1 / number of classes for
    balanced classes); the lead confirms before the pilot."""
    raise NotImplementedError("area C")


def evaluate_session(
    X: np.ndarray,
    y: np.ndarray,
    make_decoder: Callable[[int], Any],
    session: SessionKey,
    condition: Condition,
    decoder: str,
    seed: int,
) -> list[FoldRecord]:
    """Fit and test one decoder in the N_FOLDS folds of one session. ``make_decoder(fold_seed)`` returns a
    fresh unfitted estimator; fold seeds are ``determinism.derive_seed(seed, fold)``. One FoldRecord per fold
    (fold 0-4), with ``fit_seconds`` measured but never compared."""
    raise NotImplementedError("area C")


def bootstrap_ci(values: Sequence[float], seed: int) -> tuple[float, float]:
    """The ``CONFIDENCE`` percentile interval of the mean of ``values`` from ``BOOTSTRAP_RESAMPLES``
    resamples with replacement (numpy Generator from ``seed``); (nan, nan) for fewer than two values."""
    raise NotImplementedError("area C")
