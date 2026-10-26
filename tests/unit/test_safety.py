from __future__ import annotations

import os
import socket
from pathlib import Path, PurePosixPath

import pytest

from conftest import dir_link, holding_process, wait_released  # type: ignore[import-not-found]
from neurogrid.kernel import netguard, safety
from neurogrid.kernel.errors import ConfigError, InputError, NetworkBlockedError, UnsafePathError
from neurogrid.kernel.safety import (
    WORK_LOCK_SUFFIX,
    WORK_MARK,
    WorkFolder,
    check_operator_path,
    check_relative,
    decode_text,
    is_link,
    load_yaml,
    read_limited,
    redact_paths,
    remove_leftovers,
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


# --- A-54: work folders a killed run left behind are removed at the next start -----------------------------

HOLD_WORK_FOLDER = """
import sys
from pathlib import Path

from neurogrid.kernel.safety import work_directory

with work_directory(Path(sys.argv[1])) as work:
    (work / "validator").mkdir()
    (work / "validator" / "validator.json").write_text("dataset-derived", encoding="utf-8")
    print(work, flush=True)
    sys.stdin.read()  # until it is killed
"""


def _lock_of(folder: Path) -> Path:
    return folder.with_name(folder.name + WORK_LOCK_SUFFIX)


def test_work_folder_of_a_killed_run_is_removed_at_the_next_start(tmp_path: Path) -> None:
    """A-54 "deleted in finally and at the next start": a run killed while it works (no finally runs) leaves
    its work folder with dataset-derived files; the next run in the same base removes it, but never the
    folder of a run that is still going (its lock file is locked by that process)."""
    base = tmp_path / "out"
    with holding_process(HOLD_WORK_FOLDER, str(base)) as (process, held):
        assert held.parent == base and held.name.startswith(safety.RUN_PREFIX)
        assert (held / "validator" / "validator.json").is_file() and _lock_of(held).is_file()
        with work_directory(base) as mine:  # the other run is still going
            assert held.is_dir() and _lock_of(held).is_file() and mine != held
        assert not mine.exists() and not _lock_of(mine).exists()
        assert (held / "validator" / "validator.json").is_file()
        process.kill()
        process.wait()
        wait_released(_lock_of(held))
        assert (held / "validator" / "validator.json").is_file()  # the killed run removed nothing
        assert _lock_of(held).read_bytes() == WORK_MARK
        with work_directory(base) as mine:
            assert not held.exists() and not _lock_of(held).exists()
            assert sorted(p.name for p in base.iterdir()) == [mine.name, _lock_of(mine).name]
    assert list(base.iterdir()) == []


def test_next_start_leaves_alone_what_is_not_a_leftover(tmp_path: Path) -> None:
    """Only a folder whose lock file holds the mark and is no longer locked counts: a folder with the prefix
    and no lock file (a user's own folder, or a run killed before it made its lock file: empty), a lock
    file without the mark (a run between creating and locking it) or with other content, a name that
    tempfile.mkdtemp does not make and another prefix stay. A lock file whose folder is gone goes."""
    entries = {
        "run-abcdefgh": None,  # no lock file
        "run-ijklmnop": b"",  # not locked yet
        "run-qrstuvwx": b"someone else's lock\n",
        "run-abcdefghi": WORK_MARK,  # nine characters: not made by mkdtemp
        "ng-pdf-abcdefgh": WORK_MARK,  # another prefix
        "run-12345678": WORK_MARK,  # a leftover
    }
    for name, lock in entries.items():
        (tmp_path / name).mkdir()
        (tmp_path / name / "keep.txt").write_text(name, encoding="utf-8")
        if lock is not None:
            (tmp_path / (name + WORK_LOCK_SUFFIX)).write_bytes(lock)
    (tmp_path / ("run-gone0000" + WORK_LOCK_SUFFIX)).write_bytes(WORK_MARK)  # its folder is gone
    (tmp_path / "run-file0000").write_text("a file, not a folder", encoding="utf-8")
    (tmp_path / ("run-file0000" + WORK_LOCK_SUFFIX)).write_bytes(WORK_MARK)
    before = sorted(p.name for p in tmp_path.iterdir())
    remove_leftovers(tmp_path, safety.RUN_PREFIX)
    gone = ["run-12345678", "run-12345678.lock", "run-gone0000.lock"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [name for name in before if name not in gone]
    for name in entries.keys() - {"run-12345678"}:
        assert (tmp_path / name / "keep.txt").read_text(encoding="utf-8") == name
    assert (tmp_path / "run-file0000").read_text(encoding="utf-8") == "a file, not a folder"
    remove_leftovers(tmp_path / "missing", safety.RUN_PREFIX)  # never fails the run


def test_next_start_never_follows_a_link(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "keep.txt").write_text("not NeuroGrid's", encoding="utf-8")
    base = tmp_path / "base"
    base.mkdir()
    dir_link(base / "run-linked00", target)
    (base / ("run-linked00" + WORK_LOCK_SUFFIX)).write_bytes(WORK_MARK)
    remove_leftovers(base, safety.RUN_PREFIX)
    assert (target / "keep.txt").read_text(encoding="utf-8") == "not NeuroGrid's"
    assert sorted(p.name for p in base.iterdir()) == ["run-linked00", "run-linked00.lock"]


def test_own_work_folders_are_never_leftovers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A file system that lets a second lock of the same process through (Linux emulates flock on NFS
    with record locks) still never makes a run remove its own folder."""
    with work_directory(tmp_path) as first:
        monkeypatch.setattr(safety, "_lock", lambda handle, *, wait: True)
        with work_directory(tmp_path) as second:
            assert first.is_dir() and _lock_of(first).is_file() and second.is_dir()
        assert first.is_dir() and not second.exists()
    assert list(tmp_path.iterdir()) == []


def test_work_folder_without_locks_and_one_that_was_not_removed_completely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a file system without locks the folder gets no mark: removed at the end, never by a later start.
    A folder its run could not remove completely keeps its lock file, so the next start removes the rest."""

    def no_locks(handle: int, *, wait: bool) -> bool:
        raise OSError(38, "locks not supported")

    with monkeypatch.context() as patch:
        patch.setattr(safety, "_lock", no_locks)
        unlocked = WorkFolder.create(tmp_path, safety.RUN_PREFIX)
    assert unlocked.lock.read_bytes() == b""
    unlocked.remove()
    assert list(tmp_path.iterdir()) == []
    folder = WorkFolder.create(tmp_path, safety.RUN_PREFIX)
    (folder.path / "left.txt").write_text("x", encoding="utf-8")
    with monkeypatch.context() as patch:
        patch.setattr(safety.shutil, "rmtree", lambda path, ignore_errors=False: None)
        folder.remove()
    assert (folder.path / "left.txt").is_file() and folder.lock.read_bytes() == WORK_MARK
    with work_directory(tmp_path) as mine:
        assert not folder.path.exists() and not folder.lock.exists() and mine.is_dir()
    assert list(tmp_path.iterdir()) == []
