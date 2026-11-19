"""A small TEST_model.xlsx (MOD + an Earnings tab with a band 7 frozen block) and synthetic release / 10-Q Markdown.
Columns: D..H = Q1 25..Q4 25, 2025 | I spacer | J..N = Q1 26, Q2 26, Q3 26E, Q4 26E, 2026E | O spacer |
P..T = Q1 27E..Q4 27E, 2027E. Actuals are constants except the subtotal rows, which are formulas everywhere (like a
real model). values() is the truth a recalculation gives in the actual columns. A test workbook made by openpyxl:
never a user's model."""
import os

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Font

TICKER = "TEST"
PERIODS = ["Q1 25", "Q2 25", "Q3 25", "Q4 25", "2025", None, "Q1 26", "Q2 26", "Q3 26E", "Q4 26E", "2026E", None,
           "Q1 27E", "Q2 27E", "Q3 27E", "Q4 27E", "2027E"]
COL = {p: openpyxl.utils.get_column_letter(4 + i) for i, p in enumerate(PERIODS) if p}
ROWS = {  # row: (section in A or None, label in B, unit in C, key in DATA or a formula template)
    3: ("INCOME STATEMENT", None, None, None),
    4: (None, "Revenue", "$m", "rev"),
    5: (None, "% yoy", None, "=({c}4/{py}4)-1"),
    6: (None, "Cost of sales", "$m", "cos"),
    7: (None, "Gross profit", "$m", "={c}4-{c}6"),
    8: (None, "Operating expenses", "$m", "opex"),
    9: (None, "Operating income", "$m", "={c}7-{c}8"),
    10: (None, "Restructuring", "$m", "restr"),
    11: (None, "Net income", "$m", "ni"),
    12: (None, "EPS, diluted", "$", "eps"),
    13: ("BALANCE SHEET", None, None, None),
    14: ("ASSETS:", "Cash and equivalents", "$m", "cash"),
    15: (None, "Other current assets", "$m", "oca"),
    16: (None, "Prepaid expenses", "$m", "pre"),
    17: (None, "Total assets", "$m", "=SUM({c}14:{c}16)"),
    18: ("LIABILITIES & EQUITY:", "Total liabilities", "$m", "liab"),
    19: (None, "Stockholders' equity", "$m", "eq"),
    20: (None, "Total liabilities and equity", "$m", "={c}18+{c}19"),
    21: ("CASH FLOW STATEMENT", None, None, None),
    22: ("CASH FLOWS FROM OPERATING ACTIVITIES:", "Net cash from operating activities", "$m", "cfo"),
    23: ("CASH FLOWS FROM INVESTING ACTIVITIES:", "Capital expenditures", "$m", "capex"),
    24: ("NON-GAAP METRICS", "GAAP gross profit", "$m", "={c}7"),
    25: (None, "Amortization of intangibles", "$m", "amort"),
    26: (None, "Non-GAAP gross profit", "$m", "={c}24+{c}25"),
    27: ("KEY OPERATING METRICS", "Units", "k", "units"),
}
BS_ROWS = {14, 15, 16, 17, 18, 19, 20}
DATA = {
    "Q1 25": dict(rev=100, cos=40, opex=30, restr=0, ni=20, eps=0.80, cash=50, oca=10, pre=5, liab=30, cfo=15, capex=-5, amort=2, units=1000),
    "Q2 25": dict(rev=110, cos=44, opex=31, restr=0, ni=22, eps=0.88, cash=55, oca=11, pre=5, liab=31, cfo=16, capex=-5, amort=2, units=1100),
    "Q3 25": dict(rev=120, cos=48, opex=32, restr=0, ni=24, eps=0.96, cash=60, oca=12, pre=6, liab=32, cfo=17, capex=-6, amort=2, units=1200),
    "Q4 25": dict(rev=130, cos=52, opex=33, restr=0, ni=26, eps=1.04, cash=65, oca=13, pre=6, liab=33, cfo=18, capex=-6, amort=2, units=1300),
    "Q1 26": dict(rev=115, cos=45, opex=33, restr=0, ni=25, eps=1.00, cash=70, oca=14, pre=6, liab=34, cfo=19, capex=-6, amort=3, units=1250),
    "Q2 26": dict(rev=125, cos=49, opex=34, restr=0, ni=27, eps=1.08, cash=75, oca=15, pre=7, liab=35, cfo=20, capex=-7, amort=3, units=1350),
}
for d in DATA.values():
    d["eq"] = d["cash"] + d["oca"] + d["pre"] - d["liab"]
REPORT = dict(rev=140, cos=52, opex=36, restr=0, ni=30, eps=1.20, cash=80, oca=16, pre=7, liab=36, cfo=22, capex=-8, amort=3, units=1500)
REPORT["eq"] = REPORT["cash"] + REPORT["oca"] + REPORT["pre"] - REPORT["liab"]
FORECAST = {  # forecast-column formulas: {c} this column, {py} year-ago column, {pv} previous quarter column
    "rev": "={py}4*1.1", "cos": "={c}4*0.4", "opex": "={py}8*1.05", "restr": "=0", "ni": "={c}9*0.6",
    "eps": "={c}11/25", "cash": "={pv}14+5", "oca": "={pv}15+1", "pre": "={pv}16", "liab": "={pv}18+1",
    "eq": "={c}17-{c}18", "cfo": "={c}11", "capex": "=-{c}4*0.05", "amort": "={py}25", "units": "={py}27*1.15",
}
QS = [p for p in PERIODS if p and p.startswith("Q")]
BLUE = Font(color="FF0000FF")


def _py(p):
    n, yy = p.rstrip("E").split()
    t = f"{n} {int(yy) - 1:02d}"
    return next(x for x in QS if x.rstrip("E") == t)


def _pv(p):
    return QS[QS.index(p) - 1]


def _fy_quarters(fy):
    return [q for q in QS if q.split()[1][:2] == fy[2:4]]


def _f(tpl, p):
    return tpl.format(c=COL[p], py=COL[_py(p)] if p in QS and p[3:5] != "25" else "", pv=COL[_pv(p)] if QS.index(p) else "")


FLOW_PLUG = {4, 6, 8, 10, 11, 25}            # house=True: Q4 = FY less Q1-Q3, the FY typed
CF_ROWS = {22, 23}
Q4R = dict(rev=150, cos=56, opex=37, restr=0, ni=33, eps=1.32, cash=85, oca=17, pre=7, liab=37, cfo=24, capex=-9, amort=3, units=1600)
Q4R["eq"] = Q4R["cash"] + Q4R["oca"] + Q4R["pre"] - Q4R["liab"]


def _year_total(fy, k, extra=()):
    qs = [q for q in DATA if q.endswith(fy[2:4])]
    return round(sum(DATA[q][k] for q in qs) + sum(extra), 6)


def _house(p, r, k):
    """house=True history cells for one actual quarter / year: plugs, '=YTD-earlier quarters', typed FY."""
    if p[0].isdigit():                                       # FY column: typed from the 10-K
        if r in BS_ROWS:
            return DATA[f"Q4 {p[2:4]}"][k] if f"Q4 {p[2:4]}" in DATA else None
        if r == 12:
            return 3.68
        if r in FLOW_PLUG | CF_ROWS:
            return _year_total(p, k)
        return None
    n = int(p[1])
    same = [q for q in QS if q.split()[1][:2] == p.split()[1][:2]]
    fyc = COL.get("20" + p.split()[1][:2])
    if n == 4 and r in BS_ROWS:
        return f"={fyc}{r}"
    if n == 4 and r in FLOW_PLUG:
        return f"={fyc}{r}" + "".join(f"-{COL[q]}{r}" for q in reversed(same[:3]))
    if r in CF_ROWS:
        if n == 4:
            return f"={fyc}{r}-SUM({COL[same[0]]}{r}:{COL[same[2]]}{r})"
        if n > 1:
            ytd = round(sum(DATA[q][k] for q in same[:n]), 6)
            return f"={ytd:g}" + "".join(f"-{COL[q]}{r}" for q in reversed(same[:n - 1]))
    return DATA[p][k]


def model(path, frozen_quarter="Q3 26E", neg_cost=False, house=False, actual_q3=False):
    """neg_cost: row 6 is '(-) Cost of sales', stored negative (the house convention for costs).
    house: history built the way model-historicals and the user's own models build it: Q4 = FY less Q1-Q3 with the FY
    typed (flows), Q4 = FY (balances), Q2/Q3 cash flow '=<YTD>-earlier quarters', Q4 cash flow '=FY-SUM(Q1:Q3)'.
    actual_q3: Q3 26 is already reported (typed from REPORT; header 'Q3 26'), so Q4 26E is the next print."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    ws["A1"] = f"{TICKER} - model"
    for p, c in COL.items():
        ws[f"{c}2"] = "Q3 26" if actual_q3 and p == "Q3 26E" else p
    for r, (a, b, unit, k) in ROWS.items():
        if a:
            ws[f"A{r}"] = a
        if b:
            ws[f"B{r}"] = "(-) Cost of sales" if neg_cost and r == 6 else b
        if unit:
            ws[f"C{r}"] = unit
        if not b:
            continue
        for p in PERIODS:
            if not p:
                continue
            ref = f"{COL[p]}{r}"
            if house and not k.startswith("=") and (p == "2025" or p in DATA):
                v = _house(p, r, k)
                if v is not None:
                    ws[ref] = v
                    ws[ref].font = BLUE
                    continue
            if actual_q3 and p == "Q3 26E" and not k.startswith("="):
                y = {kk: DATA["Q1 26"][kk] + DATA["Q2 26"][kk] + REPORT[kk] for kk in ("cfo", "capex")}
                ws[ref] = (f"={y[k]:g}-{COL['Q2 26']}{r}-{COL['Q1 26']}{r}" if house and r in CF_ROWS else REPORT[k])
                ws[ref].font = BLUE
                continue
            if p[0].isdigit():                       # fiscal-year column
                qs = _fy_quarters(p)
                if r == 5:
                    prior = {"2026E": "2025", "2027E": "2026E"}.get(p)
                    if prior:
                        ws[ref] = f"=({COL[p]}4/{COL[prior]}4)-1"
                elif r in BS_ROWS:
                    ws[ref] = f"={COL[qs[-1]]}{r}"
                else:
                    ws[ref] = f"=SUM({COL[qs[0]]}{r}:{COL[qs[-1]]}{r})"
                continue
            neg = neg_cost and r == 6
            if k.startswith("="):
                if r == 5 and p[3:5] == "25":
                    continue                         # no year-ago column for 2025
                ws[ref] = _f("={c}4+{c}6" if neg_cost and r == 7 else k, p)
            elif p.endswith("E"):
                ws[ref] = _f("=-{c}4*0.4" if neg else FORECAST[k], p)
            else:
                ws[ref] = -DATA[p][k] if neg else DATA[p][k]
                ws[ref].font = BLUE
    ws["D4"].comment = Comment("10-K 2025 line 10", "model-historicals")
    e = wb.create_sheet("Earnings")
    e["A1"] = "TEST earnings preview"
    e["A20"] = f"7. FROZEN FORECAST: {frozen_quarter}, frozen 2026-10-15 (values: model-earnings-after reads them)"
    e["A21"], e["B21"], e["C21"] = "Line", frozen_quarter, "2026E"
    for i, (lab, q, fy) in enumerate([("Revenue", 132.0, 502.0), ("Gross profit", 79.2, 301.2), ("EPS, diluted", 1.15, 4.40)]):
        e[f"A{22 + i}"], e[f"B{22 + i}"], e[f"C{22 + i}"] = lab, q, fy
    e["A26"] = "8. RULE THRESHOLDS"
    o = wb.create_sheet("Valuation")
    o["B3"] = "=MOD!N4"                              # a green link into MOD that must keep pointing at Revenue 2026
    wb.save(path)
    return path


def values(neg_cost=False, actual_q3=False):
    """{ref: value} for the actual columns D..K (L too with actual_q3) and the 2025 year column H (constants and the
    formulas evaluated)."""
    out = {}
    src = dict(DATA, **({"Q3 26E": REPORT} if actual_q3 else {}))
    for p in ["Q1 25", "Q2 25", "Q3 25", "Q4 25", "Q1 26", "Q2 26"] + (["Q3 26E"] if actual_q3 else []):
        d, c = src[p], COL[p]
        row = {4: d["rev"], 6: d["cos"], 7: d["rev"] - d["cos"], 8: d["opex"], 9: d["rev"] - d["cos"] - d["opex"],
               10: d["restr"], 11: d["ni"], 12: d["eps"], 14: d["cash"], 15: d["oca"], 16: d["pre"],
               17: d["cash"] + d["oca"] + d["pre"], 18: d["liab"], 19: d["eq"], 20: d["liab"] + d["eq"], 22: d["cfo"],
               23: d["capex"], 24: d["rev"] - d["cos"], 25: d["amort"], 26: d["rev"] - d["cos"] + d["amort"], 27: d["units"]}
        if neg_cost:
            row[6] = -d["cos"]
        out.update({f"{c}{r}": v for r, v in row.items()})
    h = COL["2025"]
    for r in ROWS:
        qv = [out.get(f"{COL[q]}{r}") for q in ("Q1 25", "Q2 25", "Q3 25", "Q4 25")]
        if None in qv or r == 5:
            continue
        out[f"{h}{r}"] = qv[-1] if r in BS_ROWS else (3.68 if r == 12 else round(sum(qv), 6))
    return out


def release_q4_md():
    """The Q4 26 release: three months and twelve months (income statement), Dec 31 balance sheet, twelve-month cash
    flow, a three-month-only reconciliation (no full-year column: Q4 is typed and the year sums)."""
    R, P = Q4R, DATA["Q4 25"]
    y26 = {k: DATA["Q1 26"][k] + DATA["Q2 26"][k] + REPORT[k] + R[k] for k in R}
    y25 = {k: sum(DATA[q][k] for q in ("Q1 25", "Q2 25", "Q3 25", "Q4 25")) for k in R}
    y26["eps"], y25["eps"] = 4.60, 3.68
    n = _n
    row = lambda lab, k, d=1: (f"| {lab} | {n(R[k], 1, d)} |  |  | {n(P[k], 1, d)} |  |  | {n(y26[k], 1, d)} |  |  | "
                               f"{n(y25[k], 1, d)} |  |")
    L = [f"# {TICKER} Reports Fourth Quarter and Full Year 2026 Results", "",
         "## Condensed Consolidated Statements of Operations", "", "(In millions, except per share data)", "",
         "|  | Three Months EndedDecember 31, |  | Twelve Months EndedDecember 31, |", "| --- | --- | --- | --- |",
         "|  | 2026 |  | 2025 |  | 2026 |  | 2025 |",
         row("Revenue", "rev"), row("Cost of sales", "cos"), row("Total operating expenses", "opex"),
         "| Restructuring | — |  |  | — |  |  | — |  |  | — |  |",
         row("Net income", "ni"), row("Diluted net income per share", "eps", 2),
         "", "## Condensed Consolidated Balance Sheets", "", "(In millions)", "",
         "|  | December 31, 2026 |  | December 31, 2025 |", "| --- | --- | --- | --- |"]
    for lab, k in [("Cash and cash equivalents", "cash"), ("Other current assets", "oca"), ("Prepaid expenses", "pre")]:
        L.append(f"| {lab} | {n(R[k])} |  |  | {n(P[k])} |  |")
    ta, ta0 = R["cash"] + R["oca"] + R["pre"], P["cash"] + P["oca"] + P["pre"]
    L += [f"| Total assets | {n(ta)} |  |  | {n(ta0)} |  |", f"| Total liabilities | {n(R['liab'])} |  |  | {n(P['liab'])} |  |",
          f"| Total stockholders' equity | {n(R['eq'])} |  |  | {n(P['eq'])} |  |",
          f"| Total liabilities and stockholders' equity | {n(ta)} |  |  | {n(ta0)} |  |",
          "", "## Condensed Consolidated Statements of Cash Flows", "", "(In millions)", "",
          "|  | Twelve Months EndedDecember 31, |", "| --- | --- |", "|  | 2026 |  | 2025 |",
          f"| Net cash provided by operating activities | {n(y26['cfo'])} |  |  | {n(y25['cfo'])} |  |",
          f"| Purchases of property and equipment | {n(y26['capex'])} |  |  | {n(y25['capex'])} |  |",
          "", "## Reconciliation of GAAP to Non-GAAP Gross Profit", "", "(In millions)", "",
          "|  | Three Months EndedDecember 31, |", "| --- | --- |", "|  | 2026 |  | 2025 |",
          f"| GAAP gross profit | {n(R['rev'] - R['cos'])} |  |  | {n(P['rev'] - P['cos'])} |  |",
          f"| Amortization of intangible assets | {n(R['amort'])} |  |  | {n(P['amort'])} |  |",
          f"| Non-GAAP gross profit | {n(R['rev'] - R['cos'] + R['amort'])} |  |  | {n(P['rev'] - P['cos'] + P['amort'])} |  |", ""]
    return "\n".join(L)


def _n(v, k=1.0, dec=1):
    v = v * k
    s = f"{abs(v):,.{dec}f}"
    return f"({s}" if v < 0 else s


def release_md(variant="normal"):
    """Exhibit 99.1-style Markdown. variants: normal | thousands | recast | combined"""
    k = 1000.0 if variant == "thousands" else 1.0
    dec = 0 if variant == "thousands" else 1
    unit = "thousands" if variant == "thousands" else "millions"
    R, P = REPORT, DATA["Q3 25"]
    y9 = {key: sum(DATA[q][key] for q in ("Q1 26", "Q2 26")) + R[key] for key in ("cfo", "capex")}
    p9 = {key: sum(DATA[q][key] for q in ("Q1 25", "Q2 25", "Q3 25")) for key in ("cfo", "capex")}
    prev_rev = 121 if variant == "recast" else P["rev"]
    prev_cos = 49 if variant == "recast" else P["cos"]
    n = lambda v: _n(v, k, dec)
    L = [f"# {TICKER} Reports Third Quarter 2026 Results", "",
         "Revenue grew 17% to $140.0 million. The company raises its 2026 revenue guidance to $520 to $530 million.", "",
         "## Condensed Consolidated Statements of Operations", "", f"(In {unit}, except per share data)", "", "(Unaudited)", "",
         "|  | Three Months EndedSeptember 30, |  | Nine Months EndedSeptember 30, |", "| --- | --- | --- | --- |",
         "|  | 2026 |  | 2025 |  | 2026 |  | 2025 |",
         f"| Revenue | $ | {n(R['rev'])} |  |  | $ | {n(prev_rev)} |  |  | $ | {n(380)} |  |  | $ | {n(350)} |  |",
         f"| Cost of sales | {n(R['cos'])} |  |  | {n(prev_cos)} |  |  | {n(146)} |  |  | {n(132)} |  |",
         f"| Gross profit | {n(R['rev'] - R['cos'])} |  |  | {n(P['rev'] - P['cos'])} |  |  | {n(234)} |  |  | {n(218)} |  |",
         f"| Total operating expenses | {n(R['opex'])} |  |  | {n(P['opex'])} |  |  | {n(103)} |  |  | {n(93)} |  |",
         f"| Operating income | {n(R['rev'] - R['cos'] - R['opex'])} |  |  | {n(P['rev'] - P['cos'] - P['opex'])} |  |  | {n(131)} |  |  | {n(125)} |  |",
         "| Restructuring | — |  |  | — |  |  | — |  |  | — |  |",
         f"| Other income, net | {n(2.0)} |  |  | {n(1.5)} |  |  | {n(5.0)} |  |  | {n(4.0)} |  |",
         f"| Net income | $ | {n(R['ni'])} |  |  | $ | {n(P['ni'])} |  |  | $ | {n(82)} |  |  | $ | {n(66)} |  |",
         f"| Diluted net income per share | $ | {R['eps']:.2f} |  |  | $ | {P['eps']:.2f} |  |  | $ | 3.28 |  |  | $ | 2.64 |  |",
         "", "## Condensed Consolidated Balance Sheets", "", f"(In {unit})", "",
         "|  | September 30, 2026 |  | December 31, 2025 |", "| --- | --- | --- | --- |"]
    Q4 = DATA["Q4 25"]
    L += [f"| Cash and cash equivalents | $ | {n(R['cash'])} |  |  | $ | {n(Q4['cash'])} |  |"]
    if variant == "combined":
        L += [f"| Other current assets and prepaid expenses | {n(R['oca'] + R['pre'])} |  |  | {n(Q4['oca'] + Q4['pre'])} |  |"]
    else:
        L += [f"| Other current assets | {n(R['oca'])} |  |  | {n(Q4['oca'])} |  |",
              f"| Prepaid expenses | {n(R['pre'])} |  |  | {n(Q4['pre'])} |  |"]
    ta, ta0 = R["cash"] + R["oca"] + R["pre"], Q4["cash"] + Q4["oca"] + Q4["pre"]
    L += [f"| Total assets | $ | {n(ta)} |  |  | $ | {n(ta0)} |  |",
          f"| Total liabilities | {n(R['liab'])} |  |  | {n(Q4['liab'])} |  |",
          f"| Total stockholders' equity | {n(R['eq'])} |  |  | {n(Q4['eq'])} |  |",
          f"| Total liabilities and stockholders' equity | $ | {n(ta)} |  |  | $ | {n(ta0)} |  |",
          "", "## Condensed Consolidated Statements of Cash Flows", "", f"(In {unit})", "",
          "|  | Nine Months EndedSeptember 30, |", "| --- | --- |", "|  | 2026 |  | 2025 |",
          f"| Net cash provided by operating activities | {n(y9['cfo'])} |  |  | {n(p9['cfo'])} |  |",
          f"| Purchases of property and equipment | {n(y9['capex'])} | ) |  | {n(p9['capex'])} | ) |",
          "", "## Reconciliation of GAAP to Non-GAAP Gross Profit", "", f"(In {unit})", "",
          "|  | Three Months EndedSeptember 30, |", "| --- | --- |", "|  | 2026 |  | 2025 |",
          f"| GAAP gross profit | $ | {n(R['rev'] - R['cos'])} |  |  | $ | {n(P['rev'] - P['cos'])} |  |",
          f"| Amortization of intangible assets (1) | {n(R['amort'])} |  |  | {n(P['amort'])} |  |",
          f"| Non-GAAP gross profit | $ | {n(R['rev'] - R['cos'] + R['amort'])} |  |  | $ | {n(P['rev'] - P['cos'] + P['amort'])} |  |",
          "", "## Key metrics", "",
          "| Key metrics | Three months 2026 |  | 2025 |", "| --- | --- | --- | --- |",
          f"| Units (thousands) | {R['units']:,} |  | {P['units']:,} |", "",
          "## Outlook", "", "For fiscal 2026 the company now expects revenue of $520 million to $530 million (previously $500 million to $515 million).", ""]
    return "\n".join(L)


def tenq_md():
    """The Q3 26 10-Q: full balance sheet lines, and cost of sales 52.5 where the release said 52.0."""
    t = release_md("normal").replace(f"| Cost of sales | {_n(52)} |", f"| Cost of sales | {_n(52.5)} |")
    return t.replace("Reports Third Quarter 2026 Results", "Form 10-Q for the quarter ended September 30, 2026")


def research(root, variant="normal", with_tenq=False):
    base = os.path.join(root, TICKER)
    pr = os.path.join(base, "Press Releases", "_md")
    os.makedirs(pr, exist_ok=True)
    with open(os.path.join(pr, f"2026 Q3 {TICKER} release 2026-10-29.md"), "w", encoding="utf-8") as f:
        f.write(release_md(variant))
    if with_tenq:
        q = os.path.join(base, "10-Qs", "_md")
        os.makedirs(q, exist_ok=True)
        with open(os.path.join(q, f"{TICKER} 2026 Q3 10-Q.md"), "w", encoding="utf-8") as f:
            f.write(tenq_md())
    return base
