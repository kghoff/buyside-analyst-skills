"""Step 8 - the driver math: everything about the key drivers that code can answer (Rule: if code can answer,
code answers). The driver analyst reads the output; it does no arithmetic of its own.

usage: python3 drivers.py --src <ticker folder> suggest     -> candidate metric names for drivers_config.json
       python3 drivers.py --src <ticker folder> run         -> drivers_math.json + drivers_math.md
Reads _work/series.csv and _work/drivers_config.json (the main agent's choice of revenue, cost, split and unit
metrics). Costs may be negative (model-historicals signs) or positive: every cost is used as its absolute value.
  anatomy       each split's share of revenue, growth and share of revenue growth, by year
  price_volume  revenue per average unit vs unit growth
  profit_bridge yearly change in operating income = revenue growth at last year's GROSS margin + gross-margin change
                (x revenue) + each opex line's dollar change (negative when it grew) + other (lines not in the config)
  sensitivity   'pull one driver': +1% revenue (or split) at gross margin with opex held, +100 bps
                gross margin, -1% of each opex line; effect on operating income, net income and FCF (after tax)
  cost_behavior incremental cost ratio vs average ratio over 5 years: variable / semi-fixed / fixed
  fcf_bridge    net income + D&A + SBC + working capital + other = CFO; CFO - capex = FCF; FCF / net income
  seasonality   average quarter share of the year, and the 2-year stack (this year's yoy + last year's yoy)"""
import argparse, csv, json, os, re
from collections import defaultdict

from common import load, save, work_dir


def load_series(path):
    d = defaultdict(dict)
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d[r["metric"]][r["period"]] = float(r["value"])
    return d


def fy(s, metric, y):
    v = s.get(metric, {})
    if f"FY{y}" in v:
        return v[f"FY{y}"]
    qs = [v.get(f"Q{q} {y}") for q in range(1, 5)]
    return sum(qs) if all(x is not None for x in qs) else None


def level(s, metric, y):
    v = s.get(metric, {})
    return v.get(f"FY{y}", v.get(f"Q4 {y}", v.get(f"{y}-12-31")))


def anatomy(s, total, parts, years):
    out = []
    for y in years:
        t, t0 = fy(s, total, y), fy(s, total, y - 1)
        ps = {p: fy(s, p, y) for p in parts}
        if t is None or any(v is None for v in ps.values()):
            continue
        row = {"year": y, "total": t, "sum_check": sum(ps.values()) / t - 1, "parts": {}}
        for p, v in ps.items():
            v0 = fy(s, p, y - 1)
            row["parts"][p] = {"value": v, "share": v / t, "growth": (v / v0 - 1) if v0 else None,
                               "contribution": (v - v0) / (t - t0) if v0 is not None and t0 is not None and t != t0 else None}
        out.append(row)
    return out


def price_volume(s, revenue, units, years):
    out = []
    for y in years:
        r, r0 = fy(s, revenue, y), fy(s, revenue, y - 1)
        u, u1, u2 = level(s, units, y), level(s, units, y - 1), level(s, units, y - 2)
        if None in (r, r0, u, u1, u2):
            continue
        avg, avg0 = (u + u1) / 2, (u1 + u2) / 2
        rpu, rpu0 = r / avg, r0 / avg0
        out.append({"year": y, "revenue_per_unit": rpu, "unit_growth": avg / avg0 - 1, "price_growth": rpu / rpu0 - 1,
                    "revenue_growth": r / r0 - 1})
    return out


def profit_bridge(s, revenue, cogs, opex, oi, years):
    out = []
    for y in years:
        R, R0 = fy(s, revenue, y), fy(s, revenue, y - 1)
        C, C0 = fy(s, cogs, y), fy(s, cogs, y - 1)
        O, O0 = fy(s, oi, y), fy(s, oi, y - 1)
        X = {k: fy(s, k, y) for k in opex}
        X0 = {k: fy(s, k, y - 1) for k in opex}
        if None in (R, R0, C, C0, O, O0) or None in X.values() or None in X0.values():
            continue
        gm, gm0 = (R - abs(C)) / R, (R0 - abs(C0)) / R0
        row = {"year": y, "change": O - O0, "revenue_growth": (R - R0) * gm0, "gross_margin": (gm - gm0) * R}
        for k in opex:
            row[k] = -(abs(X[k]) - abs(X0[k]))
        row["other"] = row["change"] - row["revenue_growth"] - row["gross_margin"] - sum(row[k] for k in opex)
        out.append(row)
    return out


def _need_full_year(s, cfg, y):
    if fy(s, cfg["revenue"], y) is None:
        raise SystemExit(f"last_year {y} has no full-year revenue; use the last complete fiscal year")


def sensitivity(s, cfg, y):
    _need_full_year(s, cfg, y)
    R, C, O = fy(s, cfg["revenue"], y), abs(fy(s, cfg["cogs"], y)), fy(s, cfg["operating_income"], y)
    ni = fy(s, cfg["net_income"], y) if cfg.get("net_income") else None
    fcf = None
    if cfg.get("cfo") and cfg.get("capex"):
        cfo, cx = fy(s, cfg["cfo"], y), fy(s, cfg["capex"], y)
        fcf = cfo - abs(cx) if None not in (cfo, cx) else None
    gm, tax, rows = (R - C) / R, cfg.get("tax_rate", 0.21), []

    def add(driver, move, d_oi):
        after_tax = d_oi * (1 - tax)
        rows.append({"driver": driver, "move": move, "d_oi": d_oi, "pct_oi": d_oi / O if O else None,
                     "pct_ni": after_tax / ni if ni else None, "pct_fcf": after_tax / fcf if fcf else None})

    add(cfg["revenue"], "+1%, costs below gross profit held", 0.01 * R * gm)
    for parts in cfg.get("splits", {}).values():
        for p in parts:
            v = fy(s, p, y)
            if v is not None:
                add(p, "+1%, at the company gross margin", 0.01 * v * gm)
    add("Gross margin", "+100 bps", 0.01 * R)
    for k in cfg["opex"]:
        add(k, "-1% of its dollars", 0.01 * abs(fy(s, k, y)))
    return sorted(rows, key=lambda r: -abs(r["d_oi"]))


def cost_behavior(s, revenue, costs, y_end, n=5):
    ys = list(range(y_end - n, y_end + 1))
    R = {y: fy(s, revenue, y) for y in ys}
    out = []
    for k in costs:
        C = {y: fy(s, k, y) for y in ys}
        if None in R.values() or None in C.values():
            out.append({"line": k, "class": "n.a. (history incomplete)"})
            continue
        C = {y: abs(v) for y, v in C.items()}
        avg = sum(C.values()) / sum(R.values())
        dR = R[y_end] - R[y_end - n]
        if dR <= 0:
            out.append({"line": k, "avg_ratio": avg, "class": "n.a. (revenue fell)"})
            continue
        inc = (C[y_end] - C[y_end - n]) / dR
        ratio = inc / avg
        out.append({"line": k, "avg_ratio": avg, "incremental_ratio": inc, "ratio": ratio,
                    "class": "variable" if ratio >= 0.8 else "fixed" if ratio <= 0.4 else "semi-fixed"})
    return out


def fcf_bridge(s, cfg, years):
    out = []
    for y in years:
        v = {k: fy(s, cfg[k], y) for k in ("net_income", "da", "sbc", "wc", "cfo", "capex")}
        if None in v.values():
            continue
        other = v["cfo"] - v["net_income"] - v["da"] - v["sbc"] - v["wc"]
        f = v["cfo"] - abs(v["capex"])
        out.append({"year": y, **v, "other": other, "fcf": f, "conversion": f / v["net_income"] if v["net_income"] > 0 else None})
    return out


def seasonality(s, revenue, years):
    v = s.get(revenue, {})
    shares, stack = defaultdict(list), {}
    for y in years:
        qs = [v.get(f"Q{q} {y}") for q in range(1, 5)]
        if None in qs:
            continue
        for q, x in enumerate(qs, 1):
            shares[q].append(x / sum(qs))
            a, b, c = x, v.get(f"Q{q} {y - 1}"), v.get(f"Q{q} {y - 2}")
            if b and c:
                stack[f"Q{q} {y}"] = (a / b - 1) + (b / c - 1)
    return {"avg_share": {f"Q{q}": sum(xs) / len(xs) for q, xs in shares.items()}, "stack": stack}


def compute(s, cfg):
    _need_full_year(s, cfg, cfg["last_year"])
    years = list(range(cfg["first_year"], cfg["last_year"] + 1))
    costs = [cfg["cogs"], *cfg["opex"]]
    out = {"config": cfg,
           "anatomy": {name: anatomy(s, cfg["revenue"], parts, years) for name, parts in cfg.get("splits", {}).items()},
           "price_volume": {u["name"]: price_volume(s, u["revenue"], u["units"], years) for u in cfg.get("units", [])},
           "profit_bridge": profit_bridge(s, cfg["revenue"], cfg["cogs"], cfg["opex"], cfg["operating_income"], years),
           "sensitivity": sensitivity(s, cfg, cfg["last_year"]),
           "cost_behavior": cost_behavior(s, cfg["revenue"], costs, cfg["last_year"]),
           "seasonality": seasonality(s, cfg["revenue"], years)}
    if all(cfg.get(k) for k in ("net_income", "da", "sbc", "wc", "cfo", "capex")):
        out["fcf_bridge"] = fcf_bridge(s, cfg, years)
    return out


def _f(x, pct=False, na="n.a."):
    if x is None:
        return na
    return f"{x:.1%}" if pct else f"{x:,.1f}"


def _e(x):
    return str(x).replace("|", "\\|")


def to_md(m):
    c = m["config"]
    L = ["# Driver math", "", f"All figures Calc from series.csv (model + reader data). Revenue = {_e(c['revenue'])}.", ""]
    for name, rows in m["anatomy"].items():
        L += [f"## Revenue anatomy: {_e(name)}", "", "| Year | Part | Value | Share | Growth | Share of growth |", "|---|---|---|---|---|---|"]
        for r in rows:
            for p, v in r["parts"].items():
                L.append(f"| {r['year']} | {_e(p)} | {_f(v['value'])} | {_f(v['share'], 1)} | {_f(v['growth'], 1)} | {_f(v['contribution'], 1)} |")
            if abs(r["sum_check"]) > 0.01:
                L.append(f"| {r['year']} | **parts differ from revenue by {_f(r['sum_check'], 1)}** | | | | |")
        L.append("")
    for name, rows in m["price_volume"].items():
        L += [f"## Price vs volume: {_e(name)}", "", "| Year | Revenue / avg unit (revenue units per unit) | Unit growth | Price growth | Revenue growth |", "|---|---|---|---|---|"]
        L += [f"| {r['year']} | {_f(r['revenue_per_unit'])} | {_f(r['unit_growth'], 1)} | {_f(r['price_growth'], 1)} | {_f(r['revenue_growth'], 1)} |" for r in rows]
        L.append("")
    opex = c["opex"]
    L += ["## Profit bridge (change in operating income)", "", "+ helped operating income, - hurt it. Revenue growth is valued at last year's gross margin; opex columns are each line's dollar change.", "",
          "| Year | Change | Revenue growth | Gross margin | " + " | ".join(_e(k) for k in opex) + " | Other |",
          "|---|" + "---|" * (4 + len(opex))]
    L += [f"| {r['year']} | {_f(r['change'])} | {_f(r['revenue_growth'])} | {_f(r['gross_margin'])} | "
          + " | ".join(_f(r[k]) for k in opex) + f" | {_f(r['other'])} |" for r in m["profit_bridge"]]
    L += ["", f"## Sensitivity ('pull one driver', FY{c['last_year']})", "", "| Driver | Move | Δ operating income | % op. income | % net income | % FCF |", "|---|---|---|---|---|---|"]
    L += [f"| {_e(r['driver'])} | {r['move']} | {_f(r['d_oi'])} | {_f(r['pct_oi'], 1)} | {_f(r['pct_ni'], 1)} | {_f(r['pct_fcf'], 1)} |" for r in m["sensitivity"]]
    L += ["", "## Cost behavior (last 5 years)", "", "| Line | Avg % of revenue | Incremental % | Ratio | Class |", "|---|---|---|---|---|"]
    L += [f"| {_e(r['line'])} | {_f(r.get('avg_ratio'), 1)} | {_f(r.get('incremental_ratio'), 1)} | {_f(r.get('ratio'))} | {r['class']} |" for r in m["cost_behavior"]]
    if "fcf_bridge" in m:
        L += ["", "## FCF bridge", "", "| Year | Net income | D&A | SBC | Working capital | Other | CFO | Capex | FCF | FCF / NI |", "|---|---|---|---|---|---|---|---|---|---|"]
        L += [f"| {r['year']} | {_f(r['net_income'])} | {_f(r['da'])} | {_f(r['sbc'])} | {_f(r['wc'])} | {_f(r['other'])} | {_f(r['cfo'])} | {_f(r['capex'])} | {_f(r['fcf'])} | {_f(r['conversion'], 1, 'n.m.')} |" for r in m["fcf_bridge"]]
    if m.get("extra_calcs"):
        L += ["", "## Extra calcs (computed by the main agent from cited inputs)", "", "| Name | Value | Unit | Formula | Inputs |", "|---|---|---|---|---|"]
        L += ["| " + " | ".join(_e(x.get(k, "")) for k in ("name", "value", "unit", "formula", "inputs")) + " |" for x in m["extra_calcs"]]
    se = m["seasonality"]
    L += ["", "## Seasonality", "", "Average share of the year: " + ", ".join(f"{q} {_f(v, 1)}" for q, v in se["avg_share"].items()),
          "", "2-year stack (yoy + prior-year yoy): " + ", ".join(f"{k} {_f(v, 1)}" for k, v in list(se["stack"].items())[-8:])]
    return "\n".join(L) + "\n"


KEYS = re.compile(r"revenue|sales|cost|expense|operating income|net income|tax|cash provided|capex|capital exp|"
                  r"depreciation|sbc|stock-based|working capital|shares|users|customers|subscribers|installed|units", re.I)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("cmd", choices=["suggest", "run"])
    a = ap.parse_args()
    w = work_dir(a.src)
    s = load_series(os.path.join(w, "series.csv"))
    if a.cmd == "suggest":
        for m in sorted(s):
            if KEYS.search(m):
                fys = sorted(p for p in s[m] if p.startswith("FY"))
                print(f"{m}  [{fys[0] if fys else 'quarters'}..{fys[-1] if fys else ''}]")
    else:
        cfg = load(os.path.join(w, "drivers_config.json"))
        if cfg is None:
            raise SystemExit("write _work/drivers_config.json first (see the docstring of this file)")
        named = [cfg["revenue"], cfg["cogs"], cfg["operating_income"], *cfg["opex"],
                 *[p for ps in cfg.get("splits", {}).values() for p in ps],
                 *[cfg[k] for k in ("net_income", "cfo", "capex", "da", "sbc", "wc") if cfg.get(k)],
                 *[u[k] for u in cfg.get("units", []) for k in ("revenue", "units")]]
        unknown = [m for m in dict.fromkeys(named) if m not in s]
        if unknown:
            raise SystemExit("not in series.csv: " + "; ".join(unknown))
        m = compute(s, cfg)
        extra = load(os.path.join(w, "extra_calcs.json"))
        if extra:
            m["extra_calcs"] = extra
        save(os.path.join(w, "drivers_math.json"), m)
        open(os.path.join(w, "drivers_math.md"), "w", encoding="utf-8").write(to_md(m))
        print("wrote drivers_math.json and drivers_math.md")
