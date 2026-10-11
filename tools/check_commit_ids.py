"""Traceability check (TECH-12, A-43): every commit and every phase entry names requirement IDs.

Usage:
    python tools/check_commit_ids.py                      # commits after the concept, plus FORTSCHRITT.md
    python tools/check_commit_ids.py --since <rev>        # other start revision (exclusive)
    python tools/check_commit_ids.py --message-file <f>   # also check a commit message before committing
    python tools/check_commit_ids.py --no-history         # FORTSCHRITT.md (and a message file) only

Merge commits are skipped: they carry no change of their own. Progress entries of the planning phases
(Phase 0 to 2: matrix, questions, concept) predate the requirement IDs and are exempt; every other dated
entry ("### <date> – ...") must name an ID. IDs must exist in ANFORDERUNGEN.md.
Exit code 1 lists every commit or entry without a known ID.
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
from pathlib import Path

from check_matrix_coverage import expand, matrix_ids

ROOT = Path(__file__).resolve().parent.parent
PROGRESS = ROOT / "docs" / "umsetzung" / "FORTSCHRITT.md"
# Commits up to and including the approved concept (phases 0–2) predate the implementation phases.
CONCEPT_COMMIT = "d81ad0c"
ENTRY = re.compile(r"^### \d{4}-\d{2}-\d{2}\b")
PLANNING_ENTRY = re.compile(r"\bPhase [0-2]\b")


def commits(since: str) -> list[tuple[str, int, str]]:
    """(hash, number of parents, message) for every commit in since..HEAD."""
    output = subprocess.run(
        ["git", "log", "--format=%H%x00%P%x00%B%x1e", f"{since}..HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    result = []
    for record in output.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        sha, parents, message = record.split("\x00", 2)
        result.append((sha, len(parents.split()), message))
    return result


def clean_message(text: str) -> str:
    """Like git's default cleanup: drop comment lines and everything below the scissors line."""
    kept: list[str] = []
    for line in text.splitlines():
        if line.startswith("# ------------------------ >8 ------------------------"):
            break
        if not line.startswith("#"):
            kept.append(line)
    return "\n".join(kept).strip()


def first_line(message: str) -> str:
    return message.splitlines()[0] if message.strip() else "(empty message)"


def phase_entries(text: str) -> list[tuple[str, str]]:
    """(heading, body) for every progress entry of an implementation phase."""
    entries: list[tuple[str, str]] = []
    heading: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if heading is not None:
                entries.append((heading, "\n".join(body)))
            planning = PLANNING_ENTRY.search(line) and not re.search(r"\bP\d+\b", line)
            heading = line if ENTRY.match(line) and not planning else None
            body = []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        entries.append((heading, "\n".join(body)))
    return entries


def main() -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default=CONCEPT_COMMIT)
    parser.add_argument("--message-file", type=Path)
    parser.add_argument(
        "--no-history", action="store_true", help="skip the git history (e.g. shallow clones)"
    )
    args = parser.parse_args()
    known = matrix_ids()
    problems: list[str] = []
    checked = 0
    if args.message_file is not None:
        checked += 1
        message = clean_message(args.message_file.read_text(encoding="utf-8"))
        if not expand(message) & known:
            problems.append(f"message file names no requirement ID: {first_line(message)!r}")
    for sha, parents, message in [] if args.no_history else commits(args.since):
        if parents > 1:
            continue
        checked += 1
        if not expand(message) & known:
            problems.append(f"commit {sha[:10]} names no requirement ID: {first_line(message)!r}")
    entries = phase_entries(PROGRESS.read_text(encoding="utf-8"))
    for heading, body in entries:
        if not expand(body) & known:
            problems.append(f"FORTSCHRITT entry without requirement ID: {heading!r}")
    for problem in problems:
        print(problem)
    print(f"{checked} commit(s) and {len(entries)} phase entr(y/ies) checked, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
