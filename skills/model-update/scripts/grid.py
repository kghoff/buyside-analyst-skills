"""Values of a workbook as {sheet: {ref: value}} (cached values; recalculated first with --recalc).

usage: python3 grid.py MODEL OUT.json [--recalc WORKDIR]"""
import json
import os
import sys

import openpyxl

ERRORS = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!")


def dump(path, recalc_dir=None):
    if recalc_dir:
        if os.path.realpath(recalc_dir) == os.path.realpath(os.path.dirname(os.path.abspath(path))):
            raise SystemExit(f"grid: recalc dir {recalc_dir} is the model's own folder; LibreOffice would write over "
                             "the user's workbook. Use <model dir>/_model_work/update/.")
        import lo
        path = lo.recalc(path, recalc_dir)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = {}
    for ws in wb.worksheets:
        g = {}
        for row in ws.iter_rows():
            for c in row:
                if getattr(c, "value", None) is not None and hasattr(c, "coordinate"):
                    g[c.coordinate] = c.value
        out[ws.title] = g
    wb.close()
    return out


def errors(g):
    return [f"{s}!{ref}" for s in g for ref, v in g[s].items() if isinstance(v, str) and v in ERRORS]


if __name__ == "__main__":
    rd = sys.argv[sys.argv.index("--recalc") + 1] if "--recalc" in sys.argv else None
    json.dump(dump(sys.argv[1], rd), open(sys.argv[2], "w"), default=str)
    print(os.path.abspath(sys.argv[2]))
