"""Other NeuroGrid processes for the vault tests: a process that holds the vault lock until told to let go,
and processes that append events at the same time (A-30 "Dateisperre", p6 decisions 3)."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

HOLD = """
import sys
from pathlib import Path
from neurogrid.vault.lock import exclusive
with exclusive(Path(sys.argv[1])):
    sys.stdout.write("held\\n")
    sys.stdout.flush()
    sys.stdin.readline()
"""

APPEND = """
import sys
from pathlib import Path
from neurogrid.vault import ledger, store
location = store.locate(Path(sys.argv[1]), sys.argv[2])
sys.stdout.write("ready\\n")
sys.stdout.flush()
sys.stdin.readline()
statuses = set()
for number in range(int(sys.argv[3])):
    outcome = ledger.append(location, role="writer" + sys.argv[4], action="check", objects=["**"],
                            purpose=None, approval_ref=None, timeout_s=120)
    statuses.add(outcome.status)
sys.stdout.write(",".join(sorted(statuses)) + "\\n")
"""


@contextmanager
def lock_held(lock: Path) -> Iterator[subprocess.Popen[bytes]]:
    """Another process holds the vault lock of ``lock`` for the block."""
    child = subprocess.Popen(
        [sys.executable, "-c", HOLD, str(lock)], stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )
    try:
        # strip: the child's text stdout ends lines with CRLF on Windows
        assert child.stdout is not None and child.stdout.readline().strip() == b"held", "no lock in the child"
        yield child
    finally:
        if child.stdin is not None:
            child.stdin.close()
        child.wait(timeout=60)


def appenders(project: Path, vault_path: str, processes: int, events: int) -> list[str]:
    """``processes`` processes append ``events`` events each, all started before any of them begins; the
    set of statuses each one saw."""
    children = [
        subprocess.Popen(
            [sys.executable, "-c", APPEND, str(project), vault_path, str(events), str(number)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        for number in range(processes)
    ]
    for child in children:
        assert child.stdout is not None and child.stdout.readline().strip() == b"ready"
    for child in children:
        assert child.stdin is not None
        child.stdin.write(b"go\n")
        child.stdin.flush()
    results = []
    for child in children:
        out, _err = child.communicate(timeout=600)
        assert child.returncode == 0, child.returncode
        results.append(out.decode("ascii").strip())
    return results
