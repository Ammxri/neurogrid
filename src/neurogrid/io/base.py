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

import importlib
import threading
import warnings
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
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


class ModulePatch:
    """Globals of a library module replaced while at least one block holds the patch (A-77, TECH-05).

    ``added`` names globals the module does not define (a built-in it uses, such as ``open``), each with the
    object that hides the built-in; ``wrapped`` names functions it defines, each with a factory that makes
    the replacement from the original. The first holder, in any thread, installs the replacements and the
    last one to leave restores the module, so blocks may nest, overlap in several threads and end in any
    order: no block runs without the patch, and none outlives the last block. While the patch is held, other
    callers of the module see the replacements as well. A module that no longer looks as expected (a wrapped
    name missing, an added name defined) raises RuntimeError, so that a library update is reviewed.
    """

    def __init__(
        self,
        module: str,
        *,
        added: Mapping[str, Any] | None = None,
        wrapped: Mapping[str, Callable[[Any], Any]] | None = None,
    ) -> None:
        self.module = module
        self._added = dict(added or {})
        self._wrapped = dict(wrapped or {})
        self._lock = threading.Lock()
        self._holders = 0
        self._originals: dict[str, Any] = {}

    @property
    def holders(self) -> int:
        """The number of blocks holding the patch now."""
        with self._lock:
            return self._holders

    def _install(self) -> None:
        names = vars(importlib.import_module(self.module))
        for name in self._added:
            if name in names:
                raise RuntimeError(f"{self.module} defines {name}: review NeuroGrid's patch of it")
        for name in self._wrapped:
            if not callable(names.get(name)):
                raise RuntimeError(f"{self.module} has no function {name}: review NeuroGrid's patch of it")
        originals = {name: names[name] for name in self._wrapped}
        replacements = {name: make(originals[name]) for name, make in self._wrapped.items()}
        names.update(self._added)
        names.update(replacements)
        self._originals = originals

    def _restore(self) -> None:
        names = vars(importlib.import_module(self.module))
        for name in self._added:
            names.pop(name, None)
        names.update(self._originals)
        self._originals = {}

    @contextmanager
    def held(self) -> Iterator[None]:
        with self._lock:
            if self._holders == 0:
                self._install()
            self._holders += 1
        try:
            yield
        finally:
            with self._lock:
                self._holders -= 1
                if self._holders == 0:
                    self._restore()
