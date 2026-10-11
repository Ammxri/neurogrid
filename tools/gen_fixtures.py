"""Generate the small synthetic test fixtures (CC BY 4.0) deterministically.

Usage:
    python tools/gen_fixtures.py           # (re)write tests/fixtures/synthetic
    python tools/gen_fixtures.py --check   # fail if the committed fixtures differ from a fresh generation
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "tests" / "fixtures" / "synthetic"
EEG_LABELS = ("Fp1", "Fp2", "F3", "F4", "C3", "C4", "O1", "O2")


def _field(text: str, width: int) -> bytes:
    raw = text.encode("ascii")
    if len(raw) > width:
        raise ValueError(f"field too long: {text!r}")
    return raw.ljust(width, b" ")


def _num(value: float | int, width: int) -> bytes:
    text = str(value)
    if isinstance(value, float):
        text = f"{value:.6f}".rstrip("0").rstrip(".")
    return _field(text[:width], width)


def write_edf(
    path: Path,
    *,
    sfreq: int = 512,
    seconds: int = 10,
    labels: tuple[str, ...] = EEG_LABELS,
    label_prefix: str = "EEG ",
    patient: str = "X X X X",
    recording: str = "Startdate X X X X",
    startdate: str = "01.01.85",
    seed: int = 1,
    digital: tuple[int, int] = (-32768, 32767),
    physical: tuple[float, float] = (-500.0, 500.0),
    bad_digital_channel: int | None = None,
    truncate_bytes: int = 0,
) -> None:
    rng = np.random.default_rng(seed)
    n = sfreq * seconds
    t = np.arange(n) / sfreq
    signals = []
    for index in range(len(labels)):
        microvolts = 20.0 * np.sin(2 * np.pi * (8 + index) * t) + rng.normal(0.0, 5.0, n)
        scale = (digital[1] - digital[0]) / (physical[1] - physical[0])
        values = np.clip(np.round((microvolts - physical[0]) * scale + digital[0]), digital[0], digital[1])
        signals.append(values.astype("<i2"))

    ns = len(labels)
    header = bytearray()
    header += _field("0", 8)
    header += _field(patient, 80)
    header += _field(recording, 80)
    header += _field(startdate, 8)
    header += _field("00.00.00", 8)
    header += _num(256 * (ns + 1), 8)
    header += _field("", 44)
    header += _num(seconds, 8)
    header += _num(1, 8)
    header += _num(ns, 4)
    dmins = [digital[0]] * ns
    dmaxs = [digital[1]] * ns
    if bad_digital_channel is not None:
        dmins[bad_digital_channel] = digital[1]
        dmaxs[bad_digital_channel] = digital[1]
    for label in labels:
        header += _field(f"{label_prefix}{label}", 16)
    for _ in labels:
        header += _field("AgAgCl electrode", 80)
    for _ in labels:
        header += _field("uV", 8)
    for _ in labels:
        header += _num(physical[0], 8)
    for _ in labels:
        header += _num(physical[1], 8)
    for value in dmins:
        header += _num(value, 8)
    for value in dmaxs:
        header += _num(value, 8)
    for _ in labels:
        header += _field("HP:0.1Hz LP:100Hz", 80)
    for _ in labels:
        header += _num(sfreq, 8)
    for _ in labels:
        header += _field("", 32)
    assert len(header) == 256 * (ns + 1)

    body = bytearray()
    for record in range(seconds):
        for values in signals:
            body += values[record * sfreq : (record + 1) * sfreq].tobytes()
    data = bytes(header) + bytes(body)
    if truncate_bytes:
        data = data[:-truncate_bytes]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _binary(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


FIXTURES: dict[str, Callable[[Path], None]] = {
    "edf_ok/rec_a.edf": lambda p: write_edf(p, seed=1),
    "edf_ok/rec_b.edf": lambda p: write_edf(p, seed=2),
    "edf_lowrate/rec_low.edf": lambda p: write_edf(p, sfreq=256, seed=3),
    "edf_mixed/rec_512.edf": lambda p: write_edf(p, sfreq=512, seed=4),
    "edf_mixed/rec_256.edf": lambda p: write_edf(p, sfreq=256, seed=5),
    "edf_truncated/rec_trunc.edf": lambda p: write_edf(p, seed=6, truncate_bytes=4096),
    "edf_badheader/rec_bad.edf": lambda p: write_edf(p, seed=7, bad_digital_channel=2),
    "edf_identifying/rec_named.edf": lambda p: write_edf(
        p, seed=8, patient="Zhang San 01-JAN-1980", startdate="24.08.21"
    ),
    "unsupported/rec_ok.edf": lambda p: write_edf(p, seed=9),
    "unsupported/legacy.cnt": lambda p: _binary(p, b"\x00" * 64),
    "unsupported/notes.txt": lambda p: _text(p, "Notes that are not EEG data.\n"),
    "empty/README.txt": lambda p: _text(p, "A folder without EEG recordings.\n"),
}


def generate(target: Path) -> None:
    for relative, make in FIXTURES.items():
        make(target / relative)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        generate(TARGET)
        print(f"wrote {len(FIXTURES)} fixtures to {TARGET.relative_to(ROOT)}")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp)
        generate(fresh)
        differing = [rel for rel in FIXTURES if (fresh / rel).read_bytes() != (TARGET / rel).read_bytes()]
    if differing:
        print("fixtures differ from a fresh generation:", ", ".join(differing))
        return 1
    print("fixtures up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
