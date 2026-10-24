"""Version 0.1 uses no content of YY/T 2029-2026 (V-06, D-02).

The norm text was never available to the project (decision log, "Geprüfte Fakten"; there is no .local/normen),
so nothing can have been taken from it. These tests keep it that way: no built-in rule pack, check, threshold
or text of v0.1 is based on YY/T 2029, and every mention of it in the repository is a reviewed one. The
decision log docs/umsetzung/ is not part of the product and not scanned."""

from __future__ import annotations

import re
import subprocess
from importlib import resources
from pathlib import Path

import pytest
from packaging.version import Version

import neurogrid
from neurogrid.kernel.findings import SourceStatus
from neurogrid.kernel.rules import load_rulepack

ROOT = Path(__file__).resolve().parents[2]
MENTION = re.compile(r"(?i)YY\s*/?\s*T\s*2029|yyt\s*2029")
# A clause number (4.2, 5.3.1) within 40 characters after the norm's name would cite its structure.
CLAUSE = re.compile(r"(?i)(?:YY\s*/?\s*T\s*2029|yyt2029)[^\n]{0,40}?\b\d+(?:\.\d+)+")
SKIPPED_DIRS = {".git", ".venv", ".local", "site", "__pycache__", ".ruff_cache", ".mypy_cache", "umsetzung"}
STATEMENT_EN = (
    "Version 0.1 contains no content from YY/T 2029-2026. A yyt2029 rule pack follows once the norm text"
)
STATEMENT_ZH = "0.1 版不包含 YY/T 2029-2026 的任何内容。yyt2029 规则包将在研读标准文本后提供。"
# Reviewed mentions: (path, the exact text of the line part that names the norm).
KNOWN = {
    ("tests/unit/test_language_and_wording.py", '"通过 YY/T 2029",'),  # example the wording list must catch
    ("docs/en/index.md", STATEMENT_EN),
    ("docs/en/limitations.md", STATEMENT_EN),
    ("docs/en/rulepacks.md", STATEMENT_EN),
    (
        "docs/en/rulepacks.md",
        "the list of interpretation questions follows in version 0.2 with the yyt2029 pack.",
    ),
    ("docs/zh/index.md", STATEMENT_ZH),
    ("docs/zh/limitations.md", STATEMENT_ZH),
    ("docs/zh/rulepacks.md", STATEMENT_ZH),
    ("docs/zh/rulepacks.md", "解读问题清单将在 0.2 版中随 yyt2029 规则包提供。"),
}
THIS = "tests/unit/test_norm_independence.py"


def _files() -> list[str]:
    """Tracked and new (not ignored) files of the working copy; a tree walk where git is not available."""
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
        names = [name for name in listed.split("\0") if name]
    except (OSError, subprocess.CalledProcessError):
        names = [
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("*")
            if path.is_file() and not SKIPPED_DIRS & set(path.relative_to(ROOT).parts)
        ]
    return sorted(n for n in names if not n.startswith("docs/umsetzung/") and (ROOT / n).is_file())


def _mentions() -> list[tuple[str, str]]:
    found = []
    for name in _files():
        data = (ROOT / name).read_bytes()
        if b"\0" in data[:8192]:
            continue  # binary (fonts, fixtures)
        text = data.decode("utf-8", errors="replace")
        found += [(name, line.strip()) for line in text.splitlines() if MENTION.search(line)]
    return found


def test_no_builtin_pack_uses_yyt2029_content() -> None:
    folder = resources.files("neurogrid.rulepacks")
    names = sorted(entry.name for entry in folder.iterdir() if entry.name.endswith(".yaml"))
    assert {"core.yaml", "bids.yaml", "gxdsl008.yaml"} <= set(names)
    if Version(neurogrid.__version__) < Version("0.2"):
        assert not [name for name in names if MENTION.search(name)], names
    for name in names:
        loaded = load_rulepack(folder.joinpath(name).read_bytes(), "builtin")
        pack = loaded.pack
        about = " ".join(
            [pack.rulepack, pack.source, *(f"{r.id} {r.title_zh} {r.title_en}" for r in pack.rules)]
        )
        if MENTION.search(about) or MENTION.search(name):
            # from v0.2 on: only as a placeholder, without clauses (RP-10, A-41)
            assert pack.source_status is SourceStatus.PLACEHOLDER, name
            assert {rule.clause for rule in pack.rules} == {"TBD"}, name


def test_yyt2029_mentions_are_known() -> None:
    mentions = _mentions()
    assert mentions, "the documentation states the independence (V-06)"
    unknown = [
        (name, line)
        for name, line in mentions
        if name != THIS and not any(name == path and text in line for path, text in KNOWN)
    ]
    assert not unknown, unknown
    stated = {name for name, line in mentions if STATEMENT_EN in line or STATEMENT_ZH in line}
    assert {f"docs/{lang}/{page}.md" for lang in ("en", "zh") for page in ("index", "limitations")} <= stated


def test_no_yyt2029_clause_numbers() -> None:
    hits = [(name, line) for name, line in _mentions() if name != THIS and CLAUSE.search(line)]
    assert not hits, hits


@pytest.mark.parametrize(
    ("text", "hit"),
    [
        ("YY/T 2029-2026 clause 5.3.1 requires", True),
        ("yyt2029 4.2", True),
        ("Version 0.1 contains no content from YY/T 2029-2026.", False),
        ("0.1 版不包含 YY/T 2029-2026 的任何内容", False),
        ("follows with the yyt2029 pack in version 0.2.", True),  # hence the pages name the version first
    ],
)
def test_clause_pattern(text: str, hit: bool) -> None:
    assert bool(CLAUSE.search(text)) is hit
