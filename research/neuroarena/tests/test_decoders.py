"""NA-04: both decoders train and predict; CSP+LDA for MI and as a filter bank for SSVEP; EEGNet above chance
on separable synthetic data and twice identical on the CPU (A-105, A-106, F7 A)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

import numpy as np
import pytest

from neuroarena import decoders, determinism, evaluation
from neuroarena.datasets import DATASETS
from neuroarena.keys import CLEAN, SessionKey


def variance_coded(n_trials: int, n_classes: int, n_chans: int, n_times: int, seed: int) -> tuple:
    """Trials whose class raises the amplitude of one channel by half (what CSP finds). A moderate effect:
    pyriemann's multiclass CSP ranks its filters by an approximation of the mutual information that holds for
    small variance ratios only."""
    rng = np.random.default_rng(seed)
    codes = np.resize(np.arange(n_classes), n_trials)
    rng.shuffle(codes)
    mixing = np.eye(n_chans) + 0.3 * rng.standard_normal((n_chans, n_chans))
    X = rng.standard_normal((n_trials, n_chans, n_times))
    X[np.arange(n_trials), codes] *= 1.5
    return np.einsum("ij,njt->nit", mixing, X) * 1e-5, codes


def test_paradigms_follow_a105() -> None:
    """MI 8-32 Hz for CSP; 4-40 Hz and 128 Hz for EEGNet; SSVEP filter bank f +- 0.5 Hz; the epochs of the
    dataset's own interval (tmin 0, tmax None); every event of the dataset."""
    from moabb.paradigms import SSVEP, FilterBankSSVEP, MotorImagery

    zhou, kalunga = DATASETS["Zhou2016"], DATASETS["Kalunga2016"]
    mi_csp, mi_net = decoders.paradigm(zhou, "csp_lda"), decoders.paradigm(zhou, "eegnet")
    assert type(mi_csp) is MotorImagery and mi_csp.filters == [[8.0, 32.0]] and mi_csp.resample is None
    assert type(mi_net) is MotorImagery and mi_net.filters == [[4.0, 40.0]] and mi_net.resample == 128.0
    assert mi_csp.events == ["left_hand", "right_hand", "feet"] and mi_csp.n_classes == 3
    ss_csp, ss_net = decoders.paradigm(kalunga, "csp_lda"), decoders.paradigm(kalunga, "eegnet")
    assert type(ss_csp) is FilterBankSSVEP and ss_csp.n_classes == 4 and ss_csp.resample is None
    assert ss_csp.filters == [[12.5, 13.5], [16.5, 17.5], [20.5, 21.5]]
    assert type(ss_net) is SSVEP and ss_net.filters == [(4.0, 40.0)] and ss_net.resample == 128.0
    for p in (mi_csp, mi_net, ss_csp, ss_net):
        assert p.tmin == 0.0 and p.tmax is None
    cho = decoders.paradigm(DATASETS["Cho2017"], "csp_lda")
    assert cho.events == ["left_hand", "right_hand"] and cho.n_classes == 2
    with pytest.raises(ValueError):
        decoders.paradigm(zhou, "lda")


def test_csp_lda_mi_and_filterbank_ssvep(moabb_double: Any) -> None:
    """MOABB "CSP + LDA" (v1.7.2 CSP.yml): OAS covariance, CSP with 6 filters (log-variance), LDA (svd); for
    SSVEP the same blocks per band of the filter bank. Both separate variance-coded classes."""
    zhou, kalunga = DATASETS["Zhou2016"], DATASETS["Kalunga2016"]
    mi = decoders.csp_lda(zhou)
    covariances, csp, lda = (step for _, step in mi.steps)
    assert covariances.estimator == "oas" and csp.nfilter == 6 and csp.log is True and lda.solver == "svd"
    assert decoders.make(zhou, "csp_lda", 1, 1, 1, 0).get_params().keys() == mi.get_params().keys()

    X, codes = variance_coded(90, 3, 14, 200, 1)
    y = np.array(zhou.events)[codes]
    rows = evaluation.evaluate_session(
        X, y, lambda seed: decoders.csp_lda(zhou), SessionKey("Zhou2016", 1, "0"), CLEAN, "csp_lda", 5
    )
    assert sum(r.n_correct for r in rows) / sum(r.n_test for r in rows) > 0.9

    ssvep = decoders.csp_lda(kalunga)
    bank, lda = (step for _, step in ssvep.steps)
    assert bank.flatten is True and lda.solver == "svd"
    band_covariances, band_csp = (step for _, step in bank.estimator.steps)
    assert band_covariances.estimator == "oas" and band_csp.nfilter == 6
    # Separable filter-bank trials: class j < 3 raises channel j in band j only (by half); "rest" none.
    rng = np.random.default_rng(2)
    codes = np.resize(np.arange(4), 80)
    X = rng.standard_normal((80, 8, 128, 3)) * 1e-5
    for i, code in enumerate(codes):
        if code < 3:
            X[i, code, :, code] *= 1.5
    y = np.array(kalunga.events)[codes]
    rows = evaluation.evaluate_session(
        X, y, lambda seed: decoders.csp_lda(kalunga), SessionKey("Kalunga2016", 1, "0"), CLEAN, "csp_lda", 6
    )
    assert sum(r.n_correct for r in rows) / sum(r.n_test for r in rows) > 0.9

    # Through MOABB itself: FilterBankSSVEP gives one band per numeric event as a trailing axis.
    X, labels, metadata = decoders.paradigm(kalunga, "csp_lda").get_data(
        moabb_double(kalunga, n_subjects=1), subjects=[1], cache_config={"use": False}
    )
    assert X.ndim == 4 and X.shape[1] == 8 and X.shape[-1] == 3
    assert set(labels) == set(kalunga.events) and set(metadata["session"]) == {"0", "1"}
    fitted = decoders.csp_lda(kalunga).fit(X, labels)
    assert set(fitted.predict(X)) <= set(kalunga.events)


def tone_coded(n_trials: int, n_chans: int, n_times: int, seed: int) -> tuple:
    """Three classes, each a 10 Hz rhythm of 20 uV with random phase on its own channel, in 10 uV white
    noise, at 128 Hz (EEG amplitudes in volts as MOABB returns them)."""
    rng = np.random.default_rng(seed)
    y = np.resize(np.arange(3), n_trials)
    rng.shuffle(y)
    t = np.arange(n_times) / 128.0
    X = rng.standard_normal((n_trials, n_chans, n_times)) * 10e-6
    phase = rng.uniform(0, 2 * np.pi, n_trials)
    X[np.arange(n_trials), y] += 20e-6 * np.sin(2 * np.pi * 10 * t[None, :] + phase[:, None])
    return X.astype(np.float32), y


def test_eegnet_above_chance_on_separable_data() -> None:
    """EEGNet as configured (braindecode defaults, Adam 1e-3, batches of 16, cross-entropy, input x 1000,
    early stopping on 20 % stratified validation with patience 50, best weights) separates three classes;
    only ``max_epochs`` is lowered to 60 to keep the test short. 240 training trials: 12 batches per epoch."""
    net = decoders.eegnet(4, 3, 128, 7)
    params = net.get_params()
    assert params["module"].__name__ == "EEGNet" and params["module"].__module__.startswith(
        "braindecode.models"
    )
    assert params["optimizer"].__name__ == "Adam" and params["lr"] == 1e-3 and params["batch_size"] == 16
    assert params["criterion"].__name__ == "CrossEntropyLoss" and params["device"] == "cpu"
    assert params["max_epochs"] == 300 and params["iterator_train__drop_last"] is True
    split = params["train_split"]
    assert (split.cv, split.stratified, split.random_state) == (0.2, True, 7)
    stopping = dict(params["callbacks"])["early_stopping"]
    assert (stopping.monitor, stopping.patience, stopping.load_best) == ("valid_loss", 50, True)
    X, y = tone_coded(240, 4, 128, 1)
    X_test, y_test = tone_coded(90, 4, 128, 2)
    net.set_params(max_epochs=60)
    determinism.seed_everything(7)
    net.fit(X, y)
    assert evaluation.accuracy(y_test, net.predict(X_test)) > 0.8  # chance: 1/3


FINGERPRINT = """
import hashlib, json, sys
import numpy as np
from neuroarena import decoders, determinism
determinism.check_environment()
rng = np.random.default_rng(3)
y = np.resize(np.arange(3), 60)
X = (rng.standard_normal((60, 4, 128)) * 1e-5).astype(np.float32)
X[np.arange(60), y] *= 2.0
net = decoders.eegnet(4, 3, 128, 11)
net.set_params(max_epochs=12, callbacks__early_stopping__patience=4)
determinism.seed_everything(11)
net.fit(X, y)
digest = hashlib.sha256(np.asarray(net.predict_proba(X)).tobytes())
for name, tensor in sorted(net.module_.state_dict().items()):
    digest.update(name.encode() + tensor.numpy().tobytes())
print(json.dumps({"digest": digest.hexdigest(), "epochs": len(net.history),
                  "valid_loss": [float(v) for v in net.history[:, "valid_loss"]]}))
"""


def test_eegnet_twice_identical_cpu() -> None:
    """A-106: two fits in two fresh worker processes (WORKER_ENVIRONMENT, one thread, same seed) give
    bit-identical weights, probabilities and validation losses; early stopping and the restored best weights
    included (patience lowered to 4 and at most 12 epochs to keep the test short)."""
    env = {k: v for k, v in os.environ.items() if k not in determinism.WORKER_ENVIRONMENT}
    env.update(determinism.WORKER_ENVIRONMENT, PYTHONIOENCODING="utf-8", PYTHONWARNINGS="ignore")
    # Both processes at once (the imports of braindecode and torch dominate the time).
    workers = [
        subprocess.Popen(
            [sys.executable, "-c", FINGERPRINT],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        for _ in range(2)
    ]
    outputs = []
    for worker in workers:
        stdout, stderr = worker.communicate(timeout=600)
        assert worker.returncode == 0, stderr[-2000:]
        outputs.append(json.loads(stdout.strip().splitlines()[-1]))
    assert outputs[0] == outputs[1]
    assert 1 <= outputs[0]["epochs"] <= 12
