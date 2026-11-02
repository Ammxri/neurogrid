"""The risks CORE-M14-02 judges (NV-F06; A-30, A-95): vault.risks.judged and future, and the same on
LoadedRisks in each state. A risk dated on the reference date is judged, as a consent record dated on it is in
effect; the order is the ID order whatever the order of the file (two runs give the same results, NG-N03)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from neurogrid.model.risks import parse_risks
from neurogrid.vault import risks
from neurogrid.vault.store import DEFAULT_VAULT_PATH, init_vault, locate

AS_OF = date(2026, 11, 20)
ENTRY = "  - {{id: {id}, date: {date}, description: d, affected_uses: [{uses}], min_consent_version: {v}}}\n"
REGISTER = (
    "format_version: 1\nrisks:\n"
    + ENTRY.format(id="R-b", date="2026-11-20", uses="training", v=2)
    + ENTRY.format(id="R-c", date="2026-11-21", uses="sharing", v=3)
    + ENTRY.format(id="R-a", date="2026-01-01", uses="sharing, training", v=2)
    + ENTRY.format(id="Q.1", date="'2025-12-31'", uses="commercial", v=1)
).encode()


def test_judged_risks_are_dated_on_or_before_the_reference_date_in_id_order() -> None:
    register = parse_risks(REGISTER)
    assert [risk.id for risk in risks.judged(register, AS_OF)] == ["Q.1", "R-a", "R-b"]
    assert risks.future(register, AS_OF) == 1  # R-c, one day later
    later = date(2026, 11, 21)
    assert [risk.id for risk in risks.judged(register, later)] == ["Q.1", "R-a", "R-b", "R-c"]
    assert risks.future(register, later) == 0
    earlier = date(2025, 12, 30)
    assert risks.judged(register, earlier) == [] and risks.future(register, earlier) == 4


def test_the_order_of_the_file_changes_nothing() -> None:
    lines = REGISTER.split(b"\n")
    reordered = parse_risks(b"\n".join([*lines[:2], *reversed(lines[2:-1]), b""]))
    assert reordered != parse_risks(REGISTER)  # another list order, the same judged risks
    assert risks.judged(reordered, AS_OF) == risks.judged(parse_risks(REGISTER), AS_OF)


def test_loaded_risks_in_each_state(tmp_path: Path) -> None:
    location = locate(tmp_path, DEFAULT_VAULT_PATH)
    absent = risks.load_for_check(location)
    assert absent == risks.LoadedRisks("no_vault")
    assert (absent.judged(AS_OF), absent.future(AS_OF)) == ([], 0)
    init_vault(location)
    template = risks.load_for_check(location)  # risks: [] of the template
    assert template.state == "loaded" and (template.judged(AS_OF), template.future(AS_OF)) == ([], 0)
    location.risks.unlink()
    missing = risks.load_for_check(location)
    assert missing.state == "no_file" and (missing.judged(AS_OF), missing.future(AS_OF)) == ([], 0)
    location.risks.write_bytes(REGISTER)
    loaded = risks.load_for_check(location)
    assert [risk.id for risk in loaded.judged(AS_OF)] == ["Q.1", "R-a", "R-b"] and loaded.future(AS_OF) == 1


def test_the_documented_example_is_a_valid_register() -> None:
    """docs/<lang>/vault.md#risks: the example parses, and both languages give the same risks apart from the
    description (written in the page's language)."""
    docs = Path(__file__).parents[3] / "docs"
    found = {}
    for lang in ("en", "zh"):
        page = (docs / lang / "vault.md").read_text(encoding="utf-8")
        (example,) = re.findall(r"<!-- example: risks.yaml -->\n```yaml\n(.*?)\n```", page, flags=re.S)
        found[lang] = [
            (r.id, r.date, r.affected_uses, r.min_consent_version)
            for r in parse_risks(example.encode()).risks
        ]
    assert found["en"] == found["zh"] and len(found["en"]) == 1
