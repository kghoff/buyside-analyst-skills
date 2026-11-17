import datetime as dt

import pytest

import engine
import importer

Q = [{"label": "Q1 24", "date": dt.date(2024, 4, 25), "rev": (100.0, ""), "gp": (60.0, ""), "ebitda": (20.0, ""),
      "eps": (1.0, ""), "eps_gaap": (1.0, ""), "fcf": (10.0, ""), "shares": (10.0, ""), "net_debt": (50.0, "")},
     {"label": "Q2 24", "date": dt.date(2024, 7, 25), "rev": (110.0, ""), "gp": (66.0, ""), "ebitda": (-5.0, ""),
      "eps": (2.0, ""), "eps_gaap": (2.0, ""), "fcf": (12.0, ""), "shares": (10.0, ""), "net_debt": (40.0, "")}]
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


def test_relative_rows_compare_gaap_with_gaap_on_a_non_gaap_basis():
    # multpl's S&P P/E and the peers' XBRL EPS are reported (GAAP) earnings. With a non-GAAP subject P/E, the
    # relative rows must use the subject's GAAP P/E, or they'd mix an adjusted multiple with reported ones.
    q = [dict(x, eps_gaap=(x["eps"][0] / 2, "")) for x in Q]            # GAAP EPS half the adjusted figure
    peer = {"AAA": {"closes": [(dt.date(2024, 1, 1), 50.0)], "ttm": [{"known": dt.date(2024, 3, 1), "ttm": 2.5}]}}
    r = engine.free_weekly(q, W, SP, peer)[2]
    assert r["pe"] == pytest.approx(20.0) and r["pe_gaap"] == pytest.approx(40.0)    # 40 / 2.0 and 40 / 1.0
    assert r["rel_sp"] == pytest.approx(40.0 - 25.0) and r["rel_peer"] == pytest.approx(40.0 - 20.0)


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


def test_paid_weekly_from_real_importer_output(tmp_path):
    subj = tmp_path / "s.csv"
    subj.write_text("Date,Price,EPS,EV,Sales,S&P 500 NTM P/E\n2024-01-05,20,2,,100,15\n2024-01-12,30,2,300,100,16\n")
    peer = tmp_path / "p.csv"
    peer.write_text("Date,Price,EPS\n2024-01-12,50,2.5\n")
    bad = tmp_path / "b.csv"
    bad.write_text("Date,Price,EPS\n2024-01-05,50,0\n2024-01-12,50,-1\n")
    rows = engine.paid_weekly(importer.load(str(subj)), {"AAA": importer.load(str(peer)),
                                                         "BBB": importer.load(str(bad))})
    a, b = rows
    assert a["pe"] == pytest.approx(10.0) and a["ev_rev"] is None and a["ev_ebitda"] is None   # no EV -> NM
    assert b["ev_rev"] == pytest.approx(3.0)
    assert a["rel_sp"] == pytest.approx(10.0 - 15.0) and b["rel_sp"] == pytest.approx(15.0 - 16.0)
    assert a["peer_pe"]["AAA"] is None and a["peer_px"]["AAA"] is None      # peer export starts after this week
    assert b["peer_pe"]["AAA"] == pytest.approx(20.0)
    assert a["peer_pe"]["BBB"] is None and b["peer_pe"]["BBB"] is None      # eps <= 0 -> NM
    assert b["peer_med"] == 20.0 and b["rel_peer"] == pytest.approx(15.0 - 20.0) and a["peer_med"] is None


def test_ranges_take_extra_keys_for_the_paid_paths_forward_fcf_yield():
    # The paid path ranges NTM FCF yield too; the default keys stay the free path's seven (no forward-FCF history).
    rows = [{"fcf_yield_ntm": v} for v in (0.02, 0.04, 0.03)]
    rg = engine.ranges(rows, windows=(3,), keys=engine.KEYS + ("fcf_yield_ntm",))
    assert rg["fcf_yield_ntm"][3]["median"] == 0.03 and rg["fcf_yield_ntm"][3]["pct"] == pytest.approx(2 / 3)
    assert "fcf_yield_ntm" not in engine.ranges(rows, windows=(3,))
