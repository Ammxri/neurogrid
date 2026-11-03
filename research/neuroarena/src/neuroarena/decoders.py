"""The two decoders of the PRD (NA-04; F7 A, A-105; area C "decoders and evaluation").

- CSP+LDA as the MOABB pipeline "CSP + LDA" (OAS covariance, 6 CSP filters, LDA). For SSVEP a filter bank as
  F7 A: MOABB's FilterBankSSVEP (one band per stimulus frequency, f +- 0.5 Hz), CSP per band, LDA on the
  log-variance. The report marks CSP+LDA on SSVEP as not SSVEP-typical (F7).
- EEGNet from braindecode with its default hyperparameters as a skorch classifier (braindecode's
  EEGClassifier), at most 300 epochs, early stopping on a 20 % stratified validation split.
Preprocessing: MI 8-32 Hz for CSP; 4-40 Hz and resampling to 128 Hz for EEGNet. No tuning on test data.

Checked against the locked versions (2026-11-02):
- braindecode 1.8.1 has ``braindecode.models.EEGNet`` (module braindecode.models.eegnet; there is no
  ``EEGNetv4`` in 1.8.1). Defaults: F1=8, D=2, F2=None (F1*D), kernel_length=64, depthwise_kernel_length=16,
  pool1_kernel_size=4, pool2_kernel_size=8, drop_prob=0.25, pool_mode="mean", activation ELU.
- MOABB's repository at tag v1.7.2, ``pipelines/CSP.yml`` ("CSP + LDA", checked by the lead on 2026-11-02):
  ``Covariances(estimator="oas")`` -> pyriemann ``CSP(nfilter=6)`` -> ``LinearDiscriminantAnalysis(solver=
  "svd")``; the values below are those (moabb 1.7.2 as a wheel or sdist ships no pipeline YAML). MOABB has no
  SSVEP filter-bank CSP pipeline: the SSVEP variant is NeuroArena's own construction from the same blocks and
  MOABB's ``FilterBank`` (F7 A). Building blocks in the lock: ``pyriemann.estimation.Covariances``,
  ``pyriemann.spatialfilters.CSP(nfilter, metric="euclid", log=True)`` (log-variance),
  ``sklearn.discriminant_analysis.LinearDiscriminantAnalysis`` and ``moabb.pipelines.utils.FilterBank(
  estimator, flatten=True)``.
- MOABB 1.7.2 has no EEGNet pipeline. The training therefore follows the EEGNet authors' reference example
  (vlawhern/arl-eegmodels, ``examples/ERP.py``; lead decision 2026-11-02): Adam with its default parameters,
  cross-entropy, batches of 16, at most 300 epochs, the weights of the epoch with the lowest validation loss,
  the input in millivolts (``X * 1000``). A-105 adds early stopping on a 20 % stratified validation split.
  Every other setting is the default of braindecode 1.8.1's ``EEGClassifier`` and skorch 1.4.0.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from neuroarena.datasets import DatasetSpec

if TYPE_CHECKING:
    from moabb.paradigms.base import BaseParadigm
    from sklearn.pipeline import Pipeline

DECODERS = ("csp_lda", "eegnet")

# CSP+LDA (A-105; MOABB v1.7.2 pipelines/CSP.yml)
COVARIANCE_ESTIMATOR = "oas"
CSP_FILTERS = 6
LDA_SOLVER = "svd"  # MOABB CSP.yml (also scikit-learn's default)
MI_BAND_CSP_HZ = (8.0, 32.0)
SSVEP_BAND_HALF_WIDTH_HZ = 0.5  # FilterBankSSVEP default: [f - 0.5, f + 0.5] per numeric event

# EEGNet (A-105)
EEGNET_CLASS = "braindecode.models.EEGNet"
EEGNET_BAND_HZ = (4.0, 40.0)  # A-105; for MI and SSVEP alike (SSVEP confirmed by the lead, 2026-11-02)
EEGNET_SAMPLING_RATE_HZ = 128.0
EEGNET_MAX_EPOCHS = 300
EEGNET_VALIDATION_SHARE = 0.2  # stratified, seeded (determinism.derive_seed)
DEVICE = "cpu"  # F3 A
# Training of EEGNet (lead decision 2026-11-02; A-105 says "default hyperparameters" without values).
EEGNET_OPTIMIZER = "torch.optim.Adam"  # reference example ERP.py: Adam with default parameters
EEGNET_LEARNING_RATE = 1e-3  # reference example (Adam's default); skorch's own default would be 0.01
EEGNET_BATCH_SIZE = 16  # reference example; skorch's own default would be 128
EEGNET_CRITERION = "torch.nn.CrossEntropyLoss"  # reference example; braindecode 1.8.1 EEGClassifier default
EEGNET_SHUFFLE = True  # braindecode 1.8.1 EEGClassifier default (iterator_train__shuffle), seeded order
EEGNET_DROP_LAST = True  # braindecode 1.8.1 EEGClassifier default (iterator_train__drop_last)
EEGNET_INPUT_SCALE = 1000.0  # reference example: X * 1000 (volts to millivolts); constant, never fitted
EEGNET_EARLY_STOPPING_MONITOR = "valid_loss"  # A-105 early stopping on the validation split
EEGNET_PATIENCE = 50  # lead choice (A-105 names no patience)
EEGNET_LOAD_BEST = True  # reference example: keep the weights of the epoch with the lowest validation loss


def _resolve(dotted: str) -> Any:
    module, _, name = dotted.rpartition(".")
    return getattr(importlib.import_module(module), name)


def _validate(spec: DatasetSpec, decoder: str) -> None:
    if decoder not in DECODERS:
        raise ValueError(f"unknown decoder {decoder!r}")
    if spec.paradigm not in ("imagery", "ssvep"):
        raise ValueError(f"unknown paradigm {spec.paradigm!r}")


def ssvep_bands(spec: DatasetSpec) -> list[list[float]]:
    """The filter bank of CSP+LDA on SSVEP: ``[f - 0.5, f + 0.5]`` for every numeric event of ``spec`` in
    its order (FilterBankSSVEP's own default, written out; "rest" has no band)."""
    bands = []
    for event in spec.events:
        try:
            frequency = float(event)
        except ValueError:
            continue
        bands.append([frequency - SSVEP_BAND_HALF_WIDTH_HZ, frequency + SSVEP_BAND_HALF_WIDTH_HZ])
    return bands


def paradigm(spec: DatasetSpec, decoder: str) -> BaseParadigm:
    """The MOABB paradigm that prepares the epochs of ``spec`` for ``decoder``, with all ``spec.events`` and
    the dataset's own epoch interval:
    - imagery + csp_lda: ``MotorImagery(fmin=8, fmax=32, events=..., n_classes=...)``
    - imagery + eegnet: ``MotorImagery(fmin=4, fmax=40, resample=128, events=..., n_classes=...)``
    - ssvep + csp_lda: ``FilterBankSSVEP(events=..., n_classes=...)`` (X has a trailing band axis)
    - ssvep + eegnet: ``SSVEP(fmin=4, fmax=40, resample=128, events=..., n_classes=...)``
    Callers pass ``cache_config`` with ``use=False`` and no saving to ``get_data`` (MOABB's default)."""
    from moabb.paradigms import SSVEP, FilterBankSSVEP, MotorImagery

    _validate(spec, decoder)
    events = list(spec.events)
    n_classes = len(events)
    if spec.paradigm == "imagery":
        if decoder == "csp_lda":
            low, high = MI_BAND_CSP_HZ
            return MotorImagery(fmin=low, fmax=high, events=events, n_classes=n_classes)
        low, high = EEGNET_BAND_HZ
        return MotorImagery(
            fmin=low, fmax=high, resample=EEGNET_SAMPLING_RATE_HZ, events=events, n_classes=n_classes
        )
    if decoder == "csp_lda":
        return FilterBankSSVEP(filters=ssvep_bands(spec), events=events, n_classes=n_classes)
    low, high = EEGNET_BAND_HZ
    return SSVEP(fmin=low, fmax=high, resample=EEGNET_SAMPLING_RATE_HZ, events=events, n_classes=n_classes)


def csp_lda(spec: DatasetSpec) -> Pipeline:
    """A fresh unfitted pipeline: imagery ``make_pipeline(Covariances("oas"), CSP(nfilter=6), LDA())``; ssvep
    ``make_pipeline(FilterBank(make_pipeline(Covariances("oas"), CSP(nfilter=6))), LDA())``."""
    from moabb.pipelines.utils import FilterBank
    from pyriemann.estimation import Covariances
    from pyriemann.spatialfilters import CSP
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.pipeline import make_pipeline

    _validate(spec, "csp_lda")
    lda = LinearDiscriminantAnalysis(solver=LDA_SOLVER)
    if spec.paradigm == "imagery":
        return make_pipeline(Covariances(estimator=COVARIANCE_ESTIMATOR), CSP(nfilter=CSP_FILTERS), lda)
    band = make_pipeline(Covariances(estimator=COVARIANCE_ESTIMATOR), CSP(nfilter=CSP_FILTERS))
    return make_pipeline(FilterBank(band, flatten=True), lda)


def model_batch(items: Any) -> Any:
    """Collate function of EEGNet's data loaders: torch's default collation, then the signal times
    ``EEGNET_INPUT_SCALE`` (MNE's volts to millivolts as in the reference example; a constant, so nothing is
    learned from the data). braindecode's loader casts the signal to float32 and the labels to int64."""
    from torch.utils.data import default_collate

    batch = default_collate(items)
    return (batch[0] * EEGNET_INPUT_SCALE, *batch[1:])


def eegnet(n_chans: int, n_outputs: int, n_times: int, seed: int) -> Any:
    """A fresh unfitted ``braindecode.classifier.EEGClassifier`` around ``braindecode.models.EEGNet`` with its
    defaults, on the CPU, at most ``EEGNET_MAX_EPOCHS`` epochs, early stopping on a stratified
    ``EEGNET_VALIDATION_SHARE`` split drawn with ``seed``; scikit-learn API (fit(X, y), predict(X)) on float32
    arrays (trials, channels, times). ``determinism.seed_everything(seed)`` runs before the fit.

    Labels are the integers 0 .. n_outputs - 1 (``evaluation.evaluate_session`` encodes them); ``predict``
    returns such integers. The caller seeds right before ``fit`` (weight initialisation and dropout draw from
    torch's global generator; ``evaluation.evaluate_session`` does it); the order of the training batches
    comes from a generator of its own seeded with ``seed``. The validation split is skorch's
    ``ValidSplit(0.2, stratified=True, random_state=seed)``, i.e. a seeded ``StratifiedShuffleSplit``
    (skorch 1.4.0 refuses ``random_state`` with an integer number of folds). The input is scaled by
    ``EEGNET_INPUT_SCALE`` in the loaders (``model_batch``). ``max_epochs`` can be lowered with
    ``set_params`` (the runner's smoke mode)."""
    import torch
    from braindecode.classifier import EEGClassifier
    from skorch.callbacks import EarlyStopping
    from skorch.dataset import ValidSplit

    early_stopping = EarlyStopping(
        monitor=EEGNET_EARLY_STOPPING_MONITOR, patience=EEGNET_PATIENCE, load_best=EEGNET_LOAD_BEST
    )
    return EEGClassifier(
        _resolve(EEGNET_CLASS),
        module__n_chans=n_chans,
        module__n_outputs=n_outputs,
        module__n_times=n_times,
        criterion=_resolve(EEGNET_CRITERION),
        optimizer=_resolve(EEGNET_OPTIMIZER),
        lr=EEGNET_LEARNING_RATE,
        batch_size=EEGNET_BATCH_SIZE,
        max_epochs=EEGNET_MAX_EPOCHS,
        train_split=ValidSplit(EEGNET_VALIDATION_SHARE, stratified=True, random_state=seed),
        callbacks=[("early_stopping", early_stopping)],
        iterator_train__shuffle=EEGNET_SHUFFLE,
        iterator_train__drop_last=EEGNET_DROP_LAST,
        iterator_train__generator=torch.Generator().manual_seed(seed),
        iterator_train__collate_fn=model_batch,
        iterator_valid__collate_fn=model_batch,
        device=DEVICE,
        verbose=0,
    )


def make(spec: DatasetSpec, decoder: str, n_chans: int, n_outputs: int, n_times: int, seed: int) -> Any:
    """A fresh unfitted decoder by name (``DECODERS``); the shape arguments are used by EEGNet only."""
    _validate(spec, decoder)
    if decoder == "csp_lda":
        return csp_lda(spec)
    return eegnet(n_chans, n_outputs, n_times, seed)
