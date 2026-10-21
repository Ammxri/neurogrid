"""Calibrate the thresholds of M06, M07 and M09 on the public corpus (MET-01, A-20).

Start value = 95th percentile over recordings (M06, M09a, M09b) or over EEG channels (M07), measured with
NeuroGrid's own metric code on the pinned OpenNeuro snapshots of the corpus (tools/corpus_lock.json). The
protocol, with data sets, versions, counts and percentiles, is written to
src/neurogrid/rulepacks/calibration/core.json; the rule pack `core` takes the values from there.

Usage:
    python tools/calibrate.py [--root .local/corpus] [--jobs 4]          # measure and write the protocol
    python tools/calibrate.py --check                                    # protocol and rule pack agree
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = ROOT / "src" / "neurogrid" / "rulepacks" / "calibration" / "core.json"
CORE = ROOT / "src" / "neurogrid" / "rulepacks" / "core.yaml"
LOCK = ROOT / "tools" / "corpus_lock.json"
PERCENTILE = 95.0
# rule ID -> (parameter, metric, unit of the percentile)
RULES = {
    "CORE-M06-01": ("max_fraction", "M06", "recordings"),
    "CORE-M07-01": ("max_ratio", "M07", "channels"),
    "CORE-M09-01": ("max_fraction", "M09a", "recordings"),
    "CORE-M09-02": ("max_fraction", "M09b", "recordings"),
}


def _datasets(corpus: Path) -> list[dict[str, Any]]:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    return [
        {**entry, "folder": corpus / entry["local_dir"]}
        for entry in lock["datasets"]
        if entry["source"] == "openneuro"
    ]


def measure(corpus: Path, jobs: int) -> dict[str, Any]:
    from neurogrid import pipeline

    values: dict[str, list[float]] = {"M06": [], "M07": [], "M09a": [], "M09b": []}
    used = []
    for dataset in _datasets(corpus):
        results = pipeline.run_check(dataset["folder"], pipeline.CheckOptions(jobs=jobs))
        counts = {"recordings": 0, "M06": 0, "M07_channels": 0, "M09a": 0, "M09b": 0}
        for recording in results.recordings:
            metrics = recording.metrics
            if not metrics or metrics.get("state") == "not_checkable":
                continue
            counts["recordings"] += 1
            for channel in metrics.get("M07", {}).get("channels", {}).values():
                if "ratio" in channel and channel["ratio"] is not None:
                    values["M07"].append(float(channel["ratio"]))
                    counts["M07_channels"] += 1
            for key in ("M06", "M09a", "M09b"):
                entry = metrics.get(key, {})
                if entry.get("state") == "measured" and entry.get("value") is not None:
                    values[key].append(float(entry["value"]))
                    counts[key] += 1
        used.append(
            {
                "dataset": dataset["dataset"],
                "version": dataset["version"],
                "snapshot_hexsha": dataset.get("snapshot_hexsha"),
                "doi": dataset["doi"],
                "format": dataset["format"],
                **counts,
            }
        )
    thresholds = {}
    for rule, (param, metric, unit) in RULES.items():
        data = values[metric]
        thresholds[rule] = {
            "param": param,
            "metric": metric,
            "over": unit,
            "n": len(data),
            "percentile": PERCENTILE,
            # 'linear' is numpy's default; rounded to 6 significant digits so the pack stays readable
            "value": float(f"{np.percentile(data, PERCENTILE):.6g}") if data else None,
        }
    from neurogrid import __version__

    return {
        "protocol_version": 1,
        "method": "95th percentile (numpy, linear) over the public corpus, A-20/MET-01",
        "neurogrid_version": __version__,
        "settings": {
            "sampling": "10 x 60 s (A-19)",
            "seed": 20261011,
            "line_frequency": "documented, else 50 Hz",
            "positions": "electrodes.tsv > data file > standard montage > none (A-60, A-79)",
            "min_channels": 16,
            "values": "measured recordings or channels only; not_checkable ones are left out",
        },
        "datasets": used,
        "thresholds": thresholds,
    }


def _core_values() -> dict[str, Any]:
    from neurogrid.kernel.rules import load_rulepack

    pack = load_rulepack(CORE.read_bytes(), origin="builtin").pack
    return {rule.id: dict(rule.params) for rule in pack.rules}


def check() -> int:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    params = _core_values()
    problems = []
    for rule, entry in protocol["thresholds"].items():
        current = params.get(rule, {}).get(entry["param"])
        if current != entry["value"]:
            problems.append(f"{rule}.{entry['param']}: pack {current} != protocol {entry['value']}")
    for line in problems:
        print(line)
    print("calibration protocol and rule pack agree" if not problems else "calibration mismatch")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT / ".local" / "corpus")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    protocol = measure(args.root, args.jobs)
    PROTOCOL.parent.mkdir(parents=True, exist_ok=True)
    PROTOCOL.write_bytes(
        (json.dumps(protocol, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    )
    for rule, entry in protocol["thresholds"].items():
        print(f"{rule} {entry['param']} = {entry['value']}  (n = {entry['n']} {entry['over']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
