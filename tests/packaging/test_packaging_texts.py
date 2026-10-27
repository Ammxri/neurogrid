"""User-facing texts of the delivery (A-07, A-08, A-57, POS-01, ARC-05): every copy of the fixed sentence
equals the language tables, so a revised zh text after the native review cannot drift; the forbidden wording
list and the no-statements-about-patients rule hold for installer messages, the bundle README and the release
notes."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import neurogrid
from neurogrid.kernel.safety import load_yaml
from neurogrid.report.texts import disclaimer, tables

ROOT = Path(__file__).resolve().parents[2]
PACKAGING = ROOT / "packaging"
DOCS = ROOT / "docs"
COPIES = {
    "README.bundle.txt": "{}",
    "release-notes.md": "{}",
    "gitee-release.md": "{}",
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


# Where results go (UF-08, CON-04): every delivery text that says so names --out and the defaults of check,
# report and manifest (cli.py), in both languages. The README wraps its lines, hence the line breaks.
RESULT_PLACES = {
    "README.bundle.txt": (
        "Results stay on this computer",
        "check writes results.json in the current folder",
        "report writes next to\nresults.json",
        "manifest writes .neurogrid/manifest.json inside the dataset",
        "结果只保存在本机",
        "check 写入当前\n文件夹中的 results.json",
        "report 写入 results.json 所在的文件夹",
        "manifest 写入数据集中的 .neurogrid/manifest.json",
    ),
    "install.ps1": (
        "results stay on this computer: where --out points;",
        "check writes results.json in the current folder",
        "report writes next to results.json",
        "manifest writes .neurogrid\\manifest.json inside the dataset",
        "结果只保存在本机：写入 --out 指定的位置；",
        "check 写入当前文件夹中的 results.json",
        "report 写入 results.json 所在的文件夹",
        "manifest 写入数据集中的 .neurogrid\\manifest.json",
    ),
    "install.sh": (
        "results stay on this computer: where --out points;",
        "check writes results.json in the current folder",
        "report writes next to results.json",
        "manifest writes .neurogrid/manifest.json inside the dataset",
        "结果只保存在本机：写入 --out 指定的位置；",
        "check 写入当前文件夹中的 results.json",
        "report 写入 results.json 所在的文件夹",
        "manifest 写入数据集中的 .neurogrid/manifest.json",
    ),
}


def test_no_delivery_text_claims_results_go_only_to_out() -> None:
    """check, report and manifest have default locations: "only where --out points" was wrong (UF-08)."""
    for path in TEXTS:
        text = _read(path)
        assert "only where --out" not in text and "只写入 --out" not in text, path.name


@pytest.mark.parametrize("name", sorted(RESULT_PLACES))
def test_delivery_texts_name_where_results_go(name: str) -> None:
    text = _read(PACKAGING / name)
    for needle in RESULT_PLACES[name]:
        assert needle in text, (name, needle)


def test_the_named_default_locations_are_the_ones_the_cli_uses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Run without --out on a copy of a synthetic fixture: check writes results.json in the current folder,
    report writes next to results.json, manifest writes .neurogrid/manifest.json in the dataset - the places
    RESULT_PLACES requires the texts to name."""
    import shutil

    from neurogrid.cli import main

    work = tmp_path / "work"
    data = Path(shutil.copytree(ROOT / "tests" / "fixtures" / "synthetic" / "edf_ok", tmp_path / "data"))
    work.mkdir()
    monkeypatch.chdir(work)
    for args in (
        ["check", str(data), "--as-of", "2026-10-11"],
        ["report", "results.json", "--lang", "en", "--format", "html"],
        ["manifest", str(data)],
    ):
        with pytest.raises(SystemExit) as info:
            main(args)
        assert info.value.code in (0, 1), (args, capsys.readouterr())
    assert (work / "results.json").is_file()
    assert (work / "report.en.html").is_file()
    assert (data / ".neurogrid" / "manifest.json").is_file()


def test_bundle_texts_record_the_removed_berkeley_db_module() -> None:
    """B4: the _dbm removal is recorded in BUNDLE.json (tools/bundle.py), the notices and the documentation;
    the bundle's own texts and both installation pages name it."""
    pages = [DOCS / lang / "installation.md" for lang in ("en", "zh")]
    for path in [PACKAGING / "README.bundle.txt", PACKAGING / "release-notes.md", *pages]:
        text = _read(path)
        assert "_dbm" in text and "Berkeley DB" in text and "BUNDLE.json" in text, path
    for path in pages:
        assert "`dbm.ndbm`" in _read(path) and "`python.removed`" in _read(path), path


# The sentence of the installation pages that states the Windows prefix limit of this version (A-87).
PREFIX_LIMIT = {
    "en": re.compile(r"For NeuroGrid (\S+) that path has (\d+) characters, so the limit is (\d+) characters"),
    "zh": re.compile(r"NeuroGrid (\S+) 的最长相对路径为 (\d+) 个字符，因此上限为 (\d+) 个字符"),
}


def _page(lang: str) -> str:
    """The installation page of `lang` with every line break and indentation as one space."""
    return re.sub(r"\s+", " ", _read(DOCS / lang / "installation.md"))


def documented_prefix_limit(lang: str) -> tuple[str, int, int]:
    """(version, longest relative path below the prefix, prefix limit) as the installation page names them."""
    (match,) = PREFIX_LIMIT[lang].finditer(_page(lang))
    return match.group(1), int(match.group(2)), int(match.group(3))


def test_installation_pages_state_the_windows_prefix_limit_of_this_version() -> None:
    """install.ps1 keeps every installed file within 250 characters (prefix <= 249 minus
    max_relative_install_path, whatever LongPathsEnabled says). Both installation pages state that rule and
    the value of this version; tests/packaging/test_bundle_real.py compares it with the built bundle (the
    build job of offline.yml runs it on every push to dev and main, so a uv.lock change that moves the value
    without a version bump fails there)."""
    match = re.search(r"\$limit = (\d+) - 1 - \[long\]\$longest", _read(PACKAGING / "install.ps1"))
    assert match, "install.ps1 no longer derives the prefix limit from max_relative_install_path"
    total = int(match.group(1))
    for lang in ("en", "zh"):
        text = _page(lang)
        assert f" {total} " in text and f" {total - 1} " in text, lang
        assert "`max_relative_install_path`" in text and "`LongPathsEnabled`" in text, lang
        version, longest, limit = documented_prefix_limit(lang)
        assert version == neurogrid.__version__ and limit == total - 1 - longest, (lang, version, longest)
    assert documented_prefix_limit("en") == documented_prefix_limit("zh")


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


# The project's release page (D-15: repository https://github.com/Ammxri/neurogrid): the one place outside the
# archive that publishes the signer identity of a release (release notes).
RELEASES = "https://github.com/Ammxri/neurogrid/releases"


def test_signer_identity_is_compared_with_the_published_one() -> None:
    """Review R12 (lead decision: the in-archive check stays limited, D-15): the identity that cosign checks
    comes from BUNDLE.json, which a changed bundle carries as well. The installers print the identity they
    verified and tell the user to compare it with the release notes; README.txt says the same in step 1; the
    release notes publish it; the installation pages describe the comparison."""
    decisions = _read(ROOT / "docs" / "umsetzung" / "ENTSCHEIDUNGEN.md")
    assert f"`{RELEASES.removesuffix('/releases')}`" in decisions  # the repository URL of D-15
    ps1, sh = _read(PACKAGING / "install.ps1"), _read(PACKAGING / "install.sh")
    assert f"$Releases = '{RELEASES}'" in ps1 and f'RELEASES="{RELEASES}"' in sh
    for text, variable in ((ps1, "$Releases"), (sh, "$RELEASES")):
        verified = text.index("signature verified: $identity")
        sentence = (
            "compare this signer identity with the one in the release notes on the project's release page"
        )
        compare = text.index(f"{sentence} ({variable})")
        assert 0 < compare - verified < 600
    readme = _read(PACKAGING / "README.bundle.txt")
    step1 = readme[readme.index("1. ") : readme.index("2. ")]
    assert "--certificate-identity {{identity}}" in step1 and RELEASES in step1
    assert "First compare this signer identity with the one in the release notes" in step1
    assert "请先将此签名者身份与项目发布页面" in step1
    notes = _read(PACKAGING / "release-notes.md")
    assert "Signer identity / 签名者身份：`{{identity}}`" in notes
    for lang, needle in (
        ("en", "compare it with the identity in the release notes"),
        ("zh", "发布说明中的身份核对"),
    ):
        assert needle in _page(lang), lang


def test_readme_commands_are_complete_lines_in_the_named_shell() -> None:
    """Review R18: the cosign command of README.txt was split over two lines without a continuation (pasted,
    cosign ran without --certificate-oidc-issuer), and the section headed PowerShell used cmd.exe syntax.
    Every command line (indented by five spaces) is complete, and the Windows lines are PowerShell lines
    (tests/packaging/test_install_ps1.py runs them)."""
    lines = _read(PACKAGING / "README.bundle.txt").splitlines()
    commands = [line.strip() for line in lines if line.startswith("     ")]
    for line, following in zip(lines, lines[1:], strict=False):
        if line.startswith("     "):
            assert not following.lstrip().startswith("--"), (line, following)  # an option left over
            assert not line.rstrip().endswith(("\\", "`")), line  # no continuation in either shell
    (cosign,) = [line for line in commands if line.startswith("cosign ")]
    assert "--certificate-identity {{identity}}" in cosign
    assert cosign.endswith("--certificate-oidc-issuer https://token.actions.githubusercontent.com")
    windows = [line for line in commands if "install.cmd" in line or "neurogrid.cmd" in line]
    assert len(windows) == 5, windows
    launcher = '& "$env:LOCALAPPDATA\\NeuroGrid\\{{version}}\\neurogrid.cmd" '
    for line in windows:
        assert line.startswith((".\\install.cmd ", launcher)), line
        assert "%LOCALAPPDATA%" not in line, line
        assert not re.search(r"\s--(lang|format) [^\"\s]*,", line), line  # a bare a,b: an array in PowerShell
    heading = lines.index(next(line for line in lines if line.startswith("2. ")))
    assert "PowerShell" in lines[heading] and "cmd.exe" in "\n".join(lines[heading : heading + 8])


def _platform_status(lang: str) -> str:
    """The #platforms paragraph of limitations.md without its link to the installation page and without
    whitespace (the delivery texts wrap it at other places)."""
    text = _read(DOCS / lang / "limitations.md")
    section = re.split(r"^## .*\{#([A-Za-z0-9_.-]+)\}\s*$", text, flags=re.M)
    body = dict(zip(section[1::2], section[2::2], strict=True))["platforms"]
    body = re.sub(r"\s*[(（]\[[^\]]+\]\(installation\.md#platforms\)[)）]", "", body)
    return re.sub(r"\s+", "", body)


def test_delivery_texts_state_the_platform_status_of_the_documentation() -> None:
    """V-06, NG-N01, TECH-06: README.txt of the bundle and the release notes still said "Not verified: Windows
    10; Linux distributions other than Debian 12 and Ubuntu 22.04+" after the documentation had followed the
    green offline workflow (limitations.md #platforms: the offline bundle verified in CI on Windows Server,
    Debian 12, Ubuntu 22.04 and 24.04, the test suite there not yet verified, PowerShell 7 on Windows 11 and
    Ubuntu after 24.04 not verified, other distributions not supported). Both delivery texts carry the
    platform paragraph of limitations.md in both languages, so a change of the status changes all four."""
    for path in (PACKAGING / "README.bundle.txt", PACKAGING / "release-notes.md"):
        flat = re.sub(r"\s+", "", _read(path))
        assert "otherthanDebian12andUbuntu22.04+" not in flat, path.name
        for lang in ("en", "zh"):
            status = _platform_status(lang)
            assert "PowerShell7" in status and "Ubuntu24.04" in status, lang  # the paragraph was found
            assert status in flat, (path.name, lang)
