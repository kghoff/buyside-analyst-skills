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


# --- The user's 2026-11-18 asks: a line through the peers (chapter 11 "Applying P/E multiples": a name below the line
# is structurally underpriced on the multiple) and an Include toggle so one outlier (TNDM on DXCM) can be left out.
def _pt(t, g, pe):
    return {"ticker": t, "growth1": g, "pe1": pe, **{k: None for k in ("pe0", "ev_rev0", "ev_rev1", "ev_ebitda")}}


PEERS = [_pt("A", 0.04, 14.0), _pt("B", 0.07, 22.0), _pt("C", 0.08, 24.0), _pt("D", 0.12, 26.0), _pt("S", 0.10, 18.0)]


def test_line_fit_reads_the_subject_against_its_peers():
    # The slide's case: peers line up from 14x at 4% to 26x at 12%; the subject at 18x on 10% growth sits under the
    # line, so the market pays it less than its growth earns peers: structurally underpriced.
    f = comps.line_fit(PEERS, {}, "S")
    assert f["n"] == 4                                               # the subject is never one of its own peers
    assert f["slope"] == pytest.approx(0.475 / 0.003275) and f["intercept"] == pytest.approx(21.5 - 0.475 / 0.003275 * 0.0775)
    assert f["fair_pe"] == pytest.approx(f["intercept"] + f["slope"] * 0.10)
    assert f["gap"] < 0 and f["reading"].startswith("Below the line")
    assert f["implied_growth"] == pytest.approx((18.0 - f["intercept"]) / f["slope"])


def test_excluding_an_outlier_moves_the_line_and_the_averages():
    # A 180x peer drags the line and the averages; toggling it off must give back the line without it.
    rows = PEERS + [_pt("T", 0.09, 180.0)]
    with_t, without_t = comps.line_fit(rows, {}, "S"), comps.line_fit(rows, {"T": 0}, "S")
    assert without_t == comps.line_fit(PEERS, {}, "S") and with_t["n"] == 5 and with_t != without_t
    assert comps.stats(rows, {"T": 0})["average"]["pe1"] == pytest.approx(comps.stats(PEERS)["average"]["pe1"])


def test_too_few_peers_or_a_flat_line_says_nothing():
    # Two points always fit a line exactly; a downward line inverts the logic. Neither may be read as cheap or dear.
    few = comps.line_fit(PEERS[:2] + [PEERS[-1]], {}, "S")
    assert few["n"] == 2 and few["fair_pe"] is None and few["reading"].startswith("The line says nothing")
    down = comps.line_fit([_pt("A", 0.04, 26.0), _pt("B", 0.08, 22.0), _pt("C", 0.12, 14.0), PEERS[-1]], {}, "S")
    assert down["slope"] < 0 and down["fair_pe"] is None and down["reading"].startswith("The line says nothing")


def test_outliers_are_flagged_never_excluded():
    # Code only warns (over 2x the peers' median next-year P/E); the user decides by flipping the toggle.
    assert comps.outliers(PEERS + [_pt("T", 0.09, 180.0)], "S") == ["T"]
    assert comps.outliers(PEERS, "S") == []
