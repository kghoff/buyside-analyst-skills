# skills/model-earnings-before/tests/test_checks.py
"""Section 13.5's checks find the engineered hockey stick in Q4 26E, read the right MOD cells (the formula and the
value must describe the same cells, or the tab and the note disagree), and stop in plain English when a row is
missing."""
import openpyxl
import pytest

import checks
import make_fixture as mf
from modmap import ModMap


@pytest.fixture(scope="module")
def ck(fixture_model):
    mm = ModMap(fixture_model)
    g = checks.grid(openpyxl.load_workbook(fixture_model, read_only=True, data_only=True)["MOD"])
    rows = checks.find_rows(mm)
    drivers = [{"name": "Units", "key": mf.DRIVER_KEY, "row": mm.row(mf.DRIVER_KEY)}]
    return mm, rows, checks.run(mm, g, rows, drivers)


def test_target_quarter_and_rows(ck):
    mm, rows, c = ck
    assert c["quarter"] == "Q4 26E" and c["fy"] == "2026E" and c["prev"] == "Q3 26"
    assert rows["rev"] == 3 and rows["gp"] == 4 and rows["cash"] == 9 and rows["fcf"] == 11
    assert [m["name"] for m in c["metrics"]] == ["Revenue", "Gross profit", "Operating income", "EPS, diluted", "Units"]


def test_revenue_checks_flag_the_hockey_stick(ck):
    mm, rows, c = ck
    s = mf.series()
    rev = c["metrics"][0]["cells"]
    assert rev["yoy"]["value"] == pytest.approx(0.12)
    assert rev["yoy_prev"]["value"] == pytest.approx(0.02)
    assert rev["st2"]["value"] == pytest.approx(s["Q4 26E"]["rev"] / s["Q4 24"]["rev"] - 1)
    assert rev["st3"]["value"] == pytest.approx(s["Q4 26E"]["rev"] / s["Q4 23"]["rev"] - 1)
    assert rev["qoq_avg"]["periods"] == ["Q4 21", "Q4 22", "Q4 23", "Q4 24", "Q4 25"]
    assert rev["hockey"] == "yes"
    assert f"MOD!${mm.col('Q4 26E')}$3/MOD!${mm.col('Q4 25')}$3-1" in rev["yoy"]["formula"]
    assert c["metrics"][4]["cells"]["hockey"] == "yes"            # the driver moves with revenue


def test_margin_checks(ck):
    _, _, c = ck
    oi = c["metrics"][2]["cells"]
    assert oi["margin"]["value"] == pytest.approx(0.17)
    assert oi["margin_avg"]["value"] == pytest.approx(0.17)
    assert oi["incr"]["value"] == pytest.approx(0.17)
    assert "margin" not in c["metrics"][0]["cells"]


def test_second_half_share_and_blowup_inputs(ck):
    mm, _, c = ck
    s = mf.series()
    fy26 = sum(s[f"Q{q} 26" + ("E" if q == 4 else "")]["rev"] for q in range(1, 5))
    assert c["h2"]["share"]["value"] == pytest.approx((s["Q3 26"]["rev"] + s["Q4 26E"]["rev"]) / fy26)
    b = c["blowup"]
    assert b["margin_range"]["value"] == pytest.approx(0.02)
    assert b["ttm_ni"]["value"] == pytest.approx(sum(s[p]["ni"] for p in ("Q4 25", "Q1 26", "Q2 26", "Q3 26")))
    assert b["cash"]["value"] == 50.0
    assert c["ntm_eps"]["value"] == pytest.approx(sum(s[p]["eps"] for p in ("Q4 26E", "Q1 27E", "Q2 27E", "Q3 27E")))


def test_missing_required_row_stops_by_name(tmp_path):
    p = mf.build(str(tmp_path / "x.xlsx"))
    wb = openpyxl.load_workbook(p)
    wb["MOD"]["B5"] = "Something else"
    wb.save(p)
    with pytest.raises(SystemExit, match="oi"):
        checks.find_rows(ModMap(p))
