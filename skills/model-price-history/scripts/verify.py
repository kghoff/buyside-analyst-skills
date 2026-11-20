"""Check a built workbook: recalculate it in LibreOffice and compare every formula result with the pandas prototype,
look for Excel errors, prove nothing else in the workbook changed, and render the Idio Chart tab to PNG.

usage: python3 verify.py --before M.xlsx --built OUT.xlsx --work W [--refresh]
--refresh: BEFORE is the user's model with the old tabs; the tabs keep their places, and every shape carried by
refresh.py (W/carry.json) must be on the new Idio Chart unchanged.
Writes W/verify_report.md and W/idio_chart.png. Exit 1 on any failed check.
LibreOffice draws #N/A as 0 in its render while Excel leaves a gap; that is expected, not a bug."""
import argparse
import json
import math
import os
import re

import openpyxl

import build
import engine
import lo
from xlsx import Package

TOL = 1e-9
ALLOWED = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml", "xl/styles.xml", "xl/calcChain.xml",
           "docProps/app.xml"}
XL_ERRORS = {"#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#SPILL!", "#CALC!"}


def same(want, got):
    if isinstance(want, str):
        return (got or "") == want
    if want is None or (isinstance(want, float) and math.isnan(want)):
        return got in (None, "#N/A", "") or (isinstance(got, float) and math.isnan(got))
    return isinstance(got, (int, float)) and abs(got - want) <= TOL * max(1.0, abs(want))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True, help="the model before this skill ran (or with the old tabs removed)")
    ap.add_argument("--built", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    S = build.prepare(a.built, a.work)
    run, cfg = S["run"], S["cfg"]
    L = json.load(open(os.path.join(a.work, "layout.json")))
    DL, EL, R = L["daily"], L["events"], L["rows"]
    calc = lo.recalc(a.built, os.path.join(a.work, "_recalc"))
    wb = openpyxl.load_workbook(calc, data_only=True, read_only=True)
    grids = {}
    for t in build.TABS:
        ws = wb[t]
        grids[t] = {(r, c): v for r, row in enumerate(ws.iter_rows(values_only=True), 1) for c, v in enumerate(row, 1) if v is not None}
    from xlsx import colnum
    get = lambda t, col, r: grids[t].get((r, colnum(col)))
    checks, fails = 0, []

    def chk(what, t, col, r, want):
        nonlocal checks
        checks += 1
        got = get(t, col, r)
        if not same(want, got):
            fails.append(f"{what}: {t}!{col}{r} = {got!r}, expected {want!r}")

    n, b = len(run["dates"]), run["base"]
    for i in range(b + 1, n):
        r = R["R0"] + i
        chk("beta", "Px Data", DL["beta"], r, run["beta"][i])
        chk("idio", "Px Data", DL["idio"], r, run["idio"][i])
        chk("event label", "Px Data", DL["event"], r, run["label"][i])
        for k in run["okeys"]:
            chk(f"overlay {k}", "Px Data", DL["ov_" + k], r, run["daily"][k][i])
        for k in ("ttm_eps", "pe"):
            chk(k, "Px Data", DL[k], r, run["daily"][k][i])
        chk("ETF excess", "Px Data", DL["f_ind_x"], r, run["ind_x"][i])
        chk("MOM excess", "Px Data", DL["f_mom_x"], r, run["mom_x"][i])
    M = run["monthly"]
    for j in range(len(M["date"])):
        r = 5 + j
        got = get("Px Data", DL["m_date"], r)
        checks += 1
        if not (hasattr(got, "date") and got.date() == M["date"][j].date()):
            fails.append(f"month-end row {r}: {got} vs {M['date'][j].date()}")
        for k in ("close", "pe", "ttm_eps"):
            chk(f"monthly {k}", "Px Data", DL[{"close": "m_close"}.get(k, "m_" + k)], r, M[k][j])
    A = run["annual"]
    for j in range(len(A["fy"])):
        r = 5 + j
        for k, col in (("fcf", "a_fcf"), ("bb", "a_bb"), ("pe", "a_pe"), ("n", "a_n")):
            chk(f"annual {k}", "Px Data", DL[col], r, float(A[k][j]))
    W = run["weekly"]
    for j in range(len(W["date"])):
        r = 5 + j
        got = get("Px Data", DL["w_date"], r)
        checks += 1
        if not (hasattr(got, "date") and got.date() == W["date"][j].date()):
            fails.append(f"week-end row {r}: {got} vs {W['date'][j].date()}")
        for k in ("b_mkt", "b_ind", "b_mom", "r2", "idio3", "idx3", "pct3") + tuple(run["okeys"]):
            if j == 0 and k in ("b_mkt", "b_ind", "b_mom", "r2", "idio3"):
                continue
            chk(f"weekly {k}", "Px Data", DL["w_" + ("ov_" + k if k in run["okeys"] else k)], r, W[k][j])
    for k, q in enumerate(run["quarters"]):
        r = R["Q0"] + k
        for key in ["ttm_g", "ttm_n", "ttm_rev"] + run["okeys"]:
            chk(f"quarter {key}", "Px Events", EL[key], r, q[key])
    for k, e in enumerate(run["events"]):
        r = R["EV0"] + k
        got = get("Px Events", EL["e_react"], r)
        checks += 1
        want = e["reaction"]
        if not ((want is None and got in (None, "")) or (hasattr(got, "date") and want is not None and got.date() == want.date())):
            fails.append(f"reaction day {e['name']}: {got} vs {want}")
        if want is not None and engine.isnum(e.get("idio")):
            chk(f"event idio {e['name']}", "Px Events", EL["e_idio"], r, e["idio"])
    idio = [(v, i) for i, v in enumerate(run["idio"]) if engine.isnum(v)]
    up, down = sorted(idio, reverse=True)[:20], sorted(idio)[:20]
    for blk, lst in ((0, up), (1, down)):
        for k, (v, i) in enumerate(lst):
            r = 7 + blk * 25 + k
            chk("top-20 idio", "Idio Chart", "X", r, v)
            chk("top-20 event", "Idio Chart", "AA", r, run["label"][i])

    errors = [f"{t}!{openpyxl.utils.get_column_letter(c)}{r} = {v}" for t, g in grids.items() for (r, c), v in g.items()
              if isinstance(v, str) and (v in XL_ERRORS or v.startswith("Err:"))]

    before, after = Package(a.before), Package(a.built)
    import refresh
    keep = {p for p in before.parts} - (refresh.tab_parts(before) if a.refresh else set())
    new_tab_parts = set()
    for name, _, _, part in after.sheets():
        if name in build.TABS:
            new_tab_parts.add(part)
    moves = refresh.column_moves(before, after) if a.refresh else {}
    rows = refresh.row_moves(before, after, moves) if a.refresh else {}
    follow = lambda p: refresh.remap_formulas(before.text(p), moves, rows)[0].encode() if (moves or rows) and \
        p.startswith("xl/worksheets/") else before.parts[p]   # refresh: only references that follow may change
    changed = [p for p in keep if p not in ALLOWED and p in after.parts and follow(p) != after.parts[p]]
    missing = [p for p in keep if p not in ALLOWED and p not in after.parts]
    sheets_before = [s[0] for s in before.sheets()]
    sheets_after = [s[0] for s in after.sheets()]
    order_ok = (sheets_after == sheets_before if a.refresh else
                sheets_after[:len(sheets_before)] == [s for s in sheets_before if s not in build.TABS])
    lost = []
    if a.refresh:                                   # the user's shapes, each back unchanged (only its id may differ)
        d = refresh.drawing_of(after, refresh.sheet_parts(after)["Idio Chart"])
        now = {refresh.strip_id(m.group(0)) for m in refresh.ANCHOR.finditer(after.text(d))}
        carry = json.load(open(os.path.join(a.work, "carry.json")))
        lost = [f"shape not carried back: {s['name']}" for s in carry["shapes"] if refresh.strip_id(s["xml"]) not in now]

    pdf = lo.render_pdf(calc, os.path.join(a.work, "_render"))
    png = lo.page_png(pdf, sheets_after.index("Idio Chart"), os.path.join(a.work, "idio_chart.png"))

    ok = not fails and not errors and not changed and not missing and order_ok and not lost
    rep = [f"# verify: {'PASS' if ok else 'FAIL'}", "",
           f"- {checks:,} values compared with the prototype: {len(fails)} failed",
           f"- Excel errors (other than #N/A) on the three tabs: {len(errors)}",
           f"- other workbook parts changed: {len(changed)}; missing: {len(missing)}",
           f"- tab order: {sheets_after} ({'ok' if order_ok else 'CHANGED'})",
           *([f"- your shapes carried back unchanged: {len(carry['shapes']) - len(lost)} of {len(carry['shapes'])}"]
             if a.refresh else []),
           f"- render: {png}", ""]
    rep += ["## Failures", ""] + [f"- {x}" for x in (fails[:40] + errors[:40] + changed + missing + lost)] if not ok else []
    open(os.path.join(a.work, "verify_report.md"), "w").write("\n".join(rep) + "\n")
    print("\n".join(rep))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
