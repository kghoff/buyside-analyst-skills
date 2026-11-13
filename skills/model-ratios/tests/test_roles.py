import openpyxl
from roles import find_roles, fmt_num


def test_finds_model_base_rows_by_label(mod_path):
    roles, starts, opex = find_roles(openpyxl.load_workbook(mod_path)["MOD"])
    assert roles["REV"] == 4 and roles["COGS"] == 5 and roles["GP"] == 6
    assert roles["OI"] == 14 and roles["EBIT"] == 16 and roles["TAXRATE"] == 24 and roles["NI"] == 25
    assert roles["EPSD"] == 29 and roles["TA"] == 47 and roles["EQ"] == 63 and roles["CURDEBT"] == 52
    assert roles["LTDEBT"] == 57 and roles["DA"] == 72 and roles["CFO"] == 88 and roles["CAPEX"] == 93
    assert roles["WCNET"] == 86 and roles["END"] == 107 and roles["INTEXP"] == 21
    assert starts == {"IS": 2, "BS": 31, "CF": 69}
    assert opex == [9, 10]                       # R&D, SG&A: the lines between the opex header and the total


def test_number_text_matches_model_base():
    assert fmt_num(-3.0) == "-3" and fmt_num(12.345) == "12.345"


def test_non_gaap_and_kpi_sections_are_neither_roles_nor_mirrored(mod_path):
    # /model-kpis inserts these between the income statement and BALANCE SHEET; their rows (e.g. a non-GAAP
    # '(+) Interest Income / (-) Interest Expense' bridge line) must never be taken for GAAP lines, and their own
    # M / G rows, so model-ratios adds none under them
    import openpyxl
    from roles import find_roles
    from recipe import build_layout
    wb = openpyxl.load_workbook(mod_path); ws = wb["MOD"]
    ws.insert_rows(31, 6)
    ws["A31"] = "NON-GAAP METRICS"; ws["B33"] = "GAAP Net Income"; ws["B34"] = "(+) Interest Income / (-) Interest Expense"
    ws["A35"] = "KEY OPERATING METRICS"; ws["B36"] = "Customers"
    for r in (33, 34, 36): ws.cell(r, 4, 1.0)
    ws["B21"] = None                                   # no GAAP interest-expense line: the non-GAAP one must not stand in
    roles, starts, opex = find_roles(ws)
    assert not any(31 <= r <= 36 for r in roles.values())
    rows = build_layout(ws, roles, starts, opex)
    at = [i for i, R in enumerate(rows) if R.kind == "keep" and 31 <= R.mod_row <= 36]
    assert len(at) == 6 and all(rows[i + 1].kind == "keep" for i in at)    # kept as they are, nothing inserted


def test_kpi_section_above_the_income_statement_is_skipped(mod_path):
    # /model-kpis puts KEY OPERATING METRICS at the top (the user's ALT DATA area, 2026-11-06)
    wb = openpyxl.load_workbook(mod_path); ws = wb["MOD"]
    ws.insert_rows(2, 3)
    ws["A2"] = "KEY OPERATING METRICS"; ws["B3"] = "Revenue growth, organic"; ws["D3"] = 0.1
    roles, starts, _ = find_roles(ws)
    assert starts["IS"] == 5 and roles["REV"] == 7
