# skills/model-short/scripts/verify.py
"""Recalculate the built model once in LibreOffice and check the Short Check tab before it replaces the user's file:
every checked cell (layout.json 'expected') recalculates to shortmath's value (rel 1e-6; text and TRUE / FALSE equal;
an expected None means #N/A), and no other cell on the tab shows an error.

usage: python3 verify.py --out OUT.xlsx --work W     (prints JSON; exit 1 if any problem)"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import openpyxl  # noqa: E402

ERRORS = ("#N/A", "#VALUE!", "#REF!", "#DIV/0!", "#NAME?", "#NUM!", "Err:")


def _bool(v):
    """TRUE / FALSE as LibreOffice may hand them back: a bool, 1 / 0, or the text. Anything else: None."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and v in (0, 1):
        return bool(v)
    if isinstance(v, str) and v.strip().upper() in ("TRUE", "FALSE"):
        return v.strip().upper() == "TRUE"
    return None


def close(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        x, y = _bool(a), _bool(b)
        return x is not None and x == y
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= max(1e-9, 1e-6 * max(abs(a), abs(b)))
    return str(a).strip() == str(b).strip()


def compare(values, layout):
    ws = openpyxl.load_workbook(values, data_only=True)["Short Check"]
    out = []
    for ref, want in layout["expected"].items():
        got = ws[ref.replace("$", "")].value
        if want is None:
            if not (isinstance(got, str) and got.startswith("#N/A")):
                out.append(f"{ref}: expected #N/A, got {got!r}")
        elif not close(got, want):
            out.append(f"{ref}: expected {want!r}, got {got!r}")
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith(ERRORS) and c.coordinate not in layout["expected"]:
                out.append(f"{c.coordinate}: {c.value}")
    return out


def run(out, work):
    import lo
    vals = lo.recalc(out, os.path.join(work, "values_out"))
    layout = json.load(open(os.path.join(work, "layout.json")))
    return {"problems": compare(vals, layout), "recalculated": vals}


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
