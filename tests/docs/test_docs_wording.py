"""The documentation makes no conformity claim (POS-01, A-57): the list of report/wording/forbidden.yaml
applies to every page, the generator data and the site configuration; the fixed sentence and the reviewed
negations of the list's 'allowed' entries are the only exceptions. docs/umsetzung is not part of the
documentation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from neurogrid.kernel.safety import load_yaml
from neurogrid.report.texts import tables

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ROOT / "src" / "neurogrid" / "report" / "wording" / "forbidden.yaml"


def _lists() -> tuple[list[re.Pattern[str]], list[str]]:
    data = load_yaml(FORBIDDEN.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    patterns = [re.compile(p) for lang, group in data.items() if lang != "allowed" for p in group]
    allowed = [tables()[lang]["disclaimer"] for lang in ("zh", "en", "de")] + list(data["allowed"])
    return patterns, allowed


def _sources() -> list[Path]:
    docs = ROOT / "docs"
    paths = [*sorted((docs / "en").rglob("*.md")), *sorted((docs / "zh").rglob("*.md"))]
    paths += [*sorted((docs / "_data").glob("*.yaml")), ROOT / "mkdocs.yml"]
    paths += sorted((docs / "assets").rglob("*.js"))
    return paths


def _hits(text: str) -> list[str]:
    patterns, allowed = _lists()
    for sentence in allowed:
        text = re.sub(re.escape(sentence), "", text, flags=re.IGNORECASE)
    return [p.pattern for p in patterns if p.search(text)]


@pytest.mark.parametrize("path", _sources(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_documentation_makes_no_conformity_claim(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert not _hits(text), (path.name, _hits(text))


def test_scan_covers_both_languages_and_catches_claims() -> None:
    names = {p.relative_to(ROOT).as_posix() for p in _sources()}
    assert {"docs/en/index.md", "docs/zh/index.md", "mkdocs.yml", "docs/_data/labels.zh.yaml"} <= names
    assert _hits("The dataset is compliant with the norm.") and _hits("数据集符合标准要求")
    assert _hits("通过 GB/T 47127 认证") and not _hits("NeuroGrid performs no conformity assessment.")
    # a wrapped line breaks the allowed phrase: the pages keep each allowed negation on one line
    assert _hits("NeuroGrid performs no conformity\nassessment.")
