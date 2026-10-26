"""The documentation site zh/en builds offline and stays offline (TECH-06, A-28, A-08)."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import docs_site  # type: ignore[import-not-found]
import pytest
import yaml

import build_docs  # type: ignore[import-not-found]
import gen_docs  # type: ignore[import-not-found]
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
    assert len(en) == 16, sorted(en)  # the page set of the documentation spec (16 per language)


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
