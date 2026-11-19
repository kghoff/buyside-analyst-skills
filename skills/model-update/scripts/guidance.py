"""New guidance -> research-filings' guidance data; on a Q4 print, the closed year into model_series.csv.

usage: python3 guidance.py record --work "<T>/Filings Research/_work" --answers guidance_answers.json --quarter "Q3 26"
       python3 guidance.py close-year --work ... --year 2026 --model FINISHED.xlsx --rf <research-filings>/scripts
Then (Q4 only): python3 <research-filings>/scripts/handoff.py --src <T> --model TMP.xlsx --out TMP2.xlsx --charts-only
--work is the STAGED copy of research-filings' _work folder (SKILL.md step 5), never the user's own: a stopped run
must leave research-filings' data as it was.
Filings Charts' guidance blocks show completed years only, so on Q1-Q3 prints the tab does not change; the guides
are recorded so the path is complete when the year closes."""
import argparse
import csv
import json
import os
import sys

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


def close_year(work, year, model, rf):
    """Rebuild model_series.csv from the finished copy with research-filings' own extractor (modeldata.extract), then
    bump last_year. The csv's 'MOD!<col><row>' sources go stale whenever MOD rows move (model-kpis, /model-forecast):
    remapping the old rows would point the closed year at whatever line sits there now (on the real DXCM data
    Revenue pointed at a '% yoy' row), and handoff.py's check_rows would stop the run. After a Q4 the year header has
    no E, so the extractor includes the closed year."""
    if rf not in sys.path:
        sys.path.append(rf)                     # appended: this folder's own modules keep their names
    import modeldata
    rows = modeldata.extract(model)
    with open(os.path.join(work, "model_series.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=modeldata.COLS)
        w.writeheader()
        w.writerows(rows)
    dm = os.path.join(work, "drivers_math.json")
    D = json.load(open(dm))
    D["config"]["last_year"] = max(D["config"]["last_year"], year)
    json.dump(D, open(dm, "w"), indent=1)
    return {"metrics": len({r["metric"] for r in rows}), "values": len(rows),
            "closed_year_values": sum(1 for r in rows if r["period"] == f"FY{year}")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["record", "close-year"])
    for k in ("--work", "--answers", "--quarter", "--year", "--model", "--rf"):
        ap.add_argument(k)
    a = ap.parse_args()
    if a.cmd == "record":
        print(json.dumps(record(a.work, json.load(open(a.answers)), a.quarter)))
    else:
        print(json.dumps(close_year(a.work, int(a.year), a.model, os.path.abspath(a.rf))))
