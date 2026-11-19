# skills/model-summary/scripts/links.py
"""Every cell SUM links to, found by its label on the source tab, never by another skill's work files (they go
stale): DCF (the cap-table bridge), Valuation (verdict, house inputs, the primary multiple's block, blended R/R, the
R/R ladder, the 3-year IRR, the probability tree), Multiples (ranges, the forward table's Street EPS, the comp
sheet's subject 3M ADV) and MOD (rows by label within their section, FY columns, the first four forecast quarters).
A missing piece stops the build and names the skill to rerun. Reads formulas only (no recalculation needed).

collect(model) -> {"dcf", "val", "mult", "mod"} of sheet-qualified refs ('Valuation!$B$39') and labels."""
import re

import openpyxl
from openpyxl.utils import get_column_letter as L

import modrows
from modmap import ModMap

NEED = {"MOD": "model-historicals", "Px Data": "model-price-history", "DCF": "model-dcf",
        "Multiples": "model-multiples", "Valuation": "model-valuation"}
BIG = 10 ** 9


def stop(what, skill):
    raise SystemExit(f"model-summary: {what} not found. Rerun /{skill}, then /model-summary.")


def grid(ws):
    return {(r, c): v for r, row in enumerate(ws.iter_rows(values_only=True), 1)
            for c, v in enumerate(row, 1) if v is not None}


def labels(g, col=1):
    return sorted((r, str(v).strip()) for (r, c), v in g.items() if c == col and isinstance(v, str))


def first(rows, test, after=0, before=BIG):
    return next((r for r, t in rows if after < r < before and test(t)), None)


def ref(tab, col, row):
    t = f"'{tab}'" if " " in tab else tab
    return f"{t}!${col}${row}"


def dcf(g):
    b = labels(g, 2)
    out = {}
    for key, prefix in (("cash", "Cash & equivalents"), ("st", "Short-term marketable securities"),
                        ("debt_cur", "Current debt"), ("debt_lt", "Long-term debt"), ("net_debt", "Net debt"),
                        ("shares", "Diluted shares, M"), ("price", "Price (last close")):
        r = first(b, lambda t: t.startswith(prefix))
        if r is None:
            stop(f"DCF row '{prefix}'", "model-dcf")
        out[key] = ref("DCF", "C", r)
        if key == "price":
            out["date"] = ref("DCF", "D", r)
    return out


def valuation(g):
    a = labels(g)
    V = lambda col, r: ref("Valuation", col, r)       # noqa: E731

    def row(test, what, after=0, before=BIG):
        r = first(a, test, after, before)
        if r is None:
            stop(f"Valuation row '{what}'", "model-valuation")
        return r

    out = {"action": V("B", row(lambda t: t.startswith("Overall verdict"), "Overall verdict")),
           "hurdle": V("B", row(lambda t: t == "IRR hurdle", "IRR hurdle")),
           "buy_rr": V("B", row(lambda t: t == "Buy at R/R", "Buy at R/R")),
           "blended_rr": V("B", row(lambda t: t == "Blended reward / risk", "Blended reward / risk"))}
    s1 = row(lambda t: t.startswith("1. Which multiples"), "1. Which multiples and why")
    e1 = row(lambda t: t == "Weights sum", "Weights sum", s1)
    kind = next((t for r, t in a if s1 < r < e1 and g.get((r, 2)) == "primary"), None)
    if kind is None:
        stop("Valuation's primary multiple", "model-valuation")
    out["kind"] = kind

    hdr = row(lambda t: t == f"{kind} (primary)", f"{kind} (primary)")
    blk, r = {}, hdr + 1
    while isinstance(g.get((r, 1)), str) and g[(r, 1)].startswith(kind):
        blk[g[(r, 1)].strip()[len(kind):].lstrip(": ").strip()] = r
        r += 1

    def pick(test, what):
        k = next((k for k in blk if test(k)), None)
        if k is None:
            stop(f"Valuation row '{kind}: {what}'", "model-valuation")
        return k
    keys = {"ntm1": pick(lambda k: k.startswith("NTM+1 "), "NTM+1 ..."),
            "reward_mult": pick(lambda k: k.startswith("reward multiple"), "reward multiple"),
            "reward_price": pick(lambda k: k == "reward price", "reward price"),
            "risk_metric": pick(lambda k: k.startswith("risk ") and k not in ("risk multiple", "risk price", "risk %"),
                                "risk <metric>"),
            "risk_mult": pick(lambda k: k == "risk multiple", "risk multiple"),
            "risk_price": pick(lambda k: k == "risk price", "risk price")}
    out["primary"] = {n: {"ref": V("B", blk[k]), "label": f"{kind}: {k}", "row": blk[k]} for n, k in keys.items()}

    h4c = row(lambda t: t.startswith("4c. Reward / risk ladder"), "4c. Reward / risk ladder")
    lad, r = [], h4c + 1
    while isinstance(g.get((r, 1)), (int, float)):
        lad.append({"move": V("A", r), "entry": V("B", r), "reward": V("C", r), "risk": V("D", r), "rr": V("E", r)})
        r += 1
    if not lad:
        stop("rungs under '4c. Reward / risk ladder'", "model-valuation")
    out["ladder"] = lad

    h5 = row(lambda t: t.startswith("5. ") and "IRR" in t, "5. N-year IRR")
    e5 = first(a, lambda t: t.startswith("6. "), h5) or BIG
    irr = {"metric3": row(lambda t: bool(re.match(r"^IRR: .+ in \d+ years \(", t)), "IRR: <metric> in N years", h5, e5),
           "years": row(lambda t: t == "IRR: years", "IRR: years", h5, e5),
           "mult3": row(lambda t: t.endswith("-year horizon"), "<multiple> at the N-year horizon", h5, e5),
           "price3": row(lambda t: t.startswith("IRR: price in"), "IRR: price in N years", h5, e5),
           "irr": row(lambda t: t == "IRR", "IRR", h5, e5)}
    lab = dict(a)
    out["irr"] = {k: {"ref": V("B", r), "label": lab[r]} for k, r in irr.items()}

    h7 = row(lambda t: t.startswith("7. Probability tree"), "7. Probability tree")
    ev = row(lambda t: t == "Probability-weighted", "Probability-weighted", h7)
    rp, kp = out["primary"]["reward_price"]["row"], out["primary"]["risk_price"]["row"]
    tree = []
    for r, name in a:
        if h7 < r < ev:
            f = str(g.get((r, 2), "")).replace("$", "")
            case = "reward" if f == f"=B{rp}" else ("risk" if f == f"=B{kp}" else None)
            tree.append({"name": name, "target": V("B", r), "ret": V("C", r), "prob": V("D", r), "case": case})
    out["tree"] = tree
    out["tree_ev"] = {"target": V("B", ev), "ret": V("C", ev), "prob": V("D", ev)}
    return out


def multiples(g, kind):
    a = labels(g)
    M = lambda col, r: ref("Multiples", col, r)       # noqa: E731
    hdr = first(a, lambda t: t == "Metric")
    if hdr is None:
        stop("the Multiples ranges table ('Metric' header)", "model-multiples")
    heads = {str(v).strip(): c for (r, c), v in g.items() if r == hdr and isinstance(v, str)}
    ranges = {}
    for key, test in (("abs", lambda t: t == kind), ("sp", lambda t: "S&P 500" in t),
                      ("peer", lambda t: "core-peer median" in t)):
        r = first(a, test, hdr, hdr + 20)
        if r is None:
            ranges[key] = None
            continue
        cells = {h: M(L(heads[h]), r) for h in heads if h != "Metric"}
        ranges[key] = {"label": dict(a)[r], "today": cells.get("Today"),
                       **{f"{y} {s}": cells.get(f"{y} {s}") for y in ("1 year", "5 years", "10 years")
                          for s in ("min", "median", "max")}}
    street = {}
    fwd = first(a, lambda t: t.startswith("FORWARD"))
    srow = first(a, lambda t: t.startswith("Street EPS"), fwd or 0) if fwd else None
    if srow:
        for (r, c), v in g.items():
            if r == fwd + 1 and c > 1 and isinstance(g.get((srow, c)), (int, float)):
                street[str(v).strip()] = M(L(c), srow)
    adv = None
    th = first(a, lambda t: t == "Ticker")
    if th:
        ac = next((c for (r, c), v in g.items() if r == th and isinstance(v, str) and v.startswith("3M ADV")), None)
        sr = next((r for (r, c), v in g.items() if c == 2 and r > th and v == "Subject"), None)
        if ac and sr and isinstance(g.get((sr, ac)), (int, float)):
            adv = M(L(ac), sr)
    return {"ranges": ranges, "street": street, "adv": adv}


def mod(model):
    mm = ModMap(model)
    R = modrows.find_rows(mm)
    basis = modrows.eps_basis(model)
    if basis == "ng" and "eps_ng" not in R:
        stop("MOD's 'Non-GAAP EPS, Diluted' row (Px Data's P/E is non-GAAP)", "model-kpis")
    eps = R["eps_ng"] if basis == "ng" else R["eps_gaap"]
    ebitda = [R["ebitda_ng"]] if basis == "ng" and "ebitda_ng" in R else [R["oi"], R["da"]]
    actual = [p for p in mm.order if re.fullmatch(r"\d{4}", p)][-4:]
    years = actual + mm.forecast_years()
    fq = mm.forecast_quarters()[:4]
    if len(fq) < 4:
        stop("four forecast quarters in MOD", "model-forecast")
    prev = {}
    for y in years:
        n = int(y[:4]) - 1
        prev[y] = next((p for p in (f"{n}E", str(n)) if p in mm.labels), None)
    col = {p: mm.col(p) for p in set(years) | {p for p in prev.values() if p}}
    refs = [f"MOD!${mm.col(q)}${R['fcf']}" for q in fq]
    return {"years": years, "n_actual": len(actual), "col": col, "prev": prev, "basis": basis,
            "rows": {"rev": R["rev"], "gp": R.get("gp"), "ebitda": ebitda, "eps": eps, "fcf": R["fcf"]},
            "ntm_fcf": f"IF(COUNT({','.join(refs)})=4,{'+'.join(refs)},NA())", "ntm_quarters": [fq[0], fq[-1]]}


def collect(model):
    wb = openpyxl.load_workbook(model, read_only=True)
    for tab, skill in NEED.items():
        if tab not in wb.sheetnames:
            stop(f"the {tab} tab", skill)
    v = valuation(grid(wb["Valuation"]))
    return {"dcf": dcf(grid(wb["DCF"])), "val": v, "mult": multiples(grid(wb["Multiples"]), v["kind"]),
            "mod": mod(model)}
