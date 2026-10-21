"""Enforce the coverage limits of NG-N08 per module group (A-23).

"Kern" (≥ 90 %): kernel, model, vault, config.  "Prüfer" (≥ 80 %): checks, quality, io, convert, metadata,
validator, diff, dossier, report, cli, pipeline. Reads a ``coverage json`` report (lines and branches, like
``coverage report``).

Usage: python tools/coverage_gates.py .local/coverage.json
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

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


def _group_of(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    for name, (_limit, prefixes) in GROUPS.items():
        if any(prefix in normalized for prefix in prefixes):
            return name
    return None


def main() -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    totals = {name: [0, 0] for name in GROUPS}
    unassigned = []
    for path, data in report["files"].items():
        group = _group_of(path)
        summary = data["summary"]
        if group is None:
            if "neurogrid/" in path.replace("\\", "/"):
                unassigned.append(path)
            continue
        totals[group][0] += summary["covered_lines"] + summary.get("covered_branches", 0)
        totals[group][1] += summary["num_statements"] + summary.get("num_branches", 0)
    failed = False
    for name, (covered, total) in totals.items():
        limit = GROUPS[name][0]
        percent = 100.0 * covered / total if total else 100.0
        status = "ok" if percent >= limit else "FAIL"
        failed |= percent < limit
        print(f"{name}: {percent:.1f} % (limit {limit:.0f} %) {status}")
    for path in unassigned:
        print(f"note: not in a coverage group: {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
