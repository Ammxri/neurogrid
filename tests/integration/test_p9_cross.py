"""P9 across its areas (KONZEPT row P9, UF-02, UF-03, UF-06, ARC-01; A-93 to A-99): the flows that need the
registers, the re-consent, the export, the dossier and the comparison together, through the real command
line. Each area tests its own parts in its own test files."""

from __future__ import annotations

import datetime as dt
import io
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pypdf
import pytest

from conftest import DOCUMENTED_TOML  # type: ignore[import-not-found]
from neurogrid.cli import main
from neurogrid.model.results import Results
from neurogrid.model.retention import plus_three_years
from neurogrid.report import tables
from neurogrid.report.texts import translator
from report_html import visible_text  # type: ignore[import-not-found]

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = "2026-10-11"  # before every event of a test: CORE-NV04-01 judges none, two checks stay byte-identical
LATE = (dt.date.today() + dt.timedelta(days=2)).isoformat()  # after the NV04-01 cut of every event of a test
VAULT = Path(".neurogrid", "vault")
SUBJECTS = ("01", "02", "03", "04", "05", "06")  # bids_ai_ok: 01-04 in train, 05 in val, 06 in test
STEWARD = "data_steward"
YYT = ("--rulepack", "yyt2029", "--allow-draft-rulepacks")
# Planted identifiers (A-51): the risk description and the consent's ethics reference never leave the vault;
# the role description and the impact assessment text leave it only inside the export package, as written.
RISK_TEXT = "ZhangSanRiskText"
CONSENT_REF = "WangWuEthicsRef"
ROLE_TEXT = "LiSiRoleText"
PIA_TEXT = "ZhaoLiuPiaText"
GHOST = "99"  # a subject that only the consent records know: never in any output (D-17 option B)
ROLES = (
    "format_version: 1\nroles:\n"
    f"  - role: {STEWARD}\n    description: {ROLE_TEXT} prepares the dataset\n"
    "    actions: [read, check, convert, report, export, consent_manage]\n    objects: ['**']\n"
    "    ethics_approval_ref: EC-2026-17\n"
)
RISKS = (
    "format_version: 1\nrisks:\n"
    f"  - id: R-1\n    date: 2026-09-01\n    description: {RISK_TEXT}\n"
    "    affected_uses: [training]\n    min_consent_version: 2\n"
)
PIA = f"# Personal information protection impact assessment\n\n{PIA_TEXT}: assessed by the QA role.\n"
P9_RULES = {"CORE-M14-02", "CORE-NV04-01", "CORE-NV05-01", "CORE-NV05-02", "CORE-NV05-03"}
# Documented values, so that the sidecars of the conversion show their origin (as in test_convert.py).
CONVERT_TOML = (
    '[metadata.defaults]\nreference = "FCz"\nline_frequency_hz = 60\nsoftware_filters = "n/a"\n'
    '[[convert.files]]\npath = "rec_a.edf"\nsubject = "01"\ntask = "rest"\n'
    '[[convert.files]]\npath = "rec_b.edf"\nsubject = "02"\ntask = "rest"\n'
)


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(["--lang", "en", *args])
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def _pairs(items: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(item["rule_id"], item["object"]) for item in items]


def test_uf02_scan_convert_check_diff(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """UF-02: raw recordings of a clinic go through scan, convert --to bids and check; after a manifest one
    file changes, and the second check and diff decide in the pipeline: JSON alone on stdout, exit code 1 for
    the new error, 0 for the comparison the other way round."""
    raw = tmp_path / "raw"
    (raw / ".neurogrid").mkdir(parents=True)
    for name in ("rec_a.edf", "rec_b.edf"):
        shutil.copy2(FIX / "edf_ok" / name, raw / name)
    (raw / ".neurogrid" / "neurogrid.toml").write_text(CONVERT_TOML, encoding="utf-8")

    code, out, err = run(["scan", str(raw), "--out", str(tmp_path / "scan.json")], capsys)
    assert code == 0, out + err
    scan = json.loads((tmp_path / "scan.json").read_bytes())
    assert (scan["subjects"], scan["is_bids"]) == (2, False)

    bids = tmp_path / "bids"
    code, out, err = run(["convert", str(raw), "--to", "bids", "--out", str(bids)], capsys)
    assert code == 0, out + err
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    code, out, err = run(["check", str(bids), "--out", str(old), "--as-of", AS_OF], capsys)
    assert code == 0, out + err

    code, out, err = run(["manifest", str(bids)], capsys)
    assert code == 0, out + err
    readme = bids / "README.md"
    readme.write_bytes(readme.read_bytes() + b"\nchanged after the manifest\n")
    code, out, err = run(["check", str(bids), "--out", str(new), "--as-of", AS_OF], capsys)
    assert code == 1, out + err

    code, out, err = run(["diff", str(old), str(new), "--format", "json"], capsys)
    assert code == 1, err
    result = json.loads(out)  # nothing but the JSON on stdout
    assert _pairs(result["findings"]["new"]) == [("CORE-M13-02", "README.md")]
    assert _pairs(result["findings"]["fixed"]) == [("CORE-M13-01", "dataset")]  # the manifest exists now
    assert _pairs(result["findings"]["removed"]) == [("CORE-M13-02", "dataset")]  # not applicable before
    assert result["summary"]["new_errors"] == 1 and result["summary"]["exit_code"] == 1

    code, out, err = run(["diff", str(new), str(old)], capsys)
    assert code == 0, out + err


# --- a dataset with a full vault: consents, roles, risks, retention, impact assessment, log --------------


def _retention() -> str:
    """Entries for pia and access_log whose minimum retention ends at least three years after today, so that
    CORE-NV05-03 reminds of nothing whatever day the test runs."""
    created = dt.date(2026, 10, 1)
    until = max(plus_three_years(created) or created, plus_three_years(dt.date.today()) or created)
    return (
        "format_version: 1\nobjects:\n"
        f"  - {{object: pia, created: {created}, min_until: {until}}}\n"
        f"  - {{object: access_log, created: {created}, min_until: {until}}}\n"
    )


def _consent(
    folder: Path, capsys: pytest.CaptureFixture[str], subject: str, version: str
) -> tuple[int, str, str]:
    return run(
        ["vault", "consent", "add", str(folder), "--subject", subject, "--version", version]
        + ["--date", "2026-03-01", "--uses", "training,validation", "--ethics-ref", CONSENT_REF]
        + ["--role", STEWARD],
        capsys,
    )


def _full_vault(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    """bids_ai_ok with its splits and a vault from ``vault init``: consents of all six subjects and of GHOST
    through the command line (training and validation, version 1), filled registers and one edited PIA
    file."""
    folder = tmp_path / "data"
    shutil.copytree(FIX / "bids_ai_ok", folder)
    (folder / ".neurogrid" / "neurogrid.toml").write_text(DOCUMENTED_TOML, encoding="utf-8")
    code, out, err = run(["vault", "init", str(folder)], capsys)
    assert code == 0, out + err
    for subject in (*SUBJECTS, GHOST):
        code, out, err = _consent(folder, capsys, subject, "1")
        assert code == 0, out + err
    vault = folder / VAULT
    (vault / "roles.yaml").write_bytes(ROLES.encode("utf-8"))
    (vault / "risks.yaml").write_bytes(RISKS.encode("utf-8"))
    (vault / "retention.yaml").write_bytes(_retention().encode("utf-8"))
    (vault / "pia" / "pia.en.md").write_bytes(PIA.encode("utf-8"))
    return folder


def _check(
    folder: Path, out: Path, capsys: pytest.CaptureFixture[str], *extra: str, as_of: str = AS_OF
) -> tuple[int, dict[str, Any], str]:
    code, stdout, stderr = run(
        ["check", str(folder), "--out", str(out), "--as-of", as_of, "--role", STEWARD, *extra], capsys
    )
    assert code in (0, 1), stdout + stderr
    return code, json.loads(out.read_bytes()), stdout + stderr


def _report(target: Path, out: Path, capsys: pytest.CaptureFixture[str], *extra: str) -> str:
    code, stdout, stderr = run(["report", str(target), "--out", str(out), *extra], capsys)
    assert code == 0, stdout + stderr
    return stdout + stderr


def _statuses(results: dict[str, Any], rule: str) -> set[str]:
    found = {finding["status"] for finding in results["findings"] if finding["rule_id"] == rule}
    return found | {"passed" for entry in results["passed"] if entry["rule_id"] == rule}


def _events(folder: Path) -> list[dict[str, Any]]:
    text = (folder / VAULT / "access.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _export(folder: Path, out: Path, capsys: pytest.CaptureFixture[str], *reports: Path) -> str:
    args = ["vault", "export", str(folder), "--out", str(out), "--role", STEWARD]
    for report in reports:
        args += ["--report", str(report)]
    code, stdout, stderr = run(args, capsys)
    assert code == 0, stdout + stderr
    return stdout + stderr


def _members(package: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(package) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_uf06_init_consent_add_log_verify_export(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """UF-06: a vault from nothing to the export package: init, a consent, a manual entry, verify, a
    manifest, a check, a report and the export; the export event ends the archived log, index.json names
    its hash as the head, and the head stays part of the chain."""
    folder = tmp_path / "data"
    shutil.copytree(FIX / "bids_ai_ok", folder)
    assert run(["vault", "init", str(folder)], capsys)[0] == 0
    assert _consent(folder, capsys, "01", "1")[0] == 0
    code, out, err = run(
        ["vault", "log", str(folder), "--action", "read", "--objects", "**", "--purpose", "review"]
        + ["--role", STEWARD],
        capsys,
    )
    assert code == 0, out + err
    assert run(["vault", "verify", str(folder)], capsys)[0] == 0
    assert run(["manifest", str(folder)], capsys)[0] == 0
    target = tmp_path / "r.json"
    _check(folder, target, capsys)
    _report(target, tmp_path / "rep", capsys, "--lang", "en", "--format", "html")

    package = tmp_path / "package.zip"
    _export(folder, package, capsys, tmp_path / "rep" / "report.en.html")
    members = _members(package)
    assert list(members) == [
        "manifest.json", "access.jsonl", "roles.yaml", "pia/pia.zh.md", "pia/pia.en.md",
        "report/report.en.html", "index.json",
    ]  # fmt: skip
    events = _events(folder)
    # vault log and manifest read, check and export record themselves (A-90)
    assert [event["action"] for event in events] == ["consent_manage", "read", "read", "check", "export"]
    archived = [json.loads(line) for line in members["access.jsonl"].decode("utf-8").splitlines()]
    assert archived == events  # the log as written, up to and with the export event
    index = json.loads(members["index.json"])
    assert index["access_log"] == {"head": events[-1]["hash"], "events": 5, "intact": True, "deviations": 0}
    head = index["access_log"]["head"]
    code, out, err = run(["vault", "verify", str(folder), "--expect-head", head], capsys)
    assert code == 0, out + err


def test_uf03_build_check_consent_export(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """UF-03: the consents of a study and a risk found after them decide M14; check counts the subjects
    below the version the risk asks for, the report shows them only as counts, and the export package
    carries the registers and the report but never the consent records or the risk register."""
    folder = _full_vault(tmp_path, capsys)
    target = tmp_path / "r.json"
    _, results, text = _check(folder, target, capsys)
    assert _statuses(results, "CORE-M14-01") == {"passed"}
    failed = [f for f in results["findings"] if f["rule_id"] == "CORE-M14-02" and f["status"] == "failed"]
    assert sorted(f["object"] for f in failed) == ["sub-01", "sub-02", "sub-03", "sub-04"]  # training only
    assert {f["reason"] for f in failed} == {"reconsent.version_below"}
    assert [risk["id"] for risk in results["reconsent"]["risks"]] == ["R-1"]
    assert translator("en").t("cli.check.reconsent", count=4) in text

    assert run(["manifest", str(folder)], capsys)[0] == 0
    _report(target, tmp_path / "rep", capsys, "--lang", "en", "--format", "html")
    document = (tmp_path / "rep" / "report.en.html").read_text(encoding="utf-8")
    start = document.index('<div class="reconsent" id="reconsent">')
    block = visible_text(document[start : document.index("</div>", start)])
    assert translator("en").t("report.reconsent.heading") in block
    assert translator("en").t("report.reconsent.withheld") in block  # four subjects: a cell below 5
    assert not re.search(r"sub-0\d", block)

    package = tmp_path / "package.zip"
    _export(folder, package, capsys, tmp_path / "rep" / "report.en.html")
    kept = ("consents.yaml", "risks.yaml", "retention.yaml", "results.json")
    assert not any(name.endswith(kept) for name in _members(package))


@pytest.mark.parametrize("jobs", ["1", "4"])
def test_dod_two_checks_full_vault_byte_identical(
    jobs: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD P9: with consents, roles, risks, retention, the impact assessment and the log, every run appends
    an event while results.json stays byte-identical; the hashes of every register are in the config."""
    folder = _full_vault(tmp_path, capsys)
    before = len(_events(folder))
    first, second = tmp_path / "1.json", tmp_path / "2.json"
    code_1, results, _ = _check(folder, first, capsys, *YYT, "--jobs", jobs)
    code_2, _, _ = _check(folder, second, capsys, *YYT, "--jobs", jobs)
    assert code_1 == code_2 and first.read_bytes() == second.read_bytes()
    assert len(_events(folder)) == before + 2
    config = results["config"]
    assert all(config[f"{name}_sha256"] for name in ("consents", "roles", "risks", "retention"))
    rules = {f["rule_id"] for f in results["findings"]} | {p["rule_id"] for p in results["passed"]}
    assert rules >= P9_RULES
    assert _statuses(results, "CORE-NV05-01") == _statuses(results, "CORE-NV05-02") == {"passed"}


def _private_texts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[dict[str, str], dict[str, bytes]]:
    """Every output of check, diff, report (html) and vault export of a full vault, as text, and the
    members of the export package."""
    folder = _full_vault(tmp_path, capsys)
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    texts: dict[str, str] = {}
    texts["console check"] = _check(folder, old, capsys)[2]
    assert _consent(folder, capsys, "01", "2")[0] == 0
    texts["console check 2"] = _check(folder, new, capsys)[2]
    texts["results.json"] = new.read_text(encoding="utf-8")
    for form in ("text", "json"):
        code, out, err = run(["diff", str(old), str(new), "--format", form], capsys)
        assert code in (0, 1), err
        texts[f"diff {form}"] = out + err
    rep = tmp_path / "rep"
    texts["console report"] = _report(new, rep, capsys, "--lang", "zh,en", "--format", "html")
    for lang in ("zh", "en"):
        texts[f"report {lang}"] = (rep / f"report.{lang}.html").read_text(encoding="utf-8")
    assert run(["manifest", str(folder)], capsys)[0] == 0
    package = tmp_path / "package.zip"
    texts["console export"] = _export(folder, package, capsys, rep / "report.en.html", rep / "report.zh.html")
    return texts, _members(package)


def test_privacy_planted_identifiers_in_p9_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A-51 across P9: the risk description and the consent's ethics reference reach no output and no member
    of the export package; the role description and the impact assessment text appear only in the members
    that carry those files as written (NV-F07: roles.yaml and the PIA files are parts of the package);
    diff and the consoles name no subject of the consent records (D-17 option B)."""
    texts, members = _private_texts(tmp_path, capsys)
    for name, text in texts.items():
        for token in (RISK_TEXT, CONSENT_REF, ROLE_TEXT, PIA_TEXT):
            assert token not in text, (name, token)
    for name, text in texts.items():
        assert f"sub-{GHOST}" not in text, name
    for name, data in members.items():
        assert RISK_TEXT.encode() not in data and CONSENT_REF.encode() not in data, name
        assert f"sub-{GHOST}".encode() not in data, name
        assert (ROLE_TEXT.encode() in data) is (name == "roles.yaml"), name
        assert (PIA_TEXT.encode() in data) is (name == "pia/pia.en.md"), name
    for name in ("diff text", "diff json", "console check", "console check 2", "console report"):
        assert not re.search(r"sub-0\d", texts[name]), name


def test_consent_namespace_agrees_in_report_and_diff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-17 option B for every consent.* check (D-19): the rules that diff only counts are the rules the
    report aggregates, and a new consent version shows as a fixed re-consent result in the counts."""
    folder = _full_vault(tmp_path, capsys)
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    _check(folder, old, capsys)
    assert _consent(folder, capsys, "01", "2")[0] == 0
    _check(folder, new, capsys)
    code, out, err = run(["diff", str(old), str(new), "--format", "json"], capsys)
    assert code == 0, err
    result = json.loads(out)
    aggregated = {entry["rule_id"] for entry in result["aggregated"]}
    consent = set(tables.consent_rules(Results.model_validate_json(new.read_bytes())))
    assert consent == {"CORE-M14-01", "CORE-M14-02"} and aggregated and aggregated <= consent
    assert {"rule_id": "CORE-M14-02", "category": "fixed", "count": 1} in result["aggregated"]
    listed = [item for items in result["findings"].values() for item in items]
    assert not any(item["rule_id"] in consent for item in listed)


@pytest.mark.pdf
def test_dossier_as_export_report_part(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], pdf_shell: object
) -> None:
    """A-96, A-99: the dossier of a full vault is a report part of the export package (format dossier, no
    language) and holds no planted identifier and no subject of the consent records."""
    folder = _full_vault(tmp_path, capsys)
    target = tmp_path / "r.json"
    _check(folder, target, capsys)
    rep = tmp_path / "rep"
    toml = folder / ".neurogrid" / "neurogrid.toml"
    _report(target, rep, capsys, "--format", "dossier", "--config", str(toml))
    dossier = (rep / "dossier.pdf").read_bytes()
    text = "".join(page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(dossier)).pages)
    flat = re.sub(r"\s+", "", text)
    for token in (RISK_TEXT, CONSENT_REF, ROLE_TEXT, PIA_TEXT):
        assert token not in flat, token
    assert f"sub-{GHOST}" not in flat
    assert run(["manifest", str(folder)], capsys)[0] == 0
    package = tmp_path / "package.zip"
    _export(folder, package, capsys, rep / "dossier.pdf")
    members = _members(package)
    assert members["report/dossier.pdf"] == dossier
    (part,) = [part for part in json.loads(members["index.json"])["parts"] if part["part"] == "report"]
    assert (part["file"], part["format"], part["lang"]) == ("report/dossier.pdf", "dossier", None)


def test_five_stages_v1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """ARC-01 with every supplier of P9: dataset -> adapter and data model -> checkers (consent, re-consent,
    role register, retention and impact assessment, whose supplier is the vault) -> rule packs (core, bids,
    the placeholder pack) -> reports zh/en; the role register permits every event, so CORE-NV04-01 passes."""
    folder = _full_vault(tmp_path, capsys)
    target = tmp_path / "r.json"
    _, results, _ = _check(folder, target, capsys, "--rulepack", "bids", *YYT, as_of=LATE)
    assert results["recordings"]
    assert {pack["name"] for pack in results["rulepacks"]} == {"core", "bids", "yyt2029"}
    for rule in ("CORE-NV04-01", "CORE-NV05-01", "CORE-NV05-02", "CORE-M14-01"):
        assert _statuses(results, rule) == {"passed"}, rule
    assert _statuses(results, "CORE-M14-02") == {"failed"}  # consent version 1, the risk asks for 2
    toml = folder / ".neurogrid" / "neurogrid.toml"
    _report(target, tmp_path / "rep", capsys, "--lang", "zh,en", "--format", "html", "--config", str(toml))
    for lang in ("zh", "en"):
        tr = translator(lang).t
        text = visible_text((tmp_path / "rep" / f"report.{lang}.html").read_text(encoding="utf-8"))
        for key in ("report.label.access_log", "report.reconsent.heading", "report.placeholder_banner"):
            assert tr(key) in text, (lang, key)
    assert _events(folder)[-1]["action"] == "report"
