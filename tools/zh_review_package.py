"""Review package of every Chinese string NeuroGrid ships, for the native review before v0.1 (A-07, STOPP G1).

One Markdown file lists, per source, every zh string with its source and key: the language table zh.yaml
(message key; the command-line help cli.help.* and the errors errors.* are part of it), the zh rule titles of
the built-in rule packs (rule ID), the zh validator texts (validator code), the zh documentation pages and
the zh labels of the generated pages (page and line, or key), the zh lines of mkdocs.yml, the docs scripts,
the README and the English rule pack page, the installer messages of install.ps1 and install.sh (line), the
zh messages of tools/install_pdf_browser.py (message name), README.bundle.txt and the release notes (line),
and the zh word lists of the wording test (forbidden.yaml, statements.yaml; never displayed, listed so the
reviewer can check them too). Each string is marked when it was added or changed since P1 (commit a44d592,
the scaffold whose texts the earlier review rounds saw): "new" = the key, or for line sources the line, is
not in the file of that commit (or the file did not exist), "changed" = same key, other text.

The package also holds two example reports as zh PDF (design H.2 of the acceptance), so the reviewer sees
the texts in the printed layout: report.zh.pdf of run 1 of a G1 run (tools/acceptance_g1.py), copied byte
for byte next to the Markdown file as <data set>.report.zh.pdf and listed there with pages and SHA-256.
Only a data set that passed that run is taken, and only while its PDF still has the size the run recorded.

Usage:
    python tools/zh_review_package.py [--out .local/acceptance/zh_review/zh_review.md] [--since a44d592]
        [--g1 .local/acceptance/g1] [--examples ds002778-1.0.5 psg-ipa-1.0.0]

The files are deterministic for a given working tree, baseline and G1 run (no time stamp). Exit code:
0 written, 2 when git cannot read the baseline commit or the G1 run lacks an example (nothing is written).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acceptance_g1 import SUMMARY_SCHEMA, sha256_file
from neurogrid.kernel.i18n import flatten
from neurogrid.kernel.safety import load_yaml

ROOT = Path(__file__).resolve().parent.parent
P1_COMMIT = "a44d592"  # feat: P1 scaffold and end-to-end check
DEFAULT_OUT = ROOT / ".local" / "acceptance" / "zh_review" / "zh_review.md"
DEFAULT_G1 = ROOT / ".local" / "acceptance" / "g1"  # the --out of tools/acceptance_g1.py
# The two example reports: the BIDS data set with the most findings (BDF; errors and warnings of core, bids
# and gxdsl008, validator rows) and the raw EDF folder (not BIDS; the line beyond 50 rows of a rule).
EXAMPLES = ("ds002778-1.0.5", "psg-ipa-1.0.0")
EXAMPLE_PDF = "report.zh.pdf"
# Han ideographs, CJK punctuation and full-width forms: a string or line holding one of them is Chinese text
CJK = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")
QUOTED = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"")


class PackageError(Exception):
    """The baseline cannot be read, or the G1 run lacks an example (exit 2)."""


@dataclass(frozen=True)
class Entry:
    key: str
    text: str
    mark: str = ""  # "new", "changed" or ""


# --- readers: (file text) -> [(key, zh text)] ---------------------------------------------------------------


def _leaves(data: Any, prefix: str = "") -> Iterable[tuple[str, str]]:
    """Dotted key and text of every string in nested mappings and lists."""
    if isinstance(data, Mapping):
        for key, value in data.items():
            yield from _leaves(value, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(data, list):
        for index, item in enumerate(data):
            yield from _leaves(item, f"{prefix}[{index}]")
    elif isinstance(data, str):
        yield prefix, data


def language_table(text: str) -> list[tuple[str, str]]:
    """zh.yaml: every message of the zh language table with its dotted key (also those without Han
    characters, e.g. file names: the reviewer sees that they stay untranslated)."""
    data = load_yaml(text)
    return list(flatten(data).items()) if isinstance(data, Mapping) else []


def yaml_zh(text: str) -> list[tuple[str, str]]:
    """Every string with Chinese text in a YAML file (docs labels, word lists)."""
    return [(key, value) for key, value in _leaves(load_yaml(text)) if CJK.search(value)]


def rule_titles(text: str) -> list[tuple[str, str]]:
    """The zh fields (title_zh, ...) of every rule of a rule pack, keyed by rule ID and field."""
    data = load_yaml(text)
    found = []
    for rule in data.get("rules", []) if isinstance(data, Mapping) else []:
        if not isinstance(rule, Mapping):
            continue
        for name in sorted(rule):
            if str(name).endswith("_zh") and isinstance(rule[name], str):
                found.append((f"{rule.get('id')} {name}", rule[name]))
    return found


def validator_texts(text: str) -> list[tuple[str, str]]:
    """The zh text of every validator code (report/validator_codes.yaml)."""
    data = load_yaml(text)
    return [
        (str(code), entry["zh"])
        for code, entry in (data.items() if isinstance(data, Mapping) else [])
        if isinstance(entry, Mapping) and isinstance(entry.get("zh"), str)
    ]


def zh_lines(text: str) -> list[tuple[str, str]]:
    """Every line with Chinese text (pages, notes, scripts), keyed by its line number."""
    return [(f"line {n}", line.strip()) for n, line in enumerate(text.splitlines(), 1) if CJK.search(line)]


def script_messages(text: str) -> list[tuple[str, str]]:
    """Installer scripts: per line every quoted string with Chinese text, else the line itself (usage
    text written as plain lines)."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if not CJK.search(line):
            continue
        quoted = [a or b for a, b in QUOTED.findall(line) if CJK.search(a or b)]
        for item in quoted or [line.strip()]:
            found.append((f"line {number}", item))
    return found


def python_messages(text: str) -> list[tuple[str, str]]:
    """String constants with Chinese text in a Python module; a constant inside a message table entry
    (``"name": (zh, en)``) is keyed by the entry's name, any other by its line."""
    tree = ast.parse(text)
    named: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    for inner in ast.walk(value):
                        named[id(inner)] = key.value
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and CJK.search(node.value):
            found.append((named.get(id(node), f"line {node.lineno}"), node.value))
    return sorted(found, key=lambda item: (item[0].startswith("line "), item[0]))


Reader = Callable[[str], list[tuple[str, str]]]


@dataclass(frozen=True)
class Source:
    path: str  # relative to the repository root, POSIX
    what: str
    reader: Reader
    keyed: bool = True  # marks by key; line sources by the line's text


def sources(root: Path = ROOT) -> list[Source]:
    """Every shipped file that holds zh text, in review order."""
    found = [
        Source(
            "src/neurogrid/report/i18n/zh.yaml",
            "language table (messages, report, cli.help.*, errors.*)",
            language_table,
        ),
    ]
    for pack in ("core", "bids", "gxdsl008"):
        found.append(
            Source(f"src/neurogrid/rulepacks/{pack}.yaml", f"rule titles of the {pack} pack", rule_titles)
        )
    found.append(Source("src/neurogrid/report/validator_codes.yaml", "validator texts", validator_texts))
    pages = sorted(path.relative_to(root).as_posix() for path in (root / "docs" / "zh").rglob("*.md"))
    found += [Source(page, "documentation page", zh_lines, keyed=False) for page in pages]
    data = sorted(path.relative_to(root).as_posix() for path in (root / "docs" / "_data").glob("*.zh.yaml"))
    found += [Source(name, "labels of the generated documentation pages", yaml_zh) for name in data]
    found += [
        Source("mkdocs.yml", "site navigation and footer", zh_lines, keyed=False),
        Source(
            "docs/assets/javascripts/file-search-hint.js", "search hint of the site", zh_lines, keyed=False
        ),
        Source("docs/en/rulepacks.md", "zh examples in the English rule pack page", zh_lines, keyed=False),
        Source("README.md", "README", zh_lines, keyed=False),
        Source("packaging/install.ps1", "installer messages (Windows)", script_messages, keyed=False),
        Source("packaging/install.sh", "installer messages (Linux)", script_messages, keyed=False),
        Source("tools/install_pdf_browser.py", "messages of the PDF browser installer", python_messages),
        Source("packaging/README.bundle.txt", "README of the offline bundle", zh_lines, keyed=False),
        Source("packaging/release-notes.md", "release notes", zh_lines, keyed=False),
        Source(
            "src/neurogrid/report/wording/forbidden.yaml",
            "word list: forbidden phrases (not displayed)",
            yaml_zh,
        ),
        Source(
            "src/neurogrid/report/wording/statements.yaml", "word list: statements (not displayed)", yaml_zh
        ),
    ]
    return found


# --- marks against the baseline ----------------------------------------------------------------------------


def git_baseline(commit: str, root: Path = ROOT) -> Callable[[str], str | None]:
    """The text of a file at ``commit`` (None if it did not exist there)."""
    probe = subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=root, capture_output=True)
    if probe.returncode != 0:
        raise PackageError(f"git cannot read commit {commit}")

    def read(path: str) -> str | None:
        shown = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=root, capture_output=True)
        return shown.stdout.decode("utf-8") if shown.returncode == 0 else None

    return read


def marked(source: Source, current: str, baseline: str | None) -> list[Entry]:
    """The entries of ``current`` with their marks against ``baseline``."""
    entries = source.reader(current)
    if baseline is None:
        return [Entry(key, text, "new") for key, text in entries]
    try:
        old = source.reader(baseline)
    except Exception:  # a baseline the reader cannot parse counts as absent
        return [Entry(key, text, "new") for key, text in entries]
    if not source.keyed:
        lines = {text for _key, text in old}
        return [Entry(key, text, "" if text in lines else "new") for key, text in entries]
    before: dict[str, str] = {}
    for key, text in old:
        before.setdefault(key, text)
    return [
        Entry(key, text, "new" if key not in before else ("changed" if before[key] != text else ""))
        for key, text in entries
    ]


def collect(root: Path, baseline: Callable[[str], str | None]) -> list[tuple[Source, list[Entry]]]:
    collected = []
    for source in sources(root):
        path = root / source.path
        if not path.is_file():
            continue
        current = path.read_text(encoding="utf-8")
        collected.append((source, marked(source, current, baseline(source.path))))
    return collected


# --- the example reports of a G1 run -----------------------------------------------------------------------


@dataclass(frozen=True)
class Example:
    """One example report: the zh PDF of a data set in run 1 of a G1 run."""

    dataset: str
    formats: tuple[str, ...]
    source: Path
    pages: int
    size: int
    sha256: str
    run: str  # NeuroGrid version and reference date of the G1 run

    @property
    def name(self) -> str:
        """The file name in the package."""
        return f"{self.dataset}.{EXAMPLE_PDF}"


def example_pdfs(g1: Path, names: Sequence[str]) -> list[Example]:
    """The zh PDFs of ``names`` in the G1 run in ``g1`` (its summary.json and run1/<data set>/): each data set
    must have passed that run, and its PDF must still have the size the run recorded."""
    summary_file = g1 / "summary.json"
    if not summary_file.is_file():
        raise PackageError("no G1 run in the --g1 folder (summary.json missing): run tools/acceptance_g1.py")
    try:
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageError(f"the summary.json of the G1 run cannot be read ({type(exc).__name__})") from exc
    if not isinstance(summary, dict) or summary.get("schema") != SUMMARY_SCHEMA:
        raise PackageError(f"the summary.json in the --g1 folder is not a {SUMMARY_SCHEMA} summary")
    entries = {entry.get("name"): entry for entry in summary.get("datasets", []) if isinstance(entry, dict)}
    run = f"NeuroGrid {summary.get('tool_version')}, reference date {summary.get('as_of')}"
    examples = []
    for name in dict.fromkeys(names):
        entry = entries.get(name)
        if entry is None:
            raise PackageError(f"data set {name} is not in the G1 run")
        if entry.get("ok") is not True:
            raise PackageError(f"data set {name} did not pass the G1 run")
        source = g1 / "run1" / name / EXAMPLE_PDF
        if not source.is_file():
            raise PackageError(f"the G1 run has no run1/{name}/{EXAMPLE_PDF}")
        size = source.stat().st_size
        if size != entry.get("bytes", {}).get(EXAMPLE_PDF):
            raise PackageError(f"run1/{name}/{EXAMPLE_PDF} changed after the G1 run (size)")
        examples.append(
            Example(
                dataset=name,
                formats=tuple(entry.get("formats", [])),
                source=source,
                pages=int(entry.get("pdf_pages", {}).get("zh", 0)),
                size=size,
                sha256=sha256_file(source),
                run=run,
            )
        )
    return examples


def write_package(out: Path, document: str, examples: Sequence[Example]) -> None:
    """The Markdown file and, next to it, a byte copy of every example PDF."""
    out.parent.mkdir(parents=True, exist_ok=True)
    for example in examples:
        (out.parent / example.name).write_bytes(example.source.read_bytes())
    out.write_text(document, encoding="utf-8", newline="\n")


# --- the Markdown file -------------------------------------------------------------------------------------


def _cell(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def _counts(entries: Iterable[Entry]) -> tuple[int, int, int]:
    items = list(entries)
    return len(items), sum(e.mark == "new" for e in items), sum(e.mark == "changed" for e in items)


def render(collected: list[tuple[Source, list[Entry]]], since: str, examples: Sequence[Example] = ()) -> str:
    lines = [
        "# NeuroGrid – zh review package",
        "",
        "Every Chinese string NeuroGrid ships, for the native review before the release of v0.1",
        "(A-07, STOPP G1).",
        f"Generated by tools/zh_review_package.py from the working tree. Marks against P1 (commit {since}):",
        "**new** = added since P1, **changed** = same key with another text since P1, no mark = unchanged.",
        "Line sources (pages, scripts, notes) have no stable key: a line is **new** when the P1 file did not",
        "hold it. Corrections come back as a file with source, key and corrected text; they are taken over",
        "with the wording test (src/neurogrid/report/wording, tests/unit/test_language_and_wording.py).",
        "The fixed sentence (A-08) is the key `disclaimer` of the language table.",
        "",
    ]
    if examples:
        lines += [
            "## Example reports (zh PDF)",
            "",
            "The zh report of data sets of the public test corpus as printed, in the folder of this file:",
            "the texts in their layout, the fixed sentence at the foot of every page.",
            "",
            "| File | Data set | Format | Pages | Bytes | SHA-256 | Source |",
            "|---|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {e.name} | {e.dataset} | {', '.join(e.formats)} | {e.pages} | {e.size} | {e.sha256} | "
            f"run1/{e.dataset}/{EXAMPLE_PDF} of the G1 run ({e.run}) |"
            for e in examples
        ]
        lines.append("")
    lines += [
        "## Overview",
        "",
        "| Source | What | Strings | new | changed |",
        "|---|---|---|---|---|",
    ]
    total = [0, 0, 0]
    for source, entries in collected:
        count = _counts(entries)
        total = [a + b for a, b in zip(total, count, strict=True)]
        lines.append(f"| {source.path} | {source.what} | {count[0]} | {count[1]} | {count[2]} |")
        if source.reader is language_table:
            for prefix, what in (("cli.help.", "command-line help"), ("errors.", "error messages")):
                sub = _counts(e for e in entries if e.key.startswith(prefix))
                lines.append(f"| ↳ {prefix}* | {what} (part of zh.yaml) | {sub[0]} | {sub[1]} | {sub[2]} |")
    lines += [f"| **all** | | {total[0]} | {total[1]} | {total[2]} |", ""]
    for source, entries in collected:
        count = _counts(entries)
        lines += [
            f"## {source.path}",
            "",
            f"{source.what}: {count[0]} strings, {count[1]} new, {count[2]} changed since P1.",
            "",
            "| Key | Mark | Text |",
            "|---|---|---|",
        ]
        lines += [f"| {_cell(e.key)} | {e.mark} | {_cell(e.text)} |" for e in entries]
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="the review file to write (the PDFs go next to it)"
    )
    parser.add_argument("--since", default=P1_COMMIT, help="baseline commit of the marks (default: P1)")
    parser.add_argument(
        "--g1", type=Path, default=DEFAULT_G1, help="folder of a G1 run of tools/acceptance_g1.py"
    )
    parser.add_argument(
        "--examples",
        nargs="+",
        default=list(EXAMPLES),
        metavar="DATA_SET",
        help="data sets of the G1 run whose zh PDF goes into the package (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    try:
        baseline = git_baseline(args.since)
        examples = example_pdfs(args.g1, args.examples)
    except PackageError as exc:
        print(f"zh review package: {exc}", file=sys.stderr)
        return 2
    collected = collect(ROOT, baseline)
    write_package(args.out, render(collected, args.since, examples), examples)
    strings, new, changed = _counts(e for _s, entries in collected for e in entries)
    print(
        f"{args.out.name}: {strings} zh strings from {len(collected)} files "
        f"({new} new, {changed} changed since P1), {len(examples)} example PDFs"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
