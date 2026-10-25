"""The zh review package (A-07, STOPP G1, tools/zh_review_package.py): every Chinese string NeuroGrid ships,
with its source and key, marked when added or changed since P1. Completeness is checked against the tracked
files themselves: a new file with Chinese text that is neither a source of the package nor on the reviewed
list of non-displayed texts fails here."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

import zh_review_package as zh  # type: ignore[import-not-found]
from neurogrid.kernel.i18n import flatten
from neurogrid.kernel.safety import load_yaml

ROOT = Path(__file__).parent.parent.parent
# Tracked files with Chinese characters that the reviewer does not need: code comments and test folder names
# (cli.py, config.py, kernel/fonts.py, mkdocs_hooks.py, CI scripts and workflows) and the lead's German
# working documents, which are not shipped.
NOT_DISPLAYED = (
    "src/neurogrid/cli.py",
    "src/neurogrid/config.py",
    "src/neurogrid/kernel/fonts.py",
    "tools/mkdocs_hooks.py",
    ".github/workflows/ci.yml",
    "packaging/ci/cleanroom_inside.sh",
    "packaging/ci/cleanroom_windows.ps1",
)


def _tracked_with_chinese() -> set[str]:
    listed = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    found = set()
    for name in listed.splitlines():
        if name.startswith(("tests/", "docs/umsetzung/")):
            continue
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary files (fonts, fixtures)
        if zh.CJK.search(text):
            found.add(name)
    return found


def test_every_file_with_chinese_text_is_in_the_package() -> None:
    sources = {source.path for source in zh.sources(ROOT)}
    missing = _tracked_with_chinese() - sources - set(NOT_DISPLAYED)
    assert missing == set()
    for name in NOT_DISPLAYED:  # the reviewed exceptions hold no message: comments, test paths, regexes
        lines = [
            line for line in (ROOT / name).read_text(encoding="utf-8").splitlines() if zh.CJK.search(line)
        ]
        assert lines and len(lines) <= 4, name


def test_language_table_is_complete_with_keys() -> None:
    text = (ROOT / "src/neurogrid/report/i18n/zh.yaml").read_text(encoding="utf-8")
    entries = dict(zh.language_table(text))
    assert entries == flatten(load_yaml(text))
    assert any(key.startswith("cli.help.") for key in entries)
    assert any(key.startswith("errors.pdf.") for key in entries)
    assert entries["disclaimer"].startswith("使用 NeuroGrid")


def test_readers_of_each_kind() -> None:
    rules = "rules:\n  - id: CORE-M01-01\n    title_zh: 文件可读\n    title_en: Readable\n"
    assert zh.rule_titles(rules) == [("CORE-M01-01 title_zh", "文件可读")]
    codes = "EMPTY_FILE:\n  zh: 文件为空\n  en: Empty file\nOTHER:\n  en: no zh\n"
    assert zh.validator_texts(codes) == [("EMPTY_FILE", "文件为空")]
    assert zh.zh_lines("# Title\n\n中文段落。\nEnglish\n") == [("line 3", "中文段落。")]
    script = 'Write-Host "安装完成" "done"\necho done\nfoo 中文 bar\n'
    assert zh.script_messages(script) == [("line 1", "安装完成"), ("line 3", "foo 中文 bar")]
    module = 'MESSAGES = {"ok": ("已安装", "installed")}\nprint("其他")\nx = "plain"\n'
    assert zh.python_messages(module) == [("ok", "已安装"), ("line 2", "其他")]
    labels = "nav:\n  home: 首页\n  code: ABC\nlist:\n  - 第一\n"
    assert zh.yaml_zh(labels) == [("nav.home", "首页"), ("list[0]", "第一")]


def test_marks_against_the_baseline() -> None:
    keyed = zh.Source("x.yaml", "table", zh.language_table)
    current = "a: 旧\nb: 改后\nc: 新\n"
    marks = {e.key: e.mark for e in zh.marked(keyed, current, "a: 旧\nb: 改前\n")}
    assert marks == {"a": "", "b": "changed", "c": "new"}
    assert {e.mark for e in zh.marked(keyed, current, None)} == {"new"}  # file did not exist at P1
    assert {e.mark for e in zh.marked(keyed, current, "a: [unclosed")} == {"new"}  # unreadable baseline
    lines = zh.Source("p.md", "page", zh.zh_lines, keyed=False)
    marks_by_text = {e.text: e.mark for e in zh.marked(lines, "第一行\n第二行\n", "第一行\n")}
    assert marks_by_text == {"第一行": "", "第二行": "new"}


def test_render_lists_every_source_and_string() -> None:
    def no_baseline(path: str) -> str | None:
        return None

    collected = zh.collect(ROOT, no_baseline)
    document = zh.render(collected, "a44d592")
    assert document == zh.render(zh.collect(ROOT, no_baseline), "a44d592")  # deterministic
    for source, entries in collected:
        assert f"## {source.path}\n" in document
        assert all(entry.mark == "new" for entry in entries)
    table = dict(zh.language_table((ROOT / "src/neurogrid/report/i18n/zh.yaml").read_text(encoding="utf-8")))
    for key in ("disclaimer", "report.title", next(key for key in table if key.startswith("cli.help."))):
        assert f"| {zh._cell(key)} | new | {zh._cell(table[key])} |" in document
    total = sum(len(entries) for _source, entries in collected)
    assert f"| **all** | | {total} | {total} | 0 |" in document
    for machine in (ROOT, Path.home()):  # sources are named relative to the repository
        assert str(machine) not in document and machine.as_posix() not in document


def test_cells_keep_the_table_intact() -> None:
    assert zh._cell("a|b\\c\nd") == "a\\|b\\\\c<br>d"


def test_command_line(tmp_path: Path) -> None:
    out = tmp_path / "review" / "zh_review.md"
    if subprocess.run(["git", "cat-file", "-e", f"{zh.P1_COMMIT}^{{commit}}"], cwd=ROOT).returncode != 0:
        pytest.skip(f"the P1 commit {zh.P1_COMMIT} is not in this clone (shallow checkout)")
    assert zh.main(["--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# NeuroGrid – zh review package\n")
    assert "| disclaimer |  | " in text  # the fixed sentence existed at P1
    assert re.search(r"\| cli\.help\.[a-z_.]+ \| new \|", text)  # the help texts came with P5
    assert zh.main(["--out", str(out), "--since", "0000000"]) == 2
