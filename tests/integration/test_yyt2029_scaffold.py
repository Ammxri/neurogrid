"""The built-in placeholder scaffold of P6 (RP-10, NG-F11, A-41, A-92; DoD P6 a-d, POS-01, NG-N03).

The pack loads only with --allow-draft-rulepacks (exit 2 without it, by name, by path and from [check]
rulepacks), the report shows the placeholder banner, the pack gets no coverage percentage, and its findings
change neither the exit code nor a traffic light, even though its one rule is an error rule that fails on
edf_lowrate (256 Hz) and edf_mixed (mixed rates). No sentence says that a dataset passes a placeholder pack:
the console names only the evaluated packs, and with placeholder packs alone the console and the report say
that nothing was evaluated. The pack is named once below (PACK, RULE), so every mention of the norm in the
repository stays a reviewed line (tests/unit/test_norm_independence.py)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import sys
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Any

import pypdf
import pytest

from conftest import documented_config  # type: ignore[import-not-found]
from neurogrid import pipeline
from neurogrid.cli import main
from neurogrid.kernel import canonical
from neurogrid.kernel.errors import RulepackError
from neurogrid.kernel.findings import Light, Phase, Severity, SourceStatus, Status
from neurogrid.model.results import Results
from neurogrid.report import output
from neurogrid.report.output import html_document, write_reports
from neurogrid.report.render import render_report
from neurogrid.report.texts import translator

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = date(2026, 10, 11)
PACK = "yyt2029"
RULE = "YYT2029-ACQ-001"
FLAG = "--allow-draft-rulepacks"
ONLY_PACK = f'[check]\nrulepacks = ["{PACK}"]\n'


def _pack_bytes() -> bytes:
    return resources.files("neurogrid.rulepacks").joinpath(f"{PACK}.yaml").read_bytes()


def _run(folder: str, config: Path | None, *, with_pack: bool) -> Results:
    return pipeline.run_check(
        FIX / folder,
        pipeline.CheckOptions(
            rulepacks=(PACK,) if with_pack else (),
            allow_draft_rulepacks=with_pack,
            config_path=config,
            as_of=AS_OF,
        ),
    )


def cli(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


@pytest.fixture(scope="module")
def config(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The documented metadata of the raw fixtures: core gives no error there, so exit 0 unless counted."""
    return documented_config(tmp_path_factory.mktemp("documented"))


@pytest.fixture(scope="module")
def runs(config: Path) -> dict[tuple[str, bool], Results]:
    """(fixture, with the scaffold) -> results; the core signal sample costs seconds, so the runs are
    shared."""
    return {
        (folder, with_pack): _run(folder, config, with_pack=with_pack)
        for folder in ("edf_lowrate", "edf_mixed")
        for with_pack in (False, True)
    }


@pytest.fixture(scope="module")
def only_placeholder(tmp_path_factory: pytest.TempPathFactory) -> Results:
    folder = tmp_path_factory.mktemp("only")
    toml = documented_config(folder, ONLY_PACK)
    return pipeline.run_check(
        FIX / "edf_lowrate",
        pipeline.CheckOptions(config_path=toml, allow_draft_rulepacks=True, as_of=AS_OF),
    )


# --- loading (NG-F11, RP-10) --------------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["cli_name", "cli_path", "toml_name", "toml_path"])
def test_builtin_placeholder_pack_loads_with_flag(source: str, tmp_path: Path) -> None:
    """By built-in name and by path, from the command line and from [check] rulepacks (paths in the toml are
    relative to its folder, A-66): the pack in results.json is the shipped file."""
    pack_file = tmp_path / "packs" / "draft.yaml"
    pack_file.parent.mkdir()
    pack_file.write_bytes(_pack_bytes())
    refs: tuple[str, ...] = ()
    extra = ""
    if source == "cli_name":
        refs = (PACK,)
    elif source == "cli_path":
        refs = (str(pack_file),)
    elif source == "toml_name":
        extra = ONLY_PACK
    else:
        extra = '[check]\nrulepacks = ["core", "packs/draft.yaml"]\n'
    toml = documented_config(tmp_path, extra)
    results = pipeline.run_check(
        FIX / "edf_ok",
        pipeline.CheckOptions(rulepacks=refs, config_path=toml, allow_draft_rulepacks=True, as_of=AS_OF),
    )
    (entry,) = [p for p in results.rulepacks if p.name == PACK]
    assert entry.version == "0.2.0-draft" and entry.source_status is SourceStatus.PLACEHOLDER
    assert entry.norm is True and entry.sha256 == hashlib.sha256(_pack_bytes()).hexdigest()
    (rule,) = [r for r in results.rules if r.rulepack == PACK]
    assert rule.id == RULE and rule.clause == "TBD" and rule.source_status is SourceStatus.PLACEHOLDER
    assert [p.name for p in results.rulepacks] == ([PACK] if source == "toml_name" else ["core", PACK])


@pytest.mark.parametrize("lang", ["en", "zh"])
@pytest.mark.parametrize("source", ["cli", "toml"])
def test_cli_placeholder_without_flag_exits_2(
    source: str, lang: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD P6 a: without the switch exit 2 with the message naming it, before any data work: no results."""
    extra = ONLY_PACK if source == "toml" else ""
    args = ["--lang", lang, "check", str(FIX / "edf_ok"), "--out", str(tmp_path / "results.json")]
    args += ["--config", str(documented_config(tmp_path, extra))]
    if source == "cli":
        args += ["--rulepack", PACK]
    code, out, err = cli(args, capsys)
    expected = translator(lang).t("errors.rulepack.placeholder_needs_flag", rulepack=PACK)
    assert code == 2 and expected in err and FLAG in err, (code, err)
    assert not (tmp_path / "results.json").exists() and "Traceback" not in err
    with pytest.raises(RulepackError) as info:
        pipeline.run_check(FIX / "edf_ok", pipeline.CheckOptions(rulepacks=(PACK,), as_of=AS_OF))
    assert info.value.message_key == "rulepack.placeholder_needs_flag"


def test_placeholder_without_flag_exits_2_in_a_real_process(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    base = [sys.executable, "-m", "neurogrid", "check", str(FIX / "edf_ok"), "--rulepack", PACK]
    target = tmp_path / "results.json"
    refused = subprocess.run([*base, "--out", str(target)], capture_output=True, env=env, check=False)
    assert refused.returncode == 2 and FLAG in refused.stderr.decode("utf-8") and not target.exists()
    config = str(documented_config(tmp_path))
    loaded = subprocess.run(
        [*base, FLAG, "--out", str(target), "--config", config, "--as-of", "2026-10-11"],
        capture_output=True,
        env=env,
        check=False,
    )
    assert loaded.returncode == 0 and target.is_file(), loaded.stderr.decode("utf-8")


# --- no influence on exit code, traffic light, coverage (DoD P6 c, d) ---------------------------------------


@pytest.mark.parametrize("folder", ["edf_lowrate", "edf_mixed"])
def test_placeholder_pack_changes_neither_exit_nor_lights(
    folder: str, runs: dict[tuple[str, bool], Results]
) -> None:
    without, loaded = runs[(folder, False)], runs[(folder, True)]
    placeholder = [f for f in loaded.findings if f.rule_id == RULE]
    assert Status.FAILED in {f.status for f in placeholder}  # an error rule that fails: the worst case
    assert all(f.severity is Severity.ERROR for f in placeholder)
    assert all(f.source_status is SourceStatus.PLACEHOLDER for f in placeholder)
    summary = loaded.summary.model_dump(exclude={"coverage"})
    assert summary == without.summary.model_dump(exclude={"coverage"})
    assert loaded.summary.exit_code == without.summary.exit_code == 0
    assert loaded.summary.coverage == {**without.summary.coverage, PACK: "n/a"}
    counted = [f.model_dump() for f in loaded.findings if f.rule_id != RULE]
    assert counted == [f.model_dump() for f in without.findings]
    assert [p.model_dump() for p in loaded.passed if p.rule_id != RULE] == [
        p.model_dump() for p in without.passed
    ]


def test_only_placeholder_pack_gives_grey_lights_and_exit_0(
    only_placeholder: Results, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results = only_placeholder
    assert [p.name for p in results.rulepacks] == [PACK]
    assert [f.status for f in results.findings if f.rule_id == RULE] == [Status.FAILED]
    assert results.summary.exit_code == 0 and results.summary.coverage == {PACK: "n/a"}
    assert set(results.summary.phases) == set(Phase)
    assert all(p.light is Light.GREY for p in results.summary.phases.values())
    assert results.summary.errors == results.summary.warnings == results.summary.open_evidence == 0
    toml = documented_config(tmp_path, ONLY_PACK)
    out_file = tmp_path / "results.json"
    args = ["check", str(FIX / "edf_lowrate"), FLAG, "--config", str(toml), "--out", str(out_file)]
    code, _out, _err = cli([*args, "--as-of", "2026-10-11"], capsys)
    assert code == 0 and json.loads(out_file.read_text(encoding="utf-8"))["summary"]["exit_code"] == 0


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_coverage_of_placeholder_pack_is_na_without_percent(
    lang: str, runs: dict[tuple[str, bool], Results]
) -> None:
    results = runs[("edf_lowrate", True)]
    assert results.summary.coverage[PACK] == "n/a"
    assert json.loads(canonical.dumps(results))["summary"]["coverage"][PACK] == "n/a"
    html = render_report(results, lang)
    row = re.search(rf'<tr><td>{PACK}</td><td class="own">(.*?)</td></tr>', html)
    assert (
        row is not None and row.group(1) == translator(lang).t("report.value.na") and "%" not in row.group(1)
    )


# --- banner and the not-evaluated section (DoD P6 b) --------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_report_banner_with_builtin_placeholder(lang: str, runs: dict[tuple[str, bool], Results]) -> None:
    tr = translator(lang).t
    html = render_report(runs[("edf_lowrate", True)], lang)
    assert html.count(tr("report.placeholder_banner")) == 1
    findings = html[html.index('id="findings"') : html.index('id="metrics"')]
    section = findings[findings.index(tr("report.label.placeholder_findings")) :]
    assert f'data-rule="{RULE}"' in section
    rows = re.findall(r'<tr data-key="[^"]*">(.*?)</tr>', section, flags=re.S)
    assert rows and all(tr("report.value.placeholder_clause") in row for row in rows)
    assert all(tr("report.value.placeholder_status") in row for row in rows)
    appendix = html[html.index('id="appendix"') :]
    row = re.search(rf'<tr data-rule="{RULE}">(.*?)</tr>', appendix, flags=re.S)
    assert row is not None and tr("report.value.placeholder_status") in row.group(1)
    # placeholder checks are not counted as passed either (A-41)
    passed = f"{tr('report.label.passed_checks')}: "
    without = render_report(runs[("edf_lowrate", False)], lang)
    assert passed in html and _after(html, passed) == _after(without, passed)
    assert tr("report.placeholder_banner") not in without


def _after(html: str, label: str) -> str:
    start = html.index(label) + len(label)
    return html[start : html.index("<", start)]


@pytest.mark.pdf
def test_pdf_banner_with_builtin_placeholder(runs: dict[tuple[str, bool], Results], tmp_path: Path) -> None:
    """The PDF QA gate requires the banner exactly once (A-41, output.pdf_expectation); a written PDF
    passed it."""
    results = runs[("edf_lowrate", True)]
    for lang in ("zh", "en"):
        banner = translator(lang).t("report.placeholder_banner")
        expect = output.pdf_expectation(results, lang, html_document(results, lang))
        assert banner in expect.once
    paths = write_reports(results, ["zh", "en"], ["pdf"], tmp_path, environ=os.environ)
    for path, lang in zip(paths, ("zh", "en"), strict=True):
        pages = [p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(path.read_bytes())).pages]
        text = re.sub(r"\s+", "", "".join(pages))
        assert re.sub(r"\s+", "", translator(lang).t("report.placeholder_banner")) in text, lang


# --- wording (POS-01, A-57) ---------------------------------------------------------------------------------


def test_console_names_only_evaluated_packs(
    config: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tr = translator("en").t
    args = ["check", str(FIX / "edf_lowrate"), "--rulepack", PACK, FLAG, "--config", str(config)]
    code, out, _err = cli([*args, "--out", str(tmp_path / "r.json"), "--as-of", "2026-10-11"], capsys)
    assert code == 0
    assert tr("cli.check.passes", packs="core") in out and PACK not in out.split(tr("disclaimer"))[0]
    assert tr("cli.check.placeholder") in out
    assert tr("cli.check.none_evaluated", packs=PACK) not in out
    # a failing run names the evaluated packs only as well
    raw = ["check", str(FIX / "edf_lowrate"), "--rulepack", PACK, FLAG, "--out", str(tmp_path / "raw.json")]
    code, out, _err = cli(raw, capsys)
    assert code == 1 and tr("cli.check.fails", packs="core") in out and tr("cli.check.placeholder") in out


def test_cli_prints_placeholder_notice_only_with_a_placeholder_pack(
    config: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tr = translator("en").t
    args = ["check", str(FIX / "edf_ok"), "--config", str(config), "--out", str(tmp_path / "r.json")]
    code, out, _err = cli(args, capsys)
    assert (
        code == 0 and tr("cli.check.placeholder") not in out and tr("cli.check.passes", packs="core") in out
    )


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_only_placeholder_console_and_overall_sentence(
    lang: str, only_placeholder: Results, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tr = translator(lang).t
    toml = documented_config(tmp_path, ONLY_PACK)
    args = ["--lang", lang, "check", str(FIX / "edf_lowrate"), FLAG, "--config", str(toml)]
    code, out, _err = cli([*args, "--out", str(tmp_path / "r.json")], capsys)
    assert (
        code == 0 and tr("cli.check.none_evaluated", packs=PACK) in out and tr("cli.check.placeholder") in out
    )
    assert tr("cli.check.passes", packs=PACK) not in out and tr("cli.check.fails", packs=PACK) not in out
    html = render_report(only_placeholder, lang)
    summary = html[html.index('id="summary"') : html.index('id="findings"')]
    assert tr("report.text.overall_none_evaluated") in summary
    for key in ("report.text.overall_passes", "report.text.overall_passes_warnings"):
        assert tr(key, warnings=0) not in summary


def test_overall_sentence_is_unchanged_with_an_evaluated_pack(runs: dict[tuple[str, bool], Results]) -> None:
    """Negative case: next to core the overall sentence stays the P5 one (reviewed zh texts unchanged)."""
    for lang in ("en", "zh"):
        tr = translator(lang).t
        loaded = render_report(runs[("edf_lowrate", True)], lang)
        without = render_report(runs[("edf_lowrate", False)], lang)
        sentence = _overall(without)
        assert sentence == _overall(loaded) and sentence != tr("report.text.overall_none_evaluated")


def _overall(html: str) -> str:
    match = re.search(r'<p class="overall">(.*?)</p>', html, flags=re.S)
    assert match is not None
    return match.group(1)


# --- determinism (NG-N03) -----------------------------------------------------------------------------------


def test_two_runs_with_placeholder_pack_are_byte_identical(
    config: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    written = []
    for name, jobs in (("a.json", "1"), ("b.json", "4")):
        target = tmp_path / name
        args = ["check", str(FIX / "edf_mixed"), "--rulepack", PACK, FLAG, "--config", str(config)]
        code, _out, _err = cli([*args, "--out", str(target), "--as-of", "2026-10-11", "--jobs", jobs], capsys)
        assert code == 0
        written.append(target.read_bytes())
    assert written[0] == written[1]
    data: dict[str, Any] = json.loads(written[0])
    assert [p["name"] for p in data["rulepacks"]] == ["core", PACK]
