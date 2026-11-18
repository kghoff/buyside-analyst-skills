"""The pandas prototype: every number the three tabs will show, computed the way the Excel formulas compute it.

build.py takes its layout (start rows, block lengths, which years) from here, verify.py compares LibreOffice's
recalculated workbook against it, and the chart caches are filled from it. Change a rule here and in build.py together.

Rules (the user / handoff, 2026-11-08):
- Daily rows = dates where both the stock and SPY have a close. Index base = last trading day on or before
  Dec 31 of (first MOD fiscal year - 1); the first row is 252 rows before it (the beta warm-up).
- beta_t = SLOPE(stock returns, SPY returns) over the 252 rows ending at t-1. Idio = r_stock - beta * r_SPY.
- Point-in-time values: the latest full-results release dated strictly before the day (releases come after the close).
- P/E = close / TTM EPS as known that day (the user, 2026-11-17). Not NTM: the free data has no consensus history,
  and NTM on the company's later results would use EPS nobody knew at the time.
- Monthly block starts at the first month with a numeric P/E (no leading #N/A: LibreOffice draws it as 0).
- Weekly 3-factor block starts at the first week-end on or after the index base whose 252-day window has every
  factor return; LINEST of daily stock returns on [SPY, ETF - SPY, MOM - SPY] over the 252 rows ending at the prior
  week-end.
- Annual block = the last 10 reported fiscal years with a numeric FCF."""
import datetime as dt
import math

import numpy as np
import pandas as pd

import modmap

NA = float("nan")
WINDOW = 252


def isnum(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and not (isinstance(x, float) and math.isnan(x))


def load_close(path):
    s = pd.read_csv(path, parse_dates=["Date"]).set_index("Date")["Close"].dropna().astype(float)
    return s[~s.index.duplicated(keep="last")].sort_index()


def load_tr(path):
    """Total-return series: Yahoo's Adj Close (dividends in); a stooq file has only Close, which is already adjusted."""
    df = pd.read_csv(path, parse_dates=["Date"]).set_index("Date")
    s = df["Adj Close" if "Adj Close" in df.columns else "Close"].dropna().astype(float)
    return s[~s.index.duplicated(keep="last")].sort_index()


def daily_dates(stock, spy, first_fy):
    """(dates, base_index). base = last common date <= Dec 31 of first_fy - 1; start = base - 252 rows."""
    common = stock.index.intersection(spy.index).sort_values()
    base_day = pd.Timestamp(first_fy - 1, 12, 31)
    upto = common[common <= base_day]
    if len(upto) < WINDOW + 1:
        # stock history too short for the calendar base: start where it starts and base 252 rows later
        dates = common
        return dates, WINDOW
    b = len(upto) - 1
    dates = common[b - WINDOW:]
    return dates, WINDOW


def align_factor(series, dates):
    """Reindex a factor ETF onto the daily dates. Missing dates (after its first close) take the prior close.
    Returns (values, filled_dates, first_date)."""
    first = series.index.min()
    out = series.reindex(series.index.union(dates)).ffill().reindex(dates)
    out[dates < first] = NA
    have = set(series.index)
    filled = [d for d in dates if d >= first and d not in have]
    return out, filled, first


def slope(y, x):
    xm, ym = x.mean(), y.mean()
    return float(((x - xm) * (y - ym)).sum() / ((x - xm) ** 2).sum())


def linest(y, X):
    """Excel LINEST(y, X) with intercept: returns (coefs in X column order, r2)."""
    A = np.column_stack([X, np.ones(len(y))])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    fit = A @ coef
    ss_res = float(((y - fit) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return coef[:-1], 1 - ss_res / ss_tot


def asof(release_dates, values, day):
    """INDEX(values, MATCH(day-1, release_dates, 1)) wrapped in IFERROR(..., NA())."""
    k = None
    for i, d in enumerate(release_dates):
        if d <= day - pd.Timedelta(days=1):
            k = i
        else:
            break
    if k is None:
        return NA
    v = values[k]
    return v if isnum(v) else NA


def quarter_table(mod, full_dates, cfg):
    """Px Events left block, one row per reported MOD quarter. full_dates: {quarter label: Timestamp}."""
    per, V = mod["periods"], mod["values"]
    allq = modmap.quarters(per)
    labels = [p["label"] for p in allq]
    rows = []
    rq = [p for p in modmap.quarters(per, actual_only=True)]
    for k, p in enumerate(rq):
        lab = p["label"]
        i = labels.index(lab)
        prev4 = labels[i - 3:i + 1] if i >= 3 else None
        fy = modmap.fy_of(per, p["year"]) if p["q"] == 4 else None
        g = lambda role, l: V.get(role, {}).get(l)
        row = {"label": lab, "date": full_dates.get(lab), "eps_g": g("eps_gaap", lab), "eps_n": g("eps_ng", lab),
               "fy_g": g("eps_gaap", fy["label"]) if fy else None, "fy_n": g("eps_ng", fy["label"]) if fy else None}
        rows.append(row)
        for key, src, fyk in (("ttm_g", "eps_g", "fy_g"), ("ttm_n", "eps_n", "fy_n")):
            win = [r[src] for r in rows[-4:]] if k >= 3 else []
            if k >= 3 and sum(isnum(x) for x in win) == 4:
                row[key] = sum(win)
            else:
                row[key] = row[fyk] if isnum(row[fyk]) else NA
        # TTM revenue / margins / ROIC
        if prev4 and all(isnum(g("revenue", l)) for l in prev4):
            row["ttm_rev"] = sum(g("revenue", l) for l in prev4)
        else:
            row["ttm_rev"] = NA
        row["rev_g"] = (row["ttm_rev"] / rows[k - 4]["ttm_rev"] - 1) if k >= 4 and isnum(row["ttm_rev"]) and \
            isnum(rows[k - 4]["ttm_rev"]) else NA
        for key, role in (("om", cfg["oi_role"]), ("em", cfg.get("ebitda_role"))):
            if not role:
                continue
            v = NA
            if prev4 and all(isnum(g(role, l)) for l in prev4):
                v = sum(g(role, l) for l in prev4) / row["ttm_rev"] if isnum(row["ttm_rev"]) else NA
            elif fy and isnum(g(role, fy["label"])) and isnum(g("revenue", fy["label"])):
                v = g(role, fy["label"]) / g("revenue", fy["label"])
            row[key] = v
        row["roic"] = g(cfg["roic_role"], lab) if isnum(g(cfg["roic_role"], lab)) else NA
    return rows


def overlay_keys(cfg):
    return ["rev_g", "om"] + (["em"] if cfg.get("ebitda_role") else []) + ["roic"]


def run(cfg, prices, mod, full_dates, events):
    """cfg: oi_role, ebitda_role (or None), roic_role, eps_role, ttm_key ('ttm_n'|'ttm_g'), fcf_role, bb_roles.
    prices: {'stock','spy','etf','mom'} -> Series. events: [{date, name, timing}] (Timestamp dates)."""
    per = mod["periods"]
    first_fy = min(p["year"] for p in per if p["kind"] == "fy")
    dates, b = daily_dates(prices["stock"], prices["spy"], first_fy)
    n = len(dates)
    px = prices["stock"].reindex(dates).to_numpy()                      # traded price: P/E, month-end close, chart
    pt = prices.get("stock_tr", prices["stock"]).reindex(dates).to_numpy()   # total return: returns, beta, alpha
    sp = prices["spy"].reindex(dates).to_numpy()
    r = np.full(n, NA); rs = np.full(n, NA)
    r[1:] = pt[1:] / pt[:-1] - 1
    rs[1:] = sp[1:] / sp[:-1] - 1
    beta = np.full(n, NA); idio = np.full(n, NA)
    for t in range(b + 1, n):
        beta[t] = slope(r[t - WINDOW:t], rs[t - WINDOW:t])
        idio[t] = r[t] - beta[t] * rs[t]

    qt = quarter_table(mod, full_dates, cfg)
    rel = [q for q in qt if q["date"] is not None]
    rel_dates = [q["date"] for q in rel]
    okeys = overlay_keys(cfg)
    daily = {k: np.full(n, NA) for k in ["ttm_eps", "pe"] + okeys}
    for t in range(b + 1, n):
        d = dates[t]
        e = asof(rel_dates, [q[cfg["ttm_key"]] for q in rel], d)
        daily["ttm_eps"][t] = e
        daily["pe"][t] = px[t] / e if isnum(e) and e > 0 else NA
        for k in okeys:
            daily[k][t] = asof(rel_dates, [q[k] for q in rel], d)

    # event reaction days (first event wins for the daily label, as MATCH(...,0) does)
    ev = []
    pos = {d: i for i, d in enumerate(dates)}
    for e in events:
        k = int(np.searchsorted(dates.values, np.datetime64(e["date"]), side="right")) - 1
        k += 1 if e["timing"] == "After close" else 0
        day = dates[k] if 0 <= k < n else None
        ev.append({**e, "reaction": day,
                   **({"r": r[pos[day]], "rs": rs[pos[day]], "beta": beta[pos[day]], "idio": idio[pos[day]]} if day is not None else {})})
    label = [""] * n
    for e in reversed(ev):
        if e["reaction"] is not None and pos[e["reaction"]] > b:
            label[pos[e["reaction"]]] = e["name"]

    # ---- monthly ----
    first = next((t for t in range(b + 1, n) if isnum(daily["pe"][t])), None)
    months = []
    if first is not None:
        lim = pd.Timestamp(dates[first].year, dates[first].month, 1) - pd.Timedelta(days=1)   # end of the prior month
        while True:
            lim = (lim + pd.offsets.MonthEnd(1)).normalize()
            k = int(np.searchsorted(dates.values, np.datetime64(lim), side="right")) - 1
            months.append(k)
            if k == n - 1:
                break
    monthly = {"row": months, "date": [dates[k] for k in months], "close": [px[k] for k in months],
               "pe": [daily["pe"][k] for k in months],
               "ttm_eps": [daily["ttm_eps"][k] for k in months]}

    # ---- factor daily block ----
    etf, etf_filled, etf_first = align_factor(prices["etf"], dates)
    mom, mom_filled, mom_first = align_factor(prices["mom"], dates)
    ev_, mv_ = etf.to_numpy(), mom.to_numpy()
    ind_x = np.full(n, NA); mom_x = np.full(n, NA)
    ok = ~np.isnan(ev_[1:]) & ~np.isnan(ev_[:-1])
    ind_x[1:] = np.where(ok, ev_[1:] / np.where(ok, ev_[:-1], 1) - 1 - rs[1:], NA)
    ok = ~np.isnan(mv_[1:]) & ~np.isnan(mv_[:-1])
    mom_x[1:] = np.where(ok, mv_[1:] / np.where(ok, mv_[:-1], 1) - 1 - rs[1:], NA)

    # ---- weekly (Sat-Fri weeks; week-end = last trading day of the week) ----
    wk = pd.Series(range(n), index=dates).groupby(lambda d: (d + pd.Timedelta(days=(4 - d.weekday()) % 7)).normalize()).max()
    wends = [k for k in wk.to_list()]
    w0 = None
    for k in wends:
        if k < b or k - (WINDOW - 1) < 1:
            continue
        sl = slice(k - WINDOW + 1, k + 1)
        if not (np.isnan(ind_x[sl]).any() or np.isnan(mom_x[sl]).any() or np.isnan(r[sl]).any()):
            w0 = k
            break
    wrows = [k for k in wends if w0 is not None and k >= w0]
    W = {"row": wrows, "date": [dates[k] for k in wrows]}
    for key in ("ret", "spy_ret", "ind_x", "mom_x", "b_mkt", "b_ind", "b_mom", "r2", "idio3"):
        W[key] = [NA] * len(wrows)
    W["idx3"] = [100.0] + [NA] * (len(wrows) - 1)
    for j in range(1, len(wrows)):
        k, k0 = wrows[j], wrows[j - 1]
        W["ret"][j] = pt[k] / pt[k0] - 1
        W["spy_ret"][j] = sp[k] / sp[k0] - 1
        W["ind_x"][j] = ev_[k] / ev_[k0] - 1 - W["spy_ret"][j]
        W["mom_x"][j] = mv_[k] / mv_[k0] - 1 - W["spy_ret"][j]
        sl = slice(k0 - WINDOW + 1, k0 + 1)
        coef, r2 = linest(r[sl], np.column_stack([rs[sl], ind_x[sl], mom_x[sl]]))
        W["b_mkt"][j], W["b_ind"][j], W["b_mom"][j], W["r2"][j] = coef[0], coef[1], coef[2], r2
        W["idio3"][j] = (W["ret"][j] - coef[0] * W["spy_ret"][j] - coef[1] * W["ind_x"][j] - coef[2] * W["mom_x"][j])
        W["idx3"][j] = W["idx3"][j - 1] * (1 + W["idio3"][j])
    W["pct3"] = [x / 100 - 1 for x in W["idx3"]]
    for key in okeys:
        W[key] = [daily[key][k] for k in wrows]

    # ---- annual ----
    V = mod["values"]
    fys = [p for p in per if p["kind"] == "fy" and not p["est"] and isnum(V[cfg["fcf_role"]].get(p["label"]))][-10:]
    annual = {"fy": [p["year"] for p in fys], "col": [p["col"] for p in fys],
              "fcf": [V[cfg["fcf_role"]][p["label"]] for p in fys],
              "bb": [-sum((V[role].get(p["label"]) or 0) for role in cfg["bb_roles"]) for p in fys]}
    annual["pe"], annual["n"] = [], []
    fyem = cfg.get("fye_month", 12)              # month the fiscal year ends (MDT: April); December = calendar year
    fiscal = lambda d: d.year + (1 if d.month > fyem else 0)
    for y in annual["fy"]:
        xs = [v for d, v in zip(monthly["date"], monthly["pe"]) if fiscal(d) == y and isnum(v)]
        annual["pe"].append(sum(xs) / len(xs) if xs else NA)
        annual["n"].append(len(xs))

    return {"dates": dates, "base": b, "px": px, "tr": pt, "spy": sp, "r": r, "rs": rs, "beta": beta, "idio": idio,
            "daily": daily, "label": label, "quarters": qt, "events": ev, "monthly": monthly, "weekly": W,
            "annual": annual, "etf": ev_, "mom": mv_, "ind_x": ind_x, "mom_x": mom_x, "okeys": okeys,
            "fills": {"etf": etf_filled, "mom": mom_filled}, "first": {"etf": etf_first, "mom": mom_first}}


def axis_range(*arrays):
    """Right-axis min / max for the overlays: the data range rounded out to 10%; min never above 0."""
    xs = [x for a in arrays for x in a if isnum(x)]
    lo, hi = min(xs + [0.0]), max(xs)
    return math.floor(lo * 10 + 1e-9) / 10, math.ceil(hi * 10 - 1e-9) / 10
