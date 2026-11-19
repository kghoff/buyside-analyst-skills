# skills/model-summary/tests/fixtures/make_fixture.py
"""TEST_model.xlsx with only what model-summary reads: MOD (Q1 16 - Q4 29E plus FY columns; actual years 2016-2025),
Px Data, DCF, Multiples and Valuation with the labels the real skills write (ABT's model, 2026-11-19). Constants,
except the Valuation formulas a link must resolve through (the tree's targets, which links.py classifies). MOD has
a print area and Valuation is the open tab, so the tests can prove SUM's insertion moves neither. A test workbook
made by openpyxl: never a user's model."""
import datetime as dt

import openpyxl

YEARS = range(2016, 2030)
LAST_ACTUAL = 2025
PRICE = 50.0
MOD_ROWS = [(3, "INCOME STATEMENT", "Revenue", "rev"), (4, None, "% yoy", None), (5, None, "Gross Profit", "gp"),
            (6, None, "Operating Income", "oi"), (7, None, "Shares, diluted", "shares"), (8, None, "EPS, diluted", "eps"),
            (10, "CASH FLOWS FROM OPERATING ACTIVITIES:", "(+) Depreciation & Amortization", "da"),
            (12, "FREE CASH FLOW", "(+/-) Free Cash Flow", "fcf")]


def series():
    out, rev = {k: [] for k in ("q", "y", "rev", "gp", "oi", "shares", "eps", "da", "fcf")}, 100.0
    for y in YEARS:
        for qn in range(1, 5):
            rev *= 1.02
            oi = rev * 0.2
            for k, v in dict(q=f"Q{qn} {y % 100:02d}" + ("E" if y > LAST_ACTUAL else ""), y=y, rev=rev, gp=rev * 0.6,
                             oi=oi, shares=50.0, eps=oi * 0.75 / 50.0, da=rev * 0.05, fcf=oi * 0.8).items():
                out[k].append(v)
    return out


def fy(y):
    return f"{y}" + ("E" if y > LAST_ACTUAL else "")


def _mod(ws):
    s, col, cols = series(), 4, {}
    for y in YEARS:
        for qn in range(1, 5):
            lab = f"Q{qn} {y % 100:02d}" + ("E" if y > LAST_ACTUAL else "")
            ws.cell(2, col, lab)
            cols[lab], col = col, col + 1
        ws.cell(2, col, fy(y))
        cols[fy(y)], col = col, col + 1
    for r, sec, lab, key in MOD_ROWS:
        if sec:
            ws.cell(r, 1, sec)
        ws.cell(r, 2, lab)
        if key is None:
            continue
        for i, q in enumerate(s["q"]):
            ws.cell(r, cols[q], s[key][i])
        for y in YEARS:
            v = [s[key][i] for i in range(len(s["q"])) if s["y"][i] == y]
            ws.cell(r, cols[fy(y)], sum(v) / 4 if key == "shares" else sum(v))
    ws.print_area = "A1:D10"
    return cols


def _px(ws):
    ws["A4"], ws["B4"], ws["C4"] = "Date", "TEST close", "P/E (GAAP EPS)"
    for k in range(5):
        ws.cell(5 + k, 1, dt.datetime(2026, 11, 10 + k)), ws.cell(5 + k, 2, PRICE)


def _dcf(ws):
    for r, lab, v in ((10, "Cash & equivalents (Q4 25)", 100.0), (11, "Short-term marketable securities (Q4 25)", 20.0),
                      (12, "Current debt (Q4 25)", 50.0), (13, "Long-term debt (Q4 25)", 300.0),
                      (14, "Net debt (debt - cash - securities)", 230.0), (16, "Diluted shares, M (Q4 25)", 50.0),
                      (18, "Price (last close in Px Data; date beside it)", PRICE)):
        ws.cell(r, 2, lab), ws.cell(r, 3, v)
    ws["D18"] = dt.datetime(2026, 11, 14)


RANGE_HEADS = ["Metric", "Today"] + [f"{y} {s}" for y in ("1 year", "5 years", "10 years")
                                     for s in ("min", "median", "max", "percentile")]


def _mult(ws):
    ws["A5"] = "RANGES (as of 2026-11-14, the last weekly close)"
    for c, h in enumerate(RANGE_HEADS, 1):
        ws.cell(6, c, h)
    for r, lab, base in ((7, "P/E", 20.0), (8, "EV/EBITDA", 12.0), (12, "GAAP P/E − S&P 500 P/E", -2.0),
                         (13, "GAAP P/E − core-peer median", 1.0)):
        ws.cell(r, 1, lab), ws.cell(r, 2, base)
        for c in range(3, len(RANGE_HEADS) + 1):
            ws.cell(r, c, base + c)
    ws["A20"] = "FORWARD (price and EV as of 2026-11-14, the last weekly close)"
    for c, y in enumerate(("2026E", "2027E", "2028E", "2029E"), 2):
        ws.cell(21, c, y)
    ws["A34"], ws["B34"], ws["C34"] = "Street EPS (Yahoo consensus, analysts' basis)", 2.1, 2.4
    for c, h in enumerate(("Ticker", "Group", "Price", "Market cap ($M)", "Total debt ($M)", "Cash ($M)", "EV ($M)",
                           "3M ADV (shares, M)"), 1):
        ws.cell(37, c, h)
    ws["A38"], ws["B38"], ws["H38"] = "PEER", "Peers", 400000
    ws["A39"], ws["B39"], ws["H39"] = "TEST", "Subject", 900000


def _val(ws):
    rows = [(3, "Overall verdict (the agent's call: Buy / Hold / Sell)", "Buy"), (5, "Price", PRICE),
            (9, "IRR hurdle", 0.15), (10, "Buy at R/R", 2.0), (11, "Table-pound at R/R", 3.0),
            (19, "1. Which multiples and why", "Role"), (20, "P/E", "primary"), (21, "EV/EBITDA", "secondary"),
            (22, "Weights sum", 1.0), (32, "4. 12-month roll-forward and reward / risk", None),
            (34, "P/E (primary)", "Ours"), (35, "P/E: NTM EPS (Q1 26E to Q4 26E)", 2.2),
            (36, "P/E: NTM+1 EPS (Q1 27E to Q4 27E)", 2.5), (37, "P/E today (on NTM)", "=B5/B35"),
            (38, "P/E: reward multiple (x NTM+1)", 24.0), (39, "P/E: reward price", "=B38*B36"),
            (40, "P/E: risk multiple", 15.0), (41, "P/E: risk EPS", 2.0), (42, "P/E: risk price", "=B40*B41"),
            (43, "P/E: reward %", "=B39/B5-1"), (44, "P/E: risk %", "=1-B42/B5"), (45, "P/E: reward / risk", "=B43/B44"),
            (50, "EV/EBITDA (secondary)", "Ours"), (51, "EV/EBITDA: NTM EBITDA (Q1 26E to Q4 26E)", 300.0),
            (66, "4b. Blended (weights in section 1)", None), (71, "Blended reward / risk", 1.4),
            (74, "4c. Reward / risk ladder (blended)", "Entry"),
            (83, "5. 3-year IRR (P/E, the primary multiple)", None), (84, "IRR: NTM EPS now", "=B35"),
            (85, "IRR: EPS in 3 years (Q1 29E to Q4 29E)", 3.4), (86, "IRR: years", 3), (87, "IRR: P/E now", "=B37"),
            (88, "P/E: multiple at the 3-year horizon", 20.0), (89, "IRR: price now", "=B5"),
            (90, "IRR: price in 3 years", "=B88*B85"), (91, "IRR", "=IF(B90>0,(B90/B89)^(1/B86)-1,NA())"),
            (92, "IRR vs hurdle", '=IF(B91>=$B$9,"clears","below")'),
            (99, "6. DCF scenarios (model-dcf's math)", "Bear"), (108, "DCF value per share", 35.0),
            (116, "7. Probability tree", "Target")]
    for r, lab, v in rows:
        ws.cell(r, 1, lab)
        if v is not None:
            ws.cell(r, 2, v)
    ws["C74"], ws["D74"], ws["E74"] = "Reward", "Risk", "R/R"
    for k, mv in enumerate((-0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15)):
        r = 75 + k
        ws.cell(r, 1, mv), ws.cell(r, 2, f"=$B$5*(1+A{r})"), ws.cell(r, 3, 0.3 - mv), ws.cell(r, 4, 0.2 + mv)
        ws.cell(r, 5, f"=C{r}/D{r}")
    ws["C99"], ws["D99"], ws["C108"], ws["D108"] = "Base", "Bull", 52.0, 70.0
    ws["C116"], ws["D116"] = "Return", "Probability"
    for r, name, tgt, p in ((117, "Bull", "=$D$108", 0.2), (118, "Base", "=$B$39", 0.4), (119, "Risk", "=$B$42", 0.25),
                            (120, "Bear", "=$B$108", 0.15)):
        ws.cell(r, 1, name), ws.cell(r, 2, tgt), ws.cell(r, 3, f"=B{r}/$B$5-1"), ws.cell(r, 4, p)
    ws["A121"], ws["B121"] = "Probability-weighted", "=SUMPRODUCT(B117:B120,D117:D120)"
    ws["C121"], ws["D121"] = "=B121/$B$5-1", "=SUM(D117:D120)"


def build(path, multiples_adv=True):
    wb = openpyxl.Workbook()
    wb.active.title = "MOD"
    _mod(wb["MOD"])
    _px(wb.create_sheet("Px Data"))
    _dcf(wb.create_sheet("DCF"))
    _mult(wb.create_sheet("Multiples"))
    if not multiples_adv:
        wb["Multiples"]["H39"] = None
    _val(wb.create_sheet("Valuation"))
    wb.active = 4                                                 # Valuation open
    wb.save(path)
    return path
