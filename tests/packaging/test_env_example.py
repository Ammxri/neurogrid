""".env.example lists every environment variable of NeuroGrid, its tools and its workflows, with empty values
only; .env stays out of git (secrets only via environment variables)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / ".env.example"
# Set by the operating system, Python, GitHub Actions or third-party tools: read (or removed from a child's
# environment, like the Node.js and Playwright debug switches of the PDF driver), never set for NeuroGrid.
PROVIDED = {
    "ACTIONS_ID_TOKEN_REQUEST_URL",
    "APPDATA",
    "COMPUTERNAME",
    "DEBUG",
    "DEBUG_FILE",
    "GITHUB_ACTIONS",
    "GITHUB_REF",
    "GITHUB_REF_NAME",
    "GITHUB_REPOSITORY",
    "GH_TOKEN",
    "HOME",
    "LOCALAPPDATA",
    "MNE_TQDM",
    "NODE_OPTIONS",
    "NODE_PATH",
    "PATH",
    "PWDEBUG",
    "RUNNER_TEMP",
    "SystemRoot",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USERNAME",
    "XDG_DATA_HOME",
}
OWN_PREFIXES = ("NEUROGRID_", "GITEE_", "PYPI_")


def _example() -> dict[str, str]:
    values = {}
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, sep, value = line.partition("=")
            assert sep == "=" and re.fullmatch(r"[A-Z][A-Z0-9_]*", name), line
            values[name] = value
    return values


def _code_names() -> set[str]:
    """Names read with os.environ / os.getenv in the package and the tools."""
    names: set[str] = set()
    pattern = re.compile(r"""(?:environ(?:\.get)?\(?\[?|getenv\()\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""")
    for path in [*(ROOT / "src").rglob("*.py"), *(ROOT / "tools").glob("*.py")]:
        names.update(pattern.findall(path.read_text(encoding="utf-8")))
    return names


def _workflow_names() -> set[str]:
    names: set[str] = set()
    for path in [*(ROOT / ".github" / "workflows").glob("*.yml"), *(ROOT / "packaging").rglob("*.sh")]:
        text = path.read_text(encoding="utf-8")
        names.update(re.findall(r"(?:secrets|vars)\.([A-Z0-9_]+)", text))
        names.update(n for n in re.findall(r"\b([A-Z][A-Z0-9_]{3,})\b", text) if n.startswith(OWN_PREFIXES))
    return names


def test_example_exists_with_empty_values_only() -> None:
    values = _example()
    assert values and all(value == "" for value in values.values()), values
    assert len(values) == len(set(values))


def test_example_lists_every_variable_of_code_and_workflows() -> None:
    listed = set(_example())
    wanted = (_code_names() - PROVIDED) | _workflow_names()
    assert wanted - listed == set(), sorted(wanted - listed)
    assert {
        "NEUROGRID_PDF_BROWSER_DIR",
        "NEUROGRID_REQUIRE_PDF",
        "SOURCE_DATE_EPOCH",
        "GITEE_SSH_KEY",
    } <= listed


def test_every_listed_name_is_documented_by_a_comment() -> None:
    lines = EXAMPLE.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line and not line.startswith("#"):
            assert any(lines[i].startswith("#") for i in range(max(0, index - 3), index)), line


def test_dot_env_is_ignored_by_git() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored


def test_scanner_finds_planted_names(tmp_path: Path) -> None:
    pattern = re.compile(r"""(?:environ(?:\.get)?\(?\[?|getenv\()\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""")
    source = 'os.environ.get("A_B")\nos.environ["C_D"]\nos.getenv("E_F")\nenviron.get( "G_H", "x")\n'
    assert set(pattern.findall(source)) == {"A_B", "C_D", "E_F", "G_H"}
