"""Adapter contract (ARC-01, ARC-04, A-24).

- ``read(path, recording_id=…, relative_path=…)`` returns the data model ``Recording`` with its channels
  (unit, resolution, physical range and sampling rate per channel; ``metadata_sources`` names the origin).
- ``inspect(path)`` reports format-specific integrity facts for M01: header issues, identifying fields and
  missing companion files or references (A-46).
- ``read_check(path)`` opens the data with MNE and reads from both ends.

Block iteration for the signal metrics (``iter_blocks``/``read_segments``, A-24) is added together with those
metrics in P3.

Only listed header facts leave an adapter (A-51): patient and recording fields are reduced to flags saying
*that* they contain identifying content, never *what* they contain.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from neurogrid.model.dataset import Recording


class HeaderUnreadable(Exception):
    """The header cannot be parsed at all; ``reason`` is a stable key."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class HeaderInspection:
    issues: tuple[str, ...] = ()
    identifying_fields: tuple[str, ...] = ()
    missing_companions: tuple[str, ...] = ()


class FormatAdapter(Protocol):
    format: str
    extensions: tuple[str, ...]

    def read(self, path: Path, *, recording_id: str, relative_path: str) -> Recording: ...

    def inspect(self, path: Path) -> HeaderInspection: ...

    def read_check(self, path: Path) -> str | None:
        """Open the file with MNE and read data; return ``None`` or the error class name."""
        ...


def mne_read_check(reader: Callable[..., Any], path: Path, **kwargs: Any) -> str | None:
    """Open with an MNE reader (no preload) and read the first and the last second of data.

    Library warnings stay inside (they would print install paths, A-51); only the outcome counts. A file
    without data channels (e.g. annotations only) counts as readable.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            raw = reader(path, preload=False, verbose="error", **kwargs)
            if not raw.ch_names:
                return None
            n_times = int(raw.n_times)
            step = max(1, min(n_times, int(raw.info["sfreq"])))
            raw.get_data(start=0, stop=step, verbose="error")
            raw.get_data(start=max(0, n_times - step), stop=n_times, verbose="error")
    except Exception as exc:  # any failure means "not readable"; only the class name is kept
        return type(exc).__name__
    return None
