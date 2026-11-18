# skills/model-earnings-before/scripts/rates.py
"""Base rates from the user's price tabs (section 13.6): the last 12 earnings prints in Px Events (day move, idio
move) with the run-up into each (T-8 to T-1 close) and the drift after it (reaction-day close to 7 trading days
later) from Px Data closes; the daily sigma over the last 252 days; the stock against SPY since the last print; and
the next report date estimated from last year's. Columns are found by their header text, so a moved column still
reads right."""
import datetime as dt
import statistics

from openpyxl.utils import get_column_letter as L

import earnmath as em

N_PRINTS, RUN, DRIFT, VOL_DAYS = 12, 7, 7, 252


def _day(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str):
        try:
            return dt.date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def _header(g, wanted, max_row=10):
    """(row, {header text: column}) of the first row up to max_row holding `wanted`."""
    for r in range(1, max_row + 1):
        heads = {str(v).strip(): c for (rr, c), v in g.items() if rr == r and isinstance(v, str)}
        if wanted in heads:
            return r, heads
    return None, {}


def px_data(g, ticker):
    r0, h = _header(g, "Date")
    need = {"date": "Date", "close": f"{ticker} close", "spy": "SPY close", "ret": f"{ticker} daily return"}
    miss = [t for t in need.values() if t not in h]
    if r0 is None or miss:
        raise SystemExit("model-earnings-before: Px Data has no " + ", ".join(miss or ["Date"]) +
                         " column. Rerun /model-price-history.")
    c = {k: h[t] for k, t in need.items()}
    rows, r = [], r0 + 1
    while (d := _day(g.get((r, c["date"])))) is not None:
        rows.append({"row": r, "date": d, "close": g.get((r, c["close"])), "spy": g.get((r, c["spy"])),
                     "ret": g.get((r, c["ret"]))})
        r += 1
    if not rows:
        raise SystemExit("model-earnings-before: Px Data has no closes. Rerun /model-price-history.")
    return {"cols": {k: L(v) for k, v in c.items()}, "first": rows[0]["row"], "last": rows[-1]["row"], "rows": rows}


def rng(P, k):
    col = P["cols"][k]
    return f"'Px Data'!${col}${P['first']}:${col}${P['last']}"


def prints(g, P, ticker):
    hr, h = _header(g, "Idio % chg")
    need = ("Type", "Reaction day", f"{ticker} % chg", "Idio % chg")
    if hr is None or any(x not in h for x in need):
        raise SystemExit("model-earnings-before: Px Events has no " + ", ".join(x for x in need if x not in h) +
                         " column. Rerun /model-price-history.")
    ct, cr, cm, ci_ = (h[x] for x in need)
    idx = {x["date"]: i for i, x in enumerate(P["rows"])}
    cl = [x["close"] for x in P["rows"]]
    out = []
    for r in range(hr + 1, max(rr for rr, _ in g) + 1):
        t, d = g.get((r, ct)), _day(g.get((r, cr)))
        if not (isinstance(t, str) and t.lower().startswith("earn") and d in idx):
            continue
        i = idx[d]
        out.append({"row": r, "date": d.isoformat(), "move": g.get((r, cm)), "idio": g.get((r, ci_)),
                    "refs": {"date": f"'Px Events'!${L(cr)}${r}", "move": f"'Px Events'!${L(cm)}${r}",
                             "idio": f"'Px Events'!${L(ci_)}${r}"},
                    "run_up": em.growth(cl[i - 1], cl[i - 1 - RUN]) if i - 1 - RUN >= 0 else None,
                    "drift": em.growth(cl[i + DRIFT], cl[i]) if i + DRIFT < len(cl) else None})
    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:N_PRINTS]


def vol(P):
    rows = [x for x in P["rows"] if em._n(x["ret"])][-VOL_DAYS:]
    if len(rows) < 20:
        return {"formula": "NA()", "value": None, "n": len(rows)}
    col = P["cols"]["ret"]
    return {"formula": f"IFERROR(STDEV('Px Data'!${col}${rows[0]['row']}:${col}${rows[-1]['row']}),NA())",
            "value": statistics.stdev(x["ret"] for x in rows), "n": len(rows)}


def rel_since(P, last):
    """The stock against SPY from the last print's reaction-day close to the latest close."""
    if not last:
        return {"formula": "NA()", "value": None}
    a = next(x for x in P["rows"] if x["date"].isoformat() == last["date"])
    b = P["rows"][-1]
    c, s = P["cols"]["close"], P["cols"]["spy"]
    stock, spy = em.growth(b["close"], a["close"]), em.growth(b["spy"], a["spy"])
    f = (f"IFERROR(('Px Data'!${c}${b['row']}/'Px Data'!${c}${a['row']}-1)-"
         f"('Px Data'!${s}${b['row']}/'Px Data'!${s}${a['row']}-1),NA())")
    return {"formula": f, "value": stock - spy if None not in (stock, spy) else None,
            "from": last["date"], "to": b["date"].isoformat()}


def next_date(g, quarter):
    """Last year's full-results release date for the same quarter plus 364 days (52 weeks: the same weekday)."""
    hr, h = _header(g, "Full-results release date")
    if hr is None or "Period" not in h:
        return None
    n, yy = quarter.rstrip("E").split()
    want = f"{n} {int(yy) - 1:02d}"
    cp, cd = h["Period"], h["Full-results release date"]
    for r in range(hr + 1, max(rr for rr, _ in g) + 1):
        if str(g.get((r, cp)) or "").strip().rstrip("E") == want and (d := _day(g.get((r, cd)))):
            return {"value": (d + dt.timedelta(days=364)).isoformat(), "base": d.isoformat(),
                    "from": f"'Px Events'!${L(cd)}${r}"}
    return None
