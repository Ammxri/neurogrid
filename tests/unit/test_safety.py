from __future__ import annotations

import os
import re
import socket
import stat
import tempfile
from pathlib import Path, PurePosixPath

import pytest

from conftest import dir_link, holding_process, wait_released  # type: ignore[import-not-found]
from neurogrid.kernel import netguard, safety
from neurogrid.kernel.errors import ConfigError, InputError, NetworkBlockedError, UnsafePathError
from neurogrid.kernel.safety import (
    WORK_LOCK,
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
    stream = str(tmp_path / "x.edf:hidden")
    if os.name == "nt":
        with pytest.raises(UnsafePathError):
            check_operator_path(stream)
    else:  # A-67: a colon is an ordinary character on POSIX (test_operator_path_allows_colons_on_posix)
        assert check_operator_path(stream) == Path(stream)
    assert safety.operator_path_problem(stream, windows=True) == "path.colon"  # Windows' verdict, anywhere
    assert check_operator_path(tmp_path / "results.json") == tmp_path / "results.json"
    with pytest.raises(UnsafePathError):
        check_operator_path("")


WINDOWS_FORMS = [
    ("\\\\server\\share\\data", "path.unc"),
    ("//server/share", "path.unc"),
    ("\\/server/share/x", "path.unc"),
    ("\\\\?\\C:\\x", "path.device"),
    ("\\\\.\\COM1", "path.device"),
    ("\\/?/UNC/server/share", "path.device"),
    ("\\??\\UNC\\server\\share\\ds", "path.device"),
]


@pytest.mark.parametrize("windows", [True, False], ids=["windows", "posix"])
@pytest.mark.parametrize(("raw", "key"), WINDOWS_FORMS)
def test_windows_network_and_device_forms_are_refused_on_every_platform(
    raw: str, key: str, windows: bool
) -> None:
    """Linux CI failures (test_single_file_target, test_operator_path_rejects_network_and_devices): on POSIX
    only '//' was refused, so '\\\\server\\share' was taken for a relative name (input.not_found; with --out
    a file of that name in the working folder). A root that starts with a backslash and another separator,
    or the NT namespace prefix, is a Windows network or device path an operator typed or pasted: refused on
    both platforms with the same key (A-52, A-67)."""
    assert safety.operator_path_problem(raw, windows=windows) == key


@pytest.mark.parametrize(
    "raw",
    [
        "/\\server\\share\\x",
        "\\x.edf",
        "a\\b\\c.edf",
        "x.edf:hidden",
        "/??/GLOBALROOT/x",
        "CON",
        "out/aux.json",
    ],
)
def test_posix_keeps_names_that_are_legal_there(raw: str) -> None:
    """A-67: on POSIX colons, reserved Windows device names and backslashes inside a name are ordinary
    characters, and '/\\…' is an absolute POSIX path; only a backslash root and '//' are refused."""
    assert safety.operator_path_problem(raw, windows=False) is None


@pytest.mark.parametrize(
    ("raw", "key"),
    [("C:\\data\\x.edf:hidden", "path.colon"), ("out\\aux.json", "path.reserved"), ("D:relative\\x", None)],
)
def test_windows_verdicts_are_checked_on_every_platform(raw: str, key: str | None) -> None:
    assert safety.operator_path_problem(raw, windows=True) == key


def test_temporary_files_ask_for_the_mode_of_any_new_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """tempfile.mkstemp's 0600 survived the rename into every output on POSIX; create_temporary asks for
    0666 (the system takes the umask off), with mkstemp's exclusive creation and name pattern."""
    asked: list[tuple[str, int, int]] = []
    real_open = os.open

    def spy(path: str, flags: int, mode: int = 0o777) -> int:
        asked.append((path, flags, mode))
        if len(asked) == 1:  # a name that is taken: the next one is tried
            raise FileExistsError(17, "exists", path)
        return real_open(path, flags, mode)

    monkeypatch.setattr(safety.os, "open", spy)
    handle, name = safety.create_temporary(tmp_path, ".results.json.")
    os.close(handle)
    assert len(asked) == 2 and asked[1][0] == name and asked[1][2] == 0o666
    assert asked[1][1] & os.O_EXCL and asked[1][1] & os.O_CREAT
    assert (
        re.fullmatch(r"\.results\.json\.[a-z0-9_]{8}\.tmp", Path(name).name) and Path(name).parent == tmp_path
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_temporary_files_follow_the_umask_on_posix(tmp_path: Path) -> None:
    previous = os.umask(0o027)
    try:
        handle, name = safety.create_temporary(tmp_path, ".manifest.json.")
        os.close(handle)
    finally:
        os.umask(previous)
    assert stat.S_IMODE(Path(name).stat().st_mode) == 0o640


@pytest.mark.skipif(os.name != "nt", reason="the temporary folder of Windows is the user's own")
def test_temp_work_base_on_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    assert safety.temp_work_base() == tmp_path / "neurogrid"


@pytest.mark.skipif(os.name == "nt", reason="POSIX: the temporary folder is shared by every user")
def test_temp_work_base_is_the_users_own_on_posix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """/tmp is shared: one '/tmp/neurogrid' for all users let the first user's folder (0755) refuse every
    other user's runs, and its owner could swap a run's work folder (staged recordings, validator output)
    for one of theirs. The base carries the uid, is created 0700, and one that is a link, belongs to someone
    else or others may write to is refused."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    base = safety.temp_work_base()
    assert base == tmp_path / f"neurogrid-{os.getuid()}"
    assert stat.S_IMODE(base.stat().st_mode) == 0o700
    with work_directory(base) as work:
        assert work.parent == base
    base.chmod(0o777)
    with pytest.raises(InputError) as info:
        safety.temp_work_base()
    assert info.value.message_key == "output.not_writable"
    base.chmod(0o700)
    real_uid = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: real_uid + 1)  # a folder of that name made by someone else
    (tmp_path / f"neurogrid-{real_uid + 1}").mkdir(mode=0o700)
    with pytest.raises(InputError):
        safety.temp_work_base()
    monkeypatch.setattr(os, "getuid", lambda: real_uid)
    base.rmdir()
    (tmp_path / "elsewhere").mkdir(mode=0o700)
    base.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    with pytest.raises(InputError):
        safety.temp_work_base()


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


NAMES = {"<user>": ("ngtester",), "<host>": ("ng-lab-pc",)}


def test_redact_paths_replaces_login_and_computer_names_as_whole_words() -> None:
    """A-51 'keine Rechner- oder Benutzernamen' outside the home folder, e.g. Linux's /tmp/pytest-of-<user>
    and /media/<user>/<stick>: whole words without case, as the G1 privacy check searches them."""
    text = "/tmp/pytest-of-NGTester/x | /media/ngtester/USB | /net/ng-lab-pc/eeg | ngtesters | xngtester"
    assert redact_paths(text, {}, NAMES) == (
        "/tmp/pytest-of-<user>/x | /media/<user>/USB | /net/<host>/eeg | ngtesters | xngtester"
    )
    home = Path.cwd() / "ngtester"
    assert redact_paths(f"{home}{os.sep}a", {"~": home}, NAMES) == f"~{os.sep}a"  # the root first
    trace = 'File "C:\\Users\\x\\ngtester.py", line 3\n  File "~/ng-lab-pc/y.py"'
    assert redact_paths(trace, {}, NAMES) == 'File "C:\\Users\\x\\<user>.py", line 3\n  File "~/<host>/y.py"'


def test_redact_paths_leaves_dataset_names_alone() -> None:
    """Only the computer's paths (absolute or '~') carry its names: a login such as 'eeg' must not garble
    BIDS names or names below '<dataset>' in notices and errors (they follow the pseudonym rules, A-51)."""
    names = {"<user>": ("eeg",)}
    root = Path.cwd() / "ds"
    for text in ("sub-01_task-rest_eeg.edf", "eeg", f"{root}{os.sep}sub-01{os.sep}eeg{os.sep}x_eeg.edf"):
        assert "<user>" not in redact_paths(text, {"<dataset>": root}, names), text
    assert redact_paths("/srv/eeg/out/eeg.json", {}, names) == "/srv/<user>/out/<user>.json"


def test_redact_paths_keeps_its_own_labels() -> None:
    names = {"<user>": ("dataset",), "<host>": ("user",)}
    root, home = Path.cwd() / "ds", Path.cwd() / "h"
    shown = redact_paths(
        f"{home}{os.sep}dataset{os.sep}x | {root}{os.sep}dataset", {"<dataset>": root, "~": home}, names
    )
    assert shown == f"~{os.sep}<user>{os.sep}x | <dataset>{os.sep}dataset"


def test_redact_paths_with_a_root_at_the_top_of_the_file_system_or_a_drive() -> None:
    """Containers often run with HOME=/: '~' must not stand for every separator. A drive root (a dataset on
    a stick, E:\\) is matched without its separator, which stays after the label."""
    anchor = Path(Path.cwd().anchor)
    text = f"a / b, {anchor}data{os.sep}x"
    shown = redact_paths(text, {"~": anchor})
    if os.name == "nt":
        assert shown == f"a / b, ~{os.sep}data{os.sep}x"
    else:
        assert shown == text


def test_home_folder_is_none_when_it_cannot_be_determined_or_is_the_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_home() -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", no_home)
    assert safety.home_folder() is None
    monkeypatch.setattr(Path, "home", lambda: Path(Path.cwd().anchor))
    assert safety.home_folder() is None
    monkeypatch.setattr(Path, "home", lambda: Path.cwd() / "someone")
    assert safety.home_folder() == Path.cwd() / "someone"


def test_identity_names_are_the_login_and_the_computer_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USERNAME", "ngtester")
    monkeypatch.setenv("COMPUTERNAME", "NG-LAB-PC")
    monkeypatch.setattr(safety.getpass, "getuser", lambda: "ab")  # too short to search: no word of its own
    monkeypatch.setattr(safety.socket, "gethostname", lambda: "ng-lab-pc.example.org")
    names = safety.identity_names()
    assert "ngtester" in names["<user>"] and "ab" not in names["<user>"]
    assert {"ng-lab-pc.example.org", "ng-lab-pc"} <= {name.casefold() for name in names["<host>"]}
    monkeypatch.setattr(safety.socket, "gethostname", lambda: "neurogrid")  # the product, not a person
    assert "neurogrid" not in safety.identity_names()["<host>"]

    def fails() -> str:
        raise OSError("no login name")

    monkeypatch.setattr(safety.getpass, "getuser", fails)
    monkeypatch.setattr(safety.socket, "gethostname", fails)
    assert "ngtester" in safety.identity_names()["<user>"]  # never an error in the output filter


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


def test_work_folder_of_a_killed_run_is_removed_at_the_next_start(tmp_path: Path) -> None:
    """A-54 "deleted in finally and at the next start": a run killed while it works (no finally runs) leaves
    its work folder with dataset-derived files; the next run in the same base removes it, but never the
    folder of a run that is still going (its lock file is locked by that process). The lock file lies inside
    the work folder, so nothing but the work folder appears next to the output (A-82 leaves it out)."""
    base = tmp_path / "out"
    with holding_process(HOLD_WORK_FOLDER, str(base)) as (process, held):
        assert held.parent == base and held.name.startswith(safety.RUN_PREFIX)
        assert sorted(p.name for p in held.iterdir()) == [WORK_LOCK, "validator"]
        with work_directory(base) as mine:  # the other run is still going
            assert (held / "validator" / "validator.json").is_file() and mine != held
            assert sorted(p.name for p in base.iterdir()) == sorted([held.name, mine.name])
            assert [p.name for p in mine.iterdir()] == [WORK_LOCK]
        assert not mine.exists() and (held / "validator" / "validator.json").is_file()
        process.kill()
        process.wait()
        wait_released(held / WORK_LOCK)
        assert (held / "validator" / "validator.json").is_file()  # the killed run removed nothing
        assert (held / WORK_LOCK).read_bytes() == WORK_MARK
        with work_directory(base) as mine:
            assert not held.exists() and [p.name for p in base.iterdir()] == [mine.name]
    assert list(base.iterdir()) == []


def test_next_start_leaves_alone_what_is_not_a_leftover(tmp_path: Path) -> None:
    """Only a folder whose lock file holds the mark and is no longer locked counts: a folder with the prefix
    and no lock file (a user's own folder, or a run killed before it made its lock file: empty), a lock
    file without the mark (a run between creating and locking it, or one on a file system without locks)
    or with other content, a name that tempfile.mkdtemp does not make, another prefix and a file stay."""
    entries = {
        "run-abcdefgh": None,  # no lock file
        "run-ijklmnop": b"",  # not locked yet
        "run-qrstuvwx": b"someone else's lock\n",
        "run-abcdefghi": WORK_MARK,  # nine characters: not made by mkdtemp
        "ng-pdf-abcdefgh": WORK_MARK,  # another prefix
        "run-12345678": WORK_MARK,  # a leftover
    }
    for name, lock in entries.items():
        (tmp_path / name / "sub").mkdir(parents=True)
        (tmp_path / name / "sub" / "keep.txt").write_text(name, encoding="utf-8")
        if lock is not None:
            (tmp_path / name / WORK_LOCK).write_bytes(lock)
    (tmp_path / "run-file0000").write_text("a file, not a folder", encoding="utf-8")
    before = sorted(p.name for p in tmp_path.iterdir())
    remove_leftovers(tmp_path, safety.RUN_PREFIX)
    assert sorted(p.name for p in tmp_path.iterdir()) == [name for name in before if name != "run-12345678"]
    for name in entries.keys() - {"run-12345678"}:
        assert (tmp_path / name / "sub" / "keep.txt").read_text(encoding="utf-8") == name
    assert (tmp_path / "run-file0000").read_text(encoding="utf-8") == "a file, not a folder"
    remove_leftovers(tmp_path / "missing", safety.RUN_PREFIX)  # never fails the run


def test_next_start_never_follows_a_link(tmp_path: Path) -> None:
    """A link named like a work folder is left alone, and a link inside a leftover is removed, not
    followed."""
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / WORK_LOCK).write_bytes(WORK_MARK)
    (target / "keep.txt").write_text("not NeuroGrid's", encoding="utf-8")
    base = tmp_path / "base"
    base.mkdir()
    dir_link(base / "run-linked00", target)
    (base / "run-12345678").mkdir()
    (base / "run-12345678" / WORK_LOCK).write_bytes(WORK_MARK)
    dir_link(base / "run-12345678" / "link", target)
    remove_leftovers(base, safety.RUN_PREFIX)
    assert sorted(p.name for p in target.iterdir()) == ["keep.txt", WORK_LOCK]
    assert (target / "keep.txt").read_text(encoding="utf-8") == "not NeuroGrid's"
    assert [p.name for p in base.iterdir()] == ["run-linked00"]


def test_own_work_folders_are_never_leftovers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A file system that lets a second lock of the same process through (Linux emulates flock on NFS
    with record locks) still never makes a run remove its own folder."""
    with work_directory(tmp_path) as first:
        (first / "in use.txt").write_text("x", encoding="utf-8")
        monkeypatch.setattr(safety, "_lock", lambda handle, *, wait: True)
        with work_directory(tmp_path) as second:
            assert (first / "in use.txt").is_file() and second.is_dir()
        assert (first / "in use.txt").is_file() and not second.exists()
    assert list(tmp_path.iterdir()) == []


def test_work_folder_without_locks_and_one_that_was_not_removed_completely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a file system without locks the lock file gets no mark: the folder is removed at the end, never by
    a later start. A folder its run could not remove completely keeps its lock file (removed last), so the
    next start removes the rest."""

    def no_locks(handle: int, *, wait: bool) -> bool:
        raise OSError(38, "locks not supported")

    with monkeypatch.context() as patch:
        patch.setattr(safety, "_lock", no_locks)
        unlocked = WorkFolder.create(tmp_path, safety.RUN_PREFIX)
    assert unlocked.lock.read_bytes() == b""
    unlocked.remove()
    assert list(tmp_path.iterdir()) == []
    folder = WorkFolder.create(tmp_path, safety.RUN_PREFIX)
    (folder.path / "sub").mkdir()
    (folder.path / "sub" / "left.txt").write_text("x", encoding="utf-8")
    (folder.path / "gone.txt").write_text("x", encoding="utf-8")
    with monkeypatch.context() as patch:
        patch.setattr(safety.shutil, "rmtree", lambda path, ignore_errors=False: None)
        folder.remove()
    assert sorted(p.name for p in folder.path.iterdir()) == [WORK_LOCK, "sub"]
    assert folder.lock.read_bytes() == WORK_MARK
    with work_directory(tmp_path) as mine:
        assert not folder.path.exists() and mine.is_dir()
    assert list(tmp_path.iterdir()) == []
