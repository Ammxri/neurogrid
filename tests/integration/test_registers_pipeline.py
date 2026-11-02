"""The registers of the vault in the check pipeline (NV-F04, NV-F05, NV-F06; A-93 to A-95; C2; the P9
interface freeze): pipeline._load_vault_files reads roles.yaml, retention.yaml and risks.yaml before the
signal pass, each only when a loaded rule needs it; an invalid register ends the run with exit 2 before the
data are read; results.json carries config.roles_sha256, retention_sha256 and risks_sha256 (None without a
file or rule) and validates against its schema. The check IDs of the rules that follow (roles.permitted,
retention.*, consent.reconsent) are not registered yet, so the tests let a registered vault check stand for
them."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import jsonschema
import pytest

from conftest import DOCUMENTED_TOML  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.cli import main
from neurogrid.kernel.errors import ConfigError
from neurogrid.model.results import Results
from neurogrid.report.render import render_report
from neurogrid.report.texts import translator
from neurogrid.vault import ledger, retention, risks, roles
from neurogrid.vault.store import DEFAULT_VAULT_PATH, VaultLocation, init_vault, locate, pia_template
from report_html import visible_text  # type: ignore[import-not-found]

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
SCHEMAS = Path(__file__).parents[2] / "src" / "neurogrid" / "schemas"
AS_OF = dt.date(2026, 11, 20)
# A pack with one cheap dataset-level rule on the vault: the stand-in check of the tests below
LAB_PACK = """rulepack: lab
version: "1"
source: "Lab vault rule"
source_status: final
rules:
  - id: LAB-ACC-001
    clause: "LAB-1"
    title_zh: 访问日志完整
    title_en: Access log intact
    phase: access
    check: access.log_intact
    severity: error
    verification: automatic
"""
STAND_IN = "access.log_intact"
ROLES = b"format_version: 1\nroles:\n  - {role: QA, description: d, actions: [read], objects: ['**']}\n"
RETENTION = b"format_version: 1\nobjects:\n  - {object: pia, created: 2026-01-01, min_until: 2029-01-01}\n"
RISKS = (
    b"format_version: 1\nrisks:\n"
    b"  - {id: R1, date: 2026-01-01, description: d, affected_uses: [training], min_consent_version: 2}\n"
)


def _dataset(tmp_path: Path, *, vault: bool = True) -> Path:
    """edf_ok with the lab pack as its only pack (neurogrid.toml at the default location) and an initialised
    vault."""
    folder = tmp_path / "data"
    shutil.copytree(FIX / "edf_ok", folder)
    (folder / ".neurogrid").mkdir()
    (folder / "lab.yaml").write_text(LAB_PACK, encoding="utf-8")
    toml = DOCUMENTED_TOML + '\n[check]\nrulepacks = ["lab.yaml"]\n'
    (folder / ".neurogrid" / "neurogrid.toml").write_text(toml, encoding="utf-8")
    if vault:
        init_vault(locate(folder, DEFAULT_VAULT_PATH))
    return folder


def _vault(folder: Path) -> VaultLocation:
    return locate(folder, DEFAULT_VAULT_PATH)


def _check(folder: Path, tmp_path: Path) -> Results:
    options = pipeline.CheckOptions(as_of=AS_OF, work_base=tmp_path / "work")
    return pipeline.run_check(folder, options)


def _stand_in(monkeypatch: pytest.MonkeyPatch, *registers: str) -> None:
    """Let the lab rule's check stand for the checks that read ``registers`` (roles, retention, risks)."""
    if "roles" in registers:
        monkeypatch.setattr(pipeline, "ROLES_CHECK", STAND_IN)
    if "retention" in registers:
        monkeypatch.setattr(pipeline, "RETENTION_CHECKS", "access.")
    if "risks" in registers:
        monkeypatch.setattr(pipeline, "RISKS_CHECK", STAND_IN)


def test_the_check_ids_of_the_registers() -> None:
    """The rules of A-93 to A-95 name these checks (p9 decisions 3 to 5); the pipeline reads the registers
    for exactly them."""
    assert pipeline.ROLES_CHECK == "roles.permitted"
    assert pipeline.RETENTION_CHECKS == "retention."
    assert pipeline.RISKS_CHECK == "consent.reconsent"


@pytest.mark.parametrize(
    ("check_ids", "read"),
    [
        (set(), set()),
        ({"roles.permitted"}, {"roles"}),
        ({"retention.complete"}, {"retention"}),
        ({"retention.ending", "pia.edited"}, {"retention"}),
        ({"pia.edited"}, set()),
        ({"consent.reconsent"}, {"risks"}),
        ({"consent.covered"}, set()),
        ({"roles.permitted", "retention.complete", "consent.reconsent"}, {"roles", "retention", "risks"}),
    ],
)
def test_each_register_is_read_only_for_the_rules_that_need_it(
    tmp_path: Path, check_ids: set[str], read: set[str]
) -> None:
    folder = _dataset(tmp_path)
    ctx: Any = SimpleNamespace(roles=None, retention=None, risks=None)
    pipeline._load_vault_files(ctx, check_ids, _vault(folder))
    loaded = {name for name in ("roles", "retention", "risks") if getattr(ctx, name) is not None}
    assert loaded == read
    assert all(getattr(ctx, name).state == "loaded" for name in read)


def test_nothing_is_read_for_a_single_file_and_an_absent_vault_is_no_vault(tmp_path: Path) -> None:
    ids = {"roles.permitted", "retention.complete", "consent.reconsent"}
    ctx: Any = SimpleNamespace(roles=None, retention=None, risks=None)
    pipeline._load_vault_files(ctx, ids, None)  # a single file as target has no vault
    assert (ctx.roles, ctx.retention, ctx.risks) == (None, None, None)
    folder = _dataset(tmp_path, vault=False)
    pipeline._load_vault_files(ctx, ids, _vault(folder))
    assert (ctx.roles, ctx.retention, ctx.risks) == (
        roles.LoadedRoles("no_vault"),
        retention.LoadedRetention("no_vault"),
        risks.LoadedRisks("no_vault"),
    )


def test_config_hashes_without_a_rule_that_reads_the_registers(tmp_path: Path) -> None:
    """No loaded rule reads a register: nothing is read, an invalid file changes nothing, the hashes are
    None; results.json validates against its schema with the new fields."""
    folder = _dataset(tmp_path)
    for name in ("roles.yaml", "retention.yaml", "risks.yaml"):
        (folder / ".neurogrid" / "vault" / name).write_bytes(b"not: [a register\n")
    results = _check(folder, tmp_path)
    assert (results.config.roles_sha256, results.config.retention_sha256, results.config.risks_sha256) == (
        None,
        None,
        None,
    )
    data = json.loads(results.model_dump_json())
    assert {"roles_sha256", "retention_sha256", "risks_sha256"} <= set(data["config"])
    jsonschema.validate(data, json.loads((SCHEMAS / "results.schema.json").read_text(encoding="utf-8")))


def test_config_hashes_of_the_registers_a_rule_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _dataset(tmp_path)
    vault = _vault(folder)
    vault.roles.write_bytes(ROLES)
    vault.retention.write_bytes(RETENTION)
    vault.risks.write_bytes(RISKS)
    _stand_in(monkeypatch, "roles", "retention", "risks")
    results = _check(folder, tmp_path)
    assert results.config.roles_sha256 == roles.load_for_check(vault).sha256
    assert results.config.retention_sha256 == retention.load_for_check(vault).sha256
    assert results.config.risks_sha256 == risks.load_for_check(vault).sha256
    assert (
        len({results.config.roles_sha256, results.config.retention_sha256, results.config.risks_sha256}) == 3
    )
    respelled = b"# comment\r\n" + ROLES.replace(b"\n", b"\r\n")
    vault.roles.write_bytes(respelled)
    assert _check(folder, tmp_path).config.roles_sha256 == results.config.roles_sha256  # A-91 rule
    vault.roles.unlink()
    assert _check(folder, tmp_path).config.roles_sha256 is None  # a vault without the file
    data = json.loads(results.model_dump_json())
    jsonschema.validate(data, json.loads((SCHEMAS / "results.schema.json").read_text(encoding="utf-8")))
    assert "description" not in json.dumps(data["config"])  # never the content of a register (A-51)


@pytest.mark.parametrize(
    ("register", "content", "key"),
    [
        ("roles", b"format_version: 1\nroles: [x]\n", "roles.invalid"),
        ("retention", RETENTION.replace(b"2029-01-01", b"2028-12-31"), "retention.too_short"),
        ("risks", b"format_version: 1\nrisks: {}\n", "risks.invalid"),
    ],
)
def test_an_invalid_register_ends_the_run_before_the_data_are_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, register: str, content: bytes, key: str
) -> None:
    """C2: the register is read right after the consent records, before the signal pass and every measurer
    (the measurers would fail this test)."""
    folder = _dataset(tmp_path)
    (folder / ".neurogrid" / "vault" / f"{register}.yaml").write_bytes(content)
    _stand_in(monkeypatch, register)

    def no_data(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("the data were read")

    monkeypatch.setattr(pipeline, "measure", no_data)
    with pytest.raises(ConfigError) as info:
        _check(folder, tmp_path)
    assert info.value.message_key == key


def test_the_cli_ends_with_exit_2_and_names_the_object_of_a_short_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _dataset(tmp_path)
    _vault(folder).retention.write_bytes(RETENTION.replace(b"2029-01-01", b"2028-12-31"))
    _stand_in(monkeypatch, "retention")
    out = tmp_path / "results.json"
    with pytest.raises(SystemExit) as info:
        main(["--lang", "en", "check", str(folder), "--out", str(out), "--as-of", AS_OF.isoformat()])
    _stdout, err = capsys.readouterr()
    assert info.value.code == 2 and not out.exists()
    assert translator("en").t("errors.retention.too_short", object="pia") in err


# --- P9 area A with the core pack: CORE-NV04-01, CORE-NV05-01..03 (NV-F04, NV-F05; A-93, A-94) -------------

ROLE_TOML = '[vault]\nrole = "data_steward"\n'
STEWARD = (
    b"format_version: 1\nroles:\n"
    b"  - {role: data_steward, description: Prepares the dataset, actions: [read, check], objects: ['**'],"
    b" ethics_approval_ref: EC-2026-17}\n"
)
COMPLETE = (
    b"format_version: 1\nobjects:\n"
    b"  - {object: pia, created: 2026-10-01, min_until: 2029-10-01}\n"
    b"  - {object: access_log, created: 2026-10-01, min_until: 2029-10-01}\n"
)
EDITED_PIA = b"# Personal information protection impact assessment\n\nDone by the QA role.\n"
CORE_RULES = ("CORE-NV04-01", "CORE-NV05-01", "CORE-NV05-02", "CORE-NV05-03")


def _core(tmp_path: Path, name: str = "data") -> Path:
    """edf_ok with the core pack (no [check] rulepacks), the role data_steward in neurogrid.toml and a vault
    from vault init."""
    folder = tmp_path / name
    shutil.copytree(FIX / "edf_ok", folder)
    (folder / ".neurogrid").mkdir()
    (folder / ".neurogrid" / "neurogrid.toml").write_text(DOCUMENTED_TOML + ROLE_TOML, encoding="utf-8")
    init_vault(locate(folder, DEFAULT_VAULT_PATH))
    return folder


def _filled(folder: Path) -> VaultLocation:
    """The registers filled in: a role register, both required retention entries, an edited PIA file."""
    vault = _vault(folder)
    vault.roles.write_bytes(STEWARD)
    vault.retention.write_bytes(COMPLETE)
    vault.pia_files[1].write_bytes(EDITED_PIA)
    return vault


def _event(vault: VaultLocation, when: str, *, role: str | None, action: str) -> None:
    moment = dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
    outcome = ledger.append(
        vault, role=role, action=action, objects=["**"], purpose=None, approval_ref=None, now=lambda: moment
    )
    assert outcome.status == "written", outcome


def _rows(results: Results, rule: str) -> list[tuple[str | None, str, str | None]]:
    return sorted((f.subkey, f.status.value, f.reason) for f in results.findings if f.rule_id == rule)


def _passed(results: Results, rule: str) -> int:
    return sum(p.count for p in results.passed if p.rule_id == rule)


def _cli_check(
    folder: Path, out: Path, capsys: pytest.CaptureFixture[str], *extra: str
) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(["--lang", "en", "check", str(folder), "--out", str(out), *extra])
    stdout, err = capsys.readouterr()
    return int(info.value.code or 0), stdout, err


def test_min_until_below_three_years_is_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """DoD of P9 (KONZEPT 6): a min_until less than three years after created ends check with exit code 2,
    with the core pack, before results.json is written and without an access event; one day more passes."""
    folder = _core(tmp_path)
    vault = _filled(folder)
    vault.retention.write_bytes(
        COMPLETE.replace(
            b"min_until: 2029-10-01}\n  - {object: access_log",
            b"min_until: 2029-09-30}\n  - {object: access_log",
        )
    )
    log = vault.log.read_bytes()
    out = tmp_path / "results.json"
    code, _stdout, err = _cli_check(folder, out, capsys, "--as-of", "2026-11-20")
    assert code == 2 and not out.exists() and vault.log.read_bytes() == log
    assert translator("en").t("errors.retention.too_short", object="pia") in err
    vault.retention.write_bytes(COMPLETE)  # 29 Feb aside, the same day three years later is enough
    code, _stdout, err = _cli_check(folder, out, capsys, "--as-of", "2026-11-20")
    assert code in (0, 1) and out.exists(), err
    leap = b"format_version: 1\nobjects:\n  - {object: pia, created: 2024-02-29, min_until: 2027-02-28}\n"
    vault.retention.write_bytes(leap)
    code, _stdout, err = _cli_check(folder, tmp_path / "leap.json", capsys, "--as-of", "2026-11-20")
    assert code == 2 and translator("en").t("errors.retention.too_short", object="pia") in err


def test_role_findings_use_events_before_the_day_before_as_of(tmp_path: Path) -> None:
    """A-93: CORE-NV04-01 judges only events before 00:00 UTC of the day before the reference date."""
    folder = _core(tmp_path)
    vault = _filled(folder)
    _event(vault, "2026-11-18T23:59:59Z", role="data_steward", action="check")  # judged on 2026-11-20
    _event(
        vault, "2026-11-19T00:00:00Z", role="data_steward", action="convert"
    )  # not permitted, not yet judged
    before = pipeline.run_check(
        folder, pipeline.CheckOptions(as_of=dt.date(2026, 11, 20), work_base=tmp_path / "w")
    )
    assert _rows(before, "CORE-NV04-01") == [] and _passed(before, "CORE-NV04-01") == 1
    after = pipeline.run_check(
        folder, pipeline.CheckOptions(as_of=dt.date(2026, 11, 21), work_base=tmp_path / "w")
    )
    assert _rows(after, "CORE-NV04-01") == [("data_steward/convert", "failed", "roles.action_not_allowed")]
    (finding,) = [f for f in after.findings if f.rule_id == "CORE-NV04-01"]
    assert finding.details == {
        "role": "data_steward",
        "action": "convert",
        "events_not_permitted": 1,
        "first_line": 2,
    }
    assert finding.file == ".neurogrid/vault/access.jsonl" and finding.severity.value == "warning"


def test_two_checks_with_role_register_byte_identical(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """NG-N03 with every register: two check runs on the same date give the same results.json bytes, although
    each appends its own access event (it lies after the cut of CORE-NV04-01 for any UTC offset)."""
    folder = _core(tmp_path)
    vault = _filled(folder)
    _event(vault, "2026-10-29T12:00:00Z", role="data_steward", action="check")
    _event(vault, "2026-10-29T12:00:00Z", role="data_steward", action="convert")
    today = dt.date.today().isoformat()
    first, second = tmp_path / "1.json", tmp_path / "2.json"
    code_1, _, _ = _cli_check(folder, first, capsys, "--as-of", today)
    events = vault.log.read_bytes().count(b"\n")
    code_2, _, _ = _cli_check(folder, second, capsys, "--as-of", today)
    assert vault.log.read_bytes().count(b"\n") == events + 1  # the second run appended its event too
    assert code_1 == code_2 and first.read_bytes() == second.read_bytes()
    results = Results.model_validate_json(first.read_bytes())
    assert _rows(results, "CORE-NV04-01") == [("data_steward/convert", "failed", "roles.action_not_allowed")]
    assert results.config.roles_sha256 and results.config.retention_sha256
    assert _passed(results, "CORE-NV05-01") == 2 and _passed(results, "CORE-NV05-02") == 1


def test_events_without_role_are_not_checkable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """scan records its read event without a role (p6 decisions 4): CORE-NV04-01 gives one grey result per
    action without a role, never a warning."""
    folder = _core(tmp_path)
    _filled(folder)
    with pytest.raises(SystemExit):
        main(["--lang", "en", "scan", str(folder), "--out", str(tmp_path / "scan.json")])
    capsys.readouterr()
    later = dt.date.today() + dt.timedelta(days=3)  # the scan event lies before the cut, in any time zone
    results = pipeline.run_check(folder, pipeline.CheckOptions(as_of=later, work_base=tmp_path / "w"))
    assert _rows(results, "CORE-NV04-01") == [("-/read", "not_checkable", "roles.role_missing")]
    (finding,) = [f for f in results.findings if f.rule_id == "CORE-NV04-01"]
    assert finding.details == {"role": None, "action": "read", "events_without_role": 1, "first_line": 1}


def test_retention_reminder_notice(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CORE-NV05-03 (info) and the neutral reminder on the console (notice.retention_reminder, warning level);
    days is overridable (MET-02)."""
    folder = _core(tmp_path)
    vault = _filled(folder)
    vault.retention.write_bytes(
        COMPLETE.replace(
            b"created: 2026-10-01, min_until: 2029-10-01}\n  - {object: access_log",
            b"created: 2023-12-01, min_until: 2026-12-31}\n  - {object: access_log",
        )
    )
    out = tmp_path / "r.json"
    _code, stdout, _ = _cli_check(folder, out, capsys, "--as-of", "2026-11-20")
    assert translator("en").t("notice.retention_reminder", count=1) in stdout
    results = Results.model_validate_json(out.read_bytes())
    assert _rows(results, "CORE-NV05-03") == [("pia", "failed", "retention.ending")]
    (finding,) = [f for f in results.findings if f.rule_id == "CORE-NV05-03"]
    assert finding.measured_value == 41 and finding.threshold == 90 and finding.severity.value == "info"
    assert finding.details == {
        "object": "pia",
        "min_until": "2026-12-31",
        "review_at": None,
        "review_due": False,
    }
    assert [n.params for n in results.notices if n.message_key == "notice.retention_reminder"] == [
        {"count": 1}
    ]
    (folder / ".neurogrid" / "neurogrid.toml").write_text(
        DOCUMENTED_TOML + ROLE_TOML + '[rules."CORE-NV05-03".params]\ndays = 30\n', encoding="utf-8"
    )
    _code, stdout, _ = _cli_check(folder, out, capsys, "--as-of", "2026-11-20")
    assert "notice.retention_reminder" not in out.read_text(encoding="utf-8")
    assert translator("en").t("notice.retention_reminder", count=1) not in stdout


def test_raw_pia_template_is_a_finding(tmp_path: Path) -> None:
    """A vault straight from vault init: the unedited PIA template and the empty retention.yaml are findings
    (warnings), the empty role register is not checkable, the reminder is not applicable."""
    folder = _core(tmp_path)
    results = pipeline.run_check(folder, pipeline.CheckOptions(as_of=AS_OF, work_base=tmp_path / "w"))
    assert _rows(results, "CORE-NV05-02") == [(None, "failed", "pia.template_unedited")]
    assert _rows(results, "CORE-NV05-01") == [
        ("access_log", "failed", "retention.entry_missing"),
        ("pia", "failed", "retention.entry_missing"),
    ]
    assert _rows(results, "CORE-NV04-01") == [(None, "not_checkable", "roles.empty")]
    assert _rows(results, "CORE-NV05-03") == [(None, "not_applicable", "retention.no_entries")]
    (finding,) = [f for f in results.findings if f.rule_id == "CORE-NV05-02"]
    assert finding.details == {"files": 2, "open_fields": 0}


def test_register_texts_never_reach_the_outputs(tmp_path: Path) -> None:
    """A-51: descriptions, ethics references and PIA text stay in the vault; results.json and the report show
    counts, roles, actions, objects and dates only, and the identifying texts as a count."""
    folder = _core(tmp_path)
    vault = _filled(folder)
    vault.roles.write_bytes(
        STEWARD.replace(b"Prepares the dataset", b"Wang Wei leads the team").replace(
            b"EC-2026-17", b"EC-777777"
        )
    )
    vault.pia_files[1].write_bytes(EDITED_PIA + b"Assessed by Li Si, 13800138000.\n")
    _event(vault, "2026-10-29T12:00:00Z", role="data_steward", action="convert")
    results = pipeline.run_check(folder, pipeline.CheckOptions(as_of=AS_OF, work_base=tmp_path / "w"))
    text = results.model_dump_json()
    for token in ("Wang Wei", "777777", "Li Si", "13800138000", "leads the team"):
        assert token not in text, token
    identifying = [n.params for n in results.notices if n.message_key == "notice.registers_look_identifying"]
    assert identifying == [{"count": 2}]  # the description and the ethics reference
    assert not [n for n in results.notices if n.message_key == "notice.roles_without_ethics_ref"]
    for lang in ("en", "zh"):
        html = visible_text(render_report(results, lang))
        tr = translator(lang).t
        for token in ("Wang Wei", "777777", "Li Si", "13800138000"):
            assert token not in html, (lang, token)
        assert tr("report.roles.role", role="data_steward") in html
        assert tr("report.roles.action", action=tr("terms.access_action.convert")) in html
        assert tr("report.roles.events", count=1) in html


def test_report_shows_the_retention_details(tmp_path: Path) -> None:
    folder = _core(tmp_path)
    vault = _filled(folder)
    vault.retention.write_bytes(
        COMPLETE + b"  - {object: roles, created: 2026-10-01, min_until: 2029-10-01}\n"
    )
    vault.roles.unlink()
    vault.pia_files[1].write_bytes(pia_template("pia.en.md") + b"\nStarted.\n")
    results = pipeline.run_check(folder, pipeline.CheckOptions(as_of=AS_OF, work_base=tmp_path / "w"))
    assert _rows(results, "CORE-NV05-01") == [("roles", "failed", "retention.object_missing")]
    assert _rows(results, "CORE-NV05-02") == [(None, "failed", "pia.fields_open")]
    for lang in ("en", "zh"):
        html = visible_text(render_report(results, lang))
        tr = translator(lang).t
        assert tr("report.retention.object", object=tr("terms.retention_object.roles")) in html
        assert tr("report.pia.open_fields", count=16) in html and tr("report.pia.files", count=2) in html
        assert tr("reason.retention.object_missing") in html and tr("reason.pia.fields_open") in html
