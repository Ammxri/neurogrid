"""Command line (PRD §13): scan, convert, check, report, manifest, verify. Further commands follow in later
phases.

Exit codes (NG-F14, A-12): 0 no failed error rule, 1 at least one, 2 tool error. manifest: 0 written, 1 files
could not be read (nothing written); verify: 0 the dataset matches the manifest, 1 any deviation (A-82);
report: 0 written, 2 tool error, e.g. no PDF browser for --format pdf (nothing written, A-26).
"""

from __future__ import annotations

import os
import re
import sys
import traceback
import unicodedata
import warnings
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Annotated, Any

import typer
from typer.core import TyperCommand, TyperGroup
from typer.exceptions import TyperException

from neurogrid import pipeline
from neurogrid.io.provenance import inside, shown_target
from neurogrid.kernel import canonical, netguard
from neurogrid.kernel.errors import ConfigError, InputError, NeuroGridError, PdfError
from neurogrid.kernel.findings import Severity
from neurogrid.kernel.i18n import DEFAULT_LANGUAGE, detect_language, normalize_language
from neurogrid.kernel.safety import (
    check_operator_path,
    create_temporary,
    home_folder,
    identity_names,
    read_limited,
    redact_paths,
)
from neurogrid.metadata import NA_IS_MISSING
from neurogrid.model.results import Results
from neurogrid.report.texts import REPORT_LANGUAGES, translator

MAX_RESULTS_BYTES = 256_000_000
MAX_PARAM_CHARS = 200
MAX_LISTED = 200  # names listed per kind by manifest and verify; the rest as a count

_state: dict[str, object] = {"lang": "en", "debug": False, "dataset_root": None}


def _lang() -> str:
    return str(_state["lang"])


# --- Help and usage errors in the selected language (NG-N06, A-07) ------------------------------------------
# --help, the usage headings and usage errors are messages: every text comes from the language tables
# (cli.help.*, cli.error.*), none from Typer or click. NeuroGrid renders the help of its own commands through
# the public ``cls`` hook of Typer; option and command names stay as they are typed.


class _UsageProblem(TyperException):
    """A usage error that NeuroGrid words itself: a message key and its (cleaned) parameters."""

    def __init__(self, key: str, **params: str) -> None:
        super().__init__(key)
        self.key = key
        self.params = params


def _param_key(param: Any) -> str:
    """Key part of a parameter: the argument name, or the first long option name with '_' for '-'."""
    if param.param_type_name == "argument":
        return str(param.name)
    long_names = [name for name in param.opts if name.startswith("--")] or list(param.opts)
    return str(long_names[0]).lstrip("-").replace("-", "_")


def _param_label(param: Any) -> str:
    """How help and errors name a parameter: PATH for arguments, '--to' for options."""
    if param.param_type_name == "argument":
        return str(param.name).upper()
    return ", ".join(param.opts)


def _help_rows(command: Any, ctx: Any, scope: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    tr = translator(_lang()).t
    arguments: list[tuple[str, str]] = []
    options: list[tuple[str, str]] = []
    for param in command.get_params(ctx):
        if getattr(param, "hidden", False):
            continue
        if param.name == "help":
            options.append((", ".join(param.opts), tr("cli.help.option.help")))
            continue
        text = tr(f"cli.help.{scope}.{_param_key(param)}")
        if param.required:
            text += f"  [{tr('cli.help.required')}]"
        if param.param_type_name == "argument":
            arguments.append((_param_label(param), text))
            continue
        label = _param_label(param)
        if not param.is_flag:
            kind = getattr(param.type, "name", "")
            label += " " + (tr("cli.help.metavar.number") if "int" in kind else tr("cli.help.metavar.value"))
            if param.default is not None and param.default != [] and not param.required:
                text += f"  [{tr('cli.help.default', value=param.default)}]"
        options.append((label, text))
    return arguments, options


def _write_usage(formatter: Any, ctx: Any, pieces: str) -> None:
    heading = translator(_lang()).t("cli.help.heading.usage")
    prefix = heading if heading.endswith("：") else heading + " "  # no space after a full-width colon
    formatter.write_usage(ctx.command_path, pieces, prefix=prefix)


def _parse_with_context(parse: Any, ctx: Any, args: list[str]) -> list[str]:
    """click's parser raises some usage errors (an option without its value, a value for a flag) without
    their command; NeuroGrid's message names the command and needs the option (NG-N06)."""
    try:
        rest: list[str] = parse(ctx, args)
    except TyperException as exc:
        if hasattr(exc, "ctx") and exc.ctx is None:
            exc.ctx = ctx
        raise
    return rest


_WIDE = ("W", "F")
_MAX_LABEL_CELLS = 30


def _cells(text: str) -> int:
    """Terminal columns of a text: East Asian wide and full-width characters take two (Chinese help)."""
    return sum(2 if unicodedata.east_asian_width(ch) in _WIDE else 1 for ch in text)


_CLOSING = set("。，、；：！？）》」』】")  # never at the start of a line
_OPENING = set("（《「『【")  # never at the end of a line


def _units(word: str) -> list[str]:
    """Break points inside a word without spaces: before and after every wide character, except before
    closing and after opening punctuation; narrow characters stay together (for example 'neurogrid.toml'
    inside Chinese text), so does a bracketed note such as '[默认：1]'."""
    if word.startswith("[") and word.endswith("]"):
        return [word]
    units: list[str] = []
    for ch in word:
        joins = ch in _CLOSING or (_cells(ch) == 1 and _cells(units[-1][-1]) == 1) if units else False
        if joins or (units and units[-1][-1] in _OPENING):
            units[-1] += ch
        else:
            units.append(ch)
    return units


def _wrap(text: str, width: int) -> list[str]:
    """Lines of at most ``width`` terminal columns (a longer unit keeps a line of its own). Chinese text
    wraps without spaces and the columns stay aligned (NG-N06)."""
    lines: list[str] = []
    line, used = "", 0
    for word in text.split():
        for index, part in enumerate(_units(word)):
            gap = 1 if index == 0 and line else 0
            if line and used + gap + _cells(part) > width:
                lines.append(line)
                line, used, gap = "", 0, 0
            line += " " * gap + part
            used += gap + _cells(part)
    if line:
        lines.append(line)
    return lines


def _write_text(formatter: Any, text: str) -> None:
    indent = " " * formatter.current_indent
    for line in _wrap(text, max(formatter.width - formatter.current_indent, 20)):
        formatter.write(f"{indent}{line}\n")


def _write_rows(formatter: Any, rows: list[tuple[str, str]]) -> None:
    """A two-column list like click's write_dl, measured in terminal columns."""
    indent = formatter.current_indent
    first = min(max(_cells(label) for label, _ in rows), _MAX_LABEL_CELLS)
    start = indent + first + 2
    for label, text in rows:
        lines = _wrap(text, max(formatter.width - start, 20)) or [""]
        if _cells(label) > first:
            formatter.write(f"{' ' * indent}{label}\n")
        else:
            head = lines.pop(0)
            formatter.write(f"{' ' * indent}{label}{' ' * (first - _cells(label) + 2)}{head}\n")
        for line in lines:
            formatter.write(f"{' ' * start}{line}\n")


def _write_section(formatter: Any, heading: str, rows: list[tuple[str, str]]) -> None:
    if rows:
        formatter.write_paragraph()
        formatter.write(f"{heading}\n")
        formatter.indent()
        _write_rows(formatter, rows)
        formatter.dedent()


class _HelpCommand(TyperCommand):
    """A NeuroGrid command whose help text comes from the language tables (NG-N06)."""

    allow_extra_args = True  # extra arguments are reported by parse_args in NeuroGrid's own words

    def format_help(self, ctx: Any, formatter: Any) -> None:
        tr = translator(_lang()).t
        scope = str(self.name)
        pieces = [tr("cli.help.metavar.options")]
        pieces += [_param_label(p) for p in self.get_params(ctx) if p.param_type_name == "argument"]
        _write_usage(formatter, ctx, " ".join(pieces))
        formatter.write_paragraph()
        formatter.indent()
        _write_text(formatter, tr(f"cli.help.{scope}.about"))
        formatter.dedent()
        arguments, options = _help_rows(self, ctx, scope)
        _write_section(formatter, tr("cli.help.heading.arguments"), arguments)
        _write_section(formatter, tr("cli.help.heading.options"), options)

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        rest = _parse_with_context(super().parse_args, ctx, args)
        if rest and not ctx.resilient_parsing:
            shown = " ".join(_redact(_clean(item)) for item in rest)[:MAX_PARAM_CHARS]
            raise _UsageProblem("cli.error.extra_arguments", arguments=shown)
        return rest


class _HelpGroup(TyperGroup):
    """The neurogrid command group: help and unknown commands in NeuroGrid's own words (NG-N06)."""

    def format_help(self, ctx: Any, formatter: Any) -> None:
        tr = translator(_lang()).t
        pieces = f"{tr('cli.help.metavar.options')} {tr('cli.help.metavar.command')}"
        _write_usage(formatter, ctx, pieces)
        formatter.write_paragraph()
        formatter.indent()
        _write_text(formatter, tr("cli.help.app"))
        formatter.dedent()
        _arguments, options = _help_rows(self, ctx, "global")
        _write_section(formatter, tr("cli.help.heading.options"), options)
        commands = [(name, tr(f"cli.help.{name}.about")) for name in self.list_commands(ctx)]
        _write_section(formatter, tr("cli.help.heading.commands"), commands)

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        return _parse_with_context(super().parse_args, ctx, args)

    def resolve_command(self, ctx: Any, args: list[str]) -> Any:
        name = args[0] if args else ""
        if self.get_command(ctx, name) is None and not name.startswith("-") and not ctx.resilient_parsing:
            raise _UsageProblem("cli.error.no_such_command", name=_clean(name)[:MAX_PARAM_CHARS])
        return super().resolve_command(ctx, args)


def _find_option(exc: Any) -> Any:
    ctx = getattr(exc, "ctx", None)
    name = getattr(exc, "option_name", None)
    if ctx is None or name is None:
        return None
    return next((p for p in ctx.command.get_params(ctx) if name in getattr(p, "opts", ())), None)


def _usage_problem(exc: TyperException, command_given: bool) -> str:
    """The usage error in the selected language. click's English sentence is never shown (A-07): the text
    follows from the exception type and its parameter, foreign values are cleaned and shortened (A-53)."""
    tr = translator(_lang()).t
    if isinstance(exc, _UsageProblem):
        return tr(exc.key, **exc.params)
    ctx = getattr(exc, "ctx", None)
    command = _clean(ctx.command_path) if ctx is not None else "neurogrid"
    kinds = {cls.__name__ for cls in type(exc).__mro__}
    param = getattr(exc, "param", None)
    if "MissingParameter" in kinds and param is not None:
        key = (
            "cli.error.missing_argument"
            if param.param_type_name == "argument"
            else "cli.error.missing_option"
        )
        return tr(key, name=_param_label(param), command=command)
    if "BadParameter" in kinds and param is not None:
        return tr("cli.error.bad_parameter", name=_param_label(param), command=command)
    if "NoSuchOption" in kinds:
        name = _redact(_clean(str(getattr(exc, "option_name", ""))))[:MAX_PARAM_CHARS]
        return tr("cli.error.no_such_option", name=name, command=command)
    if "BadOptionUsage" in kinds:
        option = _find_option(exc)
        name = _clean(str(getattr(exc, "option_name", "")))[:MAX_PARAM_CHARS]
        if option is not None and getattr(option, "is_flag", False):
            return tr("cli.error.option_takes_no_value", name=name, command=command)
        return tr("cli.error.option_needs_value", name=name, command=command)
    if not command_given:
        return tr("cli.error.missing_command")
    return tr("cli.error.usage_generic", type=type(exc).__name__, command=command)


def _argv_language(args: list[str]) -> tuple[str, bool]:
    """The message language before the command line is parsed, for help and usage errors (NG-N06): the
    global --lang (before the command name; 'report' has an own --lang) > NEUROGRID_LANG > system locale,
    decided like detect_language. Also tells whether a command name follows. An invalid choice falls back
    here; the callback reports it afterwards (exit 2)."""
    explicit: str | None = None
    command_given = False
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--lang" and index + 1 < len(args):
            explicit = args[index + 1]
            index += 2
            continue
        if token.startswith("--lang="):
            explicit = token.split("=", 1)[1]
        elif not token.startswith("-"):
            command_given = True
            break
        index += 1
    for candidate in (explicit or None, None):
        try:
            return detect_language(candidate, supported=REPORT_LANGUAGES), command_given
        except ConfigError:
            continue
    return DEFAULT_LANGUAGE, command_given


app = typer.Typer(
    cls=_HelpGroup,
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
    rich_markup_mode=None,
)


def _say(key: str, **params: object) -> None:
    typer.echo(translator(_lang()).t(key, **params))


def _clean(text: str) -> str:
    """Drop control characters from untrusted text before printing it (A-53)."""
    return "".join(ch for ch in text if ch.isprintable())


def _clean_lines(text: str) -> str:
    """Like _clean, but keeps the line structure of multi-line texts (help, tracebacks)."""
    return "\n".join(_clean(line) for line in text.splitlines())


def _redact(text: str, *, names: bool = True) -> str:
    """Output filter for console text (A-51): dataset root → <dataset>, home directory → ~, then the login
    and the computer name → <user>, <host> (they stand in paths outside the home folder, e.g. Linux's
    /tmp/pytest-of-<user>). Without ``names`` for the PDF hint, a command that must run as printed (B2)."""
    root = _state["dataset_root"]
    roots = {"<dataset>": root if isinstance(root, Path) else None, "~": home_folder()}
    return redact_paths(text, roots, identity_names() if names else None)


def _display_path(path: Path) -> str:
    return _redact(str(path.absolute()))


def _in_dataset(shown: str) -> str:
    """A name inside the dataset (relative POSIX path or pseudonymous file name) as the console prints it."""
    return _clean(str(Path("<dataset>", *PurePosixPath(shown).parts)))


def _written_path(target: Path, *, plain: bool) -> str:
    """An output file the operator chose (--out), as the console names it (A-51): inside the dataset like
    the manifest target (shown_target: in raw folders by the pseudonymous file name verify would show, after
    '…' for its folder; in clear in BIDS datasets (``plain``), with --show-paths (``plain``) and for
    NeuroGrid's fixed names in .neurogrid/), outside it with the dataset root and the home folder redacted."""
    root = _state["dataset_root"]
    own = inside(root, target) if isinstance(root, Path) else None
    if own is None:
        return _display_path(target)
    return _in_dataset(shown_target(own, plain=plain))


def _output_file(raw: str) -> Path:
    """An output file from the command line. A trailing separator means a folder, which is refused."""
    if raw.endswith(("/", "\\")):
        raise InputError("output.is_directory")
    return check_operator_path(raw)


def _given_path(raw: str | None) -> Path | None:
    """An optional file option. Given but empty (an unset variable in a batch script) is an invalid path
    (exit 2), never the default location (A-82)."""
    return None if raw is None else check_operator_path(raw)


def _write_atomic(path: Path, data: bytes) -> None:
    """Write via a private temporary file in the target folder; nothing is left behind on failure (A-54)."""
    if path.is_dir():
        raise InputError("output.is_directory")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = create_temporary(path.parent, f".{path.name}.")
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
    lang: Annotated[str | None, typer.Option("--lang")] = None,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    _state["debug"] = debug
    if lang is not None and not lang.strip():
        raise ConfigError("i18n.empty")  # an explicit but empty choice is no silent fallback (A-73)
    _state["lang"] = detect_language(lang, supported=REPORT_LANGUAGES)


@app.command(cls=_HelpCommand)
def scan(
    path: Annotated[str, typer.Argument()],
    out: Annotated[str | None, typer.Option("--out")] = None,
    show_paths: Annotated[bool, typer.Option("--show-paths")] = False,
) -> None:
    """Inventory: formats, subjects, recordings, sizes, unsupported files."""
    _state["dataset_root"] = pipeline.resolve_target(path).root
    target = _output_file(out) if out is not None else None  # an invalid --out ends before the scan
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
    if target is not None:
        _write_atomic(target, canonical.dumps(result))
        _say("cli.scan.written", path=_written_path(target, plain=result.is_bids or show_paths))


@app.command(cls=_HelpCommand)
def check(
    path: Annotated[str, typer.Argument()],
    rulepack: Annotated[list[str] | None, typer.Option("--rulepack")] = None,
    config: Annotated[str | None, typer.Option("--config")] = None,
    out: Annotated[str, typer.Option("--out")] = "results.json",
    strict: Annotated[bool, typer.Option("--strict")] = False,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    allow_draft_rulepacks: Annotated[bool, typer.Option("--allow-draft-rulepacks")] = False,
    show_paths: Annotated[bool, typer.Option("--show-paths")] = False,
    jobs: Annotated[int, typer.Option("--jobs", min=1, max=64)] = 1,
    evidence: Annotated[str | None, typer.Option("--evidence")] = None,
    manifest_file: Annotated[str | None, typer.Option("--manifest")] = None,
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
        config_path=_given_path(config),
        strict=strict,
        as_of=reference,
        allow_draft_rulepacks=allow_draft_rulepacks,
        show_paths=show_paths,
        jobs=jobs,
        work_base=target.absolute().parent,  # work folder next to the results file (A-54)
        evidence_path=_given_path(evidence),
        manifest_path=_given_path(manifest_file),
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
    _say("cli.check.written", path=_written_path(target, plain=results.dataset.is_bids or show_paths))
    _say("disclaimer")
    raise typer.Exit(code=results.summary.exit_code)


@app.command(cls=_HelpCommand)
def convert(
    path: Annotated[str, typer.Argument()],
    to: Annotated[str, typer.Option("--to")],
    out: Annotated[str, typer.Option("--out")],
    config: Annotated[str | None, typer.Option("--config")] = None,
    strip_identifying_headers: Annotated[bool, typer.Option("--strip-identifying-headers")] = False,
) -> None:
    """Convert a raw folder to EEG-BIDS and validate the result."""
    if to.strip().lower() != "bids":
        raise NeuroGridError("errors.convert.target_unavailable", target=to)
    _state["dataset_root"] = pipeline.resolve_target(path).root
    output = check_operator_path(out)
    summary = pipeline.run_convert(
        path,
        output,
        config_path=_given_path(config),
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


@app.command(cls=_HelpCommand)
def report(
    results_file: Annotated[str, typer.Argument()],
    lang: Annotated[list[str] | None, typer.Option("--lang")] = None,
    fmt: Annotated[list[str] | None, typer.Option("--format")] = None,
    out: Annotated[str | None, typer.Option("--out")] = None,
) -> None:
    """Render the report for each language and format (HTML; PDF with the PDF browser)."""
    from neurogrid.report.output import FORMATS, write_reports

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
        if name not in FORMATS:
            raise NeuroGridError("errors.report.format_unavailable", format=name)
    folder = check_operator_path(out) if out is not None else source.resolve().parent
    if folder.exists() and not folder.is_dir():
        raise InputError("output.not_writable")
    # all files or none (A-26); with pdf the PDF browser is checked before anything is rendered
    for target in write_reports(results, languages, formats, folder, environ=os.environ):
        _say("cli.report.written", path=_display_path(target))
    _say("disclaimer")


def _print_list(items: list[str]) -> None:
    """Names from the dataset, without control characters (A-53), at most MAX_LISTED, then a count."""
    for item in items[:MAX_LISTED]:
        typer.echo(f"    - {_clean(item)}")
    if len(items) > MAX_LISTED:
        _say("cli.manifest.more", count=len(items) - MAX_LISTED)


@app.command(cls=_HelpCommand)
def manifest(
    path: Annotated[str, typer.Argument()],
    out: Annotated[str | None, typer.Option("--out")] = None,
    show_paths: Annotated[bool, typer.Option("--show-paths")] = False,
) -> None:
    """Write the provenance manifest: SHA-256 and size of every file, processing steps, software versions."""
    _state["dataset_root"] = pipeline.resolve_target(path).root
    target = _output_file(out) if out is not None else None
    run = pipeline.run_manifest(path, target, show_paths=show_paths)
    if run.too_many_entries is not None:  # dataset data: a result without a manifest, not an error (C2)
        _say("cli.manifest.too_many_entries", limit=run.too_many_entries)
    elif run.manifest is None or run.data is None:
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
        if run.shown_target is not None:  # inside the dataset: real names only where A-51 allows them
            _say("cli.manifest.written", path=_in_dataset(run.shown_target))
        else:
            _say("cli.manifest.written", path=_display_path(run.target))
        if run.validator_listing == "listed":
            _say("cli.manifest.bids_hint")
        elif run.validator_listing == "maybe":
            _say("cli.manifest.bids_hint_bidsignore")
    _say("disclaimer")
    raise typer.Exit(code=run.exit_code)


@app.command(cls=_HelpCommand)
def verify(
    path: Annotated[str, typer.Argument()],
    manifest_file: Annotated[str, typer.Option("--manifest")],
    show_paths: Annotated[bool, typer.Option("--show-paths")] = False,
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
    """Translated message; parameters may come from foreign files and are cleaned and shortened (A-53).

    A PDF error may carry a hint (e.g. the installer command or the apt packages): NeuroGrid's own values,
    cleaned and with home and dataset paths redacted, but not shortened (A-51)."""
    tr = translator(_lang()).t
    key = exc.message_key if exc.message_key.startswith("errors.") else f"errors.{exc.message_key}"
    params = {name: _redact(_clean(str(value)))[:MAX_PARAM_CHARS] for name, value in exc.params.items()}
    text = f"{tr('cli.error.prefix')}: {tr(key, **params)}"
    if isinstance(exc, PdfError) and exc.hint is not None:
        hint_key, hint_params = exc.hint
        cleaned = {name: _redact(_clean(str(value)), names=False) for name, value in hint_params.items()}
        text += "\n" + tr(f"errors.{hint_key}", **cleaned)
    return text


_DATASET_PATH = re.compile(r"<dataset>[\\/][^\n]*")
_INPUT_VALUE = re.compile(r"input_value=[^\n]*")  # pydantic shows the validated input, e.g. a file name


def _internal_error_text(exc: BaseException) -> str:
    """Type name only; with --debug a traceback without control characters, home or dataset paths (A-51).

    Paths inside the dataset are cut after ``<dataset>``: they may hold real names in raw folders. So is the
    input a validation error quotes (relative names from the dataset carry no ``<dataset>``).
    """
    text = translator(_lang()).t("cli.error.internal", type=type(exc).__name__)
    if _state["debug"]:
        trace = _redact(_clean_lines("".join(traceback.format_exception(exc))))
        text += "\n" + _INPUT_VALUE.sub("input_value=…]", _DATASET_PATH.sub("<dataset>/…", trace))
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
    # no state from an earlier call in-process; help and usage errors already speak the chosen language
    language, command_given = _argv_language(sys.argv[1:] if argv is None else argv)
    _state.update(lang=language, debug=False, dataset_root=None)
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
            message = _usage_problem(exc, command_given)
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
