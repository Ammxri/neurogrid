"""The NeuroVault commands (CLI-08, CLI-09, NV-F03; A-30, A-31, D-10; p6 decisions 5): the nested groups
'vault' and 'vault consent' and their help in the selected language, with nested help scopes."""

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
FOREIGN = (
    "Usage:",
    "Options:",
    "Commands:",
    "Show this message",
    "No such command",
    "Missing command",
    "[OPTIONS]",
)


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as info:
        main(args)
    out, err = capsys.readouterr()
    return int(info.value.code or 0), out, err


def _flat(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _walk(command: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    """Every command and group below the root with its command path."""
    found = []
    for name, child in getattr(command, "commands", {}).items():
        found.append(((*path, name), child))
        found += _walk(child, (*path, name))
    return found


def _tree_keys() -> set[str]:
    """The help keys of the whole command tree with nested scopes: cli.help.<scope>.about and
    cli.help.<scope>.<param> for every command and group (a group lists its commands by their about)."""
    keys: set[str] = set()
    for path, command in _walk(typer.main.get_command(app)):
        scope = ".".join(path)
        keys.add(f"cli.help.{scope}.about")
        keys |= {f"cli.help.{scope}.{cli._param_key(p)}" for p in command.params if p.name != "help"}
    return keys


def test_vault_groups_exist() -> None:
    root = typer.main.get_command(app)
    vault = root.commands["vault"]
    assert isinstance(vault, cli._HelpGroup)
    assert isinstance(vault.commands["consent"], cli._HelpGroup)


def test_vault_help_keys_all_languages() -> None:
    """Every command of the tree has its help texts in zh, en and de (NG-N06), Chinese in zh; no vault help
    text without a command or parameter (a sign of a renamed option)."""
    keys = _tree_keys()
    assert {"cli.help.vault.about", "cli.help.vault.consent.about"} <= keys
    for lang in LANGUAGES:
        missing = sorted(key for key in keys if not tables()[lang].get(key, "").strip())
        assert not missing, (lang, missing)
    assert all(HAN.search(tables()["zh"][key]) for key in keys)
    unused = sorted(key for key in tables()["en"] if key.startswith("cli.help.vault.") and key not in keys)
    assert not unused, unused


def test_nested_scopes_keep_vault_commands_apart_from_top_level_ones() -> None:
    """The scope is the dotted command path: 'vault verify' gets cli.help.vault.verify.*, never the keys of
    the top-level 'verify' (p6 decisions 5)."""
    root = typer.main.get_command(app)
    top = typer.Context(root, info_name="neurogrid")
    vault = typer.Context(root.commands["vault"], parent=top, info_name="vault")
    consent = typer.Context(root.commands["vault"].commands["consent"], parent=vault, info_name="consent")
    verify = typer.Context(root.commands["verify"], parent=top, info_name="verify")
    assert [cli._help_scope(ctx) for ctx in (top, vault, consent, verify)] == [
        "",
        "vault",
        "vault.consent",
        "verify",
    ]
    keys = _tree_keys()
    assert not {key for key in keys if key.startswith("cli.help.vault.verify.")} & {
        key for key in keys if key.startswith("cli.help.verify.")
    }


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_vault_help_follows_the_language(lang: str, capsys: pytest.CaptureFixture[str]) -> None:
    tr = translator(lang).t
    heading = tr("cli.help.heading.usage")
    usage = heading if heading.endswith("：") else heading + " "  # no space after a full-width colon
    code, out, err = run(["--lang", lang, "vault", "--help"], capsys)
    assert code == 0 and not err
    assert out.startswith(usage + "neurogrid vault")
    assert _flat(tr("cli.help.vault.about")) in _flat(out)
    assert "consent" in out and _flat(tr("cli.help.vault.consent.about")) in _flat(out)
    assert tr("cli.help.heading.commands") in out and tr("cli.help.option.help") in out
    code, out, err = run(["--lang", lang, "vault", "consent", "--help"], capsys)
    assert code == 0 and not err
    assert out.startswith(usage + "neurogrid vault consent")
    assert _flat(tr("cli.help.vault.consent.about")) in _flat(out)
    if lang == "zh":
        assert not [text for text in FOREIGN if text in out], out
    else:
        assert not HAN.search(out)


def test_root_help_lists_vault(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(["--lang", "zh", "--help"], capsys)
    assert code == 0 and "vault" in out
    assert _flat(translator("zh").t("cli.help.vault.about")) in _flat(out)


def test_vault_without_command_shows_help_exit2(capsys: pytest.CaptureFixture[str]) -> None:
    """Like neurogrid without a command: the help on stderr and exit code 2 (A-12)."""
    for args in (["vault"], ["vault", "consent"]):
        code, out, err = run(["--lang", "en", *args], capsys)
        assert code == 2 and not out
        assert err.startswith("Usage: neurogrid " + " ".join(args))


def test_unknown_vault_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(["--lang", "en", "vault", "bogus"], capsys)
    expected = translator("en").t("cli.error.no_such_command", name="bogus")
    assert code == 2 and translator("en").t("cli.error.usage", problem=expected) in err
