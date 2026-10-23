"""MkDocs hooks of the NeuroGrid documentation (TECH-06, A-28). Loaded by mkdocs.yml, run by
tools/build_docs.py.

- Chinese search without a dictionary: Material segments Chinese text with jieba, which exists only as a
  source distribution (no wheel, A-48 no-build). Without jieba the hook splits every run of Han characters
  into single characters (joined by U+200B in the index); Material's query splitter then matches
  multi-character queries such as 采样频率 across them. Precision is lower than with word segmentation, recall
  is complete.
- The JSON schemas of NeuroGrid's files (src/neurogrid/schemas) are published under schemas/ so the pages can
  link them; the site is built from the repository, never from a copy.
- One 404 page: mkdocs-static-i18n builds the theme's 404.html for every language into the site root, so the
  last language would win; the hook keeps the page of the default language (en).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import material.plugins.search.plugin as search_plugin
from mkdocs.structure.files import File, Files

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "src" / "neurogrid" / "schemas"
DEFAULT_LANGUAGE = "en"
_not_found_pages: dict[str, str] = {}


class HanCharacters:
    """Stands in for jieba: ``cut`` yields one token per character of a run of Han characters."""

    @staticmethod
    def cut(value: bytes | str, *args: Any, **kwargs: Any) -> list[str]:
        text = value.decode("utf-8") if isinstance(value, bytes) else value
        return list(text)


def _segment_han() -> None:
    if search_plugin.jieba is None:
        search_plugin.jieba = HanCharacters()


def on_startup(command: str, dirty: bool) -> None:
    _segment_han()


def on_config(config: Any) -> Any:
    _segment_han()  # mkdocs' build() API fires on_config, not on_startup
    return config


def on_files(files: Files, config: Any) -> Files:
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        uri = f"schemas/{path.name}"
        if files.get_file_from_path(uri) is None:
            files.append(File.generated(config, uri, abs_src_path=str(path)))
    return files


def on_post_template(output_content: str, template_name: str, config: Any) -> str:
    if template_name == "404.html":
        _not_found_pages[str(config.theme["language"])] = output_content
    return output_content


def on_post_build(config: Any) -> None:
    page = _not_found_pages.get(DEFAULT_LANGUAGE)
    if page is not None:
        Path(config.site_dir, "404.html").write_text(page, encoding="utf-8", newline="\n")
