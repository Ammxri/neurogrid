"""Evaluation within the session (A-104, F6 A; area C "decoders and evaluation").

Training and test in the same condition (NeuroGrid checks training data: a dataset of level Qx allows a model
of accuracy y). 5 folds within each session (StratifiedKFold, shuffled, seeded), as the MOABB standard, for
all three datasets. Metric: accuracy (PRD), with the chance level per dataset; averaged over the sessions with
a 95 % bootstrap interval (seeded). MOABB supplies data and paradigms; the cross-validation is NeuroArena's
own so that seeds and caches stay under control (A-104).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from neuroarena import determinism
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
    import numpy as np
    from sklearn.model_selection import StratifiedKFold

    y = np.asarray(y)
    _, counts = np.unique(y, return_counts=True)
    if len(counts) == 0 or counts.min() < N_FOLDS:
        raise ValueError(f"every class needs at least {N_FOLDS} trials, got {counts.tolist()}")
    splitter = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
    return list(splitter.split(np.zeros(len(y)), y))


def accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Share of correctly predicted test trials."""
    import numpy as np

    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    if y_true.shape != y_pred.shape or y_true.size == 0:
        raise ValueError("accuracy needs two non-empty label arrays of the same shape")
    return float(np.count_nonzero(y_true == y_pred) / y_true.size)


def chance_level(y: np.ndarray) -> float:
    """The chance level of a session's labels: the share of the most frequent class (1 / number of classes
    for balanced classes; confirmed by the lead on 2026-11-02)."""
    import numpy as np

    _, counts = np.unique(np.asarray(y), return_counts=True)
    if len(counts) == 0:
        raise ValueError("no labels")
    return float(counts.max() / counts.sum())


def encode_labels(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(classes, codes): the sorted distinct labels and every label as its int64 index among them. EEGNet's
    cross-entropy needs such codes; CSP+LDA and the accuracy do not change under the encoding."""
    import numpy as np

    classes, codes = np.unique(np.asarray(y), return_inverse=True)
    return classes, codes.astype(np.int64)


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
    (fold 0-4), with ``fit_seconds`` measured but never compared.

    The labels are encoded with ``encode_labels`` before the split; ``determinism.seed_everything`` runs with
    ``seed`` before the split and with the fold seed right before every fit."""
    import numpy as np

    if len(X) != len(y):
        raise ValueError(f"{len(X)} trials but {len(y)} labels")
    _, codes = encode_labels(y)
    determinism.seed_everything(seed)
    records = []
    for fold, (train, test) in enumerate(folds(codes, seed)):
        fold_seed = determinism.derive_seed(seed, fold)
        estimator = make_decoder(fold_seed)
        determinism.seed_everything(fold_seed)
        start = time.perf_counter()
        estimator.fit(X[train], codes[train])
        fit_seconds = time.perf_counter() - start
        predicted = np.asarray(estimator.predict(X[test]))
        n_correct = int(np.count_nonzero(predicted == codes[test]))
        records.append(
            FoldRecord(
                dataset=session.dataset,
                condition=condition.id,
                kind=condition.kind,
                level=condition.level,
                subject=session.subject,
                session=session.session,
                decoder=decoder,
                fold=fold,
                seed=fold_seed,
                n_train=len(train),
                n_test=len(test),
                n_correct=n_correct,
                accuracy=n_correct / len(test),
                fit_seconds=fit_seconds,
            )
        )
    return records


def bootstrap_ci(values: Sequence[float], seed: int) -> tuple[float, float]:
    """The ``CONFIDENCE`` percentile interval of the mean of ``values`` from ``BOOTSTRAP_RESAMPLES``
    resamples with replacement (numpy Generator from ``seed``); (nan, nan) for fewer than two values.

    The resamples are drawn in blocks of at most 1000 (one ``integers`` call per block, in order), the
    percentiles with numpy's default linear interpolation."""
    import numpy as np

    data = np.asarray(values, dtype=np.float64)
    if data.size < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = np.empty(BOOTSTRAP_RESAMPLES)
    block = 1000
    for start in range(0, BOOTSTRAP_RESAMPLES, block):
        count = min(block, BOOTSTRAP_RESAMPLES - start)
        means[start : start + count] = data[rng.integers(0, data.size, size=(count, data.size))].mean(axis=1)
    tail = (1.0 - CONFIDENCE) / 2.0 * 100.0
    low, high = np.percentile(means, [tail, 100.0 - tail])
    return (float(low), float(high))
