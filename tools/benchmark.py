"""Runtime measurement NG-N02 (A-50, D-12, D-14): `neurogrid check` on a 1 GB EDF, 64, 128, 256 channels.

Measured is the wall time of the real process (start, imports, discovery, all core rules, writing
results.json) and the peak resident memory of the process and its children (sampled every 0.1 s). The check
runs with ``--jobs 4`` (A-50: "with 4 cores"). Limits (D-14): 150 s up to 128 channels, the PRD bound of
300 s above.

Usage:
    python tools/benchmark.py [--channels 64 128 256] [--jobs 4] [--size-gb 1.0]
                              [--out .local/perf/benchmark.json]
"""

from __future__ import annotations

import argparse
import io
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psutil

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".local" / "perf"
JOBS = 4  # A-50: the reference is a machine with 4 cores


def limit_s(channels: int) -> float:
    """D-14: 150 s here for up to 128 channels; above, the PRD bound of 5 minutes (NG-N02)."""
    return 150.0 if channels <= 128 else 300.0


def _tree_rss(process: psutil.Process) -> int:
    total = 0
    try:
        total += process.memory_info().rss
        for child in process.children(recursive=True):
            try:
                total += child.memory_info().rss
            except psutil.Error:
                continue
    except psutil.Error:
        pass
    return total


def run_one(edf: Path, jobs: int = JOBS) -> dict[str, Any]:
    out = edf.with_suffix(".results.json")
    command = [
        sys.executable,
        "-m",
        "neurogrid",
        "check",
        str(edf),
        "--out",
        str(out),
        "--as-of",
        "2026-10-21",
        "--jobs",
        str(jobs),
    ]
    start = time.perf_counter()
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    watched = psutil.Process(process.pid)
    peak = 0
    while process.poll() is None:
        peak = max(peak, _tree_rss(watched))
        time.sleep(0.1)
    wall = time.perf_counter() - start
    stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
    results = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    recording = (results.get("recordings") or [{}])[0]
    return {
        "file": edf.name,
        "jobs": jobs,
        "size_bytes": edf.stat().st_size,
        "exit_code": process.returncode,
        "wall_s": round(wall, 1),
        "peak_rss_mb": round(peak / 1e6),
        "duration_s": recording.get("duration_s"),
        "channels": recording.get("n_eeg_channels"),
        "sample_states": {
            k: v.get("state")
            for k, v in (recording.get("metrics") or {}).items()
            if isinstance(v, dict) and "state" in v
        },
        "sample_values": {
            k: v.get("value")
            for k, v in (recording.get("metrics") or {}).items()
            if isinstance(v, dict) and "state" in v
        },
        "stderr_tail": stderr[-300:],
    }


def main(argv: list[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--channels", type=int, nargs="+", default=[64, 128, 256])
    parser.add_argument("--size-gb", type=float, default=1.0)
    parser.add_argument("--jobs", type=int, default=JOBS)
    parser.add_argument("--out", type=Path, default=WORK / "benchmark.json")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT / "tools"))
    from gen_large_edf import write

    rows = []
    for channels in args.channels:
        edf = WORK / f"ng_n02_{channels}ch.edf"
        if not edf.is_file():
            write(edf, channels, args.size_gb)
        row = run_one(edf, args.jobs)
        row["limit_s"] = limit_s(channels)
        row["within_limit"] = row["exit_code"] in (0, 1) and row["wall_s"] < row["limit_s"]
        rows.append(row)
        peak = row["peak_rss_mb"]
        print(f"{channels:4d} channels: {row['wall_s']:6.1f} s, peak {peak} MB, exit {row['exit_code']}")
    report = {
        "machine": {
            "platform": platform.platform(),
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(),
            "ram_gb": round(psutil.virtual_memory().total / 1e9, 1),
        },
        "runs": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return 0 if all(row["within_limit"] for row in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
