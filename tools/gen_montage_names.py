"""Freeze the standard electrode names from MNE-Python into src/neurogrid/io/montage_names.py (M04, A-18).

Usage:
    python tools/gen_montage_names.py           # (re)write the module
    python tools/gen_montage_names.py --check   # fail if the module differs from a fresh generation
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "src" / "neurogrid" / "io" / "montage_names.py"
HEADER = '''"""Standard electrode names (M04, A-18).

``SYSTEM_1020`` holds the 10-20 and 10-10 names including the old 10-20 aliases (T3, T4, T5, T6) and the
reference sites (A1, A2, M1, M2); ``ONLY_1005`` holds the names that exist only in the 10-05 system.
Source: the montage name lists shipped with MNE-Python 1.13.2 (``colin27_1020`` and ``colin27_1005``),
frozen here so that results do not depend on later library changes. Generated with
``tools/gen_montage_names.py``.
"""

from __future__ import annotations
'''


def _block(name: str, names: list[str]) -> str:
    lines = "\n".join(f'        "{entry}",' for entry in names)
    return f"\n{name}: frozenset[str] = frozenset(\n    {{\n{lines}\n    }}\n)\n"


def render() -> str:
    import mne

    system_1020 = sorted(set(mne.channels.make_standard_montage("colin27_1020").ch_names))
    only_1005 = sorted(set(mne.channels.make_standard_montage("colin27_1005").ch_names) - set(system_1020))
    return HEADER + _block("SYSTEM_1020", system_1020) + _block("ONLY_1005", only_1005)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = render()
    if args.check:
        current = TARGET.read_text(encoding="utf-8")
        if current != text:
            print("montage_names.py is outdated - run python tools/gen_montage_names.py")
            return 1
        print("montage names up to date")
        return 0
    TARGET.write_bytes(text.encode("utf-8"))
    print(textwrap.shorten(f"wrote {TARGET.name}", 80))
    return 0


if __name__ == "__main__":
    sys.exit(main())
