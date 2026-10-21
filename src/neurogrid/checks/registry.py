"""Check registry: every check ID a rule pack may use, with its parameters (A-13)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from neurogrid.checks import bids, metadata, quality, signal, structure
from neurogrid.checks.context import CheckContext
from neurogrid.kernel.rules import CheckSpec, Measurement, evidence_spec

Measurer = Callable[[CheckContext], list[Measurement]]

_MODULES = (structure, metadata, signal, quality, bids)

REGISTRY: dict[str, CheckSpec] = {spec.id: spec for module in _MODULES for spec in module.SPECS}
REGISTRY[evidence_spec().id] = evidence_spec()

MEASURERS: dict[str, Measurer] = {}
for _module in _MODULES:
    MEASURERS.update(_module.MEASURERS)


def measure(ctx: CheckContext, check_ids: Iterable[str]) -> dict[str, list[Measurement]]:
    """Run the measurers needed by the loaded rules, in a fixed order."""
    return {
        check_id: MEASURERS[check_id](ctx) for check_id in sorted(set(check_ids)) if check_id in MEASURERS
    }
