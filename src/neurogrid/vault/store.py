"""Where the vault lies and what it holds (NV-F01, NV-F03, A-30, A-66, A-90).

The vault folder is ``project_root / [vault] path`` (default ``.neurogrid/vault``; a plain relative path,
config._check_paths). It holds ``consents.yaml`` (consent records, written by ``vault consent add``),
``access.jsonl`` (the hash-chained access log, neurogrid.vault.ledger) and ``access.jsonl.lock`` (the lock
file of every reader and writer, neurogrid.vault.lock; the name is confirmed in P6, closing the A-82 note).
The log and its lock file are left out of the manifest (kernel.provenance.VAULT_LOG/VAULT_LOCK, A-82),
consents.yaml is part of it (A-22).

States (p6 decisions 2): ``present`` iff the vault folder exists; ``absent``; ``link`` if a part of the vault
path, the log, its lock file or consents.yaml is a link or junction (never followed, A-52, A-66), with
``link_part`` naming that part; ``not_folder`` if a part of the vault path is no folder. A present vault
without access.jsonl is never repaired silently: only ``vault init`` creates the log.
"""

from __future__ import annotations

import os
import secrets
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from neurogrid.kernel.errors import InputError, UnsafePathError
from neurogrid.kernel.provenance import VAULT_LOCK, VAULT_LOG
from neurogrid.kernel.safety import check_relative, is_link
from neurogrid.vault import _os

DEFAULT_VAULT_PATH = ".neurogrid/vault"  # config.VaultSection.path
CONSENTS_FILE = "consents.yaml"
VaultState = Literal["present", "absent", "link", "not_folder"]
# What ``vault init`` writes as consents.yaml: byte-equal to model.consent.dump_consents of an empty consent
# file (the consent area's canonical dump, which keeps this header). UTF-8 without BOM, LF.
CONSENTS_TEMPLATE = (
    b"# NeuroGrid consent records of this dataset (pseudonymous subject IDs only).\n"
    b"# Format: docs/<lang>/vault.md. 'neurogrid vault consent add' rewrites this file in a canonical form;\n"
    b"# comments added by hand are not kept.\n"
    b"format_version: 1\n"
    b"consents: []\n"
)


@dataclass(frozen=True)
class VaultLocation:
    """A vault location and its state when it was located (``refreshed`` looks again).

    ``path`` is the vault folder (project root resolved, the vault path below it not: links there are never
    followed), ``relative`` the [vault] path as normalised POSIX text relative to the project root (the
    namespace of event objects that name vault files, p6 decisions 3)."""

    path: Path
    relative: str
    state: VaultState
    link_part: str | None = None

    @property
    def log(self) -> Path:
        return self.path / VAULT_LOG

    @property
    def lock(self) -> Path:
        return self.path / VAULT_LOCK

    @property
    def consents(self) -> Path:
        return self.path / CONSENTS_FILE

    @property
    def project_root(self) -> Path:
        return self.path.parents[len(PurePosixPath(self.relative).parts) - 1]

    def object_name(self, name: str) -> str:
        """The event object of a file in the vault: its path relative to the project root (A-66)."""
        return f"{self.relative}/{name}"

    def refreshed(self) -> VaultLocation:
        """The same location with its state as it is now."""
        return locate(self.project_root, self.relative)


def locate(project_root: Path, vault_path: str) -> VaultLocation:
    """The vault at ``vault_path`` (relative to the project root, A-66). Raises UnsafePathError for a path
    that is no plain relative path (config._check_paths refuses those already)."""
    relative = check_relative(vault_path)
    root = Path(project_root).resolve()
    folder = root.joinpath(*relative.parts)
    text = relative.as_posix()
    current = root
    for part in relative.parts:
        current = current / part
        if is_link(current):
            return VaultLocation(folder, text, "link", part)
        if not os.path.lexists(current):
            return VaultLocation(folder, text, "absent")
        if not current.is_dir():
            return VaultLocation(folder, text, "not_folder")
    for name in (VAULT_LOG, VAULT_LOCK, CONSENTS_FILE):
        if is_link(folder / name):
            return VaultLocation(folder, text, "link", name)
    return VaultLocation(folder, text, "present")


def locate_default(dataset_root: Path) -> VaultLocation:
    """The vault at the default location of a dataset, for commands that read no neurogrid.toml (scan,
    manifest, verify; p6 decisions 4)."""
    return locate(dataset_root, DEFAULT_VAULT_PATH)


@dataclass(frozen=True)
class InitPart:
    """One part of the vault after ``init_vault``: its name relative to the project root (fixed names, shown
    in clear, A-51) and whether it was created now (else it was kept as it was)."""

    name: str
    created: bool


def require_present(location: VaultLocation) -> None:
    """Raise the tool error of a vault that is not present (exit 2): errors.vault.not_found, .link {part},
    .not_folder."""
    if location.state == "link":
        raise UnsafePathError("vault.link", part=location.link_part)
    if location.state == "absent":
        raise InputError("vault.not_found")
    if location.state == "not_folder":
        raise InputError("vault.not_folder")


def init_vault(location: VaultLocation) -> tuple[InitPart, ...]:
    """Create the missing parts of the vault (``vault init``, CLI-08): every missing folder of the vault path,
    consents.yaml from CONSENTS_TEMPLATE, an empty access.jsonl and an empty access.jsonl.lock. Existing parts
    are kept byte for byte (idempotent); nothing is overwritten and no access event is written (the chain
    starts at the genesis hash). POSIX: folders 0700, files 0600, each file and each changed folder synced.

    Raises errors.vault.link {part} or .not_folder (UnsafePathError, InputError) before anything is created,
    errors.vault.not_writable (InputError) if a part cannot be created."""
    current = location.refreshed()
    if current.state in ("link", "not_folder"):
        require_present(current)
    root = current.project_root
    parts: list[InitPart] = []
    folder = root
    try:
        for name in PurePosixPath(current.relative).parts:
            parent, folder = folder, folder / name
            created = not os.path.lexists(folder)
            if created:
                _os.make_folder(folder)
                _os.sync_folder(parent)
            if is_link(folder) or not folder.is_dir():  # replaced while we looked
                raise UnsafePathError("vault.link", part=name)
            parts.append(InitPart(folder.relative_to(root).as_posix(), created))
        for name, data in ((CONSENTS_FILE, CONSENTS_TEMPLATE), (VAULT_LOG, b""), (VAULT_LOCK, b"")):
            target = folder / name
            if is_link(target):
                raise UnsafePathError("vault.link", part=name)
            try:
                _os.create_file(target, data)
            except FileExistsError:
                if not target.is_file():
                    raise InputError("vault.not_writable") from None
                parts.append(InitPart(current.object_name(name), False))
                continue
            parts.append(InitPart(current.object_name(name), True))
        _os.sync_folder(folder)
    except OSError:
        raise InputError("vault.not_writable") from None
    return tuple(parts)


REPLACE_RETRY_S = 0.1  # one retry of os.replace on Windows, where a reader may hold the target open


def replace_file(target: Path, data: bytes) -> None:
    """Replace a file of the vault with ``data`` in one step (``vault consent add`` rewrites consents.yaml):
    a new temporary file ``.<name>.<random>.tmp`` next to it (0600 on POSIX, written and synced), os.replace
    with one retry after REPLACE_RETRY_S on PermissionError (Windows: another process has the target open),
    then the folder synced (POSIX). OSError means the target is unchanged; the temporary file is removed. The
    caller holds the vault lock."""
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(4)}.tmp")
    try:
        _os.create_file(temporary, data)
        try:
            temporary.replace(target)
        except PermissionError:
            time.sleep(REPLACE_RETRY_S)
            temporary.replace(target)
    except BaseException:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)
        raise
    with suppress(
        OSError
    ):  # the file is replaced; the folder sync only makes the new name survive a power loss
        _os.sync_folder(target.parent)
