"""Shared state for one check run: discovered files, the data model per recording, header integrity facts
and lazily computed readability (ARC-01: adapters → data model → checks)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from neurogrid.config import Config
from neurogrid.io import ADAPTERS
from neurogrid.io.base import FormatAdapter, HeaderInspection, HeaderUnreadable
from neurogrid.io.discover import DatasetScan, FoundFile
from neurogrid.model.dataset import Recording

_UNSET = object()
ENTITY_FIELDS = (("subject", "sub"), ("session", "ses"), ("task", "task"), ("run", "run"))


def _with_entities(recording: Recording, found: FoundFile) -> Recording:
    """BIDS file name entities fill subject/session/task/run; raw folders get them from the mapping (P2)."""
    update: dict[str, object] = {
        name: found.entity(entity) for name, entity in ENTITY_FIELDS if found.entity(entity) is not None
    }
    if not update:
        return recording
    sources = {**recording.metadata_sources, **dict.fromkeys(update, "bids_filename")}
    return recording.model_copy(update={**update, "metadata_sources": sources})


@dataclass
class RecordingState:
    found: FoundFile
    path: Path
    adapter: FormatAdapter
    recording: Recording | None = None
    inspection: HeaderInspection | None = None
    header_error: str | None = None
    _read_error: object = field(default=_UNSET, repr=False)

    @property
    def object_id(self) -> str:
        return self.found.display_id

    @property
    def file(self) -> str:
        return self.found.display_file

    @property
    def identity(self) -> tuple[str, ...]:
        return self.found.identity

    def read_error(self) -> str | None:
        """None if MNE can read the data, else the exception class name. Computed once."""
        if self._read_error is _UNSET:
            self._read_error = self.adapter.read_check(self.path)
        return self._read_error  # type: ignore[return-value]


@dataclass
class CheckContext:
    root: Path
    scan: DatasetScan
    config: Config
    recordings: list[RecordingState]

    @classmethod
    def build(cls, scan: DatasetScan, config: Config) -> CheckContext:
        states = []
        for found in scan.recordings:
            path = scan.root.joinpath(*found.relative.parts)
            state = RecordingState(found=found, path=path, adapter=ADAPTERS[found.suffix])
            try:
                recording = state.adapter.read(
                    path, recording_id=found.display_id, relative_path=found.relative.as_posix()
                )
                state.recording = _with_entities(recording, found)
                state.inspection = state.adapter.inspect(path)
            except HeaderUnreadable as exc:
                state.recording = None
                state.header_error = exc.reason
            except OSError:
                state.recording = None
                state.header_error = "header.io_error"
            except (ArithmeticError, ValueError):  # defensive: a header value no model can hold (A-75)
                state.recording = None
                state.header_error = "header.number_field"
            states.append(state)
        return cls(root=scan.root, scan=scan, config=config, recordings=states)
