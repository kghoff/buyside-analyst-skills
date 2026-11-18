# skills/model-earnings-before/scripts/verify.py
"""Recalculate the built model once in LibreOffice and check it before it replaces the user's file: every checked
cell on the Earnings tab (layout.json 'expected') and in the Consensus block ('expected_cons') recalculates to
earnmath's value (rel 1e-6; text equal; an expected None means #N/A), and no other cell on the Earnings tab shows an
error.

usage: python3 verify.py --out OUT.xlsx --work W     (prints JSON; exit 1 if any problem)"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import openpyxl  # noqa: E402

ERRORS = ("#N/A", "#VALUE!", "#REF!", "#DIV/0!", "#NAME?", "#NUM!", "Err:")


def close(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) <= max(1e-9, 1e-6 * max(abs(a), abs(b)))
    return str(a).strip() == str(b).strip()


def _cmp(ws, expected, tag, out):
    for ref, want in expected.items():
        got = ws[ref.replace("$", "")].value
        if want is None:
            if not (isinstance(got, str) and got.startswith("#N/A")):
                out.append(f"{tag}!{ref}: expected #N/A, got {got!r}")
        elif not close(got, want):
            out.append(f"{tag}!{ref}: expected {want!r}, got {got!r}")


def compare(values, layout):
    wb = openpyxl.load_workbook(values, data_only=True)
    ws, out = wb["Earnings"], []
    _cmp(ws, layout["expected"], "Earnings", out)
    if layout.get("expected_cons"):
        _cmp(wb["Consensus"], layout["expected_cons"], "Consensus", out)
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith(ERRORS) and c.coordinate not in layout["expected"]:
                out.append(f"Earnings!{c.coordinate}: {c.value}")
    return out


def run(out, work):
    import lo
    vals = lo.recalc(out, os.path.join(work, "values_out"))
    return {"problems": compare(vals, json.load(open(os.path.join(work, "layout.json")))), "recalculated": vals}


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
