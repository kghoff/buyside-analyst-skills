from modmap import ModMap
from methods import cells_for, value_for
from test_modmap import _book


def test_value_for_carries_the_last_year_forward_and_lets_a_quarter_override():
    v = {"2026E": 0.1, "Q2 27E": 0.3}
    assert value_for(v, "Q4 26E", "2026E") == 0.1
    assert value_for(v, "Q1 27E", "2027E") == 0.1 and value_for(v, "Q2 27E", "2027E") == 0.3


def test_pct_of_types_the_rate_in_the_analysis_row_and_links_the_line(tmp_path):
    # The user's own pattern: the assumption sits blue in the '% of sales' row, the line is revenue x that rate
    m = ModMap(_book(tmp_path))
    c = cells_for(m, {"key": "INCOME STATEMENT | (-) R&D", "method": "pct_of", "kind": "flow",
                      "of": "INCOME STATEMENT | Revenue:", "sign": -1, "rates": {"2026E": 0.125}, "source": "S73"})
    assert c["M7"] == ("f", "-M5*M8", "black") and c["M8"] == ("n", 0.125, "blue")
    assert c["N7"] == ("f", "SUM(J7:M7)", "black") and "N8" not in c        # FY sums quarters; rate row's FY untouched


def test_growth_uses_the_same_quarter_last_year(tmp_path):
    m = ModMap(_book(tmp_path))
    c = cells_for(m, {"key": "INCOME STATEMENT | Revenue:", "method": "growth", "kind": "flow",
                      "rates": {"2026E": 0.1, "2027E": 0.12}, "source": "x"})
    assert c["P5"] == ("f", "J5*(1+P6)", "black") and c["P6"] == ("n", 0.12, "blue")


def test_formula_tokens_and_balance_annual_is_q4(tmp_path):
    m = ModMap(_book(tmp_path))
    c = cells_for(m, {"key": "ASSETS: | Cash & Equivalents", "method": "formula", "kind": "balance",
                      "template": "{prev:ASSETS: | Cash & Equivalents}+{INCOME STATEMENT | Revenue:}", "source": "x"})
    assert c["P11"] == ("f", "M11+P5", "black") and c["N11"] == ("f", "M11", "black")


def test_flat_holds_the_last_actual(tmp_path):
    m = ModMap(_book(tmp_path))
    c = cells_for(m, {"key": "ASSETS: | Other Assets", "method": "flat", "kind": "balance", "source": "x"})
    assert c["M12"] == ("f", "L12", "black") and c["P12"] == ("f", "M12", "black")


def test_seasonal_quarters_add_up_to_the_year(tmp_path):
    # The filings research: forecast the year, split by seasonality; a partly reported year splits only what is left
    m = ModMap(_book(tmp_path))
    m.keys["INCOME STATEMENT | Revenue:"] = 5
    m.analysis_rows[9] = "seasonality"          # pretend a seasonality row sits under revenue
    m.analysis = lambda key, name: {"% yoy": 6, "seasonality": 9}[name]
    c = cells_for(m, {"key": "INCOME STATEMENT | Revenue:", "method": "seasonal", "kind": "flow",
                      "annual_growth": {"2026E": 0.12}, "shares": {"Q1": .2, "Q2": .25, "Q3": .25, "Q4": .3}, "source": "x"})
    assert c["N5"] == ("f", "H5*(1+N6)", "black")
    assert c["M5"] == ("f", "(N5-J5-K5-L5)*M9/(M9)", "black")
    assert c["P5"] == ("f", "T5*P9", "black")


def test_days_token_in_a_formula_template(tmp_path):
    m = ModMap(_book(tmp_path))
    c = cells_for(m, {"key": "ASSETS: | Other Assets", "method": "formula", "kind": "balance",
                      "template": "{INCOME STATEMENT | Revenue:}/{days}", "source": "x"})
    assert c["P12"] == ("f", "P5/91.25", "black")


def test_flow_schedule_by_year_spreads_the_remainder_over_forecast_quarters(tmp_path):
    # A yearly figure already partly reported: forecast quarters get only what is left, FY stays the typed number
    m = ModMap(_book(tmp_path))
    c = cells_for(m, {"key": "ASSETS: | Other Assets", "method": "schedule", "kind": "flow",
                      "values": {"2026E": 100, "2027E": 80}, "source": "x"})
    assert c["N12"] == ("n", 100, "blue") and c["T12"] == ("n", 80, "blue")
    assert c["M12"] == ("f", "(N12-J12-K12-L12)/1", "black")
    assert c["P12"] == ("f", "(T12-0)/4", "black") or c["P12"] == ("f", "T12/4", "black")


def test_balance_schedule_year_value_applies_to_every_forecast_quarter(tmp_path):
    m = ModMap(_book(tmp_path))
    c = cells_for(m, {"key": "ASSETS: | Other Assets", "method": "schedule", "kind": "balance",
                      "values": {"2026E": 50}, "source": "x"})
    assert c["M12"] == ("n", 50, "blue") and c["P12"] == ("n", 50, "blue") and c["N12"] == ("f", "M12", "black")


def test_value_for_refuses_to_guess_from_a_later_year():
    import pytest
    with pytest.raises(ValueError, match="X: no value for Q4 26E"):
        value_for({"2027E": 0.1}, "Q4 26E", "2026E", key="X")


def test_missing_analysis_row_is_an_error(tmp_path):
    import pytest
    m = ModMap(_book(tmp_path))
    with pytest.raises(KeyError, match="no '% yoy' row under"):
        m.analysis("INCOME STATEMENT | (-) R&D", "% yoy")


def test_prev_of_the_first_quarter_raises(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        ModMap(_book(tmp_path)).prev("Q1 25")


def test_fy_template_overrides_the_default_in_every_forecast_year(tmp_path):
    # A rate row (e.g. tax rate) must be recomputed in the FY column from that year's own cells, not keep a stale value
    m = ModMap(_book(tmp_path))
    c = cells_for(m, {"key": "ASSETS: | Other Assets", "method": "flat", "kind": "rate",
                      "fy_template": "-{ASSETS: | Cash & Equivalents}/{INCOME STATEMENT | Revenue:}", "source": "x"})
    assert c["N12"] == ("f", "-N11/N5", "black") and c["T12"] == ("f", "-T11/T5", "black")
    assert c["M12"] == ("f", "L12", "black")


def test_annual_driver_rows_write_only_the_year_columns(tmp_path):
    """Key drivers (customers, penetration, revenue per customer) are yearly facts: an input is typed blue in each FY
    column, a formula row chains FY to the prior FY, and no quarter cell is touched."""
    m = ModMap(_book(tmp_path))
    typed = cells_for(m, {"key": "ASSETS: | Other Assets", "method": "annual", "kind": "annual",
                          "values": {"2026E": 0.6, "2027E": 0.65}, "source": "x"})
    assert typed == {"N12": ("n", 0.6, "blue"), "T12": ("n", 0.65, "blue")}
    chain = cells_for(m, {"key": "ASSETS: | Other Assets #2", "method": "annual", "kind": "annual",
                          "template": "{prev:ASSETS: | Other Assets #2}*(1+{ASSETS: | Other Assets})", "source": "x"})
    assert chain == {"N13": ("f", "H13*(1+N12)", "black"), "T13": ("f", "N13*(1+T12)", "black")}


def test_seasonal_revenue_can_come_from_the_driver_build(tmp_path):
    """With fy_template the year is a formula on the driver rows (no typed growth rate); quarters still split it."""
    m = ModMap(_book(tmp_path))
    m.analysis_rows[9] = "seasonality"
    m.analysis = lambda key, name: {"% yoy": 6, "seasonality": 9}[name]
    c = cells_for(m, {"key": "INCOME STATEMENT | Revenue:", "method": "seasonal", "kind": "flow",
                      "fy_template": "{ASSETS: | Other Assets}*{ASSETS: | Other Assets #2}",
                      "shares": {"Q1": .2, "Q2": .25, "Q3": .25, "Q4": .3}, "source": "x"})
    assert c["N5"] == ("f", "N12*N13", "black") and c["T5"] == ("f", "T12*T13", "black")
    assert c["T6"] == ("f", 'IFERROR(T5/N5-1,"n.a.")', "black")   # growth falls out of the drivers, never typed
    assert all(ref in ("N9", "P9", "Q9", "R9", "S9", "M9") or color != "blue" for ref, (_, _, color) in c.items())
    assert c["P5"] == ("f", "T5*P9", "black")


def test_annual_templates_by_year_and_inputs_that_start_later(tmp_path):
    """A derivation in the anchor year, then hold it (no IF tricks); an input that only exists from a later year leaves
    the earlier years blank instead of a misleading 'reference' value."""
    m = ModMap(_book(tmp_path))
    c = cells_for(m, {"key": "ASSETS: | Other Assets", "method": "annual", "kind": "annual",
                      "templates": {"2026E": "{ASSETS: | Cash & Equivalents}/2", "2027E": "{prev:ASSETS: | Other Assets}"},
                      "source": "x"})
    assert c == {"N12": ("f", "N11/2", "black"), "T12": ("f", "N12", "black")}
    c = cells_for(m, {"key": "ASSETS: | Other Assets", "method": "annual", "kind": "annual",
                      "values": {"2027E": -0.04}, "history_values": {"2025": 0.5}, "source": "x"})
    assert c == {"H12": ("n", 0.5, "blue"), "T12": ("n", -0.04, "blue")}


def test_fy_token_lets_a_quarter_read_its_years_driver_and_history_shows_the_ratio(tmp_path):
    """Convention: a driver row shows the actual historical ratio beside the assumption; quarterly statements read the
    annual driver of their own fiscal year."""
    m = ModMap(_book(tmp_path))
    c = cells_for(m, {"key": "INCOME STATEMENT | (-) R&D", "method": "formula", "kind": "flow",
                      "template": "-{INCOME STATEMENT | Revenue:}*{fy:ASSETS: | Other Assets}", "source": "x"})
    assert c["M7"] == ("f", "-M5*N12", "black") and c["P7"] == ("f", "-P5*T12", "black")
    d = cells_for(m, {"key": "ASSETS: | Other Assets", "method": "annual", "kind": "annual", "values": {"2026E": 0.1},
                      "history_template": "-{INCOME STATEMENT | (-) R&D}/{INCOME STATEMENT | Revenue:}", "source": "x"})
    assert d["H12"] == ("f", "-H7/H5", "black") and d["N12"] == ("n", 0.1, "blue")


def test_quarter_tokens_reach_the_same_fiscal_years_quarters(tmp_path):
    """A nine-month actual must be a SUM of the reported quarters in the model, not a typed total."""
    m = ModMap(_book(tmp_path))
    c = cells_for(m, {"key": "ASSETS: | Other Assets", "method": "annual", "kind": "annual",
                      "template": "{q1:INCOME STATEMENT | Revenue:}+{q2:INCOME STATEMENT | Revenue:}+{q3:INCOME STATEMENT | Revenue:}",
                      "source": "x"})
    assert c["N12"] == ("f", "J5+K5+L5", "black") and c["T12"] == ("f", "P5+Q5+R5", "black")


def test_a_null_template_year_stops_a_one_year_derivation(tmp_path):
    """'Amortization, Q3 2026 (reported)' must not carry into 2027 under a 2026 label."""
    m = ModMap(_book(tmp_path))
    c = cells_for(m, {"key": "ASSETS: | Other Assets", "method": "annual", "kind": "annual",
                      "templates": {"2026E": "{q3:INCOME STATEMENT | Revenue:}", "2027E": None}, "source": "x"})
    assert c == {"N12": ("f", "L5", "black")}


def test_a_rate_run_quarter_by_quarter_shows_each_years_actual_ratio(tmp_path):
    """The SBC % of revenue row carried the last quarter forward but its year cells were blank, so they
    couldn't compare the 2.7% assumption with the 3.4% full-year history. Every year column shows the ratio."""
    m = ModMap(_book(tmp_path))
    c = cells_for(m, {"key": "ASSETS: | Other Assets", "method": "formula", "kind": "rate",
                      "template": "-{prev:INCOME STATEMENT | (-) R&D}/{prev:INCOME STATEMENT | Revenue:}",
                      "history_template": "-{INCOME STATEMENT | (-) R&D}/{INCOME STATEMENT | Revenue:}", "source": "x"})
    assert c["P12"] == ("f", "-M7/M5", "black")                      # the quarter still carries the last quarter
    assert c["H12"] == ("f", "-H7/H5", "black")                      # 2025: the actual ratio
    assert c["N12"] == ("f", "-N7/N5", "black") and c["T12"] == ("f", "-T7/T5", "black")   # forecast years too
