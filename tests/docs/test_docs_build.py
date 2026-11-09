"""The documentation site zh/en builds offline and stays offline (TECH-06, A-28, A-08)."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import shutil
import typing
from pathlib import Path
from typing import Any

import docs_site  # type: ignore[import-not-found]
import jinja2
import pytest
import yaml

import build_docs  # type: ignore[import-not-found]
import gen_docs  # type: ignore[import-not-found]
import notices  # type: ignore[import-not-found]
from neurogrid.kernel.findings import SourceStatus
from neurogrid.report.texts import tables

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
LANGUAGES = ("en", "zh")
ANCHOR = re.compile(r"\{#([A-Za-z0-9_.\-]+)\}")


@pytest.fixture(scope="session")
def built_site(browser_root: Path) -> docs_site.Build:
    # below the short folder of tests/conftest.py: the browser tests open the pages as file:// URLs, which
    # fail beyond 260 characters, whatever --basetemp is (the session builds the site once, for both modules)
    return docs_site.built(browser_root)


@pytest.fixture(scope="session")
def site_builder() -> Any:
    return docs_site.build


def _pages(lang: str) -> set[str]:
    return {p.relative_to(DOCS / lang).as_posix() for p in (DOCS / lang).rglob("*.md")}


def _mkdocs() -> dict[str, Any]:
    data = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _plugin(config: dict[str, Any], name: str) -> dict[str, Any]:
    for entry in config["plugins"]:
        if isinstance(entry, dict) and name in entry:
            return dict(entry[name])
    raise AssertionError(f"plugin {name} missing")


def test_docs_build_strict_offline(built_site: Any) -> None:
    assert built_site.returncode == 0, built_site.output[-3000:]
    assert "network events during the build: 0" in built_site.output
    assert "WARNING" not in built_site.output


def test_docs_pages_exist_in_both_languages() -> None:
    en, zh = _pages("en"), _pages("zh")
    assert en == zh, sorted(en ^ zh)
    # the page set of the documentation spec (16 per language), since P6 with vault.md (A-90), since P9 with
    # ci.md (A-98)
    assert len(en) == 18 and {"vault.md", "ci.md"} <= en, sorted(en)


def test_explicit_anchors_match_between_languages() -> None:
    for name in sorted(_pages("en")):
        en = ANCHOR.findall((DOCS / "en" / name).read_text(encoding="utf-8"))
        zh = ANCHOR.findall((DOCS / "zh" / name).read_text(encoding="utf-8"))
        assert en == zh, (name, sorted(set(en) ^ set(zh)))
    metrics = ANCHOR.findall((DOCS / "en" / "metrics.md").read_text(encoding="utf-8"))
    assert [a for a in metrics if re.fullmatch(r"M\d\d", a)] == [f"M{n:02d}" for n in range(1, 15)]


def test_generated_docs_are_current() -> None:
    assert gen_docs.main(["--check"]) == 0


def test_generated_pages_say_so_and_render_the_registry() -> None:
    for lang in LANGUAGES:
        for name in ("checks.md", "rules.md"):
            text = (DOCS / lang / "reference" / name).read_text(encoding="utf-8")
            assert text.startswith(gen_docs.HEADER), (lang, name)
        checks = (DOCS / lang / "reference" / "checks.md").read_text(encoding="utf-8")
        assert "## signal.sampling_rate_min {#signal.sampling_rate_min}" in checks
        assert "`min_hz`" in checks
        rules = (DOCS / lang / "reference" / "rules.md").read_text(encoding="utf-8")
        assert (
            "### CORE-M07-01 {#CORE-M07-01}" in rules and "### GXDSL008-ACQ-001 {#GXDSL008-ACQ-001}" in rules
        )


def test_generator_documents_every_builtin_pack_and_marks_placeholders() -> None:
    """NG-F11, A-41, A-92: the generated pages cover every built-in pack; a placeholder pack's clause is the
    report's placeholder text and its rule IDs carry the placeholder marker on the check registry page."""
    folder = ROOT / "src" / "neurogrid" / "rulepacks"
    shipped = {p.name.removesuffix(".yaml") for p in folder.glob("*.yaml")}
    assert shipped == set(gen_docs.PACKS)
    placeholders = [p.pack for p in gen_docs.builtin_packs() if p.pack.source_status.value == "placeholder"]
    assert placeholders, "the scaffold is a built-in placeholder pack"
    for lang in LANGUAGES:
        labels = gen_docs.context(lang).labels["rules"]
        rules = (DOCS / lang / "reference" / "rules.md").read_text(encoding="utf-8")
        checks = (DOCS / lang / "reference" / "checks.md").read_text(encoding="utf-8")
        clause_row = f"| {labels['clause']} | {tables()[lang]['report.value.placeholder_clause']} |"
        for pack in placeholders:
            start = rules.index(f"{{#pack-{pack.rulepack}}}")
            end = rules.find("\n## ", start)
            section = rules[start : end if end >= 0 else len(rules)]
            assert section.count(clause_row) == len(pack.rules), lang
            assert f"| {labels['version']} | {pack.version} |" in section  # the version in a row of its own
            for rule in pack.rules:
                assert f"[{rule.id}](rules.md#{rule.id}){labels['placeholder_suffix']}" in checks, lang
        # no other pack gets the marker
        assert checks.count(labels["placeholder_suffix"]) == sum(len(p.rules) for p in placeholders)


def test_placeholder_flag_is_documented_where_packs_are_chosen() -> None:
    """RP-10, A-41: every place that loads rule packs (the --rulepack option, [check] rulepacks) says that a
    placeholder pack needs --allow-draft-rulepacks and links the placeholder section."""
    flag, link = "`--allow-draft-rulepacks`", "#placeholder)"
    for lang in LANGUAGES:
        commands = (DOCS / lang / "commands.md").read_text(encoding="utf-8")
        (option,) = [
            line for line in commands.splitlines() if line.startswith("| `--rulepack NAME_OR_PATH` |")
        ]
        configuration = (DOCS / lang / "configuration.md").read_text(encoding="utf-8")
        check = configuration[configuration.index("{#check}") :]
        (key,) = [line for line in check.splitlines() if line.startswith("| `rulepacks` |")]
        for row in (option, key):
            assert flag in row and f"rulepacks.md{link}" in row, (lang, row)
        assert "{#placeholder}" in (DOCS / lang / "rulepacks.md").read_text(encoding="utf-8")


# --- interpretation questions (RP-08 template, A-92) -------------------------------------------------------


def _placeholder_pack() -> Any:
    (pack,) = [p.pack for p in gen_docs.builtin_packs() if p.pack.source_status.value == "placeholder"]
    return pack


def _builtin() -> dict[str, Any]:
    return {loaded.pack.rulepack: loaded.pack for loaded in gen_docs.builtin_packs()}


def _entry(**changes: Any) -> dict[str, Any]:
    """A valid entry for the placeholder pack, in own words (test data, not shipped)."""
    pack = _placeholder_pack()
    entry: dict[str, Any] = {
        "id": "IQ-001",
        "rulepack": pack.rulepack,
        "clause": "TBD",
        "rules": [pack.rules[0].id],
        "topic_en": "Which recordings the minimum rate applies to",
        "topic_zh": "最低采样率适用于哪些记录",
        "question_en": "Does the minimum rate apply to every EEG channel or to the recording as a whole?",
        "question_zh": "最低采样率是适用于每个 EEG 通道，还是适用于整条记录？",
        "readings": [
            {"id": "a", "en": "every EEG channel", "zh": "每个 EEG 通道"},
            {"id": "b", "en": "the recording as a whole", "zh": "整条记录"},
        ],
        "chosen": "a",
        "rationale_en": "The stricter reading until the text is read.",
        "rationale_zh": "在研读文本之前采用较严格的解读。",
        "status": "asked",
        "asked": [{"role": "test_institute", "date": "2026-11-02"}],
        "effect": "none",
    }
    entry.update(changes)
    return entry


def test_interpretation_questions_template() -> None:
    """The shipped file is valid and holds the open questions of GB/T 47127 (P7, A-116); its block in
    rulepacks.md shows each of them and not the empty text (en/zh). A valid entry renders its clause,
    readings and role, never a person."""
    shipped = gen_docs.load_questions(gen_docs.QUESTIONS)
    assert shipped.format_version == 1 and [q.id for q in shipped.questions] == [
        f"IQ-00{n}" for n in range(1, 6)
    ]
    assert {(q.rulepack, q.status, q.effect) for q in shipped.questions} == {("gbt47127", "open", "none")}
    raw = yaml.safe_load(gen_docs.QUESTIONS.read_text(encoding="utf-8"))
    assert raw["format_version"] == 1 and len(raw["questions"]) == len(shipped.questions)
    for lang in LANGUAGES:
        labels = gen_docs.context(lang).labels["questions"]
        page = (DOCS / lang / "rulepacks.md").read_text(encoding="utf-8")
        block = page[page.index("<!-- BEGIN GENERATED interpretation questions -->") :]
        block = block[: block.index("<!-- END GENERATED -->")]
        assert " ".join(str(labels["empty"]).split()) not in block and str(labels["title"]) in block
        assert all(f"{{#{q.id}}}" in block for q in shipped.questions), lang
        assert str(labels["empty"]).strip(), lang
        assert page.index("{#feedback}") < page.index("<!-- BEGIN GENERATED interpretation questions -->")
        for name in (*gen_docs.QUESTION_STATUSES, *(f"role_{r}" for r in gen_docs.ASKED_ROLES)):
            key = name if name.startswith("role_") else f"status_{name}"
            assert str(labels[key]).strip(), (lang, key)
        for effect in gen_docs.EFFECTS:
            assert str(labels[f"effect_{effect}"]).strip(), (lang, effect)
    for field, values in (
        ("status", gen_docs.QUESTION_STATUSES),
        ("effect", gen_docs.EFFECTS),
    ):
        assert typing.get_args(gen_docs.Question.model_fields[field].annotation) == values
    assert typing.get_args(gen_docs.Asked.model_fields["role"].annotation) == gen_docs.ASKED_ROLES
    valid = gen_docs.validate_questions({"format_version": 1, "questions": [_entry()]}, _builtin())
    assert valid.questions[0].asked[0].role == "test_institute"


def test_interpretation_question_block_renders_an_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "interpretation_questions.yaml"
    path.write_text(yaml.safe_dump({"format_version": 1, "questions": [_entry()]}), encoding="utf-8")
    monkeypatch.setattr(gen_docs, "QUESTIONS", path)
    env = gen_docs.environment()
    for lang in LANGUAGES:
        ctx = gen_docs.context(lang)
        labels = ctx.labels["questions"]
        block = gen_docs.questions_block(ctx, env)
        assert "#### IQ-001 {#IQ-001}" in block and str(labels["empty"]) not in block
        assert f"| {labels['clause']} | TBD |" in block
        assert f"| {labels['asked']} | {labels['role_test_institute']} (2026-11-02) |" in block
        assert f"| {labels['status']} | {labels['status_asked']} |" in block
        reading = "每个 EEG 通道" if lang == "zh" else "every EEG channel"
        assert f"(a) {reading}; (b)" in block


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("unknown_rule", "rules not in"),
        ("unknown_pack", "no built-in rule pack"),
        ("chosen_not_in_readings", "chosen reading"),
        ("one_reading", "readings"),
        ("answered_without_answer", "needs answer_en and answer_zh"),
        ("clause_number_while_placeholder", "clause of a placeholder pack is TBD"),
        ("han_in_en", "Chinese text in question_en"),
        ("han_in_reading_en", "Chinese text in readings.1.en"),
        ("forbidden_word", "wording list"),
        ("forbidden_word_zh", "wording list"),
        ("asked_with_name", "asked.0.role"),
        ("asked_bad_date", "asked.0.date"),
        ("duplicate_id", "duplicate id"),
        ("duplicate_rule", "duplicate rule id"),
        ("ideograph_ext_b_in_en", "Chinese text in topic_en"),
        ("compatibility_ideograph_in_en", "Chinese text in rationale_en"),
        ("fullwidth_comma_in_en", "Chinese text in question_en"),
        ("ideographic_full_stop_in_reading_en", "Chinese text in readings.0.en"),
        ("norm_in_topic_en", "topic_en names the norm or the pack"),
        ("pack_and_clause_in_topic_en", "topic_en names the norm or the pack"),
        ("norm_in_question_zh", "question_zh names the norm or the pack"),
        ("pack_in_reading_zh", "readings.1.zh names the norm or the pack"),
        ("bad_id", "questions.0.id"),
        ("extra_field", "questions.0.reviewer"),
        ("format_version", "format_version"),
    ],
)
def test_interpretation_questions_rejects(
    case: str, message: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every rule of the format is enforced; an invalid file ends the generator with exit 2."""
    pack = _placeholder_pack()
    entries = [_entry()]
    version: object = 1
    if case == "unknown_rule":
        entries = [_entry(rules=["NOPE-ACQ-001"])]
    elif case == "unknown_pack":
        entries = [_entry(rulepack="nosuch")]
    elif case == "chosen_not_in_readings":
        entries = [_entry(chosen="c")]
    elif case == "one_reading":
        entries = [_entry(readings=[{"id": "a", "en": "every EEG channel", "zh": "每个 EEG 通道"}])]
    elif case == "answered_without_answer":
        entries = [_entry(status="answered", answer_en="Every channel.")]
    elif case == "clause_number_while_placeholder":
        entries = [_entry(clause="4.2")]
    elif case == "han_in_en":
        entries = [_entry(question_en="Does 最低采样率 apply to every channel?")]
    elif case == "han_in_reading_en":
        readings = [
            {"id": "a", "en": "every channel", "zh": "每个通道"},
            {"id": "b", "en": "整条", "zh": "整条"},
        ]
        entries = [_entry(readings=readings)]
    elif case == "forbidden_word":
        entries = [_entry(rationale_en="A dataset with this rate is compliant.")]
    elif case == "forbidden_word_zh":
        entries = [_entry(answer_zh="数据合格。", answer_en="Answered.", status="answered")]
    elif case == "asked_with_name":
        entries = [_entry(asked=[{"role": "Dr. Wang", "date": "2026-11-02"}])]
    elif case == "asked_bad_date":
        entries = [_entry(asked=[{"role": "regulator", "date": "02.11.2026"}])]
    elif case == "duplicate_rule":
        entries = [_entry(rules=[pack.rules[0].id, pack.rules[0].id])]
    elif case == "ideograph_ext_b_in_en":
        entries = [_entry(topic_en="Which recordings \U00020000 applies to")]
    elif case == "compatibility_ideograph_in_en":
        entries = [_entry(rationale_en="The stricter reading 豈 until the text is read.")]
    elif case == "fullwidth_comma_in_en":
        entries = [_entry(question_en="Every EEG channel， or the recording as a whole?")]
    elif case == "ideographic_full_stop_in_reading_en":
        readings = [
            {"id": "a", "en": "every EEG channel。", "zh": "每个 EEG 通道"},
            {"id": "b", "en": "the recording as a whole", "zh": "整条记录"},
        ]
        entries = [_entry(readings=readings)]
    elif case == "norm_in_topic_en":
        entries = [_entry(topic_en="What " + "YY/T " + "2029 means by the minimum rate")]
    elif case == "pack_and_clause_in_topic_en":
        entries = [_entry(topic_en=pack.rulepack + " " + "4.2" + " minimum rate")]
    elif case == "norm_in_question_zh":
        entries = [_entry(question_zh="YY/T" + "2029 中的最低采样率是否适用于每个通道？")]
    elif case == "pack_in_reading_zh":
        readings = [
            {"id": "a", "en": "every EEG channel", "zh": "每个 EEG 通道"},
            {"id": "b", "en": "the recording as a whole", "zh": pack.rulepack.upper() + " 的整条记录"},
        ]
        entries = [_entry(readings=readings)]
    elif case == "duplicate_id":
        entries = [_entry(), _entry()]
    elif case == "bad_id":
        entries = [_entry(id="Q1")]
    elif case == "extra_field":
        entries = [_entry(reviewer="someone")]
    elif case == "format_version":
        version = 2
    data = {"format_version": version, "questions": entries}
    with pytest.raises(gen_docs.DocsError) as info:
        gen_docs.validate_questions(data, _builtin())
    assert message in str(info.value), str(info.value)
    assert pack.rulepack  # the cross-checks ran against the built-in packs
    # the same file through the generator: exit 2, nothing written
    path = tmp_path / "interpretation_questions.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(gen_docs, "QUESTIONS", path)
    assert gen_docs.main(["--check"]) == 2


def test_interpretation_questions_accept_latin_typography_in_en() -> None:
    """Negative of the script rule: dashes, typographic quotes, micro sign and comparison signs are no
    Chinese; the rule IDs and the pack name may name the pack (only the texts may not)."""
    text = "Does “minimum” mean ≥ 500 Hz – for every channel (µV scale)?"
    parsed = gen_docs.validate_questions(
        {"format_version": 1, "questions": [_entry(question_en=text)]}, _builtin()
    )
    entry = parsed.questions[0]
    assert entry.question_en == text and gen_docs.NORM_MENTION.search(entry.rules[0] + entry.rulepack)


def test_interpretation_question_block_refuses_a_clause_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No generated line names the pack with a dotted number after it (V-06), whatever the template puts on
    one line: here the pack and the version of the change."""
    path = tmp_path / "interpretation_questions.yaml"
    entry = _entry(effect="params", changed_in="0.3.0")
    path.write_text(yaml.safe_dump({"format_version": 1, "questions": [entry]}), encoding="utf-8")
    monkeypatch.setattr(gen_docs, "QUESTIONS", path)
    one_line = "{% for q in questions %}{{ q.rulepack }}: {{ q.effect }}\n{% endfor %}"
    env = gen_docs.environment()
    env.loader = jinja2.DictLoader({"questions.md.j2": one_line})
    with pytest.raises(gen_docs.DocsError, match="cites a clause number"):
        gen_docs.questions_block(gen_docs.context("en"), env)
    # the shipped template keeps the pack and the version in rows of their own
    block = gen_docs.questions_block(gen_docs.context("en"), gen_docs.environment())
    assert "(0.3.0)" in block and not any(gen_docs.NORM_CLAUSE.search(line) for line in block.splitlines())


def test_interpretation_questions_accept_a_clause_for_an_inventory_pack() -> None:
    """Negative of the placeholder rule: once a pack is no placeholder, its clause may be a number (P8)."""
    pack = _placeholder_pack()
    inventory = pack.model_copy(update={"source_status": SourceStatus.INVENTORY})
    parsed = gen_docs.validate_questions(
        {"format_version": 1, "questions": [_entry(clause="4.2")]}, {pack.rulepack: inventory}
    )
    assert parsed.questions[0].clause == "4.2"


def test_generator_refuses_an_outdated_or_incomplete_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--check finds a hand edit; a custom comparison without its documented 'passes' text is an error."""
    original = (DOCS / "en" / "reference" / "checks.md").read_text(encoding="utf-8")
    copy = tmp_path / "docs"
    shutil.copytree(DOCS, copy, ignore=shutil.ignore_patterns("umsetzung"))
    (copy / "en" / "reference" / "checks.md").write_text(original + "\nhand edit\n", encoding="utf-8")
    monkeypatch.setattr(gen_docs, "DOCS", copy)
    monkeypatch.setattr(gen_docs, "DATA", copy / "_data")
    monkeypatch.setattr(gen_docs, "ROOT", tmp_path)
    assert gen_docs.main(["--check"]) == 1
    data = (copy / "_data" / "checks.en.yaml").read_text(encoding="utf-8")
    (copy / "_data" / "checks.en.yaml").write_text(
        data.replace('  passes: "no other recording of the dataset has the same signal hash"\n', ""),
        encoding="utf-8",
    )
    assert gen_docs.main(["--check"]) == 2


def test_site_loads_no_external_resource(built_site: Any, tmp_path: Path) -> None:
    assert built_site.returncode == 0
    problems = build_docs.check_site(built_site.site)
    assert not [p for p in problems if "external" in p], problems
    # the check itself finds an external script, stylesheet and CSS url
    copy = tmp_path / "site"
    shutil.copytree(built_site.site, copy)
    page = copy / "zh" / "index.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            "</head>",
            '<script src="https://unpkg.com/x.js"></script>'
            '<link rel="stylesheet" href="//cdn.x/y.css"></head>',
        ),
        encoding="utf-8",
    )
    css = copy / "assets" / "stylesheets" / "neurogrid.css"
    css.write_text(
        css.read_text(encoding="utf-8") + '\n@import "https://fonts.example/x.css";\n', encoding="utf-8"
    )
    found = [p for p in build_docs.check_site(copy) if "external" in p]
    assert len(found) == 3, found


def test_scripts_hold_only_the_reviewed_loaders(built_site: Any, tmp_path: Path) -> None:
    """The theme's JavaScript keeps loaders for unpkg.com and the GitHub/GitLab APIs; each runs only under its
    condition, and no page meets the ones the site decides (diagram, repository facts). Any other script URL
    of another host, and a page that would start a loader, fail the build check."""
    assert built_site.returncode == 0
    scripts = "".join(p.read_text(encoding="utf-8", errors="replace") for p in built_site.site.rglob("*.js"))
    found = set(build_docs.SCRIPT_URL.findall(scripts))
    for prefix in build_docs.SCRIPT_LOADERS:  # every reviewed entry is still in the theme (no stale review)
        assert any(url.startswith(prefix) for url in found), prefix
    assert not [p for p in build_docs.check_site(built_site.site) if "loader" in p or ".js:" in p]
    for lang in LANGUAGES:  # the one condition the site cannot rule out is stated where the site is opened
        install = (DOCS / lang / "installation.md").read_text(encoding="utf-8")
        assert "ResizeObserver" in install and "`unpkg.com`" in install, lang
    assert set(build_docs.SCRIPT_LOADERS.values()) == {"mermaid", "repository", "browser"}
    assert build_docs.SCRIPT_URL.findall('a="x"//nbsp and emsp\n/* see https://lunrjs.com */') == []
    copy = tmp_path / "site"
    shutil.copytree(built_site.site, copy)
    (copy / "assets" / "javascripts" / "extra.js").write_text(
        'fetch("https://cdn.example.org/x.json");load(`//cdn.example.org/${name}.js`)', encoding="utf-8"
    )
    page = copy / "zh" / "metrics.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            "</article>",
            '<pre class="mermaid">graph</pre><div data-md-component="source"></div></article>',
            1,
        ),
        encoding="utf-8",
    )
    problems = build_docs.check_site(copy)
    assert "assets/javascripts/extra.js: external url https://cdn.example.org/x.json" in problems
    assert "assets/javascripts/extra.js: external url //cdn.example.org/${name}.js" in problems
    mermaid = "https://unpkg.com/mermaid@11/dist/mermaid.min.js"
    assert f"zh/metrics.html: external loader of the theme runs (mermaid: {mermaid})" in problems
    repository = [
        p for p in problems if p.startswith("zh/metrics.html: external loader of the theme runs (rep")
    ]
    assert repository == [
        "zh/metrics.html: external loader of the theme runs "
        "(repository: https://api.github.com/, https://${e}/api/v4/projects/)"
    ]


def test_mkdocs_config_is_offline() -> None:
    config = _mkdocs()
    assert config["theme"]["font"] is False
    assert "repo_url" not in config and "edit_uri" not in config
    assert config["extra"]["generator"] is False
    assert config["use_directory_urls"] is False and config["strict"] is True
    names = {next(iter(p)) if isinstance(p, dict) else p for p in config["plugins"]}
    assert names == {"search", "i18n"}, names  # no offline, privacy, social or info plugin
    search = _plugin(config, "search")
    assert search["lang"] == "en" and "\u200b" in search["separator"]
    i18n = _plugin(config, "i18n")
    assert i18n["reconfigure_search"] is False and i18n["fallback_to_default"] is False
    assert i18n["docs_structure"] == "folder"
    assert {"umsetzung/", "_data/"} <= set(config["exclude_docs"].split())


def test_docs_use_no_mermaid_or_math() -> None:
    for lang in LANGUAGES:
        for name in _pages(lang):
            text = (DOCS / lang / name).read_text(encoding="utf-8")
            assert "```mermaid" not in text and "$$" not in text, (lang, name)


def test_every_page_carries_the_fixed_sentence(built_site: Any, tmp_path: Path) -> None:
    sentences = {lang: tables()[lang]["disclaimer"] for lang in LANGUAGES}
    i18n = _plugin(_mkdocs(), "i18n")
    for language in i18n["languages"]:
        assert language["copyright"].startswith(sentences[language["locale"]]), language["locale"]
    assert built_site.returncode == 0
    for lang in LANGUAGES:
        base = built_site.site if lang == "en" else built_site.site / lang
        for page in build_docs.pages(built_site.site, lang):
            assert sentences[lang] in (base / page).read_text(encoding="utf-8"), (lang, page)
    copy = tmp_path / "site"
    shutil.copytree(built_site.site, copy)
    page = copy / "zh" / "terms.html"
    page.write_text(page.read_text(encoding="utf-8").replace(sentences["zh"], "x"), encoding="utf-8")
    assert "zh/terms.html: fixed sentence missing" in build_docs.check_site(copy)


def test_zh_search_index_is_segmented(built_site: Any) -> None:
    assert built_site.returncode == 0
    index = json.loads((built_site.site / "search" / "search_index.json").read_text(encoding="utf-8"))
    assert index["config"]["lang"] == ["en"]
    zh = [doc for doc in index["docs"] if doc["location"].startswith("zh/")]
    assert zh and all(not build_docs._han_runs_joined(doc["text"]) for doc in zh)
    assert any("采\u200b样\u200b率" in doc["text"] for doc in zh)


def test_umsetzung_is_not_published(built_site: Any) -> None:
    assert built_site.returncode == 0
    parts = {part for path in built_site.site.rglob("*") for part in path.relative_to(built_site.site).parts}
    assert "umsetzung" not in parts and "_data" not in parts
    assert not list(built_site.site.rglob("ENTSCHEIDUNGEN*"))


def test_the_report_font_is_subset_for_the_used_characters(built_site: Any) -> None:
    assert built_site.returncode == 0
    from fontTools.ttLib import TTFont

    used = build_docs.used_characters(built_site.site)
    assert "采" in used
    for weight in (400, 700):
        font = TTFont(str(built_site.site / build_docs.FONT_OUT.format(weight=weight)))
        assert font.flavor == "woff"
        cmap = font.getBestCmap()
        assert {ord(c) for c in used} <= set(cmap)
        assert len(cmap) < 3000  # a subset, not the whole font
        names = {record.nameID for record in font["name"].names}
        assert {0, 13, 14} <= names  # copyright, licence and licence URL stay (OFL, A-27)


def test_network_guard_refuses_during_the_build_only() -> None:
    guard = build_docs.NetworkGuard()
    guard("socket.connect", ())
    assert guard.events == []
    guard.active = True
    with pytest.raises(OSError):
        guard("socket.getaddrinfo", ("example.org", 443))
    guard("open", ("x",))
    assert guard.events == ["socket.getaddrinfo"]


def test_builds_are_byte_identical(built_site: Any, site_builder: Any, tmp_path: Path) -> None:
    assert built_site.returncode == 0
    second = site_builder(tmp_path / "site")
    assert second.returncode == 0, second.output[-2000:]

    def digest(root: Path) -> dict[str, str]:
        return {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*")
            if p.is_file()
        }

    assert digest(built_site.site) == digest(second.site)


def test_installer_block_follows_the_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B2: the address and SHA-256 of install_pdf_browser.py on the installation pages are generated from the
    script itself; a changed script makes --check fail until the pages are generated again."""
    assert gen_docs.main(["--check"]) == 0
    changed = tmp_path / "install_pdf_browser.py"
    changed.write_bytes(gen_docs.INSTALLER.read_bytes() + b"# changed\n")
    monkeypatch.setattr(gen_docs, "INSTALLER", changed)
    assert gen_docs.main(["--check"]) == 1
    digest = hashlib.sha256(changed.read_bytes()).hexdigest()
    assert gen_docs.installer_block() == (f"```text\n{gen_docs.INSTALLER_ADDRESS}\nSHA-256: {digest}\n```\n")


def test_site_ships_only_reviewed_permissive_parts(built_site: Any, tmp_path: Path) -> None:
    """R19, TECH-10, D-05: the lunr language files (lunr-languages under MPL, tinyseg, wordcut), which the
    English-only search never loads, and the source maps are not shipped; every other file is NeuroGrid's
    own or covered by the licence review of the installed theme, and a file nobody reviewed, a pruned file
    or a script with a copyleft licence header fails the build check."""
    assert built_site.returncode == 0, built_site.output[-3000:]
    site = built_site.site
    assert not (site / "assets" / "javascripts" / "lunr").exists()
    assert not list(site.rglob("*.map"))
    review = build_docs.theme_review()
    assert build_docs.check_site_licences(site, review) == []
    copy = tmp_path / "site"
    shutil.copytree(site, copy)
    (copy / "assets" / "javascripts" / "extra.min.js").write_text("var a=1;", encoding="utf-8")
    (copy / "assets" / "javascripts" / "lunr" / "min").mkdir(parents=True)
    (copy / "assets" / "javascripts" / "lunr" / "min" / "lunr.de.min.js").write_text(
        "/*! Lunr languages, Copyright 2014, Mihai Valentin http://www.mozilla.org/MPL/ */", encoding="utf-8"
    )
    bundle = next((copy / "assets" / "javascripts").glob("bundle.*.min.js"))
    bundle.write_text(
        bundle.read_text(encoding="utf-8") + "\n/*! SPDX-License-Identifier: LGPL-3.0 */", "utf-8"
    )
    problems = build_docs.check_site_licences(copy, review)
    assert (
        "assets/javascripts/extra.min.js: third-party file without licence review (license-gate/third_party)"
        in problems
    )
    assert "assets/javascripts/lunr/min/lunr.de.min.js: pruned by the licence review but shipped" in problems
    assert f"{bundle.relative_to(copy).as_posix()}: names a copyleft licence (MPL, GPL, LGPL)" in problems
    for favicon in copy.rglob("favicon.png"):
        favicon.unlink()
    assert "licence review: assets/images/favicon.png matches no file of the site (stale review)" in (
        build_docs.check_site_licences(copy, review)
    )


def test_the_build_log_names_each_site_licence_still_pending(built_site: Any) -> None:
    """R19: a part of the site whose licence waits for the owner does not fail the docs build, but every build
    names it, and its known_missing.toml entry stops the release. Since D-17 no part waits any more
    (focus-visible and material-design-color have their texts), so the build names none."""
    review = build_docs.theme_review()
    lines = build_docs.pending_licences(review)
    pending = {p.name: p.pending for p in review.packages if p.pending}
    gaps = {item["component"] for item in notices.load_known_missing()}
    assert set(pending.values()) <= gaps
    assert lines == sorted(lines) and len(lines) == len(pending)
    for line in lines:
        assert line in built_site.output, line
    assert not pending and "licence pending" not in built_site.output
    waiting = dataclasses.replace(
        review,
        packages=tuple(
            dataclasses.replace(p, pending="docs-site:x") if p.name == "focus-visible" else p
            for p in review.packages
        ),
    )
    assert build_docs.pending_licences(waiting) == [
        "licence pending (blocks the release, STOPP G1): focus-visible (docs-site:x)"
    ]


def test_prune_removes_the_reviewed_files_only(tmp_path: Path) -> None:
    review = build_docs.theme_review()
    lunr = tmp_path / "assets" / "javascripts" / "lunr" / "min"
    lunr.mkdir(parents=True)
    (lunr / "lunr.de.min.js").write_text("x", encoding="utf-8")
    (tmp_path / "assets" / "javascripts" / "lunr" / "wordcut.js").write_text("x", encoding="utf-8")
    (tmp_path / "assets" / "javascripts" / "bundle.1.min.js").write_text("x", encoding="utf-8")
    (tmp_path / "assets" / "javascripts" / "bundle.1.min.js.map").write_text("{}", encoding="utf-8")
    removed = build_docs.prune(tmp_path, review)
    assert removed == [
        "assets/javascripts/bundle.1.min.js.map",
        "assets/javascripts/lunr/min/lunr.de.min.js",
        "assets/javascripts/lunr/wordcut.js",
    ]
    assert not (tmp_path / "assets" / "javascripts" / "lunr").exists()
    assert (tmp_path / "assets" / "javascripts" / "bundle.1.min.js").is_file()


def test_licence_pages_and_footer_name_the_site_parts() -> None:
    """R19: CC BY 4.0 covers NeuroGrid's own text; the theme, scripts, icons and font of the site keep their
    own licences, which the licence page names and the footer points to."""
    footers = {item["locale"]: item["copyright"] for item in _plugin(_mkdocs(), "i18n")["languages"]}
    assert "Documentation text: CC BY 4.0" in footers["en"] and "Theme and scripts:" in footers["en"]
    assert "文档文本：CC BY 4.0" in footers["zh"] and "主题与脚本" in footers["zh"]
    for lang in LANGUAGES:
        page = (DOCS / lang / "license.md").read_text(encoding="utf-8")
        for name in (
            "mkdocs-material",
            "lunr",
            "rxjs",
            "Font Awesome Free",
            "Material Design Icons",
            "Octicons",
        ):
            assert name in page, (lang, name)
        assert "THIRD_PARTY_NOTICES.txt" in page and "CC BY 4.0" in page, lang
