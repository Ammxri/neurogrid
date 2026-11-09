"""The rule pack gbt47127 and the GB/T 47127—2026 reader (NG-F03, RP-11, ARC-04; P7, A-113 ff.).

A complete GB/T data set is built from the synthetic BIDS fixture by hand (independent of ``convert``): every
rule passes and the coverage is 1. Each mutation breaks one element of the clause inventory and the rule for
it fails with its reason. XML sidecars and CSV tables are read like JSON and TSV; a folder that is neither
BIDS nor GB/T shows pseudonymous names (A-51).
"""

from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from neurogrid import pipeline
from neurogrid.io import gbt47127 as gbt
from neurogrid.io.discover import pseudonym
from neurogrid.kernel.errors import InputError
from neurogrid.kernel.findings import Status
from neurogrid.model.results import Results

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"
BIDS = FIXTURES / "bids_ok"
AS_OF = date(2026, 11, 9)
SUBJECTS = ("01", "02")


def _tsv(path: Path, header: list[str], rows: list[list[str]], delimiter: str = "\t") -> None:
    lines = [delimiter.join(header), *(delimiter.join(map(str, row)) for row in rows)]
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def _subject(root: Path, source: str, label: str) -> None:
    src = BIDS / f"sub-{source}" / "eeg"
    folder = root / f"sub-{label}" / "EEG"
    folder.mkdir(parents=True)
    stem = f"sub-{label}_task-rest"
    shutil.copyfile(src / f"sub-{source}_task-rest_eeg.edf", folder / f"{stem}_EEG.edf")
    bids = json.loads((src / f"sub-{source}_task-rest_eeg.json").read_text(encoding="utf-8"))
    channels = _rows(src / f"sub-{source}_task-rest_channels.tsv")
    sidecar = {
        "TaskName": "rest",
        "EEGReference": bids["EEGReference"],
        "SamplingFrequency": bids["SamplingFrequency"],
        "PowerlineFrequency": bids["PowerLineFrequency"],
        "ChannelCount": len(channels),
    }
    (folder / f"{stem}_EEG.json").write_text(json.dumps(sidecar), encoding="utf-8")
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


def make_gbt(root: Path, labels: tuple[str, ...] = SUBJECTS) -> Path:
    root.mkdir(parents=True)
    description = {"Name": "neurogrid_gbt_demo", "Version": "GB/T 47127-2026", "Author": ["NeuroGrid test"]}
    (root / "dataset_description.json").write_text(json.dumps(description), encoding="utf-8")
    _tsv(root / "participants.tsv", ["ParticipantId", "Age"], [[f"sub-{label}", "30"] for label in labels])
    for index, label in enumerate(labels):
        _subject(root, SUBJECTS[index % 2], label)
    return root


def _check(root: Path) -> Results:
    return pipeline.run_check(root, pipeline.CheckOptions(as_of=AS_OF, rulepacks=("gbt47127",)))


def _failed(results: Results) -> list[tuple[str, str | None, str | None, str]]:
    return sorted(
        (f.rule_id, f.subkey, f.reason, f.object)
        for f in results.findings
        if f.rulepack == "gbt47127" and f.status is Status.FAILED
    )


@pytest.fixture
def gbt_set(tmp_path: Path) -> Path:
    return make_gbt(tmp_path / "gbt")


def test_complete_data_set_passes_every_rule(gbt_set: Path) -> None:
    """KONZEPT P7 DoD: a complete data set passes every rule of the pack; all its shall clauses are checked
    automatically (coverage 1); the layout is recognised."""
    assert gbt.looks_like_gbt47127(gbt_set)
    assert not gbt.looks_like_gbt47127(BIDS)
    results = _check(gbt_set)
    assert _failed(results) == []
    assert results.summary.coverage["gbt47127"] == 1.0
    statuses = {f.rule_id: f.status for f in results.findings if f.rulepack == "gbt47127"}
    assert statuses.get("GBT47127-STO-011") is Status.NOT_APPLICABLE  # no timestamp in a file name


def _eeg(root: Path, label: str = "01") -> Path:
    return root / f"sub-{label}" / "EEG"


def _stem(label: str = "01") -> str:
    return f"sub-{label}_task-rest"


def _edit_json(path: Path, **changes: object) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    path.write_text(json.dumps(data), encoding="utf-8")


def _rename_case(path: Path, name: str) -> None:
    temporary = path.with_name(path.name + "_")
    path.rename(temporary)
    temporary.rename(path.with_name(name))


def _with_timestamp(root: Path) -> None:
    folder, stem = _eeg(root), _stem()
    for name in (f"{stem}_EEG.edf", f"{stem}_EEG.json", f"{stem}_EEG_events.tsv"):
        (folder / name).rename(folder / name.replace("_EEG", "_20261109_EEG"))


def _extra_subject(label: str) -> Callable[[Path], None]:
    def add(root: Path) -> None:
        _subject(root, "02", label)
        table = root / "participants.tsv"
        table.write_bytes(table.read_bytes() + f"sub-{label}\t30\n".encode())

    return add


MUTATIONS: dict[str, tuple[Callable[[Path], None], str, str]] = {
    "version_missing": (
        lambda r: _edit_json(r / "dataset_description.json", Version=None),
        "GBT47127-STO-001",
        "gbt47127.field_missing",
    ),
    "name_with_space": (
        lambda r: _edit_json(r / "dataset_description.json", Name="demo data"),
        "GBT47127-STO-002",
        "gbt47127.name_characters",
    ),
    "participant_id_form": (
        lambda r: (r / "participants.tsv").write_bytes(
            (r / "participants.tsv").read_bytes() + b"sub_03\t30\n"
        ),
        "GBT47127-STO-003",
        "gbt47127.id_form",
    ),
    "folder_not_in_table": (
        lambda r: _subject(r, "02", "03"),
        "GBT47127-STO-004",
        "gbt47127.not_in_table",
    ),
    "two_sessions_without_table": (
        lambda r: (
            [shutil.copytree(_eeg(r), r / "sub-01" / session / "EEG") for session in ("ses-01", "ses-02")]
            and shutil.rmtree(_eeg(r))
        ),
        "GBT47127-STO-005",
        "gbt47127.file_missing",
    ),
    "not_zero_padded": (_extra_subject("3"), "GBT47127-STO-006", "gbt47127.not_zero_padded"),
    "modality_spelling": (
        lambda r: _rename_case(_eeg(r), "Eeg"),
        "GBT47127-STO-007",
        "gbt47127.modality_spelling",
    ),
    "stray_file": (
        lambda r: (_eeg(r) / "notes.txt").write_text("x"),
        "GBT47127-STO-008",
        "gbt47127.file_name",
    ),
    "metadata_format": (
        lambda r: (_eeg(r) / f"{_stem()}_channels.tsv").rename(_eeg(r) / f"{_stem()}_channels.txt"),
        "GBT47127-STO-009",
        "gbt47127.metadata_format",
    ),
    "sidecar_missing": (
        lambda r: (_eeg(r) / f"{_stem()}_EEG.json").unlink(),
        "GBT47127-STO-010",
        "gbt47127.file_missing",
    ),
    "timestamp_form": (_with_timestamp, "GBT47127-STO-011", "gbt47127.timestamp_form"),
    "digit_run": (_extra_subject("1234567"), "GBT47127-STO-012", "gbt47127.id_may_identify"),
    "sidecar_type": (
        lambda r: _edit_json(_eeg(r) / f"{_stem()}_EEG.json", SamplingFrequency="512"),
        "GBT47127-ACQ-001",
        "gbt47127.field_type",
    ),
    "channels_missing": (
        lambda r: (_eeg(r) / f"{_stem()}_channels.tsv").unlink(),
        "GBT47127-ACQ-002",
        "gbt47127.file_missing",
    ),
    "electrodes_column": (
        lambda r: _tsv(_eeg(r) / f"{_stem()}_electrodes.tsv", ["Name", "X", "Y"], [["Cz", "0", "0"]]),
        "GBT47127-ACQ-003",
        "gbt47127.column_missing",
    ),
    "rate_mismatch": (
        lambda r: _edit_json(_eeg(r) / f"{_stem()}_EEG.json", SamplingFrequency=500),
        "GBT47127-ACQ-004",
        "gbt47127.rate_signal",
    ),
    "count_mismatch": (
        lambda r: _edit_json(_eeg(r) / f"{_stem()}_EEG.json", ChannelCount=9),
        "GBT47127-ACQ-004",
        "gbt47127.count_table",
    ),
    "events_duration": (
        lambda r: _tsv(_eeg(r) / f"{_stem()}_EEG_events.tsv", ["Onset", "Value"], [["1.0", "stim"]]),
        "GBT47127-ANN-001",
        "gbt47127.column_missing",
    ),
    "events_extension": (
        lambda r: (_eeg(r) / f"{_stem()}_EEG_events.tsv").rename(_eeg(r) / f"{_stem()}_EEG.edf_events.tsv"),
        "GBT47127-ANN-002",
        "gbt47127.events_name_extension",
    ),
}


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_each_inventory_element_has_a_failing_rule(name: str, gbt_set: Path) -> None:
    """Inventory ↔ rules: breaking one element makes its rule fail with the reason for it."""
    mutate, rule, reason = MUTATIONS[name]
    mutate(gbt_set)
    failed = _failed(_check(gbt_set))
    assert any(r == rule and why == reason for r, _, why, _ in failed), failed


def test_xml_sidecar_and_csv_tables_are_read(gbt_set: Path) -> None:
    """7.1: key-value files in XML, tables in CSV (IQ-004: one root, a child element per field)."""
    folder, stem = _eeg(gbt_set), _stem()
    sidecar = json.loads((folder / f"{stem}_EEG.json").read_text(encoding="utf-8"))
    (folder / f"{stem}_EEG.json").unlink()
    body = "".join(f"<{key}>{value}</{key}>" for key, value in sidecar.items())
    (folder / f"{stem}_EEG.xml").write_text(f"<sidecar>{body}</sidecar>", encoding="utf-8")
    rows = _rows(folder / f"{stem}_channels.tsv")
    (folder / f"{stem}_channels.tsv").unlink()
    _tsv(folder / f"{stem}_channels.csv", ["Name", "Type", "Unit"], [list(row.values()) for row in rows], ",")
    assert _failed(_check(gbt_set)) == []


def test_xml_with_doctype_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="xml_declaration"):
        gbt.parse_key_value(b'<!DOCTYPE x [<!ENTITY a "b">]><x><Name>&a;</Name></x>', ".xml")
    assert gbt.parse_key_value(b"<x><Name>n</Name><Author>a</Author><Author>b</Author></x>", ".xml") == {
        "Name": "n",
        "Author": ["a", "b"],
    }


def test_file_name_parts() -> None:
    name = gbt.parse_name("sub-01_ses-02_task-rest_20260101-101010_EEG")
    assert (name.subject, name.session, name.task, name.timestamp, name.tail, name.valid) == (
        "01",
        "02",
        "rest",
        "20260101-101010",
        "EEG",
        True,
    )
    assert gbt.parse_name("sub-01_task-rest_channels").tail == "channels"
    assert not gbt.parse_name("sub-0_1_task-rest_EEG").valid
    assert not gbt.parse_name("notes").valid


def test_other_folders_show_pseudonymous_names(gbt_set: Path) -> None:
    """A-51: without a data set description the folder is no GB/T data set; names are pseudonymous."""
    (gbt_set / "dataset_description.json").unlink()
    (_eeg(gbt_set) / "notes.txt").write_text("x")
    assert not gbt.looks_like_gbt47127(gbt_set)
    results = _check(gbt_set)
    objects = {f.object for f in results.findings if f.rulepack == "gbt47127"}
    assert pseudonym(gbt.PurePosixPath("sub-01/EEG/notes.txt")) in objects
    assert not any("sub-01" in obj for obj in objects), objects


# --- convert --to gbt47127 (KONZEPT P7: round trip BIDS -> GB/T -> check without errors) -----------------


def _convert(source: Path, out: Path, config: Path | None = None) -> pipeline.ConvertSummary:
    return pipeline.run_convert(source, out, config_path=config, to="gbt47127", work_base=out.parent)


def _steps(out: Path) -> list[dict[str, object]]:
    return json.loads((out / ".neurogrid" / "processing_steps.json").read_text(encoding="utf-8"))


def test_bids_to_gbt_round_trip_checks_without_errors(tmp_path: Path) -> None:
    """DoD P7: the BIDS fixture converted to GB/T 47127 passes check without an error, the pack's coverage is
    1, and every written recording has its processing step with both hashes (DM-07)."""
    out = tmp_path / "gbt"
    summary = _convert(BIDS, out)
    assert (summary.converted, summary.skipped, summary.validator_errors) == (2, [], 0)
    assert summary.exit_code == 0 and summary.target == "gbt47127"
    assert gbt.looks_like_gbt47127(out)
    results = _check(out)
    assert results.summary.errors == 0, _failed(results)
    assert results.summary.coverage["gbt47127"] == 1.0
    assert not results.dataset.is_bids
    steps = _steps(out)
    assert [step["step"] for step in steps] == ["convert_to_gbt47127"] * 2
    assert all(step["input_hash"] and step["output_hash"] for step in steps)
    sidecar = json.loads((out / "sub-01" / "EEG" / "sub-01_task-rest_EEG.json").read_text(encoding="utf-8"))
    assert sidecar["PowerlineFrequency"] == 50 and sidecar["SoftwareFilters"] == "n/a"
    description = json.loads((out / "dataset_description.json").read_text(encoding="utf-8"))
    assert description["Version"] == gbt.FORMAT_VERSION


def test_raw_to_gbt_goes_through_bids_and_lists_gaps(tmp_path: Path) -> None:
    """A raw folder is converted to BIDS in the work folder first (both steps recorded); what nobody
    documented (the data set name, electrode positions) is left out and counted, never invented."""
    out = tmp_path / "gbt"
    summary = _convert(FIXTURES / "edf_ok", out, FIXTURES.parent / "documented.toml")
    assert summary.converted == 2
    assert summary.missing_fields == {"Name": 1, "electrodes": 2}
    assert summary.validator_errors > 0 and summary.exit_code == 1
    assert sorted({step["step"] for step in _steps(out)}) == ["convert_to_bids", "convert_to_gbt47127"]
    description = json.loads((out / "dataset_description.json").read_text(encoding="utf-8"))
    assert "Name" not in description


def test_brainvision_keeps_its_companions(tmp_path: Path) -> None:
    """A BrainVision recording keeps header, data and marker file under the GB/T name, with the references
    in the header pointing to them; the reader counts the three files as one signal file."""
    raw = tmp_path / "raw"
    shutil.copytree(FIXTURES / "brainvision_ok", raw)
    config = tmp_path / "neurogrid.toml"
    config.write_text(
        '[metadata.defaults]\nreference = "Cz"\nline_frequency_hz = 50\nsoftware_filters = "n/a"\n\n'
        '[[convert.files]]\npath = "rec.vhdr"\nsubject = "01"\ntask = "rec"\n',
        encoding="utf-8",
    )
    out = tmp_path / "gbt"
    summary = _convert(raw, out, config)
    assert summary.converted == 1, summary.skipped
    folder = out / "sub-01" / "EEG"
    names = sorted(p.name for p in folder.iterdir())
    assert {"sub-01_task-rec_EEG.vhdr", "sub-01_task-rec_EEG.eeg", "sub-01_task-rec_EEG.vmrk"} <= set(names)
    header = (folder / "sub-01_task-rec_EEG.vhdr").read_text(encoding="latin-1")
    assert "DataFile=sub-01_task-rec_EEG.eeg" in header and "MarkerFile=sub-01_task-rec_EEG.vmrk" in header
    (folder_view,) = [f for _, _, f in gbt.read_dataset(out).modality_folders()]
    assert [s.relative.name for s in folder_view.signals] == ["sub-01_task-rec_EEG.vhdr"]


def test_runs_without_distinct_times_are_not_written(tmp_path: Path) -> None:
    """GB/T 47127 has no run label: two runs of one task without acquisition times are not converted."""
    source = tmp_path / "bids"
    shutil.copytree(BIDS, source)
    folder = source / "sub-01" / "eeg"
    for path in sorted(folder.glob("sub-01_task-rest_*")):
        if path.name.endswith(("_eeg.edf", "_eeg.json", "_channels.tsv", "_events.tsv")):
            for run in ("1", "2"):
                shutil.copyfile(path, folder / path.name.replace("_task-rest_", f"_task-rest_run-{run}_"))
            path.unlink()
    summary = _convert(source, tmp_path / "gbt")
    reasons = {reason for _, reason in summary.skipped}
    assert reasons == {"convert.gbt_runs"} and summary.converted == 1


def test_output_must_be_empty(tmp_path: Path) -> None:
    out = tmp_path / "gbt"
    out.mkdir()
    (out / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(InputError, match="convert.output_not_empty"):
        _convert(BIDS, out)
    assert (out / "keep.txt").is_file()


# --- every modality of the format (tables 4 to 18) ---------------------------------------------------------

_SAMPLE = {"s": "x", "n": 1, "b": True, "S": ["x"], "N": [0.0]}
_CELL = {"s": "x", "n": "1"}


def _modality_set(root: Path, modality: str) -> Path:
    """A data set with one subject and one recording of ``modality``: the sidecar with every required field
    and the channel and position tables of the modality, from the field tables of the checks module."""
    from neurogrid.checks import gbt47127 as checks

    make = root / modality
    make.mkdir(parents=True)
    (make / "dataset_description.json").write_text(
        json.dumps({"Name": "demo", "Version": "1"}), encoding="utf-8"
    )
    _tsv(make / "participants.tsv", ["ParticipantId"], [["sub-01"]])
    folder = make / "sub-01" / modality
    folder.mkdir(parents=True)
    stem = f"sub-01_task-rest_{modality}"
    (folder / f"{stem}.dat").write_bytes(b"0")
    sidecar = {f.name: _SAMPLE[f.kind] for f in checks.SIDECAR_FIELDS_BY_MODALITY[modality] if f.required}
    (folder / f"{stem}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    tables = []
    if modality in checks.CHANNEL_FIELDS_BY_MODALITY:
        tables.append(("channels", checks.CHANNEL_FIELDS_BY_MODALITY[modality]))
    if modality in checks.POSITION_TABLES:
        kind, fields, _ = checks.POSITION_TABLES[modality]
        tables.append((kind, fields))
    for kind, fields in tables:
        header = [f.name for f in fields if f.required]
        row = [
            "source" if f.name == "Type" and kind == "optodes" else _CELL[f.kind]
            for f in fields
            if f.required
        ]
        _tsv(folder / f"sub-01_task-rest_{kind}.tsv", header, [row])
    return make


@pytest.mark.parametrize("modality", gbt.MODALITIES)
def test_every_modality_is_checked(modality: str, tmp_path: Path) -> None:
    """NG-F03 'all required elements': a complete recording of each modality passes the pack; without one
    required sidecar field it fails (tables 4, 7, 10, 12, 13, 16)."""
    from neurogrid.checks import gbt47127 as checks

    root = _modality_set(tmp_path, modality)
    assert gbt.looks_like_gbt47127(root)
    assert [f for f in _failed(_check(root)) if f[0] != "GBT47127-STO-002"] == []
    required = next(
        f.name for f in checks.SIDECAR_FIELDS_BY_MODALITY[modality] if f.required and f.name != "TaskName"
    )
    _edit_json(root / "sub-01" / modality / f"sub-01_task-rest_{modality}.json", **{required: None})
    failed = _failed(_check(root))
    assert ("GBT47127-ACQ-001", required, "gbt47127.field_missing") in {f[:3] for f in failed}, failed
