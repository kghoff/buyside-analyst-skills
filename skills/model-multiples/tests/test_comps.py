import pytest

import comps


def snap(t, price=100.0, mcap=1e10, debt=2e9, cash=1e9, eps0=2.0, eps1=2.5, rev0=4e9, rev1=4.4e9, ebitda=1e9,
         cur="USD", fcur="USD"):
    return {"ticker": t, "asof": "2026-11-17", "price": price, "currency": cur, "marketCap": mcap, "adv3m": 2e6,
            "financial": {"totalDebt": debt, "totalCash": cash, "ebitda": ebitda, "financialCurrency": fcur},
            "trend": [{"period": "0y", "endDate": "2026-12-31T00:00:00.000Z",
                       "earningsEstimate": {"avg": eps0}, "revenueEstimate": {"avg": rev0}},
                      {"period": "+1y", "endDate": "2027-12-31T00:00:00.000Z",
                       "earningsEstimate": {"avg": eps1}, "revenueEstimate": {"avg": rev1}}]}


def test_row_multiples():
    r = comps.row(snap("AAA"), group="Peers")
    assert r["ev"] == 1.1e10                                     # mcap + debt - cash
    assert r["pe1"] == pytest.approx(40.0) and r["ev_rev1"] == pytest.approx(1.1e10 / 4.4e9)
    assert r["ev_ebitda"] == pytest.approx(11.0)
    assert r["growth1"] == pytest.approx(0.10)
    assert r["fy0"] == 2026 and r["fy1"] == 2027


def test_missing_debt_and_cash_count_as_zero_on_both_sides():
    s = snap("NOD")
    s["financial"].pop("totalDebt"); s["financial"].pop("totalCash")
    r = comps.row(s, "Peers")
    assert r["debt"] == 0 and r["cash"] == 0 and r["ev"] == 1e10


def test_unprofitable_comp_is_nm_not_negative():
    r = comps.row(snap("TND", eps0=-1.0, eps1=-0.5, ebitda=-1e8), group="Peers")
    assert r["pe0"] is None and r["pe1"] is None and r["ev_ebitda"] is None


def test_currency_mismatch_is_flagged_and_left_nm():
    # An ADR priced in USD with financials in another currency: EV-based multiples would be nonsense.
    r = comps.row(snap("ADR", fcur="EUR"), group="Peers")
    assert r["warning"] and r["ev_rev1"] is None and r["ev_ebitda"] is None


def test_failed_fetch_kept_as_a_visible_row():
    r = comps.row({"ticker": "BAD", "asof": "2026-11-17", "error": "404"}, group="Peers")
    assert r["warning"].startswith("Yahoo fetch failed")
    assert r["ticker"] == "BAD" and r["pe1"] is None


def test_rank_by_next_year_pe_nm_last_and_stats_skip_nm():
    rows = [comps.row(snap("A", eps1=5.0), "g"), comps.row(snap("B", eps1=-1.0), "g"), comps.row(snap("C", eps1=2.0), "g")]
    ranked = comps.rank(rows)
    assert [r["ticker"] for r in ranked] == ["C", "A", "B"]
    st = comps.stats(ranked)
    assert st["median"]["pe1"] == pytest.approx(35.0) and st["average"]["pe1"] == pytest.approx(35.0)


def test_empty_yahoo_snapshot_is_a_visible_failed_row():
    r = comps.row({"ticker": "EMP", "asof": "2026-11-17", "error": "Yahoo returned no price / market cap"}, "g")
    assert r["warning"].startswith("Yahoo fetch failed") and r["pe1"] is None and r["ev_ebitda"] is None


def test_soft_warnings_are_visible_but_keep_ev_multiples():
    s = snap("SOFT")
    s["financial"].pop("financialCurrency"); s["financial"].pop("totalDebt")
    r = comps.row(s, "g")
    assert "financial currency not reported; assumed same as price" in r["warning"]
    assert "total debt not reported; EV assumes 0" in r["warning"] and "; " in r["warning"]
    assert r["ccy_mismatch"] is False and r["ev_ebitda"] is not None and r["ev_rev1"] is not None


def test_currency_mismatch_sets_flag_only_then():
    assert comps.row(snap("A", fcur="EUR"), "g")["ccy_mismatch"] is True
    assert comps.row(snap("B"), "g")["ccy_mismatch"] is False and comps.row(snap("B"), "g")["warning"] is None


def test_nonpositive_rev0_gives_no_growth():
    assert comps.row(snap("Z", rev0=0), "g")["growth1"] is None
    assert comps.row(snap("N", rev0=-5e9), "g")["growth1"] is None
