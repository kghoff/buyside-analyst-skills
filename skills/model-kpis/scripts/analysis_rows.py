"""Step 5 - analysis rows, exactly what the house Excel macros write (BuySideMacros.bas v2.2, not included in this repo):

  G  (Ctrl+Shift+G, RevenueRows)  -> '% yoy', '% 2 year', '% qoq'          =IFERROR(X/X_compare-1,"n.a.")
  M  (Ctrl+Shift+M, MarginRows)   profit line -> '% margin', 'bps yoy', '% yoy', 'incremental margin'
                                   cost line   -> '% of sales', 'bps yoy', '% yoy'  (sign flipped when costs are negative)
  Y  (Ctrl+Shift+Y, GrowthRowYoY) -> '% yoy' only

Comparisons: yoy = same period last year, 2 year = two years back, qoq = previous quarter (Q1 looks back to last year's Q4).
A formula is written only where both cells have something in them (the macros' HasData rule). Labels italic, indent 2.

usage: python3 analysis_rows.py --model in.xlsx --out out.xlsx --spec '[{"row": "Non-GAAP Gross Profit", "section": "NON-GAAP METRICS", "macro": "M"}]'
       (or --plan plan.json, which carries the same list under "analysis")
Each spec: row (exact label), section, macro G|M|Y, optional "revenue": {"section": "INCOME STATEMENT", "label": "^revenue"}, "cost": true|false"""
import argparse, json, re
import openpyxl
from openpyxl.styles import Alignment, Border, Font
from openpyxl.utils import get_column_letter as L
from xlmodel import PeriodMap, find_row, insert_rows, norm, PCT_FMT, BPS_FMT, ANALYSIS_INDENT, BLACK, section_bounds

LABELS = {"G": ["% yoy", "% 2 year", "% qoq"], "Y": ["% yoy"], "M": ["% margin", "bps yoy", "% yoy", "incremental margin"], "Mcost": ["% of sales", "bps yoy", "% yoy"]}


def has(ws, r, c): return ws.cell(r, c).value not in (None, "")


def put(ws, r, c, f, fmt):
    cell = ws.cell(r, c); cell.value = f; cell.number_format = fmt
    cell.alignment = Alignment(horizontal="right")


def insert_analysis(ws, base, labels, pm):
    insert_rows(ws, base + 1, len(labels))
    for i, lab in enumerate(labels, 1):
        r = base + i
        for c in range(1, ws.max_column + 1):
            cell = ws.cell(r, c)
            f = cell.font; cell.font = Font(name=f.name, sz=f.sz, b=False, i=False, color=BLACK)
            b = cell.border; cell.border = Border(left=b.left, right=b.right, top=None, bottom=None)
        lc = next((c for c in range(1, pm.first) if has(ws, base, c)), 2)
        cell = ws.cell(r, lc); cell.value = lab
        cell.font = Font(name=cell.font.name, sz=cell.font.sz, i=True, color=BLACK)
        cell.alignment = Alignment(indent=ANALYSIS_INDENT)


def growth(ws, out_r, base, kind, pm):
    for c in sorted(pm.per):
        if has(ws, base, c):
            k = pm.compare(c, kind)
            if k and has(ws, base, k):
                put(ws, out_r, c, f'=IFERROR({L(c)}{base}/{L(k)}{base}-1,"n.a.")', PCT_FMT)


def margin(ws, base, rev, cost, pm):
    neg = ""
    if cost:
        for c in sorted(pm.per):
            v = ws.cell(base, c).value
            if isinstance(v, (int, float)):
                if v < 0: neg = "-"
                break
    labels = LABELS["Mcost" if cost else "M"]
    insert_analysis(ws, base, labels, pm)
    if rev > base: rev += len(labels)
    pct = base + 1
    for c in sorted(pm.per):
        if has(ws, base, c) and has(ws, rev, c):
            put(ws, pct, c, f'=IFERROR({neg}{L(c)}{base}/{L(c)}${rev},"n.a.")', PCT_FMT)
    for c in sorted(pm.per):
        k = pm.compare(c, "yoy")
        if k and has(ws, pct, c) and has(ws, pct, k):
            put(ws, pct + 1, c, f'=IFERROR(({L(c)}{pct}-{L(k)}{pct})*10000,"n.a.")', BPS_FMT)
    growth(ws, pct + 2, base, "yoy", pm)
    if not cost:
        for c in sorted(pm.per):
            k = pm.compare(c, "yoy")
            if k and has(ws, base, c) and has(ws, base, k) and has(ws, rev, c) and has(ws, rev, k):
                put(ws, pct + 3, c, f'=IFERROR(({L(c)}{base}-{L(k)}{base})/({L(c)}${rev}-{L(k)}${rev}),"n.a.")', PCT_FMT)
    return len(labels)


def run(ws, specs):
    pm = PeriodMap(ws)
    targets = []
    for s in specs:
        r0, r1 = section_bounds(ws, s.get("section", "NON-GAAP METRICS"))
        base = next((r for r in range(r0, r1) if norm(ws.cell(r, 2).value) == norm(s["row"])), None)
        if base is None: raise SystemExit(f"row '{s['row']}' not found in {s.get('section')}")
        nxt = norm(ws.cell(base + 1, 2).value)
        if nxt in ("% yoy", "% margin", "% of sales"): print(f"skip {s['row']}: already has analysis rows"); continue
        targets.append((base, s))
    done = []
    for base, s in sorted(targets, key=lambda t: -t[0]):          # bottom-up, like the macros
        if s["macro"] in ("G", "Y"):
            labels = LABELS[s["macro"]]; insert_analysis(ws, base, labels, pm)
            for i, kind in enumerate(["yoy", "2yr", "qoq"][:len(labels)]): growth(ws, base + 1 + i, base, kind, pm)
        else:
            rv = s.get("revenue", {"section": "INCOME STATEMENT", "label": "^revenue"})
            rev = find_row(ws, rv["label"], rv.get("section"))
            margin(ws, base, rev, s.get("cost", False), pm)
        done.append(f"{s['macro']} on '{s['row']}'")
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--spec", default=None); ap.add_argument("--plan", default=None)
    a = ap.parse_args()
    specs = json.loads(a.spec) if a.spec else json.load(open(a.plan))["analysis"]
    wb = openpyxl.load_workbook(a.model); ws = wb[wb.sheetnames[0]]
    done = run(ws, specs)
    wb.calculation.fullCalcOnLoad = True; import safe_save; safe_save.safe_save(wb, a.model, a.out)   # never openpyxl's save: it drops the user's text boxes / shapes
    import modfill; modfill.fix(a.out, a.out)   # the user's MOD fill convention (quarters plain, years grey), every save
    import notebox; notebox.fix(a.out, a.out)   # note boxes open readable (none squashed next to spacer / hidden columns), every save
    print("analysis rows added:", "; ".join(done))


if __name__ == "__main__":
    main()
