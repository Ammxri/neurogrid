"""Adapter contract (ARC-01, ARC-04, A-24).

- ``read(path, recording_id=…, relative_path=…)`` returns the data model ``Recording`` with its channels
  (unit, resolution, physical range and sampling rate per channel; ``metadata_sources`` names the origin).
- ``inspect(path)`` reports format-specific header integrity facts for M01 (issues, identifying fields).
- ``read_check(path)`` opens the data with MNE and reads from both ends.

Block iteration for the signal metrics (``iter_blocks``/``read_segments``, A-24) is added together with those
metrics in P3.

Only listed header facts leave an adapter (A-51): patient and recording fields are reduced to flags saying
*that* they contain identifying content, never *what* they contain.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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


class FormatAdapter(Protocol):
    format: str
    extensions: tuple[str, ...]

    def read(self, path: Path, *, recording_id: str, relative_path: str) -> Recording: ...

    def inspect(self, path: Path) -> HeaderInspection: ...

    def read_check(self, path: Path) -> str | None:
        """Open the file with MNE and read data; return ``None`` or the error class name."""
        ...
