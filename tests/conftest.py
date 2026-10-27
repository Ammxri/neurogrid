from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from neurogrid.kernel import netguard

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"
TOOLS = Path(__file__).parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))  # lets tests reuse the fixture writer in tools/gen_fixtures.py
AS_OF = date(2026, 10, 11)
# Raw folders must document the EEG-BIDS required fields in neurogrid.toml (M02-01, A-03, A-05). Tests whose
# subject is something else use this configuration (also used by CI) so that only their subject decides the
# exit code.
DOCUMENTED_TOML = (FIXTURES.parent / "documented.toml").read_text(encoding="utf-8")
# The browser's own work folder never follows pytest's folder (kernel.pdf.browser_work, P2). The documentation
# site the browser tests open as file:// URLs does: on Windows such a page no longer loads once its path
# passes 260 characters (measured with a 232-character --basetemp: ERR_FILE_NOT_FOUND), so the site is built
# below one short folder of the system's temporary folder instead (browser_root).
BROWSER_ROOT_LIMIT = 120


def documented_config(folder: Path, extra: str = "", name: str = "documented.toml") -> Path:
    """A neurogrid.toml in ``folder`` that documents the required metadata, plus ``extra`` lines."""
    path = folder / name
    path.write_text(DOCUMENTED_TOML + extra, encoding="utf-8")
    return path


@pytest.fixture(scope="session", autouse=True)
def _offline() -> None:
    """Every test runs with the network guard that NeuroGrid installs at start-up (A-49)."""
    netguard.install()


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def pdf_shell() -> object:
    """The installed PDF browser (kernel.pdf.locate_shell, the only way the project starts a browser),
    located once per session from the environment the tests start with.

    Without it, tests marked ``pdf`` (and fixtures that request this one) are skipped with the reason,
    unless NEUROGRID_REQUIRE_PDF=1 (CI and the final local run): then a missing browser fails them."""
    from neurogrid.kernel.errors import PdfError
    from neurogrid.kernel.pdf import locate_shell

    try:
        return locate_shell(os.environ)
    except PdfError as exc:
        reason = (
            f"PDF browser not available ({exc.message_key}); install it with tools/install_pdf_browser.py"
        )
        if os.environ.get("NEUROGRID_REQUIRE_PDF") == "1":
            pytest.fail(reason)
        pytest.skip(reason)


@pytest.fixture(scope="session")
def browser_root() -> Iterator[Path]:
    """The session's folder directly below the system's temporary folder for what the browser tests open
    as file:// URLs (independent of --basetemp, BROWSER_ROOT_LIMIT), removed at the end."""
    root = Path(tempfile.mkdtemp(prefix="ngpdf-"))
    try:
        assert len(str(root)) <= BROWSER_ROOT_LIMIT, f"temporary folder too long for the PDF tests: {root}"
        yield root
    finally:
        shutil.rmtree(root)


@pytest.fixture(autouse=True)
def _pdf_marker(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("pdf") is not None:
        request.getfixturevalue("pdf_shell")


def dir_link(link: Path, target: Path) -> None:
    """A directory link: a symlink where permitted, else a Windows junction (needs no extra rights)."""
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        pass
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
        return
    pytest.skip("directory links not permitted on this system")


LOCALE_ENCODINGS = {"Linux": "utf-8", "Western Windows": "cp1252", "Chinese Windows": "cp936"}


@contextlib.contextmanager
def locale_encoding(codec: str) -> Iterator[None]:
    """Python's default text encoding as the locale of another system sets it: a text-mode ``open`` without
    an encoding decodes with ``codec`` (UTF-8 on a Linux runner with C.UTF-8, the ANSI code page on Windows).
    Python reads the locale's encoding in C, so the built-in ``open`` is replaced for the block."""
    import builtins

    real_open = builtins.open

    def system_open(
        file: Any, mode: str = "r", buffering: int = -1, encoding: Any = None, *rest: Any, **kw: Any
    ) -> Any:
        if "b" not in mode and encoding is None:
            encoding = codec
        return real_open(file, mode, buffering, encoding, *rest, **kw)

    builtins.open = system_open
    try:
        yield
    finally:
        builtins.open = real_open


def _clear_codec_lookup_cache() -> None:
    """codecs.unregister clears the registry's cache of looked-up codecs (Python 3.10+)."""
    import codecs

    def nothing(_name: str) -> None:
        return None

    codecs.register(nothing)
    codecs.unregister(nothing)


@contextlib.contextmanager
def linux_codecs() -> Iterator[None]:
    """The codec registry of Linux: there Python knows no codec "ANSI" (or "dbcs"). On Windows both are
    aliases of mbcs, the system's ANSI code page; the aliases and the lookup caches are removed for the block.
    """
    import encodings
    import encodings.aliases

    aliases = encodings.aliases.aliases
    removed = {name: aliases.pop(name) for name in ("ansi", "dbcs") if name in aliases}
    cache = encodings._cache  # type: ignore[attr-defined]
    saved = dict(cache)
    cache.clear()
    _clear_codec_lookup_cache()
    try:
        yield
    finally:
        aliases.update(removed)
        cache.clear()
        cache.update(saved)
        _clear_codec_lookup_cache()


@contextlib.contextmanager
def linux_text_system() -> Iterator[None]:
    """The locale encoding (UTF-8) and the codec registry of the Linux runner."""
    with locale_encoding(LOCALE_ENCODINGS["Linux"]), linux_codecs():
        yield


@contextlib.contextmanager
def short_folder(prefix: str) -> Iterator[Path]:
    """A new private folder in the computer's temporary folder, removed afterwards: a short path that does
    not grow with pytest's basetemp (the PDF browser cannot use long paths on Windows, P2)."""
    folder = Path(tempfile.mkdtemp(prefix=prefix)).absolute()
    try:
        yield folder
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def folder_content(folder: Path) -> dict[str, tuple[object, ...]]:
    """Everything a run could change below ``folder``: each folder's entries, size and modification time,
    each file's size, modification time and SHA-256 (byte for byte).

    Each folder is listed before its own size is read. Windows reports a folder's size from NTFS's cache: 0
    while nothing has read the folder for a while, the size of its index once something did (measured: a
    snapshot that read the size of chrome-headless-shell-win64/hyphen-data before listing it saw 0, the
    next one 12288, with nothing written in between; read after the listing it is the index size both
    times). Creating or removing an entry changes the folder's modification time, also if it is undone."""
    content: dict[str, tuple[object, ...]] = {}
    for path, _folders, files in os.walk(folder):
        here = Path(path)
        names = tuple(sorted(entry.name for entry in here.iterdir()))
        info = here.stat()
        content[here.relative_to(folder).as_posix() + "/"] = (names, info.st_size, info.st_mtime_ns)
        for name in files:
            file = here / name
            info = file.stat()
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            content[file.relative_to(folder).as_posix()] = (info.st_size, info.st_mtime_ns, digest)
    return content


@contextlib.contextmanager
def fresh_shell(shell: Any) -> Iterator[Any]:
    """A fresh installation of the PDF browser for one test: the installed shell (verified tree) copied into
    a new short folder that no browser has run from, located like the product does; removed afterwards.
    Its first print is the first print after an installation."""
    from neurogrid.kernel.pdf import ENV_BROWSER_DIR, locate_shell

    with short_folder("ng-shell-") as folder:
        shutil.copytree(shell.shell_dir, folder / shell.shell_dir.name)
        yield locate_shell({ENV_BROWSER_DIR: str(folder)})


def long_path(base: Path, length: int) -> Path:
    """A path below ``base`` of ``length`` characters (at least one 10-character folder more), in folders of
    at most 40 characters."""
    path = str(base)
    while len(path) < length - 1 or path == str(base):
        room = length - len(path) - 1
        path += os.sep + "d" * max(min(40, room if room != 41 else 39), 10)
    return Path(path)


@contextlib.contextmanager
def holding_process(code: str, *args: str, **env: str) -> Iterator[tuple[subprocess.Popen[str], Path]]:
    """Another NeuroGrid process that runs ``code`` (it prints the path of the work folder it holds, then
    waits for its input) until it is killed: hard, no finally runs (A-54). Yields the process and the path."""
    process = subprocess.Popen(
        [sys.executable, "-c", code, *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", **env},
    )
    try:
        assert process.stdout is not None
        yield process, Path(process.stdout.readline().strip())
    finally:
        process.kill()
        process.wait()
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                stream.close()


def wait_released(lock: Path) -> None:
    """Windows releases the locks of a killed process shortly after it ended (measured: up to about 6 ms
    after wait() returned); taking the lock with waiting (msvcrt.LK_LOCK tries again every second, up to 10
    times; flock blocks) and closing it again waits for that."""
    from neurogrid.kernel import safety

    handle = os.open(lock, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        assert safety._lock(handle, wait=True)
    finally:
        os.close(handle)
