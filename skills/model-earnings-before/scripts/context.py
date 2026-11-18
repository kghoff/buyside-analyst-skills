# skills/model-earnings-before/scripts/context.py
"""Everything the earnings-analyst agent and build.py read: context.json (values and the formulas that make them),
context.md (the same for the agent, in one pass) and rowmap.md (MOD's row keys, to cite cells).

Facts only: the quarter being reported and its report date (Yahoo's when the print is still ahead, else estimated),
the model checks (checks.py), base rates and sigma (rates.py), links to Multiples / Consensus / Filings Charts
(links.py), Yahoo's implied move and last 4 surprises, code's answers (the valuation-and-performance set-up row, the
blow-up flags), the documents since the last print (docs.py) and the forecast to freeze.

usage: python3 context.py --model M --work W --ticker T [--values RECALCULATED.xlsx] [--research DIR]
       [--forecast-plan PATH] [--today YYYY-MM-DD]
(without --values, M is recalculated in LibreOffice into W/values first; --research defaults to
<research_dir>/<T>; --forecast-plan to <model dir>/_model_work/forecast/forecast_plan.json)"""
import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import openpyxl  # noqa: E402
from openpyxl.utils import column_index_from_string as ci  # noqa: E402

import checks  # noqa: E402
import docs  # noqa: E402
import earnmath as em  # noqa: E402
import links  # noqa: E402
import rates  # noqa: E402
from modmap import ModMap  # noqa: E402

REQUIRED = {"MOD": "model-historicals", "Px Data": "model-price-history", "Px Events": "model-price-history",
            "Multiples": "model-multiples"}
OPTIONAL = {"Consensus": "model-consensus", "Valuation": "model-valuation", "Filings Charts": "research-filings"}


def drivers(mm, plan_path, warnings):
    """The forecast plan's revenue-identity factors with a MOD row (at most 3), as model-dcf reads them."""
    if not plan_path or not os.path.exists(plan_path):
        warnings.append("No forecast plan found, so the key-driver rows are left out of the model checks and the "
                        "variance grid (rerun /model-forecast to add them).")
        return []
    out = []
    for t in (json.load(open(plan_path)).get("revenue_identity") or {}).get("terms", []):
        for f in t.get("factors", []):
            try:
                out.append({"name": f.get("name") or f["key"].split(" | ")[-1], "key": f["key"], "row": mm.row(f["key"])})
            except KeyError:
                warnings.append(f"The forecast plan's driver {f['key']!r} has no MOD row; left out.")
    return out[:3]


def mod_block(mm, g, rows, ck, drv):
    """The MOD periods, columns and values the variance grid links to: the quarter, the same quarter a year ago,
    the fiscal year, the year before and the year after."""
    fys = [p for p in mm.order if re.fullmatch(r"\d{4}E?", p)]
    i = fys.index(ck["fy"])
    per = {"q": ck["quarter"], "q_ly": mm.pyq(ck["quarter"]), "fy": ck["fy"],
           "fy_ly": fys[i - 1] if i else None, "fy1": fys[i + 1] if i + 1 < len(fys) else None}
    used = sorted(set(rows.values()) | {d["row"] for d in drv})
    vals = {}
    for r in used:
        vals[str(r)] = {}
        for k, p in per.items():
            v = g.get((r, ci(mm.col(p)))) if p else None
            vals[str(r)][k] = v if em._n(v) else (0.0 if v is None and p else None)
    return {"periods": per, "cols": {k: mm.col(p) for k, p in per.items() if p}, "rows": rows,
            "drivers": [{"name": d["name"], "row": d["row"]} for d in drv], "vals": vals}


def frozen(mm, g, q, fy):
    out = []
    for row, key, unit in mm.lines:
        vq, vf = g.get((row, ci(mm.col(q)))), g.get((row, ci(mm.col(fy))))
        out.append({"label": key, "row": row, "unit": unit, "q": vq if em._n(vq) else None,
                    "fy": vf if em._n(vf) else None})
    return out


def _earn(work):
    p = os.path.join(work, "earnings.json")
    return json.load(open(p)) if os.path.exists(p) else {"error": "fetch_earnings.mjs was not run"}


def _research(ticker, research):
    if research:
        return research
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "lib"))
    import settings
    return os.path.join(settings.research_dir(), ticker)


def run(model, work, ticker, values=None, research=None, forecast_plan=None, today=None):
    os.makedirs(work, exist_ok=True)
    today = today or dt.date.today().isoformat()
    if values is None:
        import lo
        values = lo.recalc(model, os.path.join(work, "values"))
    wb = openpyxl.load_workbook(values, read_only=True, data_only=True)
    for tab, skill in REQUIRED.items():
        if tab not in wb.sheetnames:
            raise SystemExit(f"model-earnings-before: the model has no {tab} tab. Run /{skill} first.")
    missing = [f"{t} (/{s})" for t, s in OPTIONAL.items() if t not in wb.sheetnames]
    g = {t: checks.grid(wb[t]) for t in (*REQUIRED, *[t for t in OPTIONAL if t in wb.sheetnames])}
    warnings = []
    mm = ModMap(values)
    rows = checks.find_rows(mm)
    plan_path = forecast_plan or os.path.join(os.path.dirname(os.path.abspath(model)), "_model_work", "forecast",
                                              "forecast_plan.json")
    drv = drivers(mm, plan_path, warnings)
    ck = checks.run(mm, g["MOD"], rows, drv)
    done = rates.release(g["Px Events"], ck["quarter"])
    if done and done[0].isoformat() <= today:
        warnings.append(f"MOD's first forecast quarter, {ck['quarter']}, was already reported on "
                        f"{done[0].isoformat()}: enter its actuals (model-update) before previewing the next print")
    P = rates.px_data(g["Px Data"], ticker)
    pr = rates.prints(g["Px Events"], P, ticker)
    last = pr[0] if pr else None
    rt = {"prints": pr, "stats": em.base_stats([x["move"] for x in pr]), "vol": rates.vol(P),
          "rel": rates.rel_since(P, last), "close_range": rates.rng(P, "close"), "date_range": rates.rng(P, "date")}
    lk = {"multiples": links.multiples(g["Multiples"]),
          "consensus": links.consensus(g["Consensus"]) if "Consensus" in g else {}}
    guide = links.guidance(g["Filings Charts"]) if "Filings Charts" in g else []

    y = _earn(work)
    if y.get("error") or not em._n(y.get("price")):
        warnings.append(f"Yahoo failed ({y.get('error', 'no price')}): price from Px Data's last close, no implied "
                        "move, no surprise history.")
        lc = rates.last_close(P)
        price = {"value": lc["close"], "source": f"Px Data last close, {lc['date']}"}
        y = {"surprises": [], "implied_move": None, "earnings_date": None}
    else:
        price = {"value": y["price"], "source": f"Yahoo Finance, {y['asof']}"}
    ed = (y.get("earnings_date") or "")[:10]
    if ed and ed > today:
        report = {"value": ed, "estimated": False, "source": f"Yahoo Finance, {y.get('asof')}"}
        implied = y.get("implied_move")
    else:
        est = rates.next_date(g["Px Events"], ck["quarter"])
        report = {"value": est["value"] if est else None, "estimated": True,
                  "source": (f"estimated: last year's release ({est['base']}, {est['from']}) + 52 weeks" if est
                             else "unknown: Yahoo has no date yet and Px Events has no release for last year's quarter")}
        implied = None
        if y.get("implied_move") is not None:
            warnings.append("Yahoo's implied move was dropped: its earnings date is not ahead of today, so the "
                            "straddle holds no print.")
    days = ((dt.date.fromisoformat(report["value"]) - dt.date.fromisoformat(today)).days
            if report["value"] else None)
    H = dict(em.HOUSE)
    pe_pct = lk["multiples"].get("pe_pct", {}).get("value")
    b = ck["blowup"]
    code = {"setup": {"value_perf": em.setup_code(pe_pct, rt["rel"]["value"], H)},
            "blowups": em.blowups(b["margin_range"]["value"], b["ttm_ni"]["value"], b["ttm_fcf"]["value"],
                                  b["cash"]["value"], pe_pct, H)}
    root = _research(ticker, research)
    new_docs = docs.since(root, last["event_date"]) if last else []      # from the release day, not the reaction
    if not new_docs:
        warnings.append("No documents dated on or after the last print: rerun /collect-documents, or drop the "
                        "latest broker previews into Sellside Research, then rerun this step.")
    ctx = {"ticker": ticker, "today": today, "values": os.path.abspath(values), "research": root,
           "price": price, "quarter": ck["quarter"], "fy": ck["fy"], "report_date": report, "days_to_print": days,
           "checks": ck, "mod": mod_block(mm, g["MOD"], rows, ck, drv), "rates": rt, "links": lk, "guidance": guide,
           "yahoo": {"implied_move": implied, "surprises": y.get("surprises") or [], "straddle": y.get("straddle")},
           "code": code, "house": H, "last_print": last["date"] if last else None,
           "last_release": last["event_date"] if last else None, "new_docs": new_docs,
           "frozen": frozen(mm, g["MOD"], ck["quarter"], ck["fy"]), "missing": missing, "warnings": warnings}
    json.dump(ctx, open(os.path.join(work, "context.json"), "w"), indent=1, default=str)
    open(os.path.join(work, "context.md"), "w").write(_md(ctx))
    import modmap
    modmap.rowmap(values, os.path.join(work, "rowmap.md"))
    return ctx


def _md(c):
    L = [f"# {c['ticker']} earnings preview: context ({c['today']})", "",
         f"Quarter being reported: {c['quarter']} (fiscal year {c['fy']})",
         f"Report date: {c['report_date']['value']} ({c['report_date']['source']}); days to print: {c['days_to_print']}",
         f"Price: {c['price']['value']} ({c['price']['source']})",
         f"Last print (reaction day): {c['last_print']}; released {c['last_release']}",
         f"Missing optional tabs: {', '.join(c['missing']) or 'none'}", "", "## Warnings"]
    L += [f"- {w}" for w in c["warnings"]] or ["- none"]
    L += ["", "## Model checks (value ; formula)"]
    for m in c["checks"]["metrics"]:
        L.append(f"### {m['name']} (MOD row {m['row']})")
        L += [f"- {k}: {v['value'] if isinstance(v, dict) else v}" + (f" ; ={v['formula']}" if isinstance(v, dict) else "")
              for k, v in m["cells"].items()]
    h2 = c["checks"]["h2"]
    L += [f"- Second-half share of {c['fy']} revenue: {h2['share']['value']} (5-year average {h2['avg']['value']})",
          f"- NTM EPS ({', '.join(c['checks']['ntm_eps']['periods'])}): {c['checks']['ntm_eps']['value']}", "",
          "## Base rates (newest first: date, day move, idio, run-up, drift)"]
    L += [f"- {p['date']}: {p['move']}, {p['idio']}, {p['run_up']}, {p['drift']} ({p['refs']['move']})"
          for p in c["rates"]["prints"]]
    L += [f"Stats: {json.dumps(c['rates']['stats'])}", f"Daily sigma: {c['rates']['vol']['value']}",
          f"Stock vs SPY since the last print: {c['rates']['rel']['value']}",
          f"Options-implied move: {c['yahoo']['implied_move']}",
          f"Last 4 EPS surprises (Yahoo): {json.dumps(c['yahoo']['surprises'])}", "", "## Links (cell = value)"]
    for grp in ("multiples", "consensus"):
        L += [f"- {grp}.{k}: {v['ref']} = {v['value']}" for k, v in c["links"][grp].items() if isinstance(v, dict)]
    L += ["", "## Guidance trail (Filings Charts)"]
    for bl in c["guidance"]:
        L.append(f"- {bl['title']}: habitual raiser {bl['habitual']}; " +
                 "; ".join(f"{r['year']} {r['vs_mid']['value']} ({r['vs_mid']['ref']})" for r in bl["rows"]))
    L += ["", "## Code's answers", json.dumps(c["code"]), "", "## House thresholds", json.dumps(c["house"]), "",
          "## Documents since the last print (read them all; cite file.md:line, relative to the research folder)"]
    L += [f"- {d['date']} | {d['category']} | {d['label']} | {d['md']}" for d in c["new_docs"]] or ["- none"]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--values")
    ap.add_argument("--research")
    ap.add_argument("--forecast-plan")
    ap.add_argument("--today")
    a = ap.parse_args()
    c = run(a.model, a.work, a.ticker.upper(), a.values, a.research, a.forecast_plan, a.today)
    print(json.dumps({"quarter": c["quarter"], "report_date": c["report_date"], "price": c["price"],
                      "code": c["code"], "new_docs": len(c["new_docs"]), "missing": c["missing"],
                      "warnings": c["warnings"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
