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
from neurogrid.report.texts import translator
from neurogrid.vault import retention, risks, roles
from neurogrid.vault.store import DEFAULT_VAULT_PATH, VaultLocation, init_vault, locate

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
