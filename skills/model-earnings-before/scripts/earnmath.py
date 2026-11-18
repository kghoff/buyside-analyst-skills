# skills/model-earnings-before/scripts/earnmath.py
"""Every number and rule chapter 13 teaches for the run-up to a print, in one place. context.py, plan.py, build.py
and note.py use it; the Earnings tab's formulas mirror it and verify.py proves they agree after one recalculation.

None means "can't say" (a missing input, or a ratio over a zero or negative base); the tab shows #N/A or "?" there."""
import math
import statistics

HOUSE = {  # the rule's thresholds: yellow cells in band 8 of the tab, the user's to change
    "rr_add": 2.0, "edge_add": 0.10, "edge_trim": -0.10, "rr_trim": 1.0, "hedge_mult": 1.5,
    "margin_range": 0.15, "pe_peak": 0.80, "pe_low": 0.30, "pe_high": 0.70, "rel_perf": 0.05,
}
HOUSE_LABEL = {
    "rr_add": "Add: reward / risk at least", "edge_add": "Add: edge at least",
    "edge_trim": "Trim: edge at or below", "rr_trim": "Trim: reward / risk below (with the set-up net short)",
    "hedge_mult": "Hedge: downside move at least this many times the implied move",
    "margin_range": "Blow-up: operating-margin range over 20 quarters above",
    "pe_peak": "Blow-up: P/E 5-year percentile at or above",
    "pe_low": "Set-up long: P/E 5-year percentile at or below",
    "pe_high": "Set-up short: P/E 5-year percentile at or above",
    "rel_perf": "Set-up: move against SPY since the last print, at least",
}
STANCES = ("add", "hold", "trim", "hedge")
SIDES = ("long", "short", "neutral", "unknown")
SETUP = [  # (id, label on the tab, long set-up, short set-up, code answers it) -- section 13.4's table
    ("value_perf", "Set-up: valuation and recent performance",
     "Underperformed and trades at the low end of its P/E range",
     "Performed well and trades at the high end of its P/E range", True),
    ("consensus", "Set-up: what consensus expects", "Consensus is worried about a weak or decelerating quarter",
     "Consensus expects a strong or accelerating quarter", False),
    ("ratings", "Set-up: recent rating changes", "The stock was recently downgraded",
     "The stock was recently upgraded", False),
    ("previews", "Set-up: sell-side previews", "Sell-side previews have been cautious",
     "Sell-side previews have been optimistic", False),
    ("positioning", "Set-up: positioning", "Other investors are short and/or nervous",
     "Other investors are long and adding", False),
    ("view", "Set-up: our view", "We expect the quarter to be better than expected",
     "We expect the quarter or outlook to be worse than expected", False),
]
RISKS = [("profit_stability", "Risk score: profit stability (odds of a blow-up)"),
         ("liquidity", "Risk score: balance-sheet liquidity"),
         ("valuation_skew", "Risk score: valuation skew"),
         ("rating_change", "Risk score: rating-change potential"),
         ("revision", "Risk score: revision potential")]
CALL_Q = ("beat", "in line", "miss")
CALL_G = ("raise", "hold", "cut", "initiate", "none given")
AGENT_INPUTS = ("up_eps", "up_pe", "down_eps", "down_pe", "p_beat")


def _n(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def div(a, b):
    return a / b if _n(a) and _n(b) and b != 0 else None


def growth(now, then):
    """now / then - 1 over a positive base (growth off a loss or a zero reads backwards). A 2-year stack is
    growth(x_t, x_t-2y): compounding the two yearly rates gives the same number, (1+g1)(1+g0)-1 = x_t/x_t-2y - 1."""
    return now / then - 1 if _n(now) and _n(then) and then > 0 else None


def stack_rates(*g):
    """The chapter's way of writing a stack: (1.050 x 1.062) - 1 = 11.5%."""
    if not g or not all(_n(x) for x in g):
        return None
    return math.prod(1 + x for x in g) - 1


def daily_sigma(annual):
    return annual / math.sqrt(252) if _n(annual) else None


def annual_sigma(daily):
    return daily * math.sqrt(252) if _n(daily) else None


def move(price, pe, eps):
    """The core formula: the case's price (P/E x EPS) against today's."""
    if not (_n(price) and price > 0 and _n(pe) and _n(eps)):
        return None
    return pe * eps / price - 1


def rr(up, down):
    return up / abs(down) if _n(up) and _n(down) and up > 0 and down < 0 else None


def psuc(up, down):
    """The break-even probability of the upside case: |down| / (up + |down|)."""
    return abs(down) / (up + abs(down)) if _n(up) and _n(down) and up > 0 and down < 0 else None


def hockey(yoy, yoy_prev, st2, st2_prev, qoq, qoq_avg):
    """Section 13.5's three red flags on one quarter: yoy growth accelerates, the 2-year stack accelerates, and
    sequential growth beats the 5-year average for that quarter."""
    v = (yoy, yoy_prev, st2, st2_prev, qoq, qoq_avg)
    if not all(_n(x) for x in v):
        return None
    return yoy > yoy_prev and st2 > st2_prev and qoq > qoq_avg


def setup_code(pct, rel, H=HOUSE):
    """The set-up row code answers: cheap and lagging = long; rich and leading = short."""
    if not (_n(pct) and _n(rel)):
        return "unknown"
    if pct <= H["pe_low"] and rel <= -H["rel_perf"]:
        return "long"
    if pct >= H["pe_high"] and rel >= H["rel_perf"]:
        return "short"
    return "neutral"


def net(sides):
    s = list(sides)
    return s.count("long") - s.count("short")


def blowups(margin_range, ttm_ni, ttm_fcf, cash, pe_pct, H=HOUSE):
    """Section 13.4's three kinds of stock that blow up on prints. cash: losing money (TTM net income < 0), or
    burning cash (TTM FCF < 0) with less cash than a year's burn. Mirrors the tab's formulas branch for branch."""
    if not _n(ttm_ni):
        cash_flag = None
    elif ttm_ni < 0:
        cash_flag = True
    elif _n(ttm_fcf) and ttm_fcf < 0:
        cash_flag = (cash < abs(ttm_fcf)) if _n(cash) else None
    else:
        cash_flag = False
    return {"margins": margin_range > H["margin_range"] if _n(margin_range) else None,
            "peak_pe": pe_pct >= H["pe_peak"] if _n(pe_pct) else None, "cash": cash_flag}


def flag_text(b):
    return "?" if b is None else ("yes" if b else "no")


def habitual(vs_mid):
    """Beat the first guide's midpoint in at least 3 of the last 4 years (fewer than 3 years: can't say)."""
    v = [x for x in vs_mid if _n(x)][-4:]
    if len(v) < 3:
        return None
    return sum(1 for x in v if x > 0) >= 3


def stance(rr_, edge, net_, nblow, down, implied, H=HOUSE):
    """The fixed rule (spec): add / trim / hedge / hold. None when R/R or the edge can't be worked out."""
    if not (_n(rr_) and _n(edge)):
        return None
    if rr_ >= H["rr_add"] and edge >= H["edge_add"] and net_ >= 0 and nblow <= 1:
        return "add"
    if edge <= H["edge_trim"] or (rr_ < H["rr_trim"] and net_ < 0):
        return "trim"
    if (_n(implied) and _n(down) and abs(down) >= H["hedge_mult"] * implied - 1e-9) or nblow >= 2:
        return "hedge"
    return "hold"


def base_stats(moves):
    m = [x for x in moves if _n(x)]
    if not m:
        return {"n": 0, "avg_abs": None, "med_abs": None, "up": 0, "down": 0}
    a = [abs(x) for x in m]
    return {"n": len(m), "avg_abs": sum(a) / len(a), "med_abs": statistics.median(a),
            "up": sum(1 for x in m if x > 0), "down": sum(1 for x in m if x < 0)}


def summary(ctx, inp, sides, H=None):
    """Everything the rule needs. inp = {up_eps, up_pe, down_eps, down_pe, p_beat}; sides = the plan's set-up sides
    (the code row takes code's side unless the plan gives one)."""
    H = H or ctx.get("house") or HOUSE
    price = (ctx.get("price") or {}).get("value")
    up = move(price, inp.get("up_pe"), inp.get("up_eps"))
    down = move(price, inp.get("down_pe"), inp.get("down_eps"))
    r, p = rr(up, down), psuc(up, down)
    edge = inp["p_beat"] - p if _n(inp.get("p_beat")) and _n(p) else None
    all_sides = {rid: sides.get(rid) or (ctx["code"]["setup"].get(rid, "unknown") if code else "unknown")
                 for rid, _, _, _, code in SETUP}
    nb = sum(1 for v in ctx["code"]["blowups"].values() if v is True)
    implied = (ctx.get("yahoo") or {}).get("implied_move")
    n_ = net(all_sides.values())
    return {"price": price, "up": up, "down": down, "rr": r, "psuc": p, "edge": edge, "net": n_, "nblow": nb,
            "sides": all_sides, "implied": implied, "rule": stance(r, edge, n_, nb, down, implied, H)}
