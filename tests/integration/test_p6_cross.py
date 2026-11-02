"""P6 across its areas (KONZEPT row P6, UF-03, UF-06, ARC-01; A-90, A-91, A-92): the flows that need the
vault, the consent records and the placeholder pack together, through the real command line. The areas test
their own parts in test_vault_pipeline.py, test_consent_pipeline.py and test_yyt2029_scaffold.py."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from conftest import DOCUMENTED_TOML, dir_link  # type: ignore[import-not-found]
from neurogrid.cli import main
from neurogrid.report.texts import translator
from neurogrid.vault import ledger
from neurogrid.vault.store import locate
from report_html import visible_text  # type: ignore[import-not-found]

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = "2026-10-11"
VAULT = Path(".neurogrid", "vault")
SUBJECTS = ("01", "02", "03", "04", "05", "06")  # bids_ai_ok: 01-04 in train, 05 in val, 06 in test
YYT = ("--rulepack", "yyt2029", "--allow-draft-rulepacks")


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(["--lang", "en", *args])
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def _dataset(tmp_path: Path, fixture: str = "bids_ai_ok", *, name: str = "data") -> Path:
    folder = tmp_path / name
    shutil.copytree(FIX / fixture, folder)
    (folder / ".neurogrid").mkdir(exist_ok=True)
    toml = folder / ".neurogrid" / "neurogrid.toml"
    if not toml.exists():  # bids_ai_ok brings its own, with the splits
        toml.write_text(DOCUMENTED_TOML, encoding="utf-8")
    return folder


def _init(folder: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(["vault", "init", str(folder)], capsys)
    assert code == 0, out + err


def _add(
    folder: Path, capsys: pytest.CaptureFixture[str], subject: str, *fields: str, version: str = "1"
) -> tuple[int, str, str]:
    return run(
        [
            "vault",
            "consent",
            "add",
            str(folder),
            "--subject",
            subject,
            "--version",
            version,
            "--role",
            "data_steward",
            *fields,
        ],
        capsys,
    )


def _consents_of_all(folder: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for subject in SUBJECTS:
        code, out, err = _add(
            folder, capsys, subject, "--date", "2026-03-01", "--uses", "training,validation"
        )
        assert code == 0, out + err


def _check(
    folder: Path, out: Path, capsys: pytest.CaptureFixture[str], *extra: str
) -> tuple[int, dict[str, Any], str]:
    code, stdout, stderr = run(["check", str(folder), "--out", str(out), "--as-of", AS_OF, *extra], capsys)
    assert code in (0, 1), stdout + stderr
    return code, json.loads(out.read_bytes()), stdout + stderr


def _statuses(results: dict[str, Any], rule: str) -> list[str]:
    found = [finding["status"] for finding in results["findings"] if finding["rule_id"] == rule]
    return found + ["passed" for entry in results["passed"] if entry["rule_id"] == rule]


def _events(folder: Path) -> list[dict[str, Any]]:
    text = (folder / VAULT / "access.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_uf06_init_consent_add_log_show_verify(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """UF-06: a vault from nothing: init, a consent and a manual entry, both in the log; the chain is
    intact, a recorded head stays part of it, a changed entry is found and the old head of a rewritten log
    is missing."""
    folder = _dataset(tmp_path)
    _init(folder, capsys)
    code, out, err = _add(folder, capsys, "01", "--date", "2026-03-01", "--uses", "training")
    assert code == 0, out + err
    code, out, err = run(
        [
            "vault",
            "log",
            str(folder),
            "--action",
            "read",
            "--objects",
            "**",
            "--purpose",
            "review of the split",
            "--role",
            "QA.lead",
        ],
        capsys,
    )
    assert code == 0, out + err
    events = _events(folder)
    assert [event["action"] for event in events] == ["consent_manage", "read"]
    assert events[0]["objects"] == [".neurogrid/vault/consents.yaml"]
    assert events[1]["role"] == "QA.lead" and events[1]["purpose"] == "review of the split"

    code, out, err = run(["vault", "log", str(folder), "--show"], capsys)
    assert code == 0, out + err
    assert "QA.lead" in out and "review of the split" in out and events[1]["hash"] in out

    head = events[1]["hash"]
    code, out, err = run(["vault", "verify", str(folder), "--expect-head", head], capsys)
    assert code == 0, out + err
    log = folder / VAULT / "access.jsonl"
    original = log.read_bytes()
    log.write_bytes(original.replace(b"review of the split", b"review of the plits"))
    code, out, err = run(["vault", "verify", str(folder)], capsys)
    assert code == 1, out + err
    log.write_bytes(original.splitlines(keepends=True)[0])  # cut at the end: found only through the head
    assert run(["vault", "verify", str(folder)], capsys)[0] == 0
    code, out, err = run(["vault", "verify", str(folder), "--expect-head", head], capsys)
    assert code == 1, out + err


def test_uf03_consent_documented_and_checked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """UF-03: consents recorded through the command line decide M14; a withdrawal is a new version and turns
    it red; results.json keeps the subject, the report shows M14 without it."""
    folder = _dataset(tmp_path)
    _init(folder, capsys)
    target = tmp_path / "r.json"
    _, results, _ = _check(folder, target, capsys)
    assert _statuses(results, "CORE-M14-01") == ["not_checkable"]  # no data yet

    _consents_of_all(folder, capsys)
    _, results, _ = _check(folder, target, capsys)
    assert set(_statuses(results, "CORE-M14-01")) == {"passed"}

    code, out, err = _add(folder, capsys, "03", "--date", "2026-06-01", "--withdrawn", version="2")
    assert code == 0, out + err
    code, results, _ = _check(folder, target, capsys)
    assert code == 1
    failed = [f for f in results["findings"] if f["rule_id"] == "CORE-M14-01" and f["status"] == "failed"]
    assert len(failed) == 1 and failed[0]["reason"] == "consent.withdrawn"
    assert "sub-03" in failed[0]["object"]
    assert results["config"]["consents_sha256"]

    code, out, err = run(
        ["report", str(target), "--lang", "en", "--format", "html", "--out", str(tmp_path / "rep")], capsys
    )
    assert code == 0, out + err
    html = (tmp_path / "rep" / "report.en.html").read_text(encoding="utf-8")
    assert translator("en").t("report.consent.note") in visible_text(html)
    assert failed[0]["key"] not in html


@pytest.mark.parametrize("jobs", ["1", "4"])
def test_dod_two_checks_vault_consents_yyt2029_byte_identical(
    jobs: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD P6: with a vault that holds a log and consents and with the placeholder pack, every run appends
    an event while results.json stays byte-identical; the placeholder pack changes neither exit code nor
    light."""
    folder = _dataset(tmp_path)
    _init(folder, capsys)
    _consents_of_all(folder, capsys)
    before = len(_events(folder))
    first, second = tmp_path / "1.json", tmp_path / "2.json"
    code_1, results, _ = _check(folder, first, capsys, *YYT, "--jobs", jobs)
    code_2, _, _ = _check(folder, second, capsys, *YYT, "--jobs", jobs)
    assert code_1 == code_2
    assert first.read_bytes() == second.read_bytes()
    assert len(_events(folder)) == before + 2
    head = _events(folder)[-1]["hash"].encode("ascii")
    assert head not in first.read_bytes()

    without = tmp_path / "plain.json"
    code_plain, plain, _ = _check(folder, without, capsys, "--jobs", jobs)
    assert code_plain == code_1
    assert plain["summary"]["errors"] == results["summary"]["errors"]
    assert plain["summary"]["phases"] == results["summary"]["phases"]


def test_linked_vault_and_linked_consents_exit2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A link in the vault path or at consents.yaml is never followed (p6 decisions 2): check, consent add,
    vault verify and report --config end with exit 2 and touch nothing behind the link."""
    outside = _dataset(tmp_path, name="other")
    _init(outside, capsys)
    keep = {path.name: path.read_bytes() for path in (outside / VAULT).iterdir()}

    folder = _dataset(tmp_path)
    dir_link(folder / VAULT, outside / VAULT)
    toml = folder / ".neurogrid" / "neurogrid.toml"
    results = tmp_path / "plain.json"
    plain = _dataset(tmp_path, "edf_ok", name="plain")
    assert run(["check", str(plain), "--out", str(results), "--as-of", AS_OF], capsys)[0] in (0, 1)

    calls: list[list[str]] = [
        ["check", str(folder), "--out", str(tmp_path / "r.json"), "--as-of", AS_OF],
        [
            "vault",
            "consent",
            "add",
            str(folder),
            "--subject",
            "01",
            "--version",
            "1",
            "--date",
            "2026-03-01",
            "--uses",
            "training",
            "--role",
            "data_steward",
        ],
        ["vault", "verify", str(folder)],
        ["report", str(results), "--out", str(tmp_path / "rep"), "--config", str(toml)],
    ]
    for call in calls:
        code, out, err = run(call, capsys)
        assert code == 2, (call[0], out + err)
    assert {path.name: path.read_bytes() for path in (outside / VAULT).iterdir()} == keep

    second = _dataset(tmp_path, name="second")
    _init(second, capsys)
    consents = second / VAULT / "consents.yaml"
    consents.unlink()
    try:
        consents.symlink_to(outside / VAULT / "consents.yaml")
    except OSError:
        pytest.skip("file links not permitted on this system (the folder link above ran)")
    for call in (
        ["check", str(second), "--out", str(tmp_path / "r2.json"), "--as-of", AS_OF],
        [
            "vault",
            "consent",
            "add",
            str(second),
            "--subject",
            "01",
            "--version",
            "1",
            "--date",
            "2026-03-01",
            "--uses",
            "training",
            "--role",
            "data_steward",
        ],
    ):
        code, out, err = run(call, capsys)
        assert code == 2, (call[0], out + err)
    assert {path.name: path.read_bytes() for path in (outside / VAULT).iterdir()} == keep


def test_vault_without_access_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A present vault without access.jsonl is never repaired silently (p6 decisions 2, 3): consent add
    refuses and writes nothing; check finds it, warns that its event was not written and ends with exit 1;
    vault verify reports a deviation."""
    folder = _dataset(tmp_path)
    _init(folder, capsys)
    log = folder / VAULT / "access.jsonl"
    consents = folder / VAULT / "consents.yaml"
    before = consents.read_bytes()
    log.unlink()

    code, out, err = _add(folder, capsys, "01", "--date", "2026-03-01", "--uses", "training")
    assert code == 2, out + err
    assert consents.read_bytes() == before and not log.exists()

    code, results, text = _check(folder, tmp_path / "r.json", capsys)
    assert code == 1
    (finding,) = [f for f in results["findings"] if f["rule_id"] == "CORE-NV03-01"]
    assert (finding["status"], finding["reason"]) == ("failed", "vault.log_missing")
    tr = translator("en").t
    assert tr("cli.vault.event_not_written", reason=tr("cli.vault.event_reason.log_missing")) in text
    assert not log.exists()

    code, out, err = run(["vault", "verify", str(folder)], capsys)
    assert code == 1, out + err


def _five_stages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], formats: str
) -> tuple[Path, dict[str, Any]]:
    folder = _dataset(tmp_path)
    _init(folder, capsys)
    _consents_of_all(folder, capsys)
    target = tmp_path / "r.json"
    _, results, _ = _check(folder, target, capsys, "--rulepack", "bids", *YYT)
    toml = folder / ".neurogrid" / "neurogrid.toml"
    code, out, err = run(
        ["report", str(target), "--lang", "zh,en", "--format", formats, "--out", str(tmp_path / "rep")]
        + ["--config", str(toml)],
        capsys,
    )
    assert code == 0, out + err
    return folder, results


def test_five_stages_with_suppliers(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """ARC-01: dataset -> adapter and data model -> checkers (with consent and access log, whose supplier is
    the vault) -> rule packs (core, bids, the placeholder pack) -> reports zh/en with the access log."""
    folder, results = _five_stages(tmp_path, capsys, "html")
    assert results["recordings"]  # dataset and adapter
    assert {pack["name"] for pack in results["rulepacks"]} == {"core", "bids", "yyt2029"}  # rule packs
    rules = {f["rule_id"] for f in results["findings"]} | {p["rule_id"] for p in results["passed"]}
    assert {"CORE-M14-01", "CORE-NV03-01", "CORE-NV03-02"} <= rules  # checkers with the vault as supplier
    assert "YYT2029-ACQ-001" in rules
    assert set(_statuses(results, "CORE-NV03-01")) == {"passed"}
    assert set(_statuses(results, "CORE-M14-01")) == {"passed"}

    head = ledger.verify(locate(folder, VAULT.as_posix())).head
    assert head is not None
    for lang in ("zh", "en"):
        tr = translator(lang).t
        html = (tmp_path / "rep" / f"report.{lang}.html").read_text(encoding="utf-8")
        text = visible_text(html)
        assert tr("report.label.access_log") in text
        assert tr("report.text.os_access") in text
        assert tr("report.placeholder_banner") in text
    assert _events(folder)[-1]["action"] == "report"


@pytest.mark.pdf
def test_five_stages_print(tmp_path: Path, capsys: pytest.CaptureFixture[str], pdf_shell: object) -> None:
    """The same flow printed: the PDFs pass the QA gate of ``report``, which ends with exit 0 only then."""
    _five_stages(tmp_path, capsys, "pdf")
    for lang in ("zh", "en"):
        assert (tmp_path / "rep" / f"report.{lang}.pdf").read_bytes().startswith(b"%PDF-")
