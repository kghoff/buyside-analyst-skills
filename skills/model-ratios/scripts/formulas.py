"""Formula text for every analysis row. Reported columns use the house Excel macro formulas exactly (BuySideMacros.bas
v2.2, not included in this repo: FillGrowth, DoMarginRows, FillTTM). Estimate columns wrap the same maths in IFERROR(...,"") so they stay
blank until forecasts are typed into MOD."""
from openpyxl.utils import get_column_letter as L

NA = '"n.a."'


def a(row, col, lock_row=False):
    return f"{L(col)}{'$' if lock_row else ''}{row}"


def growth(r, c, k):                       # % yoy / % 2 year / % qoq
    return f"=IFERROR({a(r, c)}/{a(r, k)}-1,{NA})"


def margin(r, c, rev):                     # profit line: % margin
    return f"=IFERROR({a(r, c)}/{a(rev, c, True)},{NA})"


def pct_sales(r, c, rev):                  # cost line (stored negative): % of sales
    return f"=IFERROR(-{a(r, c)}/{a(rev, c, True)},{NA})"


def bps(pct_row, c, k):                    # change in a % row, in basis points
    return f"=IFERROR(({a(pct_row, c)}-{a(pct_row, k)})*10000,{NA})"


def incremental(r, c, k, rev):             # extra profit / extra revenue
    return f"=IFERROR(({a(r, c)}-{a(r, k)})/({a(rev, c, True)}-{a(rev, k, True)}),{NA})"


def ttm(r, cols):
    return "=" + "+".join(a(r, k) for k in cols)


def mod_link(mod_row, c, est):
    ref = f"MOD!{a(mod_row, c)}"
    return f'=IF(ISBLANK({ref}),"",{ref})' if est else f"={ref}"


def for_estimate(f):
    """Reported-column formula -> estimate-column version: same maths, blank (not n.a.) when inputs are missing."""
    body = f[1:]
    if body.startswith("IFERROR(") and body.endswith(f",{NA})"):
        body = body[len("IFERROR("):-len(f",{NA})")]
    return f'=IFERROR({body},"")'
