"""The documentation states what the code does (TECH-06, POS-02, CON-05, D-03): pages are checked against the
registry, the rule packs, the configuration model, the CLI, the schemas and the language tables."""

from __future__ import annotations

import hashlib
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


DEAD_PROXY = {
    "en": "except calls to port 9 on loopback",
    "zh": "回环地址的端口 9 除外",
}


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
