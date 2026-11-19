# skills/model-earnings-after/scripts/verify.py
"""(Copied from model-earnings-before, Nov 2026; keep in sync. Changes: only bands 9-15 are ours, so error cells
above layout 'start' are reported as a warning, and only when the input copy did not already show them; the Call
Notes tab is checked too; no Consensus block.) Recalculate the built copy once in LibreOffice and check it before it
replaces the user's file: every checked cell on the Earnings tab (layout.json 'expected') recalculates to
aftermath's value (rel 1e-6; text equal; an expected None means #N/A), no other cell in bands 9-15 shows an error,
and the Call Notes tab has no error cell and holds this quarter's column.

usage: python3 verify.py --out OUT.xlsx --work W     (prints JSON; exit 1 if any problem)"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import openpyxl  # noqa: E402

import callnotes  # noqa: E402
from earnings_tab import TAB  # noqa: E402

ERRORS = ("#N/A", "#VALUE!", "#REF!", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!", "Err:")


def close(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) <= max(1e-9, 1e-6 * max(abs(a), abs(b)))
    return str(a).strip() == str(b).strip()


def _err(v):
    return isinstance(v, str) and v.startswith(ERRORS)


def errors(ws, below=None):
    """{coordinate: error text} of the error cells, only rows < below when given."""
    return {c.coordinate: c.value for row in ws.iter_rows(max_row=(below - 1) if below else None) for c in row
            if _err(c.value)}


def compare(values, layout, quarter, before=None):
    """(problems, warnings). before = the recalculated input (context.json 'values'): error cells above the start
    that it already showed are not ours."""
    wb = openpyxl.load_workbook(values, data_only=True)
    ws, out, warn, start = wb[TAB], [], [], layout["start"]
    for ref, want in layout["expected"].items():
        got = ws[ref.replace("$", "")].value
        if want is None:
            if not (isinstance(got, str) and got.startswith("#N/A")):
                out.append(f"{TAB}!{ref}: expected #N/A, got {got!r}")
        elif not close(got, want):
            out.append(f"{TAB}!{ref}: expected {want!r}, got {got!r}")
    mine = {r.replace("$", "") for r in layout["expected"]}
    for row in ws.iter_rows(min_row=start):
        for c in row:
            if _err(c.value) and c.coordinate not in mine:
                out.append(f"{TAB}!{c.coordinate}: {c.value}")
    old = set()
    if before and os.path.exists(before):
        wb0 = openpyxl.load_workbook(before, data_only=True)
        old = set(errors(wb0[TAB], start)) if TAB in wb0.sheetnames else set()
    new = sorted(set(errors(ws, start)) - old)
    if new:
        warn.append(f"{len(new)} error cell(s) in bands 1-8 of the {TAB} tab that the input did not show (not "
                    f"this skill's cells): {', '.join(new[:10])}{' ...' if len(new) > 10 else ''}.")
    if callnotes.TAB not in wb.sheetnames:
        out.append(f"no {callnotes.TAB} tab")
    else:
        cn = wb[callnotes.TAB]
        out += [f"{callnotes.TAB}!{k}: {v}" for k, v in errors(cn).items()]
        head = next((r for r in cn.iter_rows() if r[0].value == callnotes.HEADER), None)
        if head is None or quarter not in [str(c.value).strip() for c in head[1:] if c.value is not None]:
            out.append(f"{callnotes.TAB}: no column for {quarter}")
    return out, warn


def run(out, work):
    import lo
    vals = lo.recalc(out, os.path.join(work, "values_out"))
    ctx = json.load(open(os.path.join(work, "context.json")))
    problems, warnings = compare(vals, json.load(open(os.path.join(work, "layout.json"))), ctx["quarter"],
                                 ctx.get("values"))
    return {"problems": problems, "warnings": warnings, "recalculated": vals}


def main():
    ap = argparse.ArgumentParser(description="Recalculate the built copy once and check it.")
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    r = run(a.out, a.work)
    print(json.dumps(r, indent=1))
    sys.exit(1 if r["problems"] else 0)


if __name__ == "__main__":
    main()
