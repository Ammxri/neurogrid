"""kernel/pdf.py without a browser (TECH-07, A-26, A-49, A-51): folders, start check, launch arguments,
router, date fields and the QA gate on PDFs built in the test."""

from __future__ import annotations

import ast
import inspect
import io
import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import pypdf
import pytest
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from conftest import holding_process, short_folder, wait_released  # type: ignore[import-not-found]
from neurogrid.kernel import pdf, safety
from neurogrid.kernel.errors import InputError, PdfError
from neurogrid.kernel.pdf import (
    CHROMIUM_FLAGS,
    CSP,
    EXECUTABLES,
    PdfExpect,
    PdfMeta,
    PdfPrinter,
    RequestLog,
    ShellInstall,
)

ROOT = Path(__file__).parent.parent.parent
AS_OF = date(2026, 10, 11)
STAMP = "D:20261011000000+00'00'"
# Synthetic ldd output (no Linux machine was available, D-09): built from the documented ldd format
# ("<soname> => <path> (<address>)", "<soname> => not found", "version `GLIBC_x' not found (required by …)")
# and sonames from Playwright 1.63.0's nativeDeps. Replace by recorded output of the first Linux CI run.
LDD_DEBIAN12_SYNTHETIC = """\
\tlinux-vdso.so.1 (0x00007ffd4b5f2000)
\tlibdl.so.2 => /lib/x86_64-linux-gnu/libdl.so.2 (0x00007f2b8c400000)
\tlibnss3.so => not found
\tlibnssutil3.so => not found
\tlibasound.so.2 => not found
\tlibglib-2.0.so.0 => /lib/x86_64-linux-gnu/libglib-2.0.so.0 (0x00007f2b8c200000)
\tlibc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007f2b8c000000)
"""
_GLIBC_LINE = "/opt/s/chrome-headless-shell: /lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_{}' not found "
LDD_GLIBC_SYNTHETIC = (
    _GLIBC_LINE.format("2.28")
    + "(required by /opt/s/chrome-headless-shell)\n"
    + _GLIBC_LINE.format("2.25")
    + "(required by /opt/s/chrome-headless-shell)\n"
    + "\tlibc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007f2b8c000000)\n"
)


def fake_shell(folder: Path, platform: str = "win64", record: dict[str, Any] | None = None) -> Path:
    shell_dir = folder / pdf.SHELL_DIRNAME
    executable = shell_dir / EXECUTABLES[platform]
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    data = {"revision": "1243", "platform": platform, "executable": EXECUTABLES[platform]}
    (shell_dir / pdf.RECORD_NAME).write_text(json.dumps(record or data), encoding="utf-8")
    return executable


def test_default_browser_dir_windows_and_linux() -> None:
    home = Path.home()
    windows = pdf.default_browser_dir({"LOCALAPPDATA": str(home / "L")}, windows=True)
    assert windows == home / "L" / "NeuroGrid" / "pdf-browser"
    assert (
        pdf.default_browser_dir({}, windows=True) == home / "AppData" / "Local" / "NeuroGrid" / "pdf-browser"
    )
    assert pdf.default_browser_dir({"LOCALAPPDATA": "rel"}, windows=True).is_absolute()
    linux = pdf.default_browser_dir({"XDG_DATA_HOME": str(home / "x")}, windows=False)
    assert linux == home / "x" / "neurogrid" / "pdf-browser"
    assert pdf.default_browser_dir({"XDG_DATA_HOME": "rel"}, windows=False) == (
        home / ".local" / "share" / "neurogrid" / "pdf-browser"
    )
    assert "ms-playwright" not in str(pdf.default_browser_dir(os.environ))


def test_browser_dir_env_override(tmp_path: Path) -> None:
    assert pdf.browser_dir({pdf.ENV_BROWSER_DIR: str(tmp_path)}) == tmp_path
    assert pdf.browser_dir({}) == pdf.default_browser_dir({})


@pytest.mark.parametrize(
    "value", ["", "  ", "relative/folder", "\\\\server\\share\\x", "//server/share", "a\x01b"]
)
def test_browser_dir_env_unc_relative_or_empty_is_exit_2(value: str) -> None:
    with pytest.raises(PdfError) as info:
        pdf.browser_dir({pdf.ENV_BROWSER_DIR: value})
    assert info.value.message_key == "pdf.browser_dir_invalid"


def test_locate_shell_missing_incomplete_wrong_revision_wrong_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pdf, "shell_platform", lambda: "win64")
    env = {pdf.ENV_BROWSER_DIR: str(tmp_path)}
    with pytest.raises(PdfError) as info:
        pdf.locate_shell(env)
    assert info.value.message_key == "pdf.shell_missing" and info.value.hint is not None
    assert info.value.params["revision"] == "1243" and info.value.params["folder"] == tmp_path
    (tmp_path / pdf.SHELL_DIRNAME).mkdir()
    with pytest.raises(PdfError) as info:
        pdf.locate_shell(env)
    assert info.value.message_key == "pdf.shell_incomplete"
    (tmp_path / pdf.SHELL_DIRNAME).rmdir()
    executable = fake_shell(tmp_path)
    shell = pdf.locate_shell(env)
    assert shell == ShellInstall(tmp_path, tmp_path / pdf.SHELL_DIRNAME, executable, "win64")
    assert shell.executable.is_relative_to(tmp_path)
    record = tmp_path / pdf.SHELL_DIRNAME / pdf.RECORD_NAME
    for wrong in ({"revision": "1200"}, {"platform": "linux64"}, {"executable": "chrome.exe"}):
        data = {"revision": "1243", "platform": "win64", "executable": EXECUTABLES["win64"], **wrong}
        record.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(PdfError) as info:
            pdf.locate_shell(env)
        assert info.value.message_key == "pdf.shell_revision" and info.value.params["required"] == "1243"
    record.write_text("not json", encoding="utf-8")
    with pytest.raises(PdfError) as info:
        pdf.locate_shell(env)
    assert info.value.message_key == "pdf.shell_incomplete"
    executable.unlink()
    record.write_text(json.dumps({"revision": "1243"}), encoding="utf-8")
    with pytest.raises(PdfError) as info:
        pdf.locate_shell(env)
    assert info.value.message_key == "pdf.shell_incomplete"


def test_shell_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    for system, machine, expected in (("win32", "AMD64", "win64"), ("linux", "x86_64", "linux64")):
        monkeypatch.setattr(pdf.sys, "platform", system)
        monkeypatch.setattr(pdf.platform, "machine", lambda m=machine: m)
        assert pdf.shell_platform() == expected
    for system, machine in (("linux", "aarch64"), ("darwin", "x86_64"), ("win32", "ARM64")):
        monkeypatch.setattr(pdf.sys, "platform", system)
        monkeypatch.setattr(pdf.platform, "machine", lambda m=machine: m)
        with pytest.raises(PdfError) as info:
            pdf.shell_platform()
        assert info.value.message_key == "pdf.platform_unsupported" and machine in str(info.value.params)


def test_install_hint_bundle_command_otherwise_docs_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B2: an offline-bundle installation (marker file in the prefix above the venv) gets the command with
    its own interpreter and script; every other installation (this source checkout, PyPI) the docs page."""
    assert pdf.install_hint() == ("pdf.install.docs", {})
    prefix = tmp_path / "Neuro Grid"
    python = prefix / "python" / ("python.exe" if os.name == "nt" else "bin/python3.12")
    script = prefix / "tools" / "install_pdf_browser.py"
    for path in (prefix / pdf.BUNDLE_MARKER, script, python):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    monkeypatch.setattr(pdf.sys, "prefix", str(prefix / "venv"))
    assert pdf.install_hint() == ("pdf.install.command", {"command": f'"{python}" "{script}"'})
    plain = tmp_path / "plain"
    for path in (
        plain / pdf.BUNDLE_MARKER,
        plain / "tools" / "install_pdf_browser.py",
        plain / "python" / "x",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    monkeypatch.setattr(pdf.sys, "prefix", str(plain / "venv"))
    assert pdf.install_hint()[0] == "pdf.install.docs"  # marker without the bundled interpreter
    for missing in (pdf.BUNDLE_MARKER, "tools/install_pdf_browser.py"):
        monkeypatch.setattr(pdf.sys, "prefix", str(prefix / "venv"))
        (prefix / missing).unlink()
        assert pdf.install_hint() == ("pdf.install.docs", {})
        (prefix / missing).write_bytes(b"")


def test_ldd_parser_maps_missing_libraries_to_packages() -> None:
    missing, glibc = pdf.parse_ldd(LDD_DEBIAN12_SYNTHETIC)
    assert missing == ["libasound.so.2", "libnss3.so", "libnssutil3.so"] and glibc == []
    error = pdf.missing_libraries_error(missing, "debian12")
    assert error.message_key == "pdf.linux_libraries"
    assert error.params["libraries"] == "libasound.so.2, libnss3.so, libnssutil3.so"
    assert error.hint == ("pdf.install.apt", {"distribution": "debian12", "packages": "libasound2 libnss3"})
    noble = pdf.missing_libraries_error(missing, "ubuntu24.04")
    assert noble.hint == (
        "pdf.install.apt",
        {"distribution": "ubuntu24.04", "packages": "libasound2t64 libnss3"},
    )
    other = pdf.missing_libraries_error(missing, None)
    assert other.hint is not None and other.hint[0] == "pdf.install.apt_other"
    assert other.hint[1]["distribution"] == "debian12"
    unknown = pdf.missing_libraries_error(["libunknown.so.9"], "debian12")
    assert unknown.hint is not None
    assert unknown.hint[1]["packages"] == " ".join(
        pdf.linux_packages()["distributions"]["debian12"]["packages"]
    )
    assert pdf.parse_ldd(LDD_GLIBC_SYNTHETIC) == ([], ["2.25", "2.28"])


def test_linux_distribution_from_os_release(tmp_path: Path) -> None:
    release = tmp_path / "os-release"
    for text, expected in (
        ('PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\nID=debian\nVERSION_ID="12"\n', "debian12"),
        ("ID=ubuntu\nVERSION_ID='22.04'\n", "ubuntu22.04"),
        ('ID=ubuntu\nVERSION_ID="24.04"\n', "ubuntu24.04"),
        ('ID=fedora\nVERSION_ID="40"\n', None),
    ):
        release.write_text(text, encoding="utf-8")
        assert pdf.linux_distribution(release) == expected
    assert pdf.linux_distribution(tmp_path / "missing") is None


def test_preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shell = ShellInstall(tmp_path, tmp_path, tmp_path / "chrome-headless-shell", "linux64")
    calls: list[list[str]] = []

    def run(output: str) -> Any:
        def fake(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            assert kwargs["env"]["LC_ALL"] == "C" and kwargs["check"] is False and "shell" not in kwargs
            return subprocess.CompletedProcess(args, 0, output, "")

        return fake

    release = tmp_path / "os-release"
    release.write_text("ID=debian\nVERSION_ID=12\n", encoding="utf-8")
    monkeypatch.setattr(pdf.shutil, "which", lambda name: "/usr/bin/ldd")
    with pytest.raises(PdfError) as info:
        pdf.preflight(shell, run=run(LDD_DEBIAN12_SYNTHETIC), os_release=release)
    assert info.value.message_key == "pdf.linux_libraries"
    assert calls == [["/usr/bin/ldd", str(shell.executable)]]
    with pytest.raises(PdfError) as info:
        pdf.preflight(shell, run=run(LDD_GLIBC_SYNTHETIC), os_release=release)
    assert info.value.message_key == "pdf.glibc_too_old" and info.value.params["required"] == "2.28"
    pdf.preflight(shell, run=run("\tlibc.so.6 => /lib/libc.so.6 (0x1)\n"), os_release=release)
    monkeypatch.setattr(pdf.shutil, "which", lambda name: None)
    pdf.preflight(shell, run=run(LDD_DEBIAN12_SYNTHETIC))  # no ldd: the launch error decides
    calls.clear()
    pdf.preflight(ShellInstall(tmp_path, tmp_path, tmp_path / "x.exe", "win64"), run=run("x"))
    assert calls == []  # Windows: no system libraries to check
    monkeypatch.setattr(pdf.metadata, "version", lambda name: "1.64.1")
    with pytest.raises(PdfError) as info:
        pdf.preflight(shell)
    assert info.value.message_key == "pdf.playwright_version" and info.value.params["found"] == "1.64.1"


def test_playwright_version_matches_pin_and_browsers_json_revision_1243() -> None:
    import playwright

    from neurogrid.kernel.pdf import PLAYWRIGHT_VERSION, SHELL_BROWSER_VERSION, SHELL_REVISION

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'"playwright=={PLAYWRIGHT_VERSION}"' in pyproject
    assert pdf.metadata.version("playwright") == PLAYWRIGHT_VERSION
    browsers = json.loads(
        (Path(playwright.__file__).parent / "driver" / "package" / "browsers.json").read_text(
            encoding="utf-8"
        )
    )
    shell = next(b for b in browsers["browsers"] if b["name"] == "chromium-headless-shell")
    assert (shell["revision"], shell["browserVersion"]) == (SHELL_REVISION, SHELL_BROWSER_VERSION)


def test_linux_package_table_matches_playwright_driver() -> None:
    import linux_pdf_packages  # tools/linux_pdf_packages.py

    data = linux_pdf_packages.from_playwright()
    assert linux_pdf_packages.render(data) == pdf.LINUX_PACKAGES.read_text(encoding="utf-8")
    assert sorted(data["distributions"]) == ["debian12", "ubuntu22.04", "ubuntu24.04"]
    assert "libnss3" in data["distributions"]["debian12"]["packages"]
    assert data["distributions"]["ubuntu24.04"]["libraries"]["libasound.so.2"] == "libasound2t64"
    assert linux_pdf_packages.main(["debian12"]) == 0 and linux_pdf_packages.main(["fedora40"]) == 2
    # the literal is read as data, never run: anything but strings, arrays and objects is refused
    assert linux_pdf_packages.parse_deps('{\n  tools: ["a",],\n  "x-y": {\n    chromium: []\n  },\n}') == {
        "tools": ["a"],
        "x-y": {"chromium": []},
    }
    for code in ('{\n  tools: f("a")\n}', '{\n  tools: ["a" + b]\n}', '["a"]'):
        with pytest.raises(ValueError):
            linux_pdf_packages.parse_deps(code)


def test_launch_arguments_fixed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The browser is always the located shell (executable_path), never a channel; the flags are fixed."""
    assert CHROMIUM_FLAGS == (
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-breakpad",
        "--no-pings",
        "--disable-domain-reliability",
        "--disable-sync",
        "--proxy-server=direct://",
        "--host-resolver-rules=MAP * ~NOTFOUND",
    )
    launched: dict[str, Any] = {}
    environment_at_start: dict[str, str | None] = {}

    class Browser:
        def close(self) -> None:
            launched["closed"] = True

    class Chromium:
        def launch(self, **kwargs: Any) -> Browser:
            launched.update(kwargs)
            return Browser()

    class Driver:
        chromium = Chromium()

        def stop(self) -> None:
            launched["stopped"] = True

    class Starter:
        def start(self) -> Driver:
            environment_at_start.update({name: os.environ.get(name) for name in ("TMP", "NODE_OPTIONS")})
            environment_at_start["cwd"] = str(Path.cwd())  # the driver and the browser keep it
            return Driver()

    import playwright.sync_api

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: Starter())
    monkeypatch.setenv("NODE_OPTIONS", "--require=evil.js")
    shell = ShellInstall(tmp_path, tmp_path, tmp_path / "shell.exe", "win64")
    before = Path.cwd()
    with pdf.browser_work() as work, PdfPrinter(shell, work, extra_flags=("--log-net-log=x",)):
        assert Path.cwd() == before  # changed only while the driver starts
    assert launched["executable_path"] == str(tmp_path / "shell.exe") and "channel" not in launched
    log_file = f"--log-file={work / 'chromium.log'}"  # not next to the executable (A-54)
    expected = [*CHROMIUM_FLAGS, "--in-process-gpu", log_file, "--log-net-log=x"]
    assert launched["args"] == expected and launched["headless"] is True
    assert launched["env"] == pdf.browser_environment(work) and launched["chromium_sandbox"] is False
    assert not (launched["handle_sigint"] or launched["handle_sigterm"] or launched["handle_sighup"])
    assert launched["closed"] and launched["stopped"]
    assert environment_at_start == {"TMP": str(work), "NODE_OPTIONS": None, "cwd": str(work)}
    assert os.environ["NODE_OPTIONS"] == "--require=evil.js"  # restored after the driver start


def test_browser_errors_never_show_playwright_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import playwright.sync_api
    from playwright.sync_api import Error, TimeoutError

    secret = str(Path.home() / "secret" / "chrome.exe")

    class Chromium:
        def __init__(self, exc: Exception) -> None:
            self.exc = exc

        def launch(self, **kwargs: Any) -> None:
            raise self.exc

    stopped: list[bool] = []

    class Driver:
        def __init__(self, exc: Exception) -> None:
            self.chromium = Chromium(exc)

        def stop(self) -> None:
            stopped.append(True)

    shell = ShellInstall(tmp_path, tmp_path, tmp_path / "shell.exe", "win64")
    for exc, key in (
        (Error(f"Executable doesn't exist at {secret}"), "pdf.launch_failed"),
        (TimeoutError("t"), "pdf.timeout"),
    ):
        monkeypatch.setattr(
            playwright.sync_api,
            "sync_playwright",
            lambda e=exc: type("S", (), {"start": lambda self: Driver(e)})(),
        )
        with pytest.raises(PdfError) as info, pdf.browser_work() as work:
            PdfPrinter(shell, work).__enter__()
        assert info.value.message_key == key and secret not in str(info.value.params)
    assert stopped == [True, True]
    printer = PdfPrinter(shell, tmp_path / "w")
    with pytest.raises(RuntimeError):
        printer.print(tmp_path / "x.html", PdfMeta("t", AS_OF))


def test_driver_environment_is_restored_and_cleaned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing from the caller's environment changes the driver or the browser: no other node binary
    (PLAYWRIGHT_NODEJS_PATH), no node options, no debug output, no PLAYWRIGHT_*/PW_* switches."""
    monkeypatch.setenv("TMP", "before")
    monkeypatch.setenv("PWDEBUG", "1")
    monkeypatch.setenv("DEBUG", "pw:api")
    monkeypatch.setenv("DEBUGP", "1")
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", str(tmp_path / "other-node.exe"))
    monkeypatch.setenv("PLAYWRIGHT_SKIP_NAVIGATION_CHECK", "1")
    monkeypatch.setenv("PW_TEST_SCREENSHOT_NO_FONTS_READY", "1")
    monkeypatch.setenv("PWD_LIKE", "kept")  # only the listed names and prefixes are removed
    monkeypatch.delenv("TMPDIR", raising=False)
    removed = {
        "PWDEBUG",
        "DEBUG",
        "DEBUGP",
        "NODE_OPTIONS",
        "NODE_PATH",
        "DEBUG_FILE",
        "PLAYWRIGHT_NODEJS_PATH",
        "PLAYWRIGHT_SKIP_NAVIGATION_CHECK",
        "PW_TEST_SCREENSHOT_NO_FONTS_READY",
    }
    with pytest.raises(ValueError), pdf.driver_environment(tmp_path):
        assert os.environ["TMP"] == os.environ["TEMP"] == os.environ["TMPDIR"] == str(tmp_path)
        assert not removed & set(os.environ) and os.environ["PWD_LIKE"] == "kept"
        raise ValueError
    assert os.environ["TMP"] == "before" and os.environ["PWDEBUG"] == "1" and "TMPDIR" not in os.environ
    assert os.environ["PLAYWRIGHT_NODEJS_PATH"] == str(tmp_path / "other-node.exe")
    assert os.environ["PW_TEST_SCREENSHOT_NO_FONTS_READY"] == "1" and os.environ["DEBUGP"] == "1"


def test_driver_runs_in_the_work_folder_and_the_caller_folder_comes_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2: the driver starts with the work folder as current folder; it keeps it and the browser and its
    child processes inherit it, so a debug.log Chromium writes into its current folder goes with the work
    folder (measured with a 208-character work folder: in the caller's folder before, in the work folder
    with this). The caller's folder is restored; if it is gone meanwhile, the process leaves the work folder
    for its parent, so that the work folder can be removed."""
    caller, work = tmp_path / "caller", tmp_path / "work"
    caller.mkdir()
    work.mkdir()
    monkeypatch.chdir(caller)
    with pdf.driver_environment(work):
        assert Path.cwd() == work
    assert Path.cwd() == caller
    with pytest.raises(ValueError), pdf.driver_environment(work):
        raise ValueError
    assert Path.cwd() == caller
    with pdf.driver_environment(work):
        caller.rmdir()
    assert Path.cwd() == tmp_path


def test_work_folder_limits_on_windows_only() -> None:
    """P2: Windows refuses paths that are too long for the shell's profile (MAX_PATH; the shell is not
    long-path aware). A work folder longer than WORK_PATH_LIMIT characters ends with exit 2, its own message
    and the hint to set a shorter temporary folder (at most TEMP_PATH_LIMIT characters: the work folder adds
    a separator, the prefix and mkdtemp's eight characters). Linux has no such limit."""
    anchor = Path(Path.cwd().anchor)
    at_limit = anchor / ("w" * (pdf.WORK_PATH_LIMIT - len(str(anchor))))
    assert len(str(at_limit)) == pdf.WORK_PATH_LIMIT == 100
    pdf.check_work_path(at_limit, windows=True)
    with pytest.raises(PdfError) as info:
        pdf.check_work_path(Path(f"{at_limit}x"), windows=True)
    assert info.value.message_key == "pdf.work_path_too_long"
    assert info.value.params == {"length": pdf.WORK_PATH_LIMIT + 1, "limit": pdf.WORK_PATH_LIMIT}
    assert info.value.hint == ("pdf.temp_hint", {"limit": pdf.TEMP_PATH_LIMIT})
    assert pdf.TEMP_PATH_LIMIT == pdf.WORK_PATH_LIMIT - 1 - len(pdf.WORK_PREFIX) - 8 == 84
    pdf.check_work_path(Path(f"{at_limit}{'x' * 300}"), windows=False)


@pytest.mark.skipif(os.name != "nt", reason="the path limit is Windows' (MAX_PATH); Linux has none")
def test_printer_refuses_a_long_work_folder_before_the_driver_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import playwright.sync_api

    def never() -> None:
        raise AssertionError("the driver was started")

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", never)
    shell = ShellInstall(tmp_path, tmp_path, tmp_path / "shell.exe", "win64")
    work = Path(Path.cwd().anchor) / ("w" * pdf.WORK_PATH_LIMIT)
    with pytest.raises(PdfError) as info:
        PdfPrinter(shell, work).__enter__()
    assert info.value.message_key == "pdf.work_path_too_long" and not work.exists()


def test_browser_work_lies_in_the_temporary_folder_and_is_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    """P2: the browser's work folder is a private folder in the computer's temporary folder, independent
    of --out; it is removed afterwards, also after an error."""
    with short_folder("ng-temp-") as base:  # stands in for the computer's temporary folder
        monkeypatch.setattr(tempfile, "tempdir", str(base))
        assert pdf.work_base() == base
        with pdf.browser_work() as work:
            assert work.parent == base and work.name.startswith(pdf.WORK_PREFIX) and not any(work.iterdir())
            (work / "profile").mkdir()
            (work / "profile" / "Local State").write_text("{}", encoding="utf-8")
        assert not work.exists()
        with pytest.raises(RuntimeError), pdf.browser_work() as work:
            raise RuntimeError
        assert not work.exists() and not any(base.iterdir())
        monkeypatch.undo()


HOLD_BROWSER_WORK = """
from neurogrid.kernel import pdf

with pdf.browser_work() as work:
    (work / "report.zh.html").write_text("<title>dataset-derived</title>", encoding="utf-8")
    (work / "playwright_chromiumdev_profile-x" / "Default").mkdir(parents=True)
    print(work, flush=True)
    input()  # until it is killed
"""


def test_browser_work_of_a_killed_run_is_removed_at_the_next_browser_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verification of P2: a run killed while it prints (no finally runs) leaves its work folder with the
    printed HTML in the computer's temporary folder. The next browser run removes it (A-54 "at the next
    start"), but never the work folder of a run that is still going."""
    with short_folder("ng-temp-") as base:  # stands in for the computer's temporary folder
        monkeypatch.setattr(tempfile, "tempdir", str(base))
        env = {"TEMP": str(base), "TMP": str(base), "TMPDIR": str(base)}
        with holding_process(HOLD_BROWSER_WORK, **env) as (process, held):
            lock = held.with_name(held.name + safety.WORK_LOCK_SUFFIX)
            assert held.parent == base and held.name.startswith(pdf.WORK_PREFIX) and lock.is_file()
            with pdf.browser_work() as work:  # the other run is still going
                assert (held / "report.zh.html").is_file() and work != held
            assert not work.exists() and (held / "report.zh.html").is_file()
            process.kill()
            process.wait()
            wait_released(lock)
            assert (held / "report.zh.html").is_file()  # the killed run removed nothing
            with pdf.browser_work() as work:
                assert not held.exists() and not lock.exists()
            assert list(base.iterdir()) == []
        monkeypatch.undo()


def test_temporary_folder_too_long_or_unusable_ends_with_its_own_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2: a temporary folder whose path is too long for the shell's profile (Windows) or in which no work
    folder can be created ends with exit 2 and its own hint, before anything is created; the start check
    (preflight) tests it before any rendering."""
    with short_folder("ng-temp-") as root:
        long = root / ("t" * (pdf.TEMP_PATH_LIMIT + 1))
        monkeypatch.setattr(tempfile, "tempdir", str(long))
        with pytest.raises(PdfError) as info, pdf.browser_work(windows=True):
            pass
        assert info.value.message_key == "pdf.work_path_too_long"
        assert info.value.params == {"length": len(str(long)), "limit": pdf.TEMP_PATH_LIMIT}
        assert info.value.hint == ("pdf.temp_hint", {"limit": pdf.TEMP_PATH_LIMIT}) and not long.exists()
        long.mkdir()
        with pdf.browser_work(windows=False) as work:  # Linux: no such limit
            assert work.parent == long
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "missing"))
    with pytest.raises(PdfError) as info, pdf.browser_work(windows=False):
        pass
    assert info.value.message_key == "pdf.temp_unusable" and info.value.hint == ("pdf.temp_unusable_hint", {})

    def no_folder() -> str:
        raise FileNotFoundError("No usable temporary directory found")

    monkeypatch.setattr(tempfile, "gettempdir", no_folder)
    with pytest.raises(PdfError) as info:
        pdf.work_base()
    assert info.value.message_key == "pdf.temp_unusable"
    with pytest.raises(PdfError) as info:
        pdf.preflight(ShellInstall(tmp_path, tmp_path, tmp_path / "x.exe", "win64"))
    assert info.value.message_key == "pdf.temp_unusable"


@pytest.mark.parametrize(
    ("before", "removable", "after"),
    [(None, True, None), (b"older lines\n", True, None), (b"older lines\n", False, b"older lines\n")],
)
def test_child_log_next_to_the_executable_is_undone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    before: bytes | None,
    removable: bool,
    after: bytes | None,
) -> None:
    """A-51/A-54: a debug.log the shell's child processes write next to the executable during a run is
    removed when the printer closes, also after a launch failure. One that is there at the start is a
    leftover of a run that could not undo it (killed, or an older version that wrote it below a long work
    folder: seen in the installed shell while P2 was verified) and is removed at the start; if it cannot
    be removed (held open by the browser of a run still going), the run cuts back only what it appended."""
    import playwright.sync_api
    from playwright.sync_api import Error

    executable = tmp_path / "shell" / "chrome-headless-shell.exe"
    executable.parent.mkdir()
    log = executable.parent / "debug.log"
    if before is not None:
        log.write_bytes(before)
    real_unlink = Path.unlink

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self == log and not removable:
            raise PermissionError(13, "held open by a running browser")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)

    class Browser:
        def close(self) -> None:
            with log.open("ab") as handle:  # a child process logs an error while the browser runs
                handle.write(b"[1023/232745.082:ERROR:shared_image_manager.cc(395)] ...\n")

    class Chromium:
        fail = False

        def launch(self, **kwargs: Any) -> Browser:
            if self.fail:
                with log.open("ab") as handle:
                    handle.write(b"launch error\n")
                raise Error("launch failed")
            return Browser()

    class Driver:
        chromium = Chromium()

        def stop(self) -> None:
            pass

    monkeypatch.setattr(
        playwright.sync_api, "sync_playwright", lambda: type("S", (), {"start": lambda s: Driver()})()
    )
    shell = ShellInstall(tmp_path, tmp_path / "shell", executable, "win64")
    with pdf.browser_work() as work, PdfPrinter(shell, work):
        pass
    assert (log.read_bytes() if log.exists() else None) == after
    Driver.chromium.fail = True
    with pytest.raises(PdfError), pdf.browser_work() as work:
        PdfPrinter(shell, work).__enter__()
    assert (log.read_bytes() if log.exists() else None) == after


def test_child_log_of_unknown_state_is_left_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "debug.log"
    log.write_bytes(b"someone else's file\n")
    real_stat = Path.stat

    def stat(self: Path, **kwargs: Any) -> os.stat_result:
        if self.name == "debug.log":
            raise PermissionError("denied")
        return real_stat(self, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    child_log = pdf._ChildLog(tmp_path / "chrome-headless-shell.exe")
    monkeypatch.setattr(Path, "stat", real_stat)
    assert not child_log.known
    child_log.restore()
    assert log.read_bytes() == b"someone else's file\n"


def test_browser_environment(tmp_path: Path) -> None:
    windows = pdf.browser_environment(tmp_path, windows=True)
    assert set(windows) == {"TMP", "TEMP", "TMPDIR", "SystemRoot"} and windows["TMP"] == str(tmp_path)
    linux = pdf.browser_environment(tmp_path, windows=False)
    assert linux["HOME"] == str(tmp_path / "home") and linux["LANG"] == "C.UTF-8"
    assert all(
        Path(linux[name]).is_dir() for name in ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME")
    )
    assert not {"PATH", "HTTP_PROXY", "HTTPS_PROXY", "USERNAME", "USER"} & (set(linux) | set(windows))


def test_route_handler_has_one_parameter() -> None:
    log = RequestLog()
    handler = pdf._router("file:///r.html", log)
    assert len(inspect.signature(handler).parameters) == 1

    class Route:
        def __init__(self, url: str) -> None:
            self.request = type("Request", (), {"url": url})()
            self.done = ""

        def continue_(self) -> None:
            self.done = "continue"

        def abort(self, reason: str) -> None:
            self.done = reason

    own, other = Route("file:///r.html"), Route("https://example.com/a.png")
    handler(own)
    handler(other)
    assert (own.done, other.done, log.aborted) == ("continue", "blockedbyclient", 1)
    count = pdf._counter("file:///r.html", log)
    for url in ("file:///r.html", "data:font/ttf;base64,AA", "file:///C:/Windows/win.ini"):
        count(type("Request", (), {"url": url})())
    pdf._failure(log)(None)
    assert log == RequestLog(seen=3, unexpected=1, aborted=1, failed=1)


def test_csp_and_title_of_the_html() -> None:
    page = f'<head><meta http-equiv="Content-Security-Policy" content="{CSP}"><title>A &amp;\n  B</title>'
    assert pdf.has_csp(page) and pdf.html_title(page) == "A & B"
    assert not pdf.has_csp(page.replace("img-src data:", "img-src *"))  # another policy
    assert pdf.has_csp(f"<meta http-equiv='Content-Security-Policy' content=\"{CSP}\">")
    assert pdf.has_csp(f'<META CONTENT="{CSP}" HTTP-EQUIV="content-security-policy"/>')  # order and case
    assert not pdf.has_csp(page.replace("default-src 'none'; ", ""))
    assert not pdf.has_csp(f'<meta name="Content-Security-Policy" content="{CSP}">')  # not http-equiv
    assert not pdf.has_csp("<html></html>") and pdf.html_title("<html></html>") == ""
    # only the head counts: a policy in the body has no effect, a chart's SVG <title> is not the title
    body = (
        "<html><head><title>Report</title></head><body>"
        f'<meta http-equiv="Content-Security-Policy" content="{CSP}">'
    )
    assert not pdf.has_csp(body + "<svg><title>Chart</title></svg></body></html>")
    assert pdf.html_title(body + "<svg><title>Chart</title></svg>") == "Report"
    assert pdf.html_title("<title>First</title><title>Second</title>") == "First"


def _skia_like(
    creation: bytes = b"D:20261023183612+00'00'", mod: bytes = b"D:20261023183612+00'00'"
) -> bytes:
    return (
        b"%PDF-1.4\n1 0 obj\n<</Title (x) /Creator (Chromium) /Producer (Skia/PDF m153) /CreationDate ("
        + creation
        + b") /ModDate ("
        + mod
        + b")>>\nendobj\n"
    )


class _FakePage:
    def __init__(self, calls: dict[str, Any]) -> None:
        self.calls = calls

    def on(self, event: str, handler: object) -> None:
        self.calls.setdefault("events", []).append(event)

    def goto(self, url: str, **kwargs: Any) -> None:
        self.calls["goto"] = (url, kwargs)

    def pdf(self, **kwargs: Any) -> bytes:
        self.calls["pdf"] = kwargs
        return _skia_like()


class _FakeContext:
    def __init__(self, calls: dict[str, Any]) -> None:
        self.calls = calls

    def set_default_timeout(self, timeout: float) -> None:
        self.calls["timeout"] = timeout

    def route(self, pattern: str, handler: object) -> None:
        self.calls["route"] = pattern

    def new_page(self) -> _FakePage:
        return _FakePage(self.calls)

    def close(self) -> None:
        self.calls["closed"] = True


def _fake_playwright(monkeypatch: pytest.MonkeyPatch, launched: dict[str, Any]) -> list[dict[str, Any]]:
    """sync_playwright with a browser whose contexts record their options and calls."""
    import playwright.sync_api

    contexts: list[dict[str, Any]] = []

    class Browser:
        def new_context(self, **kwargs: Any) -> _FakeContext:
            contexts.append({"options": kwargs})
            return _FakeContext(contexts[-1])

        def close(self) -> None:
            pass

    class Chromium:
        def launch(self, **kwargs: Any) -> Browser:
            launched.update(kwargs)
            return Browser()

    class Driver:
        chromium = Chromium()

        def stop(self) -> None:
            pass

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: type("S", (), {"start": Driver})())
    return contexts


def test_print_context_locale_per_document_and_fixed_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec D5: the context locale is the report's (zh-CN or en-US); everything else stays fixed. Another
    locale is refused before a context is opened."""
    launched: dict[str, Any] = {}
    contexts = _fake_playwright(monkeypatch, launched)
    page = tmp_path / "r.html"
    page.write_text(f'<head><meta http-equiv="Content-Security-Policy" content="{CSP}"></head>', "utf-8")
    shell = ShellInstall(tmp_path, tmp_path, tmp_path / "shell.exe", "win64")
    with pdf.browser_work() as work, PdfPrinter(shell, work) as printer:
        dated = printer.print(page, PdfMeta("t", AS_OF), locale="zh-CN")
        printer.print(page, PdfMeta("t", AS_OF))
        with pytest.raises(ValueError):
            printer.print(page, PdfMeta("t", AS_OF), locale="de-DE")
    assert pdf.LOCALES == {"zh-CN", "en-US"} and dated.data.count(STAMP.encode()) == 2
    assert [c["options"]["locale"] for c in contexts] == ["zh-CN", "en-US"]
    fixed = {k: v for k, v in contexts[0]["options"].items() if k != "locale"}
    assert fixed == {
        "java_script_enabled": False,
        "offline": True,
        "service_workers": "block",
        "accept_downloads": False,
        "timezone_id": "UTC",
        "color_scheme": "light",
    }
    for context in contexts:
        assert context["timeout"] == pdf.PAGE_TIMEOUT_MS and context["route"] == "**/*" and context["closed"]
        assert context["goto"] == (page.resolve().as_uri(), {"wait_until": "load"})
        assert context["pdf"]["tagged"] is False and context["pdf"]["outline"] is False


def test_relative_work_folder_becomes_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """On Python 3.11 tempfile.mkdtemp returns a relative folder for a relative --out: the driver and the
    browser still get absolute TMP, profile and log paths."""
    launched: dict[str, Any] = {}
    _fake_playwright(monkeypatch, launched)
    shell = ShellInstall(tmp_path, tmp_path, tmp_path / "shell.exe", "win64")
    with pdf.browser_work() as base:  # a short current folder: the absolute work folder stays in the limit
        monkeypatch.chdir(base)
        with PdfPrinter(shell, Path("out") / "run-1") as printer:
            assert printer.work == base / "out" / "run-1"
        assert launched["env"]["TMP"] == str(base / "out" / "run-1")
        assert f"--log-file={base / 'out' / 'run-1' / 'chromium.log'}" in launched["args"]
        monkeypatch.chdir(tmp_path)


def test_playwright_prints_without_a_timeout_and_navigates_with_one() -> None:
    """Playwright 1.63.0 sends Page.pdf without a timeout; the context default (PAGE_TIMEOUT_MS) bounds
    only opening and loading the page. A large report therefore never ends in pdf.timeout while it is
    printed (measured: 2000 extra finding rows, timeout 1 s: loading 0.2 s, printing 5.5 s, no timeout).
    A Playwright update that changes this fails here."""
    from playwright._impl._frame import Frame
    from playwright._impl._page import Page

    assert 'self._channel.send("pdf", None, params)' in inspect.getsource(Page.pdf)
    assert '"goto", self._navigation_timeout' in inspect.getsource(Frame.goto)


def test_set_dates_same_length_and_exactly_once() -> None:
    raw = _skia_like()
    dated = pdf.set_dates(raw, AS_OF)
    assert len(dated) == len(raw) and dated.count(STAMP.encode()) == 2 and b"20261023" not in dated
    assert pdf.set_dates(_skia_like(b"D:20261023183612+02'00'"), AS_OF).count(STAMP.encode()) == 2
    for broken in (raw.replace(b"/ModDate", b"/Other"), raw + raw, raw.replace(b"+00'00'", b"Z")):
        with pytest.raises(PdfError) as info:
            pdf.set_dates(broken, AS_OF)
        assert info.value.params == {"checks": "metadata_dates"}


def _pdf(
    *,
    info: dict[str, str] | None = None,
    fonts: dict[str, DictionaryObject] | None = None,
    form_fonts: dict[str, DictionaryObject] | None = None,
    xmp: bool = False,
    pages: int = 1,
) -> bytes:
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(595, 842)
        resources = DictionaryObject()
        if fonts:
            resources[NameObject("/Font")] = DictionaryObject(
                {NameObject(n): writer._add_object(f) for n, f in fonts.items()}
            )
        if form_fonts:
            form = DecodedStreamObject()
            form.update(
                {
                    NameObject("/Type"): NameObject("/XObject"),
                    NameObject("/Subtype"): NameObject("/Form"),
                    NameObject("/Resources"): DictionaryObject(
                        {
                            NameObject("/Font"): DictionaryObject(
                                {NameObject(n): writer._add_object(f) for n, f in form_fonts.items()}
                            )
                        }
                    ),
                }
            )
            resources[NameObject("/XObject")] = DictionaryObject(
                {NameObject("/X1"): writer._add_object(form)}
            )
        page[NameObject("/Resources")] = resources
    metadata = (
        info
        if info is not None
        else {
            "/Title": "NeuroGrid pre-check report",
            "/Creator": "Chromium",
            "/Producer": "Skia/PDF m153",
            "/CreationDate": STAMP,
            "/ModDate": STAMP,
        }
    )
    writer.add_metadata(metadata)
    if xmp:
        writer._root_object[NameObject("/Metadata")] = writer._add_object(DecodedStreamObject())
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _type0(
    base: str = "/AAAAAA+NotoSansSC-Regular",
    *,
    cid: str = "/CIDFontType2",
    file: str = "/FontFile2",
    tounicode: bool = True,
) -> DictionaryObject:
    descriptor = DictionaryObject({NameObject(file): DecodedStreamObject()})
    descendant = DictionaryObject(
        {NameObject("/Subtype"): NameObject(cid), NameObject("/FontDescriptor"): descriptor}
    )
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type0"),
            NameObject("/BaseFont"): NameObject(base),
            NameObject("/DescendantFonts"): ArrayObject([descendant]),
        }
    )
    if tounicode:
        font[NameObject("/ToUnicode")] = DecodedStreamObject()
    return font


def _simple(subtype: str, base: str = "/Helvetica") -> DictionaryObject:
    return DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject(subtype),
            NameObject("/BaseFont"): NameObject(base),
        }
    )


FONTS = ("NotoSansSC-Regular", "NotoSansSC-Bold")  # PostScript names of the faces (kernel.fonts)
EXPECT = PdfExpect(meta=PdfMeta(title="NeuroGrid pre-check report", as_of=AS_OF), fonts=FONTS)


def test_qa_gate_on_built_pdfs() -> None:
    good = _pdf(fonts={"/F1": _type0(), "/F2": _type0("/BAAAAA+NotoSansSC-Bold")})
    assert pdf.qa_gate(good, EXPECT) == []
    assert pdf.qa_gate(good, EXPECT, log=RequestLog(seen=1)) == []
    cases = {
        "font_type3": {"/F1": _simple("/Type3")},
        "font_not_cid_truetype": {"/F1": _simple("/Type1")},
        "font_not_report_font": {"/F1": _type0("/AAAAAA+MicrosoftYaHei")},
        "font_no_tounicode": {"/F1": _type0(tounicode=False)},
    }
    for code, used in cases.items():
        assert code in pdf.qa_gate(_pdf(fonts=used), EXPECT), code
    assert pdf.qa_gate(_pdf(fonts={"/F1": _type0(cid="/CIDFontType0")}), EXPECT) == ["font_not_cid_truetype"]
    assert pdf.qa_gate(_pdf(fonts={"/F1": _type0(file="/FontFile3")}), EXPECT) == ["font_not_cid_truetype"]
    assert pdf.qa_gate(_pdf(form_fonts={"/F9": _simple("/Type3")}), EXPECT) == ["font_type3"]  # inside a form
    assert pdf.qa_gate(_pdf(fonts={"/F1": _type0("/SegoeUISymbol")}), EXPECT) == ["font_not_report_font"]
    assert pdf.qa_gate(_pdf(fonts={"/F1": _type0("/NotoSansSC-Regular")}), EXPECT) == ["font_not_report_font"]
    # only the faces the product passes in: the kernel names no font itself (A-23)
    other = PdfExpect(meta=EXPECT.meta, fonts=("OtherSans-Regular",))
    assert pdf.qa_gate(_pdf(fonts={"/F1": _type0("/AAAAAA+OtherSans-Regular")}), other) == []
    assert pdf.qa_gate(good, other) == ["font_not_report_font"]
    assert pdf.qa_gate(good, PdfExpect(meta=EXPECT.meta, fonts=())) == ["font_not_report_font"]
    assert pdf.qa_gate(_pdf(fonts={"/F1": _type0("/aaaaaa+NotoSansSC-Regular")}), EXPECT) == [
        "font_not_report_font"
    ]


def test_qa_gate_metadata_phrases_and_requests() -> None:
    extra = {
        "/Title": "NeuroGrid pre-check report",
        "/Creator": "Chromium",
        "/Producer": "x",
        "/CreationDate": STAMP,
        "/ModDate": STAMP,
        "/Subject": "dataset name",
    }
    assert pdf.qa_gate(_pdf(info=extra), EXPECT) == ["metadata_keys"]
    wrong = {**extra, "/Title": "Report of /home/user/patient"}
    wrong.pop("/Subject")
    assert pdf.qa_gate(_pdf(info=wrong), EXPECT) == ["metadata_title"]
    dated = {**wrong, "/Title": EXPECT.meta.title, "/ModDate": "D:20261023183612+00'00'"}
    assert pdf.qa_gate(_pdf(info=dated), EXPECT) == ["metadata_dates"]
    assert pdf.qa_gate(_pdf(xmp=True), EXPECT) == ["metadata_xmp"]
    phrases = PdfExpect(meta=EXPECT.meta, fonts=FONTS, every_page=("fixed sentence",), once=("Cover",))
    assert pdf.qa_gate(_pdf(pages=2), phrases) == ["phrase_missing", "phrase_missing_on_page"]
    log = RequestLog(seen=3, unexpected=2, aborted=1, failed=1)
    assert pdf.qa_gate(_pdf(), EXPECT, log=log) == [
        "requests_aborted",
        "requests_failed",
        "requests_unexpected",
    ]
    assert pdf.qa_gate(b"not a pdf", EXPECT) == ["unreadable"]
    assert pdf.pdf_text(_pdf(pages=2)) == ["", ""]


def test_qa_gate_finds_radicals_and_reads_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "r.pdf"
    path.write_bytes(_pdf())
    assert pdf.qa_gate(path, EXPECT) == []
    monkeypatch.setattr(pypdf.PageObject, "extract_text", lambda self, *a, **k: "\u2f63 \u751f")
    assert pdf.qa_gate(path, EXPECT) == ["radical_codepoint"]
    monkeypatch.setattr(pypdf.PageObject, "extract_text", lambda self, *a, **k: "\u751f\uf900")
    assert pdf.qa_gate(path, EXPECT) == ["radical_codepoint"]


def test_write_atomic(tmp_path: Path) -> None:
    target = tmp_path / "a" / "r.pdf"
    pdf.write_atomic(target, b"%PDF")
    assert target.read_bytes() == b"%PDF" and [p.name for p in target.parent.iterdir()] == ["r.pdf"]
    with pytest.raises(InputError):
        pdf.write_atomic(tmp_path / "a", b"x")


def test_kernel_pdf_never_uses_another_browser() -> None:
    """A-26/B2: no channel, no Edge or system Chrome, no Playwright browser folder or installer."""
    source = (ROOT / "src" / "neurogrid" / "kernel" / "pdf.py").read_text(encoding="utf-8")
    for banned in (
        "channel=",
        "msedge",
        "ms-playwright",
        "PLAYWRIGHT_BROWSERS_PATH",
        "playwright install",
        "executable_path=None",
        'shutil.which("chrome',
    ):
        assert banned not in source, banned
    assert sys.modules.get("neurogrid.kernel.pdf") is pdf


def _browser_starts(tree: ast.AST) -> list[ast.Call]:
    """Calls like ``<x>.chromium.launch(...)``, ``launch_persistent_context`` or ``connect*``."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr.startswith(("launch", "connect"))
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr in ("chromium", "firefox", "webkit")
    ]


def test_every_browser_start_in_the_project_uses_the_located_shell() -> None:
    """B2: every browser start (product, tools, tests, also the documentation's browser tests) launches
    Chromium with ``executable_path`` from kernel.pdf.locate_shell, never a channel or another engine."""
    starts: dict[str, int] = {}
    for folder in ("src", "tools", "tests"):
        for path in (ROOT / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            calls = _browser_starts(ast.parse(text))
            if not calls:
                continue
            name = path.relative_to(ROOT).as_posix()
            starts[name] = len(calls)
            assert "locate_shell" in text or "pdf_shell" in text, name
            for call in calls:
                keywords = {keyword.arg for keyword in call.keywords}
                assert isinstance(call.func, ast.Attribute) and call.func.attr == "launch", name
                assert call.func.value.attr == "chromium", name  # type: ignore[attr-defined]
                assert "executable_path" in keywords and "channel" not in keywords, name
    assert starts["src/neurogrid/kernel/pdf.py"] == 1
    bad = ast.parse("p.chromium.launch(channel='msedge')\np.firefox.launch()\nb.chromium.connect_over_cdp(u)")
    assert len(_browser_starts(bad)) == 3


ASYNCIO_PROBE = """
import asyncio, json, socket, sys
events = []
sys.addaudithook(lambda e, a: events.append((e, repr([x for x in a if not isinstance(x, socket.socket)])))
                 if e in ("socket.bind", "socket.connect") else None)
from neurogrid.kernel import netguard
netguard.install()
loop = asyncio.new_event_loop()  # what Playwright's sync API creates (the proactor on Windows)
loop.run_until_complete(asyncio.sleep(0))
loop.close()
loop_events, blocked = list(events), netguard.blocked_count()
try:
    socket.create_connection(("192.0.2.1", 9), timeout=1)
    probe = "connected"
except Exception as exc:
    probe = type(exc).__name__
print(json.dumps({"events": loop_events, "blocked": blocked, "probe": probe}))
"""


def test_netguard_allows_the_asyncio_socket_pair_and_blocks_the_rest() -> None:
    """A-49 amendment: the event loop's wake-up socket pair (loopback) passes, other connections do not."""
    done = subprocess.run(
        [sys.executable, "-c", ASYNCIO_PROBE], capture_output=True, text=True, encoding="utf-8", check=False
    )
    assert done.returncode == 0, done.stderr
    report = json.loads(done.stdout)
    assert report["blocked"] == 0 and report["probe"] == "NetworkBlockedError"
    connects = [args for event, args in report["events"] if event == "socket.connect"]
    assert all("127.0.0.1" in args for args in connects)
    if sys.platform == "win32":  # proactor: one socket pair over 127.0.0.1 (on Linux an AF_UNIX pair)
        assert len(connects) == 1
