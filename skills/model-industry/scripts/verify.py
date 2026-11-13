"""Check a built workbook: LibreOffice recalc, every cell vs the Python prototype (layout.json "expected"),
Excel errors, byte identity of every other part, notes on every typed number, and a PNG of Industry Comparison.

usage: python3 verify.py --before M.xlsx --built OUT.xlsx --work W   (--before = the model as it was, old tabs and all)
Writes W/verify_report.md and W/industry_comparison.png. Exit 1 on any failed check.
#N/A is expected in ratio rows (chart gaps); LibreOffice draws it as 0 in the render, Excel leaves a gap."""
import argparse
import json
import math
import os
import re

import openpyxl

import build
import lo
from xlsx import Package, colnum, relpath_of, resolve

TOL = 1e-9
ALLOWED = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml", "xl/styles.xml", "xl/calcChain.xml",
           "docProps/app.xml"}
XL_ERRORS = {"#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#SPILL!", "#CALC!"}


def same(want, got):
    if want is None or (isinstance(want, float) and math.isnan(want)):
        return got in (None, "", "#N/A") or (isinstance(got, float) and math.isnan(got))
    return isinstance(got, (int, float)) and abs(got - want) <= TOL * max(1.0, abs(want))


def tab_parts(pkg):
    """Every part reachable from the Industry tabs (sheet, drawing, charts, comments, vml, and their rels). A
    --replace rebuild reuses these freed part names, so they are expected to change or go."""
    todo = [p for n, _, _, p in pkg.sheets() if n in build.TABS]
    seen = set()
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen |= {p, relpath_of(p)}
        todo += [resolve(p, tgt) for _, (_, tgt) in pkg.rels(relpath_of(p)).items() if "TargetMode" not in tgt]
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--built", required=True)
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    L = json.load(open(os.path.join(a.work, "layout.json")))
    calc = lo.recalc(a.built, os.path.join(a.work, "_recalc"))
    wb = openpyxl.load_workbook(calc, data_only=True, read_only=True)
    grids = {}
    for t in build.TABS:
        grids[t] = {(r, c): v for r, row in enumerate(wb[t].iter_rows(values_only=True), 1)
                    for c, v in enumerate(row, 1) if v is not None}
    fails = []
    for ref, want in L["expected"].items():
        tab, cell = ("Industry Comparison", ref[3:]) if ref.startswith("IC!") else ("Industry P&L", ref)
        m = re.match(r"([A-Z]+)(\d+)$", cell)
        got = grids[tab].get((int(m.group(2)), colnum(m.group(1))))
        if not same(want, got):
            fails.append(f"{tab}!{cell} = {got!r}, expected {want!r}")
    errors = [f"{t}!{openpyxl.utils.get_column_letter(c)}{r} = {v}" for t, g in grids.items() for (r, c), v in g.items()
              if isinstance(v, str) and (v in XL_ERRORS or v.startswith("Err:"))]
    before, after = Package(a.before), Package(a.built)
    skip = ALLOWED | tab_parts(before)
    changed = [p for p in before.parts if p not in skip and p in after.parts and before.parts[p] != after.parts[p]]
    missing = [p for p in before.parts if p not in skip and p not in after.parts]
    sheets_after = [s[0] for s in after.sheets()]
    pdf = lo.render_pdf(calc, os.path.join(a.work, "_render"))
    png = lo.page_png(pdf, sheets_after.index("Industry Comparison"), os.path.join(a.work, "industry_comparison.png"))
    ok = not fails and not errors and not changed and not missing and not L["typed_without_note"]
    rep = [f"# verify: {'PASS' if ok else 'FAIL'}", "",
           f"- {len(L['expected']):,} cells compared with the prototype: {len(fails)} failed",
           f"- Excel errors (other than #N/A): {len(errors)}",
           f"- other workbook parts changed: {len(changed)}; missing: {len(missing)}",
           f"- typed numbers without a note: {len(L['typed_without_note'])}",
           f"- tabs: {sheets_after}", f"- render: {png}", ""]
    if not ok:
        rep += ["## Failures", ""] + [f"- {x}" for x in fails[:40] + errors[:40] + changed + missing +
                                      L["typed_without_note"][:20]]
    open(os.path.join(a.work, "verify_report.md"), "w").write("\n".join(rep) + "\n")
    print("\n".join(rep))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
