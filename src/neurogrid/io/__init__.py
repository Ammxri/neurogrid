"""Format adapters (NG-F01). The adapter contract is described in :mod:`neurogrid.io.base` (A-24)."""

from __future__ import annotations

from neurogrid.io.base import FormatAdapter
from neurogrid.io.edf import EdfAdapter

ADAPTERS: dict[str, FormatAdapter] = {".edf": EdfAdapter()}

# EEG data formats NeuroGrid recognises but cannot read (yet). They are reported as M01 errors
# with the file name instead of being silently ignored (A-12).
KNOWN_UNSUPPORTED: frozenset[str] = frozenset(
    {".bdf", ".vhdr", ".set", ".fif", ".cnt", ".mff", ".xdf", ".gdf", ".nwb", ".cdt", ".mefd", ".nxe", ".eeg"}
)

# Formats stored as a folder (EGI MFF, MEF3). Such a folder is one unsupported recording; it is not entered.
KNOWN_UNSUPPORTED_DIRS: frozenset[str] = frozenset({".mff", ".mefd"})
