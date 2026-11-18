# skills/model-earnings-before/tests/test_rates.py
"""Base rates come from the user's own price tabs: the right ten prints, newest first, with run-up and drift read off
the closes around each reaction day; the daily sigma over 252 days; and a report date estimated as last year's plus
52 weeks (Yahoo doesn't show the next date until the company announces it)."""
import statistics

import openpyxl
import pytest

import checks
import make_fixture as mf
import rates


@pytest.fixture(scope="module")
def tabs(fixture_model):
    wb = openpyxl.load_workbook(fixture_model, read_only=True, data_only=True)
    return checks.grid(wb["Px Data"]), checks.grid(wb["Px Events"])


def test_px_data_columns(tabs):
    P = rates.px_data(tabs[0], "TEST")
    assert P["cols"] == {"date": "A", "close": "B", "spy": "C", "ret": "D"}
    assert len(P["rows"]) == len(mf.trading_days()) and P["first"] == 5


def test_prints_newest_first_with_run_up_and_drift(tabs):
    P = rates.px_data(tabs[0], "TEST")
    pr = rates.prints(tabs[1], P, "TEST")
    days = [d.isoformat() for d in mf.reaction_days()]
    assert [x["date"] for x in pr] == days[::-1]
    assert [x["move"] for x in pr] == mf.PRINT_MOVES[::-1]
    assert pr[0]["refs"]["move"] == "'Px Events'!$N$14"
    px, _ = mf.closes()
    i = mf.trading_days().index(mf.reaction_days()[-1])
    assert pr[0]["run_up"] == pytest.approx(px[i - 1] / px[i - 8] - 1)
    assert pr[0]["drift"] == pytest.approx(px[i + 7] / px[i] - 1)


def test_vol_and_relative_performance(tabs):
    P = rates.px_data(tabs[0], "TEST")
    v = rates.vol(P)
    px, spy = mf.closes()
    rets = [px[k] / px[k - 1] - 1 for k in range(1, len(px))][-252:]
    assert v["value"] == pytest.approx(statistics.stdev(rets)) and v["n"] == 252
    last = rates.prints(tabs[1], P, "TEST")[0]
    i = mf.trading_days().index(mf.reaction_days()[-1])
    r = rates.rel_since(P, last)
    assert r["value"] == pytest.approx((px[-1] / px[i] - 1) - (spy[-1] / spy[i] - 1))
    assert rates.rel_since(P, None)["value"] is None


def test_next_date_is_last_years_plus_52_weeks(tabs):
    n = rates.next_date(tabs[1], "Q4 26E")
    assert n["base"] == "2026-02-02" and n["value"] == "2027-02-01"
    assert n["from"] == "'Px Events'!$B$11"
    assert rates.next_date(tabs[1], "Q4 30E") is None
