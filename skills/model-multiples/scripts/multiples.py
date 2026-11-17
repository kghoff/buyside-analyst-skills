"""The chapter's arithmetic (Ch. 11 "A Multitude of Multiples"), pure functions, no I/O.

NM rule: a multiple whose denominator is missing or <= 0 is None. The tab shows #N/A (a gap in charts). The chapter:
a P/E on a loss is "NM", never a number. Levered metrics pair with equity value (P/E, FCF yield on market cap),
unlevered with EV (EV/Revenue, EV/GP, EV/EBITDA)."""
import statistics


def ratio(num, den):
    if num is None or den is None or den <= 0:
        return None
    return num / den


def fcf_yield(fcf, mcap):
    if fcf is None or mcap is None or mcap <= 0:
        return None
    return fcf / mcap


def six(price, shares, net_debt, rev, gp, ebitda, eps, fcf):
    """Market cap, EV and the multiples for one date. Units: price and EPS per share; the rest in one currency unit."""
    mcap = price * shares if price is not None and shares is not None else None
    ev = mcap + net_debt if mcap is not None and net_debt is not None else None
    return {"mcap": mcap, "ev": ev, "ev_rev": ratio(ev, rev), "ev_gp": ratio(ev, gp), "ev_ebitda": ratio(ev, ebitda),
            "pe": ratio(price, eps), "fcf_yield": fcf_yield(fcf, mcap)}


def window_stats(values, n):
    """Min / max / median / n over the last n points (None skipped); None when n < 1 or the window has no values.
    pct = share of window values <= today (the last point), or None when today is NM. Mirrors the tab's
    AGGREGATE(5|4|12, 6, range), which still works when today is #N/A, and COUNTIF(range, "<="&today) / COUNT(range),
    which becomes #N/A."""
    if not values or n < 1:
        return None
    tail = [v for v in values[-n:] if v is not None]
    if not tail:
        return None
    last = values[-1]
    pct = None if last is None else sum(1 for v in tail if v <= last) / len(tail)
    return {"min": min(tail), "max": max(tail), "median": statistics.median(tail), "pct": pct, "n": len(tail)}


def reverse_pe(price, pe):
    """The chapter's reverse P/E: the earnings power a price implies at a given multiple."""
    return ratio(price, pe)


def median_or_none(vals):
    v = [x for x in vals if x is not None]
    return statistics.median(v) if v else None
