"""Setups for the rule cases of the pack gbt47127 (NG-F03, RP-11; P7, A-113 ff.). Each builds, from the BIDS
fixture ``bids_ok``, a complete GB/T 47127 data set in the temporary folder (two subjects, modality folder
EEG, sidecar, channel, electrode and event tables) and applies at most one change:

- ``gbt_ok``: the complete data set; every rule of the pack passes, except the timestamp rule, which has no
  file name with a timestamp to judge (not applicable);
- ``gbt_timestamp_ok``: sub-01's recording named with the timestamp 20261109-101010;
- ``gbt_<rule>``: one element of the clause inventory broken, so that the rule fails (see FAILING below).

GB/T data sets are built at run time, never committed as fixtures: they are derived from ``bids_ok``."""

from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Callable
from pathlib import Path

Setup = Callable[[Path, Path], tuple[Path, dict[str, object]]]
PACKS = ("gbt47127",)


def _tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    lines = ["\t".join(header), *("\t".join(row) for row in rows)]
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def _subject(bids: Path, root: Path, source: str, label: str) -> None:
    src = bids / f"sub-{source}" / "eeg"
    folder = root / f"sub-{label}" / "EEG"
    folder.mkdir(parents=True)
    stem = f"sub-{label}_task-rest"
    shutil.copyfile(src / f"sub-{source}_task-rest_eeg.edf", folder / f"{stem}_EEG.edf")
    sidecar = json.loads((src / f"sub-{source}_task-rest_eeg.json").read_text(encoding="utf-8"))
    channels = _rows(src / f"sub-{source}_task-rest_channels.tsv")
    gbt_sidecar = {
        "TaskName": "rest",
        "EEGReference": sidecar["EEGReference"],
        "SamplingFrequency": sidecar["SamplingFrequency"],
        "PowerlineFrequency": sidecar["PowerLineFrequency"],
        "ChannelCount": len(channels),
        "SoftwareFilters": "n/a",
    }
    (folder / f"{stem}_EEG.json").write_text(json.dumps(gbt_sidecar), encoding="utf-8")
    _tsv(
        folder / f"{stem}_channels.tsv",
        ["Name", "Type", "Unit"],
        [[c["name"], c["type"], c["units"]] for c in channels],
    )
    electrodes = _rows(src / f"sub-{source}_electrodes.tsv")
    _tsv(
        folder / f"{stem}_electrodes.tsv",
        ["Name", "X", "Y", "Z"],
        [[e["name"], e["x"], e["y"], e["z"]] for e in electrodes],
    )
    _tsv(folder / f"{stem}_EEG_events.tsv", ["Onset", "Duration", "Value"], [["1.0", "0.5", "stim"]])


def _build(bids: Path, tmp: Path) -> Path:
    root = tmp / "gbt"
    root.mkdir(parents=True)
    description = {"Name": "neurogrid_gbt_demo", "Version": "GB/T 47127-2026"}
    (root / "dataset_description.json").write_text(json.dumps(description), encoding="utf-8")
    _tsv(root / "participants.tsv", ["ParticipantId"], [["sub-01"], ["sub-02"]])
    for label in ("01", "02"):
        _subject(bids, root, label, label)
    return root


def _eeg(root: Path) -> Path:
    return root / "sub-01" / "EEG"


STEM = "sub-01_task-rest"


def _sidecar(root: Path, **changes: object) -> None:
    path = _eeg(root) / f"{STEM}_EEG.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    path.write_text(json.dumps(data), encoding="utf-8")


def _rename_stem(root: Path, new: str) -> None:
    folder = _eeg(root)
    for name in (f"{STEM}_EEG.edf", f"{STEM}_EEG.json", f"{STEM}_EEG_events.tsv"):
        (folder / name).rename(folder / name.replace("_EEG", f"_{new}_EEG"))


def _add_subject(label: str) -> Callable[[Path], None]:
    def add(root: Path) -> None:
        folder = root / f"sub-{label}" / "EEG"
        shutil.copytree(root / "sub-02" / "EEG", folder)
        for path in folder.iterdir():
            path.rename(folder / path.name.replace("sub-02", f"sub-{label}"))
        table = root / "participants.tsv"
        table.write_bytes(table.read_bytes() + f"sub-{label}\n".encode())

    return add


def _two_sessions(root: Path) -> None:
    for session in ("ses-01", "ses-02"):
        target = root / "sub-01" / session / "EEG"
        shutil.copytree(_eeg(root), target)
        for path in target.iterdir():
            path.rename(target / path.name.replace("sub-01_", f"sub-01_{session}_"))
    shutil.rmtree(_eeg(root))


def _rename_folder(root: Path) -> None:
    temporary = root / "sub-01" / "EEG_"
    _eeg(root).rename(temporary)
    temporary.rename(root / "sub-01" / "Eeg")


# rule -> the change that makes it fail
FAILING: dict[str, Callable[[Path], None]] = {
    "GBT47127-STO-001": lambda r: (r / "dataset_description.json").write_text(json.dumps({"Name": "demo"})),
    "GBT47127-STO-002": lambda r: (r / "dataset_description.json").write_text(
        json.dumps({"Name": "demo data", "Version": "GB/T 47127-2026"})
    ),
    "GBT47127-STO-003": lambda r: (r / "participants.tsv").write_bytes(
        (r / "participants.tsv").read_bytes() + b"sub_03\n"
    ),
    "GBT47127-STO-004": lambda r: _tsv(r / "participants.tsv", ["ParticipantId"], [["sub-01"]]),
    "GBT47127-STO-005": _two_sessions,
    "GBT47127-STO-006": _add_subject("3"),
    "GBT47127-STO-007": _rename_folder,
    "GBT47127-STO-008": lambda r: (_eeg(r) / "notes.txt").write_text("x"),
    "GBT47127-STO-009": lambda r: (_eeg(r) / f"{STEM}_channels.tsv").rename(_eeg(r) / f"{STEM}_channels.txt"),
    "GBT47127-STO-010": lambda r: (_eeg(r) / f"{STEM}_EEG.json").unlink(),
    "GBT47127-STO-011": lambda r: _rename_stem(r, "20261109"),
    "GBT47127-STO-012": _add_subject("1234567"),
    "GBT47127-ACQ-001": lambda r: _sidecar(r, SamplingFrequency="512"),
    "GBT47127-ACQ-002": lambda r: (_eeg(r) / f"{STEM}_channels.tsv").unlink(),
    "GBT47127-ACQ-003": lambda r: _tsv(
        _eeg(r) / f"{STEM}_electrodes.tsv", ["Name", "X", "Y"], [["Cz", "0", "0"]]
    ),
    "GBT47127-ACQ-004": lambda r: _sidecar(r, SamplingFrequency=500),
    "GBT47127-ANN-001": lambda r: _tsv(
        _eeg(r) / f"{STEM}_EEG_events.tsv", ["Onset", "Value"], [["1.0", "stim"]]
    ),
    "GBT47127-ANN-002": lambda r: (_eeg(r) / f"{STEM}_EEG_events.tsv").rename(
        _eeg(r) / f"{STEM}_EEG.edf_events.tsv"
    ),
}


def _setup(change: Callable[[Path], None] | None) -> Setup:
    def setup(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
        root = _build(fixture, tmp)
        if change is not None:
            change(root)
        return root, {}

    return setup


GBT47127_SETUPS: dict[str, Setup] = {
    "gbt_ok": _setup(None),
    "gbt_timestamp_ok": _setup(lambda r: _rename_stem(r, "20261109-101010")),
    **{f"gbt_{rule.split('-', 1)[1].lower()}": _setup(change) for rule, change in FAILING.items()},
}
