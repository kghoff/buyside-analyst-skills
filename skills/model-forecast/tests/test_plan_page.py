import openpyxl
import pytest

import plan_page as P
from modmap import ModMap
from test_modmap import LAB

PLAN = {"ticker": "TEST",
        "guidance": [{"what": "FY2026 revenue", "key": "INCOME STATEMENT | Revenue:", "period": "2026E", "low": 5200, "high": 5250}],
        "rows": [
            {"key": "REVENUE BUILD | US revenue", "method": "seasonal", "kind": "flow",
             "annual_growth": {"2026E": 0.14, "2030E": 0.08}, "shares": {"Q1": 0.22}, "source": "guide 12-13% [Q3 release]"},
            {"key": "INCOME STATEMENT | Revenue:", "method": "formula", "kind": "flow",
             "template": "{REVENUE BUILD | US revenue}+{REVENUE BUILD | International revenue}", "source": "Filings research 6.1"},
            {"key": "INCOME STATEMENT | (-) R&D", "method": "pct_of", "kind": "flow", "of": "INCOME STATEMENT | Revenue:",
             "sign": -1, "rates": {"2026E": 0.125, "2030E": 0.12}, "source": "LRP opex"},
            {"key": "ASSETS: | Cash", "method": "flat", "kind": "balance", "source": "no view"},
            {"key": "CASH FLOWS FROM OPERATING ACTIVITIES: | Capex", "method": "schedule", "kind": "flow",
             "values": {"2026E": -100, "2030E": -150}, "source": "guide"},
            {"key": "ASSETS: | Receivables", "method": "days", "kind": "balance", "of": "INCOME STATEMENT | Revenue:",
             "rate_row": "ASSETS: | DSO", "rates": {"2026E": 45}, "source": "history"},
            {"key": "INCOME STATEMENT | Other", "method": "growth", "kind": "flow", "rates": {"2026E": 0.12}, "source": "x"}]}


@pytest.fixture
def m(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    for k, v in enumerate(LAB):
        ws.cell(2, 4 + k, v)
    p = tmp_path / "m.xlsx"
    wb.save(p)
    return ModMap(str(p))


def test_page_has_a_section_per_statement_and_a_row_per_entry(m):
    t = P.render(PLAN, m)
    for h in ("Revenue build", "Income statement", "Balance sheet", "Cash flow"):
        assert f"## {h}" in t
    assert t.count("| line | method | 2026E | 2030E | source |") == 4
    assert "| US revenue | seasonal growth (typed rate) | 14% | 8% | guide 12-13% [Q3 release] |" in t
    assert "| (-) R&D | % of revenue 12.5% | 12.5% | 12% | LRP opex |" in t
    assert "| Other | growth 12% | 12% | 12% | x |" in t            # 2030E carries the last value forward
    assert "| Receivables | days 45 | 45 | 45 | history |" in t
    assert "| Cash | held flat |" in t and "| Capex | schedule | -100 | -150 | guide |" in t


def test_formula_shows_labels_not_keys_and_guidance_is_listed(m):
    t = P.render(PLAN, m)
    assert "{US revenue}+{International revenue}" in t and "REVENUE BUILD |" not in t
    assert "FY2026 revenue" in t and "5,200" in t and "5,250" in t


def test_headlines_are_appended_after_a_build(m):
    assert "Forecast headlines" in P.render(PLAN, m, headlines="# Forecast headlines\n")


def test_open_ended_and_point_guidance(m):
    base = {"what": "g", "key": "INCOME STATEMENT | Revenue:", "period": "2026E"}
    plan = {**PLAN, "guidance": [{**base, "what": "A", "low": 10, "high": None}, {**base, "what": "B", "low": None, "high": 12},
                                 {**base, "what": "C", "low": 5, "high": 5}]}
    t = P.render(plan, m)
    assert "A: at least 10 in 2026E" in t and "B: at most 12 in 2026E" in t and "C: 5 in 2026E" in t


def test_driver_built_revenue_line_renders_without_a_growth_rate(tmp_path):
    """A revenue line built from the drivers has no typed growth rate; the page shows its formula instead."""
    from modmap import ModMap as _M
    from test_modmap import _book as _b
    from plan_page import render
    plan = {"ticker": "T", "drivers": [{"name": "d1", "rows": ["ASSETS: | Other Assets"]}],
            "rows": [{"key": "INCOME STATEMENT | Revenue:", "method": "seasonal", "kind": "flow",
                      "fy_template": "{ASSETS: | Other Assets}*2", "shares": {"Q1": .25, "Q2": .25, "Q3": .25, "Q4": .25},
                      "source": "x"}]}
    t = render(plan, _M(_b(tmp_path)))
    assert "year = {Other Assets}*2, quarters seasonal" in t and "**d1**" in t


def test_page_renders_per_year_formulas_and_history_only_rows(tmp_path):
    from modmap import ModMap as _M
    from test_modmap import _book as _b
    from plan_page import render
    plan = {"ticker": "T", "rows": [
        {"key": "ASSETS: | Other Assets", "method": "annual", "kind": "annual",
         "templates": {"2026E": "{q3:INCOME STATEMENT | Revenue:}", "2027E": None}, "source": "x"},
        {"key": "ASSETS: | Other Assets #2", "method": "annual", "kind": "annual", "values": {}, "source": "y"}]}
    t = render(plan, _M(_b(tmp_path)))
    assert "2026E: {q3:Revenue:}; 2027E: stops" in t
