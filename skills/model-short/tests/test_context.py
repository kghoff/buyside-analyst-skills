# skills/model-short/tests/test_context.py
"""context.py's numbers are recomputed here from make_fixture.series() (not from context's own code), and each
formula it hands build.py must name the same MOD cells. A wrong row or quarter window shows up as a wrong number."""
import json
import os
import re

import pytest

import make_fixture as mf

A = pytest.approx


def _sum(s, key, idx):
    return sum(s[key][i] for i in idx)


@pytest.fixture(scope="module")
def ctx(work_base):
    return json.load(open(os.path.join(work_base, "context.json")))


def test_quarter_windows_are_the_last_reported(ctx):
    assert ctx["mod"]["periods"]["last4"] == ["Q1 25", "Q2 25", "Q3 25", "Q4 25"]
    assert ctx["mod"]["periods"]["ntm"] == ["Q1 26E", "Q2 26E", "Q3 26E", "Q4 26E"]


def test_fundamentals_match_an_independent_recompute(ctx):
    s, m = mf.series(), ctx["metrics"]
    act = [i for i, q in enumerate(s["q"]) if not q.endswith("E")]
    fq = [i for i, q in enumerate(s["q"]) if q.endswith("E")]
    L, P, PP, F20 = act[-4:], act[-8:-4], act[-12:-8], act[-20:]
    g_now = _sum(s, "rev", L) / _sum(s, "rev", P) - 1
    g_ago = _sum(s, "rev", P) / _sum(s, "rev", PP) - 1
    assert m["decel"]["value"] == A(g_now - g_ago)
    assert m["incr"]["value"] == A((_sum(s, "oi", L) - _sum(s, "oi", P)) / (_sum(s, "rev", L) - _sum(s, "rev", P)))
    assert m["opm"]["value"] == A(_sum(s, "oi", L) / _sum(s, "rev", L))
    assert m["capex_da"]["value"] == A(abs(_sum(s, "capex", L)) / _sum(s, "da", L))
    assert m["acq_cfo"]["value"] == A(abs(_sum(s, "acq", F20)) / _sum(s, "cfo", F20))
    assert m["fcf_conv"]["value"] == A(_sum(s, "fcf", F20) / _sum(s, "ni_adj", F20))   # the non-GAAP row wins
    assert m["ntm_eps"]["value"] == A(_sum(s, "eps", fq[:4]))
    assert m["ntm_growth"]["value"] == A(_sum(s, "eps", fq[4:8]) / _sum(s, "eps", fq[:4]) - 1)
    assert m["eps_cagr3"]["value"] == A((_sum(s, "eps", fq[12:16]) / _sum(s, "eps", fq[:4])) ** (1 / 3) - 1)
    assert m["peak_ratio"]["value"] == A(1.0)                    # TTM margin = the 2025 FY peak (20%)


def test_formulas_cite_mod_cells_and_are_wrapped(ctx):
    f = ctx["metrics"]["capex_da"]["formula"]
    assert f.startswith("IFERROR(") and f.endswith(",NA())")
    assert re.search(r"MOD!\$[A-Z]+\$18", f) and re.search(r"MOD!\$[A-Z]+\$12", f)   # capex row 18, D&A row 12


def test_links_found_by_label(ctx):
    L = ctx["links"]
    assert L["pe_today"] == {"ref": "Multiples!$B$7", "value": 30.0}
    assert L["pe_pct"]["ref"] == "Multiples!$J$7" and L["peer_pct"]["value"] == 0.75
    assert L["dcf_base"] == {"ref": "Valuation!$C$107", "value": 42.0}
    assert L["valuation_price"]["value"] == 50.0
    # the latest snapshot's next fiscal year (the larger FY label), oldest vs latest snapshot: FY 2027, 2.30 -> 2.20
    assert L["rev_first"]["value"] == 2.30 and L["rev_last"]["value"] == 2.20
    assert ctx["metrics"]["revision"]["value"] == A(2.20 / 2.30 - 1)
    assert ctx["metrics"]["earn_move"]["value"] == A(0.065)        # median |idio| of the 4 earnings days


def test_price_short_data_stale_check_and_code_ticks(ctx):
    assert ctx["price"]["value"] == 51.0 and "Yahoo" in ctx["price"]["source"]
    assert ctx["stale"]["flag"] is False                           # 51 vs 50: 2%, inside 3%
    assert ctx["short"]["short_pct_float"] == 0.04
    t = ctx["code_ticks"]
    assert t["decel"] == "yes" and t["capex"] == "yes" and t["leaky"] == "no" and t["fcf"] == "yes"
    assert t["vs_dcf"] == "yes" and t["vs_history"] == "yes" and t["revisions"] == "yes"
    assert ctx["house"] == {"hurdle": 0.08, "fund": 1000.0, "bps": 50.0, "short_book": 500.0, "crowded_line": 0.10,
                            "print_miss": -0.05, "print_pe_slip": 1.0}


def test_missing_optional_tab_is_listed_not_fatal(fixture_model, tmp_path):
    import openpyxl
    import context
    m = str(tmp_path / "m.xlsx")
    wb = openpyxl.load_workbook(fixture_model)
    del wb["Valuation"], wb["Consensus"]
    wb.save(m)
    (tmp_path / "short.json").write_text(json.dumps({"ticker": "TEST", "asof": "2026-11-18", "error": "timeout"}))
    c = context.run(m, str(tmp_path), "TEST", values=m)
    assert c["missing"] == ["Valuation", "Consensus"]
    assert "dcf_base" not in c["links"] and c["code_ticks"]["vs_dcf"] == "unknown"
    assert c["price"]["value"] is None and "Yahoo failed" in c["price"]["source"]


def test_missing_required_tab_stops(fixture_model, tmp_path):
    import openpyxl
    import context
    m = str(tmp_path / "m.xlsx")
    wb = openpyxl.load_workbook(fixture_model)
    del wb["Multiples"]
    wb.save(m)
    with pytest.raises(SystemExit, match="model-multiples"):
        context.run(m, str(tmp_path), "TEST", values=m)


def test_link_to_a_blank_cell_is_not_recorded(fixture_model, tmp_path):
    """A blank cell shows as 0 in Excel but None in Python: recording the link would make verify fail and the tick
    wrong. A link is kept only when its cell holds a number; the row's tick is then ?."""
    import openpyxl
    import context
    m = str(tmp_path / "m.xlsx")
    wb = openpyxl.load_workbook(fixture_model)
    wb["Multiples"]["J7"] = None
    wb.save(m)
    (tmp_path / "short.json").write_text(json.dumps(mf.SHORT))
    c = context.run(m, str(tmp_path), "TEST", values=m)
    assert "pe_pct" not in c["links"] and "pe_today" in c["links"]
    assert c["code_ticks"]["vs_history"] == "unknown"


def _consensus(rows):
    """A Consensus tab grid (row, col) -> value with the "5. CONSENSUS SNAPSHOTS" block holding rows."""
    g = {(10, 1): "5. CONSENSUS SNAPSHOTS", (11, 1): "Snapshot", (11, 2): "Period", (11, 3): "EPS mean"}
    for k, (snap, per, eps) in enumerate(rows, start=12):
        g[(k, 1)], g[(k, 2)], g[(k, 3)] = snap, per, eps
    return g


def test_revisions_follow_the_live_period_not_the_most_snapshotted():
    """Once FY 2026 is reported it stops being revised: its many old snapshots must not win over the period the Street
    is estimating now. The latest snapshot's next fiscal year is used, oldest snapshot vs latest."""
    import context
    rows = [("2026-02-01", "FY 2026", 2.10), ("2026-05-01", "FY 2026", 2.05), ("2026-08-01", "FY 2026", 2.00),
            ("2026-08-01", "FY 2027", 2.40), ("2027-02-01", "FY 2027", 2.25), ("2027-02-01", "FY 2028", 2.60)]
    L = context.consensus_links(_consensus(rows))
    assert L["rev_first"]["period"] == "FY 2027"                   # FY 2028 has one snapshot; FY 2027 is next in line
    assert (L["rev_first"]["value"], L["rev_last"]["value"]) == (2.40, 2.25)
    assert (L["rev_first"]["snapshot"], L["rev_last"]["snapshot"]) == ("2026-08-01", "2027-02-01")
    rows.append(("2027-05-01", "FY 2028", 2.50))                     # now FY 2028 has two: the next year wins
    rows.append(("2027-05-01", "FY 2027", 2.20))
    L = context.consensus_links(_consensus(rows))
    assert L["rev_first"]["period"] == "FY 2028" and (L["rev_first"]["value"], L["rev_last"]["value"]) == (2.60, 2.50)


def test_revisions_with_non_fy_labels_use_the_latest_snapshots_last_period():
    import context
    rows = [("2026-02-01", "Old", 9.5), ("2026-05-01", "Old", 9.2), ("2026-08-01", "Old", 9.0),
            ("2026-08-01", "NTM", 3.00), ("2026-08-01", "Next quarter", 0.70),
            ("2026-11-01", "Next quarter", 0.65), ("2026-11-01", "NTM", 2.90)]
    L = context.consensus_links(_consensus(rows))
    assert L["rev_first"]["period"] == "NTM" and (L["rev_first"]["value"], L["rev_last"]["value"]) == (3.00, 2.90)


def _variant(fixture_model, tmp_path, edit):
    """context.run on a copy of the fixture after edit(wb, cols) ({period label: column} of MOD row 2)."""
    import openpyxl
    import context
    m = str(tmp_path / "m.xlsx")
    wb = openpyxl.load_workbook(fixture_model)
    cols = {str(c.value): c.column for c in wb["MOD"][2] if c.value is not None}
    edit(wb, cols)
    wb.save(m)
    (tmp_path / "short.json").write_text(json.dumps(mf.SHORT))
    return context.run(m, str(tmp_path), "TEST", values=m)


def test_loss_makers_and_shrinkers_get_a_question_mark_not_a_tick(fixture_model, tmp_path):
    """A ratio over a negative base reads backwards: FCF over a net loss, a margin over a loss-making peak, an
    incremental margin over falling revenue. Each shows ? (None, #N/A on the tab), and its formula carries the same
    guard so the recalculated tab still equals Python."""
    def edit(wb, cols):
        ws = wb["MOD"]
        for c in cols.values():
            for r in (5, 10):                                     # operating income and non-GAAP net income
                if isinstance(ws.cell(r, c).value, float):
                    ws.cell(r, c).value = -abs(ws.cell(r, c).value)
        for q in ("Q1 25", "Q2 25", "Q3 25", "Q4 25"):            # TTM revenue below the year before
            ws.cell(3, cols[q]).value *= 0.5
    c = _variant(fixture_model, tmp_path, edit)
    m = c["metrics"]
    assert m["fcf_conv"]["value"] is None and m["incr"]["value"] is None and m["peak_ratio"]["value"] is None
    assert c["code_ticks"]["fcf"] == "unknown" and c["code_ticks"]["incr_margin"] == "unknown"
    assert re.fullmatch(r"IFERROR\(IF\(SUM\([^)]*\$10[^)]*\)>0,.*,NA\(\)\),NA\(\)\)", m["fcf_conv"]["formula"])
    assert m["incr"]["formula"].startswith("IFERROR(IF((SUM(") and ">0," in m["incr"]["formula"]
    assert m["peak_ratio"]["formula"].startswith("IFERROR(IF(MAX(") and ">0," in m["peak_ratio"]["formula"]


def test_a_blank_fy_operating_income_counts_as_zero_as_excel_does(fixture_model, tmp_path):
    """Excel reads a blank cell in OI/Revenue as 0, so the FY margin is 0 and the peak stays the 2025 20%."""
    def edit(wb, cols):
        wb["MOD"].cell(5, cols["2018"]).value = None
    c = _variant(fixture_model, tmp_path, edit)
    assert c["metrics"]["peak_ratio"]["value"] == A(1.0)


def test_a_zero_first_consensus_estimate_is_not_a_crash(fixture_model, tmp_path):
    def edit(wb, cols):
        wb["Consensus"]["C293"] = 0.0                            # FY 2027's first snapshot
    c = _variant(fixture_model, tmp_path, edit)
    assert c["metrics"]["revision"]["value"] is None and c["code_ticks"]["revisions"] == "unknown"


def test_no_reported_quarters_means_no_empty_sums():
    """A MOD with only forecast quarters: the 5-year metrics are left out, never SUM() of nothing."""
    import context

    class MM:
        order = [f"Q{n} {y}E" for y in (26, 27, 28, 29) for n in (1, 2, 3, 4)]

        def is_q(self, p):
            return p.startswith("Q")

        def forecast_quarters(self):
            return list(self.order)

        def col(self, p):
            return "D"

    rows = {"rev": 3, "oi": 5, "ni": 6, "eps": 8, "da": 12, "cfo": 13, "acq": 15, "capex": 18, "fcf": 19}
    out, _, _ = context.mod_metrics(MM(), {}, rows)
    assert "fcf_conv" not in out and "acq_cfo" not in out
    assert not any("SUM()" in x["formula"] for x in out.values())


def test_revisions_use_next_year_even_when_brokers_add_later_years():
    """model-consensus labels years "FY 26" and adds broker years past +1y (FY 28, FY 29 on a handful of estimates).
    The live period is next year (+1y): this year's label + 1, not the largest label."""
    import context
    def snap(d):
        return [(d, "Q4 26", 0.72), (d, "Q1 27", 0.64), (d, "FY 26", 2.70), (d, "FY 27", 3.13), (d, "FY 28", 3.59),
                (d, "FY 29", 3.79)]
    rows = snap("2026-08-12") + snap("2026-11-12")
    rows[-3] = ("2026-11-12", "FY 27", 3.05)
    L = context.consensus_links(_consensus(rows))
    assert L["rev_first"]["period"] == "FY 27" and (L["rev_first"]["value"], L["rev_last"]["value"]) == (3.13, 3.05)
