"""NG-N02 runtime (A-50, D-12, D-14): ``neurogrid check --jobs 4`` on a 1 GB EDF with 64, 128 and 256
channels.

Excluded by default (marker ``perf``); run with ``pytest tests/perf -m perf``. The synthetic EDF+C files are
written once by tools/gen_large_edf.py and cached in .local/perf; tools/benchmark.py runs the real process
and measures its wall time and peak memory.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.perf

SAMPLE_KEYS = ("M06", "M09a", "M09b")
MEMORY_MB = 16_000  # NG-N02: a laptop with 16 GB RAM
MAX_BAD_SHARE = 0.25  # the benchmark data are EEG-like: pyprep finds few bad channels, so all methods do work


@pytest.mark.parametrize("channels", [64, 128, 256])
def test_check_of_a_1_gb_edf_within_the_limit(channels: int) -> None:
    """A-50/D-14: exit 0 or 1 (never a tool error), within the time limit (150 s up to 128 channels, 300 s
    above) and 16 GB peak memory, each sample metric computed on EEG-like data (not cut short by a
    precondition or a failing method)."""
    import benchmark  # type: ignore[import-not-found,unused-ignore]
    import gen_large_edf  # type: ignore[import-not-found,unused-ignore]

    edf = benchmark.WORK / f"ng_n02_{channels}ch.edf"  # the cache shared with tools/benchmark.py
    if not edf.is_file():
        gen_large_edf.write(edf, channels, 1.0)
    row = benchmark.run_one(edf)
    assert row["exit_code"] in (0, 1), row["stderr_tail"]
    assert row["channels"] == channels
    assert row["sample_states"] == dict.fromkeys(SAMPLE_KEYS, "measured"), row
    assert row["sample_values"]["M06"] <= MAX_BAD_SHARE, row
    assert row["peak_rss_mb"] < MEMORY_MB, row
    assert row["wall_s"] < benchmark.limit_s(channels), row
