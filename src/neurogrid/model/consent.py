"""Consent records of NeuroVault: ``<vault>/consents.yaml`` (DM-08, NV-F01, NV-F02, A-30, A-91). The schema
is generated from ConsentFile (tools/gen_schemas.py: schemas/consents.schema.json).

PRD → English (D-03): subject, version, datum→date, erlaubte_nutzungen→permitted_uses {training,
validierung→validation, veroeffentlichung→publication, weitergabe→sharing, kommerziell→commercial},
widerruf→withdrawn, ethikvotum_ref→ethics_approval_ref.

Format (format_version 1)::

    format_version: 1
    consents:
      - subject: sub-01                        # pseudonymous: sub-<label>, label [A-Za-z0-9]{1,64}
        version: 2                             # integer 1..1000000; a higher version replaces a lower one
        date: 2026-03-01                       # a YAML date or the text "2026-03-01"
        permitted_uses: [training, validation]
        withdrawn: false                       # true: full withdrawal from the date on, then no uses
        ethics_approval_ref: "EC-2026-17"      # optional, 1..120 printable characters

The file is a control file (C2): invalid content ends a run with exit 2 and names the place (entry index and
field name), never the text of a value (A-51). ``vault consent add`` rewrites it in a canonical form
(dump_consents); comments added by hand are not kept. The effective consent of a subject at the reference
date is the highest version dated on or before it (A-30); a partial withdrawal is a new version with fewer
uses, a full withdrawal a new version with ``withdrawn: true``, a renewed consent a later version with uses.

Only kernel imports (ARC-01): the vault, the checks and the CLI build on this model, never the reverse.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from neurogrid.kernel import canonical
from neurogrid.kernel.errors import ConfigError
from neurogrid.kernel.safety import decode_text, load_yaml

FORMAT_VERSION = 1
MAX_ENTRIES = 20_000
MAX_FILE_BYTES = 4_000_000  # consents.yaml (A-53); PyYAML reads this in a few seconds
MAX_VERSION = 1_000_000
MAX_ETHICS_REF_CHARS = 120
MAX_LABEL_CHARS = 64
SUBJECT_PATTERN = rf"^sub-[A-Za-z0-9]{{1,{MAX_LABEL_CHARS}}}$"  # pseudo_id as stored (A-05 LABEL)
SUBJECT_INPUT_PATTERN = rf"^(sub-)?[A-Za-z0-9]{{1,{MAX_LABEL_CHARS}}}$"  # as given: with or without 'sub-'
_SUBJECT_INPUT = re.compile(rf"(?:sub-)?([A-Za-z0-9]{{1,{MAX_LABEL_CHARS}}})", re.ASCII)
# A date written as text: the JSON schema's format "date"; date.fromisoformat alone also takes '20260301'
_DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
_VERSION_TEXT = re.compile(r"[0-9]{1,7}", re.ASCII)
HEADER = (
    "# NeuroGrid consent records of this dataset (pseudonymous subject IDs only).\n"
    "# Format: docs/<lang>/vault.md. 'neurogrid vault consent add' rewrites this file in a canonical form;\n"
    "# comments added by hand are not kept.\n"
)
# Field names of the file: the only key texts an error may show (C2, A-51).
FILE_KEYS = ("format_version", "consents")
ENTRY_KEYS = ("subject", "version", "date", "permitted_uses", "withdrawn", "ethics_approval_ref")
# Problems of the validators below (the ValueError text, a fixed key shown in errors.consents.invalid).
DUPLICATE_USE = "duplicate_use"
USES_REQUIRED = "uses_required"
WITHDRAWN_WITH_USES = "withdrawn_with_uses"
ETHICS_REF_TEXT = "ethics_ref_text"
DUPLICATE_VERSION = "duplicate_version"
DATE_ORDER = "date_order"
_PROBLEMS = (DUPLICATE_USE, USES_REQUIRED, WITHDRAWN_WITH_USES, ETHICS_REF_TEXT)


class ConsentUse(StrEnum):
    """The uses a consent may permit (KONZEPT 2.1); this order is the order of every list of uses."""

    TRAINING = "training"
    VALIDATION = "validation"
    PUBLICATION = "publication"
    SHARING = "sharing"
    COMMERCIAL = "commercial"


CONSENT_USES: tuple[str, ...] = tuple(use.value for use in ConsentUse)
_USE_ORDER = {use: index for index, use in enumerate(ConsentUse)}


def ordered_uses(uses: Iterable[ConsentUse | str]) -> tuple[ConsentUse, ...]:
    """The distinct uses in ConsentUse order (ValueError for an unknown one)."""
    return tuple(sorted({ConsentUse(use) for use in uses}, key=_USE_ORDER.__getitem__))


def subject_id(text: str) -> str | None:
    """The stored pseudo_id ``sub-<label>`` of a subject given with or without 'sub-'; None for anything
    else (non-ASCII, spaces, separators, '..', more than 64 characters). The label keeps its case."""
    match = _SUBJECT_INPUT.fullmatch(text)
    return f"sub-{match.group(1)}" if match else None


def date_from_text(text: str) -> dt.date | None:
    """A date written as 'YYYY-MM-DD' with ASCII digits and a real day; None otherwise (no '20260301', no
    time, no 2026-02-30)."""
    if not _DATE_TEXT.fullmatch(text):
        return None
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def version_from_text(text: str) -> int | None:
    """A version written as decimal digits, 1..MAX_VERSION; None otherwise."""
    if not _VERSION_TEXT.fullmatch(text):
        return None
    value = int(text)
    return value if 1 <= value <= MAX_VERSION else None


def ethics_ref_valid(text: str) -> bool:
    """1..120 characters, not only white space, and printable: no control or format character, no line or
    paragraph separator, no unassigned or private-use code point. The canonical file writes the reference as
    a quoted YAML string, and only printable text reads back exactly the same (A-53)."""
    return 0 < len(text) <= MAX_ETHICS_REF_CHARS and bool(text.strip()) and text.isprintable()


Use = Annotated[ConsentUse, Field(strict=False)]  # read from its text in YAML, TSV and TOML
# ConsentScope._uses_or_withdrawal in the JSON schema: a full withdrawal permits no use, otherwise one is
# needed. The schema accepts what the reader accepts, apart from what only the reader decides across records
# (duplicate versions, the date order) and that an ethics reference is printable text.
_USES_OR_WITHDRAWAL: dict[str, Any] = {
    "if": {"properties": {"withdrawn": {"const": True}}, "required": ["withdrawn"]},
    "then": {"properties": {"permitted_uses": {"maxItems": 0}}},
    "else": {"required": ["permitted_uses"], "properties": {"permitted_uses": {"minItems": 1}}},
}


class ConsentScope(BaseModel):
    """One consent record of a subject (DM-08). ``permitted_uses`` is kept in ConsentUse order, so equal
    records are equal objects however the file lists the uses."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, json_schema_extra=_USES_OR_WITHDRAWAL)

    # the schema describes the file, where the label may come without 'sub-' (stored with it)
    subject: str = Field(pattern=SUBJECT_PATTERN, json_schema_extra={"pattern": SUBJECT_INPUT_PATTERN})
    version: int = Field(ge=1, le=MAX_VERSION)
    date: dt.date
    permitted_uses: tuple[Use, ...] = Field(
        default=(), max_length=len(ConsentUse), json_schema_extra={"uniqueItems": True}
    )
    withdrawn: bool = False
    ethics_approval_ref: str | None = Field(
        default=None, min_length=1, max_length=MAX_ETHICS_REF_CHARS, json_schema_extra={"pattern": r"\S"}
    )

    @field_validator("subject", mode="before")
    @classmethod
    def _subject(cls, value: Any) -> Any:
        """'01' and 'sub-01' name the same subject; an invalid text stays as it is and fails the pattern."""
        if isinstance(value, str):
            return subject_id(value) or value
        return value

    @field_validator("date", mode="before")
    @classmethod
    def _date_text(cls, value: Any) -> Any:
        """A YAML date, or the same date as the text 'YYYY-MM-DD' (quoted, or as a YAML 1.2 editor reads an
        unquoted one; the EvidenceItem rule, A-83). Other text and timestamps are refused."""
        if isinstance(value, str):
            return date_from_text(value) or value
        return value

    @field_validator("permitted_uses", mode="before")
    @classmethod
    def _uses_list(cls, value: Any) -> Any:
        """YAML and TSV give a list; a tuple is the model's own form."""
        return tuple(value) if isinstance(value, list) else value

    @field_validator("permitted_uses")
    @classmethod
    def _uses(cls, value: tuple[ConsentUse, ...]) -> tuple[ConsentUse, ...]:
        if len(set(value)) != len(value):
            raise ValueError(DUPLICATE_USE)
        return ordered_uses(value)

    @field_validator("ethics_approval_ref")
    @classmethod
    def _ethics_ref(cls, value: str | None) -> str | None:
        if value is not None and not ethics_ref_valid(value):
            raise ValueError(ETHICS_REF_TEXT)
        return value

    @model_validator(mode="after")
    def _uses_or_withdrawal(self) -> ConsentScope:
        if self.withdrawn and self.permitted_uses:
            raise ValueError(WITHDRAWN_WITH_USES)  # a full withdrawal permits nothing (A-30)
        if not self.withdrawn and not self.permitted_uses:
            raise ValueError(USES_REQUIRED)
        return self


def _not_bool(value: Any) -> Any:
    """YAML ``true`` is no format version: a bool fails the literal check instead of passing as 1."""
    return str(value) if isinstance(value, bool) else value


class ConsentFile(BaseModel):
    """The whole consents.yaml. ``format_version`` and ``consents`` are required in a file
    (parse_consents, and the schema); the defaults only serve NeuroGrid's own construction."""

    model_config = ConfigDict(
        strict=True, extra="forbid", json_schema_extra={"required": ["format_version", "consents"]}
    )

    format_version: Literal[1] = 1
    consents: list[ConsentScope] = Field(default_factory=list, max_length=MAX_ENTRIES)

    @field_validator("format_version", mode="before")
    @classmethod
    def _format_version(cls, value: Any) -> Any:
        return _not_bool(value)

    def canonical_sha256(self) -> str:
        """Hash over the parsed content (results.json config.consents_sha256): the same for every spelling of
        the same records (order of entries and uses, quoting, comments, line ends)."""
        entries = sorted(self.consents, key=lambda entry: (entry.subject, entry.version))
        return canonical.sha256_of(
            {"format_version": self.format_version, "consents": [e.model_dump(mode="json") for e in entries]}
        )

    def by_subject(self) -> dict[str, tuple[ConsentScope, ...]]:
        """pseudo_id -> its records in version order."""
        grouped: dict[str, list[ConsentScope]] = {}
        for entry in self.consents:
            grouped.setdefault(entry.subject, []).append(entry)
        return {
            subject: tuple(sorted(entries, key=lambda entry: entry.version))
            for subject, entries in sorted(grouped.items())
        }


def consistency_problem(entries: Sequence[ConsentScope]) -> tuple[int, str, str] | None:
    """The first record that contradicts an earlier one, as (index, field, problem): the same (subject,
    version) twice (``duplicate_version`` at the later record), or a version dated before a lower version of
    the same subject (``date_order`` at the higher version; dates do not decrease with the version)."""
    seen: dict[tuple[str, int], int] = {}
    for index, entry in enumerate(entries):
        key = (entry.subject, entry.version)
        if key in seen:
            return index, "version", DUPLICATE_VERSION
        seen[key] = index
    by_subject: dict[str, list[tuple[int, ConsentScope]]] = {}
    for index, entry in enumerate(entries):
        by_subject.setdefault(entry.subject, []).append((index, entry))
    candidates = []
    for items in by_subject.values():
        latest: dt.date | None = None
        for index, entry in sorted(items, key=lambda item: item[1].version):
            if latest is not None and entry.date < latest:
                candidates.append(index)
                break
            latest = entry.date
    return (min(candidates), "date", DATE_ORDER) if candidates else None


# --- reading -----------------------------------------------------------------------------------------------


def _location(parts: Sequence[int | str]) -> str:
    """A field location that names indices and field names only, never value text (C2, A-51): any other
    key (an unknown key, which may be any text) is '?'."""
    shown = []
    for part in parts:
        text = str(part)
        known = isinstance(part, int) or text in FILE_KEYS or text in ENTRY_KEYS
        shown.append(text if known else "?")
    return ".".join(shown)


def _yaml(text: str) -> Any:
    """The strict YAML loader of the kernel (no aliases, no duplicate keys, bounded depth, A-53); the name of
    a duplicate key is shown only if it is a field name of the format."""
    try:
        return load_yaml(text, max_bytes=MAX_FILE_BYTES)
    except ConfigError as exc:
        if exc.message_key == "yaml.duplicate_key":
            name = str(exc.params.get("name", ""))
            known = name in FILE_KEYS or name in ENTRY_KEYS
            raise ConfigError(
                "yaml.duplicate_key", name=name if known else "?", line=exc.params.get("line", "?")
            ) from None
        if exc.message_key == "yaml.too_large":
            raise ConfigError("consents.too_large", limit=MAX_FILE_BYTES) from None
        raise


def parse_consents(data: bytes) -> ConsentFile:
    """Parse consents.yaml bytes: at most MAX_FILE_BYTES, UTF-8 with or without BOM, the strict YAML loader,
    the strict model, then the records against each other. Every problem is a ConfigError (exit 2):
    errors.consents.too_large, .encoding, .invalid {field, problem} and the kernel's errors.yaml.*."""
    if len(data) > MAX_FILE_BYTES:
        raise ConfigError("consents.too_large", limit=MAX_FILE_BYTES)
    raw = _yaml(decode_text(data, ConfigError, "consents.encoding"))
    if not isinstance(raw, dict):
        raise ConfigError("consents.invalid", field="consents.yaml", problem="not_mapping")
    for key in FILE_KEYS:
        if key not in raw:
            raise ConfigError("consents.invalid", field=key, problem="missing")
    try:
        parsed = ConsentFile.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        problem = str(first["type"])
        error = first.get("ctx", {}).get("error")
        if problem == "value_error" and str(error) in _PROBLEMS:
            problem = str(error)
        raise ConfigError("consents.invalid", field=_location(tuple(first["loc"])), problem=problem) from None
    found = consistency_problem(parsed.consents)
    if found is not None:
        index, name, problem = found
        raise ConfigError("consents.invalid", field=f"consents.{index}.{name}", problem=problem)
    return parsed


# --- the canonical form ------------------------------------------------------------------------------------


def dump_consents(consents: ConsentFile) -> bytes:
    """The canonical consents.yaml that ``vault consent add`` writes: the fixed comment header, records sorted
    by (subject, version), keys in the order subject, version, date, permitted_uses (ConsentUse order, flow
    style), withdrawn, ethics_approval_ref (left out when None, else a double-quoted string); UTF-8 without
    BOM, LF. parse_consents(dump_consents(x)) == x. An empty file is byte-equal to vault.store's
    CONSENTS_TEMPLATE, which ``vault init`` writes."""
    lines = [HEADER, f"format_version: {consents.format_version}\n"]
    entries = sorted(consents.consents, key=lambda entry: (entry.subject, entry.version))
    if not entries:
        lines.append("consents: []\n")
    else:
        lines.append("consents:\n")
    for entry in entries:
        uses = ", ".join(use.value for use in entry.permitted_uses)
        lines += [
            f"  - subject: {entry.subject}\n",
            f"    version: {entry.version}\n",
            f"    date: {entry.date.isoformat()}\n",
            f"    permitted_uses: [{uses}]\n",
            f"    withdrawn: {'true' if entry.withdrawn else 'false'}\n",
        ]
        if entry.ethics_approval_ref is not None:
            # JSON string escapes are valid in a YAML double-quoted scalar; the text is printable
            quoted = json.dumps(entry.ethics_approval_ref, ensure_ascii=False)
            lines.append(f"    ethics_approval_ref: {quoted}\n")
    return "".join(lines).encode("utf-8")


# --- the effective consent (A-30) --------------------------------------------------------------------------

ConsentState = Literal["none", "future_only", "withdrawn", "valid"]


@dataclass(frozen=True)
class EffectiveConsent:
    """The consent of a subject at a reference date: ``none`` (no record), ``future_only`` (every record is
    dated after it), ``withdrawn`` (the effective record is a full withdrawal) or ``valid`` with its uses.
    ``version`` is that of the effective record (None for none and future_only)."""

    state: ConsentState
    version: int | None = None
    uses: frozenset[ConsentUse] = field(default_factory=frozenset)

    def covers(self, use: ConsentUse) -> bool:
        return self.state == "valid" and use in self.uses


def effective(entries: Iterable[ConsentScope], as_of: dt.date) -> EffectiveConsent:
    """The record with the highest version whose date is on or before ``as_of`` (A-30; a record dated on
    ``as_of`` counts)."""
    records = list(entries)
    if not records:
        return EffectiveConsent("none")
    dated = [entry for entry in records if entry.date <= as_of]
    if not dated:
        return EffectiveConsent("future_only")
    current = max(dated, key=lambda entry: entry.version)
    if current.withdrawn:
        return EffectiveConsent("withdrawn", current.version)
    return EffectiveConsent("valid", current.version, frozenset(current.permitted_uses))
