"""Enforce the coverage limits of NG-N08 per module group (A-23).

"Kern" (≥ 90 %): kernel, model, vault, config.  "Prüfer" (≥ 80 %): checks, quality, io, convert, metadata,
validator, diff, dossier, report, cli, pipeline. Reads a ``coverage json`` report (lines and branches, like
``coverage report``).

Platform code (A-90, p6 decisions 12): the lines of src/neurogrid/vault/_os.py that run on one platform only
start a block with the marker comment ``# platform-only: windows`` or ``# platform-only: posix`` (the marked
line and the lines indented below it). Before the limits are applied, the marked blocks of the OTHER platform
are left out of that file's statements, missing lines and branches: a Windows run measures the Windows
branches, the Linux CI the POSIX ones (D-09). A marker in any other file is an error of the gate. The source
files are read relative to the current folder, where coverage ran.

Usage: python tools/coverage_gates.py .local/coverage.json [--platform windows|posix]
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

GROUPS: dict[str, tuple[float, tuple[str, ...]]] = {
    "Kern": (
        90.0,
        (
            "neurogrid/kernel/",
            "neurogrid/model/",
            "neurogrid/vault/",
            "neurogrid/config.py",
            "neurogrid/__init__.py",
        ),
    ),
    "Prüfer": (
        80.0,
        (
            "neurogrid/checks/",
            "neurogrid/quality/",
            "neurogrid/io/",
            "neurogrid/convert.py",
            "neurogrid/metadata.py",
            "neurogrid/validator.py",
            "neurogrid/diff.py",
            "neurogrid/dossier.py",
            "neurogrid/report/",
            "neurogrid/cli.py",
            "neurogrid/pipeline.py",
            "neurogrid/__main__.py",
            "neurogrid/rulepacks/",
        ),
    ),
}
PLATFORMS = ("windows", "posix")
MARKER = re.compile(r"#\s*platform-only:\s*(\w+)")
PLATFORM_MODULE = "neurogrid/vault/_os.py"  # the one file that may carry markers


def _group_of(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    for name, (_limit, prefixes) in GROUPS.items():
        if any(prefix in normalized for prefix in prefixes):
            return name
    return None


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def marked_blocks(source: str) -> tuple[dict[str, set[int]], list[int]]:
    """The 1-based lines of the marked blocks per platform, and the lines of markers that name no platform."""
    blocks: dict[str, set[int]] = {platform: set() for platform in PLATFORMS}
    unknown: list[int] = []
    lines = source.splitlines()
    for index, line in enumerate(lines):
        match = MARKER.search(line)
        if match is None:
            continue
        platform = match.group(1)
        if platform not in blocks:
            unknown.append(index + 1)
            continue
        blocks[platform].add(index + 1)
        for number, below in enumerate(lines[index + 1 :], start=index + 2):
            if below.strip() and _indent(below) <= _indent(line):
                break
            blocks[platform].add(number)
    return blocks, unknown


def without_lines(data: dict[str, Any], dropped: set[int]) -> dict[str, int]:
    """The summary of one file of the report with the ``dropped`` lines and the branches from or to them
    left out (coverage json: executed_lines, missing_lines, executed_branches, missing_branches; a negative
    branch target is a function exit)."""

    def kept(branches: list[list[int]]) -> int:
        return sum(1 for start, end in branches if start not in dropped and not (end > 0 and end in dropped))

    executed = set(data.get("executed_lines", [])) - dropped
    missing = set(data.get("missing_lines", [])) - dropped
    covered_branches = kept(data.get("executed_branches", []))
    missing_branches = kept(data.get("missing_branches", []))
    return {
        "covered_lines": len(executed),
        "num_statements": len(executed) + len(missing),
        "covered_branches": covered_branches,
        "num_branches": covered_branches + missing_branches,
    }


def _source(path: str) -> str | None:
    candidate = Path(path)
    try:
        return candidate.read_text(encoding="utf-8") if candidate.is_file() else None
    except (OSError, UnicodeDecodeError):
        return None


def main(argv: list[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    parser.add_argument(
        "--platform", choices=PLATFORMS, default="windows" if sys.platform == "win32" else "posix"
    )
    args = parser.parse_args(argv)
    other = next(platform for platform in PLATFORMS if platform != args.platform)
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    totals = {name: [0, 0] for name in GROUPS}
    unassigned = []
    misplaced: list[str] = []
    dropped_total = 0
    for path, data in report["files"].items():
        normalized = path.replace("\\", "/")
        summary = data["summary"]
        source = _source(path)
        if source is not None:
            blocks, unknown = marked_blocks(source)
            marked = sorted(blocks["windows"] | blocks["posix"])
            if not normalized.endswith(PLATFORM_MODULE) and (marked or unknown):
                misplaced.append(f"{normalized}:{(marked + unknown)[0]}")
            elif unknown:
                misplaced.append(f"{normalized}:{unknown[0]} (unknown platform)")
            elif blocks[other] and "executed_lines" in data:
                summary = without_lines(data, blocks[other])
                dropped_total += len(blocks[other])
        group = _group_of(path)
        if group is None:
            if "neurogrid/" in normalized:
                unassigned.append(path)
            continue
        totals[group][0] += summary["covered_lines"] + summary.get("covered_branches", 0)
        totals[group][1] += summary["num_statements"] + summary.get("num_branches", 0)
    failed = bool(misplaced)
    lines = []
    for name, (covered, total) in totals.items():
        limit = GROUPS[name][0]
        percent = 100.0 * covered / total if total else 100.0
        status = "ok" if percent >= limit else "FAIL"
        failed |= percent < limit
        lines.append(f"{name}: {percent:.1f} % (limit {limit:.0f} %) {status}")
    for line in lines:
        print(line)
    # the values as one annotation, which the public API serves without a login (TECH-05)
    print(f"::{'error' if failed else 'notice'} title=coverage::{'; '.join(lines)}")
    for place in misplaced:
        print(f"error: platform-only marker outside {PLATFORM_MODULE} or without a known platform: {place}")
    if dropped_total:
        print(f"note: {dropped_total} line(s) of {other}-only blocks left out ({args.platform} run)")
    for path in unassigned:
        print(f"note: not in a coverage group: {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
