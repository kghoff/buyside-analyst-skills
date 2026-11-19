import openpyxl

import make_fixture as mf


def test_fixture_reports_q3_26_with_formula_subtotals(model):
    """Every later test assumes Q3 26E is the first forecast quarter and subtotals are formulas, like a real model."""
    ws = openpyxl.load_workbook(model)["MOD"]
    assert ws["L2"].value == "Q3 26E" and ws["K2"].value == "Q2 26"
    assert ws["F7"].value == "=F4-F6" and ws["L7"].value == "=L4-L6"
    assert ws["L4"].value == "=F4*1.1" and ws["F4"].value == 120
    assert ws["N4"].value == "=SUM(J4:M4)" and ws["N14"].value == "=M14"


def test_values_balance_so_a_recast_test_cannot_pass_by_accident():
    v = mf.values()
    for c in "DEFGJK":
        assert v[f"{c}17"] == v[f"{c}20"]


def test_release_ytd_cash_flow_is_three_quarters():
    t = mf.release_md()
    assert "| Net cash provided by operating activities | 61.0 |" in t and "| 48.0 |" in t
