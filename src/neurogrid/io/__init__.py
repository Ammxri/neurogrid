"""Format adapters (NG-F01). The adapter contract is described in :mod:`neurogrid.io.base` (A-24)."""

from __future__ import annotations

from neurogrid.io.base import FormatAdapter
from neurogrid.io.brainvision import BrainVisionAdapter
from neurogrid.io.edf import BdfAdapter, EdfAdapter
from neurogrid.io.eeglab import EeglabAdapter
from neurogrid.io.fif import FifAdapter

ADAPTERS: dict[str, FormatAdapter] = {
    ".edf": EdfAdapter(),
    ".bdf": BdfAdapter(),
    ".vhdr": BrainVisionAdapter(),
    ".set": EeglabAdapter(),
    ".fif": FifAdapter(),
}

# EEG data formats NeuroGrid recognises but cannot read (yet). They are reported as M01 errors
# with the file name instead of being silently ignored (A-12, A-74). A .eeg or .fdt that belongs to no header
# is a data file that cannot be assigned, which is reported the same way.
# Only extensions that name an EEG data or header file are listed; generic ones (.dat, .txt, .bin, .mat, .gz)
# and companions of another file (.21e, .pnt, .rs3, .cef, .amrk) are not. An entry with two parts (.fif.gz)
# is compared with the end of the file name, all others with its last extension (lower case).
KNOWN_UNSUPPORTED: frozenset[str] = frozenset(
    {
        ".cnt",  # ANT Neuro / Neuroscan
        ".mff",  # EGI (folder format, see below)
        ".xdf",  # Lab Streaming Layer
        ".xdfz",  # Lab Streaming Layer, compressed
        ".fif.gz",  # FIF, gzip-compressed (MNE reads it; NeuroGrid does not yet)
        ".gdf",  # GDF
        ".nwb",  # Neurodata Without Borders
        ".cdt",  # Curry 8
        ".dap",  # Curry 7 header (its data file is the generic .dat)
        ".mefd",  # MEF3 (folder format, see below)
        ".nxe",  # Nexstim eXimia
        ".ahdr",  # BrainVision ASCII header (MNE reads it; NeuroGrid does not yet)
        ".lay",  # Persyst header (its data file is the generic .dat)
        ".nedf",  # Neuroelectrics NEDF
        ".easy",  # Neuroelectrics EASY
        ".trc",  # Micromed
        ".e",  # Nicolet/Natus Nervus
        ".ns1",  # Blackrock NSx (.ns1-.ns6: continuous data at different rates)
        ".ns2",
        ".ns3",
        ".ns4",
        ".ns5",
        ".ns6",
        ".nev",  # Blackrock/Neuralynx event and spike data
        ".ncs",  # Neuralynx continuously sampled channel
        ".eeg",  # without a BrainVision header: orphan companion
        ".fdt",  # without an EEGLAB header: orphan companion
    }
)
ORPHAN_SUFFIXES: frozenset[str] = frozenset({".eeg", ".fdt"})

# Formats stored as a folder (EGI MFF, MEF3). Such a folder is one unsupported recording; it is not entered.
KNOWN_UNSUPPORTED_DIRS: frozenset[str] = frozenset({".mff", ".mefd"})
