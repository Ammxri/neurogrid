"""Shared kernel: rule engine, findings, provenance, canonical output, language tables, reports.

The kernel is product-neutral so that later products can reuse it. It must not import anything
from ``neurogrid`` outside ``neurogrid.kernel`` and no EEG library (enforced by a test).
"""
