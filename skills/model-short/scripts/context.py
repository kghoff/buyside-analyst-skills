# skills/model-short/scripts/context.py
"""Everything the short-analyst agent and build.py read: context.json (exact values and the formulas that make them),
context.md (the same for the agent, in one pass) and rowmap.md (MOD's row keys, to cite cells).

Facts only. MOD sums over the last 4 / 8 / 12 / 20 reported quarters and the forecast quarters; links to Multiples,
Valuation, Consensus and Px Events found by their labels; Yahoo's short data (W/short.json from fetch_short.mjs); and
code's own ticks on the computed scorecard rows (shortmath.code_ticks). MOD rows are found by label within their
statement section, as model-dcf and model-multiples do, so any company's MOD works.

usage: python3 context.py --model M --work W --ticker T [--values RECALCULATED.xlsx]
       (without --values, M is recalculated in LibreOffice into W/values first)"""
import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import openpyxl  # noqa: E402
from openpyxl.utils import column_index_from_string as ci, get_column_letter as L  # noqa: E402

import shortmath as sm  # noqa: E402
from modmap import ModMap  # noqa: E402

REQUIRED = {"MOD": "model-historicals", "Px Data": "model-price-history", "Multiples": "model-multiples"}
OPTIONAL = ("Valuation", "Consensus", "Px Events")
ROLES = [  # (name, section regex, label regex, required, take the last match)
    ("rev", r"^income statement:?$", r"^(total )?revenue", True, False),
    ("oi", r"^income statement:?$", r"^operating income", True, False),
    ("ni", r"^income statement:?$", r"^net income", True, False),
    ("eps", r"^income statement:?$", r"^eps, diluted", True, False),
    ("ni_adj", r"^non-gaap", r"^non-gaap net income", False, False),
    ("da", r"operating activities", r"depreciation", True, False),
    ("cfo", r"operating activities", r"^net cash provided by operating", True, False),
    ("acq", r"investing activities", r"acquisition", False, False),
    ("capex", r"free cash flow|investing activities", r"capital expenditure|purchases? of property", True, True),
    ("fcf", r".", r"free cash flow$", True, True),
]


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def norm(t):
    return " ".join(t.lower().replace("(-)", "").replace("(+)", "").replace("(+/-)", "").split())


def grid(ws):
    g = {}
    for r, row in enumerate(ws.iter_rows(values_only=True), start=1):
        for c, v in enumerate(row, start=1):
            if v is not None:
                g[(r, c)] = v
    return g


def col_a(g):
    """[(row, text)] of column A, in row order."""
    return sorted((r, str(v).strip()) for (r, c), v in g.items() if c == 1 and isinstance(v, str))


def find_rows(mm):
    lines = [(r, k.split(" | ", 1)[0].lower(), norm(re.sub(r" #\d+$", "", k.split(" | ", 1)[1])))
             for k, r in mm.keys.items()]
    out, missing = {}, []
    for name, sec, lab, req, last in ROLES:
        hits = [r for r, s, lb in lines if re.search(sec, s) and re.search(lab, lb)]
        if hits:
            out[name] = hits[-1] if last else hits[0]
        elif req:
            missing.append(name)
    if missing:
        raise SystemExit("model-short: MOD has no row for " + ", ".join(missing) + ". It looks for them by label "
                         "within their statement section, as model-dcf does. Check the row labels in the model.")
    return out


def mod_metrics(mm, g, rows):
    qs = [p for p in mm.order if mm.is_q(p)]
    act = [p for p in qs if not p.endswith("E")]
    fq = mm.forecast_quarters()
    fys = [p for p in mm.order if re.fullmatch(r"\d{4}", p)][-10:]
    Lq, Pq, PPq, F20 = act[-4:], act[-8:-4], act[-12:-8], act[-20:]

    def cells(ps, row):
        return ",".join(f"MOD!${mm.col(p)}${row}" for p in ps)

    def sf(ps, row):
        return f"SUM({cells(ps, row)})"

    def sv(ps, row):
        return float(sum(v for p in ps if _num(v := g.get((row, ci(mm.col(p)))))))

    def cv(p, row):
        v = g.get((row, ci(mm.col(p))))
        return v if _num(v) else None

    out = {}

    def put(name, formula, value):
        out[name] = {"formula": f"IFERROR({formula},NA())", "value": value}

    rev, oi, eps = rows["rev"], rows["oi"], rows["eps"]
    gr = lambda a, b: sm.div(a, b) - 1 if sm.div(a, b) is not None else None   # noqa: E731
    if len(act) >= 8:
        put("ttm_growth", f"{sf(Lq, rev)}/{sf(Pq, rev)}-1", gr(sv(Lq, rev), sv(Pq, rev)))
        put("incr", f"({sf(Lq, oi)}-{sf(Pq, oi)})/({sf(Lq, rev)}-{sf(Pq, rev)})",
            sm.div(sv(Lq, oi) - sv(Pq, oi), sv(Lq, rev) - sv(Pq, rev)))
    if len(act) >= 12:
        now, ago = gr(sv(Lq, rev), sv(Pq, rev)), gr(sv(Pq, rev), sv(PPq, rev))
        put("ttm_growth_prior", f"{sf(Pq, rev)}/{sf(PPq, rev)}-1", ago)
        put("decel", f"({sf(Lq, rev)}/{sf(Pq, rev)}-1)-({sf(Pq, rev)}/{sf(PPq, rev)}-1)",
            now - ago if None not in (now, ago) else None)
    if len(act) >= 4:
        opm = sm.div(sv(Lq, oi), sv(Lq, rev))
        put("opm", f"{sf(Lq, oi)}/{sf(Lq, rev)}", opm)
        put("capex_da", f"ABS({sf(Lq, rows['capex'])})/{sf(Lq, rows['da'])}",
            sm.div(abs(sv(Lq, rows["capex"])), sv(Lq, rows["da"])))
        if fys:
            fm = [sm.div(cv(p, oi), cv(p, rev)) for p in fys]
            peak = max(fm) if None not in fm else None
            put("peak_ratio", f"({sf(Lq, oi)}/{sf(Lq, rev)})/MAX("
                + ",".join(f"MOD!${mm.col(p)}${oi}/MOD!${mm.col(p)}${rev}" for p in fys) + ")", sm.div(opm, peak))
    if "acq" in rows:
        put("acq_cfo", f"ABS({sf(F20, rows['acq'])})/{sf(F20, rows['cfo'])}",
            sm.div(abs(sv(F20, rows["acq"])), sv(F20, rows["cfo"])))
    ni = rows.get("ni_adj") or rows["ni"]
    put("fcf_conv", f"{sf(F20, rows['fcf'])}/{sf(F20, ni)}", sm.div(sv(F20, rows["fcf"]), sv(F20, ni)))
    if len(fq) >= 4:
        put("ntm_eps", sf(fq[:4], eps), sv(fq[:4], eps))
    if len(fq) >= 8:
        put("ntm_growth", f"{sf(fq[4:8], eps)}/{sf(fq[:4], eps)}-1", gr(sv(fq[4:8], eps), sv(fq[:4], eps)))
    if len(fq) >= 16:
        ratio = sm.div(sv(fq[12:16], eps), sv(fq[:4], eps))
        put("eps_cagr3", f"({sf(fq[12:16], eps)}/{sf(fq[:4], eps)})^(1/3)-1",
            ratio ** (1 / 3) - 1 if ratio is not None and ratio > 0 else None)
    periods = {"last4": Lq, "prior4": Pq, "prior8": PPq, "last20": F20, "ntm": fq[:4], "ntm1": fq[4:8],
               "y3": fq[12:16], "fy10": fys}
    basis = {"fcf_conv_ni": "non-GAAP net income" if rows.get("ni_adj") else "GAAP net income", "eps": "GAAP diluted"}
    return out, periods, basis


def multiples_links(g):
    a = col_a(g)
    hdr = next((r for r, t in a if t == "Metric"), None)
    if hdr is None:
        return {}
    heads = {str(v).strip(): c for (r, c), v in g.items() if r == hdr and isinstance(v, str)}
    pe = next((r for r, t in a if r > hdr and t == "P/E"), None)
    peer = next((r for r, t in a if r > hdr and "core-peer median" in t), None)
    out = {}
    for name, row, head in (("pe_today", pe, "Today"), ("pe_pct", pe, "5 years percentile"),
                            ("peer_gap", peer, "Today"), ("peer_pct", peer, "5 years percentile")):
        c = heads.get(head)
        v = g.get((row, c)) if row and c else None
        if _num(v):                           # a blank shows as 0 in Excel, None here: no link, the tick is ?
            out[name] = {"ref": f"Multiples!${L(c)}${row}", "value": v}
    return out


def valuation_links(g):
    a, out = col_a(g), {}
    pr = next((r for r, t in a if t == "Price"), None)
    if pr and _num(g.get((pr, 2))):
        out["valuation_price"] = {"ref": f"Valuation!$B${pr}", "value": g[(pr, 2)]}
    hdr = next((r for r, t in a if t.startswith("6. DCF scenarios")), None)
    if hdr:
        base = next((c for (r, c), v in g.items() if r == hdr and v == "Base"), None)
        row = next((r for r, t in a if r > hdr and t == "DCF value per share"), None)
        if base and row and _num(g.get((row, base))):
            out["dcf_base"] = {"ref": f"Valuation!${L(base)}${row}", "value": g[(row, base)]}
    return out


def consensus_links(g):
    a = col_a(g)
    top = next((r for r, t in a if t.startswith("5. CONSENSUS SNAPSHOTS")), None)
    if top is None:
        return {}
    heads = {str(v).strip(): c for (r, c), v in g.items() if r == top + 1 and isinstance(v, str)}
    cs, cp, ce = heads.get("Snapshot"), heads.get("Period"), heads.get("EPS mean")
    if not (cs and cp and ce):
        return {}
    rows, r = [], top + 2
    while g.get((r, cs)) is not None:
        rows.append((r, str(g.get((r, cp))), g.get((r, ce))))
        r += 1
    cnt = Counter(p for _, p, _ in rows)
    if not cnt:
        return {}
    period = [p for _, p, _ in rows if cnt[p] == max(cnt.values())][-1]
    mine = [(r, v) for r, p, v in rows if p == period and _num(v)]
    if len(mine) < 2:
        return {}
    (r0, v0), (r1, v1) = mine[0], mine[-1]
    snap = lambda r: str(g.get((r, cs)))[:10]   # noqa: E731
    return {"rev_first": {"ref": f"Consensus!${L(ce)}${r0}", "value": v0, "snapshot": snap(r0), "period": period},
            "rev_last": {"ref": f"Consensus!${L(ce)}${r1}", "value": v1, "snapshot": snap(r1), "period": period}}


def earn_move(g):
    hr = next((r for (r, c), v in sorted(g.items()) if r <= 10 and v == "Idio % chg"), None)
    if hr is None:
        return None
    heads = {v: c for (r, c), v in g.items() if r == hr and isinstance(v, str)}
    ct, cid = heads.get("Type"), heads["Idio % chg"]
    refs, vals = [], []
    for r in range(hr + 1, max(r for r, _ in g) + 1):
        t, v = g.get((r, ct)), g.get((r, cid))
        if isinstance(t, str) and "earn" in t.lower() and _num(v):
            refs.append(f"'Px Events'!${L(cid)}${r}")
            vals.append(abs(v))
    if not refs:
        return None
    return {"formula": "IFERROR(MEDIAN(" + ",".join(f"ABS({x})" for x in refs) + "),NA())",
            "value": statistics.median(vals), "n": len(refs)}


def _short(work):
    p = os.path.join(work, "short.json")
    if not os.path.exists(p):
        return {"error": "fetch_short.mjs was not run"}
    return json.load(open(p))


def _md(ticker, c):
    lines = [f"# {ticker} short check: context", "", f"Price: {c['price']['value']} ({c['price']['source']})",
             f"Stale check: {c['stale']}", f"Missing optional tabs: {', '.join(c['missing']) or 'none'}", "",
             "## MOD metrics (value; formula)"]
    lines += [f"- {k}: {v['value']} ; ={v['formula']}" for k, v in c["metrics"].items()]
    lines += ["", f"Periods: {json.dumps(c['mod']['periods'])}", f"Basis: {json.dumps(c['mod']['basis'])}", "",
              "## Links to other tabs (cell = value)"]
    lines += [f"- {k}: {v['ref']} = {v['value']}" for k, v in c["links"].items()]
    lines += ["", "## Yahoo short data", json.dumps(c["short"]), "", "## Code's ticks on the computed rows"]
    lines += [f"- {k}: {v}" for k, v in c["code_ticks"].items()]
    lines += ["", "## House defaults", json.dumps(c["house"]), "",
              "MOD row keys (to cite a cell, use its column from the periods above): see rowmap.md"]
    return "\n".join(lines) + "\n"


def run(model, work, ticker, values=None):
    os.makedirs(work, exist_ok=True)
    if values is None:
        import lo
        values = lo.recalc(model, os.path.join(work, "values"))
    wb = openpyxl.load_workbook(values, read_only=True, data_only=True)
    for tab, skill in REQUIRED.items():
        if tab not in wb.sheetnames:
            raise SystemExit(f"model-short: the model has no {tab} tab. Run /{skill} first.")
    missing = [t for t in OPTIONAL if t not in wb.sheetnames]
    g = {t: grid(wb[t]) for t in ("MOD", "Multiples", *[t for t in OPTIONAL if t in wb.sheetnames])}
    mm = ModMap(values)
    rows = find_rows(mm)
    metrics, periods, basis = mod_metrics(mm, g["MOD"], rows)
    links = multiples_links(g["Multiples"])
    if "Valuation" in g:
        links.update(valuation_links(g["Valuation"]))
    if "Consensus" in g:
        links.update(consensus_links(g["Consensus"]))
        if "rev_first" in links:
            f, l2 = links["rev_first"], links["rev_last"]
            metrics["revision"] = {"formula": f"IFERROR({l2['ref']}/{f['ref']}-1,NA())",
                                   "value": sm.div(l2["value"], f["value"]) - 1}
    if "Px Events" in g and (em := earn_move(g["Px Events"])):
        metrics["earn_move"] = em
    short = _short(work)
    if short.get("error"):
        price = {"value": None, "source": f"Yahoo failed ({short['error']}, {short.get('asof', '')})"}
    else:
        price = {"value": short["price"], "source": f"Yahoo Finance, {short['asof']}"}
    vp = (links.get("valuation_price") or {}).get("value")
    diff = sm.div(price["value"], vp) - 1 if sm.div(price["value"], vp) is not None else None
    ctx = {"ticker": ticker, "values": os.path.abspath(values), "price": price, "short": short,
           "stale": {"valuation_price": vp, "diff": diff, "flag": diff is not None and abs(diff) > sm.STALE_TOL},
           "mod": {"rows": rows, "periods": periods, "basis": basis}, "metrics": metrics, "links": links,
           "missing": missing, "house": dict(sm.HOUSE), "thresholds": dict(sm.THRESH)}
    ctx["code_ticks"] = sm.code_ticks(sm.flat(ctx, sm.HOUSE["hurdle"]))
    json.dump(ctx, open(os.path.join(work, "context.json"), "w"), indent=1, default=str)
    open(os.path.join(work, "context.md"), "w").write(_md(ticker, ctx))
    import modmap
    modmap.rowmap(values, os.path.join(work, "rowmap.md"))
    return ctx


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--values")
    a = ap.parse_args()
    c = run(a.model, a.work, a.ticker.upper(), a.values)
    print(json.dumps({"price": c["price"], "stale": c["stale"], "missing": c["missing"], "code_ticks": c["code_ticks"]},
                     indent=1, default=str))


if __name__ == "__main__":
    main()
