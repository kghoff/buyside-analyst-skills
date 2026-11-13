"""KPI step 5 - check every number the readers wrote, before (and after) it goes into the model.

usage: python3 kpi_check.py --src <source folder> --work <work_dir> --plan <work>/kpi_plan.json --model <model.xlsx> [--built]

Reads <work>/values/<key>.json: [{"period": "Q3 25", "value": 0.123, "raw": "12.3%", "scale": 0.01,
                                 "file": "<path relative to src>", "line": 23, "note": "..."}]
Each value is accepted only if:
  - its period is 'Qn yy' or 'FY yy' (and, with --model, a period the model has)
  - the cited file exists and the number in `raw` is printed on the cited line (snippets give exact line numbers)
  - value = number x scale (the sign may come from the wording: 'declined 3%' -> -0.03; those are listed)
  - the document isn't older than the period it reports
One value per period: equal values merge; different values are a restatement / definition change. The period's own
document wins (as originally reported) unless the metric has "prefer_restated": true or a list of fiscal years
(then the newest document wins for those years). Every conflict is reported.
Writes <work>/kpi_values.json and <work>/kpi_check.md.

With --built (after kpi_build.py): every accepted value is in its cell, every typed number in the section is an
accepted value, and full years summed from quarters match the reported full year within rounding. Exit 1 on problems."""
import argparse, glob, json, os, re, sys
import openpyxl
from ng_extract import classify_doc, period_of
from xlmodel import PeriodMap, Evaluator, section_bounds, norm

KPI_TITLE = "KEY OPERATING METRICS"
PER = re.compile(r"^(Q[1-4]|FY) \d\d$")
NUMTOK = re.compile(r"\d[\d,]*(?:\.\d+)?")
TYPE_RANK = {"release": 0, "deck": 1, "10-Q": 2, "10-K": 2, "call": 3, "event": 4, "recast": 5, "other": 6}
order = lambda k: (int(k[3:]), 5 if k.startswith("FY") else int(k[1]))


def nums(text):
    return {str(float(t.replace(",", ""))) for t in NUMTOK.findall(text)}


def decimals(raw):
    t = NUMTOK.search(raw or "")
    return len(t.group(0).split(".")[1]) if t and "." in t.group(0) else 0


def check_entry(e, src, model_periods):
    for k in ("period", "value", "raw", "file", "line"):
        if k not in e: return f"missing '{k}'"
    if not PER.match(str(e["period"])): return f"period '{e['period']}' is not 'Qn yy' or 'FY yy'"
    if model_periods is not None and e["period"] not in model_periods: return f"the model has no {e['period']} column"
    path = os.path.join(src, e["file"])
    if not os.path.exists(path): return f"file not found: {e['file']}"
    tok = NUMTOK.search(str(e["raw"]))
    if not tok: return f"no number in raw '{e['raw']}'"
    L = open(path, encoding="utf-8", errors="ignore").read().split("\n"); n = int(e["line"])
    if not 0 < n <= len(L) or str(float(tok.group(0).replace(",", ""))) not in nums(L[n - 1]):
        return f"'{tok.group(0)}' is not printed at {e['file']} line {n}"
    want = float(tok.group(0).replace(",", "")) * float(e.get("scale", 1))
    if not isinstance(e["value"], (int, float)) or abs(abs(e["value"]) - abs(want)) > 1e-9 * max(1, abs(want)):
        return f"value {e['value']} != {tok.group(0)} x {e.get('scale', 1)}"
    dp = period_of(path)
    if dp and order(dp) < order(e["period"]) and not (dp.startswith("Q4") and e["period"] == "FY " + dp[3:]):
        return f"{e['file']} ({dp}) is older than {e['period']}"
    e["_quote"] = L[n - 1].strip() if 0 < n <= len(L) else ""
    e["_type"] = classify_doc(path); e["_docper"] = dp
    return None


def choose(es, prefer_restated):
    """prefer_restated: true (every year) or a list of fiscal years, e.g. [2017], where a later definition replaced the
    original and the quarters must follow one definition to add up to the year"""
    own = [e for e in es if e["_docper"] == e["period"] or (e["_docper"] or "").replace("Q4", "FY") == e["period"]]
    yr = 2000 + int(es[0]["period"][3:])
    if prefer_restated is True or (isinstance(prefer_restated, list) and yr in prefer_restated): return sorted(es, key=lambda e: (order(e["_docper"]) if e["_docper"] else (0, 0)), reverse=True)[0]
    return sorted(own or es, key=lambda e: (TYPE_RANK.get(e["_type"], 9), order(e["_docper"]) if e["_docper"] else (99, 9)))[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--work", required=True); ap.add_argument("--plan", required=True)
    ap.add_argument("--model", default=None); ap.add_argument("--built", action="store_true")
    a = ap.parse_args()
    plan = json.load(open(a.plan)); metrics = {m["key"]: m for m in plan["metrics"]}
    ws = pm = None
    if a.model:
        wb = openpyxl.load_workbook(a.model); ws = wb["MOD"] if "MOD" in wb.sheetnames else wb.worksheets[0]; pm = PeriodMap(ws)
    model_periods = {pm.key(c) for c in pm.per if c not in pm.estimate} if pm else None
    accepted, rejected, conflicts, signed = {}, [], [], []
    for path in sorted(glob.glob(os.path.join(a.work, "values", "*.json"))):
        key = os.path.splitext(os.path.basename(path))[0]
        if key not in metrics: rejected.append((key, "-", "no such metric in kpi_plan.json")); continue
        by = {}
        for e in json.load(open(path)):
            why = check_entry(e, a.src, model_periods)
            if why: rejected.append((key, e.get("period", "?"), why)); continue
            if e["value"] < 0 and not re.search(r"[(\-−]", str(e["raw"])): signed.append((key, e["period"], e["raw"], e["_quote"][:160]))
            by.setdefault(e["period"], []).append(e)
        out = {}
        for per, es in by.items():
            vals = sorted({round(e["value"], 9) for e in es})
            best = choose(es, metrics[key].get("prefer_restated", False))
            if len(vals) > 1:
                best["conflict"] = [f"{e['value']} ({e['file']} line {e['line']})" for e in es if round(e["value"], 9) != round(best["value"], 9)]
                conflicts.append((key, per, best["value"], best["conflict"]))
            out[per] = best
        accepted[key] = dict(sorted(out.items(), key=lambda kv: order(kv[0])))
    missing = [k for k in metrics if k not in accepted]
    json.dump(accepted, open(os.path.join(a.work, "kpi_values.json"), "w"), indent=1)

    problems = []
    if a.built:
        import modfill
        problems += [f"fill convention: {x}" for x in modfill.summary(modfill.check(a.model))]   # quarters plain, years grey
        import notebox; problems += [f"squashed note box: {x}" for x in notebox.check(a.model)[:12]]
        b = section_bounds(ws, KPI_TITLE)
        if not b: problems.append(f"no {KPI_TITLE} section in the model")
        else:
            ev = Evaluator(ws); used = set()
            for key, vals in accepted.items():
                m = metrics[key]
                r = next((r for r in range(b[0], b[1]) if norm(ws.cell(r, 2).value) == norm(m["label"])), None)
                if r is None: problems.append(f"{key}: row '{m['label']}' not found"); continue
                for per, e in vals.items():
                    c = pm.by_key(per); cell = ws.cell(r, c); got = ev.v(cell.coordinate); used.add((r, c))
                    typed = not (isinstance(cell.value, str) and cell.value.startswith("="))
                    if typed and (not isinstance(got, (int, float)) or abs(got - e["value"]) > 1e-9 * max(1, abs(e["value"]))):
                        problems.append(f"{key} {per}: cell {cell.coordinate} = {got}, accepted value {e['value']}")
                    elif not typed and isinstance(got, (int, float)):
                        tol = 0.5 * 10 ** -decimals(e["raw"]) * float(e.get("scale", 1)) * 4 + 1e-9
                        if abs(got - e["value"]) > tol:
                            problems.append(f"{key} {per}: {cell.value} = {round(got, 6)} vs reported {e['value']} ({e['file']} line {e['line']})")
            for r in range(b[0] + 1, b[1]):
                if ws.cell(r, 2).font.i: continue
                for c in pm.per:
                    v = ws.cell(r, c).value
                    if v is not None and not (isinstance(v, str) and v.startswith("=")) and (r, c) not in used:
                        problems.append(f"{ws.cell(r, c).coordinate}: typed {v} is not an accepted value")
    with open(os.path.join(a.work, "kpi_check.md"), "w") as f:
        f.write(f"# KPI check\n\nAccepted: {sum(len(v) for v in accepted.values())} values for {len(accepted)} metrics. "
                f"Rejected: {len(rejected)}. Conflicts: {len(conflicts)}. Metrics with no values: {missing or 'none'}.\n\n")
        f.write("## Coverage\n\n| metric | periods | first | last |\n|---|---|---|---|\n" +
                "".join(f"| {k} | {len(v)} | {next(iter(v), '-')} | {next(reversed(v), '-') if v else '-'} |\n" for k, v in accepted.items()) + "\n")
        if rejected: f.write("## Rejected (not written to the model)\n\n" + "\n".join(f"- {k} {p}: {w}" for k, p, w in rejected) + "\n\n")
        if conflicts: f.write("## Different values for the same period (restated / redefined)\n\n" +
                              "\n".join(f"- {k} {p}: used {v}; also {', '.join(o)}" for k, p, v, o in conflicts) + "\n\n")
        if signed: f.write("## Negative values whose sign comes from the wording (check)\n\n" +
                           "\n".join(f"- {k} {p}: raw '{r}' | {q}" for k, p, r, q in signed) + "\n\n")
        if a.built: f.write("## Model check\n\n" + ("\n".join(f"- {x}" for x in problems) if problems else "All accepted values are in the model.") + "\n")
    print(f"accepted {sum(len(v) for v in accepted.values())} values / {len(accepted)} metrics | rejected {len(rejected)} | "
          f"conflicts {len(conflicts)} | sign from wording {len(signed)}" + (f" | model problems {len(problems)}" if a.built else ""))
    for x in (problems + [f"{k} {p}: {w}" for k, p, w in rejected])[:15]: print("  ", x)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
