# skills/write-pitch/tests/fixtures/make_values.py
"""Build the throwaway 'recalculated' workbook the anchors tests read (plain values, no formulas).

make_values(path) writes the cells README.md lists (Valuation and SUM) plus a few label cells and a 'Short Check' tab
whose name has a space. The deck builder's blocks follow, laid out with the real tabs' labels and headers (found by
label, so their position is free; they sit clear of the anchors cells): SUM's cap table (model-summary layout.py) and
internal-estimates grid, Valuation's reward / risk ladder (model-valuation build.py sec4c_ladder), Multiples' WEEKLY
DATA block (model-multiples build.py), Px Data's Date / XYZ close and Px Events' release dates (model-price-history)."""
import datetime as dt
import math

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
    deck_blocks(wb)
    wb.save(path)
    return str(path)


LAST = dt.date(2026, 11, 18)      # the last close in Px Data


def _sum_blocks(ws):
    cap = [("Cap table ($M except per share)", None), ("Price (date beside it)", 72.40), ("Diluted shares (M)", 125.0),
           ("Market cap", 9050.0), ("Total debt", 400.0), ("Cash & short-term securities", 650.0), ("Net debt", -250.0),
           ("Enterprise value", 8800.0), ("Cash per share", 5.20), ("3M ADV (M shares)", 1.6), ("3M ADV ($M)", 115.8),
           (None, None), ("Action prices (write-pitch fills these)", None), ("Buy price", None),
           ("No-brainer price", None), (None, None), ("3-year target (P/E, the primary multiple)", None),
           ("FY 2029 EPS", 4.0), ("P/E", 30.0), ("3-year target price", 120.0), ("% return", 0.657),
           ("x money", 1.657), ("Years", 3), ("IRR", 0.1834), ("IRR hurdle", 0.2), (None, None),
           ("12-month base target (P/E only)", None), ("NTM+1 EPS", 3.30), ("Reward P/E", 28.5),
           ("12-month target", 94.84), ("% return", 0.31), ("x money", 1.31), (None, None),
           ("12-month risk case (P/E only)", None), ("Risk EPS", 2.80), ("Risk P/E", 22.0), ("Risk price", 61.54),
           ("% return", -0.15), (None, None), ("Blended reward / risk", 2.07), ("Buy at R/R", 2.0)]
    for i, (lab, v) in enumerate(cap):
        if lab:
            ws.cell(row=6 + i, column=2, value=lab)
        if v is not None:
            ws.cell(row=6 + i, column=3, value=v)
    ws["D7"] = LAST
    ws["E20"] = "Internal estimates (our model; multiples at today's price and EV)"
    years = ["2024A", "2025A", "2026E", "2027E", "2028E"]
    for j, y in enumerate(years):
        ws.cell(row=21, column=6 + j, value=y)
    grid = [("Revenue", [980, 1100, 1250, 1420, 1600]), ("% yoy", [0.09, 0.122, 0.136, 0.136, 0.127]),
            ("Street revenue", ["n/a", "n/a", 1240, 1380, 1530]),
            ("Revenue delta (ours vs Street)", ["n/a", "n/a", 0.008, 0.029, 0.046]),
            ("EBITDA (operating income + D&A)", [240, 280, 330, 390, 450]),
            ("EPS (GAAP, the Street's basis)", [2.10, 2.45, 2.85, 3.30, 3.80]),
            ("% yoy", [0.1, 0.167, 0.163, 0.158, 0.152]), ("Street EPS", ["n/a", "n/a", 2.90, 3.05, 3.40]),
            ("Expected Delta (ours vs Street)", ["n/a", "n/a", -0.017, 0.082, 0.118]),
            ("EV/Sales", [9.0, 8.0, 7.0, 6.2, 5.5]), ("EV/EBITDA", [36.7, 31.4, 26.7, 22.6, 19.6]),
            ("P/E", [34.5, 29.6, 25.4, 21.9, 19.1]), ("Street P/E", ["n/a", "n/a", 25.0, 23.7, 21.3])]
    for i, (lab, vals) in enumerate(grid):
        ws.cell(row=22 + i, column=5, value=lab)
        for j, v in enumerate(vals):
            ws.cell(row=22 + i, column=6 + j, value=v)


def _ladder(ws):
    for c, h in zip("ABCDEH", ("4c. Reward / risk ladder (blended)", "Entry", "Reward", "Risk", "R/R", "Reasoning")):
        ws[f"{c}50"] = h
    for i, s in enumerate((-0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15)):
        e = round(72.40 * (1 + s), 4)
        up, down = 94.84 / e - 1, 1 - 61.54 / e
        for c, v in zip("ABCDE", (s, e, up, down, up / down if down > 0 else "#N/A")):
            ws[f"{c}{51 + i}"] = v


def _weekly(ws):
    ws["A1"] = "XYZ multiples: where the stock trades against its history, the market and its peers"
    ws["A40"] = "WEEKLY DATA"
    heads = ["Week", "Price", "EPS", None, "P/E", "S&P 500 P/E", "PEER close", "PEER P/E", "Core-peer median P/E"]
    for j, h in enumerate(heads):
        if h:
            ws.cell(row=41, column=1 + j, value=h)
    for k in range(260):
        d = LAST - dt.timedelta(weeks=259 - k)
        pe = 26 + 6 * math.sin(k / 30)
        row = [d, 50 + k * 0.08, None, None, pe if k % 50 else "#N/A", 21 + math.sin(k / 50), 40.0,
               24 + 3 * math.cos(k / 40), 24 + 3 * math.cos(k / 40)]
        for j, v in enumerate(row):
            if v is not None:
                ws.cell(row=42 + k, column=1 + j, value=v)


def _prices(px, ev):
    px["A1"] = "XYZ and SPY daily closes"
    for c, h in zip("ABC", ("Date", "XYZ close", "SPY close")):
        px[f"{c}4"] = h
    days = [LAST - dt.timedelta(days=k) for k in range(int(3.5 * 365))]
    days = sorted(d for d in days if d.weekday() < 5)
    for i, d in enumerate(days):
        px.cell(row=5 + i, column=1, value=d)
        px.cell(row=5 + i, column=2, value=round(60 + 8 * math.sin(i / 60) + i * 0.012, 2))
        px.cell(row=5 + i, column=3, value=round(400 + i * 0.2, 2))
    px.cell(row=5 + len(days) - 1, column=2, value=72.40)
    for c, h in zip("AB", ("Period", "Full-results release date")):
        ev[f"{c}4"] = h
    for i in range(14):
        q = dt.date(2023, 5, 2) + dt.timedelta(days=91 * i)
        ev[f"A{5 + i}"] = f"Q{(i + 1) % 4 + 1} {str(q.year)[2:]}"
        ev[f"B{5 + i}"] = q


def deck_blocks(wb):
    _sum_blocks(wb["SUM"])
    _ladder(wb["Valuation"])
    _weekly(wb.create_sheet("Multiples"))
    _prices(wb.create_sheet("Px Data"), wb.create_sheet("Px Events"))
