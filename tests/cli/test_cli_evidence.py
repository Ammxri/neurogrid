"""Command line, P4 evidence area: --evidence, exit 2 for invalid control files (A-12, A-14, C2), warnings
on the console, the semi-automatic document checker end to end (RP-05) and batch runs from shell scripts
(UF-04)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import dir_link, documented_config  # type: ignore[import-not-found]
from neurogrid.cli import main

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
SOP = b"Backup and checksum SOP (synthetic test document)\n"


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def _evidence(path: Path, entries: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("format_version: 1\nevidence:\n" + entries, encoding="utf-8")
    return path


# --- exit 2 for invalid control files -----------------------------------------------------------------


@pytest.mark.parametrize(
    "reason", ['reason = ""\n', 'reason = "   "\n', ""], ids=["empty", "blank", "missing"]
)
def test_exception_without_reason_is_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], reason: str
) -> None:
    """KONZEPT P4 DoD: 'Ausnahme ohne Begründung -> Exit 2' (A-14)."""
    config = tmp_path / "neurogrid.toml"
    config.write_text('[[exceptions]]\nrule = "CORE-M01-04"\n' + reason, encoding="utf-8")
    out_file = tmp_path / "r.json"
    code, _, err = run(
        ["check", str(FIX / "edf_ok"), "--config", str(config), "--out", str(out_file)], capsys
    )
    assert code == 2 and "exceptions.0.reason" in err
    assert "Traceback" not in err and str(Path.home()) not in err and not out_file.exists()


def test_invalid_evidence_is_exit_2_with_the_field(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    evidence = _evidence(tmp_path / "evidence.yaml", "  GXDSL008-ACC-001:\n    status: done\n")
    code, _, err = run(["check", str(FIX / "edf_ok"), "--evidence", str(evidence)], capsys)
    assert code == 2 and "evidence.GXDSL008-ACC-001.status" in err and "Traceback" not in err
    no_document = _evidence(tmp_path / "doc.yaml", "  GXDSL008-ACC-001:\n    status: provided\n")
    code, _, err = run(["--lang", "zh", "check", str(FIX / "edf_ok"), "--evidence", str(no_document)], capsys)
    assert code == 2 and "document_required" in err and "证明材料文件无效" in err
    unsafe = _evidence(
        tmp_path / "unsafe.yaml", "  GXDSL008-ACC-001:\n    status: provided\n    document: ../x.pdf\n"
    )
    code, _, err = run(["check", str(FIX / "edf_ok"), "--evidence", str(unsafe)], capsys)
    assert code == 2 and "GXDSL008-ACC-001" in err and "plain relative path" in err


def test_missing_evidence_file_is_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(["check", str(FIX / "edf_ok"), "--evidence", str(tmp_path / "nope.yaml")], capsys)
    assert code == 2 and "Evidence file not found" in err


def test_real_subprocess_invalid_evidence_is_exit_2(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path / "evidence.yaml", "  GXDSL008-ACC-001: {status: provided}\n")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, "-m", "neurogrid", "check", str(FIX / "edf_ok"), "--evidence", str(evidence)],
        capture_output=True,
        env=env,
        check=False,
    )
    err = result.stderr.decode("utf-8")
    assert result.returncode == 2 and "document_required" in err and "Traceback" not in err


# --- console ---------------------------------------------------------------------------------------------


def test_console_prints_warnings_and_open_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = documented_config(
        tmp_path, '[[exceptions]]\nrule = "CORE-M03-01"\nreason = "old amplifier"\nvalid_until = 2026-01-01\n'
    )
    evidence = _evidence(
        tmp_path / "evidence.yaml",
        "  GXDSL008-ACC-001:\n    status: provided\n    document: gone.pdf\n    reviewer: QA\n",
    )
    args = ["check", str(FIX / "edf_ok"), "--rulepack", "gxdsl008", "--config", str(config)]
    code, out, _ = run([*args, "--out", str(tmp_path / "a.json"), "--evidence", str(evidence)], capsys)
    assert code == 0
    assert "expired on 2026-01-01" in out  # notice.exception_expired
    assert "GXDSL008-ACC-001" in out and "was not found" in out  # notice.evidence_document.document_missing
    assert "QA" not in out  # free text from evidence.yaml never reaches the console
    code, out, _ = run([*args, "--out", str(tmp_path / "b.json"), "--as-of", "2026-01-01"], capsys)
    assert code == 0 and "1 open evidence item(s)" in out


# --- RP-05: the semi-automatic checker end to end (critic G5) --------------------------------------------

SEMI_PACK = """rulepack: storage_sop
version: "1.0"
source: Site storage SOP (synthetic)
source_status: final
rules:
  - id: SOP-STO-001
    clause: "SOP-7"
    title_zh: 备份和校验程序文件存在且未修改
    title_en: Backup and checksum procedure present and unchanged
    phase: storage
    check: evidence.document
    severity: error
    verification: semi_automatic
"""


def _semi_setup(tmp_path: Path) -> tuple[Path, Path]:
    (tmp_path / "semi.yaml").write_text(SEMI_PACK, encoding="utf-8")
    config = tmp_path / "neurogrid.toml"
    config.write_text('[check]\nrulepacks = ["semi.yaml"]\n', encoding="utf-8")  # only this pack (A-02)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "backup-sop.txt").write_bytes(SOP)
    return config, tmp_path / "evidence.yaml"


@pytest.mark.parametrize(
    ("case", "expected_code", "reason"),
    [
        ("ok", 0, None),
        ("document_missing", 1, "evidence.document_missing"),
        ("hash_mismatch", 1, "evidence.hash_mismatch"),
        ("document_link", 1, "evidence.document_link"),
    ],
)
def test_semi_automatic_rule_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str, expected_code: int, reason: str | None
) -> None:
    """RP-05 evidence: a custom semi_automatic error rule on evidence.document passes only when its document
    exists, is no link and matches the recorded hash (A-15); exit 0/1/1/1."""
    config, evidence = _semi_setup(tmp_path)
    digest = hashlib.sha256(SOP).hexdigest()
    document = "docs/backup-sop.txt"
    if case == "document_missing":
        document = "docs/restore-sop.txt"
    elif case == "hash_mismatch":
        digest = hashlib.sha256(b"an earlier version").hexdigest()
    elif case == "document_link":
        shutil.move(tmp_path / "docs", tmp_path / "real-docs")
        dir_link(tmp_path / "docs", tmp_path / "real-docs")
    _evidence(
        evidence, f"  SOP-STO-001:\n    status: provided\n    document: {document}\n    sha256: {digest}\n"
    )
    out_file = tmp_path / "results.json"
    code, _, _ = run(
        [
            "check",
            str(FIX / "edf_ok"),
            "--config",
            str(config),
            "--evidence",
            str(evidence),
            "--out",
            str(out_file),
        ],
        capsys,
    )
    assert code == expected_code
    results = json.loads(out_file.read_text(encoding="utf-8"))
    (record,) = results["evidence"]
    assert record["document_check"] == case and record["verification"] == "semi_automatic"
    reasons = [f["reason"] for f in results["findings"] if f["rule_id"] == "SOP-STO-001"]
    assert reasons == ([] if reason is None else [reason])
    if case in ("ok", "hash_mismatch"):
        assert record["sha256"] == hashlib.sha256(SOP).hexdigest()  # computed and reported either way


# --- UF-04: batch runs from scripts over several fixtures -------------------------------------------------

LAB_PACK = """rulepack: lab
version: "1.0"
source: Lab acceptance criteria (synthetic)
source_status: final
rules:
  - id: LAB-ACQ-001
    clause: "LAB-2"
    title_zh: 采样率至少 300 Hz
    title_en: Sampling rate at least 300 Hz
    phase: acquisition
    check: signal.sampling_rate_min
    params: {min_hz: 300}
    severity: error
    verification: automatic
"""
BATCH = {"edf_ok": 0, "edf_lowrate": 1, "bdf_ok": 0}  # edf_lowrate: 256 Hz < 300 Hz (LAB-ACQ-001)

BASH_LOOP = """set -u
py="$1"; out="$2"; pack="$3"; config="$4"; shift 4
for folder in "$@"; do
  name=$(basename "$folder")
  "$py" -m neurogrid check "$folder" --rulepack gxdsl008 --rulepack "$pack" --config "$config" \\
      --out "$out/$name.json" > /dev/null
  echo "$name $?" >> "$out/codes.txt"
done
"""
POWERSHELL_LOOP = """$py, $out, $pack, $config = $args[0..3]
foreach ($folder in $args[4..($args.Count - 1)]) {
    $name = Split-Path $folder -Leaf
    & $py -m neurogrid check $folder --rulepack gxdsl008 --rulepack $pack --config $config `
        --out (Join-Path $out "$name.json") | Out-Null
    Add-Content -Path (Join-Path $out 'codes.txt') -Value "$name $LASTEXITCODE"
}
"""


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


def _batch_inputs(tmp_path: Path) -> tuple[Path, Path, Path, list[str]]:
    out = tmp_path / "out"
    out.mkdir()
    pack = tmp_path / "lab.yaml"
    pack.write_text(LAB_PACK, encoding="utf-8")
    config = documented_config(tmp_path)
    return out, pack, config, [str(FIX / name) for name in BATCH]


def _check_batch(out: Path, codes: dict[str, int]) -> None:
    assert codes == BATCH
    for name in BATCH:
        results = json.loads((out / f"{name}.json").read_text(encoding="utf-8"))
        assert [p["name"] for p in results["rulepacks"]] == ["core", "gxdsl008", "lab"]
        assert results["summary"]["exit_code"] == BATCH[name]
        formats = {f["status"] for f in results["findings"] if f["rule_id"] == "GXDSL008-STO-001"}
        assert formats == ({"failed"} if name == "bdf_ok" else set())  # GX-03: BDF is no EDF (A-83)
        assert any(f["rule_id"] == "GXDSL008-ACC-001" for f in results["findings"])  # open evidence


def test_batch_loop_in_python_subprocesses(tmp_path: Path) -> None:
    out, pack, config, folders = _batch_inputs(tmp_path)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    codes = {}
    for folder in folders:
        name = Path(folder).name
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "neurogrid",
                "check",
                folder,
                "--rulepack",
                "gxdsl008",
                "--rulepack",
                str(pack),
            ]
            + ["--config", str(config), "--out", str(out / f"{name}.json")],
            capture_output=True,
            env=env,
            check=False,
        )
        codes[name] = result.returncode
    _check_batch(out, codes)


def _codes(out: Path) -> dict[str, int]:
    lines = (out / "codes.txt").read_text(encoding="utf-8-sig").split()
    return {lines[i]: int(lines[i + 1]) for i in range(0, len(lines), 2)}


def test_batch_loop_in_git_bash(tmp_path: Path) -> None:
    bash = _git_bash()
    if bash is None:
        pytest.skip("bash not available")
    out, pack, config, folders = _batch_inputs(tmp_path)
    posix = [Path(p).as_posix() for p in (sys.executable, str(out), str(pack), str(config), *folders)]
    result = subprocess.run(
        [bash, "-c", BASH_LOOP, "batch", *posix], capture_output=True, env=dict(os.environ), check=False
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    _check_batch(out, _codes(out))


def test_batch_loop_in_windows_powershell(tmp_path: Path) -> None:
    powershell = shutil.which("powershell") if sys.platform == "win32" else None
    if powershell is None:
        pytest.skip("Windows PowerShell 5.1 only exists on Windows")
    out, pack, config, folders = _batch_inputs(tmp_path)
    script = tmp_path / "batch.ps1"
    script.write_text(POWERSHELL_LOOP, encoding="utf-8-sig")  # PowerShell 5.1 reads UTF-8 only with a BOM
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        + [sys.executable, str(out), str(pack), str(config), *folders],
        capture_output=True,
        env=dict(os.environ),
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    _check_batch(out, _codes(out))
