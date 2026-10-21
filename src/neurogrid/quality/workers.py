"""Start-up of the processes that compute signal metrics (A-11, A-49, NG-N01).

Every process installs the network guard and computes with one BLAS thread, so that the values depend
neither on the number of processes nor on the BLAS threads of the environment. autoreject spreads its
threshold search over loky processes (joblib); they start the same way, keep library warnings off the
console, and get the data by pickling: joblib's memory maps would write signal data to a temporary folder.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from contextlib import contextmanager

LOKY_IDLE_S = 1  # loky keeps idle workers 300 s by default, which would delay the end of every pool worker


def worker_start() -> None:
    """Initializer of the process pool behind ``--jobs``."""
    from threadpoolctl import threadpool_limits

    from neurogrid.kernel import netguard

    netguard.install()
    threadpool_limits(limits=1)


def loky_worker_start() -> None:
    """Initializer of autoreject's loky workers."""
    import mne

    worker_start()
    warnings.simplefilter("ignore")
    mne.set_log_level("ERROR")


@contextmanager
def loky_processes() -> Iterator[None]:
    """joblib calls inside run in loky processes started by ``loky_worker_start``."""
    import joblib

    with joblib.parallel_config(
        backend="loky",
        inner_max_num_threads=1,
        max_nbytes=None,
        initializer=loky_worker_start,
        idle_worker_timeout=LOKY_IDLE_S,
    ):
        yield


__all__ = ["LOKY_IDLE_S", "loky_processes", "loky_worker_start", "worker_start"]
