# skills/model-summary/scripts/verify.py
"""Recalculate the built copy once in LibreOffice and check SUM before it replaces the user's file: every SUM cell
that is a plain link (=Tab!$C$R) equals the cell it points at; no SUM cell shows #REF!, #NAME?, #DIV/0!, #VALUE! or
Err: (#N/A is SUM's deliberate n/a); the IRR equals (3-year target / price)^(1/years) - 1.

usage: python3 verify.py --out OUT.xlsx --work W     (prints JSON; exit 1 if any problem)"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import openpyxl  # noqa: E402

LINK = re.compile(r"^='?([^'!]+)'?!\$([A-Z]+)\$(\d+)$")
BAD = ("#REF!", "#NAME?", "#DIV/0!", "#VALUE!", "Err:")


def close(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) <= max(1e-9, 1e-6 * max(abs(a), abs(b)))
    return str(a).strip() == str(b).strip()


def compare(built, values, lay):
    fw, vw = openpyxl.load_workbook(built), openpyxl.load_workbook(values, data_only=True)
    vs, problems, n = vw["SUM"], [], 0
    for row in fw["SUM"].iter_rows():
        for c in row:
            got = vs[c.coordinate].value
            if isinstance(got, str) and got.startswith(BAD):
                problems.append(f"SUM!{c.coordinate}: {got}")
            m = LINK.match(c.value) if isinstance(c.value, str) else None
            if m:
                n += 1
                src = vw[m.group(1)][f"{m.group(2)}{m.group(3)}"].value
                if not close(got, src):
                    problems.append(f"SUM!{c.coordinate} = {got!r} but {m.group(1)}!{m.group(2)}{m.group(3)} = {src!r}")
    R = lay["refs"]
    p, t, y, irr = (vs[R[k]].value for k in ("price", "target3", "years", "irr"))
    if all(isinstance(v, (int, float)) for v in (p, t, y, irr)) and t > 0 and not close(irr, (t / p) ** (1 / y) - 1):
        problems.append(f"SUM!{R['irr']} IRR {irr} != ({t}/{p})^(1/{y})-1")
    return problems, n


def run(out, work):
    import lo
    vals = lo.recalc(out, os.path.join(work, "values_out"))
    problems, n = compare(out, vals, json.load(open(os.path.join(work, "layout.json"))))
    return {"problems": problems, "checked_links": n, "recalculated": vals}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    r = run(a.out, a.work)
    print(json.dumps(r, indent=1))
    sys.exit(1 if r["problems"] else 0)


if __name__ == "__main__":
    main()
