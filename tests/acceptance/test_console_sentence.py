"""The fixed sentence on the console of every command (REP-07, A-08 "in der Konsolen-Kurzfassung", REP-00):
scan, check, report, convert, manifest and verify, each as a real process of the ``neurogrid`` entry script
with Chinese and English messages (NEUROGRID_LANG and --lang), print it as a line of stdout at exit 0 and at
exit 1, with strict UTF-8 and nothing but translated library warnings on stderr (the console check of the G1
acceptance, tools/acceptance_g1.py)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

import acceptance_g1 as g1  # type: ignore[import-not-found]
from neurogrid.report.texts import disclaimer

FIX = Path(__file__).parent.parent / "fixtures" / "synthetic"
DOCUMENTED = FIX.parent / "documented.toml"
COMMANDS = ("scan", "check", "report", "convert", "manifest", "verify")


def _run(arguments: list[str], lang: str, cwd: Path, *, option: bool = False) -> g1.CommandRun:
    """One command as the customer runs it; ``option``: the language as --lang instead of NEUROGRID_LANG."""
    env = g1.child_environment(lang)
    if option:
        env.pop("NEUROGRID_LANG")
        arguments = ["--lang", lang, *arguments]
    done = subprocess.run(
        [str(g1.neurogrid_executable()), *arguments], cwd=cwd, env=env, capture_output=True, check=False
    )
    return g1.CommandRun(arguments[0], done.returncode, done.stdout, done.stderr, 0.0)


def _commands(work: Path) -> list[tuple[str, list[str], int]]:
    """(command, arguments, expected exit) in an order where each one finds what the earlier ones wrote:
    exit 0 for a documented recording, exit 1 for a dataset with errors and for a changed file."""
    dataset = work / "data"
    shutil.copytree(FIX / "edf_ok", dataset)
    config = ["--config", str(DOCUMENTED)]
    return [
        ("scan", ["scan", str(dataset), "--out", str(work / "scan.json")], 0),
        (
            "check",
            ["check", str(dataset), *config, "--as-of", "2026-10-11", "--out", str(work / "ok.json")],
            0,
        ),
        ("check", ["check", str(FIX / "edf_mixed"), "--out", str(work / "mixed.json")], 1),
        ("report", ["report", str(work / "ok.json"), "--lang", "zh,en", "--out", str(work / "report")], 0),
        ("convert", ["convert", str(dataset), "--to", "bids", "--out", str(work / "bids"), *config], 0),
        ("manifest", ["manifest", str(dataset), "--out", str(work / "manifest.json")], 0),
        ("verify", ["verify", str(dataset), "--manifest", str(work / "manifest.json")], 0),
        ("verify", ["verify", str(FIX / "edf_mixed"), "--manifest", str(work / "manifest.json")], 1),
    ]


def _assert_sentence(run: g1.CommandRun, lang: str, work: Path) -> None:
    lines = [line.strip() for line in run.stdout.decode("utf-8").splitlines()]
    assert disclaimer(lang) in lines, run.name
    assert disclaimer("en" if lang == "zh" else "zh") not in lines, run.name
    assert g1.check_console(run.stdout, run.stderr, lang, run.code, allowed_paths=(work,)) == [], run.name


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_every_command_prints_the_fixed_sentence(tmp_path: Path, lang: str) -> None:
    seen = set()
    for name, arguments, expected in _commands(tmp_path):
        run = _run(arguments, lang, tmp_path)
        assert run.code == expected, (name, run.stderr.decode("utf-8", "replace"))
        _assert_sentence(run, lang, tmp_path)
        seen.add(name)
    assert seen == set(COMMANDS)


def test_the_language_option_chooses_the_sentence(tmp_path: Path) -> None:
    """--lang zh without NEUROGRID_LANG, on a command at exit 0 and one at exit 1."""
    commands = _commands(tmp_path)
    for name, arguments, expected in (commands[0], commands[2]):
        run = _run(arguments, "zh", tmp_path, option=True)
        assert run.code == expected, name
        _assert_sentence(run, "zh", tmp_path)


def test_the_sentence_check_fails_without_the_sentence(tmp_path: Path) -> None:
    """The check above is not vacuous: the same console without the sentence line fails it."""
    run = _run(["scan", str(FIX / "edf_ok")], "en", tmp_path)
    assert run.code == 0
    sentence = disclaimer("en").encode("utf-8")
    stripped = b"\n".join(line for line in run.stdout.splitlines() if line.strip() != sentence)
    assert stripped != run.stdout
    assert g1.check_console(stripped, run.stderr, "en", 0) == ["stdout lacks the fixed sentence (en)"]
