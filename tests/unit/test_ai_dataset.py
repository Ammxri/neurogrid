"""M11/M12 building blocks (NG-F09, A-04, A-21, A-51, A-81): participants.tsv, splits.tsv, event labels, the
A-17 display rule, small-cell suppression, the [ai] configuration and the language keys of the area."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import get_args

import pytest

from conftest import dir_link  # type: ignore[import-not-found]
from neurogrid import config as config_module
from neurogrid.checks import ai_dataset
from neurogrid.checks.context import CheckContext
from neurogrid.io.discover import FoundFile, pseudonym, scan
from neurogrid.io.events import event_labels
from neurogrid.io.identifying import display_text
from neurogrid.io.participants import (
    age_group,
    parse_participants,
    read_participants,
    sex_category,
    subject_label,
)
from neurogrid.io.splits import MAX_SPLITS_ROWS, assign, locate, parse_splits, read_splits
from neurogrid.kernel.errors import ConfigError, InputError, UnsafePathError
from neurogrid.kernel.findings import Finding, Phase, Severity, SourceStatus, Status
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
        ("89+", "80+"),
        ("95+", "90+"),
        ("20-25", "20-29"),
        ("25 - 35", "20-29"),
    ],
)
def test_age_groups(text: str, group: str) -> None:
    assert age_group(text) == group


@pytest.mark.parametrize("text", ["adult", "-1", "nan", "inf", "1e400", "1_000", "150", "999+", "30-20", ""])
def test_unparseable_ages(text: str) -> None:
    assert age_group(text) is None


def test_sex_categories_and_subject_labels() -> None:
    assert [sex_category(v) for v in ("F", "female", " m ", "Male", "x", "other", "unknown")] == [
        "female",
        "female",
        "male",
        "male",
        "other",
        "other",
        "given",
    ]
    assert subject_label(" sub-07 ") == "07" and subject_label("pd3") == "pd3"


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
    assert not none.table


def test_display_rule_for_free_text() -> None:
    assert display_text("rest_open") == ("rest_open", "rest_open")
    shown, subkey = display_text("John Smith")  # matches A-17 but looks like a name (C5)
    assert shown is None and subkey.startswith("text-") and len(subkey) == 13
    assert display_text("John Smith", {"John Smith"}) == ("John Smith", "John Smith")
    assert display_text("Zhang 张三")[0] is None and display_text("a:b")[0] is None
    assert display_text("x" * 33)[0] is None and display_text("x" * 33) == display_text("x" * 33)


def test_small_cell_suppression() -> None:
    cells, total = ai_dataset.suppressed({"A": 30, "B": 3, "C": 0}, 33)
    assert cells == {"A": None, "B": None, "C": 0} and total == 33  # complementary: A hides B
    cells, total = ai_dataset.suppressed({"A": 30, "B": 3, "C": 12}, 45)
    assert cells == {"A": 30, "B": None, "C": None} and total == 45
    cells, total = ai_dataset.suppressed({"A": 3, "B": 2}, 5)
    assert cells == {"A": None, "B": None} and total == 5
    assert ai_dataset.suppressed({"A": 3}, 3) == ({"A": None}, None)
    assert ai_dataset.suppressed({"A": 7, "B": 9}, 16) == ({"A": 7, "B": 9}, 16)
    assert ai_dataset.suppressed({}, 0) == ({}, 0)


def _finding(details: dict[str, object], message_key: str = "check.ai.class_balance") -> Finding:
    return Finding(
        key="k",
        rule_id="CORE-M11-01",
        rulepack="core",
        rulepack_version="1",
        source_status=SourceStatus.FINAL,
        clause="M11",
        phase=Phase.PROCESSING,
        severity=Severity.WARNING,
        status=Status.FAILED,
        object="dataset",
        subkey="test:A",
        measured_value=0.04,
        details=details,
        message_key=message_key,
    )


def test_suppress_small_cells_after_the_engine() -> None:
    hidden, shown, other = ai_dataset.suppress_small_cells(
        [
            _finding({"small_cell": True, "unit": "subjects"}),
            _finding({"count": 1, "total": 25, "unit": "events"}),
            _finding({"small_cell": True}, message_key="check.quality.flatline"),
        ]
    )
    assert hidden.measured_value is None and hidden.reason == "ai.small_cell"
    assert shown.measured_value == 0.04 and other.measured_value == 0.04


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
    keys += ["reason.recording.annotations_only", "reason.header.unreadable", "reason.quality.not_computed"]
    for lang in ("zh", "en", "de"):
        missing = [key for key in keys if key not in loaded[lang]]
        assert not missing, (lang, missing)


def test_reason_keys_of_the_module_are_listed() -> None:
    source = Path(ai_dataset.__file__).read_text(encoding="utf-8")
    used = set(re.findall(r'"(ai\.[a-z_]+)"', source)) - set(ai_dataset.CHECKS)
    assert used <= set(ai_dataset.REASONS)
    assert Path(ai_dataset.__file__).name == "ai_dataset.py"  # TECH-01 module name
