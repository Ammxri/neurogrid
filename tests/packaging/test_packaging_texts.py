"""User-facing texts of the delivery (A-07, A-08, A-57, POS-01, ARC-05): every copy of the fixed sentence
equals the language tables, so a revised zh text after the native review cannot drift; the forbidden wording
list and the no-statements-about-patients rule hold for installer messages, the bundle README and the release
notes."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from neurogrid.kernel.safety import load_yaml
from neurogrid.report.texts import disclaimer, tables

ROOT = Path(__file__).resolve().parents[2]
PACKAGING = ROOT / "packaging"
COPIES = {
    "README.bundle.txt": "{}",
    "release-notes.md": "{}",
    "install.ps1": "'{}'",
    "install.sh": '"{}"',
}
TEXTS = [PACKAGING / name for name in COPIES] + [PACKAGING / "install.cmd", ROOT / ".env.example"]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("name", sorted(COPIES))
def test_every_copy_of_the_fixed_sentence_equals_the_language_tables(name: str) -> None:
    text = _read(PACKAGING / name)
    for lang in ("zh", "en"):
        assert COPIES[name].format(disclaimer(lang)) in text, (name, lang)
        assert text.count(disclaimer(lang)) == 1, (name, lang)


def test_a_changed_table_sentence_would_be_noticed() -> None:
    changed = disclaimer("zh").replace("预检", "检查")
    assert changed != disclaimer("zh") and changed not in _read(PACKAGING / "README.bundle.txt")


def test_no_forbidden_wording_in_delivery_texts() -> None:
    wording = load_yaml(
        (ROOT / "src" / "neurogrid" / "report" / "wording" / "forbidden.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(wording, dict)
    patterns = [re.compile(p) for lang, group in wording.items() if lang != "allowed" for p in group]
    sentences = [tables()[lang]["disclaimer"] for lang in ("zh", "en", "de")] + list(wording["allowed"])
    hits = []
    for path in TEXTS:
        text = _read(path)
        for sentence in sentences:
            text = re.sub(re.escape(sentence), "", text, flags=re.IGNORECASE)
        hits += [(path.name, p.pattern) for p in patterns if p.search(text)]
    assert not hits, hits


def test_no_statement_about_patients_in_delivery_texts() -> None:
    for path in TEXTS:
        text = _read(path)
        assert not re.search(r"(?i)\bpatient|患者|病人|诊断", text), path.name


HAN = re.compile(r"[一-鿿]")
# A quoted argument: '...' (PowerShell doubles a quote inside) or "..." (backslash or backtick escapes).
QUOTED = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"\\`]|[\\`].)*\"")
MESSAGE_CALLS = {
    "install.ps1": re.compile(r"\b(?:Say|Fail \d)\s+(?=['\"])"),
    "install.sh": re.compile(r"\b(?:say|fail \d)\s+(?=\")"),
}


def _message_arguments(lines: list[str], index: int, start: int) -> list[str]:
    """The first two quoted arguments of the message call starting at lines[index][start:], following
    backslash continuation lines (bash)."""
    text, following = lines[index][start:], index
    while text.rstrip().endswith("\\") and following + 1 < len(lines):
        following += 1
        text = text.rstrip()[:-1] + " " + lines[following]
    return [match.group(0)[1:-1] for match in QUOTED.finditer(text)][:2]


@pytest.mark.parametrize("name", sorted(MESSAGE_CALLS))
def test_installer_messages_are_bilingual(name: str) -> None:
    """Every message of the installers is a pair: Chinese first, then English without Chinese characters
    (they run before the language tables of the package exist)."""
    lines = _read(PACKAGING / name).splitlines()
    count = 0
    for index, line in enumerate(lines):
        match = MESSAGE_CALLS[name].search(line)
        if match is None:
            continue
        arguments = _message_arguments(lines, index, match.end())
        assert len(arguments) == 2, (name, line.strip())
        zh, en = arguments
        assert HAN.search(zh), (name, "first argument without Chinese", line.strip())
        assert not HAN.search(en) and re.search(r"[A-Za-z]{3,}", en), (name, "second argument", line.strip())
        count += 1
    assert count >= 20, name


def test_message_pair_check_finds_a_one_language_message() -> None:
    lines = ["Fail 3 'SHA256SUMS missing'", 'fail 2 "只有中文" \\', '  "仍然中文"']
    assert _message_arguments(lines, 0, len("Fail 3 ")) == ["SHA256SUMS missing"]
    zh, en = _message_arguments(lines, 1, len("fail 2 "))
    assert HAN.search(zh) and HAN.search(en)  # the check above rejects such a pair
    assert _message_arguments(["Say \"a $($x -join ' ') b\" 'c ''d'''"], 0, 4) == [
        "a $($x -join ' ') b",
        "c ''d''",
    ]


def test_installers_mark_the_prefix_as_an_offline_bundle_installation() -> None:
    """The PDF part names the bundled install command when the prefix holds BUNDLE.json next to python/ and
    tools/install_pdf_browser.py (interface with kernel/pdf.py); both installers put all three there."""
    ps1 = _read(PACKAGING / "install.ps1")
    assert "Copy-Item -LiteralPath $infoPath -Destination (Join-Path $Prefix 'BUNDLE.json')" in ps1
    assert r"(Join-Path $Prefix 'tools\install_pdf_browser.py')" in ps1
    assert "-Destination (Join-Path $Prefix 'python') -Recurse" in ps1
    sh = _read(PACKAGING / "install.sh")
    assert 'cp "$bundle/BUNDLE.json" "$prefix/BUNDLE.json"' in sh
    assert 'cp "$bundle/tools/install_pdf_browser.py" "$prefix/tools/install_pdf_browser.py"' in sh
    assert 'cp -a "$bundle/python" "$prefix/python"' in sh
