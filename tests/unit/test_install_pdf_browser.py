"""tools/install_pdf_browser.py (D-08, A-26, A-53): pinned zip, checksum, safe extraction, atomic install,
NeuroGrid's own folder. The download is replaced by a fake; no test uses the network."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import urllib.error
import zipfile
from pathlib import Path
from typing import Any

import pytest

import install_pdf_browser as ipb  # tools/install_pdf_browser.py
from neurogrid.kernel import pdf

ROOT = Path(__file__).parent.parent.parent
PLATFORM = ipb.current_platform()


def _zip(entries: dict[str, bytes], *, symlink: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            info = zipfile.ZipInfo("placeholder", date_time=(2026, 10, 1, 0, 0, 0))
            info.filename = info.orig_filename = name  # literal name: ZipInfo would turn '\\' into '/'
            info.external_attr = (stat.S_IFREG | 0o755) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "/etc/passwd")
    return buffer.getvalue()


def _tree(entries: dict[str, bytes]) -> str:
    lines = sorted(
        f"{name}\t{len(data)}\t{hashlib.sha256(data).hexdigest()}\n" for name, data in entries.items()
    )
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


@pytest.fixture
def small_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict[str, Any]]:
    """A small zip that stands in for the pinned one; the pin table is patched to its values."""
    prefix = f"chrome-headless-shell-{PLATFORM}/"
    entries = {
        ipb.SHELL[PLATFORM]["executable"]: b"MZ fake shell",
        prefix + "locales/en-US.pak": b"".join(hashlib.sha256(bytes([i])).digest() for i in range(64)),
        prefix + "ABOUT": b"Google Chrome",
    }
    data = _zip(entries)
    path = tmp_path / "shell.zip"
    path.write_bytes(data)
    pin = {
        **ipb.SHELL[PLATFORM],
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "files": len(entries),
        "unpacked": sum(len(v) for v in entries.values()),
        "tree_sha256": _tree(entries),
    }
    monkeypatch.setitem(ipb.SHELL, PLATFORM, pin)
    monkeypatch.delenv(ipb.ENV_DIR, raising=False)
    return path, pin


def test_pinned_table_urls_sizes_sha256_and_revision() -> None:
    assert (ipb.REVISION, ipb.BROWSER_VERSION, ipb.PLAYWRIGHT) == (
        pdf.SHELL_REVISION,
        pdf.SHELL_BROWSER_VERSION,
        pdf.PLAYWRIGHT_VERSION,
    )
    assert ipb.SHELL_DIRNAME == pdf.SHELL_DIRNAME and ipb.RECORD_NAME == pdf.RECORD_NAME
    assert ipb.ENV_DIR == pdf.ENV_BROWSER_DIR
    assert {name: entry["executable"] for name, entry in ipb.SHELL.items()} == pdf.EXECUTABLES
    expected = {
        "win64": (120_200_717, "7aec872f3090e639c4237467624ea863c20fe2878914c93a6556bdbb52aa6c4c", 290),
        "linux64": (119_809_080, "a9da028861a0cf789ff25c2fed45f5f1aaf969ed9247835b6a7821a4f7af9d1d", 287),
    }
    for name, entry in ipb.SHELL.items():
        assert (entry["bytes"], entry["sha256"], entry["files"]) == expected[name]
        primary, mirror = entry["urls"]
        file = f"chrome-headless-shell-{name}.zip"
        assert primary == f"https://cdn.playwright.dev/builds/cft/153.0.8010.12/{name}/{file}"
        assert (
            mirror == f"https://storage.googleapis.com/chrome-for-testing-public/153.0.8010.12/{name}/{file}"
        )
        assert len(entry["tree_sha256"]) == 64


@pytest.mark.parametrize("windows", [True, False])
def test_default_dir_matches_kernel(windows: bool) -> None:
    home = str(Path.home())
    for env in (
        {},
        {"LOCALAPPDATA": home + "/L", "XDG_DATA_HOME": home + "/X"},
        {"XDG_DATA_HOME": "relative"},
    ):
        assert ipb.default_browser_dir(env, windows=windows) == pdf.default_browser_dir(env, windows=windows)
    assert ipb.browser_dir({}) == pdf.browser_dir({})


@pytest.mark.parametrize("value", ["", "relative", "\\\\server\\share", "//server/share", "a\x01"])
def test_folder_must_be_absolute_and_local(value: str) -> None:
    with pytest.raises(ipb.InstallError) as info:
        ipb.browser_dir({ipb.ENV_DIR: value})
    assert info.value.key == "folder_invalid" and info.value.code == 2
    with pytest.raises(ipb.InstallError):
        ipb.browser_dir({}, explicit=value)


def test_from_zip_installs_atomically_and_writes_record(
    tmp_path: Path, small_shell: tuple[Path, dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    zip_path, pin = small_shell
    target = tmp_path / "browser"
    code = ipb.main(["--dir", str(target), "--from-zip", str(zip_path), "--sha256", pin["sha256"].upper()])
    out = capsys.readouterr().out
    assert code == 0 and "The PDF browser was installed" in out and "PDF 浏览器已安装" in out
    assert "NeuroGrid does not distribute it" in out  # D-08
    shell_dir = target / ipb.SHELL_DIRNAME
    record = json.loads((shell_dir / ipb.RECORD_NAME).read_text(encoding="utf-8"))
    assert record == {
        "browser_version": "153.0.8010.12",
        "bytes": pin["unpacked"],
        "executable": pin["executable"],
        "files": pin["files"],
        "format_version": 1,
        "platform": PLATFORM,
        "playwright": "1.63.0",
        "revision": "1243",
        "source": "zip",
        "tree_sha256": pin["tree_sha256"],
        "zip_bytes": pin["bytes"],
        "zip_sha256": pin["sha256"],
    }
    assert sorted(p.name for p in target.iterdir()) == [ipb.SHELL_DIRNAME]  # no staging, no download left
    if os.name != "nt":
        assert (shell_dir / pin["executable"]).stat().st_mode & 0o111
    # the kernel finds exactly this installation
    shell = pdf.locate_shell({pdf.ENV_BROWSER_DIR: str(target)})
    assert shell.executable == shell_dir / pin["executable"]
    assert ipb.main(["--dir", str(target), "--check"]) == 0
    assert ipb.main(["--dir", str(target), "--from-zip", str(zip_path), "--sha256", pin["sha256"]]) == 0
    assert "already installed" in capsys.readouterr().out
    (shell_dir / pin["executable"]).write_bytes(b"changed")
    assert ipb.main(["--dir", str(target), "--check"]) == 1
    assert "Reinstall it with --force" in capsys.readouterr().out
    assert (
        ipb.main(["--dir", str(target), "--force", "--from-zip", str(zip_path), "--sha256", pin["sha256"]])
        == 0
    )
    assert ipb.main(["--dir", str(target), "--check"]) == 0
    assert ipb.main(["--dir", str(tmp_path / "none"), "--check"]) == 1


def test_from_zip_wrong_checksum_is_refused_exit_1_nothing_installed(
    tmp_path: Path, small_shell: tuple[Path, dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    zip_path, pin = small_shell
    target = tmp_path / "browser"
    assert ipb.main(["--dir", str(target), "--from-zip", str(zip_path), "--sha256", "0" * 64]) == 1
    assert "Only this pinned zip is accepted" in capsys.readouterr().out
    other = tmp_path / "other.zip"
    other.write_bytes(_zip({pin["executable"]: b"another build"}))
    assert ipb.main(["--dir", str(target), "--from-zip", str(other), "--sha256", pin["sha256"]]) == 1
    assert "Nothing was installed" in capsys.readouterr().out
    assert not (target / ipb.SHELL_DIRNAME).exists()
    assert ipb.main(["--dir", str(target), "--from-zip", str(zip_path)]) == 2  # --sha256 missing
    assert (
        ipb.main(["--dir", str(target), "--from-zip", str(tmp_path / "x.zip"), "--sha256", pin["sha256"]])
        == 2
    )


def _unsafe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data: bytes) -> ipb.InstallError:
    path = tmp_path / "unsafe.zip"
    path.write_bytes(data)
    pin = {**ipb.SHELL[PLATFORM], "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    monkeypatch.setitem(ipb.SHELL, PLATFORM, pin)
    with pytest.raises(ipb.InstallError) as info:
        ipb.install(path, PLATFORM, tmp_path / "browser", source="zip", force=True)
    assert info.value.code == 1 and info.value.key == "unsafe"
    assert sorted(p.name for p in (tmp_path / "browser").iterdir()) == []  # staging removed
    return info.value


@pytest.mark.parametrize(
    "name",
    [
        "../evil.exe",
        "/etc/evil",
        "C:/evil.exe",
        "chrome-headless-shell-{p}\\evil.exe",
        "chrome-headless-shell-{p}/../../evil",
        "other-folder/evil",
        "chrome-headless-shell-{p}/a:stream",
        "chrome-headless-shell-{p}/./x",
    ],
)
def test_unsafe_zip_entry_names_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    error = _unsafe(tmp_path, monkeypatch, _zip({name.format(p=PLATFORM): b"x"}))
    assert "entry name" in str(error.params["problem"])


def test_symlinks_sizes_ratios_and_duplicates_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = f"chrome-headless-shell-{PLATFORM}/"
    assert "entry type" in str(
        _unsafe(tmp_path, monkeypatch, _zip({}, symlink=prefix + "link")).params["problem"]
    )
    monkeypatch.setattr(ipb, "MAX_ENTRIES", 2)
    entries = {prefix + f"f{i}": b"x" for i in range(3)}
    assert "entries" in str(_unsafe(tmp_path, monkeypatch, _zip(entries)).params["problem"])
    monkeypatch.setattr(ipb, "MAX_ENTRIES", 400)
    monkeypatch.setattr(ipb, "MAX_UNPACKED", 1000)
    big = _zip({prefix + "big": b"y" * 2000})
    assert _unsafe(tmp_path, monkeypatch, big).params["problem"] == "unpacked size"
    monkeypatch.setattr(ipb, "MAX_UNPACKED", 400_000_000)
    assert "compression ratio" in str(
        _unsafe(tmp_path, monkeypatch, big).params["problem"]
    )  # 2000 'y' → ~20 B
    duplicate = io.BytesIO()
    with zipfile.ZipFile(duplicate, "w") as archive:
        archive.writestr(prefix + "a", b"1")
        archive.writestr(prefix + "A", b"2")
    assert "duplicate" in str(_unsafe(tmp_path, monkeypatch, duplicate.getvalue()).params["problem"])


def test_content_must_match_the_pinned_build(
    tmp_path: Path, small_shell: tuple[Path, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_path, pin = small_shell
    monkeypatch.setitem(ipb.SHELL, PLATFORM, {**pin, "tree_sha256": "0" * 64})
    with pytest.raises(ipb.InstallError) as info:
        ipb.install(zip_path, PLATFORM, tmp_path / "browser", source="zip", force=True)
    assert info.value.code == 1 and "pinned build" in str(info.value.params["problem"])
    assert not (tmp_path / "browser" / ipb.SHELL_DIRNAME).exists()


class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_download_uses_only_pinned_urls_and_falls_back_to_mirror(
    tmp_path: Path,
    small_shell: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    zip_path, pin = small_shell
    requested: list[str] = []

    def urlopen(request: Any, timeout: float) -> _Response:
        requested.append(request.full_url)
        assert timeout == ipb.TIMEOUT_S and request.get_header("User-agent") == ipb.USER_AGENT
        if len(requested) == 1:
            raise urllib.error.URLError("unreachable")
        return _Response(zip_path.read_bytes())

    monkeypatch.setattr(ipb.urllib.request, "urlopen", urlopen)
    target = tmp_path / "browser"
    monkeypatch.setenv(ipb.ENV_DIR, str(target))
    assert ipb.main([]) == 0
    assert requested == list(pin["urls"])
    record = json.loads((target / ipb.SHELL_DIRNAME / ipb.RECORD_NAME).read_text(encoding="utf-8"))
    assert record["source"] == "download"
    assert sorted(p.name for p in target.iterdir()) == [ipb.SHELL_DIRNAME]  # the zip is removed
    assert "Download failed" in capsys.readouterr().out


def test_download_failures(
    tmp_path: Path,
    small_shell: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _zip_path, _pin = small_shell
    monkeypatch.setattr(ipb.urllib.request, "urlopen", lambda request, timeout: _Response(b"tampered"))
    target = tmp_path / "browser"
    assert ipb.main(["--dir", str(target)]) == 2
    out = capsys.readouterr().out
    assert out.count("differ from the pinned values") == 2 and "--download-only" in out
    assert not (target / ipb.SHELL_DIRNAME).exists() and not list(target.glob(".download*"))

    def endless(request: Any, timeout: float) -> _Response:
        return _Response(b"z" * (_pin["bytes"] + 10))

    monkeypatch.setattr(ipb.urllib.request, "urlopen", endless)
    assert ipb.main(["--dir", str(target)]) == 2  # more data than the pinned size is not read on


def test_download_only_for_another_computer(
    tmp_path: Path,
    small_shell: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    zip_path, pin = small_shell
    monkeypatch.setattr(
        ipb.urllib.request, "urlopen", lambda request, timeout: _Response(zip_path.read_bytes())
    )
    out_dir = tmp_path / "transfer"
    assert ipb.main(["--download-only", "--platform", PLATFORM, "--out", str(out_dir)]) == 0
    written = out_dir / f"chrome-headless-shell-{PLATFORM}.zip"
    assert written.read_bytes() == zip_path.read_bytes()
    assert f"--sha256 {pin['sha256']}" in capsys.readouterr().out
    assert ipb.main(["--download-only", "--platform", PLATFORM]) == 2
    assert ipb.main(["--download-only", "--out", str(out_dir)]) == 2


def test_print_info_lists_addresses_checksums_and_linux_packages(capsys: pytest.CaptureFixture[str]) -> None:
    assert ipb.main(["--print-info"]) == 0
    out = capsys.readouterr().out
    for entry in ipb.SHELL.values():
        assert entry["sha256"] in out and all(url in out for url in entry["urls"])
    assert "libnss3" in out and "libasound2t64" in out and "Installation folder" in out
    assert ipb.package_lists(ROOT / "tools" / "install_pdf_browser.py") == pdf.linux_packages()
    assert ipb.package_lists(Path("/nowhere/tools/x.py")) is None


def test_unsupported_platform(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(ipb.sys, "platform", "darwin")
    assert ipb.main(["--check"]) == 2
    assert "only Windows x86_64 and Linux x86_64" in capsys.readouterr().out


@pytest.mark.pdf
def test_installed_shell_passes_check() -> None:
    """The shell this machine prints with was installed by this script and is complete (tree digest)."""
    shell = pdf.locate_shell(os.environ)
    complete, problem, files = ipb.verify_installed(shell.shell_dir, shell.platform)
    assert complete, problem
    assert files == ipb.SHELL[shell.platform]["files"]


@pytest.mark.parametrize(("required", "outcome"), [("", "1 skipped"), ("1", "1 error")])
def test_pdf_tests_skip_without_browser_unless_required(tmp_path: Path, required: str, outcome: str) -> None:
    """B2: tests marked pdf skip with a reason when no browser is found; with NEUROGRID_REQUIRE_PDF=1 (CI,
    final local run) a missing browser fails them."""
    env = {**os.environ, ipb.ENV_DIR: str(tmp_path), "NEUROGRID_REQUIRE_PDF": required}
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-rs",
            f"{Path(__file__).as_posix()}::test_installed_shell_passes_check",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert outcome in done.stdout, done.stdout
    assert "PDF browser not available (pdf.shell_missing)" in done.stdout


def test_installer_uses_only_the_standard_library() -> None:
    """It runs with the offline bundle's interpreter before NeuroGrid is installed (B2): no third-party
    and no neurogrid import."""
    import ast

    tree = ast.parse((ROOT / "tools" / "install_pdf_browser.py").read_text(encoding="utf-8"))
    modules = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    modules |= {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and not node.level
    }
    assert modules and modules <= set(sys.stdlib_module_names) | {"__future__"}, modules
