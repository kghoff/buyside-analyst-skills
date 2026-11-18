# skills/model-short/scripts/shortmath.py
"""Chapter 12's short math in one place. The Short Check tab's formulas compute the same things; verify.py checks the
recalculated tab against these functions, and plan.py uses them for the rule's verdict.

Moves are from the short seller's side, as positive fractions of today's price: reward = the fall to the reward
price (a gain), risk = the rise to the risk-case price (a loss). None means "not computable" (the tab shows #N/A)."""

HOUSE = {  # the user's defaults (2026-11-18); each is a yellow cell the user owns
    "hurdle": 0.08, "fund": 1000.0, "bps": 50.0, "short_book": 500.0, "crowded_line": 0.10,
    "print_miss": -0.05, "print_pe_slip": 1.0,
}
AGENT_INPUTS = ("reward_eps", "reward_pe", "dream_eps", "dream_pe", "takeout_premium")
BORROW_CASES = (0.05, 0.20)          # shown when the prime broker's rate is unknown
STALE_TOL = 0.03                     # Valuation-tab price vs live price
RR_ALPHA = 1.4                       # exhibit #34's entry R/R
THRESH = {"decel": -0.01, "peak_ratio": 0.95, "capex_da": 1.5, "acq_cfo": 0.25, "fcf_conv": 0.70,
          "revision": -0.01, "pct": 0.70}
TICK = {"yes": "✓", "no": "✗", "unknown": "?"}
SYM = {v: k for k, v in TICK.items()}

ROWS = [  # (id, dimension, label on the tab, computed by code?)  §12.2's FEV bullets
    ("decel", "F", "Decelerating revenue growth (TTM vs a year ago)", True),
    ("pricing", "F", "Weakening pricing power", False),
    ("margin_pressure", "F", "Margin or cost pressure", False),
    ("tailwind", "F", "Mean reversion of a temporary tailwind", False),
    ("share_loss", "F", "Market share loss", False),
    ("incr_margin", "F", "Weak incremental margin, or margin at its peak", True),
    ("capex", "F", "Capex step-up just to hold profit (capex / D&A)", True),
    ("leaky", "F", "Leaky bucket: acquisitions / cash from operations (5 years)", True),
    ("fcf", "F", "Weak FCF: conversion of adjusted net income (5 years)", True),
    ("hope", "E", "Hope dissipation: a product or plan in the stock that may fail", False),
    ("overhang", "E", "A hard-to-disprove overhang", False),
    ("miss", "E", "An upcoming quarterly miss", False),
    ("revisions", "E", "Negative revisions to Street estimates", True),
    ("vs_dcf", "V", "Expensive vs intrinsic value (DCF base)", True),
    ("vs_peers", "V", "Expensive vs closest peers (P/E gap, 5-year percentile)", True),
    ("vs_history", "V", "Expensive vs its own history (P/E, 5-year percentile)", True),
    ("vs_algo", "V", "Expensive vs its growth algorithm (IRR wedge)", True),
]
NEED = {"F": 5, "E": 2, "V": 2}      # at least half the rows
VERDICTS = ("Alpha short", "Filler short", "Watchlist", "No short")
TYPES = ("Temporary tailwind", "Dumpster fire", "Liquidity pothole", "Melting ice cube", "Hope dissipation",
         "Equilibrium to disequilibrium", "Terminal value fear anticipation", "Imminent time-out", "Peak on peak",
         "Decelerating momentum", "Subpar algorithm", "Fraud")
BUCKETS = ("Earnings catalyst", "Temporary tailwind set to dissipate", "Melting ice cube", "Emerging overhang",
           "Mispriced catalyst", "Extrapolation, meet inflection", "Simplicity to complexity", "Growth deceleration",
           "Liquidity runway")


def _n(*xs):
    return all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in xs)


def div(a, b):
    return a / b if _n(a, b) and b != 0 else None


def mul(a, b):
    return a * b if _n(a, b) else None


def roll_path(eps0, g, pe, years=5):
    """[(EPS, price)] for years 1..years with EPS growing at g and the P/E held (exhibit #30)."""
    out, e = [], eps0
    for _ in range(years):
        out.append((e, e * pe))
        e *= 1 + g
    return out


def roll_irr(g, dy):
    """Return if the P/E just rolls forward: EPS growth plus the dividend the holder gets (and the short pays)."""
    return g + dy if _n(g, dy) else None


def wedge(hurdle, irr):
    return hurdle - irr if _n(hurdle, irr) else None


def print_move(miss, pe, slip):
    return (1 + miss) * (pe - slip) / pe - 1 if _n(miss, pe, slip) and pe != 0 else None


def p_fcf(pe, conv):
    return div(pe, conv) if _n(conv) and conv > 0 else None


def reward(price, reward_price):
    return 1 - reward_price / price if _n(price, reward_price) and price else None


def risk_cases(price, dream_price, ntm_growth, takeout):
    return {"dream": dream_price / price - 1 if _n(dream_price, price) and price else None,
            "roll": ntm_growth if _n(ntm_growth) else None,
            "takeout": takeout if _n(takeout) else None}


def risk_of(cases):
    """The largest risk case; the tab's MAX(IFERROR(x,-1), ...)."""
    return max(v if v is not None else -1 for v in cases.values())


def rr(rew, risk):
    return rew / risk if _n(rew, risk) and risk > 0 else None


def borrow_drag(rate, dy):
    return rate + dy if _n(rate, dy) else None


def crowded(pct, line):
    if not _n(pct, line):
        return "n/a"
    return "crowded" if pct >= line else "not crowded"


def var_size(fund, bps, risk, book):
    budget = fund * bps / 10000 if _n(fund, bps) else None
    mx = budget / risk if _n(budget, risk) and risk > 0 else None
    return {"budget": budget, "max_pos": mx, "pct_book": div(mx, book)}


def code_ticks(f):
    """yes / no / unknown for the computed rows, from flat values (see flat()). Mirrors the tab's tick formulas."""
    def t(v, ok):
        return "unknown" if v is None else ("yes" if ok(v) else "no")
    g = f.get
    incr = "unknown" if g("incr") is None or g("opm") is None else (
        "yes" if g("incr") < g("opm") or (g("peak_ratio") or 0) >= THRESH["peak_ratio"] else "no")
    return {
        "decel": t(g("decel"), lambda v: v <= THRESH["decel"]),
        "incr_margin": incr,
        "capex": t(g("capex_da"), lambda v: v >= THRESH["capex_da"]),
        "leaky": t(g("acq_cfo"), lambda v: v >= THRESH["acq_cfo"]),
        "fcf": t(g("fcf_conv"), lambda v: v < THRESH["fcf_conv"]),
        "revisions": t(g("revision"), lambda v: v <= THRESH["revision"]),
        "vs_dcf": t(g("dcf_base"), lambda v: (g("price") or 0) > v),
        "vs_peers": t(g("peer_pct"), lambda v: v >= THRESH["pct"]),
        "vs_history": t(g("pe_pct"), lambda v: v >= THRESH["pct"]),
        "vs_algo": t(g("wedge"), lambda v: v > 0),
    }


def counts(ticks):
    c = {"F": 0, "E": 0, "V": 0}
    for rid, dim, _, _ in ROWS:
        c[dim] += ticks.get(rid) == "yes"
    return c


def passes(ticks):
    c = counts(ticks)
    return {d: c[d] >= NEED[d] for d in NEED}


def verdict(ticks, catalyst_soon, rr_, wedge_):
    """The rule, checked top to bottom (spec 'Verdict rule')."""
    p, c = passes(ticks), counts(ticks)
    if all(p.values()) and catalyst_soon and (rr_ or 0) >= RR_ALPHA:
        return "Alpha short"
    if (wedge_ or 0) > 0 and p["V"] and c["F"] >= 1:
        return "Filler short"
    if sum(p.values()) >= 2:
        return "Watchlist"
    return "No short"


def flat(ctx, hurdle):
    """context.json's metric and link values in one dict, plus price, dividend yield, IRR and wedge."""
    f = {k: (v or {}).get("value") for k, v in ctx["metrics"].items()}
    f.update({k: v.get("value") for k, v in ctx["links"].items() if isinstance(v, dict)})
    sh = ctx.get("short") or {}
    dy = None if sh.get("error") else sh.get("dividend_yield")
    irr = roll_irr(f.get("eps_cagr3"), dy)
    f.update(price=ctx["price"]["value"], dy=dy, irr=irr, wedge=wedge(hurdle, irr))
    return f


def summary(ctx, inp, ticks, catalyst_soon, borrow=None):
    """Every derived number the tab shows, from context.json and plain-number inputs. ticks (row id -> yes / no /
    unknown) replace code's ticks where given."""
    f = flat(ctx, inp["hurdle"])
    price, dy = f["price"], f["dy"]
    ntm_pe = div(price, f.get("ntm_eps"))
    rew_price = mul(inp["reward_eps"], inp["reward_pe"])
    rew = reward(price, rew_price)
    dream_price = mul(inp["dream_eps"], inp["dream_pe"])
    cases = risk_cases(price, dream_price, f.get("ntm_growth"), inp["takeout_premium"])
    risk = risk_of(cases)
    sh = ctx.get("short") or {}
    net_borrow = borrow if _n(borrow) else BORROW_CASES[0]
    out = dict(f, ntm_pe=ntm_pe, reward_price=rew_price, reward=rew, dream_price=dream_price, cases=cases, risk=risk,
               rr=rr(rew, risk), print_move=print_move(inp["print_miss"], ntm_pe, inp["print_pe_slip"]),
               drag=borrow_drag(borrow, dy), drag_low=borrow_drag(BORROW_CASES[0], dy),
               drag_high=borrow_drag(BORROW_CASES[1], dy),
               reward_net=rew - net_borrow - dy if _n(rew, dy) else None,
               size=var_size(inp["fund"], inp["bps"], risk, inp["short_book"]),
               crowded=crowded(None if sh.get("error") else sh.get("short_pct_float"), inp["crowded_line"]),
               p_fcf=p_fcf(f.get("pe_today"), f.get("fcf_conv")),
               path=roll_path(f["ntm_eps"], f["eps_cagr3"], ntm_pe) if _n(f.get("ntm_eps"), f.get("eps_cagr3"), ntm_pe) else None)
    out["code"] = code_ticks(out)
    final = dict(out["code"])
    final.update({k: v for k, v in (ticks or {}).items() if v in TICK})
    out["ticks"], out["counts"], out["passes"] = final, counts(final), passes(final)
    out["verdict"] = verdict(final, catalyst_soon, out["rr"], out["wedge"])
    return out
