"""New guidance -> research-filings' guidance data; on a Q4 print, the closed year into model_series.csv.

usage: python3 guidance.py record --work "<T>/Filings Research/_work" --answers guidance_answers.json --quarter "Q3 26"
       python3 guidance.py close-year --work ... --year 2026 --cols '{"H": "N"}' --values values_after.json
Then (Q4 only): python3 <research-filings>/scripts/handoff.py --src <T> --model TMP.xlsx --out TMP2.xlsx --charts-only
Filings Charts' guidance blocks show completed years only, so on Q1-Q3 prints the tab does not change; the guides
are recorded so the path is complete when the year closes."""
import argparse
import csv
import json
import os
import re

COLS = ["fiscal_year", "metric", "basis", "kind", "date", "low", "high", "actual", "source"]


def record(work, answers, quarter):
    H = json.load(open(os.path.join(work, "model_handoff.json")))
    names = {n.lower() for g in H.get("guidance", []) for n in g["names"]}
    d = os.path.join(work, "readers", "update_" + quarter.replace(" ", "_"))
    os.makedirs(d, exist_ok=True)
    keep = [a for a in answers if a["metric"].lower() in names and a["action"] != "none"]
    with open(os.path.join(d, "guidance.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for a in keep:
            w.writerow({"fiscal_year": a["fiscal_year"], "metric": a["metric"], "basis": a["basis"], "kind": a["kind"],
                        "date": a["date"], "low": a.get("low", ""), "high": a.get("high", ""), "actual": "",
                        "source": a["source"]})
    return {"recorded": len(keep), "no_block": [a["metric"] for a in answers if a["metric"].lower() not in names]}


def close_year(work, year, cols, grid):
    """cols: {prior FY column letter: closed FY column letter}. Each metric's FY<year-1> MOD source moves to the
    closed year's column on the same row; its value comes from the recalculated grid."""
    p = os.path.join(work, "model_series.csv")
    rows = list(csv.DictReader(open(p, newline="", encoding="utf-8")))
    fields = list(rows[0].keys())
    have = {(r["metric"], r["period"]) for r in rows}
    add = []
    for r in rows:
        if r["period"] != f"FY{year - 1}" or (r["metric"], f"FY{year}") in have:
            continue
        m = re.search(r"MOD!([A-Z]+)(\d+)", r["source"])
        if not m or m.group(1) not in cols:
            continue
        ref = f"{cols[m.group(1)]}{m.group(2)}"
        v = grid.get(ref)
        if not isinstance(v, (int, float)):
            continue
        add.append({**r, "period": f"FY{year}", "value": str(float(v)), "source": f"Model, MOD!{ref}"})
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows + add)
    dm = os.path.join(work, "drivers_math.json")
    D = json.load(open(dm))
    D["config"]["last_year"] = max(D["config"]["last_year"], year)
    json.dump(D, open(dm, "w"), indent=1)
    return {"added": len(add)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["record", "close-year"])
    for k in ("--work", "--answers", "--quarter", "--year", "--cols", "--values"):
        ap.add_argument(k)
    a = ap.parse_args()
    if a.cmd == "record":
        print(json.dumps(record(a.work, json.load(open(a.answers)), a.quarter)))
    else:
        print(json.dumps(close_year(a.work, int(a.year), json.loads(a.cols), json.load(open(a.values))["MOD"])))
