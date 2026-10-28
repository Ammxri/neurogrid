"""The documentation states what the code does (TECH-06, POS-02, CON-05, D-03): pages are checked against the
registry, the rule packs, the configuration model, the CLI, the schemas and the language tables."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import typing
from collections.abc import Sequence
from datetime import date
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest
import typer
from pydantic import BaseModel

from neurogrid import config as config_module
from neurogrid import pipeline
from neurogrid.checks.registry import REGISTRY
from neurogrid.cli import app
from neurogrid.config import Config, MetadataDefaults
from neurogrid.kernel.findings import Finding, Light, Phase, Severity, Status, Verification
from neurogrid.kernel.rules import EVIDENCE_CHECK, Bound, Rule, Rulepack, is_true, load_rulepack
from neurogrid.kernel.safety import load_yaml, operator_path_problem
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


# The preparation of the M06/M09 sample in the order of neurogrid.quality.sample: a marker of each step in the
# code, and the words of the metrics page that describe it.
PREPARATION = (
    ("_resampled(", {"en": "resampled to 250 Hz", "zh": "重采样到 250 Hz"}),
    ("notch_filter(", {"en": "a notch at the line frequency", "zh": "陷波滤波"}),
    ("raw.filter(BAND_HZ[0], BAND_HZ[1]", {"en": "a 1–100 Hz band-pass", "zh": "1–100 Hz 带通滤波"}),
)
REFERENCE = {"en": "average reference without the bad channels of M06", "zh": "去除 M06 坏通道后的平均参考"}


def _in_order(text: str, needles: list[str]) -> bool:
    positions = [text.find(needle) for needle in needles]
    return -1 not in positions and positions == sorted(positions)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_sample_preparation_is_described_in_the_order_of_the_code(lang: str) -> None:
    """M06: resampling, notch and band-pass in the order of quality.sample._prepared, the average reference
    without the bad channels only after M06 (prepare_sample), with the code's frequencies."""
    import inspect

    from neurogrid.quality import sample

    prepared = inspect.getsource(sample._prepared)
    assert _in_order(prepared, [marker for marker, _words in PREPARATION])
    flow = inspect.getsource(sample.prepare_sample)
    assert _in_order(flow, ["_prepared(", "_bad_channels(", 'set_eeg_reference("average"'])
    text = " ".join(_anchored(_page(lang, "metrics.md"))["M06"].split())
    assert _in_order(text, [words[lang] for _marker, words in PREPARATION] + [REFERENCE[lang]]), text
    assert f"{sample.TARGET_HZ:g} Hz" in text and f"{sample.TARGET_HZ / 2:g} Hz" in text  # notch below 125 Hz
    assert f"{sample.BAND_HZ[0]:g}–{sample.BAND_HZ[1]:g} Hz" in text
    assert not _in_order(text, [PREPARATION[1][1][lang], PREPARATION[0][1][lang]])  # the old order fails


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


DATASET_PRECEDENCE = {
    "en": (
        "`name` and `license` set here take precedence over `Name` and `License` of"
        " `dataset_description.json`",
        "`id`, `version` and `source` come only from this section",
    ),
    "zh": (
        "此处设置的 `name` 和 `license` 优先于 `dataset_description.json` 中的 `Name` 和 `License`",
        "`id`、`version` 和 `source` 只来自本节",
    ),
}
DATASET_PRECEDENCE_REVERSED = {
    "en": "when `dataset_description.json` does not provide them",
    "zh": "当 `dataset_description.json` 未提供时",
}


def test_dataset_section_states_the_precedence_of_the_code(tmp_path: Path) -> None:
    """A-04, A-63, review R09: [dataset] name and license of neurogrid.toml win over Name and License of
    dataset_description.json, which fills a field only when the section leaves it unset; id, version and
    source come from the section alone. The page said the reverse ("when dataset_description.json does not
    provide them")."""
    dataset = tmp_path / "ds"
    shutil.copytree(FIXTURES / "synthetic" / "bids_ok", dataset)
    description = json.loads((dataset / "dataset_description.json").read_text(encoding="utf-8"))
    assert description["Name"] and description["License"]  # both sources are set
    given = tmp_path / "given.toml"
    given.write_text(
        '[dataset]\nname = "Name from toml"\nlicense = "MIT-from-toml"\nversion = "2"\n', encoding="utf-8"
    )
    empty = tmp_path / "empty.toml"
    empty.write_text("", encoding="utf-8")
    shown: dict[str, Any] = {}
    for name, config in (("given", given), ("empty", empty)):
        options = pipeline.CheckOptions(config_path=config, as_of=date(2026, 10, 11), work_base=tmp_path)
        shown[name] = pipeline.run_check(dataset, options).dataset
    assert (shown["given"].name, shown["given"].license) == ("Name from toml", "MIT-from-toml")
    assert (shown["empty"].name, shown["empty"].license) == (description["Name"], description["License"])
    assert (shown["given"].id, shown["given"].version, shown["empty"].version) == ("unnamed", "2", None)
    for lang in LANGUAGES:
        flat = " ".join(_anchored(_page(lang, "configuration.md"))["dataset"].split())
        assert DATASET_PRECEDENCE_REVERSED[lang] not in flat, lang
        for sentence in DATASET_PRECEDENCE[lang]:
            assert sentence in flat, (lang, sentence)


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


FIXED_TITLE = {"en": "Fixed sentence", "zh": "固定声明"}
FIXED_PAGES = {"index.md", "limitations.md", "report.md"}


def _fixed_sentence_notes(text: str, lang: str) -> list[str]:
    """The body of every '!!! <type> "<fixed sentence title>"' note of a page, as one line."""
    notes = re.findall(rf'^!!! \w+ "{FIXED_TITLE[lang]}"\n((?:    .*\n)+)', text + "\n", flags=re.M)
    return [" ".join(note.split()) for note in notes]


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_copy_of_the_fixed_sentence_equals_the_table(lang: str) -> None:
    """B4, A-07: the fixed sentence is copied into the notes of the start page, the limitations and the report
    page and into the README; each copy equals report/i18n 'disclaimer' of its language, so a reviewed zh
    sentence cannot leave a stale copy behind."""
    sentence = tables()[lang]["disclaimer"]
    found = {}
    for page in sorted((DOCS / lang).rglob("*.md")):
        notes = _fixed_sentence_notes(page.read_text(encoding="utf-8"), lang)
        if notes:
            found[page.relative_to(DOCS / lang).as_posix()] = notes
    assert set(found) >= FIXED_PAGES, sorted(found)
    assert all(notes == [sentence] for notes in found.values()), found
    readme = re.findall(r"^> \*\*(.+)\*\*$", (ROOT / "README.md").read_text(encoding="utf-8"), flags=re.M)
    assert sentence in readme, readme
    assert set(readme) == {tables()[code]["disclaimer"] for code in LANGUAGES}  # the README's two copies
    stale = f'!!! note "{FIXED_TITLE[lang]}"\n    {sentence[:-1]}\n'
    assert _fixed_sentence_notes(stale, lang) != [sentence]


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


def test_decision_a67_records_the_posix_rules_of_the_code() -> None:
    """A-67 in the decision log names the POSIX rules of operator_path_problem: the Windows network and device
    forms are refused with the Windows keys, backslashes inside a name stay legal. Every example it quotes
    gets the verdict it states."""
    text = (DOCS / "umsetzung" / "ENTSCHEIDUNGEN.md").read_text(encoding="utf-8")
    found = re.search(r"^\*\*A-67 .*?(?=\n\n)", text, flags=re.M | re.S)
    assert found is not None
    paragraph = found.group(0)
    refused = {
        "//…": "path.unc",
        r"\\server\share": "path.unc",
        r"\/server/share": "path.unc",
        "\\\\?\\": "path.device",
        "\\\\.\\": "path.device",
        "\\??\\": "path.device",
    }
    for example, key in refused.items():
        assert f"`{example}`" in paragraph, example
        assert f"`{key}`" in paragraph, key
        typed = example.replace("…", "server/share") + "x"
        assert operator_path_problem(typed, windows=False) == key, example
    for example in (r"\x.edf", r"a\b.edf", "/\\…"):
        assert f"`{example}`" in paragraph, example
        assert operator_path_problem(example.replace("…", "x"), windows=False) is None, example


def test_privacy_pages_state_the_strace_rule_of_the_offline_gate(tmp_path: Path) -> None:
    """NG-N01, A-49: 'Check it yourself' states the criterion of tools/strace_check.py (the offline gate of
    CI): no AF_INET/AF_INET6 call to an address other than loopback; loopback calls are allowed, except to
    port 9, where a dead proxy such as http://127.0.0.1:9 points (review R11). A trace that the gate accepts
    must not look like a failure to a user who follows the page, and one it rejects must not look clean."""
    import strace_check  # type: ignore[import-not-found]

    for lang in LANGUAGES:
        section = _anchored(_page(lang, "privacy.md"))["check-yourself"]
        flat = " ".join(section.split())
        assert "127.0.0.0/8" in flat and "`::1`" in flat, lang
        assert "tools/strace_check.py" in flat and "`strace-*.txt`" in flat, lang
        assert "strace-check.txt" in flat, lang  # the trace file name the checker reads
        assert not re.search(r"must not contain\s+`AF_INET` or `AF_INET6`\.", flat), lang
        assert "记录中不得出现 `AF_INET` 或 `AF_INET6`。" not in flat, lang
        assert DEAD_PROXY[lang] in flat, lang  # the port-9 exception of the gate
    loopback = (
        'connect(3, {sa_family=AF_INET, sin_port=htons(4512), sin_addr=inet_addr("127.0.0.1")}, 16) = 0'
    )
    loopback6 = (
        "connect(3, {sa_family=AF_INET6, sin6_port=htons(4512), sin6_flowinfo=htonl(0),"
        ' inet_pton(AF_INET6, "::1", &sin6_addr), sin6_scope_id=0}, 28) = 0'
    )
    outside = 'connect(3, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("10.0.0.1")}, 16) = -1'
    dead_proxy = loopback.replace("htons(4512)", "htons(9)")
    dead_proxy6 = loopback6.replace("htons(4512)", "htons(9)")
    assert strace_check.classify(loopback)[0] == strace_check.classify(loopback6)[0] == "loopback"
    assert strace_check.classify(outside)[0] == "network"
    assert strace_check.classify(dead_proxy)[0] == strace_check.classify(dead_proxy6)[0] == "network"
    (tmp_path / "strace-check.txt").write_text(f"{loopback}\n{loopback6}\n", encoding="utf-8")
    _summary, attempts = strace_check.check(tmp_path)
    assert attempts == []  # what the page allows, the gate allows
    (tmp_path / "strace-check.txt").write_text(f"{loopback}\n{dead_proxy}\n", encoding="utf-8")
    _summary, attempts = strace_check.check(tmp_path)
    assert len(attempts) == 1  # what the page names as the exception, the gate rejects


EVIDENCE_IN_CLEAR = {
    "en": {
        "privacy.md#outputs": (
            "appear as written in `results.json` and in section 5 of the report, also in raw folders without"
            " `--show-paths`",
            "The console never prints them.",
            "Write a role or initials as `reviewer`, never a full name",
        ),
        "report.md#evidence": (
            "appear as written in `evidence.yaml`, also in raw folders without `--show-paths`",
            "use a role or initials as reviewer, never a full name",
        ),
        "report.md#pseudonymity": ("are the one exception: they appear as written",),
        "configuration.md#files": (
            "`reviewer`: a role or initials, never a full name",
            "These four fields appear as written in `results.json` and in the report, also in raw folders"
            " without `--show-paths`",
        ),
    },
    "zh": {
        "privacy.md#outputs": (
            "按原样出现在 `results.json` 和报告第 5 部分中，"
            "在原始数据文件夹中不使用 `--show-paths` 时也是如此",
            "控制台从不输出这些字段。",
            "`reviewer` 请填写角色或姓名缩写，从不填写全名",
        ),
        "report.md#evidence": (
            "按 `evidence.yaml` 中的原样显示，在原始数据文件夹中不使用 `--show-paths` 时也是如此",
            "审核人请填写角色或姓名缩写，从不填写全名",
        ),
        "report.md#pseudonymity": ("字段，它们按原样显示",),
        "configuration.md#files": (
            "`reviewer`：角色或姓名缩写，从不填写全名",
            "这四个字段按原样出现在 `results.json` 和报告中，"
            "在原始数据文件夹中不使用 `--show-paths` 时也是如此",
        ),
    },
}
# The evidence.yaml fields that are not free text of the user: they never name a person.
EVIDENCE_FIXED_FIELDS = {"status", "sha256", "date"}


def test_pages_state_that_evidence_free_text_appears_in_clear(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A-83 (display), A-15, review R08: document (relative path), reviewer, comment and justification of
    evidence.yaml appear as written in results.json and in report section 5, also in raw folders without
    --show-paths; the console never prints them; reviewer is a role or initials. The pages said only that raw
    folders get pseudonymous IDs. The test checks the behaviour the pages now state, and the pages."""
    from neurogrid.cli import main
    from neurogrid.kernel.evidence import EvidenceItem

    free_text = set(EvidenceItem.model_fields) - EVIDENCE_FIXED_FIELDS
    assert free_text == {"document", "reviewer", "comment", "justification"}  # the four the pages name
    dataset = tmp_path / "raw"
    shutil.copytree(FIXTURES / "synthetic" / "edf_ok", dataset)
    (dataset / ".neurogrid" / "evidence").mkdir(parents=True)
    document = ".neurogrid/evidence/Zhang_San_SOP.txt"
    (dataset / document).write_bytes(b"IT security SOP (synthetic test document)\n")
    values = {
        "document": document,
        "reviewer": "Zhang San",
        "comment": "checked with Li Si",
        "justification": "Wang Wu keeps the key",
    }
    (dataset / ".neurogrid" / "evidence.yaml").write_text(
        "format_version: 1\nevidence:\n  GXDSL008-ACC-001:\n    status: provided\n"
        + "".join(f"    {name}: {text}\n" for name, text in values.items()),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    written = str(out / "r.json")
    console = []
    for args in (
        ["check", str(dataset), "--rulepack", "gxdsl008", "--as-of", "2026-10-11", "--out", written],
        ["report", written, "--lang", "zh,en", "--format", "html", "--out", str(out / "rep")],
    ):
        with pytest.raises(SystemExit) as info:
            main(args)
        stdout, stderr = capsys.readouterr()
        assert info.value.code in (0, 1, None), (args[0], stdout, stderr)
        console.append(stdout + stderr)
    results = json.loads((out / "r.json").read_text(encoding="utf-8"))
    assert not results["dataset"]["is_bids"]  # a raw folder, checked without --show-paths
    (record,) = results["evidence"]
    assert {name: record[name] for name in values} == values  # in clear in results.json
    for lang in LANGUAGES:
        html = (out / "rep" / f"report.{lang}.html").read_text(encoding="utf-8")
        section = html[html.index('<section id="evidence">') :]
        section = section[: section.index("</section>")]
        assert all(text in section for text in values.values()), lang  # and in report section 5
    assert not [text for text in values.values() for line in console if text in line]  # never on the console
    assert "notice.evidence_looks_identifying" in {notice["message_key"] for notice in results["notices"]}
    for lang, pages in EVIDENCE_IN_CLEAR.items():
        for where, sentences in pages.items():
            name, anchor = where.split("#")
            flat = " ".join(_anchored(_page(lang, name))[anchor].split())
            assert all(f"`{field}`" in flat for field in free_text) or anchor == "evidence", (lang, where)
            for sentence in sentences:
                assert sentence in flat, (lang, where, sentence)


DEAD_PROXY = {
    "en": "except calls to port 9 on loopback",
    "zh": "回环地址的端口 9 除外",
}


OFFLINE_WORKFLOW = ROOT / ".github" / "workflows" / "offline.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
CLEANROOM_WINDOWS = ROOT / "packaging" / "ci" / "cleanroom_windows.ps1"
BEFORE_CI = ("until the first CI run", "首次 CI 运行前", "首次 CI")
BUNDLE_IN_CI = {"en": "offline bundle verified in CI", "zh": "离线安装包已在 CI 中验证"}
# The test jobs of ci.yml passed on both runners with every Python of the matrix for dcec9bd and failed again
# for 18da12f, so the pages cannot rest on a past run: release.yml runs ci.yml on the tagged commit and
# creates no draft release while it fails. Debian 12 and Ubuntu 22.04 get the offline jobs only (offline.yml),
# never the test suite. {} is the Python range.
SUITE_IN_CI = {"en": "test suite verified in CI (Python {})", "zh": "测试套件已在 CI 中验证（Python {}）"}
SUITE_NOT_IN_CI = {"en": "test suite not run in CI", "zh": "测试套件未在 CI 中运行"}
# {runners}: the runners of ci.yml in backticks; {each}: every Python of its matrix.
SUITE_DEFINITION = {
    "en": (
        '"Test suite verified in CI" means: in the CI the test suite ran on GitHub\'s {runners} runners with'
        ' Python {each} each and passed. "Test suite not run in CI" means: the CI installs the offline'
        " bundle on these systems and runs its commands, but does not run the test suite there."
    ),
    "zh": (
        "“测试套件已在 CI 中验证”表示：在 CI 中，测试套件在 GitHub 的 {runners} 运行器上分别用"
        " Python {each} 运行，全部通过。“测试套件未在 CI 中运行”表示：CI 在这些系统上安装离线安装包"
        "并运行其命令，但不在其上运行测试套件。"
    ),
}
# The status cell of the audit hook and network ban (tests) on the privacy page.
AUDIT_HOOK_IN_CI = {
    "en": "verified locally and in CI on GitHub's {runners} runners with Python {range}",
    "zh": "已在本地验证，并已在 CI 中于 GitHub 的 {runners} 运行器上用 Python {range} 验证",
}
# The test suite in the platform paragraph of limitations.md (and so of the delivery texts).
SUITE_LIMITS = {
    "en": (
        "and the test suite with Python {range} on Windows Server and Ubuntu 24.04; the CI does not run the"
        " test suite on Debian 12 and Ubuntu 22.04."
    ),
    "zh": (
        "测试套件已在 CI 中用 Python {range} 于 Windows Server 和 Ubuntu 24.04 上验证；CI 不在 Debian 12 和"
        " Ubuntu 22.04 上运行测试套件。"
    ),
}
# The wording up to 18da12f, written while the test jobs failed: no page and no delivery text may say it.
SUITE_PENDING = (
    "test suite not yet verified",
    "测试套件尚未验证",
    "on Linux and on the Windows runner not yet verified",
    "on Linux and on the Windows runner is not yet verified",
    "在 Linux 和 Windows 运行器上尚未验证",
    "Linux 和 Windows 运行器上的测试套件尚未验证",
    "do not pass yet",
    "尚未通过",
)
NOT_VERIFIED = {"en": "not verified", "zh": "未验证"}
REFUSED = {
    "en": "the installer stops with exit code 2 (verified in CI)",
    "zh": "安装程序以退出码 2 结束（已在 CI 中验证）",
}
DISTRIBUTION = {"debian:12-slim": "Debian 12", "ubuntu:18.04": "Ubuntu 18.04"}
SHELLS = {"powershell": "Windows PowerShell 5.1", "pwsh": "PowerShell 7"}
# The test runners of ci.yml and the system each one stands for in the platform table.
RUNNERS = {"windows-latest": "Windows Server", "ubuntu-24.04": "Ubuntu 24.04"}
EVIDENCE_IN_CI = {
    "en": (
        "verified in CI: installer and every v0.1 command",
        "verified in CI on GitHub's Windows Server runner",
    ),
    "zh": (
        "已在 CI 中验证：离线安装包的安装程序和 0.1 版的每条命令",
        "已在 CI 中于 GitHub 的 Windows Server 运行器上",
    ),
}
FIREWALL_RULE = (
    "New-NetFirewallRule -DisplayName neurogrid-block -Direction Outbound -Action Block -Program $_.FullName"
)


def _table_rows(text: str) -> list[list[str]]:
    lines = [line.strip() for line in text.splitlines() if line[:1] == "|"]
    return [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]


def _flat(text: str) -> str:
    """Without whitespace and in lower case, so a sentence is found wherever a page wraps it."""
    return re.sub(r"\s+", "", text).lower()


def _suite_matrix() -> tuple[list[str], list[str]]:
    """(runners, Python versions) of the test job of ci.yml."""
    matrix = load_yaml(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["test"]["strategy"]["matrix"]
    return [str(runner) for runner in matrix["os"]], [str(version) for version in matrix["python"]]


def _suite_wording(lang: str, runners: list[str], pythons: list[str]) -> tuple[str, str]:
    """(the runners in backticks, every Python version) as the pages of a language list them."""
    separator, last = {"en": (", ", " and "), "zh": ("、", " 和 ")}[lang]
    return last.join(f"`{runner}`" for runner in runners), separator.join(pythons[:-1]) + last + pythons[-1]


def test_platform_and_evidence_status_follow_the_offline_workflow() -> None:
    """V-06, NG-N01, NG-N04, TECH-06: the offline workflow ran green (both bundles, clean rooms of every image
    and both Windows shells with WFP audit and PDF, glibc 2.27 refused, every command under strace without
    network). The pages said 'not verified until the first CI run'. Each status now names what the workflow
    verifies, read from offline.yml. The test suite stayed 'not yet verified' while the test jobs of ci.yml
    failed (CI run of 55335ca). They passed on windows-latest and ubuntu-24.04 with Python 3.11-3.13 for
    dcec9bd and failed again for 18da12f: a run of an earlier commit says nothing about the commit that ships.
    So the claim rests on the release itself: release.yml runs ci.yml on the tagged commit and its draft needs
    that run, and this test fails when the gate is gone. Debian 12 and Ubuntu 22.04 get the offline jobs only.
    The row that named Debian 12, Ubuntu 22.04 and 24.04 together could not say both, so it is split: exactly
    the systems of the ci.yml runners say 'test suite verified in CI', the other Linux row says 'not run in
    CI', Windows 10 stays 'not verified', and the old wording is gone from every page and both delivery
    texts."""
    jobs = load_yaml(OFFLINE_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    images = [entry["image"] for entry in jobs["cleanroom-linux"]["strategy"]["matrix"]["include"]]
    shells = [entry["shell"] for entry in jobs["cleanroom-windows"]["strategy"]["matrix"]["include"]]
    refusal = " ".join(step.get("run", "") for step in jobs["glibc-refusal"]["steps"])
    refused_image = re.search(r"--image (\S+) --expect-refusal", refusal)
    assert refused_image and jobs["cleanroom-windows"]["runs-on"] == "windows-latest"
    names = [DISTRIBUTION.get(image, image.replace("ubuntu:", "Ubuntu ")) for image in images]
    assert names == ["Debian 12", "Ubuntu 22.04", "Ubuntu 24.04"] and shells == ["powershell", "pwsh"]
    runners, pythons = _suite_matrix()
    assert runners == list(RUNNERS) and pythons == ["3.11", "3.12", "3.13"], (runners, pythons)
    release = load_yaml(RELEASE_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    gates = [job_id for job_id, job in release.items() if job.get("uses") == "./.github/workflows/ci.yml"]
    # 'verified in CI' holds for a version only when its own commit passed ci.yml before the draft release
    assert gates and set(gates) <= set(release["draft"]["needs"]), (gates, release["draft"]["needs"])
    python_range = f"{pythons[0]}–{pythons[-1]}"
    without_suite = [name for name in names if name not in RUNNERS.values()]
    stale = [_flat(phrase) for phrase in (*SUITE_PENDING, *BEFORE_CI)]
    texts = [*sorted((DOCS / "en").rglob("*.md")), *sorted((DOCS / "zh").rglob("*.md"))]
    for path in [*texts, ROOT / "packaging" / "README.bundle.txt", ROOT / "packaging" / "release-notes.md"]:
        flat = _flat(path.read_text(encoding="utf-8"))
        assert not [phrase for phrase in stale if phrase in flat], path.relative_to(ROOT).as_posix()
    for lang in LANGUAGES:
        suite = SUITE_IN_CI[lang].format(python_range)
        page = _anchored(_page(lang, "installation.md"))["platforms"]
        rows = _table_rows(page)
        verified = [(platform, status) for platform, status in rows if BUNDLE_IN_CI[lang] in status]
        assert len(verified) == 3, (lang, rows)
        windows = [platform for platform, _ in verified if "`windows-latest`" in platform]
        assert len(windows) == 1 and all(SHELLS[shell] in windows[0] for shell in shells), lang
        linux = [platform for platform, _ in verified if platform not in windows]
        # every distribution of the clean rooms in exactly one Linux row
        assert sorted(name for name in names for platform in linux if name in platform) == sorted(names), lang
        with_suite = [platform for platform, status in verified if suite in status]
        # the test suite exactly on the systems of the ci.yml runners, each row naming its runner
        assert len(with_suite) == len(runners), (lang, verified)
        for runner, system in RUNNERS.items():
            (row,) = [platform for platform in with_suite if f"`{runner}`" in platform]
            assert system in row, (lang, row)
            assert not [name for name in without_suite if name in row], (lang, row)
        for platform, status in verified:
            if platform not in with_suite:
                assert SUITE_NOT_IN_CI[lang] in status, (lang, platform, status)
                assert all(name in platform for name in without_suite), (lang, platform)
        assert [status for platform, status in rows if "Windows 10" in platform] == [NOT_VERIFIED[lang]], lang
        both, each = _suite_wording(lang, runners, pythons)
        assert _flat(SUITE_DEFINITION[lang].format(runners=both, each=each)) in _flat(page), lang
        refused = [platform for platform, status in rows if REFUSED[lang] in status]
        assert len(refused) == 1 and DISTRIBUTION[refused_image.group(1)] in refused[0], (lang, rows)
        limits = _anchored(_page(lang, "limitations.md"))["platforms"]
        assert _flat(SUITE_LIMITS[lang].format(range=python_range)) in _flat(limits), lang
        privacy = _anchored(_page(lang, "privacy.md"))["check-yourself"]
        statuses = [status for _evidence, status in _table_rows(privacy)[2:]]
        linux_run, firewall = EVIDENCE_IN_CI[lang]
        assert any(status.startswith(linux_run) and "`debian:12-slim`" in status for status in statuses), lang
        assert any(status.startswith(firewall) for status in statuses), lang
        assert AUDIT_HOOK_IN_CI[lang].format(runners=both, range=python_range) in statuses, (lang, statuses)


CLEANROOM_LINUX = ROOT / "packaging" / "ci" / "cleanroom_linux.sh"
CLEANROOM_INSIDE = ROOT / "packaging" / "ci" / "cleanroom_inside.sh"
# What "offline bundle verified in CI" means, per platform, as the clean-room scripts do it.
CLEAN_ROOM = {
    "en": {
        "linux": (
            "On Linux the clean room is a fresh container without network (`--network none`) and without a "
            "preinstalled Python, run as an unprivileged user."
        ),
        "windows": (
            "On Windows it is a fresh folder on the runner, whose network stays on: no Python or uv is"
            " reachable on `PATH` (the runner's preinstalled Python stays installed, only its folders are"
            " removed from `PATH`), an outbound firewall rule blocks every program of the bundle, the"
            " installation and the PDF browser, and the Windows Filtering Platform audits every connection;"
            " a connection or attempt of these programs to an address other than loopback fails the run"
        ),
    },
    "zh": {
        "linux": (
            "在 Linux 上，洁净环境是一个全新的容器，没有网络（`--network none`），没有预装的 Python，以无特"
            "权用户身份运行。"
        ),
        "windows": (
            "在 Windows 上，它是运行器上的一个全新文件夹，运行器的网络保持开启：`PATH` 上找不到任何 Python "
            "或 uv（运行器预装的 Python 仍然安装着，只是其文件夹已从 `PATH` 中移除），一条出站防火墙规则阻"
            "止安装包、安装位置和 PDF 浏览器的每个程序，Windows 筛选平台审计每次连接；这些程序向回环地址以"
            "外的地址发起的任何连接或连接尝试都会使运行失败"
        ),
    },
}
NO_NETWORK_FOR_BOTH = {
    "en": "a fresh folder or container without network",
    "zh": "全新的文件夹或容器，没有网络",
}


def test_clean_room_definition_matches_each_platforms_clean_room() -> None:
    """V-06, NG-N01, TECH-06: installation.md defined "offline bundle verified in CI" as a clean room that is
    "a fresh folder or container without network and without a preinstalled Python" for both platforms. Only
    the Linux room is that (cleanroom_linux.sh: --network none, an image without Python, uid 1000). The
    Windows room keeps the runner's network: it takes Python and uv off PATH (the runner's Python stays
    installed), blocks every .exe of the bundle, the installation and the PDF browser with an outbound
    firewall rule and audits every connection with the Windows Filtering Platform. The definition now says
    so per platform; the facts are read from the scripts."""
    linux = " ".join(CLEANROOM_LINUX.read_text(encoding="utf-8").split())
    assert "docker run --rm --network none --user 1000:1000" in linux
    inside = CLEANROOM_INSIDE.read_text(encoding="utf-8")
    assert "the image has a Python interpreter: not a clean room" in inside
    windows = " ".join(CLEANROOM_WINDOWS.read_text(encoding="utf-8-sig").split())
    assert "-Direction Outbound -Action Block -Program $_.FullName" in windows
    assert "auditpol /set /subcategory:$wfpConnection" in windows  # Filtering Platform Connection audit
    assert r'$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;' in windows
    assert "python or uv is reachable on PATH: not a clean room" in windows
    # the Windows room never takes the runner off the network: nothing disables an adapter or isolates it
    assert not [word for word in ("Disable-NetAdapter", "--network none", "-Isolation") if word in windows]
    for lang in LANGUAGES:
        platforms = _anchored(_page(lang, "installation.md"))["platforms"]
        flat = re.sub(r"\s+", "", platforms)
        assert re.sub(r"\s+", "", NO_NETWORK_FOR_BOTH[lang]) not in flat, lang
        for room, sentence in CLEAN_ROOM[lang].items():
            assert re.sub(r"\s+", "", sentence) in flat, (lang, room)


# Why one rule covers the PDF browser: every one of its processes runs its one executable. That holds
# whatever the process layout, so the pages give this reason and need no claim about where a part runs.
ONE_EXECUTABLE = {
    "en": "The PDF browser's own process and every process it starts run `{}`, so this one rule covers all"
    " of them.",
    "zh": "PDF 浏览器自身的进程及其启动的每个进程都运行 `{}`，因此这一条规则涵盖所有这些进程。",
}
# A page that says a part of the PDF browser runs inside the browser process on Windows (the wording the
# pages had up to 901bda6) names the part; each part has the launch argument that puts it there.
IN_BROWSER_PROCESS = {"en": "inside the browser process", "zh": "浏览器进程内"}
LAYOUT_PARTS = {"en": ("GPU", "network service"), "zh": ("GPU", "网络服务")}
OLD_LAYOUT_CLAIM = {
    "en": "Every process of the PDF browser runs `chrome-headless-shell.exe`; on Windows its GPU and its"
    " network service run inside the browser process itself, so this one rule covers them.",
    "zh": "PDF 浏览器的每个进程都运行 `chrome-headless-shell.exe`；在 Windows 上，其 GPU 和网络服务就在"
    "浏览器进程内运行，因此这一条规则也涵盖它们。",
}


def _windows_launch_arguments() -> list[str]:
    """pdf.launch_arguments as the printer calls it on Windows. Up to 901bda6 the function has no Windows
    switch: it returns the same flags on every platform, and those are the Windows flags."""
    from neurogrid.kernel import pdf

    try:
        return pdf.launch_arguments(Path("work"), windows=True)  # type: ignore[call-arg, unused-ignore]
    except TypeError:  # no keyword windows (before 88b15a4, branch p5-ci2-chrome-log)
        return pdf.launch_arguments(Path("work"))


def _unbacked_layout_claims(section: str, lang: str) -> list[str]:
    """The parts of the PDF browser that the section says run inside the browser process although the
    launch arguments for Windows do not put them there (GPU: --in-process-gpu; network service: the feature
    NetworkServiceInProcess2 in --enable-features)."""
    from neurogrid.kernel import pdf

    flat = re.sub(r"\s+", "", section)
    if re.sub(r"\s+", "", IN_BROWSER_PROCESS[lang]) not in flat:
        return []
    arguments = _windows_launch_arguments()
    features = {
        feature
        for argument in arguments
        if argument.startswith("--enable-features=")
        for feature in argument.removeprefix("--enable-features=").split(",")
    }
    backed = (pdf.IN_PROCESS_GPU in arguments, "NetworkServiceInProcess2" in features)
    named = [part for part in LAYOUT_PARTS[lang] if re.sub(r"\s+", "", part) in flat]
    return [part for part, ok in zip(LAYOUT_PARTS[lang], backed, strict=True) if part in named and not ok]


def test_firewall_check_blocks_what_the_ci_blocks() -> None:
    """NG-N01, A-49: 'Check it yourself' on Windows blocks every .exe of the installation and of the PDF
    browser folder with the rule the Windows clean room adds (cleanroom_windows.ps1 Block-Executables),
    names the programs it covers and says that the PDF browser's processes all run its one executable.

    The pages said that on Windows the GPU and the network service run inside the browser process. Without
    88b15a4 (p5-ci2-chrome-log) the network service is a child process of its own (measured on Windows 11
    at 901bda6: browser, utility network.mojom.NetworkService, renderer, all chrome-headless-shell.exe), and
    the check of that claim here sat behind an inspect.signature test that skipped it without notice. The
    pages now give the reason that holds whatever the process layout; a claim about the layout is checked
    against the real launch arguments for Windows and fails here, never skipped, when the code lacks it."""
    from neurogrid.kernel import pdf

    script = " ".join(CLEANROOM_WINDOWS.read_text(encoding="utf-8-sig").split())
    assert FIREWALL_RULE.replace("neurogrid-block", '"$tag-block"') in script
    browser = Path(pdf.EXECUTABLES["win64"]).name
    for lang in LANGUAGES:
        section = _anchored(_page(lang, "privacy.md"))["check-yourself"]
        assert FIREWALL_RULE in " ".join(section.split()), lang
        assert "-Recurse -Filter *.exe" in section and r"$env:LOCALAPPDATA\NeuroGrid\pdf-browser" in section
        for program in ("neurogrid.exe", "python.exe", "deno.exe", "node.exe", browser):
            assert f"`{program}`" in section, (lang, program)
        assert "Remove-NetFirewallRule -DisplayName neurogrid-block" in section, lang
        assert "sys._base_executable" in section, lang  # the interpreter behind a venv's python.exe
        flat = re.sub(r"\s+", "", section)
        assert re.sub(r"\s+", "", ONE_EXECUTABLE[lang].format(browser)) in flat, lang
        unbacked = _unbacked_layout_claims(section, lang)
        assert not unbacked, (
            f"privacy.md ({lang}) says {unbacked} run inside the browser process on Windows, but"
            f" pdf.launch_arguments for Windows does not put them there: {_windows_launch_arguments()}"
        )


@pytest.mark.parametrize("lang", LANGUAGES)
def test_layout_claims_are_checked_against_the_windows_launch_arguments(
    lang: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NG-N01: the check above flags a layout claim exactly when the launch arguments lack its switch, with
    and without the keyword windows of launch_arguments (88b15a4), and never skips. The old wording of the
    pages names the GPU and the network service; the current wording makes no layout claim."""
    from neurogrid.kernel import pdf

    gpu = [*pdf.CHROMIUM_FLAGS, pdf.IN_PROCESS_GPU]
    network = "--enable-features=CDPScreenshotNewSurface,NetworkServiceInProcess2"

    def before(work: Path, extra_flags: Sequence[str] = ()) -> list[str]:  # no keyword windows
        return [*gpu, f"--log-file={work / 'chromium.log'}", *extra_flags]

    def after(work: Path, extra_flags: Sequence[str] = (), *, windows: bool | None = None) -> list[str]:
        return [*gpu, *([network] if windows else []), f"--log-file={work / 'chromium.log'}", *extra_flags]

    old = OLD_LAYOUT_CLAIM[lang]
    current = ONE_EXECUTABLE[lang].format("chrome-headless-shell.exe")
    monkeypatch.setattr(pdf, "launch_arguments", before)
    assert _unbacked_layout_claims(old, lang) == [LAYOUT_PARTS[lang][1]]
    assert _unbacked_layout_claims(current, lang) == []
    monkeypatch.setattr(pdf, "launch_arguments", after)
    assert _unbacked_layout_claims(old, lang) == []
    assert _unbacked_layout_claims(current, lang) == []

    def neither(work: Path, extra_flags: Sequence[str] = (), *, windows: bool | None = None) -> list[str]:
        return [*pdf.CHROMIUM_FLAGS, f"--log-file={work / 'chromium.log'}", *extra_flags]

    monkeypatch.setattr(pdf, "launch_arguments", neither)
    assert _unbacked_layout_claims(old, lang) == list(LAYOUT_PARTS[lang])


INSTALLER = ROOT / "tools" / "install_pdf_browser.py"
INSTALLER_ADDRESS = "<REPO_URL>/releases/download/v<version>/install_pdf_browser.py"
PDF_SECTION = {"en": "PDF browser", "zh": "PDF 浏览器", "de": "PDF-Browser"}


def test_pdf_browser_section_gives_the_installers_address_and_sha256() -> None:
    """p5_decisions B2, NG-N06: PyPI and source users take install_pdf_browser.py from the release; the docs
    section that the exit-2 hint names gives its address and its SHA-256 (the script of this version, kept
    current by tools/gen_docs.py) and how to compare it, and the hint of every language says so."""
    digest = hashlib.sha256(INSTALLER.read_bytes()).hexdigest()
    for lang in LANGUAGES:
        section = _anchored(_page(lang, "installation.md"))["pdf-browser"]
        assert INSTALLER_ADDRESS in section, lang
        assert digest in section, lang
        assert "sha256sum install_pdf_browser.py" in section, lang
        assert "Get-FileHash -Algorithm SHA256 install_pdf_browser.py" in section, lang
        assert "`SHA256SUMS`" in section and "(#verify)" in section, lang  # the signed list of the release
    for lang, texts in tables().items():
        hint = texts["errors.pdf.install.docs"]
        assert PDF_SECTION[lang] in hint and "install_pdf_browser.py" in hint, lang
    # every hint points to the documentation section for the address and the SHA-256, not elsewhere
    assert "(address and SHA-256 there)" not in tables()["en"]["errors.pdf.install.docs"]
    assert "that section gives its address and SHA-256" in tables()["en"]["errors.pdf.install.docs"]
    assert "该节给出其地址和 SHA-256" in tables()["zh"]["errors.pdf.install.docs"]
    assert "dieser Abschnitt nennt Adresse und SHA-256" in tables()["de"]["errors.pdf.install.docs"]


def test_rebuild_guide_names_the_windows_launch_flags_of_the_printer(tmp_path: Path) -> None:
    """Verifier finding after 88b15a4: NACHBAU.md section 1 item 11 named only --in-process-gpu, while the
    printer also passes the network-service feature on Windows. The guide must name every flag that
    launch_arguments adds beyond CHROMIUM_FLAGS on Windows and say that the network service stays a child
    process on Linux."""
    from neurogrid.kernel import pdf

    guide = (DOCS / "umsetzung" / "NACHBAU.md").read_text(encoding="utf-8")
    item = guide[guide.index("**Debug-Log der Headless Shell:**") :].split("\n\n", 1)[0]
    item = re.sub(r"\s+", " ", item)
    windows = pdf.launch_arguments(tmp_path, windows=True)
    linux = pdf.launch_arguments(tmp_path, windows=False)
    added = [f for f in windows if f not in pdf.CHROMIUM_FLAGS and not f.startswith("--log-file=")]
    assert pdf.IN_PROCESS_GPU in added and pdf.IN_PROCESS_GPU in linux
    for flag in added:
        assert f"`{flag}`" in item, f"NACHBAU.md item 11 does not name the Windows launch flag {flag}"
    assert not any(flag.startswith("--enable-features=") for flag in linux)
    assert "Unter Linux" in item and "Netzwerkdienst bleibt dort ein eigener Prozess" in item
    assert "--disable-features" in item  # never passed, it would replace Playwright's list
