"""BIDS structure via the BIDS validator (NG-F05, RP-09, A-06).

One validator run per check run. Each issue becomes a measurement for the recording it concerns (files of a
BrainVision triple or an EEGLAB .set/.fdt pair count as one recording), otherwise for the file or the
dataset. One measurement per object and validator code: subkey = validator code (A-06, A-09, KONZEPT), so an
exception written for a code covers all its occurrences (A-14). The details carry the total count and, when
the validator gives sub-codes (e.g. field names), the count per sub-code. HED schemas that are not available
offline are reported by their own check. Raw folders are not validated (A-03), and neither is a single file as
target, which is checked like a raw folder with exactly this file (A-66).

Links inside the dataset are never followed (A-52, A-66), but the validator lists what lies behind them. Its
issues at a link that discovery skipped, or below one, are dropped: the links_skipped notice covers them, and
names from outside the dataset must not reach results or the report (A-51).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from pathlib import PurePosixPath

from neurogrid.checks.context import CheckContext
from neurogrid.kernel.rules import CheckSpec, Measurement, is_true
from neurogrid.validator import ValidatorIssue

ERRORS = "bids.validator_errors"
WARNINGS = "bids.validator_warnings"
HED_SCHEMA = "bids.hed_schema_available"

# Names that are not valid Unicode: surrogate escapes in Python, U+FFFD in the validator's output (Deno).
_NOT_UNICODE = re.compile(r"[\ud800-\udfff\ufffd]+")


SPECS = (
    CheckSpec(id=ERRORS, evaluate=is_true),
    CheckSpec(id=WARNINGS, evaluate=is_true),
    CheckSpec(id=HED_SCHEMA, evaluate=is_true),
)


def _hed_schema(issue: ValidatorIssue) -> bool:
    return issue.code.startswith("HED") and bool(issue.sub_code) and "SCHEMA" in str(issue.sub_code).upper()


def _owner(ctx: CheckContext) -> dict[str, tuple[str, str, tuple[str, ...]]]:
    """Path (lower case) of every recording file and its companions -> (object, file, identity).

    Companions are the .eeg/.vmrk of a BrainVision header and the .fdt of an EEGLAB set (A-06, A-77); every
    other file, such as a sidecar, keeps its own location.
    """
    owners: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    for rec in ctx.recordings:
        relative = rec.found.relative
        owners[relative.as_posix().lower()] = (rec.object_id, rec.file, rec.identity)
    for rec in ctx.recordings:
        relative = rec.found.relative
        companions = {".vhdr": (".eeg", ".vmrk"), ".set": (".fdt",)}.get(relative.suffix.lower(), ())
        for suffix in companions:
            owners.setdefault(
                relative.with_suffix(suffix).as_posix().lower(), owners[relative.as_posix().lower()]
            )
    return owners


def _parts(path: PurePosixPath) -> tuple[str, ...]:
    """Path parts compared as the validator writes them: a run of characters that are not valid Unicode is
    one replacement character on both sides."""
    return tuple(_NOT_UNICODE.sub("\ufffd", part) for part in path.parts)


def _behind_link(ctx: CheckContext) -> Callable[[str], bool]:
    """True for a validator location that is a skipped link or lies below one (A-66)."""
    links = {_parts(link) for link in ctx.scan.skipped_links}

    def behind(location: str) -> bool:
        parts = _parts(PurePosixPath(location))
        return any(parts[:depth] in links for depth in range(1, len(parts) + 1))

    return behind


def _measurements(ctx: CheckContext, check_id: str, issues: list[ValidatorIssue]) -> list[Measurement]:
    owners = _owner(ctx)
    behind = _behind_link(ctx)
    # (object, file, identity, code) -> number of issues, and the number per sub-code
    counts: Counter[tuple[str, str | None, tuple[str, ...], str]] = Counter()
    sub_codes: dict[tuple[str, str | None, tuple[str, ...], str], Counter[str]] = {}
    for issue in issues:
        if issue.location is None:
            key: tuple[str, str | None, tuple[str, ...], str] = ("dataset", None, (), issue.code)
        elif behind(issue.location):
            continue
        else:
            lower = PurePosixPath(issue.location).as_posix().lower()
            if lower in owners:
                key = (*owners[lower], issue.code)
            else:
                key = (issue.location, issue.location, (issue.location,), issue.code)
        counts[key] += 1
        if issue.sub_code:
            sub_codes.setdefault(key, Counter())[issue.sub_code] += 1
    out = []
    for key in sorted(counts, key=lambda k: (k[0], k[3], k[1] or "", k[2])):
        object_id, file, identity, code = key
        details: dict[str, object] = {"validator_code": code, "count": counts[key]}
        if key in sub_codes:
            details["sub_codes"] = dict(sorted(sub_codes[key].items()))
        out.append(
            Measurement(
                check_id=check_id,
                object=object_id,
                subkey=code,
                file=file,
                value=False,
                details=details,
                identity=identity,
            )
        )
    if not out:
        out.append(Measurement(check_id=check_id, object="dataset", value=True))
    return out


def _validated(ctx: CheckContext) -> bool:
    """A BIDS dataset given as a folder. A single file as target is checked like a raw folder with exactly
    this file (A-66): the validator would report on the rest of its folder, and through links that were never
    listed (discovery does not walk the folder then)."""
    return ctx.scan.is_bids and not ctx.scan.single_file


def _not_bids(check_id: str) -> list[Measurement]:
    return [Measurement(check_id=check_id, object="dataset", state="not_applicable", reason="bids.not_bids")]


def measure_errors(ctx: CheckContext) -> list[Measurement]:
    if not _validated(ctx):
        return _not_bids(ERRORS)
    issues = [i for i in ctx.validator_result().issues if i.severity == "error" and not _hed_schema(i)]
    return _measurements(ctx, ERRORS, issues)


def measure_warnings(ctx: CheckContext) -> list[Measurement]:
    if not _validated(ctx):
        return _not_bids(WARNINGS)
    issues = [i for i in ctx.validator_result().issues if i.severity == "warning" and not _hed_schema(i)]
    return _measurements(ctx, WARNINGS, issues)


def measure_hed_schema(ctx: CheckContext) -> list[Measurement]:
    if not _validated(ctx):
        return _not_bids(HED_SCHEMA)
    issues = [i for i in ctx.validator_result().issues if _hed_schema(i) and i.severity != "ignore"]
    return _measurements(ctx, HED_SCHEMA, issues)


MEASURERS = {ERRORS: measure_errors, WARNINGS: measure_warnings, HED_SCHEMA: measure_hed_schema}
