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
    # the period with the most snapshots, ties to the last one seen: FY 2027, 2.30 -> 2.20
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
