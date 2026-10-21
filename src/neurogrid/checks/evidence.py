"""evidence.yaml for one check run (NG-F12, RP-05, A-15, A-22, A-52, A-66, A-83; KONZEPT 1.2).

Location: ``check --evidence FILE`` (an operator path; a missing file ends with exit 2), else
``<dataset>/.neurogrid/evidence.yaml``, opened without following links (a linked ``.neurogrid`` or
``evidence.yaml`` ends with exit 2, like neurogrid.toml). Without a file every manual rule is evidence_open.
Document paths start at the evidence file's project root (A-66 applied to the file: the folder above
``.neurogrid``, the dataset root for a file inside the dataset, else the file's folder). Documents are best
kept in ``.neurogrid/evidence/``: the BIDS validator and discovery skip ``.neurogrid`` (A-65), and the
manifest covers it (A-22).

The file is a control file (C2): invalid content ends the run with exit 2 and names the field. This module
binds the document checker of the kernel to the run; it registers no measurer (the engine evaluates the
rules with the check ``evidence.document``).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from neurogrid.config import CONFIG_DIR, project_root_for
from neurogrid.io.identifying import looks_identifying
from neurogrid.kernel import canonical
from neurogrid.kernel.errors import ConfigError, InputError
from neurogrid.kernel.evidence import (
    DocumentChecker,
    EvidenceItem,
    file_document_checker,
    no_document_checker,
    parse_evidence,
)
from neurogrid.kernel.safety import MAX_YAML_BYTES, check_operator_path, read_limited, resolve_within

EVIDENCE_NAME = "evidence.yaml"


@dataclass(frozen=True)
class LoadedEvidence:
    """The parsed entries, where their documents start (None without a file) and the canonical SHA-256 of
    the parsed content (config.evidence_sha256; None without a file, so results differ when the evidence
    differs, NG-N03)."""

    entries: Mapping[str, EvidenceItem]
    root: Path | None = None
    sha256: str | None = None

    def checker(self) -> DocumentChecker:
        return no_document_checker if self.root is None else file_document_checker(self.root)


def _default_location(dataset_root: Path) -> Path | None:
    if not os.path.lexists(dataset_root / CONFIG_DIR):
        return None
    # Links are not followed (A-52): a junction .neurogrid or a linked file must not pull in foreign evidence.
    path = resolve_within(dataset_root, PurePosixPath(CONFIG_DIR, EVIDENCE_NAME), must_exist=False)
    return path if path.is_file() else None


def locate(explicit: Path | None, dataset_root: Path) -> Path | None:
    """The evidence file of the run, or None if there is none at the default location."""
    if explicit is None:
        return _default_location(dataset_root.resolve())
    path = check_operator_path(explicit)
    if not path.is_file():
        raise ConfigError("evidence.not_found")
    return path


def load(explicit: Path | None, dataset_root: Path) -> LoadedEvidence:
    """Locate and parse evidence.yaml (size limit and strict YAML before parsing, A-53)."""
    path = locate(explicit, dataset_root)
    if path is None:
        return LoadedEvidence(entries={})
    try:
        data = read_limited(path, MAX_YAML_BYTES)
    except InputError:
        raise ConfigError("evidence.too_large", limit=MAX_YAML_BYTES) from None
    except OSError:
        raise ConfigError("evidence.not_found") from None
    parsed = parse_evidence(data)
    return LoadedEvidence(
        entries=dict(parsed.evidence),
        root=project_root_for(path, dataset_root),
        sha256=canonical.sha256_of(parsed.model_dump(mode="json")),
    )


def identifying_entries(entries: Mapping[str, EvidenceItem]) -> int:
    """A-51 hint: entries whose reviewer or document name looks like a name or an identifying number. The
    values are shown in clear (REP-05 needs a readable document reference, A-83); only the count is
    reported."""
    return sum(
        1
        for item in entries.values()
        if any(looks_identifying(text) for text in (item.reviewer, item.document) if text)
    )
