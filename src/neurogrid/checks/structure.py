"""M01 Lesbarkeit und Kopfzeile (PRD §12): readability with MNE, header with own parsers + edfio, companion
files and references (A-46), supported formats (A-12) and identifying header content (A-05, values are never
output). Also the storage format of the recordings for gxdsl008 (GX-03, A-40, A-83)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from neurogrid.checks.context import CheckContext, RecordingState
from neurogrid.io import ORPHAN_SUFFIXES
from neurogrid.io.discover import FoundFile
from neurogrid.kernel.rules import CheckSpec, Evaluation, Measurement, ParamSpec, ParamValue, is_true

READABLE = "structure.readable"
HEADER = "structure.header_consistent"
COMPANIONS = "structure.companions_present"
SUPPORTED = "structure.supported_format"
IDENTIFYING = "structure.identifying_header"
STORAGE_FORMAT = "structure.storage_format"
HDF5 = "HDF5"


def _allowed_format(measurement: Measurement, params: Mapping[str, ParamValue]) -> Evaluation:
    """The storage format is one of the comma-separated ``formats`` (case-insensitive); the threshold is the
    list of allowed names."""
    allowed = [name.strip() for name in str(params["formats"]).split(",") if name.strip()]
    passed = str(measurement.value).casefold() in {name.casefold() for name in allowed}
    return Evaluation(passed=passed, threshold=allowed)


SPECS = (
    CheckSpec(id=READABLE, evaluate=is_true),
    CheckSpec(id=HEADER, evaluate=is_true),
    CheckSpec(id=COMPANIONS, evaluate=is_true),
    CheckSpec(id=SUPPORTED, evaluate=is_true),
    CheckSpec(id=IDENTIFYING, evaluate=is_true),
    CheckSpec(
        id=STORAGE_FORMAT, evaluate=_allowed_format, params={"formats": ParamSpec("string", "EDF,HDF5")}
    ),
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


def measure_companions(ctx: CheckContext) -> list[Measurement]:
    out: list[Measurement] = []
    for rec in ctx.recordings:
        if rec.inspection is None:
            out.append(
                Measurement(
                    check_id=COMPANIONS,
                    object=rec.object_id,
                    file=rec.file,
                    state="not_checkable",
                    reason="header.unreadable",
                    identity=rec.identity,
                )
            )
            continue
        missing = rec.inspection.missing_companions
        out.append(
            Measurement(
                check_id=COMPANIONS,
                object=rec.object_id,
                file=rec.file,
                value=not missing,
                details={"issues": list(missing)} if missing else {},
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
            reason="format.orphan_companion" if found.suffix in ORPHAN_SUFFIXES else "format.unsupported",
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


def _is_hdf5(path: Path) -> bool:
    import h5py  # heavy import, only when an EEGLAB data set or an NWB file is checked

    try:
        return bool(h5py.is_hdf5(str(path)))
    except (OSError, ValueError):  # unreadable, or a name the HDF5 library cannot encode: no HDF5 found
        return False


def storage_format(rec: RecordingState) -> str:
    """The storage format of a recording file (GX-03, A-83): EDF for EDF, EDF+C and EDF+D (BDF stays BDF, also
    in a file named .edf); an EEGLAB data set in a MAT v7.3 container is HDF5, one in MAT v5 is EEGLAB;
    BrainVision and FIF keep their names. Taken from the header where it was read, else from the extension, so
    it is known even for a damaged header (CORE-M01 reports that)."""
    if rec.adapter.format == "EEGLAB":
        return HDF5 if _is_hdf5(rec.path) else rec.adapter.format
    return rec.recording.format if rec.recording is not None else rec.adapter.format


def unsupported_format(found: FoundFile, root: Path) -> str:
    """The storage format of a data file NeuroGrid cannot read (GX-03, A-83): its extension in upper case
    ('CNT', 'MFF', 'FIF.GZ', 'FDT' for an orphan companion), never the file name (A-51). An NWB file is an
    HDF5 container when the file is HDF5."""
    if found.suffix == ".nwb" and _is_hdf5(root.joinpath(*found.relative.parts)):
        return HDF5
    return found.suffix.lstrip(".").upper()


def measure_storage_format(ctx: CheckContext) -> list[Measurement]:
    """GX-03 per recording; annotation-only files (hypnograms) are no recordings (A-74). Recording files and
    folders in formats NeuroGrid cannot read, and orphan companions, are measured too, by their extension:
    each pack is evaluated on its own (A-40), also when core (CORE-M01-04) is not loaded (A-02)."""
    out: list[Measurement] = []
    for rec in ctx.recordings:
        if rec.annotations_only:
            out.append(
                Measurement(
                    check_id=STORAGE_FORMAT,
                    object=rec.object_id,
                    file=rec.file,
                    state="not_applicable",
                    reason="recording.annotations_only",
                    identity=rec.identity,
                )
            )
            continue
        name = storage_format(rec)
        out.append(
            Measurement(
                check_id=STORAGE_FORMAT,
                object=rec.object_id,
                file=rec.file,
                value=name,
                details={} if name == rec.adapter.format else {"format": rec.adapter.format},
                identity=rec.identity,
            )
        )
    out.extend(
        Measurement(
            check_id=STORAGE_FORMAT,
            object=found.display_id,
            file=found.display_file,
            value=unsupported_format(found, ctx.root),
            details={"extension": found.suffix},
            identity=found.identity,
        )
        for found in ctx.scan.unsupported
    )
    return out


MEASURERS = {
    READABLE: measure_readable,
    HEADER: measure_header,
    COMPANIONS: measure_companions,
    SUPPORTED: measure_supported,
    IDENTIFYING: measure_identifying,
    STORAGE_FORMAT: measure_storage_format,
}
