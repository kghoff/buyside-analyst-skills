"""The prototype must reproduce the user's accepted DXCM tabs (reference cached values) to ~1e-9. If a rule in engine.py
drifts (window length, look-ahead, release timing, start dates), these fail - that is the point."""
import math

import pandas as pd
import pytest

TOL = 1e-9


def close(a, b):
    if a is None or (isinstance(a, float) and math.isnan(a)):
        return b is None or (isinstance(b, float) and math.isnan(b))
    return b is not None and not (isinstance(b, float) and math.isnan(b)) and abs(a - b) <= TOL * max(1, abs(a))


def by_date(dates, vals):
    return {pd.Timestamp(d): v for d, v in zip(dates, vals)}


def test_daily_rows_and_base_match_reference(dxcm_run, ref_values):
    # same trading days, 2013-12-31 first, index base 2014-12-31 (252-row warm-up)
    assert [d.date().isoformat() for d in dxcm_run["dates"]] == ref_values["dates"]
    assert dxcm_run["dates"][dxcm_run["base"]] == pd.Timestamp("2014-12-31")


@pytest.mark.parametrize("ours,theirs", [("beta", "beta"), ("idio", "idio")])
def test_daily_beta_and_idio(dxcm_run, ref_values, ours, theirs):
    bad = [i for i, (a, b) in enumerate(zip(ref_values["daily"][theirs], dxcm_run[ours])) if not close(a, b)]
    assert not bad, (len(bad), bad[:5])


@pytest.mark.parametrize("ours,theirs", [("ttm_eps", "ttm_eps"), ("rev_g", "ov1"), ("om", "ov2"), ("em", "ov3"),
                                         ("roic", "ov4")])
def test_point_in_time_columns(dxcm_run, ref_values, ours, theirs):
    # values switch the trading day after each full-results release
    ref = ref_values["daily"][theirs]
    bad = [ref_values["dates"][i] for i, (a, b) in enumerate(zip(ref, dxcm_run["daily"][ours])) if i > 252 and not close(a, b)]
    assert not bad, (len(bad), bad[:5])


def test_pe_is_trailing_eps_as_known_that_day(dxcm_run):
    # The user (2026-11-17): historical P/E is LTM, said plainly. Price / the TTM EPS shown that day, #N/A when EPS <= 0.
    # The old NTM P/E divided by the next 4 quarters' actual EPS, which nobody knew at the time.
    D, px, b = dxcm_run["daily"], dxcm_run["px"], dxcm_run["base"]
    for t in range(b + 1, len(px)):
        e = D["ttm_eps"][t]
        want = px[t] / e if not math.isnan(e) and e > 0 else float("nan")
        assert close(want, D["pe"][t]), dxcm_run["dates"][t]


def test_pe_never_uses_a_later_quarter(ref_values, reference_model):
    # Change every quarter reported after 2022-06-30: no P/E on or before that date may move. If this fails, the
    # P/E is seeing the future again.
    import copy, engine, modmap, os
    from conftest import FIX
    ev = ref_values["events"]
    full = {p: pd.Timestamp(d) for p, d in zip(ev["periods"], ev["full_dates"])}
    prices = {k: engine.load_close(os.path.join(FIX, f"{t}_us_d.csv"))
              for k, t in (("stock", "dxcm"), ("spy", "spy"), ("etf", "xhe"), ("mom", "mtum"))}
    cfg = {"oi_role": "oi_ng", "ebitda_role": None, "roic_role": "roic", "eps_role": "eps_ng", "ttm_key": "ttm_n",
           "fcf_role": "fcf", "bb_roles": ["buyback_net"]}
    mod = modmap.read(reference_model)
    cut = pd.Timestamp(2022, 6, 30)
    later = {p for p, d in full.items() if d >= cut}
    mod2 = copy.deepcopy(mod)
    for p in mod2["periods"]:
        if p["label"] in later or (p["kind"] == "fy" and p["year"] >= 2022) or p["est"]:
            if engine.isnum(mod2["values"]["eps_ng"].get(p["label"])):
                mod2["values"]["eps_ng"][p["label"]] *= 3
    a, b2 = engine.run(cfg, prices, mod, full, []), engine.run(cfg, prices, mod2, full, [])
    k = int((a["dates"] <= cut).sum())
    assert all(close(x, y) for x, y in zip(a["daily"]["pe"][:k], b2["daily"]["pe"][:k]))
    assert not all(close(x, y) for x, y in zip(a["daily"]["pe"][k:], b2["daily"]["pe"][k:]))   # the change took


def test_pe_runs_to_the_last_price(dxcm_run):
    # Trailing EPS exists up to today, so the chart does not stop four quarters short (the NTM version did).
    assert engine_isnum(dxcm_run["daily"]["pe"][-1]) and engine_isnum(dxcm_run["monthly"]["pe"][-1])


def engine_isnum(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def test_event_labels_on_reaction_days(dxcm_run, ref_values):
    ref = ref_values["daily"]["event"]
    bad = [ref_values["dates"][i] for i in range(253, len(ref)) if (ref[i] or "") != dxcm_run["label"][i]]
    assert not bad, bad[:5]


def test_handoff_regression_values(dxcm_run):
    # HANDOFF.md section 4 numbers (reference as of 2026-11-04)
    assert round(dxcm_run["beta"][-1], 3) == 0.601
    W = dxcm_run["weekly"]
    assert W["date"][0] == pd.Timestamp("2016-01-08")          # 3-factor starts 2016-01-08
    assert (round(W["b_mkt"][-1], 3), round(W["b_ind"][-1], 3), round(W["b_mom"][-1], 3), round(W["r2"][-1], 3)) == \
        (0.831, 0.696, -0.205, 0.193)
    assert round(W["idx3"][-1], 2) == 137.51
    A = dxcm_run["annual"]
    i = A["fy"].index(2025)
    assert (round(A["fcf"][i], 1), round(A["bb"][i], 1), round(A["pe"][i], 1)) == (1077.2, 471.9, 43.9)  # TTM P/E
    # TTM non-GAAP EPS turns positive with the Q4 2018 release (Feb 2019): no P/E before it, 11 month-ends in 2019
    assert A["n"][A["fy"].index(2018)] == 0 and A["n"][A["fy"].index(2019)] == 11


@pytest.mark.parametrize("ours,theirs", [("b_mkt", "b_mkt"), ("b_ind", "b_ind"), ("b_mom", "b_mom"), ("r2", "r2"),
                                         ("idio3", "idio3"), ("idx3", "idx3"), ("pct3", "pct3"), ("rev_g", "ov1"),
                                         ("om", "ov2"), ("em", "ov3"), ("roic", "ov4")])
def test_weekly_three_factor(dxcm_run, ref_values, ours, theirs):
    W = dxcm_run["weekly"]
    ref = by_date(ref_values["weekly"]["date"], ref_values["weekly"][theirs])
    assert all(pd.Timestamp(d) in ref for d in W["date"])
    bad = [d for d, v in zip(W["date"], W[ours]) if not close(ref[d], v)]
    if ours.startswith("b_") or ours in ("r2", "idio3"):
        bad = [d for d in bad if d != W["date"][0]]              # base row has no regression in either
    assert not bad, (len(bad), bad[:5])


def test_monthly_block(dxcm_run, ref_values):
    M, R = dxcm_run["monthly"], ref_values["monthly"]
    # starts at the first month-end with a P/E (Feb 2019: no TTM EPS before it), then the reference's months.
    # A leading #N/A month would draw as 0x in LibreOffice renders.
    j = R["date"].index("2019-02-28")
    assert engine_isnum(M["pe"][0])
    assert [d.date().isoformat() for d in M["date"]] == R["date"][j:]
    for k in ("close", "ttm_eps"):
        assert all(close(a, b) for a, b in zip(R[k][j:], M[k])), k
    assert all(close(c / e if e > 0 else float("nan"), pe) for c, e, pe in zip(M["close"], M["ttm_eps"], M["pe"]))


def test_annual_block(dxcm_run, ref_values):
    A, R = dxcm_run["annual"], ref_values["annual"]
    assert A["fy"] == R["fy"]
    for k in ("fcf", "bb"):
        assert all(close(a, b) for a, b in zip(R[k], A[k])), k
    # P/E: the average of that year's month-end TTM P/Es (the reference averaged NTM P/Es, so its values differ)
    for y, pe, n in zip(A["fy"], A["pe"], A["n"]):
        xs = [v for d, v in zip(dxcm_run["monthly"]["date"], dxcm_run["monthly"]["pe"]) if d.year == y and not math.isnan(v)]
        assert n == len(xs) and (close(pe, sum(xs) / n) if n else math.isnan(pe)), y


def test_quarter_table(dxcm_run, ref_values):
    Q, R = dxcm_run["quarters"], ref_values["events"]
    assert [q["label"] for q in Q] == R["periods"]
    assert all(close(a, q["ttm_n"]) for a, q in zip(R["ttm_eps_ng"], Q))
    assert all(close(a, q["ttm_rev"]) for a, q in zip(R["ttm_rev"], Q))
    for j, k in enumerate(("rev_g", "om", "em", "roic")):
        assert all(close(a[j], q[k]) for a, q in zip(R["ov"], Q)), k


def test_event_returns(dxcm_run, ref_values):
    for (d, t, nm, tm, react, idio), e in zip(ref_values["events"]["list"], dxcm_run["events"]):
        assert e["reaction"] == pd.Timestamp(react), nm
        if idio is not None:
            assert close(idio, e["idio"]), nm


def test_fcf_chart_pe_groups_month_ends_by_fiscal_year(dxcm_run, ref_values, reference_model):
    # MDT's year ends in April: its FY26 P/E must average May 2025 - April 2026 month-ends, not calendar 2026
    # (calendar grouping blanked MDT's FY26 point and shifted every other year by 4 months)
    import engine, modmap, os
    from conftest import FIX
    ev = ref_values["events"]
    full = {p: pd.Timestamp(d) for p, d in zip(ev["periods"], ev["full_dates"])}
    prices = {k: engine.load_close(os.path.join(FIX, f"{t}_us_d.csv"))
              for k, t in (("stock", "dxcm"), ("spy", "spy"), ("etf", "xhe"), ("mom", "mtum"))}
    cfg = {"oi_role": "oi_ng", "ebitda_role": None, "roic_role": "roic", "eps_role": "eps_ng", "ttm_key": "ttm_n",
           "fcf_role": "fcf", "bb_roles": ["buyback_net"], "fye_month": 4}
    run = engine.run(cfg, prices, modmap.read(reference_model), full, [])
    M, A = run["monthly"], run["annual"]
    want = [v for d, v in zip(M["date"], M["pe"]) if pd.Timestamp(2024, 5, 1) <= d <= pd.Timestamp(2025, 4, 30) and engine.isnum(v)]
    i = A["fy"].index(2025)
    assert A["n"][i] == len(want) and abs(A["pe"][i] - sum(want) / len(want)) < 1e-12
    assert A["n"] != dxcm_run["annual"]["n"]              # different from the calendar-year (December) grouping


def test_pe_uses_the_traded_price_and_returns_use_total_return(ref_values, reference_model):
    """Why: stooq/Yahoo dividend-adjusted prices understate a dividend payer's old P/E. P/E must divide the TRADED
    close; returns (beta, idio, alpha) must use the total-return series. Swap either and this fails."""
    import os
    import numpy as np
    import engine
    import modmap
    from conftest import FIX
    mod = modmap.read(reference_model)
    ev = ref_values["events"]
    full = {p: pd.Timestamp(d) for p, d in zip(ev["periods"], ev["full_dates"])}
    load = lambda t: engine.load_close(os.path.join(FIX, f"{t}_us_d.csv"))
    stock = load("dxcm")
    tr = stock * np.linspace(0.8, 1.0, len(stock))          # a made-up dividend history: past prices scaled down
    prices = {"stock": stock, "stock_tr": tr, "spy": load("spy"), "etf": load("xhe"), "mom": load("mtum")}
    cfg = {"oi_role": "oi_ng", "ebitda_role": "ebitda_ng", "roic_role": "roic", "eps_role": "eps_ng",
           "ttm_key": "ttm_n", "fcf_role": "fcf", "bb_roles": ["buyback_net"]}
    run = engine.run(cfg, prices, mod, full, [])
    d = run["dates"]
    pe = run["daily"]["pe"]
    ok = [i for i in range(run["base"], len(d)) if engine.isnum(pe[i])]
    t = ok[len(ok) // 2]                  # mid-series: the fake tr factor is below 1 here, so tr and close differ
    assert tr.reindex(d).iloc[t] != pytest.approx(stock.reindex(d).iloc[t], rel=1e-3)
    assert run["px"][t] == pytest.approx(stock.reindex(d).iloc[t])                     # plain close kept for P/E
    e = run["daily"]["ttm_eps"][t]
    assert run["daily"]["pe"][t] == pytest.approx(stock.reindex(d).iloc[t] / e)
    trd = tr.reindex(d)
    assert run["r"][t] == pytest.approx(trd.iloc[t] / trd.iloc[t - 1] - 1)              # returns on total return
    assert run["tr"][t] == pytest.approx(trd.iloc[t])
