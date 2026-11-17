"""The subject company's point-in-time fundamentals (free path, spec §3.1).

A reported quarter becomes known the day after its full-results release date (Px Events column B): the as-of rule
model-price-history uses, so there's no hindsight. TTM = the last four reported quarters. Each value comes with the
formula behind it (MOD cells) so build.py writes live formulas. Rows are found by label within their statement
section, the way model-dcf finds them."""
import datetime as dt
import re

import openpyxl
from openpyxl.utils import column_index_from_string as ci

from modmap import ModMap

ROLES = [  # (name, section regex, label regex, required): the same anchors as model-dcf/scripts/context.py
    ("rev", r"^income statement:?$", r"^revenue", True),
    ("gp", r"^income statement:?$", r"^gross profit", True),
    ("oi", r"^income statement:?$", r"^operating income", True),
    ("shares", r"^income statement:?$", r"^shares, diluted", True),
    ("eps_gaap", r"^income statement:?$", r"^eps, diluted", True),
    ("eps_ng", r"^non-gaap", r"non-gaap eps, diluted", False),
    ("ebitda_ng", r"^non-gaap", r"^adjusted ebitda", False),
    ("da", r"operating activities", r"depreciation", True),
    ("cash", r"^assets", r"^cash", True),
    ("st", r"^assets", r"short-term (marketable|investments)|marketable securities", False),
]
DEBT = r"debt|notes|borrowing|convertible|credit facilit|commercial paper|finance lease|loan"
NOT_DEBT = r"^total|accounts payable|operating lease|interest payable|accrued|deferred"
FCF = r"free cash flow$"                      # the last match: the FREE CASH FLOW section sits lowest in MOD
METRICS = ("rev", "gp", "ebitda", "eps", "fcf")


def norm(t):
    return " ".join(t.lower().replace("(-)", "").replace("(+)", "").replace("(+/-)", "").split())


def find_rows(mm):
    lines = [(r, k.split(" | ", 1)[0].lower(), norm(re.sub(r" #\d+$", "", k.split(" | ", 1)[1])))
             for k, r in mm.keys.items()]
    out, missing = {}, []
    for name, sec, lab, req in ROLES:
        hit = next((r for r, s, l in lines if re.search(sec, s) and re.search(lab, l)), None)
        if hit is not None:
            out[name] = hit
        elif req:
            missing.append(name)
    fcf = [r for r, s, l in lines if re.search(FCF, l)]
    if fcf:
        out["fcf"] = fcf[-1]
    else:
        missing.append("fcf")
    out["debt"] = [r for r, s, l in lines if "liabilities" in s and re.search(DEBT, l) and not re.search(NOT_DEBT, l)]
    if missing:
        raise SystemExit("model-multiples: MOD has no row for " + ", ".join(missing) + ". It looks for these by label "
                         "within their statement section (as model-dcf does). Check the row labels in the model.")
    return out


def eps_basis(model):
    """The GAAP / non-GAAP choice the user made in model-price-history, read from Px Data's P/E header."""
    ws = openpyxl.load_workbook(model, read_only=True)["Px Data"]
    hdr = next(ws.iter_rows(min_row=4, max_row=4, values_only=True))
    pe = next((str(h) for h in hdr if h and str(h).startswith("P/E")), "")
    return "ng" if "non-gaap" in pe.lower() else "gaap"


def grid(values, maxrow):
    ws = openpyxl.load_workbook(values, read_only=True, data_only=True)["MOD"]
    return {i: list(r) for i, r in enumerate(ws.iter_rows(min_row=1, max_row=maxrow, values_only=True), 1)}


def num(g, row, col):
    line = g.get(row, [])
    k = ci(col) - 1
    v = line[k] if k < len(line) else None
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def release_dates(model):
    ws = openpyxl.load_workbook(model, read_only=True, data_only=True)["Px Events"]
    out = {}
    for r, (a, b) in enumerate(ws.iter_rows(min_row=5, max_col=2, values_only=True), 5):
        if a and isinstance(b, dt.datetime):
            out[str(a).strip()] = (b.date(), r)
    return out


def quarters(model, values):
    """[{label, date, pxe_row, rev|gp|ebitda|eps|fcf|shares|net_debt: (value, formula)}] for reported quarters with a
    release date and four quarters of history. values = a recalculated copy of the model (lo.recalc)."""
    mm = ModMap(model)
    R = find_rows(mm)
    basis = eps_basis(model)
    eps_row = R["eps_ng"] if basis == "ng" and "eps_ng" in R else R["eps_gaap"]
    g = grid(values, max(v for k, v in R.items() if k != "debt") + 5)
    rel = release_dates(model)
    qs = [p for p in mm.order if mm.is_q(p) and not p.endswith("E")]
    ref = lambda p, row: f"MOD!${mm.col(p)}${row}"
    out = []
    for i, p in enumerate(qs):
        if p not in rel or i < 3:
            continue
        last4 = qs[i - 3:i + 1]

        def ttm(rows):
            vals = [num(g, row, mm.col(q)) for q in last4 for row in rows]
            f = "+".join(ref(q, row) for q in last4 for row in rows)
            return (sum(vals) if all(v is not None for v in vals) else None, f)

        if basis == "ng" and "ebitda_ng" in R:
            ebitda = ttm([R["ebitda_ng"]])
        else:
            ebitda = ttm([R["oi"], R["da"]])
        debt = sum(num(g, r, mm.col(p)) or 0 for r in R["debt"])          # a blank debt cell = no balance
        cash = [num(g, R["cash"], mm.col(p)), num(g, R["st"], mm.col(p)) if "st" in R else 0]
        nd_f = ("+".join(ref(p, r) for r in R["debt"]) or "0") + f"-{ref(p, R['cash'])}" + \
            (f"-{ref(p, R['st'])}" if "st" in R else "")
        out.append({"label": p, "date": rel[p][0], "pxe_row": rel[p][1],
                    "rev": ttm([R["rev"]]), "gp": ttm([R["gp"]]), "ebitda": ebitda, "eps": ttm([eps_row]),
                    "fcf": ttm([R["fcf"]]),
                    "shares": (num(g, R["shares"], mm.col(p)), ref(p, R["shares"])),
                    "net_debt": (debt - (cash[0] or 0) - (cash[1] or 0) if cash[0] is not None else None, nd_f)})
    return sorted(out, key=lambda q: q["date"])


def asof(dates, day, strict=True):
    """Index of the last date before `day` (strict: release day itself doesn't count, like MATCH(day-1, dates, 1)),
    or None."""
    k = None
    for i, d in enumerate(dates):
        if d < day if strict else d <= day:
            k = i
        else:
            break
    return k


def weekly(model):
    """[(date, close, Px Data row, close column letter)]: the last trading day of each ISO week."""
    ws = openpyxl.load_workbook(model, read_only=True, data_only=True)["Px Data"]
    hdr = next(ws.iter_rows(min_row=4, max_row=4, values_only=True))
    cc = next(i for i, h in enumerate(hdr) if h and str(h).endswith(" close"))
    from openpyxl.utils import get_column_letter
    out = {}
    for r, row in enumerate(ws.iter_rows(min_row=5, max_col=cc + 1, values_only=True), 5):
        d, c = row[0], row[cc]
        if isinstance(d, dt.datetime) and isinstance(c, (int, float)):
            out[d.date().isocalendar()[:2]] = (d.date(), c, r, get_column_letter(cc + 1))
    return [out[k] for k in sorted(out)]
