"""``vault export`` through the command line (NV-F07, CON-02, UF-03, UF-06; A-30, A-51, A-96): the five parts
plus index.json and nothing else (no signals, no consent records, no register that stays in the vault), the
pseudonymous manifest copy of a raw folder, links never followed, the report part only from NeuroGrid's own
reports, and every refusal exit 2 without an event or a file."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest

from conftest import DOCUMENTED_TOML, dir_link  # type: ignore[import-not-found]
from neurogrid.cli import main
from neurogrid.io.provenance import show
from neurogrid.model.export import ExportIndex
from neurogrid.report.texts import translator

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = "2026-10-11"
VAULT = Path(".neurogrid", "vault")
NAME_LIKE = "Wang Wei 19870312.edf"  # a raw file name that reads like a person and a birth date (A-51)
PLANTED_SUBJECT = "Planted4711"  # only in consents.yaml
PLANTED_REF = "EthicsToken9931"  # an ethics approval reference of the consent records
RISK_TOKEN = "RiskToken5521"  # a risk description: stays in risks.yaml (A-95)
MEMBERS = [
    "manifest.json",
    "access.jsonl",
    "roles.yaml",
    "pia/pia.zh.md",
    "pia/pia.en.md",
    "report/report.zh.html",
    "report/report.en.html",
    "index.json",
]


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(["--lang", "en", *args])
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def _t(key: str, **params: Any) -> str:
    return translator("en").t(key, **params)


def _raw(tmp_path: Path, capsys: pytest.CaptureFixture[str], toml: str = DOCUMENTED_TOML) -> Path:
    """edf_ok as a raw folder with a name-like file, a vault with consent records of a planted subject, a risk
    register with a planted description and a manifest."""
    folder = tmp_path / "数据 data"
    shutil.copytree(FIX / "edf_ok", folder)
    (folder / "rec_a.edf").rename(folder / NAME_LIKE)
    (folder / ".neurogrid").mkdir()
    (folder / ".neurogrid" / "neurogrid.toml").write_text(toml, encoding="utf-8")
    assert run(["vault", "init", str(folder)], capsys)[0] == 0
    add = ["vault", "consent", "add", str(folder), "--subject", PLANTED_SUBJECT, "--version", "1"]
    fields = ["--date", "2026-03-01", "--uses", "training", "--ethics-ref", PLANTED_REF, "--role", "steward"]
    assert run([*add, *fields], capsys)[0] == 0
    (folder / VAULT / "risks.yaml").write_text(
        "format_version: 1\nrisks:\n  - id: R-1\n    date: 2026-09-01\n"
        f"    description: {RISK_TOKEN} second model\n    affected_uses: [training]\n"
        "    min_consent_version: 2\n",
        encoding="utf-8",
    )
    assert run(["manifest", str(folder)], capsys)[0] == 0
    return folder


def _reports(folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> list[Path]:
    """report.zh.html and report.en.html of a check of ``folder`` (no browser needed)."""
    results = tmp_path / "results.json"
    code, out, err = run(["check", str(folder), "--out", str(results), "--as-of", AS_OF], capsys)
    assert code in (0, 1), out + err
    assert run(["report", str(results), "--out", str(tmp_path / "reports")], capsys)[0] == 0
    return [tmp_path / "reports" / f"report.{lang}.html" for lang in ("zh", "en")]


def _export(
    folder: Path, out: Path, reports: list[Path], capsys: pytest.CaptureFixture[str], *extra: str
) -> tuple[int, str, str]:
    args = ["vault", "export", str(folder), "--out", str(out), "--role", "QA.lead", *extra]
    for report in reports:
        args += ["--report", str(report)]
    return run(args, capsys)


def _members(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _log(folder: Path) -> bytes:
    return (folder / VAULT / "access.jsonl").read_bytes()


def test_export_zip_five_parts_index_no_signals_no_consents(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD (KONZEPT P9, NV-F07): exactly the five parts plus index.json, only regular files, no signals, no
    consent data, no risk description; the event before packing; exit 0."""
    folder = _raw(tmp_path, capsys)
    reports = _reports(folder, tmp_path, capsys)
    out = tmp_path / "package" / "检查包.zip"
    code, stdout, stderr = _export(folder, out, list(reversed(reports)), capsys)
    assert code == 0, stdout + stderr
    with zipfile.ZipFile(out) as archive:
        infos = archive.infolist()
    assert [info.filename for info in infos] == MEMBERS
    assert all(info.external_attr >> 16 == 0o100644 and not info.is_dir() for info in infos)
    members = _members(out)
    signals = [path.read_bytes() for path in folder.glob("*.edf")]
    for name, data in members.items():
        assert not any(signal in data for signal in signals), name  # no signal bytes (A-30)
        for planted in (PLANTED_SUBJECT, PLANTED_REF, RISK_TOKEN, "Wang Wei", "19870312"):
            assert planted.encode() not in data, (name, planted)
    for vault_file in ("consents.yaml", "risks.yaml", "retention.yaml"):
        assert not any(name.endswith(vault_file) for name in members), vault_file
    index = ExportIndex.model_validate_json(members["index.json"])
    assert [part.file for part in index.parts] == MEMBERS[:-1]
    assert all(part.sha256 == hashlib.sha256(members[part.file]).hexdigest() for part in index.parts)
    events = [json.loads(line) for line in members["access.jsonl"].splitlines()]
    assert events[-1]["action"] == "export" and events[-1]["hash"] == index.access_log.head
    assert members["access.jsonl"] == _log(folder)  # nothing after the export event
    assert index.access_log.intact and index.manifest.pseudonymized
    assert members["report/report.en.html"] == reports[1].read_bytes()
    for part in index.parts:
        assert _t("cli.vault.export.part", file=part.file, size=part.size, sha256=part.sha256) in stdout
    assert _t("cli.vault.export.head", hash=index.access_log.head) in stdout
    assert _t("cli.vault.export.pia_unedited") in stdout and _t("cli.vault.export.roles_empty") in stdout
    assert stdout.rstrip().endswith(_t("disclaimer"))
    assert "Wang" not in stdout + stderr


def test_raw_manifest_pseudonymized_unless_show_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A-51: the archived manifest of a raw folder names the data files as verify shows them; --show-paths
    keeps the file as it is. The event names the manifest by its fixed name either way."""
    folder = _raw(tmp_path, capsys)
    reports = _reports(folder, tmp_path, capsys)
    manifest = (folder / ".neurogrid" / "manifest.json").read_bytes()
    assert _export(folder, tmp_path / "a.zip", reports, capsys)[0] == 0
    copy = json.loads(_members(tmp_path / "a.zip")["manifest.json"])
    paths = [item["path"] for item in copy["files"]]
    assert show(NAME_LIKE, plain=False).file in paths and NAME_LIKE not in paths
    assert ".neurogrid/neurogrid.toml" in paths  # NeuroGrid's fixed names in clear
    code, stdout, _ = _export(folder, tmp_path / "b.zip", reports, capsys, "--show-paths")
    assert code == 0
    members = _members(tmp_path / "b.zip")
    assert members["manifest.json"] == manifest
    assert not ExportIndex.model_validate_json(members["index.json"]).manifest.pseudonymized
    events = [json.loads(line) for line in _log(folder).splitlines()]
    assert [event["objects"][0] for event in events if event["action"] == "export"] == [
        ".neurogrid/manifest.json"
    ] * 2


def test_a_bids_dataset_keeps_its_manifest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "bids"
    shutil.copytree(FIX / "bids_ok", folder)
    assert run(["vault", "init", str(folder)], capsys)[0] == 0
    assert run(["manifest", str(folder)], capsys)[0] == 0
    reports = _reports(folder, tmp_path, capsys)
    code, stdout, stderr = _export(folder, folder / "derivatives" / "pkg.zip", reports[:1], capsys)
    assert code == 0, stdout + stderr
    members = _members(folder / "derivatives" / "pkg.zip")
    assert members["manifest.json"] == (folder / ".neurogrid" / "manifest.json").read_bytes()
    assert _t("cli.vault.export.inside_dataset") in stdout  # --out inside the dataset: a later verify sees it


def test_linked_part_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """P6 link rule: a link in the vault (here the pia folder) and a --report that is a link are exit 2;
    nothing written, no event."""
    folder = _raw(tmp_path, capsys)
    reports = _reports(folder, tmp_path, capsys)
    before = _log(folder)
    linked = tmp_path / "linked.html"
    dir_link(linked, tmp_path / "reports")
    code, _, err = _export(folder, tmp_path / "a.zip", [reports[0], linked], capsys)
    assert code == 2 and _t("errors.path.link") in err
    pia = folder / VAULT / "pia"
    shutil.move(str(pia), str(tmp_path / "pia-elsewhere"))
    dir_link(pia, tmp_path / "pia-elsewhere")
    code, _, err = _export(folder, tmp_path / "a.zip", reports, capsys)
    assert code == 2 and _t("errors.vault.link", part="pia") in err
    assert _log(folder) == before and not (tmp_path / "a.zip").exists()


def test_reports_must_be_neurogrid_reports_each_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _raw(tmp_path, capsys)
    reports = _reports(folder, tmp_path, capsys)
    before = _log(folder)
    notes = tmp_path / "notes.html"
    notes.write_text("<html><head><title>notes</title></head><body></body></html>", encoding="utf-8")
    edited = tmp_path / "edited.html"
    edited.write_text(
        reports[1].read_text(encoding="utf-8").replace('lang="en"', 'lang="fr"'), encoding="utf-8"
    )
    cases = [
        ([reports[0], notes], _t("errors.export.report_invalid", index=2)),
        ([edited], _t("errors.export.report_invalid", index=1)),
        ([reports[1], reports[1]], _t("errors.export.report_duplicate", name="report.en.html")),
        ([tmp_path / "missing.html"], _t("errors.export.part_missing", part="report")),
        ([tmp_path], _t("errors.export.not_regular", part="report")),
    ]
    for given, message in cases:
        code, _, err = _export(folder, tmp_path / "a.zip", given, capsys)
        assert code == 2 and message in err, given
    assert _log(folder) == before and not (tmp_path / "a.zip").exists()


def test_role_purpose_and_refusals(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A manual writer (p6 decisions 4): role = --role > [vault] role, none is exit 2; purpose and approval
    reference from the toml; --out in the vault is refused; exit 2 never writes."""
    toml = DOCUMENTED_TOML + '\n[vault]\npurpose = "inspection 2026"\napproval_ref = "EC-1"\n'
    folder = _raw(tmp_path, capsys, toml)
    reports = _reports(folder, tmp_path, capsys)
    before = _log(folder)
    code, _, err = run(
        ["vault", "export", str(folder), "--out", str(tmp_path / "a.zip"), "--report", str(reports[0])],
        capsys,
    )
    assert code == 2 and _t("errors.vault.role_missing") in err
    code, _, err = _export(folder, folder / VAULT / "pkg.zip", reports, capsys)
    assert code == 2 and _t("errors.export.out_in_vault") in err
    (tmp_path / "out").mkdir()
    code, _, err = _export(folder, tmp_path / "out", reports, capsys)
    assert code == 2 and _t("errors.output.is_directory") in err
    assert _log(folder) == before and not (tmp_path / "a.zip").exists()
    (folder / ".neurogrid" / "manifest.json").unlink()
    code, _, err = _export(folder, tmp_path / "a.zip", reports, capsys)
    assert code == 2 and _t("errors.export.part_missing", part="manifest.json") in err
    assert run(["manifest", str(folder)], capsys)[0] == 0
    code, _, err = _export(folder, tmp_path / "a.zip", reports, capsys, "--purpose", "audit")
    assert code == 0, err
    last = json.loads(_log(folder).splitlines()[-1])
    assert (last["action"], last["role"], last["purpose"], last["approval_ref"]) == (
        "export",
        "QA.lead",
        "audit",
        "EC-1",
    )


def test_a_manifest_given_elsewhere(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--manifest outside the dataset: archived, but no event object for it (it lies in no namespace of the
    log); inside a raw dataset under another name: the event names it pseudonymously."""
    folder = _raw(tmp_path, capsys)
    reports = _reports(folder, tmp_path, capsys)
    outside = tmp_path / "Zhang manifest.json"
    shutil.copy(folder / ".neurogrid" / "manifest.json", outside)
    assert _export(folder, tmp_path / "a.zip", reports, capsys, "--manifest", str(outside))[0] == 0
    last = json.loads(_log(folder).splitlines()[-1])
    assert last["objects"][0] == ".neurogrid/vault/access.jsonl"
    inside = folder / "Zhang manifest.json"
    shutil.copy(outside, inside)
    assert _export(folder, tmp_path / "b.zip", reports, capsys, "--manifest", str(inside))[0] == 0
    last = json.loads(_log(folder).splitlines()[-1])
    assert last["objects"][0] == show("Zhang manifest.json", plain=False).file and "Zhang" not in str(last)
