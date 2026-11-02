"""Shared state for one check run: discovered files, the data model per recording with its metadata from all
sources, header integrity facts and lazily computed readability (ARC-01: adapters → data model → checks)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath

from neurogrid.config import Config
from neurogrid.io import ADAPTERS
from neurogrid.io.annotations import AnnotationIndex, build_index
from neurogrid.io.base import FormatAdapter, HeaderInspection, HeaderUnreadable
from neurogrid.io.discover import DatasetScan, FoundFile
from neurogrid.io.provenance import ProvenanceState, vault_exclusions
from neurogrid.metadata import ENTITY_FIELDS, RecordingMetadata, collect
from neurogrid.model.dataset import Recording
from neurogrid.quality import QualityJob, QualityResult, QualitySettings, compute_all
from neurogrid.quality.positions import Position, sidecar_positions
from neurogrid.validator import ValidatorResult
from neurogrid.validator import run as run_validator
from neurogrid.vault.consents import LoadedConsents
from neurogrid.vault.retention import LoadedRetention
from neurogrid.vault.risks import LoadedRisks
from neurogrid.vault.roles import LoadedRoles
from neurogrid.vault.store import VaultLocation

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
    project_root: Path | None = None  # where neurogrid.toml's relative paths start (A-66)
    show_paths: bool = False  # --show-paths: clear paths and IDs in raw folders (D-10 f, A-51)
    strict: bool = False  # --strict (CLI-04)
    as_of: date | None = None  # the run's reference date (A-14 expiry, A-15 review dates)
    manifest_path: Path | None = None  # --manifest; None: <dataset>/.neurogrid/manifest.json (A-22, A-82)
    evidence_path: Path | None = None  # --evidence; None: the default location (A-15)
    # the vault of the run ([vault] path relative to the project root, A-66), located once by the pipeline
    # in any state; None for a single file as target, which has no vault (p6 decisions 2)
    vault: VaultLocation | None = None
    _validator: ValidatorResult | None = field(default=None, repr=False)
    # M11/M12 dataset structure (participants, splits, labels), built once by checks.ai_dataset (A-81)
    ai_structure: object = field(default=None, repr=False)
    _provenance: ProvenanceState | None = field(default=None, repr=False)
    _annotations: AnnotationIndex | None = field(default=None, repr=False)
    # M10 κ per object (relative path), computed once per run by checks.annotation.cached_kappa (A-53)
    annotation_kappa: dict[PurePosixPath, object] = field(default_factory=dict, repr=False)
    # M14 (A-30, A-91): the consent records of the vault, read before the signal pass (None: not read), and
    # whether the run requires consent data (--strict or [check] strict, or a configured [consent] section)
    consents: LoadedConsents | None = field(default=None, repr=False)
    consent_required: bool = False
    # NV04, NV05 and M14-02 (A-93 to A-95): the registers of the vault, read before the signal pass when a
    # loaded rule needs them (pipeline._load_vault_files); None: not read (no such rule, or a single file)
    roles: LoadedRoles | None = field(default=None, repr=False)
    retention: LoadedRetention | None = field(default=None, repr=False)
    risks: LoadedRisks | None = field(default=None, repr=False)

    def annotations(self) -> AnnotationIndex:
        """The annotations of every signal recording, with the annotation-only files attached to them (M10,
        A-80); read once per run, only when a check asks for them. ``by_recording()`` of the result is also
        the source for ``[ai] labels = "annotations"`` (A-81)."""
        if self._annotations is None:
            section = self.config.annotation
            self._annotations = build_index(
                self.root,
                self.recordings,
                is_bids=self.scan.is_bids,
                files=section.files,
                annotators=section.annotators,
            )
        return self._annotations

    @property
    def annotations_read(self) -> bool:
        """True once a check has asked for the annotations (results then carry the M10 summary)."""
        return self._annotations is not None

    def validator_result(self) -> ValidatorResult:
        """The BIDS validator result for the dataset; computed once per run."""
        if self._validator is None:
            if self.work is None:
                raise RuntimeError("the BIDS validator needs a work folder")
            self._validator = run_validator(self.root, self.work / "validator")
        return self._validator

    def provenance(self) -> ProvenanceState:
        """The manifest, its comparison with the dataset and the documentation sources (M13); each read or
        computed once per run, the comparison only when a rule asks for it."""
        if self._provenance is None:
            self._provenance = ProvenanceState(
                self.root,
                single_file=self.scan.single_file,
                is_bids=self.scan.is_bids,
                show_paths=self.show_paths,
                manifest_path=self.manifest_path,
                work=self.work,
                # CORE-M13-02 leaves out the log of every vault the run may append to, as manifest does
                vault_files=tuple(vault_exclusions(self.root, self.vault.project_root, self.vault.relative))
                if self.vault is not None
                else (),
            )
        return self._provenance

    def compute_quality(
        self,
        *,
        stream: bool,
        sample: bool,
        jobs: int = 1,
        on_recompute: Callable[[int], None] | None = None,
    ) -> None:
        """Run the signal quality job of every recording with signals (one process per job with --jobs);
        ``on_recompute`` as in ``compute_all``."""
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
        for rec, result in zip(pending, compute_all(work, jobs, on_recompute=on_recompute), strict=True):
            rec.quality = result

    @classmethod
    def build(
        cls,
        scan: DatasetScan,
        config: Config,
        work: Path | None = None,
        *,
        project_root: Path | None = None,
        show_paths: bool = False,
        strict: bool = False,
        as_of: date | None = None,
        manifest_path: Path | None = None,
        evidence_path: Path | None = None,
        vault: VaultLocation | None = None,
    ) -> CheckContext:
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
        return cls(
            root=scan.root,
            scan=scan,
            config=config,
            recordings=states,
            work=work,
            project_root=project_root,
            show_paths=show_paths,
            strict=strict,
            as_of=as_of,
            manifest_path=manifest_path,
            evidence_path=evidence_path,
            vault=vault,
        )
