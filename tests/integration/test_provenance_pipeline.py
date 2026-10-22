"""M13 end to end (NG-F10, M13, CLI-04, CLI-06, UF-05, A-22, A-82): manifest, handover and verify; check with
a manifest (CORE-M13-01..03), --strict, results.json, the report cover, privacy, exceptions, links, the GX-05
check, and real subprocesses (Python and Windows PowerShell 5.1)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path, PurePosixPath

import jsonschema
import pytest

from conftest import DOCUMENTED_TOML, dir_link, documented_config  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.cli import main
from neurogrid.io.discover import pseudonym
from neurogrid.kernel import canonical
from neurogrid.kernel.findings import Light, Phase, Severity, Status
from neurogrid.kernel.provenance import ManifestError, ManifestStatus, manifest_hash
from neurogrid.model.results import Results
from neurogrid.report.render import render_report

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
SCHEMAS = Path(__file__).parent.parent.parent / "src" / "neurogrid" / "schemas"
AS_OF = date(2026, 10, 11)
WINDOWS = sys.platform == "win32"
M13 = ("CORE-M13-01", "CORE-M13-02", "CORE-M13-03")


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def _copy(tmp_path: Path, fixture: str = "edf_ok", name: str = "ds") -> Path:
    target = tmp_path / name
    shutil.copytree(FIX / fixture, target)
    return target


def _manifest(folder: Path, out: Path | None = None) -> Path:
    built = pipeline.run_manifest(folder, out)
    assert built.data is not None
    built.target.parent.mkdir(parents=True, exist_ok=True)
    built.target.write_bytes(built.data)
    return built.target


def _check(folder: Path, **options: object) -> Results:
    return pipeline.run_check(folder, pipeline.CheckOptions(as_of=AS_OF, **options))  # type: ignore[arg-type]


def _m13(results: Results) -> dict[str, set[tuple[Status, str | None]]]:
    found: dict[str, set[tuple[Status, str | None]]] = {rule: set() for rule in M13}
    for finding in results.findings:
        if finding.rule_id in found:
            found[finding.rule_id].add((finding.status, finding.subkey))
    for passed in results.passed:
        if passed.rule_id in found:
            found[passed.rule_id].add((Status.PASSED, None))
    return found


def _lock(path: Path) -> tuple[int, int]:
    """Make a file unreadable for other handles: a byte-range lock on Windows, mode 000 on POSIX."""
    size = path.stat().st_size
    if WINDOWS:
        import msvcrt

        descriptor = os.open(path, os.O_RDWR | os.O_BINARY)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, size)
        return descriptor, size
    if os.geteuid() == 0:
        pytest.skip("root can read every file")
    path.chmod(0)
    return -1, size


def _unlock(path: Path, lock: tuple[int, int]) -> None:
    descriptor, size = lock
    if WINDOWS:
        import msvcrt

        os.lseek(descriptor, 0, 0)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, size)
        os.close(descriptor)
    else:
        path.chmod(0o644)


# --- UF-05: manifest, handover, verify -----------------------------------------------------------------


def test_uf05_manifest_handover_and_verify(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ds = _copy(tmp_path, "bids_ok")
    code, out, _ = run(["manifest", str(ds)], capsys)
    default = ds / ".neurogrid" / "manifest.json"  # KONZEPT 2.5, A-82: .neurogrid/ is created if missing
    assert code == 0 and "<dataset>" in out and str(tmp_path) not in out
    assert default.is_file() and not (ds / "manifest.json").exists() and "Manifest hash:" in out
    assert f"Manifest written to {Path('<dataset>', '.neurogrid', 'manifest.json')}" in out
    assert "BIDS validator" not in out  # the validator does not enter .neurogrid/: no hint needed
    manifest = json.loads(default.read_text(encoding="utf-8"))
    assert ".neurogrid/manifest.json" not in {item["path"] for item in manifest["files"]}
    first = default.read_bytes()
    code, _, _ = run(["manifest", str(ds)], capsys)
    assert code == 0 and default.read_bytes() == first  # deterministic; itself left out
    handover = tmp_path / "handover"
    shutil.copytree(ds, handover)  # handover: another folder, the same content, the manifest inside
    handed = handover / ".neurogrid" / "manifest.json"
    code, out, _ = run(["verify", str(handover), "--manifest", str(handed)], capsys)
    assert code == 0 and "matches the manifest" in out and manifest["manifest_hash"] in out
    sidecar = handover / "sub-01" / "eeg" / "sub-01_task-rest_eeg.json"
    sidecar.write_text(sidecar.read_text(encoding="utf-8") + " ", encoding="utf-8")
    (handover / "sub-02" / "eeg" / "notes.txt").write_text("added", encoding="utf-8")
    (handover / "README").unlink()
    code, out, _ = run(["verify", str(handover), "--manifest", str(handed)], capsys)
    assert code == 1 and "differs from the manifest" in out
    result = pipeline.run_verify(handover, handed)
    assert result.deviations == {
        "changed": ["sub-01/eeg/sub-01_task-rest_eeg.json"],
        "new": ["sub-02/eeg/notes.txt"],
        "missing": ["README"],
        "skipped_changed": [],
        "unreadable": [],
    }
    assert "  - sub-02/eeg/notes.txt" in out and "Changed: 1" in out and "Missing: 1" in out


def test_bids_validator_and_the_manifest_location(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A-82 (KONZEPT 2.5, A-22): the validator does not enter .neurogrid/, so the default location leaves
    BIDS-STO-001 green. A manifest written with --out into the BIDS dataset outside a hidden folder is listed
    (NOT_INCLUDED, SIDECAR_WITHOUT_DATAFILE with the bundled validator): manifest prints the hint."""
    ds = _copy(tmp_path, "bids_ok")
    code, out, _ = run(["manifest", str(ds)], capsys)
    assert code == 0 and "BIDS validator" not in out
    default = _check(ds, rulepacks=("bids",))
    assert [f for f in default.findings if f.rule_id == "BIDS-STO-001"] == []
    assert any(p.rule_id == "BIDS-STO-001" for p in default.passed)
    assert _m13(default)["CORE-M13-02"] == {(Status.PASSED, None)}
    (ds / ".neurogrid" / "manifest.json").unlink()
    code, out, _ = run(["manifest", str(ds), "--out", str(ds / "manifest.json")], capsys)
    assert code == 0 and "BIDS validator" in out and ".neurogrid/manifest.json" in out  # the hint
    at_root = _check(ds, rulepacks=("bids",), manifest_path=ds / "manifest.json")
    listed = {(f.object, f.subkey) for f in at_root.findings if f.rule_id == "BIDS-STO-001"}
    assert listed == {("manifest.json", "NOT_INCLUDED"), ("manifest.json", "SIDECAR_WITHOUT_DATAFILE")}
    assert _m13(at_root)["CORE-M13-02"] == {(Status.PASSED, None)}  # the manifest read is left out
    code, out, _ = run(["manifest", str(ds), "--out", str(ds / ".neurogrid" / "copy.json")], capsys)
    assert code == 0 and "BIDS validator" not in out  # inside a hidden folder: not listed
    code, out, _ = run(["manifest", str(ds), "--out", str(tmp_path / "outside.json")], capsys)
    assert code == 0 and "BIDS validator" not in out


@pytest.mark.parametrize("name", ["splits.tsv", "neurogrid.toml"])
@pytest.mark.parametrize("action", ["changed", "new", "missing"])
def test_verify_detects_changes_in_splits_and_toml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, action: str
) -> None:
    """P4 DoD: verify detects changed, new and missing also in splits.tsv and neurogrid.toml. NeuroGrid's
    control files are shown by name also in raw folders (critic X14)."""
    ds = _copy(tmp_path)
    control = ds / ".neurogrid" / name
    control.parent.mkdir()
    content = DOCUMENTED_TOML if name == "neurogrid.toml" else "recording\tsplit\nrec_a.edf\ttrain\n"
    if action != "new":
        control.write_text(content, encoding="utf-8")
    manifest = _manifest(ds, tmp_path / "m.json")
    if action == "changed":
        # an invalid TOML is a changed file for verify (it never reads the toml), not a tool error (A-82)
        changed = "[[[ not toml" if name == "neurogrid.toml" else content + "rec_b.edf\ttest\n"
        control.write_text(changed, encoding="utf-8")
    elif action == "new":
        control.write_text(content, encoding="utf-8")
    else:
        control.unlink()
    code, out, _ = run(["verify", str(ds), "--manifest", str(manifest)], capsys)
    assert code == 1 and f".neurogrid/{name}" in out
    deviations = pipeline.run_verify(ds, manifest).deviations
    assert {kind: names for kind, names in deviations.items() if names} == {action: [f".neurogrid/{name}"]}
    if action == "changed" and name == "neurogrid.toml":
        code, _, err = run(["check", str(ds), "--out", str(tmp_path / "r.json")], capsys)
        assert code == 2 and "syntax" in err  # check reads the toml: invalid configuration (A-12)


def test_links_are_reported_in_skipped(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ds = _copy(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.edf").write_bytes((FIX / "edf_ok" / "rec_a.edf").read_bytes())
    dir_link(ds / "linked", outside)
    code, out, _ = run(["manifest", str(ds), "--out", str(tmp_path / "m.json")], capsys)
    assert code == 0 and "1 link(s)" in out
    manifest = json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))
    assert manifest["skipped"] == [{"kind": "link", "path": "linked"}]
    assert [item["path"] for item in manifest["files"]] == ["rec_a.edf", "rec_b.edf"]  # nothing behind it
    dir_link(ds / "linked2", outside)
    (ds / "rec_b.edf").unlink()
    dir_link(ds / "rec_b.edf", outside)  # a file replaced by a link
    if WINDOWS:
        Path(ds / "linked").rmdir()
    else:
        (ds / "linked").unlink()
    result = pipeline.run_verify(ds, tmp_path / "m.json", show_paths=True)
    assert {kind: names for kind, names in result.deviations.items() if names} == {
        "new": ["linked2"],
        "missing": ["linked"],
        "skipped_changed": ["rec_b.edf"],
    }
    code, out, _ = run(["verify", str(ds), "--manifest", str(tmp_path / "m.json")], capsys)
    assert code == 1 and "linked2" not in out and "rec-" in out  # raw folder: pseudonyms (A-51)
    code, out, _ = run(["verify", str(ds), "--manifest", str(tmp_path / "m.json"), "--show-paths"], capsys)
    assert code == 1 and "linked2" in out
    results = _check(ds, manifest_path=tmp_path / "m.json")
    subkeys = {f.subkey for f in results.findings if f.rule_id == "CORE-M13-02"}
    assert subkeys == {"new", "missing", "skipped_changed"}
    assert any(n.message_key == "notice.links_skipped" for n in results.notices)


# --- check: CORE-M13-01..03, --strict, results.json ---------------------------------------------------


def test_strict_turns_a_missing_manifest_into_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ds = _copy(tmp_path)
    config = str(documented_config(tmp_path))
    code, _, _ = run(["check", str(ds), "--out", str(tmp_path / "a.json"), "--config", config], capsys)
    normal = Results.model_validate_json((tmp_path / "a.json").read_bytes())
    assert code == 0
    finding = next(f for f in normal.findings if f.rule_id == "CORE-M13-01")
    assert (finding.severity, finding.status, finding.reason) == (
        Severity.WARNING,
        Status.FAILED,
        "provenance.manifest_missing",
    )
    rule = next(r for r in normal.rules if r.id == "CORE-M13-01")
    assert (rule.severity, rule.strict_severity) == (Severity.WARNING, Severity.ERROR)
    code, out, _ = run(
        ["check", str(ds), "--out", str(tmp_path / "b.json"), "--config", config, "--strict"], capsys
    )
    strict = Results.model_validate_json((tmp_path / "b.json").read_bytes())
    assert code == 1 and "does not pass" in out and strict.config.strict
    finding = next(f for f in strict.findings if f.rule_id == "CORE-M13-01")
    assert finding.severity is Severity.ERROR and strict.summary.phases[Phase.STORAGE].light is Light.RED
    assert next(r for r in strict.rules if r.id == "CORE-M13-01").severity is Severity.ERROR
    strict_toml = documented_config(tmp_path, "[check]\nstrict = true\n", name="strict.toml")
    code, _, _ = run(
        ["check", str(ds), "--out", str(tmp_path / "c.json"), "--config", str(strict_toml)], capsys
    )
    assert code == 1
    _manifest(ds)
    code, _, _ = run(
        ["check", str(ds), "--out", str(tmp_path / "d.json"), "--config", config, "--strict"], capsys
    )
    assert code == 0  # with a manifest, --strict changes nothing; CORE-M13-03 stays a warning


def test_results_manifest_block_for_every_status(tmp_path: Path) -> None:
    ds = _copy(tmp_path)
    schema = json.loads((SCHEMAS / "results.schema.json").read_text(encoding="utf-8"))
    missing = _check(ds)
    assert missing.manifest is not None and missing.manifest.status is ManifestStatus.MISSING
    assert missing.dataset.manifest_hash is None
    # nothing to compare: CORE-M13-02 not applicable, the missing manifest is CORE-M13-01's finding (A-82)
    m13 = {(f.rule_id, f.status, f.reason) for f in missing.findings if f.rule_id in M13[:2]}
    assert m13 == {
        ("CORE-M13-01", Status.FAILED, "provenance.manifest_missing"),
        ("CORE-M13-02", Status.NOT_APPLICABLE, "provenance.manifest_missing"),
    }
    assert missing.summary.phases[Phase.STORAGE].errors == 0
    path = _manifest(ds)
    stored = json.loads(path.read_text(encoding="utf-8"))
    matches = _check(ds)
    assert matches.manifest is not None and matches.manifest.status is ManifestStatus.MATCHES
    assert matches.manifest.sha256 == matches.dataset.manifest_hash == stored["manifest_hash"]
    assert (matches.manifest.files, matches.manifest.changed, matches.manifest.new) == (2, 0, 0)
    text = canonical.dumps(matches).decode("utf-8")
    jsonschema.validate(json.loads(text), schema)
    for item in stored["files"]:
        assert item["sha256"] not in text  # no per-file hashes in results.json (A-11, A-51)
    assert str(tmp_path) not in text and str(Path.home()) not in text
    bids_only = documented_config(tmp_path, '[check]\nrulepacks = ["bids"]\n', name="bids.toml")
    not_verified = _check(ds, config_path=bids_only)
    assert not_verified.manifest is not None and not_verified.manifest.status is ManifestStatus.NOT_VERIFIED
    assert not_verified.dataset.manifest_hash == stored["manifest_hash"]
    (ds / "rec_a.edf").write_bytes((ds / "rec_a.edf").read_bytes()[:-1])
    differs = _check(ds)
    assert differs.manifest is not None and differs.manifest.status is ManifestStatus.DIFFERS
    assert differs.manifest.changed == 1 and differs.summary.exit_code == 1
    edited = dict(stored)
    edited["files"] = [dict(stored["files"][0], size=1), stored["files"][1]]
    path.write_text(json.dumps(edited), encoding="utf-8")
    mismatch = _check(ds)
    assert mismatch.manifest is not None and mismatch.manifest.status is ManifestStatus.HASH_MISMATCH
    assert ("CORE-M13-02", "manifest_hash") in {(f.rule_id, f.subkey) for f in mismatch.findings}
    path.write_text("{", encoding="utf-8")
    invalid = _check(ds)
    assert invalid.manifest is not None and invalid.manifest.status is ManifestStatus.INVALID
    assert invalid.manifest.sha256 is None and invalid.dataset.manifest_hash is None
    finding = next(f for f in invalid.findings if f.rule_id == "CORE-M13-01")
    assert (
        finding.reason == "provenance.manifest_invalid" and finding.details["problem"] == "manifest.invalid"
    )
    unusable = next(f for f in invalid.findings if f.rule_id == "CORE-M13-02")
    assert (unusable.status, unusable.reason) == (Status.NOT_CHECKABLE, "provenance.manifest_invalid")
    single = _check(FIX / "edf_ok" / "rec_a.edf", strict=True)
    assert single.manifest is not None and single.manifest.status is ManifestStatus.NOT_APPLICABLE
    assert {status for found in _m13(single).values() for status, _ in found} == {Status.NOT_APPLICABLE}
    for results in (missing, differs, mismatch, invalid, single):
        jsonschema.validate(json.loads(canonical.dumps(results)), schema)


def test_two_checks_with_a_manifest_are_byte_identical(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Determinism (A-11) with --out outside the dataset (critic X15)."""
    ds = _copy(tmp_path)
    _manifest(ds)
    outputs = []
    for name in ("one", "two"):
        target = tmp_path / name / "results.json"
        code, _, _ = run(["check", str(ds), "--out", str(target), "--as-of", "2026-10-11"], capsys)
        assert code == 1  # raw folder without documented metadata (M02-01)
        outputs.append(target.read_bytes())
    assert outputs[0] == outputs[1]
    results = Results.model_validate_json(outputs[0])
    assert _m13(results)["CORE-M13-02"] == {(Status.PASSED, None)}
    assert not any(n.message_key == "notice.output_inside_dataset" for n in results.notices)


def test_output_inside_the_dataset(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ds = _copy(tmp_path)
    _manifest(ds)
    config = str(documented_config(tmp_path))
    target = ds / "results" / "r.json"
    code, out, _ = run(["check", str(ds), "--out", str(target), "--config", config], capsys)
    first = Results.model_validate_json(target.read_bytes())
    assert code == 0 and "lies inside the dataset" in out
    assert any(n.message_key == "notice.output_inside_dataset" for n in first.notices)
    assert _m13(first)["CORE-M13-02"] == {(Status.PASSED, None)}  # the run's work folder is left out
    code, _, _ = run(["check", str(ds), "--out", str(target), "--config", config], capsys)
    second = Results.model_validate_json(target.read_bytes())
    assert code == 1  # the first results file is a new file now: the documented limit (critic X15)
    assert [f.subkey for f in second.findings if f.rule_id == "CORE-M13-02"] == ["new"]


def test_check_manifest_option(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = _manifest(FIX / "edf_ok", tmp_path / "elsewhere" / "m.json")  # manifest outside the dataset
    results = _check(FIX / "edf_ok", manifest_path=out)
    assert _m13(results)["CORE-M13-01"] == {(Status.PASSED, None)}
    assert _m13(results)["CORE-M13-02"] == {(Status.PASSED, None)}
    with pytest.raises(ManifestError) as info:
        _check(FIX / "edf_ok", manifest_path=tmp_path / "missing.json")
    assert info.value.message_key == "manifest.not_found"
    code, _, err = run(["check", str(FIX / "edf_ok"), "--manifest", str(tmp_path / "missing.json")], capsys)
    assert code == 2 and "Manifest file not found" in err
    code, _, err = run(["check", str(FIX / "edf_ok"), "--manifest", str(tmp_path)], capsys)
    assert code == 2 and "Manifest file not found" in err  # a folder is no manifest file


def test_single_file_is_no_dataset_for_manifest_and_verify(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run(["manifest", str(FIX / "edf_ok" / "rec_a.edf")], capsys)
    assert code == 2 and "not a single file" in err
    code, _, err = run(
        ["verify", str(FIX / "edf_ok" / "rec_a.edf"), "--manifest", str(tmp_path / "m")], capsys
    )
    assert code == 2 and "not a single file" in err


def test_documented_processing_steps_and_software(tmp_path: Path) -> None:
    ok = _check(FIX / "provenance_ok")
    assert _m13(ok)["CORE-M13-03"] == {(Status.PASSED, None)}
    bare = _check(FIX / "edf_ok")
    reasons = {f.subkey: f.reason for f in bare.findings if f.rule_id == "CORE-M13-03"}
    assert reasons == {
        "processing_steps": "provenance.steps_missing",
        "software": "provenance.software_missing",
    }
    incomplete = _check(FIX / "provenance_incomplete")
    reasons = {f.subkey: f.reason for f in incomplete.findings if f.rule_id == "CORE-M13-03"}
    assert reasons == {
        "processing_steps": "provenance.step_incomplete",
        "software": "provenance.software_missing",
    }
    invalid = _check(FIX / "provenance_steps_invalid")  # an integrity artefact: a finding, never exit 2 (C2)
    finding = next(f for f in invalid.findings if f.subkey == "processing_steps")
    assert finding.reason == "provenance.steps_invalid" and finding.details["problem"] == "schema"
    ds = _copy(tmp_path, "edf_ok")
    (ds / ".neurogrid").mkdir()
    (ds / ".neurogrid" / "provenance.yaml").write_text("processing_steps: []\n", encoding="utf-8")
    declared = _check(ds)
    statuses = {f.subkey: f.status for f in declared.findings if f.rule_id == "CORE-M13-03"}
    assert statuses == {"software": Status.FAILED}  # "no processing" documents the steps, not the software
    bids = _copy(tmp_path, "bids_ok", "bids")
    description = json.loads((bids / "dataset_description.json").read_text(encoding="utf-8"))
    description["GeneratedBy"] = [{"Name": "ExamplePipeline", "Version": "1.0"}]
    (bids / "dataset_description.json").write_text(json.dumps(description), encoding="utf-8")
    generated = _check(bids)
    statuses = {f.subkey: f.status for f in generated.findings if f.rule_id == "CORE-M13-03"}
    assert statuses == {"processing_steps": Status.FAILED}  # GeneratedBy documents software only
    run_ = pipeline.run_manifest(bids, tmp_path / "bids.json")
    assert run_.manifest is not None
    assert ("ExamplePipeline", "1.0", "bids") in {
        (s.name, s.version, s.source) for s in run_.manifest.software
    }


def test_converted_dataset_documents_its_steps(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    shutil.copy2(FIX / "edf_ok" / "rec_a.edf", raw / "rec_a.edf")
    (raw / ".neurogrid").mkdir()
    (raw / ".neurogrid" / "neurogrid.toml").write_text(
        '[metadata.defaults]\nreference = "Cz"\nline_frequency_hz = 50\nsoftware_filters = "n/a"\n'
        '[[convert.files]]\npath = "rec_a.edf"\nsubject = "01"\ntask = "rest"\n',
        encoding="utf-8",
    )
    out = tmp_path / "bids"
    summary = pipeline.run_convert(raw, out, work_base=tmp_path)
    assert summary.converted == 1
    built = pipeline.run_manifest(out, tmp_path / "m.json")
    assert built.manifest is not None and len(built.manifest.processing_steps) == 1
    step = built.manifest.processing_steps[0]
    assert (step.step, step.tool) == ("convert_to_bids", "neurogrid") and step.input_hash and step.output_hash
    sources = {(s.name, s.source) for s in built.manifest.software}
    assert {("neurogrid", "manifest"), ("neurogrid", "processing_steps")} <= sources
    assert ".neurogrid/processing_steps.json" in {item.path for item in built.manifest.files}
    results = _check(out)
    assert _m13(results)["CORE-M13-03"] == {(Status.PASSED, None)}


def test_gx05_check_passes_only_with_a_matching_manifest(tmp_path: Path) -> None:
    """provenance.manifest_matches for gxdsl008 GX-05 (A-15, A-82): semi-automatic, is_true."""
    pack = tmp_path / "gx.yaml"
    pack.write_text(
        "rulepack: gxtest\nversion: '1'\nsource: GX-05 test\nsource_status: secondary\nrules:\n"
        "  - id: GXT-STO-002\n    clause: unknown\n    title_zh: 文件校验和\n    title_en: Checksums\n"
        "    phase: storage\n    check: provenance.manifest_matches\n    severity: warning\n"
        "    verification: semi_automatic\n",
        encoding="utf-8",
    )

    def outcome(folder: Path) -> tuple[Status, str | None]:
        results = _check(folder, rulepacks=(str(pack),))
        if any(p.rule_id == "GXT-STO-002" for p in results.passed):
            return Status.PASSED, None
        finding = next(f for f in results.findings if f.rule_id == "GXT-STO-002")
        return finding.status, finding.reason

    ds = _copy(tmp_path)
    assert outcome(ds) == (Status.FAILED, "provenance.manifest_missing")
    path = _manifest(ds)
    assert outcome(ds) == (Status.PASSED, None)
    (ds / "extra.txt").write_text("x", encoding="utf-8")
    assert outcome(ds) == (Status.FAILED, "provenance.files_differ")
    (ds / "extra.txt").unlink()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["software"] = []
    path.write_text(json.dumps(data), encoding="utf-8")
    assert outcome(ds) == (Status.FAILED, "provenance.manifest_hash_mismatch")
    path.write_text("[]", encoding="utf-8")
    assert outcome(ds) == (Status.FAILED, "provenance.manifest_invalid")
    data["manifest_hash"] = manifest_hash(data)
    path.write_text(json.dumps(data), encoding="utf-8")  # re-hashed after the edit: consistent again
    assert outcome(ds) == (Status.PASSED, None)
    assert outcome(FIX / "edf_ok" / "rec_a.edf") == (Status.NOT_APPLICABLE, "provenance.single_file")


def test_gxdsl008_gx05_uses_the_default_manifest(tmp_path: Path) -> None:
    """GX-05 (GXDSL008-STO-002) in the built-in pack: semi-automatic warning with clause 'unknown' on
    provenance.manifest_matches (A-15, A-82, A-83); <dataset>/.neurogrid/manifest.json is read by default."""
    ds = _copy(tmp_path, "bids_ok")
    config = documented_config(tmp_path, '[check]\nrulepacks = ["gxdsl008"]\n', name="gx.toml")

    def gx05(results: Results) -> list[tuple[Status, Severity, str | None]]:
        found = [
            (f.status, f.severity, f.reason) for f in results.findings if f.rule_id == "GXDSL008-STO-002"
        ]
        passed = [
            (Status.PASSED, Severity.WARNING, None) for p in results.passed if p.rule_id == "GXDSL008-STO-002"
        ]
        return found + passed

    missing = _check(ds, config_path=config)
    rule = next(r for r in missing.rules if r.id == "GXDSL008-STO-002")
    assert (rule.severity, rule.verification.value, rule.phase, rule.strict_severity) == (
        Severity.WARNING,
        "semi_automatic",
        Phase.STORAGE,
        None,
    )
    assert gx05(missing) == [(Status.FAILED, Severity.WARNING, "provenance.manifest_missing")]
    assert missing.summary.exit_code == 0 and missing.summary.coverage == {"gxdsl008": "n/a"}
    _manifest(ds)
    assert gx05(_check(ds, config_path=config)) == [(Status.PASSED, Severity.WARNING, None)]
    assert gx05(_check(ds, config_path=config, strict=True)) == [(Status.PASSED, Severity.WARNING, None)]
    (ds / "README").write_text("changed\n", encoding="utf-8")
    changed = _check(ds, config_path=config, strict=True)  # a warning also in strict mode
    assert gx05(changed) == [(Status.FAILED, Severity.WARNING, "provenance.files_differ")]
    assert changed.summary.exit_code == 0


# --- exceptions, show-paths, privacy ------------------------------------------------------------------


def test_exceptions_and_stable_keys(tmp_path: Path) -> None:
    ds = _copy(tmp_path, "bids_ok")
    _manifest(ds)
    (ds / "derivatives" / "pipeline").mkdir(parents=True)
    (ds / "derivatives" / "pipeline" / "out.tsv").write_text("x\n", encoding="utf-8")
    (ds / "README").write_text("changed readme\n", encoding="utf-8")
    config = tmp_path / "exceptions.toml"
    config.write_text(
        '[[exceptions]]\nrule = "CORE-M13-02"\nobject = "derivatives/**"\nreason = "Derived files, SOP-4."\n'
        '[[exceptions]]\nrule = "CORE-M13-02"\nsubkey = "changed"\nreason = "README updated, ticket 12."\n',
        encoding="utf-8",
    )
    results = _check(ds, config_path=config)
    statuses = {(f.object, f.subkey, f.status) for f in results.findings if f.rule_id == "CORE-M13-02"}
    assert statuses == {
        ("derivatives/pipeline/out.tsv", "new", Status.EXCEPTED),
        ("README", "changed", Status.EXCEPTED),
    }
    assert results.summary.exit_code == 0 and all(use.used for use in results.exceptions)
    raw = _copy(tmp_path, "edf_ok", "raw")
    _manifest(raw)
    (raw / "rec_a.edf").write_bytes((raw / "rec_a.edf").read_bytes() + b"\0")
    hidden = _check(raw)
    shown = _check(raw, show_paths=True)
    key = {f.key for f in hidden.findings if f.rule_id == "CORE-M13-02"}
    assert key == {f.key for f in shown.findings if f.rule_id == "CORE-M13-02"}  # A-68
    assert [f.object for f in shown.findings if f.rule_id == "CORE-M13-02"] == ["rec_a.edf"]
    pseudonymous = [f for f in hidden.findings if f.rule_id == "CORE-M13-02"]
    assert (
        pseudonymous[0].object.startswith("rec-") and pseudonymous[0].file == pseudonymous[0].object + ".edf"
    )
    assert pseudonymous[0].details == {"size_manifest": 84224, "size_now": 84225}
    by_file = documented_config(
        tmp_path,
        f'[[exceptions]]\nrule = "CORE-M13-02"\nobject = "{pseudonymous[0].file}"\nreason = "Re-exported."\n',
        name="by_file.toml",
    )
    assert {f.status for f in _check(raw, config_path=by_file).findings if f.rule_id == "CORE-M13-02"} == {
        Status.EXCEPTED
    }


def test_planted_names_never_leave_the_manifest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A-51: identifying file names appear only in manifest.json (by design, the ID-to-path mapping)."""
    ds = tmp_path / "ds"
    ds.mkdir()
    edf = (FIX / "edf_ok" / "rec_a.edf").read_bytes()
    (ds / "ZhangSan_19800101.edf").write_bytes(edf)
    (ds / "张三.edf").write_bytes(edf)
    (ds / "LiSi").mkdir()
    (ds / "LiSi" / "rec.edf").write_bytes(edf)
    planted = ("ZhangSan", "19800101", "张三", "LiSi", "WangWu")
    code, out, err = run(["manifest", str(ds)], capsys)
    assert code == 0 and not any(name in out + err for name in planted)
    written = ds / ".neurogrid" / "manifest.json"
    manifest_text = written.read_text(encoding="utf-8")
    assert "ZhangSan_19800101.edf" in manifest_text and "张三.edf" in manifest_text
    (ds / "ZhangSan_19800101.edf").write_bytes(edf + b"\0")
    (ds / "WangWu_19900101.txt").write_text("x", encoding="utf-8")
    (ds / "LiSi" / "rec.edf").unlink()
    code, out, err = run(["verify", str(ds), "--manifest", str(written)], capsys)
    assert code == 1 and not any(name in out + err for name in planted) and "rec-" in out
    results_file = tmp_path / "r.json"
    # metadata only: a mapping pattern would turn the planted names into BIDS labels (A-05, not M13)
    config = tmp_path / "metadata.toml"
    config.write_text('[metadata.defaults]\nreference = "Cz"\nline_frequency_hz = 50\n', encoding="utf-8")
    code, out, err = run(["check", str(ds), "--out", str(results_file), "--config", str(config)], capsys)
    text = results_file.read_text(encoding="utf-8")
    assert not any(name in out + err + text for name in planted)
    results = Results.model_validate_json(results_file.read_bytes())
    assert {f.subkey for f in results.findings if f.rule_id == "CORE-M13-02"} == {"changed", "new", "missing"}
    for lang in ("zh", "en"):
        html = render_report(results, lang)
        assert not any(name in html for name in planted)
    code, out, _ = run(["verify", str(ds), "--manifest", str(written), "--show-paths"], capsys)
    assert "ZhangSan_19800101.edf" in out and "WangWu_19900101.txt" in out  # only on request (D-10 f)


def test_report_cover_shows_hash_and_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ds = _copy(tmp_path)
    _manifest(ds)
    results_file = tmp_path / "r.json"
    run(["check", str(ds), "--out", str(results_file)], capsys)
    results = Results.model_validate_json(results_file.read_bytes())
    assert results.dataset.manifest_hash
    code, _, _ = run(["report", str(results_file), "--lang", "zh,en"], capsys)
    assert code == 0
    english = (tmp_path / "report.en.html").read_text(encoding="utf-8")
    chinese = (tmp_path / "report.zh.html").read_text(encoding="utf-8")
    assert results.dataset.manifest_hash in english and results.dataset.manifest_hash in chinese
    assert "Manifest status" in english and "files match the manifest" in english
    assert "清单状态" in chinese and "文件与清单一致" in chinese
    older = json.loads(results_file.read_text(encoding="utf-8"))
    del older["manifest"]  # a results.json of P1-P3 has no manifest block (C1)
    (tmp_path / "old.json").write_text(json.dumps(older), encoding="utf-8")
    code, _, _ = run(
        ["report", str(tmp_path / "old.json"), "--lang", "en", "--out", str(tmp_path / "old")], capsys
    )
    assert code == 0 and "Manifest status" in (tmp_path / "old" / "report.en.html").read_text(
        encoding="utf-8"
    )


# --- manifest and verify: tool errors and edge cases --------------------------------------------------


def test_unreadable_files_write_no_manifest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ds = _copy(tmp_path)
    lock = _lock(ds / "rec_a.edf")
    try:
        code, out, _ = run(["manifest", str(ds)], capsys)
        result = pipeline.run_manifest(ds)
    finally:
        _unlock(ds / "rec_a.edf", lock)
    assert code == 1 and "cannot be read" in out and "No manifest was written" in out
    assert not (ds / ".neurogrid").exists() and result.data is None  # not even .neurogrid/ is created
    assert result.unreadable == [pseudonym(PurePosixPath("rec_a.edf")) + ".edf"]  # raw folder (A-51, A-70)


def test_manifest_command_refuses_links_folders_and_invalid_sources(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ds = _copy(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (ds / ".neurogrid").mkdir()
    default = ds / ".neurogrid" / "manifest.json"
    dir_link(default, elsewhere)  # a link at the default location is never written through
    code, _, err = run(["manifest", str(ds)], capsys)
    assert code == 2 and "not followed" in err
    if WINDOWS:
        Path(default).rmdir()
    else:
        default.unlink()
    (ds / ".neurogrid").rmdir()
    dir_link(ds / ".neurogrid", elsewhere)  # neither through a linked .neurogrid
    code, _, err = run(["manifest", str(ds)], capsys)
    assert code == 2 and "not followed" in err and list(elsewhere.iterdir()) == []
    if WINDOWS:
        Path(ds / ".neurogrid").rmdir()
    else:
        (ds / ".neurogrid").unlink()
    code, _, err = run(["manifest", str(ds), "--out", str(elsewhere)], capsys)
    assert code == 2 and "folder" in err
    code, _, err = run(["manifest", str(ds), "--out", str(tmp_path / "new") + os.sep], capsys)
    assert code == 2 and "folder" in err and not (tmp_path / "new").exists()
    (ds / ".neurogrid").mkdir()
    (ds / ".neurogrid" / "provenance.yaml").write_text("software: [\n", encoding="utf-8")
    code, _, err = run(["manifest", str(ds)], capsys)
    assert code == 2 and ".neurogrid/provenance.yaml" in err and "line" in err
    code, _, err = run(["check", str(ds), "--out", str(tmp_path / "r.json")], capsys)
    assert code == 2 and ".neurogrid/provenance.yaml" in err  # a control file (C2)
    (ds / ".neurogrid" / "provenance.yaml").unlink()
    (ds / ".neurogrid" / "processing_steps.json").write_text("{", encoding="utf-8")
    code, _, err = run(["manifest", str(ds)], capsys)
    assert code == 2 and "processing_steps.json" in err and not default.exists()
    code, _, _ = run(["check", str(ds), "--out", str(tmp_path / "r.json")], capsys)
    assert code == 1  # an integrity artefact: a finding in check (raw folder: M02-01 decides the exit)
    assert not list(ds.rglob(".manifest.json.*.tmp"))


def test_verify_refuses_unusable_manifests(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ds = _copy(tmp_path)
    code, _, err = run(["verify", str(ds)], capsys)
    assert code == 2 and "--manifest" in err
    code, _, err = run(["verify", str(ds), "--manifest", str(tmp_path / "none.json")], capsys)
    assert code == 2 and "Manifest file not found" in err
    bad = tmp_path / "bad.json"
    for content, text in (
        ("{", "Invalid manifest"),
        ('{"format_version": "9"}', "format version"),
        ("﻿[]", "Invalid manifest"),
    ):
        bad.write_text(content, encoding="utf-8")
        code, _, err = run(["verify", str(ds), "--manifest", str(bad)], capsys)
        assert code == 2 and text in err
    path = _manifest(ds, tmp_path / "m.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["files"][0]["path"] = "../outside.edf"
    data["manifest_hash"] = manifest_hash(data)
    path.write_text(json.dumps(data), encoding="utf-8")
    code, _, err = run(["verify", str(ds), "--manifest", str(path)], capsys)
    assert code == 2 and "files.0.path" in err and "outside" not in err


def test_verify_reports_a_changed_manifest_hash(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ds = _copy(tmp_path)
    path = _manifest(ds)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["software"] = []  # edited without recomputing the hash
    path.write_text(json.dumps(data, indent=4), encoding="utf-8")
    code, out, _ = run(["verify", str(ds), "--manifest", str(path)], capsys)
    assert code == 1 and "does not match the manifest content" in out


def test_verify_lists_are_capped(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ds = _copy(tmp_path)
    path = _manifest(ds, tmp_path / "m.json")
    for index in range(205):
        (ds / f"n{index:03}.txt").write_text("x", encoding="utf-8")
    code, out, _ = run(["verify", str(ds), "--manifest", str(path)], capsys)
    assert code == 1 and "New: 205" in out and "… and 5 more" in out
    assert out.count("\n    - ") == 200


def test_chinese_messages_and_vault_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ds = _copy(tmp_path)
    vault = ds / ".neurogrid" / "vault"
    vault.mkdir(parents=True)
    (vault / "roles.yaml").write_text("roles: []\n", encoding="utf-8")
    code, out, _ = run(["--lang", "zh", "manifest", str(ds)], capsys)
    assert code == 0 and "清单已写入" in out
    (vault / "access.jsonl").write_text('{"event": 1}\n', encoding="utf-8")  # hash-chained separately (A-22)
    (vault / "access.jsonl.lock").write_text("", encoding="utf-8")
    written = ds / ".neurogrid" / "manifest.json"  # next to the vault, itself left out (KONZEPT 2.5)
    code, out, _ = run(["--lang", "zh", "verify", str(ds), "--manifest", str(written)], capsys)
    assert code == 0 and "数据集与清单一致" in out
    (vault / "roles.yaml").write_text("roles: [x]\n", encoding="utf-8")
    code, out, _ = run(["verify", str(ds), "--manifest", str(written)], capsys)
    assert code == 1 and ".neurogrid/vault/roles.yaml" in out


# --- real subprocesses --------------------------------------------------------------------------------


def _subprocess(*args: str) -> subprocess.CompletedProcess[bytes]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "-m", "neurogrid", *args], capture_output=True, env=env, check=False
    )


def test_real_subprocess_manifest_and_verify(tmp_path: Path) -> None:
    ds = _copy(tmp_path, "edf_ok", "数据集 甲")  # a Chinese dataset path with a space
    out = tmp_path / "清单" / "manifest.json"
    written = _subprocess("manifest", str(ds), "--out", str(out))
    assert written.returncode == 0 and out.is_file(), written.stderr
    assert str(tmp_path).encode() not in written.stdout and b"Manifest written to" in written.stdout
    same = _subprocess("verify", str(ds), "--manifest", str(out))
    (ds / "rec_b.edf").unlink()
    changed = _subprocess("verify", str(ds), "--manifest", str(out))
    out.write_text("{", encoding="utf-8")
    invalid = _subprocess("verify", str(ds), "--manifest", str(out))
    assert (same.returncode, changed.returncode, invalid.returncode) == (0, 1, 2)
    assert b"Missing: 1" in changed.stdout


@pytest.mark.skipif(not WINDOWS or shutil.which("powershell.exe") is None, reason="Windows PowerShell 5.1")
def test_windows_powershell_manifest_and_verify(tmp_path: Path) -> None:
    ds = _copy(tmp_path, "edf_ok", "数据 集")
    out = tmp_path / "m.json"

    def powershell(*args: str) -> int:
        quoted = " ".join("'" + arg.replace("'", "''") + "'" for arg in args)
        command = f"& '{sys.executable}' -m neurogrid {quoted}; exit $LASTEXITCODE"
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            check=False,
        )
        return result.returncode

    assert powershell("manifest", str(ds), "--out", str(out)) == 0 and out.is_file()
    assert powershell("verify", str(ds), "--manifest", str(out)) == 0
    (ds / "new.txt").write_text("x", encoding="utf-8")
    assert powershell("verify", str(ds), "--manifest", str(out)) == 1
    assert powershell("verify", str(ds), "--manifest", str(tmp_path / "missing.json")) == 2
