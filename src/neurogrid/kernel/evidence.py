"""Evidence for rules that cannot be measured (NG-F12, RP-05, A-15, A-83).

``evidence.yaml`` (default ``<dataset>/.neurogrid/evidence.yaml``, ``check --evidence FILE`` overrides) holds
one entry per rule::

    format_version: 1
    evidence:
      GXDSL008-ACC-001:
        status: provided          # open | provided | partial | not_applicable
        document: .neurogrid/evidence/it-security-sop.pdf
        sha256: 3f...             # optional; compared with the document (upper case is accepted)
        reviewer: QA lead         # role or initials, never a name (A-51)
        date: 2026-11-02
        comment: AES-256 at rest, role concept v2
        justification: ...        # required for not_applicable

``provided`` means the user has filed a document; NeuroGrid does not judge its content. ``provided`` needs a
document (NG-F12: status and document reference), ``partial`` may lack one. Documents are plain relative
paths (A-52, no URLs), resolved against the evidence file's project root (A-66 applied to the file) without
following links. NeuroGrid computes the SHA-256 of every referenced document and reports it; a recorded
sha256 is compared. A semi-automatic rule passes when its document exists, is no link and, if a hash was
recorded, the hash matches (A-15 "Dokument vorhanden und Hash stimmt"). The file is a control file: invalid
content ends the run with exit 2 and names the field, never the text of a value (C2).
"""

from __future__ import annotations

import datetime as dt
import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from neurogrid.kernel.errors import ConfigError, UnsafePathError
from neurogrid.kernel.findings import Phase, Severity, Status, Verification
from neurogrid.kernel.provenance import sha256_file
from neurogrid.kernel.rules import RULE_ID_PATTERN
from neurogrid.kernel.safety import MAX_PATH_CHARS, check_relative, decode_text, is_link, load_yaml

MAX_ENTRIES = 10_000
_RULE_ID = re.compile(RULE_ID_PATTERN)
# Parts of a field location that may be shown in an error: field names and rule IDs, never value text (C2).
_SHOWN_LOCATION = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
# Problems the validators report (as the ValueError text, a fixed key; pydantic_core is outside the kernel's
# allowed libraries, A-23).
UNSAFE_PATH = "unsafe_path"
JUSTIFICATION_REQUIRED = "justification_required"
DOCUMENT_REQUIRED = "document_required"


class EvidenceState(StrEnum):
    OPEN = "open"
    PROVIDED = "provided"
    PARTIAL = "partial"
    NOT_APPLICABLE = "not_applicable"


class DocumentCheck(StrEnum):
    """What NeuroGrid found for a referenced document (A-15, A-52)."""

    OK = "ok"
    NO_DOCUMENT = "no_document"
    DOCUMENT_MISSING = "document_missing"  # not there, not a regular file, other case, or not readable
    DOCUMENT_LINK = "document_link"  # a link or junction on the way; not followed (A-52)
    HASH_MISMATCH = "hash_mismatch"


class EvidenceItem(BaseModel):
    """One entry of evidence.yaml. Strict like neurogrid.toml (A-53); ``status`` is read from its text."""

    model_config = ConfigDict(extra="forbid", strict=True)

    status: EvidenceState = Field(strict=False)
    document: str | None = Field(default=None, max_length=MAX_PATH_CHARS)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reviewer: str | None = Field(default=None, max_length=80)
    date: dt.date | None = None
    comment: str | None = Field(default=None, max_length=500)
    justification: str | None = Field(default=None, max_length=500)

    @field_validator("sha256", mode="before")
    @classmethod
    def _lower_case(cls, value: Any) -> Any:
        """PowerShell's Get-FileHash prints upper-case hex; both spellings name the same hash."""
        return value.lower() if isinstance(value, str) else value

    @field_validator("document")
    @classmethod
    def _plain_relative(cls, value: str | None) -> str | None:
        """A-52: a plain relative path (no '..', drive, UNC, device or stream, no URL), kept in POSIX form."""
        if value is None:
            return value
        try:
            return check_relative(value).as_posix()
        except UnsafePathError:
            raise ValueError(UNSAFE_PATH) from None

    @model_validator(mode="after")
    def _complete(self) -> EvidenceItem:
        if self.status is EvidenceState.NOT_APPLICABLE and not (self.justification or "").strip():
            raise ValueError(JUSTIFICATION_REQUIRED)  # A-15
        if self.status is EvidenceState.PROVIDED and self.document is None:
            raise ValueError(DOCUMENT_REQUIRED)  # NG-F12: every manual rule names its evidence document
        return self


RuleId = Annotated[str, StringConstraints(pattern=RULE_ID_PATTERN, max_length=64)]


class EvidenceFile(BaseModel):
    """The whole evidence.yaml (schemas/evidence.schema.json is generated from this model)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    format_version: Literal[1]
    evidence: dict[RuleId, EvidenceItem] = Field(default_factory=dict, max_length=MAX_ENTRIES)


def _location(parts: tuple[int | str, ...]) -> str:
    return ".".join(str(part) if _SHOWN_LOCATION.match(str(part)) else "?" for part in parts)


def parse_evidence(data: bytes) -> EvidenceFile:
    """Parse evidence.yaml bytes: UTF-8 with or without BOM, the strict YAML loader (no aliases, no duplicate
    keys, bounded size and depth, A-53), then the strict model. Every problem is a ConfigError (exit 2)."""
    raw = load_yaml(decode_text(data, ConfigError, "evidence.encoding"))
    if not isinstance(raw, dict):
        raise ConfigError("evidence.not_mapping")
    if "evidence" in raw and raw["evidence"] is None:
        raw = {**raw, "evidence": {}}  # an empty 'evidence:' section lists no entries
    entries = raw.get("evidence")
    if isinstance(entries, dict):
        for index, key in enumerate(entries, start=1):
            if not isinstance(key, str) or len(key) > 64 or not _RULE_ID.match(key):
                # the position, not the key: a malformed key may be any text (C2)
                raise ConfigError("evidence.invalid", field=f"evidence.#{index}", problem="rule_id")
    try:
        return EvidenceFile.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = tuple(first["loc"])
        problem = first["type"]
        error = first.get("ctx", {}).get("error")
        if problem == "value_error" and str(error) in (
            UNSAFE_PATH,
            JUSTIFICATION_REQUIRED,
            DOCUMENT_REQUIRED,
        ):
            problem = str(error)
        if problem == UNSAFE_PATH and len(location) >= 2:
            raise ConfigError("evidence.unsafe_path", rule=_location(location[1:2])) from None
        raise ConfigError("evidence.invalid", field=_location(location), problem=problem) from None


@dataclass(frozen=True)
class DocumentResult:
    """The check of one referenced document and the SHA-256 NeuroGrid computed from it (None if not read)."""

    check: DocumentCheck
    sha256: str | None = None


DocumentChecker = Callable[[EvidenceItem], DocumentResult]


def no_document_checker(item: EvidenceItem) -> DocumentResult:
    """For runs without a document root: a referenced document counts as missing, never as present."""
    return DocumentResult(
        DocumentCheck.NO_DOCUMENT if item.document is None else DocumentCheck.DOCUMENT_MISSING
    )


def file_document_checker(root: Path) -> DocumentChecker:
    """Check documents below ``root`` (A-15, A-52).

    Each path part must exist with exactly the stored spelling (compared with the directory listing, so that
    Windows and Linux agree) and must not be a link or junction; the document must be a regular file. Its
    SHA-256 is computed (streaming) and compared with a recorded one. Results are kept per document for the
    run.
    """
    found: dict[str, DocumentResult] = {}

    def locate(document: str) -> DocumentResult:
        try:
            relative = check_relative(document)
            current = root.resolve(strict=True)
        except (UnsafePathError, OSError):
            return DocumentResult(DocumentCheck.DOCUMENT_MISSING)
        for part in relative.parts:
            try:
                names = {entry.name for entry in current.iterdir()}
            except OSError:
                return DocumentResult(DocumentCheck.DOCUMENT_MISSING)
            if part not in names:
                return DocumentResult(DocumentCheck.DOCUMENT_MISSING)
            current = current / part
            if is_link(current):
                return DocumentResult(DocumentCheck.DOCUMENT_LINK)
        try:
            if not stat.S_ISREG(os.lstat(current).st_mode):
                return DocumentResult(DocumentCheck.DOCUMENT_MISSING)
            return DocumentResult(DocumentCheck.OK, sha256_file(current))
        except OSError:
            return DocumentResult(DocumentCheck.DOCUMENT_MISSING)

    def check(item: EvidenceItem) -> DocumentResult:
        if item.document is None:
            return DocumentResult(DocumentCheck.NO_DOCUMENT)
        if item.document not in found:
            found[item.document] = locate(item.document)
        result = found[item.document]
        if result.check is DocumentCheck.OK and item.sha256 is not None and item.sha256 != result.sha256:
            return DocumentResult(DocumentCheck.HASH_MISMATCH, result.sha256)
        return result

    return check


class EvidenceRecord(BaseModel):
    """One rule evaluated from evidence.yaml, as written to results.json (KONZEPT 2.3 ``evidence``, A-83).

    ``status`` is the entry's state (None: no entry, counted as open, A-15), ``outcome`` the rule's result
    after exceptions. ``sha256`` is computed by NeuroGrid from the document found; ``sha256_recorded`` is the
    value in evidence.yaml. ``document`` is the relative path as given (normalised to POSIX separators).
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    rulepack: str
    phase: Phase
    severity: Severity
    verification: Verification
    status: EvidenceState | None = None
    outcome: Status
    document: str | None = None
    document_check: DocumentCheck | None = None
    sha256: str | None = None
    sha256_recorded: str | None = None
    reviewer: str | None = None
    date: dt.date | None = None
    comment: str | None = None
    justification: str | None = None
