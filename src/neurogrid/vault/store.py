"""Where the vault lies and what it holds (NV-F01, NV-F03 to NV-F05, A-30, A-66, A-90, A-93 to A-95).

The vault folder is ``project_root / [vault] path`` (default ``.neurogrid/vault``; a plain relative path,
config._check_paths). It holds ``consents.yaml`` (consent records, written by ``vault consent add``),
``access.jsonl`` (the hash-chained access log, neurogrid.vault.ledger) and ``access.jsonl.lock`` (the lock
file of every reader and writer, neurogrid.vault.lock; the name is confirmed in P6, closing the A-82 note);
from P9 on also the registers ``roles.yaml`` (model.roles), ``risks.yaml`` (model.risks) and
``retention.yaml`` (model.retention), and the impact assessment ``pia/pia.zh.md`` and ``pia/pia.en.md``
(PIA_FILES). The log and its lock file are left out of the manifest (kernel.provenance.VAULT_LOG/VAULT_LOCK,
A-82); every other file of the vault is part of it (A-22; io.provenance.KNOWN_CONTROL_FILES names them all).

States (p6 decisions 2): ``present`` iff the vault folder exists; ``absent``; ``link`` if a part of the vault
path, the log, its lock file, consents.yaml, a register, the pia folder or a PIA file is a link or junction
(never followed, A-52, A-66), with ``link_part`` naming that part (relative to the vault folder:
``roles.yaml``, ``pia``, ``pia/pia.zh.md``); ``not_folder`` if a part of the vault path is no folder. A
present vault without access.jsonl is never repaired silently: only ``vault init`` creates the log. A vault
of P6 without the registers and PIA files is complete again after one ``vault init``, which adds them.

The registers are control files (C2), read for check by vault.roles, vault.retention and vault.risks
(load_for_check -> LoadedRegister) through read_vault_file: invalid content ends the run with exit 2
(errors.roles.*, errors.retention.*, errors.risks.*), a missing file is the state ``no_file``.
"""

from __future__ import annotations

import os
import secrets
import stat
import time
from contextlib import suppress
from dataclasses import dataclass
from functools import cache
from pathlib import Path, PurePosixPath
from typing import Generic, Literal, TypeVar

from neurogrid.kernel.errors import ConfigError, InputError, UnsafePathError
from neurogrid.kernel.provenance import VAULT_LOCK, VAULT_LOG
from neurogrid.kernel.safety import check_relative, is_link, read_limited
from neurogrid.model._registers import Register
from neurogrid.vault import _os

DEFAULT_VAULT_PATH = ".neurogrid/vault"  # config.VaultSection.path
CONSENTS_FILE = "consents.yaml"
ROLES_FILE = "roles.yaml"  # the role register (NV-F04, A-93)
RISKS_FILE = "risks.yaml"  # the risk register (NV-F06, A-95)
RETENTION_FILE = "retention.yaml"  # the retention periods (NV-F05, A-94)
PIA_FOLDER = "pia"  # the impact assessment (NV-F05, A-94), one file per language
PIA_FILES = ("pia.zh.md", "pia.en.md")
# The parts below the vault folder as link_part and the names of InitPart give them (relative to the folder)
PIA_PARTS = tuple(f"{PIA_FOLDER}/{name}" for name in PIA_FILES)
VAULT_FILES = (VAULT_LOG, VAULT_LOCK, CONSENTS_FILE, ROLES_FILE, RISKS_FILE, RETENTION_FILE)
# The PIA templates that vault init copies: package data, shipped in the wheel with the package folder
TEMPLATE_DIR = Path(__file__).parent / "templates"
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
# What ``vault init`` writes as roles.yaml, risks.yaml and retention.yaml (A-93 to A-95): an English comment
# header (purpose, the documentation, a commented neutral example and how to use it), then format_version 1
# and the empty list; each parses to an empty register (tests/unit/test_registers_model.py). NeuroGrid never
# rewrites these files. UTF-8 without BOM, LF.
ROLES_TEMPLATE = (
    b"# NeuroGrid role register of this dataset: which role may perform which action on which objects.\n"
    b"# NeuroGrid compares the access log with it as advice (CORE-NV04-01) and never refuses an access\n"
    b"# because of it. A role is a role name or initials, never a personal name. Descriptions and ethics\n"
    b"# references stay in this file; they never appear in results.json, a report or the console.\n"
    b"# Format: docs/<lang>/vault.md#roles. To use the example, delete the line 'roles: []' at the end and\n"
    b"# remove '# ' (the hash and the space after it) at the start of each example line.\n"
    b"#\n"
    b"# roles:\n"
    b"#   - role: data_steward\n"
    b"#     description: Prepares, checks and converts the dataset\n"
    b"#     actions: [read, check, convert, report, export, consent_manage]\n"
    b'#     objects: ["**", ".neurogrid/vault/consents.yaml"]\n'
    b'#     ethics_approval_ref: "EC-2026-17"\n'
    b"#   - role: QA.lead\n"
    b"#     description: Reviews the check results and the reports\n"
    b"#     actions: [read, report]\n"
    b'#     objects: ["**"]\n'
    b"format_version: 1\n"
    b"roles: []\n"
)
RISKS_TEMPLATE = (
    b"# NeuroGrid risk register of this dataset: risks found after the consents were given. For each risk\n"
    b"# dated on or before the reference date, CORE-M14-02 lists the subjects whose recordings need an\n"
    b"# affected use and whose valid consent has a version below min_consent_version; whether a new\n"
    b"# consent is needed is decided by the ethics committee. Descriptions stay in this file; they never\n"
    b"# appear in results.json, a report, an export or the console.\n"
    b"# Format: docs/<lang>/vault.md#risks. To use the example, delete the line 'risks: []' at the end and\n"
    b"# remove '# ' (the hash and the space after it) at the start of each example line.\n"
    b"#\n"
    b"# risks:\n"
    b"#   - id: R-2026-01\n"
    b"#     date: 2026-09-01\n"
    b"#     description: The recordings are also used to train a second model\n"
    b"#     affected_uses: [training, sharing]\n"
    b"#     min_consent_version: 2\n"
    b"format_version: 1\n"
    b"risks: []\n"
)
RETENTION_TEMPLATE = (
    b"# NeuroGrid retention periods of the files in this vault: for each object the date it was created,\n"
    b"# the date until which it is kept at least (min_until) and an optional review date (review_at).\n"
    b"# Objects: pia (the impact assessment in pia/), access_log, roles, risks, consents; an entry for pia\n"
    b"# and one for access_log are expected (NeuroGrid's reading of the PIPL, see the documentation).\n"
    b"# min_until lies at least three years after created (from 29 February: 1 March three years later),\n"
    b"# otherwise NeuroGrid stops with exit code 2. CORE-NV05-03 reminds you when a minimum retention\n"
    b"# ends; whether to keep or delete is your decision after your own legal review. EEG data have no\n"
    b"# retention period here.\n"
    b"# Format: docs/<lang>/vault.md#retention. To use the example, delete the line 'objects: []' at the\n"
    b"# end and remove '# ' (the hash and the space after it) at the start of each example line.\n"
    b"#\n"
    b"# objects:\n"
    b"#   - object: pia\n"
    b"#     created: 2026-11-02\n"
    b"#     min_until: 2029-11-02\n"
    b"#     review_at: 2029-08-01\n"
    b"#   - object: access_log\n"
    b"#     created: 2026-11-02\n"
    b"#     min_until: 2029-11-02\n"
    b"format_version: 1\n"
    b"objects: []\n"
)
# The registers ``vault init`` writes after consents.yaml, the log and its lock file (name, content)
REGISTER_TEMPLATES = (
    (ROLES_FILE, ROLES_TEMPLATE),
    (RISKS_FILE, RISKS_TEMPLATE),
    (RETENTION_FILE, RETENTION_TEMPLATE),
)


@cache
def pia_template(name: str) -> bytes:
    """The template of the PIA file ``name`` (one of PIA_FILES) as ``vault init`` writes it: package data in
    TEMPLATE_DIR, UTF-8 without BOM, LF. Its first line is the draft header of A-30 in the file's language;
    every field to fill in holds the placeholder marker of that language (A-94)."""
    if name not in PIA_FILES:
        raise ValueError(f"no PIA template {name!r}")
    return (TEMPLATE_DIR / name).read_bytes()


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
    def roles(self) -> Path:
        return self.path / ROLES_FILE

    @property
    def risks(self) -> Path:
        return self.path / RISKS_FILE

    @property
    def retention(self) -> Path:
        return self.path / RETENTION_FILE

    @property
    def pia_folder(self) -> Path:
        return self.path / PIA_FOLDER

    @property
    def pia_files(self) -> tuple[Path, ...]:
        """The PIA files in PIA_FILES order (zh, en), whether they exist or not."""
        return tuple(self.pia_folder / name for name in PIA_FILES)

    @property
    def project_root(self) -> Path:
        return self.path.parents[len(PurePosixPath(self.relative).parts) - 1]

    def object_name(self, name: str) -> str:
        """The event object of a file in the vault (``name`` relative to the vault folder, e.g. ``roles.yaml``
        or ``pia/pia.zh.md``): its path relative to the project root (A-66)."""
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
    for name in (*VAULT_FILES, PIA_FOLDER, *PIA_PARTS):  # the pia folder before the files in it
        if is_link(folder.joinpath(*PurePosixPath(name).parts)):
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
    consents.yaml from CONSENTS_TEMPLATE, an empty access.jsonl and an empty access.jsonl.lock, then (P9,
    A-93 to A-95) roles.yaml, risks.yaml and retention.yaml from REGISTER_TEMPLATES, the folder pia and in it
    pia.zh.md and pia.en.md (pia_template). Existing parts are kept byte for byte (idempotent; a vault of P6
    gets only the new parts); nothing is overwritten and no access event is written (the chain starts at the
    genesis hash). POSIX: folders 0700, files 0600, each file and each changed folder synced.

    Raises errors.vault.link {part} or .not_folder (UnsafePathError, InputError) before anything is created,
    errors.vault.not_writable (InputError) if a part cannot be created (also for a folder where a file
    belongs or a file where the pia folder belongs)."""
    current = location.refreshed()
    if current.state in ("link", "not_folder"):
        require_present(current)
    files = ((CONSENTS_FILE, CONSENTS_TEMPLATE), (VAULT_LOG, b""), (VAULT_LOCK, b""), *REGISTER_TEMPLATES)
    pia = [(name, pia_template(name)) for name in PIA_FILES]  # package data, read before anything is created
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
        parts += [_new_file(current, folder, name, data) for name, data in files]
        parts.append(_new_pia_folder(current, folder))
        parts += [_new_file(current, folder / PIA_FOLDER, name, data, PIA_FOLDER) for name, data in pia]
        _os.sync_folder(folder / PIA_FOLDER)
        _os.sync_folder(folder)
    except OSError:
        raise InputError("vault.not_writable") from None
    return tuple(parts)


def _new_pia_folder(location: VaultLocation, folder: Path) -> InitPart:
    """The folder pia of the vault ``folder``, created when missing (0700 on POSIX, the vault folder synced),
    else kept. A link at its place is errors.vault.link {part: pia}, anything else than a folder there
    errors.vault.not_writable."""
    pia = folder / PIA_FOLDER
    created = not os.path.lexists(pia)
    if created:
        _os.make_folder(pia)
        _os.sync_folder(folder)
    if is_link(pia):
        raise UnsafePathError("vault.link", part=PIA_FOLDER)
    if not pia.is_dir():
        raise InputError("vault.not_writable")
    return InitPart(location.object_name(PIA_FOLDER), created)


def _new_file(location: VaultLocation, folder: Path, name: str, data: bytes, below: str = "") -> InitPart:
    """Create a file of the vault with ``data`` when it is missing (0600 on POSIX, synced), else keep it as
    it is. ``below`` is the vault subfolder of the file (pia) for its part name. A link at its place is
    errors.vault.link {part}, anything else than a regular file there errors.vault.not_writable."""
    part = f"{below}/{name}" if below else name
    target = folder / name
    if is_link(target):
        raise UnsafePathError("vault.link", part=part)
    try:
        _os.create_file(target, data)
    except FileExistsError:
        if not target.is_file():
            raise InputError("vault.not_writable") from None
        return InitPart(location.object_name(part), False)
    return InitPart(location.object_name(part), True)


# --- reading the registers (C2; A-93 to A-95) --------------------------------------------------------------

RegisterState = Literal["no_vault", "no_file", "loaded"]
R = TypeVar("R", bound=Register)


@dataclass(frozen=True)
class LoadedRegister(Generic[R]):
    """A register as a check run found it: ``no_vault`` (no vault folder), ``no_file`` (a vault without the
    file) or ``loaded`` (an empty list included). vault.roles, vault.retention and vault.risks name their
    subclasses LoadedRoles, LoadedRetention and LoadedRisks."""

    state: RegisterState
    file: R | None = None

    @property
    def has_entries(self) -> bool:
        """At least one entry (an empty list is a register without entries)."""
        return self.file is not None and bool(self.file.entries)

    @property
    def sha256(self) -> str | None:
        """results.json config.<file>_sha256: the canonical hash of the parsed content; None without a
        file."""
        return self.file.canonical_sha256() if self.file is not None else None


def located(location: VaultLocation) -> VaultLocation | None:
    """The vault as it is now, for a reader of its files: None without a vault folder. A link in the vault
    path or at a vault file and a vault path that is no folder are the tool errors of every command that
    owns the vault (errors.vault.link {part}, errors.vault.not_folder; p6 decisions 2)."""
    current = location.refreshed()
    if current.state in ("link", "not_folder"):
        require_present(current)
    return None if current.state == "absent" else current


def read_vault_file(path: Path, *, part: str, errors: str, max_bytes: int) -> bytes:
    """The bytes of a control file of the vault (a register; C2), never through a link (A-52). ``part`` names
    the file in errors.vault.link, ``errors`` its error family. Raises FileNotFoundError for a missing file,
    UnsafePathError errors.vault.link {part} for a link and ConfigError errors.<errors>.not_a_file,
    .unreadable and .too_large {limit} (more than ``max_bytes``; nothing beyond them is read, A-53)."""
    if is_link(path):
        raise UnsafePathError("vault.link", part=part)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        raise
    except OSError:
        raise ConfigError(f"{errors}.unreadable") from None
    if not stat.S_ISREG(info.st_mode):
        raise ConfigError(f"{errors}.not_a_file")
    try:
        return read_limited(path, max_bytes)
    except InputError:
        raise ConfigError(f"{errors}.too_large", limit=max_bytes) from None
    except FileNotFoundError:
        raise
    except OSError:
        raise ConfigError(f"{errors}.unreadable") from None


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
