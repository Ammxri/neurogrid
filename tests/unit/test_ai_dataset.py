"""M11/M12 building blocks (NG-F09, A-04, A-21, A-51, A-81): participants.tsv, splits.tsv, event labels, the
A-17 display rule, the small-cell table rule, the [ai] configuration and the language keys of the area."""

from __future__ import annotations

import itertools
import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import get_args

import pytest

import neurogrid.io.annotations as annotations_module
from conftest import dir_link  # type: ignore[import-not-found]
from neurogrid import config as config_module
from neurogrid.checks import ai_dataset
from neurogrid.checks.context import CheckContext
from neurogrid.io.annotations import read_events
from neurogrid.io.discover import FoundFile, pseudonym, scan
from neurogrid.io.events import event_labels
from neurogrid.io.identifying import display_text
from neurogrid.io.participants import (
    AGE_GROUPS,
    age_group,
    is_age_column,
    parse_participants,
    read_participants,
    sex_category,
    subject_label,
)
from neurogrid.io.splits import MAX_SPLITS_ROWS, assign, locate, parse_splits, read_splits
from neurogrid.kernel import engine
from neurogrid.kernel.errors import ConfigError, InputError, UnsafePathError
from neurogrid.kernel.findings import Status
from neurogrid.kernel.rules import Measurement
from neurogrid.model.results import AILabels
from neurogrid.report.texts import tables

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"


# --- age groups and sex (A-21, A-81) ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "group"),
    [
        ("0", "0-9"),
        ("9.99", "0-9"),
        ("10", "10-19"),
        ("34.5", "30-39"),
        (" 89 ", "80-89"),
        ("90", "90+"),
        ("120", "90+"),
        ("89+", "80-89"),  # A-81: "N+" counts in the group of N
        ("75+", "70-79"),
        ("65 +", "60-69"),
        ("90+", "90+"),
        ("95+", "90+"),
        ("20-25", "20-29"),
        ("25 - 35", "20-29"),
    ],
)
def test_age_groups(text: str, group: str) -> None:
    assert age_group(text) == group
    assert group in AGE_GROUPS  # only the 10-year scheme, never "<decade>+"


@pytest.mark.parametrize(
    "text", ["adult", "-1", "nan", "inf", "1e400", "1_000", "150", "150+", "999+", "30-20", ""]
)
def test_unparseable_ages(text: str) -> None:
    assert age_group(text) is None


def test_sex_categories_and_subject_labels() -> None:
    assert [sex_category(v) for v in ("F", "female", " m ", "Male", "x", "other", "genderqueer")] == [
        "female",
        "female",
        "male",
        "male",
        "other",
        "other",
        "given",  # a real value outside the three categories
    ]
    assert subject_label(" sub-07 ") == "07" and subject_label("pd3") == "pd3"


@pytest.mark.parametrize(
    "text",
    [
        "unknown",
        "Unknown",
        " UNK ",
        "u",
        "U",
        "nan",
        "NaN",
        "na",
        "NA",
        "n/a",
        "None",
        "null",
        "missing",
        "Not reported",
        "not available",
        "?",
        "-",
        "",
    ],
)
def test_sex_placeholders_document_no_sex(text: str) -> None:
    """A-81: a placeholder says the sex is not known; it documents nothing (CORE-M11-02 ai.value_missing)."""
    assert sex_category(text) is None
    table = parse_participants(f"participant_id\tage\tsex\nsub-01\t30\t{text}\nsub-02\t31\tF\n")
    placeholder, documented = table.participants["01"], table.participants["02"]
    assert (placeholder.sex, placeholder.subject.sex) == ("missing", None)
    assert (documented.sex, documented.subject.sex) == ("documented", "female")
    gender = parse_participants(f"participant_id\tGender\nsub-01\t{text}\n")
    assert gender.sex_column == "gender" and gender.participants["01"].sex == "missing"


# --- participants.tsv ------------------------------------------------------------------------------------


def test_participants_header_rules_and_cells() -> None:
    # ds000248 has a byte order mark (removed by the reader), ds004148 headers with spaces, ds004504 capitals
    table = parse_participants(
        " Participant_ID \t Age\tGender\tGroup\n"
        "sub-01\t37.25\tF\tA\n"
        "sub-02\tn/a\t\tC\n"
        "03\tadult\tM\tA\n"
        "sub-01\t99\tM\tC\n"  # a second row of sub-01: the first row counts
        "\t40\tF\tA\n"  # no participant_id: ignored
    )
    assert table.usable and table.sex_column == "gender" and "group" in table.columns
    first, second, third = (table.participants[label] for label in ("01", "02", "03"))
    assert (first.age, first.sex, first.subject.age_group, first.subject.sex) == (
        "documented",
        "documented",
        "30-39",
        "female",
    )
    assert first.cells["group"] == "A" and first.subject.age == 37.25
    assert "age" not in first.subject.model_dump(mode="json")  # the raw age is never serialised (DM-02)
    assert (second.age, second.sex) == ("missing", "missing")
    assert third.age == "unparseable" and third.subject.age_group is None
    assert set(table.participants) == {"01", "02", "03"}


def test_participants_without_id_or_columns() -> None:
    assert not parse_participants("subject\tage\nsub-01\t30\n").usable
    assert not parse_participants("").usable
    table = parse_participants("participant_id\nsub-01\n")
    assert table.usable and table.participants["01"].age == "no_column"
    assert table.participants["01"].sex == "no_column" and table.sex_column is None


def test_participants_split_column() -> None:
    table = parse_participants(
        "participant_id\tsplit\nsub-01\tTrain\nsub-01\ttest\nsub-02\tvalidation\nsub-03\tn/a\n"
    )
    assert table.has_split
    assert table.participants["01"].splits == {"train", "test"}
    assert table.participants["02"].splits == frozenset() and table.participants["02"].invalid_splits == 1
    assert table.participants["03"].invalid_splits == 0


def test_read_participants_file_rules(tmp_path: Path) -> None:
    assert read_participants(tmp_path) is None
    (tmp_path / "participants.tsv").write_bytes(b"\xef\xbb\xbfparticipant_id\tage\r\nsub-01\t30\r\n")
    (tmp_path / "participants.json").write_text('{"sex": {"Levels": {"F": "female"}}}', encoding="utf-8")
    table = read_participants(tmp_path)
    assert table is not None and table.usable and table.participants["01"].subject.age_group == "30-39"
    assert table.vocabulary == {"sex": frozenset({"F"})}
    (tmp_path / "participants.tsv").write_bytes(b"participant_id\tage\nsub-01\t\xff\n")
    unusable = read_participants(tmp_path)
    assert unusable is not None and not unusable.usable  # not UTF-8: a finding, never exit 2 (C2)
    (tmp_path / "participants.tsv").unlink()
    (tmp_path / "participants.tsv").mkdir()
    folder = read_participants(tmp_path)
    assert folder is not None and not folder.usable


def test_read_participants_too_large(tmp_path: Path) -> None:
    with (tmp_path / "participants.tsv").open("wb") as handle:
        handle.write(b"participant_id\n")
        handle.truncate(10_000_001)
    table = read_participants(tmp_path)
    assert table is not None and not table.usable


def test_read_participants_does_not_follow_links(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "participants.tsv").write_text("participant_id\tage\nsub-01\t30\n", encoding="utf-8")
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    try:
        (dataset / "participants.tsv").symlink_to(target / "participants.tsv")
    except OSError:
        pytest.skip("file links not permitted on this system")
    table = read_participants(dataset)
    assert table is not None and not table.usable


# --- splits.tsv (control file, C2) -----------------------------------------------------------------------


def _rows(text: str) -> list[tuple[int, str, str]]:
    return [(row.line, row.recording, row.split) for row in parse_splits(text.encode("utf-8"))]


def test_splits_rows() -> None:
    text = (
        "\ufeff Recording \tSPLIT\textra\nsub-01/eeg/a.edf\tTrain\tx\n\n"
        "rec-0123abcd.EDF\tval\n rec-89abcdef \ttest\n"
    )
    assert _rows(text) == [
        (2, "sub-01/eeg/a.edf", "train"),
        (4, "rec-0123abcd.edf", "val"),
        (5, "rec-89abcdef", "test"),
    ]
    assert _rows("split\trecording\ntest\t.\\sub-01\\a.edf\n") == [(2, "sub-01/a.edf", "test")]


@pytest.mark.parametrize(
    ("text", "key", "line"),
    [
        ("recording\nsub-01/a.edf\n", "splits.columns", None),
        ("", "splits.columns", None),
        ("recording\tsplit\tsplit\na\ttrain\ttest\n", "splits.columns", None),
        ("recording\tsplit\nsub-01/a.edf\ttesting\n", "splits.invalid_split", 2),
        ("recording\tsplit\nsub-01/a.edf\tvalidation\n", "splits.invalid_split", 2),
        ("recording\tsplit\n\nsub-01/a.edf\n", "splits.invalid_row", 3),
        ("recording\tsplit\n\ttrain\n", "splits.invalid_row", 2),
        ("recording\tsplit\n../x.edf\ttrain\n", "splits.unsafe_path", 2),
        ("recording\tsplit\nC:/x.edf\ttrain\n", "splits.unsafe_path", 2),
        ("recording\tsplit\n\\\\srv\\x.edf\ttrain\n", "splits.unsafe_path", 2),
        ("recording\tsplit\n/abs/x.edf\ttrain\n", "splits.unsafe_path", 2),
        ("recording\tsplit\nsub-01/con.edf\ttrain\n", "splits.unsafe_path", 2),
    ],
)
def test_invalid_splits_name_the_line_only(text: str, key: str, line: int | None) -> None:
    with pytest.raises(InputError) as info:
        parse_splits(text.encode("utf-8"))
    assert info.value.message_key == key
    assert info.value.params == ({} if line is None else {"line": line})  # never the cell text (A-51)


def test_splits_encoding_and_limits(tmp_path: Path) -> None:
    with pytest.raises(InputError) as info:
        parse_splits(b"recording\tsplit\nsub-\xff.edf\ttrain\n")
    assert info.value.message_key == "splits.encoding"
    rows = "recording\tsplit\n" + "a.edf\ttrain\n" * (MAX_SPLITS_ROWS + 1)
    with pytest.raises(InputError) as info:
        parse_splits(rows.encode("utf-8"))
    assert info.value.message_key == "splits.too_many_rows"
    big = tmp_path / "splits.tsv"
    with big.open("wb") as handle:
        handle.write(b"recording\tsplit\n")
        handle.truncate(10_000_001)
    with pytest.raises(InputError) as info:
        read_splits(big)
    assert info.value.message_key == "splits.too_large"
    with pytest.raises(InputError) as info:
        read_splits(tmp_path)
    assert info.value.message_key == "splits.not_a_file"


def _found(relative: str) -> FoundFile:
    path = PurePosixPath(relative)
    return FoundFile(relative=path, display_id=pseudonym(path), suffix=path.suffix.lower(), size_bytes=1)


def test_assign_by_path_and_pseudonym() -> None:
    files = [_found("a/one.edf"), _found("two.EDF"), _found("three.vhdr")]
    pseudo = pseudonym(PurePosixPath("two.EDF"))
    text = (
        "recording\tsplit\n"
        "a/one.edf\ttrain\n"
        f"{pseudo}\ttest\n"
        f"{pseudonym(PurePosixPath('three.vhdr'))}.vhdr\tval\n"
        f"{pseudonym(PurePosixPath('three.vhdr'))}.edf\tval\n"  # wrong extension: unknown
        "A/one.edf\ttrain\n"  # case matters (A-14 matcher)
        "missing.edf\ttest\n"
        "a/one.edf\ttest\n"
    )
    assigned, unknown = assign(parse_splits(text.encode("utf-8")), files)
    assert assigned == {"a/one.edf": {"train", "test"}, "two.EDF": {"test"}, "three.vhdr": {"val"}}
    assert unknown == 3


def test_locate_default_and_configured(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    (dataset / ".neurogrid").mkdir(parents=True)
    assert locate(dataset, None, None) is None
    (dataset / ".neurogrid" / "splits.tsv").write_text("recording\tsplit\n", encoding="utf-8")
    found = locate(dataset, None, None)
    assert found is not None and found.path.name == "splits.tsv" and not found.outside_dataset
    project = tmp_path / "project"
    project.mkdir()
    (project / "my_splits.tsv").write_text("recording\tsplit\n", encoding="utf-8")
    outside = locate(dataset, project, "my_splits.tsv")
    assert outside is not None and outside.outside_dataset
    with pytest.raises(ConfigError) as info:
        locate(dataset, project, "nope.tsv")
    assert info.value.message_key == "config.splits_not_found" and info.value.params == {"field": "ai.splits"}


def test_locate_refuses_links(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "splits.tsv").write_text("recording\tsplit\n", encoding="utf-8")
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    dir_link(dataset / ".neurogrid", target)  # a junction where symlinks are not permitted
    with pytest.raises(UnsafePathError) as info:
        locate(dataset, None, None)
    assert info.value.message_key == "splits.link"
    project = tmp_path / "project"
    project.mkdir()
    dir_link(project / "linked", target)
    with pytest.raises(UnsafePathError):
        locate(dataset, project, "linked/splits.tsv")


def test_read_splits_refuses_a_file_link(tmp_path: Path) -> None:
    real = tmp_path / "real.tsv"
    real.write_text("recording\tsplit\n", encoding="utf-8")
    link = tmp_path / "splits.tsv"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("file links not permitted on this system")
    with pytest.raises(UnsafePathError):
        read_splits(link)


# --- event labels, display rule, small cells -------------------------------------------------------------


def test_event_labels_from_the_nearest_events_tsv() -> None:
    root = FIX / "bids_ai_issues"
    labels = event_labels(root, PurePosixPath("sub-02/eeg/sub-02_task-rest_run-1_eeg.edf"), " Trial_Type ")
    assert labels.table and labels.column and labels.values.count("rare") == 1 and len(labels.values) == 8
    assert labels.vocabulary == {"A", "B", "C"}  # Levels from task-rest_events.json
    missing = event_labels(root, PurePosixPath("sub-02/eeg/sub-02_task-rest_run-1_eeg.edf"), "value")
    assert missing.table and not missing.column
    none = event_labels(FIX / "bids_issues", PurePosixPath("sub-02/eeg/sub-02_task-rest_eeg.edf"), "x")
    assert not none.table and not none.unreadable


def test_event_labels_use_the_reader_and_header_rule_of_m10(tmp_path: Path) -> None:
    """Critic G10: events:<column> reads events.tsv with io.annotations.read_events. A table that is not
    UTF-8 is unreadable (not "no column"); duplicate columns: the first one counts, as in M10."""
    data_file = PurePosixPath("sub-01/eeg/sub-01_task-rest_eeg.edf")
    folder = tmp_path / "sub-01" / "eeg"
    folder.mkdir(parents=True)
    events = folder / "sub-01_task-rest_events.tsv"
    events.write_bytes("onset\tduration\ttrial_type\n0\t1\t睁眼\n".encode("gbk"))
    unreadable = event_labels(tmp_path, data_file, "trial_type")
    assert unreadable.unreadable and unreadable.table and not unreadable.column and not unreadable.values
    events.write_text(
        "onset\tduration\ttrial_type\tTrial_Type \n0\t1\tA\tB\n1\t1\tn/a\tB\n2\t1\t\tB\n", encoding="utf-8"
    )
    (tmp_path / "task-rest_events.json").write_text(
        '{"trial_type": {"Levels": {"A": "a"}}}', encoding="utf-8"
    )
    first = event_labels(tmp_path, data_file, " TRIAL_TYPE")
    assert (first.unreadable, first.column, first.values, first.vocabulary) == (False, True, ("A",), {"A"})
    table = read_events(tmp_path, data_file)
    assert table is not None and tuple(table.values("trial_type") or ()) == first.values  # M10's cells


def test_event_labels_of_an_oversized_events_tsv_are_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AI13 (A-53, C2): a table above the size or row limit of M10's reader is unreadable, not "no table" and
    no exit 2; an empty table is readable and simply has no label column."""
    data_file = PurePosixPath("sub-01/eeg/sub-01_task-rest_eeg.edf")
    folder = tmp_path / "sub-01" / "eeg"
    folder.mkdir(parents=True)
    events = folder / "sub-01_task-rest_events.tsv"
    events.write_text("onset\tduration\ttrial_type\n0\t1\tA\n1\t1\tB\n2\t1\tA\n", encoding="utf-8")
    assert event_labels(tmp_path, data_file, "trial_type").values == ("A", "B", "A")
    monkeypatch.setattr(annotations_module, "MAX_ANNOTATIONS", 2)
    rows = event_labels(tmp_path, data_file, "trial_type")
    assert (rows.table, rows.column, rows.unreadable, rows.values) == (True, False, True, ())
    monkeypatch.setattr(annotations_module, "MAX_ANNOTATIONS", 3)
    monkeypatch.setattr(annotations_module, "MAX_TSV_BYTES", 16)
    assert event_labels(tmp_path, data_file, "trial_type").unreadable
    monkeypatch.undo()
    events.write_text("", encoding="utf-8")
    empty = event_labels(tmp_path, data_file, "trial_type")
    assert (empty.table, empty.column, empty.unreadable) == (True, False, False)


def test_display_rule_for_free_text() -> None:
    assert display_text("rest_open") == ("rest_open", "rest_open")
    shown, subkey = display_text("John Smith")  # matches A-17 but looks like a name (C5)
    assert shown is None and subkey.startswith("text-") and len(subkey) == 13
    assert display_text("John Smith", {"John Smith"}) == ("John Smith", "John Smith")
    assert display_text("Zhang 张三")[0] is None and display_text("a:b")[0] is None
    assert display_text("x" * 33)[0] is None and display_text("x" * 33) == display_text("x" * 33)


@pytest.mark.parametrize(
    "cells",
    [
        {"A": 30, "B": 3, "C": 0},
        {"A": 30, "B": 3, "C": 12},
        {"A": 3, "B": 2},
        {"A": 3},  # a single category (CON49)
        {"A": 1, "B": 1, "C": 30},  # hidden cells at their minimum (AI10)
        {"A": 4, "B": 4, "C": 4, "D": 30},
        {key: 1 for key in "ABCDEF"},
        {"F": 1, "M": 0},  # a zero next to a single small cell (INT38)
    ],
)
def test_a_table_with_a_small_cell_is_withheld_as_a_whole(cells: dict[str, int]) -> None:
    """A-51 table rule: no category key and no count of a table with a non-zero cell of 1-4 subjects, so no
    cell is derivable from the public total, zero cells or the keys."""
    assert ai_dataset.small_cell(cells) and ai_dataset.published(cells) is None


def test_a_table_without_small_cells_is_published() -> None:
    assert ai_dataset.published({"M": 9, "F": 7}) == {"F": 7, "M": 9}
    assert ai_dataset.published({"A": 5, "B": 0}) == {"A": 5, "B": 0}  # zero cells may then show
    assert ai_dataset.published({"female": 5}) == {"female": 5}
    assert ai_dataset.published({}) == {} and not ai_dataset.small_cell({"A": 0, "B": 5})


def _scope(total: int, small: bool) -> Measurement:
    details: dict[str, object] = {"scope": "all", "unit": "subjects", "total": total, "withheld": True}
    if small:
        details["small_cell"] = True
    return Measurement(check_id=ai_dataset.CLASS_BALANCE, object="dataset", value=None, details=details)


@pytest.mark.parametrize(
    ("total", "min_share", "passed", "not_checkable"),
    [
        (100, 0.05, False, None),  # 4/100 < 0.05: every possible small count fails
        (81, 0.05, False, None),
        (80, 0.05, False, "ai.small_cell"),  # 3 of 80 fails, 4 of 80 passes: the outcome would tell
        (30, 0.05, False, "ai.small_cell"),  # AI09: 1 of 30 fails, 2 of 30 passes
        (21, 0.05, False, "ai.small_cell"),
        (20, 0.05, True, None),  # 1/20 reaches 0.05: every non-zero cell passes
        (6, 0.05, True, None),
        (6, 0.9, False, None),
        (6, 0.5, False, "ai.small_cell"),
        (1, 0.9, True, None),
    ],
)
def test_withheld_scope_with_a_surely_small_cell_is_judged_from_public_facts(
    total: int, min_share: float, passed: bool, not_checkable: str | None
) -> None:
    """A-51: a scope that the numbers of subjects alone show to hold a cell of 1-4 subjects (details
    small_cell) is judged from its number of subjects N and min_share; there is no share to use."""
    verdict = ai_dataset._class_share(_scope(total, True), {"min_share": min_share})
    assert (verdict.passed, verdict.not_checkable, verdict.threshold) == (passed, not_checkable, min_share)


@pytest.mark.parametrize(
    ("total", "min_share", "passed", "not_checkable"),
    [
        (100, 0.05, False, "ai.small_cell"),  # failed only if the scope surely held the small cell
        (30, 0.05, False, "ai.small_cell"),
        (24, 0.05, False, "ai.small_cell"),  # INT38/AI10 (L1): a train split with a class missing or not
        (20, 0.05, True, None),  # every category present passes, whatever the counts
        (6, 0.9, False, "ai.small_cell"),
        (1, 0.9, True, None),
    ],
)
def test_other_withheld_scopes_never_tell_where_the_small_cell_is(
    total: int, min_share: float, passed: bool, not_checkable: str | None
) -> None:
    """P4 review repair (AI10, INT38, CON48): a withheld scope that may or may not hold the small cell gets
    no exact outcome, as it would tell, with the sums, the split counts and a demographic table, which
    scope holds a cell of 1-4 or that a category is missing from a split. Before, such a scope kept the
    exact outcome of its lowest share and its own small_cell flag."""
    verdict = ai_dataset._class_share(_scope(total, False), {"min_share": min_share})
    assert (verdict.passed, verdict.not_checkable, verdict.threshold) == (passed, not_checkable, min_share)


def test_published_classes_keep_the_exact_outcome() -> None:
    published = Measurement(check_id=ai_dataset.CLASS_BALANCE, object="dataset", value=0.05, details={})
    assert ai_dataset._class_share(published, {"min_share": 0.05}).passed
    assert not ai_dataset._class_share(published, {"min_share": 0.06}).passed
    assert ai_dataset._class_share(published, {"min_share": 0.06}).not_checkable is None


@pytest.mark.parametrize(
    ("total", "totals", "small"),
    [
        (4, (30, 26, 4), True),  # 1-4 subjects: every non-zero cell is small
        (26, (30, 26, 4), False),
        (30, (30, 26, 4), False),
        (6, (6,), True),  # no split: the scope all holds the small cell of the withheld source
        (6, (6, 6), True),  # every subject in train: the two scopes are one table
        (6, (6, 6, 0), True),  # a split without labelled subjects does not count
        (6, (6, 5, 1), False),
    ],
)
def test_surely_small_uses_the_numbers_of_subjects_only(
    total: int, totals: tuple[int, ...], small: bool
) -> None:
    assert ai_dataset.surely_small(total, totals) is small


def _withheld_outputs(
    monkeypatch: pytest.MonkeyPatch, scopes: dict[str, dict[str, int]], min_share: float
) -> str:
    """Everything CORE-M11-01 and the labels block publish for a participants label source with these cells:
    status, reason, threshold, value and details of every scope, the passed scopes and the labels block."""
    counts = {scope: Counter({k: v for k, v in cells.items() if v}) for scope, cells in scopes.items()}
    counted = ai_dataset.Labels(
        "participants", "group", "subjects", counts=counts, shown={key: key for key in scopes["all"]}
    )
    monkeypatch.setattr(ai_dataset, "labels", lambda ctx: counted)
    spec = ai_dataset.SPECS[0]
    published: list[object] = []
    for measurement in ai_dataset.measure_class_balance(None):  # type: ignore[arg-type]
        outcome = engine._measurement_outcome(spec, measurement, {"min_share": min_share})
        passed = outcome.status is Status.PASSED
        published.append(
            (
                measurement.subkey,
                outcome.status.value,
                None if passed else outcome.reason,
                outcome.threshold,
                outcome.measurement.value,
                sorted(measurement.details.items()),
            )
        )
    block = ai_dataset._labels_block(counted)
    published.append(block.model_dump(mode="json") if block else None)
    return repr(published)


def _layouts(sizes: dict[str, int]) -> Iterator[dict[str, dict[str, int]]]:
    """Every distribution of two classes A, B over splits of these sizes (each subject in one split)."""
    names = list(sizes)
    for minority in itertools.product(*(range(sizes[name] + 1) for name in names)):
        splits = {name: {"A": a, "B": sizes[name] - a} for name, a in zip(names, minority, strict=True)}
        total_a = sum(minority)
        yield {"all": {"A": total_a, "B": sum(sizes.values()) - total_a}, **splits}


@pytest.mark.parametrize(
    "sizes",
    [
        {"train": 24, "test": 6},  # INT38 / AI10 L1: the class shared by all of train, 1 subject in test
        {"train": 20, "val": 5, "test": 5},  # CON48 L2: val 1 F / 4 M from the outcomes of train and test
        {"train": 26, "test": 4},  # CON48 L3: passed vs. not checkable told test 4 F / 0 M
        {"train": 5, "test": 6},
    ],
)
@pytest.mark.parametrize("min_share", [0.05, 0.2, 0.9])
def test_withheld_outputs_depend_on_the_public_numbers_only(
    monkeypatch: pytest.MonkeyPatch, sizes: dict[str, int], min_share: float
) -> None:
    """P4 review repair (AI10, INT38, CON48): every distribution of the subjects over the classes that is
    withheld gives the same output, so neither the sums of the scopes, the split counts, the demographic
    table of the same column nor the statuses tell a cell of 1-4. With the earlier rule, a scope without a
    small cell kept its exact outcome and its small_cell flag, and these outputs differed."""
    seen = {
        _withheld_outputs(monkeypatch, scopes, min_share)
        for scopes in _layouts(sizes)
        if any(ai_dataset.small_cell(cells) for cells in scopes.values())
    }
    assert len(seen) == 1, seen
    assert "('withheld', True)" in next(iter(seen))


def test_withheld_scopes_carry_no_share_count_or_class(monkeypatch: pytest.MonkeyPatch) -> None:
    """A withheld scope is output with its public facts only (A-51), also a scope without a small cell of
    its own; the output filter that removed a share after the engine is no longer needed."""
    scopes = {"all": {"A": 25, "B": 5}, "train": {"A": 21, "B": 5}, "test": {"A": 4, "B": 0}}
    counts = {scope: Counter({k: v for k, v in cells.items() if v}) for scope, cells in scopes.items()}
    counted = ai_dataset.Labels("participants", "sex", "subjects", counts=counts, shown={"A": "A", "B": "B"})
    monkeypatch.setattr(ai_dataset, "labels", lambda ctx: counted)
    measured = ai_dataset.measure_class_balance(None)  # type: ignore[arg-type]
    assert [(m.subkey, m.value, m.reason, m.details) for m in measured] == [
        ("all", None, "ai.small_cell", {"scope": "all", "unit": "subjects", "total": 30, "withheld": True}),
        (
            "train",
            None,
            "ai.small_cell",
            {"scope": "train", "unit": "subjects", "total": 26, "withheld": True},
        ),
        (
            "test",
            None,
            "ai.small_cell",
            {"scope": "test", "unit": "subjects", "total": 4, "withheld": True, "small_cell": True},
        ),
    ]
    assert not hasattr(ai_dataset, "suppress_small_cells")


@pytest.mark.parametrize(
    ("name", "ages"),
    [
        ("age", True),
        ("Age", True),
        ("age_years", True),
        ("Age at scan", True),
        ("subject_age", True),
        ("AgeYears", True),
        ("AgeAtScan", True),
        ("age-group", True),
        ("ages", True),
        ("language", False),
        ("stage", False),
        ("agency", False),
        ("page_count", False),
        ("group", False),
    ],
)
def test_columns_that_hold_ages_by_their_name(name: str, ages: bool) -> None:
    """A-21 (P4 review repair): every column whose name says age counts in the 10-year groups as a label
    source, not only the column age."""
    assert is_age_column(name) is ages


# --- configuration and language keys ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "value", ["events:trial_type", "participants:Group", "events:value.code-1", "annotations"]
)
def test_label_source_grammar_accepts(value: str) -> None:
    assert config_module.parse(f'[ai]\nlabels = "{value}"\n').ai.labels == value


@pytest.mark.parametrize(
    "value",
    [
        "foo",
        "events:",
        "events:a b",
        "participants:" + "x" * 65,
        "annotations:code",  # the M10 code is the class, there is no column to choose
        "annotation",
        "Annotations",
        " annotations",
        "annotations\\n",
    ],
)
def test_label_source_grammar_refuses(value: str) -> None:
    with pytest.raises(ConfigError) as info:
        config_module.parse(f'[ai]\nlabels = "{value}"\n')
    assert info.value.message_key == "config.invalid" and info.value.params["field"] == "ai.labels"


def test_label_sources_agree_with_the_grammar_and_results_model() -> None:
    """A-81: the three label sources of the configuration, the check module and results.ai.labels."""
    assert config_module.AI_LABEL_SOURCES == ("events", "participants", "annotations")
    assert get_args(ai_dataset.LabelSource) == config_module.AI_LABEL_SOURCES
    source = AILabels.model_fields["source"].annotation
    assert get_args(source) == config_module.AI_LABEL_SOURCES
    for value in ("events:x", "participants:x", "annotations"):
        match = config_module.AI_LABELS.fullmatch(value)
        assert match is not None and (match.group("source") or match.group("annotations")) in get_args(source)


def test_annotation_labels_are_counted_once_and_only_when_needed() -> None:
    """The source "annotations" reads the M10 annotations (A-80) lazily: building the structure (before the
    signal pass, C2) does not, the first labels() call does, and later calls reuse the count."""
    folder = FIX / "annotation_continuous_ok"
    ctx = CheckContext.build(scan(folder), config_module.parse('[ai]\nlabels = "annotations"\n'))
    ai_dataset.structure(ctx)
    assert not ctx.annotations_read
    counted = ai_dataset.labels(ctx)
    assert ctx.annotations_read and counted is not None and ai_dataset.labels(ctx) is counted
    assert (counted.source, counted.column, counted.unit, counted.reason) == (
        "annotations",
        None,
        "events",
        None,
    )
    # three scorers attached by their stem (C10): 31 annotations, "Lights off" (zero duration) included
    assert dict(counted.counts[ai_dataset.SCOPE_ALL]) == {
        "Lights off": 1,
        "N1": 4,
        "N2": 9,
        "N3": 6,
        "R": 4,
        "W": 7,
    }
    unset = CheckContext.build(scan(folder), config_module.Config())
    assert ai_dataset.labels(unset) is None and not unset.annotations_read


def test_splits_path_must_be_relative() -> None:
    with pytest.raises(ConfigError) as info:
        config_module.parse('[ai]\nsplits = "../splits.tsv"\n')
    assert info.value.params == {"field": "ai.splits"}


def test_language_keys_of_the_area() -> None:
    """Keys built at run time (reasons passed through variables, notices, error keys): zh, en, de (C7)."""
    loaded = tables()
    keys = [f"reason.{key}" for key in ai_dataset.REASONS] + list(ai_dataset.NOTICES)
    keys += [f"check.{spec.id}" for spec in ai_dataset.SPECS]
    keys += [
        f"errors.splits.{name}"
        for name in (
            "columns",
            "invalid_row",
            "invalid_split",
            "unsafe_path",
            "too_large",
            "too_many_rows",
            "encoding",
            "not_a_file",
            "unreadable",
            "link",
        )
    ]
    keys += ["errors.config.splits_not_found", "report.ai.unit_events", "report.ai.unit_subjects"]
    keys += ["report.ai.withheld"]
    keys += ["reason.recording.annotations_only", "reason.header.unreadable", "reason.quality.not_computed"]
    for lang in ("zh", "en", "de"):
        missing = [key for key in keys if key not in loaded[lang]]
        assert not missing, (lang, missing)


def test_reason_keys_of_the_module_are_listed() -> None:
    source = Path(ai_dataset.__file__).read_text(encoding="utf-8")
    used = set(re.findall(r'"(ai\.[a-z_]+)"', source)) - set(ai_dataset.CHECKS)
    assert used <= set(ai_dataset.REASONS)
    assert Path(ai_dataset.__file__).name == "ai_dataset.py"  # TECH-01 module name
