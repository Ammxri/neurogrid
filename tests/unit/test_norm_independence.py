"""This version uses no content of YY/T 2029-2026 (V-06, D-02, A-41, A-92).

The norm text was never available to the project (decision log, "Geprüfte Fakten"; there is no .local/normen),
so nothing can have been taken from it. These tests keep it that way: the only built-in rule pack that names
the norm is the placeholder scaffold yyt2029 (RP-10) with its one example rule, clause TBD and the placeholder
parameter; no check, threshold or text is based on the norm; and every line of the repository that
mentions it is a reviewed one, listed exactly in KNOWN. The decision log docs/umsetzung/ is not part of
the product and not scanned. Until P8: the clause inventory replaces the pinned scaffold (source_status
inventory, clause numbers read from the norm text), and with it test_no_builtin_pack_uses_yyt2029_content and
the KNOWN lines of the pack and of the generated pages."""

from __future__ import annotations

import re
import subprocess
from importlib import resources
from pathlib import Path

import pytest

from neurogrid.kernel.findings import Severity, SourceStatus
from neurogrid.kernel.rules import load_rulepack

ROOT = Path(__file__).resolve().parents[2]
MENTION = re.compile(r"(?i)YY\s*/?\s*T\s*2029|yyt\s*2029")
# A clause number (4.2, 5.3.1) within 40 characters after the norm's name would cite its structure.
CLAUSE = re.compile(r"(?i)(?:YY\s*/?\s*T\s*2029|yyt2029)[^\n]{0,40}?\b\d+(?:\.\d+)+")
SKIPPED_DIRS = {".git", ".venv", ".local", "site", "__pycache__", ".ruff_cache", ".mypy_cache", "umsetzung"}
# The statement of the pages index, limitations and rulepacks, one line each (A-92; phrased for the current
# version: it names the placeholder pack and no version number after the norm or the pack).
STATEMENT_EN = (
    "This version contains no content from YY/T 2029-2026. The placeholder pack yyt2029 (one example rule "
    "without clause, loaded only with `--allow-draft-rulepacks`, never counted) is not based on the norm "
    "text either; the clause-based pack follows once the norm text has been read."
)
STATEMENT_ZH = (
    "本版本不包含 YY/T 2029-2026 的任何内容。占位规则包 yyt2029（仅含一条无条款号的示例规则，须使用 "
    "`--allow-draft-rulepacks` 加载，不计入统计）同样并非依据标准原文；"
    "基于条款的规则包将在研读标准文本后提供。"
)
PACK = "yyt2029.yaml"
# Until P8: the pinned content of the scaffold (A-41: the example rule of the product specification only).
PINNED_RULES = {"YYT2029-ACQ-001"}
PINNED_CHECK = "signal.sampling_rate_consistency"
PINNED_PARAMS = {"min_hz": 500}
# Reviewed mentions: (path, the exact stripped line). A line that differs in any character is unknown.
KNOWN = {
    ("tests/unit/test_language_and_wording.py", '"通过 YY/T 2029",'),  # example the wording list must catch
    ("docs/en/index.md", STATEMENT_EN),
    ("docs/en/limitations.md", f"- {STATEMENT_EN}"),
    ("docs/en/rulepacks.md", STATEMENT_EN),
    ("docs/zh/index.md", STATEMENT_ZH),
    ("docs/zh/limitations.md", f"- {STATEMENT_ZH}"),
    ("docs/zh/rulepacks.md", STATEMENT_ZH),
    # the user pages of the scaffold: the four built-in packs, the command, the --rulepack row
    (
        "docs/en/rulepacks.md",
        "`gbt47127` (the GB/T 47127 multi-modal data format), `gxdsl008` and the placeholder pack `yyt2029`",
    ),
    ("docs/en/rulepacks.md", "neurogrid check DATA --rulepack yyt2029 --allow-draft-rulepacks"),
    (
        "docs/zh/rulepacks.md",
        "和核验方式。NeuroGrid 内置五个规则包：`core`、`bids`、`gbt47127`（GB/T 47127 多模态数据格式）、"
        "`gxdsl008` 和占位规则包 `yyt2029`",
    ),
    ("docs/zh/rulepacks.md", "neurogrid check DATA --rulepack yyt2029 --allow-draft-rulepacks"),
    (
        "docs/en/commands.md",
        "| `--rulepack NAME_OR_PATH` | Built-in pack (`core`, `bids`, `gxdsl008`, `yyt2029`) or a YAML file; "
        "repeatable. `yyt2029` is a placeholder pack and loads only with `--allow-draft-rulepacks` until its "
        "clause-based version follows ([Placeholder packs](rulepacks.md#placeholder)). |",
    ),
    (
        "docs/zh/commands.md",
        "| `--rulepack NAME_OR_PATH` | 内置规则包（`core`、`bids`、`gxdsl008`、`yyt2029`）或 YAML 文件；"
        "可重复指定。`yyt2029` 是占位规则包，在基于条款的版本提供之前只有使用 `--allow-draft-rulepacks` "
        "时才会加载（[占位规则包](rulepacks.md#placeholder)）。 |",
    ),
    (
        "tools/acceptance_g1.py",
        'NORM = "YY/T 2029"  # the norm of V-06 and D-02; the one place this tool names it '
        "(reviewed mention)",
    ),
    # the scaffold itself (A-92): header, name, source and the one rule ID; the version has its own line
    (
        "src/neurogrid/rulepacks/yyt2029.yaml",
        "# NeuroGrid rule pack yyt2029: placeholder scaffold (RP-10, A-41, A-92), "
        "not based on the norm text.",
    ),
    ("src/neurogrid/rulepacks/yyt2029.yaml", "rulepack: yyt2029"),
    ("src/neurogrid/rulepacks/yyt2029.yaml", 'source: "YY/T 2029-2026, norm text not read"'),
    ("src/neurogrid/rulepacks/yyt2029.yaml", "- id: YYT2029-ACQ-001"),
    ("tools/gen_docs.py", 'PACKS = ("core", "bids", "gbt47127", "gxdsl008", "yyt2029")'),
    # the generator's copy of CLAUSE for the interpretation questions (test_generator_guard_is_this_guard)
    (
        "tools/gen_docs.py",
        r'NORM_CLAUSE = re.compile(r"(?i)(?:YY\s*/?\s*T\s*2029|yyt2029)[^\n]{0,40}?\b\d+(?:\.\d+)+")',
    ),
    # the generated reference pages: pack heading, source row, rule heading and the check's rule column
    ("docs/en/reference/rules.md", "## Rule pack yyt2029 {#pack-yyt2029}"),
    ("docs/en/reference/rules.md", "| Source | YY/T 2029-2026, norm text not read |"),
    ("docs/en/reference/rules.md", "### YYT2029-ACQ-001 {#YYT2029-ACQ-001}"),
    ("docs/zh/reference/rules.md", "## 规则包 yyt2029 {#pack-yyt2029}"),
    ("docs/zh/reference/rules.md", "| 来源 | YY/T 2029-2026, norm text not read |"),
    ("docs/zh/reference/rules.md", "### YYT2029-ACQ-001 {#YYT2029-ACQ-001}"),
    (
        "docs/en/reference/checks.md",
        "| Built-in rules | [YYT2029-ACQ-001](rules.md#YYT2029-ACQ-001) (placeholder) |",
    ),
    ("docs/zh/reference/checks.md", "| 内置规则 | [YYT2029-ACQ-001](rules.md#YYT2029-ACQ-001)（占位） |"),
    # the tests of the scaffold name the pack and its rule once per file
    (
        "tests/unit/test_message_tables.py",
        'BUILTIN_PACKS = ("core", "bids", "gbt47127", "gxdsl008", "yyt2029")',
    ),
    (
        "tests/rules/test_builtin_rules.py",
        'YYT = ("yyt2029",)  # the placeholder scaffold, with the flag (A-92)',
    ),
    ("tests/rules/test_builtin_rules.py", 'YYT_RULE = "YYT2029-ACQ-001"'),
    ("tests/integration/test_yyt2029_scaffold.py", 'PACK = "yyt2029"'),
    ("tests/integration/test_yyt2029_scaffold.py", 'RULE = "YYT2029-ACQ-001"'),
    # the P6 cross-area tests load the scaffold with the flag (tests/integration/test_p6_cross.py)
    ("tests/integration/test_p6_cross.py", 'YYT = ("--rulepack", "yyt2029", "--allow-draft-rulepacks")'),
    ("tests/integration/test_p6_cross.py", 'assert "YYT2029-ACQ-001" in rules'),
    (
        "tests/integration/test_p6_cross.py",
        'assert {pack["name"] for pack in results["rulepacks"]} == {"core", "bids", "yyt2029"}  # rule packs',
    ),
    ("tests/integration/test_p6_cross.py", "def test_dod_two_checks_vault_consents_yyt2029_byte_identical("),
    # P9: the access log details that wait for the norm text (NV-F03) and the P9 cross-area tests
    ("docs/en/limitations.md", "depend on the text of YY/T 2029 follow once the norm text has been read."),
    ("docs/zh/limitations.md", "YY/T 2029 文本的细节将在研读标准文本后提供。"),
    ("tests/integration/test_p9_cross.py", 'YYT = ("--rulepack", "yyt2029", "--allow-draft-rulepacks")'),
    (
        "tests/integration/test_p9_cross.py",
        'assert {pack["name"] for pack in results["rulepacks"]} == {"core", "bids", "yyt2029"}',
    ),
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
    """Until P8: yyt2029 is the only pack naming the norm, a placeholder with exactly the example rule."""
    folder = resources.files("neurogrid.rulepacks")
    names = sorted(entry.name for entry in folder.iterdir() if entry.name.endswith(".yaml"))
    assert {"core.yaml", "bids.yaml", "gxdsl008.yaml", PACK} <= set(names)
    naming = []
    for name in names:
        data = folder.joinpath(name).read_bytes()
        loaded = load_rulepack(data, "builtin")
        pack = loaded.pack
        about = " ".join(
            [pack.rulepack, pack.source, *(f"{r.id} {r.title_zh} {r.title_en}" for r in pack.rules)]
        )
        if MENTION.search(about) or MENTION.search(name) or MENTION.search(data.decode("utf-8")):
            naming.append(name)
            # only as a placeholder, without clauses (RP-10, A-41)
            assert pack.source_status is SourceStatus.PLACEHOLDER, name
            assert {rule.clause for rule in pack.rules} == {"TBD"}, name
    assert naming == [PACK], naming
    scaffold = load_rulepack(folder.joinpath(PACK).read_bytes(), "builtin").pack
    assert scaffold.rulepack == "yyt2029" and scaffold.version == "0.2.0-draft"
    assert scaffold.source_status is SourceStatus.PLACEHOLDER and scaffold.norm is True
    assert {rule.id for rule in scaffold.rules} == PINNED_RULES
    for rule in scaffold.rules:
        assert rule.clause == "TBD", rule.id
        assert rule.check == PINNED_CHECK and dict(rule.params) == PINNED_PARAMS, rule.id
        assert rule.severity is Severity.ERROR and rule.strict_severity is None, rule.id


def test_yyt2029_mentions_are_known() -> None:
    mentions = _mentions()
    assert mentions, "the documentation states the independence (V-06)"
    unknown = [(name, line) for name, line in mentions if name != THIS and (name, line) not in KNOWN]
    assert not unknown, ("new or changed lines naming the norm: review each, then list it in KNOWN", unknown)
    # every reviewed line still exists: a changed or removed one leaves no stale entry behind
    stale = sorted(KNOWN - set(mentions))
    assert not stale, ("KNOWN lines no longer in the repository: remove or update the entry", stale)
    stated = {name for name, line in mentions if STATEMENT_EN in line or STATEMENT_ZH in line}
    pages = ("index", "limitations", "rulepacks")
    assert {f"docs/{lang}/{page}.md" for lang in ("en", "zh") for page in pages} <= stated


def test_no_yyt2029_clause_numbers() -> None:
    hits = [(name, line) for name, line in _mentions() if name != THIS and CLAUSE.search(line)]
    assert not hits, hits


def test_generator_guard_is_this_guard() -> None:
    """tools/gen_docs.py refuses interpretation questions that name the norm and generated lines with a
    clause number (A-92); its patterns are the ones of this file."""
    import gen_docs  # type: ignore[import-not-found]  # tools/ is on sys.path (tests/conftest.py)

    assert gen_docs.NORM_MENTION.pattern == MENTION.pattern
    assert gen_docs.NORM_CLAUSE.pattern == CLAUSE.pattern


@pytest.mark.parametrize(
    ("text", "hit"),
    [
        ("YY/T 2029-2026 clause 5.3.1 requires", True),
        ("yyt2029 4.2", True),
        ("Version 0.1 contains no content from YY/T 2029-2026.", False),
        ("0.1 版不包含 YY/T 2029-2026 的任何内容", False),
        ("follows with the yyt2029 pack in version 0.2.", True),  # hence the pages name the version first
        ("rulepack: yyt2029 version: 0.2.0-draft", True),  # hence the version has its own line or cell
        (STATEMENT_EN, False),
        (STATEMENT_ZH, False),
    ],
)
def test_clause_pattern(text: str, hit: bool) -> None:
    assert bool(CLAUSE.search(text)) is hit
