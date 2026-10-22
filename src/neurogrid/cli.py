"""Command line (PRD §13): scan, convert, check, report, manifest, verify. Further commands follow in later
phases.

Exit codes (NG-F14, A-12): 0 no failed error rule, 1 at least one, 2 tool error. manifest: 0 written, 1 files
could not be read (nothing written); verify: 0 the dataset matches the manifest, 1 any deviation (A-82).
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import traceback
import warnings
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from typer.exceptions import TyperException

from neurogrid import pipeline
from neurogrid.kernel import canonical, netguard
from neurogrid.kernel.errors import ConfigError, InputError, NeuroGridError
from neurogrid.kernel.findings import Severity
from neurogrid.kernel.i18n import detect_language, normalize_language
from neurogrid.kernel.safety import check_operator_path, read_limited, redact_paths
from neurogrid.metadata import NA_IS_MISSING
from neurogrid.model.results import Results
from neurogrid.report.texts import REPORT_LANGUAGES, translator

MAX_RESULTS_BYTES = 256_000_000
MAX_PARAM_CHARS = 200
MAX_LISTED = 200  # names listed per kind by manifest and verify; the rest as a count

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
    rich_markup_mode=None,
    help="NeuroGrid – local, offline pre-check of EEG datasets. Not a conformity assessment.",
)

_state: dict[str, object] = {"lang": "en", "debug": False, "dataset_root": None}


def _lang() -> str:
    return str(_state["lang"])


def _say(key: str, **params: object) -> None:
    typer.echo(translator(_lang()).t(key, **params))


def _clean(text: str) -> str:
    """Drop control characters from untrusted text before printing it (A-53)."""
    return "".join(ch for ch in text if ch.isprintable())


def _clean_lines(text: str) -> str:
    """Like _clean, but keeps the line structure of multi-line texts (help, tracebacks)."""
    return "\n".join(_clean(line) for line in text.splitlines())


def _redact(text: str) -> str:
    """Output filter for console text (A-51): dataset root → <dataset>, home directory → ~."""
    root = _state["dataset_root"]
    return redact_paths(text, {"<dataset>": root if isinstance(root, Path) else None, "~": Path.home()})


def _display_path(path: Path) -> str:
    return _redact(str(path.absolute()))


def _output_file(raw: str) -> Path:
    """An output file from the command line. A trailing separator means a folder, which is refused."""
    if raw.endswith(("/", "\\")):
        raise InputError("output.is_directory")
    return check_operator_path(raw)


def _write_atomic(path: Path, data: bytes) -> None:
    """Write via a private temporary file in the target folder; nothing is left behind on failure (A-54)."""
    if path.is_dir():
        raise InputError("output.is_directory")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    except OSError:
        raise InputError("output.not_writable") from None
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise InputError("output.not_writable") from None
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _split_list(values: list[str]) -> list[str]:
    """Accept '--lang zh,en' as well as '--lang zh --lang en' (PowerShell splits unquoted commas)."""
    items: list[str] = []
    for value in values:
        for part in value.split(","):
            part = part.strip().lower()
            if part and part not in items:
                items.append(part)
    return items


def _rulepack_refs(values: list[str]) -> list[str]:
    """Rule pack names or paths: kept as given (case matters on Linux, commas are legal in paths)."""
    refs: list[str] = []
    for value in values:
        ref = value.strip()
        if ref and ref not in refs:
            refs.append(ref)
    return refs


@app.callback()
def _options(
    lang: Annotated[str | None, typer.Option("--lang", help="Language of messages: zh or en.")] = None,
    debug: Annotated[
        bool, typer.Option("--debug", help="Show a sanitized traceback on internal errors.")
    ] = False,
) -> None:
    _state["debug"] = debug
    if lang is not None and not lang.strip():
        raise ConfigError("i18n.empty")  # an explicit but empty choice is no silent fallback (A-73)
    _state["lang"] = detect_language(lang, supported=REPORT_LANGUAGES)


@app.command()
def scan(
    path: Annotated[str, typer.Argument(help="Dataset folder or single data file.")],
    out: Annotated[str | None, typer.Option("--out", help="Also write the inventory as JSON.")] = None,
    show_paths: Annotated[
        bool, typer.Option("--show-paths", help="Show real paths instead of pseudonymous IDs.")
    ] = False,
) -> None:
    """Inventory: formats, subjects, recordings, sizes, unsupported files."""
    _state["dataset_root"] = pipeline.resolve_target(path).root
    result = pipeline.run_scan(path, show_paths=show_paths)
    tr = translator(_lang()).t
    typer.echo(f"{tr('cli.scan.title')}")
    typer.echo(f"  {tr('cli.scan.bids')}: {tr('cli.scan.yes') if result.is_bids else tr('cli.scan.no')}")
    formats = ", ".join(f"{name} {count}" for name, count in result.formats.items()) or "–"
    typer.echo(f"  {tr('cli.scan.formats')}: {formats}")
    subjects = tr("cli.scan.subjects_unknown") if result.subjects is None else str(result.subjects)
    typer.echo(f"  {tr('cli.scan.subjects')}: {subjects}")
    typer.echo(f"  {tr('cli.scan.recordings')}: {len(result.recordings)}")
    typer.echo(f"  {tr('cli.scan.unsupported')}: {len(result.unsupported)}")
    for item in result.unsupported:
        typer.echo(f"    - {_clean(item.id)} ({item.format})")
    if result.orphans:
        # a .eeg/.fdt that no header refers to cannot be assigned to a recording; it is no format
        # NeuroGrid cannot read (A-77, CORE-M01-04)
        typer.echo(f"  {tr('cli.scan.orphans')}: {len(result.orphans)}")
        for item in result.orphans:
            typer.echo(f"    - {_clean(item.id)} ({item.format}) – {tr('reason.format.orphan_companion')}")
    typer.echo(f"  {tr('cli.scan.other')}: {result.other_files}")
    typer.echo(f"  {tr('cli.scan.links')}: {result.links_skipped}")
    typer.echo(f"  {tr('cli.scan.size')}: {result.total_bytes / 1_000_000:.1f} MB")
    if result.unreadable:
        typer.echo(f"  {tr('cli.scan.unreadable')}: {len(result.unreadable)}")
        for item in result.unreadable:
            typer.echo(f"    - {_clean(item.id)}")
    if result.suspicious_names:
        typer.echo(tr("cli.scan.names_hint", count=result.suspicious_names))
    typer.echo(tr("disclaimer"))
    if out:
        target = _output_file(out)
        _write_atomic(target, canonical.dumps(result))
        _say("cli.scan.written", path=_display_path(target))


@app.command()
def check(
    path: Annotated[str, typer.Argument(help="Dataset folder or single data file.")],
    rulepack: Annotated[
        list[str] | None, typer.Option("--rulepack", help="Rule pack name or path (repeatable).")
    ] = None,
    config: Annotated[str | None, typer.Option("--config", help="Path to neurogrid.toml.")] = None,
    out: Annotated[str, typer.Option("--out", help="Results file.")] = "results.json",
    strict: Annotated[
        bool, typer.Option("--strict", help="Strict mode (missing manifest is an error).")
    ] = False,
    as_of: Annotated[
        str | None, typer.Option("--as-of", help="Reference date YYYY-MM-DD (default: today).")
    ] = None,
    allow_draft_rulepacks: Annotated[
        bool,
        typer.Option(
            "--allow-draft-rulepacks", help="Allow placeholder rule packs (not based on a norm text)."
        ),
    ] = False,
    show_paths: Annotated[
        bool, typer.Option("--show-paths", help="Show real paths instead of pseudonymous IDs.")
    ] = False,
    jobs: Annotated[
        int,
        typer.Option(
            "--jobs", min=1, max=64, help="Processes for the signal metrics (results do not change)."
        ),
    ] = 1,
    evidence: Annotated[
        str | None,
        typer.Option(
            "--evidence",
            help="evidence.yaml with the evidence for manual rules (default: .neurogrid/evidence.yaml).",
        ),
    ] = None,
    manifest_file: Annotated[
        str | None,
        typer.Option(
            "--manifest", help="Manifest to compare with (default: .neurogrid/manifest.json in the dataset)."
        ),
    ] = None,
) -> None:
    """Check a dataset against rule packs and write results.json."""
    reference = None
    if as_of:
        try:
            reference = date.fromisoformat(as_of)
        except ValueError:
            raise InputError("input.bad_date") from None
    _state["dataset_root"] = pipeline.resolve_target(path).root
    target = _output_file(out)
    options = pipeline.CheckOptions(
        rulepacks=tuple(_rulepack_refs(rulepack or [])),
        config_path=Path(config) if config else None,
        strict=strict,
        as_of=reference,
        allow_draft_rulepacks=allow_draft_rulepacks,
        show_paths=show_paths,
        jobs=jobs,
        work_base=target.absolute().parent,  # work folder next to the results file (A-54)
        evidence_path=Path(evidence) if evidence else None,
        manifest_path=Path(manifest_file) if manifest_file else None,
    )
    results = pipeline.run_check(path, options)
    _write_atomic(target, canonical.dumps(results))
    packs = ", ".join(p.name for p in results.rulepacks)
    _say("cli.check.fails" if results.summary.exit_code else "cli.check.passes", packs=packs)
    _say("cli.check.counts", errors=results.summary.errors, warnings=results.summary.warnings)
    if results.summary.open_evidence:
        _say("cli.check.open_evidence", count=results.summary.open_evidence)
    if any(p.source_status.value == "placeholder" for p in results.rulepacks):
        _say("cli.check.placeholder")
    for notice in results.notices:
        # warnings reach the console (links not followed, expired or unknown exceptions, evidence documents
        # that changed); their parameters are cleaned and shortened like those of error messages (A-51, A-53)
        if notice.level is Severity.WARNING:
            params = {
                name: _redact(_clean(str(value)))[:MAX_PARAM_CHARS] for name, value in notice.params.items()
            }
            _say(notice.message_key, **params)
    _say("cli.check.written", path=_display_path(target))
    _say("disclaimer")
    raise typer.Exit(code=results.summary.exit_code)


@app.command()
def convert(
    path: Annotated[str, typer.Argument(help="Raw data folder or single data file.")],
    to: Annotated[str, typer.Option("--to", help="Target structure: bids.")],
    out: Annotated[str, typer.Option("--out", help="Output folder (must be empty or missing).")],
    config: Annotated[str | None, typer.Option("--config", help="Path to neurogrid.toml.")] = None,
    strip_identifying_headers: Annotated[
        bool,
        typer.Option(
            "--strip-identifying-headers", help="Replace identifying header fields by placeholders."
        ),
    ] = False,
) -> None:
    """Convert a raw folder to EEG-BIDS and validate the result."""
    if to.strip().lower() != "bids":
        raise NeuroGridError("errors.convert.target_unavailable", target=to)
    _state["dataset_root"] = pipeline.resolve_target(path).root
    output = check_operator_path(out)
    summary = pipeline.run_convert(
        path,
        output,
        config_path=Path(config) if config else None,
        strip_identifying_headers=strip_identifying_headers,
        work_base=output.absolute().parent,
    )
    _say("cli.convert.converted", count=summary.converted)
    for item_id, reason in summary.skipped:
        _say("cli.convert.skipped", id=_clean(item_id), reason=translator(_lang()).t(f"reason.{reason}"))
    for name, count in summary.missing_fields.items():
        # n/a documents SoftwareFilters in BIDS (A-03), so 'check' reports only the other fields
        key = "cli.convert.missing_field" if name in NA_IS_MISSING else "cli.convert.missing_field_na_valid"
        _say(key, field=name, count=count)
    if summary.name_missing:
        _say("cli.convert.missing_name")
    if summary.converted:
        _say("cli.convert.validator", errors=summary.validator_errors, warnings=summary.validator_warnings)
        _say("cli.convert.written", path=_display_path(output))
    else:
        _say("cli.convert.nothing")
    _say("disclaimer")
    raise typer.Exit(code=summary.exit_code)


@app.command()
def report(
    results_file: Annotated[str, typer.Argument(help="results.json written by 'check'.")],
    lang: Annotated[list[str] | None, typer.Option("--lang", help="Report languages, e.g. zh,en.")] = None,
    fmt: Annotated[list[str] | None, typer.Option("--format", help="Output formats, e.g. html,pdf.")] = None,
    out: Annotated[
        str | None, typer.Option("--out", help="Output folder (default: next to results.json).")
    ] = None,
) -> None:
    """Render the report for each language and format."""
    from neurogrid.report.render import render_report

    source = check_operator_path(results_file)
    if not source.is_file():
        raise InputError("input.not_found")
    try:
        results = Results.model_validate_json(read_limited(source, MAX_RESULTS_BYTES))
    except ValueError:
        raise InputError("input.results_invalid") from None
    languages = list(dict.fromkeys(normalize_language(item) for item in _split_list(lang or ["zh,en"])))
    if not languages:
        raise ConfigError("i18n.empty")
    formats = _split_list(fmt or ["html"])
    for language in languages:
        if language not in REPORT_LANGUAGES:
            raise NeuroGridError("errors.i18n.unknown_language", language=language)
    for name in formats:
        if name != "html":
            raise NeuroGridError("errors.report.format_unavailable", format=name)
    folder = check_operator_path(out) if out else source.resolve().parent
    if folder.exists() and not folder.is_dir():
        raise InputError("output.not_writable")
    for language in languages:
        html = render_report(results, language)
        target = folder / f"report.{language}.html"
        _write_atomic(target, html.encode("utf-8"))
        _say("cli.report.written", path=_display_path(target))


def _print_list(items: list[str]) -> None:
    """Names from the dataset, without control characters (A-53), at most MAX_LISTED, then a count."""
    for item in items[:MAX_LISTED]:
        typer.echo(f"    - {_clean(item)}")
    if len(items) > MAX_LISTED:
        _say("cli.manifest.more", count=len(items) - MAX_LISTED)


@app.command()
def manifest(
    path: Annotated[str, typer.Argument(help="Dataset folder.")],
    out: Annotated[
        str | None,
        typer.Option(
            "--out", help="Manifest file (default: .neurogrid/manifest.json in the dataset folder)."
        ),
    ] = None,
    show_paths: Annotated[
        bool, typer.Option("--show-paths", help="Show real paths instead of pseudonymous IDs.")
    ] = False,
) -> None:
    """Write the provenance manifest: SHA-256 and size of every file, processing steps, software versions."""
    _state["dataset_root"] = pipeline.resolve_target(path).root
    target = _output_file(out) if out else None
    run = pipeline.run_manifest(path, target, show_paths=show_paths)
    if run.manifest is None or run.data is None:
        _say("cli.manifest.unreadable", count=len(run.unreadable))
        _print_list(run.unreadable)
        _say("cli.manifest.not_written")
    else:
        _write_atomic(run.target, run.data)
        _say("cli.manifest.summary", files=run.files, size=f"{run.total_bytes / 1_000_000:.1f}")
        if run.skipped:
            _say(
                "cli.manifest.skipped",
                links=run.skipped.get("link", 0),
                special=run.skipped.get("special", 0),
                unsafe=run.skipped.get("unsafe_name", 0),
            )
        _say("cli.manifest.hash", hash=run.manifest.manifest_hash)
        _say("cli.manifest.written", path=_display_path(run.target))
        if run.visible_to_validator:
            _say("cli.manifest.bids_hint")
    _say("disclaimer")
    raise typer.Exit(code=run.exit_code)


@app.command()
def verify(
    path: Annotated[str, typer.Argument(help="Dataset folder.")],
    manifest_file: Annotated[str, typer.Option("--manifest", help="manifest.json written by 'manifest'.")],
    show_paths: Annotated[
        bool, typer.Option("--show-paths", help="Show real paths instead of pseudonymous IDs.")
    ] = False,
) -> None:
    """Compare a dataset with its manifest: changed, new and missing files (exit 0 equal, 1 deviation)."""
    _state["dataset_root"] = pipeline.resolve_target(path).root
    run = pipeline.run_verify(path, manifest_file, show_paths=show_paths)
    _say("cli.verify.hash_ok" if run.hash_ok else "cli.verify.hash_mismatch", hash=run.manifest_hash)
    _say("cli.verify.checked", files=run.files)
    for kind, names in run.deviations.items():
        _say(f"cli.verify.{kind}", count=len(names))
        _print_list(names)
    _say("cli.verify.differs" if run.exit_code else "cli.verify.matches")
    _say("disclaimer")
    raise typer.Exit(code=run.exit_code)


def _error_text(exc: NeuroGridError) -> str:
    """Translated message; parameters may come from foreign files and are cleaned and shortened (A-53)."""
    tr = translator(_lang()).t
    key = exc.message_key if exc.message_key.startswith("errors.") else f"errors.{exc.message_key}"
    params = {name: _redact(_clean(str(value)))[:MAX_PARAM_CHARS] for name, value in exc.params.items()}
    return f"{tr('cli.error.prefix')}: {tr(key, **params)}"


_DATASET_PATH = re.compile(r"<dataset>[\\/][^\n]*")


def _internal_error_text(exc: BaseException) -> str:
    """Type name only; with --debug a traceback without control characters, home or dataset paths (A-51).

    Paths inside the dataset are cut after ``<dataset>``: they may hold real names in raw folders.
    """
    text = translator(_lang()).t("cli.error.internal", type=type(exc).__name__)
    if _state["debug"]:
        trace = _redact(_clean_lines("".join(traceback.format_exception(exc))))
        text += "\n" + _DATASET_PATH.sub("<dataset>/…", trace)
    return text


def _show_warning(
    message: Warning | str,
    category: type[Warning],
    filename: str,
    lineno: int,
    file: object = None,
    line: str | None = None,
) -> None:
    """Library warnings carry install paths and foreign text; only the category is shown (A-07, A-51)."""
    typer.echo(translator(_lang()).t("cli.warning.library", type=category.__name__), err=True)


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> None:
    netguard.install()
    _configure_output()
    _state.update(lang="en", debug=False, dataset_root=None)  # no state from an earlier call in-process
    warnings.showwarning = _show_warning
    code = 0
    try:
        rv = app(args=argv, standalone_mode=False, prog_name="neurogrid")
        code = rv if isinstance(rv, int) else 0
    except typer.Exit as exc:
        code = exc.exit_code
    except typer.Abort:
        code = 2
    except TyperException as exc:
        if type(exc).__name__ == "NoArgsIsHelpError":
            typer.echo(_clean_lines(exc.format_message()), err=True)  # plain help, not an error text
        else:
            message = _clean_lines(exc.format_message())
            typer.echo(translator(_lang()).t("cli.error.usage", problem=message), err=True)
        code = 2
    except NeuroGridError as exc:
        try:
            message = _error_text(exc)
        except Exception as inner:  # formatting must never turn a tool error into a crash (exit 2 stays)
            message = _internal_error_text(inner)
        typer.echo(message, err=True)
        code = 2
    except Exception as exc:  # every unexpected failure is a tool error (exit 2), never a data verdict
        typer.echo(_internal_error_text(exc), err=True)
        code = 2
    sys.exit(code)
