# skills/model-earnings-before/scripts/checks.py
"""Section 13.5's model checks on the quarter being reported, as live formulas on MOD with their values: yoy growth
(and the quarter before's), the 2- and 3-year stacks, sequential growth against the 5-year average for that quarter,
margin against that quarter's 5-year average, incremental margin, the hockey-stick flag, and the second-half share
of the year. Also the blow-up inputs (operating-margin range, TTM net income and FCF, cash) and NTM EPS.

MOD rows are found by label within their section (as model-short and model-dcf do), so any company's MOD works.
A blank cell counts as 0 the way Excel's arithmetic reads it; a text cell is an error (None)."""
import re

from openpyxl.utils import column_index_from_string as ci

import earnmath as em

ROLES = [  # (name, section regex, label regex, required, take the last match)
    ("rev", r"^income statement:?$", r"^(total )?revenue", True, False),
    ("gp", r"^income statement:?$", r"^gross profit", False, False),
    ("oi", r"^income statement:?$", r"^operating income", True, False),
    ("ni", r"^income statement:?$", r"^net income", True, False),
    ("eps", r"^income statement:?$", r"^eps, diluted", True, False),
    ("cash", r"balance sheet|assets", r"^cash (and|&) (cash )?equivalents", False, False),
    ("fcf", r"^free cash flow", r"free cash flow$", False, True),
]
FALLBACK = {"fcf": r"."}  # no FREE CASH FLOW section: any section's last "...free cash flow" row
AVG_YEARS = 5


def grid(ws):
    g = {}
    for r, row in enumerate(ws.iter_rows(values_only=True), start=1):
        for c, v in enumerate(row, start=1):
            if v is not None:
                g[(r, c)] = v
    return g


def norm(t):
    return " ".join(t.lower().replace("(-)", "").replace("(+)", "").replace("(+/-)", "").split())


def find_rows(mm):
    lines = [(r, k.split(" | ", 1)[0].lower(), norm(re.sub(r" #\d+$", "", k.split(" | ", 1)[1])))
             for k, r in mm.keys.items()]
    out, missing = {}, []
    for name, sec, lab, req, last in ROLES:
        hits = [r for r, s, lb in lines if re.search(sec, s) and re.search(lab, lb)]
        if not hits and name in FALLBACK:
            hits = [r for r, s, lb in lines if re.search(FALLBACK[name], s) and re.search(lab, lb)]
        if hits:
            out[name] = hits[-1] if last else hits[0]
        elif req:
            missing.append(name)
    if missing:
        raise SystemExit("model-earnings-before: MOD has no row for " + ", ".join(missing) + ". It looks for them by "
                         "label within their statement section, as model-dcf does. Check the row labels in the model.")
    return out


class Cells:
    def __init__(self, mm, g):
        self.mm, self.g = mm, g

    def ref(self, p, row):
        return f"MOD!${self.mm.col(p)}${row}"

    def v(self, p, row):
        x = self.g.get((row, ci(self.mm.col(p))))
        return x if em._n(x) else None

    def v0(self, p, row):
        x = self.g.get((row, ci(self.mm.col(p))))
        return 0.0 if x is None else (x if em._n(x) else None)


def _na():
    return {"formula": "NA()", "value": None}


def _back(mm, p, years):
    try:
        for _ in range(years):
            p = mm.pyq(p)
        return p
    except StopIteration:
        return None


def _g(C, row, now, then):
    if now is None or then is None:
        return _na()
    a, b = C.ref(now, row), C.ref(then, row)
    return {"formula": f"IFERROR(IF({b}>0,{a}/{b}-1,NA()),NA())", "value": em.growth(C.v0(now, row), C.v(then, row))}


def _same_q(mm, q):
    qn = q.split()[0]
    return [p for p in mm.order if mm.is_q(p) and not p.endswith("E") and p.split()[0] == qn][-AVG_YEARS:]


def _avg(parts, vals, periods):
    if not parts:
        return _na()
    return {"formula": "IFERROR(AVERAGE(" + ",".join(parts) + "),NA())",
            "value": None if None in vals else sum(vals) / len(vals), "periods": periods}


def _avg_qoq(C, mm, row, q):
    pairs = []
    for p in _same_q(mm, q):
        try:
            pairs.append((p, mm.prev(p)))
        except ValueError:
            pass
    vals = []
    for a, b in pairs:
        r = em.div(C.v0(a, row), C.v(b, row))
        vals.append(r - 1 if r is not None else None)
    return _avg([f"{C.ref(a, row)}/{C.ref(b, row)}-1" for a, b in pairs], vals, [a for a, _ in pairs])


def _ratio(C, row, rev, p):
    return {"formula": f"IFERROR({C.ref(p, row)}/{C.ref(p, rev)},NA())", "value": em.div(C.v0(p, row), C.v(p, rev))}


def _avg_ratio(C, mm, row, rev, q):
    ps = _same_q(mm, q)
    return _avg([f"{C.ref(p, row)}/{C.ref(p, rev)}" for p in ps], [em.div(C.v0(p, row), C.v(p, rev)) for p in ps], ps)


def _incr(C, row, rev, q, y1):
    if y1 is None:
        return _na()
    dr = f"({C.ref(q, rev)}-{C.ref(y1, rev)})"
    f = f"IFERROR(IF({dr}>0,({C.ref(q, row)}-{C.ref(y1, row)})/{dr},NA()),NA())"
    a, b, c, d = C.v0(q, row), C.v0(y1, row), C.v0(q, rev), C.v0(y1, rev)
    val = (a - b) / (c - d) if None not in (a, b, c, d) and c - d > 0 else None
    return {"formula": f, "value": val}


def _h2(C, mm, rev, fy):
    def one(f):
        qs = mm.quarters_of(f)
        if len(qs) != 4 or f not in mm.labels:
            return None
        a, b = C.v0(qs[2], rev), C.v0(qs[3], rev)
        return (f"({C.ref(qs[2], rev)}+{C.ref(qs[3], rev)})/{C.ref(f, rev)}",
                em.div(a + b, C.v(f, rev)) if None not in (a, b) else None)
    now = one(fy)
    past = [p for p in mm.order if re.fullmatch(r"\d{4}", p)][-AVG_YEARS:]
    parts = [x for x in (one(p) for p in past) if x]
    return {"share": {"formula": f"IFERROR({now[0]},NA())", "value": now[1]} if now else _na(),
            "avg": _avg([f for f, _ in parts], [v for _, v in parts], past)}


def _blowup(C, mm, rows):
    act = [p for p in mm.order if mm.is_q(p) and not p.endswith("E")]
    last20, last4 = act[-20:], act[-4:]
    oi, rev = rows["oi"], rows["rev"]
    ratios = ",".join(f"{C.ref(p, oi)}/{C.ref(p, rev)}" for p in last20)
    vals = [em.div(C.v0(p, oi), C.v(p, rev)) for p in last20]
    out = {"margin_range": {"formula": f"IFERROR(MAX({ratios})-MIN({ratios}),NA())",
                            "value": None if None in vals or not vals else max(vals) - min(vals), "n": len(last20)}}

    def ttm(key):
        if key not in rows:
            return _na()
        vs = [C.v0(p, rows[key]) for p in last4]
        return {"formula": "IFERROR(SUM(" + ",".join(C.ref(p, rows[key]) for p in last4) + "),NA())",
                "value": None if None in vs else float(sum(vs))}

    out["ttm_ni"], out["ttm_fcf"] = ttm("ni"), ttm("fcf")
    out["cash"] = ({"formula": f"IFERROR({C.ref(act[-1], rows['cash'])}+0,NA())", "value": C.v0(act[-1], rows["cash"])}
                   if "cash" in rows else _na())
    return out


def run(mm, g, rows, drivers):
    C = Cells(mm, g)
    fq = mm.forecast_quarters()
    if not fq:
        raise SystemExit("model-earnings-before: MOD has no forecast quarters. Run /model-forecast first.")
    q = fq[0]
    prevq = mm.prev(q)
    metrics = [("Revenue", rows["rev"], False)]
    if "gp" in rows:
        metrics.append(("Gross profit", rows["gp"], True))
    metrics += [("Operating income", rows["oi"], True), ("EPS, diluted", rows["eps"], False)]
    metrics += [(d["name"], d["row"], False) for d in drivers]
    out = []
    for name, row, margin in metrics:
        y1, y2, y3 = (_back(mm, q, k) for k in (1, 2, 3))
        c = {"yoy": _g(C, row, q, y1), "yoy_prev": _g(C, row, prevq, _back(mm, prevq, 1)),
             "st2": _g(C, row, q, y2), "st2_prev": _g(C, row, prevq, _back(mm, prevq, 2)),
             "st3": _g(C, row, q, y3), "qoq": _g(C, row, q, prevq), "qoq_avg": _avg_qoq(C, mm, row, q)}
        if margin:
            c["margin"] = _ratio(C, row, rows["rev"], q)
            c["margin_avg"] = _avg_ratio(C, mm, row, rows["rev"], q)
            c["incr"] = _incr(C, row, rows["rev"], q, y1)
        c["hockey"] = em.flag_text(em.hockey(*(c[k]["value"] for k in ("yoy", "yoy_prev", "st2", "st2_prev",
                                                                         "qoq", "qoq_avg"))))
        out.append({"name": name, "row": row, "cells": c})
    ntm = fq[:4]
    ev = [C.v0(p, rows["eps"]) for p in ntm]
    ntm_eps = ({"formula": "IFERROR(SUM(" + ",".join(C.ref(p, rows["eps"]) for p in ntm) + "),NA())",
                "value": None if None in ev else float(sum(ev))} if len(ntm) == 4 else _na())
    return {"quarter": q, "fy": mm.fy_of(q), "prev": prevq, "metrics": out, "h2": _h2(C, mm, rows["rev"], mm.fy_of(q)),
            "blowup": _blowup(C, mm, rows),
            "ntm_eps": {**ntm_eps, "periods": ntm}}
