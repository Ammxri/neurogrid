"""M01 Lesbarkeit und Kopfzeile (PRD §12): readability with MNE, header with own parser + edfio,
supported formats (A-12) and identifying header content (A-05, values are never output)."""

from __future__ import annotations

from neurogrid.checks.context import CheckContext
from neurogrid.kernel.rules import CheckSpec, Measurement, is_true

READABLE = "structure.readable"
HEADER = "structure.header_consistent"
SUPPORTED = "structure.supported_format"
IDENTIFYING = "structure.identifying_header"

SPECS = (
    CheckSpec(id=READABLE, evaluate=is_true),
    CheckSpec(id=HEADER, evaluate=is_true),
    CheckSpec(id=SUPPORTED, evaluate=is_true),
    CheckSpec(id=IDENTIFYING, evaluate=is_true),
)


def measure_readable(ctx: CheckContext) -> list[Measurement]:
    """Each recording file, each unreadable entry, and the dataset: at least one readable recording with
    signal channels. Annotation-only EDF+ files (hypnograms) are readable but are no recording (A-12)."""
    out: list[Measurement] = []
    readable = 0
    for rec in ctx.recordings:
        details: dict[str, str] = {}
        if rec.header_error is not None:
            details = {"issue": rec.header_error}  # own key, translated in the report
        else:
            error_type = rec.read_error()
            if error_type is not None:
                details = {"error_type": error_type}  # foreign exception: class name only (A-07)
        ok = not details
        has_signals = rec.recording is not None and any(ch.type != "ANNOT" for ch in rec.recording.channels)
        readable += ok and has_signals
        out.append(
            Measurement(
                check_id=READABLE,
                object=rec.object_id,
                file=rec.file,
                value=ok,
                reason=None if ok else "read.failed",
                details=details,
                identity=rec.identity,
            )
        )
    for entry in ctx.scan.unreadable:
        folder = entry.suffix == ""
        out.append(
            Measurement(
                check_id=READABLE,
                object=entry.display_id,
                file=entry.display_file,
                value=False,
                reason="read.unlistable" if folder else "read.failed",
                details={} if folder else {"issue": "header.io_error"},
                identity=entry.identity,
            )
        )
    out.append(
        Measurement(
            check_id=READABLE,
            object="dataset",
            subkey="readable_recordings",
            value=readable > 0,
            reason=None if readable else "dataset.no_readable_recording",
            details={"readable": readable, "recordings": len(ctx.recordings)},
        )
    )
    return out


def measure_header(ctx: CheckContext) -> list[Measurement]:
    out: list[Measurement] = []
    for rec in ctx.recordings:
        if rec.inspection is None:
            issues: tuple[str, ...] = (rec.header_error or "header.unreadable",)
        else:
            issues = rec.inspection.issues
        out.append(
            Measurement(
                check_id=HEADER,
                object=rec.object_id,
                file=rec.file,
                value=not issues,
                details={"issues": list(issues)} if issues else {},
                identity=rec.identity,
            )
        )
    return out


def measure_supported(ctx: CheckContext) -> list[Measurement]:
    out = [
        Measurement(
            check_id=SUPPORTED, object=rec.object_id, file=rec.file, value=True, identity=rec.identity
        )
        for rec in ctx.recordings
    ]
    out.extend(
        Measurement(
            check_id=SUPPORTED,
            object=found.display_id,
            file=found.display_file,
            value=False,
            reason="format.unsupported",
            details={"extension": found.suffix},
            identity=found.identity,
        )
        for found in ctx.scan.unsupported
    )
    return out


def measure_identifying(ctx: CheckContext) -> list[Measurement]:
    out: list[Measurement] = []
    for rec in ctx.recordings:
        if rec.inspection is None:
            out.append(
                Measurement(
                    check_id=IDENTIFYING,
                    object=rec.object_id,
                    file=rec.file,
                    state="not_checkable",
                    reason="header.unreadable",
                    identity=rec.identity,
                )
            )
            continue
        fields = rec.inspection.identifying_fields
        out.append(
            Measurement(
                check_id=IDENTIFYING,
                object=rec.object_id,
                file=rec.file,
                value=not fields,
                details={"fields": list(fields)} if fields else {},
                identity=rec.identity,
            )
        )
    return out


MEASURERS = {
    READABLE: measure_readable,
    HEADER: measure_header,
    SUPPORTED: measure_supported,
    IDENTIFYING: measure_identifying,
}
