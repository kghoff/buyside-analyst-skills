import openpyxl
import pytest

import check as C
from modmap import ModMap
from test_modmap import LAB


@pytest.fixture
def m(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    for k, v in enumerate(LAB):
        ws.cell(2, 4 + k, v)
    ws["A4"], ws["B5"] = "INCOME STATEMENT", "Revenue:"
    ws["A10"], ws["B11"], ws["B12"], ws["B13"] = "ASSETS:", "Cash", "Cash Flow Items", "Balance Check:"
    ws["B14"] = "Cash Check:"
    p = tmp_path / "m.xlsx"
    wb.save(p)
    return ModMap(str(p))


PLAN = {"rows": [{"key": "INCOME STATEMENT | Revenue:", "kind": "flow"},
                 {"key": "ASSETS: | Cash", "kind": "balance"}],
        "guidance": [{"what": "FY2026 revenue", "key": "INCOME STATEMENT | Revenue:", "period": "2026E", "low": 390, "high": 410}]}


def clean():
    g = {}
    for c in "MNPQRST":
        g[(13, c)] = 0
        g[(14, c)] = 0.0
    for c, v in zip("JKLM", [90, 95, 100, 115]):
        g[(5, c)] = v
    g[(5, "N")] = 400
    for c, v in zip("PQRS", [100, 100, 100, 100]):
        g[(5, c)] = v
    g[(5, "T")] = 400
    g[(11, "M")], g[(11, "N")] = 50, 50
    g[(11, "S")], g[(11, "T")] = 70, 70
    return g


def test_clean_grid_has_no_problems(m):
    assert C.check_grid(m, clean(), PLAN) == []


def test_nonzero_balance_check_is_reported(m):
    g = clean()
    g[(13, "P")] = 3.5
    out = C.check_grid(m, g, PLAN)
    assert len(out) == 1 and "Balance Check" in out[0] and "Q1 27E" in out[0]


def test_error_value_in_forecast_cell_is_reported(m):
    g = clean()
    g[(11, "Q")] = "#DIV/0!"
    assert any("#DIV/0!" in x for x in C.check_grid(m, g, PLAN))


def test_error_in_history_is_not_ours_to_report(m):
    g = clean()
    g[(5, "E")] = "#DIV/0!"
    assert C.check_grid(m, g, PLAN) == []


def test_annual_flow_must_equal_sum_of_quarters_and_balance_must_equal_q4(m):
    g = clean()
    g[(5, "T")] = 401
    g[(11, "N")] = 49
    out = C.check_grid(m, g, PLAN)
    assert any("2027E" in x and "sum of quarters" in x for x in out)
    assert any("2026E" in x and "Q4" in x for x in out)


def test_guidance_outside_range_reported_unless_explained(m):
    g = clean()
    g[(5, "J")], g[(5, "N")] = 200, 500
    g[(5, "N")] = 500
    bad = C.check_grid(m, g, PLAN)
    assert any("FY2026 revenue" in x for x in bad)
    plan = {**PLAN, "guidance": [{**PLAN["guidance"][0], "outside": "mgmt guide is stale"}]}
    notes = []
    out = C.check_grid(m, g, plan, notes)
    assert not any("FY2026 revenue" in x for x in out)
    assert any("mgmt guide is stale" in x for x in notes)


# --- allowed_diffs: which other-tab cells may legitimately move -------------------------------------------------
FC = {73, 74}           # MOD forecast columns BU, BV by index


def test_direct_ref_to_forecast_column_is_allowed():
    f = {"Research": {(1, 1): "MOD!BU113*2", (2, 1): "MOD!A113", (3, 1): "'MOD'!$BV$5"}}
    got = C.allowed_diffs(f, {73, 74})
    assert ("Research", 1, 1) in got and ("Research", 3, 1) in got and ("Research", 2, 1) not in got


def test_range_spanning_forecast_columns_is_allowed():
    f = {"Research": {(1, 1): "SUM(MOD!BS5:CT5)", (2, 1): "SUM(MOD!A5:BR5)"}}
    got = C.allowed_diffs(f, set(range(73, 99)))
    assert ("Research", 1, 1) in got and ("Research", 2, 1) not in got


def test_two_step_chain_and_range_over_allowed_cell_and_local_refs_on_mod():
    f = {"MOD": {(9, 5): "BU9/2"},                       # local ref on MOD to a forecast column
         "Research": {(1, 1): "MOD!BU113", (2, 1): "A1+1", (3, 1): "SUM(A1:A2)", (4, 1): "Other!B2"},
         "Other": {(2, 2): "Research!A3"}}
    got = C.allowed_diffs(f, {73})
    assert ("MOD", 9, 5) in got
    assert {("Research", 2, 1), ("Research", 3, 1), ("Other", 2, 2), ("Research", 4, 1)} <= got


def test_non_dependent_cell_stays_a_failure():
    f = {"Research": {(1, 1): "MOD!BU113", (2, 1): "B7*3", (3, 1): "MOD!D9+Research!B7"}}
    got = C.allowed_diffs(f, {73})
    assert ("Research", 2, 1) not in got and ("Research", 3, 1) not in got


def test_compare_allow_counts_per_tab():
    import xlverify as X
    before = {"MOD": {(1, 1): 1, (2, 1): 5}, "R": {(1, 1): 1, (2, 2): 9}}
    after = {"MOD": {(1, 1): 2, (2, 1): 5}, "R": {(1, 1): 3, (2, 2): 8}}
    counts = {}
    d = X.compare(before, after, allow=lambda t, r, c: (t, r, c) in {("MOD", 1, 1), ("R", 1, 1)}, counts=counts)
    assert counts == {"MOD": 1, "R": 1} and len(d) == 1 and "R" == d[0][0]


def test_headlines_lists_each_forecast_year(m):
    g = clean()
    text = C.headlines(m, g)
    assert "2026E" in text and "2027E" in text and "Revenue" in text


def test_sequential_inserts_become_original_row_numbers():
    # insert 2 rows at 34 (original row 34), then 1 row at 50 in the new numbering = original row 48
    assert C.to_original([(34, 2), (50, 1)]) == [("MOD", 34, 2), ("MOD", 48, 1)]
    assert C.to_original([(50, 1), (34, 2)]) == [("MOD", 50, 1), ("MOD", 34, 2)]


def test_missing_check_rows_fail(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    for k, v in enumerate(LAB):
        ws.cell(2, 4 + k, v)
    ws["A4"], ws["B5"] = "INCOME STATEMENT", "Revenue:"
    p = tmp_path / "n.xlsx"
    wb.save(p)
    out = C.check_grid(ModMap(str(p)), {}, {"rows": []})
    assert any("Balance Check" in x and "missing" in x for x in out) and any("Cash Check" in x and "missing" in x for x in out)


def test_empty_or_text_check_cell_fails(m):
    g = clean()
    del g[(13, "Q")]
    g[(14, "R")] = "n/a"
    out = C.check_grid(m, g, PLAN)
    assert any("Balance Check" in x and "Q2 27E" in x for x in out)
    assert any("Cash Check" in x and "Q3 27E" in x for x in out)


def test_duplicate_suffix_and_variant_labels_are_all_checked(m):
    mm = m
    mm.keys = dict(mm.keys)
    mm.keys["ASSETS: | Balance Check: #2"] = 20
    mm.keys["ASSETS: | Balance Check (total)"] = 21
    g = clean()
    for c in "MNPQRST":
        g[(20, c)] = 0
        g[(21, c)] = 0
    g[(20, "P")] = 5
    g[(21, "Q")] = 6
    out = C.check_grid(mm, g, PLAN)
    assert any("row 20" in x for x in out) and any("row 21" in x for x in out)


def test_error_cell_never_allowed_unless_same_error_before():
    import xlverify as X
    allow = lambda t, r, c: True
    d = X.compare({"R": {(1, 1): 1}}, {"R": {(1, 1): "#DIV/0!"}}, allow=allow)
    assert len(d) == 1
    d = X.compare({"R": {(1, 1): "#DIV/0!"}}, {"R": {(1, 1): "#DIV/0!"}}, allow=allow)
    assert d == []
    d = X.compare({"R": {(1, 1): "#N/A"}}, {"R": {(1, 1): "#DIV/0!"}}, allow=allow)
    assert len(d) == 1


def test_row_ranges_and_two_sided_ranges_touch_forecast_columns():
    f = {"R": {(1, 1): "SUM(MOD!5:5)", (2, 1): "SUM(MOD!$5:$400)", (3, 1): "SUM(MOD!BS5:MOD!CT5)", (4, 1): "SUM(MOD!A5:MOD!B5)",
               (5, 1): "SUM(Other!5:5)"}}
    got = C.allowed_diffs(f, {73})
    assert {("R", 1, 1), ("R", 2, 1), ("R", 3, 1)} <= got and ("R", 4, 1) not in got and ("R", 5, 1) not in got


def test_open_ended_guidance(m):
    g = clean()
    base = PLAN["guidance"][0]
    at_least = {"rows": [], "guidance": [{**base, "low": 390, "high": None}]}
    at_most = {"rows": [], "guidance": [{**base, "low": None, "high": 410}]}
    assert C.check_grid(m, g, at_least) == [] and C.check_grid(m, g, at_most) == []
    g[(5, "N")] = 500
    assert any("at most 410" in x for x in C.check_grid(m, g, at_most))
    g[(5, "N")] = 300
    assert any("at least 390" in x for x in C.check_grid(m, g, at_least))


def test_preexisting_error_is_a_note_new_error_is_a_problem(m):
    g = clean()
    g[(11, "Q")] = "#DIV/0!"
    g[(11, "R")] = "#DIV/0!"
    notes = []
    out = C.check_grid(m, g, PLAN, notes, preexisting={(11, "Q"): "=Q9/Q10"})
    assert len(out) == 1 and "row 11" in out[0] and "Q3 27E" in out[0]
    assert any("already an error before the forecast" in x and "MOD!Q11" in x and "=Q9/Q10" in x for x in notes)


def test_headlines_margins_fcf_and_conversion_from_modmap_keys(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    for k, v in enumerate(LAB):
        ws.cell(2, 4 + k, v)
    rows = [(4, "INCOME STATEMENT", "Revenue:"), (5, None, "Net Income (Loss)"), (6, None, "Diluted EPS"),
            (8, "NON-GAAP METRICS", "Non-GAAP Gross Profit"), (9, None, "Non-GAAP Operating Income #x"),
            (11, "FREE CASH FLOW", "(+/-) Free Cash Flow")]
    for r, a, b in rows:
        ws.cell(r, 1, a)
        ws.cell(r, 2, b)
    ws["B9"] = "Non-GAAP Operating Income"
    p = tmp_path / "h.xlsx"
    wb.save(p)
    mm = ModMap(str(p))
    g = {}
    for c in "NT":
        g.update({(4, c): 1000, (5, c): 100, (6, c): 1.5, (8, c): 700, (9, c): 250, (11, c): 150})
    t = C.headlines(mm, g)
    assert "| Non-GAAP gross margin | 70.0% | 70.0% |" in t
    assert "| Non-GAAP operating margin | 25.0% | 25.0% |" in t
    assert "| Free cash flow | 150.0 | 150.0 |" in t
    assert "| FCF conversion (FCF / GAAP net income) | 150.0% | 150.0% |" in t   # the check row uses non-GAAP net income; the headline says which it is
    assert "| GAAP EPS, diluted | 1.50 | 1.50 |" in t


def test_rounded_guidance_matches_within_half_a_unit_of_its_last_decimal(m):
    g = clean()
    def plan(lo, hi):
        return {"rows": [], "guidance": [{"what": "tax", "key": "INCOME STATEMENT | Revenue:", "period": "2026E", "low": lo, "high": hi}]}
    g[(5, "N")] = 0.21695
    assert C.check_grid(m, g, plan(0.217, 0.217)) == []
    g[(5, "N")] = 0.2164
    assert C.check_grid(m, g, plan(0.217, 0.217))
    g[(5, "N")] = 5200.4
    assert C.check_grid(m, g, plan(5200, 5200)) == []
    g[(5, "N")] = 5200.6
    assert C.check_grid(m, g, plan(5200, 5200))


def test_cell_added_on_non_mod_tab_fails():
    import xlverify as X
    d = X.compare({"MOD": {(1, 1): 1}, "R": {(1, 1): 1}}, {"MOD": {(1, 1): 1}, "R": {(1, 1): 1, (5, 2): 7}},
                  allow=lambda t, r, c: t == "MOD")
    assert len(d) == 1 and "cell added" in d[0][1]


def test_new_forecast_column_cell_passes():
    import xlverify as X
    counts = {}
    d = X.compare({"MOD": {(1, 1): 1}}, {"MOD": {(1, 1): 1, (1, 73): 5}},
                  allow=lambda t, r, c: t == "MOD" and c == 73, counts=counts)
    assert d == [] and counts == {"MOD": 1}


def test_unexpected_new_tab_fails_unless_listed():
    import xlverify as X
    b, a = {"MOD": {(1, 1): 1}}, {"MOD": {(1, 1): 1}, "Extra": {(1, 1): 1}}
    assert len(X.compare(b, a)) == 1
    assert X.compare(b, a, new_tabs={"Extra"}) == []


# ---- the revenue engine is the key drivers (house default) -------------------------------------------------
from check import check_drivers  # noqa: E402
from modmap import ModMap as _MM  # noqa: E402
from test_modmap import _book as _bk  # noqa: E402

# _book columns: N = 2026E, T = 2027E; rows: 5 Revenue, 6 % yoy, 11 Cash, 12 Other Assets, 13 Other Assets #2
_DRV = [{"name": "customers", "rows": ["ASSETS: | Other Assets"]},
        {"name": "revenue per customer", "rows": ["ASSETS: | Other Assets #2"]}]


def _fm(rev_formula):
    return {(5, 14): "=" + rev_formula.format(c="N"), (5, 20): "=" + rev_formula.format(c="T")}


def test_driver_built_revenue_passes(tmp_path):
    m = _MM(_bk(tmp_path))
    plan = {"drivers": _DRV, "rows": [{"key": "INCOME STATEMENT | Revenue:", "method": "seasonal", "fy_template": "x"}]}
    assert check_drivers(m, _fm("{c}12*{c}13"), {}, plan) == []


def test_a_driver_that_does_not_feed_revenue_fails(tmp_path):
    """Naming a driver is not enough: the research only matters if revenue is computed from it."""
    m = _MM(_bk(tmp_path))
    probs = check_drivers(m, _fm("{c}12*2"), {}, {"drivers": _DRV, "rows": []})
    assert len(probs) == 1 and "revenue per customer" in probs[0]


def test_a_typed_growth_rate_driving_revenue_fails(tmp_path):
    """The DXCM failure: 11.8% typed into a revenue growth row, the driver research left as prose."""
    m = _MM(_bk(tmp_path))
    plan = {"drivers": _DRV, "rows": [{"key": "ASSETS: | Cash & Equivalents", "method": "seasonal", "annual_growth": {}}]}
    probs = check_drivers(m, _fm("{c}11+{c}12*{c}13"), {}, plan)
    assert any("typed growth rate" in p for p in probs)


def test_no_drivers_named_fails_and_growth_engine_needs_a_reason(tmp_path):
    m = _MM(_bk(tmp_path))
    assert check_drivers(m, _fm("{c}11"), {}, {"rows": []})
    assert check_drivers(m, _fm("{c}11"), {}, {"revenue_engine": "growth"})
    notes = []
    assert check_drivers(m, _fm("{c}11"), {}, {"revenue_engine": "growth", "growth_reason": "no volume data"}, notes) == []
    assert notes


def test_phase1_checks_need_a_number_every_year_and_respect_their_bounds(tmp_path):
    """A penetration ceiling (e.g. 80%) is the check that keeps a driver assumption honest."""
    m = _MM(_bk(tmp_path))
    plan = {"revenue_engine": "growth", "growth_reason": "r",
            "checks": [{"what": "type 1 penetration", "key": "ASSETS: | Other Assets", "max": 0.8}]}
    assert check_drivers(m, {}, {(12, "N"): 0.7, (12, "T"): 0.75}, plan) == []
    assert any("outside" in p for p in check_drivers(m, {}, {(12, "N"): 0.7, (12, "T"): 0.85}, plan))
    assert any("no number" in p for p in check_drivers(m, {}, {(12, "N"): 0.7}, plan))


def test_revenue_identity_must_reproduce_revenue_and_carry_long_run_growth(tmp_path):
    """/model-dcf extends this identity 30 years; if it doesn't equal MOD revenue, the DCF would value a different
    company from the forecast the user approved."""
    from check import check_identity
    m = _MM(_bk(tmp_path))
    ident = {"terms": [{"factors": [
        {"key": "ASSETS: | Other Assets", "name": "units", "average": True, "long_run": 0.03, "long_run_source": "x"},
        {"key": "ASSETS: | Other Assets #2", "name": "price", "long_run": 0.0, "long_run_source": "y"}]}]}
    grid = {(12, "H"): 2.0, (12, "N"): 4.0, (12, "T"): 6.0, (13, "N"): 10.0, (13, "T"): 10.0, (5, "N"): 30.0, (5, "T"): 50.0}
    assert check_identity(m, grid, {"revenue_identity": ident}, "INCOME STATEMENT | Revenue:") == []
    grid[(5, "T")] = 60.0
    assert any("2027E" in p for p in check_identity(m, grid, {"revenue_identity": ident}, "INCOME STATEMENT | Revenue:"))
    del ident["terms"][0]["factors"][1]["long_run"]
    assert any("long_run" in p for p in check_identity(m, grid, {"revenue_identity": ident}, "INCOME STATEMENT | Revenue:"))
    assert check_identity(m, grid, {}, "INCOME STATEMENT | Revenue:")


def test_revenue_inputs_outside_the_revenue_build_and_typed_calibrations_fail(tmp_path):
    """The user: show the work. A driver computed elsewhere, or a solved-for number typed in, hides the assumption."""
    from check import check_shown_work
    import openpyxl as _o
    p = _bk(tmp_path)
    wb = _o.load_workbook(p)
    wb["MOD"]["A14"], wb["MOD"]["B15"] = "REVENUE BUILD", "Units"
    wb.save(p)
    m = _MM(p)
    fm = {(5, 14): "=N15*N12", (5, 20): "=T15*T12"}          # revenue reads Units (in the build) and Other Assets (not)
    probs = check_shown_work(m, fm, {"rows": []}, "INCOME STATEMENT | Revenue:")
    assert len(probs) == 1 and "Other Assets" in probs[0]
    fm = {(5, 14): "=N15", (5, 20): "=T15"}
    plan = {"rows": [{"key": "REVENUE BUILD | Units", "values": {"2026E": 3}, "source": "calibration: lands guide"}]}
    assert any("calibrated" in x for x in check_shown_work(m, fm, plan, "INCOME STATEMENT | Revenue:"))
    plan["rows"][0]["source"] = "10-K, Item 7"
    assert check_shown_work(m, fm, plan, "INCOME STATEMENT | Revenue:") == []


def test_statement_rows_may_not_type_forecast_numbers_in_a_v2_plan(tmp_path):
    """The user: gross margin %, opex %, days and dollar schedules typed on statement rows hide the work."""
    from check import check_statements_are_formulas
    m = _MM(_bk(tmp_path))
    plan = {"driver_sections": [{"title": "DRIVERS"}],
            "rows": [{"key": "INCOME STATEMENT | (-) R&D", "method": "pct_of", "rates": {"2026E": 0.12}},
                     {"key": "INCOME STATEMENT | Revenue:", "method": "formula", "template": "x"}]}
    probs = check_statements_are_formulas(m, plan)
    assert len(probs) == 1 and "(-) R&D" in probs[0]


def test_headline_lookup_prefers_the_exact_section_over_a_driver_section(tmp_path):
    """A driver section called 'INCOME STATEMENT DRIVERS' with a 'Revenue growth' row once became the headline revenue."""
    from check import _line
    m = _MM(_bk(tmp_path))
    m.keys["INCOME STATEMENT DRIVERS | Revenue growth"] = 2
    assert _line(m, "INCOME STATEMENT", "Revenue") == 5


def test_an_error_in_a_history_ratio_fails(m):
    """The evidence beside an assumption is useless as #DIV/0! (a ratio read a row with no history)."""
    plan = {"rows": [{"key": "INCOME STATEMENT | Revenue:", "method": "annual", "history_template": "x"}]}
    probs = C.check_grid(m, {(5, "H"): "#DIV/0!"}, plan)
    assert any("history ratio" in p for p in probs)
