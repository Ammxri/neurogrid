"""PDF printing of reports (TECH-07, A-26, A-27, A-49): Playwright 1.63.0 drives the Chrome Headless Shell
revision 1243 from NeuroGrid's own folder; every PDF passes the QA gate before anything is written.

- **Browser:** only the shell installed by tools/install_pdf_browser.py into NeuroGrid's folder
  (``NEUROGRID_PDF_BROWSER_DIR`` or the default below). Never Playwright's own browser folder, never Edge or
  a system Chrome, never a browser channel or a PATH lookup.
- **Network:** fixed Chromium flags (no background networking, component updates, crash uploads, pings,
  proxy auto-detection or name resolution); JavaScript off, offline context, service workers blocked; a
  router lets only the printed file through and aborts every other request; the requests are counted and
  the gate requires none but the file. Data URIs (fonts) never reach the network stack. The HTML carries
  the Content-Security-Policy of A-08, checked before printing.
- **Python process:** Playwright's synchronous API runs an asyncio loop in this process; on Windows its
  proactor creates one loopback socket pair. The network guard (kernel/netguard.py) allows loopback only
  and still blocks every other connection, datagram and name resolution (A-49). The driver starts without
  the caller's node, debug and Playwright variables; the browser gets a complete, minimal environment.
- **Files (A-54):** temporary files, profile, logs and the HTML files it prints in a private work folder in
  the computer's temporary folder (browser_work), never below ``--out``: Chromium cannot create profile paths
  longer than Windows allows (measured with the merged state: ``--out`` of 195 characters left a debug.log
  with local paths in the current folder, 210 characters ended in pdf.launch_failed). A temporary folder
  with a path too long for the profile ends with exit 2 and its own hint before anything is rendered.
  Driver and browser run with the work folder as their current folder (a debug.log Chromium writes there
  goes with it); the GPU runs inside the browser process, and a debug.log that a child process appends
  next to the executable is undone. What a run could not remove because it was killed is removed at the
  next start of a browser run: its work folder (its lock file, kernel.safety.remove_leftovers) and
  a debug.log next to the executable (also one an older version left).
- **Determinism (A-11):** untagged PDF (tagged output embeds DOM node IDs), fixed context (locale of the
  report language, time zone, colour scheme), CreationDate/ModDate set to the reference date by a
  same-length byte replacement of the two fields Chromium writes; the result is byte-identical for the same
  input.
- **QA gate:** the fonts it accepts are passed in by the product (PdfExpect.fonts, the PostScript names
  of the report fonts); the kernel names no font itself (A-23).
- **Metadata (A-51):** /Info holds exactly Title (the HTML title), Creator, Producer, CreationDate and
  ModDate; no XMP.

Playwright is imported only when a browser is started, so HTML reports never load it.
"""

from __future__ import annotations

import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from importlib import metadata
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any

import pypdf
from pypdf.errors import PyPdfError
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, PdfObject

from neurogrid.kernel.errors import InputError, PdfError, UnsafePathError
from neurogrid.kernel.fonts import is_radical_or_compat
from neurogrid.kernel.safety import WorkFolder, check_operator_path, create_temporary, remove_leftovers

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Playwright, Request, Route

PLAYWRIGHT_VERSION = "1.63.0"
SHELL_REVISION = "1243"
SHELL_BROWSER_VERSION = "153.0.8010.12"
SHELL_DIRNAME = f"chrome-headless-shell-{SHELL_REVISION}"
RECORD_NAME = "neurogrid-install.json"
ENV_BROWSER_DIR = "NEUROGRID_PDF_BROWSER_DIR"
EXECUTABLES = {
    "win64": "chrome-headless-shell-win64/chrome-headless-shell.exe",
    "linux64": "chrome-headless-shell-linux64/chrome-headless-shell",
}
# A-49: fixed in code, not left to Playwright's defaults. --proxy-server=direct:// also stops the proxy
# auto-detection (WPAD) the shell otherwise configures; the resolver rule makes every name unresolvable.
CHROMIUM_FLAGS = (
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-breakpad",
    "--no-pings",
    "--disable-domain-reliability",
    "--disable-sync",
    "--proxy-server=direct://",
    "--host-resolver-rules=MAP * ~NOTFOUND",
)
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:"
# The browser context's locale per printed document (zh-CN for the Chinese report, en-US otherwise). The
# HTML names its language and JavaScript is off: the locale is not observable in the PDF (tested: each
# report gives identical bytes in either locale).
LOCALES = frozenset({"zh-CN", "en-US"})
LAUNCH_TIMEOUT_MS = 60_000
# Context default: opening the page and loading the file. Page.pdf itself runs without a timeout
# (Playwright 1.63.0 sends no timeout for it), so a large report never ends in pdf.timeout while printing.
PAGE_TIMEOUT_MS = 300_000
# The driver (node) and Playwright's Python side read these: node options and module paths, debug output,
# PLAYWRIGHT_NODEJS_PATH (another node binary), PLAYWRIGHT_*/PW_* switches that change the browser's flags or
# checks. None of them may reach a NeuroGrid run.
DRIVER_ENV_REMOVED = ("NODE_OPTIONS", "NODE_PATH", "DEBUG", "DEBUG_FILE", "DEBUGP", "PWDEBUG")
DRIVER_ENV_PREFIXES = ("PLAYWRIGHT_", "PW_")
# On Windows the shell's child processes do not use the log file of --log-file: an error is appended to
# debug.log next to the executable, i.e. in NeuroGrid's browser folder (measured: the GPU process under load).
# The GPU runs as a thread of the browser process instead; a debug.log a run causes is undone (A-51, A-54).
# Where a process cannot open its log file, Chromium's logging falls back to debug.log in its current folder
# (measured with revision 1243: from a work folder of 197 characters on, the profile paths pass 260
# characters). The browser inherits the driver's current folder, so the driver starts in the work folder: that
# debug.log is removed with it and never lands in the user's current folder (driver_environment).
IN_PROCESS_GPU = "--in-process-gpu"
CHILD_LOG = "debug.log"
# The browser's work folder lies in the computer's temporary folder (tempfile.gettempdir(): TMPDIR, TEMP or
# TMP), independent of --out. Below it the driver's profile reaches 96 characters (measured, revision 1243,
# both reports printed: playwright_chromiumdev_profile-XXXXXX\Default\blob_storage\<uuid>); the shell is not
# long-path aware. Measured with work folders of exact lengths: up to 160 characters every print was clean;
# from 170 Chromium could not create its disk cache folders and wrote the errors, with local paths, to
# debug.log (next to the executable, and into its current folder: at 208 characters with the caller's
# current folder there); at 215 characters the launch failed. The limit leaves 60 characters reserve; it
# applies on Windows only (Linux has no such path limit).
WORK_PREFIX = "ng-pdf-"
WORK_PATH_LIMIT = 100
# the temporary folder itself: the work folder adds a separator, the prefix and tempfile.mkdtemp's 8 random
# characters
TEMP_PATH_LIMIT = WORK_PATH_LIMIT - 1 - len(WORK_PREFIX) - 8
LINUX_PACKAGES = Path(__file__).with_name("pdf_linux_packages.json")
BUNDLE_MARKER = "BUNDLE.json"  # in the prefix of an offline-bundle installation (next to venv/, python/)
# an embedded font subset: six capital letters, "+", the PostScript name of the face
_SUBSET_FONT = re.compile(r"^/?[A-Z]{6}\+(.+)$")
INFO_KEYS = frozenset({"/Title", "/Creator", "/Producer", "/CreationDate", "/ModDate"})
_DATE_FIELD = re.compile(rb"/(CreationDate|ModDate) ?\(D:\d{14}[+-]\d{2}'\d{2}'\)")
_HEAD_END = re.compile(r"</head\s*>", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ShellInstall:
    """An installed shell: NeuroGrid's browser folder, the revision folder and the executable in it."""

    folder: Path
    shell_dir: Path
    executable: Path
    platform: str


@dataclass(frozen=True)
class PdfMeta:
    """What the PDF's metadata must say: the title of the HTML document and the reference date."""

    title: str
    as_of: date


@dataclass(frozen=True)
class PdfExpect:
    """What the QA gate requires: the metadata, the fonts (PostScript names of the faces whose subsets the
    PDF may embed, passed in by the product), phrases on every page and phrases somewhere in the text."""

    meta: PdfMeta
    fonts: tuple[str, ...]
    every_page: tuple[str, ...] = ()
    once: tuple[str, ...] = ()


@dataclass
class RequestLog:
    """Requests of one printed page: seen, other than the printed file, aborted by the router, failed."""

    seen: int = 0
    unexpected: int = 0
    aborted: int = 0
    failed: int = 0


@dataclass(frozen=True)
class PrintedPdf:
    data: bytes
    log: RequestLog = field(default_factory=RequestLog)


# --- locating the shell ------------------------------------------------------------------------------


def shell_platform() -> str:
    machine = platform.machine().lower()
    if sys.platform == "win32" and machine in ("amd64", "x86_64"):
        return "win64"
    if sys.platform.startswith("linux") and machine in ("x86_64", "amd64"):
        return "linux64"
    raise PdfError("pdf.platform_unsupported", platform=f"{sys.platform}/{platform.machine()}")


def default_browser_dir(environ: Mapping[str, str], *, windows: bool | None = None) -> Path:
    """Windows: %LOCALAPPDATA%\\NeuroGrid\\pdf-browser; Linux: ${XDG_DATA_HOME:-~/.local/share}/neurogrid/
    pdf-browser (a relative XDG_DATA_HOME is ignored, as the XDG specification says)."""
    if windows if windows is not None else os.name == "nt":
        base = environ.get("LOCALAPPDATA", "")
        root = Path(base) if base and Path(base).is_absolute() else Path.home() / "AppData" / "Local"
        return root / "NeuroGrid" / "pdf-browser"
    data = environ.get("XDG_DATA_HOME", "")
    root = Path(data) if data and Path(data).is_absolute() else Path.home() / ".local" / "share"
    return root / "neurogrid" / "pdf-browser"


def browser_dir(environ: Mapping[str, str]) -> Path:
    """NEUROGRID_PDF_BROWSER_DIR (an absolute local folder; set but empty is an error) or the default."""
    value = environ.get(ENV_BROWSER_DIR)
    if value is None:
        return default_browser_dir(environ)
    try:
        path = check_operator_path(value.strip())
    except UnsafePathError:
        raise PdfError("pdf.browser_dir_invalid", variable=ENV_BROWSER_DIR) from None
    if not path.is_absolute():
        raise PdfError("pdf.browser_dir_invalid", variable=ENV_BROWSER_DIR)
    return path


def _quoted(path: Path) -> str:
    text = str(path)
    return f'"{text}"' if " " in text else text


def install_hint() -> tuple[str, dict[str, object]]:
    """How to install the shell, by installation type: an offline bundle (marker file in its prefix, the
    folder above the venv) gets the command with its own interpreter and script; every other installation
    (PyPI, source) gets the documentation page, which names the installer's release address and SHA-256."""
    prefix = Path(sys.prefix).parent
    script = prefix / "tools" / "install_pdf_browser.py"
    python = prefix / "python" / ("python.exe" if os.name == "nt" else "bin/python3.12")
    if (prefix / BUNDLE_MARKER).is_file() and script.is_file() and python.is_file():
        return "pdf.install.command", {"command": f"{_quoted(python)} {_quoted(script)}"}
    return "pdf.install.docs", {}


def locate_shell(environ: Mapping[str, str]) -> ShellInstall:
    """The installed shell, or PdfError (exit 2) with the install command as hint."""
    folder = browser_dir(environ)
    platform_name = shell_platform()
    shell_dir = folder / SHELL_DIRNAME
    executable = shell_dir / EXECUTABLES[platform_name]
    if not shell_dir.is_dir():
        raise PdfError("pdf.shell_missing", folder=folder, revision=SHELL_REVISION, hint=install_hint())
    try:
        record = json.loads((shell_dir / RECORD_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = None
    if not isinstance(record, dict) or not executable.is_file():
        raise PdfError("pdf.shell_incomplete", folder=shell_dir, hint=install_hint())
    if (
        record.get("revision") != SHELL_REVISION
        or record.get("platform") != platform_name
        or record.get("executable") != EXECUTABLES[platform_name]
    ):
        found = f"{record.get('revision')}/{record.get('platform')}"[:40]
        raise PdfError("pdf.shell_revision", found=found, required=SHELL_REVISION, hint=install_hint())
    return ShellInstall(folder=folder, shell_dir=shell_dir, executable=executable, platform=platform_name)


# --- start check -------------------------------------------------------------------------------------


def parse_ldd(text: str) -> tuple[list[str], list[str]]:
    """Libraries ldd reports as 'not found' and GLIBC versions it reports as missing."""
    missing = re.findall(r"^\s*(\S+) => not found\s*$", text, flags=re.MULTILINE)
    glibc = re.findall(r"version .GLIBC_([0-9.]+). not found", text)
    return sorted(set(missing)), sorted(set(glibc), key=lambda v: tuple(int(p) for p in v.split(".")))


def linux_packages() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(LINUX_PACKAGES.read_text(encoding="utf-8"))
    return data


def linux_distribution(os_release: Path = Path("/etc/os-release")) -> str | None:
    """The name in pdf_linux_packages.json that /etc/os-release identifies, or None."""
    try:
        text = os_release.read_text(encoding="utf-8")
    except OSError:
        return None
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key.strip()] = value.strip().strip("\"'")
    for name, entry in linux_packages()["distributions"].items():
        wanted = entry["os_release"]
        if all(fields.get(key) == value for key, value in wanted.items()):
            return str(name)
    return None


def missing_libraries_error(libraries: Sequence[str], distribution: str | None) -> PdfError:
    """Exit 2 with the missing libraries and the apt packages that provide them (A-26)."""
    data = linux_packages()
    name = distribution if distribution in data["distributions"] else str(data["fallback"])
    table: dict[str, str] = data["distributions"][name]["libraries"]
    packages = list(dict.fromkeys(table[lib] for lib in libraries if lib in table))
    if not packages:  # a library Playwright does not list: name all packages of the distribution
        packages = list(data["distributions"][name]["packages"])
    key = "pdf.install.apt" if distribution == name else "pdf.install.apt_other"
    return PdfError(
        "pdf.linux_libraries",
        libraries=", ".join(libraries),
        hint=(key, {"distribution": name, "packages": " ".join(packages)}),
    )


def preflight(
    shell: ShellInstall,
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    os_release: Path = Path("/etc/os-release"),
) -> None:
    """Before any rendering: the pinned Playwright, the temporary folder for the browser's work folder
    (work_base) and, on Linux, the shell's system libraries (ldd)."""
    try:
        found = metadata.version("playwright")
    except metadata.PackageNotFoundError:
        found = "none"
    if found != PLAYWRIGHT_VERSION:
        raise PdfError("pdf.playwright_version", found=found, required=PLAYWRIGHT_VERSION)
    work_base()
    if shell.platform != "linux64":
        return
    ldd = shutil.which("ldd")
    if ldd is None:  # no ldd (unusual): a failing launch is still reported as exit 2
        return
    result = run(
        [ldd, str(shell.executable)],
        env={"LC_ALL": "C", "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    missing, glibc = parse_ldd(f"{result.stdout}\n{result.stderr}")
    if glibc:
        raise PdfError("pdf.glibc_too_old", required=glibc[-1])
    if missing:
        raise missing_libraries_error(missing, linux_distribution(os_release))


# --- printing ----------------------------------------------------------------------------------------


class _HeadReader(HTMLParser):
    """The <title> texts and the Content-Security-Policy values of <meta http-equiv> elements."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.policies: list[str] = []
        self.titles: list[list[str]] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta":
            values = {name.lower(): value or "" for name, value in attrs}
            if values.get("http-equiv", "").strip().lower() == "content-security-policy":
                self.policies.append(values.get("content", ""))
        elif tag == "title":
            self._in_title = True
            self.titles.append([])

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.titles[-1].append(data)


def _read_head(document: str) -> _HeadReader:
    """Only the head is read: the CSP applies from there, and the body may hold SVG <title> elements."""
    end = _HEAD_END.search(document)
    reader = _HeadReader()
    reader.feed(document[: end.end()] if end else document)
    reader.close()
    return reader


def html_title(document: str) -> str:
    """The document title as the browser uses it for the PDF: the first <title>, entities decoded,
    whitespace collapsed."""
    titles = _read_head(document).titles
    return _WHITESPACE.sub(" ", "".join(titles[0])).strip() if titles else ""


def has_csp(document: str) -> bool:
    """The document's head declares exactly the Content-Security-Policy of A-08 (attribute order and case
    as HTML allows)."""
    return CSP in _read_head(document).policies


def pdf_date(as_of: date) -> str:
    return f"D:{as_of:%Y%m%d}000000+00'00'"


def set_dates(raw: bytes, as_of: date) -> bytes:
    """CreationDate and ModDate = reference date, by a same-length replacement of the two fields Chromium
    writes (the offsets in the cross-reference table stay valid). Each field must occur exactly once."""
    found = sorted(m.group(1) for m in _DATE_FIELD.finditer(raw))
    if found != [b"CreationDate", b"ModDate"]:
        raise PdfError("pdf.qa_failed", checks="metadata_dates")
    stamp = pdf_date(as_of).encode("ascii")

    def replace(match: re.Match[bytes]) -> bytes:
        old = match.group(0)
        new = old[: old.index(b"(")] + b"(" + stamp + b")"
        if len(new) != len(old):
            raise PdfError("pdf.qa_failed", checks="metadata_dates")
        return new

    return _DATE_FIELD.sub(replace, raw)


def browser_environment(work: Path, *, windows: bool | None = None) -> dict[str, str]:
    """The complete environment of the shell: temporary and profile folders inside the work folder."""
    env = {"TMP": str(work), "TEMP": str(work), "TMPDIR": str(work)}
    if windows if windows is not None else os.name == "nt":
        env["SystemRoot"] = os.environ.get("SystemRoot", r"C:\Windows")
        return env
    for name, sub in (
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "xdg-config"),
        ("XDG_CACHE_HOME", "xdg-cache"),
        ("XDG_DATA_HOME", "xdg-data"),
    ):
        (work / sub).mkdir(parents=True, exist_ok=True)
        env[name] = str(work / sub)
    env["LANG"] = "C.UTF-8"
    return env


def _too_long(length: int, limit: int) -> PdfError:
    return PdfError(
        "pdf.work_path_too_long",
        length=length,
        limit=limit,
        hint=("pdf.temp_hint", {"limit": TEMP_PATH_LIMIT}),
    )


def _unusable() -> PdfError:
    return PdfError("pdf.temp_unusable", hint=("pdf.temp_unusable_hint", {}))


def check_work_path(work: Path, *, windows: bool | None = None) -> None:
    """Windows: a work folder path longer than WORK_PATH_LIMIT characters is refused before the browser
    starts (exit 2, with the hint to choose a shorter temporary folder)."""
    length = len(str(Path(work).absolute()))
    if (windows if windows is not None else os.name == "nt") and length > WORK_PATH_LIMIT:
        raise _too_long(length, WORK_PATH_LIMIT)


def work_base(*, windows: bool | None = None) -> Path:
    """The computer's temporary folder, the base of the browser's work folders: PdfError (exit 2, with
    the hint) when there is no usable one or, on Windows, its path is longer than TEMP_PATH_LIMIT
    characters."""
    try:
        base = Path(tempfile.gettempdir()).absolute()
    except OSError:  # tempfile found no writable folder among TMPDIR, TEMP, TMP and its fallbacks
        raise _unusable() from None
    if (windows if windows is not None else os.name == "nt") and len(str(base)) > TEMP_PATH_LIMIT:
        raise _too_long(len(str(base)), TEMP_PATH_LIMIT)
    return base


@contextmanager
def browser_work(*, windows: bool | None = None) -> Iterator[Path]:
    """A private work folder for one browser run in the computer's temporary folder (work_base),
    independent of the output folder; removed afterwards, also after errors. Work folders of earlier
    browser runs that could not remove theirs (killed, the computer stopped; they hold the printed HTML)
    are removed first (kernel.safety.remove_leftovers, A-54). A temporary folder that cannot be used or
    whose path is too long ends with exit 2 and the hint, before anything is created."""
    base = work_base(windows=windows)
    remove_leftovers(base, WORK_PREFIX)
    try:
        folder = WorkFolder.create(base, WORK_PREFIX)
    except OSError:
        raise _unusable() from None
    try:
        yield folder.path
    finally:
        folder.remove()


def _change_folder(folder: str) -> bool:
    try:
        os.chdir(folder)
    except OSError:
        return False
    return True


@contextmanager
def driver_environment(work: Path) -> Iterator[None]:
    """While Playwright's driver (node) starts: temporary files in the work folder, the work folder as the
    current folder (the driver keeps it and the browser and its child processes inherit it, so a debug.log
    Chromium writes into its current folder lands there), none of the variables that change the driver or
    the browser (DRIVER_ENV_REMOVED, DRIVER_ENV_PREFIXES). Restored right afterwards."""
    removed = [
        name
        for name in os.environ
        if name.upper() in DRIVER_ENV_REMOVED or name.upper().startswith(DRIVER_ENV_PREFIXES)
    ]
    names = ("TMP", "TEMP", "TMPDIR", *DRIVER_ENV_REMOVED, *removed)
    saved = {name: os.environ.get(name) for name in names}
    try:
        previous: str | None = str(Path.cwd())
    except OSError:  # the current folder no longer exists: nothing to return to
        previous = None
    try:
        for name in ("TMP", "TEMP", "TMPDIR"):
            os.environ[name] = str(work)
        for name in (*DRIVER_ENV_REMOVED, *removed):
            os.environ.pop(name, None)
        os.chdir(work)
        yield
    finally:
        # back to the previous folder; if it is gone, out of the work folder so that it can be removed
        for folder in (previous, str(Path(work).absolute().parent)):
            if folder is not None and _change_folder(folder):
                break
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _router(url: str, log: RequestLog) -> Callable[[Route], None]:
    """One parameter on purpose: Playwright calls a handler with two or more parameters as
    (route, request)."""

    def handle(route: Route) -> None:
        if route.request.url == url:
            route.continue_()
        else:
            log.aborted += 1
            route.abort("blockedbyclient")

    return handle


def _counter(url: str, log: RequestLog) -> Callable[[Request], None]:
    def count(request: Request) -> None:
        log.seen += 1
        if request.url != url and not request.url.startswith("data:"):
            log.unexpected += 1

    return count


def _failure(log: RequestLog) -> Callable[[Request], None]:
    def fail(_request: Request) -> None:
        log.failed += 1

    return fail


def launch_arguments(work: Path, extra_flags: Sequence[str] = ()) -> list[str]:
    """The fixed flags, the GPU in the browser process and its log file inside the work folder: the shell
    otherwise writes debug.log next to its executable, i.e. into NeuroGrid's browser folder (A-54)."""
    return [*CHROMIUM_FLAGS, IN_PROCESS_GPU, f"--log-file={work / 'chromium.log'}", *extra_flags]


class _ChildLog:
    """debug.log next to the executable (A-51, A-54). It is never part of the installation
    (install_pdf_browser.py --check fails while it is there) and holds local paths, so one that is there
    at the start is a leftover of a run that could not undo it (killed, or a version that wrote it below a
    long work folder) and is removed. If it cannot be removed (the browser of a run still going holds it
    open), the run remembers its size and cuts back only what it appends."""

    def __init__(self, executable: Path) -> None:
        self.path = executable.parent / CHILD_LOG
        self.known = True
        self.size: int | None = None
        try:
            self.size = self.path.stat().st_size
        except FileNotFoundError:
            return
        except OSError:  # state unknown: leave the file alone
            self.known = False
            return
        try:
            self.path.unlink()
        except FileNotFoundError:
            self.size = None
        except OSError:
            pass
        else:
            self.size = None

    def restore(self) -> None:
        """Remove a debug.log the run created, or cut the lines it appended. Never fails the run."""
        if not self.known:
            return
        try:
            if self.size is None:
                self.path.unlink(missing_ok=True)
            elif self.path.stat().st_size > self.size:
                with self.path.open("r+b") as handle:
                    handle.truncate(self.size)
        except OSError:
            pass


class PdfPrinter:
    """One driver and one browser for several documents (``with browser_work() as work, PdfPrinter(shell,
    work) as printer``). ``work`` holds the driver's temporary files, the profile, the log and the printed
    files; on Windows it must not be longer than WORK_PATH_LIMIT characters.

    Playwright's own error texts are never shown: they contain paths (A-07, A-51); only the type is."""

    def __init__(self, shell: ShellInstall, work: Path, *, extra_flags: Sequence[str] = ()) -> None:
        self.shell = shell
        # absolute: TMP, profile and log paths of driver and browser (on Python 3.11, tempfile.mkdtemp
        # returns a relative folder for a relative --out)
        self.work = Path(work).absolute()
        self.extra_flags = tuple(extra_flags)  # tests only (e.g. a Chromium net-log)
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._child_log: _ChildLog | None = None

    def __enter__(self) -> PdfPrinter:
        from playwright.sync_api import Error, sync_playwright

        check_work_path(self.work)
        self.work.mkdir(parents=True, exist_ok=True)
        environment: dict[str, str | float | bool] = dict(browser_environment(self.work))
        self._child_log = _ChildLog(self.shell.executable)
        try:
            with driver_environment(self.work):
                self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                executable_path=str(self.shell.executable),
                headless=True,
                args=launch_arguments(self.work, self.extra_flags),
                env=environment,
                timeout=LAUNCH_TIMEOUT_MS,
                chromium_sandbox=False,
                handle_sigint=False,
                handle_sigterm=False,
                handle_sighup=False,
            )
        except Error as exc:
            self.close()
            raise _browser_error("pdf.launch_failed", exc, LAUNCH_TIMEOUT_MS) from None
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        from playwright.sync_api import Error

        browser, self._browser = self._browser, None
        driver, self._playwright = self._playwright, None
        child_log, self._child_log = self._child_log, None
        if browser is not None:
            try:
                browser.close()
            except Error:
                pass
        if driver is not None:
            try:
                driver.stop()
            except Error:
                pass
        if child_log is not None:  # after the last browser process has ended
            child_log.restore()

    def print(self, html_path: Path, meta: PdfMeta, *, locale: str = "en-US") -> PrintedPdf:
        """Print one HTML file (A4, CSS page size, backgrounds, untagged) with dates set to ``meta.as_of``;
        ``locale`` is the browser context's locale (one of LOCALES)."""
        from playwright.sync_api import Error

        if locale not in LOCALES:
            raise ValueError(f"locale must be one of {sorted(LOCALES)}")
        if self._browser is None:
            raise RuntimeError("PdfPrinter is not started")
        try:
            document = html_path.read_text(encoding="utf-8")
        except OSError:
            raise InputError("output.not_writable") from None
        if not has_csp(document):
            raise PdfError("pdf.qa_failed", checks="html_csp_missing")
        url = html_path.resolve().as_uri()
        log = RequestLog()
        try:
            context = self._browser.new_context(
                java_script_enabled=False,
                offline=True,
                service_workers="block",
                accept_downloads=False,
                locale=locale,
                timezone_id="UTC",
                color_scheme="light",
            )
            try:
                context.set_default_timeout(PAGE_TIMEOUT_MS)
                context.route("**/*", _router(url, log))
                page = context.new_page()
                page.on("request", _counter(url, log))
                page.on("requestfailed", _failure(log))
                page.goto(url, wait_until="load")
                raw = page.pdf(
                    format="A4",
                    prefer_css_page_size=True,
                    print_background=True,
                    display_header_footer=False,
                    tagged=False,
                    outline=False,
                )
            finally:
                context.close()
        except Error as exc:
            raise _browser_error("pdf.print_failed", exc, PAGE_TIMEOUT_MS) from None
        return PrintedPdf(data=set_dates(raw, meta.as_of), log=log)


def _browser_error(key: str, exc: Exception, timeout_ms: int) -> PdfError:
    if type(exc).__name__ == "TimeoutError":
        return PdfError("pdf.timeout", seconds=timeout_ms // 1000)
    return PdfError(key, type=type(exc).__name__)


# --- QA gate -----------------------------------------------------------------------------------------


def _resolve(value: PdfObject | None) -> Any:
    return value.get_object() if isinstance(value, IndirectObject) else value


def _font_violations(font: DictionaryObject, allowed: frozenset[str]) -> set[str]:
    found: set[str] = set()
    subtype = _resolve(font.get("/Subtype"))
    if subtype == "/Type3":
        return {"font_type3"}
    if subtype != "/Type0":
        return {"font_not_cid_truetype"}
    subset_font = _SUBSET_FONT.match(str(_resolve(font.get("/BaseFont"))))
    if subset_font is None or subset_font.group(1) not in allowed:
        found.add("font_not_report_font")
    if "/ToUnicode" not in font:
        found.add("font_no_tounicode")
    descendants = _resolve(font.get("/DescendantFonts"))
    descendant = _resolve(descendants[0]) if isinstance(descendants, ArrayObject) and descendants else None
    descriptor = (
        _resolve(descendant.get("/FontDescriptor")) if isinstance(descendant, DictionaryObject) else None
    )
    if (
        not isinstance(descendant, DictionaryObject)
        or _resolve(descendant.get("/Subtype")) != "/CIDFontType2"
        or not isinstance(descriptor, DictionaryObject)
        or "/FontFile2" not in descriptor
        or "/FontFile" in descriptor
        or "/FontFile3" in descriptor
    ):
        found.add("font_not_cid_truetype")
    return found


def _resource_violations(resources: Any, seen: set[int], allowed: frozenset[str]) -> set[str]:
    """Fonts of a resource dictionary and, recursively, of its form XObjects."""
    resources = _resolve(resources)
    if not isinstance(resources, DictionaryObject) or id(resources) in seen:
        return set()
    seen.add(id(resources))
    found: set[str] = set()
    fonts = _resolve(resources.get("/Font"))
    if isinstance(fonts, DictionaryObject):
        for ref in fonts.values():
            font = _resolve(ref)
            if isinstance(font, DictionaryObject):
                found |= _font_violations(font, allowed)
    xobjects = _resolve(resources.get("/XObject"))
    if isinstance(xobjects, DictionaryObject):
        for ref in xobjects.values():
            xobject = _resolve(ref)
            if isinstance(xobject, DictionaryObject) and xobject.get("/Subtype") == "/Form":
                found |= _resource_violations(xobject.get("/Resources"), seen, allowed)
    return found


def _squeeze(text: str) -> str:
    return _WHITESPACE.sub("", text)


def pdf_text(data: bytes) -> list[str]:
    """The extracted text of every page (pypdf)."""
    return [page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(data)).pages]


def qa_gate(pdf: Path | bytes, expect: PdfExpect, *, log: RequestLog | None = None) -> list[str]:
    """The PDF QA gate (KONZEPT 1.6, A-27): sorted violation codes, empty when the PDF passes.

    Fonts: only embedded Type0/CIDFontType2 subsets of ``expect.fonts`` with ToUnicode, no Type3, no system
    font. Text: no radical or compatibility code point; ``every_page`` phrases on each page, ``once``
    phrases somewhere (whitespace ignored, cells wrap). Metadata: exactly the five /Info keys, the title and
    the reference date, no XMP. Requests: none but the printed file, none aborted or failed."""
    data = pdf.read_bytes() if isinstance(pdf, Path) else pdf
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = list(reader.pages)
        texts = [page.extract_text() or "" for page in pages]
        info = reader.metadata
        root = _resolve(reader.trailer.get("/Root"))
    except (PyPdfError, ValueError, KeyError, TypeError):
        return ["unreadable"]
    violations: set[str] = set()
    if not pages:
        violations.add("no_pages")
    seen: set[int] = set()
    allowed = frozenset(expect.fonts)
    for page in pages:
        violations |= _resource_violations(page.get("/Resources"), seen, allowed)
    if any(is_radical_or_compat(ord(ch)) for text in texts for ch in text):
        violations.add("radical_codepoint")
    squeezed = [_squeeze(text) for text in texts]
    for phrase in expect.every_page:
        if any(_squeeze(phrase) not in text for text in squeezed):
            violations.add("phrase_missing_on_page")
    whole = "".join(squeezed)
    if any(_squeeze(phrase) not in whole for phrase in expect.once):
        violations.add("phrase_missing")
    keys = set(info.keys()) if info is not None else set()
    if keys != INFO_KEYS:
        violations.add("metadata_keys")
    if info is None or info.get("/Title") != expect.meta.title:
        violations.add("metadata_title")
    stamp = pdf_date(expect.meta.as_of)
    if info is None or info.get("/CreationDate") != stamp or info.get("/ModDate") != stamp:
        violations.add("metadata_dates")
    if isinstance(root, DictionaryObject) and "/Metadata" in root:
        violations.add("metadata_xmp")
    if log is not None:
        if log.unexpected:
            violations.add("requests_unexpected")
        if log.aborted:
            violations.add("requests_aborted")
        if log.failed:
            violations.add("requests_failed")
    return sorted(violations)


def print_pdf(
    html_path: Path,
    pdf_path: Path,
    *,
    meta: PdfMeta,
    expect: PdfExpect,
    shell: ShellInstall,
    work: Path,
    locale: str = "en-US",
) -> PrintedPdf:
    """Print one document, run the QA gate and write ``pdf_path`` atomically only if it passed."""
    with PdfPrinter(shell, work) as printer:
        printed = printer.print(html_path, meta, locale=locale)
    violations = qa_gate(printed.data, expect, log=printed.log)
    if violations:
        raise PdfError("pdf.qa_failed", checks=",".join(violations))
    write_atomic(pdf_path, printed.data)
    return printed


def write_atomic(path: Path, data: bytes) -> None:
    """A private temporary file in the target folder, then a rename; nothing is left on failure (A-54)."""
    if path.is_dir():
        raise InputError("output.is_directory")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, name = create_temporary(path.parent, f".{path.name}.")
    except OSError:
        raise InputError("output.not_writable") from None
    temporary = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise InputError("output.not_writable") from None
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
