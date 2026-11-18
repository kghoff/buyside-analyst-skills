"""A small TEST_model.xlsx with only what model-earnings-before reads: MOD (Q1 19 - Q4 28E with FY columns; actuals
through Q3 26, so Q4 26E is the quarter being reported, engineered as a hockey stick), Px Data (daily closes from
2023), Px Events (10 earnings prints with known moves), Multiples, Consensus (mean row and a variance block) and a
Filings Charts guidance block. Constants only, except the Consensus variance formulas (I-K), which nothing reads
before a recalculation: the file is its own recalculated copy. series() is the truth the tests recompute from.
A test workbook made by openpyxl: never a user's model."""
import datetime as dt
import math

import openpyxl

TICKER = "TEST"
YEARS = range(2019, 2029)
LAST = (2026, 3)                                  # last actual quarter: Q3 26
SEAS = {1: 0.95, 2: 1.00, 3: 1.00, 4: 1.05}
SHARES = 25.0
EARN = {"ticker": "TEST", "asof": "2026-11-18", "source": "Yahoo Finance (fixture)", "price": 51.0,
        "earnings_date": None, "implied_move": None, "straddle": None,
        "surprises": [{"quarter": "2025-12-31", "estimate": 0.60, "actual": 0.64, "surprise": 0.0667},
                      {"quarter": "2026-03-31", "estimate": 0.55, "actual": 0.57, "surprise": 0.0364},
                      {"quarter": "2026-06-30", "estimate": 0.60, "actual": 0.59, "surprise": -0.0167},
                      {"quarter": "2026-09-30", "estimate": 0.61, "actual": 0.65, "surprise": 0.0656}]}
MOD_ROWS = [(3, "INCOME STATEMENT", "Revenue", "rev"), (4, None, "Gross Profit", "gp"),
            (5, None, "Operating Income", "oi"), (6, None, "Net Income", "ni"), (7, None, "EPS, diluted", "eps"),
            (9, "BALANCE SHEET", "Cash & Equivalents", "cash"),
            (11, "FREE CASH FLOW", "(+/-) Free Cash Flow", "fcf"),
            (13, "KEY OPERATING METRICS", "Units", "units")]
DRIVER_KEY = "KEY OPERATING METRICS | Units"
PRINT_PERIODS = ["Q2 24", "Q3 24", "Q4 24", "Q1 25", "Q2 25", "Q3 25", "Q4 25", "Q1 26", "Q2 26", "Q3 26"]
PRINT_MOVES = [0.04, -0.06, 0.03, -0.09, 0.05, 0.02, -0.03, 0.07, -0.05, 0.06]      # oldest first
GUIDE_VS_MID = [0.02, 0.03, -0.01, 0.04, 0.02]        # fiscal 2021-2025; last four: 3 beats -> habitual raiser
VAR_DEFAULT = ["Revenue", "Revenue growth", "Gross margin", "Operating margin", "FCF", "EPS",
               "(key driver)", "(key driver)", "(key driver)"]
CONS_MEAN = {"J": 0.62, "K": 2.45, "L": 2.75, "M": 140.0, "N": 540.0, "O": 575.0}   # EPS q/fy/fy1, rev q/fy/fy1


def g(y, q):
    if y == 2026:
        return 0.02 if q <= 3 else 0.12               # Q4 26E: the hockey stick
    return 0.06


def label(y, q):
    return f"Q{q} {y % 100:02d}" + ("E" if (y, q) > LAST else "")


def fy_label(y):
    return f"{y}" + ("E" if (y, 4) > LAST else "")


def series():
    """{quarter label: {key: value}}, in period order."""
    out, rev = {}, {}
    for y in YEARS:
        for q in range(1, 5):
            rev[(y, q)] = 100.0 * SEAS[q] if y == YEARS[0] else rev[(y - 1, q)] * (1 + g(y, q))
            r = rev[(y, q)]
            oi = r * (0.15 + (0.02 if q == 4 else 0))
            ni = oi * 0.8
            out[label(y, q)] = {"rev": r, "gp": r * 0.6, "oi": oi, "ni": ni, "eps": ni / SHARES, "cash": 50.0,
                                "fcf": ni * 0.9, "units": r / 2}
    return out


def trading_days(start=dt.date(2023, 1, 2), end=dt.date(2026, 11, 17)):
    d, out = start, []
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def closes():
    n = len(trading_days())
    px = [50.0 * (1.0003 ** i) * (1 + 0.02 * math.sin(i / 7)) for i in range(n)]
    spy = [400.0 * (1.0002 ** i) * (1 + 0.01 * math.sin(i / 11)) for i in range(n)]
    return px, spy


def reaction_days():
    """One per printed quarter: the first trading day on or after the quarter's 28th day of its last month + 35."""
    days = trading_days()
    out = []
    for p in PRINT_PERIODS:
        q, yy = int(p[1]), 2000 + int(p[3:5])
        target = dt.date(yy, 3 * q, 28) + dt.timedelta(days=35)
        out.append(next(d for d in days if d >= target))
    return out


def event_dates():
    """The release day of each print: the reaction day, except the last print, released after the close on the
    trading day before its reaction day (so its release is dated a day before the reaction)."""
    days, out = trading_days(), reaction_days()
    return out[:-1] + [days[days.index(out[-1]) - 1]]


def _mod(ws):
    s = series()
    ws["A1"] = "TEST model"
    col, cols = 4, {}
    for y in YEARS:
        for q in range(1, 5):
            cols[label(y, q)] = col
            ws.cell(2, col, label(y, q))
            col += 1
        cols[fy_label(y)] = col
        ws.cell(2, col, fy_label(y))
        col += 1
    for r, sec, lab, key in MOD_ROWS:
        if sec:
            ws.cell(r, 1, sec)
        ws.cell(r, 2, lab)
        ws.cell(r, 3, "$" if key == "eps" else "$M")
        for y in YEARS:
            vals = [s[label(y, q)][key] for q in range(1, 5)]
            for q in range(1, 5):
                ws.cell(r, cols[label(y, q)], vals[q - 1])
            ws.cell(r, cols[fy_label(y)], vals[3] if key == "cash" else sum(vals))


def _px_data(ws):
    ws["A1"] = "TEST and SPY daily closes (fixture)"
    for c, h in enumerate(("Date", "TEST close", "SPY close", "TEST daily return"), start=1):
        ws.cell(4, c, h)
    px, spy = closes()
    for i, d in enumerate(trading_days()):
        r = 5 + i
        ws.cell(r, 1, d).number_format = "yyyy-mm-dd"
        ws.cell(r, 2, px[i])
        ws.cell(r, 3, spy[i])
        if i:
            ws.cell(r, 4, px[i] / px[i - 1] - 1)
    # model-price-history's weekly block shares header row 4 and repeats "TEST close" / "SPY close": the reader must
    # keep the daily ones (columns B and C), not these
    for c, h in enumerate(("Week-end", "TEST close", "SPY close"), start=6):
        ws.cell(4, c, h)
    for k, i in enumerate(range(0, len(px), 5)[:20]):
        ws.cell(5 + k, 6, trading_days()[i]).number_format = "yyyy-mm-dd"
        ws.cell(5 + k, 7, px[i] * 2)
        ws.cell(5 + k, 8, spy[i] * 2)


def _px_events(ws):
    heads = ("Period", "Full-results release date", "GAAP EPS (qtr)", "Non-GAAP EPS (qtr)", "GAAP EPS (FY)",
             "Non-GAAP EPS (FY)", "TTM GAAP EPS", "TTM non-GAAP EPS", "Event date", "Type", "Event", "Timing",
             "Reaction day", "TEST % chg", "SPY % chg", "β (252d)", "Idio % chg")
    for c, h in enumerate(heads, start=1):
        ws.cell(4, c, h)
    for i, (p, d, m) in enumerate(zip(PRINT_PERIODS, reaction_days(), PRINT_MOVES)):
        r = 5 + i
        e = event_dates()[i]
        ws.cell(r, 1, p)
        ws.cell(r, 2, e).number_format = "yyyy-mm-dd"
        ws.cell(r, 9, e).number_format = "yyyy-mm-dd"
        ws.cell(r, 10, "Earnings")
        ws.cell(r, 11, f"{p} results")
        ws.cell(r, 12, "Before open" if e == d else "After close")
        ws.cell(r, 13, d).number_format = "yyyy-mm-dd"
        ws.cell(r, 14, m)
        ws.cell(r, 15, 0.005)
        ws.cell(r, 16, 1.0)
        ws.cell(r, 17, m - 0.005)
    r = 5 + len(PRINT_PERIODS)
    ws.cell(r, 10, "Investor event")
    ws.cell(r, 13, trading_days()[-30]).number_format = "yyyy-mm-dd"
    ws.cell(r, 14, 0.01)
    ws.cell(r, 17, 0.008)


def _consensus(wb, variance):
    c = wb.create_sheet("Consensus")
    c["A1"] = "TEST consensus"
    c["B10"] = "Consensus mean"
    for col, v in CONS_MEAN.items():
        c[f"{col}10"] = v
    if variance != "none":
        c["A20"] = "2. VARIANCE TABLE: consensus vs your own numbers (type them in)"
        c["B21"] = "($M except per share; margins and growth in %)"
        for col, h in zip("CDEFGHIJK", ["Consensus Q4 26", "Consensus FY26", "Consensus FY27", "Internal Q4 26",
                                        "Internal FY26", "Internal FY27", "Variance Q4 26", "Variance FY26",
                                        "Variance FY27"]):
            c[f"{col}21"] = h
        for i, lab in enumerate(VAR_DEFAULT):
            r = 22 + i
            c[f"B{r}"] = lab
            for cc, ic, vc in (("C", "F", "I"), ("D", "G", "J"), ("E", "H", "K")):
                c[f"{vc}{r}"] = f'=IF(OR({cc}{r}="",{ic}{r}=""),"",IFERROR({ic}{r}/{cc}{r}-1,""))'
        if variance == "data":
            c["F22"] = 999.0                          # the user typed their own revenue
        c["A32"] = "3. RATING HISTORY CHART (last 5 years)"
    c["A40"] = "5. CONSENSUS SNAPSHOTS (rows added on every run)"
    for k, h in enumerate(("Snapshot", "Period", "EPS mean"), start=1):
        c.cell(41, k, h)
    c["A42"], c["B42"], c["C42"] = "2026-11-01", "FY 2026", 2.45


def _filings_charts(wb):
    f = wb.create_sheet("Filings Charts")
    f["B5"] = "Guidance vs actual: Revenue"
    f["B6"] = "Fiscal year"
    for k, h in enumerate(["First guide", "Low", "High", "Last guide", "Low", "High", "Actual", "vs first mid",
                           "Changes", "Path of the guide (date: range)"]):
        f.cell(6, 3 + k, h)
    for i, v in enumerate(GUIDE_VS_MID):
        f.cell(7 + i, 2, str(2021 + i))
        f.cell(7 + i, 10, v)
        f.cell(7 + i, 11, 2)


def build(path, variance="skeleton"):
    """variance: 'skeleton' (model-consensus's empty block), 'data' (the user typed in it) or 'none' (no block)."""
    wb = openpyxl.Workbook()
    _mod(wb.active)
    wb.active.title = "MOD"
    _px_data(wb.create_sheet("Px Data"))
    _px_events(wb.create_sheet("Px Events"))
    m = wb.create_sheet("Multiples")
    for c, h in enumerate(["Metric", "Today", "1 year min", "1 year median", "1 year max", "1 year percentile",
                           "5 years min", "5 years median", "5 years max", "5 years percentile"], start=1):
        m.cell(6, c, h)
    for c, v in zip((1, 2, 7, 8, 9, 10), ("P/E", 30.0, 15.0, 22.0, 40.0, 0.85)):
        m.cell(7, c, v)
    _consensus(wb, variance)
    _filings_charts(wb)
    wb.save(path)
    return path
