# tests/test_ratings.py
from datetime import date

import firms
import ratings
from conftest import snap

F = firms.Firms()


def h(day, firm, action, frm, to, pf=None, pt=None, hour="15:00:00"):
    return {"epochGradeDate": f"{day}T{hour}.000Z", "firm": firm, "action": action, "fromGrade": frm, "toGrade": to,
            "priorPriceTarget": pf, "currentPriceTarget": pt}


def S(history, splits=(), asof="2026-11-12"):
    return {"asof": asof, "yahoo": {"history": history}, "splits": list(splits)}


def test_evening_utc_timestamps_are_the_us_trading_day():
    # Yahoo stamps in UTC: 01:58 UTC on 31 Oct is the evening of 30 Oct in New York
    a = ratings.actions(S([h("2026-10-31", "UBS", "main", "Buy", "Buy", 102, 107, hour="01:58:43")]), F)
    assert a[0]["date"] == date(2026, 10, 30)


def test_targets_before_a_split_are_divided_by_the_ratio():
    # closes in Px Data are split-adjusted, so pre-split targets must be too
    a = ratings.actions(S([h("2022-03-01", "UBS", "main", "Buy", "Buy", 400, 480),
                           h("2022-08-01", "UBS", "main", "Buy", "Buy", 120, 130)],
                          splits=[{"date": "2022-06-13", "ratio": 4}]), F)
    old = next(x for x in a if x["date"].year == 2022 and x["date"].month == 3)
    new = next(x for x in a if x["date"].month == 8)
    assert (old["pt_from"], old["pt_to"], old["split_adj"]) == (100, 120, True)
    assert (new["pt_to"], new["split_adj"]) == (130, False)


def test_action_kinds():
    a = ratings.actions(S([h("2026-01-02", "UBS", "up", "Neutral", "Buy"), h("2026-01-03", "Citi", "down", "Buy", "Neutral"),
                           h("2026-01-04", "BTIG", "init", "", "Buy", None, 90), h("2026-01-05", "Barclays", "main", "Overweight", "Overweight", 115, 120),
                           h("2026-01-06", "Mizuho", "main", "Neutral", "Neutral", 80, 80), h("2026-01-07", "Baird", "reit", "Outperform", "Outperform")]), F)
    kinds = {x["firm"]: x["kind"] for x in a}
    assert kinds == {"UBS": "Upgrade", "Citi": "Downgrade", "BTIG": "Initiation", "Barclays": "Target change",
                     "Mizuho": "Maintains", "Baird": "Reiterate"}


def test_latest_by_firm_keeps_the_last_target_and_drops_silent_firms():
    a = ratings.actions(S([h("2026-10-01", "UBS", "main", "Buy", "Buy", 100, 110),
                           h("2026-11-01", "UBS", "reit", "Buy", "Buy"),          # no target on the newest action
                           h("2024-01-05", "Citi", "main", "Buy", "Buy", 50, 60)]), F)
    rows, dropped = ratings.latest_by_firm(a, date(2026, 11, 12))
    ubs = next(r for r in rows if r["firm"] == "UBS")
    assert ubs["kind"] == "Reiterate" and ubs["pt"] == 110
    assert [d["firm"] for d in dropped] == ["Citi"]           # silent for more than 12 months


def test_split_types_separates_analysts_shops_and_unknowns():
    a = ratings.actions(S([h("2026-10-01", "UBS", "main", "Buy", "Buy", 100, 110),
                           h("2026-10-02", "Morningstar", "main", "", "4 stars"),
                           h("2026-10-03", "Mystery Partners", "init", "", "Buy")]), F)
    rows, _ = ratings.latest_by_firm(a, date(2026, 11, 12))
    an, shops, unknown = ratings.split_types(rows)
    assert [r["firm"] for r in an] == ["UBS"]
    assert [r["firm"] for r in shops] == ["Morningstar"]
    assert [r["firm"] for r in unknown] == ["Mystery Partners"]


def test_log_keeps_five_years_newest_first():
    a = ratings.actions(S([h("2020-01-02", "UBS", "up", "Neutral", "Buy"), h("2026-01-02", "Citi", "down", "Buy", "Neutral"),
                           h("2023-05-02", "BTIG", "init", "", "Buy")]), F)
    lg = ratings.log(a, date(2026, 11, 12))
    assert [x["firm"] for x in lg] == ["Citi", "BTIG"]


def test_average_target_uses_each_live_firms_latest_target():
    a = ratings.actions(S([h("2026-01-02", "UBS", "main", "Buy", "Buy", 90, 100),
                           h("2026-02-02", "Citi", "main", "Buy", "Buy", 70, 80),
                           h("2026-03-02", "UBS", "main", "Buy", "Buy", 100, 120)]), F)
    days = [date(2026, 1, 1), date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15), date(2027, 4, 15)]
    assert ratings.avg_pt(a, days) == [None, 100, 90, 100, None]   # 2027-04-15: both targets older than 12 months


def test_real_snapshot_runs_end_to_end():
    s = snap("DXCM")
    a = ratings.actions(s, F)
    rows, _ = ratings.latest_by_firm(a, date.fromisoformat(s["asof"]))
    an, _, _ = ratings.split_types(rows)
    assert len(an) >= 5 and all(r["pt"] is None or r["pt"] > 0 for r in an)


def _find(acts, d, firm):
    return next(a for a in acts if str(a["date"]) == d and a["firm"] == firm)


def test_first_action_after_a_split_with_a_presplit_prior_is_adjusted():
    # Yahoo leaves the prior target in pre-split dollars on a firm's first post-split action (SENS 1:20 reverse split)
    a = ratings.actions(snap("SENS"), F)
    hc = _find(a, "2025-11-06", "H.C. Wainwright")
    assert abs(hc["pt_from"] - 28) < 0.01 and hc["pt_to"] < hc["pt_from"]
    assert hc["kind"] == "Target change"
    bc = _find(a, "2025-11-05", "Barclays")
    assert abs(bc["pt_from"] - 30) < 0.01
    assert bc["pt_from"] == round(bc["pt_from"], 4)


def test_prior_already_post_split_is_left_alone():
    td = _find(ratings.actions(snap("SENS"), F), "2025-11-05", "TD Cowen")
    assert td["pt_from"] == 25 and td["pt_to"] == 15


def test_adjusts_is_a_mechanical_split_adjustment_not_a_target_change():
    ms = _find(ratings.actions(snap("DXCM"), F), "2022-06-13", "Morgan Stanley")
    assert ms["kind"] == "Maintains" and abs(ms["pt_from"] - 90.75) < 0.01


def test_nasdaq_covering_lists_analyst_firms_missing_from_yahoo_rows():
    s = snap("dxcm")
    rows, _ = ratings.latest_by_firm(ratings.actions(s, F), date.fromisoformat(s["asof"]))
    extra = ratings.nasdaq_covering(s, F, rows)
    assert "William Blair" in extra                          # last Yahoo action 2017, Nasdaq still lists it
    assert not set(extra) & {r["firm"] for r in rows}
    assert extra == sorted(extra)
    assert ratings.nasdaq_covering({"asof": s["asof"]}, F, rows) == []
