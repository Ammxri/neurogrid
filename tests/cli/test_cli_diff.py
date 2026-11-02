"""`neurogrid diff OLD NEW` on the command line (NG-F15, CLI-07, UF-02; A-97): exit codes 0/1/2, the text and
JSON outputs and where they go, errors that name the argument, no access event, consent subjects only counted,
and the call from Git Bash and Windows PowerShell 5.1 with a Chinese path."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from conftest import documented_config  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.cli import main
from neurogrid.kernel import canonical
from neurogrid.model.consent import ConsentFile, ConsentScope, dump_consents
from neurogrid.model.diff import DiffResult
from neurogrid.report.texts import disclaimer, translator
from neurogrid.vault import store

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = date(2026, 10, 11)


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """results.json of edf_ok checked plainly (exit 0) and with --strict (CORE-M13-01 becomes an error)."""
    tmp = tmp_path_factory.mktemp("cli-diff")
    config = documented_config(tmp)
    found = {}
    for name, strict in (("plain", False), ("strict", True)):
        options = pipeline.CheckOptions(config_path=config, as_of=AS_OF, strict=strict, work_base=tmp)
        found[name] = tmp / f"{name}.json"
        found[name].write_bytes(canonical.dumps(pipeline.run_check(FIX / "edf_ok", options)))
    return found


def test_exit_codes_and_text(files: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
    tr = translator("en").t
    code, out, err = run(["diff", str(files["plain"]), str(files["strict"])], capsys)
    assert (code, err) == (1, "")
    lines = out.splitlines()
    assert lines[0] == tr("cli.diff.title") and lines[-1] == disclaimer("en")
    assert (
        tr("cli.diff.exit_new_errors", count=1) in lines and tr("cli.diff.section.changed", count=1) in lines
    )
    code, out, _ = run(["diff", str(files["strict"]), str(files["plain"])], capsys)
    assert code == 0 and tr("cli.diff.exit_no_new_errors") in out.splitlines()
    code, out, _ = run(["diff", str(files["plain"]), str(files["plain"])], capsys)
    assert code == 0 and tr("cli.diff.section.changed", count=0) in out.splitlines()
    code, out, _ = run(["--lang", "zh", "diff", str(files["plain"]), str(files["strict"])], capsys)
    zh = translator("zh").t
    assert (
        code == 1 and out.splitlines()[0] == zh("cli.diff.title") and out.splitlines()[-1] == disclaimer("zh")
    )


def test_json_alone_goes_to_stdout(files: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(["diff", str(files["plain"]), str(files["strict"]), "--format", "json"], capsys)
    assert (code, err) == (1, "")
    result = DiffResult.model_validate_json(out)  # nothing but the JSON: the fixed sentence is its field
    assert result.summary.exit_code == 1 and result.disclaimer.en == disclaimer("en")
    assert out.encode("utf-8") == canonical.dumps(result)


def test_text_and_json_with_out(
    files: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "out" / "diff.json"
    args = ["diff", str(files["plain"]), str(files["strict"]), "--format", "text,json", "--out", str(target)]
    code, out, _ = run(args, capsys)
    assert code == 1 and out.splitlines()[0] == translator("en").t("cli.diff.title")
    first = target.read_bytes()
    assert DiffResult.model_validate_json(first).summary.changed == 1
    written = translator("en").t("cli.diff.written", path="")
    assert any(line.startswith(written) for line in out.splitlines()) and out.splitlines()[-1] == disclaimer(
        "en"
    )
    code, out, _ = run([*args[:3], "--format", "json", "--format", "text", "--out", str(target)], capsys)
    assert code == 1 and target.read_bytes() == first  # byte-identical again (NG-N03)
    code, out, _ = run([*args[:3], "--format", "json", "--out", str(target)], capsys)
    assert code == 1 and translator("en").t("cli.diff.title") not in out and target.read_bytes() == first


@pytest.mark.parametrize(
    ("extra", "key", "params"),
    [
        (["--format", "text,json"], "errors.diff.json_needs_out", {}),
        (["--format", "text", "--out", "d.json"], "errors.diff.out_needs_json", {}),
        (["--format", "xml"], "errors.report.format_unavailable", {"format": "xml"}),
        (["--format", ""], "errors.report.format_unavailable", {"format": ""}),
    ],
)
def test_option_errors_are_exit_2(
    files: dict[str, Path],
    capsys: pytest.CaptureFixture[str],
    extra: list[str],
    key: str,
    params: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tr = translator("en").t
    code, out, err = run(["diff", str(files["plain"]), str(files["strict"]), *extra], capsys)
    assert (code, out) == (2, "") and err.strip() == f"{tr('cli.error.prefix')}: {tr(key, **params)}"
    assert not (tmp_path / "d.json").exists()


def test_unreadable_inputs_name_the_argument(
    files: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tr = translator("en").t
    broken = tmp_path / "broken.json"
    broken.write_text("{}", encoding="utf-8")
    missing = tmp_path / "nichts.json"
    for args, label in (
        ([str(missing), str(files["plain"])], "OLD"),
        ([str(files["plain"]), str(broken)], "NEW"),
        ([str(broken), str(missing)], "OLD"),  # the old file is read first
    ):
        code, out, err = run(["diff", *args], capsys)
        assert (code, out) == (2, "")
        assert err.strip() == f"{tr('cli.error.prefix')}: {tr('errors.diff.results_invalid', file=label)}"
        assert "nichts" not in err and str(tmp_path) not in err  # never the path (A-51)


def _vault_dataset(tmp_path: Path, records: list[ConsentScope]) -> tuple[Path, store.VaultLocation]:
    folder = tmp_path / "ds"
    shutil.copytree(FIX / "bids_ai_ok", folder)
    location = store.locate(folder, store.DEFAULT_VAULT_PATH)
    store.init_vault(location)
    location.consents.write_bytes(dump_consents(ConsentFile(consents=records)))
    return folder, location


def _consent(subject: str) -> ConsentScope:
    return ConsentScope(
        subject=subject, version=1, date=date(2026, 1, 1), permitted_uses=("training", "validation")
    )


def test_consent_subjects_only_counted_and_no_access_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-17 option B and A-30: a subject whose consent is missing in the new run is a new error finding of
    CORE-M14-01 (exit 1), shown only as a count per rule and category; diff writes no access event."""
    every = [_consent(f"sub-0{n}") for n in range(1, 7)]
    folder, location = _vault_dataset(tmp_path, every)
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    run(["check", str(folder), "--as-of", "2026-11-20", "--out", str(old)], capsys)
    location.consents.write_bytes(dump_consents(ConsentFile(consents=every[:3] + every[4:])))  # no sub-04
    run(["check", str(folder), "--as-of", "2026-11-20", "--out", str(new)], capsys)
    assert "consent.missing" not in old.read_text(encoding="utf-8")
    (missing,) = [
        f for f in json.loads(new.read_text(encoding="utf-8"))["findings"] if f["reason"] == "consent.missing"
    ]
    log = location.log.read_bytes()
    target = tmp_path / "diff.json"
    for lang in ("en", "zh"):
        code, out, _ = run(
            ["--lang", lang, "diff", str(old), str(new), "--format", "text,json", "--out", str(target)],
            capsys,
        )
        tr = translator(lang).t
        line = tr("cli.diff.aggregated", rule="CORE-M14-01", category=tr("terms.diff_category.new"), count=1)
        assert code == 1 and line in out.splitlines()
        assert tr("cli.diff.exit_new_errors", count=1) in out.splitlines()
        text = out + target.read_text(encoding="utf-8")
        assert missing["key"] not in text and "consent.missing" not in text and "CORE-M14-01 [" not in text
        result = DiffResult.model_validate_json(target.read_bytes())
        assert [(c.rule_id, c.category, c.count) for c in result.aggregated] == [("CORE-M14-01", "new", 1)]
    assert location.log.read_bytes() == log  # no access event (the comparison reads no vault)


# --- shells and a Chinese path (CLI-07, p9 decisions 10) ----------------------------------------------------

BASH_DIFF = """set -u
plain="$2/plain.json"; strict="$2/strict.json"; out="$2/比较 结果.json"
"$1" -m neurogrid diff "$plain" "$strict" > /dev/null
echo "worse $?" > "$3"
"$1" -m neurogrid diff "$strict" "$plain" --format text,json --out "$out" > /dev/null
echo "better $?" >> "$3"
"$1" -m neurogrid diff "$plain" "$strict" --format text,json 2> /dev/null
echo "usage $?" >> "$3"
"""
POWERSHELL_DIFF = """$py, $folder, $codes = $args[0..2]
$plain = Join-Path $folder 'plain.json'; $strict = Join-Path $folder 'strict.json'
$out = Join-Path $folder '比较 结果.json'
& $py -m neurogrid diff $plain $strict | Out-Null
Set-Content -Path $codes -Value "worse $LASTEXITCODE"
& $py -m neurogrid diff $strict $plain --format 'text,json' --out $out | Out-Null
Add-Content -Path $codes -Value "better $LASTEXITCODE"
& $py -m neurogrid diff $plain $strict --format 'text,json' 2> $null
Add-Content -Path $codes -Value "usage $LASTEXITCODE"
"""


def _chinese_folder(files: dict[str, Path], tmp_path: Path) -> Path:
    folder = tmp_path / "数据 集"
    folder.mkdir()
    for name, path in files.items():
        shutil.copyfile(path, folder / f"{name}.json")
    return folder


def _check_shell_run(folder: Path, codes: Path) -> None:
    assert codes.read_text(encoding="utf-8-sig").split() == ["worse", "1", "better", "0", "usage", "2"]
    assert DiffResult.model_validate_json((folder / "比较 结果.json").read_bytes()).summary.changed == 1


def _git_bash() -> str | None:
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


def test_diff_in_git_bash_with_a_chinese_path(files: dict[str, Path], tmp_path: Path) -> None:
    bash = _git_bash()
    if bash is None:
        pytest.skip("bash not available")
    folder = _chinese_folder(files, tmp_path)
    codes = tmp_path / "codes.txt"
    posix = [Path(p).as_posix() for p in (sys.executable, str(folder), str(codes))]
    result = subprocess.run(
        [bash, "-c", BASH_DIFF, "diff", *posix], capture_output=True, env=dict(os.environ), check=False
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    _check_shell_run(folder, codes)


@pytest.mark.parametrize("shell", ["powershell", "pwsh"])
def test_diff_in_powershell_with_a_chinese_path(files: dict[str, Path], tmp_path: Path, shell: str) -> None:
    executable = shutil.which(shell) if sys.platform == "win32" or shell == "pwsh" else None
    if executable is None:
        pytest.skip(f"{shell} not available")
    folder = _chinese_folder(files, tmp_path)
    codes = tmp_path / "codes.txt"
    script = tmp_path / "diff.ps1"
    script.write_text(POWERSHELL_DIFF, encoding="utf-8-sig")  # PowerShell 5.1 reads UTF-8 only with a BOM
    result = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        + [sys.executable, str(folder), str(codes)],
        capture_output=True,
        env=dict(os.environ),
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    _check_shell_run(folder, codes)
