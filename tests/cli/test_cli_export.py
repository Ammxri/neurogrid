"""``neurogrid vault export`` on the command line (NV-F07, CLI-08; A-96; p9 decisions 10): help in the
selected language, exit codes 0 and 2 (never 1), usage errors in NeuroGrid's words, and runs under Windows
PowerShell 5.1 and Git Bash with a Chinese path."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

from neurogrid import pipeline
from neurogrid.cli import main
from neurogrid.report.output import html_document
from neurogrid.report.texts import translator

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
HAN = re.compile("[㐀-䶿一-鿿]")
VAULT = Path(".neurogrid", "vault")


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def _flat(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _dataset(folder: Path) -> Path:
    """bids_ok with the report of its check next to it (report.en.html, written without a browser)."""
    shutil.copytree(FIX / "bids_ok", folder)
    results = pipeline.run_check(folder, pipeline.CheckOptions(as_of=date(2026, 10, 11)))
    report = folder.parent / "report.en.html"
    report.write_bytes(html_document(results, "en").encode("utf-8"))
    return report


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_vault_export_help_follows_the_language(lang: str, capsys: pytest.CaptureFixture[str]) -> None:
    tr = translator(lang).t
    code, out, err = run(["--lang", lang, "vault", "export", "--help"], capsys)
    assert code == 0 and not err
    for key in ("about", "report", "out", "manifest", "show_paths", "role", "purpose", "approval_ref"):
        assert _flat(tr(f"cli.help.vault.export.{key}")) in _flat(out), key
    assert bool(HAN.search(out)) is (lang == "zh")
    code, out, _ = run(["--lang", lang, "vault", "--help"], capsys)
    assert code == 0 and "export" in out and _flat(tr("cli.help.vault.export.about")) in _flat(out)


def test_usage_errors_are_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tr = translator("en").t
    command = "neurogrid vault export"
    code, _, err = run(["--lang", "en", "vault", "export", str(tmp_path), "--out", "x.zip"], capsys)
    problem = tr("cli.error.missing_option", name="--report", command=command)
    assert code == 2 and tr("cli.error.usage", problem=problem) in err
    code, _, err = run(["--lang", "en", "vault", "export", str(tmp_path), "--report", "r.html"], capsys)
    problem = tr("cli.error.missing_option", name="--out", command=command)
    assert code == 2 and tr("cli.error.usage", problem=problem) in err
    code, _, err = run(
        ["--lang", "en", "vault", "export", str(tmp_path), "--report", "r.html", "--out", f"{tmp_path}/"],
        capsys,
    )
    assert code == 2 and tr("errors.output.is_directory") in err
    code, _, err = run(
        [
            "--lang",
            "en",
            "vault",
            "export",
            str(tmp_path),
            "--report",
            "r.html",
            "--out",
            "x.zip",
            "--role",
            "Q",
        ],
        capsys,
    )
    assert code == 2 and tr("errors.vault.not_found") in err  # no vault: refused before anything is read


def test_vault_export_chinese_path_in_process(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "数据" / "受试者"
    folder.parent.mkdir()
    report = _dataset(folder)
    zh = translator("zh").t
    assert run(["--lang", "zh", "vault", "init", str(folder)], capsys)[0] == 0
    assert run(["--lang", "zh", "manifest", str(folder)], capsys)[0] == 0
    out = tmp_path / "导出" / "检查包.zip"
    code, stdout, stderr = run(
        [
            "--lang",
            "zh",
            "vault",
            "export",
            str(folder),
            "--report",
            str(report),
            "--out",
            str(out),
            "--role",
            "QA",
        ],
        capsys,
    )
    assert code == 0, stdout + stderr
    assert zh("cli.vault.export.pia_unedited") in stdout and stdout.rstrip().endswith(zh("disclaimer"))
    with zipfile.ZipFile(out) as archive:
        names = archive.namelist()
    assert names[-1] == "index.json" and "report/report.en.html" in names


ROLES_WITHOUT_EXPORT = (
    b"format_version: 1\nroles:\n  - role: QA\n    description: quality assurance\n"
    b"    actions: [read, check]\n    objects: ['**']\n"
)


def test_export_warns_when_the_register_does_not_permit_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The role register is advisory (A-93): an export it does not permit is written with the warning and
    exit 0; once the role may export, the warning is gone."""
    folder = tmp_path / "data"
    report = _dataset(folder)
    assert run(["--lang", "en", "vault", "init", str(folder)], capsys)[0] == 0
    assert run(["--lang", "en", "manifest", str(folder)], capsys)[0] == 0
    roles = folder / VAULT / "roles.yaml"
    roles.write_bytes(ROLES_WITHOUT_EXPORT)
    tr = translator("en").t
    warning = tr("cli.vault.role_not_permitted", reason=tr("cli.vault.role_reason.action_not_allowed"))
    out = tmp_path / "package.zip"
    args = ["--lang", "en", "vault", "export", str(folder), "--report", str(report), "--out", str(out)]
    code, stdout, stderr = run([*args, "--role", "QA"], capsys)
    assert code == 0 and out.is_file() and warning in stdout + stderr
    out.unlink()
    roles.write_bytes(ROLES_WITHOUT_EXPORT.replace(b"[read, check]", b"[read, check, export]"))
    code, stdout, stderr = run([*args, "--role", "QA"], capsys)
    prefix = tr("cli.vault.role_not_permitted", reason="|").split("|")[0]
    assert code == 0 and out.is_file() and prefix not in stdout + stderr


POWERSHELL_FLOW = """$py, $folder, $report, $out, $codes = $args[0..4]
& $py -m neurogrid --lang zh vault init $folder | Out-Null
Add-Content -Path $codes -Value "init $LASTEXITCODE"
& $py -m neurogrid --lang zh manifest $folder | Out-Null
Add-Content -Path $codes -Value "manifest $LASTEXITCODE"
& $py -m neurogrid --lang zh vault export $folder --report $report --out $out --role QA | Out-Null
Add-Content -Path $codes -Value "export $LASTEXITCODE"
& $py -m neurogrid --lang zh vault export $folder --report $folder --out $out --role QA 2>$null | Out-Null
Add-Content -Path $codes -Value "refused $LASTEXITCODE"
"""
BASH_FLOW = """set -u
py="$1"; folder="$2"; report="$3"; out="$4"; codes="$5"
"$py" -m neurogrid --lang zh vault init "$folder" > /dev/null; echo "init $?" >> "$codes"
"$py" -m neurogrid --lang zh manifest "$folder" > /dev/null; echo "manifest $?" >> "$codes"
"$py" -m neurogrid --lang zh vault export "$folder" --report "$report" --out "$out" --role QA > /dev/null
echo "export $?" >> "$codes"
"$py" -m neurogrid --lang zh vault export "$folder" --report "$folder" --out "$out" --role QA > /dev/null 2>&1
echo "refused $?" >> "$codes"
"""


def _codes(path: Path) -> dict[str, int]:
    pairs = (line.split() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip())
    return {name: int(code) for name, code in pairs}


def _flow_result(folder: Path, out: Path, codes: Path) -> None:
    """Written once (exit 0), the folder as report refused (exit 2, the package unchanged, no event)."""
    assert _codes(codes) == {"init": 0, "manifest": 0, "export": 0, "refused": 2}
    events = [json.loads(line) for line in (folder / VAULT / "access.jsonl").read_bytes().splitlines()]
    assert [event["action"] for event in events] == ["read", "export"] and events[-1]["role"] == "QA"
    with zipfile.ZipFile(out) as archive:
        assert archive.namelist()[-1] == "index.json"


@pytest.mark.parametrize("shell", ["powershell", "pwsh"], ids=["powershell-5.1", "pwsh-7"])
def test_vault_export_windows_powershell_chinese_path(tmp_path: Path, shell: str) -> None:
    """Windows PowerShell 5.1 and PowerShell 7 (p9 decisions 10)."""
    powershell = shutil.which(shell) if sys.platform == "win32" else None
    if powershell is None:
        pytest.skip(f"{shell} is not installed (Windows only; PowerShell 7 where the runner has it)")
    folder = tmp_path / "数据集"
    report = _dataset(folder)
    script = tmp_path / "flow.ps1"
    script.write_text(POWERSHELL_FLOW, encoding="utf-8-sig")  # PowerShell 5.1 reads UTF-8 only with a BOM
    out, codes = tmp_path / "检查包.zip", tmp_path / "codes.txt"
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        + [sys.executable, str(folder), str(report), str(out), str(codes)],
        capture_output=True,
        env=dict(os.environ),
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    _flow_result(folder, out, codes)


def _git_bash() -> str | None:
    """Git Bash on Windows (the bash.exe in System32 belongs to WSL); bash elsewhere."""
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


def test_vault_export_git_bash_chinese_path(tmp_path: Path) -> None:
    bash = _git_bash()
    if bash is None:
        pytest.skip("bash not available")
    folder = tmp_path / "数据集"
    report = _dataset(folder)
    out, codes = tmp_path / "检查包.zip", tmp_path / "codes.txt"
    posix = [Path(p).as_posix() for p in (sys.executable, str(folder), str(report), str(out), str(codes))]
    result = subprocess.run(
        [bash, "-c", BASH_FLOW, "flow", *posix], capture_output=True, env=dict(os.environ), check=False
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    _flow_result(folder, out, codes)
