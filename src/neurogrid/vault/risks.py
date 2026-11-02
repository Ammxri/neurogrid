"""The risk register of the vault: ``<vault>/risks.yaml`` (NV-F06; A-30, A-95), read for CORE-M14-02
(model.risks). The interface of the P9 freeze: the reader; the re-consent area builds on it.

risks.yaml is a control file (C2): a link at its place or anywhere in the vault path is never followed
(errors.vault.link, p6 decisions 2), and a file that is no regular file, cannot be read, is too large, is no
UTF-8 text or holds an invalid register ends the run with exit 2 (errors.risks.*). A missing vault and a vault
without risks.yaml are no error (states no_vault and no_file of LoadedRisks). Risk descriptions stay in the
file: nothing here puts them into an output (A-51).
"""

from __future__ import annotations

from pathlib import Path

from neurogrid.model.risks import MAX_FILE_BYTES, RiskRegister, parse_risks
from neurogrid.vault import store
from neurogrid.vault.store import RISKS_FILE, LoadedRegister, VaultLocation


class LoadedRisks(LoadedRegister[RiskRegister]):
    """The risk register a check run found: ``no_vault``, ``no_file`` or ``loaded`` (``risks: []`` is a
    loaded register without entries)."""


def read_risks(path: Path) -> RiskRegister:
    """risks.yaml at ``path``. Raises FileNotFoundError for a missing file, UnsafePathError errors.vault.link
    for a link and ConfigError errors.risks.not_a_file, .unreadable, .too_large and the errors of
    model.risks.parse_risks."""
    data = store.read_vault_file(path, part=RISKS_FILE, errors="risks", max_bytes=MAX_FILE_BYTES)
    return parse_risks(data)


def load_for_check(location: VaultLocation) -> LoadedRisks:
    """The risk register for CORE-M14-02, read before the signal pass (C2, KONZEPT 1.4). Raises
    errors.vault.link {part} (UnsafePathError) and errors.vault.not_folder (InputError) like every command
    that reads the vault (p6 decisions 2), and the errors of read_risks."""
    current = store.located(location)
    if current is None:
        return LoadedRisks("no_vault")
    try:
        return LoadedRisks("loaded", read_risks(current.risks))
    except FileNotFoundError:
        return LoadedRisks("no_file")
