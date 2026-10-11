from __future__ import annotations

import os
import socket
from pathlib import Path, PurePosixPath

import pytest

from neurogrid.kernel import netguard
from neurogrid.kernel.errors import ConfigError, InputError, NetworkBlockedError, UnsafePathError
from neurogrid.kernel.safety import (
    check_operator_path,
    check_relative,
    decode_text,
    is_link,
    load_yaml,
    read_limited,
    redact_paths,
    resolve_within,
    work_directory,
)


def test_yaml_plain_mapping() -> None:
    assert load_yaml("a: 1\nb: [x, y]\n") == {"a": 1, "b": ["x", "y"]}


def test_yaml_rejects_alias() -> None:
    with pytest.raises(ConfigError) as info:
        load_yaml("a: &x [1, 2]\nb: *x\n")
    assert info.value.message_key == "yaml.alias"


def test_yaml_rejects_duplicate_key() -> None:
    with pytest.raises(ConfigError) as info:
        load_yaml("severity: info\nseverity: error\n")
    assert info.value.message_key == "yaml.duplicate_key"


def test_yaml_rejects_python_tags() -> None:
    with pytest.raises(ConfigError):
        load_yaml("x: !!python/object/apply:os.system ['echo hi']\n")


def test_yaml_limits() -> None:
    with pytest.raises(ConfigError) as info:
        load_yaml("a: " + "x" * 50, max_bytes=10)
    assert info.value.message_key == "yaml.too_large"
    deep = "a: " + "[" * 40 + "]" * 40
    with pytest.raises(ConfigError) as info:
        load_yaml(deep)
    assert info.value.message_key == "yaml.too_deep"


def test_yaml_syntax_error() -> None:
    with pytest.raises(ConfigError) as info:
        load_yaml("a: [1, 2\n")
    assert info.value.message_key == "yaml.syntax"


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("/etc/passwd", "path.absolute"),
        ("\\\\server\\share\\x.eeg", "path.absolute"),
        ("C:\\data\\x.eeg", "path.colon"),
        ("x.edf:stream", "path.colon"),
        ("../secret.txt", "path.parent"),
        ("a/../../b", "path.parent"),
        ("CON", "path.reserved"),
        ("dir/nul.txt", "path.reserved"),
        ("dir./x", "path.trailing"),
        ("", "path.invalid"),
        ("a\x00b", "path.invalid"),
        ("./", "path.invalid"),
    ],
)
def test_check_relative_rejects(raw: str, key: str) -> None:
    with pytest.raises(UnsafePathError) as info:
        check_relative(raw)
    assert info.value.message_key == key


def test_check_relative_accepts() -> None:
    assert check_relative("sub-01\\eeg/./x.edf") == PurePosixPath("sub-01/eeg/x.edf")


def test_resolve_within(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.txt").write_text("x", encoding="utf-8")
    assert resolve_within(tmp_path, PurePosixPath("a/f.txt")) == (tmp_path / "a" / "f.txt").resolve()
    with pytest.raises(FileNotFoundError):
        resolve_within(tmp_path, PurePosixPath("a/missing.txt"))


def test_resolve_within_refuses_links(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    try:
        Path(root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not permitted on this system")
    assert is_link(root / "link")
    with pytest.raises(UnsafePathError) as info:
        resolve_within(root, PurePosixPath("link"), must_exist=False)
    assert info.value.message_key == "path.link"


@pytest.mark.parametrize("raw", ["\\\\server\\share\\data", "//server/share", "\\\\?\\C:\\x", "\\\\.\\COM1"])
def test_operator_path_rejects_network_and_devices(raw: str) -> None:
    with pytest.raises(UnsafePathError):
        check_operator_path(raw)


def test_operator_path_rejects_streams_and_accepts_local(tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError):
        check_operator_path(str(tmp_path / "x.edf:hidden"))
    assert check_operator_path(tmp_path / "results.json") == tmp_path / "results.json"
    with pytest.raises(UnsafePathError):
        check_operator_path("")


def test_work_directory_is_removed(tmp_path: Path) -> None:
    with work_directory(tmp_path / "work") as path:
        (path / "f").write_text("x", encoding="utf-8")
        kept = path
    assert not kept.exists()


def test_netguard_blocks_remote_and_allows_loopback() -> None:
    netguard.install()
    before = netguard.blocked_count()
    with pytest.raises(NetworkBlockedError):
        socket.getaddrinfo("example.org", 443)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock, pytest.raises(NetworkBlockedError):
        sock.connect(("192.0.2.1", 9))
    assert netguard.blocked_count() == before + 2
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    with socket.create_connection(server.getsockname(), timeout=2):
        pass
    server.close()
    assert netguard._is_local(b"::1") and netguard._is_local(None) and not netguard._is_local(5)


def test_yaml_duplicate_key_names_the_key_without_clashing() -> None:
    with pytest.raises(ConfigError) as info:
        load_yaml("version: '1'\nversion: '2'\n")
    assert info.value.params == {"name": "version", "line": 2}


def test_yaml_unhashable_key_is_a_syntax_error() -> None:
    with pytest.raises(ConfigError) as info:
        load_yaml("? [a, b]\n: 1\n")
    assert info.value.message_key == "yaml.syntax"


@pytest.mark.parametrize("depth", [33, 400, 5000])
def test_yaml_depth_is_limited_while_composing(depth: int) -> None:
    with pytest.raises(ConfigError) as info:
        load_yaml("a: " + "[" * depth + "]" * depth)
    assert info.value.message_key == "yaml.too_deep"
    assert load_yaml("a: " + "[" * 31 + "]" * 31) is not None


def test_read_limited_and_decode(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_bytes(b"x" * 11)
    with pytest.raises(InputError) as info:
        read_limited(path, 10)
    assert info.value.message_key == "file.too_large"
    assert read_limited(path, 11) == b"x" * 11
    assert decode_text(b"\xef\xbb\xbfabc") == "abc"
    with pytest.raises(InputError):
        decode_text(b"\xff\xfe")


@pytest.mark.skipif(os.name != "nt", reason="UNC and drive semantics exist only on Windows")
@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("\\/server/share/x", "path.unc"),
        ("/\\server\\share\\x", "path.unc"),
        ("\\/?/UNC/server/share", "path.device"),
        ("\\/./PhysicalDrive0", "path.device"),
        ("\\??\\UNC\\server\\share\\ds", "path.device"),
        ("/??/GLOBALROOT/Device/Mup/server/share", "path.device"),
        ("\\??\\GLOBALROOT\\Device\\HarddiskVolume3\\data", "path.device"),
        ("CON", "path.reserved"),
        ("out\\aux.json", "path.reserved"),
        ("C:\\Windows\\Temp\\NUL", "path.reserved"),
        ("CONIN$", "path.reserved"),
    ],
)
def test_operator_path_rejects_network_device_and_reserved_names(raw: str, key: str) -> None:
    with pytest.raises(UnsafePathError) as info:
        check_operator_path(raw)
    assert info.value.message_key == key


@pytest.mark.skipif(os.name != "nt", reason="junctions are a Windows feature")
def test_operator_path_rejects_link_to_network_share(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neurogrid.kernel import safety

    monkeypatch.setattr(safety, "_is_network_drive", lambda path: path.anchor.upper().startswith("Z:"))
    with pytest.raises(UnsafePathError):
        check_operator_path("Z:\\data\\ds")
    assert check_operator_path(tmp_path) == tmp_path


@pytest.mark.skipif(os.name == "nt", reason="POSIX allows ':' in names")
def test_operator_path_allows_colons_on_posix(tmp_path: Path) -> None:
    assert check_operator_path(str(tmp_path / "2026-10-11T10:30")) == tmp_path / "2026-10-11T10:30"


def test_redact_paths_covers_all_spellings(tmp_path: Path) -> None:
    root = tmp_path / "Mustermann_Max"
    home = tmp_path
    text = f"{root}\\x.edf | {str(root).replace(chr(92), '/')}/y | {repr(str(root))} | {home}\\other"
    cleaned = redact_paths(text, {"<dataset>": root, "~": home})
    assert "Mustermann" not in cleaned and str(home) not in cleaned
    assert cleaned.count("<dataset>") == 3 and "~" in cleaned
    assert redact_paths(f"{root}_suffix", {"<dataset>": root}) == f"{root}_suffix"  # only whole segments


def test_netguard_blocks_all_name_resolution() -> None:
    netguard.install()
    for call in (
        lambda: socket.gethostbyname("example.org"),
        lambda: socket.gethostbyname_ex("example.org"),
        lambda: socket.gethostbyaddr("8.8.8.8"),
        lambda: socket.getnameinfo(("8.8.8.8", 53), 0),
    ):
        with pytest.raises(NetworkBlockedError):
            call()


def test_yaml_control_character_is_a_syntax_error() -> None:
    with pytest.raises(ConfigError) as info:
        load_yaml("a: \x07\n")
    assert info.value.message_key == "yaml.syntax"
