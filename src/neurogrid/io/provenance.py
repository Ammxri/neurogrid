"""The NeuroGrid side of provenance (M13, NG-F10, A-22, A-82): what the manifest leaves out, the
documentation sources of processing steps and software versions, the manifest state of one check run and how
deviating paths are shown. The format, the walk, the hashes and the comparison live in
neurogrid.kernel.provenance.

Documentation sources (CORE-M13-03):
- ``.neurogrid/provenance.yaml``, written by the user. A control file (C2): invalid content ends the run with
  exit 2 and names the field or line. ``processing_steps`` is a list of DM-07 steps (step, tool, version,
  parameters, input_hash, output_hash); an explicit empty list documents "no processing". ``software`` is a
  list of {name, version}.
- ``.neurogrid/processing_steps.json``, written by ``convert`` (A-77). An integrity artefact (C2): invalid
  content is a finding in ``check`` and exit 2 in ``manifest``.
- ``dataset_description.json`` ``GeneratedBy`` entries with Name and Version (BIDS), as software
  documentation. Only these two fields are read (A-74 allowlist, extended by A-82); they never reach
  results.json.

Display (A-51, A-70, critic X14): in BIDS datasets and with --show-paths a deviating path is shown as stored;
in raw folders as its pseudonymous ID (rec-<sha256(path)[:8]> plus extension, as M01 shows recordings), except
NeuroGrid's own control files in .neurogrid/, whose fixed names identify nobody. Finding keys and exceptions
use the stored path, the pseudonym and the pseudonymous file name, independent of --show-paths (A-68).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from neurogrid.io.discover import _suffix as classify_suffix  # the extension rule of M01 displays (A-70)
from neurogrid.kernel.errors import ConfigError, InputError, UnsafePathError
from neurogrid.kernel.provenance import (
    DEFAULT_MANIFEST,
    VAULT_LOCK,
    VAULT_LOG,
    Comparison,
    Exclusions,
    Manifest,
    ManifestError,
    ManifestStatus,
    ParsedManifest,
    ProcessingStep,
    SoftwareEntry,
    compare,
    name_bytes,
    read_manifest,
    strict_json,
)
from neurogrid.kernel.safety import (
    MAX_YAML_BYTES,
    decode_text,
    is_link,
    load_yaml,
    read_limited,
    resolve_within,
)
from neurogrid.model.results import ManifestInfo

STEPS_FILE = PurePosixPath(".neurogrid", "processing_steps.json")
PROVENANCE_FILE = PurePosixPath(".neurogrid", "provenance.yaml")
DESCRIPTION = "dataset_description.json"
MAX_STEPS_BYTES = 16_000_000
MAX_DESCRIPTION_BYTES = 1_000_000  # as discovery (A-74)
MAX_GENERATED_BY = 100
# NeuroGrid's own files in .neurogrid/ (KONZEPT 2.5, A-30): fixed names, shown in clear in raw folders too.
KNOWN_CONTROL_FILES = frozenset(
    f".neurogrid/{name}"
    for name in (
        "neurogrid.toml",
        "splits.tsv",
        "evidence.yaml",
        "provenance.yaml",
        "processing_steps.json",
        "mapping-template.toml",
        "vault/consents.yaml",
        "vault/roles.yaml",
        "vault/risks.yaml",
        "vault/retention.yaml",
        "vault/access.jsonl",
        "vault/pia/pia.zh.md",
        "vault/pia/pia.en.md",
    )
)
# Extensions shown next to a pseudonym; others (letters outside ASCII, odd characters) are left out (A-51).
_SHOWN_SUFFIX = re.compile(r"^(?:\.[a-z0-9]{1,10}){1,2}$")


# --- documentation sources ------------------------------------------------------------------------------


class SoftwareVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(max_length=200)
    version: str = Field(max_length=80)


class ProvenanceFile(BaseModel):
    """.neurogrid/provenance.yaml (A-52 names it, A-82 defines it)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    processing_steps: list[ProcessingStep] | None = Field(default=None, max_length=100_000)
    software: list[SoftwareVersion] = Field(default_factory=list, max_length=10_000)


def _check_values(value: Any, location: str) -> None:
    """Parameters must be JSON values: they are written into the manifest and hashed canonically (A-61)."""
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
    elif isinstance(value, list):
        for item in value:
            _check_values(item, location)
        return
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                break
            _check_values(item, location)
        else:
            return
    raise ConfigError("provenance.invalid", field=location, problem="value")


def load_provenance_file(root: Path) -> ProvenanceFile | None:
    """The user's provenance.yaml, or None if there is none. Never followed as a link (A-52, A-66)."""
    path = resolve_within(root, PROVENANCE_FILE, must_exist=False)
    if not os.path.lexists(path):
        return None
    if not path.is_file():
        raise ConfigError("provenance.invalid", field="-", problem="not_a_file")
    try:
        data = read_limited(path, MAX_YAML_BYTES)
    except InputError:
        raise ConfigError("provenance.yaml_too_large", limit=MAX_YAML_BYTES) from None
    except OSError:
        raise ConfigError("provenance.unreadable") from None
    text = decode_text(data, ConfigError, "provenance.encoding")
    try:
        raw = load_yaml(text)
    except ConfigError as exc:  # yaml.alias, yaml.duplicate_key, yaml.syntax, yaml.too_large, yaml.too_deep
        raise ConfigError("provenance." + exc.message_key.replace(".", "_"), **exc.params) from None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError("provenance.invalid", field="-", problem="not_mapping")
    try:
        parsed = ProvenanceFile.model_validate(raw, strict=True)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or "-"
        raise ConfigError("provenance.invalid", field=location, problem=first["type"]) from None
    for index, step in enumerate(parsed.processing_steps or []):
        _check_values(step.parameters, f"processing_steps.{index}.parameters")
    return parsed


def load_processing_steps(root: Path) -> tuple[list[ProcessingStep], str | None]:
    """The steps ``convert`` wrote, and the problem if the file cannot be used (link, json, schema, …)."""
    try:
        path = resolve_within(root, STEPS_FILE, must_exist=False)
    except UnsafePathError:
        return [], "link"
    if not os.path.lexists(path):
        return [], None
    if not path.is_file():
        return [], "not_a_file"
    try:
        data = read_limited(path, MAX_STEPS_BYTES)
    except InputError:
        return [], "too_large"
    except OSError:
        return [], "unreadable"
    try:
        raw = strict_json(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return [], "json"
    if not isinstance(raw, list):
        return [], "schema"
    try:
        return [ProcessingStep.model_validate(item, strict=True) for item in raw], None
    except ValidationError:
        return [], "schema"


def _plain_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = "".join(char for char in value if char.isprintable()).strip()
    return text if text and len(text) <= limit else None


def generated_by(root: Path, is_bids: bool) -> list[tuple[str, str]]:
    """(Name, Version) of the dataset_description.json GeneratedBy entries that give both (BIDS only). Dataset
    data: an unreadable description documents nothing and never ends the run (C2)."""
    if not is_bids:
        return []
    path = root / DESCRIPTION
    try:
        if is_link(path) or not path.is_file() or path.stat().st_size > MAX_DESCRIPTION_BYTES:
            return []
        raw = json.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError, RecursionError):
        return []
    entries = raw.get("GeneratedBy") if isinstance(raw, dict) else None
    found: set[tuple[str, str]] = set()
    for entry in entries[:MAX_GENERATED_BY] if isinstance(entries, list) else []:
        if isinstance(entry, dict):
            name, version = _plain_text(entry.get("Name"), 200), _plain_text(entry.get("Version"), 80)
            if name and version:
                found.add((name, version))
    return sorted(found)


@dataclass(frozen=True)
class Sources:
    """The documentation of processing steps and software versions found in a dataset (CORE-M13-03)."""

    provenance: ProvenanceFile | None
    converted_steps: tuple[ProcessingStep, ...]
    converted_problem: str | None
    generated_by: tuple[tuple[str, str], ...]

    @property
    def steps(self) -> list[ProcessingStep]:
        """provenance.yaml first, then the steps of processing_steps.json (fixed order)."""
        own = list(self.provenance.processing_steps or []) if self.provenance else []
        return own + list(self.converted_steps)

    @property
    def no_processing_declared(self) -> bool:
        return self.provenance is not None and self.provenance.processing_steps == []

    @property
    def incomplete_steps(self) -> int:
        return sum(1 for s in self.steps if not (s.step.strip() and s.tool.strip() and s.version.strip()))

    def software(self, generator: str | None = None) -> list[SoftwareEntry]:
        """Software versions, sorted by (name, version, source); ``generator`` is the NeuroGrid version that
        writes a manifest (source "manifest", not counted as documentation)."""
        entries: set[tuple[str, str, str]] = set()
        if generator:
            entries.add(("neurogrid", generator, "manifest"))
        for step in self.steps:
            if step.tool.strip() and step.version.strip():
                entries.add((step.tool.strip(), step.version.strip(), "processing_steps"))
        for item in self.provenance.software if self.provenance else []:
            if item.name.strip() and item.version.strip():
                entries.add((item.name.strip(), item.version.strip(), "provenance"))
        entries.update((name, version, "bids") for name, version in self.generated_by)
        return [
            SoftwareEntry.model_validate({"name": name, "version": version, "source": source})
            for name, version, source in sorted(entries)
        ]

    @property
    def documented_software(self) -> list[SoftwareEntry]:
        return [entry for entry in self.software() if entry.source != "manifest"]

    def source_names(self) -> list[str]:
        names = []
        if self.provenance is not None:
            names.append("provenance")
        if self.converted_steps or self.converted_problem:
            names.append("processing_steps")
        if self.generated_by:
            names.append("bids")
        return names


def load_sources(root: Path, is_bids: bool) -> Sources:
    provenance = load_provenance_file(root)
    steps, problem = load_processing_steps(root)
    return Sources(provenance, tuple(steps), problem, tuple(generated_by(root, is_bids)))


# --- exclusions -----------------------------------------------------------------------------------------


def inside(root: Path, path: Path | None) -> str | None:
    """The path relative to the dataset root (POSIX) if it lies inside it, else None. Operator paths may pass
    through links (the operator chose them, A-66), so the resolved location counts."""
    if path is None:
        return None
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_relative_to(root):
        return None
    relative = resolved.relative_to(root).as_posix()
    return None if relative in ("", ".") else relative


def vault_exclusions(root: Path, project_root: Path, vault_path: str) -> list[str]:
    """The vault access log and its lock file, if the vault ([vault] path, relative to the project root, A-66)
    lies inside the dataset. Recorded in the manifest even before they exist, so that ``verify`` leaves them
    out without reading neurogrid.toml (A-22, A-82)."""
    folder = project_root.joinpath(*PurePosixPath(vault_path).parts)
    try:
        relative = folder.relative_to(root).as_posix()
    except ValueError:
        return []
    prefix = "" if relative in ("", ".") else relative + "/"
    return [f"{prefix}{VAULT_LOG}", f"{prefix}{VAULT_LOCK}"]


def comparison_exclusions(
    root: Path, manifest: Manifest, location: Path | None, work: Path | None = None
) -> Exclusions:
    """What a comparison leaves out: the default manifest .neurogrid/manifest.json, the manifest being read
    (if inside the dataset), the paths the manifest recorded as excluded and the run's transient work folder
    (A-82). Everything else in .neurogrid/ is compared."""
    files = [DEFAULT_MANIFEST.as_posix(), *manifest.excluded]
    own = inside(root, location)
    if own is not None:
        files.append(own)
    work_folder = inside(root, work)
    return Exclusions.of(files, [work_folder] if work_folder else [])


# --- display --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Shown:
    object: str
    file: str
    identity: tuple[str, ...]


def show(path: str, *, plain: bool, kind: str | None = None) -> Shown:
    """How a stored manifest path appears in findings and on the console (A-51, A-68, A-70, critic X14)."""
    pseudo = "rec-" + hashlib.sha256(name_bytes(path, kind)).hexdigest()[:8]
    suffix = classify_suffix(path.rsplit("/", 1)[-1])
    if not _SHOWN_SUFFIX.match(suffix):
        suffix = ""
    identity = (path, pseudo, pseudo + suffix)
    if plain or path in KNOWN_CONTROL_FILES:
        return Shown(path, path, identity)
    return Shown(pseudo, pseudo + suffix, identity)


def is_bids_folder(root: Path) -> bool:
    """As discovery decides it (A-03): a dataset_description.json at the root."""
    return os.path.lexists(root / DESCRIPTION)


# --- the manifest state of a check run ------------------------------------------------------------------


@dataclass(frozen=True)
class ManifestRead:
    """The manifest of a check run, or the problem: "missing", "link" (a link at the default location
    .neurogrid/manifest.json, or a linked .neurogrid, is not followed, A-52) or the ManifestError key."""

    parsed: ParsedManifest | None
    problem: str | None
    location: Path | None


class ProvenanceState:
    """M13 state of one check run, computed lazily and once: the manifest is read on first use; the dataset is
    walked and hashed only when a rule compares it and a usable manifest exists (no hashing otherwise)."""

    def __init__(
        self,
        root: Path,
        *,
        single_file: bool,
        is_bids: bool,
        show_paths: bool,
        manifest_path: Path | None,
        work: Path | None,
    ) -> None:
        self.root = root
        self.single_file = single_file
        self.is_bids = is_bids
        self.plain = is_bids or show_paths
        self.manifest_path = manifest_path
        self.work = work
        self._read: ManifestRead | None = None
        self._compared = False
        self._comparison: Comparison | None = None
        self._sources: Sources | None = None

    def read(self) -> ManifestRead:
        if self._read is None:
            self._read = self._load()
        return self._read

    def _load(self) -> ManifestRead:
        location = self.manifest_path
        if location is None:
            try:  # a linked .neurogrid or manifest.json at the default location is not followed (A-52, A-66)
                location = resolve_within(self.root, DEFAULT_MANIFEST, must_exist=False)
            except UnsafePathError:
                return ManifestRead(None, "link", None)
            if not os.path.lexists(location):
                return ManifestRead(None, "missing", None)
        try:
            parsed = read_manifest(location)
        except ManifestError as exc:
            return ManifestRead(None, exc.message_key, location)
        return ManifestRead(parsed, None, location)

    def comparison(self) -> Comparison | None:
        """The comparison with the manifest; None without a usable manifest or for a single file."""
        if not self._compared:
            self._compared = True
            read = self.read()
            if read.parsed is not None and not self.single_file:
                manifest = read.parsed.manifest
                exclusions = comparison_exclusions(self.root, manifest, read.location, self.work)
                self._comparison = compare(self.root, manifest, exclusions)
        return self._comparison

    def sources(self) -> Sources:
        if self._sources is None:
            self._sources = load_sources(self.root, self.is_bids)
        return self._sources

    def info(self) -> ManifestInfo:
        """results.json ``manifest`` and Dataset.manifest_hash (A-82, REP-01); never triggers a comparison."""
        if self.single_file:
            return ManifestInfo(status=ManifestStatus.NOT_APPLICABLE)
        read = self.read()
        if read.parsed is None:
            missing = read.problem == "missing"
            return ManifestInfo(status=ManifestStatus.MISSING if missing else ManifestStatus.INVALID)
        manifest = read.parsed.manifest
        comparison = self._comparison
        if not read.parsed.hash_ok:
            status = ManifestStatus.HASH_MISMATCH
        elif comparison is None:
            status = ManifestStatus.NOT_VERIFIED
        else:
            status = ManifestStatus.DIFFERS if comparison.deviations else ManifestStatus.MATCHES
        counts: dict[str, int] = {}
        if comparison is not None:
            counts = {
                "changed": comparison.count("changed"),
                "new": comparison.count("new"),
                "missing": comparison.count("missing"),
                "skipped_changed": comparison.count("skipped_changed"),
                "unreadable": comparison.count("unreadable"),
            }
        return ManifestInfo(sha256=manifest.manifest_hash, status=status, files=len(manifest.files), **counts)
