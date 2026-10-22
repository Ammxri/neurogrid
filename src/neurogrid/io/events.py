"""Class labels from BIDS events.tsv for M11 (``[ai] labels = "events:<column>"``; A-04, A-81, critic G10).

One events.tsv reader for M10 and M11: io.annotations.read_events reads the nearest events.tsv of a recording
(inheritance principle, io/bids.py; links are not followed, sizes and rows are limited, utf-8-sig because
ds000248 starts with a byte order mark). The label column is found by its header rule
(:meth:`EventsTable.column`: without surrounding space and without regard to case, the first of duplicate
columns, as M10), its cells by :meth:`EventsTable.values` (empty cells and ``n/a`` are no label). The
documented values of the column are the "Levels" of the merged events.json sidecars for that column
(io.annotations.events_levels; they decide which labels may be shown, A-17/C5).

Events are dataset data (C2): a missing table is no error, only "no labels"; a table that cannot be read
(not UTF-8, too large, too many rows) is marked ``unreadable``, so that M11 leaves its recording out as a
whole and counts it (A-81), never exit 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from neurogrid.io.annotations import AnnotationsUnreadable, events_levels, read_events


@dataclass(frozen=True)
class EventLabels:
    table: bool  # an events.tsv applies to the recording
    column: bool  # it could be read and has the label column
    values: tuple[str, ...] = ()  # one label per event row with a value, in file order
    vocabulary: frozenset[str] = frozenset()  # Levels of the column in events.json
    unreadable: bool = False  # the applicable events.tsv could not be read


def event_labels(root: Path, data_file: PurePosixPath, column: str) -> EventLabels:
    try:
        table = read_events(root, data_file)
    except AnnotationsUnreadable:
        return EventLabels(table=True, column=False, unreadable=True)
    if table is None:
        return EventLabels(table=False, column=False)
    index = table.column(column)
    if index is None:
        return EventLabels(table=True, column=False)
    values = tuple(table.values(column) or ())
    levels = events_levels(root, data_file, table.columns[index])
    return EventLabels(table=True, column=True, values=values, vocabulary=frozenset(levels or ()))
