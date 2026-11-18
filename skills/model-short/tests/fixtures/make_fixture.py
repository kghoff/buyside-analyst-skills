# skills/model-short/tests/fixtures/make_fixture.py
"""A ~50 KB TEST_model.xlsx with only what model-short reads: MOD (quarters Q1 16 - Q4 29E with FY columns, the rows
context.py finds by label), Px Data, Multiples, Valuation, Consensus and Px Events stubs with the real tabs' labels.
Numbers only, no formulas, so the file is its own recalculated copy. series() is the source of truth the tests
recompute from. A test workbook made by openpyxl: never a user's model."""
import openpyxl

YEARS = range(2016, 2030)
LAST_ACTUAL = 2025
SHORT = {"ticker": "TEST", "asof": "2026-11-18", "source": "Yahoo Finance quoteSummary (fixture)", "price": 51.0,
         "dividend_yield": 0.01, "shares_short": 2000000, "short_pct_float": 0.04, "days_to_cover": 2.5,
         "short_date": "2026-10-31", "avg_volume_3m": 800000}
MOD_ROWS = [  # (row, section in A or None, label in B, series key or None)
    (3, "INCOME STATEMENT", "Revenue", "rev"), (4, None, "% qoq", None), (5, None, "Operating Income", "oi"),
    (6, None, "Net Income", "ni"), (7, None, "Shares, diluted", "shares"), (8, None, "EPS, diluted", "eps"),
    (10, "NON-GAAP METRICS", "Non-GAAP Net Income for Diluted EPS", "ni_adj"),
    (12, "CASH FLOWS FROM OPERATING ACTIVITIES:", "(+) Depreciation & Amortization", "da"),
    (13, None, "Net Cash Provided by Operating Activities:", "cfo"),
    (15, "CASH FLOWS FROM INVESTING ACTIVITIES:", "(-) Acquisitions", "acq"),
    (17, "FREE CASH FLOW", "(+/-) Net Cash Provided by Operating Activities", "cfo"),
    (18, None, "(-) Capital Expenditure", "capex"), (19, None, "(+/-) Free Cash Flow", "fcf"),
]


def growth(y):
    return 0.12 if y <= 2023 else (0.08 if y == 2024 else 0.04)     # decelerating: 12% -> 8% -> 4%


def series():
    """{'q': [quarter labels], key: [values per quarter]} in period order."""
    out = {k: [] for k in ("q", "y", "rev", "oi", "ni", "ni_adj", "shares", "eps", "da", "cfo", "acq", "capex", "fcf")}
    rev = 100.0
    for y in YEARS:
        for qn in range(1, 5):
            rev *= (1 + growth(y)) ** 0.25
            m = min(0.10 + 0.01 * (y - 2016), 0.19) + (0.01 if y >= 2025 else 0)   # margin peaks at 20% from 2025
            oi = rev * m
            ni = oi * 0.75
            cfo = ni * 1.1
            capex = -rev * 0.09                                                     # capex / D&A = 1.8x
            vals = dict(q=f"Q{qn} {y % 100:02d}" + ("E" if y > LAST_ACTUAL else ""), y=y, rev=rev, oi=oi, ni=ni,
                        ni_adj=ni * 1.1, shares=50.0, eps=ni / 50.0, da=rev * 0.05, cfo=cfo, acq=-cfo * 0.10,
                        capex=capex, fcf=cfo + capex)
            for k, v in vals.items():
                out[k].append(v)
    return out


def _mod(ws):
    s = series()
    ws["A1"] = "TEST model"
    col, cols = 4, {}
    for y in YEARS:
        for qn in range(1, 5):
            lab = f"Q{qn} {y % 100:02d}" + ("E" if y > LAST_ACTUAL else "")
            ws.cell(2, col, lab)
            cols[lab] = col
            col += 1
        fy = f"{y}" + ("E" if y > LAST_ACTUAL else "")
        ws.cell(2, col, fy)
        cols[fy] = col
        col += 1
    for r, sec, lab, key in MOD_ROWS:
        if sec:
            ws.cell(r, 1, sec)
        ws.cell(r, 2, lab)
        if key is None:
            continue
        ws.cell(r, 3, "$M" if key not in ("eps",) else "$")
        for i, q in enumerate(s["q"]):
            ws.cell(r, cols[q], s[key][i])
        for y in YEARS:                                          # FY = sum of its quarters (shares: average)
            v = [s[key][i] for i in range(len(s["q"])) if s["y"][i] == y]
            ws.cell(r, cols[str(y) + ("E" if y > LAST_ACTUAL else "")], sum(v) / 4 if key == "shares" else sum(v))


def build(path):
    wb = openpyxl.Workbook()
    _mod(wb.active)
    wb.active.title = "MOD"
    wb.create_sheet("Px Data")["A1"] = "Date"
    m = wb.create_sheet("Multiples")
    heads = ["Metric", "Today", "1 year min", "1 year median", "1 year max", "1 year percentile", "5 years min",
             "5 years median", "5 years max", "5 years percentile"]
    for c, h in enumerate(heads, start=1):
        m.cell(6, c, h)
    for r, lab, today, med, mx, pct in ((7, "P/E", 30.0, 22.0, 40.0, 0.85),
                                        (13, "GAAP P/E − core-peer median", 6.0, 2.0, 9.0, 0.75)):
        m.cell(r, 1, lab), m.cell(r, 2, today), m.cell(r, 8, med), m.cell(r, 9, mx), m.cell(r, 10, pct)
    v = wb.create_sheet("Valuation")
    v["A5"], v["B5"] = "Price", 50.0
    v["A99"], v["B99"], v["C99"], v["D99"] = "6. DCF scenarios (model-dcf's math)", "Bear", "Base", "Bull"
    v["A107"], v["B107"], v["C107"], v["D107"] = "DCF value per share", 30.0, 42.0, 55.0
    c = wb.create_sheet("Consensus")
    c["A290"] = "5. CONSENSUS SNAPSHOTS"
    for k, h in enumerate(("Snapshot", "Period", "EPS mean"), start=1):
        c.cell(291, k, h)
    for k, (snap, per, eps) in enumerate((("2026-08-01", "FY 2026", 2.00), ("2026-08-01", "FY 2027", 2.30),
                                          ("2026-11-01", "FY 2026", 1.95), ("2026-11-01", "FY 2027", 2.20)), start=292):
        c.cell(k, 1, snap), c.cell(k, 2, per), c.cell(k, 3, eps)
    p = wb.create_sheet("Px Events")
    for k, h in enumerate(("Period", "Full-results release date", "GAAP EPS (qtr)", "Non-GAAP EPS (qtr)",
                           "GAAP EPS (FY)", "Non-GAAP EPS (FY)", "TTM GAAP EPS", "TTM non-GAAP EPS", "Event date",
                           "Type", "Event", "Timing", "Reaction day", "TEST % chg", "SPY % chg", "β (252d)",
                           "Idio % chg"), start=1):
        p.cell(4, k, h)
    for r, typ, idio in ((5, "Earnings", -0.08), (6, "Investor event", 0.01), (7, "Earnings", 0.05),
                         (8, "Earnings", -0.12), (9, "Earnings", 0.03)):
        p.cell(r, 10, typ), p.cell(r, 17, idio)
    wb.save(path)
    return path
