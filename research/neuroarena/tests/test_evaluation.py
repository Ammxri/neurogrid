"""Evaluation within the session (A-104, F6 A): folds, accuracy, chance level, bootstrap interval."""

from __future__ import annotations

import math

import numpy as np
import pytest

from neuroarena import determinism, evaluation
from neuroarena.keys import Condition, SessionKey


def test_folds_are_stratified_seeded_and_cover_every_trial() -> None:
    y = np.array(["a"] * 12 + ["b"] * 8)
    splits = evaluation.folds(y, 11)
    assert len(splits) == evaluation.N_FOLDS == 5
    tests = np.concatenate([test for _, test in splits])
    assert sorted(tests.tolist()) == list(range(20))
    for train, test in splits:
        assert set(train).isdisjoint(test)
        assert (y[test] == "a").sum() in (2, 3) and (y[test] == "b").sum() in (1, 2)
    again = evaluation.folds(y, 11)
    assert all(np.array_equal(a[1], b[1]) for a, b in zip(splits, again, strict=True))
    other = evaluation.folds(y, 12)
    assert not all(np.array_equal(a[1], b[1]) for a, b in zip(splits, other, strict=True))


def test_folds_need_five_trials_per_class() -> None:
    with pytest.raises(ValueError, match="at least 5"):
        evaluation.folds(np.array([0] * 10 + [1] * 4), 1)


def test_accuracy_and_chance_level() -> None:
    assert evaluation.accuracy(np.array([1, 2, 3, 4]), np.array([1, 2, 0, 4])) == 0.75
    with pytest.raises(ValueError):
        evaluation.accuracy(np.array([1]), np.array([1, 2]))
    # Lead (2026-11-02): the share of the most frequent class, 1/k for balanced classes.
    assert evaluation.chance_level(np.array(["13", "17", "21", "rest"] * 8)) == 0.25
    assert evaluation.chance_level(np.array(["l"] * 6 + ["r"] * 4)) == 0.6


def test_bootstrap_interval_is_seeded_and_brackets_the_mean() -> None:
    values = [0.5, 0.6, 0.7, 0.8, 0.65, 0.55]
    low, high = evaluation.bootstrap_ci(values, 3)
    assert (low, high) == evaluation.bootstrap_ci(values, 3)
    assert low < sum(values) / len(values) < high and 0.5 <= low and high <= 0.8
    spread = np.random.default_rng(0).uniform(0.3, 0.9, 25).tolist()
    assert evaluation.bootstrap_ci(spread, 3) != evaluation.bootstrap_ci(spread, 4)
    assert all(math.isnan(v) for v in evaluation.bootstrap_ci([0.7], 3))
    assert all(math.isnan(v) for v in evaluation.bootstrap_ci([], 3))
    assert evaluation.BOOTSTRAP_RESAMPLES == 10_000 and evaluation.CONFIDENCE == 0.95


class MajorityOfFirstFeature:
    """A deterministic stand-in estimator: predicts the label whose mean of channel 0 is closest."""

    def __init__(self, seed: int) -> None:
        self.seed = seed

    def fit(self, X: np.ndarray, y: np.ndarray) -> MajorityOfFirstFeature:
        self.labels_ = np.unique(y)
        self.means_ = np.array([X[y == label, 0].mean() for label in self.labels_])
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        feature = X[:, 0].mean(axis=-1)
        return self.labels_[np.abs(feature[:, None] - self.means_[None, :]).argmin(axis=1)]


def test_evaluate_session_gives_one_record_per_fold() -> None:
    rng = np.random.default_rng(0)
    y = np.array(["left_hand", "right_hand", "feet"] * 10)
    X = rng.standard_normal((30, 3, 10)) + (np.unique(y, return_inverse=True)[1] * 3.0)[:, None, None]
    seeds = []

    def make(seed: int) -> MajorityOfFirstFeature:
        seeds.append(seed)
        return MajorityOfFirstFeature(seed)

    condition = Condition("artifacts", 2)
    key = SessionKey("Zhou2016", 4, "1")
    rows = evaluation.evaluate_session(X, y, make, key, condition, "csp_lda", 99)
    assert [r.fold for r in rows] == [0, 1, 2, 3, 4]
    assert seeds == [determinism.derive_seed(99, fold) for fold in range(5)] == [r.seed for r in rows]
    assert {(r.dataset, r.condition, r.kind, r.level, r.subject, r.session, r.decoder) for r in rows} == {
        ("Zhou2016", "artifacts-2", "artifacts", 2, 4, "1", "csp_lda")
    }
    assert sum(r.n_test for r in rows) == 30 and all(r.n_train + r.n_test == 30 for r in rows)
    assert all(r.accuracy == r.n_correct / r.n_test for r in rows)
    assert sum(r.n_correct for r in rows) == 30  # the classes are far apart
    again = evaluation.evaluate_session(X, y, make, key, condition, "csp_lda", 99)
    assert [r.n_correct for r in again] == [r.n_correct for r in rows]
