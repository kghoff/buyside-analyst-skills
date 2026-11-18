"""Comp-sheet rows (spec §3.3 item 5) from fetch_comps.mjs snapshots. Raw Yahoo values are kept as printed
(dollars); the tab shows them in millions by number format, so no typed number is rescaled."""
import statistics

from multiples import ratio

KEYS = ("pe0", "pe1", "ev_rev0", "ev_rev1", "ev_ebitda", "growth1")


def _trend(s, period):
    return next((t for t in s.get("trend", []) if t.get("period") == period), {})


def row(s, group):
    r = {"ticker": s["ticker"], "group": group, "asof": s.get("asof"), "warning": None, "ccy_mismatch": False}
    if s.get("error"):
        return {**r, **{k: None for k in KEYS}, "warning": f"Yahoo fetch failed: {s['error']}"}
    f = s.get("financial", {})
    t0, t1 = _trend(s, "0y"), _trend(s, "+1y")
    r.update(price=s.get("price"), mcap=s.get("marketCap"), debt=f.get("totalDebt") or 0, cash=f.get("totalCash") or 0,
             adv=s.get("adv3m"), ebitda=f.get("ebitda"),
             eps0=(t0.get("earningsEstimate") or {}).get("avg"), eps1=(t1.get("earningsEstimate") or {}).get("avg"),
             rev0=(t0.get("revenueEstimate") or {}).get("avg"), rev1=(t1.get("revenueEstimate") or {}).get("avg"),
             fy0=int(t0["endDate"][:4]) if t0.get("endDate") else None,
             fy1=int(t1["endDate"][:4]) if t1.get("endDate") else None)
    r["ev"] = r["mcap"] + r["debt"] - r["cash"] if r["mcap"] is not None else None
    r["pe0"], r["pe1"] = ratio(r["price"], r["eps0"]), ratio(r["price"], r["eps1"])
    same_ccy = f.get("financialCurrency") in (None, s.get("currency"))
    warns = []
    if not same_ccy:
        r["ccy_mismatch"] = True
        warns.append(f"financials in {f.get('financialCurrency')}, price in {s.get('currency')}: EV multiples "
                     "left NM")
    if f.get("financialCurrency") is None:
        warns.append("financial currency not reported; assumed same as price")
    if f.get("totalDebt") is None:
        warns.append("total debt not reported; EV assumes 0")
    r["warning"] = "; ".join(warns) or None
    r["ev_rev0"] = ratio(r["ev"], r["rev0"]) if same_ccy else None
    r["ev_rev1"] = ratio(r["ev"], r["rev1"]) if same_ccy else None
    r["ev_ebitda"] = ratio(r["ev"], r["ebitda"]) if same_ccy else None
    r["growth1"] = (r["rev1"] / r["rev0"] - 1) if r["rev0"] and r["rev0"] > 0 and r["rev1"] is not None else None
    return r


def rank(rows):
    """Most expensive first on next year's P/E (the comp sheet's ranking); NM last."""
    return sorted(rows, key=lambda r: (r["pe1"] is None, -(r["pe1"] or 0)))


def included(r, inc):
    """inc: {ticker: 0 | 1} from the tab's Include? column (the user's toggle); a ticker not in it is included."""
    return inc.get(r["ticker"], 1) == 1


def stats(rows, inc=None):
    """Average and median of each comp column over the included rows (the tab's array formulas do the same)."""
    out = {"average": {}, "median": {}}
    for k in KEYS:
        v = [r[k] for r in rows if r.get(k) is not None and included(r, inc or {})]
        out["average"][k] = sum(v) / len(v) if v else None
        out["median"][k] = statistics.median(v) if v else None
    return out


SAYS_NOTHING = ("The line says nothing here: fewer than 3 included peers have both numbers, or the line does not "
                "slope up")
BELOW = "Below the line: structurally underpriced on the multiple (cheaper than its growth earns its peers)"
ABOVE = "Above the line: the multiple already pays for more growth than its peers get paid for"


def line_fit(rows, inc, subject):
    """Least-squares line of next-year P/E on next-year revenue growth through the included peers (never the
    subject), and where the subject sits against it (chapter 11, "Applying P/E multiples"). The tab computes the same
    with array formulas. Fewer than 3 points, or a line that does not slope up, gives no reading: two points always
    fit exactly, and a downward line would call the fastest grower cheap for the wrong reason."""
    pts = [(r["growth1"], r["pe1"]) for r in rows if r["ticker"] != subject and included(r, inc)
           and r.get("growth1") is not None and r.get("pe1") is not None]
    n = len(pts)
    out = {"n": n, "slope": None, "intercept": None, "fair_pe": None, "gap": None, "implied_growth": None,
           "reading": SAYS_NOTHING}
    sx, sy = sum(x for x, _ in pts), sum(y for _, y in pts)
    sxx, sxy = sum(x * x for x, _ in pts), sum(x * y for x, y in pts)
    den = n * sxx - sx * sx
    if n < 2 or den == 0:
        return out
    out["slope"] = (n * sxy - sx * sy) / den
    out["intercept"] = (sy - out["slope"] * sx) / n
    s = next((r for r in rows if r["ticker"] == subject), {})
    if n < 3 or not out["slope"] > 0 or s.get("growth1") is None or s.get("pe1") is None:
        return out
    out["fair_pe"] = out["intercept"] + out["slope"] * s["growth1"]
    out["gap"] = s["pe1"] - out["fair_pe"]
    out["implied_growth"] = (s["pe1"] - out["intercept"]) / out["slope"]
    out["reading"] = BELOW if out["gap"] < 0 else ABOVE
    return out


def outliers(rows, subject, times=2.0):
    """Peers whose next-year P/E is more than `times` the peers' median: flagged for the user, never left out."""
    pe = [r["pe1"] for r in rows if r["ticker"] != subject and r.get("pe1") is not None]
    if len(pe) < 3:
        return []
    med = statistics.median(pe)
    return [r["ticker"] for r in rows if r["ticker"] != subject and r.get("pe1") is not None and r["pe1"] > times * med]
