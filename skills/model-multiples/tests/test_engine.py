import datetime as dt

import pytest

import engine

Q = [{"label": "Q1 24", "date": dt.date(2024, 4, 25), "rev": (100.0, ""), "gp": (60.0, ""), "ebitda": (20.0, ""),
      "eps": (1.0, ""), "fcf": (10.0, ""), "shares": (10.0, ""), "net_debt": (50.0, "")},
     {"label": "Q2 24", "date": dt.date(2024, 7, 25), "rev": (110.0, ""), "gp": (66.0, ""), "ebitda": (-5.0, ""),
      "eps": (2.0, ""), "fcf": (12.0, ""), "shares": (10.0, ""), "net_debt": (40.0, "")}]
W = [(dt.date(2024, 4, 26), 20.0, 10, "B"), (dt.date(2024, 7, 25), 30.0, 11, "B"), (dt.date(2024, 7, 26), 40.0, 12, "B")]
SP = [{"date": dt.date(2024, 4, 1), "pe": 20.0, "estimate": False}, {"date": dt.date(2024, 7, 1), "pe": 25.0, "estimate": False}]


def test_free_weekly_uses_quarter_known_before_the_week_and_nm_ebitda():
    rows = engine.free_weekly(Q, W, SP, {})
    assert rows[0]["q"] == 0 and rows[0]["pe"] == pytest.approx(20.0)            # Q1 known (released 4/25)
    assert rows[1]["q"] == 0                                                      # release day: still Q1
    assert rows[2]["q"] == 1 and rows[2]["pe"] == pytest.approx(20.0)             # 40 / 2.0
    assert rows[2]["ev_ebitda"] is None                                           # negative EBITDA -> NM
    assert rows[2]["ev"] == pytest.approx(440.0) and rows[2]["rel_sp"] == pytest.approx(-5.0)


def test_peer_median_ignores_nm_peers():
    peer = {"AAA": {"closes": [(dt.date(2024, 1, 1), 50.0)],
                    "ttm": [{"known": dt.date(2024, 3, 1), "ttm": 2.5}]},
            "BBB": {"closes": [(dt.date(2024, 1, 1), 50.0)],
                    "ttm": [{"known": dt.date(2024, 3, 1), "ttm": -1.0}]}}
    rows = engine.free_weekly(Q, W, SP, peer)
    assert rows[0]["peer_pe"] == {"AAA": 20.0, "BBB": None}
    assert rows[0]["peer_med"] == 20.0 and rows[0]["rel_peer"] == pytest.approx(0.0)


def test_ranges_and_reverse_pe_from_weekly_rows():
    rows = [{"price": 10.0, "pe": v, "ev_ebitda": None, "ev_rev": None, "ev_gp": None, "fcf_yield": None,
             "rel_sp": None, "rel_peer": None} for v in (10.0, 20.0, 30.0, 40.0)]
    rg = engine.ranges(rows, windows=(2, 4))
    assert rg["pe"][4]["median"] == 25.0 and rg["pe"][2]["min"] == 30.0
    assert engine.reverse(rows, rg)[4]["min"] == pytest.approx(10.0 / 10.0)


def test_peer_with_none_ttm_at_latest_known_quarter_gives_none_no_fallback():
    peer = {"AAA": {"closes": [(dt.date(2024, 1, 1), 50.0)],
                    "ttm": [{"known": dt.date(2024, 3, 1), "ttm": 2.5}, {"known": dt.date(2024, 4, 1), "ttm": None}]}}
    rows = engine.free_weekly(Q, W, SP, peer)
    assert rows[0]["peer_pe"] == {"AAA": None} and rows[0]["peer_med"] is None and rows[0]["rel_peer"] is None


def test_ranges_and_reverse_survive_nm_today():
    rows = [{"price": 10.0, "pe": v, "ev_ebitda": None, "ev_rev": None, "ev_gp": None, "fcf_yield": None,
             "rel_sp": None, "rel_peer": None} for v in (10.0, 20.0, None)]
    rg = engine.ranges(rows, windows=(3,))
    assert rg["pe"][3]["pct"] is None and rg["pe"][3]["median"] == 15.0
    assert engine.reverse(rows, rg)[3]["max"] == pytest.approx(0.5)
