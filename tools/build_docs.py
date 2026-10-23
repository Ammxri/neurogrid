"""Build the documentation site zh/en offline and check it (TECH-06, A-28). Used locally, in CI and in
releases.

Steps: (1) the generated pages are current (tools/gen_docs.py --check); (2) SOURCE_DATE_EPOCH from the
environment, else the commit time of HEAD, so that two builds are byte-identical; (3) `mkdocs build --strict`
in-process under an audit hook that refuses every network operation; (4) the Chinese font subset: the Han
characters of all built pages, cut from the report font Noto Sans SC (A-27) into assets/fonts/*.woff; (5)
checks of the built site: both languages have the same pages, every page carries the fixed sentence of its
language (report/i18n), no page or stylesheet loads an external resource, no script holds a URL of another
host except the theme's reviewed loaders (SCRIPT_LOADERS) and no page meets the condition of one, the search
index is configured for offline use and its Chinese entries are segmented, docs/umsetzung and docs/_data are
not published, the fonts cover every character they are meant for.

Usage: python tools/build_docs.py [--site-dir site]
Exit codes: 0 built and checked, 1 a check failed, 2 the build failed (generation, fonts, network, mkdocs).
"""

from __future__ import annotations

import argparse
import html.parser
import io
import json
import logging
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "mkdocs.yml"
FONT_DIR = ROOT / "src" / "neurogrid" / "report" / "fonts"
FONTS = {400: FONT_DIR / "NotoSansSC-Regular.ttf", 700: FONT_DIR / "NotoSansSC-Bold.ttf"}
FONT_OUT = "assets/fonts/neurogrid-sc-{weight}.woff"
HINT_SCRIPT = ROOT / "docs" / "assets" / "javascripts" / "file-search-hint.js"
LANGUAGES = ("en", "zh")
NOT_PAGES = ("assets/", "search/", "schemas/", "zh/")
NOT_FOUND = "404.html"
# The unicode-range of docs/assets/stylesheets/neurogrid.css: these characters are drawn with the subset font.
CJK = re.compile("[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\ufe30-\ufe4f\uff00-\uffef]")
HAN = "\u3400-\u4dbf\u4e00-\u9fff"
NETWORK_EVENTS = {
    "socket.connect",
    "socket.getaddrinfo",
    "socket.gethostbyname",
    "socket.gethostbyaddr",
    "socket.sendto",
    "socket.sendmsg",
    "urllib.Request",
}
EXTERNAL = re.compile(r"^\s*(?:[a-z][a-z0-9+.-]*:|//)", re.I)
RESOURCE_ATTRS = {
    "script": ("src",),
    "img": ("src", "srcset"),
    "iframe": ("src",),
    "source": ("src", "srcset"),
    "video": ("src", "poster"),
    "audio": ("src",),
    "embed": ("src",),
    "object": ("data",),
    "track": ("src",),
}
LINK_RELS = {
    "stylesheet",
    "preload",
    "modulepreload",
    "preconnect",
    "prefetch",
    "dns-prefetch",
    "icon",
    "manifest",
}
CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)|@import\s+['\"]([^'\"]+)['\"]", re.I)
# A URL of another host that starts a string literal in a script (comments and messages are no loaders).
SCRIPT_URL = re.compile(r"[\"'`]((?:https?:)?//(?:\$\{|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)[^\"'`\s]*)", re.I)
# The loaders in the theme's JavaScript (mkdocs-material 9.7.7), reviewed: each runs only under its condition.
# "mermaid": a diagram (an element of class mermaid); "repository": the repository facts of repo_url (an
# element data-md-component="source"). check_site() fails for a page that meets one of them. "browser": a
# browser without the ResizeObserver interface - not decided by the site, stated in installation.md.
SCRIPT_LOADERS = {
    "https://unpkg.com/mermaid@11/dist/mermaid.min.js": "mermaid",
    "https://unpkg.com/resize-observer-polyfill": "browser",
    "https://api.github.com/": "repository",
    "https://${e}/api/v4/projects/": "repository",
}


class BuildError(Exception):
    """The site could not be built (exit 2)."""


# --- build --------------------------------------------------------------------------------------------------


def source_date_epoch() -> str:
    value = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if value:
        return value
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        out = ""
    if not out.isdigit():
        raise BuildError("SOURCE_DATE_EPOCH is not set and the commit time of HEAD is unknown")
    return out


class NetworkGuard:
    """Audit hook: any network operation during the build is recorded and refused."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.active = False

    def __call__(self, event: str, args: tuple[Any, ...]) -> None:
        if self.active and event in NETWORK_EVENTS:
            self.events.append(event)
            raise OSError(f"network access during the documentation build refused ({event})")


def run_mkdocs(site: Path, guard: NetworkGuard) -> None:
    from mkdocs.commands.build import build
    from mkdocs.config import load_config
    from mkdocs.exceptions import MkDocsException

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)-7s - %(message)s"))
    logger = logging.getLogger("mkdocs")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    guard.active = True
    try:
        config = load_config(config_file=str(CONFIG), site_dir=str(site), strict=True)
        build(config)
    except MkDocsException as exc:
        raise BuildError(f"mkdocs: {exc}") from None
    finally:
        guard.active = False
        logger.removeHandler(handler)


# --- fonts --------------------------------------------------------------------------------------------------


def used_characters(site: Path) -> set[str]:
    chars: set[str] = set()
    for path in sorted(site.rglob("*.html")):
        chars.update(CJK.findall(path.read_text(encoding="utf-8")))
    chars.update(CJK.findall(HINT_SCRIPT.read_text(encoding="utf-8")))
    return chars


def write_fonts(site: Path, chars: set[str]) -> None:
    """Subset the static report font for the characters of the site (deterministic, WOFF with zlib)."""
    from fontTools import subset
    from fontTools.ttLib import TTFont

    missing = [str(path.relative_to(ROOT)) for path in FONTS.values() if not path.is_file()]
    if missing:
        raise BuildError(f"report fonts missing: {', '.join(missing)} (tools/build_fonts.py, A-27)")
    codepoints = sorted(ord(c) for c in chars)
    for weight, path in FONTS.items():
        font = TTFont(str(path), recalcTimestamp=False, lazy=False)
        options = subset.Options()
        options.flavor = "woff"
        options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]
        options.name_languages = [0x409]
        options.recalc_timestamp = False
        options.notdef_outline = True
        options.hinting = False
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(unicodes=codepoints)
        subsetter.subset(font)
        buffer = io.BytesIO()
        font.flavor = "woff"
        font.save(buffer, reorderTables=True)
        target = site / FONT_OUT.format(weight=weight)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(buffer.getvalue())


def font_coverage(site: Path, chars: set[str]) -> list[str]:
    from fontTools.ttLib import TTFont

    problems = []
    for weight in FONTS:
        target = site / FONT_OUT.format(weight=weight)
        if not target.is_file():
            problems.append(f"font {target.name} missing")
            continue
        cmap = TTFont(str(target)).getBestCmap() or {}
        absent = sorted(c for c in chars if ord(c) not in cmap)
        if absent:
            problems.append(f"font {target.name} lacks {len(absent)} characters, e.g. {''.join(absent[:10])}")
    return problems


# --- checks of the built site -------------------------------------------------------------------------------


class _Resources(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[str] = []
        self.lang = ""
        self.loaders: set[str] = set()  # conditions of SCRIPT_LOADERS the page meets

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k: v or "" for k, v in attrs}
        if tag == "html":
            self.lang = values.get("lang", "")
        if "mermaid" in values.get("class", "").split():
            self.loaders.add("mermaid")
        if values.get("data-md-component") == "source":
            self.loaders.add("repository")
        names = RESOURCE_ATTRS.get(tag, ())
        if tag == "link" and set(values.get("rel", "").lower().split()) & LINK_RELS:
            names = ("href",)
        for name in names:
            for part in values.get(name, "").split(","):
                url = part.strip().split(" ")[0]
                if url and EXTERNAL.match(url) and not url.lower().startswith("data:"):
                    self.found.append(f"<{tag} {name}={url}>")


def pages(site: Path, lang: str) -> set[str]:
    base = site if lang == "en" else site / lang
    found = set()
    for path in base.rglob("*.html"):
        rel = path.relative_to(base).as_posix()
        if lang == "en" and rel.startswith(NOT_PAGES):
            continue
        if rel.startswith(("assets/", "search/", "schemas/")) or rel == NOT_FOUND:
            continue
        found.add(rel)
    return found


def disclaimers() -> dict[str, str]:
    sys.path.insert(0, str(ROOT / "src"))
    from neurogrid.report.texts import tables

    return {lang: tables()[lang]["disclaimer"] for lang in LANGUAGES}


def _external_in_css(text: str) -> list[str]:
    hits = []
    for match in CSS_URL.finditer(text):
        url = (match.group(1) or match.group(2) or "").strip()
        if url and EXTERNAL.match(url) and not url.lower().startswith("data:"):
            hits.append(url)
    return hits


def _external_in_script(text: str) -> list[str]:
    """URLs of other hosts a script could load that are not one of the theme's reviewed loaders."""
    found = {url for url in SCRIPT_URL.findall(text) if not url.startswith(tuple(SCRIPT_LOADERS))}
    return sorted(found)


def _han_runs_joined(text: str) -> list[str]:
    """Places where two Han characters follow each other without the U+200B segmentation."""
    return re.findall(f"[{HAN}][{HAN}]", text)


def check_site(site: Path) -> list[str]:
    problems: list[str] = []
    en, zh = pages(site, "en"), pages(site, "zh")
    if en != zh:
        problems.append(f"pages differ between en and zh: {sorted(en ^ zh)}")
    sentences = disclaimers()
    for lang, names in (("en", en), ("zh", zh)):
        base = site if lang == "en" else site / lang
        for name in sorted(names):
            text = (base / name).read_text(encoding="utf-8")
            parser = _Resources()
            parser.feed(text)
            if sentences[lang] not in text:
                problems.append(f"{lang}/{name}: fixed sentence missing")
            if parser.lang.split("-")[0] != lang:
                problems.append(f"{lang}/{name}: html lang is {parser.lang!r}")
            problems += [f"{lang}/{name}: external resource {hit}" for hit in parser.found]
            for condition in sorted(parser.loaders):
                urls = ", ".join(url for url, need in SCRIPT_LOADERS.items() if need == condition)
                problems.append(f"{lang}/{name}: external loader of the theme runs ({condition}: {urls})")
    not_found = site / NOT_FOUND  # one 404 page, in the default language (tools/mkdocs_hooks.py)
    if not not_found.is_file() or sentences["en"] not in not_found.read_text(encoding="utf-8"):
        problems.append(f"{NOT_FOUND}: missing or without the English fixed sentence")
    for css in sorted(site.rglob("*.css")):
        problems += [
            f"{css.relative_to(site).as_posix()}: external url {u}"
            for u in _external_in_css(css.read_text(encoding="utf-8"))
        ]
    for script in sorted(site.rglob("*.js")):
        problems += [
            f"{script.relative_to(site).as_posix()}: external url {u}"
            for u in _external_in_script(script.read_text(encoding="utf-8", errors="replace"))
        ]
    for forbidden in ("umsetzung", "_data"):
        if any(part == forbidden for path in site.rglob("*") for part in path.relative_to(site).parts):
            problems.append(f"{forbidden}/ is published")
    index_path = site / "search" / "search_index.json"
    if not index_path.is_file():
        problems.append("search/search_index.json missing")
    else:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        config = index.get("config", {})
        if config.get("lang") != ["en"]:
            problems.append(f"search lang is {config.get('lang')}, expected ['en']")
        if "\u200b" not in config.get("separator", ""):
            problems.append("search separator does not split at U+200B")
        zh_docs = [d for d in index.get("docs", []) if str(d.get("location", "")).startswith("zh/")]
        if not zh_docs:
            problems.append("search index holds no zh page")
        for doc in zh_docs:
            joined = _han_runs_joined(str(doc.get("title", "")) + " " + str(doc.get("text", "")))
            if joined:
                problems.append(f"search index zh entry {doc.get('location')}: Han characters not segmented")
                break
    return problems


def build_site(site: Path) -> tuple[list[str], NetworkGuard]:
    """Steps 1-5; returns the problems of the checks (empty = fine) and the guard with its events."""
    sys.path.insert(0, str(ROOT / "tools"))
    sys.path.insert(0, str(ROOT / "src"))
    import gen_docs

    if gen_docs.main(["--check"]) != 0:
        raise BuildError("generated documentation is outdated (python tools/gen_docs.py)")
    os.environ["SOURCE_DATE_EPOCH"] = source_date_epoch()
    guard = NetworkGuard()
    sys.addaudithook(guard)
    run_mkdocs(site, guard)
    chars = used_characters(site)
    guard.active = True
    try:
        write_fonts(site, chars)
    finally:
        guard.active = False
    problems = check_site(site) + font_coverage(site, chars)
    if guard.events:
        problems.append(f"network operations during the build: {sorted(set(guard.events))}")
    return problems, guard


def report(problems: Iterable[str]) -> int:
    problems = list(problems)
    for problem in problems:
        print(f"docs check: {problem}", file=sys.stderr)
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-dir", type=Path, default=ROOT / "site")
    args = parser.parse_args(argv)
    site = args.site_dir.resolve()
    try:
        problems, guard = build_site(site)
    except BuildError as exc:
        print(f"build_docs: {exc}", file=sys.stderr)
        return 2
    print(f"network events during the build: {len(guard.events)}")
    code = report(problems)
    if code == 0:
        print(f"documentation built and checked: {site}")
    return code


if __name__ == "__main__":
    sys.exit(main())
