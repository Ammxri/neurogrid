"""Every rule of every built-in rule pack has a positive and a negative case (NG-N08).

A case names a fixture folder (and optionally a config and further rule packs) and the expected status of
the rule there: "passed" (positive case) or a non-passing status (negative case). A case may name a setup
(SETUPS) that prepares the run in a temporary folder, e.g. a copy of the fixture with a manifest or an
evidence file, and further CheckOptions fields such as ``strict``.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import pytest
from provenance_setups import PROVENANCE_SETUPS  # type: ignore[import-not-found]

from neurogrid import pipeline
from neurogrid.kernel.findings import Status
from neurogrid.kernel.rules import load_rulepack

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"


@dataclass(frozen=True)
class Case:
    rule: str
    folder: str
    expected: Status
    config: str | None = None
    rulepacks: tuple[str, ...] = ()
    setup: str | None = None  # name in SETUPS
    options: tuple[tuple[str, object], ...] = ()  # further CheckOptions fields, e.g. (("strict", True),)


# name -> function(fixture folder, temporary folder) -> (folder to check, further CheckOptions fields)
SETUPS: dict[str, Callable[[Path, Path], tuple[Path, dict[str, object]]]] = {}
SETUPS.update(PROVENANCE_SETUPS)  # P4 M13: manifest, manifest_outside, manifest_changed, manifest_invalid


def _ai_duplicate_copy(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    """M12-02: a raw folder in which one recording is copied under another name (same signal hash)."""
    folder = tmp / fixture.name
    shutil.copytree(fixture, folder)
    shutil.copyfile(folder / "rec_a.edf", folder / "rec_a_copy.edf")
    return folder, {}


def _ai_participants_split(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    """M12-01 through the participants.tsv split column (A-04): sub-01 has a row for train and one for val;
    without .neurogrid/splits.tsv the column is the split source."""
    folder = tmp / fixture.name
    shutil.copytree(fixture, folder)
    (folder / ".neurogrid" / "splits.tsv").unlink()
    rows = ["participant_id\tage\tsex\tsplit", "sub-01\t23\tF\ttrain", "sub-01\t23\tF\tval"]
    rows += [f"sub-0{n}\t40\tM\ttrain" for n in range(2, 7)]
    (folder / "participants.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return folder, {}


def _ai_unassigned_placeholder(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    """P4 review (AI14, AI15): a splits.tsv with only its header (a split source that assigns nothing) and
    the sex of sub-03 given as the placeholder "unknown"."""
    folder = tmp / fixture.name
    shutil.copytree(fixture, folder)
    (folder / ".neurogrid" / "splits.tsv").write_text("recording\tsplit\n", encoding="utf-8")
    table = folder / "participants.tsv"
    table.write_text(
        table.read_text(encoding="utf-8").replace("sub-03\t45\tF", "sub-03\t45\tunknown"), "utf-8"
    )
    return folder, {}


SETUPS["ai_duplicate_copy"] = _ai_duplicate_copy
SETUPS["ai_participants_split"] = _ai_participants_split
SETUPS["ai_unassigned_placeholder"] = _ai_unassigned_placeholder


WET = '[metadata.defaults]\nelectrode_type = "wet"\n'
DRY = '[metadata.defaults]\nelectrode_type = "dry"\n'
RAW_DOCUMENTED = (
    '[metadata.defaults]\nreference = "Cz"\nline_frequency_hz = 50\nsoftware_filters = "n/a"\n'
    '[[convert.files]]\npath = "rec.vhdr"\nsubject = "01"\ntask = "rest"\n'
)
BIDS = ("bids",)
# documents 60 Hz for data with 50 Hz line noise (A-47)
LINE_60_HZ = "[metadata.defaults]\nline_frequency_hz = 60\n"
GX = ("gxdsl008",)


def _evidence_setup(entry: str) -> Callable[[Path, Path], tuple[Path, dict[str, object]]]:
    """An evidence.yaml for GXDSL008-ACC-001 next to its document, outside the fixture (--evidence): documents
    are relative to the evidence file's folder (A-66, A-83)."""

    def setup(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
        tmp.mkdir(parents=True, exist_ok=True)
        (tmp / "it-security-sop.txt").write_bytes(
            b"AES-256 at rest; role concept v2 (synthetic test document)\n"
        )
        evidence = tmp / "evidence.yaml"
        evidence.write_text(f"format_version: 1\nevidence:\n  GXDSL008-ACC-001:\n{entry}", encoding="utf-8")
        return fixture, {"evidence_path": evidence}

    return setup


def _eeglab_v73(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    """An EEGLAB data set in a MAT v7.3 (HDF5) container, written at run time (not committed, see
    tools/gen_fixtures.py)."""
    from gen_fixtures import write_eeglab_v73  # type: ignore[import-not-found]

    write_eeglab_v73(tmp / "rec.set", seed=17)
    return tmp, {}


SETUPS.update(
    {
        "evidence_provided": _evidence_setup(
            "    status: provided\n    document: it-security-sop.txt\n"
            "    reviewer: QA\n    date: 2026-10-01\n"
        ),
        "evidence_open": _evidence_setup("    status: open\n"),
        "evidence_partial": _evidence_setup("    status: partial\n    document: it-security-sop.txt\n"),
        "evidence_not_applicable": _evidence_setup(
            "    status: not_applicable\n    justification: no data at rest on this system\n"
        ),
        "eeglab_v73": _eeglab_v73,
    }
)
AI_LABELS = '[ai]\nlabels = "events:trial_type"\n'  # M11 label source (A-81)
# P4 review: subject-level label sources, withheld by the A-51 table rule (cells of 1-4 subjects)
AGE_LABELS = '[ai]\nlabels = "participants:age"\n'
SEX_LABELS_STRICT = '[ai]\nlabels = "participants:sex"\n[rules."CORE-M11-01".params]\nmin_share = 0.9\n'
# P4 annotation (M10, A-80): continuous sleep staging with the vocabulary of tools/gen_fixtures.py
CONTINUOUS = (
    '[annotation]\nmode = "continuous"\nepoch_s = 30\n'
    'vocabulary = ["W", "N1", "N2", "N3", "R", "Lights off"]\n'
)
# the hypnograms of annotation_continuous_ok under names the stem heuristic cannot attach (see SETUPS)
FILES_TABLE = CONTINUOUS + "".join(
    f'[[annotation.files]]\npath = "scoring/hyp_{n}.edf"\nrecording = "night.edf"\nannotator = "s{n}"\n'
    for n in (1, 2, 3)
)


def _renamed_hypnograms(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    """A copy of the fixture whose hypnograms only [[annotation.files]] can attach (A-80)."""
    target = tmp / "renamed"
    (target / "scoring").mkdir(parents=True)
    shutil.copy2(fixture / "night.edf", target / "night.edf")
    for n in (1, 2, 3):
        shutil.copy2(fixture / f"night_scorer{n}.edf", target / "scoring" / f"hyp_{n}.edf")
    return target, {}


SETUPS["annotation_files_table"] = _renamed_hypnograms

# P4 integration: M11 class shares from the M10 annotations ([ai] labels = "annotations", A-80/A-81)
ANNOTATION_LABELS = CONTINUOUS + '[ai]\nlabels = "annotations"\n'
# scorer2 and scorer3 only: W/N1/N2/N3/R at 4/3/6/4/3 of 20 events (scorer1's "Lights off" left out)
TWO_SCORERS_LABELS = CONTINUOUS + 'annotators = ["scorer2", "scorer3"]\n[ai]\nlabels = "annotations"\n'


def _annotation_split(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
    """A copy of an annotation fixture with night.edf in train (.neurogrid/splits.tsv): its hypnograms count
    in train too (C10)."""
    folder = tmp / fixture.name
    shutil.copytree(fixture, folder)
    (folder / ".neurogrid").mkdir()
    (folder / ".neurogrid" / "splits.tsv").write_text(
        "recording\tsplit\nnight.edf\ttrain\n", encoding="utf-8"
    )
    return folder, {}


SETUPS["annotation_split"] = _annotation_split


# P4 review (R7-R9): annotation inputs that ended the run with exit 2 or were judged wrongly
def _annotation_copy(
    change: Callable[[Path], None],
) -> Callable[[Path, Path], tuple[Path, dict[str, object]]]:
    """A copy of the fixture, then ``change`` applied to the copy."""

    def setup(fixture: Path, tmp: Path) -> tuple[Path, dict[str, object]]:
        folder = tmp / fixture.name
        shutil.copytree(fixture, folder)
        change(folder)
        return folder, {}

    return setup


def _marker_night(folder: Path) -> None:
    """ANN03: night.edf as EDF+C whose only annotation is the technician's zero-duration "Lights off": no
    rater, so κ (0.667, not 0.333) and the gaps judge the three scorers alone."""
    from gen_fixtures import write_edf  # type: ignore[import-not-found]

    markers = ((12.0, 0.0, "Lights off"),)
    write_edf(folder / "night.edf", sfreq=16, seconds=300, labels=("C3", "C4"), plus="C", annotations=markers)


def _empty_scorer(folder: Path) -> None:
    """ANN04: a fourth scorer file without any annotation (a failed export): an annotator with coverage 0."""
    from gen_fixtures import write_annotation_edf  # type: ignore[import-not-found]

    write_annotation_edf(folder / "night_scorer4.edf", ())


def _negative_header_size(folder: Path) -> None:
    """ANN01: a hypnogram whose header size field reads -1 (numpy's memory map raised OverflowError)."""
    path = folder / "night_scorer1.edf"
    raw = bytearray(path.read_bytes())
    raw[184:192] = b"-1      "
    path.write_bytes(bytes(raw))


ODDBALL_EVENTS_TSV = Path("sub-01") / "eeg" / "sub-01_task-oddball_events.tsv"


def _overflowing_events(folder: Path) -> None:
    """ANN00: rows whose onset and duration are finite but whose end overflows (1e308 + 1e308) under both
    annotators: invalid rows, never an annotation (A-53)."""
    with (folder / ODDBALL_EVENTS_TSV).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("1e308\t1e308\tstandard\tA1\n1e308\t1e308\tstimx\tA2\n")


def _many_annotators(folder: Path) -> None:
    """ANN05: 101 annotators with one event each, one more than MAX_KAPPA_ANNOTATORS (A-53)."""
    rows = ["onset\tduration\ttrial_type\tannotator"]
    rows += [f"{1.2 + 2 * (n % 7)}\t0.6\tstandard\tR{n}" for n in range(101)]
    (folder / ODDBALL_EVENTS_TSV).write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")


SETUPS.update(
    {
        "annotation_marker_track": _annotation_copy(_marker_night),
        "annotation_empty_scorer": _annotation_copy(_empty_scorer),
        "annotation_negative_header": _annotation_copy(_negative_header_size),
        "events_overflow": _annotation_copy(_overflowing_events),
        "events_many_annotators": _annotation_copy(_many_annotators),
    }
)


CASES = [
    Case("CORE-M01-01", "edf_ok", Status.PASSED),
    Case("CORE-M01-01", "empty", Status.FAILED),
    Case("CORE-M01-02", "edf_ok", Status.PASSED),
    Case("CORE-M01-02", "edf_truncated", Status.FAILED),
    Case("CORE-M01-04", "edf_ok", Status.PASSED),
    Case("CORE-M01-04", "unsupported", Status.FAILED),
    Case("CORE-M01-05", "edf_ok", Status.PASSED),
    Case("CORE-M01-05", "edf_identifying", Status.FAILED),
    Case("CORE-M03-01", "edf_ok", Status.PASSED),
    Case("CORE-M03-01", "edf_lowrate", Status.FAILED),
    Case("CORE-M03-02", "edf_ok", Status.PASSED),
    Case("CORE-M03-02", "edf_mixed", Status.FAILED),
    Case(
        "CORE-M03-02",
        "edf_mixed",
        Status.PASSED,
        '[metadata]\nmixed_sampling_rates_reason = "two amplifiers"\n',
    ),
    # P2: further formats, companions, metadata, channels, impedance and the BIDS validator
    Case("CORE-M01-01", "bdf_ok", Status.PASSED),
    Case("CORE-M01-01", "brainvision_ok", Status.PASSED),
    Case("CORE-M01-01", "eeglab_ok", Status.PASSED),
    Case("CORE-M01-01", "eeglab_embedded", Status.PASSED),
    Case("CORE-M01-01", "brainvision_missing", Status.FAILED),
    Case("CORE-M01-02", "bdf_ok", Status.PASSED),
    Case("CORE-M01-02", "bdf_truncated", Status.FAILED),
    Case("CORE-M01-02", "brainvision_truncated", Status.FAILED),
    Case("CORE-M01-03", "brainvision_ok", Status.PASSED),
    Case("CORE-M01-03", "eeglab_ok", Status.PASSED),
    Case("CORE-M01-03", "brainvision_missing", Status.FAILED),
    Case("CORE-M01-03", "brainvision_unsafe", Status.FAILED),
    Case("CORE-M01-04", "orphan", Status.FAILED),
    Case("CORE-M02-01", "bids_ok", Status.PASSED),
    Case("CORE-M02-01", "brainvision_ok", Status.PASSED, RAW_DOCUMENTED),
    Case("CORE-M02-01", "bids_issues", Status.FAILED),
    Case("CORE-M02-01", "brainvision_ok", Status.FAILED),
    Case("CORE-M02-02", "bids_ok", Status.PASSED),
    Case("CORE-M02-02", "bids_issues", Status.FAILED),
    Case("CORE-M03-03", "bids_ok", Status.PASSED),
    Case("CORE-M03-03", "bids_issues", Status.FAILED),
    Case("CORE-M04-01", "bids_ok", Status.PASSED),
    Case("CORE-M04-01", "bids_issues", Status.FAILED),
    Case("CORE-M04-01", "bids_issues", Status.PASSED, '[metadata.channel_map]\nEXG1 = "Oz"\n'),
    Case("CORE-M04-02", "bids_ok", Status.PASSED),
    Case("CORE-M04-02", "bids_issues", Status.FAILED),
    Case("CORE-M04-03", "bids_ok", Status.PASSED),
    Case("CORE-M04-03", "bids_issues", Status.FAILED),
    Case("CORE-M04-04", "bids_ok", Status.PASSED),
    Case("CORE-M04-04", "bids_issues", Status.FAILED),
    Case("CORE-M04-05", "bids_ok", Status.PASSED),
    Case("CORE-M04-05", "bids_issues", Status.FAILED),
    Case("CORE-M05-01", "bids_ok", Status.PASSED),
    Case("CORE-M05-01", "brainvision_ok", Status.PASSED),
    Case("CORE-M05-01", "bids_issues", Status.FAILED),
    Case("CORE-M05-01", "brainvision_impedance", Status.FAILED),
    Case("CORE-M05-02", "bids_ok", Status.PASSED, WET),
    Case("CORE-M05-02", "brainvision_ok", Status.PASSED, WET),
    Case("CORE-M05-02", "bids_issues", Status.FAILED, WET),
    Case("CORE-M05-02", "brainvision_impedance", Status.FAILED, WET),
    Case("CORE-M05-02", "bids_ok", Status.NOT_CHECKABLE),
    Case("CORE-M05-02", "bids_issues", Status.NOT_APPLICABLE, DRY),
    Case("BIDS-STO-001", "bids_ok", Status.PASSED, rulepacks=BIDS),
    Case("BIDS-STO-001", "bids_issues", Status.FAILED, rulepacks=BIDS),
    Case("BIDS-STO-001", "edf_ok", Status.NOT_APPLICABLE, rulepacks=BIDS),
    Case("BIDS-STO-002", "bids_ok", Status.PASSED, rulepacks=BIDS),
    Case("BIDS-STO-002", "bids_issues", Status.FAILED, rulepacks=BIDS),
    Case("BIDS-STO-003", "bids_ok", Status.PASSED, rulepacks=BIDS),
    Case("BIDS-STO-003", "bids_issues", Status.FAILED, rulepacks=BIDS),
    # P3: signal quality M06–M09 at the calibrated thresholds, all from the measured values of the synthetic
    # recordings (tools/gen_fixtures.py): edf_quality_ok passes every rule, edf_quality_issues has one problem
    # per rule, edf_quality_artefacts is dominated by artefacts (ICLabel).
    Case("CORE-M06-01", "edf_quality_ok", Status.PASSED),  # 2 of 20 channels bad (0.1)
    Case("CORE-M06-01", "edf_quality_issues", Status.FAILED),  # 10 of 20 channels bad (0.5)
    Case("CORE-M06-01", "edf_ok", Status.NOT_CHECKABLE),  # 10 s of data: quality.too_short (A-79)
    Case("CORE-M07-01", "edf_quality_ok", Status.PASSED),  # ratios 0.0096–0.028
    Case("CORE-M07-01", "edf_quality_issues", Status.FAILED),  # 40 µV hum on T7, T8, P7, P8 (ratio ≥ 5)
    Case("CORE-M07-02", "edf_quality_ok", Status.PASSED),  # documented 50 Hz fits the 50 Hz hum
    Case("CORE-M07-02", "edf_quality_ok", Status.FAILED, LINE_60_HZ),  # 50 Hz median 8 × the 60 Hz one
    Case("CORE-M08-01", "edf_quality_ok", Status.PASSED),  # P8 flat in 2 of 70 windows (2.9 %)
    Case("CORE-M08-01", "edf_quality_issues", Status.FAILED),  # O2 flat for 10 s (14 %)
    Case("CORE-M08-02", "edf_quality_ok", Status.PASSED),  # P8 at the digital maximum in 2 of 70 windows
    Case("CORE-M08-02", "edf_quality_issues", Status.FAILED),  # F8 at the digital maximum for 6 s (8.6 %)
    Case("CORE-M09-01", "edf_quality_ok", Status.PASSED),  # 3 of 35 epochs rejected (0.086)
    Case("CORE-M09-01", "edf_quality_issues", Status.FAILED),  # 22 of 35 epochs rejected (0.63)
    Case("CORE-M09-02", "edf_quality_ok", Status.PASSED),  # 5 of 17 components not brain (0.29)
    Case("CORE-M09-02", "edf_quality_artefacts", Status.FAILED),  # 17 of 19 components not brain (0.89)
    Case("CORE-M09-02", "edf_quality_issues", Status.NOT_CHECKABLE),  # 10 good channels, ICA needs 16
    # P4 evidence area: gxdsl008 (GX-00..GX-05, A-40, A-83), loaded next to core; GX-05 with M13 (A-82)
    Case("CORE-M05-02", "edf_ok", Status.NOT_CHECKABLE),  # Q16: no impedance documented, never silent
    Case("GXDSL008-ACQ-001", "bids_ok", Status.PASSED, WET, GX),  # 3.5 kOhm per electrode
    Case("GXDSL008-ACQ-001", "brainvision_ok", Status.PASSED, WET, GX),
    Case("GXDSL008-ACQ-001", "bids_issues", Status.FAILED, WET, GX),
    Case("GXDSL008-ACQ-001", "brainvision_impedance", Status.FAILED, WET, GX),  # C3 25 kOhm
    Case("GXDSL008-ACQ-001", "bids_ok", Status.NOT_CHECKABLE, rulepacks=GX),  # electrode type unknown
    Case("GXDSL008-ACQ-001", "edf_ok", Status.NOT_CHECKABLE, rulepacks=GX),  # impedance.not_documented
    Case("GXDSL008-ACQ-001", "bids_issues", Status.NOT_APPLICABLE, DRY, GX),
    Case("GXDSL008-ACQ-002", "edf_ok", Status.PASSED, rulepacks=GX),  # 512 Hz
    Case("GXDSL008-ACQ-002", "edf_lowrate", Status.FAILED, rulepacks=GX),  # 256 Hz
    Case("GXDSL008-STO-001", "edf_ok", Status.PASSED, rulepacks=GX),
    Case("GXDSL008-STO-001", "edf_plus_d", Status.PASSED, rulepacks=GX),  # EDF+D counts as EDF
    Case("GXDSL008-STO-001", "eeglab_ok", Status.PASSED, rulepacks=GX, setup="eeglab_v73"),  # HDF5
    Case("GXDSL008-STO-001", "bdf_ok", Status.FAILED, rulepacks=GX),
    Case("GXDSL008-STO-001", "brainvision_ok", Status.FAILED, rulepacks=GX),
    Case("GXDSL008-STO-001", "eeglab_ok", Status.FAILED, rulepacks=GX),  # MATLAB v5
    Case("GXDSL008-ACC-001", "edf_ok", Status.EVIDENCE_OPEN, rulepacks=GX),  # no evidence.yaml
    Case("GXDSL008-ACC-001", "edf_ok", Status.PASSED, rulepacks=GX, setup="evidence_provided"),
    Case("GXDSL008-ACC-001", "edf_ok", Status.EVIDENCE_OPEN, rulepacks=GX, setup="evidence_open"),
    Case("GXDSL008-ACC-001", "edf_ok", Status.EVIDENCE_OPEN, rulepacks=GX, setup="evidence_partial"),
    Case("GXDSL008-ACC-001", "edf_ok", Status.NOT_APPLICABLE, rulepacks=GX, setup="evidence_not_applicable"),
    # GX-05 on the M13 check provenance.manifest_matches (A-15, A-82): manifest present and every file matches
    Case("GXDSL008-STO-002", "edf_ok", Status.PASSED, rulepacks=GX, setup="manifest"),
    Case("GXDSL008-STO-002", "bids_ok", Status.PASSED, rulepacks=GX, setup="manifest_outside"),
    Case("GXDSL008-STO-002", "edf_ok", Status.FAILED, rulepacks=GX),  # no manifest: the warning
    Case("GXDSL008-STO-002", "edf_ok", Status.FAILED, rulepacks=GX, setup="manifest_changed"),
    Case("GXDSL008-STO-002", "edf_ok", Status.FAILED, rulepacks=GX, setup="manifest_invalid"),
    # P4 ai: M11/M12 (tools/gen_fixtures.py). bids_ai_ok passes every rule: classes A/B/C at 0.4/0.3/0.3 in
    # every scope, age and sex for all six subjects, subject-disjoint splits, seven different signals.
    # bids_ai_issues has one problem per rule.
    Case("CORE-M11-01", "bids_ai_ok", Status.PASSED, AI_LABELS),
    Case("CORE-M11-01", "bids_ai_issues", Status.FAILED, AI_LABELS),  # 'rare' 1 of 40 events; test lacks C
    Case("CORE-M11-01", "edf_ok", Status.NOT_APPLICABLE),  # no [ai] labels (A-81)
    Case("CORE-M11-01", "edf_ok", Status.NOT_CHECKABLE, AI_LABELS),  # events.tsv labels need BIDS
    # P4 review (A-51 table rule): age groups of 6 subjects are withheld; 1 of 6 reaches 0.05, so every
    # possible small cell passes
    Case("CORE-M11-01", "bids_ai_ok", Status.PASSED, AGE_LABELS, setup="ai_unassigned_placeholder"),
    # P4 review repair (AI10, INT38, CON48): without assigned splits the scope all surely holds the small
    # cell (sex of 5 subjects, "unknown" is no label): even 4 of 5 is below 0.9
    Case("CORE-M11-01", "bids_ai_ok", Status.FAILED, SEX_LABELS_STRICT, setup="ai_unassigned_placeholder"),
    # with splits the numbers decide neither all (6) nor train (4: 1 of 4 fails, 4 of 4 passes)
    Case("CORE-M11-01", "bids_ai_ok", Status.NOT_CHECKABLE, SEX_LABELS_STRICT),
    Case("CORE-M11-02", "bids_ai_ok", Status.PASSED, AI_LABELS),
    Case("CORE-M11-02", "bids_ai_issues", Status.FAILED, AI_LABELS),  # sub-03 age n/a, sub-04 without a row
    Case("CORE-M11-02", "bids_ok", Status.FAILED),  # participants.tsv without age and sex columns
    Case("CORE-M11-02", "edf_ok", Status.NOT_CHECKABLE),  # raw folder without mapping: subjects unknown
    # P4 review (AI15): sex "unknown" is a placeholder, not documented
    Case("CORE-M11-02", "bids_ai_ok", Status.FAILED, AGE_LABELS, setup="ai_unassigned_placeholder"),
    Case("CORE-M12-01", "bids_ai_ok", Status.PASSED, AI_LABELS),
    Case("CORE-M12-01", "bids_ai_issues", Status.FAILED, AI_LABELS),  # sub-02 in train and test (NG-F09)
    Case("CORE-M12-01", "bids_ai_ok", Status.FAILED, setup="ai_participants_split"),  # sub-01 train + val
    Case("CORE-M12-01", "bids_ok", Status.NOT_APPLICABLE),  # no splits (A-21, C11)
    # P4 review (AI14): splits.tsv with only its header assigns no recording
    Case("CORE-M12-01", "bids_ai_ok", Status.NOT_APPLICABLE, AGE_LABELS, setup="ai_unassigned_placeholder"),
    Case("CORE-M12-02", "bids_ai_ok", Status.PASSED, AI_LABELS),
    Case("CORE-M12-02", "edf_ok", Status.PASSED),  # rec_a and rec_b have different signals
    Case("CORE-M12-02", "bids_ai_issues", Status.FAILED, AI_LABELS),  # sub-05 run-1 = sub-01 run-1
    Case("CORE-M12-02", "edf_ok", Status.FAILED, setup="ai_duplicate_copy"),  # a copy under another name
    # P4 provenance (M13, A-82): manifests are built per case (tests/rules/provenance_setups.py)
    Case("CORE-M13-01", "edf_ok", Status.PASSED, setup="manifest"),
    Case("CORE-M13-01", "bids_ok", Status.PASSED, setup="manifest_outside"),
    Case("CORE-M13-01", "edf_ok", Status.FAILED),  # no manifest: warning
    Case("CORE-M13-01", "edf_ok", Status.FAILED, options=(("strict", True),)),  # --strict: error
    Case("CORE-M13-01", "edf_ok", Status.FAILED, setup="manifest_invalid"),
    Case("CORE-M13-02", "edf_ok", Status.PASSED, setup="manifest"),
    Case("CORE-M13-02", "bids_ok", Status.PASSED, setup="manifest_outside"),
    Case("CORE-M13-02", "edf_ok", Status.FAILED, setup="manifest_changed"),
    Case("CORE-M13-02", "edf_ok", Status.NOT_APPLICABLE),  # no manifest: nothing to compare (M13-01 says it)
    Case("CORE-M13-02", "edf_ok", Status.NOT_CHECKABLE, setup="manifest_invalid"),
    Case("CORE-M13-03", "provenance_ok", Status.PASSED),  # provenance.yaml with steps and software
    Case("CORE-M13-03", "edf_ok", Status.FAILED),  # no source at all
    Case("CORE-M13-03", "bids_ok", Status.FAILED),  # GeneratedBy without Version, no processing steps
    Case("CORE-M13-03", "provenance_incomplete", Status.FAILED),  # a step without version
    Case("CORE-M13-03", "provenance_steps_invalid", Status.FAILED),  # processing_steps.json not usable
    # P4 review R12: deep manifests and steps (A-53), refused names (critic X8)
    Case("CORE-M13-01", "edf_ok", Status.FAILED, setup="manifest_deep"),  # a finding, no RecursionError
    Case("CORE-M13-02", "edf_ok", Status.NOT_CHECKABLE, setup="manifest_deep"),
    Case("CORE-M13-02", "edf_ok", Status.PASSED, setup="refused_folder"),
    Case("CORE-M13-02", "edf_ok", Status.FAILED, setup="refused_folder_changed"),  # walked below it
    Case("CORE-M13-01", "edf_ok", Status.PASSED, setup="names_alike"),  # the reader takes its own manifest
    Case("CORE-M13-02", "edf_ok", Status.PASSED, setup="names_alike"),
    Case("CORE-M13-02", "edf_ok", Status.FAILED, setup="names_alike_missing"),
    Case("CORE-M13-03", "edf_ok", Status.PASSED, setup="steps_deepest"),
    Case("CORE-M13-03", "edf_ok", Status.FAILED, setup="steps_too_deep"),  # not counted as documented
    # --- P4 annotation (M10, A-80): fixtures of tools/gen_fixtures.py ---
    Case("CORE-M10-01", "annotation_continuous_ok", Status.PASSED, CONTINUOUS),  # mean kappa 0.667
    Case("CORE-M10-01", "annotation_continuous_issues", Status.FAILED, CONTINUOUS),  # mean kappa 0.024
    Case("CORE-M10-01", "edf_ok", Status.NOT_APPLICABLE),  # no annotations: one dataset-level finding
    Case(
        "CORE-M10-01",
        "annotation_continuous_ok",
        Status.PASSED,
        FILES_TABLE,
        setup="annotation_files_table",
    ),
    Case("CORE-M10-02", "annotation_continuous_ok", Status.PASSED, CONTINUOUS),
    Case("CORE-M10-02", "annotation_continuous_issues", Status.FAILED, CONTINUOUS),  # "Stage 2"
    Case("CORE-M10-02", "bids_events_issues", Status.FAILED),  # "stimx" not in events.json Levels
    Case("CORE-M10-03", "annotation_continuous_ok", Status.PASSED, CONTINUOUS),
    Case("CORE-M10-03", "annotation_continuous_issues", Status.FAILED, CONTINUOUS),  # 180-210 s unscored
    Case("CORE-M10-03", "annotation_continuous_ok", Status.NOT_APPLICABLE),  # events mode
    Case("CORE-M10-04", "annotation_continuous_ok", Status.PASSED, CONTINUOUS),
    Case("CORE-M10-04", "annotation_continuous_issues", Status.FAILED, CONTINUOUS),  # 80-90 s
    Case("CORE-M10-04", "bids_events_issues", Status.FAILED),  # two "standard" events overlap
    # --- P4 review (R7-R9): inputs that ended the run with exit 2 or were judged wrongly ---
    Case(
        "CORE-M10-01",
        "annotation_continuous_ok",
        Status.PASSED,
        CONTINUOUS,
        setup="annotation_marker_track",
    ),  # ANN03: the markers in night.edf are no rater
    Case(
        "CORE-M10-03",
        "annotation_continuous_ok",
        Status.PASSED,
        CONTINUOUS,
        setup="annotation_marker_track",
    ),  # ANN03: no coverage 0 for the markers
    Case(
        "CORE-M10-03",
        "annotation_continuous_ok",
        Status.FAILED,
        CONTINUOUS,
        setup="annotation_empty_scorer",
    ),  # ANN04: the empty scorer file has coverage 0
    Case(
        "CORE-M10-01",
        "annotation_continuous_ok",
        Status.NOT_CHECKABLE,
        CONTINUOUS,
        setup="annotation_negative_header",
    ),  # ANN01: annotation.unreadable
    Case("CORE-M10-01", "bids_events_issues", Status.PASSED, setup="events_overflow"),  # ANN00
    Case("CORE-M10-01", "bids_events_issues", Status.NOT_CHECKABLE, setup="events_many_annotators"),  # ANN05
    # --- P4 integration: CORE-M11-01 with [ai] labels = "annotations" (A-81) in the scopes all and train ---
    Case(
        "CORE-M11-01",
        "annotation_continuous_ok",
        Status.PASSED,
        TWO_SCORERS_LABELS,
        setup="annotation_split",
    ),  # every class at least 3 of 20 events
    Case(
        "CORE-M11-01",
        "annotation_continuous_issues",
        Status.FAILED,
        ANNOTATION_LABELS,
        setup="annotation_split",
    ),  # "Stage 2" 1 of 29 events
    Case("CORE-M11-01", "edf_ok", Status.NOT_CHECKABLE, '[ai]\nlabels = "annotations"\n'),  # no annotation
]


def builtin_rule_ids() -> set[str]:
    ids: set[str] = set()
    for entry in resources.files("neurogrid.rulepacks").iterdir():
        if entry.name.endswith(".yaml"):
            pack = load_rulepack(entry.read_text(encoding="utf-8"), origin="builtin").pack
            ids.update(rule.id for rule in pack.rules)
    return ids


# Statuses per rule of one run, keyed by fixture, configuration and rule packs. A run is deterministic, so
# the cases of the same run share it: the signal quality sample (M06/M09) costs seconds per recording.
_RUNS: dict[tuple[object, ...], dict[str, set[Status]]] = {}


def statuses(case: Case, tmp_path: Path) -> set[Status]:
    key = (case.folder, case.config, case.rulepacks, case.setup, case.options)
    if key not in _RUNS:
        config_path = None
        if case.config:
            config_path = tmp_path / "neurogrid.toml"
            config_path.write_text(case.config, encoding="utf-8")
        target, extra = FIX / case.folder, {}
        if case.setup:
            target, extra = SETUPS[case.setup](FIX / case.folder, tmp_path / "setup")
        options = {**dict(case.options), **extra}
        results = pipeline.run_check(
            target,
            pipeline.CheckOptions(config_path=config_path, rulepacks=case.rulepacks, **options),  # type: ignore[arg-type]
        )
        by_rule: dict[str, set[Status]] = {}
        for finding in results.findings:
            by_rule.setdefault(finding.rule_id, set()).add(finding.status)
        for passed in results.passed:
            by_rule.setdefault(passed.rule_id, set()).add(Status.PASSED)
        _RUNS[key] = by_rule
    return set(_RUNS[key].get(case.rule, set()))


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c.rule}-{c.folder}-{c.expected.value}")
def test_rule_case(case: Case, tmp_path: Path) -> None:
    found = statuses(case, tmp_path)
    if case.expected is Status.PASSED:
        assert found == {Status.PASSED}
    else:
        assert case.expected in found


def test_every_builtin_rule_has_positive_and_negative_case() -> None:
    positive = {c.rule for c in CASES if c.expected is Status.PASSED}
    negative = {c.rule for c in CASES if c.expected is not Status.PASSED}
    missing = sorted((builtin_rule_ids() - positive) | (builtin_rule_ids() - negative))
    assert not missing, f"rules without positive and negative case: {missing}"
