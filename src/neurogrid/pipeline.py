"""Orchestration of ``scan``, ``check``, ``convert``, ``manifest``, ``verify`` and the NeuroVault commands
(KONZEPT §1.4).

Access events (NV-F03, A-30, A-90, p6 decisions 4): a run that reads the dataset returns a PendingAccess for
the vault it found; the CLI commits it after every output of the run is written (KONZEPT 1.4 step 8), and an
event that cannot be written is a console warning, never exit code 2. check, convert and ``report --config``
append to the vault of their neurogrid.toml (action check, convert, report); scan, manifest and verify, which
read no neurogrid.toml for this (A-82), append to the vault at the dataset's default location only (action
read, without role, purpose or approval reference). A run that ends with exit code 2 records nothing."""

from __future__ import annotations

import hashlib
import itertools
import math
import os
import platform
import re
import sys
from collections import deque
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date, datetime
from importlib import metadata, resources
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import neurogrid
from neurogrid import config as config_module
from neurogrid.checks import access as access_checks
from neurogrid.checks import ai_dataset
from neurogrid.checks import annotation as annotation_checks
from neurogrid.checks import consent as consent_checks
from neurogrid.checks import evidence as evidence_module
from neurogrid.checks import provenance as provenance_checks
from neurogrid.checks import retention as retention_checks
from neurogrid.checks.context import CheckContext
from neurogrid.checks.quality import SAMPLE_CHECKS, STREAM_CHECKS
from neurogrid.checks.registry import REGISTRY, measure
from neurogrid.config import BUILTIN_RULEPACK, Config
from neurogrid.io import ADAPTERS, KNOWN_UNSUPPORTED_DIRS
from neurogrid.io.discover import DatasetScan, FoundFile, pseudonym, scan, shown_extension
from neurogrid.io.identifying import annotator_pseudonym, dates_or_times, display_text, looks_identifying
from neurogrid.io.provenance import (
    KNOWN_CONTROL_FILES,
    comparison_exclusions,
    inside,
    is_bids_folder,
    load_sources,
    show,
    shown_suffix,
    shown_target,
    validator_listing,
    vault_exclusions,
)
from neurogrid.kernel import canonical, engine
from neurogrid.kernel.errors import ConfigError, InputError, RulepackError, UnsafePathError
from neurogrid.kernel.findings import Notice, Severity, SourceStatus
from neurogrid.kernel.provenance import (
    DEFAULT_MANIFEST,
    DEVIATION_KINDS,
    Exclusions,
    Manifest,
    ManifestError,
    build_manifest,
    compare,
    manifest_bytes,
    read_manifest,
)
from neurogrid.kernel.rules import LoadedRulepack, load_rulepack, validate_against_registry
from neurogrid.kernel.safety import (
    MAX_YAML_BYTES,
    check_operator_path,
    check_relative,
    is_link,
    read_limited,
    resolve_within,
    temp_work_base,
    work_directory,
)
from neurogrid.model.access import AccessEvent
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
from neurogrid.vault import consents as vault_consents
from neurogrid.vault import ledger
from neurogrid.vault import lock as vault_lock
from neurogrid.vault import retention as vault_retention
from neurogrid.vault import risks as vault_risks
from neurogrid.vault import roles as vault_roles
from neurogrid.vault import store as vault_store
from neurogrid.vault.lock import VaultLocked
from neurogrid.vault.roles import role_looks_identifying, validate_role
from neurogrid.vault.store import VaultLocation

if TYPE_CHECKING:
    from neurogrid.report.render import VaultView

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
# Exception and annotator patterns made only of wildcards and pseudonymous IDs, each with at most one
# extension that the one suffix rule of file names shows (discover.shown_extension, A-70), reveal no names,
# dates or clock times (A-51); _shown_pattern shows any other pattern as pattern-<sha8> (A-69).
_SAFE_PATTERN_PART = re.compile(
    r"\*\*|\*|\*(?P<wildcard_extension>\.[A-Za-z0-9]+)"
    r"|rec-[0-9a-f]{8}(?P<pseudonym_extension>\.[A-Za-z0-9]+)?"
)


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
    # called with the number of recordings computed again after a process of --jobs died (console only, A-89)
    on_recompute: Callable[[int], None] | None = None
    manifest_path: Path | None = None  # --manifest (CLI-04/CLI-06, A-22); None: the default location
    evidence_path: Path | None = None  # --evidence (A-15); None: the default location
    role: str | None = None  # --role (CLI-03, A-31): the role of the run's access event, over [vault] role


@dataclass(frozen=True)
class CheckRun:
    """A check run: its results and the access event to append after results.json is written (None without
    a vault: none at the vault path, or a single file as target)."""

    results: Results
    access: PendingAccess | None


@dataclass(frozen=True)
class _CheckStart:
    target: Target
    loaded_config: config_module.LoadedConfig
    role: str | None  # the role of the run's event: --role over [vault] role (A-31)
    vault: VaultLocation | None  # None for a single file, which has no vault


def _check_start(raw_target: str | Path, options: CheckOptions) -> _CheckStart:
    """What a check run settles before any data work: --role (exit 2 also without a vault, p6 decisions 4),
    the target, neurogrid.toml and the vault, where a link in the vault path or a path that is no folder ends
    the run with exit 2 whichever checks are loaded: the run appends its event there (p6 decisions 2)."""
    if options.role is not None:
        validate_role(options.role)
    target = resolve_target(raw_target)
    config_path = check_operator_path(options.config_path) if options.config_path else None
    loaded_config = config_module.load(config_path, target.root)
    cfg = loaded_config.config
    role = options.role if options.role is not None else cfg.vault.role
    vault = None if target.only is not None else _run_vault(loaded_config.project_root, cfg)
    return _CheckStart(target, loaded_config, role, vault)


def check_run(raw_target: str | Path, options: CheckOptions | None = None) -> CheckRun:
    """A check run and the access event to append after its results are written (the CLI commits it): the
    event's fields are validated before the data are read (errors.vault.text_invalid, exit 2)."""
    options = options or CheckOptions()
    start = _check_start(raw_target, options)
    pending = None
    if start.vault is not None and start.vault.state == "present":
        pending = _pending(start.vault, start.loaded_config.config, start.role, "check")
    return CheckRun(run_check(raw_target, options), pending)


def run_check(raw_target: str | Path, options: CheckOptions | None = None) -> Results:
    """The results of a check run; no access event is appended (check_run returns it)."""
    options = options or CheckOptions()
    start = _check_start(raw_target, options)
    target, loaded_config, role, vault = start.target, start.loaded_config, start.role, start.vault
    cfg = loaded_config.config
    as_of = options.as_of or cfg.check.as_of or date.today()
    strict = options.strict or cfg.check.strict
    manifest_path = _explicit_manifest(options.manifest_path)
    packs = resolve_rulepacks(
        cfg,
        list(options.rulepacks),
        allow_draft=options.allow_draft_rulepacks,
        project_root=loaded_config.project_root,
    )
    # evidence.yaml is a control file (C2): an invalid one ends the run before the data are read
    evidence = evidence_module.load(options.evidence_path, target.root)

    found = scan(target.root, show_paths=options.show_paths, only=target.only)
    check_ids = {rule.check for loaded in packs for rule in loaded.pack.rules}
    base = options.work_base if options.work_base is not None else temp_work_base()
    with work_directory(base) as work:
        ctx = CheckContext.build(
            found,
            cfg,
            work=work,
            project_root=loaded_config.project_root,
            show_paths=options.show_paths,
            strict=strict,
            as_of=as_of,
            manifest_path=manifest_path,
            evidence_path=options.evidence_path,
            vault=vault,
        )
        if check_ids & ai_dataset.CHECKS:  # control files first: an invalid splits.tsv ends with exit 2 (C2)
            ai_dataset.structure(ctx)
        if provenance_checks.DOCUMENTED in check_ids and not ctx.provenance().single_file:
            ctx.provenance().sources()  # likewise an invalid provenance.yaml, before the signal pass (C2)
        if check_ids & consent_checks.CHECKS and not found.single_file:
            # M14 (A-30, A-91): the consent records are a control file too; a single file has no vault
            ai_dataset.structure(ctx)
            ctx.consents = vault_consents.load_for_check(
                target.root, loaded_config.project_root, cfg.vault.path
            )
            ctx.consent_required = strict or cfg.consent.configured
        _load_vault_files(ctx, check_ids, vault)  # the registers are control files too (A-93 to A-95)
        stream = bool(check_ids & (STREAM_CHECKS | ai_dataset.STREAM_CHECKS))  # M12 needs the signal hash
        sample = bool(check_ids & SAMPLE_CHECKS)
        if stream or sample:
            ctx.compute_quality(
                stream=stream, sample=sample, jobs=options.jobs, on_recompute=options.on_recompute
            )
        measurements = measure(ctx, check_ids)
        ai_outputs = ai_dataset.outputs(ctx, check_ids)
    result = engine.run(
        engine.EngineInput(
            packs=packs,
            registry=REGISTRY,
            measurements=measurements,
            as_of=as_of,
            overrides=cfg.overrides(),
            exceptions=cfg.exceptions,
            evidence=evidence.entries,
            document_check=evidence.checker(),
            strict=strict,
        )
    )
    manifest = ctx.provenance().info()
    plain_names = found.is_bids or options.show_paths
    notices = list(result.notices)
    identifying_evidence = evidence_module.identifying_entries(evidence.entries)
    if identifying_evidence:
        notices.append(
            Notice(
                level=Severity.INFO,
                message_key="notice.evidence_looks_identifying",
                params={"count": identifying_evidence},
            )
        )
    notices.extend(ai_outputs.notices)
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
    if (
        target.only is None
        and options.work_base is not None
        and options.work_base.resolve().is_relative_to(target.root)
    ):
        # results.json and the run's work folder land in the dataset: a manifest made later covers them, and a
        # later check or verify reports them as new files (A-82, critic X15). A single file is no dataset
        # (A-66): no manifest covers its folder, so there is nothing to warn about.
        notices.append(Notice(level=Severity.WARNING, message_key="notice.output_inside_dataset"))
    notices.extend(annotation_checks.notices(ctx))  # M10: files and rows that could not be used (A-80)
    notices.extend(consent_checks.notices(ctx, check_ids))  # M14: counts only (A-51)
    notices.extend(access_checks.notices(ctx, check_ids))  # the registers: counts only (A-51, A-93)
    notices.extend(retention_checks.notices(result.findings))  # NV05-03: the reminder on the console (A-94)
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
    settings = _effective_settings(cfg, plain_names, show_paths=options.show_paths)
    settings["vault"]["role"] = role  # the role of the run's event: --role over [vault] role (A-31)
    return Results(
        disclaimer=disclaimer_block(),
        tool=tool_info(),
        environment=environment_info(),
        dataset=_dataset_info(cfg, found, packs, manifest_hash=manifest.sha256),
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
                severity=rule.effective_severity(strict),
                strict_severity=rule.strict_severity,
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
            effective_settings=settings,
            evidence_sha256=evidence.sha256,
            consents_sha256=ctx.consents.sha256 if ctx.consents is not None else None,
            roles_sha256=ctx.roles.sha256 if ctx.roles is not None else None,
            retention_sha256=ctx.retention.sha256 if ctx.retention is not None else None,
            risks_sha256=ctx.risks.sha256 if ctx.risks is not None else None,
        ),
        recordings=_recording_summaries(ctx),
        findings=result.findings,
        passed=result.passed,
        evidence=result.evidence,
        exceptions=exceptions,
        notices=notices,
        summary=Summary(
            phases=result.phases,
            coverage=result.coverage,
            errors=sum(p.errors for p in result.phases.values()),
            warnings=sum(p.warnings for p in result.phases.values()),
            exit_code=result.exit_code,
            open_evidence=sum(p.open_evidence for p in result.phases.values()),
        ),
        duplicates=ai_outputs.duplicates,
        ai=ai_outputs.summary,
        manifest=manifest,
        consent=consent_checks.summary(ctx, check_ids),  # M14 subjects per use, for the report (A-91)
    )


# The checks that read a register of the vault (A-93 to A-95): CORE-NV04-01 reads roles.yaml, CORE-NV05-01
# and CORE-NV05-03 (every check whose ID starts with RETENTION_CHECKS) retention.yaml, CORE-M14-02
# risks.yaml. CORE-NV05-02 (pia.edited) reads the PIA files itself.
ROLES_CHECK = "roles.permitted"
RETENTION_CHECKS = "retention."
RISKS_CHECK = "consent.reconsent"


def _load_vault_files(ctx: CheckContext, check_ids: set[str], vault: VaultLocation | None) -> None:
    """Read the registers of the vault that a loaded rule needs into ``ctx`` (ctx.roles, ctx.retention,
    ctx.risks), right after the consent records and before the signal pass: they are control files, so an
    invalid one ends the run with exit 2 before the data are read (C2; errors.roles.*, errors.retention.*
    with too_short, errors.risks.*, errors.vault.link {part}). Nothing is read for a single file, which has
    no vault (``vault`` None: the fields stay None); a vault path without a vault gives the state no_vault,
    a vault without the file no_file. config.<file>_sha256 of results.json comes from these fields."""
    if vault is None:
        return
    if ROLES_CHECK in check_ids:
        ctx.roles = vault_roles.load_for_check(vault)
    if any(check_id.startswith(RETENTION_CHECKS) for check_id in check_ids):
        ctx.retention = vault_retention.load_for_check(vault)
    if RISKS_CHECK in check_ids:
        ctx.risks = vault_risks.load_for_check(vault)


def _explicit_manifest(raw: Path | None) -> Path | None:
    """--manifest is an operator path (A-66). A file that does not exist is a tool error (exit 2, A-82),
    unlike a missing manifest at the default location, which is a finding (CORE-M13-01)."""
    if raw is None:
        return None
    path = check_operator_path(raw)
    if not path.is_file():
        raise ManifestError("manifest.not_found")
    return path


def _safe_pattern_part(part: str) -> bool:
    """A part between '/' of a pattern that reveals nothing (_SAFE_PATTERN_PART): '**', '*', '*.<ext>' or
    'rec-<sha8>' with an optional '.<ext>', where the extension, in lower case as file names are classified,
    is one that discover.shown_extension shows next to a pseudonym. A digit run, a date, a year or a clock
    time written as the extension ('*.19610312', 'rec-<sha8>.1961', '*.10pm') is not."""
    match = _SAFE_PATTERN_PART.fullmatch(part)
    if match is None:
        return False
    extension = match.group("wildcard_extension") or match.group("pseudonym_extension")
    return extension is None or shown_extension(extension.lower()) != ""


def _shown_pattern(pattern: str | None, plain_names: bool) -> str | None:
    """In raw folders without --show-paths an exception pattern may contain real folder names, and its
    extension a date or a clock time (A-51): it is shown only if every part is _safe_pattern_part."""
    if pattern is None or plain_names:
        return pattern
    if all(_safe_pattern_part(part) for part in pattern.split("/")):
        return pattern
    return "pattern-" + hashlib.sha256(pattern.encode("utf-8")).hexdigest()[:8]


# Configuration values that can carry file names, folder names or names derived from them (A-51, C4). In raw
# folders without --show-paths they appear as in findings: a file path as its pseudonymous file name
# (rec-<sha8>.<ext>, A-70), a pattern as pattern-<sha8> (A-69), an annotator as ann-<sha8> (C5). A control
# file (ai.splits, A-81) keeps its name only if it is one of NeuroGrid's fixed names in .neurogrid/, which
# identify nobody (as manifest/verify show them, A-82); any other path is shown as a file. Each entry is
# (section, key, row key or None, kind); a row key names the key inside each row of a list of tables.
_HIDDEN_SETTINGS: tuple[tuple[str, str, str | None, str], ...] = (
    ("convert", "pattern", None, "pattern"),
    ("convert", "files", "path", "file"),
    ("annotation", "files", "path", "file"),
    ("annotation", "files", "recording", "file"),
    ("annotation", "files", "annotator", "annotator"),
    ("annotation", "annotators", None, "pattern"),
    ("ai", "splits", None, "control_file"),
)


def _shown_setting(value: Any, kind: str) -> Any:
    """A path-bearing configuration value as raw folders show it without --show-paths (A-51, C4)."""
    if isinstance(value, list):
        return [_shown_setting(item, kind) for item in value]
    if not isinstance(value, str):
        return value
    if kind == "control_file":
        if PurePosixPath(value.replace("\\", "/")).as_posix() in KNOWN_CONTROL_FILES:
            return value
        kind = "file"
    if kind == "file":
        relative = PurePosixPath(value.replace("\\", "/"))
        return pseudonym(relative) + shown_suffix(relative.name)  # an odd extension is left out (A-51)
    if kind == "annotator":
        return annotator_pseudonym(value)
    return _shown_pattern(value, plain_names=False)


# Annotator values of the configuration. Path values are shown as configured in BIDS, but annotator IDs are
# names of people as often as codes: without --show-paths they follow the display rule of the annotator IDs
# that findings show from events.tsv (C5, "Freitext in Ausgaben"), else ann-<sha8> or pattern-<sha8>.
_ANNOTATOR_SETTINGS: tuple[tuple[str, str, str | None, str], ...] = (
    ("annotation", "files", "annotator", "annotator"),
    ("annotation", "annotators", None, "pattern"),
)


# What a wildcard of an annotator pattern stands for next to the pattern's fixed text (kernel.glob): '?' one
# character (a separator, a letter in either case, a digit, or a separator of dates and clock times as in
# 12.03.1961, 12/03/1961, 1961-03-12, 22:31 and 22h31), '*' also nothing. A pattern with more wildcards than
# MAX_SHOWN_PATTERN_WILDCARDS is not shown (at most 10**3 = 1000 values to test per pattern, A-53).
_DATE_TIME_FILLS = (".", ":", "-", "/", "h")
_WILDCARD_FILLS = {
    "?": (" ", "a", "A", "0", *_DATE_TIME_FILLS),
    "*": ("", " ", "a", "A", "0", *_DATE_TIME_FILLS),
}
_WILDCARD = re.compile(r"([*?])")
MAX_SHOWN_PATTERN_WILDCARDS = 3


def _pattern_displayable(pattern: str) -> bool:
    """A pattern is shown only if no value its fixed text spells, with each wildcard filled in independently
    (_WILDCARD_FILLS), is one the display rule hides (C5): display_text must show every value filled with
    separators, letters and digits only, and no value with a separator of dates and clock times
    (_DATE_TIME_FILLS) may spell a date, a year or a clock time (dates_or_times, ':' read as the '.' of the
    clock-time rule). Such a value is judged by its dates and clock times only, because '/' on both sides
    of a word would read as a folder path and ':' is no A-17 character. Thus 'Zhang*San' (a separator),
    'Zh?ng San' (a letter), 'Wang W?i' and 'Zhang S*' are hidden like the names they spell, 'night 22?31',
    '10?30pm' and 'born 12?03?1961' like the clock times and dates, while 'scorer*' and '*scorer*' stay.
    Other glob syntax ('[...]') is no A-17 character, so such a pattern is hidden."""
    pieces = _WILDCARD.split(pattern)  # fixed text and wildcards alternate: text, wildcard, text, ...
    texts, wildcards = pieces[::2], pieces[1::2]
    if len(wildcards) > MAX_SHOWN_PATTERN_WILDCARDS:
        return False
    for fills in itertools.product(*(_WILDCARD_FILLS[wildcard] for wildcard in wildcards)):
        value = texts[0] + "".join(fill + text for fill, text in zip(fills, texts[1:], strict=True))
        if any(fill in _DATE_TIME_FILLS for fill in fills):
            if dates_or_times(value.replace(":", ".")):
                return False
        elif value and display_text(value).shown is None:  # '*' alone as nothing spells nothing
            return False
    return True


def _displayed_annotator(value: Any, kind: str) -> Any:
    """An annotator ID ("annotator") or pattern ("pattern") of the configuration as BIDS datasets show it
    without --show-paths: as configured if display_text shows it (a pattern: _pattern_displayable), else as
    in raw folders."""
    if isinstance(value, list):
        return [_displayed_annotator(item, kind) for item in value]
    if not isinstance(value, str):
        return value
    shown = _pattern_displayable(value) if kind == "pattern" else display_text(value).shown is not None
    return value if shown else _shown_setting(value, kind)


def _replace_settings(
    settings: dict[str, Any],
    table: tuple[tuple[str, str, str | None, str], ...],
    shown: Callable[[Any, str], Any],
) -> None:
    """Replace each value named in ``table`` by ``shown(value, kind)``; a row key names the key inside each
    row of a list of tables."""
    for section, key, row_key, kind in table:
        holder = settings.get(section, {})
        if row_key is None:
            holder[key] = shown(holder.get(key), kind)
            continue
        for row in holder.get(key) or []:
            row[row_key] = shown(row.get(row_key), kind)


def _effective_settings(cfg: Config, plain_names: bool, *, show_paths: bool = False) -> dict[str, Any]:
    """The effective configuration, cleaned for output (A-51, A-61). Paths in it are relative by
    construction (A-52); exception patterns are shown as in the exceptions block, and in raw folders without
    --show-paths the path-bearing values of _HIDDEN_SETTINGS are replaced (C4). In BIDS datasets without
    --show-paths the annotator values follow the display rule of C5 (_ANNOTATOR_SETTINGS)."""
    settings = cfg.model_dump(mode="json")
    for entry in settings.get("exceptions", []):
        entry["object"] = _shown_pattern(entry.get("object"), plain_names)
    if not plain_names:
        _replace_settings(settings, _HIDDEN_SETTINGS, _shown_setting)
    elif not show_paths:
        _replace_settings(settings, _ANNOTATOR_SETTINGS, _displayed_annotator)
    normalized: dict[str, Any] = canonical.normalize(settings)
    return normalized


def _dataset_info(
    cfg: Config, found: DatasetScan, packs: list[LoadedRulepack], *, manifest_hash: str | None = None
) -> Dataset:
    section = cfg.dataset
    description = found.description
    return Dataset(
        id=section.id or "unnamed",
        name=section.name or description.get("Name") or None,
        version=section.version,
        source=section.source,
        license=section.license or description.get("License") or None,
        rulepacks=[p.pack.rulepack for p in packs],
        manifest_hash=manifest_hash,
        is_bids=found.is_bids,
    )


def _finite_or_none(value: float | None) -> float | None:
    return value if value is not None and math.isfinite(value) else None


def _recording_summaries(ctx: CheckContext) -> list[RecordingSummary]:
    summaries = []
    annotations = annotation_checks.summaries(ctx)  # M10 per object, under metrics["annotation"] (X10)
    for rec in ctx.recordings:
        recording = rec.recording
        annotation = annotations.get(rec.found.relative)
        extra = {"annotation": canonical.normalize(annotation)} if annotation is not None else {}
        if recording is None:
            # Entities from file names or the mapping do not depend on the header (A-72).
            entities = rec.metadata.entities
            summaries.append(
                RecordingSummary(
                    id=rec.object_id,
                    format=rec.adapter.format,
                    metadata_sources={name: documented.source for name, documented in entities.items()},
                    metrics=extra,
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
                metrics={
                    **(
                        canonical.normalize(finite_values(describe_quality(rec.quality)))
                        if rec.quality
                        else {}
                    ),
                    **extra,
                },
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
    access: PendingAccess | None = None  # the event for the source project's vault (p6 decisions 4)

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
    loaded_config = config_module.load(checked_config, target.root)
    cfg = loaded_config.config
    # the source project's vault; convert does not own it as input: a link there means no event and a
    # warning, never exit 2 (p6 decisions 2). A single file has no vault, as for check.
    access = None
    if target.only is None:
        location = vault_store.locate(loaded_config.project_root, cfg.vault.path)
        if location.state != "absent":
            access = _pending(location, cfg, cfg.vault.role, "convert")
    base = work_base if work_base is not None else temp_work_base()
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
        access=access,
    )


# --- manifest and verify (M13, CLI-06) ---------------------------------------------------------------------


def _folder(raw_target: str | Path) -> Path:
    """manifest and verify cover a dataset folder, never a single file (A-82)."""
    target = resolve_target(raw_target)
    if target.only is not None:
        raise InputError("manifest.needs_folder")
    return target.root


@dataclass(frozen=True)
class ManifestRun:
    """What ``manifest`` built (CLI-06, A-22, A-82). ``data`` is None when files or folders could not be read
    (an incomplete manifest would hide changes) or the dataset holds more entries than a manifest lists
    (``too_many_entries``, the limit; dataset data, C2): nothing is written, the command ends with exit 1."""

    root: Path
    target: Path
    manifest: Manifest | None
    data: bytes | None
    unreadable: list[str]  # displayed IDs (A-51)
    too_many_entries: int | None  # the limit (MAX_MANIFEST_ENTRIES) when the dataset holds more entries
    skipped: dict[str, int]  # kind -> number of entries not hashed
    files: int
    total_bytes: int
    # a target inside a BIDS dataset that the bundled BIDS validator lists ("listed") or may list ("maybe":
    # .bidsignore holds patterns NeuroGrid does not evaluate); None: outside the dataset or not listed
    validator_listing: str | None
    # the target inside the dataset as the console names it (relative POSIX path or pseudonymous file name,
    # A-51); None: outside the dataset
    shown_target: str | None
    access: PendingAccess | None = None  # the read event for the default vault (p6 decisions 4)

    @property
    def exit_code(self) -> int:
        return 1 if self.data is None else 0


def run_manifest(
    raw_target: str | Path, out: str | Path | None = None, *, show_paths: bool = False
) -> ManifestRun:
    """Build the manifest of a dataset folder; the caller writes ``data`` to ``target``.

    The default target is <dataset>/.neurogrid/manifest.json (KONZEPT 2.5, A-82; the BIDS validator does not
    enter .neurogrid/), never written through a link, neither a linked .neurogrid nor a linked manifest.json
    (A-52, A-66); the caller creates .neurogrid/ when it is missing. ``out`` is an operator path that may lie
    outside the dataset (D-10 d) and is left out of the file list when it lies inside; inside a BIDS dataset
    the bundled BIDS validator may list it (``validator_listing``: never in hidden folders such as
    .neurogrid/, in the top-level folders it ignores or in what .bidsignore names). Inside a raw folder the
    console names it by its pseudonymous file name unless --show-paths is given or it is the default location
    (``shown_target``, A-51). neurogrid.toml is read from its default location only for [vault] path: the
    access log and lock file of that vault and of the one at the default location, where this command appends
    its read event, are excluded and recorded as such (vault_exclusions). An invalid provenance.yaml or
    processing_steps.json ends with exit 2 (C2)."""
    root = _folder(raw_target)
    loaded = config_module.load(None, root)
    is_bids = is_bids_folder(root)
    sources = load_sources(root, is_bids)
    if sources.converted_problem is not None:
        raise ManifestError("manifest.steps_invalid", problem=sources.converted_problem)
    if out is None:
        target = resolve_within(root, DEFAULT_MANIFEST, must_exist=False)
    else:
        target = check_operator_path(out)
        if target.is_dir():
            raise InputError("output.is_directory")
    recorded = vault_exclusions(root, loaded.project_root, loaded.config.vault.path)
    own = inside(root, target)
    exclusions = Exclusions.of([DEFAULT_MANIFEST.as_posix(), *recorded, *([own] if own else [])])
    built = build_manifest(
        root,
        exclusions,
        excluded=recorded,
        processing_steps=sources.steps,
        software=sources.software(neurogrid.__version__),
    )
    plain = is_bids or show_paths
    skipped: dict[str, int] = {}
    for entry in built.skipped:
        skipped[entry.kind] = skipped.get(entry.kind, 0) + 1
    return ManifestRun(
        root=root,
        target=target,
        manifest=built.manifest,
        data=manifest_bytes(built.manifest) if built.manifest is not None else None,
        unreadable=[show(path, plain=plain).file for path in built.unreadable],
        too_many_entries=built.too_many,
        skipped=dict(sorted(skipped.items())),
        files=len(built.manifest.files) if built.manifest is not None else 0,
        total_bytes=built.total_bytes,
        validator_listing=validator_listing(root, own) if is_bids and own is not None else None,
        shown_target=shown_target(own, plain=plain) if own is not None else None,
        access=read_access(root),
    )


@dataclass(frozen=True)
class VerifyRun:
    """What ``verify`` found (CLI-06, NG-F10, UF-05): displayed names per kind of deviation (A-51, A-70)."""

    root: Path
    manifest_hash: str
    hash_ok: bool
    files: int
    deviations: dict[str, list[str]]
    access: PendingAccess | None = None  # the read event for the default vault (p6 decisions 4)

    @property
    def exit_code(self) -> int:
        """0 = the dataset matches the manifest and its hash; 1 = any deviation (A-12)."""
        return 0 if self.hash_ok and not any(self.deviations.values()) else 1


def run_verify(raw_target: str | Path, manifest_path: str | Path, *, show_paths: bool = False) -> VerifyRun:
    """Compare a dataset folder with a manifest. An unusable manifest is a tool error (exit 2, C2). The
    exclusions come from the manifest itself: verify does not read neurogrid.toml, so a damaged toml is
    reported as changed, never as exit 2 (A-82)."""
    root = _folder(raw_target)
    path = check_operator_path(manifest_path)
    if not path.is_file():
        raise ManifestError("manifest.not_found")
    parsed = read_manifest(path)
    manifest = parsed.manifest
    comparison = compare(root, manifest, comparison_exclusions(root, manifest, path))
    plain = is_bids_folder(root) or show_paths
    deviations: dict[str, list[str]] = {
        kind: [
            show(item.path, plain=plain, kind="unsafe_name" if item.unsafe else None).file
            for item in comparison.of(kind)
        ]
        for kind in DEVIATION_KINDS
    }
    return VerifyRun(
        root=root,
        manifest_hash=manifest.manifest_hash,
        hash_ok=parsed.hash_ok,
        files=comparison.files,
        deviations=deviations,
        access=read_access(root),
    )


# --- NeuroVault: access events and the vault commands (NV-F01, NV-F03, CLI-08, CLI-09; A-30, A-90) ----------

DATASET_OBJECTS = ("**",)  # the object of automatic data events: the whole dataset (an A-14 pattern)


@dataclass(frozen=True)
class PendingAccess:
    """The access event of a run, validated when the run starts (a field that cannot be recorded ends the run
    with exit 2 before the data are read) and appended by ``commit`` after every output of the run is written
    (KONZEPT 1.4 step 8). ``commit`` never raises for an event that cannot be written: its AppendOutcome
    tells why (the vault went missing or became a link, the log is missing or damaged, the vault is locked
    or read-only), and the command warns without changing its exit code (p6 decisions 4)."""

    location: VaultLocation
    role: str | None
    purpose: str | None
    approval_ref: str | None
    action: str
    objects: tuple[str, ...] = DATASET_OBJECTS
    # the event compared with the role register at the start of the run (A-93): a vault.roles.Permission or
    # vault.roles.ROLES_INVALID; None when not compared (read events without a role, a vault not present)
    permission: str | None = None

    def commit(self, now: Callable[[], datetime] = ledger.utc_now) -> ledger.AppendOutcome:
        return ledger.append(
            self.location,
            role=self.role,
            action=self.action,
            objects=self.objects,
            purpose=self.purpose,
            approval_ref=self.approval_ref,
            now=now,
            timeout_s=vault_lock.LOCK_TIMEOUT_S,
        )

    @property
    def role_looks_identifying(self) -> bool:
        return self.role is not None and role_looks_identifying(self.role)

    @property
    def role_warning(self) -> str | None:
        """What the command warns about the role register (cli.vault.role_not_permitted {reason},
        cli.vault.roles_invalid; KONZEPT 2.8): a permission of vault.roles.NOT_PERMITTED or ROLES_INVALID;
        None (silent) without a register, with an empty one or for a permitted access."""
        return vault_roles.role_warning(self.permission)


def _run_vault(project_root: Path, cfg: Config) -> VaultLocation:
    """The vault of a command that owns it as input (check, ``report --config``): a link anywhere in the vault
    path, at the log, its lock file or consents.yaml, and a vault path that is no folder are tool errors
    (errors.vault.link {part}, errors.vault.not_folder; p6 decisions 2); absent and present are returned."""
    location = vault_store.locate(project_root, cfg.vault.path)
    if location.state in ("link", "not_folder"):
        vault_store.require_present(location)
    return location


def _pending(location: VaultLocation, cfg: Config, role: str | None, action: str) -> PendingAccess:
    """The automatic event of a run for ``location``: objects ``**``, purpose and approval reference from
    [vault]. Every field is valid already: [vault] purpose and approval_ref follow the rules of the event when
    neurogrid.toml is read (config.VaultSection: config.invalid naming the field, exit 2 for every command),
    the role there and with --role; check_fields only guards that no event is lost after the outputs."""
    purpose, approval_ref = cfg.vault.purpose, cfg.vault.approval_ref
    ledger.check_fields(
        role=role, action=action, objects=DATASET_OBJECTS, purpose=purpose, approval_ref=approval_ref
    )
    # compared with the role register now, at the start of the run (A-93): the warning describes the
    # register as it was when the access began; a vault that is not present gets no event anyway
    permission = None
    if location.state == "present":
        permission = vault_roles.permission_at(location, role, action, DATASET_OBJECTS)
    return PendingAccess(location, role, purpose, approval_ref, action, permission=permission)


def read_access(raw_target: str | Path) -> PendingAccess | None:
    """The read event of scan, manifest and verify: only the vault at the dataset's default location
    (``<dataset>/.neurogrid/vault``), since they read no neurogrid.toml for it (A-82); no role, purpose or
    approval reference (p6 decisions 4). None without a vault there and for a single file. A link there is
    no tool error for these commands, which do not own the vault: the event is not written (commit returns
    the status link) and the command warns."""
    target = resolve_target(raw_target)
    if target.only is not None:
        return None
    location = vault_store.locate_default(target.root)
    if location.state == "absent":
        return None
    return PendingAccess(location, None, None, None, "read")


def vault_view(location: VaultLocation) -> VaultView:
    """The access log as ``report --config`` shows it (A-30, p6 decisions 7): read with the snapshot rule
    before anything is rendered, so its head is the one before the report's own event. A link or a vault path
    that is no folder are tool errors as in check."""
    from neurogrid.report.render import VaultView

    current = location.refreshed()
    if current.state == "absent":
        return VaultView("not_found")
    if current.state != "present":
        vault_store.require_present(current)
    try:
        size = ledger.snapshot(current, vault_lock.LOCK_TIMEOUT_S)
        verification = ledger.verify_entries(ledger.iter_entries(current.log, size))
    except VaultLocked:
        return VaultView("locked")
    except FileNotFoundError:
        return VaultView("log_missing")
    except OSError:
        return VaultView("unreadable")
    return VaultView(
        "intact" if verification.intact else "broken",
        events=verification.events,
        head=verification.head,
        deviations=len(verification.deviations),
    )


def config_dataset(config_path: Path, vault_path: str) -> Path:
    """The dataset a neurogrid.toml lies in, for ``report --config``, which is given no dataset (A-66): the
    nearest folder at or above the file's folder that holds NeuroGrid's folder ``.neurogrid``, a BIDS
    dataset_description.json or the vault at [vault] path; else the file's folder (a file outside any
    dataset). With it config.project_root_for gives the project root check and the vault commands use for the
    same file inside that dataset: the folder above ``.neurogrid`` for a file in such a folder, else this
    folder; for a file outside the dataset its own folder, unless a folder above it is marked so."""
    folder = config_path.resolve().parent
    for candidate in (folder, *folder.parents):
        if (
            os.path.lexists(candidate / config_module.CONFIG_DIR)
            or is_bids_folder(candidate)
            or vault_store.locate(candidate, vault_path).state != "absent"
        ):
            return candidate
    return folder


def report_vault(config_path: Path) -> tuple[PendingAccess | None, VaultView]:
    """``report --config FILE`` (A-30): the vault of that neurogrid.toml, at the project root check uses for
    the file (A-66; the report knows no dataset, config_dataset finds the one the file lies in), and how the
    report shows it; the report event (action report, objects ``**``) when a vault is present. Without
    --config the report finds no vault and records nothing."""
    path = check_operator_path(config_path)
    if not path.is_file():
        raise ConfigError("config.not_found")
    cfg = config_module.load(path, path.resolve().parent).config
    project_root = config_module.project_root_for(path, config_dataset(path, cfg.vault.path))
    location = _run_vault(project_root, cfg)
    pending = _pending(location, cfg, cfg.vault.role, "report") if location.state == "present" else None
    return pending, vault_view(location)


@dataclass(frozen=True)
class VaultTarget:
    """What a vault command works on: the dataset folder (PATH, default '.'), its configuration (--config,
    else the default location in the folder) and the vault there (A-66)."""

    root: Path
    config: Config
    location: VaultLocation
    is_bids: bool


def vault_target(raw_path: str | Path, config_path: Path | None = None) -> VaultTarget:
    """PATH must be a folder (errors.vault.target_not_folder for a file); an invalid neurogrid.toml or an
    empty --config end with exit 2 like every other command (A-82)."""
    path = check_operator_path(raw_path)
    if not path.exists():
        raise InputError("input.not_found")
    if not path.is_dir():
        raise InputError("vault.target_not_folder")
    root = path.resolve()
    checked = check_operator_path(config_path) if config_path is not None else None
    loaded = config_module.load(checked, root)
    location = vault_store.locate(loaded.project_root, loaded.config.vault.path)
    return VaultTarget(root, loaded.config, location, is_bids_folder(root))


def run_vault_init(raw_path: str | Path, config_path: Path | None = None) -> tuple[vault_store.InitPart, ...]:
    """``vault init`` (CLI-08): create the missing parts of the vault, keep the others byte for byte; no
    access event (the chain starts at the genesis hash)."""
    return vault_store.init_vault(vault_target(raw_path, config_path).location)


def _raw_file(root: Path, item: str, index: int) -> str | None:
    """The raw-folder file that the object ``item`` names when its text is taken as a name, glob characters
    included, and read as the system reads it (Windows: any case, trailing dots and spaces, short names), as
    its relative path in the stored spelling (A-66); None when nothing of that name exists or it is a folder.
    The literal name is looked up before the object counts as a pattern, so ``Zhang[EEG].edf`` is a file when
    one of that name exists. A link at the name or on the way to it is refused (errors.vault.object_link
    {index}, exit 2): links in the dataset are never followed (A-52), so the file behind one has no stored
    name, and its own name would be recorded in clear."""
    parts = [part for part in item.split("/") if part not in ("", ".")]
    if not parts:
        return None
    candidate = root.joinpath(*parts)
    try:
        if not os.path.lexists(candidate):  # a pattern, or a path that does not exist
            return None
    except (OSError, ValueError):  # a name the system refuses (an embedded NUL is refused before)
        return None
    current = root
    for part in parts:
        current = current / part
        if is_link(current):
            raise UnsafePathError("vault.object_link", index=index)
    try:
        if not candidate.is_file():
            return None
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    return resolved.relative_to(root).as_posix() if resolved.is_relative_to(root) else None


def _stored_object(root: Path, item: str, index: int, *, plain: bool) -> str:
    """How a manual object is recorded (NZ-09, A-51): in a raw folder an object that names an existing file
    (_raw_file) by the pseudonymous file name verify shows (rec-<sha8>.<ext>; NeuroGrid's fixed names in
    .neurogrid/ in clear); anything else (BIDS datasets, patterns, folders, paths that do not exist) as given,
    with the note when it looks identifying. The log is part of the P9 export."""
    if plain:
        return item
    stored = _raw_file(root, item, index)
    return item if stored is None else show(stored, plain=False).file


@dataclass(frozen=True)
class VaultLogRun:
    """The event ``vault log`` appended and the warnings it gives (the event is written anyway)."""

    event: AccessEvent
    identifying: bool  # an object, the purpose or the approval reference looks like a name or an ID
    role_identifying: bool  # the role does
    # the role register does not permit the event, or cannot be read (vault.roles.role_warning; A-93)
    role_warning: str | None = None


def run_vault_log(
    raw_path: str | Path,
    config_path: Path | None = None,
    *,
    action: str,
    objects: Sequence[str],
    purpose: str | None,
    approval_ref: str | None,
    role: str | None,
) -> VaultLogRun:
    """``vault log`` (CLI-08, A-31): append one manual event. Role = --role > [vault] role, purpose =
    --purpose > [vault] purpose (both required: errors.vault.role_missing, .purpose_missing), approval
    reference = --approval-ref > [vault] approval_ref > none. Every refusal and every event that cannot be
    written is exit 2 (errors.vault.*); nothing is written then. An event the role register does not permit,
    or a register that cannot be read, is written anyway and only warned about (A-93)."""
    target = vault_target(raw_path, config_path)
    vault_store.require_present(target.location)
    section = target.config.vault
    role = role if role is not None else section.role
    if role is None:
        raise InputError("vault.role_missing")
    validate_role(role)
    purpose = purpose if purpose is not None else section.purpose
    if purpose is None:
        raise InputError("vault.purpose_missing")
    approval_ref = approval_ref if approval_ref is not None else section.approval_ref
    ledger.check_fields(role=role, action=action, objects=objects, purpose=purpose, approval_ref=approval_ref)
    stored = [
        _stored_object(target.root, item, index, plain=target.is_bids)
        for index, item in enumerate(objects, start=1)
    ]
    # the objects as the log records them (pseudonymous in raw folders) are compared with the register
    permission = vault_roles.permission_at(target.location, role, action, stored)
    outcome = ledger.append(
        target.location,
        role=role,
        action=action,
        objects=stored,
        purpose=purpose,
        approval_ref=approval_ref,
        timeout_s=vault_lock.LOCK_TIMEOUT_S,
    )
    if outcome.status != "written" or outcome.event is None:
        raise outcome.error()
    texts = [*stored, purpose, *([approval_ref] if approval_ref else [])]
    return VaultLogRun(
        outcome.event,
        identifying=any(looks_identifying(text) for text in texts),
        role_identifying=role_looks_identifying(role),
        role_warning=vault_roles.role_warning(permission),
    )


SHOWN_ENTRIES = 200  # vault log --show: the newest lines shown, then a count of the earlier ones (A-53)


@dataclass(frozen=True)
class VaultShowRun:
    """``vault log --show`` (D-10 c): the newest SHOWN_ENTRIES lines of the log (entries and unreadable
    lines), how many earlier lines are not shown, and the verification of the same pass."""

    entries: tuple[ledger.Entry, ...]
    earlier: int
    verification: ledger.LogVerification


def _log_size(target: VaultTarget) -> int:
    """The snapshot size of a present vault's log: a missing log is errors.vault.log_missing, a lock not
    obtained in time errors.vault.locked, a log that cannot be read errors.vault.log_unreadable (exit 2)."""
    vault_store.require_present(target.location)
    try:
        return ledger.snapshot(target.location, vault_lock.LOCK_TIMEOUT_S)
    except FileNotFoundError:
        raise InputError("vault.log_missing") from None
    except (VaultLocked, UnsafePathError):
        raise
    except OSError:
        raise InputError("vault.log_unreadable") from None


def run_vault_show(raw_path: str | Path, config_path: Path | None = None) -> VaultShowRun:
    """Read and verify the log in one streaming pass (the lock only while its size is taken), keeping the
    newest SHOWN_ENTRIES lines. Writes no event."""
    target = vault_target(raw_path, config_path)
    size = _log_size(target)
    shown: deque[ledger.Entry] = deque(maxlen=SHOWN_ENTRIES)

    def entries() -> Iterator[ledger.Entry]:
        for entry in ledger.iter_entries(target.location.log, size):
            shown.append(entry)
            yield entry

    try:
        verification = ledger.verify_entries(entries())
    except OSError:
        raise InputError("vault.log_unreadable") from None
    return VaultShowRun(tuple(shown), verification.lines - len(shown), verification)


def run_vault_verify(
    raw_path: str | Path, config_path: Path | None = None, expect_heads: Sequence[str] = ()
) -> ledger.LogVerification:
    """``vault verify`` (CLI-09, NV-F03): the chain and the expected heads (contained semantics). Invalid
    heads are refused before anything is read (errors.vault.bad_head). A missing log is the deviation
    log_missing (exit 1); no vault, a link, a path that is no folder and a lock not obtained in time are
    tool errors (exit 2). Writes no event."""
    heads = [ledger.normalize_head(head) for head in expect_heads]
    target = vault_target(raw_path, config_path)
    vault_store.require_present(target.location)
    try:
        return ledger.verify(target.location, heads, vault_lock.LOCK_TIMEOUT_S)
    except (VaultLocked, UnsafePathError):
        raise
    except OSError:
        raise InputError("vault.log_unreadable") from None
