"""Recalculate the built model in LibreOffice and check the Multiples tab (spec §3.4):
- every checked cell (layout.json "expected") recalculates to engine.py's value (relative 1e-6; None = #N/A);
- no error values other than #N/A on the tab;
- every other part of the workbook is byte-identical to the input (the old Multiples tab's parts may change or go);
- a PNG of the tab for Claude to look at.

usage: python3 verify.py --model M --out OUT --work W"""
import argparse
import datetime as dt
import json
import math
import os
import zipfile

import openpyxl

import lo
from xlsx import Package, relpath_of, resolve

ALLOWED = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml", "xl/styles.xml", "xl/calcChain.xml",
           "docProps/app.xml"}
TAB = "Multiples"


def tab_parts(path):
    pkg = Package(path)
    todo = [p for n, _, _, p in pkg.sheets() if n == TAB]
    seen = set()
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen |= {p, relpath_of(p)}
        todo += [resolve(p, t) for _, (_, t) in pkg.rels(relpath_of(p)).items() if "TargetMode" not in t]
    return seen


def close(a, b):
    if isinstance(a, dt.datetime):                        # date-formatted cells read back as datetimes
        a = (a - dt.datetime(1899, 12, 30)).total_seconds() / 86400
    if b is None:
        return a in (None, "#N/A")
    if isinstance(b, str):                                # a text formula (the line's reading)
        return a == b
    if not isinstance(a, (int, float)):
        return False
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9)


def find_page(pdf):
    """PDF page of the Multiples tab: the one whose text has the tab's title (one page per tab, so not page 1)."""
    import fitz
    for i, pg in enumerate(fitz.open(pdf)):
        if "multiples: where the stock trades" in pg.get_text().lower():
            return i
    raise ValueError("no page with the Multiples title")


def run(model, out, work):
    lay = json.load(open(os.path.join(work, "layout.json")))
    rec = lo.recalc(out, os.path.join(work, "verify"))
    ws = openpyxl.load_workbook(rec, read_only=False, data_only=True)[TAB]
    failed = [{"cell": ref, "got": ws[ref].value, "want": want} for ref, want in lay["expected"].items()
              if not close(ws[ref].value, want)]
    errors = [c.coordinate for row in ws.iter_rows() for c in row
              if isinstance(c.value, str) and c.value.startswith("#") and c.value != "#N/A"]
    a, b = zipfile.ZipFile(model), zipfile.ZipFile(out)
    skip = ALLOWED | tab_parts(model)
    changed = [n for n in a.namelist() if n not in skip and (n not in b.namelist() or a.read(n) != b.read(n))]
    pdf = lo.render_pdf(rec, os.path.join(work, "verify"))
    png = os.path.join(work, "multiples.png")
    try:
        lo.page_png(pdf, find_page(pdf), png)
    except Exception as e:                                # the PNG is for looking, not for passing
        png = f"not rendered: {e}"
    return {"checked": len(lay["expected"]), "failed": failed[:30], "errors": errors[:30], "changed_parts": changed,
            "png": png, "recalculated": rec, "ok": not failed and not errors and not changed}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    r = run(a.model, a.out, a.work)
    print(json.dumps(r, indent=1, default=str))
    raise SystemExit(0 if r["ok"] else 1)
