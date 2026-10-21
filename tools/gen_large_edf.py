"""Write a synthetic EDF+C file of about 1 GB for the runtime measurement NG-N02 (A-50, D-12).

The file has standard channel names (10-05 system, so the sample metrics run with positions), 512 Hz and
one-second data records. The signal is EEG-like, as in the quality fixtures of tools/gen_fixtures.py: current
dipoles under the scalp (so neighbouring channels are correlated, as pyprep, autoreject and ICA expect), each
with 1/f activity and alpha bursts, plus a little sensor noise and a small 50 Hz line component. The time
courses come from filters whose state carries over from block to block, so there are no steps at block
borders; everything follows from a fixed seed (the file is the same on every run).

Usage:
    python tools/gen_large_edf.py OUT.edf --channels 64 [--size-gb 1.0]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

RATE = 512
PHYSICAL = (-3200.0, 3200.0)  # µV
DIGITAL = (-32768, 32767)
BLOCK_RECORDS = 60
SOURCES = 16
BRAIN_UV = 15.0  # RMS of the brain signal on an average channel
NOISE_UV = 2.0
LINE_UV = 0.5
# Paul Kellet's filter for 1/f ("pink") noise from white noise
PINK_B = (0.049922035, -0.095993537, 0.050612699, -0.004408786)
PINK_A = (1.0, -2.494956002, 2.017265875, -0.522189400)


def _montage() -> dict[str, np.ndarray]:
    import mne

    positions: dict[str, np.ndarray] = mne.channels.make_standard_montage("colin27_1005").get_positions()[
        "ch_pos"
    ]
    return positions


def channel_names(count: int) -> list[str]:
    references = {"A1", "A2", "M1", "M2"}
    names = [n for n in _montage() if n not in references]
    if count > len(names):
        raise SystemExit(f"at most {len(names)} standard names")
    return names[:count]


def _topographies(names: list[str], rng: np.random.Generator) -> np.ndarray:
    """(channels, SOURCES): scalp patterns of current dipoles 4.5 cm from the head centre, mostly radial."""
    montage = _montage()
    positions = np.array([montage[name] for name in names])
    centre = np.array([montage[n] for n in montage]).mean(axis=0)
    patterns = []
    for _ in range(SOURCES):
        direction = rng.normal(size=3)
        direction[2] = abs(direction[2]) + 0.3
        direction /= np.linalg.norm(direction)
        diff = positions - (centre + 0.045 * direction)
        topography = diff @ (rng.normal(size=3) + 1.5 * direction) / np.linalg.norm(diff, axis=1) ** 3
        patterns.append(topography / np.sqrt(np.mean(topography**2)))
    return np.array(patterns).T


class _Activity:
    """Source time courses, block by block with carried-over filter state: 1/f noise plus alpha bursts
    (8–12 Hz under a slow log-normal envelope). Both parts are scaled to unit standard deviation with the
    values of the first block, so the scale is the same in every block."""

    def __init__(self, rng: np.random.Generator) -> None:
        from scipy.signal import butter

        self.rng = rng
        self.alpha = butter(4, (8.0, 12.0), btype="bandpass", fs=RATE, output="sos")
        self.slow = butter(2, 0.5, btype="lowpass", fs=RATE, output="sos")
        self.pink_state = np.zeros((SOURCES, len(PINK_A) - 1))
        self.alpha_state = np.zeros((self.alpha.shape[0], SOURCES, 2))
        self.slow_state = np.zeros((self.slow.shape[0], SOURCES, 2))
        self.scale: tuple[float, float, float, float] | None = None

    def block(self, n: int) -> np.ndarray:
        from scipy.signal import lfilter, sosfilt

        white = self.rng.normal(size=(3, SOURCES, n))
        pink, self.pink_state = lfilter(PINK_B, PINK_A, white[0], axis=1, zi=self.pink_state)
        alpha, self.alpha_state = sosfilt(self.alpha, white[1], axis=1, zi=self.alpha_state)
        slow, self.slow_state = sosfilt(self.slow, white[2], axis=1, zi=self.slow_state)
        if self.scale is None:
            first = alpha / alpha.std() * np.exp(slow / slow.std())
            self.scale = (float(pink.std()), float(alpha.std()), float(slow.std()), float(first.std()))
        pink_sd, alpha_sd, slow_sd, bursts_sd = self.scale
        bursts = alpha / alpha_sd * np.exp(slow / slow_sd) / bursts_sd
        return np.asarray((pink / pink_sd + 1.5 * bursts) / np.sqrt(1.0 + 1.5**2))


def _field(text: str, width: int) -> bytes:
    raw = text.encode("ascii")
    if len(raw) > width:
        raise ValueError(text)
    return raw.ljust(width, b" ")


def header(names: list[str], records: int) -> bytes:
    ns = len(names) + 1  # plus the EDF+ annotation signal
    out = bytearray()
    out += _field("0", 8) + _field("X X X X", 80) + _field("Startdate X X X X", 80)
    out += _field("01.01.85", 8) + _field("00.00.00", 8) + _field(str(256 * (ns + 1)), 8)
    out += _field("EDF+C", 44) + _field(str(records), 8) + _field("1", 8) + _field(str(ns), 4)
    labels = [f"EEG {n}" for n in names] + ["EDF Annotations"]
    out += b"".join(_field(label, 16) for label in labels)
    out += b"".join(_field("AgAgCl electrode" if i < len(names) else "", 80) for i in range(ns))
    out += b"".join(_field("uV" if i < len(names) else "", 8) for i in range(ns))
    out += b"".join(_field(f"{PHYSICAL[0]:g}" if i < len(names) else "-1", 8) for i in range(ns))
    out += b"".join(_field(f"{PHYSICAL[1]:g}" if i < len(names) else "1", 8) for i in range(ns))
    out += b"".join(_field(str(DIGITAL[0]), 8) for _ in range(ns))
    out += b"".join(_field(str(DIGITAL[1]), 8) for _ in range(ns))
    out += b"".join(_field("HP:0.1Hz LP:100Hz" if i < len(names) else "", 80) for i in range(ns))
    out += b"".join(_field(str(RATE) if i < len(names) else "30", 8) for i in range(ns))
    out += b"".join(_field("", 32) for _ in range(ns))
    return bytes(out)


def write(path: Path, channels: int, size_gb: float, seed: int = 20261011) -> Path:
    names = channel_names(channels)
    record_bytes = (channels * RATE + 30) * 2
    records = int(size_gb * 1e9) // record_bytes
    rng = np.random.default_rng(seed)
    mix = _topographies(names, rng) * BRAIN_UV / np.sqrt(SOURCES)
    activity = _Activity(rng)
    scale = (DIGITAL[1] - DIGITAL[0]) / (PHYSICAL[1] - PHYSICAL[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(header(names, records))
        for first in range(0, records, BLOCK_RECORDS):
            count = min(BLOCK_RECORDS, records - first)
            n = count * RATE
            t = (first * RATE + np.arange(n)) / RATE
            uv = mix @ activity.block(n) + LINE_UV * np.sin(2 * np.pi * 50 * t)
            uv += rng.normal(0.0, NOISE_UV, (channels, n))
            digital = np.clip(np.round((uv - PHYSICAL[0]) * scale + DIGITAL[0]), *DIGITAL).astype("<i2")
            block = np.zeros((count, channels * RATE + 30), dtype="<i2")
            block[:, : channels * RATE] = (
                digital.reshape(channels, count, RATE).transpose(1, 0, 2).reshape(count, -1)
            )
            tal = np.zeros((count, 60), dtype=np.uint8)
            for i in range(count):
                text = f"+{first + i}\x14\x14\x00".encode("ascii")
                tal[i, : len(text)] = np.frombuffer(text, dtype=np.uint8)
            block[:, channels * RATE :] = tal.view("<i2")
            handle.write(block.tobytes())
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--channels", type=int, default=64)
    parser.add_argument("--size-gb", type=float, default=1.0)
    args = parser.parse_args(argv)
    path = write(args.out, args.channels, args.size_gb)
    print(f"wrote {path} ({path.stat().st_size / 1e9:.3f} GB, {args.channels} channels)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
