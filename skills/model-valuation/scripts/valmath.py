# scripts/valmath.py
"""Chapter 11's valuation math, pure functions. build.py writes the same math as Excel formulas; verify.py compares
the recalculated tab with these. Multiples: pe, ev_rev, ev_gp, ev_ebitda (x), fcf_yield (a yield, e.g. 0.04).
Metrics: eps per share; rev, gp, ebitda, fcf in $M; net_debt $M; shares M."""
import math
import statistics

METRIC = {"pe": "eps", "fcf_yield": "fcf", "ev_rev": "rev", "ev_gp": "gp", "ev_ebitda": "ebitda"}
LEVERED = {"pe", "fcf_yield"}           # paired with equity value; the rest with EV (chapter 11.2)
DOUBLE = math.log(2) / 3                # a 3-year double is a 26% IRR


def price_from_multiple(kind, mult, metric, net_debt=0.0, shares=1.0):
    if kind == "pe":
        return mult * metric
    if kind == "fcf_yield":
        return metric / shares / mult
    return (mult * metric - net_debt) / shares


def multiple_now(kind, price, metric, net_debt=0.0, shares=1.0):
    if kind == "pe":
        return price / metric
    if kind == "fcf_yield":
        return metric / (price * shares)
    return (price * shares + net_debt) / metric


def reward_risk(price, reward_px, risk_px, short=False):
    """(reward %, risk % as a positive number, R/R). A short gains toward the risk price and loses toward the reward."""
    up, down = ((price - risk_px) / price, (reward_px - price) / price) if short else \
        (reward_px / price - 1, 1 - risk_px / price)
    return up, down, (up / down if down > 0 else None)


def ladder(reward_px, risk_px, price=None, entries=None, short=False):
    entries = entries or [price * (1 + s / 100) for s in (-15, -10, -5, 0, 5, 10, 15)]
    return [(e, *reward_risk(e, reward_px, risk_px, short)) for e in entries]


def irr(p0, p1, years):
    return (p1 / p0) ** (1 / years) - 1


def irr_split(m0, m1, x0, x1, years):
    """IRR on P/E x EPS, split into the roll-forward (metric growth) and re-rating (multiple change), chapter 11.6."""
    return {"irr": irr(m0 * x0, m1 * x1, years), "growth": irr(m0, m1, years), "rerate": irr(x0, x1, years)}


def double_path(x0, x1, m0, m1):
    """Which route to a 3-year double: by the share of the log price change that comes from the multiple."""
    total = math.log((x1 * m1) / (x0 * m0))
    if total <= 0:
        return "no double path (price falls)"
    share = math.log(x1 / x0) / total
    return "P/E expansion" if share >= 2 / 3 else "EPS growth" if share <= 1 / 3 else "both"


def normalized(mult, eps, rate, years):
    p = mult * eps
    return p, p / (1 + rate) ** years


def reverse_pe(price, pe):
    return price / pe


def tree(rows, price):
    if abs(sum(p for _, p in rows) - 1) > 1e-9:
        raise ValueError("probabilities must sum to 100%")
    ev = sum(t * p for t, p in rows)
    return ev, ev / price - 1


def reward_to_vol(up, vol):
    return up / vol


def inside_one_sigma(down, vol, months):
    return down < vol * math.sqrt(months / 12)


def verdict(rr, buy, pound):
    return "table-pound" if rr >= pound else "buy" if rr >= buy else "below hurdle"


def annual_vol(closes):
    """Sample stdev of daily log returns over the closes given (build uses the last 253), annualized by sqrt(252)."""
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:])]
    return statistics.stdev(rets) * math.sqrt(252)


def cagr(a, b, years):
    return (b / a) ** (1 / years) - 1 if a and b and a > 0 and b > 0 else None


def gap(dcf, target, limit=0.25):
    return abs(dcf / target - 1) > limit
