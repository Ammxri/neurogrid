"""The word lists of the main project for the report and the notebook (A-57, ARC-05; A-107, R-P11-12): read by
path from ``src/neurogrid/report/wording/`` (NeuroArena never imports neurogrid, A-100) and applied as the
main project's tests apply them: every pattern of every language to every text, after the exact phrases of
the lists' ``allowed`` entries are removed. Also what a published file must not contain (no absolute path,
user or host name)."""

from __future__ import annotations

import getpass
import io
import json
import platform
import re
import socket
import tokenize
from pathlib import Path

import yaml

from neuroarena import paths

WORDING = paths.REPO / "src" / "neurogrid" / "report" / "wording"
FORBIDDEN = WORDING / "forbidden.yaml"  # A-57: no conformity claim
STATEMENTS = WORDING / "statements.yaml"  # ARC-05: no statement about patients, no law article
# The scope statement of the report (A-36, A-107): en exactly as decided, zh its translation.
SCOPE = {
    "en": (
        "applies only to the public datasets and decoders studied; no statement about the performance or "
        "safety of a medical device"
    ),
    "zh": "仅适用于所研究的公开数据集和解码器；不对任何医疗器械的性能或安全性作任何陈述",
}


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), path.name
    return data


def word_lists() -> tuple[list[re.Pattern[str]], list[str]]:
    """(patterns, allowed phrases) of both lists."""
    forbidden, statements = _load(FORBIDDEN), _load(STATEMENTS)
    patterns = [
        re.compile(p) for language, group in forbidden.items() if language != "allowed" for p in group
    ]
    for group in ("patient", "law_article"):
        patterns += [re.compile(p) for items in statements[group].values() for p in items]
    return patterns, [*forbidden["allowed"], *statements["allowed"]]


def hits(text: str) -> list[str]:
    """The patterns that match ``text`` once the allowed phrases are removed."""
    patterns, allowed = word_lists()
    for phrase in allowed:
        text = re.sub(re.escape(phrase), "", text, flags=re.IGNORECASE)
    return [pattern.pattern for pattern in patterns if pattern.search(text)]


def notebook_texts(path: Path) -> list[str]:
    """The text a reader of the notebook reads: every Markdown cell and the comments of every code cell."""
    document = json.loads(path.read_text(encoding="utf-8"))
    texts = []
    for cell in document["cells"]:
        source = "".join(cell["source"])
        if cell["cell_type"] == "markdown":
            texts.append(source)
        elif cell["cell_type"] == "code":
            tokens = tokenize.generate_tokens(io.StringIO(source).readline)
            texts += [token.string for token in tokens if token.type == tokenize.COMMENT]
    return texts


def private_names(*folders: Path) -> list[str]:
    """What must not appear in a published file: the given folders (both slash forms), the home folder, the
    user's folder in /home and C:\\Users and the host name."""
    found = set()
    for folder in (*folders, Path.home()):
        resolved = folder.resolve()
        found |= {str(folder), str(resolved), resolved.as_posix()}
    user = getpass.getuser()
    found |= {f"Users\\{user}", f"Users/{user}", f"/home/{user}"}
    found |= {name for name in (socket.gethostname(), platform.node()) if len(name) >= 3}
    return sorted(found)


def private_hits(data: bytes, names: list[str]) -> list[str]:
    """The names of ``private_names`` that occur in ``data`` (text or binary, case-insensitive)."""
    text = data.decode("utf-8", errors="replace").lower() + "\n" + data.decode("latin-1").lower()
    return [name for name in names if name.lower() in text]
