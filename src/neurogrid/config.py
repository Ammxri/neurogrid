"""Project configuration neurogrid.toml (NG-F18, MET-02, A-13, A-14, A-52, A-53).

Default location: <dataset>/.neurogrid/neurogrid.toml. Validation is strict: unknown keys, values of the
wrong type and non-finite numbers are errors, never silently converted. Paths in the file are relative to
the project root (A-52, A-66): the folder that holds ``.neurogrid`` for a file in such a folder, else the
dataset root if the file lies inside the dataset, else the folder of the file.
"""

from __future__ import annotations

import importlib
import math
import os
import re
import tomllib
from collections.abc import Iterator
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from neurogrid.kernel import canonical
from neurogrid.kernel.engine import ExceptionEntry
from neurogrid.kernel.errors import ConfigError, InputError, UnsafePathError
from neurogrid.kernel.rules import ParamValue
from neurogrid.kernel.safety import check_relative, decode_text, read_limited, resolve_within

CONFIG_DIR = ".neurogrid"
CONFIG_NAME = "neurogrid.toml"
MAX_CONFIG_BYTES = 1_000_000
BUILTIN_RULEPACK = re.compile(r"^[a-z0-9_]+$")
LABEL = r"^[A-Za-z0-9]+$"  # BIDS labels are alphanumeric (A-05)
MAPPING_GROUPS = frozenset({"subject", "session", "task", "run"})
_RE_PARSER: Any = importlib.import_module("re._parser")  # private, but stable in Python 3.11-3.13 (A-42)
_RE_COMPILER: Any = importlib.import_module("re._compiler")
_REPEATS = frozenset({"MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"})
# A-53: the worst case of a mapping expression is estimated for a name of NAME_LENGTH characters; above
# MAX_SPLITS ways to divide such a name the expression is refused (Python's matcher tries them one by one,
# some 10-40 million a second). Four parts that can match the same characters (``.+_.+_.+_.+\.edf``) stay
# allowed, about 5 s on a hostile name of 255 characters; five do not.
NAME_LENGTH = 255
MAX_SPLITS = 2 * 10**8
_ATOMS = frozenset({"LITERAL", "NOT_LITERAL", "ANY", "IN"})
_END = ""  # stands for the end of the name in the set of characters that may follow a part
# characters outside ASCII that every expression is probed with (letters, digits, spaces, case folding)
_PROBES = "éÉß١²  　中Kſİı\U0001f600"


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


class QualitySection(_Section):
    """Measurement settings of the signal quality metrics (A-18, A-60, A-79)."""

    flat_tolerance_uv: float = Field(default=0.1, gt=0, le=1000)  # floating-point formats (EEGLAB, FIF)
    plateau_samples: int = Field(default=10, ge=2, le=100_000)  # clipping without a known range
    min_seconds: float = Field(default=60.0, gt=0, le=86_400)  # data needed for M06/M09
    min_channels: int = Field(default=16, ge=2, le=4096)  # EEG channels needed for M06/M09


class RuleOverride(_Section):
    params: dict[str, ParamValue] = Field(default_factory=dict)


class MetadataDefaults(_Section):
    """Documented values for all recordings; they take precedence over sidecars and headers (A-04)."""

    electrode_type: Literal["wet", "dry"] | None = None
    line_frequency_hz: float | None = Field(default=None, gt=0)
    device: str | None = Field(default=None, max_length=120)
    reference: str | None = Field(default=None, max_length=120)
    software_filters: str | None = Field(default=None, max_length=500)


class MetadataSection(_Section):
    defaults: MetadataDefaults = Field(default_factory=MetadataDefaults)
    mixed_sampling_rates_reason: str | None = Field(default=None, max_length=500)
    # channel label -> standard position name (10-20/10-10/10-05) for labels that differ from it (M04)
    channel_map: dict[str, str] = Field(default_factory=dict, max_length=4096)


class MappedFile(_Section):
    """One row of the mapping table for raw folders (A-05)."""

    path: str = Field(max_length=1024)
    subject: str = Field(pattern=LABEL, max_length=64)
    session: str | None = Field(default=None, pattern=LABEL, max_length=64)
    task: str = Field(pattern=LABEL, max_length=64)
    run: str | None = Field(default=None, pattern=r"^[0-9]+$", max_length=8)


def _subpatterns(value: Any) -> Iterator[Any]:
    """The parsed subpatterns inside the argument of one opcode of ``re._parser`` (any nesting of tuples
    and lists, which differs between opcodes and Python versions)."""
    if isinstance(value, _RE_PARSER.SubPattern):
        yield value
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _subpatterns(item)


def _name(op: Any) -> str:
    return str(getattr(op, "name", op))


def _may_backtrack(items: Any, repeated: bool) -> bool:
    """True if a parsed expression contains a back-reference, or a part that is repeated more than once
    (``+``, ``*``, ``{2,}``) and holds another repetition or alternatives; ``(?:_x+)?`` stays allowed."""
    for op, argument in items:
        name = _name(op)
        if name.startswith("GROUPREF"):
            return True
        if repeated and (name in _REPEATS or name == "BRANCH"):
            return True
        inner = repeated or (name in _REPEATS and argument[1] > 1)
        if any(_may_backtrack(sub, inner) for sub in _subpatterns(argument)):
            return True
    return False


class _Chars(NamedTuple):
    """Characters a part of an expression can start with, or that may follow it: members of the probe
    alphabet (``_END`` for the end of the name), and whether characters beyond the alphabet belong to it."""

    members: frozenset[str]
    beyond: bool

    def union(self, other: _Chars) -> _Chars:
        return _Chars(self.members | other.members, self.beyond or other.beyond)

    def overlaps(self, other: _Chars) -> bool:
        # Two sets that both reach beyond the alphabet count as overlapping. Otherwise one of them lies
        # inside the alphabet, so a shared character would be a shared member.
        return bool(self.members & other.members) or (self.beyond and other.beyond)


_NOTHING = _Chars(frozenset(), False)


def _codes(items: Any) -> Iterator[int]:
    """Every character an expression names: literals and the ends of ranges (all of a short range)."""
    for op, argument in items:
        name = _name(op)
        if name in ("LITERAL", "NOT_LITERAL"):
            yield argument
        elif name == "IN":
            for item_op, item in argument:
                if _name(item_op) == "LITERAL":
                    yield item
                elif _name(item_op) == "RANGE":
                    low, high = item
                    yield from range(low, high + 1) if high - low < 256 else (low, high)
        else:
            for sub in _subpatterns(argument):
                yield from _codes(sub)


class _Splits:
    """A-53: the choices of a parsed expression that the next character does not decide.

    A repetition that may stop or go on, an optional part and alternatives are decided by the next character
    when the characters they can start with differ from those that may follow (``[a-z]+_``, ``edf|bdf``).
    Undecided choices let the matcher try many ways to divide the same name: ``lengths`` counts those that
    choose a length (``\\w+_``, ``.*``), ``ways`` multiplies the others (``a?``, ``a|ab``). Without nested
    repetitions (refused before), a name of n characters can be divided in at most
    ``comb(n + lengths, lengths) * ways`` ways.
    """

    def __init__(self, parsed: Any) -> None:
        alphabet = {chr(code) for code in range(128)} | set(_PROBES)
        for code in set(_codes(parsed)):
            for near in (code - 1, code, code + 1):
                if 0 <= near <= 0x10FFFF:
                    char = chr(near)
                    alphabet.update(c for c in (char, char.lower(), char.upper()) if len(c) == 1)
        self.alphabet = frozenset(alphabet)
        self._text = "".join(sorted(alphabet))
        self.everything = _Chars(self.alphabet | {_END}, True)
        self.lengths = 0
        self.ways = 1
        self._atoms: dict[tuple[str, str, int], _Chars] = {}
        self._walk(parsed, _Chars(frozenset({_END}), False), parsed.state.flags)

    def estimate(self, length: int) -> int:
        return math.comb(length + self.lengths, self.lengths) * self.ways

    def _atom(self, op: Any, argument: Any, flags: int) -> _Chars:
        """The characters one character class matches, found by compiling it alone with its flags."""
        key = (_name(op), repr(argument), flags)
        if key not in self._atoms:
            state = _RE_PARSER.State()
            state.flags = flags
            matcher = _RE_COMPILER.compile(_RE_PARSER.SubPattern(state, [(op, argument)]), flags)
            members = frozenset(matcher.findall(self._text))  # the class matches exactly one character
            inside = key[0] == "LITERAL" or (
                key[0] == "IN"
                and all(
                    _name(item_op) == "LITERAL"
                    or (_name(item_op) == "RANGE" and (item[1] < 128 or item[1] - item[0] < 256))
                    for item_op, item in argument
                )
            )
            if flags & re.IGNORECASE and any(char.lower() != char.upper() for char in members):
                inside = False  # case folding reaches characters such as the Kelvin sign
            self._atoms[key] = _Chars(members, not inside)
        return self._atoms[key]

    def _first(self, items: Any, flags: int) -> tuple[_Chars, bool]:
        """The characters a sequence can start with, and whether it can match an empty text."""
        chars = _NOTHING
        for op, argument in items:
            part, empty = self._part_first(op, argument, flags)
            chars = chars.union(part)
            if not empty:
                return chars, False
        return chars, True

    def _part_first(self, op: Any, argument: Any, flags: int) -> tuple[_Chars, bool]:
        name = _name(op)
        if name in _ATOMS:
            return self._atom(op, argument, flags), False
        if name == "SUBPATTERN":
            _group, add, remove, items = argument
            return self._first(items, (flags | add) & ~remove)
        if name == "ATOMIC_GROUP":
            return self._first(argument, flags)
        if name == "BRANCH":
            chars, empty = _NOTHING, False
            for items in argument[1]:
                part, part_empty = self._first(items, flags)
                chars, empty = chars.union(part), empty or part_empty
            return chars, empty
        if name in _REPEATS:
            low, _high, items = argument
            chars, empty = self._first(items, flags)
            return chars, empty or low == 0
        if name in ("AT", "ASSERT", "ASSERT_NOT"):
            return _NOTHING, True  # zero width
        return self.everything, True  # an opcode this check does not know

    def _walk(self, items: Any, follow: _Chars, flags: int) -> None:
        for index, (op, argument) in enumerate(items):
            rest, empty = self._first(items[index + 1 :], flags)
            self._part(op, argument, rest.union(follow) if empty else rest, flags)

    def _part(self, op: Any, argument: Any, follow: _Chars, flags: int) -> None:
        name = _name(op)
        if name in _ATOMS or name == "AT":
            return
        if name == "SUBPATTERN":
            _group, add, remove, items = argument
            self._walk(items, follow, (flags | add) & ~remove)
        elif name == "ATOMIC_GROUP":
            self._walk(argument, follow, flags)
        elif name == "BRANCH":
            starts = []
            for items in argument[1]:
                chars, empty = self._first(items, flags)
                starts.append(chars.union(follow) if empty else chars)
            if any(a.overlaps(b) for index, a in enumerate(starts) for b in starts[index + 1 :]):
                self.ways *= len(starts)
            for items in argument[1]:
                self._walk(items, follow, flags)
        elif name in _REPEATS:
            low, high, items = argument
            body, empty = self._first(items, flags)
            if high != low and (empty or body.overlaps(follow)):
                if high - low == 1:
                    self.ways *= 2
                else:
                    self.lengths += 1
            self._walk(items, body.union(follow) if high > 1 else follow, flags)
        else:  # a look-around (tried wherever it stands) or an opcode this check does not know
            self.lengths += 1
            for sub in _subpatterns(argument):
                self._walk(sub, self.everything, flags)


def backtracking_risk(pattern: str) -> bool:
    """A-53: a mapping expression comes from a file inside the dataset, and Python's matcher backtracks.

    Refused when the configuration is read: back-references, nested repetitions (``(a+)+``), alternatives
    inside a repetition (``(a|aa)+``), and expressions that may divide a name of NAME_LENGTH characters in
    more than MAX_SPLITS ways (many neighbouring parts that can match the same characters, e.g. ``a?a?a?…``,
    ``a*a*a*…`` or six ``.*``). Uses the parser and compiler of the standard library (``re._parser``,
    ``re._compiler``, Python 3.11-3.13)."""
    try:
        parsed = _RE_PARSER.parse(pattern)
        if _may_backtrack(parsed, repeated=False):
            return True
        return _Splits(parsed).estimate(NAME_LENGTH) > MAX_SPLITS
    except RecursionError:
        return True  # too deeply nested to inspect


class ConvertSection(_Section):
    """Mapping of raw files to subject/session/task/run (A-05): a regular expression with named groups over
    the relative path (or the file name), or a table; table rows win over the expression."""

    pattern: str | None = Field(default=None, max_length=512)
    files: list[MappedFile] = Field(default_factory=list, max_length=100_000)

    @field_validator("pattern")
    @classmethod
    def _pattern_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            compiled = re.compile(value)
        except re.error:
            raise ValueError("not a valid regular expression") from None
        groups = set(compiled.groupindex)
        if not groups <= MAPPING_GROUPS or not {"subject", "task"} <= groups:
            raise ValueError("named groups must include subject and task, and only subject/session/task/run")
        if backtracking_risk(value):
            # not a ValueError: pydantic passes this error through, so it keeps its own message (A-53)
            raise ConfigError("config.unsafe_pattern", field="convert.pattern")
        return value


class AnnotationSection(_Section):
    mode: Literal["continuous", "events"] = "events"
    epoch_s: float | None = Field(default=None, gt=0)
    vocabulary: list[str] | None = None


# [ai] labels names where the M11 class labels come from (A-81): a column of the BIDS events.tsv files (unit:
# events) or of participants.tsv (unit: subjects). The label source "annotations" (M10 reader) extends this
# grammar and AI_LABEL_SOURCES together with its reader in checks/ai_dataset.py; until then it is refused.
AI_LABEL_SOURCES = ("events", "participants")
AI_LABELS = re.compile(r"^(?P<source>events|participants):(?P<column>[A-Za-z0-9_.\-]{1,64})$")


class AISection(_Section):
    """M11/M12 (A-21, A-81): the label source and the split control file (relative to the project root)."""

    labels: str | None = Field(default=None, max_length=120)
    splits: str | None = Field(default=None, max_length=512)

    @field_validator("labels")
    @classmethod
    def _labels_valid(cls, value: str | None) -> str | None:
        if value is not None and not AI_LABELS.fullmatch(value):
            raise ValueError("expected 'events:<column>' or 'participants:<column>'")
        return value


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
    quality: QualitySection = Field(default_factory=QualitySection)
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
    fields += [(f"convert.files.{index}.path", row.path) for index, row in enumerate(cfg.convert.files)]
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


def project_root_for(path: Path, dataset_root: Path) -> Path:
    """A-66 for a NeuroGrid file (neurogrid.toml, evidence.yaml, A-83): the folder above ``.neurogrid`` for a
    file in such a folder, else the dataset root for a file inside the dataset, else the file's folder."""
    resolved = path.resolve()
    root = dataset_root.resolve()
    if os.path.normcase(resolved.parent.name) == os.path.normcase(CONFIG_DIR):
        return resolved.parent.parent
    if resolved.is_relative_to(root):
        return root
    return resolved.parent


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
    return LoadedConfig(parse_bytes(data), path, project_root_for(path, root))
