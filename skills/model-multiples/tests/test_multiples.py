import pytest

import multiples as M


def test_abt_raw_pull_row_matches_the_chapter():
    # Chapter 11, "the raw data pull": ABT 10/25/22 = 4.5x EV/Rev, 8.0x EV/GP, 16.7x EV/EBITDA, 21.4x P/E, 5.3% LTM FCF yld.
    ev, mcap = 180480, 171532
    assert round(M.ratio(ev, 40165), 1) == 4.5
    assert round(M.ratio(ev, 22615), 1) == 8.0
    assert round(M.ratio(ev, 10806), 1) == 16.7
    assert round(M.ratio(98, 4.58), 1) == 21.4
    assert round(M.fcf_yield(9017, mcap), 3) == 0.053


def test_negative_or_missing_denominator_is_not_meaningful():
    # Chapter: "20x a negative number produces a negative value ... the P/E is NM". NM must never be a number.
    assert M.ratio(50, -0.13) is None
    assert M.ratio(50, 0) is None
    assert M.ratio(50, None) is None
    assert M.ratio(None, 2) is None


def test_fcf_yield_can_be_negative_but_needs_positive_market_cap():
    assert M.fcf_yield(-10, 100) == -0.1
    assert M.fcf_yield(10, 0) is None


def test_leverage_moves_pe_not_ev_ebitda():
    # Chapter's Business A vs B: same 10x EV/EBITDA, but B's debt makes its P/E look cheaper (16.7x vs 12.1x).
    a = M.six(price=10.0, shares=10, net_debt=0, rev=100, gp=None, ebitda=10, eps=0.60, fcf=None)
    b = M.six(price=5.0, shares=10, net_debt=50, rev=100, gp=None, ebitda=10, eps=0.4125, fcf=None)
    assert a["ev_ebitda"] == b["ev_ebitda"] == 10.0
    assert round(a["pe"], 1) == 16.7 and round(b["pe"], 1) == 12.1


def test_reverse_pe_matches_nvda_example():
    # $438.75 / 45x = $9.75 and / 35x = $12.54 of implied earnings power.
    assert round(M.reverse_pe(438.75, 45.0), 2) == 9.75
    assert round(M.reverse_pe(438.75, 35.0), 2) == 12.54


def test_window_stats_skip_nm_and_rank_today():
    s = [20.0, None, 15.0, 30.0, 25.0]
    w = M.window_stats(s, 4)                      # last 4 points: None, 15, 30, 25
    assert w == {"min": 15.0, "max": 30.0, "median": 25.0, "pct": pytest.approx(2 / 3), "n": 3}
    w = M.window_stats([1.0, None], 2)             # today NM: AGGREGATE still works, only the percentile is #N/A
    assert w["min"] == 1.0 and w["pct"] is None


def test_window_stats_edges():
    assert M.window_stats([None, None], 2) is None
    assert M.window_stats([], 3) is None
    assert M.window_stats([1.0, 2.0], 0) is None
    assert M.window_stats([1.0, 3.0], 10)["n"] == 2          # n larger than the list uses the whole list
    assert M.window_stats([10.0, 20.0, 20.0], 3)["pct"] == 1.0   # tie: today equal to another value counts as <=
    assert M.window_stats([20.0, 10.0, 20.0], 3)["pct"] == 1.0


def test_median_or_none():
    assert M.median_or_none([None, 10.0, 30.0]) == 20.0
    assert M.median_or_none([None]) is None
