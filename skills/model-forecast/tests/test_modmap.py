import openpyxl
from modmap import ModMap

LAB = ["Q1 25", "Q2 25", "Q3 25", "Q4 25", 2025, None, "Q1 26", "Q2 26", "Q3 26", "Q4 26E", "2026E", None,
       "Q1 27E", "Q2 27E", "Q3 27E", "Q4 27E", "2027E", None, "2050E"]


def _book(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    for k, v in enumerate(LAB):
        ws.cell(2, 4 + k, v)
    ws["A4"], ws["B5"], ws["B6"] = "INCOME STATEMENT", "Revenue:", "% yoy"
    ws["B7"], ws["B8"] = "(-) R&D", "% of sales"
    ws["A10"], ws["B11"], ws["B12"] = "ASSETS:", "Cash & Equivalents", "Other Assets"
    ws["B13"] = "Other Assets"
    p = tmp_path / "m.xlsx"
    wb.save(p)
    return str(p)


def test_periods_know_quarters_years_and_forecasts(tmp_path):
    m = ModMap(_book(tmp_path))
    assert m.forecast_quarters() == ["Q4 26E", "Q1 27E", "Q2 27E", "Q3 27E", "Q4 27E"]
    assert m.col("2026E") == "N" and m.fy_of("Q4 26E") == "2026E"
    assert m.prev("Q1 27E") == "Q4 26E" and m.pyq("Q1 27E") == "Q1 26"
    assert m.quarters_of("2026E") == ["Q1 26", "Q2 26", "Q3 26", "Q4 26E"]
    assert "2050E" not in m.forecast_years()


def test_rows_are_keyed_by_section_and_label_with_duplicates_numbered(tmp_path):
    m = ModMap(_book(tmp_path))
    assert m.row("INCOME STATEMENT | Revenue:") == 5
    assert m.analysis("INCOME STATEMENT | (-) R&D", "% of sales") == 8
    assert m.row("ASSETS: | Other Assets") == 12 and m.row("ASSETS: | Other Assets #2") == 13
