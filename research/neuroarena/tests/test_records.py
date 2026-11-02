"""The CSV files of a run (records module docstring; area C writes them, area D reads them)."""

from __future__ import annotations

from pathlib import Path

import pytest

from neuroarena import records
from neuroarena.records import CurvePoint, FoldRecord, SessionRecord


def fold(subject: int, fold_index: int, accuracy: float = 0.75, condition: str = "clean") -> FoldRecord:
    return FoldRecord(
        dataset="Zhou2016",
        condition=condition,
        kind="clean",
        level=0,
        subject=subject,
        session="0",
        decoder="csp_lda",
        fold=fold_index,
        seed=123,
        n_train=16,
        n_test=4,
        n_correct=3,
        accuracy=accuracy,
        fit_seconds=0.1 + fold_index,
    )


def session(level: int | None, subject: int = 3) -> SessionRecord:
    return SessionRecord(
        dataset="Kalunga2016",
        paradigm="ssvep",
        condition="channels-2",
        kind="channels",
        level=2,
        subject=subject,
        session="0",
        decoder="eegnet",
        n_trials=48,
        accuracy=1 / 3,
        chance=0.25,
        quality_level=level,
        runs_without_level=0 if level else 1,
    )


def test_fold_csv_has_the_frozen_format(tmp_path: Path) -> None:
    """UTF-8, LF, header in column order, comma, no index, floats by repr, sorted by FOLD_KEY."""
    rows = [fold(2, 0), fold(1, 1, 0.1 + 0.2), fold(1, 0)]
    path = records.write_csv(rows, tmp_path / "folds" / "eegnet.csv")
    data = path.read_bytes()
    assert b"\r" not in data
    lines = data.decode("utf-8").split("\n")
    assert lines[0] == ",".join(records.FOLD_COLUMNS) and lines[-1] == ""
    assert lines[1].startswith("Zhou2016,clean,clean,0,1,0,csp_lda,0,123,16,4,3,0.75,")
    assert lines[2] == "Zhou2016,clean,clean,0,1,0,csp_lda,1,123,16,4,3,0.30000000000000004,1.1"
    assert records.read_folds(path) == sorted(rows, key=lambda r: (r.subject, r.fold))
    assert [p.name for p in path.parent.iterdir()] == ["eegnet.csv"]  # no temporary file left


def test_missing_level_is_an_empty_field_and_reads_back_as_none(tmp_path: Path) -> None:
    path = records.write_csv([session(4, subject=10), session(None, subject=3)], tmp_path / "sessions.csv")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[1].endswith(",3,0,eegnet,48,0.3333333333333333,0.25,,1")
    assert lines[2].endswith(",10,0,eegnet,48,0.3333333333333333,0.25,4,0")  # subject 3 before 10: by value
    assert records.read_sessions(path) == [session(None, subject=3), session(4, subject=10)]


def test_write_csv_refuses_what_it_cannot_write(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no records"):
        records.write_csv([], tmp_path / "x.csv")
    with pytest.raises(ValueError, match="one type"):
        records.write_csv([fold(1, 0), session(1)], tmp_path / "x.csv")
    with pytest.raises(ValueError, match="key"):
        records.write_csv([fold(1, 0), fold(1, 0, 0.5)], tmp_path / "x.csv")
    assert not (tmp_path / "x.csv").exists()


def test_curve_csv_round_trip_with_nan(tmp_path: Path) -> None:
    point = CurvePoint("Cho2017", "csp_lda", "quality", "all", 3, 1, 0, 0.8, float("nan"), float("nan"), 0.5)
    other = CurvePoint("Cho2017", "csp_lda", "degradation", "channels", 0, 2, 0, 0.7, 0.6, 0.8, 0.5)
    path = records.write_csv([point, other], tmp_path / "curve.csv")
    assert (
        path.read_text(encoding="utf-8").splitlines()[1].startswith("Cho2017,csp_lda,degradation,channels,0,")
    )
    back = records.read_curve(path)
    assert back[1].x == 3 and back[1].ci_low != back[1].ci_low  # nan
    assert back[0] == other


def test_reading_checks_the_header(tmp_path: Path) -> None:
    path = tmp_path / "folds.csv"
    path.write_text("dataset,condition\nZhou2016,clean\n", encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="header"):
        records.read_folds(path)
    good = records.write_csv([fold(1, 0)], tmp_path / "good.csv")
    good.write_text(good.read_text(encoding="utf-8").replace(",csp_lda,0,", ",csp_lda,x,"), encoding="utf-8")
    with pytest.raises(ValueError, match="not a int"):
        records.read_folds(good)
