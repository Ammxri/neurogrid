"""Class labels from BIDS events.tsv for M11 (``[ai] labels = "events:<column>"``; A-04, A-81, critic G10).

The nearest events.tsv of a recording counts (inheritance principle, io/bids.py; links are not followed,
sizes are limited, utf-8-sig because ds000248 starts with a byte order mark). The label column is matched
without surrounding space and without regard to case (ds004148 has headers with spaces). Cells are stripped;
empty cells and ``n/a`` are no label. The documented values of the column are the "Levels" of the merged
events.json sidecars (they decide which labels may be shown, A-17/C5).

Events are dataset data (C2): a missing or unreadable table is no error, only "no labels".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from neurogrid.io import bids
from neurogrid.io.participants import canonical, missing


@dataclass(frozen=True)
class EventLabels:
    table: bool  # an events.tsv applies to the recording
    column: bool  # it has the label column
    values: tuple[str, ...] = ()  # one label per event row with a value, in file order
    vocabulary: frozenset[str] = frozenset()  # Levels of the column in events.json


def event_labels(root: Path, data_file: PurePosixPath, column: str) -> EventLabels:
    table = bids.nearest_tsv(root, data_file, "events")
    if table is None:
        return EventLabels(table=False, column=False)
    header, rows = table
    wanted = canonical(column)
    name = next((name for name in header if canonical(name) == wanted), None)
    if name is None:
        return EventLabels(table=True, column=False)
    values = tuple(cell.strip() for row in rows if not missing(cell := row.get(name, "")))
    sidecar, _found = bids.merged_json(root, data_file, "events")
    vocabulary: frozenset[str] = frozenset()
    for key, entry in sidecar.items():
        levels = entry.get("Levels") if isinstance(entry, dict) else None
        if canonical(str(key)) == wanted and isinstance(levels, dict):
            vocabulary = frozenset(str(level) for level in levels)
            break
    return EventLabels(table=True, column=True, values=values, vocabulary=vocabulary)
