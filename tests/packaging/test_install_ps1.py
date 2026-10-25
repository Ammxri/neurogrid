"""packaging/install.ps1 and install.cmd (UF-08, NG-N04, A-26, D-10 g) under Windows PowerShell 5.1 (and
PowerShell 7 when installed) on a stand-in bundle: integrity (exit 3), signature (exit 4), usage and
environment (exit 2), cleanup after a failed installation. The full installation of a real bundle is the clean
room (packaging/ci/cleanroom_windows.ps1). A stand-in cosign (a .cmd that exits 0 or 1) exercises the
signature branch without network.

Every folder of these tests lies in a short folder of its own below the system's temporary folder, not below
pytest's temporary folder: the installer refuses an install folder longer than 249 minus the longest path the
bundle installs, and Windows PowerShell 5.1 reaches paths over 260 characters only with long-path support. So
the outcome does not depend on how long pytest's folder (--basetemp) is."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from bundle_fakes import extract, inputs

import bundle
from neurogrid.report.texts import disclaimer

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "packaging" / "install.ps1"
POWERSHELL = shutil.which("powershell") if sys.platform == "win32" else None
PWSH = shutil.which("pwsh") if sys.platform == "win32" else None
pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell 5.1 exists only on Windows")


# Room for the deepest folder below the short root: the guard test needs a prefix of up to 249 - 1 characters
# and the module copies of test_the_guard_keeps_modules_and_programs_loadable a path of 250.
SHORT_ROOT_LIMIT = 120


@pytest.fixture(scope="module")
def short_root() -> Iterator[Path]:
    """This module's folder below the system's temporary folder (independent of --basetemp), removed at the
    end."""
    root = Path(tempfile.mkdtemp(prefix="ngps-"))
    try:
        assert len(str(root)) <= SHORT_ROOT_LIMIT, f"temporary folder too long for these tests: {root}"
        yield root
    finally:
        shutil.rmtree(root)


@pytest.fixture
def work(short_root: Path) -> Path:
    """A new folder of one test below the short root."""
    return Path(tempfile.mkdtemp(prefix="t", dir=short_root))


@pytest.fixture(scope="module")
def built(short_root: Path) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="ps1-", dir=short_root))
    return extract(bundle.build(inputs(tmp, "win_amd64")), tmp / "extracted")


@pytest.fixture
def folder(built: Path, work: Path) -> Path:
    return Path(shutil.copytree(built, work / built.name))


def _run(
    folder: Path, *args: str, shell: str | None = None, env: dict[str, str] | None = None
) -> tuple[int, str]:
    assert POWERSHELL is not None
    command = [shell or POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
    result = subprocess.run(
        [*command, str(folder / "install.ps1"), *args], capture_output=True, env=env, timeout=300, check=False
    )
    text = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
    return result.returncode, text


def _resum(folder: Path) -> None:
    lines = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        rel = path.relative_to(folder).as_posix()
        if rel not in ("SHA256SUMS", "SHA256SUMS.sigstore.json"):
            lines.append(f"{bundle.sha256_file(path)}  {rel}\n")
    (folder / "SHA256SUMS").write_bytes("".join(sorted(lines, key=lambda line: line[66:])).encode())


def _sign(folder: Path) -> None:
    info = json.loads((folder / "BUNDLE.json").read_text(encoding="utf-8"))
    info["release_identity"] = (
        "https://github.com/owner/neurogrid/.github/workflows/release.yml@refs/tags/v9.8.7"
    )
    (folder / "BUNDLE.json").write_text(json.dumps(info, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (folder / "SHA256SUMS.sigstore.json").write_text("{}", encoding="utf-8")
    _resum(folder)


def _fake_cosign(base: Path, code: int) -> Path:
    path = base / "cosign-stand-in" / "cosign.cmd"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"@echo off\r\necho stand-in cosign %*\r\nexit /b {code}\r\n", encoding="ascii")
    return path


def test_script_is_utf8_with_bom_and_parses_without_errors() -> None:
    assert SCRIPT.read_bytes().startswith(b"\xef\xbb\xbf")
    check = (
        "$e = $null; [void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{SCRIPT}', [ref]$null, [ref]$e); $e.Count"
    )
    for shell in filter(None, (POWERSHELL, PWSH)):
        result = subprocess.run(
            [shell, "-NoProfile", "-Command", check], capture_output=True, text=True, check=False
        )
        assert result.stdout.strip() == "0", (shell, result.stdout, result.stderr)


def test_verify_only_passes_on_an_intact_bundle(folder: Path) -> None:
    code, text = _run(folder, "-VerifyOnly", "-SkipSignatureCheck")
    assert code == 0, text
    assert "integrity verified" in text and "完整性已核对" in text
    assert "unsigned development bundle, signature not verified" in text


@pytest.mark.skipif(PWSH is None, reason="PowerShell 7 (pwsh) is not installed; CI runs it")
def test_verify_only_under_powershell_7(folder: Path) -> None:
    code, text = _run(folder, "-VerifyOnly", "-SkipSignatureCheck", shell=PWSH)
    assert code == 0, text


@pytest.mark.parametrize(
    "tamper, expected",
    [
        (lambda f: (f / "LICENSE").write_text("changed", encoding="utf-8"), "changed / 已更改：LICENSE"),
        (lambda f: (f / "NOTICE").unlink(), "missing / 缺少：NOTICE"),
        (
            lambda f: (f / "docs" / "extra.html").write_text("x", encoding="utf-8"),
            "unexpected / 多余：docs/extra.html",
        ),
        (lambda f: (f / "SHA256SUMS").write_bytes(b"not a checksum line\n"), "malformed SHA256SUMS line"),
        (lambda f: (f / "SHA256SUMS").unlink(), "SHA256SUMS missing"),
    ],
)
def test_integrity_problems_exit_3_and_install_nothing(
    folder: Path, work: Path, tamper: object, expected: str
) -> None:
    tamper(folder)  # type: ignore[operator]
    prefix = work / "target"
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(prefix))
    assert code == 3, text
    assert expected in text
    assert not prefix.exists()


def test_unsigned_bundle_needs_the_explicit_switch(folder: Path) -> None:
    code, text = _run(folder, "-VerifyOnly")
    assert code == 4, text
    assert "pass -SkipSignatureCheck to continue" in text


def test_signed_bundle_without_cosign_needs_the_switch(folder: Path) -> None:
    _sign(folder)
    env = {**_clean_env(), "PATH": r"C:\Windows\System32;C:\Windows\System32\WindowsPowerShell\v1.0"}
    code, text = _run(folder, "-VerifyOnly", env=env)
    assert code == 4 and "cosign not found" in text, text
    code, text = _run(folder, "-VerifyOnly", "-SkipSignatureCheck", env=env)
    assert code == 0 and "signature not verified here, as requested" in text, text


def test_signed_bundle_with_cosign(folder: Path, work: Path) -> None:
    _sign(folder)
    good, bad = _fake_cosign(work / "ok", 0), _fake_cosign(work / "bad", 1)
    code, text = _run(folder, "-VerifyOnly", "-Cosign", str(good))
    assert code == 0, text
    assert "signature verified: https://github.com/owner/neurogrid/" in text
    assert (
        "--certificate-oidc-issuer https://token.actions.githubusercontent.com" in text
    )  # what cosign received
    code, text = _run(folder, "-VerifyOnly", "-Cosign", str(bad))
    assert code == 4 and "signature check failed" in text, text
    on_path = {**_clean_env(), "PATH": f"{bad.parent};C:\\Windows\\System32"}
    code, text = _run(folder, "-VerifyOnly", env=on_path)
    assert code == 4, text  # a cosign on PATH is used
    code, text = _run(folder, "-VerifyOnly", "-SkipSignatureCheck", env=on_path)
    assert code == 0, text  # an explicit skip wins over a cosign on PATH (it may lack Sigstore's trust root)


@pytest.mark.parametrize(
    "args, expected",
    [
        (["-Bogus", "x"], "unknown option: -Bogus x"),
        (["extra-positional"], "unknown option: extra-positional"),
        (["-Cosign", "C:\\x\\cosign.exe", "-SkipSignatureCheck"], "exclude each other"),
        (["-PdfBrowserZip", "C:\\x\\shell.zip"], "-PdfBrowserZip needs -PdfBrowserSha256"),
        (["-PdfBrowserZip", "C:\\does\\not\\exist.zip", "-PdfBrowserSha256", "a" * 64], "file not found"),
        (["-SkipSignatureCheck", "-Prefix", "relative\\folder"], "absolute local path"),
        (["-SkipSignatureCheck", "-Prefix", "\\\\server\\share\\ng"], "absolute local path"),
    ],
)
def test_usage_and_environment_errors_exit_2(folder: Path, args: list[str], expected: str) -> None:
    code, text = _run(folder, *args)
    assert code == 2, text
    assert expected in text


def test_existing_target_is_never_overwritten(folder: Path, work: Path) -> None:
    prefix = work / "target"
    prefix.mkdir()
    (prefix / "keep.txt").write_text("mine", encoding="utf-8")
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(prefix))
    assert code == 2 and "target exists and is not empty" in text, text
    assert [p.name for p in prefix.iterdir()] == ["keep.txt"]


def test_failed_installation_exits_2_and_removes_what_it_created(folder: Path, work: Path) -> None:
    """The stand-in uv.exe is not a program: creating the venv fails, the new folder is removed again."""
    prefix = work / "new-target"
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(prefix))
    assert code == 2, text
    assert "installation failed" in text or "creating the virtual environment failed" in text
    assert not prefix.exists()


def test_variables_for_uv_are_restored_in_an_open_session(folder: Path, work: Path) -> None:
    """Run inside an existing session (not through install.cmd), a failed installation leaves neither the uv
    variables nor PYTHONIOENCODING behind, and a value the session had before is kept."""
    assert POWERSHELL is not None
    prefix = work / "target"
    script = (
        "$env:UV_NO_CONFIG = 'mine'; "
        f"& '{folder / 'install.ps1'}' -SkipSignatureCheck -Prefix '{prefix}' *> $null; "
        "'code=' + $LASTEXITCODE; 'offline=[' + $env:UV_OFFLINE + ']'; 'io=[' + $env:PYTHONIOENCODING + ']'; "
        "'config=[' + $env:UV_NO_CONFIG + ']'"
    )
    env = {k: v for k, v in _clean_env().items() if k not in ("UV_OFFLINE", "PYTHONIOENCODING")}
    env["PATH"] = r"C:\Windows\System32;C:\Windows\System32\WindowsPowerShell\v1.0"
    result = subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        env=env,
        timeout=300,
        check=False,
    )
    # The installer writes its messages to the console directly; only the session's own lines are compared.
    lines = [
        line.strip()
        for line in result.stdout.decode("utf-8", "replace").splitlines()
        if line.startswith(("code=", "offline=", "io=", "config="))
    ]
    errors = result.stderr.decode("utf-8", "replace")
    assert lines == ["code=2", "offline=[]", "io=[]", "config=[mine]"], errors
    assert not prefix.exists()


def _predict_longest_path(folder: Path, longest: object) -> None:
    info = json.loads((folder / "BUNDLE.json").read_text(encoding="utf-8"))
    info["max_relative_install_path"] = longest
    (folder / "BUNDLE.json").write_text(json.dumps(info, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    _resum(folder)


def _long_paths_enabled() -> bool:
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem")
        return bool(winreg.QueryValueEx(key, "LongPathsEnabled")[0] == 1)
    except OSError:
        return False


def _total_path_limit() -> int:
    """The total path length install.ps1 keeps every installed file within (step 3)."""
    match = re.search(r"\$limit = (\d+) - 1 - \[long\]\$longest", SCRIPT.read_text(encoding="utf-8-sig"))
    assert match, "install.ps1 no longer derives the prefix limit from max_relative_install_path"
    return int(match.group(1))


def test_long_path_guard_applies_whatever_long_paths_enabled_says(folder: Path, work: Path) -> None:
    """Every installed file stays within 250 characters: at the limit the guard lets the installation start
    (the stand-in uv then fails), one character more is refused before anything is created - also with
    LongPathsEnabled = 1 (this machine), where the old guard let a 181-character prefix through and extension
    modules then failed to load (UF-08). The limit counts characters; the Chinese folder name checks that."""
    prefix = work / "安装 目录"
    length = len(str(prefix))
    total = _total_path_limit()
    assert total == 250
    _predict_longest_path(folder, total - 1 - length)
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(prefix))
    assert code == 2 and "install folder path too long" not in text, text
    assert "creating the virtual environment failed" in text or "installation failed" in text
    assert not prefix.exists()
    _predict_longest_path(folder, total - length)
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(prefix))
    assert code == 2, text
    expected = f"install folder path too long ({length} characters, limit {length - 1})"
    assert expected in text, (_long_paths_enabled(), text)
    assert (
        "even with long paths enabled" in text
        and f"安装文件夹路径过长（{length} 个字符，上限 {length - 1}）" in text
    )
    assert not prefix.exists()


@pytest.mark.parametrize("longest", [None, "88", -1, 1.5])
def test_missing_path_prediction_is_an_integrity_error(folder: Path, work: Path, longest: object) -> None:
    _predict_longest_path(folder, longest)
    prefix = work / "t"
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(prefix))
    assert code == 3 and "BUNDLE.json incomplete" in text, text
    assert not prefix.exists()


def _copy_at_length(source: Path, base: Path, total: int) -> Path:
    """A copy of source whose full path has exactly `total` characters (folder names of at most 100)."""
    left = total - len(str(base)) - 1 - len(source.name)  # characters of the folders and their separators
    assert left >= 2, left
    folder = base
    while left > 0:
        part = min(100, left - 1)
        if left - (part + 1) == 1:  # never leave one character, which cannot form a folder and a separator
            part -= 1
        folder = folder / ("d" * part)
        left -= part + 1
    folder.mkdir(parents=True)
    target = folder / source.name
    shutil.copyfile(source, target)
    assert len(str(target)) == total, (len(str(target)), total)
    return target


def test_the_guard_keeps_modules_and_programs_loadable(work: Path) -> None:
    """The allowance of the guard is safe: at the total length it allows, an extension module with an embedded
    manifest (fontTools' bezierTools, the measured case: 250 loads, 251 fails with ERROR_FILENAME_EXCED_RANGE
    even with LongPathsEnabled = 1) loads in a fresh interpreter, and a program starts."""
    import fontTools.misc

    total = _total_path_limit()
    module = _copy_at_length(
        next(Path(fontTools.misc.__file__).parent.glob("bezierTools*.pyd")), work / "m", total
    )
    code = (
        "import importlib.machinery, importlib.util, sys\n"
        "loader = importlib.machinery.ExtensionFileLoader('bezierTools', sys.argv[1])\n"
        "spec = importlib.util.spec_from_file_location('bezierTools', sys.argv[1], loader=loader)\n"
        "importlib.util.module_from_spec(spec)\n"
        "print('loaded')\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, str(module)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0 and result.stdout.strip() == "loaded", result.stderr
    program = _copy_at_length(Path(r"C:\Windows\System32\hostname.exe"), work / "p", total)
    assert subprocess.run([str(program)], capture_output=True, timeout=60, check=False).returncode == 0


def test_install_cmd_passes_exit_codes_through(folder: Path) -> None:
    for args, expected in (([], 4), (["-SkipSignatureCheck"], 0)):
        result = subprocess.run(
            ["cmd.exe", "/c", str(folder / "install.cmd"), "-VerifyOnly", *args],
            capture_output=True,
            check=False,
        )
        assert result.returncode == expected, result.stdout.decode("utf-8", "replace")


def test_installer_names_the_fixed_sentence() -> None:
    text = SCRIPT.read_text(encoding="utf-8-sig")
    assert f"'{disclaimer('zh')}'" in text and f"'{disclaimer('en')}'" in text


def _clean_env() -> dict[str, str]:
    import os

    return {k: v for k, v in os.environ.items() if k.upper() != "PATH"}
