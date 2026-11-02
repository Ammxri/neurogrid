"""The index of the NeuroVault export package: ``index.json`` (NV-F07, A-30, A-96). The schema is generated
from ExportIndex (tools/gen_schemas.py: schemas/export_index.schema.json).

index.json is the last member of the ZIP that ``vault export`` writes, canonical JSON with LF
(kernel.canonical.dumps). It holds the format version, the fixed sentence in zh and en, the tool that wrote
it, every other member of the archive in archive order (its part, its name in the archive, SHA-256 and size;
the language of a PIA file or a report and the format of a report), the manifest (its manifest_hash as
stored, the SHA-256 of the dataset's file and whether the archived copy shows pseudonymous names) and the
access log as archived (its head hash, i.e. the hash of the export event, the number of well-formed entries,
whether the chain is intact and the number of deviations). It holds no time, no path outside the archive and
no user or host name (A-51).

Only kernel and model imports (ARC-01).
"""

from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from neurogrid.kernel.provenance import SHA256_PATTERN
from neurogrid.model.results import Disclaimer, ToolInfo

FORMAT_VERSION: Literal[1] = 1
# The five parts of the export (A-30, NV-F07), in archive order; index.json lists every member but itself.
Part = Literal["manifest", "access_log", "roles", "pia", "report"]
PARTS: tuple[str, ...] = get_args(Part)
# The format of a report part: a report as html or pdf, or the evidence dossier (dossier.pdf, A-99), which
# holds both languages (no lang).
ReportFormat = Literal["html", "pdf", "dossier"]
Language = Literal["zh", "en"]
# The names of the members (fixed, A-96): manifest.json, access.jsonl, roles.yaml, pia/pia.<lang>.md,
# report/report.<lang>.<html|pdf>, report/dossier.pdf.
MEMBER_PATTERN = (
    r"^(manifest\.json|access\.jsonl|roles\.yaml|pia/pia\.(zh|en)\.md"
    r"|report/report\.(zh|en)\.(html|pdf)|report/dossier\.pdf)$"
)


class ExportPart(BaseModel):
    """One member of the archive: its part, its name in the archive, SHA-256 and size of its bytes; ``lang``
    for a PIA file and a report (not the dossier), ``format`` for a report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    part: Part
    file: str = Field(pattern=MEMBER_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size: int = Field(ge=0)
    lang: Language | None = None
    format: ReportFormat | None = None


class ExportManifest(BaseModel):
    """The manifest part: ``manifest_hash`` as the file stores it (the value the report shows), the SHA-256 of
    the file read from the dataset (or --manifest) and whether the archived manifest.json is the copy with the
    pseudonymous names of a raw folder (then its manifest_hash no longer matches its content)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_hash: str = Field(pattern=SHA256_PATTERN)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    pseudonymized: bool


class ExportAccessLog(BaseModel):
    """The access log as archived (bytes [0, S) after the export event, A-30): the head hash (the hash of
    the export event), the well-formed entries, whether the hash chain is intact and its deviations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    head: str = Field(pattern=SHA256_PATTERN)
    events: int = Field(ge=1)
    intact: bool
    deviations: int = Field(ge=0)


class ExportIndex(BaseModel):
    """index.json of the export package (A-96)."""

    model_config = ConfigDict(extra="forbid")

    format_version: Literal[1] = FORMAT_VERSION
    disclaimer: Disclaimer
    tool: ToolInfo
    parts: list[ExportPart] = Field(min_length=5, max_length=10)
    manifest: ExportManifest
    access_log: ExportAccessLog
