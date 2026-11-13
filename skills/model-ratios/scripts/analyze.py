"""Insert the analysis rows and sections into MOD (the house layout): % yoy / margin rows under each line,
ROIC, ROE, ROA + LEVERAGE & CASH CONVERSION after the balance sheet, FREE CASH FLOW after the cash flow statement.
Existing rows move down; every formula in the workbook is re-pointed so nothing changes value.

usage: python3 analyze.py --model <TICKER_model.xlsx> --work <_model_work> [--src <gather folder>]
                          [--decisions <analyze_decisions.json>] [--replace]
Exit codes: 0 written | 2 MOD already has analysis rows (ask the user; --replace removes this skill's rows and
            rebuilds them) | 1 error. Copies the file to <work>/before_analyze.xlsx before writing."""
import argparse
import json
import os
import re
import shutil
import sys
from copy import copy

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Color, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

from adjust import ytd_values, adj_cell, period_ends, quarter_days
from evaluate import Book, ERR
from formulas import growth, margin, pct_sales, bps, incremental, for_estimate
from periods import Periods, HDR
from recipe import build_layout, Ctx, SUBTOTAL, TOTAL, SUB_ROWS, INDENTED, SECTIONS, IC_DEFAULT, CASH_ROLES, LABELS
from roles import find_roles, addon_rows, analysis_section_rows, norm
from rowmap import remap_rows

GREEN, BLUE, BLACK = "FF008000", "FF0000FF", "FF000000"
FMT = {
    "pct": "#,##0.0%_);(#,##0.0%)", "bps": "#,##0_);(#,##0)", "pct1": '0.0%_);\\(0.0%\\);"-"_)',
    "x": '0.0"x"_);\\(0.0"x"\\);"-"_)', "days": '#,##0.0_);\\(#,##0.0\\);"-"_)', "int": '#,##0_);\\(#,##0\\);"-"_)',
}
AUTHOR = "model-ratios"
# the DXCM example shading: FY columns grey ("Background 2", darker 10%); the inserted section headers a lighter
# sub-section blue, like their NON-GAAP METRICS header
FY_FILL = PatternFill("solid", fgColor=Color(theme=2, tint=-0.0999786370433668))
SUB_FILL = PatternFill("solid", fgColor=Color(theme=3, tint=0.249977111117893))
METRIC_LABELS = set(LABELS.values())


def our_rows(mod):
    """rows this skill inserted: its three sections (+ the blank row before FREE CASH FLOW) and the standard
    analysis rows (% yoy, % margin...) outside the non-GAAP / KPI sections, which carry their own"""
    addon, out = addon_rows(mod), set(analysis_section_rows(mod))
    for r in range(1, mod.max_row + 1):
        lab = mod.cell(r, 2).value
        if r not in addon and isinstance(lab, str) and lab.strip() in METRIC_LABELS: out.add(r)
        if norm(mod.cell(r, 1).value).startswith("free cash flow") and r > 1 and \
                all(mod.cell(r - 1, c).value in (None, "") for c in range(1, mod.max_column + 1)):
            out.add(r - 1)
    return out


def outlier_flags(wb, layout, keys, p, notes):
    """Report-only checks on reported FY columns: tax rate outside 0-40%, ROIC > 100%, invested capital <= 0."""
    b, out = Book(wb), []
    checks = [("TAXRATE", lambda v: v < 0 or v > 0.40, "tax rate {v:.1%} is outside 0-40%; NOPAT and ROIC use it as-is"),
              ("ROIC_A", lambda v: v > 1.0, "ROIC (asset) {v:.1%} is above 100%"),
              ("ROIC_M", lambda v: v > 1.0, "ROIC (minus cash) {v:.1%} is above 100%"),
              ("ICAVG_A", lambda v: v <= 0, "average invested capital (asset) {v:,.1f} is zero or negative"),
              ("ICAVG_M", lambda v: v <= 0, "average invested capital (minus cash) {v:,.1f} is zero or negative")]
    for key, bad, msg in checks:
        if key not in keys: continue
        for c, (q, y, est) in p.cols.items():
            if q != 0 or est: continue
            v = b.value("MOD", f"{L(c)}{keys[key]}")
            if not isinstance(v, (int, float)) or v is ERR or not bad(v): continue
            label = p.label(c)
            text = f"Outlier: {msg.format(v=v)}." + (f" Likely cause: {notes[label]}." if label in notes else "")
            out.append(("Outlier", f"{label} {key}", text, keys[key], c))
    return out


def write_judgment_calls(path, model, decisions, log, flags):
    t = os.path.basename(model).split("_model")[0]
    with open(path, "w") as f:
        f.write(f"# {t} analysis - judgment calls\n\nModel: {os.path.basename(model)} | tab MOD\n\n## Decisions\n\n")
        for n in decisions.get("notes", []): f.write(f"- {n}\n")
        if not decisions.get("fcf_adjustments"):
            f.write(f"- **No FCF adjustments:** FCF = CFO - capex. {decisions.get('fcf_note', '')}\n")
        for kind, what, why in log: f.write(f"- **{kind}:** {what} - {why}\n")
        f.write("\n## Outlier flags (numbers unchanged)\n\n")
        for _, what, text, _, _ in flags: f.write(f"- {what}: {text}\n")
        if not flags: f.write("- none\n")


def styled(base, color=None, italic=None, bold=None):
    """MOD's font name and size, with only italic / bold / colour changed."""
    return Font(name=base.name, sz=base.sz, b=bool(bold), i=bool(italic), color=color)


def recolor(cell, color, italic=None, bold=None):
    f = cell.font
    cell.font = Font(name=f.name, sz=f.sz, b=f.b if bold is None else bold, i=f.i if italic is None else italic,
                     u=f.u, color=color)


def is_link(v):
    return isinstance(v, str) and bool(re.fullmatch(r"=\$?[A-Z]{1,3}\$?\d+", v))


def ic_lines(decisions, roles, log):
    """the invested-capital lines the user's formula uses, minus any this MOD has no row for (logged)"""
    ic = decisions.get("invested_capital") or IC_DEFAULT
    out = {}
    for part in ("operating_assets", "nibcl"):
        out[part] = [k for k in ic[part] if k in roles]
        gone = [k for k in ic[part] if k not in roles]
        if gone and decisions.get("invested_capital"):        # default lines a company doesn't report are expected
            log.append(("Invested capital", f"{part}: no MOD row for {', '.join(gone)}", "left out of the sum"))
    log.append(("Invested capital", f"asset based = ({' + '.join(out['operating_assets'])}) - ({' + '.join(out['nibcl'])}); "
                f"minus cash = the same without {' / '.join(CASH_ROLES)}",
                ic.get("note") or "default lines (the DXCM example choice); no invested_capital in the decisions file"))
    return out


def run(model, work, src=None, decisions=None, replace=False):
    decisions = decisions or {}
    wb = openpyxl.load_workbook(model)
    mod = wb["MOD"]
    log = []
    if analysis_section_rows(mod) and not replace:
        return {"code": 2, "message": "MOD already has analysis sections (ROIC / FREE CASH FLOW...). Ask the user before "
                                      "rebuilding; --replace removes this skill's rows and rebuilds them."}
    # the pre-analyze copy verify.py compares against; it lives in the work folder and the skill deletes it once
    # verify passes (the user keeps no old model versions, 2026-11-08)
    os.makedirs(work, exist_ok=True)
    backup = os.path.join(work, "before_analyze.xlsx")
    shutil.copy2(model, backup)
    if "ANALYZED" in wb.sheetnames:
        log.append(("Old ANALYZED tab", "left as it was (its links still point at the right MOD rows)",
                    "the analysis now lives in MOD; delete the tab when you no longer need it"))
    first = list(range(1, mod.max_row + 1))                      # backup row -> current row, for verify.py
    if replace:
        drop = our_rows(mod)
        kept = [r for r in range(1, mod.max_row + 1) if r not in drop]
        remap_rows(mod, {r: i for i, r in enumerate(kept, 1)})
        first = [kept.index(r) + 1 if r in kept else None for r in first]

    roles, starts, opex = find_roles(mod)
    p = Periods(mod)
    adj = decisions.get("fcf_adjustments", [])
    ic = ic_lines(decisions, roles, log)
    layout = build_layout(mod, roles, starts, opex, [d["label"] for d in adj], ic)
    maxc = mod.max_column
    usd_fmt = mod.cell(roles["REV"], min(p.cols)).number_format
    sect_style = starts["BS"]
    lab_font = copy(mod.cell(roles["REV"], 2).font)
    val_font = copy(mod.cell(roles["REV"], min(p.cols)).font)
    new_of = {R.mod_row: i for i, R in enumerate(layout, 1) if R.kind == "keep"}
    remap_rows(mod, new_of)
    sect_style = new_of[sect_style]
    keys = {R.key: i for i, R in enumerate(layout, 1) if R.key}
    ctx = Ctx(keys, p)
    ws = mod

    filings_path = os.path.join(work, "filings.json")
    filings = json.load(open(filings_path)) if os.path.exists(filings_path) else {}
    if adj and not filings:
        raise SystemExit(f"FCF adjustments requested but {filings_path} is missing - rerun model-historicals extract.py into {work}.")
    ytds = [ytd_values(filings, d["pattern"]) for d in adj]
    man = os.path.join(src, "_manifest.json") if src else None
    ends = period_ends(man) if man and os.path.exists(man) else {}
    missing_days = []

    for r, R in enumerate(layout, 1):
        if R.kind == "keep":
            continue
        elif R.kind == "section":
            for c in range(1, maxc + 1):
                ws.cell(r, c)._style = copy(mod.cell(sect_style, c)._style)
                ws.cell(r, c).fill = SUB_FILL
            ws.cell(r, 1).value, ws.cell(r, 3).value = R.label, "Units"
        elif R.kind == "label":
            ws.cell(r, 2).value = R.label
        elif R.kind == "metric":
            lab = ws.cell(r, 2)
            lab.value = R.label
            lab.font, lab.alignment = styled(lab_font, BLACK, italic=True), Alignment(indent=2)
            for c in p.cols:
                f = metric_formula(R, c, p, keys)
                if f is None: continue
                cell = ws.cell(r, c)
                cell.value = for_estimate(f) if p.is_est(c) else f
                cell.number_format, cell.font, cell.alignment = FMT[R.fmt], styled(val_font, BLACK), Alignment(horizontal="right")
        elif R.kind == "kpi":
            ws.cell(r, 2).value, ws.cell(r, 3).value = R.label, R.units
            ws.cell(r, 2).font = styled(lab_font, bold=R.bold, italic=R.key in SUB_ROWS)
            if R.key in SUB_ROWS | INDENTED: ws.cell(r, 2).alignment = Alignment(indent=2)
            if R.key in SUBTOTAL | TOTAL:
                line = Border(top=Side("thin"), bottom=Side("double") if R.key in TOTAL else Side())
                for c in range(2, maxc + 1): ws.cell(r, c).border = line
            for c in p.cols:
                na_role = None
                try:
                    f = R.calc(ctx, c)
                except KeyError as e:
                    f = "n.a."
                    na_role = e.args[0] if e.args else "?"
                    if not any(m == R.key for _, m, _ in log):
                        log.append(("Missing row", R.key, f"MOD has no row for role {e}; {R.label} shows n.a."))
                if f is None: continue
                cell = ws.cell(r, c)
                if f.startswith("=") and not is_link(f) and not f.startswith("=IFERROR("):
                    f = f'=IFERROR({f[1:]},"n.a.")'                 # every KPI division/chain fails soft
                if p.is_est(c) and f.startswith("=") and not is_link(f):
                    f = for_estimate(f)
                cell.value = f
                cell.number_format = usd_fmt if R.fmt == "usd" else FMT[R.fmt]
                cell.font = styled(val_font, GREEN if is_link(f) else BLACK, bold=R.bold)
                if na_role: cell.comment = Comment(f"n.a.: MOD has no row for {na_role}.", AUTHOR)
        elif R.kind == "adj":
            d = adj[R.adj]
            lab = ws.cell(r, 2)
            lab.value, ws.cell(r, 3).value = R.label, R.units
            lab.comment = Comment(d["note"], AUTHOR)
            gaps = []
            for c in p.cols:
                v = adj_cell(ytds[R.adj], p, c, r)
                if v is None:
                    if not p.is_est(c): gaps.append(p.label(c))
                    continue
                cell = ws.cell(r, c)
                cell.value, cell.number_format, cell.font = v, usd_fmt, styled(val_font, BLUE)
                cell.comment = Comment(f"{d['note']}\nFiling line: /{d['pattern']}/ (year-to-date converted to quarters).", AUTHOR)
            log.append(("FCF adjustment", R.label, d["note"] + (f" No parsed filing for: {', '.join(gaps)}." if gaps else "")))
        elif R.kind == "days":
            ws.cell(r, 2).value, ws.cell(r, 3).value = R.label, R.units
            ws.cell(r, 2).comment = Comment("Days come from the period-end dates of the 10-Qs and 10-Ks in the /collect-documents "
                                            "manifest. Estimate columns assume 91 days per quarter and 365 per "
                                            "annual-only year.", AUTHOR)
            for c in p.cols:
                q, y, est = p.cols[c]
                cell = ws.cell(r, c)
                if q == 0:
                    q1, q4 = p.find(1, y), p.find(4, y)
                    cell.value = f"=SUM({L(q1)}{r}:{L(q4)}{r})" if q1 and q4 else 365
                else:
                    n = None if est else quarter_days(ends, q, y)
                    if n is None and not est: missing_days.append(p.label(c))
                    cell.value = n or 91
                    if not n and not est:
                        cell.comment = Comment("Assumed 91 days: no period-end date for this quarter in the /collect-documents manifest.", AUTHOR)
                cell.number_format = FMT["int"]
                cell.font = styled(val_font, BLACK if isinstance(cell.value, str) else BLUE)
    if missing_days:
        log.append(("Days in period", "assumed 91 days", "no period-end dates in the /collect-documents manifest for: " + ", ".join(missing_days)))
    for key, c, text in ctx.notes:
        cell = ws.cell(keys[key], c)
        cell.comment = Comment(text, AUTHOR)
        if ("Tax rate fallback", text) not in [(t, w) for t, w, _ in log]:
            log.append(("Tax rate fallback", text, "current-year quarters"))
    for c, (q, _, _) in p.cols.items():
        if q != 0: continue
        for r, R in enumerate(layout, 1):
            if R.kind != "keep" and not ws.cell(r, c).fill.fill_type: ws.cell(r, c).fill = FY_FILL
    flags = outlier_flags(wb, layout, keys, p, decisions.get("outlier_notes", {}))
    for _, _, text, r, c in flags:
        cell = ws.cell(r, c)
        cell.comment = Comment((cell.comment.text + "\n" if cell.comment else "") + text, AUTHOR)
    wb.calculation.fullCalcOnLoad = True
    import safe_save; safe_save.safe_save(wb, model, model)   # never openpyxl's save: it drops the user's text boxes / shapes
    import modfill; modfill.fix(model, model)   # the user's MOD fill convention (quarters plain, years grey), every save
    import notebox; notebox.fix(model, model)   # note boxes open readable (none squashed next to spacer / hidden columns), every save
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(work, "analyze_rowmap.json"), "w") as f:      # backup row -> row now (None = removed)
        json.dump({"backup": os.path.basename(backup),
                   "rows": {str(i): (new_of[r] if r else None) for i, r in enumerate(first, 1)}}, f)
    write_judgment_calls(os.path.join(work, "ANALYZE_JUDGMENT_CALLS.md"), model, decisions, log, flags)
    return {"code": 0, "log": log, "flags": [(k, w, t) for k, w, t, _, _ in flags], "rows": len(layout), "backup": backup}


def metric_formula(R, c, p, keys):
    base, rev = keys[R.base], keys["REV"]
    if R.metric in ("yoy", "2yr", "qoq"):
        k = {"yoy": p.yoy, "2yr": p.two_year, "qoq": p.qoq}[R.metric](c)
        return None if k is None else growth(base, c, k)
    if R.metric == "margin":
        return margin(base, c, rev)
    if R.metric == "pct_sales":
        return pct_sales(base, c, rev)
    k = p.yoy(c)
    if k is None:
        return None
    if R.metric == "bps":
        return bps(keys[R.pct], c, k)
    return incremental(base, c, k, rev)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--work", required=True)
    ap.add_argument("--src", default=None); ap.add_argument("--decisions", default=None)
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args()
    dec = json.load(open(a.decisions)) if a.decisions and os.path.exists(a.decisions) else {}
    res = run(a.model, a.work, a.src, dec, a.replace)
    print(res["message"] if "message" in res else f"wrote the analysis into MOD ({res['rows']} rows) of {a.model}; backup {res['backup']}")
    sys.exit(res["code"])


if __name__ == "__main__":
    main()
