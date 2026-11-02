"""Reading the registers of the vault for check (NV-F04, NV-F05, NV-F06; A-93 to A-95; C2, p6 decisions 2):
load_for_check and read_* of vault.roles, vault.retention and vault.risks. The states no_vault, no_file and
loaded, the tool errors of a link, of a file that is no regular file, too large, unreadable or invalid, and
the hash of the loaded register."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from conftest import dir_link  # type: ignore[import-not-found]
from neurogrid.kernel import safety
from neurogrid.kernel.errors import ConfigError, InputError, UnsafePathError
from neurogrid.model import retention as retention_model
from neurogrid.model import risks as risks_model
from neurogrid.model import roles as roles_model
from neurogrid.vault import retention, risks, roles, store
from neurogrid.vault.store import (
    RETENTION_TEMPLATE,
    RISKS_TEMPLATE,
    ROLES_TEMPLATE,
    LoadedRegister,
    VaultLocation,
    init_vault,
    locate,
)


@dataclass(frozen=True)
class Kind:
    """One register: its file, error family, loader, reader, byte limit and template."""

    file: str
    errors: str
    load: Callable[[VaultLocation], LoadedRegister[Any]]
    read: Callable[[Path], Any]
    limit: int
    template: bytes
    loaded: type[LoadedRegister[Any]]


KINDS = {
    "roles": Kind(
        "roles.yaml",
        "roles",
        roles.load_for_check,
        roles.read_roles,
        roles_model.MAX_FILE_BYTES,
        ROLES_TEMPLATE,
        roles.LoadedRoles,
    ),
    "retention": Kind(
        "retention.yaml",
        "retention",
        retention.load_for_check,
        retention.read_retention,
        retention_model.MAX_FILE_BYTES,
        RETENTION_TEMPLATE,
        retention.LoadedRetention,
    ),
    "risks": Kind(
        "risks.yaml",
        "risks",
        risks.load_for_check,
        risks.read_risks,
        risks_model.MAX_FILE_BYTES,
        RISKS_TEMPLATE,
        risks.LoadedRisks,
    ),
}
CONTENT = {
    "roles": b"format_version: 1\nroles:\n  - {role: QA, description: d, actions: [read], objects: ['**']}\n",
    "retention": (
        b"format_version: 1\nobjects:\n  - {object: pia, created: 2026-01-01, min_until: 2029-01-01}\n"
    ),
    "risks": (
        b"format_version: 1\nrisks:\n"
        b"  - {id: R1, date: 2026-01-01, description: d, affected_uses: [training], min_consent_version: 2}\n"
    ),
}


def _vault(tmp_path: Path) -> VaultLocation:
    """A vault at the default location of ``tmp_path`` as ``vault init`` creates it."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    location = locate(tmp_path, store.DEFAULT_VAULT_PATH)
    init_vault(location)
    return location.refreshed()


@pytest.mark.parametrize("name", KINDS)
def test_the_three_states(tmp_path: Path, name: str) -> None:
    kind = KINDS[name]
    absent = kind.load(locate(tmp_path, store.DEFAULT_VAULT_PATH))
    assert absent == kind.loaded("no_vault") and absent.sha256 is None and not absent.has_entries
    location = _vault(tmp_path)
    template = kind.load(location)
    assert isinstance(template, kind.loaded) and template.state == "loaded"
    assert not template.has_entries and template.sha256 == template.file.canonical_sha256()  # type: ignore[union-attr]
    (location.path / kind.file).write_bytes(CONTENT[name])
    loaded = kind.load(location)
    assert loaded.has_entries and loaded.sha256 not in (None, template.sha256)
    (location.path / kind.file).unlink()
    missing = kind.load(location)
    assert missing == kind.loaded("no_file") and missing.sha256 is None
    with pytest.raises(FileNotFoundError):
        kind.read(location.path / kind.file)


@pytest.mark.parametrize("name", KINDS)
def test_the_loader_looks_at_the_vault_again(tmp_path: Path, name: str) -> None:
    """The location of the run start may be stale: the loader locates the vault as it is now."""
    kind = KINDS[name]
    stale = locate(tmp_path, store.DEFAULT_VAULT_PATH)  # absent when the run started
    _vault(tmp_path)
    assert kind.load(stale).state == "loaded"


@pytest.mark.parametrize("name", KINDS)
def test_a_link_at_the_register_or_in_the_vault_path_is_never_followed(tmp_path: Path, name: str) -> None:
    kind = KINDS[name]
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    root = tmp_path / "ds"
    location = _vault(root)
    (location.path / kind.file).unlink()
    dir_link(location.path / kind.file, elsewhere)  # a junction where Windows refuses symlinks
    with pytest.raises(UnsafePathError) as info:
        kind.load(location)
    assert info.value.message_key == "vault.link" and info.value.params == {"part": kind.file}
    with pytest.raises(UnsafePathError):
        kind.read(location.path / kind.file)  # the reader alone refuses it too
    other = tmp_path / "other"
    (other / ".neurogrid").mkdir(parents=True)
    dir_link(other / ".neurogrid" / "vault", location.path)
    with pytest.raises(UnsafePathError) as info:
        kind.load(locate(other, store.DEFAULT_VAULT_PATH))
    assert info.value.params == {"part": "vault"}


@pytest.mark.parametrize("name", KINDS)
def test_a_vault_path_that_is_no_folder(tmp_path: Path, name: str) -> None:
    (tmp_path / ".neurogrid").write_bytes(b"")
    with pytest.raises(InputError) as info:
        KINDS[name].load(locate(tmp_path, store.DEFAULT_VAULT_PATH))
    assert info.value.message_key == "vault.not_folder"


@pytest.mark.parametrize("name", KINDS)
def test_no_regular_file_too_large_unreadable_and_invalid(
    tmp_path: Path, name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    kind = KINDS[name]
    location = _vault(tmp_path)
    target = location.path / kind.file
    target.unlink()
    target.mkdir()
    with pytest.raises(ConfigError) as info:
        kind.load(location)
    assert info.value.message_key == f"{kind.errors}.not_a_file"
    target.rmdir()
    target.write_bytes(b"#" * (kind.limit + 1))
    with pytest.raises(ConfigError) as info:
        kind.load(location)
    assert (info.value.message_key, info.value.params) == (f"{kind.errors}.too_large", {"limit": kind.limit})
    target.write_bytes(b"format_version: 1\n")
    with pytest.raises(ConfigError) as info:
        kind.load(location)
    assert info.value.message_key == f"{kind.errors}.invalid"
    target.write_bytes(kind.template)

    def refuse(_path: Path, _limit: int) -> bytes:
        raise PermissionError(13, "denied")

    monkeypatch.setattr(store, "read_limited", refuse)
    with pytest.raises(ConfigError) as info:
        kind.load(location)
    assert info.value.message_key == f"{kind.errors}.unreadable"


def test_read_vault_file_reads_at_most_the_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A-53: nothing beyond the limit is read (kernel.safety.read_limited with the register's limit)."""
    calls: list[int] = []
    real = safety.read_limited

    def counted(path: Path, limit: int) -> bytes:
        calls.append(limit)
        return real(path, limit)

    monkeypatch.setattr(store, "read_limited", counted)
    path = tmp_path / "roles.yaml"
    path.write_bytes(ROLES_TEMPLATE)
    assert store.read_vault_file(path, part="roles.yaml", errors="roles", max_bytes=500_000) == ROLES_TEMPLATE
    assert calls == [500_000]


def test_retention_too_short_is_raised_by_the_loader(tmp_path: Path) -> None:
    location = _vault(tmp_path)
    location.retention.write_bytes(
        b"format_version: 1\nobjects:\n  - {object: pia, created: 2026-11-02, min_until: 2029-11-01}\n"
    )
    with pytest.raises(ConfigError) as info:
        retention.load_for_check(location)
    assert (info.value.message_key, info.value.params) == ("retention.too_short", {"object": "pia"})
