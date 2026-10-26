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


# GitHub's Windows runners start every step under PowerShell 7 (pwsh), and Windows PowerShell 5.1 started from
# there (as these tests and install.cmd do) inherits pwsh's module path: PowerShell 7's own
# Microsoft.PowerShell.Utility comes first and does not load under 5.1, so the commands of 5.1's script module
# (Get-FileHash among them) are "not recognized" - 17 failures of CI run 40355705974. A user who starts
# install.cmd from a PowerShell 7 window gets the same. Every PowerShell of this module runs with a stand-in
# of that module first on the module path, so the runner's condition holds on any machine. Like PowerShell 7's
# manifest, the stand-in lists every cmdlet of the module (Get-FileHash and Format-Hex are cmdlets there) and
# names the module's assembly: the first Utility cmdlet the installer runs (ConvertFrom-Json) imports it, the
# assembly resolves to Windows PowerShell's own, and Get-FileHash, a function of 5.1's script module, is then
# missing (measured: a stand-in that lists fewer cmdlets is passed over and hides nothing).
PWSH_UTILITY_MANIFEST = """@{{
GUID = "1DA87E53-152B-403E-98DC-74D7B4D63D59"
ModuleVersion = "7.0.0.0"
CompatiblePSEditions = @("Core")
PowerShellVersion = "3.0"
CmdletsToExport = "Get-FileHash", "Format-Hex", {cmdlets}
FunctionsToExport = @()
NestedModules = "Microsoft.PowerShell.Commands.Utility.dll"
}}
"""


def _utility_cmdlets() -> str:
    """The cmdlet list of Windows PowerShell 5.1's own Microsoft.PowerShell.Utility manifest."""
    import os

    module = "Microsoft.PowerShell.Utility"
    manifest = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / f"System32/WindowsPowerShell/v1.0/Modules/{module}/{module}.psd1"
    )
    text = manifest.read_text(encoding="latin-1")  # ANSI ("©"); only the ASCII cmdlet names are used
    match = re.search(r"CmdletsToExport\s*=(.*?)\n\s*FunctionsToExport", text, re.S)
    assert match and "ConvertFrom-Json" in match.group(1), manifest
    return " ".join(match.group(1).split())


@pytest.fixture(scope="module", autouse=True)
def pwsh_module_path(short_root: Path) -> Iterator[str]:
    """PSModulePath as a PowerShell 7 parent hands it on: its own module folder (here the stand-in) first."""
    import os

    folder = short_root / "pwsh7" / "Modules"
    manifest = folder / "Microsoft.PowerShell.Utility" / "Microsoft.PowerShell.Utility.psd1"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(PWSH_UTILITY_MANIFEST.format(cmdlets=_utility_cmdlets()), encoding="utf-8")
    saved = os.environ.get("PSModulePath")
    os.environ["PSModulePath"] = os.pathsep.join(filter(None, [str(folder), saved]))
    try:
        yield os.environ["PSModulePath"]
    finally:
        if saved is None:
            os.environ.pop("PSModulePath", None)
        else:
            os.environ["PSModulePath"] = saved


def test_the_runner_module_path_hides_script_module_commands() -> None:
    """The stand-in has the runner's effect: under it, Windows PowerShell 5.1 cannot find Get-FileHash (the
    command the installer used to hash files with), while the engine's own commands still work."""
    assert POWERSHELL is not None
    probe = (
        "('{\"a\": 1}' | ConvertFrom-Json).a; "
        "(@(Get-Command Get-FileHash -ErrorAction SilentlyContinue)).Count"
    )
    result = subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-Command", probe], capture_output=True, text=True, check=False
    )
    assert result.stdout.split() == ["1", "0"], (result.stdout, result.stderr)


SCRIPT_MODULE_COMMANDS = (
    "Get-FileHash",
    "Expand-Archive",
    "Compress-Archive",
    "New-TemporaryFile",
    "Format-Hex",
)


def test_installer_uses_no_command_of_a_script_module() -> None:
    """Get-FileHash and the other functions of Windows PowerShell 5.1's script modules are unreachable under
    a PowerShell 7 parent (see above); the installer, the Windows clean room and the workflows hash with
    .NET."""
    scripts = [SCRIPT, ROOT / "packaging" / "ci" / "cleanroom_windows.ps1"]
    scripts += sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    for path in scripts:
        text = path.read_text(encoding="utf-8-sig")
        for command in SCRIPT_MODULE_COMMANDS:
            assert not re.search(rf"^[^#]*\b{command}\b", text, re.M), (path.name, command)
    for path in scripts[:2]:
        assert "[System.Security.Cryptography.SHA256]::Create()" in path.read_text(encoding="utf-8-sig")


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


def _run_streams(
    folder: Path,
    *args: str,
    shell: str | None = None,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> tuple[int, str, str]:
    """(exit code, standard output, standard error) of install.ps1 with `args`."""
    assert POWERSHELL is not None
    command = [shell or POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
    result = subprocess.run(
        [*command, str(folder / "install.ps1"), *args],
        capture_output=True,
        env=env,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        timeout=300,
        check=False,
    )
    out, err = (stream.decode("utf-8", "replace") for stream in (result.stdout, result.stderr))
    return result.returncode, out, err


def _run(
    folder: Path,
    *args: str,
    shell: str | None = None,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> tuple[int, str]:
    code, out, err = _run_streams(folder, *args, shell=shell, env=env, cwd=cwd)
    return code, out + err


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
    # Review R12: the identity comes from the bundle itself; the installer says to compare it with the
    # identity the project publishes.
    assert (
        "compare this signer identity with the one in the release notes on the project's release page "
        "(https://github.com/Ammxri/neurogrid/releases)"
    ) in text
    code, text = _run(folder, "-VerifyOnly", "-Cosign", str(bad))
    assert code == 4 and "signature check failed" in text, text
    on_path = {**_clean_env(), "PATH": f"{bad.parent};C:\\Windows\\System32"}
    code, text = _run(folder, "-VerifyOnly", env=on_path)
    assert code == 4, text  # a cosign on PATH is used
    assert "does not skip the check of a cosign found on PATH" not in text
    # D-15 (review R16): with cosign there the signature is checked; the switch only lets an installation
    # without cosign go on, so it no longer overrides a cosign on PATH that rejected the bundle.
    code, text = _run(folder, "-VerifyOnly", "-SkipSignatureCheck", env=on_path)
    assert code == 4 and "signature check failed; nothing installed" in text, text
    assert "-SkipSignatureCheck does not skip the check of a cosign found on PATH" in text
    assert "verified only" not in text
    good_on_path = {**_clean_env(), "PATH": f"{good.parent};C:\\Windows\\System32"}
    code, text = _run(folder, "-VerifyOnly", "-SkipSignatureCheck", env=good_on_path)
    assert code == 0 and "signature verified: https://github.com/owner/neurogrid/" in text, text
    assert "stand-in cosign verify-blob" in text and "as requested" not in text


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
        # Review R17: drive-relative, resolved against the current folder of drive C: (not an absolute path)
        (["-SkipSignatureCheck", "-Prefix", "C:relative\\folder"], "absolute local path"),
        (["-SkipSignatureCheck", "-Prefix", "//server/share/ng"], "absolute local path"),
    ],
)
def test_usage_and_environment_errors_exit_2(folder: Path, args: list[str], expected: str) -> None:
    code, text = _run(folder, *args)
    assert code == 2, text
    assert expected in text


def test_a_relative_cosign_is_the_named_file(folder: Path, work: Path) -> None:
    """Review R17: '-Cosign cosign.cmd' (a file in the current folder) passed Test-Path, but '& $Cosign'
    looked the bare name up on PATH: another cosign ran, or the run ended in 'installation failed'. The named
    file verifies; a cosign on PATH that would reject the bundle is not asked."""
    _sign(folder)
    here = work / "here"
    here.mkdir()
    shutil.copyfile(_fake_cosign(work / "good", 0), here / "cosign.cmd")
    bad = _fake_cosign(work / "bad", 1)
    env = {**_clean_env(), "PATH": f"{bad.parent};C:\\Windows\\System32"}
    code, text = _run(folder, "-VerifyOnly", "-Cosign", "cosign.cmd", env=env, cwd=here)
    assert code == 0 and "signature verified: https://github.com/owner/neurogrid/" in text, text
    code, text = _run(folder, "-VerifyOnly", "-Cosign", "absent.cmd", env=env, cwd=here)
    assert code == 2 and "cosign not found: absent.cmd" in text, text


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


# A stand-in uv that works, so the installer runs to its end without the real uv and interpreter: uv.exe is a
# copy of this test run's venv launcher (python.exe of a venv, which starts the base interpreter named by the
# pyvenv.cfg next to it), and `uv venv ...` / `uv pip ...` then run the packages venv/ and pip/ of the working
# folder. `uv venv` creates <venv>\Scripts with the launcher as python.exe and neurogrid.exe, so the
# installer's self-test (neurogrid.cmd --help = python --help) passes; `uv pip` exits with
# NG_STAND_IN_PIP_EXIT (default 0).
STAND_IN_VENV = """import shutil
import sys
from pathlib import Path

venv = Path(sys.argv[-1])
launcher = Path(sys.executable)
(venv / "Scripts").mkdir(parents=True)
for name in ("python.exe", "neurogrid.exe"):
    shutil.copyfile(launcher, venv / "Scripts" / name)
shutil.copyfile(launcher.parent / "pyvenv.cfg", venv / "pyvenv.cfg")
"""
# A failing `uv pip` names its cache and the user's settings the way the real uv names paths in its errors.
STAND_IN_PIP = r"""import os, sys
code = int(os.environ.get("NG_STAND_IN_PIP_EXIT", "0"))
if code:
    print("error: failed to read " + os.environ["UV_CACHE_DIR"] + "\\wheels", file=sys.stderr)
    print("hint: settings in " + os.environ.get("USERPROFILE", "") + "\\uv.toml")
sys.exit(code)
"""


@pytest.fixture
def installable(folder: Path, work: Path) -> tuple[Path, Path]:
    """(bundle folder with the working stand-in uv, working folder to run the installer in)."""
    launcher = Path(sys.executable)
    config = Path(sys.prefix) / "pyvenv.cfg"
    if not config.is_file():
        pytest.skip("the tests do not run in a virtual environment: no venv launcher to copy")
    shutil.copyfile(launcher, folder / "uv" / "uv.exe")
    shutil.copyfile(config, folder / "uv" / "pyvenv.cfg")
    _resum(folder)
    cwd = work / "cwd"
    for name, text in (("venv", STAND_IN_VENV), ("pip", STAND_IN_PIP)):
        (cwd / name).mkdir(parents=True)
        (cwd / name / "__main__.py").write_text(text, encoding="utf-8")
    probe = subprocess.run(
        [str(folder / "uv" / "uv.exe"), "-c", "print('ok')"], capture_output=True, text=True, check=False
    )
    if probe.stdout.strip() != "ok":
        pytest.skip(f"the copied venv launcher does not start: {probe.stderr}")
    return folder, cwd


def _short_path(path: Path) -> str:
    """The 8.3 spelling of an existing path (the same text where the volume makes no short names)."""
    import ctypes

    buffer = ctypes.create_unicode_buffer(1024)
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    length = kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    return buffer.value if 0 < length < len(buffer) else str(path)


def test_the_working_stand_in_installs_to_the_end(installable: tuple[Path, Path], work: Path) -> None:
    folder, cwd = installable
    prefix = work / "ok"
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(prefix), cwd=cwd)
    assert code == 0, text
    assert (prefix / "neurogrid.cmd").is_file() and (prefix / "BUNDLE.json").is_file()
    assert (prefix / "venv" / "Scripts" / "neurogrid.exe").is_file() and not (prefix / ".uv-cache").exists()
    assert disclaimer("en") in text


def test_console_names_no_user_folder(installable: tuple[Path, Path], short_root: Path) -> None:
    """A-51 (review R13): with the default prefix below %LOCALAPPDATA% the installer printed the full path
    with the user name ('installed: C:\\Users\\<name>\\AppData\\Local\\NeuroGrid\\...'). Like NeuroGrid's own
    console, it shows %LOCALAPPDATA% and ~, also for the 8.3 spelling (C:\\Users\\RUNNER~1 on GitHub's
    runners) and another letter case."""
    import os

    folder, cwd = installable
    home = Path(tempfile.mkdtemp(prefix="h", dir=short_root)) / "Users" / "runneradmin"
    local = home / "AppData" / "Local"
    local.mkdir(parents=True)
    env = {**os.environ, "USERPROFILE": str(home), "LOCALAPPDATA": str(local)}
    env.pop("NEUROGRID_PDF_BROWSER_DIR", None)
    code, text = _run(folder, "-SkipSignatureCheck", env=env, cwd=cwd)
    assert code == 0, text
    assert "installed: %LOCALAPPDATA%\\NeuroGrid\\9.8.7\\neurogrid.cmd" in text
    assert "已安装：%LOCALAPPDATA%\\NeuroGrid\\9.8.7\\neurogrid.cmd" in text
    assert (
        "uninstall: delete the folder %LOCALAPPDATA%\\NeuroGrid\\9.8.7 "
        "(and %LOCALAPPDATA%\\NeuroGrid\\pdf-browser if the PDF browser was installed)"
    ) in text
    assert "runneradmin" not in text.lower(), text
    spellings = {str(local).upper() + "\\NeuroGrid\\9.8.7", _short_path(local) + "\\NeuroGrid\\9.8.7"}
    for spelling in sorted(spellings):
        code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", spelling, env=env, cwd=cwd)
        assert code == 2, text
        assert "target exists and is not empty: %LOCALAPPDATA%\\NeuroGrid\\9.8.7 (" in text, text
        assert "RUNNERADMIN" not in text.upper() and "RUNNER~" not in text.upper(), text
    outside = {**env, "LOCALAPPDATA": str(short_root / "elsewhere")}
    prefix = home / "ng" / "x"
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(prefix), env=outside, cwd=cwd)
    assert code == 0 and "installed: ~\\ng\\x\\neurogrid.cmd" in text, text


def test_program_output_names_no_user_folder(
    installable: tuple[Path, Path], short_root: Path, work: Path
) -> None:
    """A-51 (verification of review R13): Invoke-Native passed what uv, cosign and Python printed to the
    console unchanged (Out-Host, error output as it came), so a failing uv showed the user folder in its
    cache path %LOCALAPPDATA%\\NeuroGrid\\<version>\\.uv-cache. Their output and their errors go through Show
    now, each on its own stream, under Windows PowerShell 5.1 and PowerShell 7."""
    import os

    folder, cwd = installable
    home = Path(tempfile.mkdtemp(prefix="p", dir=short_root)) / "Users" / "runneradmin"
    local = home / "AppData" / "Local"
    local.mkdir(parents=True)
    env = {**os.environ, "USERPROFILE": str(home), "LOCALAPPDATA": str(local), "NG_STAND_IN_PIP_EXIT": "1"}
    code, out, err = _run_streams(folder, "-SkipSignatureCheck", env=env, cwd=cwd)
    assert code == 2 and "offline installation failed (uv exit code 1)" in err, out + err
    assert "error: failed to read %LOCALAPPDATA%\\NeuroGrid\\9.8.7\\.uv-cache\\wheels" in err, err
    assert "hint: settings in ~\\uv.toml" in out, out
    assert "runneradmin" not in (out + err).lower(), out + err
    assert not (local / "NeuroGrid").exists()
    _sign(folder)
    cosign = work / "talkative" / "cosign.cmd"
    cosign.parent.mkdir()
    cosign.write_text(
        "@echo off\r\necho trust root: %LOCALAPPDATA%\\sigstore\\root\r\n"
        "1>&2 echo error: cannot open %USERPROFILE%\\.sigstore\\targets.json\r\nexit /b 1\r\n",
        encoding="ascii",
    )
    for shell in filter(None, (POWERSHELL, PWSH)):
        code, out, err = _run_streams(folder, "-VerifyOnly", "-Cosign", str(cosign), shell=shell, env=env)
        assert code == 4 and "signature check failed" in err, (shell, out + err)
        assert "trust root: %LOCALAPPDATA%\\sigstore\\root" in out, (shell, out)
        assert "error: cannot open ~\\.sigstore\\targets.json" in err, (shell, err)
        assert "runneradmin" not in (out + err).lower(), (shell, out + err)


def _show(text: str, env: dict[str, str]) -> str:
    """install.ps1's Show applied to `text` in a Windows PowerShell with `env`."""
    assert POWERSHELL is not None
    source = SCRIPT.read_text(encoding="utf-8-sig")
    (function,) = re.findall(r"^function Show\(.*?^}\n", source, re.M | re.S)
    escaped = text.replace("'", "''")
    script = f"$ErrorActionPreference = 'Stop'\n$script:hidden = $null\n{function}Show '{escaped}'\n"
    done = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.rstrip("\r\n")


def test_show_replaces_only_whole_user_folders(short_root: Path) -> None:
    """Show also cleans foreign text (the message of an unexpected exception): every occurrence, any case,
    but only whole folder names."""
    import os

    home = Path(tempfile.mkdtemp(prefix="s", dir=short_root)) / "runneradmin"
    (home / "AppData" / "Local").mkdir(parents=True)
    env = {**os.environ, "USERPROFILE": str(home), "LOCALAPPDATA": str(home / "AppData" / "Local")}
    sample = (
        f"Access to the path '{home}\\AppData\\Local\\NeuroGrid\\x' is denied. In {str(home).upper()}\\"
        f"b\\install.ps1:38; {home}x\\y; {_short_path(home)}\\z"
    )
    shown = _show(sample, env)
    expected = "Access to the path '%LOCALAPPDATA%\\NeuroGrid\\x' is denied. In ~\\b\\install.ps1:38; "
    assert shown.startswith(expected), shown
    assert f"{home}x\\y" in shown  # another folder that only starts with the home folder's name
    assert shown.endswith("; ~\\z"), shown
    assert _show("C:\\data\\set", env) == "C:\\data\\set"
    bare = {k: v for k, v in env.items() if k.upper() not in ("USERPROFILE", "LOCALAPPDATA")}
    assert _show(f"{home}\\q", bare) == f"{home}\\q"  # nothing to hide, no error


def test_a_failed_installation_leaves_the_target_as_it_was(
    installable: tuple[Path, Path], work: Path
) -> None:
    """Review R14: a failure into an existing empty folder left python\\ (and the venv) behind, so a retry
    stopped at 'target exists and is not empty'; parents the installer created stayed too. Now the empty
    folder is empty again and the retry runs to its end; created parents go again."""
    import os

    folder, cwd = installable
    failing = {**os.environ, "NG_STAND_IN_PIP_EXIT": "1"}
    empty = work / "empty"
    empty.mkdir()
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(empty), env=failing, cwd=cwd)
    assert code == 2 and "offline installation failed (uv exit code 1)" in text, text
    assert empty.is_dir() and list(empty.iterdir()) == []
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(empty), cwd=cwd)
    assert code == 0 and "target exists" not in text, text
    assert (empty / "neurogrid.cmd").is_file()
    shared = work / "shared"
    shared.mkdir()
    prefix = shared / "NeuroGrid" / "9.8.7"
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(prefix), env=failing, cwd=cwd)
    assert code == 2, text
    assert shared.is_dir() and list(shared.iterdir()) == []  # NeuroGrid\9.8.7 and NeuroGrid\ went again
    (shared / "NeuroGrid").mkdir()
    (shared / "NeuroGrid" / "pdf-browser").mkdir()  # content of the parent that the installer did not create
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(prefix), env=failing, cwd=cwd)
    assert code == 2, text
    assert [p.name for p in (shared / "NeuroGrid").iterdir()] == ["pdf-browser"]


def test_readme_windows_commands_run_as_printed_in_powershell(folder: Path, short_root: Path) -> None:
    """Review R18: README.txt headed its Windows section PowerShell but printed cmd.exe syntax ('install.cmd'
    is not found in the current folder, %LOCALAPPDATA% is not expanded). Its install, check and report lines
    run as printed in Windows PowerShell 5.1 in the unpacked folder (placeholders filled in), with the working
    stand-in uv and stand-ins of the check and report commands (the launcher's interpreter runs the packages
    check/ and report/ of the current folder)."""
    import os

    if not (Path(sys.prefix) / "pyvenv.cfg").is_file():
        pytest.skip("the tests do not run in a virtual environment: no venv launcher to copy")
    assert POWERSHELL is not None
    shutil.copyfile(sys.executable, folder / "uv" / "uv.exe")
    shutil.copyfile(Path(sys.prefix) / "pyvenv.cfg", folder / "uv" / "pyvenv.cfg")
    command = 'import sys\nprint("ran", sys.argv[1:])\n'
    for name, text in (
        ("venv", STAND_IN_VENV),
        ("pip", STAND_IN_PIP),
        ("check", command),
        ("report", command),
    ):
        (folder / name).mkdir()
        (folder / name / "__main__.py").write_text(text, encoding="utf-8")
    _resum(folder)
    readme = (folder / "README.txt").read_text(encoding="utf-8")
    lines = [line.strip() for line in readme.splitlines() if line.startswith("     ")]
    (install,) = [line for line in lines if line.startswith(".\\install.cmd -SkipSignatureCheck")]
    install = install.split("   ")[0]  # the explanation after the command
    check = next(line for line in lines if 'neurogrid.cmd" check' in line)
    report = next(line for line in lines if 'neurogrid.cmd" report' in line)
    data = folder / "数据 集"
    check = check.replace("<数据集 / dataset>", f"'{data}'")
    local = Path(tempfile.mkdtemp(prefix="l", dir=short_root))
    script = "\n".join(
        [
            f"Set-Location -LiteralPath '{folder}'",
            install,
            "'install=' + $LASTEXITCODE",
            check,
            "'check=' + $LASTEXITCODE",
            report,
            "'report=' + $LASTEXITCODE",
        ]
    )
    env = {**os.environ, "LOCALAPPDATA": str(local), "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        env=env,
        stdin=subprocess.DEVNULL,
        timeout=300,
        check=False,
    )
    text = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
    assert "install=0" in text and "check=0" in text and "report=0" in text, text
    assert f"ran {[str(data), '--out', 'results.json']}" in text, text
    assert "ran ['results.json', '--lang', 'zh,en', '--format', 'html']" in text, text
    assert (local / "NeuroGrid" / "9.8.7" / "neurogrid.cmd").is_file()
