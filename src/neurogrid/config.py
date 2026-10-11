"""Project configuration neurogrid.toml (NG-F18, MET-02, A-13, A-14, A-52, A-53).

Default location: <dataset>/.neurogrid/neurogrid.toml. Validation is strict: unknown keys, values of the
wrong type and non-finite numbers are errors, never silently converted. Paths in the file are relative to
the project root (A-52, A-66): the folder that holds ``.neurogrid`` for a file in such a folder, else the
dataset root if the file lies inside the dataset, else the folder of the file.
"""

from __future__ import annotations

import os
import re
import tomllib
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from neurogrid.kernel import canonical
from neurogrid.kernel.engine import ExceptionEntry
from neurogrid.kernel.errors import ConfigError, InputError, UnsafePathError
from neurogrid.kernel.rules import ParamValue
from neurogrid.kernel.safety import check_relative, decode_text, read_limited, resolve_within

CONFIG_DIR = ".neurogrid"
CONFIG_NAME = "neurogrid.toml"
MAX_CONFIG_BYTES = 1_000_000
BUILTIN_RULEPACK = re.compile(r"^[a-z0-9_]+$")


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class DatasetSection(_Section):
    id: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=40)
    source: str | None = Field(default=None, max_length=200)
    license: str | None = Field(default=None, max_length=80)


class CheckSection(_Section):
    rulepacks: list[str] | None = Field(default=None, min_length=1)
    strict: bool = False
    seed: int = Field(default=20261011, ge=0, le=2**63 - 1)
    as_of: date | None = None


class SamplingSection(_Section):
    mode: Literal["sample", "full"] = "sample"
    segments: int = Field(default=10, ge=1, le=100)
    segment_s: float = Field(default=60.0, gt=0, le=3600)


class RuleOverride(_Section):
    params: dict[str, ParamValue] = Field(default_factory=dict)


class MetadataDefaults(_Section):
    electrode_type: Literal["wet", "dry"] | None = None
    line_frequency_hz: float | None = Field(default=None, gt=0)
    device: str | None = Field(default=None, max_length=120)
    reference: str | None = Field(default=None, max_length=120)


class MetadataSection(_Section):
    defaults: MetadataDefaults = Field(default_factory=MetadataDefaults)
    mixed_sampling_rates_reason: str | None = Field(default=None, max_length=500)


class ConvertSection(_Section):
    pattern: str | None = Field(default=None, max_length=512)


class AnnotationSection(_Section):
    mode: Literal["continuous", "events"] = "events"
    epoch_s: float | None = Field(default=None, gt=0)
    vocabulary: list[str] | None = None


class AISection(_Section):
    labels: str | None = Field(default=None, max_length=120)
    splits: str | None = Field(default=None, max_length=512)


class ConsentSection(_Section):
    split_use: dict[str, str] = Field(default_factory=dict)
    dataset_uses: list[str] = Field(default_factory=list)


class VaultSection(_Section):
    path: str = ".neurogrid/vault"
    role: str | None = Field(default=None, max_length=80)
    purpose: str | None = Field(default=None, max_length=200)
    approval_ref: str | None = Field(default=None, max_length=120)


class Config(_Section):
    dataset: DatasetSection = Field(default_factory=DatasetSection)
    check: CheckSection = Field(default_factory=CheckSection)
    sampling: SamplingSection = Field(default_factory=SamplingSection)
    rules: dict[str, RuleOverride] = Field(default_factory=dict)
    exceptions: list[ExceptionEntry] = Field(default_factory=list)
    metadata: MetadataSection = Field(default_factory=MetadataSection)
    convert: ConvertSection = Field(default_factory=ConvertSection)
    annotation: AnnotationSection = Field(default_factory=AnnotationSection)
    ai: AISection = Field(default_factory=AISection)
    consent: ConsentSection = Field(default_factory=ConsentSection)
    vault: VaultSection = Field(default_factory=VaultSection)

    def canonical_sha256(self) -> str:
        """Hash over the parsed, canonical content – independent of formatting and line endings."""
        return canonical.sha256_of(self.model_dump(mode="json"))

    def overrides(self) -> dict[str, dict[str, ParamValue]]:
        return {rule_id: dict(entry.params) for rule_id, entry in self.rules.items()}


class LoadedConfig(NamedTuple):
    config: Config
    path: Path | None
    project_root: Path


def _check_paths(cfg: Config) -> None:
    """Every path in the file must be a plain relative path (A-52); resolution happens where it is used."""
    fields: list[tuple[str, str | None]] = [("ai.splits", cfg.ai.splits), ("vault.path", cfg.vault.path)]
    fields += [
        (f"check.rulepacks.{index}", ref)
        for index, ref in enumerate(cfg.check.rulepacks or [])
        if not BUILTIN_RULEPACK.match(ref)
    ]
    for name, value in fields:
        if value is None:
            continue
        try:
            check_relative(value)
        except UnsafePathError:
            raise ConfigError("config.unsafe_path", field=name) from None


def parse(text: str) -> Config:
    if len(text.encode("utf-8", "surrogatepass")) > MAX_CONFIG_BYTES:
        raise ConfigError("config.too_large")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError("config.syntax", problem=str(exc).split("(")[0].strip()) from None
    except RecursionError:
        raise ConfigError("config.too_deep") from None
    except ValueError:  # e.g. an integer with more digits than Python converts
        raise ConfigError("config.syntax", problem="value") from None
    try:
        cfg = Config.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"])
        raise ConfigError("config.invalid", field=location, problem=first["type"]) from None
    _check_paths(cfg)
    return cfg


def parse_bytes(data: bytes) -> Config:
    """UTF-8 with or without byte order mark (PowerShell 5.1 writes one); other encodings are refused."""
    return parse(decode_text(data, ConfigError, "config.encoding"))


def _default_location(dataset_root: Path) -> Path | None:
    if not os.path.lexists(dataset_root / CONFIG_DIR):
        return None
    # Links are not followed (A-52): a junction .neurogrid must not pull in a foreign configuration.
    path = resolve_within(dataset_root, PurePosixPath(CONFIG_DIR, CONFIG_NAME), must_exist=False)
    return path if path.is_file() else None


def load(config_path: Path | None, dataset_root: Path) -> LoadedConfig:
    """Explicit --config, else the default location inside the dataset, else defaults."""
    root = dataset_root.resolve()
    path = config_path if config_path is not None else _default_location(root)
    if path is None:
        return LoadedConfig(Config(), None, root)
    if not path.is_file():
        raise ConfigError("config.not_found")
    try:
        data = read_limited(path, MAX_CONFIG_BYTES)
    except InputError:
        raise ConfigError("config.too_large") from None
    resolved = path.resolve()
    if os.path.normcase(resolved.parent.name) == os.path.normcase(CONFIG_DIR):
        project_root = resolved.parent.parent
    elif resolved.is_relative_to(root):
        project_root = root
    else:
        project_root = resolved.parent
    return LoadedConfig(parse_bytes(data), path, project_root)
