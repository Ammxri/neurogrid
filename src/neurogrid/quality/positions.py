"""Channel positions for the sample metrics M06/M09 (A-60, A-79).

Montage source: the first of these that has positions for every analysed EEG channel, or for at least
``min_channels`` of them (then only those channels are analysed and the others are listed):

1. ``sidecar``: the electrodes.tsv of the recording (BIDS), with a coordsystem.json that names the units (m,
   cm, mm) and a coordinate system of known orientation. RAS systems (CapTrak, ElektaNeuromag, ChietiItab) are
   used as they are; ALS systems (CTF, 4DBti, KitYokogawa, EEGLAB, EEGLAB-HJ) are turned to RAS. Template
   spaces and "Other" are not used, and neither is an electrodes.tsv without coordsystem.json; the reason is
   reported.
2. ``header``: positions stored in the file, as MNE reads them in the head frame (FIF, EEGLAB, BrainVision).
3. ``standard_montage``: template positions (colin27, 10-05) of the channels' standard names (M04,
   ``channel_map``), transformed to MNE's head frame like the other two sources; bipolar labels and unknown
   names have none.
4. ``none``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import numpy as np

from neurogrid.io import bids
from neurogrid.io.channels import standard_name

Position = tuple[float, float, float]

UNITS_M = {"m": 1.0, "cm": 0.01, "mm": 0.001}
RAS_SYSTEMS = frozenset({"captrak", "elektaneuromag", "chietiitab"})
ALS_SYSTEMS = frozenset({"ctf", "4dbti", "kityokogawa", "eeglab", "eeglab-hj"})


@dataclass(frozen=True)
class Choice:
    source: str  # sidecar | header | standard_montage | none
    positions: dict[str, Position]  # of the analysed channels; empty for "none"
    analysed: tuple[str, ...]  # channel names in source order
    excluded: tuple[str, ...]  # channels left out because they have no position from ``source``


def _number(text: str | None) -> float | None:
    try:
        value = float(text) if text is not None else math.nan
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def sidecar_positions(root: Path, data_file: PurePosixPath) -> tuple[dict[str, Position], str | None]:
    """Positions (m, RAS) from an electrodes.tsv that applies to ``data_file``, and the reason when electrodes
    files exist but none can be used (key below ``report.positions_unused``). Of several files (one per
    ``space``), the most specific level comes first, and within it the first usable file in name order."""
    electrodes = bids.applicable(root, data_file, "electrodes", ".tsv", ignore=("space",))
    if not electrodes:
        return {}, None
    deepest = max(len(path.parts) for path in electrodes)
    ordered = [p for p in electrodes if len(p.parts) == deepest] + [
        p for p in reversed(electrodes) if len(p.parts) < deepest
    ]
    systems = bids.applicable(root, data_file, "coordsystem", ".json", ignore=("space",))
    first_reason: str | None = None
    for path in ordered:
        found, reason = _electrodes_file(path, systems)
        if reason is None:
            return found, None
        first_reason = first_reason or reason
    return {}, first_reason


def _electrodes_file(path: Path, systems: list[Path]) -> tuple[dict[str, Position], str | None]:
    table = bids.read_tsv(path)
    if table is None:
        return {}, "unreadable"
    name = bids.parse_name(path.name)
    space = name.entities.get("space") if name else None
    paired = [
        system
        for system in systems
        if (parsed := bids.parse_name(system.name)) is not None and parsed.entities.get("space") == space
    ]
    coordsystem = bids.read_json(paired[-1]) if paired else None
    if coordsystem is None:
        return {}, "coordsystem_missing"
    scale = UNITS_M.get(str(coordsystem.get("EEGCoordinateUnits", "")).strip().lower())
    if scale is None:
        return {}, "units_unknown"
    system = str(coordsystem.get("EEGCoordinateSystem", "")).strip().lower()
    if system not in RAS_SYSTEMS | ALS_SYSTEMS:
        return {}, "frame_unsupported"
    found: dict[str, Position] = {}
    for row in table[1]:
        coords = [_number(row.get(axis)) for axis in ("x", "y", "z")]
        if any(c is None for c in coords):
            continue
        x, y, z = (float(c) * scale for c in coords if c is not None)
        if x == 0 and y == 0 and z == 0:
            continue
        found[row.get("name", "")] = (x, y, z) if system in RAS_SYSTEMS else (-y, x, z)
    return found, (None if found else "no_coordinates")


def template_positions(names: Sequence[str], channel_map: Mapping[str, str]) -> dict[str, Position]:
    import mne

    # the template is stored in its MRI frame; the head frame (origin between the ears, as MNE's set_montage
    # gives it) is the frame of the file and sidecar positions too
    montage = mne.channels.transform_to_head(mne.channels.make_standard_montage("colin27_1005"))
    positions = montage.get_positions()["ch_pos"]
    by_upper = {name.upper(): name for name in positions}
    found: dict[str, Position] = {}
    for name in names:
        standard = standard_name(name, channel_map)
        if standard is None or "-" in standard[0]:
            continue
        key = by_upper.get(standard[0].upper())
        if key is not None:
            x, y, z = (float(v) for v in positions[key])
            found[name] = (x, y, z)
    return found


def usable(positions: Mapping[str, np.ndarray | Position]) -> dict[str, Position]:
    """Finite positions that are not all zero (MNE marks a missing position with zeros or NaN)."""
    found: dict[str, Position] = {}
    for name, value in positions.items():
        coords = [float(v) for v in value]
        if len(coords) == 3 and all(math.isfinite(c) for c in coords) and any(c != 0 for c in coords):
            found[name] = (coords[0], coords[1], coords[2])
    return found


def choose(
    names: Sequence[str], candidates: Sequence[tuple[str, Mapping[str, Position]]], min_channels: int
) -> Choice:
    for source, positions in candidates:
        have = [name for name in names if name in positions]
        if len(have) == len(names) or len(have) >= min_channels:
            return Choice(
                source=source,
                positions={name: positions[name] for name in have},
                analysed=tuple(have),
                excluded=tuple(name for name in names if name not in positions),
            )
    return Choice(source="none", positions={}, analysed=tuple(names), excluded=())


__all__ = ["Choice", "Position", "choose", "sidecar_positions", "template_positions", "usable"]
