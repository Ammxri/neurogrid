"""packaging/install.ps1 and install.cmd (UF-08, NG-N04, A-26, D-10 g) under Windows PowerShell 5.1 (and
PowerShell 7 when installed) on a stand-in bundle: integrity (exit 3), signature (exit 4), usage and
environment (exit 2), cleanup after a failed installation. The full installation of a real bundle is the clean
room (packaging/ci/cleanroom_windows.ps1). A stand-in cosign (a .cmd that exits 0 or 1) exercises the
signature branch without network."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
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


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("ps1")
    return extract(bundle.build(inputs(tmp, "win_amd64")), tmp / "extracted")


@pytest.fixture
def folder(built: Path, tmp_path: Path) -> Path:
    return Path(shutil.copytree(built, tmp_path / built.name))


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


def _fake_cosign(tmp_path: Path, code: int) -> Path:
    path = tmp_path / "cosign-stand-in" / "cosign.cmd"
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
    folder: Path, tmp_path: Path, tamper: object, expected: str
) -> None:
    tamper(folder)  # type: ignore[operator]
    prefix = tmp_path / "target"
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(prefix))
    assert code == 3, text
    assert expected in text
    assert not prefix.exists()


def test_unsigned_bundle_needs_the_explicit_switch(folder: Path) -> None:
    code, text = _run(folder, "-VerifyOnly")
    assert code == 4, text
    assert "pass -SkipSignatureCheck to continue" in text


def test_signed_bundle_without_cosign_needs_the_switch(folder: Path, tmp_path: Path) -> None:
    _sign(folder)
    env = {**_clean_env(), "PATH": r"C:\Windows\System32;C:\Windows\System32\WindowsPowerShell\v1.0"}
    code, text = _run(folder, "-VerifyOnly", env=env)
    assert code == 4 and "cosign not found" in text, text
    code, text = _run(folder, "-VerifyOnly", "-SkipSignatureCheck", env=env)
    assert code == 0 and "signature not verified here, as requested" in text, text


def test_signed_bundle_with_cosign(folder: Path, tmp_path: Path) -> None:
    _sign(folder)
    good, bad = _fake_cosign(tmp_path / "ok", 0), _fake_cosign(tmp_path / "bad", 1)
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


def test_existing_target_is_never_overwritten(folder: Path, tmp_path: Path) -> None:
    prefix = tmp_path / "target"
    prefix.mkdir()
    (prefix / "keep.txt").write_text("mine", encoding="utf-8")
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(prefix))
    assert code == 2 and "target exists and is not empty" in text, text
    assert [p.name for p in prefix.iterdir()] == ["keep.txt"]


def test_failed_installation_exits_2_and_removes_what_it_created(folder: Path, tmp_path: Path) -> None:
    """The stand-in uv.exe is not a program: creating the venv fails, the new folder is removed again."""
    prefix = tmp_path / "new-target"
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(prefix))
    assert code == 2, text
    assert "installation failed" in text or "creating the virtual environment failed" in text
    assert not prefix.exists()


def test_variables_for_uv_are_restored_in_an_open_session(folder: Path, tmp_path: Path) -> None:
    """Run inside an existing session (not through install.cmd), a failed installation leaves neither the uv
    variables nor PYTHONIOENCODING behind, and a value the session had before is kept."""
    assert POWERSHELL is not None
    prefix = tmp_path / "target"
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


def test_long_path_guard(folder: Path, tmp_path: Path) -> None:
    info = json.loads((folder / "BUNDLE.json").read_text(encoding="utf-8"))
    info["max_relative_install_path"] = 300
    (folder / "BUNDLE.json").write_text(json.dumps(info, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    _resum(folder)
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem")
        enabled = winreg.QueryValueEx(key, "LongPathsEnabled")[0] == 1
    except OSError:
        enabled = False
    code, text = _run(folder, "-SkipSignatureCheck", "-Prefix", str(tmp_path / "t"))
    assert code == 2, text
    assert ("install path too long" in text) is not enabled  # the guard applies only without long paths


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
