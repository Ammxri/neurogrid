"""--help, usage headings and usage errors are messages in the selected language (NG-N06, A-07).

Every command, argument and option has its help text in the language tables (cli.help.*), the help follows
--lang and NEUROGRID_LANG, and a wrong command line is described by NeuroGrid's own sentence (cli.error.*),
never by the English sentence of the command-line library."""

from __future__ import annotations

import re
from typing import Any

import pytest
import typer

from neurogrid import cli
from neurogrid.cli import app, main
from neurogrid.kernel.i18n import LANGUAGES
from neurogrid.report.texts import tables, translator

HAN = re.compile("[㐀-䶿一-鿿]")
# Sentences of the command-line library that must never reach the user (A-07).
FOREIGN = (
    "Usage:",
    "Options:",
    "Arguments:",
    "Commands:",
    "Show this message",
    "Missing option",
    "Missing argument",
    "Missing parameter",
    "No such option",
    "No such command",
    "Invalid value",
    "requires an argument",
    "does not take a value",
    "Got unexpected extra",
    "[default:",
    "[required]",
    "Try '",
)


def _flat(text: str) -> str:
    """Text without white space: the help wraps long texts over several indented lines."""
    return re.sub(r"\s+", "", text)


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def _tree() -> Any:
    return typer.main.get_command(app)


def _help_keys() -> set[str]:
    """The cli.help keys the command tree needs: one per command and parameter, plus the group's options."""
    group = _tree()
    keys = {"cli.help.app", "cli.help.option.help"}
    keys |= {f"cli.help.global.{cli._param_key(p)}" for p in group.params if p.name != "help"}
    for name, command in group.commands.items():
        keys.add(f"cli.help.{name}.about")
        keys |= {f"cli.help.{name}.{cli._param_key(p)}" for p in command.params if p.name != "help"}
    return keys


def test_every_command_and_parameter_has_its_help_text() -> None:
    keys = _help_keys()
    assert len(keys) > 30
    for lang in LANGUAGES:
        missing = sorted(key for key in keys if not tables()[lang].get(key, "").strip())
        assert not missing, (lang, missing)
    assert all(HAN.search(tables()["zh"][key]) for key in keys)
    unused = sorted(
        key
        for key in tables()["en"]
        if re.fullmatch(r"cli\.help\.(app|global|scan|check|convert|report|manifest|verify)(\..+)?", key)
        and key not in keys
    )
    assert not unused, unused  # a text without a parameter is a sign of a renamed option


@pytest.mark.parametrize("command", ["scan", "check", "convert", "report", "manifest", "verify"])
def test_command_help_follows_the_language(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    zh, en = translator("zh").t, translator("en").t
    code, out, err = run(["--lang", "zh", command, "--help"], capsys)
    assert code == 0 and not err
    assert out.startswith(zh("cli.help.heading.usage") + f"neurogrid {command}")
    for key in sorted(k for k in _help_keys() if k.startswith(f"cli.help.{command}.")):
        assert _flat(zh(key)) in _flat(out), key  # every argument and option is described in Chinese
    assert zh("cli.help.heading.options") in out and zh("cli.help.option.help") in out
    assert not [s for s in FOREIGN if s in out], out
    code, out, _ = run(["--lang", "en", command, "--help"], capsys)
    assert code == 0 and _flat(en(f"cli.help.{command}.about")) in _flat(out) and not HAN.search(out)


def test_group_help_and_environment_language(capsys: pytest.CaptureFixture[str], monkeypatch: Any) -> None:
    zh = translator("zh").t
    monkeypatch.setenv("NEUROGRID_LANG", "zh")
    code, out, _ = run(["--help"], capsys)
    assert code == 0 and zh("cli.help.heading.commands") in out and zh("cli.help.check.about") in out
    assert not [s for s in FOREIGN if s in out]
    code, out, _ = run(["check", "--help"], capsys)
    assert code == 0 and _flat(zh("cli.help.check.rulepack")) in _flat(out)
    code, _, err = run([], capsys)  # no arguments: the help on stderr, exit code 2 (A-12), no error text
    assert (
        code == 2 and err.startswith(zh("cli.help.heading.usage")) and _flat(zh("cli.help.app")) in _flat(err)
    )
    # --lang wins over the environment
    code, out, _ = run(["--lang", "en", "check", "--help"], capsys)
    assert code == 0 and "Rule pack name or path" in out and not HAN.search(out)


CASES = [
    (["convert", "x"], "cli.error.missing_option", {"name": "--to", "command": "neurogrid convert"}),
    (["check"], "cli.error.missing_argument", {"name": "PATH", "command": "neurogrid check"}),
    (
        ["check", "--bogus", "x"],
        "cli.error.no_such_option",
        {"name": "--bogus", "command": "neurogrid check"},
    ),
    (
        ["check", "x", "--jobs", "abc"],
        "cli.error.bad_parameter",
        {"name": "--jobs", "command": "neurogrid check"},
    ),
    (
        ["check", "x", "--jobs", "0"],
        "cli.error.bad_parameter",
        {"name": "--jobs", "command": "neurogrid check"},
    ),
    (
        ["check", "x", "--out"],
        "cli.error.option_needs_value",
        {"name": "--out", "command": "neurogrid check"},
    ),
    (
        ["check", "x", "--strict=1"],
        "cli.error.option_takes_no_value",
        {"name": "--strict", "command": "neurogrid check"},
    ),
    (["frob"], "cli.error.no_such_command", {"name": "frob"}),
    (["scan", "a", "b"], "cli.error.extra_arguments", {"arguments": "b"}),
    ([], "cli.error.missing_command", {}),
]


@pytest.mark.parametrize("lang", ["zh", "en"])
@pytest.mark.parametrize(
    ("args", "key", "params"), CASES, ids=[c[1].rsplit(".", 1)[1] + str(i) for i, c in enumerate(CASES)]
)
def test_usage_errors_are_translated(
    lang: str, args: list[str], key: str, params: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    tr = translator(lang).t
    code, out, err = run(["--lang", lang, *args], capsys)
    expected = tr("cli.error.usage", problem=tr(key, **params))
    assert code == 2 and not out
    assert err.strip() == expected
    assert not [s for s in FOREIGN if s in err], err
    assert bool(HAN.search(err)) is (lang == "zh")


def test_usage_error_values_are_cleaned(capsys: pytest.CaptureFixture[str]) -> None:
    """A foreign value in a usage error loses its control characters and is shortened (A-53)."""
    code, _, err = run(["--lang", "zh", "check", "--bo\x1b[2Jgus" + "x" * 500, "y"], capsys)
    assert code == 2 and "\x1b" not in err and len(err) < 400
    code, _, err = run(["--lang", "zh", "fr\x07ob"], capsys)
    assert code == 2 and "\x07" not in err and "frob" in err


def test_report_lang_is_not_the_message_language(capsys: pytest.CaptureFixture[str]) -> None:
    """'report --lang' names report languages; the message language is the global --lang (A-07)."""
    code, out, _ = run(["--lang", "en", "report", "--lang", "zh", "--help"], capsys)
    assert code == 0 and "Report languages" in out and not HAN.search(out)


@pytest.mark.parametrize(
    ("text", "width", "lines"),
    [
        ("Path to neurogrid.toml (default: x).", 20, ["Path to", "neurogrid.toml", "(default: x)."]),
        ("规则包名称或路径（可重复指定）。", 12, ["规则包名称或", "路径（可重复", "指定）。"]),
        ("neurogrid.toml 的路径（默认：数据集中的 .neurogrid/neurogrid.toml）。", 30, None),
        ("结果文件。 [默认：results.json]", 12, ["结果文件。", "[默认：results.json]"]),
    ],
)
def test_help_wraps_by_terminal_columns(text: str, width: int, lines: list[str] | None) -> None:
    wrapped = cli._wrap(text, width)
    if lines is not None:
        assert wrapped == lines
    assert "".join(wrapped).replace(" ", "") == text.replace(" ", "")
    for line in wrapped:
        assert cli._cells(line) <= width or " " not in line  # only a single unit may be longer
        assert line[0] not in "。，、；：！？）" and line[-1] not in "（"
    assert cli._cells("规则") == 4 and cli._cells("ab") == 2
