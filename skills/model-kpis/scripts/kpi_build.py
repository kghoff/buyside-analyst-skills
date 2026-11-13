"""KPI step 6 - write the KEY OPERATING METRICS section from kpi_plan.json + kpi_values.json (kpi_check.py output).

usage: python3 kpi_build.py --model <model.xlsx> --work <work_dir> --plan <work>/kpi_plan.json --out <model_out.xlsx> [--replace]

- inserts the section at the top, just above INCOME STATEMENT (the user's ALT DATA area, 2026-11-06). Models built
  before then have the INCOME STATEMENT title on the period-header row; there it goes before BALANCE SHEET as it
  used to. Every formula in the workbook keeps pointing at the same cells
- one row per metric, in plan order, a blank row between groups; units in column C
- quarters typed (blue) with a note: file, md line, the printed line, and any other figure seen for that period
- full year by kind: flow = SUM(Q1:Q4) when all four quarters exist, else the reported full year (typed);
  stock = the Q4 value (link, green), else the reported year-end figure; rate = the reported full-year figure
- every row label gets a note: definition, why a modeler tracks it, how FY is filled, coverage
Writes <work>/kpi_build_log.json."""
import argparse, json, os
from copy import copy
import openpyxl
from openpyxl.utils import get_column_letter as L
from xlmodel import PeriodMap, find_row, section_bounds, insert_rows, delete_rows, note, set_font_color, color_for, PCT_FMT

TITLE = "KEY OPERATING METRICS"
IS = "INCOME STATEMENT"
FMT = {"%": PCT_FMT, "$": '"$"#,##0.00_);\\("$"#,##0.00\\)', "x": '0.00"x"'}
NUM_FMT = "#,##0.0_);(#,##0.0)"
FY_RULE = {"flow": "full year = sum of the four quarters (typed from the annual figure when a quarter is missing)",
           "stock": "full year = the Q4 (year-end) value", "rate": "full year = the company's reported full-year figure"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--work", required=True); ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--replace", action="store_true")
    a = ap.parse_args()
    plan = json.load(open(a.plan)); vals = json.load(open(os.path.join(a.work, "kpi_values.json")))
    wb = openpyxl.load_workbook(a.model); ws = wb["MOD"] if "MOD" in wb.sheetnames else wb.worksheets[0]
    log = []
    old = section_bounds(ws, TITLE)
    if old:
        if not a.replace: raise SystemExit(f"'{TITLE}' already exists (row {old[0]}). Re-run with --replace to rebuild it.")
        delete_rows(ws, old[0], old[1] - old[0]); log.append(f"Replaced the existing {TITLE} section.")
    metrics = [m for m in plan["metrics"] if vals.get(m["key"])]
    log += [f"{m['label']}: no accepted values - no row written." for m in plan["metrics"] if not vals.get(m["key"])]
    layout = [("title", None), ("blank", None)]
    for i, m in enumerate(metrics):
        if i and m.get("group") != metrics[i - 1].get("group"): layout.append(("blank", None))
        layout.append(("metric", m))
    layout.append(("blank", None))
    hdr = section_bounds(ws, IS)[0]
    style = find_row(ws, plan.get("style_from", "^revenue"), IS)
    where = plan.get("insert_before") or ("INCOME STATEMENT" if hdr != PeriodMap(ws).hdr else "BALANCE SHEET")
    if where == "BALANCE SHEET" and not plan.get("insert_before"):
        log.append("Older model layout (INCOME STATEMENT title on the period-header row): section placed before BALANCE SHEET.")
    at = section_bounds(ws, where)[0]
    insert_rows(ws, at, len(layout))
    if style >= at: style += len(layout)
    if hdr >= at: hdr += len(layout)
    pm = PeriodMap(ws); maxc = ws.max_column
    keys = sorted({pm.key(c) for c in pm.per if c not in pm.estimate}, key=lambda k: (int(k[3:]), 5 if k.startswith("FY") else int(k[1])))
    for i, (role, m) in enumerate(layout):
        r = at + i; src = hdr if role == "title" else (style if role == "metric" else None)
        for c in range(1, maxc + 1):
            ws.cell(r, c)._style = copy(ws.cell(src, c)._style) if src else copy(ws.cell(r, c)._style); ws.cell(r, c).value = None
        if role == "title":
            ws.cell(r, 1).value = TITLE
            note(ws.cell(r, 1), "Company-specific operating metrics found by the model-kpis skill's KPI scan. Every number is typed from "
                                "the source document named in its note and was checked against that line. See kpi_check.md.")
            continue
        if role != "metric": continue
        v = vals[m["key"]]; fmt = FMT.get(m["units"], NUM_FMT)
        ws.cell(r, 2).value = m["label"]; ws.cell(r, 3).value = m["units"]
        pers = list(v)
        note(ws.cell(r, 2), f"{m.get('definition', '')}\nWhy it matters: {m.get('why', '')}\nHow FY is filled: {FY_RULE[m['kind']]}.\n"
                            f"Reported in: {', '.join(m.get('doc_types') or ['any document'])}; {len(pers)} periods, {pers[0]} to {pers[-1]}.")
        def put(c, value, text):
            cell = ws.cell(r, c); cell.value = value; cell.number_format = fmt
            set_font_color(cell, color_for(value)); note(cell, text)
        def typed(c, e):
            txt = f"Source: {e['file']} (md line ~{e['line']})\n“{e.get('_quote', '')[:400]}”"
            if e.get("note"): txt += f"\n{e['note']}"
            if e.get("conflict"): txt += "\nOther figures seen for this period: " + "; ".join(e["conflict"])
            put(c, e["value"], txt)
        for k in keys:
            c = pm.by_key(k)
            if not k.startswith("FY"):
                if k in v: typed(c, v[k])
                continue
            yy = k[3:]; qs = [f"Q{q} {yy}" for q in (1, 2, 3, 4)]; qc = [pm.by_key(q) for q in qs]
            rep = v.get(k)
            if m["kind"] == "flow" and all(q in v for q in qs) and all(qc):
                put(c, f"=SUM({L(qc[0])}{r}:{L(qc[3])}{r})", "Sum of Q1-Q4." + (f" Reported full year: {rep['value']} ({rep['file']} line {rep['line']})." if rep else ""))
            elif m["kind"] == "stock" and "Q4 " + yy in v and qc[3]:
                put(c, f"={L(qc[3])}{r}", "Year-end = Q4.")
            elif rep:
                typed(c, rep)
                if m["kind"] == "flow": log.append(f"{m['label']} {k}: typed from the reported full year (not all four quarters reported).")
            if v.get(k, {}).get("conflict"): log.append(f"{m['label']} {k}: different figures reported for this period; used {v[k]['value']}.")
        log += [f"{m['label']} {q}: different figures reported for this period; used {v[q]['value']} ({v[q]['file']})."
                for q in pers if not q.startswith("FY") and v[q].get("conflict")]
    wb.calculation.fullCalcOnLoad = True
    import safe_save; safe_save.safe_save(wb, a.model, a.out)   # never openpyxl's save: it drops the user's text boxes / shapes
    import modfill; modfill.fix(a.out, a.out)   # the user's MOD fill convention (quarters plain, years grey), every save
    import notebox; notebox.fix(a.out, a.out)   # note boxes open readable (none squashed next to spacer / hidden columns), every save
    json.dump({"log": log, "section_rows": [at, at + len(layout) - 1], "metrics": [m["key"] for m in metrics]},
              open(os.path.join(a.work, "kpi_build_log.json"), "w"), indent=1)
    print(f"{TITLE} inserted at row {at} ({len(metrics)} metrics); log items: {len(log)}")


if __name__ == "__main__":
    main()
