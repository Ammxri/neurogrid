"""The comparison of two check runs, `neurogrid diff` (NG-F15, CLI-07, UF-02; A-33, A-97).

New, fixed, removed and changed findings are separated by their stable key; the measured value is compared
after rounding to 6 significant digits; a change of the effective severity is a change; exit code 1 only for a
key that became a counted error finding; placeholder findings are counted, not compared; findings of consent
rules are counted per rule and category, never listed (D-17 option B); results.json of earlier phases load
(C1); the same inputs give byte-identical JSON (NG-N03)."""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from conftest import documented_config  # type: ignore[import-not-found]
from neurogrid import diff, pipeline
from neurogrid.kernel import canonical
from neurogrid.kernel.errors import NeuroGridError
from neurogrid.kernel.findings import (
    Finding,
    PassedCount,
    Phase,
    Severity,
    SourceStatus,
    Status,
    finding_key,
)
from neurogrid.model.diff import DiffResult
from neurogrid.model.results import Results, RuleInfo
from neurogrid.report.texts import translator

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
SRC = Path(__file__).parent.parent.parent / "src" / "neurogrid"
AS_OF = date(2026, 10, 11)


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Results]:
    """edf_ok checked plainly and with --strict (CORE-M13-01: a missing manifest becomes an error)."""
    tmp = tmp_path_factory.mktemp("diff")
    config = documented_config(tmp)
    found = {}
    for name, strict in (("plain", False), ("strict", True)):
        options = pipeline.CheckOptions(config_path=config, as_of=AS_OF, strict=strict, work_base=tmp)
        found[name] = pipeline.run_check(FIX / "edf_ok", options)
    return found


def _copy(results: Results) -> Results:
    return results.model_copy(deep=True)


def _finding(base: Finding, **changes: Any) -> Finding:
    """A finding like ``base`` with other fields; the key follows rule, object and sub-key (A-09)."""
    finding = base.model_copy(update=changes, deep=True)
    if {"rule_id", "object", "subkey"} & set(changes) and "key" not in changes:
        finding.key = finding_key(finding.rule_id, finding.object, finding.subkey)
    return finding


def _pick(results: Results, rule_id: str, status: Status | None = None) -> Finding:
    return next(f for f in results.findings if f.rule_id == rule_id and status in (None, f.status))


def _keys(result: DiffResult, category: str) -> set[str]:
    return {entry.key for entry in getattr(result.findings, category)}


def test_new_fixed_changed_are_separated(runs: dict[str, Results]) -> None:
    """KONZEPT DoD P9: `diff` lists new, fixed and changed findings separately (and removed ones apart from
    the fixed ones); every other key is counted as unchanged."""
    old = runs["plain"]
    new = _copy(old)
    fixed = _pick(new, "CORE-M04-02", Status.FAILED)  # passes for its object in the new run
    removed = _pick(new, "CORE-M05-02")  # no passed result: rule not loaded or object gone
    changed = _pick(new, "CORE-M06-01")
    added = _finding(fixed, object="rec-0000beef")
    new.findings = [f for f in new.findings if f.key not in (fixed.key, removed.key)]
    new.findings.append(added)
    new.passed.append(PassedCount(rule_id=fixed.rule_id, object=fixed.object, count=1))
    new.findings[new.findings.index(changed)] = _finding(changed, status=Status.FAILED, measured_value=2.5)

    result = diff.compare(old, new)
    assert _keys(result, "new") == {added.key}
    assert _keys(result, "fixed") == {fixed.key}
    assert _keys(result, "removed") == {removed.key}
    assert _keys(result, "changed") == {changed.key}
    (change,) = result.findings.changed
    assert (change.old.status, change.new.status) == (Status.NOT_CHECKABLE, Status.FAILED)
    assert (change.old.measured_value, change.new.measured_value) == (None, 2.5)
    assert (result.findings.fixed[0].status, result.findings.fixed[0].object) == (Status.FAILED, fixed.object)
    summary = result.summary
    assert (summary.new, summary.fixed, summary.removed, summary.changed) == (1, 1, 1, 1)
    assert summary.unchanged == len(old.findings) - 3
    assert (summary.new_errors, summary.exit_code) == (0, 0)  # warnings only
    assert result.aggregated == [] and result.rules.added == result.rules.removed == []
    # the reverse comparison: the fixed finding is new again, the new one removed (its object has no pass)
    back = diff.compare(new, old)
    assert _keys(back, "new") == {fixed.key, removed.key} and _keys(back, "removed") == {added.key}


def test_removed_is_told_from_fixed_per_object(runs: dict[str, Results]) -> None:
    old = runs["plain"]
    a, b = [f for f in old.findings if f.rule_id == "CORE-M05-01"]
    new = _copy(old)
    new.findings = [f for f in new.findings if f.rule_id != "CORE-M05-01"]
    new.passed.append(PassedCount(rule_id="CORE-M05-01", object=a.object, count=2))
    new.passed.append(PassedCount(rule_id="CORE-M04-02", object=b.object, count=1))  # another rule's pass
    result = diff.compare(old, new)
    assert _keys(result, "fixed") == {a.key} and _keys(result, "removed") == {b.key}


def test_measured_values_are_compared_after_rounding(runs: dict[str, Results]) -> None:
    old = _copy(runs["plain"])
    base = _pick(old, "CORE-M06-01")
    pairs = [
        (1.0000001, 1.0000002, False),
        ({"a": [3.14159265, 2]}, {"a": [3.14159271, 2]}, False),
        (1.0, 1.1, True),
        ({"documented": 0}, {"documented": 1}, True),
        (8, "8", True),
        (None, 0.0, True),
    ]
    old.findings, new_findings = [], []
    for index, (before, after, _differs) in enumerate(pairs):
        finding = _finding(base, subkey=f"case{index}", measured_value=before)
        old.findings.append(finding)
        new_findings.append(_finding(finding, measured_value=after))
    new = _copy(old)
    new.findings = new_findings
    result = diff.compare(old, new)
    expected = {old.findings[i].key for i, (_old, _new, differs) in enumerate(pairs) if differs}
    assert _keys(result, "changed") == expected and result.summary.unchanged == 2
    assert diff._value(float("nan")) is None and diff._value([float("inf"), 0.1234567]) == [None, 0.123457]
    shown = {c.key: c.new.measured_value for c in result.findings.changed}
    assert shown[old.findings[2].key] == 1.1


def test_severity_change_is_a_change_and_decides_the_exit_code(runs: dict[str, Results]) -> None:
    """--strict turns CORE-M13-01 into an error: listed as changed (A-97 adds the severity to A-33), and it is
    a new counted error finding (exit 1); the other way round nothing becomes an error (exit 0)."""
    result = diff.compare(runs["plain"], runs["strict"])
    (change,) = result.findings.changed
    assert change.rule_id == "CORE-M13-01" and change.old.status is change.new.status is Status.FAILED
    assert (change.old.severity, change.new.severity) == (Severity.WARNING, Severity.ERROR)
    assert (result.summary.changed, result.summary.new_errors, result.summary.exit_code) == (1, 1, 1)
    assert result.old.config_sha256 == result.new.config_sha256  # strict is no part of the configuration
    back = diff.compare(runs["strict"], runs["plain"])
    assert (back.summary.changed, back.summary.new_errors, back.summary.exit_code) == (1, 0, 0)
    same = diff.compare(runs["plain"], runs["plain"])
    assert same.summary.unchanged == len(runs["plain"].findings) and same.summary.exit_code == 0


@pytest.mark.parametrize(
    ("before", "after", "exit_code"),
    [
        (None, (Severity.ERROR, Status.FAILED), 1),  # a new error finding
        (None, (Severity.ERROR, Status.EVIDENCE_OPEN), 1),  # open evidence of an error rule counts (A-16)
        (None, (Severity.WARNING, Status.FAILED), 0),
        (None, (Severity.ERROR, Status.NOT_CHECKABLE), 0),
        (None, (Severity.ERROR, Status.EXCEPTED), 0),  # a justified exception is not counted
        ((Severity.ERROR, Status.FAILED), (Severity.ERROR, Status.FAILED), 0),  # an old error stays
        (
            (Severity.ERROR, Status.FAILED),
            (Severity.ERROR, Status.EVIDENCE_OPEN),
            0,
        ),  # changed, counted before
        ((Severity.ERROR, Status.NOT_APPLICABLE), (Severity.ERROR, Status.FAILED), 1),
        ((Severity.ERROR, Status.EXCEPTED), (Severity.ERROR, Status.FAILED), 1),  # the exception ran out
        ((Severity.INFO, Status.FAILED), (Severity.ERROR, Status.FAILED), 1),
        ((Severity.ERROR, Status.FAILED), None, 0),  # gone
    ],
)
def test_exit_rule(
    runs: dict[str, Results],
    before: tuple[Severity, Status] | None,
    after: tuple[Severity, Status] | None,
    exit_code: int,
) -> None:
    base = _pick(runs["plain"], "CORE-M06-01")
    old, new = _copy(runs["plain"]), _copy(runs["plain"])
    old.findings = [] if before is None else [_finding(base, severity=before[0], status=before[1])]
    new.findings = [] if after is None else [_finding(base, severity=after[0], status=after[1])]
    result = diff.compare(old, new)
    assert (result.summary.exit_code, result.summary.new_errors) == (exit_code, exit_code)


def test_placeholder_findings_are_counted_not_compared(runs: dict[str, Results]) -> None:
    """A-41: findings of placeholder packs never count; diff counts their keys in placeholder_skipped and
    lists none of them, an error among them changes no exit code."""
    base = _pick(runs["plain"], "CORE-M06-01")
    placeholder = {
        "source_status": SourceStatus.PLACEHOLDER,
        "rule_id": "DRAFT-X-01",
        "rulepack": "draft",
    }
    both = _finding(base, **placeholder, severity=Severity.ERROR, status=Status.FAILED)
    only_new = _finding(both, object="rec-feedf00d")
    old, new = _copy(runs["plain"]), _copy(runs["plain"])
    old.findings.append(both)
    new.findings += [_finding(both, status=Status.NOT_CHECKABLE), only_new]
    result = diff.compare(old, new)
    assert result.summary.placeholder_skipped == 2
    assert result.summary.unchanged == len(runs["plain"].findings) and result.summary.exit_code == 0
    listed = canonical.dumps(result.findings).decode("utf-8")
    assert "DRAFT-X-01" not in listed and "feedf00d" not in listed


def _with_consent_rule(results: Results, rule_id: str) -> Results:
    """Results whose rules hold ``rule_id`` on the consent check (a pack of one's own, like LAB-ACC-001)."""
    copied = _copy(results)
    if all(rule.id != rule_id for rule in copied.rules):
        template = next(rule for rule in copied.rules if rule.check == "consent.covered")
        copied.rules.append(RuleInfo(**{**template.model_dump(), "id": rule_id, "rulepack": "lab"}))
    return copied


def test_consent_rules_are_counted_per_rule_never_listed(runs: dict[str, Results]) -> None:
    """D-17 option B (owner answer 4 of P9): findings of rules on a consent.* check are only counted per rule
    and category in text and JSON; the exit rule still sees each key."""
    old = _with_consent_rule(runs["plain"], "LAB-ACC-001")
    template = Finding(
        key=finding_key("CORE-M14-01", "sub-plant7731", "training"),
        rule_id="CORE-M14-01",
        rulepack="core",
        rulepack_version="0.2.0",
        source_status=SourceStatus.FINAL,
        clause="",
        phase=Phase.ACCESS,
        severity=Severity.ERROR,
        status=Status.FAILED,
        object="sub-plant7731",
        subkey="training",
        message_key="check.consent.covered",
        reason="consent.missing",
        measured_value=3,
    )
    gone = _finding(template, object="sub-plant7732")
    turned = _finding(template, object="sub-plant7733", status=Status.NOT_CHECKABLE)
    lab = _finding(template, rule_id="LAB-ACC-001", rulepack="lab", object="sub-plant7734")
    old.findings += [gone, turned]
    new = _with_consent_rule(runs["plain"], "LAB-ACC-001")
    new.findings += [_finding(template), _finding(template, object="sub-plant7735"), lab]
    new.findings.append(_finding(turned, status=Status.FAILED, measured_value=4))
    new.passed.append(PassedCount(rule_id="CORE-M14-01", object=gone.object, count=1))
    result = diff.compare(old, new)
    counts = [(c.rule_id, c.category, c.count) for c in result.aggregated]
    assert counts == [
        ("CORE-M14-01", "new", 2),
        ("CORE-M14-01", "fixed", 1),
        ("CORE-M14-01", "changed", 1),
        ("LAB-ACC-001", "new", 1),
    ]
    summary = result.summary
    assert (summary.new, summary.fixed, summary.changed, summary.new_errors, summary.exit_code) == (
        3,
        1,
        1,
        4,
        1,
    )
    assert not any(getattr(result.findings, category) for category in ("new", "fixed", "removed", "changed"))
    output = canonical.dumps(result).decode("utf-8") + "\n".join(diff.text_lines(result, "zh"))
    output += "\n".join(diff.text_lines(result, "en"))
    assert "plant77" not in output and "consent.missing" not in output
    for finding in (template, gone, turned, lab):
        assert finding.key not in output
    tr = translator("en").t
    assert tr("cli.diff.aggregated", rule="CORE-M14-01", category="new", count=2) in output


def _older(results: Results, phase: str) -> Results:
    """results.json of an earlier phase: P5 has no consent block (P6), P1-P3 no evidence, manifest, AI and
    duplicate blocks either (C1)."""
    data = json.loads(canonical.dumps(results))
    data.pop("consent", None)
    data["config"].pop("consents_sha256", None)
    if phase == "P1-P3":
        for name in ("evidence", "manifest", "ai", "duplicates"):
            data.pop(name, None)
        data["config"].pop("evidence_sha256", None)
        data["summary"].pop("open_evidence", None)
    return Results.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("phase", ["P5", "P1-P3"])
def test_results_of_earlier_phases_load_and_compare(
    runs: dict[str, Results], phase: str, tmp_path: Path
) -> None:
    path = tmp_path / "old.json"
    path.write_bytes(canonical.dumps(_older(runs["plain"], phase)))
    old = diff.load(str(path), "OLD")
    result = diff.compare(old, runs["strict"])
    assert result.summary.changed == 1 and result.summary.exit_code == 1


def test_same_inputs_give_byte_identical_json(runs: dict[str, Results], tmp_path: Path) -> None:
    files = {}
    for name in ("plain", "strict"):
        files[name] = tmp_path / f"{name}.json"
        files[name].write_bytes(canonical.dumps(runs[name]))
    first = canonical.dumps(diff.compare(runs["plain"], runs["strict"]))
    again = canonical.dumps(
        diff.compare(diff.load(str(files["plain"]), "OLD"), diff.load(str(files["strict"]), "NEW"))
    )
    assert first == again and first.endswith(b"}\n") and b"\r" not in first
    parsed = DiffResult.model_validate_json(first)
    assert canonical.dumps(parsed) == first
    assert parsed.disclaimer.zh and parsed.disclaimer.en and parsed.tool.name == "neurogrid"
    for text in (str(tmp_path), tmp_path.as_posix(), str(Path.home())):  # no path of the inputs (A-51)
        assert text not in first.decode("utf-8")


def test_lists_follow_the_order_of_results_json(runs: dict[str, Results]) -> None:
    """A-61: severity error > warning > info, then rule, object, sub-key."""
    base = _pick(runs["plain"], "CORE-M06-01")
    old = _copy(runs["plain"])
    old.findings = []
    new = _copy(old)
    new.findings = [
        _finding(base, rule_id="Z-1", severity=Severity.INFO, object="a"),
        _finding(base, rule_id="B-1", severity=Severity.WARNING, object="b", subkey="y"),
        _finding(base, rule_id="B-1", severity=Severity.WARNING, object="b", subkey="x"),
        _finding(base, rule_id="B-1", severity=Severity.WARNING, object="a"),
        _finding(base, rule_id="C-1", severity=Severity.ERROR, object="z"),
    ]
    result = diff.compare(old, new)
    shown = [(e.rule_id, e.object, e.subkey) for e in result.findings.new]
    assert shown == [
        ("C-1", "z", None),
        ("B-1", "a", None),
        ("B-1", "b", "x"),
        ("B-1", "b", "y"),
        ("Z-1", "a", None),
    ]


def test_rule_and_run_differences(runs: dict[str, Results]) -> None:
    old = _copy(runs["plain"])
    new = _copy(runs["plain"])
    gone = new.rules.pop()
    new.rules.append(RuleInfo(**{**gone.model_dump(), "id": "LAB-NEW-001"}))
    new.dataset.name = "Other study"
    new.config.canonical_sha256 = "0" * 64
    result = diff.compare(old, new)
    assert result.rules.added == ["LAB-NEW-001"] and result.rules.removed == [gone.id]
    assert result.new.dataset.name == "Other study" and result.old.dataset.name is None
    text = diff.text_lines(result, "en")
    tr = translator("en").t
    for key in ("cli.diff.dataset_differs", "cli.diff.config_changed"):
        assert tr(key) in text, key
    assert tr("cli.diff.rules", added="LAB-NEW-001", removed=gone.id) in text
    same = diff.text_lines(diff.compare(old, old), "en")
    assert tr("cli.diff.config_unchanged") in same and tr("cli.diff.dataset_differs") not in same


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_text_has_every_part_in_the_language(runs: dict[str, Results], lang: str) -> None:
    result = diff.compare(runs["plain"], runs["strict"])
    lines = diff.text_lines(result, lang)
    tr = translator(lang).t
    assert lines[0] == tr("cli.diff.title")
    for category in ("new", "fixed", "removed", "changed"):
        count = 1 if category == "changed" else 0
        assert tr(f"cli.diff.section.{category}", count=count) in lines
    assert lines[-1] == tr("cli.diff.exit_new_errors", count=1)
    (line,) = [line for line in lines if "CORE-M13-01" in line]
    warning, error = tr("severity.warning"), tr("severity.error")
    assert f"{warning} → {error}" in line and tr("status.failed") in line and "false" in line
    reverse = diff.text_lines(diff.compare(runs["strict"], runs["plain"]), lang)
    assert reverse[-1] == tr("cli.diff.exit_no_new_errors")


def test_text_lists_at_most_200_per_category_and_cleans_foreign_text(runs: dict[str, Results]) -> None:
    base = _pick(runs["plain"], "CORE-M06-01")
    old = _copy(runs["plain"])
    old.findings = []
    new = _copy(old)
    new.findings = [_finding(base, object=f"rec-{n:08x}") for n in range(250)]
    new.findings.append(_finding(base, object="rec-\x1b[31mred\x07", measured_value="x" * 500, reason=None))
    result = diff.compare(old, new)
    assert len(result.findings.new) == 251  # the JSON lists every finding
    lines = diff.text_lines(result, "en")
    listed = [line for line in lines if line.startswith("  - ")]
    assert len(listed) == diff.MAX_LISTED
    assert translator("en").t("cli.diff.more", count=51) in lines
    assert not [line for line in lines if any(not ch.isprintable() for ch in line)]
    head = diff.text_lines(diff.compare(old, _replace(new, new.findings[-1:])), "en")
    (line,) = [line for line in head if line.startswith("  - ")]
    assert "rec-[31mred" in line and len(line) < 600 and "x" * 199 + "…" in line


def _replace(results: Results, findings: list[Finding]) -> Results:
    copied = _copy(results)
    copied.findings = findings
    return copied


@pytest.mark.parametrize(
    ("write", "problem"),
    [
        (None, "missing"),
        (lambda p: p.write_text("{", encoding="utf-8"), "not JSON"),
        (lambda p: p.write_text('{"schema_version": "1.0"}', encoding="utf-8"), "not results"),
        (lambda p: p.mkdir(), "a folder"),
        (lambda p: p.write_bytes(b"\xff\xfe{}"), "not UTF-8"),
    ],
)
def test_unreadable_inputs_are_one_error_naming_the_argument(
    tmp_path: Path, write: Callable[[Path], Any] | None, problem: str
) -> None:
    path = tmp_path / "results.json"
    if write is not None:
        write(path)
    for label in ("OLD", "NEW"):
        with pytest.raises(NeuroGridError) as info:
            diff.load(str(path), label)
        assert (info.value.message_key, info.value.params) == ("errors.diff.results_invalid", {"file": label})


def test_too_large_input_is_refused_before_reading(
    tmp_path: Path, runs: dict[str, Results], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "results.json"
    path.write_bytes(canonical.dumps(runs["plain"]))
    assert diff.load(str(path), "OLD").findings == runs["plain"].findings
    monkeypatch.setattr(diff, "MAX_RESULTS_BYTES", 100)
    with pytest.raises(NeuroGridError) as info:
        diff.load(str(path), "OLD")
    assert info.value.message_key == "errors.diff.results_invalid"


def test_diff_imports_only_kernel_model_and_the_language_tables() -> None:
    """ARC-01 (p9 decisions 1): diff.py imports the kernel, the models and report.texts (translations), and
    the package version; model/diff.py imports only the kernel and the models."""
    allowed = {
        "diff.py": ("neurogrid.kernel", "neurogrid.model", "neurogrid.report.texts"),
        "model/diff.py": ("neurogrid.kernel", "neurogrid.model"),
    }
    for name, prefixes in allowed.items():
        tree = ast.parse((SRC / name).read_text(encoding="utf-8"))
        modules = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        modules |= {
            alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
        }
        own = {m for m in modules if m.split(".")[0] == "neurogrid"}
        outside = sorted(m for m in own if m != "neurogrid" and not m.startswith(prefixes))
        assert outside == [], (name, outside)
        if name == "diff.py":  # `from neurogrid import __version__` is the one import of the package itself
            package = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "neurogrid"]
            assert [alias.name for node in package for alias in node.names] == ["__version__"]
