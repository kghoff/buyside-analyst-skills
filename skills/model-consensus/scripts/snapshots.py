"""Consensus from a snapshot: the broker table's consensus rows, the dated rows of the snapshot block, and what moved
since the last snapshot. Free sources only show today's consensus, so each run's snapshot file is what builds the
history. Revenue in $ millions; EPS per share; labels in the company's fiscal calendar."""
import calendar
import glob
import json
import os
from datetime import date

import periods

CODES = {"q": "0q", "fy": "0y", "fy1": "+1y"}
MONTHS = {m: i for i, m in enumerate(calendar.month_abbr) if m}


def load_all(work):
    return sorted((json.load(open(p)) for p in glob.glob(os.path.join(work, "snapshots", "*.json"))),
                  key=lambda s: s["asof"])


def num(x):
    if x is None or x == "":
        return None
    if isinstance(x, (int, float)):
        return float(x)
    t = str(x).replace("$", "").replace(",", "").strip()
    if t.startswith("(") and t.endswith(")"):
        t = "-" + t[1:-1].strip()
    try:
        return float(t)
    except ValueError:
        return None


def _label(t, fye):
    d = periods.end_date(t["endDate"])
    return periods.qlabel(d, fye) if t["period"].endswith("q") else periods.fylabel(d, fye)


def _est(e, scale=1.0):
    e = e or {}
    g = lambda k: num(e.get(k)) / scale if num(e.get(k)) is not None else None
    return {"mean": g("avg"), "low": g("low"), "high": g("high"), "n": e.get("numberOfAnalysts")}


def consensus(snap, fye):
    tr = {t["period"]: t for t in snap["yahoo"]["trend"] if t.get("endDate")}
    fin = snap["yahoo"].get("financial") or {}
    out = {"labels": {}, "ends": {}, "eps": {}, "rev": {},
           "pt": {"mean": fin.get("targetMeanPrice"), "high": fin.get("targetHighPrice"), "low": fin.get("targetLowPrice"),
                  "n": fin.get("numberOfAnalystOpinions")}}
    for k, code in CODES.items():
        t = tr.get(code)
        out["labels"][k] = _label(t, fye) if t and fye else None
        out["ends"][k] = periods.end_date(t["endDate"]).isoformat() if t else None
        out["eps"][k] = _est(t.get("earningsEstimate")) if t else _est(None)
        out["rev"][k] = _est(t.get("revenueEstimate"), 1e6) if t else _est(None)
    return out


def _counts(snap):
    r = next((x for x in snap["yahoo"].get("recommendation") or [] if x.get("period") == "0m"), None)
    if not r:
        return None, None, None
    return r.get("strongBuy", 0) + r.get("buy", 0), r.get("hold", 0), r.get("sell", 0) + r.get("strongSell", 0)


def _month_end(s):
    mon, yr = s.split()
    y, m = int(yr), MONTHS[mon[:3].title()]
    return date(y, m, calendar.monthrange(y, m)[1])


def rows(snap, fye):
    buy, hold, sell = _counts(snap)
    pt = (snap["yahoo"].get("financial") or {}).get("targetMeanPrice")
    out = []
    for t in snap["yahoo"]["trend"]:
        if not t.get("endDate") or not fye or t["period"] not in ("0q", "+1q", "0y", "+1y"):
            continue
        e, r = _est(t.get("earningsEstimate")), _est(t.get("revenueEstimate"), 1e6)
        rv = t.get("epsRevisions") or {}
        lab = _label(t, fye)
        if lab in {r["period"] for r in out}:        # Yahoo's +1q can share 0q's endDate
            continue
        out.append({"asof": snap["asof"], "period": lab, "eps_mean": e["mean"], "eps_low": e["low"],
                    "eps_high": e["high"], "eps_n": e["n"], "rev_mean": r["mean"], "rev_low": r["low"], "rev_high": r["high"],
                    "rev_n": r["n"], "up30": rv.get("upLast30days"), "down30": rv.get("downLast30days"), "mean_pt": pt,
                    "buy": buy, "hold": hold, "sell": sell, "source": "Yahoo"})
    have = {r["period"] for r in out}
    fc = (snap.get("nasdaq") or {}).get("forecast") or {}
    for key, lab in (("quarterlyForecast", periods.qlabel), ("yearlyForecast", periods.fylabel)):
        for x in (fc.get(key) or {}).get("rows") or []:
            try:
                p = lab(_month_end(x["fiscalEnd"]), fye) if fye else None
            except (KeyError, ValueError):
                continue
            if not p or p in have:
                continue
            have.add(p)
            out.append({"asof": snap["asof"], "period": p, "eps_mean": num(x.get("consensusEPSForecast")),
                        "eps_low": num(x.get("lowEPSForecast")), "eps_high": num(x.get("highEPSForecast")),
                        "eps_n": x.get("noOfEstimates"), "rev_mean": None, "rev_low": None, "rev_high": None, "rev_n": None,
                        "up30": x.get("up"), "down30": x.get("down"), "mean_pt": None, "buy": None, "hold": None,
                        "sell": None, "source": "Nasdaq (Zacks)"})
    return out


def changes(prev, cur, fye):
    """Plain-English lines: consensus moves by period and the mean target, since the previous snapshot."""
    p = {r["period"]: r for r in rows(prev, fye) if r["source"] == "Yahoo"}
    out = []
    for r in rows(cur, fye):
        o = p.get(r["period"])
        if not o or r["source"] != "Yahoo":
            continue
        for k, name, f in (("eps_mean", "EPS", "{:.2f}"), ("rev_mean", "revenue ($M)", "{:,.0f}")):
            if o[k] is not None and r[k] is not None and abs(r[k] - o[k]) > 1e-9:
                pct = f" ({r[k] / o[k] - 1:+.1%})" if o[k] else ""
                out.append(f"{r['period']} {name}: {f.format(o[k])} → {f.format(r[k])}{pct} since {prev['asof']}")
    a = (prev["yahoo"].get("financial") or {}).get("targetMeanPrice")
    b = (cur["yahoo"].get("financial") or {}).get("targetMeanPrice")
    if a and b and abs(a - b) > 1e-9:
        out.append(f"mean price target: {a:.2f} → {b:.2f} since {prev['asof']}")
    return out
