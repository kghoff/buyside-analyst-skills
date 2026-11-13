"""Check a built workbook before it replaces the user's model:
- LibreOffice recalculation; every formula cell vs the skill's own figure (layout.json "expected")
- no Excel errors other than #N/A (deliberate chart gaps in the upgrade / downgrade columns)
- every other part of the workbook byte-identical (the old Consensus tab's parts may change or go)
- every typed number in the built tab has a note, unless its block carries a header note (layout.json "header_noted")
  or it is the user's own variance-table cell (layout.json "user")
- colour convention: typed numbers blue (stale broker estimates grey, layout.json "stale"), formulas never blue
- the user's variance-table entries carried over cell for cell (layout.json "preserved")
- a PNG of the Consensus tab for the agent to look at (LibreOffice draws #N/A as 0; Excel leaves a gap)

usage: python3 verify.py --before M.xlsx --built OUT.xlsx --work W     (exit 1 on any failure; writes W/verify_report.md)"""
import argparse
import datetime
import json
import math
import os
import re

import openpyxl
from openpyxl.utils.cell import range_boundaries
from openpyxl.worksheet.formula import ArrayFormula

import lo
from xlsx import Package, colnum, relpath_of, resolve

TAB = "Consensus"
TOL = 1e-9
ALLOWED = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml", "xl/styles.xml", "xl/calcChain.xml",
           "docProps/app.xml"}
BLUE, GREY = "FF0000FF", "FF808080"
XL_ERRORS = {"#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#SPILL!", "#CALC!"}


def serial(v):
    """Excel serial for a date/datetime (LibreOffice-recalculated date-formatted cells read back as datetime)."""
    if isinstance(v, datetime.datetime):
        d = v - datetime.datetime(1899, 12, 30)
        return d.days + d.seconds / 86400 + d.microseconds / 86400e6
    if isinstance(v, datetime.date):
        return float((v - datetime.date(1899, 12, 30)).days)
    return v


def same(want, got):
    got = serial(got)
    if want is None or (isinstance(want, float) and math.isnan(want)):
        return got in (None, "", "#N/A") or (isinstance(got, float) and math.isnan(got))
    return isinstance(got, (int, float)) and abs(got - want) <= TOL * max(1.0, abs(want))


def find_page(pdf, default):
    """PDF page of the Consensus tab: the page whose text has the tab's title (falls back to the tab's index)."""
    import fitz
    for i, pg in enumerate(fitz.open(pdf)):
        if "sell-side consensus" in pg.get_text().lower():
            return i
    return default


def crop_top(png, out, height=4000):
    """The top of the (very tall) tab as its own PNG, so it is readable."""
    from PIL import Image
    im = Image.open(png)
    im.crop((0, 0, im.width, min(height, im.height))).save(out)
    return out


def in_ranges(ref, ranges):
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    c, r = colnum(m.group(1)), int(m.group(2))
    for rg in ranges:
        c0, r0, c1, r1 = range_boundaries(rg)
        if c0 <= c <= c1 and r0 <= r <= r1:
            return True
    return False


def scan(built, L):
    """Read the built Consensus tab itself: typed numbers (numbers and dates, not formulas) without a note, and cells
    breaking the colour convention. The user's variance-table block is theirs, so it is skipped."""
    ws = openpyxl.load_workbook(built)[TAB]
    user_cells = [L["user"]] if L.get("user") else []
    stale = set(L.get("stale") or [])
    no_note, colour = [], []
    for row in ws.iter_rows():
        for c in row:
            v = c.value
            if v is None or in_ranges(c.coordinate, user_cells):
                continue
            rgb = getattr(c.font.color, "rgb", None) if c.font and c.font.color else None
            if isinstance(v, ArrayFormula) or (isinstance(v, str) and v.startswith("=")):
                if rgb == BLUE:
                    colour.append(f"{c.coordinate} is a formula in blue (blue = typed)")
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float, datetime.date)):
                continue
            if c.comment is None and not in_ranges(c.coordinate, L.get("header_noted") or []):
                no_note.append(c.coordinate)
            if not (rgb == BLUE or (rgb == GREY and c.coordinate in stale)):
                colour.append(f"{c.coordinate} is a typed number in {rgb or 'black'}, not blue")
    return {"no_note": no_note, "colour": colour}


def tab_parts(pkg):
    todo = [p for n, _, _, p in pkg.sheets() if n == TAB]
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
    grid = {(r, c): v for r, row in enumerate(wb[TAB].iter_rows(values_only=True), 1) for c, v in enumerate(row, 1)
            if v is not None}
    fails = []
    for ref, want in L["expected"].items():
        m = re.match(r"([A-Z]+)(\d+)$", ref)
        got = grid.get((int(m.group(2)), colnum(m.group(1))))
        if not same(want, got):
            fails.append(f"{ref} = {got!r}, expected {want!r}")
    errors = [f"{TAB}!{openpyxl.utils.get_column_letter(c)}{r} = {v}" for (r, c), v in grid.items()
              if isinstance(v, str) and (v in XL_ERRORS or v.startswith("Err:"))]
    raw = openpyxl.load_workbook(a.built)[TAB]
    lost = []
    for ref, (kind, content) in L["preserved"].items():
        v = raw[ref].value
        if kind == "fa":                                  # array formula: openpyxl hands back an ArrayFormula
            ok = getattr(v, "text", None) == "=" + content
        else:
            ok = (v == "=" + content) if kind == "f" else (v == content)
        if not ok:
            lost.append(f"{ref}: had {content!r}, now {v!r}")
    before, after = Package(a.before), Package(a.built)
    skip = ALLOWED | tab_parts(before)
    changed = [p for p in before.parts if p not in skip and p in after.parts and before.parts[p] != after.parts[p]]
    missing = [p for p in before.parts if p not in skip and p not in after.parts]
    sheets = [s[0] for s in after.sheets()]
    sc = scan(a.built, L)
    pdf = lo.render_pdf(calc, os.path.join(a.work, "_render"))
    png = lo.page_png(pdf, find_page(pdf, sheets.index(TAB)), os.path.join(a.work, "consensus.png"))
    top = crop_top(png, os.path.join(a.work, "consensus_top.png"))
    ok = not (fails or errors or lost or changed or missing or sc["no_note"] or sc["colour"])
    rep = [f"# verify: {'PASS' if ok else 'FAIL'}", "",
           f"- {len(L['expected']):,} formula cells compared with the skill's own figures: {len(fails)} failed",
           f"- Excel errors (other than #N/A): {len(errors)}",
           (f"- the user's variance-table cells carried over: {len(L['preserved']) - len(lost)} of {len(L['preserved'])}"
            if L.get("carried_over") else
            f"- variance-table skeleton written (first build): {len(L['preserved']) - len(lost)} of {len(L['preserved'])} cells"),
           f"- other workbook parts changed: {len(changed)}; missing: {len(missing)}",
           f"- typed numbers without a note: {len(sc['no_note'])}",
           f"- colour convention breaks (typed not blue / formula blue): {len(sc['colour'])}",
           f"- tabs: {sheets}", f"- render: {png} (whole tab; top section: {top})", ""]
    if not ok:
        rep += ["## Failures", ""] + [f"- {x}" for x in fails[:40] + errors[:40] + lost + changed + missing +
                                      [f"no note: {x}" for x in sc["no_note"][:20]] + sc["colour"][:20]]
    open(os.path.join(a.work, "verify_report.md"), "w").write("\n".join(rep) + "\n")
    print("\n".join(rep))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
