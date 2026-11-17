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


def stats(rows):
    out = {"average": {}, "median": {}}
    for k in KEYS:
        v = [r[k] for r in rows if r.get(k) is not None]
        out["average"][k] = sum(v) / len(v) if v else None
        out["median"][k] = statistics.median(v) if v else None
    return out
