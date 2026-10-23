"""HTML rendering with Jinja2 (TECH-07). Templates are passed in by the product (A-23).

Autoescaping is always on: dataset-derived strings (labels, file names) are untrusted (A-53).
Fonts and their subsets: kernel/fonts.py; PDF printing and the PDF QA gate: kernel/pdf.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined


@lru_cache(maxsize=8)
def _environment(template_dir: str) -> Environment:
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_html(template_dir: Path, template: str, context: Mapping[str, Any]) -> str:
    return _environment(str(template_dir)).get_template(template).render(**context)
