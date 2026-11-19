# scripts/aftermath.py
"""All of model-earnings-after's math. The tab's formulas compute the same things; verify.py proves they agree."""
import math

FADE_CUTS = (0.0, -0.05, -0.10, -0.15, -0.20, -0.25, -0.30)
YEARS = 3
TREND_YEARS = 3


def _n(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def growth(now, then):
    """now / then - 1 over a positive base (growth off a loss or a zero reads backwards)."""
    return now / then - 1 if _n(now) and _n(then) and then > 0 else None


def surprise(actual, frozen):
    """(actual - frozen) / |frozen|: a cost stored negative that comes in smaller is a positive surprise."""
    return (actual - frozen) / abs(frozen) if _n(actual) and _n(frozen) and frozen != 0 else None


def result(s, band):
    if not _n(s) or not _n(band):
        return None
    return "in line" if abs(s) <= band else ("beat" if s > 0 else "miss")


def daily_sigma(annual):
    return annual / math.sqrt(252) if _n(annual) else None


def sigmas(move, daily):
    return move / daily if _n(move) and _n(daily) and daily else None


def irr(now, later, years=YEARS):
    if not (_n(now) and _n(later) and now > 0 and later > 0 and years):
        return None
    return (later / now) ** (1 / years) - 1


def fade_table(price, later, years=YEARS):
    return [{"cut": c, "price": price * (1 + c), "later": later, "irr": irr(price * (1 + c), later, years)}
            for c in FADE_CUTS]


def trend(by_year, now_year, k=TREND_YEARS):
    a, b = by_year.get(now_year), by_year.get(now_year - k)
    return (a - b) / k if _n(a) and _n(b) else None


def lt_pace(now_value, now_year, slope, target, target_year):
    yrs = target_year - now_year
    if not all(_n(x) for x in (now_value, slope, target)) or yrs <= 0:
        return {"run_rate": None, "needed_per_year": None, "status": "?"}
    run = now_value + slope * yrs
    up = target >= now_value
    ok = run >= target if up else run <= target
    return {"run_rate": run, "needed_per_year": (target - now_value) / yrs, "status": "on pace" if ok else "behind pace"}


def gap(target_change, move):
    return target_change - move if _n(target_change) and _n(move) else None
