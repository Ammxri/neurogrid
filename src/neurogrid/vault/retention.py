"""The retention periods of the vault: ``<vault>/retention.yaml`` (NV-F05; A-30, A-94), read for
CORE-NV05-01 and CORE-NV05-03 (model.retention).

retention.yaml is a control file (C2): a link at its place or anywhere in the vault path is never followed
(errors.vault.link, p6 decisions 2), and a file that is no regular file, cannot be read, is too large, is no
UTF-8 text or holds invalid entries ends the run with exit 2 (errors.retention.*), a minimum retention of less
than three years included (errors.retention.too_short {object}, the DoD of P9). A missing vault and a vault
without retention.yaml are no error (states no_vault and no_file of LoadedRetention): CORE-NV05-01 reports the
missing file as a finding.
"""

from __future__ import annotations

from pathlib import Path

from neurogrid.model.retention import MAX_FILE_BYTES, RetentionRegister, parse_retention
from neurogrid.vault import store
from neurogrid.vault.store import RETENTION_FILE, LoadedRegister, VaultLocation


class LoadedRetention(LoadedRegister[RetentionRegister]):
    """The retention periods a check run found: ``no_vault``, ``no_file`` or ``loaded`` (``objects: []`` is
    a loaded register without entries)."""


def read_retention(path: Path) -> RetentionRegister:
    """retention.yaml at ``path``. Raises FileNotFoundError for a missing file, UnsafePathError
    errors.vault.link for a link and ConfigError errors.retention.not_a_file, .unreadable, .too_large and the
    errors of model.retention.parse_retention."""
    data = store.read_vault_file(path, part=RETENTION_FILE, errors="retention", max_bytes=MAX_FILE_BYTES)
    return parse_retention(data)


def load_for_check(location: VaultLocation) -> LoadedRetention:
    """The retention periods for CORE-NV05-01/03, read before the signal pass (C2, KONZEPT 1.4). Raises
    errors.vault.link {part} (UnsafePathError) and errors.vault.not_folder (InputError) like every command
    that reads the vault (p6 decisions 2), and the errors of read_retention."""
    current = store.located(location)
    if current is None:
        return LoadedRetention("no_vault")
    try:
        return LoadedRetention("loaded", read_retention(current.retention))
    except FileNotFoundError:
        return LoadedRetention("no_file")
