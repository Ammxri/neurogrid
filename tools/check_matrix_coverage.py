"""Check the requirement matrix against the phase plan.

Reads docs/umsetzung/ANFORDERUNGEN.md (first column of every table row) and the
phase table in docs/umsetzung/KONZEPT.md (rows starting with "| P<n>"): column 3
lists the IDs a phase closes, column 4 the IDs it contributes to. Ranges like
"NZ-01–NZ-09" are expanded.

Fails (exit 1) if an ID has no closing phase, more than one closing phase, or if
the plan mentions an ID that is not in the matrix.
"""

from __future__ import annotations

import io
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "docs" / "umsetzung" / "ANFORDERUNGEN.md"
CONCEPT = ROOT / "docs" / "umsetzung" / "KONZEPT.md"

ID_PATTERN = (
    r"(?:NG-F|NG-N|NV-F|MET-|DM-|RP-|GX-|CLI-|REP-|POS-|ARC-|LIB-|TECH-|CON-|UF-|NA-|NZ-|BIZ-|V-|M)\d{2}"
)
RANGE = re.compile(rf"({ID_PATTERN})\s*[–-]\s*({ID_PATTERN})")
SINGLE = re.compile(rf"(?<![A-Z0-9-]){ID_PATTERN}")
PHASE_ROW = re.compile(r"^\|\s*(P\d+)\b")


def split_id(req_id: str) -> tuple[str, int]:
    match = re.fullmatch(r"(.*?)(\d{2})", req_id)
    assert match is not None
    return match.group(1), int(match.group(2))


def expand(cell: str) -> set[str]:
    ids: set[str] = set()
    for start, end in RANGE.findall(cell):
        prefix_a, num_a = split_id(start)
        prefix_b, num_b = split_id(end)
        if prefix_a == prefix_b:
            ids.update(f"{prefix_a}{n:02d}" for n in range(num_a, num_b + 1))
    ids.update(SINGLE.findall(RANGE.sub("", cell)))
    return ids


def matrix_ids() -> set[str]:
    ids: set[str] = set()
    for line in MATRIX.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) > 2 and re.fullmatch(ID_PATTERN, cells[1]):
            ids.add(cells[1])
    return ids


def phase_table() -> dict[str, tuple[set[str], set[str]]]:
    phases: dict[str, tuple[set[str], set[str]]] = {}
    in_plan = False
    for line in CONCEPT.read_text(encoding="utf-8").splitlines():
        if line.startswith("## 6."):
            in_plan = True
            continue
        if in_plan and line.startswith("## "):
            break
        match = PHASE_ROW.match(line) if in_plan else None
        if match:
            cells = [c.strip() for c in line.split("|")]
            phases[match.group(1)] = (expand(cells[3]), expand(cells[4]))
    return phases


def main() -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    required = matrix_ids()
    phases = phase_table()
    closing: dict[str, list[str]] = defaultdict(list)
    mentioned: set[str] = set()
    for name, (closes, contributes) in phases.items():
        for req_id in closes:
            closing[req_id].append(name)
        mentioned |= closes | contributes

    no_close = sorted(required - closing.keys())
    multi_close = sorted(i for i, p in closing.items() if len(p) > 1)
    unknown = sorted(mentioned - required)

    print(
        f"Matrix-IDs: {len(required)}  Phasen: {len(phases)}  "
        f"mit genau einer abschließenden Phase: {len(required) - len(no_close) - len(multi_close)}"
    )
    for name, (closes, contributes) in phases.items():
        print(f"  {name}: schließt {len(closes)} ab, trägt zu {len(contributes)} bei")
    if no_close:
        print("Ohne abschließende Phase:", ", ".join(no_close))
    if multi_close:
        print("Mehrfach abgeschlossen:", ", ".join(f"{i} ({'/'.join(closing[i])})" for i in multi_close))
    if unknown:
        print("Unbekannt (nicht in der Matrix):", ", ".join(unknown))
    return 1 if no_close or multi_close or unknown else 0


if __name__ == "__main__":
    sys.exit(main())
