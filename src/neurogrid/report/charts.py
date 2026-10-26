"""Small distribution charts of section 4 (REP-04): deterministic inline SVG, standard library only.

Each chart is a histogram of one value per recording with equal bins over a fixed domain, a dashed line per
threshold and numeric tick labels; title and caption are real HTML text next to the SVG. The SVG holds only
``rect``, ``line`` and ``text`` elements with a fixed attribute order, no ids, no time stamps and no
external references, so the same values always give the same bytes (NG-N03). It carries aggregates only,
never signal data (NG-N05). The text is set in the report font through the report's CSS.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from html import escape

CHART_BINS = 20
WIDTH, HEIGHT = 300, 150
PLOT_LEFT, PLOT_RIGHT, PLOT_TOP, PLOT_BOTTOM = 34, 6, 10, 22
_NICE_STEPS = (1.0, 2.0, 2.5, 5.0, 10.0)


def nice_ceiling(value: float) -> float:
    """The smallest m · 10^k with m in {1, 2, 2.5, 5} that is at least ``value``; 1.0 for values <= 0 and
    for a value that is not finite. Near the largest float, where that number would overflow to infinity,
    ``value`` itself (the result is always finite and at least ``value``)."""
    if not math.isfinite(value) or value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    for step in _NICE_STEPS:
        candidate = step * 10.0**exponent
        if not math.isfinite(candidate):
            return value
        if candidate >= value * (1 - 1e-12):
            return float(f"{candidate:.12g}")
    return value


def bin_index(value: float, lo: float, hi: float, bins: int = CHART_BINS) -> int:
    """Bin of ``value`` for ``bins`` equal bins over [lo, hi]; values outside fall into the first or last
    bin, the upper edge belongs to the last bin. A position too large to represent (a huge value over a
    small domain) also falls into the last bin, so floor() never sees an infinity."""
    position = (value - lo) / ((hi - lo) / bins)
    if position < 0:
        return 0
    if not position < bins:  # also an infinite (or undefined) position
        return bins - 1
    return min(bins - 1, math.floor(position))


def bin_counts(values: Sequence[float], lo: float, hi: float, bins: int = CHART_BINS) -> list[int]:
    if not hi > lo:
        raise ValueError("the chart domain needs hi > lo")
    counts = [0] * bins
    for value in values:
        counts[bin_index(value, lo, hi, bins)] += 1
    return counts


def _tick(value: float) -> str:
    text = format(value, ".3g")
    return "0" if text in ("-0", "0") else text


def threshold_x(threshold: float, lo: float, hi: float) -> float:
    plot = WIDTH - PLOT_LEFT - PLOT_RIGHT
    # the fraction first: plot * (threshold - lo) overflows near the largest float
    return PLOT_LEFT + plot * ((threshold - lo) / (hi - lo))


def histogram_svg(
    values: Sequence[float],
    *,
    lo: float,
    hi: float,
    label: str,
    thresholds: Sequence[float] = (),
    bins: int = CHART_BINS,
) -> str:
    """The SVG of one histogram. ``label`` is the accessible name (already in the report's language);
    thresholds outside [lo, hi] are not drawn."""
    counts = bin_counts(values, lo, hi, bins)
    top = max(counts) if any(counts) else 1
    plot_w = WIDTH - PLOT_LEFT - PLOT_RIGHT
    plot_h = HEIGHT - PLOT_TOP - PLOT_BOTTOM
    base = PLOT_TOP + plot_h
    parts = [
        f'<svg class="hist" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" role="img" '
        f'aria-label="{escape(label, quote=True)}">'
    ]
    for index, count in enumerate(counts):
        if not count:
            continue
        height = plot_h * count / top
        x = PLOT_LEFT + plot_w * index / bins
        parts.append(
            f'<rect class="bar" x="{x:.2f}" y="{base - height:.2f}" width="{plot_w / bins - 1:.2f}" '
            f'height="{height:.2f}"/>'
        )
    parts.append(f'<line class="ax" x1="{PLOT_LEFT}" y1="{base}" x2="{PLOT_LEFT + plot_w}" y2="{base}"/>')
    parts.append(f'<line class="ax" x1="{PLOT_LEFT}" y1="{PLOT_TOP}" x2="{PLOT_LEFT}" y2="{base}"/>')
    parts.append(f'<text class="tk" x="{PLOT_LEFT - 3}" y="{PLOT_TOP + 7}" text-anchor="end">{top}</text>')
    parts.append(f'<text class="tk" x="{PLOT_LEFT - 3}" y="{base}" text-anchor="end">0</text>')
    for fraction in (0.0, 0.5, 1.0):
        x = PLOT_LEFT + plot_w * fraction
        parts.append(
            f'<text class="tk" x="{x:.2f}" y="{base + 12}" text-anchor="middle">'
            f"{_tick(lo + (hi - lo) * fraction)}</text>"
        )
    for threshold in sorted(set(thresholds)):
        if lo <= threshold <= hi:
            x = threshold_x(threshold, lo, hi)
            parts.append(f'<line class="thr" x1="{x:.2f}" y1="{PLOT_TOP}" x2="{x:.2f}" y2="{base}"/>')
    parts.append("</svg>")
    return "".join(parts)
