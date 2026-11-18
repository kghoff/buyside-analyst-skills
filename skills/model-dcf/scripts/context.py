"""Reads the user's model (MOD, Px Data) into context.json: the values the DCF needs and where each came from.

usage: python3 context.py <model.xlsx> <out context.json> [forecast_plan.json]
Read only (cached values). Revenue's drivers come from the forecast plan's `revenue_identity` (default: the model's
_model_work/forecast/forecast_plan.json); without one, revenue itself is the single driver (a growth engine, flagged).
KEYS are the template's statement rows; an unknown row stops with its name."""
import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modmap import ModMap  # noqa: E402

# (name, section regex, label regex, required): MOD rows found by role (sections anchored: a forecast's driver
# sections, e.g. "INCOME STATEMENT DRIVERS" or "... (NON-GAAP)", must not be read as the statements), the way /model-historicals reads its template, so
# the user's own labels ("Current LT Senior Convertible Notes") and the template's ("Current Portion of Debt") both work.
ROLES = [
    ("rev", r"^income statement:?$", r"^revenue", True),
    ("gp", r"^income statement:?$", r"^gross profit", True),
    ("oi", r"^income statement:?$", r"^operating income", True),
    ("tax_rate", r"^income statement:?$", r"tax rate", True),
    ("shares", r"^income statement:?$", r"^shares, diluted", True),
    ("eps", r"^income statement:?$", r"^eps, diluted", True),
    ("eps_ng", r"^non-gaap", r"non-gaap eps, diluted", False),
    ("cash", r"^assets", r"^cash", True),
    ("st", r"^assets", r"short-term (marketable|investments)|marketable securities", False),
    ("da", r"operating activities", r"depreciation", True),
    ("wc", r"operating activities", r"working capital changes, net", True),
    ("capex", r"investing activities", r"capex|purchase of pp&e|property", True),
]
DEBT = r"debt|notes|borrowing|convertible|credit facilit|commercial paper|finance lease|loan"
NOT_DEBT = r"^total|accounts payable|operating lease|interest payable|accrued|deferred"
KEYS = {"rev": "INCOME STATEMENT | Revenue:"}     # the fallback driver's key (only when there is no identity)


def find_rows(mm):
    """{name: MOD row} for ROLES (first match in its section; an optional role may be missing), plus
    'debt_current' / 'debt_lt': every liability row that reads as debt, split at Total Current Liabilities."""
    out, missing = {}, []
    lines = [(r, k.split(" | ", 1)[0], re.sub(r" #\d+$", "", k.split(" | ", 1)[1])) for k, r in mm.keys.items()]
    norm = lambda t: " ".join(t.lower().replace("(-)", "").replace("(+)", "").replace("(+/-)", "").split())
    for name, sec, lab, req in ROLES:
        hit = next((r for r, s_, l_ in lines if re.search(sec, s_.lower()) and re.search(lab, norm(l_))), None)
        if hit is None and req:
            missing.append(name)
        elif hit is not None:
            out[name] = hit
    liab = [(r, norm(l_)) for r, s_, l_ in lines if re.search(r"liabilities", s_.lower())]
    tcl = next((r for r, l_ in liab if re.search(r"total current liabilities", l_)), None)
    debt = [r for r, l_ in liab if re.search(DEBT, l_) and not re.search(NOT_DEBT, l_)]
    out["debt_current"] = [r for r in debt if tcl is not None and r < tcl]
    out["debt_lt"] = [r for r in debt if tcl is None or r > tcl]
    if missing:
        plain = {"rev": "Revenue (income statement)", "gp": "Gross Profit (income statement)",
                 "oi": "Operating Income (income statement)", "tax_rate": "Income Tax Rate (income statement)",
                 "shares": "Shares, diluted (income statement)", "eps": "EPS, diluted (income statement)",
                 "cash": "Cash & Equivalents (assets)", "da": "Depreciation & Amortization (operating cash flows)",
                 "wc": "Working Capital Changes, Net (operating cash flows)",
                 "capex": "CapEx (Purchase of PP&E) (investing cash flows)"}
        raise SystemExit("model-dcf: MOD has no row for " + "; ".join(plain.get(n, n) for n in missing) + ". It looks "
                         "for these by label within their statement section. Check the row labels in the model.")
    return out


def _load(path, mm):
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)["MOD"]
    return {i: list(r) for i, r in enumerate(ws.iter_rows(min_row=1, max_row=max(mm.keys.values()) + 1, values_only=True), 1)}


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def load_identity(path, plan=None):
    """(identity, plan path or None). Fallback: revenue as the only driver, long-run 0%."""
    plan = plan or os.path.join(os.path.dirname(os.path.abspath(path)), "_model_work", "forecast", "forecast_plan.json")
    ident = json.load(open(plan)).get("revenue_identity") if os.path.exists(plan) else None
    if ident and ident.get("terms"):
        return ident, plan
    return {"terms": [{"factors": [{"key": KEYS["rev"], "name": "Revenue", "average": False, "long_run": 0.0,
                                    "long_run_source": "fallback: the forecast plan has no revenue identity, so revenue "
                                                       "is the only driver (rerun /model-forecast to build it from the key drivers)"}]}]}, None


def build(path, plan=None):
    try:
        return _build(path, plan=plan)
    except _Missing:
        tmp = tempfile.mkdtemp(prefix="dcf_ctx_")
        try:                                  # the recalculated file is a copy of the user's model: never keep it
            import lo
            return _build(lo.recalc(path, tmp), orig=path, plan=plan)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class _Missing(Exception):
    pass


def _build(path, orig=None, plan=None):
    mm = ModMap(path)
    ident, plan_path = load_identity(orig or path, plan)
    rows = find_rows(mm)
    keys = {}
    flat = [f for t in ident["terms"] for f in t["factors"]]
    for i, f in enumerate(flat):
        keys[f"f{i}"] = f["key"]
    for n, key in keys.items():
        try:
            rows[n] = mm.row(key)
        except KeyError:
            raise SystemExit(f"model-dcf: MOD has no row '{key}' (needed for the DCF). Check the row label in the model.")
    grid = _load(path, mm)

    def cell(n, label):
        col = mm.col(label)
        ci = openpyxl.utils.column_index_from_string(col) - 1
        return _num(grid[rows[n]][ci]), f"MOD!{col}{rows[n]}"

    blank_as_0 = []                   # blank cells counted as 0 (forecast-only additive terms): the user is told

    def need(n, label, blank_is_0=False):
        v, ref = cell(n, label)
        if v is None:
            if orig is None:
                raise _Missing()
            if blank_is_0:
                blank_as_0.append(f"{ref} ({keys.get(n, n)}, {label})")
                return 0.0, ref
            raise SystemExit(f"model-dcf: MOD {ref} ({keys.get(n, n)}, {label}) has no value, even after a recalculation.")
        return v, ref

    def _need_row(r):
        """A debt row at the cap-table quarter: blank counts as 0 (no balance that quarter)."""
        col = mm.col(q4)
        v = _num(grid[r][openpyxl.utils.column_index_from_string(col) - 1])
        return (v or 0.0), f"MOD!{col}{r}"

    fy = [p for p in mm.order if re.match(r"\d{4}E?$", p)]
    year0 = next(p for p in reversed(fy) if p.endswith("E") and any(not q.endswith("E") for q in mm.quarters_of(p)))
    y0 = int(year0[:4])
    fc = []
    while True:
        lab = f"{y0 + len(fc) + 1}E"
        if lab not in mm.labels or cell("rev", lab)[0] is None:
            break
        fc.append(lab)
    last_actual = str(y0 - 1)
    if last_actual not in mm.labels:
        raise SystemExit(f"model-dcf: MOD has no column for last actual year {last_actual}.")

    refs = {}
    rev0, refs["rev0"] = need("rev", year0)
    gp0, r_gp = need("gp", year0)
    oi0, r_oi = need("oi", year0)
    out = {"year0": year0, "forecast_years": fc, "k": len(fc), "rev0": rev0, "gm0": gp0 / rev0, "opex0": gp0 - oi0}
    refs.update(gm0=[r_gp, refs["rev0"]], opex0=[r_gp, r_oi])     # opex = all operating expenses = GP - OI

    factors, terms, n = [], [], 0
    for t in ident["terms"]:
        idx = []
        alone = len(t["factors"]) == 1   # an additive term written only from the forecast on: empty before it = 0
        for f in t["factors"]:           # (never inside a product: a 0 there would wipe the whole term)
            fid = f"f{n}"
            lp, rp = need(fid, last_actual, alone)
            l0, r0 = need(fid, year0, alone)
            ms = [need(fid, lab) for lab in fc]
            factors.append({"name": f.get("name") or f["key"].split(" | ", 1)[-1], "key": f["key"],
                            "average": bool(f.get("average")), "long_run": float(f["long_run"]),
                            "long_run_source": f.get("long_run_source", ""), "unit": mm_unit(mm, f["key"]),
                            "level_prev": lp, "level0": l0, "mod": [v for v, _ in ms],
                            "refs": {"prev": rp, "year0": r0, "mod": [r for _, r in ms]}, "row": rows[fid]})
            idx.append(n)
            n += 1
        terms.append(idx)
    out["factors"], out["terms"], out["blank_as_0"] = factors, terms, blank_as_0
    out["identity_fallback"], out["forecast_plan"] = plan_path is None, plan_path

    mod = {x: [] for x in ("rev", "gp", "opex", "tax_rate", "da", "capex", "wc")}
    mr = {x: [] for x in mod}
    for lab in fc:
        v, r = need("rev", lab); mod["rev"].append(v); mr["rev"].append(r)
        v, r = need("gp", lab); mod["gp"].append(v); mr["gp"].append(r)
        a, ra = need("gp", lab)
        b, rb = need("oi", lab)
        mod["opex"].append(a - b); mr["opex"].append([ra, rb])
        v, r = need("tax_rate", lab); mod["tax_rate"].append(v); mr["tax_rate"].append(r)
        v, r = need("da", lab); mod["da"].append(v); mr["da"].append(r)
        v, r = need("capex", lab); mod["capex"].append(-v); mr["capex"].append(r)
        v, r = need("wc", lab); mod["wc"].append(v); mr["wc"].append(r)
    out["mod"], refs["mod"] = mod, mr

    eps = {"gaap": {}, "non_gaap": {}}
    for nm, n in (("gaap", "eps"), ("non_gaap", "eps_ng")):
        if n not in rows:
            continue
        eps[nm]["year0"] = need(n, year0)[0]
        if fc:
            eps[nm]["year1"] = need(n, fc[0])[0]
    out["eps"] = eps

    q4 = f"Q4 {str(y0)[2:]}E"
    q4 = q4 if q4 in mm.labels else f"Q4 {str(y0)[2:]}"
    cap = {"column": mm.col(q4), "quarter": q4}
    for nm, n in (("cash", "cash"), ("shares", "shares")):
        cap[nm], refs[f"cap_{nm}"] = need(n, q4)
    cap["st_securities"], refs["cap_st_securities"] = need("st", q4) if "st" in rows else (0.0, None)
    for nm in ("debt_current", "debt_lt"):                       # every debt-like row, summed (none = 0)
        got = [_need_row(r) for r in rows[nm]]
        cap[nm], refs[f"cap_{nm}"] = sum(v for v, _ in got), [x for _, x in got]
        cap[nm + "_labels"] = [next(k for k, rr in mm.keys.items() if rr == r).split(" | ", 1)[1] for r in rows[nm]]
    cap["debt"] = cap["debt_current"] + cap["debt_lt"]
    out["cap"] = cap
    out["net_debt"] = cap["debt"] - cap["cash"] - cap["st_securities"]
    out["shares"] = cap["shares"]

    hist = []
    for lab in fy:
        if lab.endswith("E") or int(lab) >= y0:
            continue
        if cell("rev", lab)[0] is None:
            continue
        h = {"year": lab}
        for key, n in (("rev", "rev"), ("gp", "gp"), ("tax_rate", "tax_rate"), ("da", "da"), ("capex", "capex"), ("wc", "wc")):
            h[key] = cell(n, lab)[0]
        h["levels"] = [cell(f"f{i}", lab)[0] for i in range(len(factors))]
        h["capex"] = None if h["capex"] is None else -h["capex"]
        g_, o_ = cell("gp", lab)[0], cell("oi", lab)[0]
        h["opex"] = None if g_ is None or o_ is None else g_ - o_
        hist.append(h)
    out["history"] = hist[-5:]
    out["refs"] = refs

    src = orig or path
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ser = []
    for d, v in wb["Px Data"].iter_rows(min_row=5, max_col=2, values_only=True):
        if isinstance(d, dt.datetime) and _num(v) is not None:
            ser.append((d, float(v)))
    if not ser:
        raise SystemExit("model-dcf: Px Data has no closes (row 5 down, A = date, B = close).")
    ld, lv = ser[-1]
    start = ld.replace(year=ld.year - 3) if not (ld.month == 2 and ld.day == 29) else ld.replace(year=ld.year - 3, day=28)
    win = [x for x in ser if x[0] >= start]
    hi, lo_ = max(win, key=lambda x: x[1]), min(win, key=lambda x: x[1])
    f = lambda x: {"date": x[0].strftime("%Y-%m-%d"), "value": x[1]}
    out["price"] = {"last": f((ld, lv)), "high3y": f(hi), "low3y": f(lo_)}

    out["source_model"] = os.path.basename(src)
    return out


def mm_unit(mm, key):
    """The MOD row's unit (column C), e.g. '$ M', 'M persons', '%'."""
    return next((str(c or "") for i, k, c in mm.lines if k == key), "")


if __name__ == "__main__":
    ctx = build(sys.argv[1], sys.argv[3] if len(sys.argv) > 3 else None)
    json.dump(ctx, open(sys.argv[2], "w"), indent=1)
    print(f"wrote {sys.argv[2]}")
    for b in ctx["blank_as_0"]:
        print(f"warning: {b} is blank and counts as 0 (a revenue term that starts in the forecast). If it should "
              "have a value, fill it in MOD and rerun.")
