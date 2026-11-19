"""After a real recalculation, every plain link on SUM equals the cell it points at, nothing shows #REF!, #NAME?,
#DIV/0! or #VALUE!, and the IRR equals (target / price)^(1/years) - 1. One LibreOffice run for the suite."""
import json
import os

import openpyxl
import pytest

import verify


@pytest.fixture(scope="session")
def recalculated(built):
    out, _, work = built
    return out, work, verify.run(out, work)


@pytest.mark.slow
def test_recalculated_sum_ties_out(built, recalculated):
    r = recalculated[2]
    assert r["problems"] == [], r["problems"]
    assert r["checked_links"] > 60


@pytest.mark.slow
def test_a_wrong_link_target_is_caught(recalculated, tmp_path):
    """The link check must be able to fail: repoint one SUM link at a different DCF cell (net debt, 230, not the price, 50) (formula copy only, the
    recalculated values are reused, no second LibreOffice run) and verify must name that cell."""
    out, work, r = recalculated
    wb = openpyxl.load_workbook(out)
    c = wb["SUM"]["C7"]
    assert c.value == "=DCF!$C$18", c.value
    c.value = "=DCF!$C$14"
    bad = str(tmp_path / "bad.xlsx")
    wb.save(bad)                                   # scratch copy only, never a user file
    lay = json.load(open(os.path.join(work, "layout.json")))
    problems, _ = verify.compare(bad, r["recalculated"], lay)
    assert any(p.startswith("SUM!C7 ") for p in problems), problems
