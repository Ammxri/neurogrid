"""The impact assessment as CORE-NV05-02 reads it (NV-F05; A-30, A-94): vault.pia.read_pia with its states,
the template comparison without BOM and CRLF, the placeholder markers of both languages, and the limit."""

from __future__ import annotations

from pathlib import Path

import pytest

from neurogrid.vault import pia
from neurogrid.vault.pia import PIA_MARKERS, PiaReading, markers, read_pia
from neurogrid.vault.store import VaultLocation, init_vault, locate, pia_template

ZH, EN = "pia.zh.md", "pia.en.md"


def _vault(tmp_path: Path) -> VaultLocation:
    location = locate(tmp_path, ".neurogrid/vault")
    init_vault(location)
    return location.refreshed()


def test_the_markers_are_those_of_the_templates() -> None:
    assert PIA_MARKERS == ("【待填写】", "[to be completed]")
    assert markers(pia_template(ZH)) == markers(pia_template(EN)) == 16
    assert markers("【待填写】 and [to be completed]".encode()) == 2


def test_the_templates_are_unedited(tmp_path: Path) -> None:
    location = _vault(tmp_path)
    assert read_pia(location) == PiaReading("template_unedited", files=2)
    zh, en = location.pia_files
    en.write_bytes(b"\xef\xbb\xbf" + pia_template(EN).replace(b"\n", b"\r\n"))  # an editor's BOM and CRLF
    assert read_pia(location).state == "template_unedited"
    zh.unlink()
    assert read_pia(location) == PiaReading("template_unedited", files=1)


def test_edited_files_with_and_without_markers(tmp_path: Path) -> None:
    location = _vault(tmp_path)
    zh, en = location.pia_files
    en.write_bytes(pia_template(EN).replace(b"Purpose: [to be completed]", b"Purpose: model training"))
    assert read_pia(location) == PiaReading("fields_open", files=2, open_fields=15)
    zh.write_bytes("# 评估\n\n已完成。\n".encode())  # one edited file without a marker suffices
    assert read_pia(location) == PiaReading("edited", files=2, open_fields=15)
    en.unlink()
    assert read_pia(location) == PiaReading("edited", files=1, open_fields=0)
    zh.write_bytes(b"Notes [to be completed]\n")  # the marker of the other language counts too
    assert read_pia(location) == PiaReading("fields_open", files=1, open_fields=1)


def test_missing_and_unreadable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    location = _vault(tmp_path)
    zh, en = location.pia_files
    zh.unlink()
    en.unlink()
    assert read_pia(location) == PiaReading("missing")
    en.mkdir()  # a folder at a file's place is no PIA file
    assert read_pia(location) == PiaReading("missing")
    en.rmdir()
    monkeypatch.setattr(pia, "MAX_PIA_BYTES", 10)
    en.write_bytes(b"x" * 11)
    assert read_pia(location) == PiaReading("unreadable", files=1)
