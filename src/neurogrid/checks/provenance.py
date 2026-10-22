"""Provenance M13 (NG-F10, A-22, A-82): manifest present (CORE-M13-01), files match the manifest
(CORE-M13-02), processing steps and software versions documented (CORE-M13-03), and "manifest present and
every file matches it" for semi-automatic rules (gxdsl008 GX-05; A-15: document present and hash matches).

All four are dataset-wide checks with ``is_true``; the severity, also the stricter one of CORE-M13-01 under
--strict, is the engine's business (ARC-02). The manifest is read once per run (default
<dataset>/.neurogrid/manifest.json or --manifest); the dataset is walked and hashed only when a rule compares
it and a usable manifest exists. Invalid manifest content is a finding, not a tool error (A-12, C2). A single
file as target is no dataset: all four are not applicable (A-66).

CORE-M13-02 reports one finding per deviating path (subkey changed, new, missing, skipped_changed, unreadable)
plus ``manifest_hash`` when the stored hash does not match the content; without deviation one passed dataset
measurement (A-59). Details carry sizes and kinds only, never per-file hashes (A-11, A-51). Without a manifest
there is nothing to compare: not applicable (provenance.manifest_missing; CORE-M13-01 reports the missing
manifest); a manifest that cannot be used leaves the comparison not checkable (provenance.manifest_invalid).
"""

from __future__ import annotations

from typing import Any

from neurogrid.checks.context import CheckContext
from neurogrid.io.provenance import ManifestRead, show
from neurogrid.kernel.provenance import Deviation
from neurogrid.kernel.rules import CheckSpec, Measurement, is_true

MANIFEST_PRESENT = "provenance.manifest_present"
FILES_MATCH = "provenance.files_match"
DOCUMENTED = "provenance.documented"
MANIFEST_MATCHES = "provenance.manifest_matches"  # used by gxdsl008 GXDSL008-STO-002 (GX-05)

SPECS = (
    CheckSpec(id=MANIFEST_PRESENT, evaluate=is_true),
    CheckSpec(id=FILES_MATCH, evaluate=is_true),
    CheckSpec(id=DOCUMENTED, evaluate=is_true),
    CheckSpec(id=MANIFEST_MATCHES, evaluate=is_true),
)


def _single_file(check_id: str) -> list[Measurement]:
    return [
        Measurement(
            check_id=check_id, object="dataset", state="not_applicable", reason="provenance.single_file"
        )
    ]


def _no_manifest(check_id: str, read: ManifestRead, *, compares: bool = False) -> list[Measurement]:
    """A missing manifest, or one that cannot be used (the problem key, never text from the file).

    ``compares``: the check only compares the files with a manifest (CORE-M13-02). Without a manifest there is
    nothing to compare (not applicable; the missing manifest is CORE-M13-01's finding); with a manifest that
    cannot be used the comparison is not checkable (A-82). Otherwise a failed measurement."""
    if read.problem == "missing":
        if compares:
            return [
                Measurement(
                    check_id=check_id,
                    object="dataset",
                    state="not_applicable",
                    reason="provenance.manifest_missing",
                )
            ]
        return [
            Measurement(
                check_id=check_id, object="dataset", value=False, reason="provenance.manifest_missing"
            )
        ]
    return [
        Measurement(
            check_id=check_id,
            object="dataset",
            value=False,
            state="not_checkable" if compares else "measured",
            reason="provenance.manifest_invalid",
            details={"problem": read.problem},
        )
    ]


def measure_manifest_present(ctx: CheckContext) -> list[Measurement]:
    state = ctx.provenance()
    if state.single_file:
        return _single_file(MANIFEST_PRESENT)
    read = state.read()
    if read.parsed is None:
        return _no_manifest(MANIFEST_PRESENT, read)
    files = len(read.parsed.manifest.files)
    return [Measurement(check_id=MANIFEST_PRESENT, object="dataset", value=True, details={"files": files})]


def _details(deviation: Deviation) -> dict[str, Any]:
    details: dict[str, Any] = {}
    if deviation.size_manifest is not None:
        details["size_manifest"] = deviation.size_manifest
    if deviation.size_now is not None:
        details["size_now"] = deviation.size_now
    if deviation.kind in ("skipped_changed", "missing") and deviation.before is not None:
        details["before"] = deviation.before
    if deviation.kind in ("skipped_changed", "new") and deviation.now is not None:
        details["now"] = deviation.now
    return details


_REASONS = {
    "changed": "provenance.file_changed",
    "new": "provenance.file_new",
    "missing": "provenance.file_missing",
    "skipped_changed": "provenance.file_skipped_changed",
    "unreadable": "provenance.file_unreadable",
}


def measure_files_match(ctx: CheckContext) -> list[Measurement]:
    state = ctx.provenance()
    if state.single_file:
        return _single_file(FILES_MATCH)
    read = state.read()
    comparison = state.comparison()
    if read.parsed is None or comparison is None:
        return _no_manifest(FILES_MATCH, read, compares=True)
    out = []
    if not read.parsed.hash_ok:
        out.append(
            Measurement(
                check_id=FILES_MATCH,
                object="dataset",
                subkey="manifest_hash",
                value=False,
                reason="provenance.manifest_hash_mismatch",
            )
        )
    for deviation in comparison.deviations:
        shown = show(deviation.path, plain=state.plain, kind="unsafe_name" if deviation.unsafe else None)
        out.append(
            Measurement(
                check_id=FILES_MATCH,
                object=shown.object,
                file=shown.file,
                identity=shown.identity,
                subkey=deviation.kind,
                value=False,
                reason=_REASONS[deviation.kind],
                details=_details(deviation),
            )
        )
    if not out:
        details = {"files": comparison.files, "bytes": comparison.checked_bytes}
        out.append(Measurement(check_id=FILES_MATCH, object="dataset", value=True, details=details))
    return out


def measure_documented(ctx: CheckContext) -> list[Measurement]:
    """Two dataset measurements on the current sources: subkeys processing_steps and software. Whether the
    sources changed since the manifest is CORE-M13-02's concern."""
    state = ctx.provenance()
    if state.single_file:
        return _single_file(DOCUMENTED)
    sources = state.sources()
    common = {"sources": sources.source_names()}
    steps = {**common, "steps": len(sources.steps)}
    if sources.converted_problem is not None:
        step_measurement = Measurement(
            check_id=DOCUMENTED,
            object="dataset",
            subkey="processing_steps",
            value=False,
            reason="provenance.steps_invalid",
            details={**steps, "problem": sources.converted_problem},
        )
    elif sources.incomplete_steps:
        step_measurement = Measurement(
            check_id=DOCUMENTED,
            object="dataset",
            subkey="processing_steps",
            value=False,
            reason="provenance.step_incomplete",
            details={**steps, "incomplete": sources.incomplete_steps},
        )
    elif sources.steps or sources.no_processing_declared:
        step_measurement = Measurement(
            check_id=DOCUMENTED, object="dataset", subkey="processing_steps", value=True, details=steps
        )
    else:
        step_measurement = Measurement(
            check_id=DOCUMENTED,
            object="dataset",
            subkey="processing_steps",
            value=False,
            reason="provenance.steps_missing",
            details=steps,
        )
    software = sources.documented_software
    software_details = {**common, "entries": len(software)}
    if software:
        software_measurement = Measurement(
            check_id=DOCUMENTED, object="dataset", subkey="software", value=True, details=software_details
        )
    else:
        software_measurement = Measurement(
            check_id=DOCUMENTED,
            object="dataset",
            subkey="software",
            value=False,
            reason="provenance.software_missing",
            details=software_details,
        )
    return [step_measurement, software_measurement]


def measure_manifest_matches(ctx: CheckContext) -> list[Measurement]:
    """Passes only when a usable manifest exists, its hash matches its content and no path deviates (A-82)."""
    state = ctx.provenance()
    if state.single_file:
        return _single_file(MANIFEST_MATCHES)
    read = state.read()
    comparison = state.comparison()
    if read.parsed is None or comparison is None:
        return _no_manifest(MANIFEST_MATCHES, read)
    details = {
        "files": comparison.files,
        "changed": comparison.count("changed"),
        "new": comparison.count("new"),
        "missing": comparison.count("missing"),
        "skipped_changed": comparison.count("skipped_changed"),
        "unreadable": comparison.count("unreadable"),
    }
    if not read.parsed.hash_ok:
        return [
            Measurement(
                check_id=MANIFEST_MATCHES,
                object="dataset",
                value=False,
                reason="provenance.manifest_hash_mismatch",
                details=details,
            )
        ]
    if comparison.deviations:
        return [
            Measurement(
                check_id=MANIFEST_MATCHES,
                object="dataset",
                value=False,
                reason="provenance.files_differ",
                details=details,
            )
        ]
    return [Measurement(check_id=MANIFEST_MATCHES, object="dataset", value=True, details=details)]


MEASURERS = {
    MANIFEST_PRESENT: measure_manifest_present,
    FILES_MATCH: measure_files_match,
    DOCUMENTED: measure_documented,
    MANIFEST_MATCHES: measure_manifest_matches,
}
