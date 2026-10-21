"""Orchestration of ``scan`` and ``check`` (KONZEPT §1.4)."""

from __future__ import annotations

import hashlib
import math
import os
import platform
import re
import sys
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date
from importlib import metadata, resources
from pathlib import Path, PurePosixPath
from typing import Any

import neurogrid
from neurogrid import config as config_module
from neurogrid.checks.context import CheckContext
from neurogrid.checks.quality import SAMPLE_CHECKS, STREAM_CHECKS
from neurogrid.checks.registry import REGISTRY, measure
from neurogrid.config import BUILTIN_RULEPACK, Config
from neurogrid.io import ADAPTERS, KNOWN_UNSUPPORTED_DIRS
from neurogrid.io.discover import DatasetScan, FoundFile, scan
from neurogrid.kernel import canonical, engine
from neurogrid.kernel.errors import InputError, RulepackError, UnsafePathError
from neurogrid.kernel.findings import Notice, Severity, SourceStatus
from neurogrid.kernel.rules import LoadedRulepack, load_rulepack, validate_against_registry
from neurogrid.kernel.safety import (
    MAX_YAML_BYTES,
    check_operator_path,
    check_relative,
    is_link,
    read_limited,
    resolve_within,
    work_directory,
)
from neurogrid.model.dataset import Dataset
from neurogrid.model.results import (
    ConfigInfo,
    Disclaimer,
    EnvironmentInfo,
    RecordingSummary,
    Results,
    RuleInfo,
    RulepackInfo,
    ScanFile,
    ScanResult,
    Summary,
    ToolInfo,
)
from neurogrid.quality import describe as describe_quality
from neurogrid.quality import finite_values
from neurogrid.report.texts import disclaimer

# Libraries whose versions can change a result (A-11): readers, the BIDS validator and its runtime (A-48).
RESULT_LIBRARIES = (
    "bids-validator-deno",
    "deno",
    "edfio",
    "h5py",
    "jinja2",
    "mne",
    "numpy",
    "pydantic",
    "pymatreader",
    "scipy",
)
# Exception patterns made only of wildcards, extensions and pseudonymous IDs reveal no names (A-51).
_SAFE_PATTERN_PART = re.compile(r"^(\*\*|\*|\*\.[A-Za-z0-9]+|rec-[0-9a-f]{8}(\.[A-Za-z0-9]+)?)$")


@dataclass(frozen=True)
class Target:
    """The dataset root and, if a single file was given, that file relative to the root."""

    root: Path
    only: PurePosixPath | None


def resolve_target(raw: str | Path) -> Target:
    """The dataset root, or the folder of a single data file. Folders on the way may be links (the operator
    chose the path); inside the dataset links are never followed, and neither is a linked single file."""
    path = check_operator_path(raw)
    if not path.exists():
        raise InputError("input.not_found")
    known = ", ".join(sorted(ADAPTERS))
    if path.is_dir():
        if path.suffix.lower() in KNOWN_UNSUPPORTED_DIRS:  # an EGI/MEF3 recording, not a dataset (A-74)
            raise InputError("input.unknown_format", file=path.name[:120], known=known)
        return Target(root=path.resolve(), only=None)
    if is_link(path):
        raise UnsafePathError("path.link")  # a linked single file is not followed (A-52)
    suffix = path.suffix.lower()
    if suffix not in ADAPTERS:
        raise InputError("input.unknown_format", file=path.name[:120], known=known)
    real = path.resolve()  # the name as stored, so that IDs and keys do not depend on how it was typed
    return Target(root=real.parent, only=PurePosixPath(real.name))


def tool_info() -> ToolInfo:
    return ToolInfo(version=neurogrid.__version__)


def disclaimer_block() -> Disclaimer:
    return Disclaimer(zh=disclaimer("zh"), en=disclaimer("en"))


def environment_info() -> EnvironmentInfo:
    libraries = {}
    for name in RESULT_LIBRARIES:
        try:
            libraries[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            libraries[name] = "missing"
    blas_threads = 1  # the quality metrics always compute with one BLAS thread (A-11, neurogrid.quality)
    return EnvironmentInfo(
        python=".".join(platform.python_version_tuple()[:2]),
        platform=f"{sys.platform}-{platform.machine().lower()}",
        libraries=libraries,
        blas_threads=blas_threads,
    )


# --- scan --------------------------------------------------------------------------------------


def run_scan(raw_target: str | Path, *, show_paths: bool = False) -> ScanResult:
    """The inventory (NG-F01). An orphan .eeg/.fdt, which no header names, is listed under ``orphans``,
    not as a format NeuroGrid cannot read (A-74, A-77; check reports it as format.orphan_companion)."""
    from neurogrid.io import ORPHAN_SUFFIXES

    target = resolve_target(raw_target)
    found = scan(target.root, show_paths=show_paths, only=target.only)
    subjects = found.subjects
    if not found.is_bids and found.recordings:
        from neurogrid.metadata import mapped_entities

        cfg = config_module.load(None, target.root).config
        # Annotation-only files (hypnograms) are no recordings and need no mapping, as in convert (A-77).
        mapped = [item for item in found.recordings if not _annotations_only(target.root, item)]
        labels = [mapped_entities(item, cfg).get("subject") for item in mapped]
        if mapped and all(labels):  # known only when every recording is mapped (A-72, A-77)
            subjects = len(set(labels))
    formats: dict[str, int] = {}
    for item in found.recordings:
        name = ADAPTERS[item.suffix].format
        formats[name] = formats.get(name, 0) + 1
    return ScanResult(
        disclaimer=disclaimer_block(),
        tool=tool_info(),
        is_bids=found.is_bids,
        formats=dict(sorted(formats.items())),
        subjects=subjects,
        recordings=[
            ScanFile(id=f.display_id, format=ADAPTERS[f.suffix].format, size_bytes=f.size_bytes)
            for f in found.recordings
        ],
        unsupported=[_scan_file(f) for f in found.unsupported if f.suffix not in ORPHAN_SUFFIXES],
        orphans=[_scan_file(f) for f in found.unsupported if f.suffix in ORPHAN_SUFFIXES],
        unreadable=[ScanFile(id=f.display_id, format=None, size_bytes=0) for f in found.unreadable],
        other_files=len(found.other),
        links_skipped=found.links_skipped,
        suspicious_names=found.suspicious_names,
        total_bytes=found.total_bytes,
    )


def _scan_file(item: FoundFile) -> ScanFile:
    """A data file NeuroGrid does not read, with its extension as format ('FIF.GZ', 'FDT')."""
    return ScanFile(id=item.display_id, format=item.suffix.lstrip(".").upper(), size_bytes=item.size_bytes)


def _annotations_only(root: Path, item: FoundFile) -> bool:
    """An EDF+/BDF+ file with annotation channels only (A-74, A-77). Only EDF and BDF carry annotation
    channels, and their headers are small, so scan stays an inventory without reading data."""
    from neurogrid.convert import annotations_only, read_header

    return item.suffix in (".edf", ".bdf") and annotations_only(read_header(root, item))


# --- rule packs --------------------------------------------------------------------------------


def _locate_rulepack(ref: str, project_root: Path | None) -> tuple[str, Path | None]:
    """A key for de-duplication and the file to read (None for a built-in pack).

    Paths from the toml (``project_root`` set) are relative to the project root and may not leave it (A-52,
    A-66); command-line paths are operator paths, relative to the working directory.
    """
    if BUILTIN_RULEPACK.match(ref):
        return f"builtin:{ref}", None
    if project_root is None:
        path = check_operator_path(ref)
        if not path.is_file():
            raise RulepackError("rulepack.not_found", rulepack=path.name[:120])
    else:
        relative = check_relative(ref)
        try:
            path = resolve_within(project_root, relative)
        except FileNotFoundError:
            raise RulepackError("rulepack.not_found", rulepack=relative.name[:120]) from None
        if not path.is_file():
            raise RulepackError("rulepack.not_found", rulepack=relative.name[:120])
    return "path:" + os.path.normcase(str(path.resolve())), path


def load_rulepack_ref(ref: str, *, project_root: Path | None = None) -> LoadedRulepack:
    """A built-in name, a path from the command line (``project_root`` None) or a path from neurogrid.toml."""
    _key, path = _locate_rulepack(ref, project_root)
    if path is None:
        resource = resources.files("neurogrid.rulepacks").joinpath(f"{ref}.yaml")
        if not resource.is_file():
            raise RulepackError("rulepack.not_found", rulepack=ref)
        return load_rulepack(resource.read_bytes(), origin="builtin")
    return load_rulepack(read_limited(path, MAX_YAML_BYTES), origin="path")


def resolve_rulepacks(
    cfg: Config, cli_refs: list[str], *, allow_draft: bool, project_root: Path | None = None
) -> list[LoadedRulepack]:
    """``core`` unless the toml lists packs (A-02), then the --rulepack packs.

    The same file named twice (in any spelling) is loaded once; two files with the same pack name are an
    error.
    """
    refs: list[tuple[str, Path | None]] = []
    if cfg.check.rulepacks is None:
        refs.append(("core", None))
    else:
        root = project_root if project_root is not None else Path.cwd()
        refs.extend((ref, root) for ref in cfg.check.rulepacks)
    refs.extend((ref, None) for ref in cli_refs)
    loaded: list[LoadedRulepack] = []
    names: set[str] = set()
    seen: set[str] = set()
    for ref, base in refs:
        key, _path = _locate_rulepack(ref, base)
        if key in seen:
            continue
        seen.add(key)
        pack = load_rulepack_ref(ref, project_root=base)
        if pack.pack.rulepack in names:
            raise RulepackError("rulepack.duplicate_pack", rulepack=pack.pack.rulepack)
        if pack.pack.source_status is SourceStatus.PLACEHOLDER and not allow_draft:
            raise RulepackError("rulepack.placeholder_needs_flag", rulepack=pack.pack.rulepack)
        names.add(pack.pack.rulepack)
        loaded.append(pack)
    validate_against_registry(loaded, REGISTRY)
    return loaded


# --- check -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckOptions:
    rulepacks: tuple[str, ...] = ()
    config_path: Path | None = None
    strict: bool = False
    as_of: date | None = None
    allow_draft_rulepacks: bool = False
    show_paths: bool = False
    work_base: Path | None = None  # where the run's private work folder is created (A-54); default: temp
    jobs: int = 1  # processes for the signal quality jobs (E3 --jobs); results do not depend on it
    manifest_path: Path | None = None  # --manifest (CLI-04/CLI-06, A-22); None: the default location
    evidence_path: Path | None = None  # --evidence (A-15); None: the default location


def run_check(raw_target: str | Path, options: CheckOptions | None = None) -> Results:
    options = options or CheckOptions()
    target = resolve_target(raw_target)
    config_path = check_operator_path(options.config_path) if options.config_path else None
    loaded_config = config_module.load(config_path, target.root)
    cfg = loaded_config.config
    as_of = options.as_of or cfg.check.as_of or date.today()
    strict = options.strict or cfg.check.strict
    packs = resolve_rulepacks(
        cfg,
        list(options.rulepacks),
        allow_draft=options.allow_draft_rulepacks,
        project_root=loaded_config.project_root,
    )

    found = scan(target.root, show_paths=options.show_paths, only=target.only)
    check_ids = {rule.check for loaded in packs for rule in loaded.pack.rules}
    base = options.work_base if options.work_base is not None else Path(tempfile.gettempdir()) / "neurogrid"
    with work_directory(base) as work:
        ctx = CheckContext.build(
            found,
            cfg,
            work=work,
            project_root=loaded_config.project_root,
            show_paths=options.show_paths,
            strict=strict,
            as_of=as_of,
            manifest_path=options.manifest_path,
            evidence_path=options.evidence_path,
        )
        stream = bool(check_ids & STREAM_CHECKS)
        sample = bool(check_ids & SAMPLE_CHECKS)
        if stream or sample:
            ctx.compute_quality(stream=stream, sample=sample, jobs=options.jobs)
        measurements = measure(ctx, check_ids)
    result = engine.run(
        engine.EngineInput(
            packs=packs,
            registry=REGISTRY,
            measurements=measurements,
            as_of=as_of,
            overrides=cfg.overrides(),
            exceptions=cfg.exceptions,
        )
    )
    plain_names = found.is_bids or options.show_paths
    notices = list(result.notices)
    if not found.is_bids and any(check_id.startswith("bids.") for check_id in check_ids):
        notices.append(Notice(level=Severity.INFO, message_key="notice.bids_not_checked"))  # A-03
    if found.links_skipped:
        notices.append(
            Notice(
                level=Severity.WARNING,
                message_key="notice.links_skipped",
                params={"count": found.links_skipped},
            )
        )
    if found.suspicious_names:
        notices.append(
            Notice(
                level=Severity.INFO,
                message_key="notice.names_look_identifying",
                params={"count": found.suspicious_names},
            )
        )
    exceptions = [
        use.model_copy(
            update={
                "entry": use.entry.model_copy(
                    update={"object": _shown_pattern(use.entry.object, plain_names)}
                )
            }
        )
        for use in result.exceptions
    ]
    return Results(
        disclaimer=disclaimer_block(),
        tool=tool_info(),
        environment=environment_info(),
        dataset=_dataset_info(cfg, found, packs),
        rulepacks=[
            RulepackInfo(
                name=p.pack.rulepack,
                version=p.pack.version,
                source=p.pack.source,
                source_status=p.pack.source_status,
                norm=p.pack.norm,
                sha256=p.sha256,
            )
            for p in packs
        ],
        rules=[
            RuleInfo(
                id=rule.id,
                rulepack=p.pack.rulepack,
                clause=rule.clause,
                title_zh=rule.title_zh,
                title_en=rule.title_en,
                phase=rule.phase,
                check=rule.check,
                severity=rule.severity,
                verification=rule.verification,
                source_status=p.pack.source_status,
            )
            for p in packs
            for rule in p.pack.rules
        ],
        config=ConfigInfo(
            canonical_sha256=cfg.canonical_sha256(),
            as_of=as_of,
            seed=cfg.check.seed,
            strict=strict,
            sampling=canonical.normalize(cfg.sampling.model_dump(mode="json")),
            effective_params=result.effective_params,
            effective_settings=_effective_settings(cfg, plain_names),
        ),
        recordings=_recording_summaries(ctx),
        findings=result.findings,
        passed=result.passed,
        exceptions=exceptions,
        notices=notices,
        summary=Summary(
            phases=result.phases,
            coverage=result.coverage,
            errors=sum(p.errors for p in result.phases.values()),
            warnings=sum(p.warnings for p in result.phases.values()),
            exit_code=result.exit_code,
        ),
    )


def _shown_pattern(pattern: str | None, plain_names: bool) -> str | None:
    """In raw folders without --show-paths an exception pattern may contain real folder names (A-51)."""
    if pattern is None or plain_names:
        return pattern
    if all(_SAFE_PATTERN_PART.match(part) for part in pattern.split("/")):
        return pattern
    return "pattern-" + hashlib.sha256(pattern.encode("utf-8")).hexdigest()[:8]


def _effective_settings(cfg: Config, plain_names: bool) -> dict[str, Any]:
    """The effective configuration, cleaned for output (A-51, A-61). Paths in it are relative by
    construction (A-52); exception patterns are shown as in the exceptions block."""
    settings = cfg.model_dump(mode="json")
    for entry in settings.get("exceptions", []):
        entry["object"] = _shown_pattern(entry.get("object"), plain_names)
    normalized: dict[str, Any] = canonical.normalize(settings)
    return normalized


def _dataset_info(cfg: Config, found: DatasetScan, packs: list[LoadedRulepack]) -> Dataset:
    section = cfg.dataset
    description = found.description
    return Dataset(
        id=section.id or "unnamed",
        name=section.name or description.get("Name") or None,
        version=section.version,
        source=section.source,
        license=section.license or description.get("License") or None,
        rulepacks=[p.pack.rulepack for p in packs],
        manifest_hash=None,
        is_bids=found.is_bids,
    )


def _finite_or_none(value: float | None) -> float | None:
    return value if value is not None and math.isfinite(value) else None


def _recording_summaries(ctx: CheckContext) -> list[RecordingSummary]:
    summaries = []
    for rec in ctx.recordings:
        recording = rec.recording
        if recording is None:
            # Entities from file names or the mapping do not depend on the header (A-72).
            entities = rec.metadata.entities
            summaries.append(
                RecordingSummary(
                    id=rec.object_id,
                    format=rec.adapter.format,
                    metadata_sources={name: documented.source for name, documented in entities.items()},
                    **{name: str(documented.value) for name, documented in entities.items()},
                )
            )
            continue
        summaries.append(
            RecordingSummary(
                id=rec.object_id,
                format=recording.format,
                subject=recording.subject,
                session=recording.session,
                task=recording.task,
                run=recording.run,
                sampling_rate_hz=_finite_or_none(recording.sampling_rate_hz),
                duration_s=_finite_or_none(recording.duration_s),
                n_channels=len(recording.channels),
                n_eeg_channels=len(recording.eeg_channels),
                streamable=recording.streamable,
                metadata_sources=dict(recording.metadata_sources),
                metrics=canonical.normalize(finite_values(describe_quality(rec.quality)))
                if rec.quality
                else {},
                sample=(
                    canonical.normalize(finite_values(rec.quality.sample.describe()))
                    if rec.quality and rec.quality.sample
                    else None
                ),
            )
        )
    return summaries


# --- convert -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ConvertSummary:
    """What ``convert`` did, for the console (CLI-02)."""

    converted: int
    skipped: list[tuple[str, str]]  # (displayed ID, reason key)
    missing_fields: dict[str, int]  # field -> number of recordings without a documented value
    name_missing: bool  # dataset_description.json Name written as n/a (no [dataset] name)
    validator_errors: int
    validator_warnings: int
    steps_file: Path

    @property
    def exit_code(self) -> int:
        """0 only if every recording was converted and the validator reports no error (A-77)."""
        return 1 if self.skipped or self.validator_errors or not self.converted else 0


def run_convert(
    raw_target: str | Path,
    out: str | Path,
    *,
    config_path: Path | None = None,
    strip_identifying_headers: bool = False,
    work_base: Path | None = None,
) -> ConvertSummary:
    """Convert, then validate the output (A-77).

    Paths with a comma are refused before anything is written: deno splits its permission lists at commas
    (A-06), so the validator could not run afterwards. The run's work folder (staging, validator output, A-54)
    is created only after input and output were accepted. If the run ends early (tool error, validator
    failure, Ctrl+C), a newly created output is removed and an output folder that was empty is emptied again.
    """
    from neurogrid.convert import convert_to_bids, remove_output
    from neurogrid.validator import ValidatorError
    from neurogrid.validator import run as run_validator

    target = resolve_target(raw_target)
    output = check_operator_path(out)
    checked_config = check_operator_path(config_path) if config_path else None
    cfg = config_module.load(checked_config, target.root).config
    base = work_base if work_base is not None else Path(tempfile.gettempdir()) / "neurogrid"
    for path in (output, base):
        if "," in str(path) or "," in str(path.resolve()):
            raise ValidatorError("validator.comma_path")
    created = not output.exists()
    was_empty = output.is_dir() and not any(output.iterdir())
    finished = False
    try:
        with ExitStack() as stack:
            folders: list[Path] = []

            def work() -> Path:
                if not folders:
                    folders.append(stack.enter_context(work_directory(base)))
                return folders[0]

            result = convert_to_bids(
                target.root,
                output,
                cfg,
                only=target.only,
                strip_identifying_headers=strip_identifying_headers,
                work=work,
            )
            if not result.converted and (created or was_empty):
                # nothing converted: no output that could pass for a BIDS dataset (A-77)
                remove_output(output, keep_folder=not created)
            errors = warnings = 0
            if result.converted:
                validation = run_validator(output, work() / "validator")
                errors = sum(1 for issue in validation.issues if issue.severity == "error")
                warnings = sum(1 for issue in validation.issues if issue.severity == "warning")
        finished = True
    finally:
        if not finished and (created or was_empty):
            remove_output(output, keep_folder=not created)
    missing: dict[str, int] = {}
    for converted in result.converted:
        for name in converted.missing_fields:
            missing[name] = missing.get(name, 0) + 1
    return ConvertSummary(
        converted=len(result.converted),
        skipped=[(item.display_id, reason) for item, reason in result.skipped],
        missing_fields=dict(sorted(missing.items())),
        name_missing=bool(result.converted) and not cfg.dataset.name,
        validator_errors=errors,
        validator_warnings=warnings,
        steps_file=output / ".neurogrid" / "processing_steps.json",
    )
