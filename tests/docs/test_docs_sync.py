"""The documentation states what the code does (TECH-06, POS-02, CON-05, D-03): pages are checked against the
registry, the rule packs, the configuration model, the CLI, the schemas and the language tables."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import typing
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest
import typer
from pydantic import BaseModel

from neurogrid import config as config_module
from neurogrid.checks.registry import REGISTRY
from neurogrid.cli import app
from neurogrid.config import Config, MetadataDefaults
from neurogrid.kernel.findings import Finding, Light, Phase, Severity, Status, Verification
from neurogrid.kernel.rules import EVIDENCE_CHECK, Bound, Rule, Rulepack, is_true, load_rulepack
from neurogrid.kernel.safety import load_yaml
from neurogrid.model.dataset import Channel
from neurogrid.model.results import Results, Summary
from neurogrid.report.texts import tables

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
DATA = DOCS / "_data"
LANGUAGES = ("en", "zh")
FIXTURES = ROOT / "tests" / "fixtures"
CALIBRATION = ROOT / "src" / "neurogrid" / "rulepacks" / "calibration" / "core.json"
PLACEHOLDERS = {"REPO_URL", "PYPI_RELEASE"}
PLACEHOLDER_TITLE = {"en": "Placeholder", "zh": "占位"}


def _page(lang: str, name: str) -> str:
    return (DOCS / lang / name).read_text(encoding="utf-8")


def _sections(text: str, level: str = "##") -> dict[str, str]:
    """Body of every heading of a level, keyed by the heading text without its anchor."""
    parts = re.split(rf"^{level} (.+)$", text, flags=re.M)
    return {re.sub(r"\s*\{#[^}]+\}\s*$", "", parts[i]).strip(): parts[i + 1] for i in range(1, len(parts), 2)}


def _anchored(text: str) -> dict[str, str]:
    """Body of every '## title {#anchor}' heading, keyed by the anchor (the same in both languages)."""
    parts = re.split(r"^## .*\{#([A-Za-z0-9_.-]+)\}\s*$", text, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def _core() -> Rulepack:
    from importlib import resources

    return load_rulepack(
        resources.files("neurogrid.rulepacks").joinpath("core.yaml").read_bytes(), "builtin"
    ).pack


def _tagged(text: str, tag: str, language: str) -> list[str]:
    return re.findall(rf"<!-- example: {re.escape(tag)} -->\n```{language}\n(.*?)\n```", text, flags=re.S)


# --- metrics, registry, origins -----------------------------------------------------------------------------


@pytest.mark.parametrize("lang", LANGUAGES)
def test_metrics_page_has_every_core_metric(lang: str) -> None:
    text = _page(lang, "metrics.md")
    sections = {m.group(1): m.start() for m in re.finditer(r"^## (M\d\d) .*\{#\1\}$", text, flags=re.M)}
    for rule in _core().rules:
        assert rule.clause in sections, (lang, rule.clause)
        start = sections[rule.clause]
        end = min([pos for pos in sections.values() if pos > start] + [len(text)])
        assert f"[{rule.id}](reference/rules.md#{rule.id})" in text[start:end], (lang, rule.id)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_check_has_a_docs_entry(lang: str) -> None:
    entries = load_yaml((DATA / f"checks.{lang}.yaml").read_text(encoding="utf-8"))
    assert isinstance(entries, dict)
    assert set(entries) == set(REGISTRY), sorted(set(entries) ^ set(REGISTRY))
    for check_id, spec in REGISTRY.items():
        own = (
            not isinstance(spec.evaluate, Bound)
            and spec.evaluate is not is_true
            and check_id != EVIDENCE_CHECK
        )
        assert entries[check_id].get("object"), (lang, check_id)
        assert bool(entries[check_id].get("passes")) == own, (lang, check_id)


def test_bounded_checks_declare_their_direction() -> None:
    """A-13: every threshold check of the registry declares parameter and direction (kernel Bound)."""
    bounds = {
        check_id: spec.evaluate for check_id, spec in REGISTRY.items() if isinstance(spec.evaluate, Bound)
    }
    assert bounds["signal.sampling_rate_min"] == Bound("min_hz", ">=")
    assert bounds["quality.line_noise"] == Bound("max_ratio", "<=")
    assert all(bound.param in REGISTRY[check_id].params for check_id, bound in bounds.items())


def test_every_rule_has_an_origin() -> None:
    origins = load_yaml((DATA / "rule_origins.yaml").read_text(encoding="utf-8"))
    assert isinstance(origins, dict)
    core = _core()
    assert set(origins) == {rule.id for rule in core.rules}
    assert {origin["origin"] for origin in origins.values()} <= {
        "spec",
        "spec_second_hand",
        "assumption",
        "calibrated",
    }
    calibrated = {rule_id for rule_id, origin in origins.items() if origin["origin"] == "calibrated"}
    thresholds = json.loads(CALIBRATION.read_text(encoding="utf-8"))["thresholds"]
    assert calibrated == set(thresholds)
    for rule in core.rules:
        if rule.id in thresholds:
            assert rule.params[thresholds[rule.id]["param"]] == thresholds[rule.id]["value"]


# --- commands and configuration -----------------------------------------------------------------------------


def _cli() -> Any:
    return typer.main.get_command(app)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_cli_option_is_documented(lang: str) -> None:
    sections = _sections(_page(lang, "commands.md"))
    group = _cli()
    global_section = next(body for title, body in sections.items() if "--debug" in body)
    for param in group.params:
        for name in param.opts:
            assert f"`{name}" in global_section, (lang, name)
    for name, command in group.commands.items():
        assert name in sections, (lang, name)
        body = sections[name]
        for param in command.params:
            labels = [p for p in param.opts if p.startswith("--")] or [str(param.name).upper()]
            for label in labels:
                assert f"`{label}" in body, (lang, name, label)
    assert "NEUROGRID_LANG" in global_section


def _leaves(model: type[BaseModel], prefix: str = "") -> list[str]:
    out = []
    for name, field in model.model_fields.items():
        nested = [
            arg
            for arg in (field.annotation, *typing.get_args(field.annotation))
            for arg in (arg, *typing.get_args(arg))
            if isinstance(arg, type) and issubclass(arg, BaseModel)
        ]
        if nested:
            out += _leaves(nested[0], f"{prefix}{name}.")
        else:
            out.append(prefix + name)
    return out


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_config_field_is_documented(lang: str) -> None:
    """Every key of neurogrid.toml (config.Config) appears in the section of its table on configuration.md."""
    bodies: dict[str, str] = {}
    for title, body in _sections(_page(lang, "configuration.md")).items():
        for table in re.findall(r"\[\[?([a-z_]+)", title):
            bodies[table] = bodies.get(table, "") + title + body
    for path in _leaves(Config):
        top, _, rest = path.partition(".")
        assert top in bodies, (lang, top)
        for part in rest.split(".") if rest else []:
            found = f"`{part}" in bodies[top] or f"{part}." in bodies[top] or f".{part}" in bodies[top]
            assert found, (lang, path, part)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_documented_toml_examples_are_valid(lang: str) -> None:
    examples = _tagged(_page(lang, "configuration.md"), "neurogrid.toml", "toml")
    assert len(examples) == 1
    parsed = config_module.parse_bytes(examples[0].encode("utf-8"))
    assert parsed.check.rulepacks == ["core", "bids", "gxdsl008"]
    assert examples[0] == _tagged(_page("en", "configuration.md"), "neurogrid.toml", "toml")[0]


def test_rulepack_tutorial_example_runs(tmp_path: Path) -> None:
    """POS-02: the example pack of rulepacks.md runs as printed, in both languages the same."""
    en = _tagged(_page("en", "rulepacks.md"), "rulepack", "yaml")
    zh = _tagged(_page("zh", "rulepacks.md"), "rulepack", "yaml")
    assert len(en) == 1 and en == zh
    pack = tmp_path / "lab_sop.yaml"
    pack.write_text(en[0] + "\n", encoding="utf-8")
    out = tmp_path / "results.json"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "neurogrid",
            "check",
            str(FIXTURES / "synthetic" / "edf_ok"),
            "--config",
            str(FIXTURES / "documented.toml"),
            "--rulepack",
            str(pack),
            "--as-of",
            "2026-10-11",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    for lang in LANGUAGES:
        assert "exit code 0" in _page(lang, "rulepacks.md") or "退出码 0" in _page(lang, "rulepacks.md")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    results = json.loads(out.read_text(encoding="utf-8"))
    rules = {rule["id"] for rule in results["rules"]}
    assert {"LABSOP-ACQ-001", "LABSOP-ACQ-002", "LABSOP-ACC-001"} <= rules
    states = {f["rule_id"]: f["status"] for f in results["findings"] if f["rule_id"].startswith("LABSOP")}
    assert states.get("LABSOP-ACC-001") == "evidence_open"  # as the page says


# --- outputs, exit codes, report ----------------------------------------------------------------------------


@pytest.mark.parametrize("lang", LANGUAGES)
def test_output_page_names_every_results_field(lang: str) -> None:
    sections = _anchored(_page(lang, "reference/outputs.md"))
    for anchor, schema in (("results-json", "results"), ("scan-json", "scan"), ("manifest", "manifest")):
        path = ROOT / "src" / "neurogrid" / "schemas" / f"{schema}.schema.json"
        properties = json.loads(path.read_text(encoding="utf-8"))["properties"]
        missing = [name for name in properties if f"`{name}`" not in sections[anchor]]
        assert not missing, (lang, schema, missing)
    assert set(Results.model_fields) <= set(re.findall(r"`(\w+)`", sections["results-json"]))


EXIT_CODES = {
    "scan": {0, 2},
    "convert": {0, 1, 2},
    "check": {0, 1, 2},
    "report": {0, 2},
    "manifest": {0, 1, 2},
    "verify": {0, 1, 2},
}


@pytest.mark.parametrize("lang", LANGUAGES)
def test_exit_code_tables_match(lang: str) -> None:
    """A-12, A-82: each command documents exactly its exit codes; check's rows match quickstart's."""
    sections = _sections(_page(lang, "commands.md"))
    assert set(EXIT_CODES) == set(_cli().commands)
    for command, codes in EXIT_CODES.items():
        rows = {int(code) for code in re.findall(r"^\| ([0-2]) \|", sections[command], flags=re.M)}
        assert rows == codes, (lang, command, rows)
    quick = re.findall(r"^\| ([0-2]) \|", _page(lang, "quickstart.md"), flags=re.M)
    assert quick == ["0", "1", "2"]


@pytest.mark.parametrize("lang", LANGUAGES)
def test_report_page_names_every_section(lang: str) -> None:
    headings = set(_sections(_page(lang, "report.md")))
    labels = {key: value for key, value in tables()[lang].items() if key.startswith("report.section.")}
    assert labels and set(labels.values()) <= headings, sorted(set(labels.values()) - headings)
    text = _page(lang, "report.md")
    assert tables()[lang]["disclaimer"] in text
    assert "50" in text and "results.json" in text  # overflow beyond 50 rows per rule (A-59, B1)


# --- references, terms, placeholders ------------------------------------------------------------------------


def _known_dois() -> set[str]:
    text = (ROOT / "DATA_SOURCES.md").read_text(encoding="utf-8") + CALIBRATION.read_text(encoding="utf-8")
    for dist in ("pyprep", "autoreject", "mne-icalabel", "mne-bids", "mne", "python-picard"):
        text += metadata.metadata(dist).get_payload() or ""  # type: ignore[attr-defined]
    return {doi.rstrip(".").lower() for doi in re.findall(r"10\.\d{4,9}/[A-Za-z0-9._/-]+", text)}


def test_every_doi_is_traceable() -> None:
    known = _known_dois()
    for lang in LANGUAGES:
        for page in (DOCS / lang).rglob("*.md"):
            for doi in re.findall(r"10\.\d{4,9}/[A-Za-z0-9._/-]+", page.read_text(encoding="utf-8")):
                assert doi.rstrip(".").lower() in known, (lang, page.name, doi)


MAPPING = {
    "rulepack-format": {
        "rulepack": "rulepack",
        "version": "version",
        "quelle": "source",
        "regeln": "rules",
        "id": "id",
        "klausel": "clause",
        "titel_zh": "title_zh",
        "titel_en": "title_en",
        "phase": "phase",
        "pruefung": "check",
        "parameter": "params",
        "schweregrad": "severity",
        "nachweis": "verification",
    },
    "values": {
        "erfassung": "acquisition",
        "verarbeitung": "processing",
        "annotation": "annotation",
        "speicherung": "storage",
        "zugriff": "access",
        "fehler": "error",
        "warnung": "warning",
        "hinweis": "info",
        "automatisch": "automatic",
        "halbautomatisch": "semi_automatic",
        "manuell": "manual",
        "nass": "wet",
        "trocken": "dry",
        "gut": "good",
        "schlecht": "bad",
        "training": "training",
        "validierung": "validation",
        "veroeffentlichung": "publication",
        "weitergabe": "sharing",
        "kommerziell": "commercial",
    },
    "report-terms": {
        "Befund": "finding",
        "Belege": "details",
        "Nachweis": "evidence",
        "Ausnahme": "exception",
        "Ampel": "light",
        "Abdeckungsmass": "coverage",
        "Stichtag": "as_of",
    },
}


def test_spec_terms_are_documented() -> None:
    """D-03: the specification terms that became identifiers, against the code and both pages."""
    fields = set(Rulepack.model_fields) | set(Rule.model_fields)
    assert set(MAPPING["rulepack-format"].values()) <= fields
    enum_values = {e.value for enum in (Phase, Severity, Verification) for e in enum}
    literals = set(
        typing.get_args(typing.get_args(MetadataDefaults.model_fields["electrode_type"].annotation)[0])
    )
    literals |= set(typing.get_args(typing.get_args(Channel.model_fields["status"].annotation)[0]))
    consent_uses = {"training", "validation", "publication", "sharing", "commercial"}  # ConsentScope, v0.2
    assert set(MAPPING["values"].values()) <= enum_values | literals | consent_uses
    assert {"details"} <= set(Finding.model_fields) and {"evidence", "exceptions"} <= set(
        Results.model_fields
    )
    phase_summary = typing.get_args(Summary.model_fields["phases"].annotation)[1]
    assert "light" in phase_summary.model_fields and {light.value for light in Light} == {
        "red",
        "yellow",
        "green",
        "grey",
    }
    assert "coverage" in Summary.model_fields and "as_of" in config_module.CheckSection.model_fields
    assert {s.value for s in Status} == {
        "passed",
        "failed",
        "excepted",
        "not_applicable",
        "not_checkable",
        "evidence_open",
    }
    for lang in LANGUAGES:
        text = _page(lang, "terms.md")
        anchors = {m.group(1): m.end() for m in re.finditer(r"\{#([a-z-]+)\}$", text, flags=re.M)}
        for section, pairs in MAPPING.items():
            start = anchors[section]
            end = min([pos for pos in anchors.values() if pos > start] + [len(text)])
            rows = set(re.findall(r"^\| (\w+) \| (\w+)", text[start:end], flags=re.M | re.ASCII))
            missing = [(term, ident) for term, ident in pairs.items() if (term, ident) not in rows]
            assert not missing, (lang, section, missing)


def test_no_unmarked_placeholders() -> None:
    """Only <REPO_URL> and <PYPI_RELEASE> wait for the publication, each named in a visible placeholder note
    on its page (the release workflow fails while they remain)."""
    for lang in LANGUAGES:
        for page in sorted((DOCS / lang).rglob("*.md")):
            text = page.read_text(encoding="utf-8")
            used = set(re.findall(r"<([A-Z][A-Z_]{2,})>", text))
            assert used <= PLACEHOLDERS, (lang, page.name, used)
            notes = re.findall(
                rf'^!!! warning "{PLACEHOLDER_TITLE[lang]}"\n((?:    .*\n)+)', text + "\n", flags=re.M
            )
            for name in used:
                assert any(f"<{name}>" in note for note in notes), (lang, page.name, name)
