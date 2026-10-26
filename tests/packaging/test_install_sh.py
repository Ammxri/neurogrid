"""packaging/install.sh and the CI shell scripts (UF-08, NG-N04, A-26, A-58, D-10 g) with bash: Git Bash on
Windows, bash on Linux (CI). A stand-in Linux bundle without links checks integrity (exit 3), signature (exit
4), usage and platform (exit 2); the glibc rule is checked through the script's own function. The real
installation runs in the Linux clean room (packaging/ci/cleanroom_linux.sh, CI only, D-09)."""

from __future__ import annotations

import json
import os
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


def _run(folder: Path, *args: str, env: dict[str, str] | None = None) -> tuple[int, str]:
    assert BASH is not None
    result = subprocess.run(
        [BASH, (folder / "install.sh").as_posix(), *args],
        capture_output=True,
        env=env,
        timeout=300,
        check=False,
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
    # D-15 (review R16): a cosign found on PATH verifies, also with --skip-signature-check, which only lets an
    # installation without cosign go on; a rejection is no longer overridden by the switch.
    for code_, name in ((1, "bad"), (0, "good")):
        on_path = tmp_path / f"path-{name}"
        on_path.mkdir()
        shutil.copyfile(tmp_path / f"cosign-{name}", on_path / "cosign")
        (on_path / "cosign").chmod(0o755)
        env = {**os.environ, "PATH": os.pathsep.join([str(on_path), os.environ.get("PATH", "")])}
        code, text = _run(folder, "--verify-only", "--skip-signature-check", env=env)
        if code_ == 0:
            assert code == 0 and "signature verified: https://github.com/owner/neurogrid/" in text, text
            assert "stand-in cosign verify-blob" in text and "as requested" not in text
        else:
            assert code == 4 and "signature check failed; nothing installed" in text, text
            assert "--skip-signature-check does not skip the check of a cosign found on PATH" in text
            assert "verified only" not in text


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


def test_a_relative_cosign_is_the_named_file(folder: Path, tmp_path: Path) -> None:
    """Review R17: a relative --cosign was checked after the script had changed into the bundle folder, and a
    bare name ran whatever cosign PATH held. It names a file of the current folder."""
    assert BASH is not None
    info = json.loads((folder / "BUNDLE.json").read_text(encoding="utf-8"))
    info["release_identity"] = (
        "https://github.com/owner/neurogrid/.github/workflows/release.yml@refs/tags/v9.8.7"
    )
    (folder / "BUNDLE.json").write_text(json.dumps(info, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (folder / "SHA256SUMS.sigstore.json").write_text("{}", encoding="utf-8")
    _resum(folder)
    here, elsewhere = tmp_path / "here", tmp_path / "path"
    for place, code_ in ((here, 0), (elsewhere, 1)):
        place.mkdir()
        (place / "cosign").write_text(
            f'#!/bin/sh\necho stand-in cosign "$@"\nexit {code_}\n', encoding="utf-8", newline="\n"
        )
        (place / "cosign").chmod(0o755)
    env = {**os.environ, "PATH": os.pathsep.join([str(elsewhere), os.environ.get("PATH", "")])}
    for name in ("cosign", "./cosign"):
        result = subprocess.run(
            [BASH, (folder / "install.sh").as_posix(), "--verify-only", "--cosign", name],
            capture_output=True,
            cwd=here,
            env=env,
            timeout=300,
            check=False,
        )
        text = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
        assert result.returncode == 0 and "signature verified: https://github.com/owner/" in text, (
            name,
            text,
        )


def _bash_path(path: Path) -> str:
    """The absolute path as bash sees it (/c/... under Git Bash on Windows)."""
    text = path.as_posix()
    if sys.platform == "win32" and len(text) > 2 and text[1] == ":":
        return f"/{text[0].lower()}{text[2:]}"
    return text


def _run_as_linux_x86_64(folder: Path, *args: str, env: dict[str, str] | None = None) -> tuple[int, str]:
    """install.sh's main with uname and getconf replaced by shell functions that report Linux x86_64 with
    glibc 2.36, so the installer gets past its platform check on any machine (Git Bash's wrapper puts its own
    /usr/bin first on PATH, so stand-in programs could not win)."""
    assert BASH is not None
    script = (
        'uname() { case "$1" in -m) echo x86_64 ;; *) echo Linux ;; esac; }\n'
        "getconf() { echo glibc 2.36; }\n"
        f'source "{(folder / "install.sh").as_posix()}"\n'
        'main "$@"\n'
    )
    result = subprocess.run(
        [BASH, "-c", script, "install.sh", *args], capture_output=True, env=env, timeout=300, check=False
    )
    return result.returncode, result.stdout.decode("utf-8", "replace") + result.stderr.decode(
        "utf-8", "replace"
    )


def test_prefix_length_guard_counts_bytes_against_path_max(folder: Path, tmp_path: Path) -> None:
    """Every installed path fits into PATH_MAX (4096 bytes with the closing NUL): the prefix may have at most
    4094 bytes minus BUNDLE.json's longest relative path. At the limit the installation starts (the stand-in
    uv then fails and the folder is removed); one byte more is refused with exit 2 before anything is
    created. The Chinese folder name proves that bytes are counted, not characters."""
    target = tmp_path / "安装 目录"
    prefix = _bash_path(target)
    length = len(prefix.encode("utf-8"))
    info = json.loads((folder / "BUNDLE.json").read_text(encoding="utf-8"))
    for longest, refused in ((4094 - length, False), (4095 - length, True)):
        info["max_relative_install_path"] = longest
        (folder / "BUNDLE.json").write_text(
            json.dumps(info, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
        _resum(folder)
        code, text = _run_as_linux_x86_64(folder, "--skip-signature-check", "--prefix", prefix)
        assert code == 2, text
        assert "only Linux x86_64 is supported" not in text, text  # the stand-ins took effect
        if refused:
            assert f"install folder path too long ({length} bytes, limit {length - 1})" in text, text
            assert f"安装文件夹路径过长（{length} 字节，上限 {length - 1}）" in text, text
        else:
            assert "install folder path too long" not in text, text
            assert "creating the virtual environment failed" in text, text
        assert not target.exists()


@pytest.mark.parametrize("longest", [None, -1, 1.5])
def test_incomplete_path_prediction_is_an_integrity_error(
    folder: Path, tmp_path: Path, longest: object
) -> None:
    info = json.loads((folder / "BUNDLE.json").read_text(encoding="utf-8"))
    info["max_relative_install_path"] = longest
    (folder / "BUNDLE.json").write_text(json.dumps(info, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    _resum(folder)
    target = tmp_path / "target"
    code, text = _run_as_linux_x86_64(folder, "--skip-signature-check", "--prefix", _bash_path(target))
    assert code == 3 and "BUNDLE.json incomplete" in text, text
    assert not target.exists()


def test_help_and_fixed_sentence() -> None:
    assert BASH is not None
    result = subprocess.run([BASH, SCRIPT.as_posix(), "--help"], capture_output=True, check=False)
    assert result.returncode == 0 and b"--pdf-browser-zip" in result.stdout
    text = SCRIPT.read_text(encoding="utf-8")
    assert f'"{disclaimer("zh")}"' in text and f'"{disclaimer("en")}"' in text


# A stand-in uv that works (a shell script): `uv venv ... <venv>` creates <venv>/bin/neurogrid, which exits 0,
# so the installer's self-test passes; `uv pip ...` exits with NG_STAND_IN_PIP_EXIT (default 0).
STAND_IN_UV = """#!/bin/sh
case "$1" in
  venv)
    for venv in "$@"; do :; done
    mkdir -p "$venv/bin"
    printf '#!/bin/sh\\nexit 0\\n' >"$venv/bin/neurogrid"
    chmod 755 "$venv/bin/neurogrid"
    ;;
  pip) exit "${NG_STAND_IN_PIP_EXIT:-0}" ;;
  *) exit 1 ;;
esac
"""


@pytest.fixture
def installable(folder: Path) -> Path:
    (folder / "uv" / "uv").write_text(STAND_IN_UV, encoding="utf-8", newline="\n")
    (folder / "uv" / "uv").chmod(0o755)
    _resum(folder)
    return folder


def _environment(**changes: str | None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("XDG_DATA_HOME", "NEUROGRID_PDF_BROWSER_DIR")}
    for key, value in changes.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def test_show_writes_the_home_folder_as_tilde() -> None:
    out = _source(
        "HOME=/home/runneradmin; unset XDG_DATA_HOME; for p in /home/runneradmin /home/runneradmin/a/b "
        '/home/runneradminx/c /opt/ng; do show "$p"; echo; done; '
        "XDG_DATA_HOME=/home/runneradmin/.data; show /home/runneradmin/.data/neurogrid/1; echo; "
        "HOME=/; show /x; echo; HOME=; show /home/runneradmin/y; echo"
    )
    assert out.splitlines() == [
        "~",
        "~/a/b",
        "/home/runneradminx/c",
        "/opt/ng",
        "${XDG_DATA_HOME}/neurogrid/1",
        "/x",
        "/home/runneradmin/y",
    ]


def test_console_names_no_user_folder(installable: Path, tmp_path: Path) -> None:
    """A-51 (review R13): the installer printed /home/<name>/... in 'installed:', 'uninstall:' and 'target
    exists'; like NeuroGrid's own console it shows ~ (or ${XDG_DATA_HOME})."""
    home = tmp_path / "home" / "runneradmin"
    home.mkdir(parents=True)
    env = _environment(HOME=_bash_path(home))
    code, text = _run_as_linux_x86_64(installable, "--skip-signature-check", env=env)
    assert code == 0, text
    assert "installed: ~/.local/share/neurogrid/9.8.7/bin/neurogrid" in text
    assert "已安装：~/.local/share/neurogrid/9.8.7/bin/neurogrid" in text
    assert (
        "uninstall: delete the folder ~/.local/share/neurogrid/9.8.7 "
        "(and ${XDG_DATA_HOME:-~/.local/share}/neurogrid/pdf-browser if the PDF browser was installed)"
    ) in text
    assert "runneradmin" not in text, text
    code, text = _run_as_linux_x86_64(installable, "--skip-signature-check", env=env)
    assert code == 2 and "target exists and is not empty: ~/.local/share/neurogrid/9.8.7 (" in text, text
    assert "runneradmin" not in text, text
    data = home / "data"
    env = _environment(HOME=_bash_path(home), XDG_DATA_HOME=_bash_path(data))
    code, text = _run_as_linux_x86_64(installable, "--skip-signature-check", env=env)
    assert code == 0 and "installed: ${XDG_DATA_HOME}/neurogrid/9.8.7/bin/neurogrid" in text, text
    assert "runneradmin" not in text, text


def test_a_failed_installation_leaves_the_target_as_it_was(installable: Path, tmp_path: Path) -> None:
    """Review R14: a failure into an existing empty folder left python/ behind, so a retry stopped at 'target
    exists and is not empty'; parents that mkdir -p created stayed too. Now the empty folder is empty again
    and the retry runs to its end; created parents go again, a parent with other content stays."""
    failing = _environment(NG_STAND_IN_PIP_EXIT="1")
    empty = tmp_path / "empty"
    empty.mkdir()
    code, text = _run_as_linux_x86_64(
        installable, "--skip-signature-check", "--prefix", _bash_path(empty), env=failing
    )
    assert code == 2 and "offline installation failed" in text, text
    assert empty.is_dir() and list(empty.iterdir()) == []
    code, text = _run_as_linux_x86_64(installable, "--skip-signature-check", "--prefix", _bash_path(empty))
    assert code == 0 and "target exists" not in text, text
    shared = tmp_path / "shared"
    shared.mkdir()
    prefix = _bash_path(shared / "neurogrid" / "9.8.7")
    code, text = _run_as_linux_x86_64(installable, "--skip-signature-check", "--prefix", prefix, env=failing)
    assert code == 2, text
    assert shared.is_dir() and list(shared.iterdir()) == []
    (shared / "neurogrid" / "pdf-browser").mkdir(parents=True)
    code, text = _run_as_linux_x86_64(installable, "--skip-signature-check", "--prefix", prefix, env=failing)
    assert code == 2, text
    assert [p.name for p in (shared / "neurogrid").iterdir()] == ["pdf-browser"]
