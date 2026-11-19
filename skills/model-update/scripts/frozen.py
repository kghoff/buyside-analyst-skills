"""The pre-print forecast: Earnings band 7 (model-earnings-before) for this quarter, or preprint.json written here.

usage: python3 frozen.py ensure --model MODEL --quarter "Q3 26E" --values values.json --work DIR
       python3 frozen.py table --model MODEL --quarter "Q3 26E" --values values_after.json --work DIR --column L --out table.md [--state state.json]
A forecast placeholder (state.json) is not an actual: its row shows no actual and no difference."""
import argparse
import json
import os
import re
import sys

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modmap import ModMap   # noqa: E402

FROZEN_RE = re.compile(r"^7\. FROZEN FORECAST: (.+?), frozen (\d{4}-\d{2}-\d{2})")   # model-earnings-before build.py


def band7(model):
    wb = openpyxl.load_workbook(model, read_only=True)
    if "Earnings" not in wb.sheetnames:
        return None
    g = {(c.row, c.column): c.value for row in wb["Earnings"].iter_rows(max_col=3) for c in row
         if getattr(c, "value", None) is not None}
    top = next(((r, mm) for (r, c), v in sorted(g.items()) if c == 1 and isinstance(v, str) and (mm := FROZEN_RE.match(v))), None)
    if not top:
        return None
    r, mm = top[0] + 2, top[1]
    rows = []
    while isinstance(g.get((r, 1)), str) and not re.match(r"^\d+\. ", g[(r, 1)]):
        rows.append({"label": g[(r, 1)], "q": g.get((r, 2)), "fy": g.get((r, 3))})
        r += 1
    return {"quarter": mm.group(1), "date": mm.group(2), "rows": rows}


def ensure(model, quarter, grid, work):
    b = band7(model)
    if b and b["quarter"].rstrip("E") == quarter.rstrip("E"):
        return {"source": "band7", "date": b["date"]}
    m = ModMap(model)
    qc, fc = m.col(quarter), m.col(m.fy_of(quarter))
    rows = {k: {"q": grid.get(f"{qc}{r}"), "fy": grid.get(f"{fc}{r}")} for r, k, _ in m.lines
            if grid.get(f"{qc}{r}") is not None}
    os.makedirs(work, exist_ok=True)
    json.dump({"quarter": quarter, "rows": rows}, open(os.path.join(work, "preprint.json"), "w"), indent=1)
    return {"source": "preprint", "why": "no band 7" if not b else f"band 7 is for {b['quarter']}"}


def read(model, quarter, grid, work):
    """[{label, q}] of the frozen forecast for this quarter, from band 7 or preprint.json."""
    b = band7(model)
    if b and b["quarter"].rstrip("E") == quarter.rstrip("E"):
        return [{"label": x["label"], "q": x["q"]} for x in b["rows"]]
    pre = json.load(open(os.path.join(work, "preprint.json")))
    return [{"label": k.split(" | ")[-1], "key": k, "q": v["q"]} for k, v in pre["rows"].items()]


def table(rows, grid, model, col, placeholders=()):
    m = ModMap(model)
    by_label = {}
    for r, k, _ in m.lines:
        by_label.setdefault(k.split(" | ")[-1].strip().lower(), r)
    out = []
    for x in rows:
        r = m.keys.get(x.get("key")) or by_label.get(str(x["label"]).strip().lower())
        a = grid.get(f"{col}{r}") if r and f"{col}{r}" not in placeholders else None
        f = x["q"]
        d = round(a - f, 6) if isinstance(a, (int, float)) and isinstance(f, (int, float)) else None
        out.append({"label": x["label"], "frozen": f, "actual": a, "diff": d})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["ensure", "table"])
    for k in ("--model", "--quarter", "--values", "--work", "--column", "--out", "--state"):
        ap.add_argument(k)
    a = ap.parse_args()
    g = json.load(open(a.values))["MOD"]
    if a.cmd == "ensure":
        print(json.dumps(ensure(a.model, a.quarter, g, a.work)))
        return
    ph = {p["ref"] for p in json.load(open(a.state)).get("placeholders", [])} if a.state else set()
    rows = table(read(a.model, a.quarter, g, a.work), g, a.model, a.column, ph)
    L = ["| Line | Frozen forecast | Actual | Difference |", "|---|---|---|---|"]
    L += [f"| {x['label']} | {x['frozen']} | {x['actual']} | {x['diff']} |" for x in rows]
    open(a.out, "w").write("\n".join(L) + "\n")
    print(a.out)


if __name__ == "__main__":
    main()
