"""Step 4 - recalculate the model and tie the NON-GAAP section to what the company reported.

usage: python3 ng_verify.py --model <model.xlsx> --work <work_dir> --plan <plan.json> [--before <model before build>]

Checks: every bridge total = the reported non-GAAP figure (each quarter + FY); every FY = reported FY;
EPS = reported EPS (split-adjusted); links still equal the reconciliation lines; no #errors; colours;
and (with --before) that nothing outside the new section changed value. Writes <work>/verify_report.md; exit 1 on failure."""
import argparse, json, os, re, sys
import openpyxl
from xlmodel import PeriodMap, Evaluator, section_bounds, norm, color_for, map_formula, sheet_refs, BLUE, GREEN
KPI_TITLE = "KEY OPERATING METRICS"
from ng_build import order
from ng_extract import period_of


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--work", required=True); ap.add_argument("--plan", required=True)
    ap.add_argument("--before", default=None)
    a = ap.parse_args()
    plan = json.load(open(a.plan)); C = json.load(open(os.path.join(a.work, "candidates.json")))["candidates"]
    wb = openpyxl.load_workbook(a.model); ws = wb["MOD"] if "MOD" in wb.sheetnames else wb.worksheets[0]
    ev, pm = Evaluator(ws), PeriodMap(ws)
    nb = section_bounds(ws, plan.get("section_title", "NON-GAAP METRICS"))
    if plan["metrics"] and not nb: raise SystemExit("no NON-GAAP METRICS section in the model - run ng_build.py first")
    r0, r1 = nb or (1, 1)                    # a company with no reconciliations: only the KPI section and the rest are checked
    def row(label, after=r0):
        for r in range(after, r1):
            if norm(ws.cell(r, 2).value) == norm(label): return r
    fails, n = [], 0
    by = {}
    for c in C: by.setdefault((c["metric"], c["period"]), []).append(c)
    restated = {(x["metric"], x["fiscal_year"] % 100) for x in plan.get("prefer_restated", [])}
    cursor = r0
    for m in plan["metrics"]:
        end_label = next(r for r in m["rows"] if r["role"] == "end")["label"]
        start_label = next(r for r in m["rows"] if r["role"] == "start")["label"]
        sr = row(start_label, cursor); er = row(end_label, sr); cursor = er
        for c in sorted(pm.per):
            if c in pm.estimate or ws.cell(er, c).value is None: continue
            key = pm.key(c)
            cs = [x for x in by.get((m["key"], key), []) if x.get("start_matches_model") is not False]
            if not cs: continue
            pref = (m["key"], int(key[3:])) in restated
            want = sorted(cs, key=lambda x: (x["vintage"] == "current") if pref else (x["vintage"] != "current"))[0]["end"]
            got = ev.v(ws.cell(er, c).coordinate); n += 1
            # a full year is SUM(Q1:Q4); for a whole-million reporter that sum can be a unit or three off the
            # reported full year (each figure rounded on its own)
            tol = 3 if key.startswith("FY") and float(want).is_integer() else 0.11
            if not isinstance(got, (int, float)) or abs(got - want) > tol:
                fails.append(f"{m['key']} {key}: model {got} vs reported {want}")
    if plan.get("eps"):
        er = row(plan["eps"]["rows"][-1]["label"], cursor)
        for c in sorted(pm.per):
            v = ev.v(ws.cell(er, c).coordinate) if ws.cell(er, c).value is not None else None
            if not isinstance(v, (int, float)): continue
            key = pm.key(c)
            reps = [x for x in by.get(("reported non-gaap eps", key), []) if x.get("start_matches_model") is not False]
            if not reps: continue
            pref = any((mm, int(key[3:])) in restated for mm in ("non-gaap net income",))
            rep = sorted(reps, key=lambda x: (x["vintage"] == "current") if pref else (x["vintage"] != "current"))[0]
            f = 1
            for s in plan.get("share_splits", []):
                if order(period_of(rep["source"]) or key) <= order(s["through_period"]): f *= s["factor"]
            n += 1
            if abs(v - rep["value"] / f) > 0.005 / f + 0.0005:                  # reported to the cent
                fails.append(f"EPS {key}: model {round(v, 4)} vs reported {rep['value']}{f' / {f}' if f != 1 else ''}")
    # the inserted sections (non-GAAP + KPI); everything else must be exactly as before
    ours = [b for b in (section_bounds(ws, t) for t in (plan.get("section_title", "NON-GAAP METRICS"), KPI_TITLE)) if b]
    inside = lambda r: any(b0 <= r < b1 for b0, b1 in ours)
    errs, col_bad, no_note = [], [], []
    for b0, b1 in ours:
        for r in range(b0 + 1, b1):
            for c in pm.per:
                x = ws.cell(r, c); v = x.value
                if v is None: continue
                ev_v = ev.v(x.coordinate)
                if isinstance(ev_v, str) and ev_v.startswith("#"): errs.append(x.coordinate)
                want = color_for(v); got = x.font.color.rgb if x.font.color is not None and isinstance(x.font.color.rgb, str) else None
                if got != want: col_bad.append(x.coordinate)
                # The user: every number says where it came from (typed = source, link = what it points at)
                if want in (BLUE, GREEN) and not ws.cell(r, 2).font.i and not x.comment: no_note.append(x.coordinate)
    moved, tabs = [], []
    if a.before:
        bwb = openpyxl.load_workbook(a.before); b = bwb[ws.title]; eb = Evaluator(b)
        kept = [r for r in range(1, ws.max_row + 1) if not inside(r)]
        rowmap = {r: kept[r - 1] for r in range(1, min(b.max_row, len(kept)) + 1)}
        for r, nr in rowmap.items():
            for c in range(1, b.max_column + 1):
                if b.cell(r, c).value is None and ws.cell(nr, c).value is None: continue
                x, y = eb.v(b.cell(r, c).coordinate), ev.v(ws.cell(nr, c).coordinate)
                if x != y and not (isinstance(x, (int, float)) and isinstance(y, (int, float)) and abs(x - y) < 1e-6):
                    moved.append(f"{b.cell(r, c).coordinate} -> {ws.cell(nr, c).coordinate}")
        # other tabs (e.g. ANALYZED): same cells, every link into this tab re-pointed to the same row and same value
        awb = ws.parent
        for bs in bwb.worksheets:
            if bs.title == ws.title: continue
            if bs.title not in awb.sheetnames: tabs.append(f"{bs.title}: tab missing"); continue
            ts = awb[bs.title]
            for row in bs.iter_rows():
                for bc in row:
                    tc = ts[bc.coordinate]; bv = bc.value
                    if isinstance(bv, str) and bv.startswith("=") and ws.title in bv:
                        want_f = map_formula(bv, ws.title, lambda r: rowmap.get(r, r), home=False)
                        if tc.value != want_f: tabs.append(f"{bs.title}!{bc.coordinate}: {tc.value} (expected {want_f})"); continue
                        for br_, ar_ in zip(sheet_refs(bv, ws.title, home=False), sheet_refs(tc.value, ws.title, home=False)):
                            if eb.v(br_) != ev.v(ar_): tabs.append(f"{bs.title}!{bc.coordinate}: {ws.title}!{ar_} = {ev.v(ar_)}, was {eb.v(br_)}")
                    elif tc.value != bv:
                        tabs.append(f"{bs.title}!{bc.coordinate}: {tc.value!r} (was {bv!r})")
    import modfill
    col_bad += [f"fill convention: {x}" for x in modfill.summary(modfill.check(a.model))]   # quarters plain, years grey
    import notebox; col_bad += [f"squashed note box: {x}" for x in notebox.check(a.model)[:12]]
    bad = fails + errs + col_bad + no_note + moved + tabs
    summary = (f"{n} checks, {len(fails)} failed | errors {len(errs)} | colour exceptions {len(col_bad)} | missing notes {len(no_note)} | "
               f"changed outside sections {len(moved) if a.before else '-'} | other tabs changed {len(tabs) if a.before else '-'}")
    with open(os.path.join(a.work, "verify_report.md"), "w") as f:
        f.write("# Non-GAAP verification\n\n" + summary + "\n\n" + "\n".join(f"- FAIL {x}" for x in fails) + "\n" +
                "".join(f"\n## {t}\n\n" + "\n".join(f"- {x}" for x in xs[:200]) + "\n" for t, xs in
                        [("Formula errors", errs), ("Colour exceptions", col_bad), ("Missing notes", no_note),
                         ("Changed outside the sections", moved), ("Other tabs", tabs)] if xs))
    print(summary)
    for x in bad[:20]: print("  ", x)
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
