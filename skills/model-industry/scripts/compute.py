"""Python prototype of every number on Industry P&L and Industry Comparison (the rules table in the plan / NOTES.md).
build.py writes Excel formulas that must reproduce these; verify.py checks every cell against them. Missing = None."""
import lines

AN = ("growth", "share", "gm", "om", "em", "capex_sales", "capex_da", "fcf_m", "tax_rate", "nopat", "ic", "roic",
      "d_rev", "prior_rev")


def _div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def _analysis(L, years, ind_rev=None):
    g = lambda k, y: L.get(k, {}).get(y)
    an = {k: {} for k in AN}
    for i, y in enumerate(years):
        p = years[i - 1] if i else None
        rev, prev = g("revenue", y), (g("revenue", p) if p else None)
        both = rev is not None and prev is not None
        an["d_rev"][y] = rev - prev if both else None
        an["prior_rev"][y] = prev if both else None
        an["growth"][y] = rev / prev - 1 if both and prev else None
        an["share"][y] = _div(rev, ind_rev[y]) if ind_rev else None
        an["gm"][y] = _div(g("gross_profit", y), rev)
        an["om"][y] = _div(g("oi", y), rev)
        an["em"][y] = _div(g("ebitda", y), rev)
        c = g("capex", y)
        an["capex_sales"][y] = _div(-c, rev) if c is not None else None
        an["capex_da"][y] = _div(-c, g("da", y)) if c is not None else None
        an["fcf_m"][y] = _div(g("fcf", y), rev)
        pt, tx = g("pretax", y), g("tax", y)
        an["tax_rate"][y] = (-(tx or 0) / pt) if pt is not None and pt > 0 else 0.0
        oi = g("oi", y)
        an["nopat"][y] = oi * (1 - an["tax_rate"][y]) if oi is not None else None
        an["ic"][y] = (sum(g(k, y) or 0 for k in ("cash", "receivables", "inventory", "ppe", "gwi")) - (g("payables", y) or 0)
                       if rev is not None else None)
        icp = an["ic"].get(p) if p else None
        an["roic"][y] = (an["nopat"][y] / ((icp + an["ic"][y]) / 2)
                         if an["nopat"][y] is not None and icp is not None and an["ic"][y] is not None
                         and (icp + an["ic"][y]) != 0 else None)
    return an


def _with_calc(L, years):
    out = {k: {y: L.get(k, {}).get(y) for y in years} for k in lines.INPUTS}
    for k, (a, b) in lines.CALC.items():
        out[k] = {y: (out[a][y] + out[b][y] if out[a][y] is not None and out[b][y] is not None else None) for y in years}
    return out


def run(I):
    years = I["years"]
    co = {}
    for c in I["companies"]:
        L = {k: {int(y): x["v"] for y, x in c["lines"].get(k, {}).items()} for k in lines.INPUTS}
        P = ({k: {int(y): x["v"] for y, x in c["parent"].get(k, {}).items()} for k in lines.INPUTS}
             if c.get("parent") else None)
        co[c["ticker"]] = {"lines": _with_calc(L, years), "parent": P}
    ind = {}
    for k in lines.KEYS:
        ind[k] = {}
        for y in years:
            vs = [co[t]["lines"][k][y] for t in co if co[t]["lines"][k][y] is not None]
            ind[k][y] = sum(vs) if vs else None
    for t in co:
        co[t]["an"] = _analysis(co[t]["lines"], years, ind["revenue"])
    ind_an = _analysis(ind, years)
    for y in years:
        d = [co[t]["an"]["d_rev"][y] for t in co if co[t]["an"]["d_rev"][y] is not None]
        p = [co[t]["an"]["prior_rev"][y] for t in co if co[t]["an"]["prior_rev"][y] is not None]
        ind_an["d_rev"][y] = sum(d) if d else None
        ind_an["prior_rev"][y] = sum(p) if p else None
        ind_an["growth"][y] = _div(ind_an["d_rev"][y], ind_an["prior_rev"][y])
    ind_an["count"] = {y: sum(1 for t in co if co[t]["lines"]["revenue"][y] is not None) for y in years}
    subj = I["companies"][0]["ticker"]
    ind_an["new_dollars"] = {}
    for y in years:
        dI, pI, dS = ind_an["d_rev"][y], ind_an["prior_rev"][y], co[subj]["an"]["d_rev"][y]
        ok = dI is not None and pI and dS is not None and dI > 0 and dI >= 0.01 * pI
        ind_an["new_dollars"][y] = dS / dI if ok else None
    return {"years": years, "co": co, "ind": ind, "ind_an": ind_an, "subject": subj}
