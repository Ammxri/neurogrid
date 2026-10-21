"""Channel positions for the sample metrics M06/M09 (A-60, A-79): the montage source order with its subset
rule, template positions of standard names (M04), usable header positions and electrodes.tsv with
coordsystem.json from a BIDS tree (units, orientation, space entity)."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

import mne
import numpy as np
import pytest

from neurogrid.quality.positions import (
    Choice,
    Position,
    choose,
    sidecar_positions,
    template_positions,
    usable,
)

DATA = PurePosixPath("sub-01/eeg/sub-01_task-rest_eeg.edf")
EEG_DIR = PurePosixPath("sub-01/eeg")
ROWS_MM = {"Fp1": (-29.4, 83.9, -7.0), "Cz": (0.4, -9.2, 100.2), "O2": (29.8, -112.3, 8.8)}


def _colin27() -> dict[str, np.ndarray]:
    """colin27 10-05 in MNE's head frame, the frame of the file and sidecar positions too (A-79)."""
    montage = mne.channels.transform_to_head(mne.channels.make_standard_montage("colin27_1005"))
    return dict(montage.get_positions()["ch_pos"])


def _at(index: int) -> Position:
    return (0.01 * index, 0.02, 0.03)


def _names(count: int) -> list[str]:
    return [f"E{index:02d}" for index in range(count)]


# --- choose(): source order and subset rule --------------------------------------------------------------


def test_choose_takes_the_first_source_with_every_channel() -> None:
    """A-60: sidecar > header > standard_montage; a source with all channels is used as it is."""
    names = ["Fp1", "Cz", "O2"]
    sidecar = {"O2": _at(3), "Cz": _at(2), "Fp1": _at(1), "Fz": _at(9)}  # Fz is no channel of the file
    header = {name: _at(5) for name in names}
    choice = choose(names, [("sidecar", sidecar), ("header", header)], min_channels=16)
    assert choice == Choice(
        source="sidecar",
        positions={"Fp1": _at(1), "Cz": _at(2), "O2": _at(3)},
        analysed=("Fp1", "Cz", "O2"),  # source order, not the order of the position table
        excluded=(),
    )


def test_choose_all_channels_wins_even_below_min_channels() -> None:
    """A-79: the subset threshold applies only when channels are left out."""
    choice = choose(["C3", "C4"], [("header", {"C3": _at(1), "C4": _at(2)})], min_channels=16)
    assert choice.source == "header" and choice.analysed == ("C3", "C4") and choice.excluded == ()


def test_choose_subset_lists_the_excluded_channels_in_source_order() -> None:
    """A-79: positions for at least min_channels channels -> only those are analysed, the rest listed."""
    names = _names(10) + ["EXG2"] + _names(20)[10:] + ["EXG1"]
    positions = {name: _at(i) for i, name in enumerate(names) if not name.startswith("EXG")}
    choice = choose(names, [("sidecar", positions), ("standard_montage", {n: _at(0) for n in names})], 16)
    assert choice.source == "sidecar"
    assert choice.analysed == tuple(_names(20))
    assert choice.excluded == ("EXG2", "EXG1")
    assert choice.positions == positions


def test_choose_subset_at_exactly_min_channels() -> None:
    names = _names(20)
    positions = {name: _at(i) for i, name in enumerate(names[:16])}
    choice = choose(names, [("header", positions)], min_channels=16)
    assert choice.source == "header" and len(choice.analysed) == 16 and choice.excluded == tuple(names[16:])


def test_choose_falls_through_to_the_next_source() -> None:
    """Fewer than min_channels positions (and not all): the next source is tried."""
    names = _names(20)
    sidecar = {name: _at(1) for name in names[:15]}
    template = {name: _at(2) for name in names[2:]}
    choice = choose(names, [("sidecar", sidecar), ("header", {}), ("standard_montage", template)], 16)
    assert choice.source == "standard_montage"
    assert choice.analysed == tuple(names[2:]) and choice.excluded == tuple(names[:2])
    assert set(choice.positions.values()) == {_at(2)}


def test_choose_none_keeps_every_channel() -> None:
    """No source qualifies -> "none": all channels are analysed (M06 without RANSAC), nothing excluded."""
    names = _names(20)
    few = {name: _at(1) for name in names[:15]}
    choice = choose(names, [("sidecar", few), ("header", few), ("standard_montage", {})], 16)
    assert choice == Choice(source="none", positions={}, analysed=tuple(names), excluded=())
    assert choose(names, [], 16).source == "none"


# --- template positions of standard names (M04) ----------------------------------------------------------


def test_template_positions_of_standard_names() -> None:
    """colin27 10-05 positions via the standard name: type word, reference suffix and case are ignored."""
    colin = _colin27()
    found = template_positions(["Fp1", "EEG Cz", "O2-REF", "fp2", "AFF1h"], {})
    expected = {"Fp1": "Fp1", "EEG Cz": "Cz", "O2-REF": "O2", "fp2": "Fp2", "AFF1h": "AFF1h"}
    assert set(found) == set(expected)
    for label, standard in expected.items():
        assert found[label] == pytest.approx(tuple(float(v) for v in colin[standard]))
        assert all(isinstance(v, float) for v in found[label])


def test_template_positions_equal_what_set_montage_gives() -> None:
    """The template is used in the head frame: the positions equal those of raw.set_montage("colin27_1005"),
    not the template's MRI-frame coordinates (origin about 5 cm apart)."""
    names = ["Fp1", "Cz", "O2", "T7"]
    raw = mne.io.RawArray(np.zeros((len(names), 10)), mne.create_info(names, 250.0, "eeg"), verbose="error")
    raw.set_montage("colin27_1005", verbose="error")
    found = template_positions(names, {})
    for channel in raw.info["chs"]:
        assert found[channel["ch_name"]] == pytest.approx(
            tuple(float(v) for v in channel["loc"][:3]), abs=1e-7
        )
    mri = mne.channels.make_standard_montage("colin27_1005").get_positions()["ch_pos"]
    assert max(abs(found["Cz"][axis] - float(mri["Cz"][axis])) for axis in range(3)) > 0.01


def test_template_positions_skip_bipolar_and_unknown_names() -> None:
    """A bipolar derivation ("Fp1-F7") has no single position; unknown names have none."""
    assert template_positions(["Fp1-F7", "EXG1", "Kanal1", "E7", "C3-C4"], {}) == {}


def test_template_positions_follow_the_channel_map() -> None:
    """channel_map (neurogrid.toml) gives a non-standard label its standard name and so a position."""
    colin = _colin27()
    found = template_positions(["Kanal1", "Kanal2", "EXG1"], {"Kanal1": "Pz", "Kanal2": "NoSuchName"})
    assert set(found) == {"Kanal1"}
    assert found["Kanal1"] == pytest.approx(tuple(float(v) for v in colin["Pz"]))


# --- usable() --------------------------------------------------------------------------------------------


def test_usable_drops_missing_positions() -> None:
    """MNE marks a missing position with NaN or zeros; both are dropped, as are non-finite and short ones."""
    found = usable(
        {
            "Fp1": np.array([-0.03, 0.08, -0.007]),
            "nan": np.array([math.nan, math.nan, math.nan]),
            "partly_nan": (0.01, math.nan, 0.02),
            "zero": np.zeros(3),
            "inf": (math.inf, 0.0, 0.0),
            "short": np.array([0.01, 0.02]),
            "on_axis": (0.0, 0.09, 0.0),
        }
    )
    assert found == {"Fp1": (-0.03, 0.08, -0.007), "on_axis": (0.0, 0.09, 0.0)}
    assert all(type(v) is float for position in found.values() for v in position)


# --- electrodes.tsv + coordsystem.json -------------------------------------------------------------------


def _tree(root: Path) -> Path:
    folder = root.joinpath(*EEG_DIR.parts)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / DATA.name).write_bytes(b"")  # the data file itself is not read
    return folder


def _electrodes(
    root: Path, rows: Mapping[str, tuple[Any, Any, Any]], name: str = "sub-01_electrodes.tsv"
) -> None:
    lines = ["name\tx\ty\tz\ttype\timpedance"]
    lines += [f"{label}\t{x}\t{y}\t{z}\tcup\tn/a" for label, (x, y, z) in rows.items()]
    (_tree(root) / name).write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _coordsystem(root: Path, system: str, units: str | None, name: str = "sub-01_coordsystem.json") -> None:
    content: dict[str, Any] = {"EEGCoordinateSystem": system}
    if units is not None:
        content["EEGCoordinateUnits"] = units
    (_tree(root) / name).write_bytes(json.dumps(content).encode("utf-8"))


def _scaled(rows: Mapping[str, tuple[float, float, float]], factor: float) -> dict[str, Position]:
    return {label: (x * factor, y * factor, z * factor) for label, (x, y, z) in rows.items()}


def _assert_positions(found: dict[str, Position], expected: dict[str, Position]) -> None:
    assert set(found) == set(expected)
    for label, position in expected.items():
        assert found[label] == pytest.approx(position, abs=1e-12)


def test_no_electrodes_file(tmp_path: Path) -> None:
    """No electrodes.tsv: no positions and no reason (a coordsystem.json alone changes nothing)."""
    _tree(tmp_path)
    assert sidecar_positions(tmp_path, DATA) == ({}, None)
    _coordsystem(tmp_path, "CapTrak", "mm")
    assert sidecar_positions(tmp_path, DATA) == ({}, None)


def test_electrodes_without_coordsystem(tmp_path: Path) -> None:
    _electrodes(tmp_path, ROWS_MM)
    assert sidecar_positions(tmp_path, DATA) == ({}, "coordsystem_missing")


def test_unreadable_electrodes_file(tmp_path: Path) -> None:
    _tree(tmp_path)
    (tmp_path / EEG_DIR / "sub-01_electrodes.tsv").write_bytes(b"")
    _coordsystem(tmp_path, "CapTrak", "mm")
    assert sidecar_positions(tmp_path, DATA) == ({}, "unreadable")


@pytest.mark.parametrize("units", ["n/a", "inch", "", None])
def test_unknown_units(tmp_path: Path, units: str | None) -> None:
    """EEGCoordinateUnits must be m, cm or mm; "n/a" (allowed by BIDS) gives no positions."""
    _electrodes(tmp_path, ROWS_MM)
    _coordsystem(tmp_path, "CapTrak", units)
    assert sidecar_positions(tmp_path, DATA) == ({}, "units_unknown")


@pytest.mark.parametrize("system", ["Other", "MNI152NLin2009cAsym", "fsaverage", ""])
def test_unsupported_coordinate_system(tmp_path: Path, system: str) -> None:
    """Template spaces and "Other" have no known orientation relative to the head."""
    _electrodes(tmp_path, ROWS_MM)
    _coordsystem(tmp_path, system, "mm")
    assert sidecar_positions(tmp_path, DATA) == ({}, "frame_unsupported")


@pytest.mark.parametrize(
    ("system", "units", "factor"),
    [
        ("CapTrak", "mm", 0.001),
        ("CapTrak", "MM", 0.001),
        ("ElektaNeuromag", "cm", 0.01),
        ("ChietiItab", "m", 1.0),
    ],
)
def test_ras_systems_are_scaled_to_metres(tmp_path: Path, system: str, units: str, factor: float) -> None:
    """RAS systems keep their orientation; the units become metres."""
    _electrodes(tmp_path, ROWS_MM)
    _coordsystem(tmp_path, system, units)
    found, reason = sidecar_positions(tmp_path, DATA)
    assert reason is None
    _assert_positions(found, _scaled(ROWS_MM, factor))


@pytest.mark.parametrize("system", ["EEGLAB", "EEGLAB-HJ", "CTF", "4DBti", "KitYokogawa"])
def test_als_systems_are_turned_to_ras(tmp_path: Path, system: str) -> None:
    """ALS (x anterior, y left) to RAS (x right, y anterior): (x, y, z) -> (-y, x, z)."""
    rows = {"Fp1": (8.39, 2.94, -0.70), "T8": (-1.60, -8.42, -0.93), "Cz": (-0.92, -0.04, 10.02)}
    _electrodes(tmp_path, rows)
    _coordsystem(tmp_path, system, "cm")
    found, reason = sidecar_positions(tmp_path, DATA)
    assert reason is None
    _assert_positions(found, {label: (-y * 0.01, x * 0.01, z * 0.01) for label, (x, y, z) in rows.items()})
    assert found["Fp1"][0] < 0 < found["Fp1"][1]  # left frontal stays left frontal
    assert found["T8"][0] > 0  # right temporal is on the right


def test_rows_without_coordinates_are_skipped(tmp_path: Path) -> None:
    """n/a, non-numeric, non-finite and all-zero rows have no position; the other rows are kept."""
    rows: dict[str, tuple[Any, Any, Any]] = {
        "Fp1": ("n/a", "n/a", "n/a"),
        "Fp2": (29.8, 84.9, -7.1),
        "F3": (0, 0, 0),
        "F4": ("abc", 1, 2),
        "C3": ("inf", 1, 2),
        "C4": (67.1, "n/a", 63.6),
        "O1": (-29.5, -112.5, 0.0),
    }
    _electrodes(tmp_path, rows)
    _coordsystem(tmp_path, "CapTrak", "mm")
    found, reason = sidecar_positions(tmp_path, DATA)
    assert reason is None
    _assert_positions(found, {"Fp2": (0.0298, 0.0849, -0.0071), "O1": (-0.0295, -0.1125, 0.0)})


def test_no_row_with_coordinates(tmp_path: Path) -> None:
    _electrodes(tmp_path, {"Fp1": ("n/a", "n/a", "n/a"), "Fp2": (0, 0, 0)})
    _coordsystem(tmp_path, "CapTrak", "mm")
    assert sidecar_positions(tmp_path, DATA) == ({}, "no_coordinates")


def test_space_entity_pairs_electrodes_and_coordsystem(tmp_path: Path) -> None:
    """The coordsystem.json with the same space entity as the electrodes.tsv applies, not another one."""
    _electrodes(tmp_path, ROWS_MM, name="sub-01_space-CapTrak_electrodes.tsv")
    _coordsystem(tmp_path, "CapTrak", "mm", name="sub-01_space-CapTrak_coordsystem.json")
    _coordsystem(tmp_path, "Other", "m", name="sub-01_space-Other_coordsystem.json")  # sorts last
    found, reason = sidecar_positions(tmp_path, DATA)
    assert reason is None
    _assert_positions(found, _scaled(ROWS_MM, 0.001))


def test_space_entity_must_match(tmp_path: Path) -> None:
    """An electrodes.tsv with a space entity has no coordsystem.json without it, and vice versa."""
    _electrodes(tmp_path, ROWS_MM, name="sub-01_space-CapTrak_electrodes.tsv")
    _coordsystem(tmp_path, "CapTrak", "mm")
    assert sidecar_positions(tmp_path, DATA) == ({}, "coordsystem_missing")

    other = tmp_path / "other"
    _electrodes(other, ROWS_MM)
    _coordsystem(other, "CapTrak", "mm", name="sub-01_space-CapTrak_coordsystem.json")
    assert sidecar_positions(other, DATA) == ({}, "coordsystem_missing")


def test_electrodes_of_the_data_file_only(tmp_path: Path) -> None:
    """Sidecars of another subject do not apply (BIDS inheritance)."""
    folder = _tree(tmp_path)
    (folder / "sub-02_electrodes.tsv").write_bytes(b"name\tx\ty\tz\nFp1\t1\t2\t3\n")
    _coordsystem(tmp_path, "CapTrak", "mm", name="sub-02_coordsystem.json")
    assert sidecar_positions(tmp_path, DATA) == ({}, None)
