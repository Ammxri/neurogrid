"""HTML rendering with Jinja2 (TECH-07). Templates are passed in by the product (A-23).

Autoescaping is always on: dataset-derived strings (labels, file names) are untrusted (A-53). ``finalize``
post-processes the value of every template expression before it is escaped (e.g. the report's glyph safety);
values marked safe (``Markup``) are passed to it as they are.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

Finalize = Callable[[Any], Any]


@lru_cache(maxsize=8)
def _environment(template_dir: str, finalize: Finalize | None) -> Environment:
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        finalize=finalize,
    )


def render_html(
    template_dir: Path, template: str, context: Mapping[str, Any], *, finalize: Finalize | None = None
) -> str:
    """Render ``template``. ``finalize`` should be a module-level function: environments are cached per
    template folder and finalize function."""
    return _environment(str(template_dir), finalize).get_template(template).render(**context)
