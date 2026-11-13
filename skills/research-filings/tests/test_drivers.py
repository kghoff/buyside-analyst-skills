from drivers import anatomy, cost_behavior, fcf_bridge, fy, price_volume, profit_bridge, seasonality, sensitivity


def S(**metrics):
    return {m: dict(v) for m, v in metrics.items()}


BASE = S(rev={"FY2023": 1000, "FY2024": 1200}, cogs={"FY2023": -400, "FY2024": -456},
         rd={"FY2023": -200, "FY2024": -216}, sga={"FY2023": -150, "FY2024": -168},
         oi={"FY2023": 250, "FY2024": 360})


def test_profit_bridge_pieces_add_up_to_the_change_in_operating_income():
    # the bridge is how we find which line items actually moved profit; it must reconcile exactly
    b = profit_bridge(BASE, "rev", "cogs", ["rd", "sga"], "oi", [2024])[0]
    parts = b["revenue_growth"] + b["gross_margin"] + b["rd"] + b["sga"]
    assert abs(b["change"] - 110) < 1e-9 and abs(parts - 110) < 1e-9 and abs(b["other"]) < 1e-9
    assert abs(b["revenue_growth"] - 120) < 1e-9         # +200 revenue at last year's 60% gross margin


def test_a_line_left_out_of_the_bridge_shows_up_as_other_not_hidden():
    s = S(**BASE)
    s["oi"] = {"FY2023": 250, "FY2024": 330}               # a 30 restructuring charge not listed
    assert abs(profit_bridge(s, "rev", "cogs", ["rd", "sga"], "oi", [2024])[0]["other"] + 30) < 1e-9


def test_anatomy_contributions_sum_to_one_when_parts_sum_to_total():
    s = S(tot={"FY2023": 100, "FY2024": 130}, us={"FY2023": 70, "FY2024": 80}, intl={"FY2023": 30, "FY2024": 50})
    row = anatomy(s, "tot", ["us", "intl"], [2024])[0]
    assert abs(row["parts"]["intl"]["contribution"] - 20 / 30) < 1e-9
    assert abs(sum(p["contribution"] for p in row["parts"].values()) - 1) < 1e-9 and abs(row["sum_check"]) < 1e-9


def test_anatomy_flags_splits_that_do_not_add_to_revenue():
    s = S(tot={"FY2024": 100}, us={"FY2024": 60}, intl={"FY2024": 30})
    assert abs(anatomy(s, "tot", ["us", "intl"], [2024])[0]["sum_check"] + 0.10) < 1e-9


def test_price_volume_splits_growth_into_units_and_revenue_per_unit():
    s = S(rev={"FY2023": 100, "FY2024": 132}, u={"FY2022": 9, "FY2023": 11, "FY2024": 13})
    row = price_volume(s, "rev", "u", [2024])[0]
    assert abs((1 + row["unit_growth"]) * (1 + row["price_growth"]) - 1.32) < 1e-9


def test_sensitivity_revenue_flows_through_at_gross_margin_and_is_ranked_by_size():
    rows = sensitivity(BASE, {"revenue": "rev", "cogs": "cogs", "opex": ["rd", "sga"], "operating_income": "oi",
                              "net_income": "oi", "tax_rate": 0.2}, 2024)
    rev = next(r for r in rows if r["driver"] == "rev")
    assert abs(rev["d_oi"] - 0.01 * 1200 * 0.62) < 1e-9
    assert [abs(r["d_oi"]) for r in rows] == sorted((abs(r["d_oi"]) for r in rows), reverse=True)


def test_cost_behavior_tells_fixed_from_variable():
    rev = {f"FY{y}": 100 * (1.1 ** i) for i, y in enumerate(range(2019, 2025))}
    s = S(rev=rev, var={k: -0.4 * v for k, v in rev.items()}, fix={k: -30 for k in rev})
    cls = {c["line"]: c["class"] for c in cost_behavior(s, "rev", ["var", "fix"], 2024)}
    assert cls == {"var": "variable", "fix": "fixed"}


def test_fcf_bridge_reconciles_net_income_to_free_cash_flow():
    s = S(ni={"FY2024": 100}, da={"FY2024": 20}, sbc={"FY2024": 15}, wc={"FY2024": -10}, cfo={"FY2024": 130},
          capex={"FY2024": -40})
    b = fcf_bridge(s, {"net_income": "ni", "da": "da", "sbc": "sbc", "wc": "wc", "cfo": "cfo", "capex": "capex"}, [2024])[0]
    assert (b["other"], b["fcf"], b["conversion"]) == (5, 90, 0.9)


def test_fy_falls_back_to_the_sum_of_four_quarters():
    assert fy(S(x={"Q1 2024": 1, "Q2 2024": 2, "Q3 2024": 3, "Q4 2024": 4}), "x", 2024) == 10


def test_seasonality_quarter_shares_sum_to_one_and_stack_two_years():
    q = {f"Q{i} {y}": v for y, vals in ((2023, [20, 25, 25, 30]), (2024, [22, 28, 30, 40])) for i, v in enumerate(vals, 1)}
    q.update({"Q1 2022": 18})
    out = seasonality(S(r=q), "r", [2023, 2024])
    assert abs(sum(out["avg_share"].values()) - 1) < 1e-9
    assert abs(out["stack"]["Q1 2024"] - ((22 / 20 - 1) + (20 / 18 - 1))) < 1e-9


def test_markdown_escapes_pipes_in_metric_names():
    # metric names look like "SECTION | label"; an unescaped pipe adds phantom columns
    from drivers import to_md
    cfg = {"revenue": "A | B", "cogs": "C", "opex": ["D | E"], "operating_income": "O", "last_year": 2024}
    m = {"config": cfg, "anatomy": {}, "price_volume": {}, "sensitivity": [], "cost_behavior": [],
         "seasonality": {"avg_share": {}, "stack": {}},
         "profit_bridge": [{"year": 2024, "change": 1, "revenue_growth": 1, "gross_margin": 0, "D | E": 0, "other": 0}]}
    hdr = next(l for l in to_md(m).split("\n") if l.startswith("| Year | Change"))
    assert "D \\| E" in hdr and len(hdr.replace("\\|", "").strip("|").split("|")) == 6


def test_fcf_conversion_is_not_meaningful_when_net_income_is_negative():
    s = S(ni={"FY2024": -5}, da={"FY2024": 0}, sbc={"FY2024": 0}, wc={"FY2024": 0}, cfo={"FY2024": 10}, capex={"FY2024": -1})
    b = fcf_bridge(s, {"net_income": "ni", "da": "da", "sbc": "sbc", "wc": "wc", "cfo": "cfo", "capex": "capex"}, [2024])[0]
    assert b["conversion"] is None


def test_last_year_without_full_year_revenue_fails_loudly():
    import pytest
    with pytest.raises(SystemExit):
        sensitivity(BASE, {"revenue": "rev", "cogs": "cogs", "opex": [], "operating_income": "oi"}, 2030)


def test_extra_calcs_appear_in_markdown_with_pipes_escaped_and_absent_otherwise():
    from drivers import to_md
    base = {"config": {"revenue": "r", "cogs": "c", "opex": [], "operating_income": "o", "last_year": 2024}, "anatomy": {},
            "price_volume": {}, "sensitivity": [], "cost_behavior": [], "seasonality": {"avg_share": {}, "stack": {}},
            "profit_bridge": []}
    assert "Extra calcs" not in to_md(base)
    base["extra_calcs"] = [{"name": "A | B", "value": 3.4, "unit": "x", "formula": "a/b", "inputs": "a=1; b=2"},
                           {"name": "Range", "value": "3.4-3.5", "unit": "x", "formula": "f", "inputs": "i"}]
    md = to_md(base)
    assert "## Extra calcs (computed by the main agent from cited inputs)" in md
    assert "| A \\| B | 3.4 | x | a/b | a=1; b=2 |" in md and "| Range | 3.4-3.5 |" in md
