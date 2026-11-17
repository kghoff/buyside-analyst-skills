"""Everything the valuation-analyst agent reads, in two files: context.json (for code and exact lookups) and
context.md (for the agent to read in one pass). Facts only: forward metrics, the DCF bridge (model-dcf's own math),
cell-by-cell dumps of the Multiples, Consensus and DCF tabs (so anchors can cite exact refs), the valuation brief,
the house defaults and the agent's last plan.

usage: python3 context.py --model M --work W --ticker T [--research-dir D]"""
import argparse
import json
import os
import re
import subprocess
import sys

import openpyxl

import brief
import lo
import metrics

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))
import settings  # noqa: E402

SCENARIO_EVAL = os.path.join(HERE, "scenario_eval.py")
NEEDS = {"MOD": "/model-forecast", "Px Data": "/model-price-history", "DCF": "/model-dcf",
         "Multiples": "/model-multiples"}
HOUSE = {"hurdle": .20, "buy_rr": 2.0, "pound_rr": 3.0, "discount": .15, "horizon_months": 12,
         "position": "long", "mkt_rev": .05, "mkt_oi": .08, "mkt_eps": .12}
CONSENSUS_CAP = 250
FADE_YEARS = 10      # model-dcf's dcfmath.FADE_YEARS (not imported: its modules share names with ours)


def _fmt(v):
    if isinstance(v, float):
        return repr(round(v, 6))
    return repr(v) if isinstance(v, str) else str(v)


def dump(ws, stop=None, first=1, last=None, cap=None):
    """One line per non-empty row, each cell as REF=value. Stops before a row whose column A matches `stop`."""
    out, n, capped = [], 0, False
    for row in ws.iter_rows(min_row=first, max_row=last):
        cells = [c for c in row if c.value is not None and c.value != ""]
        if not cells:
            continue
        a = row[0].value
        if stop and isinstance(a, str) and re.match(stop, a):
            break
        if cap and n >= cap:
            capped = True
            break
        out.append(f"row {row[0].row}: " + " | ".join(f"{c.coordinate}={_fmt(c.value)}" for c in cells))
        n += 1
    if capped:
        out.append(f"[Capped at {cap} rows; the tab goes on past row {row[0].row - 1}.]")
    return "\n".join(out)


def _brief(work, ticker, research_dir):
    path = os.path.join(work, "valuation_brief.md")
    base = os.path.join(research_dir, ticker)
    reps = [p for p in (brief.newest(os.path.join(base, f)) for f in brief.FOLDERS) if p]
    newest_rep = max((os.path.getmtime(p) for p in reps), default=0)
    summary_path = path + ".json"
    if os.path.exists(path) and os.path.exists(summary_path) and os.path.getmtime(path) > newest_rep:
        s = json.load(open(summary_path))
        s["reused"] = True
    else:
        text, s = brief.build(ticker, research_dir)
        open(path, "w", encoding="utf-8").write(text)
        json.dump(s, open(summary_path, "w"), indent=1)
        s["reused"] = False
    s["path"] = path
    return s, [os.path.relpath(p, base) for p in reps]


def _dcf_summary(dcf):
    yrs = dcf["input_years"]
    pick = [yrs[0], yrs[min(FADE_YEARS, len(yrs) - 1)], yrs[-1]]
    lines = [f"| input | {pick[0]} (first) | {pick[1]} (after the fade) | {pick[2]} (long run) |",
             "|---|---|---|---|"]
    for n in dcf["names"]:
        v = dcf["inputs"].get(n)
        if isinstance(v, dict):
            lines.append(f"| {n} | " + " | ".join(_fmt(v.get(y)) for y in pick) + " |")
        else:
            lines.append(f"| {n} | {_fmt(v)} (all years) | | |")
    return lines


def _md(ticker, m, dcf, dumps, b, reports, last_plan):
    def num(x, f="{:,.2f}"):
        return f.format(x) if isinstance(x, (int, float)) else "n/a"
    px = {k: f"${num(v['value'])} on {v['date']}" for k, v in dcf["price"].items()}
    L = [f"# {ticker} valuation context", "",
         "Facts only. Every number below is in context.json; every tab line carries its cell refs for anchors.", "",
         "## Today", "",
         f"- Price: {px['last']} ({dcf['refs']['price']}); 3-year high {px['high3y']}, low {px['low3y']}",
         f"- Net debt {dcf['refs']['net_debt']}, diluted shares {dcf['refs']['shares']}",
         f"- EPS basis: {'non-GAAP' if m['basis'] == 'ng' else 'GAAP'}; annualized volatility "
         f"{num(m['vol']['value'], '{:.1%}')} (last 253 closes)", "",
         f"| metric | NTM | NTM+1 | year {m['years3']} |", "|---|---|---|---|"]
    for k in ("eps", "rev", "gp", "ebitda", "fcf"):
        L.append(f"| {k} | " + " | ".join(num(m[k][b_]["value"]) for b_ in ("ntm", "ntm1", "y3")) + " |")
    L += ["", "Growth from the last actual year (CAGR):", ""]
    for k, g in m["growth"].items():
        L.append(f"- {k}: {num(g['start'])} → {num(g['end'])} over {g['years']} years = {num(g['cagr'], '{:.1%}')} "
                 f"({g['start_ref']} → {g['end_ref']})")
    L += ["", "## DCF (model-dcf's math, the user's current inputs)", "",
          f"- Value per share ${num(dcf['value_per_share'])} ({dcf['refs']['vps']}); "
          f"terminal-value share {num(dcf.get('tv_share'), '{:.0%}')}"]
    if dcf.get("stale"):
        L.append(f"- STALE: {dcf['stale']}")
    L += [""] + _dcf_summary(dcf) + ["", "Reverse DCF (what each price implies):", "",
                                    "```", json.dumps(dcf["reverse"], indent=1), "```", ""]
    L += ["## Multiples (tab, down to its weekly data)", "", "```", dumps["Multiples"], "```", "",
          "## Consensus (tab)", "", "```", dumps["Consensus"] or "(no Consensus tab: /model-consensus not run)",
          "```", "", "## DCF (tab, rows 1-30)", "", "```", dumps["DCF"], "```", "",
          "## House defaults (chapter 11)", "", "```", json.dumps(HOUSE, indent=1), "```", "",
          "## Brief", "", f"- File: {b['path']} ({b['words']} words; {'reused' if b['reused'] else 'rebuilt'})",
          f"- Reports (research anchors cite these paths): {', '.join(reports) or 'none found'}"]
    L += [f"- Missing section: {x}" for x in b["missing"]]
    L += [f"- Cut: {c['section']} ({c['kept']} of {c['words']} words; rest at {c['source']})" for c in b["cut"]]
    L += ["", "## Last plan", "",
          "Your previous valuation_plan.json is in context.json (`last_plan`); start from it." if last_plan
          else "None: first run."]
    return "\n".join(L) + "\n"


def run(model, work, ticker, research_dir=None):
    model = os.path.abspath(model)
    research_dir = research_dir or settings.research_dir()
    tabs = openpyxl.load_workbook(model, read_only=True).sheetnames
    missing = [f"{t} (run {s})" for t, s in NEEDS.items() if t not in tabs]
    if missing:
        raise SystemExit("model-valuation: the model is missing " + ", ".join(missing) + ".")
    os.makedirs(work, exist_ok=True)
    values = lo.recalc(model, os.path.join(work, "values"))

    dcf_json = os.path.join(work, "dcf_ctx.json")
    cmd = [sys.executable, "-I", SCENARIO_EVAL, "context", "--model", model, "--out", dcf_json]
    fplan = os.path.join(os.path.dirname(model), "_model_work", "forecast", "forecast_plan.json")
    if os.path.exists(fplan):
        cmd += ["--plan", fplan]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"model-valuation: the DCF bridge failed:\n{r.stderr.strip()}")
    dcf = json.load(open(dcf_json))
    dcf.pop("ctx", None)            # model-dcf's internal context: the eval step reads it from dcf_ctx.json

    m = metrics.collect(model, values)
    wb = openpyxl.load_workbook(values, data_only=True)
    dumps = {"Multiples": dump(wb["Multiples"], stop=r"^WEEKLY DATA"),
             "Consensus": dump(wb["Consensus"], cap=CONSENSUS_CAP) if "Consensus" in wb.sheetnames else None,
             "DCF": dump(wb["DCF"], last=30)}
    b, reports = _brief(work, ticker, research_dir)
    lp = os.path.join(work, "valuation_plan.json")
    last_plan = json.load(open(lp)) if os.path.exists(lp) else None

    ctx = {"ticker": ticker, "metrics": m, "dcf": dcf, "dumps": dumps, "brief": b, "reports": reports,
           "house": HOUSE, "last_plan": last_plan, "values": values}
    json.dump(ctx, open(os.path.join(work, "context.json"), "w"), indent=1, default=str)
    open(os.path.join(work, "context.md"), "w", encoding="utf-8").write(
        _md(ticker, m, dcf, dumps, b, reports, last_plan))
    return ctx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--research-dir")
    a = ap.parse_args()
    ctx = run(a.model, a.work, a.ticker.upper(), a.research_dir)
    print(json.dumps({"wrote": os.path.join(a.work, "context.json"), "values": ctx["values"],
                      "stale": ctx["dcf"].get("stale"), "brief_missing": ctx["brief"]["missing"]}, indent=1))


if __name__ == "__main__":
    main()
