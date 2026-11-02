"""Reproducibility of the decoder runs (A-106, F3 A; area C "decoders and evaluation").

CPU only. Seeds for Python, NumPy and torch, and for folds and the bootstrap; ``PYTHONHASHSEED=0``;
``torch.use_deterministic_algorithms(True)``; torch, BLAS and OpenMP with one thread per process. Equality is
promised only per machine and lock (A-106); across machines nothing is claimed (F3).
"""

from __future__ import annotations

# Environment of every worker process, set before the worker imports numpy or torch (spawn start method).
# Variables of other programs (BLAS, OpenMP, Python); not NeuroArena's own.
WORKER_ENVIRONMENT = {
    "PYTHONHASHSEED": "0",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
}
# Base of every seed of a run. Scaffold choice (A-106 names no value): fixed before the first run, recorded
# in run.json, never adapted to results.
BASE_SEED = 20261102


def derive_seed(*parts: str | int) -> int:
    """A seed in [0, 2**32) from ``BASE_SEED`` and ``parts`` (e.g. dataset, condition id, subject, session,
    decoder, fold): the first four bytes (big endian) of SHA-256 over the UTF-8 of ``"|".join(map(str,
    (BASE_SEED, *parts)))``. Never Python's ``hash``."""
    raise NotImplementedError("area C")


def seed_everything(seed: int) -> None:
    """Seed ``random``, ``numpy.random`` (legacy global state) and torch with ``seed``; set
    ``torch.use_deterministic_algorithms(True)``, ``torch.set_num_threads(1)`` and keep the device on the CPU.
    Called before every fit (EEGNet) and before the CV split. braindecode's ``set_random_seeds`` does not set
    the deterministic algorithms itself (draft 2.4, braindecode issue 333)."""
    raise NotImplementedError("area C")


def check_environment() -> None:
    """Raise RuntimeError if this process does not run with ``WORKER_ENVIRONMENT`` (a worker started without
    it would not be reproducible)."""
    raise NotImplementedError("area C")
