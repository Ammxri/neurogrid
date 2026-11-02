"""Strict reading of the registers of NeuroVault (NV-F04, NV-F05, NV-F06; A-93, A-94, A-95): the role register
``roles.yaml`` (model.roles), the retention periods ``retention.yaml`` (model.retention) and the risk register
``risks.yaml`` (model.risks), each in the vault folder next to consents.yaml.

One parse helper for the three files, as model.consent reads consents.yaml (C2, A-51, A-53): the byte limit
of the file is checked before the YAML is read; UTF-8 with or without BOM; the strict YAML loader of the
kernel (no aliases, no duplicate keys, bounded depth); ``format_version: 1`` and the list key of the file
required; the strict model (unknown keys refused). Every problem is a ConfigError (exit 2) that names the
entry index and the field name, never the text of a value (an unknown key, which may be any text, is '?'):
errors.<file>.too_large {limit}, .encoding, .invalid {field, problem} and the kernel's errors.yaml.*. Dates
are a YAML date or the same date as the text 'YYYY-MM-DD' (the A-83 rule of model.consent); timestamps and
other text are refused.

Only kernel and model imports (ARC-01): the vault, the checks and the CLI build on these models.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Protocol, TypeVar

from pydantic import BaseModel, BeforeValidator, ValidationError

from neurogrid.kernel.errors import ConfigError
from neurogrid.kernel.safety import decode_text, load_yaml
from neurogrid.model.consent import date_from_text

FORMAT_VERSION = 1
FILE_KEY = "format_version"
# Problems of the validators of the three registers (the ValueError text, a fixed key shown in
# errors.<file>.invalid; pydantic's own error types are shown as they are, e.g. string_too_long).
INVALID_TEXT = "invalid_text"  # empty, only white space or not printable
NOT_MAPPING = "not_mapping"
MISSING = "missing"
M = TypeVar("M", bound=BaseModel)


def text_valid(text: str, max_chars: int) -> bool:
    """1..max_chars characters, not only white space, and printable: no control or format character, no line
    or paragraph separator, no unassigned or private-use code point (the rule of
    model.consent.ethics_ref_valid for every free text of a register)."""
    return 0 < len(text) <= max_chars and bool(text.strip()) and text.isprintable()


def _date_text(value: Any) -> Any:
    """A YAML date, or the same date as the text 'YYYY-MM-DD' (quoted, or as a YAML 1.2 editor reads an
    unquoted one; A-83). Other text stays as it is and fails the strict date check, as do timestamps."""
    if isinstance(value, str):
        return date_from_text(value) or value
    return value


def _not_bool(value: Any) -> Any:
    """YAML ``true`` is no format version: a bool fails the literal check instead of passing as 1."""
    return str(value) if isinstance(value, bool) else value


def _as_tuple(value: Any) -> Any:
    """YAML gives a list; a tuple is the models' own form of a list inside an entry."""
    return tuple(value) if isinstance(value, list) else value


RegisterDate = Annotated[dt.date, BeforeValidator(_date_text)]
FormatVersion = Annotated[Literal[1], BeforeValidator(_not_bool)]
TupleFromList = BeforeValidator(_as_tuple)


class Register(Protocol):
    """What a parsed register offers the vault and the checks: its entries in file order and the canonical
    hash of its content (results.json config.<file>_sha256)."""

    @property
    def entries(self) -> Sequence[BaseModel]: ...

    def canonical_sha256(self) -> str: ...


@dataclass(frozen=True)
class RegisterSpec:
    """What the parse helper knows of one register file: its name in the error keys (errors.<name>.*), its
    list key, its byte limit, the field names an error may show (FILE_KEY and the list key included) and the
    problems of its validators."""

    name: str
    list_key: str
    max_bytes: int
    keys: frozenset[str]
    problems: frozenset[str]

    @property
    def file(self) -> str:
        return f"{self.name}.yaml"


def invalid(spec: RegisterSpec, field: str, problem: str) -> ConfigError:
    """errors.<file>.invalid naming a field (index and field names only) and a fixed problem key."""
    return ConfigError(f"{spec.name}.invalid", field=field, problem=problem)


def location(parts: Sequence[int | str], keys: Collection[str]) -> str:
    """A field location that names indices and field names only, never value text (C2, A-51): any other key
    (an unknown key, which may be any text) is '?'."""
    shown = []
    for part in parts:
        text = str(part)
        shown.append(text if isinstance(part, int) or text in keys else "?")
    return ".".join(shown)


def _yaml(text: str, spec: RegisterSpec) -> Any:
    """The strict YAML loader of the kernel (no aliases, no duplicate keys, bounded depth, A-53); the name of
    a duplicate key is shown only if it is a field name of the format."""
    try:
        return load_yaml(text, max_bytes=spec.max_bytes)
    except ConfigError as exc:
        if exc.message_key == "yaml.duplicate_key":
            name = str(exc.params.get("name", ""))
            raise ConfigError(
                "yaml.duplicate_key",
                name=name if name in spec.keys else "?",
                line=exc.params.get("line", "?"),
            ) from None
        if exc.message_key == "yaml.too_large":
            raise ConfigError(f"{spec.name}.too_large", limit=spec.max_bytes) from None
        raise


def parse_register(data: bytes, spec: RegisterSpec, model: type[M]) -> M:
    """Parse register bytes: at most spec.max_bytes, UTF-8 with or without BOM, the strict YAML loader, a
    mapping with ``format_version`` and the list key, then the strict model. The checks across entries (unique
    names, the retention rules) are the caller's. Raises ConfigError errors.<file>.too_large {limit},
    .encoding, .invalid {field, problem} and the kernel's errors.yaml.*."""
    if len(data) > spec.max_bytes:
        raise ConfigError(f"{spec.name}.too_large", limit=spec.max_bytes)
    raw = _yaml(decode_text(data, ConfigError, f"{spec.name}.encoding"), spec)
    if not isinstance(raw, dict):
        raise invalid(spec, spec.file, NOT_MAPPING)
    for key in (FILE_KEY, spec.list_key):
        if key not in raw:
            raise invalid(spec, key, MISSING)
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        problem = str(first["type"])
        error = first.get("ctx", {}).get("error")
        if problem == "value_error" and str(error) in spec.problems:
            problem = str(error)
        raise invalid(spec, location(tuple(first["loc"]), spec.keys), problem) from None


def first_duplicate(values: Sequence[object]) -> int | None:
    """The index of the first value that repeats an earlier one, or None."""
    seen: set[object] = set()
    for index, value in enumerate(values):
        if value in seen:
            return index
        seen.add(value)
    return None
