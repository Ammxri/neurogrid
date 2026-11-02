"""NA-02 (unit): the quality level of a recording and a session from results.json (A-102 = A-45 made precise,
F5b, F5c (i), F5e), and its JSON form."""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from neuroarena import quality
from neuroarena.keys import Condition, RecordingKey, SessionKey

THRESHOLDS = {
    "CORE-M06-01": ("max_fraction", 0.30625),
    "CORE-M07-01": ("max_ratio", 0.407669),
    "CORE-M07-02": ("min_factor", 2.0),
    "CORE-M08-01": ("max_fraction", 0.05),
    "CORE-M08-02": ("max_fraction", 0.05),
    "CORE-M09-01": ("max_fraction", 0.305083),
    "CORE-M09-02": ("max_fraction", 0.6),
}


def metrics(
    m06: float | None = 0.0,
    m07: tuple[float | None, ...] = (0.01, 0.02),
    flat: tuple[float | None, ...] = (0.0, 0.0),
    clipped: tuple[float | None, ...] = (0.0, 0.0),
    m09a: float | None = 0.0,
    m09b: float | None = 0.0,
) -> dict[str, Any]:
    """The metrics of one recording as NeuroGrid writes them (``quality.describe``); None = not measured."""

    def single(value: float | None) -> dict[str, Any]:
        if value is None:
            return {"state": "not_checkable", "reason": "quality.too_few_channels"}
        return {"state": "measured", "value": value}

    return {
        "M06": single(m06),
        "M07": {
            "line_frequency_hz": 50.0,
            "channels": {
                f"C{index}": {"ratio": value, "other_ratio": 0.01}
                if value is not None
                else {"state": "not_applicable", "reason": "quality.rate_too_low"}
                for index, value in enumerate(m07)
            },
        },
        "M08": {
            "window_s": 1.0,
            "channels": {
                f"C{index}": {"windows": 60, "flat_fraction": f, "clipped_fraction": c}
                for index, (f, c) in enumerate(zip(flat, clipped, strict=True))
            },
        },
        "M09a": single(m09a),
        "M09b": single(m09b),
    }


def results(*recordings: tuple[str, Any], scale: float = 1.0) -> dict[str, Any]:
    return {
        "config": {
            "effective_params": {
                rule: {parameter: {"origin": "rulepack", "value": value * scale}}
                for rule, (parameter, value) in THRESHOLDS.items()
            }
        },
        "recordings": [{"id": name, "metrics": entry} for name, entry in recordings],
    }


def key(run: str = "0", subject: int = 1, session: str = "0") -> RecordingKey:
    return RecordingKey("Zhou2016", subject, session, run)


def one(entry: Any, scale: float = 1.0) -> quality.RecordingQuality:
    return quality.recording_quality(results(("a.fif", entry), scale=scale), {"a.fif": key()})[key()]


def test_quality_level_boundaries() -> None:
    """F5c (i): Q1 < 0.5 <= Q2 < 0.75 <= Q3 < 1.0 <= Q4 < 1.5 <= Q5; a bound belongs to the higher level."""
    cases = {
        0.0: 1,
        0.4999999: 1,
        0.5: 2,
        0.7499999: 2,
        0.75: 3,
        0.9999999: 3,
        1.0: 4,
        1.4999999: 4,
        1.5: 5,
        1e9: 5,
    }
    assert {ratio: quality.level_for_ratio(ratio) for ratio in cases} == cases
    assert quality.level_for_ratio(1) == 4  # an int is a ratio as well
    for bad in (-1e-12, math.nan, math.inf, -math.inf, True, None, "0.5"):
        with pytest.raises(ValueError):
            quality.level_for_ratio(bad)  # type: ignore[arg-type]
    # through results.json: a value exactly at the threshold is Q4 (the threshold fails the core rule)
    assert one(metrics(m06=0.30625)).level == 4
    assert one(metrics(m06=0.30625 * 0.75)).level == 3


def test_worst_ratio_wins() -> None:
    """r = value / effective threshold; M07/M08 per recording = maximum over the channels; the largest r
    gives the level; a tie goes to the first rule of RULES."""
    item = one(metrics(m06=0.1, m07=(0.1, 0.5, 0.2), flat=(0.0, 0.01), m09a=0.2, m09b=0.3))
    assert item.ratios["CORE-M07-01"] == 0.5 / 0.407669
    assert item.ratios["CORE-M08-01"] == 0.01 / 0.05
    assert item.worst_rule == "CORE-M07-01" and item.worst_ratio == 0.5 / 0.407669 and item.level == 4
    assert set(item.ratios) == {rule.rule_id for rule in quality.RULES} and item.unmeasured == ()
    tie = one(metrics(m06=0.30625, m07=(0.0,), flat=(0.05,), clipped=(0.05,), m09a=0.0, m09b=0.0))
    assert tie.worst_rule == "CORE-M06-01" and tie.worst_ratio == 1.0
    clipped = one(metrics(m06=0.0, m07=(0.0,), flat=(0.0,), clipped=(0.1,), m09a=0.0, m09b=0.0))
    assert clipped.worst_rule == "CORE-M08-02" and clipped.level == 5
    # the thresholds come from config.effective_params: doubled thresholds halve every ratio
    assert one(metrics(m06=0.1), scale=2.0).ratios["CORE-M06-01"] == 0.1 / (2 * 0.30625)


def test_unmeasured_metrics_are_left_out_and_counted() -> None:
    entry = metrics(
        m06=None, m07=(None, None), flat=(None, 0.0), clipped=(None, math.nan), m09a=0.1, m09b=None
    )
    del entry["M09b"]
    item = one(entry)
    assert item.unmeasured == ("CORE-M06-01", "CORE-M07-01", "CORE-M08-02", "CORE-M09-02")
    assert set(item.ratios) == {"CORE-M08-01", "CORE-M09-01"}
    assert item.worst_rule == "CORE-M09-01" and item.level == 1
    # a null value, a channel without the field and a not_applicable metric are left out as well
    other = metrics()
    other["M06"] = {"state": "measured", "value": None}
    other["M07"] = {"state": "not_applicable"}
    other["M08"]["channels"] = {"C0": {"windows": 0, "flat_fraction": None}}
    assert one(other).unmeasured == ("CORE-M06-01", "CORE-M07-01", "CORE-M08-01", "CORE-M08-02")


def test_no_metric_gives_no_level() -> None:
    for entry in ({"state": "not_checkable", "reason": "read.failed"}, {}, None):
        item = one(entry)
        assert item.level is None and item.worst_rule is None and item.worst_ratio is None
        assert item.ratios == {} and item.unmeasured == tuple(rule.rule_id for rule in quality.RULES)


def test_session_is_the_worst_run() -> None:
    """F5e: the worst level of the runs that have one; runs without a level are counted, never dropped."""
    doc = results(
        ("r0.fif", metrics(m06=0.2)),  # r = 0.65: Q2
        ("r1.fif", metrics(m09a=0.4)),  # r = 1.31: Q4
        ("r2.fif", {"state": "not_checkable"}),
        ("s1.fif", {"state": "not_checkable"}),
    )
    index = {"r0.fif": key("0"), "r1.fif": key("1"), "r2.fif": key("2"), "s1.fif": key("0", session="1")}
    recordings = quality.recording_quality(doc, index)
    sessions = quality.session_quality(recordings)
    first = sessions[SessionKey("Zhou2016", 1, "0")]
    assert first.level == 4 and first.runs_without_level == 1
    assert first.runs == (key("0"), key("1"), key("2"))
    empty = sessions[SessionKey("Zhou2016", 1, "1")]
    assert empty.level is None and empty.runs_without_level == 1


def test_index_and_results_must_match() -> None:
    doc = results(("a.fif", metrics()), ("b.fif", metrics()))
    with pytest.raises(ValueError, match="differ"):
        quality.recording_quality(doc, {"a.fif": key()})
    with pytest.raises(ValueError, match="differ"):
        quality.recording_quality(doc, {"a.fif": key("0"), "b.fif": key("1"), "c.fif": key("2")})
    broken = results(("a.fif", metrics()))
    del broken["config"]["effective_params"]["CORE-M09-02"]
    with pytest.raises(ValueError, match="threshold"):
        quality.recording_quality(broken, {"a.fif": key()})


def test_quality_json_round_trip_is_sorted_and_stable(tmp_path) -> None:
    doc = results(
        ("b.fif", metrics(m06=0.1 / 3)),
        ("a.fif", {"state": "not_checkable"}),
        ("c.fif", metrics(m07=(0.3,))),
    )
    index = {"b.fif": key("1", subject=2), "a.fif": key("0", subject=2), "c.fif": key("0", subject=1)}
    recordings = quality.recording_quality(doc, index)
    condition = Condition("artifacts", 4)
    result = quality.ConditionQuality("Zhou2016", condition, recordings, quality.session_quality(recordings))
    data = result.to_dict()
    assert data["version"] == 1 and data["condition"] == "artifacts-4"
    assert [(r["subject"], r["run"]) for r in data["recordings"]] == [(1, "0"), (2, "0"), (2, "1")]
    assert data["sessions"][1]["runs"] == ["0", "1"] and data["sessions"][1]["runs_without_level"] == 1
    path = quality.write_quality(result, tmp_path / "quality.json")
    raw = path.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert json.loads(raw) == json.loads(json.dumps(data))
    assert repr(0.1 / 3 / 0.30625).encode() in raw  # floats as Python writes them
    back = quality.read_quality(path)
    assert back == result
    assert quality.read_quality(tmp_path) == result
    assert quality.write_quality(back, tmp_path / "again.json").read_bytes() == raw
    with pytest.raises(ValueError):
        quality.ConditionQuality.from_dict({**data, "version": 2})
