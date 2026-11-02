"""``neurogrid vault consent add`` (NV-F01, CLI-08, D-10 b; A-30, A-31, A-91; p6 decisions 3-5): one record or
an import table, under the vault lock, one access event consent_manage before consents.yaml is rewritten,
every refusal exit 2 without a change. The vault is created with vault.store.init_vault (what ``vault init``
does; the command itself is the vault area's)."""

from __future__ import annotations

import datetime as dt
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from conftest import dir_link  # type: ignore[import-not-found]
from neurogrid.cli import main
from neurogrid.model.consent import ConsentFile, ConsentScope, dump_consents, parse_consents
from neurogrid.report.texts import disclaimer, translator
from neurogrid.vault import ledger, store

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
HEADER = "subject\tversion\tdate\tpermitted_uses\twithdrawn\tethics_approval_ref\n"


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def _dataset(tmp_path: Path, name: str = "bids_ai_ok", records: list[ConsentScope] | None = None) -> Path:
    folder = tmp_path / name
    shutil.copytree(FIX / name, folder)
    location = store.locate(folder, store.DEFAULT_VAULT_PATH)
    store.init_vault(location)
    if records is not None:
        location.consents.write_bytes(dump_consents(ConsentFile(consents=records)))
    return folder


def _vault(folder: Path) -> store.VaultLocation:
    return store.locate(folder, store.DEFAULT_VAULT_PATH)


def _state(folder: Path) -> tuple[bytes, bytes]:
    location = _vault(folder)
    return location.consents.read_bytes(), location.log.read_bytes()


def _events(folder: Path) -> list[Any]:
    location = _vault(folder)
    return [entry.event for entry in ledger.iter_entries(location.log)]


ADD = ["--lang", "en", "vault", "consent", "add"]
FIELDS = ["--subject", "07", "--version", "2", "--date", "2026-03-01", "--uses", "training,validation"]


def test_add_one_record(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _dataset(tmp_path)
    code, out, err = run(
        [*ADD, str(folder), *FIELDS, "--ethics-ref", "EC-2026-17", "--role", "data_steward"], capsys
    )
    assert code == 0 and not err, err
    lines = out.strip().splitlines()
    assert lines[0] == translator("en").t("cli.vault.consent.added", subject="sub-07", version=2)
    assert lines[-1] == disclaimer("en")
    assert "EC-2026-17" not in out and "training" not in out  # never the reference or the uses
    record = ConsentScope(
        subject="sub-07",
        version=2,
        date=dt.date(2026, 3, 1),
        permitted_uses=("training", "validation"),
        ethics_approval_ref="EC-2026-17",
    )
    assert _vault(folder).consents.read_bytes() == dump_consents(ConsentFile(consents=[record]))
    (event,) = _events(folder)
    assert (event.action, event.role, event.objects) == (
        "consent_manage",
        "data_steward",
        [".neurogrid/vault/consents.yaml"],
    )
    assert ledger.verify(_vault(folder)).intact


def test_withdrawal_and_a_partial_withdrawal_are_new_versions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _dataset(tmp_path)
    base = [*ADD, str(folder), "--role", "QA", "--subject", "sub-07"]
    assert (
        run(
            [*base, "--version", "1", "--date", "2026-01-01", "--uses", "training", "--uses", "sharing"],
            capsys,
        )[0]
        == 0
    )
    assert run([*base, "--version", "2", "--date", "2026-03-01", "--uses", "training"], capsys)[0] == 0
    assert run([*base, "--version", "3", "--date", "2026-06-01", "--withdrawn"], capsys)[0] == 0
    records = parse_consents(_vault(folder).consents.read_bytes()).consents
    assert [(r.version, r.permitted_uses, r.withdrawn) for r in records] == [
        (1, ("training", "sharing"), False),
        (2, ("training",), False),
        (3, (), True),
    ]
    assert [event.seq for event in _events(folder)] == [1, 2, 3] and ledger.verify(_vault(folder)).intact


REFUSALS = [
    (["--from", "x.tsv", "--subject", "07"], "errors.consent.from_with_fields", {}),
    (FIELDS[:6] + ["--uses", "training", "--withdrawn"], "errors.consent.withdrawn_with_uses", {}),
    (FIELDS[:6], "errors.consent.uses_required", {}),
    (
        FIELDS[:6] + ["--uses", "research"],
        "errors.consent.unknown_use",
        {"allowed": "training, validation, publication, sharing, commercial"},
    ),
    (["--subject", "Zhang San", *FIELDS[2:]], "errors.consent.subject_invalid", {}),
    (["--subject", "07", "--version", "0", *FIELDS[4:]], "errors.consent.version_invalid", {}),
    (["--subject", "07", "--version", "x", *FIELDS[4:]], "errors.consent.version_invalid", {}),
    ([*FIELDS[:4], "--date", "2026-1-5", *FIELDS[6:]], "errors.consent.date_invalid", {}),
    ([*FIELDS[:4], "--date", "20261005", *FIELDS[6:]], "errors.consent.date_invalid", {}),
    ([*FIELDS, "--ethics-ref", "E" * 121], "errors.consent.ethics_ref_invalid", {}),
    ([*FIELDS, "--ethics-ref", "   "], "errors.consent.ethics_ref_invalid", {}),
    ([*FIELDS, "--role", "Zhang San"], "errors.vault.role_invalid", {}),
    ([*FIELDS, "--purpose", "x" * 201], "errors.vault.text_invalid", {"field": "purpose"}),
]


@pytest.mark.parametrize(("args", "key", "params"), REFUSALS, ids=[r[1].split(".", 1)[1] for r in REFUSALS])
def test_refusals_change_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], args: list[str], key: str, params: dict[str, str]
) -> None:
    folder = _dataset(
        tmp_path,
        records=[
            ConsentScope(subject="sub-01", version=1, date=dt.date(2026, 1, 1), permitted_uses=("training",))
        ],
    )
    before = _state(folder)
    role = [] if "--role" in args else ["--role", "QA"]
    code, out, err = run([*ADD, str(folder), *args, *role], capsys)
    tr = translator("en").t
    assert code == 2 and not out
    assert err.strip() == f"{tr('cli.error.prefix')}: {tr(key, **params)}"
    assert "Zhang" not in err
    assert _state(folder) == before


def test_conflicts_with_existing_records_change_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _dataset(
        tmp_path,
        records=[
            ConsentScope(subject="sub-07", version=2, date=dt.date(2026, 3, 1), permitted_uses=("training",))
        ],
    )
    before = _state(folder)
    for version, day, key in (("2", "2026-04-01", "duplicate_version"), ("3", "2026-02-01", "date_order")):
        args = [
            *ADD,
            str(folder),
            "--subject",
            "07",
            "--version",
            version,
            "--date",
            day,
            "--uses",
            "training",
        ]
        code, _, err = run([*args, "--role", "QA"], capsys)
        assert code == 2 and translator("en").t(f"errors.consent.{key}") in err
    assert _state(folder) == before


def test_usage_and_vault_refusals(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tr = translator("en").t
    folder = _dataset(tmp_path)
    code, _, err = run(
        [*ADD, str(folder), "--version", "1", "--date", "2026-01-01", "--uses", "training"], capsys
    )
    missing = tr("cli.error.missing_option", name="--subject", command="neurogrid vault consent add")
    assert code == 2 and err.strip() == tr("cli.error.usage", problem=missing)
    code, _, err = run([*ADD, str(folder), *FIELDS], capsys)  # no --role and no [vault] role
    assert code == 2 and tr("errors.vault.role_missing") in err
    code, _, err = run([*ADD, str(FIX / "edf_ok" / "rec_a.edf"), *FIELDS, "--role", "QA"], capsys)
    assert code == 2 and tr("errors.vault.target_not_folder") in err
    plain = tmp_path / "plain"
    shutil.copytree(FIX / "edf_ok", plain)
    code, _, err = run([*ADD, str(plain), *FIELDS, "--role", "QA"], capsys)  # vault init not run
    assert code == 2 and tr("errors.vault.not_found") in err and not (plain / ".neurogrid").exists()
    _vault(folder).consents.write_bytes(b"format_version: 1\nconsents:\n  - subject: Zhang San\n")
    before = _state(folder)
    code, _, err = run([*ADD, str(folder), *FIELDS, "--role", "QA"], capsys)
    assert code == 2 and "consents.yaml" in err and "Zhang" not in err and _state(folder) == before


def test_a_vault_without_its_log_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _dataset(tmp_path)
    _vault(folder).log.unlink()
    before = _vault(folder).consents.read_bytes()
    code, _, err = run([*ADD, str(folder), *FIELDS, "--role", "QA"], capsys)
    assert code == 2 and translator("en").t("errors.vault.log_missing") in err
    assert _vault(folder).consents.read_bytes() == before and not _vault(folder).log.exists()


@pytest.mark.parametrize("part", ["vault", "consents.yaml"])
def test_links_in_the_vault_are_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], part: str
) -> None:
    folder = tmp_path / "ds"
    shutil.copytree(FIX / "bids_ai_ok", folder)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    store.init_vault(store.locate(elsewhere, store.DEFAULT_VAULT_PATH))
    if part == "vault":
        (folder / ".neurogrid").mkdir(exist_ok=True)
        dir_link(folder / ".neurogrid" / "vault", elsewhere / ".neurogrid" / "vault")
    else:
        store.init_vault(_vault(folder))
        _vault(folder).consents.unlink()
        dir_link(_vault(folder).consents, elsewhere)
    code, _, err = run([*ADD, str(folder), *FIELDS, "--role", "QA"], capsys)
    assert code == 2 and translator("en").t("errors.vault.link", part=part) in err
    assert (elsewhere / ".neurogrid" / "vault" / "access.jsonl").read_bytes() == b""


def test_event_fields_from_the_toml_and_a_toml_outside_the_dataset(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A-66: the vault is [vault] path relative to the project root; for a toml outside the dataset that is
    the toml's folder, and the event names consents.yaml relative to it (p6 decisions 3)."""
    folder = tmp_path / "ds"
    shutil.copytree(FIX / "bids_ai_ok", folder)
    project = tmp_path / "project"
    project.mkdir()
    toml = project / "study.toml"
    toml.write_text(
        '[vault]\npath = "records/vault"\nrole = "data_steward"\npurpose = "registration"\n'
        'approval_ref = "EC-2026-17"\n',
        encoding="utf-8",
    )
    store.init_vault(store.locate(project, "records/vault"))
    code, out, err = run([*ADD, str(folder), *FIELDS, "--config", str(toml)], capsys)
    assert code == 0, err
    location = store.locate(project, "records/vault")
    (event,) = [entry.event for entry in ledger.iter_entries(location.log)]
    assert event.objects == ["records/vault/consents.yaml"]
    assert (event.role, event.purpose, event.approval_ref) == ("data_steward", "registration", "EC-2026-17")
    code, _, err = run(
        [
            *ADD,
            str(folder),
            "--subject",
            "08",
            *FIELDS[2:],
            "--config",
            str(toml),
            "--role",
            "QA",
            "--purpose",
            "audit",
        ],
        capsys,
    )
    assert code == 0, err
    second = [entry.event for entry in ledger.iter_entries(location.log)][-1]
    assert (second.role, second.purpose, second.approval_ref) == ("QA", "audit", "EC-2026-17")
    assert not (folder / ".neurogrid" / "vault").exists()


def test_console_hints(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tr = translator("en").t
    folder = _dataset(tmp_path)
    later = (dt.date.today() + dt.timedelta(days=30)).isoformat()
    args = [
        "--subject",
        "1234567",
        "--version",
        "1",
        "--date",
        later,
        "--uses",
        "training",
        "--role",
        "Wang_Wei",
    ]
    code, out, _ = run([*ADD, str(folder), *args], capsys)
    assert code == 0
    assert tr("cli.vault.consent.date_in_future", count=1) in out  # recorded anyway
    assert tr("cli.vault.consent.subject_hint", count=1) in out
    assert tr("cli.vault.role_looks_identifying") in out
    assert parse_consents(_vault(folder).consents.read_bytes()).consents[0].subject == "sub-1234567"


def test_a_write_failure_after_the_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _dataset(tmp_path)
    before = _vault(folder).consents.read_bytes()

    def refuse(source: object, target: object) -> None:
        raise PermissionError(13, "in use")

    monkeypatch.setattr(os, "replace", refuse)
    code, _, err = run([*ADD, str(folder), *FIELDS, "--role", "QA"], capsys)
    assert code == 2 and translator("en").t("errors.consent.write_failed") in err
    assert _vault(folder).consents.read_bytes() == before
    assert [event.action for event in _events(folder)] == ["consent_manage"]  # the logged attempt
    assert not list(_vault(folder).path.glob(".consents.yaml.*.tmp"))


# --- --from consents.tsv (D-10 b) ------------------------------------------------------------------------


def test_import_a_table(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _dataset(tmp_path)
    table = tmp_path / "consents.tsv"
    table.write_bytes(
        "﻿Subject\tVersion\tDate\tUses\tEthics_Ref\n"
        "01\t1\t2026-01-05\ttraining,validation\tEC-1\n"
        "02\t1\t2026-01-06\ttraining\t\n".encode()
    )
    code, out, err = run([*ADD, str(folder), "--from", str(table), "--role", "QA"], capsys)
    assert code == 0, err
    assert out.splitlines()[0] == translator("en").t("cli.vault.consent.imported", count=2)
    records = parse_consents(_vault(folder).consents.read_bytes()).consents
    assert [(r.subject, r.ethics_approval_ref) for r in records] == [("sub-01", "EC-1"), ("sub-02", None)]
    assert len(_events(folder)) == 1  # one event per import


TABLES = {
    "invalid row": (
        "sub-01\t1\t2026-01-05\ttraining\t\t\nZhang San\t1\t2026-01-05\ttraining\t\t\n",
        "errors.consent_tsv.invalid_row",
        {"line": 3, "field": "subject"},
    ),
    "duplicate in the table": (
        "sub-02\t1\t2026-01-05\ttraining\t\t\n02\t1\t2026-02-05\ttraining\t\t\n",
        "errors.consent_tsv.duplicate",
        {"line": 3},
    ),
    "duplicate of the file": (
        "sub-01\t1\t2026-02-05\ttraining\t\t\n",
        "errors.consent_tsv.duplicate",
        {"line": 2},
    ),
}


@pytest.mark.parametrize(("rows", "key", "params"), TABLES.values(), ids=list(TABLES))
def test_an_invalid_table_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], rows: str, key: str, params: dict[str, object]
) -> None:
    folder = _dataset(
        tmp_path,
        records=[
            ConsentScope(subject="sub-01", version=1, date=dt.date(2026, 1, 1), permitted_uses=("training",))
        ],
    )
    before = _state(folder)
    table = tmp_path / "consents.tsv"
    table.write_text(HEADER + rows, encoding="utf-8")
    code, out, err = run([*ADD, str(folder), "--from", str(table), "--role", "QA"], capsys)
    tr = translator("en").t
    assert code == 2 and not out and err.strip() == f"{tr('cli.error.prefix')}: {tr(key, **params)}"
    assert "Zhang" not in err and _state(folder) == before


def test_table_columns_size_and_links(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from neurogrid.vault import consents

    tr = translator("en").t
    folder = _dataset(tmp_path)
    before = _state(folder)
    table = tmp_path / "consents.tsv"
    table.write_text("subject\tversion\tdate\tpermitted_uses\tnotes\n", encoding="utf-8")
    code, _, err = run([*ADD, str(folder), "--from", str(table), "--role", "QA"], capsys)
    assert code == 2 and tr("errors.consent_tsv.columns") in err
    table.write_text(
        HEADER + "sub-01\t1\t2026-01-05\ttraining\t\t\nsub-02\t1\t2026-01-05\ttraining\t\t\n", "utf-8"
    )
    monkeypatch.setattr(consents, "MAX_TSV_ROWS", 1)
    code, _, err = run([*ADD, str(folder), "--from", str(table), "--role", "QA"], capsys)
    assert code == 2 and tr("errors.consent_tsv.too_many_rows", limit=1) in err
    code, _, err = run([*ADD, str(folder), "--from", str(tmp_path / "missing.tsv"), "--role", "QA"], capsys)
    assert code == 2 and tr("errors.consent.from_not_found") in err
    linked = tmp_path / "linked.tsv"
    (tmp_path / "target").mkdir()
    dir_link(linked, tmp_path / "target")
    code, _, err = run([*ADD, str(folder), "--from", str(linked), "--role", "QA"], capsys)
    assert code == 2 and tr("errors.path.link") in err
    assert _state(folder) == before


# --- concurrency: the one vault lock (A-30 "Dateisperre", p6 decisions 3) --------------------------------

ADD_PROCESS = """
import sys
from neurogrid.cli import main
sys.stdout.write("ready\\n")
sys.stdout.flush()
sys.stdin.readline()
main(["vault", "consent", "add", sys.argv[1], "--subject", sys.argv[2], "--version", "1", "--date",
      "2026-01-01", "--uses", "training", "--role", "QA"])
"""
# what check appends after its outputs (vault area: pipeline.PendingAccess.commit -> ledger.append)
CHECK_EVENTS = """
import sys
from pathlib import Path
from neurogrid.vault import ledger, store
location = store.locate(Path(sys.argv[1]), ".neurogrid/vault")
sys.stdout.write("ready\\n")
sys.stdout.flush()
sys.stdin.readline()
statuses = set()
for number in range(int(sys.argv[2])):
    outcome = ledger.append(location, role="checker", action="check", objects=["**"], purpose=None,
                            approval_ref=None)
    statuses.add(outcome.status)
sys.stdout.write(",".join(sorted(statuses)) + "\\n")
"""


def _together(scripts: list[list[str]]) -> list[subprocess.CompletedProcess[bytes]]:
    """Start the processes, wait until each is ready, then let them go at the same time."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    children = [
        subprocess.Popen(
            [sys.executable, "-c", *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        for args in scripts
    ]
    for child in children:
        assert child.stdout is not None and child.stdout.readline().strip() == b"ready"
    for child in children:
        assert child.stdin is not None
        child.stdin.write(b"go\n")
        child.stdin.flush()
    results = []
    for child, args in zip(children, scripts, strict=True):
        out, err = child.communicate(timeout=600)
        results.append(subprocess.CompletedProcess(args, child.returncode, out, err))
    return results


def test_consent_add_while_a_check_appends(tmp_path: Path) -> None:
    folder = _dataset(tmp_path)
    added, checked = _together([[ADD_PROCESS, str(folder), "07"], [CHECK_EVENTS, str(folder), "20"]])
    assert added.returncode == 0, added.stderr.decode("utf-8", "replace")
    assert checked.returncode == 0 and checked.stdout.decode("ascii").strip() == "written"  # no timeout
    events = _events(folder)
    assert sorted(event.action for event in events) == ["check"] * 20 + ["consent_manage"]
    verification = ledger.verify(_vault(folder))
    assert verification.intact and verification.events == 21
    assert parse_consents(_vault(folder).consents.read_bytes()).consents[0].subject == "sub-07"


def test_two_consent_adds_at_the_same_time(tmp_path: Path) -> None:
    folder = _dataset(tmp_path)
    runs = _together([[ADD_PROCESS, str(folder), "07"], [ADD_PROCESS, str(folder), "08"]])
    assert [result.returncode for result in runs] == [0, 0], [r.stderr for r in runs]
    subjects = [r.subject for r in parse_consents(_vault(folder).consents.read_bytes()).consents]
    assert subjects == ["sub-07", "sub-08"]  # neither rewrite lost the other's record
    assert ledger.verify(_vault(folder)).events == 2 and ledger.verify(_vault(folder)).intact


# --- shells and languages (CLI-08: PowerShell 5.1/7 and Bash, a Chinese path) ---------------------------

BASH_ADD = """set -u
"$1" -m neurogrid vault consent add "$2" --subject 07 --version 1 --date 2026-01-01 \\
    --uses training,validation --role QA > /dev/null
echo "add $?" > "$3"
"$1" -m neurogrid vault consent add "$2" --subject 07 --version 1 --date 2026-01-01 \\
    --uses training --role QA 2> /dev/null
echo "again $?" >> "$3"
"""
POWERSHELL_ADD = """$py, $dataset, $codes = $args[0..2]
& $py -m neurogrid vault consent add $dataset --subject 07 --version 1 --date 2026-01-01 `
    --uses training,validation --role QA | Out-Null
Set-Content -Path $codes -Value "add $LASTEXITCODE"
& $py -m neurogrid vault consent add $dataset --subject 07 --version 1 --date 2026-01-01 `
    --uses training --role QA 2> $null
Add-Content -Path $codes -Value "again $LASTEXITCODE"
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


def _check_shell_run(folder: Path, codes: Path) -> None:
    assert codes.read_text(encoding="utf-8-sig").split() == ["add", "0", "again", "2"]
    records = parse_consents(_vault(folder).consents.read_bytes()).consents
    assert [(r.subject, r.permitted_uses) for r in records] == [("sub-07", ("training", "validation"))]
    assert ledger.verify(_vault(folder)).intact and ledger.verify(_vault(folder)).events == 1


def test_consent_add_in_git_bash_with_a_chinese_path(tmp_path: Path) -> None:
    bash = _git_bash()
    if bash is None:
        pytest.skip("bash not available")
    folder = _dataset(tmp_path / "数据集")
    codes = tmp_path / "codes.txt"
    posix = [Path(p).as_posix() for p in (sys.executable, str(folder), str(codes))]
    result = subprocess.run(
        [bash, "-c", BASH_ADD, "add", *posix], capture_output=True, env=dict(os.environ), check=False
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    _check_shell_run(folder, codes)


def test_consent_add_in_windows_powershell_with_a_chinese_path(tmp_path: Path) -> None:
    powershell = shutil.which("powershell") if sys.platform == "win32" else None
    if powershell is None:
        pytest.skip("Windows PowerShell 5.1 only exists on Windows")
    folder = _dataset(tmp_path / "数据集")
    codes = tmp_path / "codes.txt"
    script = tmp_path / "add.ps1"
    script.write_text(POWERSHELL_ADD, encoding="utf-8-sig")  # PowerShell 5.1 reads UTF-8 only with a BOM
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        + [sys.executable, str(folder), str(codes)],
        capture_output=True,
        env=dict(os.environ),
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    _check_shell_run(folder, codes)


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_help_of_consent_add_follows_the_language(lang: str, capsys: pytest.CaptureFixture[str]) -> None:
    import re

    tr = translator(lang).t
    code, out, err = run(["--lang", lang, "vault", "consent", "add", "--help"], capsys)
    assert code == 0 and not err
    flat = re.sub(r"\s+", "", out)
    for name in (
        "about",
        "path",
        "subject",
        "version",
        "date",
        "uses",
        "withdrawn",
        "ethics_ref",
        "from",
        "config",
        "role",
        "purpose",
        "approval_ref",
    ):
        assert re.sub(r"\s+", "", tr(f"cli.help.vault.consent.add.{name}")) in flat, name
    assert ("Usage:" in out) is (lang == "en")
