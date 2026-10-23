"""Structure of the GitHub workflows (TECH-05, TECH-08, NG-N01, NG-N04, CON-02, V-01, D-07, D-09, D-10 g).

The workflows have not run yet (no repository URL, D-09); these tests pin what can be checked without GitHub:
triggers, pinned actions, permissions, the jobs and the commands they run, and that no job uploads datasets.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
NAMES = ("ci", "offline", "corpus", "docs", "release", "publish-pypi", "mirror-gitee")
# Tools of other P5 areas that the workflows call by name (docs: build_docs, notices; pdf:
# install_pdf_browser, linux_pdf_packages; acceptance: acceptance_g1). They arrive with the merge.
OTHER_AREAS = {
    "build_docs.py",
    "notices.py",
    "install_pdf_browser.py",
    "linux_pdf_packages.py",
    "acceptance_g1.py",
}
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
            assert (ROOT / "tools" / tool).is_file() or tool in OTHER_AREAS, (name, tool)


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
    assert offline["on"]["push"] == {"branches": ["main"], "tags": ["v*"]}  # dev pushes run ci.yml only
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
    for command in ("tools/release_check.py --tag", "uv lock --check", "tools/licenses.py --release",
                    "SOURCE_DATE_EPOCH", "uv build",
                    "tools/build_docs.py --site-dir site", "tools/notices.py --download --check",
                    "--sign sigstore", "tools/bundle.py verify", "cosign sign-blob", "cosign verify-blob",
                    "sha256sum --check --strict SHA256SUMS", "--notes"):  # fmt: skip
        assert command in commands, command
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
