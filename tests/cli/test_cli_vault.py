"""The NeuroVault commands (CLI-08, CLI-09, NV-F03; A-30, A-31, D-10; p6 decisions 5): the nested groups
'vault' and 'vault consent' and their help in the selected language, with nested help scopes; vault init,
vault log (and --show) and vault verify with their exit codes, refusals and console texts (A-51: never entry
content in verify, pseudonymous objects), also under Windows PowerShell 5.1 and Git Bash with a Chinese
path."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import typer

from conftest import dir_link, holding_process, wait_released  # type: ignore[import-not-found]
from neurogrid import cli
from neurogrid.cli import app, main
from neurogrid.io.provenance import show
from neurogrid.kernel.i18n import LANGUAGES
from neurogrid.report.texts import tables, translator
from neurogrid.vault import ledger
from neurogrid.vault import lock as vault_lock
from neurogrid.vault.store import CONSENTS_TEMPLATE

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


# --- vault init, vault log, vault verify (CLI-08, CLI-09, NV-F03) -------------------------------------------

VAULT = Path(".neurogrid", "vault")
HOLD = """
import sys
from pathlib import Path
from neurogrid.vault.lock import exclusive
with exclusive(Path(sys.argv[1])):
    sys.stdout.write(sys.argv[1] + "\\n")
    sys.stdout.flush()
    sys.stdin.readline()
"""
ENTRY = "--action read --objects ** --purpose review --role QA".split()


def _folder(tmp_path: Path, name: str = "data") -> Path:
    """A raw folder with one file whose name looks like a person's name."""
    folder = tmp_path / name
    folder.mkdir(parents=True)
    (folder / "rec_Zhang_San.edf").write_bytes(b"not read")
    return folder


def _initialised(tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str = "data") -> Path:
    folder = _folder(tmp_path, name)
    code, _, err = run(["--lang", "en", "vault", "init", str(folder)], capsys)
    assert code == 0, err
    return folder


def _log(folder: Path) -> bytes:
    return (folder / VAULT / "access.jsonl").read_bytes()


def _events(folder: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in _log(folder).decode("utf-8").splitlines() if line.strip()]


def _entry(folder: Path, capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    return run(["--lang", "en", "vault", "log", str(folder), *args], capsys)


def _write_chain(folder: Path, count: int, **changes: Any) -> list[dict[str, Any]]:
    """An intact log of ``count`` entries written directly (fixed times)."""
    events: list[dict[str, Any]] = []
    previous = ledger.GENESIS
    for seq in range(1, count + 1):
        body = {
            "format_version": 1,
            "seq": seq,
            "time": "2026-10-29T12:00:00Z",
            "role": "QA",
            "action": "check",
            "objects": ["**"],
            "purpose": None,
            "approval_ref": None,
            "tool_version": "0.2.0",
            "previous_hash": previous,
            **changes,
        }
        body["hash"] = ledger.event_hash(body)
        events.append(body)
        previous = body["hash"]
    (folder / VAULT / "access.jsonl").write_bytes(b"".join(ledger.compact_event(e) + b"\n" for e in events))
    return events


@contextmanager
def _locked(folder: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Another process holds the vault lock; this process waits only 0.3 s for it."""
    monkeypatch.setattr(vault_lock, "LOCK_TIMEOUT_S", 0.3)
    lock = folder / VAULT / "access.jsonl.lock"
    with holding_process(HOLD, str(lock)):
        yield
    wait_released(lock)


def _t(key: str, **params: Any) -> str:
    return translator("en").t(key, **params)


def test_vault_init_creates_parts_and_is_idempotent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    code, out, _ = run(["--lang", "en", "vault", "init", str(folder)], capsys)
    names = [".neurogrid", ".neurogrid/vault"] + [
        f".neurogrid/vault/{name}" for name in ("consents.yaml", "access.jsonl", "access.jsonl.lock")
    ]
    assert code == 0 and [_t("cli.vault.init.created", name=name) in out for name in names] == [True] * 5
    assert _t("cli.vault.init.manifest_hint") in out and out.rstrip().endswith(_t("disclaimer"))
    assert (folder / VAULT / "consents.yaml").read_bytes() == CONSENTS_TEMPLATE
    assert _log(folder) == b""  # no access event: the chain starts at the genesis hash
    before = {path.name: path.read_bytes() for path in (folder / VAULT).iterdir()}
    code, out, _ = run(["--lang", "en", "vault", "init", str(folder)], capsys)
    assert code == 0 and all(_t("cli.vault.init.kept", name=name) in out for name in names)
    assert {path.name: path.read_bytes() for path in (folder / VAULT).iterdir()} == before


def test_vault_init_with_a_config_outside_the_dataset(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """[vault] path is relative to the project root, here the folder of the toml (A-66)."""
    folder = _folder(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    (project / "neurogrid.toml").write_text('[vault]\npath = "vaults/v1"\n', encoding="utf-8")
    code, out, _ = run(
        ["--lang", "en", "vault", "init", str(folder), "--config", str(project / "neurogrid.toml")], capsys
    )
    assert code == 0 and _t("cli.vault.init.created", name="vaults/v1/access.jsonl") in out
    assert (project / "vaults" / "v1" / "consents.yaml").is_file() and not (folder / ".neurogrid").exists()


def test_vault_commands_refuse_bad_targets(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _folder(tmp_path)
    for command in (["init"], ["log", "--show"], ["verify"], ["log", *ENTRY]):
        code, _, err = run(
            ["--lang", "en", "vault", command[0], str(folder / "rec_Zhang_San.edf"), *command[1:]], capsys
        )
        assert code == 2 and _t("errors.vault.target_not_folder") in err, command
        code, _, err = run(
            ["--lang", "en", "vault", command[0], str(tmp_path / "missing"), *command[1:]], capsys
        )
        assert code == 2, command
        code, _, err = run(
            ["--lang", "en", "vault", command[0], str(folder), "--config", "", *command[1:]], capsys
        )
        assert code == 2, command  # an empty --config is no default location (A-82)
    bad = folder / ".neurogrid"
    bad.mkdir()
    (bad / "neurogrid.toml").write_text('[vault]\nrole = "QA lead"\n', encoding="utf-8")
    code, _, err = run(["--lang", "en", "vault", "init", str(folder)], capsys)
    assert code == 2 and "vault.role" in err  # ROLE_PATTERN in neurogrid.toml: config.invalid
    assert not (bad / "vault").exists()


def test_vault_commands_refuse_a_link_in_the_vault_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    target = tmp_path / "elsewhere"
    target.mkdir()
    (folder / ".neurogrid").mkdir()
    dir_link(folder / ".neurogrid" / "vault", target)
    for command in (["init"], ["log", "--show"], ["verify"], ["log", *ENTRY]):
        code, _, err = run(["--lang", "en", "vault", command[0], str(folder), *command[1:]], capsys)
        assert code == 2 and _t("errors.vault.link", part="vault") in err, command
    assert not any(target.iterdir())


def test_vault_commands_refuse_a_vault_path_that_is_no_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    (folder / ".neurogrid").mkdir()
    (folder / ".neurogrid" / "vault").write_bytes(b"a file")
    for command in (["init"], ["log", "--show"], ["verify"], ["log", *ENTRY]):
        code, _, err = run(["--lang", "en", "vault", command[0], str(folder), *command[1:]], capsys)
        assert code == 2 and _t("errors.vault.not_folder") in err, command


def test_vault_log_appends(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _initialised(tmp_path, capsys)
    args = [
        "--action",
        "read",
        "--objects",
        "sub-01/**",
        "--objects",
        "a,b.edf",
        "--purpose",
        "export for review",
    ]
    code, out, _ = _entry(folder, capsys, *args, "--approval-ref", "EC-2026-17", "--role", "QA")
    (event,) = _events(folder)
    assert code == 0 and _t("cli.vault.log.written", seq=1, hash=event["hash"]) in out
    assert out.rstrip().endswith(_t("disclaimer"))
    assert event["objects"] == ["sub-01/**", "a,b.edf"]  # repeatable, never split at a comma
    assert (event["role"], event["action"], event["purpose"], event["approval_ref"]) == (
        "QA",
        "read",
        "export for review",
        "EC-2026-17",
    )
    assert event["previous_hash"] == ledger.GENESIS and event["seq"] == 1
    code, out, _ = _entry(folder, capsys, *ENTRY)
    assert code == 0 and [e["seq"] for e in _events(folder)] == [1, 2]
    assert _events(folder)[1]["previous_hash"] == event["hash"]


def test_vault_log_takes_role_purpose_and_reference_from_the_toml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _initialised(tmp_path, capsys)
    (folder / ".neurogrid" / "neurogrid.toml").write_text(
        '[vault]\nrole = "data_steward"\npurpose = "audit"\napproval_ref = "EC-1"\n', encoding="utf-8"
    )
    assert _entry(folder, capsys, "--action", "export", "--objects", "**")[0] == 0
    assert (
        _entry(folder, capsys, "--action", "read", "--objects", "**", "--role", "QA", "--purpose", "p")[0]
        == 0
    )
    first, second = _events(folder)
    assert (first["role"], first["purpose"], first["approval_ref"]) == ("data_steward", "audit", "EC-1")
    assert (second["role"], second["purpose"], second["approval_ref"]) == ("QA", "p", "EC-1")


@pytest.mark.parametrize(
    ("args", "key", "params"),
    [
        (["--action", "read", "--objects", "**", "--purpose", "p"], "errors.vault.role_missing", {}),
        (["--action", "read", "--objects", "**", "--role", "QA"], "errors.vault.purpose_missing", {}),
        (
            ["--action", "copy", "--objects", "**", "--purpose", "p", "--role", "QA"],
            "errors.vault.action_invalid",
            {"allowed": "read, check, convert, report, export, consent_manage"},
        ),
        (
            [
                "--action",
                "read",
                "--objects",
                "ok",
                "--objects",
                "../secret_Wang",
                "--purpose",
                "p",
                "--role",
                "QA",
            ],
            "errors.vault.object_invalid",
            {"index": 2},
        ),
        (
            ["--action", "read", "--objects", "C:/Users/x", "--purpose", "p", "--role", "QA"],
            "errors.vault.object_invalid",
            {"index": 1},
        ),
        (
            ["--action", "read", "--objects", "**", "--purpose", "p", "--role", "QA lead"],
            "errors.vault.role_invalid",
            {},
        ),
        (
            ["--action", "read", "--objects", "**", "--purpose", "a\x07b", "--role", "QA"],
            "errors.vault.text_invalid",
            {"field": "purpose"},
        ),
        (
            [
                "--action",
                "read",
                "--objects",
                "**",
                "--purpose",
                "p",
                "--role",
                "QA",
                "--approval-ref",
                "x" * 121,
            ],
            "errors.vault.text_invalid",
            {"field": "approval_ref"},
        ),
    ],
)
def test_vault_log_refusals_exit2_nothing_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], args: list[str], key: str, params: dict[str, Any]
) -> None:
    folder = _initialised(tmp_path, capsys)
    code, out, err = _entry(folder, capsys, *args)
    assert code == 2 and _t(key, **params) in err and _log(folder) == b""
    assert "secret_Wang" not in out + err  # the value of a refused object is never shown (A-51)


def test_vault_log_too_many_objects_and_missing_options(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _initialised(tmp_path, capsys)
    many = [part for n in range(1001) for part in ("--objects", f"f{n}")]
    code, _, err = _entry(folder, capsys, "--action", "read", *many, "--purpose", "p", "--role", "QA")
    assert code == 2 and _t("errors.vault.too_many_objects", limit=1000) in err
    for missing, args in (("--action", ["--objects", "**"]), ("--objects", ["--action", "read"])):
        code, _, err = _entry(folder, capsys, *args, "--purpose", "p", "--role", "QA")
        problem = _t("cli.error.missing_option", name=missing, command="neurogrid vault log")
        assert code == 2 and _t("cli.error.usage", problem=problem) in err
    assert _log(folder) == b""


def test_vault_log_without_vault_or_log_exit2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _folder(tmp_path)
    code, _, err = _entry(folder, capsys, *ENTRY)
    assert code == 2 and _t("errors.vault.not_found") in err and not (folder / ".neurogrid").exists()
    folder = _initialised(tmp_path, capsys, "other")
    (folder / VAULT / "access.jsonl").unlink()
    code, _, err = _entry(folder, capsys, *ENTRY)
    assert code == 2 and _t("errors.vault.log_missing") in err
    assert not (folder / VAULT / "access.jsonl").exists()  # never recreated silently


def test_vault_log_locked_exit2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _initialised(tmp_path, capsys)
    with _locked(folder, monkeypatch):
        code, _, err = _entry(folder, capsys, *ENTRY)
        assert code == 2 and _t("errors.vault.locked") in err
        code, _, err = run(["--lang", "en", "vault", "log", str(folder), "--show"], capsys)
        assert code == 2 and _t("errors.vault.locked") in err
        code, _, err = run(["--lang", "en", "vault", "verify", str(folder)], capsys)
        assert code == 2 and _t("errors.vault.locked") in err
    assert _log(folder) == b""


def test_vault_log_objects_pseudonymous_in_raw_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """NZ-09, A-51: an object naming an existing file of a raw folder is recorded by the pseudonymous file
    name verify shows; patterns, folders and paths that do not exist as given, with a note when they look
    identifying; BIDS paths and NeuroGrid's fixed names in clear."""
    folder = _initialised(tmp_path, capsys)
    objects = [
        "rec_Zhang_San.edf",
        "./rec_Zhang_San.edf",
        "Wang_Wei/**",
        "missing.edf",
        ".neurogrid/vault/consents.yaml",
    ]
    code, out, _ = _entry(
        folder,
        capsys,
        "--action",
        "read",
        *[p for o in objects for p in ("--objects", o)],
        "--purpose",
        "p",
        "--role",
        "QA",
    )
    pseudonym = show("rec_Zhang_San.edf", plain=False).file
    assert code == 0 and pseudonym.startswith("rec-") and pseudonym.endswith(".edf")
    assert _events(folder)[0]["objects"] == [
        pseudonym,
        pseudonym,
        "Wang_Wei/**",
        "missing.edf",
        ".neurogrid/vault/consents.yaml",
    ]
    assert (
        b"Zhang" not in _log(folder) and _t("cli.vault.log.identifying") in out
    )  # Wang_Wei/** looks like a name
    bids = _initialised(tmp_path, capsys, "bids")
    (bids / "dataset_description.json").write_text('{"Name": "x", "BIDSVersion": "1.11.1"}', encoding="utf-8")
    assert (
        _entry(
            bids,
            capsys,
            "--action",
            "read",
            "--objects",
            "rec_Zhang_San.edf",
            "--purpose",
            "p",
            "--role",
            "QA",
        )[0]
        == 0
    )
    assert _events(bids)[0]["objects"] == ["rec_Zhang_San.edf"]


def _objects(*objects: str) -> list[str]:
    return [
        *(p for o in objects for p in ("--objects", o)),
        "--action",
        "read",
        "--purpose",
        "p",
        "--role",
        "QA",
    ]


def test_vault_log_looks_up_the_literal_name_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """P6 review (NZ-09, A-51): an object is looked up as the literal name of a raw-folder file before it
    counts as a pattern, and as the system reads the name, so a file whose name holds glob characters is
    recorded by its pseudonymous file name, and under Windows also a name given with another case or with
    trailing dots or spaces (Windows opens the same file); a real pattern stays a pattern."""
    folder = _initialised(tmp_path, capsys)
    (folder / "ZhangSan[EEG].edf").write_bytes(b"not read")
    code, _, err = _entry(folder, capsys, *_objects("ZhangSan[EEG].edf", "*.edf", "sub-?[0-9]/**"))
    assert code == 0, err
    glob_name = show("ZhangSan[EEG].edf", plain=False).file
    assert glob_name.startswith("rec-") and glob_name.endswith(".edf")
    assert _events(folder)[-1]["objects"] == [glob_name, "*.edf", "sub-?[0-9]/**"]
    assert b"Zhang" not in _log(folder)
    if sys.platform == "win32":  # one file under several names; on POSIX they name files that do not exist
        variants = ("rec_Zhang_San.edf.", "rec_Zhang_San.edf ", "REC_ZHANG_SAN.EDF", "rec_Zhang_San.edf. .")
        code, _, err = _entry(folder, capsys, *_objects(*variants))
        assert code == 0, err
        assert _events(folder)[-1]["objects"] == [show("rec_Zhang_San.edf", plain=False).file] * 4
        assert b"Zhang" not in _log(folder)


def test_vault_log_refuses_an_object_that_names_a_link(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """P6 review (A-52, A-66): a link in the dataset is never followed, so an object that names one, or a
    file behind one, cannot be recorded by the pseudonymous name of a raw-folder file: exit 2
    errors.vault.object_link with the object's number, nothing written. A pattern through the link stays a
    pattern."""
    folder = _initialised(tmp_path, capsys)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "Li_Si.edf").write_bytes(b"not read")
    dir_link(folder / "linked", outside)
    before = _log(folder)
    for objects in (("**", "linked/Li_Si.edf"), ("**", "linked"), ("**", "linked/")):
        code, out, err = _entry(folder, capsys, *_objects(*objects))
        assert code == 2 and _t("errors.vault.object_link", index=2) in err, (objects, out, err)
        assert _log(folder) == before
    code, _, err = _entry(folder, capsys, *_objects("linked/*.edf"))
    assert code == 0, err
    assert _events(folder)[-1]["objects"] == ["linked/*.edf"]
    target = outside / "Wang_Wu.edf"
    target.write_bytes(b"not read")
    try:
        (folder / "Wang_Wu.edf").symlink_to(target)
    except OSError:
        return  # file links need extra rights on Windows; the folder link above covers the rule
    code, _, err = _entry(folder, capsys, *_objects("Wang_Wu.edf"))
    assert code == 2 and _t("errors.vault.object_link", index=1) in err
    assert b"Wang_Wu" not in _log(folder)


def test_vault_log_identifying_purpose_and_role_warn(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _initialised(tmp_path, capsys)
    code, out, _ = _entry(
        folder, capsys, "--action", "read", "--objects", "**", "--purpose", "for Wang Wei", "--role", "QA"
    )
    assert (
        code == 0
        and _t("cli.vault.log.identifying") in out
        and _t("cli.vault.role_looks_identifying") not in out
    )
    code, out, _ = _entry(
        folder, capsys, "--action", "read", "--objects", "**", "--purpose", "audit", "--role", "Wang_Wei"
    )
    assert (
        code == 0
        and _t("cli.vault.role_looks_identifying") in out
        and _t("cli.vault.log.identifying") not in out
    )
    code, out, _ = _entry(folder, capsys, *ENTRY)
    assert (
        code == 0
        and _t("cli.vault.log.identifying") not in out
        and _t("cli.vault.role_looks_identifying") not in out
    )
    assert len(_events(folder)) == 3  # recorded anyway


def test_vault_log_show(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _initialised(tmp_path, capsys)
    code, out, _ = run(["--lang", "en", "vault", "log", str(folder), "--show"], capsys)
    assert code == 0 and _t("cli.vault.show.empty") in out and _t("cli.vault.verify.head_none") in out
    for purpose in ("first", "second", "third"):
        assert (
            _entry(
                folder, capsys, "--action", "read", "--objects", "**", "--purpose", purpose, "--role", "QA"
            )[0]
            == 0
        )
    events = _events(folder)
    before = _log(folder)
    code, out, _ = run(["--lang", "en", "vault", "log", str(folder), "--show"], capsys)
    assert code == 0 and _log(folder) == before  # --show records nothing
    lines = out.splitlines()
    assert lines[0] == _t("cli.vault.show.header")
    for number, event in enumerate(events, start=1):
        row = _t(
            "cli.vault.show.row",
            line=number,
            seq=number,
            time=event["time"],
            role="QA",
            action="read",
            objects="**",
            purpose=event["purpose"],
            approval_ref="–",
        )
        assert lines[number] == row
    assert (
        _t("cli.vault.verify.events", events=3) in out
        and _t("cli.vault.verify.head", hash=events[-1]["hash"]) in out
    )
    assert _t("cli.vault.show.summary_intact") in out and out.rstrip().endswith(_t("disclaimer"))


def test_vault_log_show_marks_malformed_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _initialised(tmp_path, capsys)
    events = _write_chain(folder, 3)
    raw = _log(folder).splitlines(keepends=True)
    (folder / VAULT / "access.jsonl").write_bytes(
        raw[0] + b"{not json Secret_Name 123456}\n" + b"".join(raw[1:])
    )
    code, out, _ = run(["--lang", "en", "vault", "log", str(folder), "--show"], capsys)
    assert code == 0 and _t("cli.vault.show.unreadable_line", line=2) in out
    assert "Secret_Name" not in out and _t("cli.vault.show.summary_broken", deviations=1) in out
    assert _t("cli.vault.verify.head", hash=events[-1]["hash"]) in out


def test_vault_log_show_newest_200(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """At most the newest 200 lines, then the number of the earlier ones (A-53; --last N is not part of v0.2,
    p6 decisions 5)."""
    folder = _initialised(tmp_path, capsys)
    _write_chain(folder, 205)
    code, out, _ = run(["--lang", "en", "vault", "log", str(folder), "--show"], capsys)
    rows = [line for line in out.splitlines() if line.startswith("Line ")]
    assert (
        code == 0
        and len(rows) == 200
        and rows[0].startswith("Line 6: #6,")
        and rows[-1].startswith("Line 205:")
    )
    assert _t("cli.vault.show.more", count=5) in out and _t("cli.vault.verify.events", events=205) in out
    code, _, err = run(["--lang", "en", "vault", "log", str(folder), "--show", "--last", "5"], capsys)
    assert code == 2  # no such option


def test_vault_log_show_exclusive_with_append_options(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _initialised(tmp_path, capsys)
    for extra in (
        ["--role", "QA"],
        ["--objects", "**"],
        ["--action", "read"],
        ["--purpose", "p"],
        ["--approval-ref", "r"],
    ):
        code, _, err = run(["--lang", "en", "vault", "log", str(folder), "--show", *extra], capsys)
        assert code == 2 and _t("errors.vault.show_exclusive") in err, extra
    assert _log(folder) == b""


def test_vault_log_show_without_log_or_vault_exit2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    code, _, err = run(["--lang", "en", "vault", "log", str(folder), "--show"], capsys)
    assert code == 2 and _t("errors.vault.not_found") in err
    folder = _initialised(tmp_path, capsys, "other")
    (folder / VAULT / "access.jsonl").unlink()
    code, _, err = run(["--lang", "en", "vault", "log", str(folder), "--show"], capsys)
    assert code == 2 and _t("errors.vault.log_missing") in err


def test_vault_verify_exit_codes_0_1_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _initialised(tmp_path, capsys)
    assert run(["--lang", "en", "vault", "verify", str(folder)], capsys)[0] == 0  # an empty log is intact
    events = _write_chain(folder, 3)
    code, out, _ = run(["--lang", "en", "vault", "verify", str(folder)], capsys)
    assert code == 0 and _t("cli.vault.verify.intact") in out
    assert (
        _t("cli.vault.verify.events", events=3) in out
        and _t("cli.vault.verify.head", hash=events[-1]["hash"]) in out
    )
    raw = _log(folder).splitlines(keepends=True)
    (folder / VAULT / "access.jsonl").write_bytes(raw[0] + raw[2] + raw[1])  # reordered
    code, out, _ = run(["--lang", "en", "vault", "verify", str(folder)], capsys)
    kind, likely = _t("terms.access_kind.link_mismatch"), _t("terms.access_likely.reorder")
    assert code == 1 and _t("cli.vault.verify.deviation_likely", line=2, kind=kind, likely=likely) in out
    assert _t("cli.vault.verify.differs", deviations=2) in out
    (folder / VAULT / "access.jsonl").unlink()
    code, out, _ = run(["--lang", "en", "vault", "verify", str(folder)], capsys)
    assert (
        code == 1
        and _t("cli.vault.verify.deviation_no_line", kind=_t("terms.access_kind.log_missing")) in out
    )
    assert not (folder / VAULT / "access.jsonl").exists()
    code, _, err = run(["--lang", "en", "vault", "verify", str(folder), "--expect-head", "xyz"], capsys)
    assert code == 2 and _t("errors.vault.bad_head") in err
    code, _, err = run(["--lang", "en", "vault", "verify", str(_folder(tmp_path, "none"))], capsys)
    assert code == 2 and _t("errors.vault.not_found") in err


def test_vault_verify_expect_head(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI-09: the recorded head must still be part of the intact chain, also after later entries; only it
    shows truncation at the end (A-30)."""
    folder = _initialised(tmp_path, capsys)
    events = _write_chain(folder, 3)
    early, head = events[1]["hash"], events[2]["hash"]
    code, out, _ = run(
        ["--lang", "en", "vault", "verify", str(folder), "--expect-head", early.upper()], capsys
    )
    assert code == 0 and _t("cli.vault.verify.expected_found", hash=early, line=2, after=1) in out
    raw = _log(folder).splitlines(keepends=True)
    (folder / VAULT / "access.jsonl").write_bytes(b"".join(raw[:2]))  # the last entry cut off
    assert run(["--lang", "en", "vault", "verify", str(folder)], capsys)[0] == 0  # the limit: not detected
    code, out, _ = run(
        ["--lang", "en", "vault", "verify", str(folder), "--expect-head", early, "--expect-head", head],
        capsys,
    )
    assert code == 1 and _t("cli.vault.verify.expected_missing", hash=head) in out
    assert _t("cli.vault.verify.expected_found", hash=early, line=2, after=0) in out


def test_vault_verify_prints_head_hint_and_limits(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _initialised(tmp_path, capsys)
    _write_chain(folder, 1)
    code, out, _ = run(["--lang", "en", "vault", "verify", str(folder)], capsys)
    assert code == 0 and _t("cli.vault.verify.head_hint") in out and _t("cli.vault.verify.limits") in out
    assert (
        out.rstrip().endswith(_t("disclaimer")) and _log(folder).count(b"\n") == 1
    )  # verify records nothing
    for word in ("tamper-proof", "tamperproof"):
        assert word not in out.lower()


def test_vault_verify_never_prints_entry_content(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _initialised(tmp_path, capsys)
    _write_chain(folder, 3, purpose="Secret Purpose 123456", role="Wang_Wei", objects=["Zhang_San/**"])
    raw = _log(folder).splitlines(keepends=True)
    raw[1] = raw[1].replace(b"Secret Purpose", b"Other Purpose")
    (folder / VAULT / "access.jsonl").write_bytes(b"".join(raw) + b'{"broken": "Zhang_San"')
    code, out, err = run(["--lang", "en", "vault", "verify", str(folder)], capsys)
    assert (
        code == 1
        and _t(
            "cli.vault.verify.deviation_likely",
            line=2,
            kind=_t("terms.access_kind.hash_mismatch"),
            likely=_t("terms.access_likely.change"),
        )
        in out
    )
    assert _t("cli.vault.verify.deviation", line=4, kind=_t("terms.access_kind.malformed")) in out
    for planted in ("Secret", "Other Purpose", "123456", "Wang", "Zhang"):
        assert planted not in out + err, planted


def test_vault_commands_chinese_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _folder(tmp_path / "数据" / "受试者")
    zh = translator("zh").t
    code, out, _ = run(["--lang", "zh", "vault", "init", str(folder)], capsys)
    assert code == 0 and zh("cli.vault.init.created", name=".neurogrid/vault/access.jsonl") in out
    code, out, _ = run(["--lang", "zh", "vault", "log", str(folder), *ENTRY], capsys)
    assert code == 0 and HAN.search(out)
    code, out, _ = run(["--lang", "zh", "vault", "verify", str(folder)], capsys)
    assert code == 0 and zh("cli.vault.verify.intact") in out and zh("cli.vault.verify.limits") in out
    assert not [text for text in FOREIGN if text in out]


def _git_bash() -> str | None:
    """Git Bash on Windows (the bash.exe in System32 belongs to WSL); bash elsewhere."""
    if sys.platform != "win32":
        return shutil.which("bash")
    git = shutil.which("git")
    if git is None:
        return None
    for base in Path(git).resolve().parents[:3]:
        candidate = base / "bin" / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    return None


SHELL_FLOW = ("init", "log", "verify")
POWERSHELL_FLOW = """$py, $folder, $codes = $args[0..2]
& $py -m neurogrid --lang zh vault init $folder | Out-Null
Add-Content -Path $codes -Value "init $LASTEXITCODE"
& $py -m neurogrid --lang zh vault log $folder --action read --objects '**' --purpose 'review' --role QA `
    | Out-Null
Add-Content -Path $codes -Value "log $LASTEXITCODE"
& $py -m neurogrid --lang zh vault verify $folder | Out-Null
Add-Content -Path $codes -Value "verify $LASTEXITCODE"
"""
BASH_FLOW = """set -u
py="$1"; folder="$2"; codes="$3"
"$py" -m neurogrid --lang zh vault init "$folder" > /dev/null; echo "init $?" >> "$codes"
"$py" -m neurogrid --lang zh vault log "$folder" --action read --objects '**' --purpose review --role QA \\
    > /dev/null; echo "log $?" >> "$codes"
"$py" -m neurogrid --lang zh vault verify "$folder" > /dev/null; echo "verify $?" >> "$codes"
"""


def _codes(path: Path) -> dict[str, int]:
    pairs = (line.split() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip())
    return {name: int(code) for name, code in pairs}


def _flow_result(folder: Path, codes: Path) -> None:
    assert _codes(codes) == dict.fromkeys(SHELL_FLOW, 0)
    (event,) = _events(folder)
    assert event["objects"] == ["**"] and event["role"] == "QA"  # the shell passed '**' unexpanded


def test_vault_flow_windows_powershell_51_chinese_path(tmp_path: Path) -> None:
    powershell = shutil.which("powershell") if sys.platform == "win32" else None
    if powershell is None:
        pytest.skip("Windows PowerShell 5.1 only exists on Windows")
    folder = _folder(tmp_path / "数据集")
    script = tmp_path / "flow.ps1"
    script.write_text(POWERSHELL_FLOW, encoding="utf-8-sig")  # PowerShell 5.1 reads UTF-8 only with a BOM
    codes = tmp_path / "codes.txt"
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        + [sys.executable, str(folder), str(codes)],
        capture_output=True,
        env=dict(os.environ),
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    _flow_result(folder, codes)


def test_vault_flow_git_bash_chinese_path(tmp_path: Path) -> None:
    bash = _git_bash()
    if bash is None:
        pytest.skip("bash not available")
    folder = _folder(tmp_path / "数据集")
    codes = tmp_path / "codes.txt"
    posix = [Path(p).as_posix() for p in (sys.executable, str(folder), str(codes))]
    result = subprocess.run(
        [bash, "-c", BASH_FLOW, "flow", *posix], capture_output=True, env=dict(os.environ), check=False
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    _flow_result(folder, codes)
