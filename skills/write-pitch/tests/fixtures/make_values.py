# skills/write-pitch/tests/fixtures/make_values.py
"""Build the throwaway 'recalculated' workbook the anchors tests read (plain values, no formulas).

make_values(path) writes the cells README.md lists (Valuation and SUM) plus a few label cells and a 'Short Check' tab
whose name has a space. Later tasks extend it with SUM / Multiples / Px Data / Px Events blocks."""
import openpyxl

VALUATION = {"C5": 72.40, "C30": 120, "F20": 0.31, "F21": -0.15, "C32": 55.00, "D12": 4.10, "D13": 32, "D14": 0.81,
             "D15": 0.25, "C40": 0.06, "C41": 0.08, "C42": 0.04, "C13": 28, "C15": 0.5, "E12": 2.60, "E13": 22,
             "E15": 0.25}
SUM = {"H12": 2.85, "J12": 3.30, "K12": 3.05, "H8": 1250, "J8": 1420}
LABELS = {"Valuation": {"B5": "Price", "B30": "3-year target", "C11": "Base", "D11": "Bull", "E11": "Bear",
                        "B12": "EPS", "B13": "P/E", "B15": "Probability"},
          "SUM": {"A8": "Revenue", "A12": "EPS (GAAP)", "H6": "2026E", "J6": "2027E", "K6": "2027 Street"}}


def make_values(path):
    wb = openpyxl.Workbook()
    wb.active.title = "SUM"
    val = wb.create_sheet("Valuation")
    sc = wb.create_sheet("Short Check")
    for ws, cells in ((wb["SUM"], SUM), (val, VALUATION)):
        for ref, v in cells.items():
            ws[ref] = v
    for name, cells in LABELS.items():
        for ref, v in cells.items():
            wb[name][ref] = v
    sc["A5"] = "Days to cover"
    sc["B5"] = 12.5
    sc["B6"] = "n/a"        # a non-numeric cell
    wb.save(path)
    return str(path)
