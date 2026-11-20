"""Read the deck's model data out of the recalculated values copy, by label or header, never by address.
Pure: grids (lists of rows) in, plain data out; no pptx. build_deck.py draws what these return.
usage: from model_reads import Values, cap_table, typed_prices, estimates_grid, price_history, pe_history, ladder

- cap_table(SUM grid, plan numbers): the "Cap table" block's label column (model-summary layout.py, B:C); the buy and
  no-brainer prices always come from the plan. typed_prices(SUM grid, plan numbers, record) names a SUM price box the
  user typed a different number into.
- estimates_grid(SUM grid): the "Internal estimates" block; its year columns stop at the first header that is blank
  or not year-shaped, because SUM's header row also carries the probability tree (P:U) and the R/R ladder (W:AA).
- price_history(Px Data grid, Px Events grid, ticker): "Date" and "<T> close" columns; "Full-results release date".
- pe_history(Multiples grid): the "WEEKLY DATA" block. When it has "P/E (GAAP)" (a non-GAAP model) that column is
  the subject's line, since the S&P 500 and core-peer P/Es are GAAP (model-multiples compares GAAP with GAAP).
- ladder(Valuation grid): the block whose column-A header is "<n><letter>. Reward / risk ladder ..." (model-valuation
  build.py sec4c_ladder), with Entry / Reward / Risk / R/R headers on that row."""
import datetime as dt
import re

GRID_ROWS = (("Revenue", True), ("Street revenue", True), ("Revenue delta", False), ("EPS (", False),
             ("Street EPS", True), ("Expected Delta", False), ("P/E", True), ("Street P/E", True), ("EV/EBITDA", True))
CAP_ROWS = (  # (shown label, SUM label, exact?, after this SUM label, format, plan key fallback)
    ("Price", "Price", False, None, "px", "price"), ("Market cap ($M)", "Market cap", False, None, "mn", None),
    ("Enterprise value ($M)", "Enterprise value", False, None, "mn", None),
    ("3M ADV ($M)", "3M ADV ($M)", True, None, "mn", None), ("Buy price", "Buy price", True, None, "px", "buy_price"),
    ("No-brainer price", "No-brainer price", True, None, "px", "nobrainer_price"),
    ("3-year target", "3-year target price", True, None, "px", "target_3y"),
    ("3-year IRR", "IRR", True, "3-year target price", "pct", "irr_3y"),
    ("12-month base target", "12-month target", True, None, "px", None),
    ("12-month base return", "% return", True, "12-month target", "spct", "base_ret"),
    ("12-month risk price", "Risk price", True, None, "px", None),
    ("12-month risk return", "% return", True, "Risk price", "spct", "risk_ret"),
    ("Blended reward / risk", "Blended reward / risk", True, None, "x", None))
PLAN_FIRST = ("buy_price", "nobrainer_price")    # SUM's action-price boxes: write-pitch fills them, after the deck
YEAR = re.compile(r"^(FY\s?)?(\d{2}|\d{4})[AE]?$", re.I)            # 2026, 2026E, 2025A, FY26E, FY 2026
LADDER = re.compile(r"^(\d+[a-z]?\.\s*)?reward / risk ladder\b", re.I)


def num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def as_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    n = num(v)
    return dt.date(1899, 12, 30) + dt.timedelta(days=int(n)) if n and n > 1000 else None


class Values:
    """The recalculated copy, each tab read once into a grid of rows (0-based lists); None for a missing tab."""

    def __init__(self, path):
        import openpyxl
        self.wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        self.grids = {}

    def grid(self, name):
        if name not in self.grids:
            real = {n.lower(): n for n in self.wb.sheetnames}.get(name.lower())
            self.grids[name] = [list(r) for r in self.wb[real].iter_rows(values_only=True)] if real else None
        return self.grids[name]

    def close(self):
        self.wb.close()


def cell(g, r, c):
    return g[r][c] if g and 0 <= r < len(g) and 0 <= c < len(g[r]) else None


def text_of(v):
    return v.strip() if isinstance(v, str) else ""


def find(g, pred, rows=None, cols=None):
    """(row, col) of the first cell, row by row, whose text passes pred."""
    for r in rows if rows is not None else range(len(g)):
        for c, v in enumerate(g[r] if r < len(g) else []):
            if (cols is None or c in cols) and pred(text_of(v)):
                return r, c
    return None


def year_text(v):
    """A header as text; a typed year number (2026) as "2026"."""
    return str(int(v)) if num(v) is not None and float(v).is_integer() else text_of(v)


def column_after(g, r0, c):
    """Cells of column c below row r0 until the first empty one: [(row, value)]."""
    out, r = [], r0 + 1
    while cell(g, r, c) not in (None, ""):
        out.append((r, cell(g, r, c)))
        r += 1
    return out


# ------------------------------------------------------------------ formats
def show(v, kind):
    n = num(v)
    if n is None:
        return "n/a" if v not in (None, "") else ""
    return {"px": f"${n:,.2f}", "mn": f"{n:,.0f}", "eps": f"{n:,.2f}", "x": f"{n:,.1f}x", "bps": f"{n:+,.0f}",
            "pct": f"{n:.1%}", "spct": f"{n:+.1%}"}[kind]


def sign_colour(v):
    n = num(v)
    return None if n is None or n == 0 else ("good" if n > 0 else "bad")


def text_sign(t):
    """good / bad from a shown string's sign ('+31%' good, '-15%' or '(15%)' bad); None if unsigned."""
    t = t.strip()
    if t[:1] in "-(−–":
        return "bad"
    return "good" if t[:1] == "+" else None


def grid_kind(lab):
    low = lab.lower()
    if "bps" in low:
        return "bps"
    if "delta" in low:
        return "spct"
    if "p/e" in low or "ev/" in low:
        return "x"
    if "eps" in low:
        return "eps"
    return "pct" if "%" in low or "margin" in low or "yield" in low else "mn"


# ------------------------------------------------------------------ the blocks
def _cap_cells(g):
    """[(CAP_ROWS entry, SUM value or None, found?)] from SUM's "Cap table" block, or None without one."""
    at = g and find(g, lambda t: t.startswith("Cap table"))
    if not at:
        return None
    r0, c = at
    labels = [(r, text_of(cell(g, r, c))) for r in range(r0 + 1, len(g))]
    out = []
    for row in CAP_ROWS:
        _, lab, exact, after, _, _ = row
        start = next((r for r, t in labels if t == after), None) if after else r0
        if start is None:
            continue
        hit = next((r for r, t in labels if r > start and (t == lab if exact else t.startswith(lab))), None)
        out.append((row, cell(g, hit, c + 1) if hit is not None else None, hit is not None))
    return out


def cap_table(g, numbers):
    """([(label, shown, colour)], [plan keys shown in place of a SUM cell]) from SUM's cap table, or None.
    The action prices (PLAN_FIRST) are always the plan's: SUM's boxes are what write-pitch wrote last run (it fills
    them after the deck is built), so on a rerun they are stale. Any other row falls back to the plan when empty."""
    rows = _cap_cells(g)
    if rows is None:
        return None
    out, from_plan = [], []
    for (shown, _, _, _, kind, key), v, hit in rows:
        if key in numbers and (key in PLAN_FIRST or num(v) is None):
            s = numbers[key]["shown"]
            out.append((shown, s, text_sign(s) if kind == "spct" else None))
            from_plan.append(key)
        elif hit:
            out.append((shown, show(v, kind), sign_colour(v) if kind == "spct" else None))
    return out, from_plan


def typed_prices(g, numbers, record=None):
    """Speaker-note lines for a SUM action-price box holding a number that is neither the plan's nor what the last run
    wrote (record: sum_written.json, {label: {"cell", "value"}}; None = no record, so any other number is the user's).
    The pitch shows the plan's price; the line tells the presenter the model says something else."""
    lines = []
    for (shown, lab, _, _, kind, key), v, _ in _cap_cells(g) or []:
        if key not in PLAN_FIRST or key not in numbers or num(v) is None:
            continue
        plan_v, last = num(numbers[key].get("value")), ((record or {}).get(lab) or {}).get("value")
        if plan_v is not None and abs(num(v) - plan_v) < 0.005:
            continue
        if num(last) is not None and abs(num(v) - num(last)) < 1e-9 * max(1.0, abs(num(last))):
            continue                                       # still what the last run wrote: Step 10 replaces it
        lines.append(f"SUM's {lab} box holds {show(v, kind)} (typed by you); the pitch uses {numbers[key]['shown']}")
    return lines


def estimates_grid(g):
    """(header, rows, colours) of SUM's internal-estimates grid, chosen rows only, or None."""
    at = g and find(g, lambda t: t.startswith("Internal estimates"))
    if not at:
        return None
    r0, c0 = at
    yc, c = [], c0 + 1
    while YEAR.match(year_text(cell(g, r0 + 1, c))):      # the grid's own years; blocks further right are not ours
        yc.append(c)
        c += 1
    if not yc:
        return None
    lab = column_after(g, r0 + 1, c0)
    rows, colours = [], {}
    for want, exact in GRID_ROWS:
        hit = next(((r, text_of(t)) for r, t in lab if (text_of(t) == want if exact else text_of(t).startswith(want))),
                   None)
        if not hit:
            continue
        r, t = hit
        kind = grid_kind(t)
        if kind in ("spct", "bps"):
            for j, c in enumerate(yc, 1):
                if sign_colour(cell(g, r, c)):
                    colours[(len(rows), j)] = sign_colour(cell(g, r, c))
        rows.append([t] + [show(cell(g, r, c), kind) for c in yc])
    if not rows:
        return None
    return ["$M except per share"] + [year_text(cell(g, r0 + 1, c)) for c in yc], rows, colours


def price_history(px, ev, ticker):
    """([(date, close)] sorted, release dates or None when Px Events has none) from Px Data / Px Events, or None."""
    hd = px and find(px, lambda t: t == "Date", range(min(15, len(px))))
    if not hd:
        return None
    r0, dc = hd
    heads = [text_of(v) for v in px[r0]]
    want = f"{ticker} close"
    cc = heads.index(want) if want in heads else next(
        (j for j, h in enumerate(heads) if h.endswith(" close") and not h.startswith("SPY")), None)
    if cc is None:
        return None
    pts = sorted((as_date(cell([row], 0, dc)), num(cell([row], 0, cc))) for row in px[r0 + 1:]
                 if as_date(cell([row], 0, dc)) and num(cell([row], 0, cc)) is not None)
    if not pts:
        return None
    at = ev and find(ev, lambda t: t == "Full-results release date", range(min(15, len(ev))))
    rel = [d for d in (as_date(v) for _, v in column_after(ev, *at)) if d] if at else None
    return pts, rel


def pe_history(g):
    """(weeks, {"pe": ys, "S&P 500 P/E": ys, "Core-peer median P/E": ys}, basis) from Multiples' weekly block, or
    None. ys hold None for a gap (#N/A, negative). basis names the subject line, e.g. "GAAP, TTM" or "NTM"."""
    at = g and find(g, lambda t: t == "WEEKLY DATA")
    if not at or at[0] + 1 >= len(g):
        return None
    hr = at[0] + 1
    heads = [text_of(v) for v in g[hr]]
    if "Week" not in heads or "P/E" not in heads:
        return None
    wc, rows = heads.index("Week"), []
    for row in g[hr + 1:]:
        if not as_date(cell([row], 0, wc)):
            break
        rows.append(row)
    weeks = [as_date(cell([r], 0, wc)) for r in rows]

    def col(h):
        ys = [num(cell([r], 0, heads.index(h))) for r in rows]
        return [y if y is not None and y > 0 else None for y in ys]
    out = {h: col(h) for h in ("S&P 500 P/E", "Core-peer median P/E") if h in heads and any(col(h))}
    gaap = "P/E (GAAP)" in heads and any(col("P/E (GAAP)"))
    out["pe"] = col("P/E (GAAP)" if gaap else "P/E")
    top = " ".join(text_of(v) for r in g[:4] for v in r if isinstance(v, str))
    period = "NTM" if re.search(r"\bNTM\b", top) else "TTM" if re.search(r"Trailing|TTM", top) else ""
    basis = ", ".join(x for x in ("GAAP" if gaap else "", period) if x) or "as on the Multiples tab"
    return (weeks, out, basis) if any(out["pe"]) else None


def ladder(g):
    """[(step, entry, reward, risk, rr)] from Valuation's reward / risk ladder block, or None."""
    at = g and find(g, lambda t: bool(LADDER.match(t)), cols={0})
    if not at:
        return None
    r0, c0 = at
    heads = [text_of(v) for v in g[r0]]
    if not all(h in heads for h in ("Entry", "Reward", "Risk", "R/R")):
        return None
    cols = [heads.index(h) for h in ("Entry", "Reward", "Risk", "R/R")]
    out, r = [], r0 + 1
    while num(cell(g, r, c0)) is not None:
        out.append([num(cell(g, r, c0))] + [cell(g, r, c) for c in cols])
        r += 1
    return out or None
