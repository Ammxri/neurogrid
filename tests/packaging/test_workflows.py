"""Structure of the GitHub workflows (TECH-05, TECH-08, NG-N01, NG-N04, CON-02, V-01, D-07, D-09, D-10 g).

The workflows have not run yet (no repository URL, D-09); these tests pin what can be checked without GitHub:
triggers, pinned actions, permissions, the jobs and the commands they run, and that no job uploads datasets.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import importlib.util
import inspect
import io
import itertools
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, NoReturn
from unittest import mock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
WORKFLOWS = ROOT / ".github" / "workflows"
NAMES = ("ci", "offline", "corpus", "docs", "release", "publish-pypi", "mirror-gitee")
# Tools that the workflows call but that another P5 job is still writing, with exactly the options the
# workflows pass them: tools/acceptance_g1.py comes from the acceptance phase (corpus.yml). Every other called
# tool must be in the tree, and its real argparse parser is checked. A pending tool is checked the same way as
# soon as its file exists; test_a_pending_tool_defines_the_options_the_workflows_pass then fails while it
# lacks one of them.
PENDING = {"acceptance_g1.py": frozenset({"--corpus", "--out"})}
PINS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",  # v7.0.1
    "astral-sh/setup-uv": "07a047e608db84b3d8c06cd9a7c7dcc9c355c18e",  # v10.3.2
    "actions/upload-artifact": "cf430e030ddbb5b0abf93d22962f4752f3646cd9",  # v7.0.2
    "actions/download-artifact": "9000827ccba6bdab643e8b6fd33ac0654aef8333",  # v8.0.2
    "actions/cache": "55cc8345863c7cc4c66a329aec7e433d2d1c52a9",  # v6.1.0
    "sigstore/cosign-installer": "6f9f17788090df1f26f669e9d70d6ae9567deba6",  # v4.1.2
    "pypa/gh-action-pypi-publish": "7245906fb61fa33a13554f9d5fb856fe61758086",  # v1.14.3 (commit of the tag)
}


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((WORKFLOWS / f"{name}.yml").read_text(encoding="utf-8"))
    data["on"] = data.pop(True, data.get("on"))  # YAML 1.1 reads the key `on` as true
    return data


def _text(name: str) -> str:
    return (WORKFLOWS / f"{name}.yml").read_text(encoding="utf-8")


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = job.get("steps", [])
    return steps


def _runs(job: dict[str, Any]) -> str:
    return "\n".join(str(step.get("run", "")) for step in _steps(job))


def _all_jobs() -> list[tuple[str, str, dict[str, Any]]]:
    return [(name, job_id, job) for name in NAMES for job_id, job in _load(name)["jobs"].items()]


def test_exactly_the_planned_workflows_exist() -> None:
    assert sorted(p.stem for p in WORKFLOWS.glob("*.yml")) == sorted(NAMES)
    assert not list(WORKFLOWS.glob("*.yaml"))


def test_every_action_is_pinned_to_a_reviewed_commit() -> None:
    for name in NAMES:
        for line in _text(name).splitlines():
            match = re.search(r"uses:\s*(\S+)", line)
            if not match:
                continue
            target = match.group(1)
            if target.startswith("./.github/workflows/"):
                assert (ROOT / target).is_file(), target
                continue
            action, _, ref = target.partition("@")
            assert re.fullmatch(r"[0-9a-f]{40}", ref), (name, line)
            assert PINS.get(action) == ref, (name, action, ref)
            assert re.search(r"# v\d+\.\d+\.\d+", line), (name, line)  # the tag stays readable


def test_permissions_are_least_privilege() -> None:
    writers = {}
    for name in NAMES:
        assert _load(name)["permissions"] == {"contents": "read"}, name
    for name, job_id, job in _all_jobs():
        permissions = job.get("permissions", {})
        for scope, level in permissions.items():
            if level == "write":
                writers[(name, job_id, scope)] = True
    assert set(writers) == {
        ("release", "build", "id-token"),
        ("release", "draft", "contents"),
        ("publish-pypi", "publish", "id-token"),
    }


def test_every_job_has_a_timeout_and_no_risky_trigger() -> None:
    for name, job_id, job in _all_jobs():
        if "uses" in job:  # a reusable workflow call has its own timeouts
            continue
        assert isinstance(job.get("timeout-minutes"), int), (name, job_id)
    for name in NAMES:
        assert "pull_request_target" not in _load(name)["on"], name
        assert "pull_request_target" not in _text(name)


def test_no_secret_or_event_text_is_expanded_inside_a_script() -> None:
    for name, job_id, job in _all_jobs():
        for step in _steps(job):
            run = str(step.get("run", ""))
            assert "secrets." not in run and "github.event" not in run, (name, job_id, run[:80])
            assert "github.head_ref" not in run
    secrets = {(name, s) for name in NAMES for s in re.findall(r"secrets\.([A-Z0-9_]+)", _text(name))}
    assert secrets == {("mirror-gitee", "GITEE_SSH_KEY")}


def test_no_job_uploads_datasets_or_local_files() -> None:
    for name, job_id, job in _all_jobs():
        for step in _steps(job):
            if "upload-artifact" not in str(step.get("uses", "")):
                continue
            path = str(step["with"]["path"])
            assert ".local" not in path and "tests/fixtures" not in path and "corpus" not in path, (
                name,
                path,
            )
            assert isinstance(step["with"].get("retention-days"), int), (name, job_id)


def test_scripts_and_tools_called_by_the_workflows_exist() -> None:
    for name in NAMES:
        text = _text(name)
        for script in re.findall(r"packaging/ci/[A-Za-z0-9_.-]+", text):
            assert (ROOT / script).is_file(), (name, script)
        for tool in set(re.findall(r"tools/([A-Za-z0-9_]+\.py)", text)):
            assert (TOOLS / tool).is_file() or tool in PENDING, (name, tool)


# A call of a repository tool: tools/<name>.py (also "$root/tools/..." or tools\<name>.py in PowerShell). Its
# arguments are the words up to a pipe, a separator, a redirection or the end of the line; in bash also up to
# the ")" that closes a command substitution (PowerShell lists its arguments after the closing parenthesis).
TOOL_CALL = {
    "sh": re.compile(r"tools[/\\]([A-Za-z0-9_]+\.py)\b([^|;&>)\n]*)"),
    "ps1": re.compile(r"tools[/\\]([A-Za-z0-9_]+\.py)\b([^|;&>\n]*)"),
}
OPTION = re.compile(r"--[a-z][a-z0-9-]*")
# A bash word: quoted parts and unquoted characters together; a lone quote (the end of a quoted tool path such
# as "$root/tools/x.py") is no word.
SH_WORD = re.compile(r"""(?:"[^"]*"|'[^']*'|[^\s"'])+""")
CALLERS = [
    *sorted((ROOT / "packaging" / "ci").glob("*.sh")),
    *sorted((ROOT / "packaging" / "ci").glob("*.ps1")),
    ROOT / "packaging" / "install.sh",
    ROOT / "packaging" / "install.ps1",
]
_MODULES = itertools.count()


def _words(arguments: str, kind: str) -> list[str]:
    """The argument words of a call without their quotes; PowerShell passes an argument array, whose words
    are separated by commas and parentheses."""
    parts = re.split(r"[\s,()]+", arguments) if kind == "ps1" else SH_WORD.findall(arguments)
    return [word for word in (part.replace('"', "").replace("'", "") for part in parts) if word]


def _tool_calls(text: str, kind: str = "sh") -> list[tuple[str, list[str]]]:
    """(tool file name, argument words) of every tool call in shell text; comment lines are left out and bash
    line continuations joined."""
    calls = []
    for line in re.sub(r"\\\n\s*", " ", text).splitlines():
        if line.lstrip().startswith("#"):
            continue
        for match in TOOL_CALL[kind].finditer(line):
            calls.append((match.group(1), _words(match.group(2), kind)))
    return calls


def _options(words: list[str]) -> set[str]:
    return {word.partition("=")[0] for word in words if OPTION.fullmatch(word.partition("=")[0])}


class _Parsed(BaseException):
    """Stops a tool's main() where it parses its arguments and carries the parser it built (a BaseException,
    so that the tool's own `except SystemExit` or `except Exception` lets it through)."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        super().__init__(parser.prog)
        self.parser = parser


@functools.cache
def _parser_of(tool: Path) -> argparse.ArgumentParser | None:
    """The real argparse parser of a tool, exactly as its main() builds it: main() runs until it parses and is
    stopped there, so the tool does nothing. None for a tool that reads sys.argv without argparse."""
    if "argparse" not in tool.read_text(encoding="utf-8"):
        return None
    name = f"_workflow_tool_{next(_MODULES)}_{tool.stem}"
    spec = importlib.util.spec_from_file_location(name, tool)
    assert spec is not None and spec.loader is not None, tool
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)

    def stop(self: argparse.ArgumentParser, *args: object, **kwargs: object) -> NoReturn:
        raise _Parsed(self)

    main = module.main
    with (
        mock.patch.object(argparse.ArgumentParser, "parse_args", stop),
        mock.patch.object(argparse.ArgumentParser, "parse_known_args", stop),
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        try:
            if inspect.signature(main).parameters:
                main([])
            else:
                main()
        except _Parsed as parsed:
            return parsed.parser
    raise AssertionError(f"{tool.name}: main() returned without parsing its arguments")


def _subcommands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _positionals(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    return [
        action
        for action in parser._actions
        if not action.option_strings and not isinstance(action, argparse._SubParsersAction)
    ]


def _defined_options(parser: argparse.ArgumentParser) -> set[str]:
    """Every option of the parser and of its subcommands."""
    found = set(parser._option_string_actions)
    for sub in _subcommands(parser).values():
        found |= _defined_options(sub)
    return found


def _literal(word: str) -> bool:
    """A fixed word: no variable, expression, substitution or pattern of the calling shell or workflow."""
    return not re.search(r"[$%*?`{}()\[\]]", word)


def _call_problems(name: str, parser: argparse.ArgumentParser | None, words: list[str]) -> list[str]:
    """What the tool's own parser rejects in a call: an unknown option (also one that only another subcommand
    has, or one given before the subcommand), an unknown subcommand, and a fixed value outside the choices of
    an option or a positional argument. Values from variables are not judged, and words beyond the positional
    arguments are left alone (the tool's path can also be named by cp or in a for list)."""
    if parser is None:
        return [f"{name} takes no options: {option}" for option in sorted(_options(words))]
    problems = []
    subcommands = _subcommands(parser)
    parsers, positionals = [parser], _positionals(parser)

    def check_choice(action: argparse.Action, value: str, what: str) -> None:
        if action.choices is not None and _literal(value) and value not in action.choices:
            problems.append(f"{name}: {what} {value!r} is not one of {sorted(action.choices)}")

    index = 0
    while index < len(words):
        word = words[index]
        index += 1
        option, equals, value = word.partition("=")
        if OPTION.fullmatch(option):
            known = [p._option_string_actions[option] for p in parsers if option in p._option_string_actions]
            if not known:
                problems.append(f"{name}: unknown option {option}")
                continue
            action = known[0]
            if action.nargs == 0:
                continue
            if equals:
                check_choice(action, value, option)
                continue
            while index < len(words) and not words[index].startswith("-"):
                check_choice(action, words[index], option)
                index += 1
                if action.nargs not in ("+", "*"):
                    break
        elif subcommands:
            if not _literal(word):  # chosen at run time: the options of any subcommand
                parsers, positionals = list(subcommands.values()), []
            elif word in subcommands:
                parsers, positionals = [subcommands[word]], _positionals(subcommands[word])
            else:
                problems.append(f"{name}: unknown subcommand {word!r} (one of {sorted(subcommands)})")
                parsers, positionals = [], []
            subcommands = {}
        elif positionals:
            action = positionals[0]
            if action.nargs in (None, "?"):
                positionals = positionals[1:]
            check_choice(action, word, action.dest)
    return problems


def _command_texts() -> dict[str, tuple[str, str]]:
    texts = {f"{name}.yml/{job_id}": (_runs(job), "sh") for name, job_id, job in _all_jobs()}
    for path in CALLERS:
        texts[path.name] = (path.read_text(encoding="utf-8-sig"), path.suffix.lstrip("."))
    return texts


def test_every_option_passed_to_a_tool_exists() -> None:
    """A workflow, CI script or installer that passes a tool an option or subcommand the tool does not define
    fails on every run: release.yml once called `tools/licenses.py --release`, which no area defines (argparse
    exits 2). Every called tool in the tree is checked against its own parser (_parser_of); only a pending
    tool whose file does not exist yet is left out (PENDING)."""
    checked = 0
    problems = []
    for where, (text, kind) in _command_texts().items():
        for name, words in _tool_calls(text, kind):
            tool = TOOLS / name
            if not tool.is_file():
                assert name in PENDING, (where, name)
                continue
            problems += [f"{where}: {problem}" for problem in _call_problems(name, _parser_of(tool), words)]
            checked += 1
    assert problems == []
    assert checked >= 25, checked


def test_the_option_check_finds_an_unknown_option() -> None:
    assert _tool_calls("uv run --no-sync python tools/licenses.py --release\n") == [
        ("licenses.py", ["--release"])
    ]
    assert _call_problems("licenses.py", _parser_of(TOOLS / "licenses.py"), ["--release"]) == [
        "licenses.py: unknown option --release"
    ]
    text = (
        'uv run python tools/bundle.py build --platform "$p" \\\n  --wheel w --sign sigstore | tee log\n'
        "# python tools/bundle.py --commented-out\n"
        'packages="$(python3 "$root/tools/linux_pdf_packages.py" debian12)" --not-an-option-of-it\n'
    )
    assert _tool_calls(text) == [
        ("bundle.py", ["build", "--platform", "$p", "--wheel", "w", "--sign", "sigstore"]),
        ("linux_pdf_packages.py", ["debian12"]),
    ]
    powershell = (
        "Invoke-Native $python @('-I', (Join-Path $Prefix 'tools\\install_pdf_browser.py'), '--from-zip', $z)"
    )
    assert _tool_calls(powershell, "ps1") == [("install_pdf_browser.py", ["--from-zip", "$z"])]


@pytest.mark.parametrize(
    "words, problem",
    [
        (["build", "--platform", "$p", "--wheel", "w", "--sign", "sigstore", "--cache", "c"], None),
        (["verify", "--platform", "win_amd64", "x.zip"], "unknown option --platform"),  # only build has it
        (["--sign", "none", "build"], "unknown option --sign"),  # before the subcommand: the main parser's
        (["build", "--platform", "win32"], "--platform 'win32' is not one of ['linux_x86_64', 'win_amd64']"),
        (["build", "--sign=gpg"], "--sign 'gpg' is not one of ['none', 'sigstore']"),
        (["biuld", "--wheel", "w"], "unknown subcommand 'biuld'"),
        (["$command", "--wheel", "w"], None),  # chosen at run time: the options of any subcommand
        (["$command", "--release"], "unknown option --release"),
    ],
)
def test_the_check_reads_subcommands_and_choices_from_the_real_parser(words: list[str], problem: str) -> None:
    parser = _parser_of(TOOLS / "bundle.py")
    assert parser is not None and set(_subcommands(parser)) == {"build", "verify", "sizes", "lock"}
    found = _call_problems("bundle.py", parser, words)
    if problem is None:
        assert found == []
    else:
        assert any(problem in line for line in found), found


def test_the_check_reads_positional_choices_and_tools_without_argparse() -> None:
    corpus = _parser_of(TOOLS / "corpus.py")
    assert _call_problems("corpus.py", corpus, ["verify", "--workers", "2"]) == []
    assert _call_problems("corpus.py", corpus, ["fetchh"]) == [
        "corpus.py: command 'fetchh' is not one of ['fetch', 'lock', 'verify']"
    ]
    shell = _parser_of(TOOLS / "install_pdf_browser.py")
    assert _call_problems("install_pdf_browser.py", shell, ["--download-only", "--platform", "linux64"]) == []
    assert _call_problems("install_pdf_browser.py", shell, ["--platform", "linux32"]) == [
        "install_pdf_browser.py: --platform 'linux32' is not one of ['linux64', 'win64']"
    ]
    licenses = _parser_of(TOOLS / "licenses.py")
    assert _call_problems("licenses.py", licenses, ["--groups", "runtime", "docs"]) == []
    assert _call_problems("licenses.py", licenses, ["--groups", "runtime", "test", "--download"]) == [
        "licenses.py: --groups 'test' is not one of ['dev', 'docs', 'runtime']"
    ]
    assert _parser_of(TOOLS / "strace_check.py") is None  # reads sys.argv itself
    assert _call_problems("strace_check.py", None, ["evidence", "--verbose"]) == [
        "strace_check.py takes no options: --verbose"
    ]


def _pending_problems(tools: Path) -> list[str]:
    """The options the workflows pass to a pending tool that the tool, once its file exists in `tools`, does
    not define (with its subcommands); nothing for a tool that does not exist yet."""
    problems = []
    for name, options in sorted(PENDING.items()):
        if (tools / name).is_file():
            parser = _parser_of(tools / name)
            defined = set() if parser is None else _defined_options(parser)
            problems += [f"{name} lacks {option}" for option in sorted(options - defined)]
    return problems


def test_a_pending_tool_defines_the_options_the_workflows_pass() -> None:
    passed: dict[str, set[str]] = defaultdict(set)
    for _where, (text, kind) in _command_texts().items():
        for name, words in _tool_calls(text, kind):
            if name in PENDING:
                passed[name] |= _options(words)
    assert dict(passed) == {name: set(options) for name, options in PENDING.items()}  # the record is exact
    assert _pending_problems(TOOLS) == []


FAKE_TOOL = """import argparse


def main(argv=None):
    parser = argparse.ArgumentParser()
{arguments}
    parser.parse_args(argv)
    return 0
"""


def test_the_pending_check_fails_for_a_tool_that_lacks_the_options(tmp_path: Path) -> None:
    assert _pending_problems(tmp_path) == []  # not written yet: nothing to check
    for folder, arguments, expected in (
        ("corpus-only", ['"--corpus"'], ["acceptance_g1.py lacks --out"]),
        ("neither", ['"--datasets"'], ["acceptance_g1.py lacks --corpus", "acceptance_g1.py lacks --out"]),
        ("both", ['"--corpus", required=True', '"--out"', '"--runs", type=int'], []),
    ):
        (tmp_path / folder).mkdir()
        lines = "\n".join(f"    parser.add_argument({argument})" for argument in arguments)
        (tmp_path / folder / "acceptance_g1.py").write_text(
            FAKE_TOOL.format(arguments=lines), encoding="utf-8"
        )
        assert _pending_problems(tmp_path / folder) == expected, folder


def test_ci_matrix_and_gates() -> None:
    ci = _load("ci")
    assert set(ci["on"]) == {"push", "pull_request"} and ci["on"]["push"]["branches"] == ["dev", "main"]
    assert ci["concurrency"]["cancel-in-progress"] is True
    assert ci["env"]["NEUROGRID_REQUIRE_PDF"] == "1"
    matrix = ci["jobs"]["test"]["strategy"]["matrix"]
    assert {"windows-latest", "ubuntu-24.04"} <= set(matrix["os"]) and matrix["python"] == [
        "3.11",
        "3.12",
        "3.13",
    ]
    test = _runs(ci["jobs"]["test"])
    for command in (
        "uv sync --locked --no-build",
        "ruff check",
        "ruff format --check",
        "mypy --strict src/neurogrid/kernel",
        "mypy src/neurogrid tools",
        "pytest",
        "tools/coverage_gates.py",
        "tools/install_pdf_browser.py",
        "tools/linux_pdf_packages.py ubuntu24.04",
    ):
        assert command in test, command
    assert ci["jobs"]["powershell51"]["defaults"]["run"]["shell"] == "powershell"
    assert ci["jobs"]["pwsh"]["defaults"]["run"]["shell"] == "pwsh"
    for job in ("powershell51", "pwsh"):
        assert '--format "html,pdf"' in _runs(ci["jobs"][job])
    licences = _runs(ci["jobs"]["licenses"])
    assert "tools/licenses.py" in licences and "tools/scan_runtime_network.py" in licences
    assert "tools/check_commit_ids.py" in _runs(ci["jobs"]["traceability"])


def test_offline_workflow_runs_every_offline_proof() -> None:
    offline = _load("offline")
    assert set(offline["on"]) == {"push", "workflow_dispatch", "workflow_call"}
    # dev pushes run ci.yml only. A tag v* starts release.yml, which calls this workflow with the signed
    # bundles: a tag trigger here as well would run every clean room twice per release tag.
    assert offline["on"]["push"] == {"branches": ["main"]}
    release = _load("release")
    assert release["on"]["push"] == {"tags": ["v*"]}
    assert release["jobs"]["test"]["uses"] == "./.github/workflows/offline.yml"
    callers = [name for name in NAMES if "./.github/workflows/offline.yml" in _text(name)]
    assert callers == ["release"]
    assert offline["on"]["workflow_call"]["inputs"]["artifact"]["default"] == ""
    jobs = offline["jobs"]
    assert set(jobs) == {
        "build",
        "offline-strace",
        "cleanroom-linux",
        "glibc-refusal",
        "pdf-debian12",
        "cleanroom-windows",
    }
    build = _runs(jobs["build"])
    assert (
        "tools/build_docs.py --site-dir site" in build and "for platform in win_amd64 linux_x86_64" in build
    )
    assert "tools/bundle.py build" in build and "--sign" not in build  # development bundles are unsigned
    assert "offline_strace_linux.sh" in _runs(jobs["offline-strace"])
    images = [entry["image"] for entry in jobs["cleanroom-linux"]["strategy"]["matrix"]["include"]]
    assert images == ["debian:12-slim", "ubuntu:22.04", "ubuntu:24.04"]
    assert "--image ubuntu:18.04 --expect-refusal" in _runs(jobs["glibc-refusal"])
    assert "pdf_debian12.sh" in _runs(jobs["pdf-debian12"])
    assert "--download-only --platform linux64" in _runs(jobs["pdf-debian12"])
    shells = [entry["shell"] for entry in jobs["cleanroom-windows"]["strategy"]["matrix"]["include"]]
    assert shells == ["powershell", "pwsh"]
    windows = _runs(jobs["cleanroom-windows"])
    assert "cleanroom_windows.ps1" in windows and "-NoOsAudit" not in windows  # the CI run has the WFP audit
    for job_id, job in jobs.items():
        if job_id != "build":
            assert job["needs"] == "build" and "!cancelled()" in job["if"], job_id


def test_offline_scripts_enforce_no_network_no_python_and_strace() -> None:
    linux = (ROOT / "packaging" / "ci" / "cleanroom_linux.sh").read_text(encoding="utf-8")
    assert "--network none" in linux and "--user 1000:1000" in linux
    inside = (ROOT / "packaging" / "ci" / "cleanroom_inside.sh").read_text(encoding="utf-8")
    assert "command -v python3" in inside and "trace=connect,sendto,sendmsg" in inside
    assert "--skip-signature-check" in inside
    for needle in (
        'prefix="$room/安装 目录/neurogrid"',
        'export TMPDIR="$room/tmp"',
        "temp-left.txt",
        "BUNDLE.json python/bin/python3.12 tools/install_pdf_browser.py",
        "max_relative_install_path",
    ):
        assert needle in inside, needle
    strace = (ROOT / "packaging" / "ci" / "offline_strace_linux.sh").read_text(encoding="utf-8")
    assert "FROM debian:12-slim" in strace and "tools/strace_check.py" in strace
    windows = (ROOT / "packaging" / "ci" / "cleanroom_windows.ps1").read_text(encoding="utf-8-sig")
    for needle in ("0CCE9226-69AE-11D9-BED3-505054503030", "New-NetFirewallRule", "Id = 5156, 5157",
                   "http://127.0.0.1:9", "System32\\tar.exe", "'安装 目录\\NeuroGrid'", "temp-left.txt",
                   "max_relative_install_path", "'BUNDLE.json', 'python\\python.exe'"):  # fmt: skip
        assert needle in windows, needle


def test_release_is_started_only_by_a_tag_and_creates_a_draft() -> None:
    release = _load("release")
    assert set(release["on"]) == {"push", "workflow_dispatch"} and release["on"]["push"] == {"tags": ["v*"]}
    build = release["jobs"]["build"]
    assert build["if"] == "startsWith(github.ref, 'refs/tags/v')" and build["environment"] == "release"
    commands = _runs(build)
    for command in ("tools/release_check.py --tag", "uv lock --check", "python tools/licenses.py\n",
                    "SOURCE_DATE_EPOCH", "uv build",
                    "tools/build_docs.py --site-dir site", "tools/notices.py --download --check",
                    "--sign sigstore", "tools/bundle.py verify", "cosign sign-blob", "cosign verify-blob",
                    "sha256sum --check --strict SHA256SUMS", "--notes"):  # fmt: skip
        assert command in commands, command
    # The licence texts gate (notices.py --check exits 1 while license-gate/known_missing.toml lists a gap,
    # G1) is its own step and runs before anything is built or signed.
    steps = [str(step.get("run", "")) for step in _steps(build)]
    (texts,) = [i for i, run in enumerate(steps) if "tools/notices.py --download --check" in run]
    (building,) = [i for i, run in enumerate(steps) if "uv build" in run]
    assert texts < building and "uv build" not in steps[texts]
    assert release["jobs"]["test"]["uses"] == "./.github/workflows/offline.yml"
    assert release["jobs"]["test"]["with"] == {"artifact": "release-dist"}
    draft = _runs(release["jobs"]["draft"])
    assert "gh release create" in draft and "--draft" in draft and "--verify-tag" in draft
    assert release["jobs"]["draft"]["needs"] == ["build", "test"]


def test_pypi_upload_is_manual_trusted_publishing_of_the_signed_release() -> None:
    pypi = _load("publish-pypi")
    assert set(pypi["on"]) == {"workflow_dispatch"}
    assert pypi["on"]["workflow_dispatch"]["inputs"]["repository"]["options"] == ["testpypi", "pypi"]
    assert pypi["jobs"]["fetch"]["if"] == "startsWith(github.ref, 'refs/tags/v')"
    fetch = _runs(pypi["jobs"]["fetch"])
    assert "gh release download" in fetch and "cosign verify-blob" in fetch and "uv build" not in fetch
    assert 'test "$(wc -l < wanted)" -eq 2' in fetch
    publish = pypi["jobs"]["publish"]
    assert publish["environment"] == "${{ inputs.repository }}"
    (upload,) = [s for s in _steps(publish) if "gh-action-pypi-publish" in str(s.get("uses"))]
    assert set(upload["with"]) == {"repository-url"}  # no password or token: Trusted Publishing


def test_gitee_mirror_is_switched_off_until_the_owner_enables_it() -> None:
    mirror = _load("mirror-gitee")
    assert set(mirror["on"]) == {"workflow_dispatch", "release"} and mirror["on"]["release"] == {
        "types": ["published"]
    }
    job = mirror["jobs"]["mirror"]
    assert job["if"] == "vars.GITEE_MIRROR == 'true'" and job["environment"] == "gitee"
    run = _runs(job)
    (push,) = [line.strip() for line in run.splitlines() if line.strip().startswith("git push")]
    assert push.endswith('"refs/remotes/origin/main:refs/heads/main" "refs/tags/v*:refs/tags/v*"')
    for forbidden in ("--force", "--mirror", " -f", "dev", "+refs", "--all", "--delete"):
        assert forbidden not in push, forbidden
    assert "StrictHostKeyChecking=yes" in run and "git push" not in run.replace(push, "")
    (step,) = [s for s in _steps(job) if "env" in s]
    assert step["env"]["GITEE_SSH_KEY"] == "${{ secrets.GITEE_SSH_KEY }}"


def test_docs_and_corpus_workflows() -> None:
    docs = _load("docs")
    assert set(docs["on"]) == {"push", "pull_request", "workflow_dispatch"}
    assert docs["on"]["push"] == {"branches": ["main"]}  # dev pushes run ci.yml only
    assert "tools/build_docs.py --site-dir site" in _runs(docs["jobs"]["build"])
    assert docs["jobs"]["browser"]["strategy"]["matrix"]["os"] == ["ubuntu-24.04", "windows-latest"]
    browser = _runs(docs["jobs"]["browser"])
    for command in ("tools/linux_pdf_packages.py ubuntu24.04", "tools/install_pdf_browser.py",
                    "tools/build_docs.py --site-dir site", "pytest -m browser tests/docs"):  # fmt: skip
        assert command in browser, command
    assert docs["env"]["NEUROGRID_REQUIRE_PDF"] == "1"
    corpus = _load("corpus")
    assert set(corpus["on"]) == {"workflow_dispatch", "push"} and corpus["on"]["push"] == {
        "branches": ["main"]
    }
    job = corpus["jobs"]["g1"]
    (cache,) = [s for s in _steps(job) if "actions/cache" in str(s.get("uses"))]
    assert cache["with"] == {
        "path": ".local/corpus",
        "key": "corpus-${{ hashFiles('tools/corpus_lock.json') }}",
    }
    run = _runs(job)
    assert "tools/corpus.py verify" in run and "tools/acceptance_g1.py" in run
    uploads = [s for s in _steps(job) if "upload-artifact" in str(s.get("uses"))]
    assert [u["with"]["path"] for u in uploads] == ["acceptance-summary/"]


@pytest.mark.parametrize("name", NAMES)
def test_workflows_are_lf_utf8(name: str) -> None:
    raw = (WORKFLOWS / f"{name}.yml").read_bytes()
    assert b"\r\n" not in raw and not raw.startswith(b"\xef\xbb\xbf")
    raw.decode("utf-8")
