# skills/model-earnings-before/tests/test_links_docs.py
"""Links point at the cells that hold the numbers (found by label, so a moved row still links right); the guidance
trail is research-filings' block, not a re-read of the releases; and the agent's reading list starts on the print
day (the release and the call set the bar) and leaves out everything older."""
import openpyxl
import pytest

import checks
import docs
import links
from conftest import RESEARCH


@pytest.fixture(scope="module")
def wb(fixture_model):
    return openpyxl.load_workbook(fixture_model, read_only=True, data_only=True)


def test_multiples(wb):
    m = links.multiples(checks.grid(wb["Multiples"]))
    assert m["pe_pct"] == {"ref": "Multiples!$J$7", "value": 0.85}
    assert m["pe_med5"]["value"] == 22.0 and m["pe_min5"]["value"] == 15.0 and m["pe_max5"]["value"] == 40.0


def test_consensus_mean_row_and_snapshot(wb):
    c = links.consensus(checks.grid(wb["Consensus"]))
    assert c["eps_fy"] == {"ref": "Consensus!$K$10", "value": 2.45}
    assert c["rev_q"]["value"] == 140.0 and c["snapshot"] == "2026-11-01"


def test_guidance_block_last_four_years(wb):
    (b,) = links.guidance(checks.grid(wb["Filings Charts"]))
    assert b["title"] == "Revenue"
    assert [r["year"] for r in b["rows"]] == ["2022", "2023", "2024", "2025"]
    assert b["rows"][-1]["vs_mid"]["ref"] == "'Filings Charts'!$J$11"
    assert b["habitual"] == "yes"


def test_docs_since_the_print_day():
    got = docs.since(RESEARCH, "2026-11-02")
    assert [d["date"] for d in got] == ["2026-11-02", "2026-11-10", "2026-11-12"]
    assert got[1]["md"] == "Investor Events/_md/TEST 2026-11-10 conference.md"
    assert docs.since("/nonexistent", "2026-11-02") == []
