"""CI integration (V-03, UF-02, CON-02; A-34, A-98, D-10 h): the composite GitHub Action action.yml and the
GitLab template ci-templates/gitlab-ci.yml.

GitHub runs the action only after a push (D-09, .github/workflows/ci-integration.yml); here its steps run as
GitHub's runner runs them: each script written to a file and started with the runner's command line for bash
(`bash --noprofile --norc -eo pipefail`) or Windows PowerShell 5.1 (`powershell -command ". '<file>'"`, with
the runner's first and last line), the env of the step evaluated from the inputs, runner.environment and the
outputs of earlier steps, the outputs read from GITHUB_OUTPUT, and the run stopped at the first failing step.
The GitLab template is checked the same way, with its variables as the environment; it has not run on GitLab.
Inputs reach the scripts only through env, the guard refuses every runner that is not self-hosted unless
allow-hosted-runner is true, and nothing is uploaded."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import documented_config  # type: ignore[import-not-found]
from neurogrid.kernel.safety import load_yaml
from neurogrid.model.diff import DiffResult
from neurogrid.model.results import Results

ROOT = Path(__file__).resolve().parents[2]
ACTION = ROOT / "action.yml"
TEMPLATE = ROOT / "ci-templates" / "gitlab-ci.yml"
FIX = ROOT / "tests" / "fixtures" / "synthetic"
INPUTS = {
    "path": None,  # required
    "rulepacks": "",
    "config": "",
    "out": "neurogrid-results/results.json",
    "strict": "false",
    "role": "",
    "report-formats": "html",
    "report-lang": "zh,en",
    "baseline": "",
    "fail-on": "errors",
    "neurogrid": "neurogrid",
    "allow-hosted-runner": "false",
}
# The GitLab variable of each input (the template has no flag for hosted runners: it runs by its tag).
VARIABLES = {
    name: "NEUROGRID_" + name.upper().replace("-", "_") for name in INPUTS if name != "allow-hosted-runner"
}
VARIABLES["neurogrid"] = "NEUROGRID_COMMAND"
VARIANTS = {"bash": "runner.os != 'Windows'", "powershell": "runner.os == 'Windows'"}
# What an upload or a download would need; none of it in a script of the action or the template (CON-02).
NETWORK_WORDS = (
    "upload",
    "curl",
    "wget",
    "Invoke-WebRequest",
    "Invoke-RestMethod",
    "Start-BitsTransfer",
    "WebClient",
    "scp ",
    "rsync",
    "git push",
    "gh ",
    "http://",
    "https://",
    "ssh ",
    "ftp",
)


def _action() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    return data


def _template() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    return data


def _steps() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = _action()["runs"]["steps"]
    return steps


# --- the runner -------------------------------------------------------------------------------------------

# The only expressions action.yml uses (test_expressions_have_the_forms_the_runner_evaluates).
TERM = re.compile(r"inputs\.([a-z-]+)|runner\.environment|steps\.([a-z-]+)\.outputs\.([a-z-]+)")


def _shell(variant: str) -> str | None:
    """bash: Git Bash on Windows (the bash.exe in System32 belongs to WSL), bash elsewhere; powershell:
    Windows PowerShell 5.1, which exists on Windows only."""
    if variant == "powershell":
        return shutil.which("powershell") if sys.platform == "win32" else None
    if sys.platform != "win32":
        return shutil.which("bash")
    git = shutil.which("git")
    for base in Path(git).resolve().parents[:3] if git else []:
        candidate = base / "bin" / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _path(path: Path, variant: str) -> str:
    """A path as the variant's scripts get it: Git Bash takes C:/... (a backslash is an escape in bash)."""
    return path.as_posix() if variant == "bash" else str(path)


def _launcher(variant: str) -> str:
    """The installed neurogrid launcher of this environment (the input `neurogrid`)."""
    folder = Path(sys.executable).parent
    found = folder / ("neurogrid.exe" if sys.platform == "win32" else "neurogrid")
    assert found.is_file(), found
    return _path(found, variant)


def _evaluate(value: object, context: dict[str, Any]) -> str:
    text = str(value)
    match = re.fullmatch(r"\$\{\{\s*(.+?)\s*\}\}", text)
    if match is None:
        assert "${{" not in text, text
        return text
    for term in match.group(1).split(" || "):
        found = TERM.fullmatch(term.strip())
        assert found is not None, term
        if found.group(1):
            result = context["inputs"][found.group(1)]
        elif found.group(2):
            result = context["steps"].get(found.group(2), {}).get(found.group(3), "")
        else:
            result = context["environment"]
        if result:
            return str(result)
    return ""


def _script(run: str, variant: str, folder: Path, name: str) -> list[str]:
    """The script file and command line of GitHub's runner for a run step (runner defaults for bash and
    powershell; PowerShell gets the runner's first and last line around the script)."""
    if variant == "bash":
        path = folder / f"{name}.sh"
        path.write_bytes(run.encode("utf-8"))
        return [_shell("bash") or "bash", "--noprofile", "--norc", "-eo", "pipefail", path.as_posix()]
    path = folder / f"{name}.ps1"
    wrapped = (
        "$ErrorActionPreference = 'stop'\n"
        + run
        + "\nif ((Test-Path -LiteralPath variable:\\LASTEXITCODE)) { exit $LASTEXITCODE }\n"
    )
    path.write_bytes(wrapped.encode("utf-8"))  # without BOM: the scripts must be ASCII (test below)
    return [_shell("powershell") or "powershell", "-command", f". '{path}'"]


@dataclass
class ActionRun:
    code: int  # exit code of the first failing step, else 0
    steps: list[str]  # ids of the steps that ran
    outputs: dict[str, str]  # the action's outputs
    stdout: str
    stderr: str
    step_outputs: dict[str, dict[str, str]] = field(default_factory=dict)


def run_action(
    variant: str, workspace: Path, inputs: dict[str, str], environment: str = "self-hosted", only: str = ""
) -> ActionRun:
    """Run the action's steps of one variant in ``workspace`` like GitHub's runner; ``only`` limits the run
    to the steps whose id starts with it."""
    given = {name: default for name, default in INPUTS.items() if default is not None}
    given.update(inputs)
    context: dict[str, Any] = {"inputs": given, "environment": environment, "steps": {}}
    scratch = workspace.parent / f"runner-{variant}"
    scratch.mkdir(exist_ok=True)
    ran, out, err = [], [], []
    code = 0
    for index, step in enumerate(_steps()):
        if step["if"] != VARIANTS[variant] or not step["id"].startswith(only):
            continue
        output = scratch / f"output-{index}.txt"
        output.write_bytes(b"")
        env = dict(os.environ)
        env["GITHUB_OUTPUT"] = _path(output, variant)
        env.update({name: _evaluate(value, context) for name, value in step.get("env", {}).items()})
        command = _script(step["run"], variant, scratch, step["id"])
        result = subprocess.run(
            command, cwd=workspace, env=env, capture_output=True, check=False, timeout=600
        )
        ran.append(step["id"])
        out.append(result.stdout.decode("utf-8", "replace"))
        err.append(result.stderr.decode("utf-8", "replace"))
        lines = output.read_bytes().decode("utf-8").splitlines()
        context["steps"][step["id"]] = dict(line.split("=", 1) for line in lines if line)
        if result.returncode != 0:
            code = result.returncode
            break
    outputs = {name: _evaluate(spec["value"], context) for name, spec in _action()["outputs"].items()}
    return ActionRun(code, ran, outputs, "".join(out), "".join(err), context["steps"])


@pytest.fixture(params=["bash", "powershell"])
def variant(request: pytest.FixtureRequest) -> str:
    if _shell(request.param) is None:
        pytest.skip(f"{request.param} not available here (Windows PowerShell 5.1 exists on Windows only)")
    return str(request.param)


# A rule pack of one's own: the consent rule, not applicable on edf_ok (no use is needed), so it changes no
# exit code; its path holds a comma (A-73: rule packs are never split at commas).
LAB_PACK = """rulepack: lab
version: "1"
source: "Lab consent rule"
source_status: final
rules:
  - id: LAB-ACC-001
    clause: "LAB-9"
    title_zh: 用途在知情同意范围内
    title_en: Use covered by consent
    phase: access
    check: consent.covered
    severity: error
    verification: automatic
"""
RULEPACKS = "core\n\npacks/lab,pack.yaml\n"


def _workspace(tmp_path: Path) -> Path:
    """A workspace with a copy of the synthetic dataset edf_ok, its neurogrid.toml and the pack LAB_PACK."""
    workspace = tmp_path / "workspace"
    shutil.copytree(FIX / "edf_ok", workspace / "data" / "edf_ok")
    documented_config(workspace, name="neurogrid.toml")
    (workspace / "packs").mkdir()
    (workspace / "packs" / "lab,pack.yaml").write_text(LAB_PACK, encoding="utf-8")
    return workspace


def _texts(step_id: str, prefix: str) -> list[str]:
    (step,) = [s for s in _steps() if s["id"] == step_id]
    return [str(value) for name, value in step["env"].items() if name.startswith(prefix)]


# --- the action file ---------------------------------------------------------------------------------------


def test_inputs_outputs_and_their_defaults() -> None:
    """A-98: the inputs with their defaults (path required) and the outputs exit-code, diff-exit-code and
    results; a composite action that installs nothing."""
    action = _action()
    inputs = action["inputs"]
    assert list(inputs) == list(INPUTS)
    for name, default in INPUTS.items():
        assert inputs[name].get("required", False) is (default is None), name
        assert inputs[name].get("default") == default, name
        assert inputs[name]["description"].strip(), name
    assert set(action["outputs"]) == {"exit-code", "diff-exit-code", "results"}
    assert action["runs"]["using"] == "composite"
    assert [step["id"].rsplit("-", 1)[0] for step in _steps()][::2] == [
        "guard",
        "check",
        "report",
        "diff",
        "verdict",
    ]


def test_inputs_reach_the_scripts_only_through_env() -> None:
    """The script-injection rule of test_workflows: no expression inside a script; each input is an env value
    of its own (`${{ inputs.<name> }}`) of the steps that need it. Every step exists for bash (not Windows)
    and for Windows PowerShell (Windows) with the same name, env and texts; the scripts are ASCII, so that
    PowerShell 5.1 reads them in any code page (the Chinese texts come through env)."""
    steps = _steps()
    used = set()
    for step in steps:
        assert set(step) == {"name", "id", "if", "shell", "env", "run"}, step["id"]
        assert "${{" not in step["run"] and "inputs." not in step["run"], step["id"]
        assert step["run"].isascii(), step["id"]
        for name, value in step["env"].items():
            assert name.startswith("NG_"), name
            found = re.fullmatch(r"\$\{\{ inputs\.([a-z-]+) \}\}", str(value))
            if found:
                used.add(found.group(1))
                assert name == "NG_" + found.group(1).upper().replace("-", "_"), name
    assert used == set(INPUTS)
    for bash, powershell in zip(steps[::2], steps[1::2], strict=True):
        assert bash["id"].removesuffix("-bash") == powershell["id"].removesuffix("-powershell")
        assert (bash["shell"], bash["if"]) == ("bash", VARIANTS["bash"])
        assert (powershell["shell"], powershell["if"]) == ("powershell", VARIANTS["powershell"])
        assert bash["name"] == powershell["name"]
        compared = []
        for variant, step in (("bash", bash), ("powershell", powershell)):
            values = dict(step["env"])
            for name, value in values.items():  # the outputs of a step come from its own variant
                if "steps." in str(value):
                    assert f"-{variant}.outputs." in str(value), (variant, name)
                    values[name] = str(value).replace(f"-{variant}.", "-*.")
            compared.append(values)
        assert compared[0] == compared[1], bash["id"]


def test_expressions_have_the_forms_the_runner_evaluates() -> None:
    text = ACTION.read_text(encoding="utf-8")
    for expression in re.findall(r"\$\{\{\s*(.+?)\s*\}\}", text):
        for term in expression.split(" || "):
            assert TERM.fullmatch(term.strip()), expression
    raw = ACTION.read_bytes()
    assert b"\r\n" not in raw and not raw.startswith(b"\xef\xbb\xbf")


def test_nothing_is_uploaded_by_the_action_or_the_template() -> None:
    """CON-02, A-34: no step uses another action (no upload-artifact), no script names a transfer, and the
    GitLab template has no artifacts section; its commented example carries the warning in zh and en, and the
    action's last step says in zh and en that nothing was uploaded."""
    assert all("uses" not in step for step in _steps())
    scripts = [step["run"] for step in _steps()] + _template_scripts()
    for script in scripts:
        for word in NETWORK_WORDS:
            assert word.lower() not in script.lower(), word
    for name, job in _template().items():
        assert "artifacts" not in job, name
    text = TEMPLATE.read_text(encoding="utf-8")
    assert (
        "  # artifacts:  # uploads to the GitLab server: only for results without data of real persons\n"
        in text
    )
    assert "制品" in text and "GitLab 服务器" in text  # the warning in zh
    note = _texts("verdict-bash", "NG_TEXT_NOTE")
    assert len(note) == 2 and "上传" in note[0] and "uploads nothing" in note[1]


def _forbidden() -> list[re.Pattern[str]]:
    wording = ROOT / "src" / "neurogrid" / "report" / "wording"
    lists = load_yaml((wording / "forbidden.yaml").read_text(encoding="utf-8"))
    statements = load_yaml((wording / "statements.yaml").read_text(encoding="utf-8"))
    assert isinstance(lists, dict) and isinstance(statements, dict)
    patterns = [p for lang, group in lists.items() if lang != "allowed" for p in group]
    patterns += [
        p for group in ("patient", "law_article") for lang in statements[group].values() for p in lang
    ]
    return [re.compile(p) for p in patterns]


@pytest.mark.parametrize("path", [ACTION, TEMPLATE], ids=lambda p: p.name)
def test_texts_make_no_claim(path: Path) -> None:
    """POS-01, ARC-05, A-57: the wording lists of the report apply to the texts of the action and the
    template."""
    text = path.read_text(encoding="utf-8")
    assert not [p.pattern for p in _forbidden() if p.search(text)]


# --- the guard (A-34) ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("environment", ["github-hosted", "self-hosted", ""])
@pytest.mark.parametrize("allow", ["false", "true"])
def test_guard_refuses_every_runner_that_is_not_self_hosted(
    variant: str, tmp_path: Path, environment: str, allow: str
) -> None:
    """Only `self-hosted` passes without allow-hosted-runner; an empty or unknown value is refused as well
    (fail-safe). The refusal names both languages and exits 1 before NeuroGrid runs."""
    workspace = _workspace(tmp_path)
    inputs = {"path": "data/edf_ok", "neurogrid": _launcher(variant), "allow-hosted-runner": allow}
    run = run_action(variant, workspace, inputs, environment, only="guard")
    refused = environment != "self-hosted" and allow != "true"
    assert run.code == (1 if refused else 0), run.stdout + run.stderr
    zh, en = _texts(f"guard-{variant}", "NG_TEXT_REFUSED")
    assert (f"::error title=NeuroGrid::{zh}" in run.stdout) is refused
    assert (f"::error title=NeuroGrid::{en}" in run.stdout) is refused
    hosted = environment != "self-hosted" and allow == "true"
    assert (_texts(f"guard-{variant}", "NG_TEXT_HOSTED")[0] in run.stdout) is hosted
    if refused:  # nothing ran: the whole action stops at the guard
        whole = run_action(variant, workspace, inputs, environment)
        assert (whole.code, whole.steps, whole.outputs["exit-code"]) == (1, [f"guard-{variant}"], "")
        assert not (workspace / "neurogrid-results").exists()


@pytest.mark.parametrize(
    ("change", "name"),
    [
        ({"path": ""}, "path"),
        ({"out": ""}, "out"),
        ({"out": "a\nb.json"}, "out"),
        ({"strict": "yes"}, "strict"),
        ({"fail-on": "warnings"}, "fail-on"),
        ({"fail-on": "new-errors"}, "fail-on (new-errors needs baseline)"),
        ({"neurogrid": "no-such-neurogrid-launcher"}, "neurogrid"),
    ],
)
def test_guard_checks_the_inputs(variant: str, tmp_path: Path, change: dict[str, str], name: str) -> None:
    workspace = _workspace(tmp_path)
    inputs = {"path": "data/edf_ok", "neurogrid": _launcher(variant), **change}
    run = run_action(variant, workspace, inputs, only="guard")
    zh, en = _texts(f"guard-{variant}", "NG_TEXT_INVALID")
    # `powershell -command ". '<file>'"`, the runner's command line, ends with 1 for every exit code but 0
    assert run.code == (2 if variant == "bash" else 1), run.stdout + run.stderr
    assert f"{zh} {name}" in run.stdout and f"{en} {name}" in run.stdout


# --- the verdict (fail-on) ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fail_on", "check", "diff", "code"),
    [
        ("errors", "0", "", 0),
        ("errors", "1", "", 1),
        ("errors", "0", "1", 0),
        ("new-errors", "1", "0", 0),
        ("new-errors", "0", "1", 1),
        ("never", "1", "1", 0),
    ],
)
def test_verdict_follows_fail_on(
    variant: str, tmp_path: Path, fail_on: str, check: str, diff: str, code: int
) -> None:
    (step,) = [s for s in _steps() if s["id"] == f"verdict-{variant}"]
    env = dict(os.environ)
    env.update({name: str(value) for name, value in step["env"].items() if name.startswith("NG_TEXT_")})
    env.update({"NG_FAIL_ON": fail_on, "NG_CHECK_EXIT": check, "NG_DIFF_EXIT": diff})
    env = {name: value for name, value in env.items() if value != ""}  # as an unset step output
    result = subprocess.run(
        _script(step["run"], variant, tmp_path, "verdict"),
        env=env,
        capture_output=True,
        check=False,
        timeout=120,
    )
    stdout = result.stdout.decode("utf-8")
    assert result.returncode == code, stdout
    zh, en = _texts(step["id"], "NG_TEXT_NOTE")
    assert stdout.startswith(f"{zh}\n{en}\n")  # the note comes first, whatever the verdict
    failed = {"errors": "NG_TEXT_ERRORS_", "new-errors": "NG_TEXT_NEW_ERRORS_"}.get(fail_on)
    if failed is not None:
        for text in _texts(step["id"], failed):
            assert (f"::error title=NeuroGrid::{text}" in stdout) is bool(code)


# --- the whole action on synthetic data ---------------------------------------------------------------------


def test_action_checks_reports_and_compares(variant: str, tmp_path: Path) -> None:
    """A self-hosted run: check with the rule packs of a newline list (one path holds a comma), no report and
    no diff; then a strict run against that baseline with the HTML reports and diff.json: CORE-M13-01 becomes
    an error, so check and diff exit 1, and the step fails by fail-on only (errors, the default, or
    new-errors; never lets it pass)."""
    workspace = _workspace(tmp_path)
    common = {
        "path": "data/edf_ok",
        "config": "neurogrid.toml",
        "rulepacks": RULEPACKS,
        "neurogrid": _launcher(variant),
    }
    run = run_action(variant, workspace, {**common, "out": "baseline/results.json", "report-formats": "none"})
    assert run.code == 0, run.stdout + run.stderr
    assert run.outputs == {"exit-code": "0", "diff-exit-code": "", "results": "baseline/results.json"}
    assert len(run.steps) == 5
    baseline = Results.model_validate_json((workspace / "baseline" / "results.json").read_bytes())
    assert [pack.name for pack in baseline.rulepacks] == ["core", "lab"]  # the comma path is one pack
    assert sorted(p.name for p in (workspace / "baseline").iterdir()) == ["results.json"]
    note_zh, note_en = _texts(f"verdict-{variant}", "NG_TEXT_NOTE")
    assert note_zh in run.stdout and note_en in run.stdout

    strict = {**common, "strict": "true", "baseline": "baseline/results.json"}
    run = run_action(variant, workspace, {**strict, "fail-on": "never"})
    assert run.code == 0, run.stdout + run.stderr
    expected = {"exit-code": "1", "diff-exit-code": "1", "results": "neurogrid-results/results.json"}
    assert run.outputs == expected
    written = sorted(p.name for p in (workspace / "neurogrid-results").iterdir())
    assert written == ["diff.json", "report.en.html", "report.zh.html", "results.json"]
    compared = DiffResult.model_validate_json((workspace / "neurogrid-results" / "diff.json").read_bytes())
    assert (compared.summary.changed, compared.summary.exit_code) == (1, 1)
    for fail_on in ("errors", "new-errors"):
        run = run_action(variant, workspace, {**strict, "fail-on": fail_on, "report-formats": "none"})
        assert run.code == 1 and run.steps[-1] == f"verdict-{variant}", run.stdout + run.stderr
        assert run.outputs == expected and note_en in run.stdout


# --- the GitLab template (not run on GitLab: not verified) -------------------------------------------------


def _template_scripts() -> list[str]:
    return ["\n".join(job["script"]) for job in _template().values()]


def test_gitlab_template_structure() -> None:
    """D-10 h, A-98: two hidden jobs, sh and PowerShell, with the same variables (the second extends the
    first); only a runner with the tag in NEUROGRID_RUNNER_TAG takes the job; no artifacts; the defaults
    are the action's."""
    template = _template()
    assert list(template) == [".neurogrid", ".neurogrid-powershell"]
    job, powershell = template[".neurogrid"], template[".neurogrid-powershell"]
    assert job["tags"] == ["$NEUROGRID_RUNNER_TAG"]
    assert powershell == {"extends": ".neurogrid", "script": powershell["script"]}
    variables = job["variables"]
    assert "NEUROGRID_RUNNER_TAG" not in variables  # required: no default could pick a runner
    for name, variable in VARIABLES.items():
        default = INPUTS[name]
        assert variables[variable] == ("" if default is None else default), variable
    texts = {name for name in variables if name.startswith("NEUROGRID_TEXT_")}
    assert set(variables) == set(VARIABLES.values()) | texts
    assert {name.rsplit("_", 1)[0] for name in texts} == {
        f"NEUROGRID_TEXT_{kind}" for kind in ("UNSET", "INVALID", "NOTE", "FAILED")
    }
    assert all(name.endswith(("_ZH", "_EN")) for name in texts)
    for script in _template_scripts():
        assert script.isascii()  # the Chinese texts come through the variables (PowerShell 5.1)
        for variable in VARIABLES.values():
            assert variable in script, variable
    raw = TEMPLATE.read_bytes()
    assert b"\r\n" not in raw and not raw.startswith(b"\xef\xbb\xbf")
    assert raw.decode("utf-8").startswith("# NeuroGrid GitLab CI template")
    assert "Not run on GitLab yet: not verified." in raw.decode("utf-8")


def _gitlab_shell(kind: str) -> list[str] | None:
    """sh in POSIX mode (Git Bash's sh on Windows) or Windows PowerShell 5.1."""
    if kind == "powershell":
        found = _shell("powershell")
        return (
            None
            if found is None
            else [found, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File"]
        )
    bash = _shell("bash")
    if bash is None:
        return None
    sh = Path(bash).with_name("sh.exe" if sys.platform == "win32" else "sh")
    return [str(sh) if sh.is_file() else "sh", "-e"]


def run_template(kind: str, workspace: Path, variables: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
    """The script of a hidden job with the job's variables and the given ones as the environment (an empty
    variable stays an empty environment variable), as a GitLab runner runs it: sh with -e, PowerShell from a
    file with BOM (how the runner encodes it is not verified)."""
    template = _template()
    script = "\n".join(template[".neurogrid-powershell" if kind == "powershell" else ".neurogrid"]["script"])
    env = dict(os.environ)
    env.update({name: str(value) for name, value in template[".neurogrid"]["variables"].items()})
    env.update(variables)
    command = _gitlab_shell(kind)
    assert command is not None
    if kind == "powershell":
        path = workspace.parent / "gitlab.ps1"
        path.write_bytes(b"\xef\xbb\xbf" + script.encode("utf-8"))
        command.append(str(path))
    else:
        path = workspace.parent / "gitlab.sh"
        path.write_bytes(script.encode("utf-8"))
        command.append(path.as_posix())
    return subprocess.run(command, cwd=workspace, env=env, capture_output=True, check=False, timeout=600)


@pytest.fixture(params=["sh", "powershell"])
def gitlab_shell(request: pytest.FixtureRequest) -> str:
    if _gitlab_shell(request.param) is None:
        pytest.skip(f"{request.param} not available here")
    return str(request.param)


def test_gitlab_template_script_runs(gitlab_shell: str, tmp_path: Path) -> None:
    """The script stops without the runner tag or with an invalid NEUROGRID_FAIL_ON (exit 2), then checks,
    reports and compares as the action does; the job fails by NEUROGRID_FAIL_ON only."""
    variant = "powershell" if gitlab_shell == "powershell" else "bash"
    workspace = _workspace(tmp_path)
    texts = _template()[".neurogrid"]["variables"]
    stopped = run_template(gitlab_shell, workspace, {"NEUROGRID_PATH": "data/edf_ok"})  # no runner tag
    message = stopped.stderr.decode("utf-8")
    assert stopped.returncode == 2, message
    assert texts["NEUROGRID_TEXT_UNSET_ZH"] in message and texts["NEUROGRID_TEXT_UNSET_EN"] in message
    common = {
        "NEUROGRID_RUNNER_TAG": "neurogrid",
        "NEUROGRID_PATH": "data/edf_ok",
        "NEUROGRID_CONFIG": "neurogrid.toml",
        "NEUROGRID_RULEPACKS": RULEPACKS.replace("\n", "\r\n"),  # a variable typed on Windows
        "NEUROGRID_COMMAND": _launcher(variant),
    }
    invalid = run_template(gitlab_shell, workspace, {**common, "NEUROGRID_FAIL_ON": "new-errors"})
    assert invalid.returncode == 2 and texts["NEUROGRID_TEXT_INVALID_EN"] in invalid.stderr.decode("utf-8")
    first = {**common, "NEUROGRID_OUT": "baseline/results.json", "NEUROGRID_REPORT_FORMATS": "none"}
    result = run_template(gitlab_shell, workspace, first)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    baseline = Results.model_validate_json((workspace / "baseline" / "results.json").read_bytes())
    assert [pack.name for pack in baseline.rulepacks] == ["core", "lab"]
    assert texts["NEUROGRID_TEXT_NOTE_ZH"] in result.stderr.decode("utf-8")
    strict = {**common, "NEUROGRID_STRICT": "true", "NEUROGRID_BASELINE": "baseline/results.json"}
    result = run_template(gitlab_shell, workspace, {**strict, "NEUROGRID_FAIL_ON": "never"})
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    written = sorted(p.name for p in (workspace / "neurogrid-results").iterdir())
    assert written == ["diff.json", "report.en.html", "report.zh.html", "results.json"]
    for fail_on in ("errors", "new-errors"):
        failing = {**strict, "NEUROGRID_FAIL_ON": fail_on, "NEUROGRID_REPORT_FORMATS": "none"}
        result = run_template(gitlab_shell, workspace, failing)
        assert result.returncode == 1 and texts["NEUROGRID_TEXT_FAILED_EN"] in result.stderr.decode("utf-8")


# --- the documentation (docs/<lang>/ci.md) ---------------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_ci_page_shows_the_template_and_the_inputs(lang: str) -> None:
    """The offline bundle carries the documentation, not ci-templates/ (A-98): the CI page shows the GitLab
    template byte for byte, every input of the action with its default and every output; its example workflow
    uses inputs of the action only."""
    text = (ROOT / "docs" / lang / "ci.md").read_text(encoding="utf-8")
    (block,) = re.findall(r"<!-- example: gitlab-ci.yml -->\n```yaml\n(.*?)```\n", text, flags=re.S)
    assert block == TEMPLATE.read_text(encoding="utf-8")
    rows = dict(re.findall(r"^\| `([a-z-]+)` \| (–|`[^`]*`) \|", text, flags=re.M))
    assert rows == {name: f"`{default}`" if default else "–" for name, default in INPUTS.items()}
    for output in _action()["outputs"]:
        assert f"| `{output}` |" in text, output
    (example,) = re.findall(r"<!-- example: workflow -->\n```yaml\n(.*?)```\n", text, flags=re.S)
    (step,) = [s for s in yaml.safe_load(example)["jobs"]["neurogrid"]["steps"] if "with" in s]
    assert set(step["with"]) <= set(INPUTS) and "self-hosted" in example
