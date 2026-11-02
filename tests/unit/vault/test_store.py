"""Vault location, states and ``init_vault`` (NV-F01 to NV-F05, A-30, A-66, A-90, A-93 to A-95; p6
decisions 2, 3; the registers and PIA files of the P9 freeze)."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import dir_link  # type: ignore[import-not-found]
from neurogrid.kernel.errors import InputError, UnsafePathError
from neurogrid.kernel.provenance import VAULT_LOCK, VAULT_LOG
from neurogrid.kernel.safety import load_yaml
from neurogrid.vault import _os, store
from neurogrid.vault.store import (
    CONSENTS_TEMPLATE,
    PIA_FILES,
    RETENTION_TEMPLATE,
    RISKS_TEMPLATE,
    ROLES_TEMPLATE,
    InitPart,
    init_vault,
    locate,
    locate_default,
    pia_template,
)

PARTS = (
    ".neurogrid",
    ".neurogrid/vault",
    ".neurogrid/vault/consents.yaml",
    ".neurogrid/vault/access.jsonl",
    ".neurogrid/vault/access.jsonl.lock",
    ".neurogrid/vault/roles.yaml",
    ".neurogrid/vault/risks.yaml",
    ".neurogrid/vault/retention.yaml",
    ".neurogrid/vault/pia",
    ".neurogrid/vault/pia/pia.zh.md",
    ".neurogrid/vault/pia/pia.en.md",
)
FOLDERS = (".neurogrid", ".neurogrid/vault", ".neurogrid/vault/pia")
# The parts of P6 (a vault made before P9 has only these)
P6_PARTS = PARTS[:5]
TEMPLATES = {
    "consents.yaml": CONSENTS_TEMPLATE,
    "access.jsonl": b"",
    "access.jsonl.lock": b"",
    "roles.yaml": ROLES_TEMPLATE,
    "risks.yaml": RISKS_TEMPLATE,
    "retention.yaml": RETENTION_TEMPLATE,
    "pia/pia.zh.md": pia_template("pia.zh.md"),
    "pia/pia.en.md": pia_template("pia.en.md"),
}


def _files(vault: Path) -> dict[str, bytes]:
    """Every file of the vault folder (relative POSIX name -> bytes)."""
    return {
        path.relative_to(vault).as_posix(): path.read_bytes() for path in vault.rglob("*") if path.is_file()
    }


def test_locate_states(tmp_path: Path) -> None:
    assert locate(tmp_path, ".neurogrid/vault").state == "absent"
    (tmp_path / ".neurogrid").mkdir()
    assert locate(tmp_path, ".neurogrid/vault").state == "absent"
    (tmp_path / ".neurogrid" / "vault").mkdir()
    present = locate(tmp_path, ".neurogrid/vault")
    assert (present.state, present.link_part) == ("present", None)  # present iff the folder exists
    (tmp_path / "file").write_bytes(b"x")
    assert locate(tmp_path, "file").state == "not_folder"
    assert locate(tmp_path, "file/vault").state == "not_folder"


def test_locate_paths_and_names(tmp_path: Path) -> None:
    location = locate(tmp_path, ".neurogrid/vault")
    assert location.path == tmp_path.resolve() / ".neurogrid" / "vault"
    assert location.relative == ".neurogrid/vault"
    assert location.log.name == VAULT_LOG == "access.jsonl"
    assert location.lock.name == VAULT_LOCK == "access.jsonl.lock"  # name confirmed in P6 (A-82)
    assert location.consents.name == "consents.yaml"
    vault = tmp_path.resolve() / ".neurogrid" / "vault"
    assert (location.roles, location.risks, location.retention) == (
        vault / "roles.yaml",
        vault / "risks.yaml",
        vault / "retention.yaml",
    )
    assert location.pia_folder == vault / "pia" and PIA_FILES == ("pia.zh.md", "pia.en.md")
    assert location.pia_files == (vault / "pia" / "pia.zh.md", vault / "pia" / "pia.en.md")
    assert location.object_name("pia/pia.zh.md") == ".neurogrid/vault/pia/pia.zh.md"
    assert (store.ROLES_FILE, store.RISKS_FILE, store.RETENTION_FILE, store.PIA_FOLDER) == (
        "roles.yaml",
        "risks.yaml",
        "retention.yaml",
        "pia",
    )
    assert location.project_root == tmp_path.resolve()
    assert location.object_name("consents.yaml") == ".neurogrid/vault/consents.yaml"
    assert locate_default(tmp_path) == location
    assert store.DEFAULT_VAULT_PATH == ".neurogrid/vault"


@pytest.mark.parametrize("spelling", [".neurogrid\\vault", "./.neurogrid//vault", ".neurogrid/vault/"])
def test_locate_normalises_the_relative_path(tmp_path: Path, spelling: str) -> None:
    location = locate(tmp_path, spelling)
    assert location.relative == ".neurogrid/vault"
    assert location.object_name("consents.yaml") == ".neurogrid/vault/consents.yaml"


@pytest.mark.parametrize("unsafe", ["../vault", "/abs/vault", "C:/vault", "", "a/../../b"])
def test_locate_refuses_paths_that_are_not_plain_relative(tmp_path: Path, unsafe: str) -> None:
    with pytest.raises(UnsafePathError):
        locate(tmp_path, unsafe)


def test_locate_relative_to_project_root(tmp_path: Path) -> None:
    """A-66: with a neurogrid.toml outside the dataset the project root is the folder of the toml, and the
    vault lies there, outside the dataset; its relative name stays the [vault] path."""
    project = tmp_path / "project"
    (project / "secure" / "vault").mkdir(parents=True)
    location = locate(project, "secure/vault")
    assert location.state == "present"
    assert location.path == project.resolve() / "secure" / "vault"
    assert location.project_root == project.resolve()
    assert location.object_name("consents.yaml") == "secure/vault/consents.yaml"
    assert location.refreshed() == location


LINK_PARTS = [
    ".neurogrid",
    "vault",
    VAULT_LOG,
    VAULT_LOCK,
    "consents.yaml",
    "roles.yaml",
    "risks.yaml",
    "retention.yaml",
    "pia",
    "pia/pia.zh.md",
    "pia/pia.en.md",
]


@pytest.mark.parametrize("part", LINK_PARTS)
def test_locate_link_state(tmp_path: Path, part: str) -> None:
    """A link anywhere in the vault path or at its files is never followed (p6 decisions 2; P9: also the
    registers, the pia folder and the PIA files, named relative to the vault folder)."""
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "vault").mkdir(parents=True)
    root = tmp_path / "ds"
    if part == ".neurogrid":
        root.mkdir()
        dir_link(root / ".neurogrid", elsewhere)
    elif part == "vault":
        (root / ".neurogrid").mkdir(parents=True)
        dir_link(root / ".neurogrid" / "vault", elsewhere / "vault")
    else:
        target = root / ".neurogrid" / "vault" / part
        target.parent.mkdir(parents=True)
        dir_link(target, elsewhere)  # a junction where Windows refuses symlinks
    location = locate(root, ".neurogrid/vault")
    assert (location.state, location.link_part) == ("link", part)
    with pytest.raises(UnsafePathError) as info:
        store.require_present(location)
    assert info.value.message_key == "vault.link" and info.value.params == {"part": part}


def test_require_present(tmp_path: Path) -> None:
    with pytest.raises(InputError) as info:
        store.require_present(locate(tmp_path, ".neurogrid/vault"))
    assert info.value.message_key == "vault.not_found"
    (tmp_path / ".neurogrid").write_bytes(b"")
    with pytest.raises(InputError) as info:
        store.require_present(locate(tmp_path, ".neurogrid/vault"))
    assert info.value.message_key == "vault.not_folder"
    (tmp_path / "v").mkdir()
    store.require_present(locate(tmp_path, "v"))


def test_init_creates_parts(tmp_path: Path) -> None:
    parts = init_vault(locate(tmp_path, ".neurogrid/vault"))
    assert parts == tuple(InitPart(name, True) for name in PARTS)
    vault = tmp_path / ".neurogrid" / "vault"
    assert (vault / "consents.yaml").read_bytes() == CONSENTS_TEMPLATE
    assert (vault / VAULT_LOG).read_bytes() == b""
    assert (vault / VAULT_LOCK).read_bytes() == b""
    assert _files(vault) == TEMPLATES  # the registers and the PIA files from their templates (A-93 to A-95)
    assert sorted(path.name for path in (vault / "pia").iterdir()) == sorted(PIA_FILES)
    assert locate(tmp_path, ".neurogrid/vault").state == "present"


def test_init_idempotent_keeps_bytes(tmp_path: Path) -> None:
    location = locate(tmp_path, ".neurogrid/vault")
    init_vault(location)
    vault = tmp_path / ".neurogrid" / "vault"
    (vault / "consents.yaml").write_bytes(b"format_version: 1\nconsents: []\n# mine\n")
    (vault / VAULT_LOG).write_bytes(b'{"x":1}\n')
    (vault / "roles.yaml").write_bytes(b"format_version: 1\nroles: []\n# mine\n")
    (vault / "retention.yaml").write_bytes(b"")
    (vault / "pia" / "pia.zh.md").write_bytes("已编辑\n".encode())
    before = _files(vault)
    assert init_vault(location) == tuple(InitPart(name, False) for name in PARTS)
    assert _files(vault) == before


def test_init_completes_a_vault_of_p6(tmp_path: Path) -> None:
    """A vault made before P9 (consents.yaml, the log and its lock file) gets only the registers, the pia
    folder and the PIA files; its own files are kept byte for byte (one vault init after the upgrade)."""
    vault = tmp_path / ".neurogrid" / "vault"
    vault.mkdir(parents=True)
    (vault / "consents.yaml").write_bytes(CONSENTS_TEMPLATE + b"# mine\n")
    (vault / VAULT_LOG).write_bytes(b'{"x":1}\n')
    (vault / VAULT_LOCK).write_bytes(b"")
    parts = init_vault(locate(tmp_path, ".neurogrid/vault"))
    assert [part.name for part in parts if part.created] == list(PARTS[5:])
    assert [part.name for part in parts if not part.created] == list(P6_PARTS)
    assert (vault / "consents.yaml").read_bytes() == CONSENTS_TEMPLATE + b"# mine\n"
    assert (vault / VAULT_LOG).read_bytes() == b'{"x":1}\n'
    (vault / "pia" / "pia.en.md").unlink()
    assert [part.name for part in init_vault(locate(tmp_path, ".neurogrid/vault")) if part.created] == [
        ".neurogrid/vault/pia/pia.en.md"
    ]


def test_init_creates_only_the_missing_parts(tmp_path: Path) -> None:
    """A present vault without access.jsonl is repaired only by ``vault init`` (p6 decisions 2)."""
    location = locate(tmp_path, ".neurogrid/vault")
    init_vault(location)
    (tmp_path / ".neurogrid" / "vault" / VAULT_LOG).unlink()
    parts = init_vault(location)
    assert [part.name for part in parts if part.created] == [".neurogrid/vault/access.jsonl"]


def test_init_with_a_custom_path_outside_the_dataset(tmp_path: Path) -> None:
    project = tmp_path / "project"  # the folder of a neurogrid.toml outside the dataset (A-66)
    project.mkdir()
    parts = init_vault(locate(project, "secure/vault"))
    assert [part.name for part in parts] == [
        "secure",
        "secure/vault",
        "secure/vault/consents.yaml",
        "secure/vault/access.jsonl",
        "secure/vault/access.jsonl.lock",
        "secure/vault/roles.yaml",
        "secure/vault/risks.yaml",
        "secure/vault/retention.yaml",
        "secure/vault/pia",
        "secure/vault/pia/pia.zh.md",
        "secure/vault/pia/pia.en.md",
    ]


@pytest.mark.parametrize("part", [".neurogrid", "vault"])
def test_init_refuses_linked_neurogrid_and_vault(tmp_path: Path, part: str) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    root = tmp_path / "ds"
    (root / ".neurogrid").mkdir(parents=True)
    if part == ".neurogrid":
        (root / ".neurogrid").rmdir()
        dir_link(root / ".neurogrid", elsewhere)
    else:
        dir_link(root / ".neurogrid" / "vault", elsewhere)
    with pytest.raises(UnsafePathError) as info:
        init_vault(locate(root, ".neurogrid/vault"))
    assert info.value.params == {"part": part}
    assert list(elsewhere.iterdir()) == []  # nothing was created behind the link


@pytest.mark.parametrize("part", ["roles.yaml", "pia", "pia/pia.en.md"])
def test_init_refuses_links_at_the_new_parts(tmp_path: Path, part: str) -> None:
    """P9: a link at a register, the pia folder or a PIA file ends vault init with errors.vault.link {part}
    before anything is created; nothing is written behind the link."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    target = tmp_path / "ds" / ".neurogrid" / "vault" / part
    target.parent.mkdir(parents=True)
    dir_link(target, elsewhere)
    with pytest.raises(UnsafePathError) as info:
        init_vault(locate(tmp_path / "ds", ".neurogrid/vault"))
    assert info.value.params == {"part": part}
    assert list(elsewhere.iterdir()) == []
    assert not (tmp_path / "ds" / ".neurogrid" / "vault" / "consents.yaml").exists()


def test_init_reports_a_file_where_the_pia_folder_belongs(tmp_path: Path) -> None:
    (tmp_path / ".neurogrid" / "vault").mkdir(parents=True)
    (tmp_path / ".neurogrid" / "vault" / "pia").write_bytes(b"")
    with pytest.raises(InputError) as info:
        init_vault(locate(tmp_path, ".neurogrid/vault"))
    assert info.value.message_key == "vault.not_writable"


def test_init_refuses_a_file_in_the_vault_path(tmp_path: Path) -> None:
    (tmp_path / ".neurogrid").write_bytes(b"")
    with pytest.raises(InputError) as info:
        init_vault(locate(tmp_path, ".neurogrid/vault"))
    assert info.value.message_key == "vault.not_folder"


def test_init_reports_a_part_that_cannot_be_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_path: Path, _data: bytes) -> None:
        raise PermissionError(13, "read-only")

    monkeypatch.setattr(_os, "create_file", refuse)
    with pytest.raises(InputError) as info:
        init_vault(locate(tmp_path, ".neurogrid/vault"))
    assert info.value.message_key == "vault.not_writable"


def test_init_reports_a_folder_where_a_file_belongs(tmp_path: Path) -> None:
    (tmp_path / ".neurogrid" / "vault" / "consents.yaml").mkdir(parents=True)
    with pytest.raises(InputError) as info:
        init_vault(locate(tmp_path, ".neurogrid/vault"))
    assert info.value.message_key == "vault.not_writable"


def test_replace_file(tmp_path: Path) -> None:
    target = tmp_path / "consents.yaml"
    target.write_bytes(b"old\n")
    store.replace_file(target, b"new\n")
    assert target.read_bytes() == b"new\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["consents.yaml"]  # no temporary file left
    store.replace_file(tmp_path / "fresh.yaml", b"x")  # also a file that does not exist yet
    assert (tmp_path / "fresh.yaml").read_bytes() == b"x"


@pytest.mark.parametrize("failures", [1, 2])
def test_replace_file_retries_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failures: int) -> None:
    """Windows refuses os.replace while another process has the target open: one retry after
    REPLACE_RETRY_S; a second refusal leaves the target unchanged and no temporary file behind."""
    target = tmp_path / "consents.yaml"
    target.write_bytes(b"old\n")
    real = os.replace
    calls: list[str] = []

    def busy(source: Path, destination: Path) -> None:
        calls.append(Path(source).name)
        if len(calls) <= failures:
            raise PermissionError(13, "in use")
        real(source, destination)

    with monkeypatch.context() as patched:
        patched.setattr(os, "replace", busy)
        if failures == 1:
            store.replace_file(target, b"new\n")
        else:
            with pytest.raises(PermissionError):
                store.replace_file(target, b"new\n")
    assert target.read_bytes() == (b"new\n" if failures == 1 else b"old\n")
    assert len(calls) == 2 and calls[0].startswith(".consents.yaml.") and calls[0].endswith(".tmp")
    assert sorted(path.name for path in tmp_path.iterdir()) == ["consents.yaml"]


def test_replace_file_failure_before_the_rename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "consents.yaml"
    target.write_bytes(b"old\n")

    def full(_path: Path, _data: bytes) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(_os, "create_file", full)
    with pytest.raises(OSError):
        store.replace_file(target, b"new\n")
    assert target.read_bytes() == b"old\n" and len(list(tmp_path.iterdir())) == 1


def test_consents_template() -> None:
    """The template is the canonical dump of an empty consent file (the consent area's test compares it
    with model.consent.dump_consents): comment header in English pointing to the documentation, LF, UTF-8
    without BOM."""
    text = CONSENTS_TEMPLATE.decode("ascii")
    assert b"\r" not in CONSENTS_TEMPLATE and not CONSENTS_TEMPLATE.startswith(b"\xef\xbb\xbf")
    assert text.endswith("format_version: 1\nconsents: []\n")
    assert all(line.startswith("#") for line in text.splitlines()[:-2])
    assert "docs/<lang>/vault.md" in text
    assert load_yaml(text) == {"format_version": 1, "consents": []}


def test_pia_templates_are_package_data() -> None:
    """vault init copies the PIA templates from the package (vault/templates, shipped with the package
    folder); tests/unit/test_registers_model.py checks their content."""
    for name in PIA_FILES:
        assert pia_template(name) == (store.TEMPLATE_DIR / name).read_bytes()
        assert pia_template(name).decode("utf-8").splitlines()[0]
    with pytest.raises(ValueError):
        pia_template("pia.de.md")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes (D-09: proven in the Linux CI)")
@pytest.mark.parametrize("umask", [0o022, 0o077, 0o277])
def test_init_posix_permissions(tmp_path: Path, umask: int) -> None:
    old = os.umask(umask)
    try:
        init_vault(locate(tmp_path, ".neurogrid/vault"))
        # consents.yaml rewritten as vault consent add does it: still 0600
        store.replace_file(tmp_path / ".neurogrid" / "vault" / "consents.yaml", CONSENTS_TEMPLATE)
    finally:
        os.umask(old)
    modes = {name: stat.S_IMODE((tmp_path / name).stat().st_mode) for name in PARTS}
    expected = {name: 0o700 if name in FOLDERS else 0o600 for name in modes}
    assert modes == expected, f"umask {umask:o}: measured {[f'{n} {m:o}' for n, m in modes.items()]}"


def _dacl(path: Path) -> str:
    """Windows: the DACL of ``path`` in SDDL ("D:P..." when it is protected, i.e. does not inherit from the
    parent folder), read with GetFileSecurityW through ctypes (no extra dependency)."""
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
    dacl_information = 0x4  # DACL_SECURITY_INFORMATION
    needed = wintypes.DWORD()
    advapi32.GetFileSecurityW(str(path), dacl_information, None, 0, ctypes.byref(needed))
    descriptor = ctypes.create_string_buffer(needed.value)
    assert advapi32.GetFileSecurityW(str(path), dacl_information, descriptor, needed, ctypes.byref(needed))
    text = wintypes.LPWSTR()
    assert advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
        descriptor, 1, dacl_information, ctypes.byref(text), None
    )
    try:
        return str(text.value)
    finally:
        kernel32.LocalFree(text)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows ACLs (the POSIX modes: the test above)")
def test_init_windows_folders_inherit_the_acls_of_their_parent(tmp_path: Path) -> None:
    """p6 decisions 2 and KONZEPT 2.8: on Windows the vault folders and files inherit the ACLs of the folder
    they are made in, as a folder made with cmd's mkdir and a file made with open() next to them; os.mkdir's
    mode (0o700 gives a protected ACL of the owner, SYSTEM and the administrators only, Python 3.12.4) is used
    on POSIX only."""
    subprocess.run(["cmd", "/c", "mkdir", "reference"], cwd=tmp_path, check=True)  # CreateDirectoryW, no SD
    (tmp_path / "reference.txt").write_bytes(b"")
    folder, file = _dacl(tmp_path / "reference"), _dacl(tmp_path / "reference.txt")
    assert folder.startswith("D:") and not folder.startswith("D:P")
    init_vault(locate(tmp_path, ".neurogrid/vault"))
    store.replace_file(tmp_path / ".neurogrid" / "vault" / "consents.yaml", CONSENTS_TEMPLATE)
    for name in FOLDERS:
        assert _dacl(tmp_path / name) == folder, name
    for name in PARTS:
        if name not in FOLDERS:
            assert _dacl(tmp_path / name) == file, name
