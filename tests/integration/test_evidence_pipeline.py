"""check with evidence.yaml (NG-F12, RP-05, A-15, A-83), the gxdsl008 pack (GX-00..GX-04, A-40), exceptions
(A-14) and a custom pack with a manual rule (UF-04, NG-F11) through the pipeline."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from conftest import DOCUMENTED_TOML, dir_link, documented_config  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.kernel import canonical
from neurogrid.kernel.errors import ConfigError, UnsafePathError
from neurogrid.kernel.evidence import DocumentCheck, EvidenceState
from neurogrid.kernel.findings import Light, Phase, Severity, SourceStatus, Status
from neurogrid.model.results import Results

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = date(2026, 10, 11)
GX = ("gxdsl008",)
SOP = b"IT security SOP 12: AES-256 at rest, role concept v2 (synthetic test document)\n"
WET = '[metadata.defaults]\nelectrode_type = "wet"\n'


def _dataset(tmp_path: Path, name: str = "ds", fixture: str = "edf_ok") -> Path:
    target = tmp_path / name
    shutil.copytree(FIX / fixture, target)
    return target


def _write_evidence(path: Path, entries: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("format_version: 1\nevidence:\n" + entries, encoding="utf-8")
    return path


def _check(target: Path, tmp_path: Path, **options: object) -> Results:
    config = options.pop("config_path", None) or documented_config(tmp_path)
    return pipeline.run_check(
        target,
        pipeline.CheckOptions(rulepacks=GX, as_of=AS_OF, config_path=config, **options),  # type: ignore[arg-type]
    )


def _gx04(results: Results) -> set[Status]:
    statuses = {f.status for f in results.findings if f.rule_id == "GXDSL008-ACC-001"}
    return statuses | (
        {Status.PASSED} if any(p.rule_id == "GXDSL008-ACC-001" for p in results.passed) else set()
    )


# --- location, flag and document root (A-22, A-66, A-83) -------------------------------------------------


def test_default_location_is_found_and_the_flag_wins(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path)
    (dataset / ".neurogrid" / "evidence").mkdir(parents=True)
    (dataset / ".neurogrid" / "evidence" / "sop.txt").write_bytes(SOP)
    _write_evidence(
        dataset / ".neurogrid" / "evidence.yaml",
        "  GXDSL008-ACC-001:\n    status: provided\n    document: .neurogrid/evidence/sop.txt\n"
        "    reviewer: QA\n    date: 2026-10-01\n    comment: role concept v2\n",
    )
    default = _check(dataset, tmp_path)
    assert _gx04(default) == {Status.PASSED}
    (record,) = default.evidence
    assert record.status is EvidenceState.PROVIDED and record.document_check is DocumentCheck.OK
    assert (
        record.document == ".neurogrid/evidence/sop.txt" and record.sha256 == hashlib.sha256(SOP).hexdigest()
    )
    assert (record.reviewer, record.date, record.comment) == ("QA", date(2026, 10, 1), "role concept v2")
    assert default.config.evidence_sha256 is not None and default.summary.open_evidence == 0
    elsewhere = _write_evidence(
        tmp_path / "other" / "evidence.yaml", "  GXDSL008-ACC-001:\n    status: open\n"
    )
    flagged = _check(dataset, tmp_path, evidence_path=elsewhere)
    assert _gx04(flagged) == {Status.EVIDENCE_OPEN} and flagged.summary.open_evidence == 1
    assert flagged.config.evidence_sha256 != default.config.evidence_sha256


def test_flag_outside_the_dataset_resolves_documents_next_to_the_file(tmp_path: Path) -> None:
    folder = tmp_path / "qms"
    (folder / "docs").mkdir(parents=True)
    (folder / "docs" / "sop.txt").write_bytes(SOP)
    evidence = _write_evidence(
        folder / "evidence.yaml",
        f"  GXDSL008-ACC-001:\n    status: provided\n    document: docs/sop.txt\n"
        f"    sha256: {hashlib.sha256(SOP).hexdigest().upper()}\n",
    )
    results = _check(FIX / "edf_ok", tmp_path, evidence_path=evidence)
    assert _gx04(results) == {Status.PASSED} and results.evidence[0].document_check is DocumentCheck.OK
    assert not [n for n in results.notices if n.level is Severity.WARNING]


def test_evidence_file_inside_the_dataset_resolves_against_the_dataset_root(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path)
    (dataset / "docs").mkdir()
    (dataset / "docs" / "sop.txt").write_bytes(SOP)
    evidence = _write_evidence(
        dataset / "docs" / "evidence.yaml",
        "  GXDSL008-ACC-001:\n    status: provided\n    document: docs/sop.txt\n",
    )
    results = _check(dataset, tmp_path, evidence_path=evidence)
    assert results.evidence[0].document_check is DocumentCheck.OK


def test_linked_default_evidence_is_not_followed(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path)
    foreign = tmp_path / "foreign"
    _write_evidence(foreign / "evidence.yaml", "  GXDSL008-ACC-001:\n    status: open\n")
    dir_link(dataset / ".neurogrid", foreign)
    with pytest.raises(UnsafePathError) as info:
        _check(dataset, tmp_path)  # explicit --config, so only the evidence lookup meets the link
    assert info.value.message_key == "path.link"


def test_missing_explicit_file_and_invalid_content_are_tool_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as info:
        _check(FIX / "edf_ok", tmp_path, evidence_path=tmp_path / "missing.yaml")
    assert info.value.message_key == "evidence.not_found"
    with pytest.raises(ConfigError) as info:
        _check(FIX / "edf_ok", tmp_path, evidence_path=tmp_path)  # a folder is no evidence file
    assert info.value.message_key == "evidence.not_found"
    bad = _write_evidence(tmp_path / "bad.yaml", "  GXDSL008-ACC-001:\n    status: provided\n")
    with pytest.raises(ConfigError) as info:
        _check(FIX / "edf_ok", tmp_path, evidence_path=bad)
    assert (
        info.value.message_key == "evidence.invalid" and info.value.params["problem"] == "document_required"
    )
    big = tmp_path / "big.yaml"
    big.write_bytes(b"format_version: 1\n#" + b"x" * 2_000_001 + b"\n")
    with pytest.raises(ConfigError) as info:
        _check(FIX / "edf_ok", tmp_path, evidence_path=big)
    assert info.value.message_key == "evidence.too_large"


# --- evaluation (A-15, A-83) ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutate", "check"),
    [
        (lambda folder: (folder / "sop.txt").unlink(), DocumentCheck.DOCUMENT_MISSING),
        (lambda folder: (folder / "sop.txt").write_bytes(SOP + b"edited\n"), DocumentCheck.HASH_MISMATCH),
    ],
)
def test_manual_provided_with_a_changed_document_stays_passed_with_a_warning(
    tmp_path: Path,
    mutate,
    check: DocumentCheck,  # type: ignore[no-untyped-def]
) -> None:
    folder = tmp_path / "qms"
    folder.mkdir()
    (folder / "sop.txt").write_bytes(SOP)
    evidence = _write_evidence(
        folder / "evidence.yaml",
        f"  GXDSL008-ACC-001:\n    status: provided\n    document: sop.txt\n"
        f"    sha256: {hashlib.sha256(SOP).hexdigest()}\n",
    )
    mutate(folder)
    results = _check(FIX / "edf_ok", tmp_path, evidence_path=evidence)
    assert _gx04(results) == {Status.PASSED} and results.summary.exit_code == 0
    assert results.evidence[0].document_check is check
    assert [(n.level, n.message_key) for n in results.notices if n.level is Severity.WARNING] == [
        (Severity.WARNING, f"notice.evidence_document.{check.value}")
    ]


def test_entries_for_other_rules_give_notices(tmp_path: Path) -> None:
    evidence = _write_evidence(
        tmp_path / "evidence.yaml",
        "  GXDSL008-ACQ-002:\n    status: open\n  LAB-ACC-009:\n    status: open\n",
    )
    results = _check(FIX / "edf_ok", tmp_path, evidence_path=evidence)
    keys = {(n.message_key, n.params.get("rule")) for n in results.notices}
    assert ("notice.evidence_ignored", "GXDSL008-ACQ-002") in keys
    assert ("notice.evidence_unused", "LAB-ACC-009") in keys
    assert _gx04(results) == {Status.EVIDENCE_OPEN}  # GX-04 itself has no entry


CUSTOM_MANUAL = """rulepack: lab
version: "1.0"
source: Lab SOP (synthetic)
source_status: final
rules:
  - id: LAB-ACC-001
    clause: "SOP-4.2"
    title_zh: 访问控制已记录
    title_en: Access control documented
    phase: access
    check: evidence.document
    severity: error
    verification: manual
"""


def test_custom_pack_with_a_manual_error_rule_works_without_code_changes(tmp_path: Path) -> None:
    """UF-04 / NG-F11: a custom pack by path with a manual error rule: exit 1 while open, 0 when provided."""
    pack = tmp_path / "lab.yaml"
    pack.write_text(CUSTOM_MANUAL, encoding="utf-8")
    options = {"rulepacks": (str(pack),), "as_of": AS_OF, "config_path": documented_config(tmp_path)}
    open_run = pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(**options))  # type: ignore[arg-type]
    assert open_run.summary.exit_code == 1 and open_run.summary.phases[Phase.ACCESS].light is Light.RED
    assert open_run.summary.open_evidence == 1 and open_run.summary.errors == 1
    (tmp_path / "sop.txt").write_bytes(SOP)
    evidence = _write_evidence(
        tmp_path / "evidence.yaml", "  LAB-ACC-001:\n    status: provided\n    document: sop.txt\n"
    )
    provided = pipeline.run_check(
        FIX / "edf_ok",
        pipeline.CheckOptions(evidence_path=evidence, **options),  # type: ignore[arg-type]
    )
    assert provided.summary.exit_code == 0 and provided.summary.phases[Phase.ACCESS].light is Light.GREEN


# --- gxdsl008 as a pack (GX-00, A-40, A-83) ---------------------------------------------------------------


def test_gxdsl008_pack_loads_without_draft_flag_and_only_warns(tmp_path: Path) -> None:
    results = _check(FIX / "edf_lowrate", tmp_path)  # 256 Hz: GX-02 fails, core M03-01 too (a warning)
    (pack,) = [p for p in results.rulepacks if p.name == "gxdsl008"]
    assert pack.source_status is SourceStatus.SECONDARY and pack.norm is True
    assert results.summary.coverage["gxdsl008"] == "n/a"
    gx = [f for f in results.findings if f.rulepack == "gxdsl008"]
    assert {f.rule_id for f in gx} >= {"GXDSL008-ACQ-002", "GXDSL008-ACC-001"}
    assert all(f.severity is Severity.WARNING and f.clause == "unknown" for f in gx)
    assert all(r.severity is Severity.WARNING for r in results.rules if r.rulepack == "gxdsl008")
    assert results.summary.exit_code == 0  # only warnings (A-12)
    assert results.summary.phases[Phase.ACCESS].light is Light.YELLOW  # GX-04 open, counted as a warning
    assert results.summary.phases[Phase.ACCESS].open_evidence == 1


def test_shared_thresholds_give_one_finding_per_pack(tmp_path: Path) -> None:
    config = tmp_path / "wet.toml"
    config.write_text(WET, encoding="utf-8")
    results = _check(FIX / "bids_issues", tmp_path, config_path=config)
    core = {
        (f.object, f.subkey, f.measured_value): f.key for f in results.findings if f.rule_id == "CORE-M05-02"
    }
    gx = {
        (f.object, f.subkey, f.measured_value): f.key
        for f in results.findings
        if f.rule_id == "GXDSL008-ACQ-001"
    }
    assert core and core.keys() == gx.keys()  # same measured values, own findings (A-40)
    assert not set(core.values()) & set(gx.values())  # different keys
    overridden = tmp_path / "override.toml"
    overridden.write_text(WET + '[rules."CORE-M05-02".params]\nmax_kohm = 100\n', encoding="utf-8")
    changed = _check(FIX / "bids_issues", tmp_path, config_path=overridden)
    assert not [f for f in changed.findings if f.rule_id == "CORE-M05-02" and f.status is Status.FAILED]
    assert [f for f in changed.findings if f.rule_id == "GXDSL008-ACQ-001" and f.status is Status.FAILED]
    params = changed.config.effective_params
    assert params["CORE-M05-02"]["max_kohm"].origin == "config"
    assert params["GXDSL008-ACQ-001"]["max_kohm"].origin == "rulepack"


def test_exception_on_core_leaves_the_gxdsl008_finding(tmp_path: Path) -> None:
    config = tmp_path / "exc.toml"
    config.write_text(
        WET + '[[exceptions]]\nrule = "CORE-M05-02"\nreason = "Electrodes re-gelled, see SOP-5."\n',
        encoding="utf-8",
    )
    results = _check(FIX / "bids_issues", tmp_path, config_path=config)
    core = {f.status for f in results.findings if f.rule_id == "CORE-M05-02"}
    gx = {f.status for f in results.findings if f.rule_id == "GXDSL008-ACQ-001"}
    assert Status.EXCEPTED in core and Status.FAILED not in core
    assert Status.FAILED in gx and Status.EXCEPTED not in gx


def test_gxdsl008_alone_is_never_silent_on_impedance(tmp_path: Path) -> None:
    """Q16: loaded without core, GX-01 reports every recording without documented impedances."""
    config = tmp_path / "only.toml"
    config.write_text('[check]\nrulepacks = ["gxdsl008"]\n', encoding="utf-8")
    results = pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(config_path=config, as_of=AS_OF))
    assert [p.name for p in results.rulepacks] == ["gxdsl008"]
    gx01 = [f for f in results.findings if f.rule_id == "GXDSL008-ACQ-001"]
    assert len(gx01) == 2 and {f.reason for f in gx01} == {"impedance.not_documented"}


# --- determinism and privacy (NG-N03, A-11, A-51) ---------------------------------------------------------


def _determinism_setup(tmp_path: Path, comment: str) -> tuple[Path, Path, Path]:
    dataset = _dataset(tmp_path, "ds", "bids_issues")
    (dataset / ".neurogrid" / "evidence").mkdir(parents=True)
    (dataset / ".neurogrid" / "evidence" / "sop.txt").write_bytes(SOP)
    evidence = _write_evidence(
        dataset / ".neurogrid" / "evidence.yaml",
        "  GXDSL008-ACC-001:\n    status: provided\n    document: .neurogrid/evidence/sop.txt\n"
        f"    reviewer: QA\n    date: 2026-10-01\n    comment: {comment}\n",
    )
    config = tmp_path / "det.toml"
    config.write_text(
        WET
        + '[[exceptions]]\nrule = "CORE-M05-02"\nreason = "old"\nvalid_until = 2026-01-01\n'
        + '[[exceptions]]\nrule = "GXDSL008-ACQ-001"\nreason = "SOP-5"\nvalid_until = 2027-01-01\n',
        encoding="utf-8",
    )
    return dataset, config, evidence


def test_two_runs_are_byte_identical_and_evidence_changes_only_its_block(tmp_path: Path) -> None:
    dataset, config, evidence = _determinism_setup(tmp_path, "role concept v2")
    first = canonical.dumps(_check(dataset, tmp_path, config_path=config))
    second = canonical.dumps(_check(dataset, tmp_path, config_path=config))
    assert first == second
    text = first.decode("utf-8")
    for absolute in (str(tmp_path), str(tmp_path).replace("\\", "/"), str(evidence), "evidence.yaml"):
        assert absolute not in text
    before = json.loads(first)
    assert [u["expired"] for u in before["exceptions"]] == [True, False]
    evidence.write_text(evidence.read_text(encoding="utf-8").replace("v2", "v3"), encoding="utf-8")
    after = json.loads(canonical.dumps(_check(dataset, tmp_path, config_path=config)))
    assert after["config"]["evidence_sha256"] != before["config"]["evidence_sha256"]
    assert after["evidence"][0]["comment"] == "role concept v3"
    assert after["findings"] == before["findings"] and after["passed"] == before["passed"]


def test_raw_folder_names_do_not_leak_through_evidence(tmp_path: Path) -> None:
    dataset = tmp_path / "raw"
    site = dataset / "ZhangSan_19800101"
    site.mkdir(parents=True)
    (site / "rec.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    (dataset / ".neurogrid" / "evidence").mkdir(parents=True)
    (dataset / ".neurogrid" / "evidence" / "sop.txt").write_bytes(SOP)
    _write_evidence(
        dataset / ".neurogrid" / "evidence.yaml",
        "  GXDSL008-ACC-001:\n    status: provided\n    document: .neurogrid/evidence/sop.txt\n"
        "    reviewer: Max Mustermann\n",
    )
    config = tmp_path / "raw.toml"
    config.write_text(
        DOCUMENTED_TOML.split("[convert]")[0]
        + '[[exceptions]]\nrule = "CORE-M01-02"\nobject = "ZhangSan_19800101/**"\nreason = "SOP"\n',
        encoding="utf-8",
    )
    results = _check(dataset, tmp_path, config_path=config)
    text = canonical.dumps(results).decode("utf-8")
    assert "ZhangSan" not in text and "19800101" not in text  # data file names stay pseudonymous
    assert results.evidence[0].document == ".neurogrid/evidence/sop.txt"  # relative reference (G15)
    hint = [n for n in results.notices if n.message_key == "notice.evidence_looks_identifying"]
    assert hint and hint[0].params == {"count": 1}  # the reviewer looks like a name (A-51 hint)
