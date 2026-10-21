"""Shared state for one check run: discovered files, the data model per recording with its metadata from all
sources, header integrity facts and lazily computed readability (ARC-01: adapters → data model → checks)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from neurogrid.config import Config
from neurogrid.io import ADAPTERS
from neurogrid.io.base import FormatAdapter, HeaderInspection, HeaderUnreadable
from neurogrid.io.discover import DatasetScan, FoundFile
from neurogrid.metadata import ENTITY_FIELDS, RecordingMetadata, collect
from neurogrid.model.dataset import Recording
from neurogrid.quality import QualityJob, QualityResult, QualitySettings, compute_all
from neurogrid.quality.positions import Position, sidecar_positions
from neurogrid.validator import ValidatorResult
from neurogrid.validator import run as run_validator

__all__ = ["ENTITY_FIELDS", "CheckContext", "RecordingState"]

_UNSET = object()


@dataclass
class RecordingState:
    found: FoundFile
    path: Path
    adapter: FormatAdapter
    recording: Recording | None = None
    inspection: HeaderInspection | None = None
    header_error: str | None = None
    metadata: RecordingMetadata = field(default_factory=RecordingMetadata)
    quality: QualityResult | None = None  # signal quality job (M06–M09), set by CheckContext.compute_quality
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

    @property
    def annotations_only(self) -> bool:
        """An EDF+/BDF+ file with annotations only (e.g. a hypnogram): readable, but no signal recording."""
        return (
            self.recording is not None
            and bool(self.recording.channels)
            and all(ch.type == "ANNOT" for ch in self.recording.channels)
        )

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
    work: Path | None = None  # private folder of this run (A-54), e.g. for the validator output
    _validator: ValidatorResult | None = field(default=None, repr=False)

    def validator_result(self) -> ValidatorResult:
        """The BIDS validator result for the dataset; computed once per run."""
        if self._validator is None:
            if self.work is None:
                raise RuntimeError("the BIDS validator needs a work folder")
            self._validator = run_validator(self.root, self.work / "validator")
        return self._validator

    def compute_quality(self, *, stream: bool, sample: bool, jobs: int = 1) -> None:
        """Run the signal quality job of every recording with signals (one process per job with --jobs)."""
        cfg = self.config
        settings = QualitySettings(
            flat_tolerance_uv=cfg.quality.flat_tolerance_uv,
            plateau_samples=cfg.quality.plateau_samples,
            min_seconds=cfg.quality.min_seconds,
            min_channels=cfg.quality.min_channels,
            mode=cfg.sampling.mode,
            segments=cfg.sampling.segments,
            segment_s=cfg.sampling.segment_s,
            seed=cfg.check.seed,
        )
        pending = [rec for rec in self.recordings if rec.recording is not None and not rec.annotations_only]
        work = []
        for rec in pending:
            if rec.recording is None:
                continue
            sidecar: tuple[dict[str, Position], str | None] = ({}, None)
            if sample and self.scan.is_bids:
                sidecar = sidecar_positions(self.root, rec.found.relative)
            work.append(
                QualityJob(
                    path=str(rec.path),
                    recording=rec.recording,
                    settings=settings,
                    channel_map=dict(cfg.metadata.channel_map),
                    stream=stream,
                    sample=sample,
                    sidecar_positions=sidecar[0],
                    sidecar_reason=sidecar[1],
                )
            )
        for rec, result in zip(pending, compute_all(work, jobs), strict=True):
            rec.quality = result

    @classmethod
    def build(cls, scan: DatasetScan, config: Config, work: Path | None = None) -> CheckContext:
        states = []
        for found in scan.recordings:
            path = scan.root.joinpath(*found.relative.parts)
            state = RecordingState(found=found, path=path, adapter=ADAPTERS[found.suffix])
            recording = None
            try:
                recording = state.adapter.read(
                    path, recording_id=found.display_id, relative_path=found.relative.as_posix()
                )
                state.inspection = state.adapter.inspect(path)
            except HeaderUnreadable as exc:
                recording = None
                state.header_error = exc.reason
            except OSError:
                recording = None
                state.header_error = "header.io_error"
            except (ArithmeticError, ValueError):  # defensive: a header value no model can hold (A-75)
                recording = None
                state.header_error = "header.number_field"
            state.recording, state.metadata = collect(scan.root, found, recording, config, scan.is_bids)
            states.append(state)
        return cls(root=scan.root, scan=scan, config=config, recordings=states, work=work)
