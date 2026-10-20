"""Review P2, discovery and BIDS validator: links and junctions are recorded, never opened and never let the
validator's view behind them reach the results; EEG formats outside the readable set are named as unsupported
(A-12, A-51, A-52, A-66, A-74, A-77).

Covers neurogrid.io.discover (skipped_links, link and hidden-file filtering before companions are read, links
inside folder formats, the .ahdr companion), neurogrid.io.KNOWN_UNSUPPORTED and, with real validator runs,
neurogrid.checks.bids dropping issues behind skipped links.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path, PurePosixPath

import pytest

import gen_fixtures  # type: ignore[import-not-found,unused-ignore]
from conftest import DOCUMENTED_TOML, dir_link  # type: ignore[import-not-found,unused-ignore]
from neurogrid import pipeline
from neurogrid.io import ADAPTERS, KNOWN_UNSUPPORTED, ORPHAN_SUFFIXES, discover
from neurogrid.io.brainvision import BrainVisionAdapter
from neurogrid.io.discover import pseudonym, scan
from neurogrid.kernel.findings import Status
from neurogrid.model.results import Results
from neurogrid.report.render import render_report

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
AS_OF = date(2026, 10, 11)
OUTSIDE_NAMES = ("Mueller_Hans_1975", "Patient_Zhang_San_1980", "sub-07_task-rest_eeg")
# Extensions added after the review (A-74): EEG data or header files NeuroGrid cannot read yet.
ADDED = (
    ".ahdr",
    ".lay",
    ".nedf",
    ".easy",
    ".trc",
    ".e",
    ".ns1",
    ".ns2",
    ".ns3",
    ".ns4",
    ".ns5",
    ".ns6",
    ".nev",
    ".ncs",
    ".xdfz",
    ".fif.gz",  # two parts: compared with the end of the name
)


def _names(files: list[discover.FoundFile]) -> list[str]:
    return sorted(f.relative.as_posix() for f in files)


def _outside(tmp_path: Path) -> Path:
    """A folder outside the dataset whose names identify persons (A-51) and look like BIDS data."""
    outside = tmp_path / "OUTSIDE"
    for name in OUTSIDE_NAMES[:2]:
        (outside / name).mkdir(parents=True)
        (outside / name / "notes.txt").write_text("x", encoding="utf-8")
    (outside / f"{OUTSIDE_NAMES[2]}.edf").write_bytes(b"0" * 300)
    return outside


class _Recorder:
    """Stands in for the header readers that discovery calls; records which files they were given."""

    def __init__(self) -> None:
        self.opened: list[str] = []

    def companions(self, path: Path) -> tuple[str, ...]:
        self.opened.append(path.name)
        return ()

    def referenced_fdt(self, path: Path) -> str | None:
        self.opened.append(path.name)
        return None


def _pretend_links(monkeypatch: pytest.MonkeyPatch, names: set[str]) -> _Recorder:
    """File symlinks need extra rights on Windows: ``names`` count as links, header reads are recorded."""
    real = discover.is_link
    recorder = _Recorder()
    monkeypatch.setattr(discover, "is_link", lambda path: path.name in names or real(path))
    monkeypatch.setattr(BrainVisionAdapter, "companions", staticmethod(recorder.companions))
    monkeypatch.setattr(discover, "referenced_fdt", recorder.referenced_fdt)
    return recorder


# --- links are recorded, not opened (A-52, A-66) ----------------------------------------------------------


def test_linked_headers_are_never_opened_to_find_companions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review P2: _companions parsed rec.vhdr and x.set (and loaded the .set for a stray .fdt) before the link
    check. Now only regular files reach it."""
    (tmp_path / "rec.vhdr").write_text(
        "Brain Vision Data Exchange Header File Version 1.0\n", encoding="utf-8"
    )
    (tmp_path / "x.set").write_bytes(b"MATLAB")
    (tmp_path / "stray.fdt").write_bytes(b"\0" * 4)  # would make discovery read every .set header
    (tmp_path / "own.vhdr").write_text(
        "Brain Vision Data Exchange Header File Version 1.0\n", encoding="utf-8"
    )
    (tmp_path / "own.set").write_bytes(b"MATLAB")
    recorder = _pretend_links(monkeypatch, {"rec.vhdr", "x.set"})
    result = scan(tmp_path)
    assert sorted(recorder.opened) == ["own.set", "own.vhdr"]
    assert result.links_skipped == 2
    assert result.skipped_links == [PurePosixPath("rec.vhdr"), PurePosixPath("x.set")]
    assert _names(result.recordings) == ["own.set", "own.vhdr"]
    assert _names(result.unsupported) == ["stray.fdt"]


def test_regular_companion_of_a_linked_header_is_an_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A link is not part of the dataset (A-66): it claims no companion, so its regular .eeg has no header and
    is reported like any orphan (M01-04, A-77); the link itself only counts in the notice."""
    gen_fixtures.write_brainvision(tmp_path / "rec.vhdr", seconds=1)
    _pretend_links(monkeypatch, {"rec.vhdr"})
    result = scan(tmp_path)
    assert result.recordings == [] and result.skipped_links == [PurePosixPath("rec.vhdr")]
    assert [(f.relative.as_posix(), f.suffix) for f in result.unsupported] == [("rec.eeg", ".eeg")]
    assert ".eeg" in ORPHAN_SUFFIXES and _names(result.other) == ["rec.vmrk"]


def test_hidden_headers_are_not_opened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gen_fixtures.write_brainvision(tmp_path / "rec.vhdr", data_file="data.eeg", seconds=1)
    (tmp_path / "rec.vhdr").rename(tmp_path / ".rec.vhdr")
    (tmp_path / ".x.set").write_bytes(b"MATLAB")
    (tmp_path / "stray.fdt").write_bytes(b"\0" * 4)
    recorder = _pretend_links(monkeypatch, set())
    result = scan(tmp_path)
    assert recorder.opened == [] and result.links_skipped == 0
    assert _names(result.unsupported) == ["data.eeg", "stray.fdt"]  # no visible header names them


def test_real_file_symlinks_are_not_opened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    gen_fixtures.write_brainvision(outside / "t.vhdr", seconds=1)
    root = tmp_path / "ds"
    root.mkdir()
    try:
        (root / "rec.vhdr").symlink_to(outside / "t.vhdr")
    except OSError:
        pytest.skip("file symlinks not permitted on this system")
    recorder = _Recorder()
    monkeypatch.setattr(BrainVisionAdapter, "companions", staticmethod(recorder.companions))
    result = scan(root)
    assert recorder.opened == [] and result.skipped_links == [PurePosixPath("rec.vhdr")]


def test_skipped_links_are_recorded_with_their_relative_paths(tmp_path: Path) -> None:
    outside = _outside(tmp_path)
    root = tmp_path / "ds"
    (root / "sub-01" / "eeg").mkdir(parents=True)
    shutil.copyfile(FIX / "edf_ok" / "rec_a.edf", root / "sub-01" / "eeg" / "rec.edf")
    dir_link(root / "extra", outside)
    dir_link(root / "sub-01" / "eeg" / "linked", outside)
    (root / ".hidden").mkdir()
    dir_link(root / ".hidden" / "inside", outside)  # hidden folders are not entered at all
    result = scan(root)
    assert result.skipped_links == [PurePosixPath("extra"), PurePosixPath("sub-01/eeg/linked")]
    assert result.links_skipped == 2 and _names(result.recordings) == ["sub-01/eeg/rec.edf"]


def test_links_inside_a_folder_format_are_recorded(tmp_path: Path) -> None:
    """Discovery does not enter an .mff folder, but the BIDS validator does: its links must be known too."""
    outside = _outside(tmp_path)
    mff = tmp_path / "ds" / "rec.mff"
    mff.mkdir(parents=True)
    (mff / "info.xml").write_bytes(b"<x/>")
    dir_link(mff / "j", outside)
    result = scan(tmp_path / "ds")
    assert result.skipped_links == [PurePosixPath("rec.mff/j")] and result.links_skipped == 1
    assert [(f.relative.as_posix(), f.size_bytes) for f in result.unsupported] == [("rec.mff", 4)]


def test_links_in_hidden_entries_of_a_folder_format_are_not_counted(tmp_path: Path) -> None:
    """Verifier, review P2: hidden entries are not counted anywhere else, and the validator does not report
    from them; inside an .mff they raised the links_skipped count (3 instead of 1 here)."""
    outside = _outside(tmp_path)
    mff = tmp_path / "ds" / "rec.mff"
    (mff / ".hid").mkdir(parents=True)
    (mff / ".hid" / "data.bin").write_bytes(b"\x00" * 6)
    (mff / "info.xml").write_bytes(b"<x/>")
    dir_link(mff / "j", outside)
    dir_link(mff / ".j2", outside)
    dir_link(mff / ".hid" / "j3", outside)
    result = scan(tmp_path / "ds")
    assert result.skipped_links == [PurePosixPath("rec.mff/j")] and result.links_skipped == 1
    assert [(f.relative.as_posix(), f.size_bytes) for f in result.unsupported] == [("rec.mff", 10)]


def test_link_paths_stay_out_of_the_scan_output(tmp_path: Path) -> None:
    outside = _outside(tmp_path)
    root = tmp_path / "ds"
    root.mkdir()
    shutil.copyfile(FIX / "edf_ok" / "rec_a.edf", root / "rec.edf")
    dir_link(root / "Link_Schmidt_1960", outside)
    result = pipeline.run_scan(root, show_paths=True)
    dumped = result.model_dump_json()
    assert result.links_skipped == 1
    assert "Link_Schmidt_1960" not in dumped and not any(name in dumped for name in OUTSIDE_NAMES)


# --- the validator does not report through links (A-51, A-66, review P2) -----------------------------------


@pytest.fixture(scope="module")
def linked_bids(tmp_path_factory: pytest.TempPathFactory) -> tuple[Results, Path]:
    """bids_ok with junctions at the root, in a subject folder and inside an .mff folder; one check run."""
    base = tmp_path_factory.mktemp("linked")
    outside = _outside(base)
    root = base / "ds"
    shutil.copytree(FIX / "bids_ok", root)
    dir_link(root / "extra", outside)
    dir_link(root / "sub-01" / "eeg" / "linked", outside)
    mff = root / "sub-02" / "eeg" / "sub-02_task-other_eeg.mff"
    mff.mkdir()
    (mff / "info.xml").write_bytes(b"<x/>")
    dir_link(mff / "j", outside)
    options = pipeline.CheckOptions(rulepacks=("core", "bids"), as_of=AS_OF, work_base=base / "work")
    return pipeline.run_check(root, options), root


def test_validator_names_behind_junctions_do_not_reach_results(
    linked_bids: tuple[Results, Path],
) -> None:
    """Review P2: res.json held findings for 'extra' and 'extra/Mueller_Hans_1975' although the console said
    the junction was not followed."""
    results, _root = linked_bids
    dumped = results.model_dump_json()
    for name in (*OUTSIDE_NAMES, '"extra', "eeg/linked", "eeg.mff/j"):
        assert name not in dumped, name
    for lang in ("zh", "en"):
        html = render_report(results, lang)
        assert not any(name in html for name in OUTSIDE_NAMES), lang
    (notice,) = [n for n in results.notices if n.message_key == "notice.links_skipped"]
    assert notice.params == {"count": 3}
    bids_objects = {f.object for f in results.findings if f.rule_id.startswith("BIDS-")}
    assert bids_objects  # the run did report: the .mff folder itself is unsupported and not BIDS-named
    assert all(not obj.startswith(("extra", "sub-01/eeg/linked")) for obj in bids_objects)
    assert all("/j" not in obj for obj in bids_objects)


def test_without_links_the_same_dataset_reports_nothing_from_outside(tmp_path: Path) -> None:
    """bids_ok passes the validator checks; with a junction it still does (before the fix: NOT_INCLUDED
    errors for the junction and the folders behind it, exit 1). Passed checks are not listed as findings."""
    root = tmp_path / "ds"
    shutil.copytree(FIX / "bids_ok", root)
    dir_link(root / "extra", _outside(tmp_path))
    options = pipeline.CheckOptions(rulepacks=("bids",), as_of=AS_OF, work_base=tmp_path / "work")
    results = pipeline.run_check(root, options)
    assert {"BIDS-STO-001", "BIDS-STO-002", "BIDS-STO-003"} <= {rule.id for rule in results.rules}
    assert [f for f in results.findings if f.rule_id.startswith("BIDS-")] == []
    assert (results.summary.exit_code, results.summary.errors) == (0, 0)
    assert [n.params for n in results.notices if n.message_key == "notice.links_skipped"] == [{"count": 1}]


# --- formats NeuroGrid cannot read (A-12, A-74) -------------------------------------------------------------


@pytest.mark.parametrize("suffix", ADDED)
def test_added_eeg_formats_are_unsupported_data_files(tmp_path: Path, suffix: str) -> None:
    assert suffix in KNOWN_UNSUPPORTED and suffix not in ADAPTERS
    name = f"patient{suffix.upper()}"  # extensions count without regard to case
    (tmp_path / name).write_bytes(b"\x00" * 64)
    result = scan(tmp_path)
    assert [(f.relative.as_posix(), f.suffix) for f in result.unsupported] == [(name, suffix)]
    assert result.other == []


@pytest.mark.parametrize(
    "name",
    [
        "data.dat",
        "notes.txt",
        "rec.21e",
        "rec.pnt",
        "rec.amrk",
        "rec.rs3",
        "rec.cef",
        "rec.bin",
        "rec.mat",
        "x.ee",
        "rec.gz",
        "rec.tar.gz",
        "rec.fif.gzip",
    ],
)
def test_generic_and_companion_extensions_stay_other_files(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_bytes(b"\x00" * 64)
    result = scan(tmp_path)
    assert result.unsupported == [] and _names(result.other) == [name]


def test_known_unsupported_list() -> None:
    """The list named in A-74 after the review; .eeg/.fdt are the orphan companions (A-77)."""
    assert KNOWN_UNSUPPORTED == {
        ".cnt", ".mff", ".xdf", ".xdfz", ".gdf", ".nwb", ".cdt", ".dap", ".mefd", ".nxe",
        ".ahdr", ".lay", ".nedf", ".easy", ".trc", ".e", ".fif.gz",
        ".ns1", ".ns2", ".ns3", ".ns4", ".ns5", ".ns6", ".nev", ".ncs",
        ".eeg", ".fdt",
    }  # fmt: skip
    assert ORPHAN_SUFFIXES <= KNOWN_UNSUPPORTED and not set(ADAPTERS) & KNOWN_UNSUPPORTED


def test_data_file_of_an_ascii_brainvision_header_is_no_orphan(tmp_path: Path) -> None:
    """The .ahdr is the unsupported recording; its .eeg (by stem or named in DataFile) is its companion."""
    gen_fixtures.write_brainvision(tmp_path / "rec.vhdr", data_file="Other.eeg", seconds=1)
    (tmp_path / "rec.vhdr").rename(tmp_path / "rec.ahdr")
    (tmp_path / "rec.vmrk").rename(tmp_path / "rec.amrk")
    (tmp_path / "two.ahdr").write_bytes(b"not a header")
    (tmp_path / "two.eeg").write_bytes(b"\x00" * 64)
    result = scan(tmp_path)
    assert _names(result.unsupported) == ["rec.ahdr", "two.ahdr"]
    assert _names(result.other) == ["Other.eeg", "rec.amrk", "two.eeg"] and result.recordings == []


def test_a_header_never_claims_a_recording_or_another_data_file(tmp_path: Path) -> None:
    """Verifier, review P2: a DataFile/MarkerFile (or the data field of a .set) that named a recording made
    discovery count that recording as a companion, so it was never checked and only counted as 'other file'
    (A-12). The .ahdr added after the review did the same. Data and marker files stay companions."""
    import scipy.io

    shutil.copyfile(FIX / "edf_ok" / "rec_a.edf", tmp_path / "victim.edf")
    shutil.copyfile(FIX / "edf_ok" / "rec_a.edf", tmp_path / "victim2.EDF")
    (tmp_path / "rec.cnt").write_bytes(b"\x00" * 64)
    gen_fixtures.write_brainvision(tmp_path / "other.vhdr", seconds=1)
    gen_fixtures.write_brainvision(tmp_path / "x.vhdr", data_file="x_data.bin", seconds=1)
    header = (tmp_path / "x.vhdr").read_text(encoding="utf-8")
    assert "DataFile=x_data.bin\n" in header and "MarkerFile=x.vmrk\n" in header
    (tmp_path / "x.vhdr").write_text(header.replace("MarkerFile=x.vmrk", "MarkerFile=victim.edf"), "utf-8")
    ascii_header = header.replace("DataFile=x_data.bin", "DataFile=rec.cnt")
    (tmp_path / "y.ahdr").write_text(
        ascii_header.replace("MarkerFile=x.vmrk", "MarkerFile=OTHER.vhdr"), "utf-8"
    )
    eeg = {"nbchan": 1.0, "pnts": 1.0, "trials": 1.0, "srate": 1.0, "data": "victim2.EDF"}
    scipy.io.savemat(tmp_path / "z.set", {"EEG": eeg})
    (tmp_path / "stray.fdt").write_bytes(b"\x00" * 4)  # makes discovery read the .set's data field
    result = scan(tmp_path)
    assert _names(result.recordings) == ["other.vhdr", "victim.edf", "victim2.EDF", "x.vhdr", "z.set"]
    assert _names(result.unsupported) == ["rec.cnt", "stray.fdt", "y.ahdr"]
    assert _names(result.other) == ["other.eeg", "other.vmrk", "x.vmrk", "x_data.bin"]


def test_compressed_fif_is_named_as_unsupported(tmp_path: Path) -> None:
    """A two-part extension (.fif.gz, A-74): scan shows it as such, check names it (M01-04, exit 1)."""
    data = tmp_path / "data"
    data.mkdir()
    shutil.copyfile(FIX / "edf_ok" / "rec_a.edf", data / "rest_s1.edf")
    (data / "run1_raw.FIF.gz").write_bytes(b"\x1f\x8b" + b"\x00" * 62)
    toml = tmp_path / "documented.toml"
    toml.write_text(DOCUMENTED_TOML, encoding="utf-8")
    scanned = pipeline.run_scan(data)
    assert [(f.format, f.id) for f in scanned.unsupported] == [
        ("FIF.GZ", pseudonym(PurePosixPath("run1_raw.FIF.gz")))
    ]
    assert scanned.other_files == 0
    results = pipeline.run_check(
        data, pipeline.CheckOptions(config_path=toml, as_of=AS_OF, work_base=tmp_path)
    )
    (finding,) = [f for f in results.findings if f.rule_id == "CORE-M01-04" and f.status is Status.FAILED]
    assert finding.file == pseudonym(PurePosixPath("run1_raw.FIF.gz")) + ".fif.gz"
    assert (finding.reason, finding.details) == ("format.unsupported", {"extension": ".fif.gz"})
    assert results.summary.exit_code == 1


def test_check_names_each_unsupported_file(tmp_path: Path) -> None:
    """Review P2 (repro_unknown_formats.py): 'recordings 1 unsupported 0 other 6', exit 0 before the fix."""
    data = tmp_path / "data"
    data.mkdir()
    shutil.copyfile(FIX / "edf_ok" / "rec_a.edf", data / "rest_s1.edf")
    names = ("patient1.ahdr", "patient2.TRC", "patient3.lay", "patient4.e", "patient5.nedf", "patient6.ns2")
    for name in names:
        (data / name).write_bytes(b"\x00" * 64)
    toml = tmp_path / "documented.toml"
    toml.write_text(DOCUMENTED_TOML, encoding="utf-8")
    scanned = pipeline.run_scan(data)
    assert (len(scanned.recordings), len(scanned.unsupported), scanned.other_files) == (1, 6, 0)
    results = pipeline.run_check(
        data, pipeline.CheckOptions(config_path=toml, as_of=AS_OF, work_base=tmp_path)
    )
    failed = {
        f.file: f.reason for f in results.findings if f.rule_id == "CORE-M01-04" and f.status is Status.FAILED
    }
    expected = {
        pseudonym(PurePosixPath(n)) + PurePosixPath(n).suffix.lower(): "format.unsupported" for n in names
    }
    assert failed == expected and results.summary.exit_code == 1


def test_scan_json_has_no_link_list(tmp_path: Path) -> None:
    """skipped_links is internal: the scan document keeps only the count."""
    root = tmp_path / "ds"
    root.mkdir()
    dir_link(root / "x", _outside(tmp_path))
    document = json.loads(pipeline.run_scan(root).model_dump_json())
    assert document["links_skipped"] == 1 and "skipped_links" not in document
