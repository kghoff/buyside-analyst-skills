"""Rating actions from Yahoo's upgrade/downgrade history, for any stock.

- Dates are New York trading days (Yahoo stamps UTC; an evening action lands on the next UTC day).
- Price targets dated before a stock split are divided by the split ratio, so they match split-adjusted closes.
- latest_by_firm(): each firm's newest action and newest target within 12 months (= covering); firms silent longer go
  to `dropped` ("may have dropped coverage").
- log(): the last 5 years, newest first. avg_pt(): for each day, the mean of each covering analyst firm's latest
  target (12-month window), the chart's average-target line."""
import math
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

from firms import ANALYST

ET = ZoneInfo("America/New_York")
KIND = {"up": "Upgrade", "down": "Downgrade", "init": "Initiation", "reit": "Reiterate"}
COVER_DAYS = 365
LOG_YEARS = 5


def day(iso):
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(ET).date()


def split_factor(d, splits):
    f = 1.0
    for s in splits:
        if date.fromisoformat(s["date"]) > d:
            f *= s["ratio"]
    return f


def actions(snap, F):
    splits = snap.get("splits") or []
    sd = sorted((date.fromisoformat(s["date"]), s["ratio"]) for s in splits)
    items = []
    for x in snap["yahoo"]["history"]:
        f = F.match(x["firm"])
        items.append((day(x["epochGradeDate"]), f["name"] if f else x["firm"], f, x))
    prev_date = {}                                   # firm -> date of its previous action
    out = []
    for d, name, f, x in sorted(items, key=lambda i: (i[1], i[0])):
        k = split_factor(d, splits)
        pf, pt = x.get("priorPriceTarget") or None, x.get("currentPriceTarget") or None
        prev = prev_date.get(name)
        prev_date[name] = d
        # Yahoo can leave the prior target in pre-split dollars on a firm's first action after a split
        r = 1.0
        for sdate, ratio in sd:
            if sdate <= d and (prev is None or sdate > prev):
                r *= ratio
        if prev is None and r != 1.0:
            r = [ratio for sdate, ratio in sd if sdate <= d][-1]
        first_after = r != 1.0 and any(sdate <= d for sdate, _ in sd)
        if first_after and pf and pt and abs(math.log((pf / r) / pt)) < abs(math.log(pf / pt)):
            pf = pf / r
        pf, pt = (round(pf / k, 4) if pf else None), (round(pt / k, 4) if pt else None)
        mech = x.get("priceTargetAction") == "Adjusts"
        kind = KIND.get(x.get("action")) or ("Maintains" if mech else
                                              "Target change" if pf and pt and abs(pt - pf) > 1e-9 else "Maintains")
        out.append({"date": d, "raw": x["firm"], "firm": name, "type": f["type"] if f else None,
                    "from": x.get("fromGrade") or "", "to": x.get("toGrade") or "", "bucket": F.bucket(x.get("toGrade") or ""),
                    "kind": kind, "pt_from": pf, "pt_to": pt, "split_adj": k != 1})
    out.sort(key=lambda a: (a["date"], a["firm"]), reverse=True)
    return out


def latest_by_firm(acts, asof):
    by = {}
    for a in acts:                                   # newest first
        if a["date"] <= asof:
            by.setdefault(a["firm"], []).append(a)
    rows, dropped = [], []
    for firm, lst in by.items():
        last = lst[0]
        if (asof - last["date"]).days > COVER_DAYS:
            dropped.append(last)
            continue
        p = next((x for x in lst if x["pt_to"] and (asof - x["date"]).days <= COVER_DAYS), None)
        rows.append({**last, "pt": p["pt_to"] if p else None, "pt_date": p["date"] if p else None})
    return rows, dropped


def split_types(rows):
    return ([r for r in rows if r["type"] in ANALYST], [r for r in rows if r["type"] in ("rating shop", "quant")],
            [r for r in rows if r["type"] is None])


def nasdaq_covering(snap, F, rows):
    """Analyst-type firms on Nasdaq's covering list that have no Yahoo action in the last 12 months (not in `rows`)."""
    names = ((snap.get("nasdaq") or {}).get("ratings") or {}).get("brokerNames") or []
    have = {r["firm"] for r in rows}
    found = {f["name"] for f in (F.match(n) for n in names) if f and f["type"] in ANALYST}
    return sorted(found - have)


def log(acts, asof):
    start = asof - timedelta(days=round(365.25 * LOG_YEARS))
    return [a for a in acts if start <= a["date"] <= asof]


def avg_pt(acts, days):
    pts = sorted((a for a in acts if a["pt_to"] and a["type"] in ANALYST), key=lambda a: a["date"])
    out = []
    for d in days:
        latest = {}
        for a in pts:
            if a["date"] > d:
                break
            latest[a["firm"]] = a
        live = [a["pt_to"] for a in latest.values() if (d - a["date"]).days <= COVER_DAYS]
        out.append(sum(live) / len(live) if live else None)
    return out
