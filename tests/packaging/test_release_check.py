"""tools/release_check.py (V-01, D-07, D-10 g): the release gate on throwaway git repositories."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

import release_check

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


def _git(repo: Path, *args: str) -> str:
    command = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args]
    return subprocess.run(command, cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def _repo(tmp_path: Path, version: str = "1.2.3", tag: str | None = None) -> Path:
    repo = tmp_path / "repo"
    (repo / "src" / "neurogrid").mkdir(parents=True)
    (repo / "src" / "neurogrid" / "__init__.py").write_text(
        f'"""x"""\n\n__version__ = "{version}"\n', encoding="utf-8"
    )
    (repo / "REUSE.toml").write_text(
        'version = 1\n\n[[annotations]]\npath = ["src/**"]\nSPDX-License-Identifier = "Apache-2.0"\n\n'
        '[[annotations]]\npath = ["docs/**"]\n'
        'SPDX-License-Identifier = "CC-BY-4.0 OR (MIT WITH LLVM-exception)"\n',
        encoding="utf-8",
    )
    for name in ("Apache-2.0", "CC-BY-4.0", "MIT", "LLVM-exception"):
        (repo / "LICENSES").mkdir(exist_ok=True)
        (repo / "LICENSES" / f"{name}.txt").write_text(name, encoding="utf-8")
    (repo / "docs" / "en").mkdir(parents=True)
    (repo / "docs" / "en" / "index.md").write_text("# Docs\n", encoding="utf-8")
    (repo / "README.md").write_text("# NeuroGrid\n", encoding="utf-8")
    (repo / "packaging").mkdir()
    shutil.copy(ROOT / "packaging" / "release-notes.md", repo / "packaging" / "release-notes.md")
    _git(repo, "init", "--quiet", "--initial-branch", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "release")
    _git(repo, "tag", tag or f"v{version}")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def _check(repo: Path, tag: str) -> list[str]:
    return release_check.check(repo, tag)


def test_a_clean_tagged_release_on_main_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert _check(repo, "v1.2.3") == []
    assert release_check.main(["--tag", "v1.2.3", "--root", str(repo)]) == 0
    assert "all checks passed" in capsys.readouterr().out


def test_release_candidates_pass_and_development_versions_fail(tmp_path: Path) -> None:
    assert _check(_repo(tmp_path / "rc", "0.1.0rc1"), "v0.1.0rc1") == []
    assert "0.1.0.dev1 is a development version" in _check(
        _repo(tmp_path / "dev", "0.1.0.dev1"), "v0.1.0.dev1"
    )


def test_tag_and_version_must_agree(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "1.2.3", tag="v1.2.4")
    problems = _check(repo, "v1.2.4")
    assert "tag v1.2.4 does not match the version 1.2.3 (expected v1.2.3)" in problems
    assert release_check.main(["--tag", "v1.2.4", "--root", str(repo)]) == 1
    assert "tag v9.9.9 not found" in _check(_repo(tmp_path / "b", "9.9.9", tag="other"), "v9.9.9")


def test_the_tagged_commit_must_be_on_main_and_checked_out(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "README.md").write_text("# changed\n", encoding="utf-8")
    _git(repo, "commit", "--quiet", "-am", "later")
    assert "the checkout is not the commit of v1.2.3" in _check(repo, "v1.2.3")
    _git(repo, "checkout", "--quiet", "v1.2.3")
    assert _check(repo, "v1.2.3") == []
    _git(repo, "tag", "-d", "v1.2.3")
    _git(repo, "checkout", "--quiet", "main")
    _git(repo, "tag", "v1.2.3")  # now on the later commit, which origin/main does not contain
    assert "the commit of v1.2.3 is not contained in origin/main" in _check(repo, "v1.2.3")
    _git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    assert "origin/main is not available (fetch it before the check)" in _check(repo, "v1.2.3")


def test_the_working_tree_must_be_clean(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "untracked.txt").write_text("x", encoding="utf-8")
    assert "the working tree is not clean" in _check(repo, "v1.2.3")


def test_placeholders_block_the_release_outside_the_implementation_notes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "docs" / "umsetzung").mkdir()
    (repo / "docs" / "umsetzung" / "notes.md").write_text("<REPO_URL> is open\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "notes")
    _git(repo, "tag", "-f", "v1.2.3")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert _check(repo, "v1.2.3") == []
    (repo / "docs" / "en" / "index.md").write_text("see <PYPI_RELEASE>\n", encoding="utf-8")
    _git(repo, "commit", "--quiet", "-am", "placeholder")
    _git(repo, "tag", "-f", "v1.2.3")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert _check(repo, "v1.2.3") == ["placeholder <PYPI_RELEASE> left in docs/en/index.md"]


def test_every_licence_of_reuse_toml_needs_its_text(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "LICENSES" / "CC-BY-4.0.txt").unlink()
    (repo / "LICENSES" / "LLVM-exception.txt").unlink()
    _git(repo, "commit", "--quiet", "-am", "drop texts")
    _git(repo, "tag", "-f", "v1.2.3")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert _check(repo, "v1.2.3") == [
        "licence text missing: LICENSES/CC-BY-4.0.txt",
        "licence text missing: LICENSES/LLVM-exception.txt",
    ]
    assert release_check.licence_ids(repo) == {"Apache-2.0", "CC-BY-4.0", "MIT", "LLVM-exception"}


def test_release_notes_are_rendered_for_the_draft(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    out = tmp_path / "notes.md"
    code = release_check.main(
        ["--tag", "v1.2.3", "--root", str(repo), "--notes", str(out), "--repository", "o/neurogrid"]
    )
    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "# NeuroGrid 1.2.3" in text and "{{" not in text
    assert "https://github.com/o/neurogrid/.github/workflows/release.yml@refs/tags/v1.2.3" in text
    assert "neurogrid-1.2.3-offline-win_amd64.zip" in text
    assert (
        release_check.main(["--tag", "v1.2.3", "--root", str(repo), "--notes", str(out), "--repository", "x"])
        == 2
    )


def test_the_template_of_this_repository_renders() -> None:
    text = release_check.render_notes(ROOT, "v0.1.0", "owner/neurogrid")
    assert "{{" not in text and "NeuroGrid 0.1.0" in text


def test_usage_error_exits_2() -> None:
    assert release_check.main([]) == 2
