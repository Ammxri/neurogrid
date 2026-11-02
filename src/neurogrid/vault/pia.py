"""The impact assessment of the vault: ``<vault>/pia/pia.zh.md`` and ``pia.en.md`` (NV-F05; A-30, A-94), as
CORE-NV05-02 (pia.edited) reads it. ``vault init`` writes both files from the package templates
(store.pia_template); the user fills in the fields, which hold a placeholder marker until then.

NeuroGrid judges only whether the files were edited and whether markers are left, never their content: no
legal basis, no assessment, nothing of the text reaches an output (counts only, A-51). A file is compared with
its template after a BOM and CRLF line ends are removed, so an editor that saves with either still counts as
unedited. A link at the pia folder or a PIA file ends check with exit 2 before (store.locate, p6 decisions 2).
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from neurogrid.kernel.errors import InputError
from neurogrid.kernel.safety import is_link, read_limited
from neurogrid.vault.store import PIA_FILES, VaultLocation, pia_template

MAX_PIA_BYTES = 4_000_000  # per file (A-53); a larger file is not read (not checkable)
# The placeholder markers of the templates (pia.zh.md, pia.en.md); both are counted in every file
PIA_MARKERS = ("\u3010\u5f85\u586b\u5199\u3011", "[to be completed]")
_BOM = b"\xef\xbb\xbf"
PiaState = Literal["missing", "unreadable", "template_unedited", "fields_open", "edited"]


@dataclass(frozen=True)
class PiaReading:
    """What the PIA files of a vault show: the state, the number of present files and the number of
    placeholder markers left in the edited ones (``open_fields``). ``edited``: one edited file without a
    marker suffices; ``fields_open``: every edited file still holds a marker."""

    state: PiaState
    files: int = 0
    open_fields: int = 0


def _normalized(data: bytes) -> bytes:
    return data.removeprefix(_BOM).replace(b"\r\n", b"\n")


def _regular(path: Path) -> bool:
    try:
        return not is_link(path) and stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def markers(data: bytes) -> int:
    """How many placeholder markers of either language ``data`` holds (their UTF-8 bytes; a file need not
    be valid UTF-8 to be counted)."""
    return sum(data.count(marker.encode("utf-8")) for marker in PIA_MARKERS)


def read_pia(location: VaultLocation) -> PiaReading:
    """The PIA files of the vault at ``location`` (present: a regular file at its place). ``unreadable`` when
    a present file is larger than MAX_PIA_BYTES or cannot be read."""
    present = [
        (name, path) for name, path in zip(PIA_FILES, location.pia_files, strict=True) if _regular(path)
    ]
    if not present:
        return PiaReading("missing")
    edited: list[int] = []
    for name, path in present:
        try:
            data = read_limited(path, MAX_PIA_BYTES)
        except (InputError, OSError):
            return PiaReading("unreadable", files=len(present))
        if _normalized(data) != pia_template(name):
            edited.append(markers(data))
    if not edited:
        return PiaReading("template_unedited", files=len(present))
    state: PiaState = "edited" if 0 in edited else "fields_open"
    return PiaReading(state, files=len(present), open_fields=sum(edited))
