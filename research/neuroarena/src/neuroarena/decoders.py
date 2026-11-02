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
- moabb 1.7.2 (wheel and sdist) ships no pipeline configuration "CSP + LDA": the YAML files live only in
  MOABB's repository. The values below are those of A-105; checking them against the repository at the tag
  of 1.7.2 is open (lead). Building blocks in the lock: ``pyriemann.estimation.Covariances(estimator=...)``
  (default "scm"), ``pyriemann.spatialfilters.CSP(nfilter=4, metric="euclid", log=True)`` (defaults),
  ``sklearn.discriminant_analysis.LinearDiscriminantAnalysis(solver="svd")`` (default) and
  ``moabb.pipelines.utils.FilterBank(estimator, flatten=True)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neuroarena.datasets import DatasetSpec

if TYPE_CHECKING:
    from moabb.paradigms.base import BaseParadigm
    from sklearn.pipeline import Pipeline

DECODERS = ("csp_lda", "eegnet")

# CSP+LDA (A-105)
COVARIANCE_ESTIMATOR = "oas"
CSP_FILTERS = 6
MI_BAND_CSP_HZ = (8.0, 32.0)
SSVEP_BAND_HALF_WIDTH_HZ = 0.5  # FilterBankSSVEP default: [f - 0.5, f + 0.5] per numeric event

# EEGNet (A-105)
EEGNET_CLASS = "braindecode.models.EEGNet"
EEGNET_BAND_HZ = (4.0, 40.0)  # A-105 names it for EEGNet; the scaffold uses it for MI and SSVEP (lead)
EEGNET_SAMPLING_RATE_HZ = 128.0
EEGNET_MAX_EPOCHS = 300
EEGNET_VALIDATION_SHARE = 0.2  # stratified, seeded (determinism.derive_seed)
DEVICE = "cpu"  # F3 A
# OPEN (A-105 says "default hyperparameters" without values): optimizer, learning rate, batch size, the
# early-stopping rule (monitor, patience) and the unit scaling of the input (MOABB returns volts). Area C
# names the values it takes from braindecode 1.8.1 and skorch 1.4.0 in its first commit; the lead fixes them
# before the pilot (A-109).


def paradigm(spec: DatasetSpec, decoder: str) -> BaseParadigm:
    """The MOABB paradigm that prepares the epochs of ``spec`` for ``decoder``, with all ``spec.events`` and
    the dataset's own epoch interval:
    - imagery + csp_lda: ``MotorImagery(fmin=8, fmax=32, events=..., n_classes=...)``
    - imagery + eegnet: ``MotorImagery(fmin=4, fmax=40, resample=128, events=..., n_classes=...)``
    - ssvep + csp_lda: ``FilterBankSSVEP(events=..., n_classes=...)`` (X has a trailing band axis)
    - ssvep + eegnet: ``SSVEP(fmin=4, fmax=40, resample=128, events=..., n_classes=...)``
    Callers pass ``cache_config`` with ``use=False`` and no saving to ``get_data`` (MOABB's default)."""
    raise NotImplementedError("area C")


def csp_lda(spec: DatasetSpec) -> Pipeline:
    """A fresh unfitted pipeline: imagery ``make_pipeline(Covariances("oas"), CSP(nfilter=6), LDA())``; ssvep
    ``make_pipeline(FilterBank(make_pipeline(Covariances("oas"), CSP(nfilter=6))), LDA())``."""
    raise NotImplementedError("area C")


def eegnet(n_chans: int, n_outputs: int, n_times: int, seed: int) -> Any:
    """A fresh unfitted ``braindecode.classifier.EEGClassifier`` around ``braindecode.models.EEGNet`` with its
    defaults, on the CPU, at most ``EEGNET_MAX_EPOCHS`` epochs, early stopping on a stratified
    ``EEGNET_VALIDATION_SHARE`` split drawn with ``seed``; scikit-learn API (fit(X, y), predict(X)) on float32
    arrays (trials, channels, times). ``determinism.seed_everything(seed)`` runs before the fit."""
    raise NotImplementedError("area C")


def make(spec: DatasetSpec, decoder: str, n_chans: int, n_outputs: int, n_times: int, seed: int) -> Any:
    """A fresh unfitted decoder by name (``DECODERS``); the shape arguments are used by EEGNet only."""
    raise NotImplementedError("area C")
