"""Reproducibility settings of area C (A-106, F3 A): seeds, deterministic algorithms, worker environment."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys

import pytest

from neuroarena import determinism


def test_derive_seed_is_sha256_of_the_joined_parts() -> None:
    """A-106/A-103 style seeds: never Python's hash, so equal in every process and on every machine."""
    text = f"{determinism.BASE_SEED}|Zhou2016|clean|1|0|eegnet|3"
    expected = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "big")
    assert determinism.derive_seed("Zhou2016", "clean", 1, "0", "eegnet", 3) == expected
    assert determinism.BASE_SEED == 20261102
    # Fixed values: a change of the derivation changes every result of a run.
    assert determinism.derive_seed() == int.from_bytes(hashlib.sha256(b"20261102").digest()[:4], "big")
    assert determinism.derive_seed("a", 1) != determinism.derive_seed("a", 2)
    assert all(0 <= determinism.derive_seed(i) < 2**32 for i in range(100))


def test_seed_everything_sets_seeds_threads_and_deterministic_algorithms() -> None:
    import random

    import numpy as np
    import torch

    determinism.seed_everything(5)
    first = (random.random(), np.random.random(), torch.rand(1).item())
    determinism.seed_everything(5)
    assert (random.random(), np.random.random(), torch.rand(1).item()) == first
    assert torch.are_deterministic_algorithms_enabled()
    assert torch.get_num_threads() == 1


def test_check_environment_needs_the_worker_environment_from_the_start() -> None:
    probe = "from neuroarena import determinism; determinism.check_environment(); print('ok')"
    clean = {k: v for k, v in os.environ.items() if k not in determinism.WORKER_ENVIRONMENT}
    clean["PYTHONIOENCODING"] = "utf-8"
    good = subprocess.run(
        [sys.executable, "-c", probe],
        env={**clean, **determinism.WORKER_ENVIRONMENT},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert good.returncode == 0 and good.stdout.strip() == "ok", good.stderr
    bad = subprocess.run(
        [sys.executable, "-c", probe],
        env=clean,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert bad.returncode != 0 and "PYTHONHASHSEED" in bad.stderr
    # Set after the start, PYTHONHASHSEED no longer acts: the check must still refuse.
    late = (
        "import os\nfrom neuroarena import determinism\nos.environ.update(determinism.WORKER_ENVIRONMENT)\n"
        "determinism.check_environment()\n"
    )
    after = subprocess.run(
        [sys.executable, "-c", late], env=clean, capture_output=True, text=True, encoding="utf-8", check=False
    )
    assert after.returncode != 0 and "hash randomisation" in after.stderr


def test_check_environment_refuses_a_wrong_thread_count(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in determinism.WORKER_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("OMP_NUM_THREADS", "4")
    with pytest.raises(RuntimeError, match="OMP_NUM_THREADS"):
        determinism.check_environment()
