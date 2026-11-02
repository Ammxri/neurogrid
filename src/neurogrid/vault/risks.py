"""The risk register of the vault: ``<vault>/risks.yaml`` (NV-F06; A-30, A-95), read for CORE-M14-02
(model.risks): the reader of the P9 freeze and the risks a run judges at its reference date.

risks.yaml is a control file (C2): a link at its place or anywhere in the vault path is never followed
(errors.vault.link, p6 decisions 2), and a file that is no regular file, cannot be read, is too large, is no
UTF-8 text or holds an invalid register ends the run with exit 2 (errors.risks.*). A missing vault and a vault
without risks.yaml are no error (states no_vault and no_file of LoadedRisks). Risk descriptions stay in the
file: nothing here puts them into an output (A-51).

CORE-M14-02 judges the risks dated on or before the reference date, as a consent record dated on it is in
effect (A-30); a risk dated later is only counted (notice.risks_future). Both depend on the file and the
reference date alone, so two runs give the same results (NG-N03).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from neurogrid.model.risks import MAX_FILE_BYTES, Risk, RiskRegister, parse_risks
from neurogrid.vault import store
from neurogrid.vault.store import RISKS_FILE, LoadedRegister, VaultLocation


class LoadedRisks(LoadedRegister[RiskRegister]):
    """The risk register a check run found: ``no_vault``, ``no_file`` or ``loaded`` (``risks: []`` is a
    loaded register without entries)."""

    def judged(self, as_of: date) -> list[Risk]:
        """The risks judged at ``as_of`` (judged); none without a file."""
        return judged(self.file, as_of) if self.file is not None else []

    def future(self, as_of: date) -> int:
        """How many risks are dated after ``as_of`` (future); 0 without a file."""
        return future(self.file, as_of) if self.file is not None else 0


def judged(register: RiskRegister, as_of: date) -> list[Risk]:
    """The risks CORE-M14-02 judges at the reference date ``as_of``: those dated on or before it, in ID order
    (the order of the measurements and of the report's tables; IDs are unique)."""
    return sorted((risk for risk in register.risks if risk.date <= as_of), key=lambda risk: risk.id)


def future(register: RiskRegister, as_of: date) -> int:
    """How many risks are dated after the reference date ``as_of``: not judged in this run."""
    return sum(1 for risk in register.risks if risk.date > as_of)


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
