"""The forward metrics the Valuation tab prices: NTM (MOD's first four forecast quarters), NTM+1 (quarters 5-8,
chapter 11.5) and the 3-year block (quarters 13-16, or the last full year available), each with the MOD formula
behind it so the tab's links equal what Python used. Also the annualized volatility over Px Data's last 253 closes
and revenue / operating income / EPS growth from the last actual year.

collect(model, values): model = the user's workbook (formulas), values = its recalculated copy (lo.recalc)."""
import openpyxl

import subject
import valmath
from modmap import ModMap


def _rows(mm, basis):
    """{metric: [MOD rows summed per quarter]} for every metric in valmath.METRIC, plus 'oi'."""
    R = subject.find_rows(mm)
    if basis == "ng" and "eps_ng" not in R:
        raise SystemExit("model-valuation: Px Data uses non-GAAP EPS but MOD has no 'Non-GAAP EPS, Diluted' row. Add "
                         "the row (run /model-kpis) or rebuild Px Data on the GAAP basis.")
    eps = R["eps_ng"] if basis == "ng" else R["eps_gaap"]
    ebitda = [R["ebitda_ng"]] if basis == "ng" and "ebitda_ng" in R else [R["oi"], R["da"]]
    rows = {"rev": [R["rev"]], "gp": [R["gp"]], "eps": [eps], "ebitda": ebitda, "fcf": [R["fcf"]], "oi": [R["oi"]]}
    return {k: rows[k] for k in (*valmath.METRIC.values(), "oi")}


def _block(mm, g, rows, quarters):
    """{"value", "formula", "quarters"}: the sum over the quarters of every row; NA() / None if any cell is blank."""
    cells = [(mm.col(q), r) for q in quarters for r in rows]
    refs = [f"MOD!${c}${r}" for c, r in cells]
    vals = [subject.num(g, r, c) for c, r in cells]
    f = f"IF(COUNT({','.join(refs)})={len(refs)},{'+'.join(refs)},NA())"
    return {"value": sum(vals) if all(v is not None for v in vals) else None, "formula": f, "quarters": list(quarters)}


def _vol(model):
    """{"value", "formula"}: annualized volatility of daily log returns over Px Data's last 253 closes."""
    ws = subject._wb(model)["Px Data"]
    hdr = next(ws.iter_rows(min_row=4, max_row=4, values_only=True))
    cc = next(i for i, h in enumerate(hdr) if h and str(h).endswith(" close"))      # subject.weekly's close column
    col = openpyxl.utils.get_column_letter(cc + 1)
    data = [(r, row[cc]) for r, row in enumerate(ws.iter_rows(min_row=5, max_col=cc + 1, values_only=True), 5)
            if isinstance(row[cc], (int, float)) and not isinstance(row[cc], bool)]
    if len(data) < 253:
        raise SystemExit(f"model-valuation: Px Data has {len(data)} closes; volatility needs 253. Rerun "
                         "/model-price-history.")
    last = data[-253:]
    if last[-1][0] - last[0][0] != 252:
        raise SystemExit("model-valuation: Px Data's last 253 closes are not on consecutive rows.")
    n, px = last[-1][0], f"'Px Data'!${col}$"
    f = f"STDEV(LN({px}{n - 251}:${col}${n}/{px}{n - 252}:${col}${n - 1}))*SQRT(252)"
    return {"value": valmath.annual_vol([c for _, c in last]), "formula": f}


def _growth(mm, g, rows):
    """Revenue, operating income and EPS from the last actual FY to FY+3 (or the last forecast year)."""
    fy = mm.forecast_years()
    start = str(int(fy[0][:4]) - 1)
    end = fy[min(3, len(fy)) - 1]
    years = int(end[:4]) - int(start)
    if start not in mm.labels:
        raise SystemExit(f"model-valuation: MOD has no {start} column (the last actual year, before {fy[0]}); growth "
                         "is measured from it. Rebuild the model (/model-historicals) so the year is there.")
    out = {}
    for k in ("rev", "oi", "eps"):
        r = rows[k][0]
        a, b = subject.num(g, r, mm.col(start)), subject.num(g, r, mm.col(end))
        out[k] = {"start": a, "end": b, "years": years, "start_ref": f"MOD!${mm.col(start)}${r}",
                  "end_ref": f"MOD!${mm.col(end)}${r}", "cagr": valmath.cagr(a, b, years)}
    return out


def collect(model, values):
    mm = ModMap(model)
    fq = mm.forecast_quarters()
    if len(fq) < 8:
        raise SystemExit(f"model-valuation: MOD needs at least 8 forecast quarters (NTM and NTM+1); it has {len(fq)}. "
                         "Extend the forecast (/model-forecast).")
    basis = subject.eps_basis(model)
    rows = _rows(mm, basis)
    g = subject.grid(values, max(r for rs in rows.values() for r in rs) + 5)
    Y = min(3, len(fq) // 4 - 1)
    out = {"basis": basis, "years3": Y, "vol": _vol(model), "growth": _growth(mm, g, rows)}
    for k in valmath.METRIC.values():
        out[k] = {"ntm": _block(mm, g, rows[k], fq[0:4]), "ntm1": _block(mm, g, rows[k], fq[4:8]),
                  "y3": _block(mm, g, rows[k], fq[4 * Y:4 * Y + 4])}
    return out
