"""The forecast plan as one readable markdown page for the user's approval (after a build, the headline results are appended).

usage: python3 plan_page.py --model MODEL.xlsx --plan forecast_plan.json --out forecast_plan.md [--headlines forecast_headlines.md]"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from methods import TOKEN, value_for                                   # noqa: E402
from modmap import ModMap                                              # noqa: E402

SECTIONS = [("Revenue build", r"REVENUE BUILD"), ("Income statement", r"INCOME"), ("Balance sheet", r"BALANCE|ASSETS|LIABILIT"),
            ("Cash flow", r"CASH FLOW")]


def _heading(section):
    for name, rx in SECTIONS:
        if re.search(rx, section, re.I):
            return name
    return section.strip(" :").capitalize()


def _pct(v):
    return f"{v * 100:g}%"


def _num(v):
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,}"


def _values(e):
    """(dict of year/quarter -> value, formatter) the entry types in, or (None, None)."""
    meth = e["method"]
    if meth in ("growth", "pct_of"):
        return e["rates"], _pct
    if meth == "days":
        return e["rates"], _num
    if meth == "seasonal":
        return (e["annual_growth"], _pct) if not e.get("fy_template") else (None, None)
    if meth == "schedule":
        return e["values"], _num
    if meth == "annual" and e.get("values"):
        vals = e["values"]
        small = all(isinstance(v, (int, float)) and abs(v) < 1.5 for v in vals.values())
        return vals, (_pct if small and e.get("unit") == "%" else _num)
    return None, None


def _at(vals, fmt, y):
    if vals is None:
        return "-"
    try:
        return fmt(value_for(vals, y, y, ""))
    except ValueError:
        return "n/a"


def _method(e, vals, fmt, first):
    meth = e["method"]
    if meth == "flat":
        return "held flat"
    if meth == "seasonal":
        if e.get("fy_template"):
            return "year = " + TOKEN.sub(lambda t: "{" + (t.group(1) + ":" if t.group(1) else "") + t.group(2).split(" | ", 1)[-1] + "}", e["fy_template"]) + ", quarters seasonal"
        return "seasonal growth (typed rate)"
    if meth == "annual":
        if e.get("templates"):
            return "yearly: " + "; ".join(f"{y}: " + (TOKEN.sub(lambda t: "{" + (t.group(1) + ":" if t.group(1) else "") + t.group(2).split(" | ", 1)[-1] + "}", v) if v else "stops")
                                          for y, v in sorted(e["templates"].items()))
        if e.get("template"):
            return "yearly: " + TOKEN.sub(lambda t: "{" + (t.group(1) + ":" if t.group(1) else "") + t.group(2).split(" | ", 1)[-1] + "}", e["template"])
        return "yearly input"
    if meth == "schedule":
        return "schedule"
    if meth == "formula":
        return TOKEN.sub(lambda t: "{" + (t.group(1) + ":" if t.group(1) else "") + t.group(2).split(" | ", 1)[-1] + "}", e["template"])
    word = {"growth": "growth", "pct_of": "% of revenue", "days": "days"}[meth]
    if meth == "pct_of" and e.get("rate_row", "% of sales") != "% of sales":
        word = e["rate_row"]
    return f"{word} {_at(vals, fmt, first)}"


def render(plan, m, headlines=None, coverage=None):
    years = m.forecast_years()
    yrs = {y for e in plan["rows"] for d in (_values(e)[0],) if d for y in d if re.match(r"\d{4}E$", y)}
    first, last = years[0], max(set(years) | yrs)
    out = [f"# {plan.get('ticker', '')} forecast plan", "", "Review each line; the build writes exactly this."]
    if plan.get("revenue_engine", "drivers") == "growth":
        out += ["", "## Revenue engine: GROWTH RATES (last resort)", "", f"Why no driver build: {plan.get('growth_reason', 'NOT GIVEN')}"]
    if plan.get("driver_sections"):
        out += ["", "## Driver sections (in order)", ""] + [f"- {d['title']}" for d in plan["driver_sections"]]
    if coverage:
        counts = {s: sum(1 for c in coverage if c.get("status") == s) for s in ("built", "explained", "missing")}
        out += ["", f"## Research coverage (independent review): {counts['built']} built, {counts['explained']} "
                f"explained, {counts['missing']} missing", "", "| recommendation | source | status | rows / why |",
                "|---|---|---|---|"]
        for c in coverage:
            where = ", ".join(r.split(" | ", 1)[-1] for r in c.get("rows", [])) or c.get("why", "")
            out.append(f"| {c.get('rec', '')} | {c.get('source', '')} | {c.get('status', '')} | {where} |".replace("\n", " "))
    if plan.get("drivers"):
        out += ["", "## Key drivers and the rows that carry them", ""]
        for d in plan["drivers"]:
            rows = ", ".join(k.split(" | ", 1)[-1] for k in d.get("rows", []))
            out.append(f"- **{d.get('name')}** -> {d.get('feeds', 'revenue').split(' | ', 1)[-1]}: {rows}")
    if plan.get("revenue_identity"):
        terms = [" x ".join(("avg " if f.get("average") else "") + f.get("name", f["key"].split(" | ", 1)[-1])
                            for f in t["factors"]) for t in plan["revenue_identity"]["terms"]]
        out += ["", "## Revenue identity (what /model-dcf extends to 30 years)", "", "Revenue = " + " + ".join(terms), ""]
        for t in plan["revenue_identity"]["terms"]:
            for f in t["factors"]:
                lr = f.get("long_run")
                out.append(f"- {f.get('name', f['key'])}: long-run growth {_pct(lr) if isinstance(lr, (int, float)) else 'MISSING'}"
                           f" ({(f.get('long_run_source') or 'no source').replace('|', '/')})")
    if plan.get("checks"):
        out += ["", "## Filings research checks (rows in the model; the check fails outside the bounds)", ""]
        for ck in plan["checks"]:
            b = " ".join(x for x in (f"min {ck['min']}" if ck.get("min") is not None else "",
                                     f"max {ck['max']}" if ck.get("max") is not None else "") if x)
            out.append(f"- {ck['what']}: {ck['key'].split(' | ', 1)[-1]}{' (' + b + ')' if b else ''}")
    groups = {}
    for e in plan["rows"]:
        groups.setdefault(_heading(e["key"].split(" | ", 1)[0]), []).append(e)
    order = [n for n, _ in SECTIONS] + sorted(set(groups) - {n for n, _ in SECTIONS})
    for name in order:
        if name not in groups:
            continue
        out += ["", f"## {name}", "", f"| line | method | {first} | {last} | source |", "|---|---|---|---|---|"]
        for e in groups[name]:
            vals, fmt = _values(e)
            label = e["key"].split(" | ", 1)[-1]
            out.append(f"| {label} | {_method(e, vals, fmt, first)} | {_at(vals, fmt, first)} | {_at(vals, fmt, last)} | "
                       f"{(e.get('source') or '').replace('|', '/')} |")
    if plan.get("guidance"):
        out += ["", "## Guidance the forecast must land inside", ""]
        for g in plan["guidance"]:
            why = f" (plan explains a miss: {g['outside']})" if g.get("outside") else ""
            lo_, hi_ = g.get("low"), g.get("high")
            rng = (f"at least {_num(lo_)}" if hi_ is None else f"at most {_num(hi_)}" if lo_ is None
                   else _num(lo_) if lo_ == hi_ else f"{_num(lo_)} to {_num(hi_)}")
            out.append(f"- {g['what']}: {rng} in {g['period']}{why}")
    if headlines:
        out += ["", headlines.rstrip()]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--headlines")
    ap.add_argument("--coverage", help="the reviewer's coverage.json")
    a = ap.parse_args()
    h = open(a.headlines, encoding="utf-8").read() if a.headlines else None
    cov = json.load(open(a.coverage, encoding="utf-8")) if a.coverage and os.path.exists(a.coverage) else None
    open(a.out, "w", encoding="utf-8").write(render(json.load(open(a.plan, encoding="utf-8")), ModMap(a.model), h, cov))


if __name__ == "__main__":
    main()
