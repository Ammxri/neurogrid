"""packaging/install.sh and the CI shell scripts (UF-08, NG-N04, A-26, A-58, D-10 g) with bash: Git Bash on
Windows, bash on Linux (CI). A stand-in Linux bundle without links checks integrity (exit 3), signature (exit
4), usage and platform (exit 2); the glibc rule is checked through the script's own function. The real
installation runs in the Linux clean room (packaging/ci/cleanroom_linux.sh, CI only, D-09)."""

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
SCRIPT = ROOT / "packaging" / "install.sh"
CI_SCRIPTS = sorted((ROOT / "packaging" / "ci").glob("*.sh"))


def _bash() -> str | None:
    """Git Bash on Windows (the bash.exe in System32 belongs to WSL and sees other paths); bash elsewhere."""
    if sys.platform != "win32":
        return shutil.which("bash")
    git = shutil.which("git")
    if git is None:
        return None
    for base in Path(git).resolve().parents[:3]:
        candidate = base / "bin" / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    return None


BASH = _bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("sh")
    archive = bundle.build(inputs(tmp, "linux_x86_64", links=False, case_pair=False))
    return extract(archive, tmp / "extracted")


@pytest.fixture
def folder(built: Path, tmp_path: Path) -> Path:
    return Path(shutil.copytree(built, tmp_path / built.name))


def _run(folder: Path, *args: str) -> tuple[int, str]:
    assert BASH is not None
    result = subprocess.run(
        [BASH, (folder / "install.sh").as_posix(), *args], capture_output=True, timeout=300, check=False
    )
    return result.returncode, result.stdout.decode("utf-8", "replace") + result.stderr.decode(
        "utf-8", "replace"
    )


def _source(code: str) -> str:
    assert BASH is not None
    script = f'source "{SCRIPT.as_posix()}"\n{code}\n'
    result = subprocess.run([BASH, "-c", script], capture_output=True, timeout=60, check=False)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    return result.stdout.decode("utf-8", "replace")


def _resum(folder: Path) -> None:
    lines = []
    for path in folder.rglob("*"):
        rel = path.relative_to(folder).as_posix()
        if path.is_file() and rel not in ("SHA256SUMS", "SHA256SUMS.sigstore.json"):
            lines.append((rel, f"{bundle.sha256_file(path)}  {rel}\n"))
    (folder / "SHA256SUMS").write_bytes("".join(line for _, line in sorted(lines)).encode())


def test_scripts_have_valid_bash_syntax() -> None:
    assert BASH is not None
    for script in [SCRIPT, *CI_SCRIPTS]:
        result = subprocess.run([BASH, "-n", script.as_posix()], capture_output=True, text=True, check=False)
        assert result.returncode == 0, (script.name, result.stderr)
    assert {s.name for s in CI_SCRIPTS} == {
        "cleanroom_inside.sh",
        "cleanroom_linux.sh",
        "offline_strace_linux.sh",
        "pdf_debian12.sh",
    }


def test_scripts_use_lf_line_endings() -> None:
    for script in [SCRIPT, *CI_SCRIPTS]:
        assert b"\r\n" not in script.read_bytes(), script.name


def test_glibc_rule_of_a58() -> None:
    out = _source(
        "for v in 2.27 2.17 2.28 2.31 2.36 2.39 3.0 '' unknown 2 2.x; do"
        ' if glibc_supported "$v"; then echo "$v yes"; else echo "$v no"; fi; done'
    )
    answers = dict(line.rsplit(" ", 1) for line in out.splitlines())
    assert answers == {
        "2.27": "no", "2.17": "no", "2.28": "yes", "2.31": "yes", "2.36": "yes", "2.39": "yes", "3.0": "yes",
        "": "no", "unknown": "no", "2": "no", "2.x": "no",
    }  # fmt: skip


def test_bundle_fields_are_read_from_bundle_json(folder: Path) -> None:
    out = _source(
        f'f="{folder.as_posix()}"; bundle_field "$f" version; bundle_field "$f" platform;'
        ' bundle_field "$f" release_identity; bundle_field "$f" max_relative_install_path'
    )
    info = json.loads((folder / "BUNDLE.json").read_text(encoding="utf-8"))
    assert out.splitlines() == ["9.8.7", "linux_x86_64", "null", str(info["max_relative_install_path"])]


def test_verify_only_passes_on_an_intact_bundle(folder: Path) -> None:
    code, text = _run(folder, "--verify-only", "--skip-signature-check")
    assert code == 0, text
    assert "integrity verified" in text and "verified only, nothing installed" in text


@pytest.mark.parametrize(
    "tamper, expected",
    [
        (lambda f: (f / "LICENSE").write_text("changed", encoding="utf-8"), "files do not match SHA256SUMS"),
        (lambda f: (f / "NOTICE").unlink(), "files do not match SHA256SUMS"),
        (
            lambda f: (f / "docs" / "extra.html").write_text("x", encoding="utf-8"),
            "unlisted files present: docs/extra.html",
        ),
        (lambda f: (f / "SHA256SUMS").write_bytes(b"not a checksum line\n"), "malformed SHA256SUMS line"),
        (lambda f: (f / "SHA256SUMS").unlink(), "SHA256SUMS missing"),
    ],
)
def test_integrity_problems_exit_3(folder: Path, tamper: object, expected: str) -> None:
    tamper(folder)  # type: ignore[operator]
    code, text = _run(folder, "--verify-only", "--skip-signature-check")
    assert code == 3, text
    assert expected in text


def test_recorded_links_must_match(folder: Path) -> None:
    (folder / "SYMLINKS").write_text("python/bin/python3 -> python3.12\n", encoding="utf-8")
    _resum(folder)
    code, text = _run(folder, "--verify-only", "--skip-signature-check")
    assert code == 3 and "symbolic links differ from SYMLINKS" in text, text


def test_signature_branch(folder: Path, tmp_path: Path) -> None:
    code, text = _run(folder, "--verify-only")
    assert code == 4 and "pass --skip-signature-check to continue" in text, text
    info = json.loads((folder / "BUNDLE.json").read_text(encoding="utf-8"))
    info["release_identity"] = (
        "https://github.com/owner/neurogrid/.github/workflows/release.yml@refs/tags/v9.8.7"
    )
    (folder / "BUNDLE.json").write_text(json.dumps(info, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (folder / "SHA256SUMS.sigstore.json").write_text("{}", encoding="utf-8")
    _resum(folder)
    for code_, name in ((0, "good"), (1, "bad")):
        stand_in = tmp_path / f"cosign-{name}"
        stand_in.write_text(
            f'#!/bin/sh\necho stand-in cosign "$@"\nexit {code_}\n', encoding="utf-8", newline="\n"
        )
        stand_in.chmod(0o755)
        code, text = _run(folder, "--verify-only", "--cosign", stand_in.as_posix())
        if code_ == 0:
            assert code == 0 and "signature verified: https://github.com/owner/neurogrid/" in text, text
            assert "--certificate-oidc-issuer https://token.actions.githubusercontent.com" in text
        else:
            assert code == 4 and "signature check failed" in text, text
    code, text = _run(folder, "--verify-only", "--skip-signature-check")
    assert code == 0 and "signature not verified here, as requested" in text, text


@pytest.mark.parametrize(
    "args, expected",
    [
        (["--bogus"], "unknown option: --bogus"),
        (["--prefix"], "--prefix needs a value"),
        (["--cosign", "/x/cosign", "--skip-signature-check"], "exclude each other"),
        (["--pdf-browser-zip", "/x/shell.zip"], "--pdf-browser-zip needs --pdf-browser-sha256"),
        (["--pdf-browser-zip", "/does/not/exist.zip", "--pdf-browser-sha256", "a" * 64], "file not found"),
    ],
)
def test_usage_errors_exit_2(folder: Path, args: list[str], expected: str) -> None:
    code, text = _run(folder, *args)
    assert code == 2, text
    assert expected in text


def test_install_refuses_or_cleans_up(folder: Path, tmp_path: Path) -> None:
    """Under Git Bash the platform check refuses (exit 2); on Linux the stand-in uv cannot run, so the
    installation fails with exit 2 and the folder it created is removed again."""
    prefix = tmp_path / "target"
    code, text = _run(folder, "--skip-signature-check", "--prefix", prefix.as_posix())
    assert code == 2, text
    if sys.platform == "win32":
        assert "only Linux x86_64 is supported" in text
    assert not prefix.exists()


def test_relative_prefix_is_refused_on_linux(folder: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("the platform check of install.sh comes first under Git Bash")
    code, text = _run(folder, "--skip-signature-check", "--prefix", "relative/folder")
    assert code == 2 and "must be an absolute path" in text, text


def test_help_and_fixed_sentence() -> None:
    assert BASH is not None
    result = subprocess.run([BASH, SCRIPT.as_posix(), "--help"], capture_output=True, check=False)
    assert result.returncode == 0 and b"--pdf-browser-zip" in result.stdout
    text = SCRIPT.read_text(encoding="utf-8")
    assert f'"{disclaimer("zh")}"' in text and f'"{disclaimer("en")}"' in text
