"""Release gate of the owner-started release workflow (V-01, D-07, D-10 g; KONZEPT 3 "Lieferkette").

Runs before anything is built or signed and checks that
  - the tag is "v" + __version__ of src/neurogrid/__init__.py and the version is no development version;
  - the checkout is the tagged commit and that commit is contained in origin/main (releases come from main);
  - the working tree is clean;
  - no documentation placeholder (<REPO_URL>, <PYPI_RELEASE>) is left in docs/ (outside docs/umsetzung) or
    README.md;
  - every licence and licence exception named in REUSE.toml has its text in LICENSES/ (a licence text whose
    download still waits for the owner's approval blocks the release).
`uv lock --check` runs as its own workflow step. With --notes OUT it also renders packaging/release-notes.md
for the draft release (version, repository and the Sigstore identity of the release workflow).

Standard library only, so it runs before any environment exists.

Usage: python tools/release_check.py --tag v0.1.0 [--root DIR] [--notes OUT [--repository owner/repo]]
Exit codes: 0 fine, 1 a check failed, 2 usage error.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDERS = ("<REPO_URL>", "<PYPI_RELEASE>")
SPDX_OPERATORS = {"AND", "OR", "WITH"}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=False
    )


def project_version(root: Path) -> str:
    text = (root / "src" / "neurogrid" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', text, re.MULTILINE)
    if match is None:
        raise ValueError("no __version__ in src/neurogrid/__init__.py")
    return match.group(1)


def licence_ids(root: Path) -> set[str]:
    """Every licence and exception identifier of the REUSE.toml annotations."""
    data = tomllib.loads((root / "REUSE.toml").read_text(encoding="utf-8"))
    found: set[str] = set()
    for annotation in data.get("annotations", []):
        expression = str(annotation.get("SPDX-License-Identifier", ""))
        found.update(t for t in re.findall(r"[A-Za-z0-9.+-]+", expression) if t not in SPDX_OPERATORS)
    return found


def check(root: Path, tag: str) -> list[str]:
    problems: list[str] = []
    version = project_version(root)
    if tag != f"v{version}":
        problems.append(f"tag {tag} does not match the version {version} (expected v{version})")
    if re.search(r"(?i)dev", version):  # PEP 440 development releases always carry "dev"
        problems.append(f"{version} is a development version")
    tagged = _git(root, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}")
    head = _git(root, "rev-parse", "HEAD")
    if tagged.returncode != 0:
        problems.append(f"tag {tag} not found")
    elif tagged.stdout.strip() != head.stdout.strip():
        problems.append(f"the checkout is not the commit of {tag}")
    else:
        main = _git(root, "rev-parse", "--verify", "--quiet", "refs/remotes/origin/main")
        if main.returncode != 0:
            problems.append("origin/main is not available (fetch it before the check)")
        elif _git(
            root, "merge-base", "--is-ancestor", tagged.stdout.strip(), "refs/remotes/origin/main"
        ).returncode:
            problems.append(f"the commit of {tag} is not contained in origin/main")
    status = _git(root, "status", "--porcelain")
    if status.returncode != 0 or status.stdout.strip():
        problems.append("the working tree is not clean")
    listed = _git(root, "ls-files", "-z", "--", "docs", "README.md")
    for name in sorted(n for n in listed.stdout.split("\0") if n):
        if name.startswith("docs/umsetzung/"):
            continue
        text = (root / name).read_text(encoding="utf-8", errors="replace")
        for placeholder in PLACEHOLDERS:
            if placeholder in text:
                problems.append(f"placeholder {placeholder} left in {name}")
    for identifier in sorted(licence_ids(root)):
        if not (root / "LICENSES" / f"{identifier}.txt").is_file():
            problems.append(f"licence text missing: LICENSES/{identifier}.txt")
    return problems


def render_notes(root: Path, tag: str, repository: str) -> str:
    version = tag.removeprefix("v")
    identity = f"https://github.com/{repository}/.github/workflows/release.yml@refs/tags/{tag}"
    text = (root / "packaging" / "release-notes.md").read_text(encoding="utf-8")
    for key, value in (("version", version), ("repository", repository), ("identity", identity)):
        text = text.replace("{{" + key + "}}", value)
    if "{{" in text:
        raise ValueError("release-notes.md has an unknown placeholder")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--tag", required=True)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--notes", help="write the rendered release notes to this file")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    root = Path(args.root)
    problems = check(root, args.tag)
    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:
        return 1
    if args.notes:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
            print("FAIL: --repository (or GITHUB_REPOSITORY) must be owner/repo")
            return 2
        Path(args.notes).write_text(
            render_notes(root, args.tag, args.repository), encoding="utf-8", newline="\n"
        )
    print(f"release {args.tag}: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
