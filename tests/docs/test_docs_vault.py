"""The NeuroVault pages state what the code does (NV-F03, DM-09, A-30, A-90; p6 decisions 8): the test vector
and the standard-library check of the hash chain on vault.md, the AccessEvent mapping on data-model.md, what
the access log holds on privacy.md, the lock timeout and the honest limits."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from neurogrid.model.access import AccessEvent
from neurogrid.vault import ledger
from neurogrid.vault.lock import LOCK_TIMEOUT_S
from neurogrid.vault.store import init_vault, locate

DOCS = Path(__file__).resolve().parents[2] / "docs"
LANGUAGES = ("en", "zh")
# the PRD fields of DM-09 (D-03) and the fields NeuroGrid adds
PRD_FIELDS = {
    "zeit": "time",
    "rolle": "role",
    "aktion": "action",
    "objekte": "objects",
    "zweck": "purpose",
    "genehmigung_ref": "approval_ref",
    "vorheriger_hash": "previous_hash",
    "hash": "hash",
}
SUPPLEMENTS = {"format_version", "seq", "tool_version"}


def _page(lang: str, name: str) -> str:
    return (DOCS / lang / name).read_text(encoding="utf-8")


def _tagged(text: str, tag: str, language: str) -> list[str]:
    return re.findall(rf"<!-- example: {re.escape(tag)} -->\n```{language}\n(.*?)\n```", text, flags=re.S)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_vault_page_test_vector(lang: str) -> None:
    """The test vector of the page is canonical compact JSON and has the hash the page names."""
    text = _page(lang, "vault.md")
    (vector,) = _tagged(text, "vault-vector", "json")
    event = json.loads(vector)
    assert vector.encode("utf-8") == ledger.compact_event(event)
    digest = ledger.event_hash(event)
    assert f"`{digest}`" in text
    AccessEvent.model_validate({**event, "hash": digest}, strict=True)


def _snippet(tmp_path: Path, lang: str, log: Path) -> list[str]:
    (snippet,) = _tagged(_page(lang, "vault.md"), "vault-check", "python")
    script = tmp_path / f"check_{lang}.py"
    script.write_text(snippet + "\n", encoding="utf-8")
    run = subprocess.run(
        [sys.executable, "-I", str(script), str(log)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert run.returncode == 0, run.stderr
    return run.stdout.splitlines()


def test_vault_check_snippet_verifies_a_neurogrid_log(tmp_path: Path) -> None:
    """The standard-library lines of vault.md (the same in both languages) give the head NeuroGrid gives and
    find what vault verify finds: a changed entry, a broken link, an unreadable line."""
    snippets = {lang: _tagged(_page(lang, "vault.md"), "vault-check", "python") for lang in LANGUAGES}
    assert snippets["en"] == snippets["zh"]
    location = locate(tmp_path, ".neurogrid/vault")
    init_vault(location)
    for role in ("QA", "data_steward", "QA"):
        outcome = ledger.append(
            location, role=role, action="check", objects=["**"], purpose=None, approval_ref=None
        )
        assert outcome.status == "written"
    head = ledger.verify(location).head
    assert _snippet(tmp_path, "en", location.log) == [f"head {head}"]
    lines = location.log.read_bytes().splitlines(keepends=True)
    location.log.write_bytes(
        b"\xef\xbb\xbf"
        + lines[0].replace(b"\n", b"\r\n")
        + lines[1].replace(b'"data_steward"', b'"other"')
        + b"not json\n"
        + lines[2]
    )
    found = _snippet(tmp_path, "zh", location.log)
    assert found == ["line 2: changed", "line 3: unreadable", f"head {head}"]
    kinds = [(d.line, d.kind) for d in ledger.verify(location).deviations]
    assert kinds == [(2, "hash_mismatch"), (3, "malformed")]
    location.log.write_bytes(lines[0] + lines[2] + lines[1])
    assert _snippet(tmp_path, "en", location.log)[:2] == ["line 2: link broken", "line 3: link broken"]


@pytest.mark.parametrize("lang", LANGUAGES)
def test_access_event_mapping_is_documented(lang: str) -> None:
    """DM-09: the eight fields of the product specification and the supplements, against the model."""
    text = _page(lang, "data-model.md")
    section = text.split("### AccessEvent {#access-event}", 1)[1].split("\n## ", 1)[0]
    rows = dict(re.findall(r"^\| (\w+) \| (\w+)", section, flags=re.M | re.ASCII))
    assert {key: rows.get(key) for key in PRD_FIELDS} == PRD_FIELDS
    assert all(f"`{name}`" in section for name in SUPPLEMENTS)
    assert set(PRD_FIELDS.values()) | SUPPLEMENTS == set(AccessEvent.model_fields)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_privacy_page_says_what_the_access_log_holds(lang: str) -> None:
    """KONZEPT 2.8, p6 decisions 8: no more 'no log files'; the access log and what it holds, and that the
    operating system governs access."""
    text = _page(lang, "privacy.md")
    assert "access.jsonl" in text and "vault.md" in text
    if lang == "en":
        assert "No user accounts and no log files" not in text
        assert "governed by the operating system" in text
    else:
        assert "没有用户账户，也没有日志文件" not in text and "由操作系统管理" in text


@pytest.mark.parametrize("lang", LANGUAGES)
def test_vault_pages_state_the_lock_timeout_and_the_limits(lang: str) -> None:
    seconds = f"{LOCK_TIMEOUT_S:g}"
    vault = _page(lang, "vault.md")
    assert re.search(rf"(?<!\d){seconds} ?(s|秒)", vault), seconds
    for page in ("vault.md", "limitations.md", "commands.md"):
        assert "--expect-head" in _page(lang, page), page
    limits = _page(lang, "limitations.md").split("{#neurovault}", 1)[1]
    assert "--expect-head" in limits and "`.neurogrid/vault`" in limits and "--config" in limits
