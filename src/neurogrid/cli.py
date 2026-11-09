"""Command line (PRD §13): scan, convert, check, report, manifest, verify, diff (v1.0), and the NeuroVault
groups 'vault' and 'vault consent' (v0.2; vault export v1.0).

Exit codes (NG-F14, A-12): 0 no failed error rule, 1 at least one, 2 tool error. manifest: 0 written, 1 files
could not be read (nothing written); verify: 0 the dataset matches the manifest, 1 any deviation (A-82);
diff: 0 no new error finding, 1 new error findings, 2 tool error (A-97);
report: 0 written, 2 tool error, e.g. no PDF browser for --format pdf or dossier (nothing written, A-26).
vault init, vault log and vault export: 0 done, 2 every refusal (export: never 1, A-96); vault verify: 0 the
access log is intact, 1 a deviation (also a missing log or an expected head not found), 2 tool error
(CLI-09). An access event that cannot be written after the outputs of a run is a warning and never changes
the exit code; check, report --config and every vault command end with exit 2 on a link in the vault path
(A-30, p6 decisions 2 and 4).
"""

from __future__ import annotations

import hashlib
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

from neurogrid import config as config_module
from neurogrid import pipeline
from neurogrid.io.provenance import inside, shown_target
from neurogrid.kernel import canonical, netguard, processes
from neurogrid.kernel.errors import ConfigError, InputError, NeuroGridError, PdfError
from neurogrid.kernel.findings import Severity, SourceStatus
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
from neurogrid.model.consent import (
    CONSENT_USES,
    ConsentScope,
    ConsentUse,
    date_from_text,
    ethics_ref_valid,
    subject_id,
    version_from_text,
)
from neurogrid.model.results import Results
from neurogrid.report.tables import reconsent_subjects
from neurogrid.report.texts import REPORT_LANGUAGES, translator
from neurogrid.vault.ledger import AppendOutcome, Deviation, Entry

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


def _help_scope(ctx: Any) -> str:
    """The help scope of a command: its dotted command path below the root ("check", "vault",
    "vault.consent.add"), "" for the root itself. Its keys are cli.help.<scope>.about and
    cli.help.<scope>.<param>; a group lists its commands with cli.help.<scope>.<name>.about. Nested scopes
    keep 'vault verify' apart from the top-level 'verify' (p6 decisions 5)."""
    names: list[str] = []
    while ctx is not None and ctx.parent is not None:
        names.append(str(ctx.command.name))
        ctx = ctx.parent
    return ".".join(reversed(names))


def _scoped(scope: str, name: str) -> str:
    return f"{scope}.{name}" if scope else name


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
        scope = _help_scope(ctx)
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
    """A NeuroGrid command group (the root and the nested 'vault', 'vault consent'): help and unknown commands
    in NeuroGrid's own words (NG-N06). The root's texts are cli.help.app and cli.help.global.*, a nested
    group's those of its help scope."""

    def format_help(self, ctx: Any, formatter: Any) -> None:
        tr = translator(_lang()).t
        scope = _help_scope(ctx)
        pieces = f"{tr('cli.help.metavar.options')} {tr('cli.help.metavar.command')}"
        _write_usage(formatter, ctx, pieces)
        formatter.write_paragraph()
        formatter.indent()
        _write_text(formatter, tr(f"cli.help.{scope}.about" if scope else "cli.help.app"))
        formatter.dedent()
        _arguments, options = _help_rows(self, ctx, scope or "global")
        _write_section(formatter, tr("cli.help.heading.options"), options)
        commands = [(name, tr(f"cli.help.{_scoped(scope, name)}.about")) for name in self.list_commands(ctx)]
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


def _access_messages(
    access: pipeline.PendingAccess | None, outcome: AppendOutcome | None, *, role_option: bool = False
) -> None:
    """What the user needs to know about the access event of a run (p6 decisions 4), committed after its
    outputs were written: --role without a vault, an event that was not written with its reason, and for a
    written automatic event a missing role (recorded as null) or a role that looks like a name; then the
    role register's view of the event, compared at the start of the run (A-93). The exit code never changes
    for it."""
    if access is None:
        if role_option:
            _say("cli.vault.role_without_vault")
        return
    if outcome is None or outcome.status != "written":
        status = outcome.status if outcome is not None else "no_vault"
        reason = translator(_lang()).t(f"cli.vault.event_reason.{status}")
        _say("cli.vault.event_not_written", reason=reason)
    elif access.action != "read":  # scan, manifest and verify record no role (p6 decisions 4)
        if access.role is None:
            _say("cli.vault.role_missing")
        elif access.role_looks_identifying:
            _say("cli.vault.role_looks_identifying")
    _role_warning(access.role_warning)


def _role_warning(warning: str | None) -> None:
    """The warning of a command whose access the role register does not permit, or whose register cannot be
    read (KONZEPT 2.8 "Ein Befehl warnt", A-93): the event is written anyway, the exit code stays."""
    from neurogrid.vault.roles import ROLES_INVALID

    if warning == ROLES_INVALID:
        _say("cli.vault.roles_invalid")
    elif warning is not None:
        _say("cli.vault.role_not_permitted", reason=translator(_lang()).t(f"cli.vault.role_reason.{warning}"))


def _commit(access: pipeline.PendingAccess | None) -> AppendOutcome | None:
    """Append the run's access event; called after every output of the run is written (KONZEPT 1.4 step 8)."""
    return access.commit() if access is not None else None


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
    access = pipeline.read_access(path)
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
    _access_messages(access, _commit(access))  # after the inventory is written (p6 decisions 4)


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
    role: Annotated[str | None, typer.Option("--role")] = None,
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
        # a dead process of --jobs: only the time is lost, its output never reaches the console (A-89)
        on_recompute=lambda count: _say("cli.check.recomputed", count=count),
        work_base=target.absolute().parent,  # work folder next to the results file (A-54)
        evidence_path=_given_path(evidence),
        manifest_path=_given_path(manifest_file),
        role=role,
    )
    run = pipeline.check_run(path, options)
    results = run.results
    _write_atomic(target, canonical.dumps(results))
    outcome = _commit(run.access)  # after results.json: the event never reaches it (DoD P6, A-30)
    # the sentence names only the evaluated packs: a dataset never "passes" a placeholder pack (POS-01,
    # A-41, A-92); with placeholder packs alone nothing was evaluated (and the exit code is 0)
    placeholder = [p.name for p in results.rulepacks if p.source_status is SourceStatus.PLACEHOLDER]
    evaluated = [p.name for p in results.rulepacks if p.source_status is not SourceStatus.PLACEHOLDER]
    if evaluated:
        verdict = "cli.check.fails" if results.summary.exit_code else "cli.check.passes"
        _say(verdict, packs=", ".join(evaluated))
    else:
        _say("cli.check.none_evaluated", packs=", ".join(placeholder))
    _say("cli.check.counts", errors=results.summary.errors, warnings=results.summary.warnings)
    if results.summary.open_evidence:
        _say("cli.check.open_evidence", count=results.summary.open_evidence)
    if reconsent := reconsent_subjects(results):  # a number only: the list is in results.json (A-95)
        _say("cli.check.reconsent", count=reconsent)
    if placeholder:
        _say("cli.check.placeholder")
    for notice in results.notices:
        # warnings reach the console (links not followed, expired or unknown exceptions, evidence documents
        # that changed); their parameters are cleaned and shortened like those of error messages (A-51, A-53)
        if notice.level is Severity.WARNING:
            params = {
                name: _redact(_clean(str(value)))[:MAX_PARAM_CHARS] for name, value in notice.params.items()
            }
            _say(notice.message_key, **params)
    _access_messages(run.access, outcome, role_option=role is not None)
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
    """Convert a raw folder to EEG-BIDS, or a raw or BIDS folder to GB/T 47127 (P7), and check the result."""
    target = to.strip().lower()
    if target not in ("bids", "gbt47127"):
        raise NeuroGridError("errors.convert.target_unavailable", target=to)
    _state["dataset_root"] = pipeline.resolve_target(path).root
    output = check_operator_path(out)
    summary = pipeline.run_convert(
        path,
        output,
        config_path=_given_path(config),
        strip_identifying_headers=strip_identifying_headers,
        work_base=output.absolute().parent,
        to=target,
    )
    outcome = _commit(summary.access)  # after the output and its check
    _say("cli.convert.converted", count=summary.converted)
    for item_id, reason in summary.skipped:
        _say("cli.convert.skipped", id=_clean(item_id), reason=translator(_lang()).t(f"reason.{reason}"))
    gbt = summary.target == "gbt47127"
    for name, count in summary.missing_fields.items():
        # n/a documents SoftwareFilters in BIDS (A-03), so 'check' reports only the other fields;
        # GB/T 47127: undocumented values are left out
        if gbt:
            key = "cli.convert.gbt_gap"
        else:
            key = (
                "cli.convert.missing_field" if name in NA_IS_MISSING else "cli.convert.missing_field_na_valid"
            )
        _say(key, field=name, count=count)
    if summary.name_missing:
        _say("cli.convert.missing_name")
    if summary.converted:
        check_key = "cli.convert.gbt_check" if gbt else "cli.convert.validator"
        _say(check_key, errors=summary.validator_errors, warnings=summary.validator_warnings)
        _say("cli.convert.gbt_written" if gbt else "cli.convert.written", path=_display_path(output))
    else:
        _say("cli.convert.gbt_nothing" if gbt else "cli.convert.nothing")
    _access_messages(summary.access, outcome)
    _say("disclaimer")
    raise typer.Exit(code=summary.exit_code)


@app.command(cls=_HelpCommand)
def report(
    results_file: Annotated[str, typer.Argument()],
    lang: Annotated[list[str] | None, typer.Option("--lang")] = None,
    fmt: Annotated[list[str] | None, typer.Option("--format")] = None,
    out: Annotated[str | None, typer.Option("--out")] = None,
    config: Annotated[str | None, typer.Option("--config")] = None,
) -> None:
    """Render the report for each language and format (HTML; PDF with the PDF browser; the dossier, A-99:
    dossier.pdf with the zh and en report whatever --lang says). With --config the report finds the vault of
    that neurogrid.toml: the cover shows its access log, and the report appends its access event after the
    files are written (A-30); without it no vault is read or written."""
    from neurogrid.report.output import FORMATS, write_reports

    source = check_operator_path(results_file)
    if not source.is_file():
        raise InputError("input.not_found")
    data = read_limited(source, MAX_RESULTS_BYTES)
    try:
        results = Results.model_validate_json(data)
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
    access, view = None, None
    if config is not None:  # a link in the vault path ends here, before anything is rendered (exit 2)
        access, view = pipeline.report_vault(check_operator_path(config))
    # all files or none (A-26); with pdf the PDF browser is checked before anything is rendered; the dossier
    # names the SHA-256 of the results.json bytes it was made from (A-99)
    sha256 = hashlib.sha256(data).hexdigest()
    written = write_reports(
        results, languages, formats, folder, environ=os.environ, vault=view, results_sha256=sha256
    )
    for target in written:
        _say("cli.report.written", path=_display_path(target))
    _access_messages(access, _commit(access))
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
    # after the manifest is written, which leaves the log and its lock file out (A-82)
    _access_messages(run.access, _commit(run.access))
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
    _access_messages(run.access, _commit(run.access))
    _say("disclaimer")
    raise typer.Exit(code=run.exit_code)


@app.command("diff", cls=_HelpCommand)
def diff_runs(
    old: Annotated[str, typer.Argument()],
    new: Annotated[str, typer.Argument()],
    fmt: Annotated[list[str] | None, typer.Option("--format")] = None,
    out: Annotated[str | None, typer.Option("--out")] = None,
) -> None:
    """Compare two results.json files (NG-F15, CLI-07, A-97): new, fixed, removed and changed findings. Exit 0
    no new error finding, 1 new error findings, 2 tool error. The text goes to stdout; the JSON to stdout when
    it is the only format and --out is missing, else into --out. Reads no dataset, writes no access event."""
    from neurogrid import diff

    formats = _split_list(fmt or ["text"])
    if not formats:
        raise NeuroGridError("errors.report.format_unavailable", format="")
    for name in formats:
        if name not in diff.FORMATS:
            raise NeuroGridError("errors.report.format_unavailable", format=name)
    if out is not None and "json" not in formats:
        raise InputError("diff.out_needs_json")
    if out is None and len(formats) > 1:  # text and json: the console takes the text, the JSON needs a file
        raise InputError("diff.json_needs_out")
    target = _output_file(out) if out is not None else None
    result = diff.compare(diff.load(old, "OLD"), diff.load(new, "NEW"))
    if "text" in formats:
        for line in diff.text_lines(result, _lang()):
            typer.echo(line)
    if "json" in formats:
        data = canonical.dumps(result)
        if target is None:  # the JSON alone on stdout: its field disclaimer is the fixed sentence (A-08)
            typer.echo(data.decode("utf-8"), nl=False)
            raise typer.Exit(code=result.summary.exit_code)
        _write_atomic(target, data)
        _say("cli.diff.written", path=_display_path(target))
    _say("disclaimer")
    raise typer.Exit(code=result.summary.exit_code)


# --- vault (CLI-08, CLI-09, NV-F03; A-30, A-31, D-10) -------------------------------------------------------
# The NeuroVault commands live in the nested groups 'vault' and 'vault consent'; their help scopes are
# "vault.<command>" and "vault.consent.<command>" (_help_scope). The commands are added to these groups.

vault_app = typer.Typer(cls=_HelpGroup, no_args_is_help=True, rich_markup_mode=None)
consent_app = typer.Typer(cls=_HelpGroup, no_args_is_help=True, rich_markup_mode=None)
vault_app.add_typer(consent_app, name="consent")
app.add_typer(vault_app, name="vault")


def _consent_record(
    ctx: typer.Context,
    subject: str | None,
    version: str | None,
    when: str | None,
    uses: list[str],
    withdrawn: bool,
    ethics_ref: str | None,
) -> ConsentScope:
    """The single record of ``vault consent add`` from its options (NV-F01). Every refusal is exit 2 and
    names the option, never the value (A-51)."""
    for option, value in (("--subject", subject), ("--version", version), ("--date", when)):
        if value is None:
            raise _UsageProblem("cli.error.missing_option", name=option, command=_clean(ctx.command_path))
    assert subject is not None and version is not None and when is not None
    if withdrawn and uses:
        raise InputError("consent.withdrawn_with_uses")
    if not withdrawn and not uses:
        raise InputError("consent.uses_required")
    if any(use not in CONSENT_USES for use in uses):
        raise InputError("consent.unknown_use", allowed=", ".join(CONSENT_USES))
    pseudo_id = subject_id(subject.strip())
    if pseudo_id is None:
        raise InputError("consent.subject_invalid")
    number = version_from_text(version.strip())
    if number is None:
        raise InputError("consent.version_invalid")
    moment = date_from_text(when.strip())
    if moment is None:
        raise InputError("consent.date_invalid")
    if ethics_ref is not None and not ethics_ref_valid(ethics_ref):
        raise InputError("consent.ethics_ref_invalid")
    return ConsentScope(
        subject=pseudo_id,
        version=number,
        date=moment,
        permitted_uses=tuple(ConsentUse(use) for use in uses),
        withdrawn=withdrawn,
        ethics_approval_ref=ethics_ref,
    )


@consent_app.command("add", cls=_HelpCommand)
def consent_add(
    ctx: typer.Context,
    path: Annotated[str, typer.Argument()],
    subject: Annotated[str | None, typer.Option("--subject")] = None,
    version: Annotated[str | None, typer.Option("--version")] = None,
    when: Annotated[str | None, typer.Option("--date")] = None,
    uses: Annotated[list[str] | None, typer.Option("--uses")] = None,
    withdrawn: Annotated[bool, typer.Option("--withdrawn")] = False,
    ethics_ref: Annotated[str | None, typer.Option("--ethics-ref")] = None,
    from_file: Annotated[str | None, typer.Option("--from")] = None,
    config: Annotated[str | None, typer.Option("--config")] = None,
    role: Annotated[str | None, typer.Option("--role")] = None,
    purpose: Annotated[str | None, typer.Option("--purpose")] = None,
    approval_ref: Annotated[str | None, typer.Option("--approval-ref")] = None,
) -> None:
    """Record consent in the vault (NV-F01, CLI-08, D-10 b; p6 decisions 3-5): one record from the options or
    every record of a consents.tsv (--from), under the vault lock, with one access event consent_manage
    before consents.yaml is rewritten. Role: --role > [vault] role, none is exit 2; purpose and approval
    reference: option > [vault] > none."""
    from neurogrid.vault import consents as vault_consents
    from neurogrid.vault import roles, store

    use_list = _split_list(uses or [])
    given = [subject, version, when, ethics_ref]
    if from_file is not None and (any(value is not None for value in given) or uses or withdrawn):
        raise InputError("consent.from_with_fields")
    record = None
    if from_file is None:
        record = _consent_record(ctx, subject, version, when, use_list, withdrawn, ethics_ref)
    target = pipeline.resolve_target(path)
    if target.only is not None:
        raise InputError("vault.target_not_folder")
    _state["dataset_root"] = target.root
    loaded = config_module.load(_given_path(config), target.root)
    section = loaded.config.vault
    chosen_role = role if role is not None else section.role
    if chosen_role is None:
        raise InputError("vault.role_missing")
    roles.validate_role(chosen_role)
    chosen_purpose = purpose if purpose is not None else section.purpose
    chosen_ref = approval_ref if approval_ref is not None else section.approval_ref
    location = store.locate(loaded.project_root, section.path)
    store.require_present(location)
    # the event (consent_manage on consents.yaml) compared with the role register before it is written
    objects = [location.object_name(store.CONSENTS_FILE)]
    warning = roles.role_warning(
        roles.permission_at(location, chosen_role, vault_consents.CONSENT_ACTION, objects)
    )
    added: list[ConsentScope | vault_consents.ImportedRecord] = []
    if record is not None:
        added.append(record)
    elif from_file is not None:  # the table is read before the lock: all records or none (D-10 b)
        added.extend(vault_consents.read_consents_tsv(check_operator_path(from_file)))
    result = vault_consents.add_consents(
        location, added, role=chosen_role, purpose=chosen_purpose, approval_ref=chosen_ref
    )
    if record is not None:
        _say("cli.vault.consent.added", subject=record.subject, version=record.version)
    else:
        _say("cli.vault.consent.imported", count=len(result.records))
    future = sum(1 for item in result.records if item.date > date.today())
    if future:
        _say("cli.vault.consent.date_in_future", count=future)
    long_numbers = vault_consents.subjects_with_long_numbers(result.records)
    if long_numbers:
        _say("cli.vault.consent.subject_hint", count=long_numbers)
    if roles.role_looks_identifying(chosen_role):
        _say("cli.vault.role_looks_identifying")
    _role_warning(warning)
    _say("disclaimer")


def _vault_folder(path: str) -> None:
    """The dataset folder of a vault command, for the redaction of console paths (A-51); the pipeline checks
    it (errors.vault.target_not_folder)."""
    folder = check_operator_path(path)
    _state["dataset_root"] = folder.resolve() if folder.is_dir() else None


@vault_app.command("init", cls=_HelpCommand)
def vault_init(
    path: Annotated[str, typer.Argument()] = ".",
    config: Annotated[str | None, typer.Option("--config")] = None,
) -> None:
    """Create the missing parts of the vault (CLI-08, A-30): idempotent, no access event."""
    from neurogrid.vault.store import PIA_FILES, PIA_FOLDER, REGISTER_TEMPLATES

    _vault_folder(path)
    parts = pipeline.run_vault_init(path, _given_path(config))
    for part in parts:
        _say("cli.vault.init.created" if part.created else "cli.vault.init.kept", name=_clean(part.name))
    _say("cli.vault.init.manifest_hint")
    # the registers and the impact assessment are templates to fill in (A-93 to A-95)
    templates = {name for name, _data in REGISTER_TEMPLATES} | {f"{PIA_FOLDER}/{name}" for name in PIA_FILES}
    if any(part.created and part.name.endswith(tuple(f"/{name}" for name in templates)) for part in parts):
        _say("cli.vault.init.templates_hint")
    _say("disclaimer")


def _shown_text(value: str | None) -> str:
    """A text of a log entry on the console: cleaned, paths redacted, shortened (A-51, A-53)."""
    if value is None:
        return translator(_lang()).t("cli.vault.show.none")
    text = _redact(_clean(value))
    return text if len(text) <= MAX_PARAM_CHARS else text[: MAX_PARAM_CHARS - 1] + "…"


def _show_entry(entry: Entry) -> None:
    event = entry.event
    if event is None:
        _say("cli.vault.show.unreadable_line", line=entry.line)
        return
    _say(
        "cli.vault.show.row",
        line=entry.line,
        seq=event.seq,
        time=event.time,
        role=_shown_text(event.role),
        action=event.action,
        objects=_shown_text(", ".join(event.objects)),
        purpose=_shown_text(event.purpose),
        approval_ref=_shown_text(event.approval_ref),
    )


def _show_head(head: str | None) -> None:
    if head is None:
        _say("cli.vault.verify.head_none")
    else:
        _say("cli.vault.verify.head", hash=head)


def _vault_show(path: str, config: str | None) -> None:
    """``vault log --show`` (D-10 c): the newest entries, the earlier ones as a count, then entries, head and
    the state of the chain. Exit 0 whatever the state; writes no event."""
    run = pipeline.run_vault_show(path, _given_path(config))
    verification = run.verification
    if not verification.lines:
        _say("cli.vault.show.empty")
    else:
        _say("cli.vault.show.header")
        for entry in run.entries:
            _show_entry(entry)
        if run.earlier:
            _say("cli.vault.show.more", count=run.earlier)
    _say("cli.vault.verify.events", events=verification.events)
    _show_head(verification.head)
    if verification.intact:
        _say("cli.vault.show.summary_intact")
    else:
        _say("cli.vault.show.summary_broken", deviations=len(verification.deviations))
    _say("disclaimer")


@vault_app.command("log", cls=_HelpCommand)
def vault_log(
    path: Annotated[str, typer.Argument()] = ".",
    config: Annotated[str | None, typer.Option("--config")] = None,
    action: Annotated[str | None, typer.Option("--action")] = None,
    objects: Annotated[list[str] | None, typer.Option("--objects")] = None,
    purpose: Annotated[str | None, typer.Option("--purpose")] = None,
    approval_ref: Annotated[str | None, typer.Option("--approval-ref")] = None,
    role: Annotated[str | None, typer.Option("--role")] = None,
    show: Annotated[bool, typer.Option("--show")] = False,
) -> None:
    """Append one access event by hand (CLI-08, A-31), or show the log with --show (D-10 c)."""
    _vault_folder(path)
    given = (action, objects, purpose, approval_ref, role)
    if show:
        if any(value is not None for value in given):
            raise InputError("vault.show_exclusive")
        _vault_show(path, config)
        return
    for name, value in (("--action", action), ("--objects", objects)):
        if not value:
            raise _UsageProblem("cli.error.missing_option", name=name, command="neurogrid vault log")
    run = pipeline.run_vault_log(
        path,
        _given_path(config),
        action=str(action),
        objects=list(objects or []),  # never split at commas: they are legal in paths
        purpose=purpose,
        approval_ref=approval_ref,
        role=role,
    )
    _say("cli.vault.log.written", seq=run.event.seq, hash=run.event.hash)
    if run.identifying:
        _say("cli.vault.log.identifying")
    if run.role_identifying:
        _say("cli.vault.role_looks_identifying")
    _role_warning(run.role_warning)
    _say("disclaimer")


@vault_app.command("export", cls=_HelpCommand)
def vault_export(
    report: Annotated[list[str], typer.Option("--report")],
    out: Annotated[str, typer.Option("--out")],
    path: Annotated[str, typer.Argument()] = ".",
    manifest_file: Annotated[str | None, typer.Option("--manifest")] = None,
    show_paths: Annotated[bool, typer.Option("--show-paths")] = False,
    config: Annotated[str | None, typer.Option("--config")] = None,
    role: Annotated[str | None, typer.Option("--role")] = None,
    purpose: Annotated[str | None, typer.Option("--purpose")] = None,
    approval_ref: Annotated[str | None, typer.Option("--approval-ref")] = None,
) -> None:
    """Write the export package of the vault (NV-F07, A-30, A-96): a ZIP with the manifest, the access log,
    the role register, the impact assessment and 1 to 5 reports, plus index.json; the access event export
    comes first. Exit 0 written, 2 for every refusal (nothing written); a broken chain is exported and
    named."""
    _vault_folder(path)
    target = _output_file(out)  # a trailing separator names a folder: refused before anything is read
    run = pipeline.run_vault_export(
        path,
        _given_path(config),
        reports=[check_operator_path(item) for item in report],  # never split: a comma is part of a path
        out=target,
        manifest_path=_given_path(manifest_file),
        show_paths=show_paths,
        role=role,
        purpose=purpose,
        approval_ref=approval_ref,
    )
    index = run.result.index
    for part in index.parts:  # fixed names of the archive, never a name of the dataset (A-51)
        _say("cli.vault.export.part", file=part.file, size=part.size, sha256=part.sha256)
    _say("cli.vault.export.head", hash=index.access_log.head)
    for warning in run.result.warnings:
        _say(f"cli.vault.export.{warning}", deviations=index.access_log.deviations)
    if run.inside_dataset:
        _say("cli.vault.export.inside_dataset")
    if run.role_identifying:
        _say("cli.vault.role_looks_identifying")
    _role_warning(run.result.role_warning)
    _say("cli.vault.export.written", path=_written_path(target, plain=run.plain))
    _say("disclaimer")


def _say_deviation(deviation: Deviation) -> None:
    tr = translator(_lang()).t
    kind = tr(f"terms.access_kind.{deviation.kind}")
    if deviation.line is None:
        _say("cli.vault.verify.deviation_no_line", kind=kind)
    elif deviation.likely is None:
        _say("cli.vault.verify.deviation", line=deviation.line, kind=kind)
    else:
        likely = tr(f"terms.access_likely.{deviation.likely}")
        _say("cli.vault.verify.deviation_likely", line=deviation.line, kind=kind, likely=likely)


@vault_app.command("verify", cls=_HelpCommand)
def vault_verify(
    path: Annotated[str, typer.Argument()] = ".",
    config: Annotated[str | None, typer.Option("--config")] = None,
    expect_head: Annotated[list[str] | None, typer.Option("--expect-head")] = None,
) -> None:
    """Verify the hash chain of the access log (CLI-09, NV-F03): exit 0 intact, 1 deviation."""
    _vault_folder(path)
    verification = pipeline.run_vault_verify(path, _given_path(config), expect_head or [])
    _say("cli.vault.verify.events", events=verification.events)
    _show_head(verification.head)
    deviations = verification.deviations
    for deviation in deviations[:MAX_LISTED]:  # line numbers, kinds and likely causes, never content
        _say_deviation(deviation)
    if len(deviations) > MAX_LISTED:
        _say("cli.manifest.more", count=len(deviations) - MAX_LISTED)
    for expected in verification.expected:
        if expected.found:
            _say(
                "cli.vault.verify.expected_found",
                hash=expected.hash,
                line=expected.line,
                after=expected.events_after,
            )
        else:
            _say("cli.vault.verify.expected_missing", hash=expected.hash)
    if verification.intact:
        _say("cli.vault.verify.intact")
    else:
        _say("cli.vault.verify.differs", deviations=len(deviations))
    _say("cli.vault.verify.head_hint")
    _say("cli.vault.verify.limits")
    _say("disclaimer")
    raise typer.Exit(code=0 if verification.intact else 1)


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
    processes.avoid_wmi()  # before any library asks platform (A-51: see kernel/processes.py)
    _configure_output()
    # no state from an earlier call in-process; help and usage errors already speak the chosen language
    language, command_given = _argv_language(sys.argv[1:] if argv is None else argv)
    _state.update(lang=language, debug=False, dataset_root=None)
    warnings.showwarning = _show_warning
    code = 0
    try:
        # click expands wildcards in sys.argv on Windows; NeuroGrid takes every argument as typed, so that a
        # pattern such as 'vault log --objects "**"' arrives as on POSIX (A-14 patterns, A-73)
        rv = app(args=argv, standalone_mode=False, prog_name="neurogrid", windows_expand_args=False)
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
