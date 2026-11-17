import datetime as dt
import json
import os

import pytest

import peers
from conftest import FIX


@pytest.fixture(scope="module")
def x():
    return json.load(open(os.path.join(FIX, "abt_xbrl.json")))


def test_our_ttm_matches_the_tools_ttm(x):
    # Intent: quarter stitching is right only if the latest four quarters sum to the tool's own TTM figure.
    q = peers.eps_quarters(x)
    t = peers.ttm(q)
    # The tool's TTM EPS is TTM net income / TTM average shares, so it differs from the sum of quarterly EPS by share
    # drift (0.05% here). 0.2% still catches a misaligned quarter (a wrong quarter moves it by 20%+).
    assert t[-1]["ttm"] == pytest.approx(x["ttm"]["income"]["diluted_earnings_per_share"], rel=2e-3)
    assert t[-1]["consecutive"] is True
    # Exact proof of alignment: the same four quarters' net income sums to the tool's TTM net income.
    ni = sum(x["quarterly"][str(r["fy"])]["Q%d" % r["q"]]["income"]["net_income_loss"] for r in q[-4:])
    assert ni == x["ttm"]["income"]["net_income_loss"]


def test_quarter_known_after_filing_deadline_never_at_quarter_end(x):
    q = peers.eps_quarters(x)
    for r in q:
        lag = (r["known"] - r["end"]).days
        assert lag == (60 if r["q"] == 4 else 40)
    assert q[-1]["end"] == dt.date.fromisoformat(x["ttm"]["endDate"])


def test_gap_in_quarters_breaks_ttm(x):
    q = peers.eps_quarters(x)
    del q[-2]                                          # a missing quarter: no TTM until four consecutive again
    t = peers.ttm(q)
    assert t[-1]["ttm"] is None and t[-1]["consecutive"] is False


def test_missing_eps_is_kept_visible_and_breaks_ttm(x):
    # Intent: a quarter with no EPS must not vanish silently; it stays as a row and breaks every TTM that spans it,
    # so build can write NA() exactly where Python says None.
    y = json.loads(json.dumps(x))
    y["quarterly"]["2026"]["Q2"]["income"].pop("diluted_earnings_per_share")
    q = peers.eps_quarters(y)
    assert len(q) == len(peers.eps_quarters(x))
    assert [r["eps"] for r in q if (r["fy"], r["q"]) == (2026, 2)] == [None]
    t = peers.ttm(q)
    assert [r["consecutive"] for r in t[-3:]] == [True, False, False]   # Q1 FY26's window ends before the hole
    assert all(r["ttm"] is None for r in t[-2:])


def test_weekly_close_is_last_close_on_or_before_the_week(tmp_path):
    p = tmp_path / "abt_us_d.csv"
    p.write_text("Date,Open,High,Low,Close,Volume\n2026-01-05,1,1,1,100,1\n2026-01-07,1,1,1,102,1\n")
    closes = peers.load_closes(str(p))
    assert peers.close_on(closes, dt.date(2026, 1, 9)) == 102
    assert peers.close_on(closes, dt.date(2026, 1, 4)) is None
