"""NeuroVault in the pipeline (NV-F03, NV-F01, ARC-01, CLI-03, CLI-08, CLI-09, DoD P6; A-30, A-51, A-82, A-90;
p6 decisions 2, 4, 6, 7 and 11): the access events of check, convert, report --config, scan, manifest and
verify (appended after the outputs, never exit 2 for a failed event), --role, the link rule, the access log in
results.json (CORE-NV03-01/02 only; byte-identical runs) and in the report (cover row, notes), and privacy
(no user or host name, pseudonymous objects)."""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

import neurogrid
from conftest import DOCUMENTED_TOML, dir_link, holding_process, wait_released  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.cli import main
from neurogrid.io.provenance import KNOWN_CONTROL_FILES, show
from neurogrid.report.texts import translator
from neurogrid.vault import ledger
from neurogrid.vault import lock as vault_lock
from neurogrid.vault.store import init_vault, locate
from report_html import visible_text  # type: ignore[import-not-found]

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = "2026-10-11"
VAULT = Path(".neurogrid", "vault")
ROLE_TOML = (
    '[vault]\nrole = "data_steward"\npurpose = "pre-check before registration"\napproval_ref = "EC-2026-17"\n'
)
HOLD = """
import sys
from pathlib import Path
from neurogrid.vault.lock import exclusive
with exclusive(Path(sys.argv[1])):
    sys.stdout.write(sys.argv[1] + "\\n")
    sys.stdout.flush()
    sys.stdin.readline()
"""
READ_ONLY_MODES = sys.platform != "win32" and os.geteuid() == 0  # root writes read-only files


def _t(key: str, **params: Any) -> str:
    return translator("en").t(key, **params)


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(["--lang", "en", *args])
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def _dataset(tmp_path: Path, *, vault: bool = True, toml: str = "", fixture: str = "edf_ok") -> Path:
    """A copy of the fixture with neurogrid.toml at its default location (the required metadata documented,
    so that only the subject of a test decides the exit code) and, with ``vault``, an initialised vault."""
    folder = tmp_path / "data"
    shutil.copytree(FIX / fixture, folder)
    (folder / ".neurogrid").mkdir()
    (folder / ".neurogrid" / "neurogrid.toml").write_text(DOCUMENTED_TOML + toml, encoding="utf-8")
    if vault:
        init_vault(locate(folder, VAULT.as_posix()))
    return folder


def _check(folder: Path, out: Path, capsys: pytest.CaptureFixture[str], *extra: str) -> tuple[int, str, str]:
    return run(["check", str(folder), "--out", str(out), "--as-of", AS_OF, *extra], capsys)


def _log(folder: Path) -> bytes:
    return (folder / VAULT / "access.jsonl").read_bytes()


def _events(folder: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in _log(folder).decode("utf-8").splitlines() if line.strip()]


def _statuses(results: dict[str, Any], rule: str) -> list[tuple[str, str | None]]:
    statuses = [(f["status"], f.get("reason")) for f in results["findings"] if f["rule_id"] == rule]
    statuses += [("passed", None) for p in results["passed"] if p["rule_id"] == rule]
    return statuses


@contextmanager
def _locked(folder: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Another process holds the vault lock; this process waits only 0.3 s for it."""
    monkeypatch.setattr(vault_lock, "LOCK_TIMEOUT_S", 0.3)
    lock = folder / VAULT / "access.jsonl.lock"
    with holding_process(HOLD, str(lock)):
        yield
    wait_released(lock)


# --- check -------------------------------------------------------------------------------------------------


def test_check_appends_one_event(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """KONZEPT 1.4 step 8: one event after results.json: action check, the whole dataset, --role over [vault]
    role (CLI-03), purpose and approval reference from [vault], the NeuroGrid version; no user or host."""
    folder = _dataset(tmp_path, toml=ROLE_TOML)
    code, out, err = _check(folder, tmp_path / "r.json", capsys, "--role", "QA.lead")
    assert code == 0, out + err
    (event,) = _events(folder)
    assert event == {
        **event,
        "seq": 1,
        "previous_hash": ledger.GENESIS,
        "action": "check",
        "objects": ["**"],
        "role": "QA.lead",
        "purpose": "pre-check before registration",
        "approval_ref": "EC-2026-17",
        "tool_version": neurogrid.__version__,
    }
    assert set(event) == {
        "format_version",
        "seq",
        "time",
        "role",
        "action",
        "objects",
        "purpose",
        "approval_ref",
        "tool_version",
        "previous_hash",
        "hash",
    }
    results = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert results["config"]["effective_settings"]["vault"]["role"] == "QA.lead"
    assert _statuses(results, "CORE-NV03-01") == [("passed", None)]  # measured before the own event
    assert _statuses(results, "CORE-NV03-02") == [("passed", None)]
    for key in ("cli.vault.role_missing", "cli.vault.role_without_vault", "cli.vault.role_looks_identifying"):
        assert _t(key) not in out
    assert "event_not_written" not in out and _t("cli.vault.event_not_written", reason="x")[:20] not in out
    code, _, _ = _check(folder, tmp_path / "r2.json", capsys)
    second = _events(folder)[1]
    assert code == 0 and second["role"] == "data_steward" and second["previous_hash"] == event["hash"]
    settings = json.loads((tmp_path / "r2.json").read_text(encoding="utf-8"))["config"]["effective_settings"]
    assert settings["vault"]["role"] == "data_steward"


def test_check_without_role_writes_null_role_and_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _dataset(tmp_path)
    code, out, _ = _check(folder, tmp_path / "r.json", capsys)
    (event,) = _events(folder)
    assert code == 0 and event["role"] is None and event["purpose"] is None and event["approval_ref"] is None
    assert _t("cli.vault.role_missing") in out


def test_check_role_looking_identifying_warns_and_is_recorded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _dataset(tmp_path)
    code, out, _ = _check(folder, tmp_path / "r.json", capsys, "--role", "Wang_Wei")
    assert (
        code == 0
        and _t("cli.vault.role_looks_identifying") in out
        and _events(folder)[0]["role"] == "Wang_Wei"
    )


def test_check_role_invalid_exit2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An invalid --role ends the run before anything is read, with and without a vault (p6 decisions 4)."""
    for vault in (True, False):
        folder = _dataset(tmp_path / str(vault), vault=vault)
        for role in ("QA lead", "1QA", "Zhang San", "a" * 81, ""):
            code, _, err = _check(folder, tmp_path / "r.json", capsys, "--role", role)
            assert code == 2 and _t("errors.vault.role_invalid") in err, role
            assert not (tmp_path / "r.json").exists()
        if vault:
            assert _log(folder) == b""


def test_role_without_vault_hint_no_files_created(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _dataset(tmp_path, vault=False)
    before = sorted(path.relative_to(folder) for path in folder.rglob("*"))
    code, out, _ = _check(folder, tmp_path / "r.json", capsys, "--role", "QA")
    assert code == 0 and _t("cli.vault.role_without_vault") in out and _t("cli.vault.role_missing") not in out
    assert sorted(path.relative_to(folder) for path in folder.rglob("*")) == before
    results = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert _statuses(results, "CORE-NV03-01") == [("not_checkable", "vault.not_found")]
    assert _statuses(results, "CORE-NV03-02") == [("not_checkable", "vault.not_found")]
    code, out, _ = _check(folder, tmp_path / "r2.json", capsys)
    assert code == 0 and _t("cli.vault.role_without_vault") not in out


def test_two_checks_with_vault_byte_identical(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """DoD P6: every run appends an event, results.json stays byte-identical (jobs 1 and 4); it holds no head
    hash, no event time or number (A-30, KONZEPT 2.3)."""
    folder = _dataset(tmp_path, toml=ROLE_TOML)
    outputs = []
    for number, jobs in enumerate(("1", "1", "4")):
        target = tmp_path / f"r{number}.json"
        code, out, err = _check(folder, target, capsys, "--jobs", jobs)
        assert code == 0, out + err
        outputs.append(target.read_bytes())
    assert outputs[0] == outputs[1] == outputs[2]
    events = _events(folder)
    assert [event["seq"] for event in events] == [1, 2, 3]
    for event in events:
        for value in (event["hash"], event["time"]):
            assert value.encode("ascii") not in outputs[0], value
    assert b"access.jsonl" not in outputs[0] and b"previous_hash" not in outputs[0]
    vault_settings = json.loads(outputs[0])["config"]["effective_settings"]["vault"]
    assert set(vault_settings) == {"path", "role", "purpose", "approval_ref"}


def test_reordered_log_two_checks_byte_identical(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """p6 decisions 6: an append after a reorder of the last two entries changes the likely cause that vault
    verify names (reorder, then not any more), never results.json: its details are first line, kind and
    number of deviations only."""
    folder = _dataset(tmp_path)
    location = locate(folder, VAULT.as_posix())
    for _ in range(4):
        assert (
            ledger.append(
                location, role="QA", action="check", objects=["**"], purpose=None, approval_ref=None
            ).status
            == "written"
        )
    lines = _log(folder).splitlines(keepends=True)
    (folder / VAULT / "access.jsonl").write_bytes(b"".join([*lines[:2], lines[3], lines[2]]))
    likely_before = {d.likely for d in ledger.verify(location).deviations}
    outputs = []
    for number in range(2):
        target = tmp_path / f"r{number}.json"
        assert _check(folder, target, capsys, "--role", "QA")[0] == 1  # CORE-NV03-01 is an error
        outputs.append(target.read_bytes())
    likely_after = {d.likely for d in ledger.verify(location).deviations}
    assert likely_before == {"reorder"} and likely_after != likely_before
    assert outputs[0] == outputs[1]
    (finding,) = [f for f in json.loads(outputs[0])["findings"] if f["rule_id"] == "CORE-NV03-01"]
    assert finding["status"] == "failed" and finding["reason"] == "vault.chain_broken"
    assert finding["details"] == {"first_line": 3, "kind": "link_mismatch", "deviations": 2}
    assert finding["file"] == ".neurogrid/vault/access.jsonl"


def test_check_read_only_vault_warns_and_finding_no_exit2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A-30: a read-only vault gives a warning and a finding (CORE-NV03-02), never exit code 2."""
    if READ_ONLY_MODES:
        pytest.skip("root writes read-only files")
    folder = _dataset(tmp_path)
    log = folder / VAULT / "access.jsonl"
    log.chmod(stat.S_IREAD)
    try:
        code, out, err = _check(folder, tmp_path / "r.json", capsys, "--role", "QA")
    finally:
        log.chmod(stat.S_IREAD | stat.S_IWRITE)
    assert code == 0, out + err  # a warning rule: the exit code is that of the run without it
    reason = _t("cli.vault.event_reason.not_writable")
    assert _t("cli.vault.event_not_written", reason=reason) in out and _log(folder) == b""
    results = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert _statuses(results, "CORE-NV03-02") == [("failed", "vault.not_writable")]
    assert _statuses(results, "CORE-NV03-01") == [("passed", None)]
    assert results["summary"]["phases"]["access"]["light"] == "yellow"


def test_check_locked_vault_console_warning_exit_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _dataset(tmp_path)
    with _locked(folder, monkeypatch):
        code, out, err = _check(folder, tmp_path / "r.json", capsys, "--role", "QA")
    assert code == 0, out + err
    assert _t("cli.vault.event_not_written", reason=_t("cli.vault.event_reason.locked")) in out
    results = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert _statuses(results, "CORE-NV03-01") == [("not_checkable", "vault.locked")]
    assert _log(folder) == b""


def test_vault_without_access_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A present vault without access.jsonl is never repaired silently: CORE-NV03-01 fails (exit 1), the event
    is not written (a warning), vault verify reports the deviation log_missing (exit 1)."""
    folder = _dataset(tmp_path)
    (folder / VAULT / "access.jsonl").unlink()
    code, out, _ = _check(folder, tmp_path / "r.json", capsys, "--role", "QA")
    assert code == 1
    assert _t("cli.vault.event_not_written", reason=_t("cli.vault.event_reason.log_missing")) in out
    results = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert _statuses(results, "CORE-NV03-01") == [("failed", "vault.log_missing")]
    assert _statuses(results, "CORE-NV03-02") == [("failed", "vault.log_missing")]
    assert run(["vault", "verify", str(folder)], capsys)[0] == 1
    assert not (folder / VAULT / "access.jsonl").exists()


@pytest.mark.parametrize("part", ["vault", "access.jsonl", "consents.yaml"])
def test_check_link_in_vault_path_exit2_before_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, part: str
) -> None:
    """p6 decisions 2: a link in the vault path, at the log or at consents.yaml is never followed: check ends
    with exit 2 before the data are read, whichever rules are loaded; so does report --config."""
    folder = _dataset(tmp_path, vault=part != "vault")
    results = tmp_path / "results.json"
    assert _check(folder, results, capsys)[0] == 0  # before the link: the results report renders below
    target = tmp_path / "elsewhere"
    if part == "vault":
        target.mkdir()
        dir_link(folder / VAULT, target)
    else:
        target.write_bytes(b"")
        (folder / VAULT / part).unlink()
        try:
            (folder / VAULT / part).symlink_to(target)
        except OSError:
            pytest.skip("file links not permitted on this system")

    def _no_scan(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the dataset was read")

    monkeypatch.setattr(pipeline, "scan", _no_scan)
    for extra in ([], ["--rulepack", "bids"]):
        code, _, err = _check(folder, tmp_path / "r.json", capsys, *extra)
        assert code == 2 and _t("errors.vault.link", part=part) in err
    assert not (tmp_path / "r.json").exists()
    code, _, err = run(["vault", "verify", str(folder)], capsys)
    assert code == 2 and _t("errors.vault.link", part=part) in err
    toml = folder / ".neurogrid" / "neurogrid.toml"
    code, _, err = run(
        ["report", str(results), "--out", str(tmp_path / "rep"), "--config", str(toml)], capsys
    )
    assert code == 2 and _t("errors.vault.link", part=part) in err and not (tmp_path / "rep").exists()
    assert target.read_bytes() == b"" if target.is_file() else not any(target.iterdir())


def test_check_vault_path_no_folder_exit2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _dataset(tmp_path, vault=False)
    (folder / VAULT).write_bytes(b"not a folder")
    code, _, err = _check(folder, tmp_path / "r.json", capsys)
    assert code == 2 and _t("errors.vault.not_folder") in err and not (tmp_path / "r.json").exists()


def test_check_invalid_vault_fields_exit2_before_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A purpose or approval reference that cannot be recorded is a configuration error at the start, never a
    lost event after results.json: config.invalid naming the field (P6 review: as a role off the pattern)."""
    folder = _dataset(tmp_path, toml='[vault]\npurpose = "line one\\nline two"\n')
    code, _, err = _check(folder, tmp_path / "r.json", capsys)
    assert code == 2 and _t("errors.config.invalid", field="vault.purpose", problem="value_error") in err
    assert not (tmp_path / "r.json").exists() and _log(folder) == b""
    other = _dataset(tmp_path / "other", toml='[vault]\nrole = "QA lead"\n')
    code, _, err = _check(other, tmp_path / "r.json", capsys)
    assert code == 2 and "vault.role" in err


@pytest.mark.parametrize(
    ("toml", "field", "problem"),
    [
        ('[vault]\npurpose = ""\n', "vault.purpose", "string_too_short"),
        ('[vault]\npurpose = "QA\\trun"\n', "vault.purpose", "value_error"),
        ('[vault]\napproval_ref = ""\n', "vault.approval_ref", "string_too_short"),
        ('[vault]\napproval_ref = "EC\\u0007-17"\n', "vault.approval_ref", "value_error"),
    ],
)
@pytest.mark.parametrize("vault", [False, True])
def test_vault_texts_of_the_toml_are_config_errors_for_every_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], toml: str, field: str, problem: str, vault: bool
) -> None:
    """P6 review (spec sections 4 and 5): a [vault] purpose or approval_ref that the access log cannot record
    (empty, a tab or another control character) is an invalid value of neurogrid.toml: every command that
    reads the file ends with exit 2 config.invalid naming the field, with or without a vault, before the data
    are read and without an event, as for [vault] role; never errors.vault.text_invalid of a pending event."""
    folder = _dataset(tmp_path, vault=vault, toml=toml)
    before = _log(folder) if vault else b""
    message = _t("errors.config.invalid", field=field, problem=problem)
    config = str(folder / ".neurogrid" / "neurogrid.toml")
    results = tmp_path / "results.json"
    commands = [
        ["check", str(folder), "--out", str(results), "--as-of", AS_OF],
        ["convert", str(folder), "--to", "bids", "--out", str(tmp_path / "bids")],
        ["manifest", str(folder)],
        ["vault", "init", str(folder)],
        [
            "vault",
            "log",
            str(folder),
            "--action",
            "read",
            "--objects",
            "**",
            "--purpose",
            "p",
            "--role",
            "QA",
        ],
    ]
    for args in commands:
        code, out, err = run(args, capsys)
        assert code == 2 and message in err, (args, out, err)
    assert not results.exists() and not (tmp_path / "bids").exists()
    assert not (folder / ".neurogrid" / "manifest.json").exists()
    good = _dataset(tmp_path / "good", vault=False)
    assert _check(good, results, capsys)[0] in (0, 1)
    code, out, err = run(["report", str(results), "--format", "html", "--config", config], capsys)
    assert code == 2 and message in err, (out, err)
    assert not (results.parent / "report.en.html").exists()
    if vault:
        assert _log(folder) == before


def test_check_single_file_has_no_vault(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _dataset(tmp_path)
    code, out, _ = _check(folder / "rec_a.edf", tmp_path / "r.json", capsys, "--role", "QA")
    assert code in (0, 1) and _log(folder) == b"" and _t("cli.vault.role_without_vault") in out
    results = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert _statuses(results, "CORE-NV03-01") == [("not_applicable", "vault.single_file")]


def test_manifest_then_check_with_vault_verify_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A-82: the access log and its lock file are left out of the manifest, so manifest -> check (appends,
    creates the lock) -> verify is clean and CORE-M13-02 passes; scan, manifest and verify append read events
    to the default vault without role, purpose or approval reference and without a role note."""
    folder = _dataset(tmp_path, toml=ROLE_TOML)
    (folder / VAULT / "access.jsonl.lock").unlink()
    code, out, _ = run(["manifest", str(folder)], capsys)
    assert code == 0 and _t("cli.vault.role_missing") not in out
    manifest = json.loads((folder / ".neurogrid" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["excluded"] == [".neurogrid/vault/access.jsonl", ".neurogrid/vault/access.jsonl.lock"]
    assert ".neurogrid/vault/consents.yaml" in {entry["path"] for entry in manifest["files"]}
    code, out, err = _check(folder, tmp_path / "r.json", capsys)
    assert code == 0, out + err
    results = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert _statuses(results, "CORE-M13-02") == [("passed", None)]
    code, out, _ = run(
        ["verify", str(folder), "--manifest", str(folder / ".neurogrid" / "manifest.json")], capsys
    )
    assert code == 0 and _t("cli.vault.role_missing") not in out
    code, out, _ = run(["scan", str(folder)], capsys)
    assert code == 0 and _t("cli.vault.role_missing") not in out
    events = _events(folder)
    assert [(e["action"], e["role"], e["purpose"], e["approval_ref"]) for e in events] == [
        ("read", None, None, None),
        ("check", "data_steward", "pre-check before registration", "EC-2026-17"),
        ("read", None, None, None),
        ("read", None, None, None),
    ]
    assert all(event["objects"] == ["**"] for event in events)
    assert run(["vault", "verify", str(folder)], capsys)[0] == 0


def test_the_manifest_leaves_out_the_log_of_every_vault(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """P6 review (spec section 4, A-82): with a vault at the default location and another one at [vault] path,
    manifest leaves out the log and lock file of both (scan, manifest and verify append to the default one,
    check to the configured one), so every later verify and CORE-M13-02 stay clean. A manifest made before
    (it lists the default log) is compared without the default log and lock file as well."""
    from neurogrid.kernel.provenance import Exclusions, build_manifest, manifest_bytes

    folder = _dataset(tmp_path, toml='[vault]\npath = "audit/vault"\nrole = "QA"\n')
    init_vault(locate(folder, "audit/vault"))
    assert run(["manifest", str(folder)], capsys)[0] == 0
    manifest_file = folder / ".neurogrid" / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    logs = [
        f"{vault}/{name}"
        for vault in (".neurogrid/vault", "audit/vault")
        for name in ("access.jsonl", "access.jsonl.lock")
    ]
    assert manifest["excluded"] == logs
    assert not {entry["path"] for entry in manifest["files"]} & set(logs)
    for _ in range(2):  # each verify appends a read event to the default vault
        code, out, err = run(["verify", str(folder), "--manifest", str(manifest_file)], capsys)
        assert code == 0, out + err
    assert run(["scan", str(folder)], capsys)[0] == 0
    code, out, err = _check(folder, tmp_path / "r.json", capsys)
    assert code == 0, out + err
    results = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert _statuses(results, "CORE-M13-02") == [("passed", None)]
    assert [e["action"] for e in _events(folder)] == [
        "read",
        "read",
        "read",
        "read",
    ]  # manifest, 2 verify, scan
    assert [
        json.loads(line)["action"] for line in (folder / "audit/vault/access.jsonl").read_bytes().splitlines()
    ] == ["check"]
    # a manifest that excludes the configured vault only, as manifest wrote it before
    old = build_manifest(
        folder,
        Exclusions.of([".neurogrid/manifest.json", *logs[2:]]),
        excluded=logs[2:],
    ).manifest
    assert old is not None and ".neurogrid/vault/access.jsonl" in {item.path for item in old.files}
    manifest_file.write_bytes(manifest_bytes(old))
    assert run(["scan", str(folder)], capsys)[0] == 0  # the default log changes after the manifest
    code, out, err = run(["verify", str(folder), "--manifest", str(manifest_file)], capsys)
    assert code == 0, out + err
    code, out, err = _check(folder, tmp_path / "r2.json", capsys)
    results = json.loads((tmp_path / "r2.json").read_text(encoding="utf-8"))
    assert code == 0 and _statuses(results, "CORE-M13-02") == [("passed", None)], out + err


def test_check_compares_without_the_log_of_its_vault(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CORE-M13-02 leaves out the log and lock file of the run's own vault also when the manifest lists them
    (made before the vault was configured): check appends its event there after results.json."""
    from neurogrid.kernel.provenance import Exclusions, build_manifest, manifest_bytes

    folder = _dataset(tmp_path, vault=False, toml='[vault]\npath = "audit/vault"\n')
    init_vault(locate(folder, "audit/vault"))
    built = build_manifest(folder, Exclusions.of([".neurogrid/manifest.json"])).manifest
    assert built is not None and "audit/vault/access.jsonl" in {item.path for item in built.files}
    (folder / ".neurogrid" / "manifest.json").write_bytes(manifest_bytes(built))
    for name in ("r1.json", "r2.json"):  # the first check appends to audit/vault/access.jsonl
        code, out, err = _check(folder, tmp_path / name, capsys)
        results = json.loads((tmp_path / name).read_text(encoding="utf-8"))
        assert code == 0 and _statuses(results, "CORE-M13-02") == [("passed", None)], (name, out + err)
    assert (folder / "audit" / "vault" / "access.jsonl").read_bytes().count(b"\n") == 2


def test_read_events_only_at_the_default_location(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """p6 decisions 4: scan, manifest and verify read no neurogrid.toml for the vault; a vault at another
    [vault] path gets no read event (a documented narrowing), check does append there."""
    folder = _dataset(tmp_path, vault=False, toml='[vault]\npath = "vaults/v1"\n')
    location = locate(folder, "vaults/v1")
    init_vault(location)
    assert run(["scan", str(folder)], capsys)[0] == 0
    assert location.log.read_bytes() == b""
    assert _check(folder, tmp_path / "r.json", capsys)[0] == 0
    assert [json.loads(line)["action"] for line in location.log.read_bytes().splitlines()] == ["check"]


def test_read_commands_warn_on_a_linked_vault_exit_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """scan, manifest and verify do not own the vault: a link there means no event and a warning, never exit
    2 (p6 decisions 2)."""
    folder = _dataset(tmp_path, vault=False)
    target = tmp_path / "elsewhere"
    target.mkdir()
    dir_link(folder / VAULT, target)
    warning = _t("cli.vault.event_not_written", reason=_t("cli.vault.event_reason.link"))
    code, out, _ = run(["scan", str(folder)], capsys)
    assert code == 0 and warning in out
    code, out, _ = run(["manifest", str(folder)], capsys)
    assert code == 0 and warning in out
    code, out, _ = run(
        ["verify", str(folder), "--manifest", str(folder / ".neurogrid" / "manifest.json")], capsys
    )
    assert code == 0 and warning in out
    assert not any(target.iterdir())


def test_log_has_no_user_or_host(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A-30, A-51: an event holds no OS user, host name or absolute path, whatever the environment says."""
    planted = {"USERNAME": "PlantedUser73", "USER": "PlantedUser73", "COMPUTERNAME": "PLANTEDHOST9"}
    for name, value in planted.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("HOSTNAME", "PLANTEDHOST9")
    folder = _dataset(tmp_path)
    assert _check(folder, tmp_path / "r.json", capsys, "--role", "QA")[0] == 0
    assert run(["scan", str(folder)], capsys)[0] == 0
    log = _log(folder).decode("utf-8")
    for value in ("PlantedUser73", "PLANTEDHOST9", str(tmp_path), tmp_path.as_posix(), os.getpid()):
        assert str(value) not in log, value


def test_convert_appends_event_to_source_vault(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The source project's vault gets the convert event after the BIDS output is written; a link there is a
    warning (p6 decisions 2, 4)."""
    folder = _dataset(tmp_path, toml=ROLE_TOML)
    code, out, err = run(["convert", str(folder), "--to", "bids", "--out", str(tmp_path / "bids")], capsys)
    assert code == 0, out + err
    (event,) = _events(folder)
    assert (event["action"], event["objects"], event["role"]) == ("convert", ["**"], "data_steward")
    assert not (tmp_path / "bids" / ".neurogrid" / "vault").exists()
    linked = _dataset(tmp_path / "linked", vault=False)
    target = tmp_path / "elsewhere"
    target.mkdir()
    dir_link(linked / VAULT, target)
    code, out, _ = run(["convert", str(linked), "--to", "bids", "--out", str(tmp_path / "bids2")], capsys)
    assert code == 0
    assert _t("cli.vault.event_not_written", reason=_t("cli.vault.event_reason.link")) in out
    assert _t("cli.vault.role_missing") not in out  # no event, so no note on its role


def test_lock_file_is_a_known_control_file() -> None:
    """A-82, A-90: the name of the lock file is confirmed; raw folders show it in clear like the log."""
    for name in (".neurogrid/vault/access.jsonl", ".neurogrid/vault/access.jsonl.lock"):
        assert name in KNOWN_CONTROL_FILES and show(name, plain=False).file == name


# --- report --config ----------------------------------------------------------------------------------------


def _checked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[Path, Path]:
    folder = _dataset(tmp_path, toml=ROLE_TOML)
    results = tmp_path / "results.json"
    assert _check(folder, results, capsys)[0] == 0
    return folder, results


def test_report_with_config_shows_head_and_appends_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A-30: report --config shows the access log on the cover (entries, head before the report's own event,
    state) and the notes in the appendix, then appends its event (action report)."""
    folder, results = _checked(tmp_path, capsys)
    head = _events(folder)[-1]["hash"]
    toml = folder / ".neurogrid" / "neurogrid.toml"
    code, out, err = run(
        ["report", str(results), "--out", str(tmp_path / "rep"), "--config", str(toml)], capsys
    )
    assert code == 0, out + err
    events = _events(folder)
    assert [e["action"] for e in events] == ["check", "report"] and events[1]["role"] == "data_steward"
    for lang in ("en", "zh"):
        html = (tmp_path / "rep" / f"report.{lang}.html").read_text(encoding="utf-8")
        text = visible_text(html)
        tr = translator(lang).t
        assert f'<span class="mono">{head}</span>' in html
        for key in ("report.label.access_log", "report.value.access_log_state.intact"):
            assert tr(key) in text, key
        assert tr("report.text.access_log_note") in text and tr("report.text.os_access") in text
        assert events[1]["hash"] not in html  # the report's own event comes after the files


@pytest.mark.parametrize(
    ("place", "toml", "vault"),
    [
        (
            "data/conf/neurogrid.toml",
            '[vault]\nrole = "QA"\n',
            "data/.neurogrid/vault",
        ),  # inside, default path
        ("data/conf/neurogrid.toml", '[vault]\npath = "audit/vault"\nrole = "QA"\n', "data/audit/vault"),
        (
            "configs/neurogrid.toml",
            '[vault]\nrole = "QA"\n',
            "configs/.neurogrid/vault",
        ),  # outside the dataset
    ],
)
def test_report_config_finds_the_vault_of_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], place: str, toml: str, vault: str
) -> None:
    """P6 review (A-66): report --config resolves the project root of the file as check and the vault commands
    do for it: a file inside the dataset that is not in .neurogrid has the dataset root, which the report
    finds as the nearest folder above the file with .neurogrid, dataset_description.json or the vault path;
    a file outside the dataset has its own folder. So the report shows and extends the log check appended to,
    and never looks for a vault next to the file."""
    folder = tmp_path / "data"
    shutil.copytree(FIX / "edf_ok", folder)
    config = tmp_path / place
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(DOCUMENTED_TOML + toml, encoding="utf-8")
    assert run(["vault", "init", str(folder), "--config", str(config)], capsys)[0] == 0
    log = tmp_path / vault / "access.jsonl"
    assert log.is_file()
    results = tmp_path / "results.json"
    code, out, err = _check(folder, results, capsys, "--config", str(config))
    assert code == 0, out + err
    head = json.loads(log.read_bytes().splitlines()[-1])["hash"]
    code, out, err = run(
        ["report", str(results), "--lang", "en", "--out", str(tmp_path / "rep"), "--config", str(config)],
        capsys,
    )
    assert code == 0, out + err
    assert [json.loads(line)["action"] for line in log.read_bytes().splitlines()] == ["check", "report"]
    html = (tmp_path / "rep" / "report.en.html").read_text(encoding="utf-8")
    assert f'<span class="mono">{head}</span>' in html
    assert _t("report.value.access_log_state.intact") in visible_text(html)
    assert not (config.parent / ".neurogrid").exists() or config.parent == tmp_path / "configs"


def test_report_with_config_without_vault(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _dataset(tmp_path, vault=False)
    results = tmp_path / "results.json"
    assert _check(folder, results, capsys)[0] == 0
    toml = folder / ".neurogrid" / "neurogrid.toml"
    code, out, _ = run(
        ["report", str(results), "--lang", "en", "--out", str(tmp_path / "rep"), "--config", str(toml)],
        capsys,
    )
    text = visible_text((tmp_path / "rep" / "report.en.html").read_text(encoding="utf-8"))
    assert code == 0 and _t("report.value.access_log_state.not_found") in text
    assert not (folder / VAULT).exists() and _t("cli.vault.role_missing") not in out


def test_report_without_config_no_row_no_event_two_renders_identical(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without --config the report reads and writes no vault: no access-log row, no event, two renders are
    byte-identical; the appendix always states that the operating system governs access (KONZEPT 2.8)."""
    folder, results = _checked(tmp_path, capsys)
    before = _log(folder)
    rendered = []
    for name in ("a", "b"):
        assert run(["report", str(results), "--out", str(tmp_path / name)], capsys)[0] == 0
        rendered.append({path.name: path.read_bytes() for path in (tmp_path / name).iterdir()})
    assert rendered[0] == rendered[1] and _log(folder) == before
    for lang in ("en", "zh"):
        text = visible_text(rendered[0][f"report.{lang}.html"].decode("utf-8"))
        tr = translator(lang).t
        assert tr("report.label.access_log") not in text and tr("report.text.access_log_note") not in text
        assert tr("report.text.os_access") in text


def test_report_config_shows_a_broken_chain(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder, results = _checked(tmp_path, capsys)
    (folder / VAULT / "access.jsonl").write_bytes(_log(folder) + b"not json\n")
    toml = folder / ".neurogrid" / "neurogrid.toml"
    code, _, _ = run(
        ["report", str(results), "--lang", "en", "--out", str(tmp_path / "rep"), "--config", str(toml)],
        capsys,
    )
    text = visible_text((tmp_path / "rep" / "report.en.html").read_text(encoding="utf-8"))
    assert code == 0 and _t("report.value.access_log_state.broken", deviations=1) in text


# --- manual entries and the whole flow -------------------------------------------------------------------


def test_planted_identifiers_absent_from_access_jsonl_console_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """NZ-09, A-51: a manual object naming a file of a raw folder is recorded pseudonymously; neither the log,
    the console nor the report shows the planted name."""
    folder = _dataset(tmp_path, toml=ROLE_TOML)
    (folder / "notes").mkdir()
    (folder / "notes" / "ZhangSan_19610312.txt").write_text("planted\n", encoding="utf-8")
    name = "notes/ZhangSan_19610312.txt"
    code, out, err = run(
        ["vault", "log", str(folder), "--action", "read", "--objects", name, "--purpose", "copy"], capsys
    )
    assert code == 0, err
    results = tmp_path / "results.json"
    code, out2, _ = _check(folder, results, capsys)
    toml = folder / ".neurogrid" / "neurogrid.toml"
    code, out3, _ = run(
        ["report", str(results), "--out", str(tmp_path / "rep"), "--config", str(toml)], capsys
    )
    texts = [_log(folder).decode("utf-8"), out, out2, out3]
    texts += [path.read_text(encoding="utf-8") for path in (tmp_path / "rep").iterdir()]
    for text in texts:
        assert "ZhangSan" not in text and "19610312" not in text


def test_user_flow_init_log_show_verify(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """UF-06 (vault part; consent add joins with the consent area, export in P9): init, check, a manual
    entry, show and verify, with the head recorded outside and checked with --expect-head."""
    folder = _dataset(tmp_path, vault=False, toml=ROLE_TOML)
    assert run(["vault", "init", str(folder)], capsys)[0] == 0
    assert _check(folder, tmp_path / "r.json", capsys)[0] == 0
    code, out, _ = run(
        ["vault", "log", str(folder), "--action", "export", "--objects", "**", "--purpose", "review"], capsys
    )
    assert code == 0
    head = _events(folder)[-1]["hash"]
    code, out, _ = run(["vault", "log", str(folder), "--show"], capsys)
    assert (
        code == 0
        and _t("cli.vault.verify.head", hash=head) in out
        and _t("cli.vault.show.summary_intact") in out
    )
    code, out, _ = run(["vault", "verify", str(folder), "--expect-head", head], capsys)
    assert code == 0 and _t("cli.vault.verify.expected_found", hash=head, line=2, after=0) in out
    assert [e["action"] for e in _events(folder)] == ["check", "export"]  # show and verify record nothing
